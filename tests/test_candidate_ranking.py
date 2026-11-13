"""A candidate with the right totals can still have its hole in the wrong place."""
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agentic_cad.candidate_rank import quality, rank_snapshots


def test_internal_structure_is_considered_even_when_silhouettes_are_close():
    facts = {"volume_mm3": 100, "surface_area_mm2": 100, "through_holes_genus": 6}
    wrong = {"solids": 1, "volume_mm3": 100, "surface_area_mm2": 70, "through_holes_genus": 18}
    complete = {"solids": 1, "volume_mm3": 101, "surface_area_mm2": 101, "through_holes_genus": 6}
    assert quality(complete, facts, .96) < quality(wrong, facts, .97)
    assert quality({**complete, "solids": 2}, facts, 1) == float("inf")


def test_view_comparison_selects_the_correct_hole_location(tmp_path):
    from build123d import Box, Cylinder, Pos, export_step
    from PIL import Image
    from agentic_cad import factsgen, raster

    correct = Box(60, 40, 10) - Pos(-15, 0, 0) * Cylinder(2.5, 12)
    wrong = Box(60, 40, 10) - Pos(-5, 0, 0) * Cylinder(2.5, 12)
    case = tmp_path / "case"
    images = case / "images"
    images.mkdir(parents=True)
    for stem, mask in raster.render_all(correct).items():
        Image.fromarray((~mask * 255).astype("uint8")).save(images / f"{stem}.png")
    facts = factsgen.measure(correct)
    constraints = {key: facts[key] for key in ("bounding_box_mm", "volume_mm3", "surface_area_mm2", "through_holes_genus")}
    (case / "facts.json").write_text(json.dumps(constraints))
    (case / "description.md").write_text("A plate with one eccentric hole.")
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    export_step(wrong, str(snapshots / "0000.stp"))
    export_step(correct, str(snapshots / "0001.stp"))
    (snapshots / "index.jsonl").write_text("\n".join(json.dumps({**constraints, "solids": 1, "file": name}) for name in ("0000.stp", "0001.stp")))
    output = tmp_path / "out.stp"
    export_step(wrong, str(output))
    result = rank_snapshots(case, snapshots, output, time.time() + 60)
    assert result["selected"] == "0001.stp", result
    assert output.read_bytes() == (snapshots / "0001.stp").read_bytes()


def test_expired_ranking_preserves_existing_output(tmp_path):
    output = tmp_path / "part.stp"
    output.write_bytes(b"existing")
    case = tmp_path / "case"
    case.mkdir()
    result = rank_snapshots(case, tmp_path / "snapshots", output, time.time() - 1)
    assert result["evaluated"] == 0
    assert output.read_bytes() == b"existing"
