"""Drive the reconstruction with DeepSeek Harness as the agent.

The pipeline in `agent.py` is a code harness: the model emits one module per
attempt and code does the rest. This script runs the other architecture, the one
the challenge actually rewards: a real agent with tools, which can look at a view,
write a module, measure it, look again, and decide what to change.

Per case:

  install the tools plugin into a dedicated profile   (once)
  run `dsh --profile headless "<task>"` with cwd = a per-case workspace
  the agent loads the skill, reads the eight PNGs with `read_image`, writes
  solution.py, and calls cad_build / cad_verify / cad_render / cad_submit
  collect the STEP from the output directory and time the whole thing

Subagents are forbidden by the task text and by `--disallowed-tools`-style
instruction: one agent, one part, no delegation.

    python scripts/run_agent.py --setup
    python scripts/run_agent.py --cases 3
    python scripts/run_agent.py --timeout 900
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INPUTS = REPO_ROOT / "artifacts/inputs"
PLUGIN_DIR = REPO_ROOT / "dsh-plugin"
DEFAULT_HOME = REPO_ROOT / ".runs" / "dsh-home"
DEFAULT_OUT = REPO_ROOT / ".runs" / "agent" / "outputs"
# Deliberately OUTSIDE the repo: inside it, `glob`/`grep`/`read` can walk up and
# find the hand-written reference fixture under tests/specs, which would let the
# agent copy an answer instead of reconstructing the part.
WORKSPACES = REPO_ROOT.parent / "cad-agent-work"
PROFILE = "headless"
PLUGIN_ROW = "agentic-cad-tools"


def find_dsh() -> str:
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/DeepSeek Harness/resources/runtime/cli/bin/dsh.cmd",
        Path(os.environ.get("LOCALAPPDATA", "")) / "DeepSeek Harness/resources/runtime/cli/bin/dsh.cmd",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("dsh")
    if found:
        return found
    raise SystemExit("cannot find the dsh CLI; open DeepSeek Harness Desktop once, or set PATH")


def dsh_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    for path in (Path.home() / ".dsh" / ".credentials.yaml",):
        if path.is_file():
            match = re.search(r"DEEPSEEK_API_KEY:\s*(\S+)", path.read_text(encoding="utf-8", errors="ignore"))
            if match:
                return match.group(1)
    raise SystemExit("no DeepSeek key: set DEEPSEEK_API_KEY or keep ~/.dsh/.credentials.yaml")


def child_env(home: Path, case: Path | None, out: Path) -> dict[str, str]:
    env = dict(os.environ)
    src = REPO_ROOT / "src"
    env.update(
        {
            "DSH_HOME": str(home),
            "DEEPSEEK_API_KEY": dsh_key(),
            "AGENTIC_CAD_PYTHON": sys.executable,
            "AGENTIC_CAD_SRC": str(src),
            "AGENTIC_CAD_OUTPUT": str(out),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    if case is not None:
        env["AGENTIC_CAD_CASE_DIR"] = str(case)
    # The package is not pip-installed in a development checkout, so every child that
    # runs `python -m agentic_cad.cli` needs src on the import path.
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{src}{os.pathsep}{existing}" if existing else str(src)
    )
    # The sandbox on this machine leaves no usable OS temp dir for children.
    tmp = REPO_ROOT / ".tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    env["TMP"] = env["TEMP"] = str(tmp)
    return env


def setup(home: Path, out: Path) -> None:
    """Install the plugin into the dedicated profile and enable its row."""
    home.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    dsh = find_dsh()

    print(f"installing {PLUGIN_DIR.name} into profile '{PROFILE}' under {home}")
    install = subprocess.run(
        [dsh, "plugin", "--profile", PROFILE, "add", str(PLUGIN_DIR)],
        env=child_env(home, None, out),
        capture_output=True,
        text=True,
        timeout=900,
    )
    print((install.stdout or "").strip()[-1500:])
    if install.returncode != 0:
        print((install.stderr or "").strip()[-2000:], file=sys.stderr)
        raise SystemExit(f"plugin install failed with {install.returncode}")

    # The row ships disabled; enable it only in this profile.
    patch = home / "profiles" / PROFILE / "cordis.patch.yml"
    body = patch.read_text(encoding="utf-8") if patch.is_file() else ""
    marker = f"- id: {PLUGIN_ROW}\n  disabled: false"
    if marker not in body:
        entry = f"# enabled by scripts/run_agent.py\n{marker}\n"
        # A fresh profile writes the user layer as the empty flow sequence `[]`,
        # and a block sequence appended after `[]` is not valid YAML. Replace the
        # whole document when there is nothing but that placeholder.
        meaningful = "\n".join(
            line for line in body.splitlines() if line.strip() and not line.lstrip().startswith("#")
        ).strip()
        if meaningful in ("", "[]"):
            patch.write_text(entry, encoding="utf-8")
        else:
            with patch.open("a", encoding="utf-8") as handle:
                handle.write("\n" + entry)
        print(f"enabled row '{PLUGIN_ROW}' in {patch}")
    print("setup done\n")


def task_prompt(case: str) -> str:
    return f"""\
