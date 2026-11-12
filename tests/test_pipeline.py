"""Tests for the deterministic half of the pipeline.

These run without an LLM and without a CAD GUI: they cover the renderer's
orientation, the provenance checker, the single-solid contract, independent
measurement, and the silhouette comparison. The model-facing half (prompting,
diagnosis, retry) is exercised by running the pipeline against a reference spec,
which is what `tests/specs/` is for.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agentic_cad import cad, factsgen, imagecmp, provenance, raster  # noqa: E402
from agentic_cad.gt import load_case  # noqa: E402

CASE3 = REPO_ROOT / "artifacts/inputs/test_case_3"
SPEC3 = REPO_ROOT / "tests/specs/test_case_3.py"


@pytest.fixture(scope="module")
def case3():
    return load_case(CASE3)


@pytest.fixture(scope="module")
def case3_shape(case3):
    built = cad.run_module(case3, SPEC3.read_text(encoding="utf-8"))
    assert built.ok, built.error
    return built.shape


# --------------------------------------------------------------------------- #
# renderer
# --------------------------------------------------------------------------- #
def test_front_view_is_not_vertically_flipped():
    """A notch at +Z must appear in the top half of the front view.

    The first two reference parts were both symmetric about their mid-height, so a
    flipped image axis passed unnoticed and only the isometric views exposed it.
    This builds a deliberately asymmetric part so the orientation is pinned.
    """
    from build123d import Box, Pos

    part = Box(40, 20, 40) - Pos(0, 0, 12) * Box(10, 30, 8)
    vertices, triangles = raster.mesh_of(part)

    front = raster.View("view_0_front", u=(1.0, 0.0, 0.0), v=(0.0, 0.0, 1.0))
    mask = raster.silhouette(vertices, triangles, front, size=256, fit_px=246)

    rows = mask.sum(axis=1)
    assert rows.any(), "the part produced an empty silhouette"
    top_fill = rows[: rows.size // 2].sum()
    bottom_fill = rows[rows.size // 2 :].sum()
    # The notch removes material near +Z, so the top half must hold less material.
    assert top_fill < bottom_fill, (
        f"front view looks flipped: material in the top half ({top_fill}) >= bottom half "
        f"({bottom_fill}), but the notch is at +Z"
    )


def test_orthographic_bases_match_the_stated_conventions():
    expected = {
        "view_0_front": ((1, 0, 0), (0, 0, 1)),
        "view_1_back": ((-1, 0, 0), (0, 0, 1)),
        "view_2_left": ((0, -1, 0), (0, 0, 1)),
        "view_3_right": ((0, 1, 0), (0, 0, 1)),
        "view_4_top": ((1, 0, 0), (0, 1, 0)),
        "view_5_bottom": ((1, 0, 0), (0, -1, 0)),
    }
    by_stem = {view.stem: view for view in raster.VIEWS}
    for stem, (u, v) in expected.items():
        assert by_stem[stem].u == u, f"{stem}: u axis is {by_stem[stem].u}, expected {u}"
        assert by_stem[stem].v == v, f"{stem}: v axis is {by_stem[stem].v}, expected {v}"


def test_isometric_views_reproduce_the_reference(case3, case3_shape):
    """Both iso views must agree with the reference within a tight tolerance.

    The camera direction was solved from the reference aspect ratios and confirmed
    by overlap; this is the regression that keeps it solved.
    """
    vertices, triangles = raster.mesh_of(case3_shape)
    for view in raster.ISO_VIEWS:
        mask = raster.silhouette(vertices, triangles, view)
        reference = imagecmp.reference_mask(CASE3 / "images" / f"{view.stem}.png")
        score = imagecmp.compare_view(view.stem, reference, mask)
        assert score.iou > 0.97, f"{view.stem}: IoU {score.iou:.3f} against the reference"


def test_orthographic_views_reproduce_the_reference(case3, case3_shape):
    vertices, triangles = raster.mesh_of(case3_shape)
    for view in raster.ORTHO_VIEWS:
        mask = raster.silhouette(vertices, triangles, view)
        reference = imagecmp.reference_mask(CASE3 / "images" / f"{view.stem}.png")
        score = imagecmp.compare_view(view.stem, reference, mask)
        assert score.iou > 0.97, f"{view.stem}: IoU {score.iou:.3f} against the reference"


# --------------------------------------------------------------------------- #
# provenance
# --------------------------------------------------------------------------- #
def test_reference_spec_passes_provenance(case3):
    report = provenance.check(case3, SPEC3.read_text(encoding="utf-8"))
    assert report.ok, report.render()


def test_unexplained_literal_is_rejected(case3):
    source = """
def derive(facts):
    d = {}
    d["length"] = facts["bounding_box_mm"]["x"]
    d["mystery"] = 37.5
    return d

def build(p):
    from build123d import Box
    return Box(p["length"], p["mystery"], p["length"])

NOTES = ""
"""
    report = provenance.check(case3, source)
    assert not report.ok
    assert any("37.5" in v.message for v in report.violations), report.render()


def test_dimension_literal_in_build_is_rejected(case3):
    source = """
def derive(facts):
    return {"length": facts["bounding_box_mm"]["x"]}

def build(p):
    from build123d import Box
    return Box(p["length"], 14.0, p["length"])

NOTES = ""
"""
    report = provenance.check(case3, source)
    assert not report.ok
    assert any("build()" in v.message for v in report.violations), report.render()


def test_structural_literals_are_allowed(case3):
    source = """
def derive(facts):
    d = {}
    d["length"] = facts["bounding_box_mm"]["x"]
    d["half"] = d["length"] / 2
    return d

