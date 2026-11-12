"""Development-only: run every test case in its own process, in parallel, timed.

Not part of the submission. `scripts/main.py` stays the entrypoint the organisers
call; this tool exists to explore the practice set quickly and to measure where the
20 minute budget actually goes.

Each case runs as an isolated OS process, so:

  * one slow or crashing case cannot affect the others, and the timing per case is
    real rather than blended;
  * no subagent, no agent loop, no shared session state -- the pipeline is a plain
    sequence of API calls and CAD operations, and this runner never delegates.

Time is measured but not enforced (`--budget-s` defaults to a day), which is the
point of a first exploratory run: find out what it costs before deciding what to
cut.

    python scripts/run_parallel.py --jobs 9 --attempts 2
    python scripts/run_parallel.py --cases 1,3 --jobs 2
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INPUTS = REPO_ROOT / "artifacts/inputs"
MAIN = REPO_ROOT / "scripts" / "main.py"

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-flash"


def discover_cases() -> list[str]:
    cases = [p.name for p in INPUTS.glob("test_case_*") if (p / "description.md").is_file()]
    return sorted(cases, key=lambda n: int(n.removeprefix("test_case_")))


def read_dsh_key() -> str | None:
    """Pull DEEPSEEK_API_KEY out of the local harness credentials, if present.

    Only used so a developer does not have to retype the key. In the container the
    value comes from the handed-over <team>.env instead.
    """
    candidates = [
        Path(os.environ.get("DSH_HOME", "")) / ".credentials.yaml",
        Path.home() / ".dsh" / ".credentials.yaml",
    ]
    for path in candidates:
        if not path.is_file():
            continue
        match = re.search(r"DEEPSEEK_API_KEY:\s*(\S+)", path.read_text(encoding="utf-8", errors="ignore"))
        if match:
            return match.group(1)
    return None


def writable_temp() -> Path:
    """A TMP dir a sandboxed child can actually use.

    `tempfile.gettempdir()` fails inside the DSH sandbox on this machine, which
    breaks both pip and anything that shells out to it, so the runner hands its
    children an explicit directory under the repo.
    """
    path = REPO_ROOT / ".tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_case(case: str, args: argparse.Namespace, env: dict[str, str]) -> dict:
    started = time.time()
    cmd = [
        sys.executable,
        str(MAIN),
        "--cases", case,
        "--input_dir", str(INPUTS),
        "--output_dir", str(args.out_dir),
        "--work_dir", str(args.work_dir / case),
    ]
    log_path = args.work_dir / f"{case}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as handle:
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env, stdout=handle, stderr=subprocess.STDOUT)
    elapsed = time.time() - started

    output = args.out_dir / f"{case}.stp"
    # main.py nests its own case directory under the --work_dir it is given, so
    # look in both places rather than assuming one layout.
    accepted = None
    attempts = None
    iou = None
    timings = {}
    for summary in (args.work_dir / case / case / "case_summary.json", args.work_dir / case / "case_summary.json"):
        if not summary.is_file():
            continue
        import json

        try:
            data = json.loads(summary.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        accepted = data.get("accepted")
        attempts = data.get("attempts")
        iou = data.get("mean_iou_ortho")
        timings = data.get("timings_s") or {}
        break

    return {
        "case": case,
        "elapsed_s": elapsed,
        "returncode": proc.returncode,
        "bytes": output.stat().st_size if output.is_file() else 0,
        "accepted": accepted,
        "attempts": attempts,
        "iou": iou,
        "timings": timings,
        "log": log_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="", help="comma separated; default all")
    parser.add_argument("--jobs", type=int, default=9)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--iou", type=float, default=0.93)
    parser.add_argument("--budget-s", type=float, default=86400.0, help="per-case wall clock; effectively unlimited")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / ".runs" / "outputs")
    parser.add_argument("--work-dir", type=Path, default=REPO_ROOT / ".runs" / "work")
    parser.add_argument("--from-dsh", action="store_true", help="read the API key from ~/.dsh/.credentials.yaml")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.work_dir.mkdir(parents=True, exist_ok=True)

    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key and args.from_dsh:
        api_key = read_dsh_key() or ""
    if not api_key:
        print("no API key: set OPENAI_API_KEY or pass --from-dsh", file=sys.stderr)
        return 2

    env = dict(os.environ)
    env.update(
        {
            "OPENAI_BASE_URL": os.environ.get("OPENAI_BASE_URL", DEEPSEEK_BASE_URL),
            "OPENAI_API_KEY": api_key,
            "OPENAI_MODEL": args.model,
            "AGENTIC_CAD_ATTEMPTS": str(args.attempts),
            "AGENTIC_CAD_IOU": str(args.iou),
            "AGENTIC_CAD_BUDGET_S": str(args.budget_s),
            "AGENTIC_CAD_WORK_DIR": str(args.work_dir),
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )
    # The spec-directory escape hatch must not leak in, or the run would replay the
    # hand-written reference instead of asking the model.
    env.pop("AGENTIC_CAD_SPEC_DIR", None)
    tmp = writable_temp()
    env["TMP"] = env["TEMP"] = str(tmp)

    cases = discover_cases()
    if args.cases:
        wanted = {c.strip() for c in args.cases.split(",") if c.strip()}
        cases = [c for c in cases if c in wanted or c.removeprefix("test_case_") in wanted]
    if not cases:
        print("no cases found", file=sys.stderr)
        return 2

    print(f"model   : {env['OPENAI_MODEL']} @ {env['OPENAI_BASE_URL']}")
    print(f"cases   : {len(cases)}  jobs: {args.jobs}  attempts: {args.attempts}")
    print(f"outputs : {args.out_dir}")
    print(f"logs    : {args.work_dir.resolve() / '<case>.log'}")
    print()

    started = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {pool.submit(run_case, case, args, env): case for case in cases}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            verdict = "ACCEPTED" if result["accepted"] else ("no summary" if result["accepted"] is None else "best-effort")
            iou_text = f"IoU {result['iou']:.3f}" if isinstance(result["iou"], float) else "IoU n/a"
            print(
                f"  done {result['case']:14} {result['elapsed_s']:7.1f}s  "
                f"{verdict:12} {iou_text:11} {result['bytes']:>7} bytes  rc={result['returncode']}"
            )
    total = time.time() - started

    results.sort(key=lambda r: r["elapsed_s"], reverse=True)
    print("\n=== summary, slowest first ===")
    print(f"{'case':16}{'seconds':>9}{'llm':>7}{'build':>7}{'render':>8}{'att':>5}{'IoU':>7}{'bytes':>9}  status")
    for r in results:
        iou_text = f"{r['iou']:.3f}" if isinstance(r["iou"], float) else "-"
        attempts = str(r["attempts"]) if r["attempts"] is not None else "-"
        status = "accepted" if r["accepted"] else ("produced" if r["bytes"] else "MISSING")
        t = r["timings"]
        print(
            f"{r['case']:16}{r['elapsed_s']:9.1f}"
            f"{t.get('llm', 0):7.1f}{t.get('build', 0):7.1f}{t.get('render', 0):8.1f}"
            f"{attempts:>5}{iou_text:>7}{r['bytes']:>9}  {status}"
        )

    produced = sum(1 for r in results if r["bytes"] > 0)
    accepted = sum(1 for r in results if r["accepted"])
    print(f"\ntotal wall clock: {total:.1f}s   produced {produced}/{len(results)}   accepted {accepted}/{len(results)}")

    if results:
        slowest = results[0]
        print(f"\nslowest case    : {slowest['case']} at {slowest['elapsed_s']:.1f}s")
        t = slowest["timings"]
        if t:
            print(
                f"  its breakdown : llm {t.get('llm', 0):.1f}s  build {t.get('build', 0):.1f}s  "
                f"measure {t.get('measure', 0):.1f}s  render {t.get('render', 0):.1f}s  "
                f"diagnose {t.get('diagnose', 0):.1f}s"
            )
        summed = sum(r["elapsed_s"] for r in results)
        print(f"  all cases sum : {summed:.0f}s (this is the one-process cost the 20 min limit applies to)")
    return 0 if produced == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
