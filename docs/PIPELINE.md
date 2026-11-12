# Reconstruction pipeline

What runs between `python scripts/main.py --input_dir <in> --output_dir <out>` and
one `test_case_<n>.stp` per part.

The design follows one observation about this task: **the written brief and
`facts.json` are a near-complete parametric specification, and the rendered views
are secondary evidence.** So the loop is driven by *numbers*, and the images are
used to confirm or question what the numbers already say. A model that can be
argued out of a 12 % volume error cannot be argued out of a silhouette, and a
human reading eight 1024 px renders cannot measure 0.05 mm.

---

## Stages

```
per case
  ├─ load        facts.json + description.md  (read-only, never rewritten)
  ├─ propose     LLM → one Python module:  derive(facts) → build(p)
  ├─ provenance  static check: every literal traces to the facts or is structural
  ├─ build       build123d → exactly one connected solid, mm, bbox min at origin
  ├─ measure     independent B-rep measurement → compare with facts.json
  ├─ render      8 silhouettes from the stated camera directions
  ├─ compare     normalised silhouette IoU / overfill / underfill / aspect
  └─ classify    name the cause, feed it into the next attempt (bounded)
                 export the best candidate seen, always
```

| module | role |
|---|---|
| `gt.py` | loads the authoritative inputs, renders the fact sheet, lists every known number |
| `prompts.py` | competition system prompt, per-case user prompt, diagnosis prompt |
| `llm.py` | OpenAI-compatible client, vision attachments, code extraction |
| `provenance.py` | AST check of the generated module |
| `cad.py` | executes the module, enforces one solid, normalises, exports STEP |
| `factsgen.py` | measures the produced B-rep and compares it with `facts.json` |
| `meshutil.py` | in-memory triangulation and genus |
| `raster.py` | orthographic silhouette rasteriser, eight camera bases |
| `imagecmp.py` | reference mask extraction, normalisation, overlap metrics |
| `diagnose.py` | deterministic failure classification |
| `agent.py` | the loop, the budget, the best-candidate bookkeeping |

---

## The four gates

Only these decide whether a candidate is accepted:

| gate | test | gating |
|---|---|---|
| submission | exactly one `.stp` per case, one solid in it | yes |
| geometry | valid B-rep, one connected solid | yes |
| facts | `bounding_box_mm`, `volume_mm3`, `solids` all match | yes |
| projection | mean orthographic silhouette IoU ≥ `AGENTIC_CAD_IOU` (default 0.93) | yes |

Everything else `factsgen` reports — surface area, genus, face and edge counts, the
face-type histogram, the bore inventory — is **advisory**. That distinction is
deliberate and was earned: face and edge counts depend on how the reference model
was *constructed*, not on the solid it represents. The flanged bushing in
`test_case_3` reproduces at volume 177662.587 mm³ against 177662.6 and silhouette
IoU 0.987–0.993, while its face count is 6 against the facts' 9, because the
reference was built as two fused bodies and the pipeline builds one revolve. Same
solid, different topology. Gating on face count would have rejected a perfect
part.

---

## Provenance, and how it is enforced

Every parameter is classified as `grounded`, `derived`, `estimated` or `assumed`.
`provenance.py` makes the first two the only cheap options:

- `derive()` may contain a numeric literal **only** when that value appears in
  `facts.json` or `description.md`, or is structural (`0 1 2 3 -1 90 180 270`).
- `build()` may contain **only** structural literals. Every dimension passes
  through the parameter dict.
- `open`, `eval`, `exec`, `export_step`, process spawning and imports outside
  `build123d`/`math`/`itertools`/`numpy`/`typing` are rejected outright.

Writing `12.7` where the brief says the diameter is 25.4 fails the check, and the
message says to write `d["boss_d"] / 2` instead. That strictness is the point:
a folded constant is how a derivation quietly stops being a derivation.

Violations are reported with line numbers and become the next attempt's prompt, so
the model is told which line is wrong rather than reminded of the rule.

---

## View conventions, and how they were established

The challenge states the six orthographic cameras exactly. The two isometric ones
are named (`iso_front_right_top` from +X, −Y, +Z) but not their up-vector, and the
reference framings are not uniform.

Rather than guess, the conventions were measured against the reference renders:

- **Orthographic framing.** Only the largest silhouette extent occupies 986 px of
  the 1024 px frame, with a 19 px margin, centred, fitted independently per view.
  Confirmed on two parts: `test_case_1` (19 × 19 × 50.8) gives 0.3753 against
  19/50.8 = 0.3740, and `test_case_3` (21.59 × 132.08 × 132.08) gives 0.1663
  against 0.1635.