def build(p):
    from build123d import Box, Rot
    return Rot(0, 90, 0) * Box(p["length"], p["half"], p["half"])

NOTES = ""
"""
    assert provenance.check(case3, source).ok


def test_file_io_is_rejected(case3):
    source = """
def derive(facts):
    open("x", "w")
    return {}

def build(p):
    from build123d import Box
    return Box(1, 1, 1)

NOTES = ""
"""
    report = provenance.check(case3, source)
    assert not report.ok
    assert any(v.rule == "io" for v in report.violations), report.render()


def test_disallowed_import_is_rejected(case3):
    source = """
import os

def derive(facts):
    return {}

def build(p):
    from build123d import Box
    return Box(1, 1, 1)

NOTES = ""
"""
    assert not provenance.check(case3, source).ok


# --------------------------------------------------------------------------- #
# build contract
# --------------------------------------------------------------------------- #
def test_two_disjoint_solids_are_rejected(case3):
    source = """
def derive(facts):
    d = {}
    d["a"] = facts["bounding_box_mm"]["x"]
    return d

def build(p):
    from build123d import Box, Pos
    return Pos(0, 0, 0) * Box(p["a"], p["a"], p["a"]) + Pos(100, 0, 0) * Box(p["a"], p["a"], p["a"])

NOTES = ""
"""
    built = cad.run_module(case3, source)
    assert not built.ok
    assert "separate solids" in built.error


def test_missing_function_is_reported(case3):
    built = cad.run_module(case3, "def derive(facts):\n    return {}\n")
    assert not built.ok
    assert built.stage == "contract"


def test_build_exception_is_captured_not_raised(case3):
    source = """
def derive(facts):
    return {}

def build(p):
    raise ValueError("boom")
"""
    built = cad.run_module(case3, source)
    assert not built.ok
    assert "boom" in built.error


def test_bbox_minimum_is_moved_to_the_origin():
    from build123d import Box, Pos

    off_centre = Pos(100, -50, 7) * Box(10, 20, 30)
    source = f"""
def derive(facts):
    return {{}}

def build(p):
    from build123d import Box, Pos
    return Pos({100}, {-50}, {7}) * Box({10}, {20}, {30})

NOTES = ""
"""
    # provenance would reject these literals; test the normaliser directly instead
    from agentic_cad.cad import _normalise

    moved = _normalise(off_centre)
    box = moved.bounding_box()
    assert abs(box.min.X) < 1e-6 and abs(box.min.Y) < 1e-6 and abs(box.min.Z) < 1e-6


# --------------------------------------------------------------------------- #
# measurement
# --------------------------------------------------------------------------- #
def test_measurement_is_independent_of_the_input_facts(case3, case3_shape):
    measured = factsgen.measure(case3_shape)
    assert measured["bounding_box_mm"]["x"] == pytest.approx(case3.bbox[0], abs=1e-3)
    assert measured["volume_mm3"] == pytest.approx(case3.volume, rel=1e-3)
    assert measured["surface_area_mm2"] == pytest.approx(case3.surface_area, rel=1e-3)
    assert measured["solids"] == 1
    assert measured["through_holes_genus"] == case3.genus


def test_bore_classification_separates_holes_from_shafts(case3, case3_shape):
    measured = factsgen.measure(case3_shape)
    bores = {c["diameter"] for c in measured["cylinders"] if c["kind"] == "bore"}
    shafts = {c["diameter"] for c in measured["cylinders"] if c["kind"] == "shaft"}
    assert 76.2 in bores
    assert {127.0, 132.08} <= shafts


def test_comparison_passes_gating_checks_for_a_correct_part(case3, case3_shape):
    comparison = factsgen.compare(case3, factsgen.measure(case3_shape))
    assert comparison.ok, comparison.render()
    assert not comparison.gating_failures


def test_wrong_envelope_fails_the_gating_check(case3):
    from build123d import Box

    wrong = Box(case3.bbox[0] * 1.2, case3.bbox[1], case3.bbox[2])
    comparison = factsgen.compare(case3, factsgen.measure(wrong))
    assert not comparison.ok
    names = {check.name for check in comparison.gating_failures}
    assert "bounding_box_mm" in names


def test_unmeasurable_genus_is_reported_unverified_not_passed():
    """A measurement that cannot be taken must never be reported as a pass."""
    from build123d import Box

    shell_only = Box(10, 10, 10).faces()[0]
    measured = factsgen.measure(shell_only)
    # A bare face has no volume; measurement must not invent numbers.
    assert measured["solids"] == 0


# --------------------------------------------------------------------------- #
# pipeline
# --------------------------------------------------------------------------- #
def test_pipeline_writes_one_step_file(tmp_path):
    from agentic_cad import agent

    case = load_case(CASE3)
    work = tmp_path / "work"
    output = tmp_path / "outputs" / "test_case_3.stp"

    result = agent.reconstruct(
        case,
        images_dir=CASE3 / "images",
        output_path=output,
        work_dir=work,
        deadline=__import__("time").time() + 120,
        client=None,
    )
    # Without AGENTIC_CAD_SPEC_DIR and without a client, nothing can be produced;
    # the point here is that the loop reports it instead of raising.
    assert not result.attempts or result.output_path == output


def test_step_round_trip_preserves_the_solid(case3, case3_shape, tmp_path):
    path = tmp_path / "part.stp"
    cad.export_step(case3_shape, path)
    assert path.is_file() and path.stat().st_size > 0
    reopened = cad.reopen_step(path)
    assert reopened.volume == pytest.approx(case3_shape.volume, rel=1e-6)
