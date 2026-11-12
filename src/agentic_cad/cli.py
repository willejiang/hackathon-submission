"""Deterministic tool backend for the DSH plugin.

The agent decides what to try; everything that can be computed is computed here
and returned as numbers, never prose. Each subcommand prints one JSON object.

    python -m agentic_cad.cli case              # ground truth for this case
    python -m agentic_cad.cli build   {"path": "solution.py"}
    python -m agentic_cad.cli verify  {"path": "solution.py"}
    python -m agentic_cad.cli render  {"path": "solution.py"}
    python -m agentic_cad.cli submit  {"path": "solution.py"}

The case directory, the output directory and the image directory come from the
environment (`AGENTIC_CAD_CASE_DIR`, `AGENTIC_CAD_OUTPUT`) so the tool calls carry
no state and a retry after a crash is just another call.

`path` is a file the agent writes with its own editor. Passing a module as an inline
JSON string would work too, but shell quoting around a few hundred lines of Python
is exactly the kind of avoidable failure this design removes.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# environment
# --------------------------------------------------------------------------- #


def case_dir() -> Path:
    value = os.environ.get("AGENTIC_CAD_CASE_DIR", "").strip()
    if not value:
        raise SystemExit("AGENTIC_CAD_CASE_DIR is not set")
    return Path(value)


def output_dir() -> Path:
    value = os.environ.get("AGENTIC_CAD_OUTPUT", "").strip()
    if not value:
        raise SystemExit("AGENTIC_CAD_OUTPUT is not set")
    return Path(value)


def load_gt():
    from .gt import load_case

    return load_case(case_dir())


def read_source(args: dict) -> str:
    raw = args.get("path")
    if not isinstance(raw, str) or not raw.strip():
        raise SystemExit("args.path must be the file holding the module")
    path = Path(raw)
    if not path.is_absolute():
        # The agent works inside the session workspace, so a relative path is
        # relative to the process cwd the harness launched us in.
        path = Path(os.getcwd()) / path
    if not path.is_file():
        raise SystemExit(f"no such file: {path}")
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# tools
# --------------------------------------------------------------------------- #


def tool_case(_args: dict) -> dict:
    gt = load_gt()
    views = [{"stem": p.stem, "path": str(p)} for p in gt.views]
    return {
        "ok": True,
        "case": gt.name,
        "facts": gt.facts,
        "description": gt.description,
        "views": views,
        "context_png": str(gt.context) if gt.context else None,
        "camera_conventions": {
            "view_0_front": "looking along +Y: X right, Z up",
            "view_1_back": "looking along -Y: X left, Z up",
            "view_2_left": "looking along +X: Y left, Z up",
            "view_3_right": "looking along -X: Y right, Z up",
            "view_4_top": "looking along -Z: X right, Y up",
            "view_5_bottom": "looking along +Z: X right, Y down",
            "view_6_iso_front_right_top": "isometric from +X, -Y, +Z",
            "view_7_iso_back_left_bottom": "isometric from -X, +Y, -Z",
        },
        "units": "mm, positions measured from the bounding-box minimum corner",
    }


def _build(source: str):
    from . import cad, factsgen

    gt = load_gt()
    built = cad.run_module(gt, source)
    if not built.ok:
        return gt, built, None, None
    measured = factsgen.measure(built.shape)
    comparison = factsgen.compare(gt, measured)
    return gt, built, measured, comparison


def tool_build(args: dict) -> dict:
    from . import provenance

    gt = load_gt()
    source = read_source(args)
    prov = provenance.check(gt, source)
    if not prov.ok:
        return {"ok": False, "stage": "provenance", "report": prov.render()}

    _gt, built, measured, _comparison = _build(source)
    if not built.ok:
        return {"ok": False, "stage": built.stage, "error": built.error}

    return {
        "ok": True,
        "volume_mm3": measured["volume_mm3"],
        "bounding_box_mm": measured["bounding_box_mm"],
        "solids": measured["solids"],
        "faces": measured["faces"],
        "edges": measured["edges"],
        "through_holes_genus": measured["through_holes_genus"],
        "face_types": measured["face_types"],
        "cylinders": measured["cylinders"],
        "provenance": prov.render(),
    }


def tool_verify(args: dict) -> dict:
    from . import provenance

    gt = load_gt()
    source = read_source(args)
    prov = provenance.check(gt, source)
    if not prov.ok:
        return {"ok": False, "stage": "provenance", "report": prov.render()}

    _gt, built, measured, comparison = _build(source)
    if not built.ok:
        return {"ok": False, "stage": built.stage, "error": built.error}

    return {
        "ok": comparison.ok,
        "gating_failures": [c.name for c in comparison.gating_failures],
        "rows": [
            {
                "name": c.name,
                "expected": c.expected,
                "actual": c.actual,
                "verdict": c.verdict,
                "gating": c.gating,
                "note": c.note,
            }
            for c in comparison.checks
        ],
        "table": comparison.render(),
        "advise": comparison.advise(),
    }


def tool_render(args: dict) -> dict:
    from . import imagecmp, raster

    gt = load_gt()
    source = read_source(args)
    _gt, built, _measured, _comparison = _build(source)
    if not built.ok:
        return {"ok": False, "stage": built.stage, "error": built.error}

    rendered = raster.render_all(built.shape)
    comparison = imagecmp.compare_all(case_dir() / "images", rendered)
    return {
        "ok": True,
        "mean_iou_ortho": round(comparison.mean_iou_ortho, 4),
        "mean_iou_iso": round(comparison.mean_iou_iso, 4),
        "views": [
            {
                "stem": v.stem,
                "iou": round(v.iou, 4),
                "overfill": round(v.overfill, 4),
                "underfill": round(v.underfill, 4),
                "aspect_render": round(v.aspect_render, 4),
                "aspect_reference": round(v.aspect_ref, 4),
            }
            for v in comparison.views
        ],
        "table": comparison.render(),
        "advise": comparison.advise(),
    }


def tool_facts_scaffold(_args: dict) -> dict:
    """The shape of this case's facts.json, with every measurement removed.

    The agent needs the structure to write a measurer for it, and must not have the
    numbers, or the measurer could copy them instead of measuring.
    """
    from . import measuredoc

    gt = load_gt()
    return {
        "ok": True,
        "case": gt.name,
        "note": "structure only. Every number has been replaced by null, so any number "
                "in your measured document has to come from the geometry.",
        "structure": measuredoc.scaffold(gt.facts),
        "rules": [
            "write measure_result.py defining `def measure(shape):` and returning a dict "
            "with exactly this structure",
            "shape is a build123d solid, already imported for you",
            "no I/O, no os/sys/json/pathlib imports: the module is refused before it runs "
            "if it can reach the filesystem",
            "convention: axis labels are the letters X/Y/Z or a [x,y,z] direction; surface "
            "type names match face.geom_type.name; angles are degrees; lengths are mm",
        ],
    }


def tool_measure_result(args: dict) -> dict:
    """Run the agent's measurer, check its shape, then compare it with facts.json."""
    from . import cad, factscompare, measuredoc

    gt = load_gt()
    source = read_source(args)
    violations = measuredoc.audit_measurer(source)
    if violations:
        return {
            "ok": False,
            "stage": "measurer_refused",
            "violations": violations,
            "report": "the measurer was refused before it ran:\n" + "\n".join(f"- {v}" for v in violations),
        }

    step = args.get("step") or str(output_dir() / f"{gt.name}.stp")
    step_path = Path(step)
    if not step_path.is_absolute():
        step_path = Path(os.getcwd()) / step_path
    if not step_path.is_file():
        return {"ok": False, "stage": "no_step",
                "error": f"no STEP at {step_path}; submit a module first, then measure the file it produced"}

    shape = cad.reopen_step(step_path)
    work_dir = Path(os.getcwd())
    document, error = measuredoc.run_measurer(source, shape, work_dir)
    if document is None:
        return {"ok": False, "stage": "measurer_failed", "error": error}

    shape_problems = measuredoc.check_structure(gt.facts, document)
    facts_file = work_dir / "facts_from_result.json"
    measuredoc.write_document(document, facts_file)

    comparison = factscompare.compare_facts(gt.facts, document)
    return {
        "ok": comparison.ok and not shape_problems,
        "gating_failures": [c.name for c in comparison.gating_failures],
        "structure_problems": shape_problems,
        "facts_from_result": str(facts_file),
        "table": comparison.render(),
        "advise": comparison.advise(),
        "rows": [
            {"name": c.name, "expected": c.expected, "actual": c.actual,
             "verdict": c.verdict, "gating": c.gating, "note": c.note}
            for c in comparison.checks
        ],
    }