- **Isometric direction.** A flanged bushing is rotationally symmetric, so it
  cannot determine an isometric orientation on its own; a basis fitted to it put a
  standing plate's long axis nearly horizontal. The direction was therefore solved
  from the *projected aspect ratios of all nine cases* at once, then confirmed by
  overlap against known-correct geometry: predicted aspect 0.8410, reference
  0.8410.
- **Image orientation.** The first two reference parts were both symmetric about
  their mid-height, which hid a vertical flip in the rasteriser until the
  isolated views exposed it. `tests/test_pipeline.py::test_front_view_is_not_vertically_flipped`
  builds a deliberately asymmetric part so this cannot regress.

Because the two framing conventions differ, the comparison **normalises both sides**
before computing overlap: each mask is cropped to its own bounding box, scaled so
its largest extent fills the same fraction of the canvas, and centred, with aspect
ratio preserved. The test therefore measures shape and proportion, not framing.
Absolute size is the facts gate's job, which is a far better instrument for it.

---

## Failure classification

`diagnose.py` names a cause, in the vocabulary the prompt uses, so the retry gets a
direction instead of a diff:

| label | meaning |
|---|---|
| `formula_error` | an equation is wrong |
| `formula_missing` | two dimensions were independent numbers; write the relation |
| `constraint_missing` | a described feature was never modelled |
| `constraint_wrong` | a feature exists but contradicts the brief |
| `constraint_excess` | material or a feature the brief does not describe |
| `image_misread` | a visual conclusion was wrong |
| `topology_error` | not one valid connected solid |
| `build_error` | the code did not build |

The classifier is deterministic and needs no model, so the loop still produces a
usable diagnosis when the endpoint is down. When one is configured, the model's
reading is layered on top and the deterministic evidence is appended to it.

---

## Running it

With an endpoint (this is the submission configuration):

```bash
export OPENAI_BASE_URL=... OPENAI_API_KEY=... OPENAI_MODEL=...
python scripts/main.py --input_dir artifacts/inputs --output_dir artifacts/outputs
```

Without one, or to reproduce the reference fixtures:

```bash
AGENTIC_CAD_SPEC_DIR=tests/specs python scripts/main.py --cases test_case_3
```

| env var | default | effect |
|---|---|---|
| `AGENTIC_CAD_ATTEMPTS` | 3 | attempts per case |
| `AGENTIC_CAD_IOU` | 0.93 | projection gate threshold (orthographic mean) |
| `AGENTIC_CAD_BUDGET_S` | 1020 | whole-run wall clock |
| `AGENTIC_CAD_SPEC_DIR` | — | load `<case>.py` instead of calling the model |
| `AGENTIC_CAD_WORK_DIR` | temp | scratch directory for per-attempt artifacts |
| `OPENAI_IMAGE_MAX_SIDE` | 768 | downscale before sending views |

Budget: the hard limit is 20 minutes for the whole run. The runner keeps a global
deadline below that and gives each remaining case an equal share of what is left,
so one hard part cannot starve the others. Every case exports its best candidate
even when nothing was accepted, because a missing file scores zero.

---

## Status: what is verified and what is not

Verified locally, without a model:

- `tests/test_pipeline.py` — 21 tests: renderer orientation, all eight camera bases
  against the references, provenance accept/reject cases, the single-solid
  contract, independent measurement, bore-vs-shaft classification, unmeasurable
  values reported as `unverified` instead of `pass`, STEP round trip.
- End to end on `test_case_3` from `tests/specs/test_case_3.py`:
  volume 177662.587 mm³ vs 177662.6, surface area 32104.99 vs 32105.0, bounding box
  exact, genus 1, bore inventory correct, silhouette IoU 0.987–0.993 on all eight
  views, 2.5 s per case.

**Not** verified here:

- The model-facing half. No endpoint was available in this environment, so the
  propose → diagnose → retry loop has never run against a real model. The prompts,
  the client and the loop are written and their deterministic halves are tested,
  but the first real run is on the team's VM.
- Any case other than `test_case_3`. Only that one has a hand-authored reference
  spec, so only its `.stp` is committed. The other eight outputs require a run with
  the endpoint configured; until then `tests/test_submission_format.py::test_output_exists`
  fails for them by design.
- Rendering time on the largest parts. `test_case_9` (508 × 255.94 × 511.87 mm) is
  far heavier than the bushing; the rasteriser reports anything over 20 s, and the
  budget accounting assumes a few seconds per view.

These are the first things to check on the VM, in this order: one case end to end
with the real endpoint, then all nine with timing, then the `uv lock` refresh.
