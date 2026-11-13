"""Rounded CAD extents use length tolerances; topology counts remain exact."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentic_cad.factscompare import compare_facts


@pytest.mark.parametrize("expected,actual,accepted", [
    (255.94, 255.935, True),
    (255.94, 256.8, False),
    (1.0, 1.1, True),
    (1.0, 1.2, False),
])
def test_bounding_box_uses_configured_relative_and_absolute_tolerances(expected, actual, accepted):
    result = compare_facts({"bounding_box_mm": {"y": expected}},
                           {"bounding_box_mm": {"y": actual}})
    assert result.ok is accepted, result.render()


def test_face_type_counts_stay_exact():
    result = compare_facts({"face_types": {"PLANE": 100}},
                           {"face_types": {"PLANE": 101}})
    assert result.checks[0].verdict == "fail"
