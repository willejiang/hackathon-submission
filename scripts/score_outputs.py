"""Score produced STEP files against the practice facts and reference views.

Same instruments the pipeline uses internally, applied to a file on disk:
independent measurement of the re-imported B-rep, the facts comparison, and the
eight-view silhouette overlap. This is how an agent run is judged, and how two
architectures are compared on identical terms.

    python scripts/score_outputs.py --dir .runs/agent/outputs
    python scripts/score_outputs.py --dir artifacts/outputs --cases 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_cad import cad, factsgen, imagecmp, raster  # noqa: E402
from agentic_cad.gt import load_case  # noqa: E402

INPUTS = REPO_ROOT / "artifacts/inputs"


IOU_GATE = 0.93


def score(path: Path, case_dir: Path) -> dict:
    gt = load_case(case_dir)
    shape = cad.reopen_step(path)
    measured = factsgen.measure(shape)
    comparison = factsgen.compare(gt, measured)
    rendered = raster.render_all(shape)
    images = imagecmp.compare_all(case_dir / "images", rendered)
    # The pipeline accepts on facts AND projection. Report both, or a part the
    # harness would reject shows up green here: test_case_7 matches its volume to
    # 0.00004% yet scores 0.853 on the orthographic views.
    projection_ok = images.mean_iou_ortho >= IOU_GATE
    gating_failures = [c.name for c in comparison.gating_failures]
    if not projection_ok:
        gating_failures = gating_failures + [f"projection(ortho {images.mean_iou_ortho:.3f})"]
    return {
        "case": gt.name,
        "bytes": path.stat().st_size,
        "gating_ok": comparison.ok and projection_ok,
        "gating_failures": gating_failures,
        "volume_ratio": (
            measured["volume_mm3"] / gt.volume if gt.volume else None
        ),
        "iou_ortho": round(images.mean_iou_ortho, 4),
        "iou_iso": round(images.mean_iou_iso, 4),
        "iou_all": round(images.mean_iou, 4),
        "worst_view": images.worst[0].stem if images.worst else "",
        "worst_iou": round(images.worst[0].iou, 4) if images.worst else 0.0,
        "table": comparison.render(),
        "views": images.render(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, required=True)
    parser.add_argument("--cases", default="")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    wanted = {c.strip().removeprefix("test_case_") for c in args.cases.split(",") if c.strip()}
    rows = []
    for path in sorted(args.dir.glob("*.stp")):
        stem = path.stem
        if wanted and stem.removeprefix("test_case_") not in wanted:
            continue
        case_dir = INPUTS / stem
        if not (case_dir / "description.md").is_file():
            print(f"skip {stem}: no inputs")
            continue
        try:
            rows.append(score(path, case_dir))
        except Exception as error:  # noqa: BLE001
            print(f"{stem}: FAILED to score: {type(error).__name__}: {error}")

    if not rows:
        print(f"no scoreable .stp in {args.dir}")
        return 1

    print(f"{'case':16}{'bytes':>8}{'vol/exp':>9}{'IoUortho':>10}{'IoUiso':>8}{'IoUall':>8}  gates")
    for r in rows:
        vol = f"{r['volume_ratio']:.4f}" if isinstance(r["volume_ratio"], float) else "-"
        gates = "PASS" if r["gating_ok"] else "FAIL(" + ",".join(r["gating_failures"]) + ")"
        print(
            f"{r['case']:16}{r['bytes']:>8}{vol:>9}{r['iou_ortho']:>10.4f}"
            f"{r['iou_iso']:>8.4f}{r['iou_all']:>8.4f}  {gates}"
        )

    print(f"\nmean IoU over {len(rows)} case(s): "
          f"{sum(r['iou_all'] for r in rows) / len(rows):.4f}")

    if args.verbose:
        for r in rows:
            print(f"\n=== {r['case']}  (worst view {r['worst_view']} at {r['worst_iou']:.3f})")
            print(r["table"])
            print(r["views"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
