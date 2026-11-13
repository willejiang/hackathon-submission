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
  AGENTIC_CAD_BUDGET_S        whole-run budget, default 1110 (organisers kill at 1200)
  AGENTIC_CAD_MAX_WORKERS     cases in parallel, default 9
  AGENTIC_CAD_EXPORT_RESERVE  seconds kept back for the forced export, default 120

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
        env["AGENTIC_CAD_SNAPSHOT_DIR"] = str(SCRATCH / "snapshots" / case_dir.name)
    return env


def setup_template() -> None:
    """Build time: install the tools plugin into TEMPLATE_HOME and enable it."""
    os.environ.setdefault("DEEPSEEK_API_KEY", "build-time-placeholder")
    run_agent.setup(TEMPLATE_HOME, SCRATCH / "setup-out")


def prepare_home(name: str) -> Path:
    """One dsh home per case: parallel dsh processes must not share session state."""
    home = SCRATCH / "dsh-home" / name
    if home.exists():
        shutil.rmtree(home)
    home.parent.mkdir(parents=True, exist_ok=True)
    if TEMPLATE_HOME.is_dir():
        shutil.copytree(TEMPLATE_HOME, home, symlinks=True)
        # pnpm links the plugin with a RELATIVE symlink, which breaks when the home
        # is copied to a different depth: dsh then skips the bundle and the agent
        # runs without any cad_* tool. Re-point it at the absolute plugin directory.
        link = home / "profiles" / PROFILE / "node_modules" / "@agentic-cad" / "dsh-tools"
        if link.is_symlink() or link.exists():
            link.unlink()
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(REPO_ROOT / "dsh-plugin")
    else:  # local run without the image: install now
        home.mkdir(parents=True)
        run_agent.setup(home, SCRATCH / "setup-out")
    return home


def _solid_count(path: Path, timeout: float = 10) -> int:
    """Number of solids in a valid STEP, within the remaining time budget."""
    code = ("import sys\nfrom build123d import import_step\n"
            "s = import_step(sys.argv[1])\n"
            "print('SOLIDS', len(s.solids()) if s.is_valid else -1)")
    try:
        proc = subprocess.run([sys.executable, "-c", code, str(path)],
                              capture_output=True, text=True, timeout=max(.1, timeout))
        for line in (proc.stdout or "").splitlines():
            if line.startswith("SOLIDS "):
                return int(line.split()[1])
    except Exception:
        pass
    return -1


def ensure_single_solid(case_dir: Path, target: Path, deadline: float) -> str:
    """Last gate before a case ends: the file must hold exactly one solid.

    A STEP with shells but no solid, or with several solids, scores zero. Seen in a
    Docker run on an unseen part: the agent submitted a compound of 13 shells. Fall
    back to the newest snapshot that is one solid, then to the envelope box.
    """
    # A slow STEP reader must not turn six fallback attempts into nine minutes.
    deadline = min(deadline, time.time() + 20)
    def valid(path: Path) -> bool:
        remaining = deadline - time.time() - 1
        return remaining > .1 and _solid_count(path, min(10, remaining)) == 1

    try:
        if target.is_file() and valid(target):
            return ""
        snap_dir = SCRATCH / "snapshots" / case_dir.name
        steps = sorted(snap_dir.glob("*.stp"), key=lambda p: p.stat().st_mtime, reverse=True) if snap_dir.is_dir() else []
        for step in steps[:6]:
            if time.time() >= deadline - 1:
                break
            if valid(step):
                shutil.copyfile(step, target)
                return f"output was not one solid; replaced by snapshot {step.name}"
        write_box(case_dir, target)
        return "output was not one solid; replaced by the envelope box"
    except Exception as exc:
        return f"single-solid check failed: {type(exc).__name__}: {exc}"


def write_box(case_dir: Path, target: Path) -> bool:
    """Envelope box from facts.json, so a case never ends without a file."""
    try:
        from agentic_cad.gt import load_case

        facts = load_case(case_dir).facts
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


def _proxy_error(row: dict, facts: dict) -> float | None:
    """Distance of a built solid from facts.json: envelope, volume, through passages."""
    try:
        if row.get("solids") != 1:
            return None
        err = 0.0
        target_bb = facts.get("bounding_box_mm") or {}
        bb = row.get("bounding_box_mm") or {}
        for axis in ("x", "y", "z"):
            if axis in target_bb and axis in bb:
                err += abs(float(bb[axis]) - float(target_bb[axis])) / max(float(target_bb[axis]), 1e-6)
        if facts.get("volume_mm3") and row.get("volume_mm3"):
            import math

            err += abs(math.log(float(row["volume_mm3"]) / float(facts["volume_mm3"])))
        genus_t, genus = facts.get("through_holes_genus"), row.get("through_holes_genus")
        if genus_t is not None and genus is not None:
            err += 0.02 * min(abs(int(genus) - int(genus_t)), 10)
        return err
    except Exception:
        return None


