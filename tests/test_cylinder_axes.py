"""Oblique bore families must be compared by their 3D axes, not a display letter."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentic_cad import factscompare, factsgen  # noqa: E402


@pytest.mark.parametrize("expected", [(0, 0.71, 0.71), "(-0.00, 0.71, 0.71)", "[0, .71, .71]"])
def test_fact_axis_formats_match_the_same_physical_direction(expected):
    assert factsgen._axis_matches((0, -1, -1), expected)
    assert not factsgen._axis_matches((0, 1, -1), expected)
    assert not factsgen._axis_matches((0, 1, 0), expected)


@pytest.mark.parametrize("group", [factsgen.cylinder_groups, factscompare._group_cylinders])
def test_banks_with_the_same_dominant_axis_are_not_collapsed(group):
    rows = [
        {"diameter": 10.0, "axis": "Y", "axis_vector": vector, "kind": "bore",
         "area": 2 * math.pi * 5 * 20, "axial_extent": 20}
        for vector in [(0, 0.7071, 0.7071), (0, 0.7071, -0.7071)]
    ]

    groups = group(rows)

    assert len(groups) == 2
    assert [item["faces"] for item in groups] == [1, 1]
    assert {tuple(round(v, 4) for v in item["axis_vector"]) for item in groups} == {
        (0, 0.7071, 0.7071), (0, 0.7071, -0.7071),
    }


def test_fact_comparison_uses_the_measured_axis_vector():
    reference = {"diameter": 127.0, "axis": "(-0.00, 0.71, 0.71)", "count": 3}
    correct = {"diameter": 127.0, "axis": "Y", "axis_vector": (0, .7071, .7071), "count": 3}
    other_bank = {**correct, "axis_vector": (0, .7071, -.7071)}

    assert factscompare._entry_matches(reference, correct, "cylindrical_holes_and_bores")
    assert not factscompare._entry_matches(reference, other_bank, "cylindrical_holes_and_bores")
    comparison = factscompare.compare_facts(
        {"cylindrical_holes_and_bores": [reference]},
        {"cylindrical_holes_and_bores": [correct]},
    )
    assert comparison.ok, comparison.render()


def test_invalid_axis_is_not_silently_accepted():
    assert not factsgen._axis_matches((0, 1, 0), "not an axis")
    assert not factsgen._axis_matches((0, 1, 0), (0, 0, 0))
    assert not factsgen._axis_matches((0, 1, 0), (0, float("nan"), 0))
