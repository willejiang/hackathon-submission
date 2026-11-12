"""Competition entrypoint.

The organisers run exactly this:

    python scripts/main.py --input_dir /data/inputs --output_dir /data/outputs

so the CLI contract is fixed: those two arguments, one `<case>.stp` per input case
in `--output_dir`, nothing else written there. Extra flags exist for local
debugging only and are never required.

Time budget: the whole run has 20 minutes wall clock. A global deadline is set
below that, and each remaining case gets an equal share of what is left, so one
hard part cannot starve the rest -- a missing file scores zero for that case, and
three mediocre files beat one perfect one plus two zeros.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_cad import agent  # noqa: E402  (path is set up above)
from agentic_cad.gt import load_case  # noqa: E402

DEFAULT_INPUTS = REPO_ROOT / "artifacts/inputs"
DEFAULT_OUTPUTS = REPO_ROOT / "artifacts/outputs"

# 20 minutes is the hard limit; stop starting work well before it so that the
# last case still has time to export its best candidate.
DEFAULT_BUDGET_S = 1020.0
MIN_CASE_SECONDS = 45.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--output_dir", type=Path, default=DEFAULT_OUTPUTS)
    # local debugging only
    parser.add_argument("--cases", default="", help="comma separated test_case names (debug)")
    parser.add_argument("--work_dir", type=Path, default=None, help="scratch directory (debug)")
    parser.add_argument("--budget_s", type=float, default=None, help="override the wall-clock budget")
    return parser.parse_args()


def discover_cases(input_dir: Path) -> list[Path]:
    cases = [p for p in input_dir.glob("test_case_*") if (p / "description.md").is_file()]
    return sorted(cases, key=lambda p: int(p.name.removeprefix("test_case_")))


def pick_work_root(explicit: Path | None) -> Path:
    """A writable scratch root, chosen without assuming a usable OS temp dir."""
    if explicit is not None:
        explicit.mkdir(parents=True, exist_ok=True)
        return explicit.resolve()

    configured = os.environ.get("AGENTIC_CAD_WORK_DIR", "").strip()
    if configured:
        path = Path(configured)
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    candidates = []
    try:
        import tempfile

        candidates.append(Path(tempfile.gettempdir()) / "agentic_cad")
    except Exception:  # noqa: BLE001 - an unusable temp dir is not fatal
        pass
    candidates.append(REPO_ROOT / ".agentic_cad_work")

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return candidate.resolve()
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("no writable scratch directory; set AGENTIC_CAD_WORK_DIR")


def main(args: argparse.Namespace) -> int:
    started = time.time()
    budget = args.budget_s if args.budget_s is not None else float(
        os.environ.get("AGENTIC_CAD_BUDGET_S", "") or DEFAULT_BUDGET_S
    )
    deadline_global = started + budget

    args.output_dir.mkdir(parents=True, exist_ok=True)
    work_root = pick_work_root(args.work_dir)

    cases = discover_cases(args.input_dir)
    if args.cases:
        wanted = {name.strip() for name in args.cases.split(",") if name.strip()}
        cases = [c for c in cases if c.name in wanted or c.name.removeprefix("test_case_") in wanted]
    if not cases:
        print(f"no test cases found under {args.input_dir}")
        return 1

    client = agent.make_client()
    if client is None:
        print("note: no LLM configured; set OPENAI_BASE_URL / OPENAI_MODEL (and OPENAI_API_KEY)")
        if not os.environ.get("AGENTIC_CAD_SPEC_DIR"):
            print("note: and no AGENTIC_CAD_SPEC_DIR, so no candidate can be produced")

    print(f"cases: {len(cases)}  budget: {budget:.0f}s  work: {work_root}")

    results = []
    for position, case_dir in enumerate(cases):
        remaining_cases = len(cases) - position
        remaining_time = max(0.0, deadline_global - time.time())
        share = max(MIN_CASE_SECONDS, remaining_time / remaining_cases)
        case_deadline = min(deadline_global, time.time() + share)

        gt = load_case(case_dir)
        output_path = args.output_dir / f"{gt.name}.stp"
        work_dir = work_root / gt.name

        print(f"\n=== {gt.name}  ({gt.bbox[0]:g} x {gt.bbox[1]:g} x {gt.bbox[2]:g} mm, "
              f"share {share:.0f}s)")
        try:
            result = agent.reconstruct(
                gt,
                images_dir=case_dir / "images",
                output_path=output_path,
                work_dir=work_dir,
                deadline=case_deadline,
                client=client,
            )
        except Exception as error:  # noqa: BLE001 - one case must not kill the run
            print(f"  {gt.name}: FAILED with {type(error).__name__}: {error}")
            results.append((gt.name, False))
            continue

        print(f"  {result.summary()}")
        for note in result.notes[:6]:
            print(f"    note: {note}")
        results.append((gt.name, output_path.is_file()))

    # ---- final gate: the submission interface itself -------------------------
    print("\n=== submission check")
    ok = True
    for case_dir in cases:
        path = args.output_dir / f"{case_dir.name}.stp"
        exists = path.is_file()
        size = path.stat().st_size if exists else 0
        print(f"  {'OK  ' if exists and size > 0 else 'MISS'} {path.name}  {size} bytes")
        ok = ok and exists and size > 0

    extra = sorted(
        p.name for p in args.output_dir.iterdir()
        if p.name != ".gitkeep" and not p.name.endswith(".stp")
    )
    if extra:
        print(f"  WARNING unexpected files in the output directory: {extra}")

    print(f"\ntotal {time.time() - started:.1f}s; {'all outputs present' if ok else 'some outputs missing'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(parse_args()))
