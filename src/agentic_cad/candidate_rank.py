"""Choose saved CAD candidates using independent geometry and rendered views.

This is a local surrogate, not the organisers' scorer. Each improved selection
is exported immediately so a deadline cannot discard work already evaluated.
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import time
from pathlib import Path


def quality(measured: dict, facts: dict, iou: float | None) -> float:
    """Lower is better; equal volume is not evidence of equal geometry."""
    if measured.get("solids") != 1:
        return math.inf
    loss = 0.0
    for axis, expected in (facts.get("bounding_box_mm") or {}).items():
        actual = (measured.get("bounding_box_mm") or {}).get(axis)
        if expected and actual is not None:
            loss += abs(actual / expected - 1)
    for key, weight in (("volume_mm3", 1.0), ("surface_area_mm2", 0.5)):
        expected, actual = facts.get(key), measured.get(key)
        if expected and actual is not None:
            if actual <= 0 or not math.isfinite(actual):
                return math.inf
            loss += weight * abs(math.log(actual / expected))
    expected = facts.get("through_holes_genus")
    actual = measured.get("through_holes_genus")
    if expected is not None and actual is not None:
        loss += 0.03 * min(abs(actual - expected), 12)
    if iou is not None:
        loss += 2 * (1 - iou)
    return loss if math.isfinite(loss) else math.inf


def rank_snapshots(case_dir: Path, snapshot_dir: Path, output: Path, deadline: float) -> dict:
    from . import cad, factsgen, imagecmp, raster
    from .gt import load_case

    gt = load_case(case_dir)
    rows = []
    index = snapshot_dir / "index.jsonl"
    if index.is_file():
        for line in index.read_text().splitlines():
            try:
                row = json.loads(line)
                name = row["file"]
                if Path(name).name == name and (snapshot_dir / name).is_file():
                    rows.append(row)
            except (ValueError, KeyError, TypeError):
                continue
    rows.sort(key=lambda row: quality(row, gt.facts, None))
    # Evaluate scalar-best, newest and middle candidates early, then the rest.
    # Later candidates still get a chance when an earlier model merely fits totals.
    ordered = rows[:1] + sorted(rows, key=lambda row: row["file"], reverse=True)[:1]
    by_time = sorted(rows, key=lambda row: row["file"])
    if by_time:
        ordered += [by_time[len(by_time) // 2]]
    ordered += rows
    paths = ([output] if output.is_file() else []) + [snapshot_dir / row["file"] for row in ordered]
    seen = set()
    result = {"selected": None, "quality": None, "evaluated": 0, "errors": []}
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for path in paths:
        if path in seen or time.time() >= deadline:
            continue
        seen.add(path)
        try:
            shape = cad.reopen_step(path)
            if not shape.is_valid:
                continue
            measured = factsgen.measure(shape)
            images = imagecmp.compare_all(case_dir / "images", raster.render_all(shape)) if gt.views else None
            iou = images.mean_iou if images and images.views else None
            loss = quality(measured, gt.facts, iou)
            result["evaluated"] += 1
            if math.isfinite(loss) and (result["quality"] is None or loss < result["quality"] - 1e-9):
                if path != output:
                    temporary = output.with_suffix(".candidate")
                    shutil.copyfile(path, temporary)
                    temporary.replace(output)
                result.update(selected=path.name, quality=loss, iou=iou)
            temporary = snapshot_dir / "ranking.tmp"
            temporary.write_text(json.dumps(result))
            temporary.replace(snapshot_dir / "ranking.json")
        except Exception as error:
            result["errors"].append(f"{path.name}: {type(error).__name__}")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deadline", type=float, required=True)
    args = parser.parse_args()
    print(json.dumps(rank_snapshots(args.case_dir, args.snapshot_dir, args.output, args.deadline)))


if __name__ == "__main__":
    main()