def tool_submit(args: dict) -> dict:
    from . import cad, provenance

    gt = load_gt()
    source = read_source(args)
    prov = provenance.check(gt, source)
    if not prov.ok:
        return {"ok": False, "stage": "provenance", "report": prov.render()}

    _gt, built, _measured, _comparison = _build(source)
    if not built.ok:
        return {"ok": False, "stage": built.stage, "error": built.error}

    target = output_dir() / f"{gt.name}.stp"
    # The measured document goes into the workspace, never the output directory.
    facts_file = Path(os.getcwd()) / "facts_from_result.json"
    cad.export_step(built.shape, target, measured=_measured, facts_path=facts_file)
    return {
        "ok": True,
        "path": str(target),
        "bytes": target.stat().st_size,
        "facts_from_result": str(facts_file),
    }


TOOLS = {
    "case": tool_case,
    "build": tool_build,
    "verify": tool_verify,
    "render": tool_render,
    "submit": tool_submit,
    "facts_scaffold": tool_facts_scaffold,
    "measure_result": tool_measure_result,
}


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in TOOLS:
        print(json.dumps({"ok": False, "error": f"usage: cli <{'|'.join(TOOLS)}> [json-args]"}))
        return 2
    name = argv[1]
    args: dict = {}
    if len(argv) > 2 and argv[2].strip():
        try:
            args = json.loads(argv[2])
        except json.JSONDecodeError as error:
            print(json.dumps({"ok": False, "error": f"args are not JSON: {error}"}))
            return 2
    try:
        result = TOOLS[name](args)
    except SystemExit as error:
        result = {"ok": False, "error": str(error)}
    except Exception as error:  # noqa: BLE001 - a tool must return, never crash the agent
        import traceback

        result = {"ok": False, "error": f"{type(error).__name__}: {error}",
                  "traceback": traceback.format_exc()[-1500:]}
    # A degenerate boolean can leave volume or area as NaN or Inf. Python's json
    # module happily writes the bare tokens NaN/Infinity, which are not JSON, and the
    # plugin's JSON.parse then throws -- so the model sees "cli returned non-JSON"
    # instead of "your solid is degenerate". Sanitise before serialising.
    print(json.dumps(_finite(result), ensure_ascii=False))
    return 0 if result.get("ok") else 1


def _finite(value):
    """Replace non-finite floats with None, recursively, and note that we did."""
    import math

    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
