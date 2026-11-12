"""Run the dsh agent for every case inside the submission container.

`scripts/main.py` hands over to this module when AGENTIC_CAD_MODE=agent (the
Dockerfile sets it). It reproduces how the committed outputs were made -- the dsh
agent with the agentic-cad tools plugin -- under the re-run's constraints:

- 20 minutes wall clock for the whole run: all cases run in parallel (MAX_WORKERS),
  each with a hard deadline, and the dsh process group is killed when it is reached;
- a missing file scores zero: every case first gets a box of the facts.json envelope,
  the agent overwrites it through cad_submit, and if the agent never submitted, the
  newest solution.py in its workspace is exported after it stops;
- non-root, read-only image: DSH_HOME, workspaces and temp files live under /tmp.

Environment (handed over in <team>.env):
  DEEPSEEK_API_KEY            the key dsh uses; falls back to OPENAI_API_KEY
  AGENTIC_CAD_BUDGET_S        whole-run budget, default 1080 (organisers kill at 1200)
  AGENTIC_CAD_MAX_WORKERS     cases in parallel, default 9
  AGENTIC_CAD_EXPORT_RESERVE  seconds kept back for the forced export, default 150

The plugin is installed at build time into /opt/dsh-home (`--setup-template`).
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_agent  # noqa: E402  (task prompt, plugin setup)

TEMPLATE_HOME = Path(os.environ.get("DSH_TEMPLATE_HOME", "/opt/dsh-home"))
SCRATCH = Path(os.environ.get("AGENTIC_CAD_SCRATCH", "/tmp/agentic-cad"))
PROFILE = run_agent.PROFILE
_print_lock = threading.Lock()


def log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def api_key() -> str:
    return (os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()


def child_env(home: Path, case_dir: Path | None, out: Path) -> dict[str, str]:
    env = dict(os.environ)
    tmp = SCRATCH / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    env.update({
        "HOME": str(SCRATCH / "home"),
        "DSH_HOME": str(home),
        "DEEPSEEK_API_KEY": api_key(),
        "AGENTIC_CAD_PYTHON": sys.executable,
        "AGENTIC_CAD_SRC": str(REPO_ROOT / "src"),
        "AGENTIC_CAD_OUTPUT": str(out),
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "TMP": str(tmp), "TEMP": str(tmp), "TMPDIR": str(tmp),
    })
    (SCRATCH / "home").mkdir(parents=True, exist_ok=True)
    if case_dir is not None:
        env["AGENTIC_CAD_CASE_DIR"] = str(case_dir)
    return env


def setup_template() -> None:
    """Build time: install the tools plugin into TEMPLATE_HOME and enable it."""
    os.environ.setdefault("DEEPSEEK_API_KEY", "build-time-placeholder")
    run_agent.setup(TEMPLATE_HOME, SCRATCH / "setup-out")


def prepare_home() -> Path:
    home = SCRATCH / "dsh-home"
    if home.exists():
        shutil.rmtree(home)
    if TEMPLATE_HOME.is_dir():
        shutil.copytree(TEMPLATE_HOME, home, symlinks=True)
    else:  # local run without the image: install now
        home.mkdir(parents=True)
        run_agent.setup(home, SCRATCH / "setup-out")
    return home


def write_box(case_dir: Path, target: Path) -> bool:
    """Envelope box from facts.json, so a case never ends without a file."""
    try:
        facts = json.loads((case_dir / "facts.json").read_text())
        bb = facts["bounding_box_mm"]
        from build123d import Align, Box, export_step

        box = Box(float(bb["x"]), float(bb["y"]), float(bb["z"]), align=(Align.MIN, Align.MIN, Align.MIN))
        export_step(box, str(target))
        return True
    except Exception as exc:  # never let the fallback itself stop the run
        log(f"[{case_dir.name}] box fallback failed: {type(exc).__name__}: {exc}")
        return False


def _signature(path: Path) -> tuple[int, int] | None:
    return (path.stat().st_size, path.stat().st_mtime_ns) if path.is_file() else None


def export_workspace(case_dir: Path, workspace: Path, home: Path, out: Path, timeout: float) -> str:
    candidates = [workspace / n for n in ("solution.py", "solution_full.py", "sol_best.py")]
    candidates += sorted(workspace.glob("*.py"), key=lambda p: p.stat().st_mtime, reverse=True)
    for cand in candidates:
        if not cand.is_file() or cand.stat().st_size == 0 or cand.name.startswith("measure"):
            continue
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "agentic_cad.cli", "submit", json.dumps({"path": str(cand)})],
                cwd=str(workspace), env=child_env(home, case_dir, out),
                capture_output=True, text=True, timeout=max(timeout, 10),
            )
        except subprocess.TimeoutExpired:
            return f"export of {cand.name} timed out"
        for line in (proc.stdout or "").splitlines():
            if line.strip().startswith("{"):
                try:
                    if json.loads(line).get("ok"):
                        return f"exported {cand.name}"
                except json.JSONDecodeError:
                    pass
        return f"export of {cand.name} failed"
    return "no solution.py to export"


def run_case(case_dir: Path, home: Path, out: Path, deadline: float, reserve: float) -> dict:
    name = case_dir.name
    target = out / f"{name}.stp"
    workspace = SCRATCH / "work" / name
    workspace.mkdir(parents=True, exist_ok=True)
    box_written = write_box(case_dir, target)
    box_sig = _signature(target)

    started = time.time()
    agent_time = deadline - reserve - started
    status = "skipped (no time)"
    if agent_time > 30:
        log_path = SCRATCH / "logs" / f"{name}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w") as handle:
            proc = subprocess.Popen(
                ["dsh", "--profile", PROFILE, run_agent.task_prompt(name)],
                cwd=str(workspace), env=child_env(home, case_dir, out),
                stdout=handle, stderr=subprocess.STDOUT, start_new_session=True,
            )
            try:
                rc = proc.wait(timeout=agent_time)
                status = f"agent exited rc={rc}"
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
                status = "agent timed out"

    submitted = _signature(target) != box_sig and target.is_file()
    export = ""
    if not submitted:
        remaining = deadline - time.time() - 10
        if remaining > 15:
            export = export_workspace(case_dir, workspace, home, out, remaining)
            submitted = _signature(target) != box_sig
    source = "agent" if submitted else ("box" if box_written else "none")
    detail = export or ("agent submitted" if submitted else "nothing submitted")
    log(f"[{name}] {status}; {detail}; output={source} "
        f"{target.stat().st_size if target.is_file() else 0} bytes; {time.time() - started:.0f}s")
    return {"case": name, "status": status, "export": export, "output": source,
            "elapsed_s": round(time.time() - started, 1)}


def run(input_dir: Path, output_dir: Path) -> int:
    started = time.time()
    budget = _env_float("AGENTIC_CAD_BUDGET_S", 1080.0)
    reserve = _env_float("AGENTIC_CAD_EXPORT_RESERVE", 150.0)
    workers = int(_env_float("AGENTIC_CAD_MAX_WORKERS", 9))
    deadline = started + budget
    output_dir.mkdir(parents=True, exist_ok=True)

    cases = sorted((p for p in input_dir.glob("test_case_*") if (p / "description.md").is_file()),
                   key=lambda p: int(p.name.removeprefix("test_case_")))
    log(f"agent mode: {len(cases)} cases, {workers} in parallel, budget {budget:.0f}s, "
        f"dsh {shutil.which('dsh') or 'NOT FOUND'}, key {'set' if api_key() else 'MISSING'}")

    if not api_key() or not shutil.which("dsh"):
        log("cannot run the agent; writing envelope boxes only")
        for case_dir in cases:
            write_box(case_dir, output_dir / f"{case_dir.name}.stp")
        return 0

    home = prepare_home()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(lambda c: run_case(c, home, output_dir, deadline, reserve), cases))

    missing = [c.name for c in cases if not (output_dir / f"{c.name}.stp").is_file()]
    agent = sum(r["output"] == "agent" for r in results)
    log(f"done in {time.time() - started:.0f}s: {agent}/{len(cases)} from the agent, "
        f"{len(cases) - agent - len(missing)} boxes, {len(missing)} missing {missing or ''}")
    return 0


if __name__ == "__main__":
    if "--setup-template" in sys.argv:
        setup_template()
        sys.exit(0)
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--input_dir", type=Path, default=REPO_ROOT / "artifacts/inputs")
    p.add_argument("--output_dir", type=Path, default=REPO_ROOT / "artifacts/outputs")
    a = p.parse_args()
    sys.exit(run(a.input_dir, a.output_dir))