def best_snapshot(case_dir: Path, workspace: Path, home: Path, out: Path, deadline: float,
                  preserve_existing: bool = False) -> str:
    """After the agent stopped without submitting: ship the best solid it ever built.

    Modules still on disk are built once more without the provenance check, so a
    module the agent could not get past provenance still counts. The envelope box
    stays only if nothing that built is closer to facts.json than the box is.
    """
    name = case_dir.name
    target = out / f"{name}.stp"
    snap_dir = SCRATCH / "snapshots" / name
    modules = sorted((p for p in workspace.glob("*.py") if p.stat().st_size > 0 and not p.name.startswith("measure")),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    for module in modules[:3]:
        remaining = deadline - time.time() - 60
        if remaining < 15:
            break
        try:
            subprocess.run(
                [sys.executable, "-m", "agentic_cad.cli", "snapshot", json.dumps({"path": str(module)})],
                cwd=str(workspace), env=child_env(home, case_dir, out),
                capture_output=True, text=True, timeout=min(remaining, 20),
            )
        except subprocess.TimeoutExpired:
            pass

    try:
        from agentic_cad.gt import load_case

        facts = load_case(case_dir).facts
    except Exception:
        facts = {}
    rows = []
    index = snap_dir / "index.jsonl"
    if index.is_file():
        for line in index.read_text().splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            err = _proxy_error(row, facts)
            if err is not None and (snap_dir / row["file"]).is_file():
                rows.append((err, row["file"]))
    if not rows:
        return "no built solid to ship"
    remaining = deadline - time.time() - 10
    if remaining > 5:
        try:
            subprocess.run(
                [sys.executable, "-m", "agentic_cad.candidate_rank", "--case-dir", str(case_dir),
                 "--snapshot-dir", str(snap_dir), "--output", str(target),
                 "--deadline", str(time.time() + remaining - 1)],
                env=child_env(home, case_dir, out), capture_output=True, text=True, timeout=remaining,
            )
        except subprocess.TimeoutExpired:
            pass
        finally:
            target.with_suffix(".candidate").unlink(missing_ok=True)
        ranking = snap_dir / "ranking.json"
        if ranking.is_file():
            result = json.loads(ranking.read_text())
            if result.get("selected"):
                return f"geometry-ranked {result['evaluated']} candidates; kept {result['selected']} (loss {result['quality']:.3f})"
    if preserve_existing:
        return "kept the agent's submitted solid; geometric ranking unavailable"
    err, file = min(rows)
    bb = facts.get("bounding_box_mm") or {}
    box_err = None
    if facts.get("volume_mm3") and all(k in bb for k in "xyz"):
        import math

        box_err = abs(math.log(float(bb["x"]) * float(bb["y"]) * float(bb["z"]) / float(facts["volume_mm3"])))
    if box_err is not None and err >= box_err:
        return f"best of {len(rows)} snapshots (error {err:.3f}) is no better than the box ({box_err:.3f})"
    shutil.copyfile(snap_dir / file, target)
    return f"shipped snapshot {file} of {len(rows)} (proxy error {err:.3f}, box {box_err if box_err is None else round(box_err, 3)})"


def run_case(case_dir: Path, out: Path, deadline: float, reserve: float) -> dict:
    name = case_dir.name
    home = prepare_home(name)
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
                # --add-dir: let the session's sandbox write the output directory too
                ["dsh", "--profile", PROFILE, "--add-dir", str(out), run_agent.task_prompt(name, agent_time)],
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
    if not submitted or (SCRATCH / "snapshots" / name / "index.jsonl").is_file():
        export = best_snapshot(case_dir, workspace, home, out, deadline - 20, preserve_existing=submitted)
        submitted = _signature(target) != box_sig
    repaired = ensure_single_solid(case_dir, target, deadline)
    if repaired:
        export = f"{export}; {repaired}" if export else repaired
        submitted = "snapshot" in repaired
    log_file = SCRATCH / "logs" / f"{name}.log"
    if log_file.is_file() and "skipping profile bundle" in log_file.read_text(errors="ignore")[:4000]:
        status += " (WARNING: cad tools plugin did not load)"
    source = "agent" if submitted else ("box" if box_written else "none")
    detail = export or ("agent submitted" if submitted else "nothing submitted")
    log(f"[{name}] {status}; {detail}; output={source} "
        f"{target.stat().st_size if target.is_file() else 0} bytes; {time.time() - started:.0f}s")
    return {"case": name, "status": status, "export": export, "output": source,
            "elapsed_s": round(time.time() - started, 1)}


def run(input_dir: Path, output_dir: Path) -> int:
    started = time.time()
    budget = _env_float("AGENTIC_CAD_BUDGET_S", 1110.0)
    reserve = _env_float("AGENTIC_CAD_EXPORT_RESERVE", 120.0)
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

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        results = list(pool.map(lambda c: run_case(c, output_dir, deadline, reserve), cases))

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
