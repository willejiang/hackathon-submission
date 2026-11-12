"""The timeout fallback may relax dimensions, but must keep execution safe."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentic_cad import cli, provenance  # noqa: E402
from agentic_cad.gt import load_case  # noqa: E402


@pytest.mark.parametrize("unsafe", ["open('marker', 'w')", "import os"])
def test_snapshot_rejects_unsafe_source_before_build(monkeypatch, unsafe):
    source = f"""
def derive(facts):
    {unsafe}
    return {{}}

def build(p):
    from build123d import Box
    return Box(1, 1, 1)
"""
    monkeypatch.setattr(cli, "read_source", lambda _args: source)
    monkeypatch.setattr(cli, "load_gt", lambda: load_case(ROOT / "artifacts/inputs/test_case_3"))
    monkeypatch.setattr(cli, "_build", lambda _source: pytest.fail("unsafe source was executed"))

    result = cli.tool_snapshot({"path": "solution.py"})

    assert result["ok"] is False
    assert result["stage"] == "provenance"
    assert "not allowed" in result["report"]


def test_snapshot_allows_only_numeric_provenance_violations(monkeypatch):
    source = """
def derive(facts):
    return {"width": 37.5}

def build(p):
    from build123d import Box
    return Box(p["width"], 14.0, 1)
"""
    gt = load_case(ROOT / "artifacts/inputs/test_case_3")
    violations = provenance.check(gt, source).violations
    assert violations and {item.rule for item in violations} == {"provenance"}
    built_sources = []
    monkeypatch.setattr(cli, "read_source", lambda _args: source)
    monkeypatch.setattr(cli, "load_gt", lambda: gt)
    monkeypatch.setattr(
        cli,
        "_build",
        lambda candidate: (built_sources.append(candidate), SimpleNamespace(ok=True),
                           {"volume_mm3": 525.0, "solids": 1}, None),
    )

    result = cli.tool_snapshot({"path": "solution.py"})

    assert result == {"ok": True, "volume_mm3": 525.0, "solids": 1}
    assert built_sources == [source]
