"""Hidden inputs must not depend on the optional debugging fact sheet."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agentic_cad.gt import facts_from_description, load_case


@pytest.mark.parametrize("separator", ["x", "×", "X"])
def test_explicit_envelope_volume_and_passages(separator):
    text = f"**Envelope:** 508 {separator} 85.73 {separator} 165.1 mm (X x Y x Z); volume 4246.4 cm³; 15 through‑passages."
    facts = facts_from_description(text)
    assert facts["bounding_box_mm"] == {"x": 508, "y": 85.73, "z": 165.1}
    assert facts["volume_mm3"] == pytest.approx(4_246_400)
    assert facts["through_holes_genus"] == 15
    assert "cylindrical_holes_and_bores" not in facts
    assert "surface_area_mm2" not in facts


def test_mm_volume_is_not_scaled():
    facts = facts_from_description("Envelope: 10 x 20 x 30 mm; volume 2,000 mm^3; 0 through-passages.")
    assert facts["volume_mm3"] == 2000
    assert facts["through_holes_genus"] == 0


def test_absent_measurements_are_not_guessed():
    assert facts_from_description("A plate with an M8 hole.") == {"_input_source": "description.md"}


def test_missing_facts_does_not_modify_inputs(tmp_path):
    (tmp_path / "description.md").write_text("Envelope: 10 x 20 x 30 mm; volume 2.4 cm^3.")
    case = load_case(tmp_path)
    assert case.bbox == (10, 20, 30)
    assert case.volume == 2400
    assert not (tmp_path / "facts.json").exists()


def test_supplied_measurements_remain_authoritative(tmp_path):
    (tmp_path / "facts.json").write_text('{"volume_mm3": 2401}')
    (tmp_path / "description.md").write_text("volume 2.4 cm^3")
    assert load_case(tmp_path).volume == 2401
