# Two architectures, one measurement layer

The repository contains two ways to reconstruct a part. They share every
deterministic component — measurement, rendering, comparison, export — and differ
only in **who decides what to try next**.

| | code harness (`scripts/main.py`) | agent (`scripts/run_agent.py`) |
|---|---|---|
| who decides | Python | the model |
| how it sees a view | images attached to the request | `read_image` on demand |
| what it can measure | fixed sequence per attempt | any `cad_*` tool, any number of times |
| attempts | bounded by a counter | bounded by wall clock |
| cost per case | ~40 s (one completion) | ~125 s and up (many turns) |
| failure feedback | numbers + a classification | numbers + its own reading of the views |

Neither is strictly better. The code harness is cheap and predictable, which
matters when nine parts must fit in twenty minutes. The agent can look at a
silhouette, form a hypothesis, measure it, look again, and change its mind, which
matters when the brief leaves something genuinely ambiguous.

## The split of responsibility

This is the part that matters, and it is the same in both:

```
model        decides geometry, interprets evidence, chooses what to change
code         builds, measures, renders, compares, exports -- exactly
```

The model is never asked to compute a volume, estimate a silhouette overlap, or
remember a gate threshold. Those are Python, they are identical across runs, and
they return numbers instead of prose. The model is never told what to try next
either; `cad_verify` says *what disagrees*, and the skill says *what that kind of
disagreement usually means*.

## The agent path

### Components

```
dsh-plugin/                     @agentic-cad/dsh-tools
  cordis.patch.yml              one host-plane row, disabled by default
  lib/index.js                  five tools + runtime skill registration
  skills/cad-reconstruction/    the discipline, shipped in the package
src/agentic_cad/cli.py          the tool backend: python -m agentic_cad.cli <tool>
scripts/run_agent.py            install the plugin, run one `dsh --profile headless` per case
scripts/score_outputs.py        score any .stp against the facts and the reference views
```

### Tools

| tool | returns |
|---|---|
| `cad_case_info` | facts.json, the brief, the eight view paths, camera conventions |
| `cad_build` | provenance result, then volume / bbox / solids / faces / edges / genus |
| `cad_verify` | per-fact expected vs measured, gating rows marked |
| `cad_render` | per-view silhouette IoU, overfill, underfill, aspect |
| `cad_submit` | writes the case's STEP file |

Every tool shells out to `python -m agentic_cad.cli`, so the tool implementations
are the same functions the code harness calls. There is one measurement layer, not
two.

The agent writes its module to `solution.py` with its own editor and passes the
path. Handing a few hundred lines of Python around as a JSON string is a failure
mode with no upside.

### Skill

`cad-reconstruction` is registered at mount time from `skills/cad-reconstruction/SKILL.md`
through `ctx.skills.register`, so it reaches every session regardless of which agent
preset that session picked. It carries: ground-truth immutability, the order of
work, the view trust ranking, the module contract and the provenance rules the
tools enforce, and a table mapping each symptom in `cad_verify` output to a likely
cause.

### Isolation, learned the hard way

Two things went wrong on the first run and are now enforced:

1. **The skill registered but would not load.** The registry requires a string
   `source` on the loaded definition; without it the catalog lists the skill and
   every load fails with `loaded skill "<name>" source must be a string`. Fixed by
   passing `source: "runtime"`.
2. **The agent found the hand-written reference fixture.** The workspace was
   inside the repository, so `glob`/`read` could walk up into `tests/specs` and the
   agent copied the answer for `test_case_3`. The workspace now lives outside the
   repository (`../cad-agent-work/`) and the task text forbids searching the repo
   for solutions. A run before that change is not evidence.

### Running it

```bash
python scripts/run_agent.py --setup            # install the plugin, enable its row
python scripts/run_agent.py --cases 3          # one case
python scripts/run_agent.py --timeout 900      # all nine, 15 min per case
python scripts/score_outputs.py --dir .runs/agent/outputs --verbose
```

`run_agent.py` creates a dedicated harness home (`.runs/dsh-home`) so the plugin
never touches an ordinary profile, and it deletes any previous `.stp` for a case
before running, so a stale artifact cannot be counted as a success.

Subagents are forbidden in the task text: one agent, one part.

### Credentials

The agent runs on **DeepSeek Harness** with **`deepseek-flash`**, which is a
reasoning model *and* multimodal — it reads the eight PNG views through the
`read_image` tool. That is the configuration the results below were produced with.

The API key is read from `DEEPSEEK_API_KEY` in the environment, or — for local
development only — from `~/.dsh/.credentials.yaml`, the harness's own credential
store that already existed before this pipeline. It is **never written to disk by
this repository**: it is passed to child processes through the environment and
nothing here serialises it. Verified by scanning every file in the working tree,
including the untracked scratch directories, for the key value.

In the submission image the key comes from the handed-over `<team>.env`, as the
challenge intends. Do not commit it, and do not put it in the Dockerfile.

## Results so far

## Scoring, so the two paths are comparable

`score_outputs.py` re-imports each produced STEP, measures the B-rep from scratch,
and compares it with the facts and the eight reference silhouettes. The numbers are
therefore independent of how the part was produced.

Baseline for `test_case_3`, all three approaches:

| approach | volume / expected | ortho IoU | iso IoU | time |
|---|---|---|---|---|
| hand-written reference spec | 1.0000 | 0.989 | 0.993 | 2.5 s |
| code harness (`main.py`) | 1.0000 | 0.989 | 0.993 | ~41 s |
| agent (`dsh` + `deepseek-flash`) | 1.0000 | 0.989 | 0.993 | ~126 s |

All three converge on the same solid. That is the expected result for a part whose
brief is unambiguous: the brief is a complete parametric specification, so the
interesting question is not whether the easy case works but how the two
architectures behave as the brief gets thinner and the geometry gets harder.

`test_case_1` is where they separate. Its brief is wrong: the front recess is
described as a cylinder centred at `Y = 7.0`, and taken literally the volume comes
out roughly a third low. The text-only path could not reconcile it. The agent read
the left and right silhouettes, placed the recess axis on the front face instead,
fitted the back-view arcs to `r = 12.5` centred on the bolt holes, and predicted the
total volume to 0.17 mm³:

| case | volume / expected | surface area | genus | gating | mean IoU |
|---|---|---|---|---|---|
| `test_case_1` (agent) | 1.0000 (9195.9 vs 9195.9) | 4538.53 vs 4538.5 | 2 | PASS | 0.9945 |
| `test_case_3` (agent) | 1.0000 | 32104.99 vs 32105.0 | 1 | PASS | 0.9896 |

That is the case for paying for vision — and also a warning: the skill says a
conflict between a picture and the brief is your misreading of the picture. Here it
was not. The rule should be "the numbers in facts.json win, and a brief that
contradicts them is a defect worth recording", not "the brief is always right".

## Where the twenty minutes go

Measured on `test_case_3` with `deepseek-flash`:

- **agent path**: ~126 s, almost all of it model turns. Each turn re-sends the
  conversation; the model is a reasoning model and spends thousands of hidden
  tokens per turn.
- **code harness**: ~41 s, of which ~38 s is one completion and ~3 s is the CAD
  kernel and the rasteriser.

Nine cases at 126 s is 19 minutes, which is the whole budget with nothing left for
the harder parts. Nine at 41 s is 6 minutes. The agent path is the more capable one
and the one that will not fit; the practical answer is a hybrid — let the agent work
while its own budget lasts, then fall back to the deterministic loop for the rest.

That hybrid is not implemented. It is the obvious next step, and the numbers above
are why.