Reconstruct the mechanical part for test case `{case}`.

First call `cad_case_info` for this case, then load the `cad-reconstruction` skill
and follow it exactly. `cad_case_info` returns the authoritative facts.json, the
design brief, and the absolute paths of the eight rendered views; read those PNGs
with `read_image` and reason about their silhouettes.

Write your module to `solution.py` in the current workspace, then use `cad_build`,
`cad_verify` and `cad_render` to check it, and `cad_submit` once the gating facts
pass.

Rules:
- facts.json and the design brief are authoritative. Do not modify or reinterpret them.
- every dimension must come from facts.json, the brief, or a formula over them.
- exactly one connected solid, millimetres, bounding-box minimum at the origin.
- do NOT use subagent, subagent_fork, workflow, send_message or list_agents.
  Do the work yourself in this session.
- do not create goals or todo lists; work directly.
- read ONLY the case directory that `cad_case_info` reports, and the files you create
  in your own workspace. Do not search the repository for reference solutions,
  fixtures or examples: if you find one, do not use it.

Stop after `cad_submit` succeeds, or after you have submitted your best candidate.
"""


def run_case(case: str, home: Path, out: Path, timeout: float, model: str | None) -> dict:
    dsh = find_dsh()
    workspace = WORKSPACES / case
    workspace.mkdir(parents=True, exist_ok=True)
    for stale in workspace.glob("*.py"):
        stale.unlink()
    log_path = WORKSPACES / f"{case}.log"
    # Remove any earlier artifact, or a leftover file from a previous run counts
    # as a success for a run that produced nothing.
    previous = out / f"{case}.stp"
    if previous.is_file():
        previous.unlink()

    cmd = [dsh, "--profile", PROFILE, task_prompt(case)]
    started = time.time()
    try:
        with log_path.open("w", encoding="utf-8") as handle:
            proc = subprocess.run(
                cmd,
                cwd=str(workspace),
                env=child_env(home, INPUTS / case, out),
                stdout=handle,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
        rc = proc.returncode
        timed_out = False
    except subprocess.TimeoutExpired:
        rc = -1
        timed_out = True
    elapsed = time.time() - started

    step = out / f"{case}.stp"
    forced = None
    # A missing STEP scores zero, so never let a case end without one. If the agent
    # ran out of time -- or crashed -- before calling cad_submit, export whatever
    # solution.py it had reached. On test_case_6 the run hit the timeout and
    # submitted nothing, which is the worst possible outcome for a case whose
    # geometry was at least partly there.
    if not step.is_file():
        candidate = None
        for name in ("solution.py", "solution_full.py", "sol_best.py"):
            path = workspace / name
            if path.is_file() and path.stat().st_size > 0:
                candidate = path
                break
        if candidate is None:
            others = sorted(workspace.glob("*.py"), key=lambda p: p.stat().st_size, reverse=True)
            candidate = others[0] if others else None
        if candidate is not None:
            forced = export_candidate(case, candidate, home, out)

    return {
        "case": case,
        "elapsed_s": elapsed,
        "rc": rc,
        "timed_out": timed_out,
        "bytes": step.stat().st_size if step.is_file() else 0,
        "forced_submit": forced,
        "log": log_path,
        "workspace": workspace,
    }


def export_candidate(case: str, candidate: Path, home: Path, out: Path) -> dict:
    """Build and export a candidate module after the agent has stopped.

    Deliberately a separate python -m invocation rather than a retry inside the
    session: the session is gone by this point, and the module only has to build and
    be one solid for the file to be worth submitting.
    """
    env = child_env(home, INPUTS / case, out)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "agentic_cad.cli", "submit", json.dumps({"path": str(candidate)})],
            cwd=str(candidate.parent),
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "from": candidate.name, "error": "export timed out"}
    payload = {}
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                pass
    error = payload.get("error") or payload.get("report")
    if not payload and (proc.stderr or "").strip():
        error = (proc.stderr or "").strip()[-800:]
    return {
        "ok": bool(payload.get("ok")),
        "from": candidate.name,
        "error": error,
        "bytes": payload.get("bytes", 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="", help="comma separated; default all")
    parser.add_argument("--timeout", type=float, default=900.0, help="per-case seconds")
    parser.add_argument("--home", type=Path, default=DEFAULT_HOME)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--setup", action="store_true", help="(re)install the plugin, then exit")
    parser.add_argument("--model", default=None, help="advisory only; set the model via the profile")
    args = parser.parse_args()

    if args.setup:
        setup(args.home, args.out)
        return 0

    # Setup is idempotent and cheap when already installed.
    setup(args.home, args.out)

    cases = sorted(
        (p.name for p in INPUTS.glob("test_case_*") if (p / "description.md").is_file()),
        key=lambda n: int(n.removeprefix("test_case_")),
    )
    if args.cases:
        wanted = {c.strip() for c in args.cases.split(",") if c.strip()}
        cases = [c for c in cases if c in wanted or c.removeprefix("test_case_") in wanted]
    if not cases:
        print("no cases", file=sys.stderr)
        return 2

    print(f"cases: {len(cases)}   timeout: {args.timeout:.0f}s per case   home: {args.home}")
    results = []
    started = time.time()
    for case in cases:
        print(f"\n=== {case}")
        result = run_case(case, args.home, args.out, args.timeout, args.model)
        results.append(result)
        status = "submitted" if result["bytes"] else ("TIMEOUT" if result["timed_out"] else "MISSING")
        print(f"  {result['elapsed_s']:.1f}s  {status}  {result['bytes']} bytes  rc={result['rc']}")
    total = time.time() - started

    results.sort(key=lambda r: r["elapsed_s"], reverse=True)
    print("\n=== summary, slowest first ===")
    print(f"{'case':16}{'seconds':>9}{'bytes':>9}  status")
    for r in results:
        status = "submitted" if r["bytes"] else ("TIMEOUT" if r["timed_out"] else "MISSING")
        print(f"{r['case']:16}{r['elapsed_s']:9.1f}{r['bytes']:>9}  {status}")
    produced = sum(1 for r in results if r["bytes"])
    print(f"\ntotal {total:.1f}s   submitted {produced}/{len(results)}")
    if results:
        print(f"slowest: {results[0]['case']} at {results[0]['elapsed_s']:.1f}s")
    summary = {"total_s": round(total, 1), "cases": [
        {k: (str(v) if isinstance(v, Path) else v) for k, v in r.items()} for r in results
    ]}
    (REPO_ROOT / ".runs" / "agent").mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / ".runs" / "agent" / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return 0 if produced == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
