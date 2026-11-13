import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from agentic_cad.gt import GroundTruth
from agentic_cad.provenance import check


def test_estimates_require_a_reason_and_stay_out_of_build():
    gt = GroundTruth("part", {}, "", [], None)
    source = '''
def derive(facts):
    return {"width": 37.125}  # estimated: view_0_front pixel width
def build(p):
    return p["width"]
'''
    assert check(gt, source).ok
    assert not check(gt, source.replace("# estimated: view_0_front pixel width", "")).ok
    assert not check(gt, source.replace('return p["width"]', 'return 37.125')).ok


def test_estimate_annotations_do_not_bypass_execution_checks():
    gt = GroundTruth("part", {}, "", [], None)
    source = '''
def derive(facts):
    open("file", "w")  # estimated: view_0_front
    return {"width": 37.125}  # estimated: view_0_front pixel width
def build(p):
    return p["width"]
'''
    assert any(v.rule == "io" for v in check(gt, source).violations)
