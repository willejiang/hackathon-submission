"""Independent measurement of a built part, and comparison against facts.json.

Verification inspects the geometry that was produced, never the parameters that
were meant to produce it. That distinction is the whole point: a model can be
convinced its formula is right, but it cannot talk a 12% volume error out of
existence.

The comparison returns a row per fact so the retry prompt can quote numbers
instead of adjectives, and each row is explicitly `pass`, `fail` or `unverified`.
A measurement that cannot be taken is never reported as a pass.
"""

from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any

from .gt import GroundTruth, HoleSpec

# Gating thresholds. bbox and volume decide whether a candidate is worth another
# render; everything else is advisory evidence for the diagnosis step.
BBOX_ABS_TOL_MM = 0.15
BBOX_REL_TOL = 0.002
VOLUME_REL_TOL = 0.02
AREA_REL_TOL = 0.03


@dataclass
class Check:
    name: str
    expected: str
    actual: str
    verdict: str  # pass | fail | unverified
    gating: bool = False
    note: str = ""

    def render(self) -> str:
        flag = {"pass": "PASS", "fail": "FAIL", "unverified": "UNVERIFIED"}[self.verdict]
        gate = "*" if self.gating else " "
        line = f"{gate}{flag:10} {self.name:26} expected {self.expected:<22} actual {self.actual}"
        if self.note:
            line += f"   [{self.note}]"
        return line


@dataclass
class Comparison:
    checks: list[Check] = field(default_factory=list)
    measured: dict[str, Any] = field(default_factory=dict)

    @property
    def gating_failures(self) -> list[Check]:
        return [c for c in self.checks if c.gating and c.verdict == "fail"]

    @property
    def ok(self) -> bool:
        return not self.gating_failures

    def render(self) -> str:
        lines = ["(* = gating)"]
        lines.extend(check.render() for check in self.checks)
        return "\n".join(lines)

    def advise(self) -> str:
        """Compact hint list for the next attempt's prompt."""
        fails = [c for c in self.checks if c.verdict in ("fail", "unverified")]
        if not fails:
            return ""
        return "\n".join(f"- {c.name}: expected {c.expected}, measured {c.actual}" for c in fails)


def _axis_name(direction: Any) -> str:
    components = [abs(direction.X), abs(direction.Y), abs(direction.Z)]
    index = components.index(max(components))
    return "XYZ"[index]


def _cylinders(shape: Any) -> list[dict[str, Any]]:
    """Classify every cylindrical face as a bore (concave) or a shaft (convex).

    The test: take the outward normal at the face centre and the radial vector
    from the axis to that point. A bore's normal points back at the axis, a shaft's
    points away from it.
    """
    out: list[dict[str, Any]] = []
    for face in shape.faces():
        if face.geom_type.name != "CYLINDER":
            continue
        try:
            radius = float(face.radius)
            axis = face.axis_of_rotation
            centre = face.center()
            normal = face.normal_at(centre)
        except Exception:  # noqa: BLE001 - a degenerate face is not worth failing over
            continue

        position = axis.position
        direction = axis.direction
        radial = (centre - position) - direction * ((centre - position).dot(direction))
        radial_len = math.sqrt(radial.X**2 + radial.Y**2 + radial.Z**2)
        if radial_len < 1e-9:
            continue
        dot = (normal.X * radial.X + normal.Y * radial.Y + normal.Z * radial.Z) / radial_len
        out.append(
            {
                "diameter": round(radius * 2.0, 4),
                "axis": _axis_name(direction),
                "kind": "bore" if dot < 0 else "shaft",
            }
        )
    return out


def _genus(shape: Any) -> int | None:
    """Euler characteristic of the surface, converted to genus.

    Done on a tessellation rather than the B-rep face list: periodic faces carry
    seam edges that make a naive V-E+F count on the B-rep wrong.
    """
    try:
        from .meshutil import genus, triangulate

        vertices, faces = triangulate(shape)
        return genus(vertices, faces)
    except Exception:  # noqa: BLE001
        return None


def measure(shape: Any) -> dict[str, Any]:
    """Extract every fact-shaped quantity from the produced geometry."""
    box = shape.bounding_box()
    solids = list(shape.solids())
    faces = list(shape.faces())
    face_types: dict[str, int] = {}
    for face in faces:
        name = face.geom_type.name
        face_types[name] = face_types.get(name, 0) + 1

    return {
        "bounding_box_mm": {
            "x": round(box.size.X, 4),
            "y": round(box.size.Y, 4),
            "z": round(box.size.Z, 4),
        },
        "bbox_min": [round(box.min.X, 4), round(box.min.Y, 4), round(box.min.Z, 4)],
        "volume_mm3": round(float(shape.volume), 4),
        "surface_area_mm2": round(float(shape.area), 4),
        "solids": len(solids),
        "faces": len(faces),
        "edges": len(list(shape.edges())),
        "vertices": len(list(shape.vertices())),
        "through_holes_genus": _genus(shape),
        "face_types": dict(sorted(face_types.items())),
        "cylinders": _cylinders(shape),
        "_note": "independently measured from the produced B-rep, not copied from the inputs",
    }


def _rel(actual: float, expected: float) -> float:
    if expected == 0:
        return 0.0 if actual == 0 else float("inf")
    return abs(actual - expected) / abs(expected)


def _close(actual: float, expected: float, *, abs_tol: float, rel_tol: float) -> bool:
    return abs(actual - expected) <= max(abs_tol, abs(expected) * rel_tol)


def _compare_holes(gt: GroundTruth, measured_cylinders: list[dict[str, Any]]) -> Check:
    """Compare the bore inventory against facts.

    Matches on (diameter, axis) with a tolerance, because a chamfered or
    countersunk bore legitimately splits into several cylindrical faces of
    different radii and the count alone is misleading.
    """
    expected: list[HoleSpec] = [hole for hole in gt.holes if hole.count > 0]
    if not expected:
        return Check("holes", "none declared", f"{len(measured_cylinders)} cylindrical faces", "unverified",
                     note="facts declare no bores")

    measured_bores = [c for c in measured_cylinders if c["kind"] == "bore"]
    matched = 0
    missed: list[str] = []
    for hole in expected:
        hits = [
            c
            for c in measured_bores
            if c["axis"] == hole.axis
            and _close(c["diameter"], hole.diameter, abs_tol=0.05, rel_tol=0.005)
        ]
        # One B-rep face may represent a bore that splits into two halves, so the
        # comparison is "at least one face per declared bore family".
        if hits:
            matched += 1
        else:
            missed.append(f"{hole.count}x d{hole.diameter:g} along {hole.axis}")

    expected_text = ", ".join(f"{h.count}x d{h.diameter:g} {h.axis}" for h in expected)
    if missed:
        return Check(
            "holes",
            expected_text,
            f"{len(measured_bores)} bore faces; missing {', '.join(missed)}",
            "fail",
            note="declared bores not found in the geometry",
        )
    return Check("holes", expected_text, f"{len(measured_bores)} bore faces", "pass")


def compare(gt: GroundTruth, measured: dict[str, Any]) -> Comparison:
    """Compare measured geometry with the authoritative facts."""
    result = Comparison(measured=measured)

    expected_box = gt.bbox
    actual_box = measured["bounding_box_mm"]
    box_ok = all(
        _close(actual_box[axis], expected_box[i], abs_tol=BBOX_ABS_TOL_MM, rel_tol=BBOX_REL_TOL)
        for i, axis in enumerate("xyz")
    )
    result.checks.append(
        Check(
            "bounding_box_mm",
            " x ".join(f"{v:g}" for v in expected_box),
            " x ".join(f"{actual_box[a]:g}" for a in "xyz"),
            "pass" if box_ok else "fail",
            gating=True,
            note="" if box_ok else "envelope mismatch: a stated envelope dimension is wrong or a feature overhangs",
        )
    )

    if gt.volume is not None:
        volume_ok = _close(measured["volume_mm3"], gt.volume, abs_tol=0.0, rel_tol=VOLUME_REL_TOL)
        result.checks.append(
            Check(
                "volume_mm3",
                f"{gt.volume:g}",
                f"{measured['volume_mm3']:g}",
                "pass" if volume_ok else "fail",
                gating=True,
                note=f"{_rel(measured['volume_mm3'], gt.volume) * 100:.1f}% off",
            )
        )

    if gt.surface_area is not None:
        area_ok = _close(measured["surface_area_mm2"], gt.surface_area, abs_tol=0.0, rel_tol=AREA_REL_TOL)
        result.checks.append(
            Check(
                "surface_area_mm2",
                f"{gt.surface_area:g}",
                f"{measured['surface_area_mm2']:g}",
                "pass" if area_ok else "fail",
                note=f"{_rel(measured['surface_area_mm2'], gt.surface_area) * 100:.1f}% off",
            )
        )

    if gt.solids is not None:
        result.checks.append(
            Check("solids", str(gt.solids), str(measured["solids"]),
                  "pass" if measured["solids"] == gt.solids else "fail", gating=True)
        )

    if gt.genus is not None:
        actual_genus = measured.get("through_holes_genus")
        if actual_genus is None:
            result.checks.append(Check("through_holes_genus", str(gt.genus), "not measurable", "unverified",
                                       note="tessellation failed or the shell is not watertight"))
        else:
            result.checks.append(
                Check("through_holes_genus", str(gt.genus), str(actual_genus),
                      "pass" if actual_genus == gt.genus else "fail")
            )

    for name, expected, actual in (
        ("faces", gt.faces, measured["faces"]),
        ("edges", gt.edges, measured["edges"]),
    ):
        if expected is None:
            continue
        delta = abs(actual - expected)
        result.checks.append(
            Check(name, str(expected), str(actual), "pass" if delta == 0 else "fail",
                  note="" if delta == 0 else f"{delta} off")
        )

    expected_types = gt.face_types
    if expected_types:
        actual_types = measured["face_types"]
        keys = sorted(set(expected_types) | set(actual_types))
        l1 = sum(abs(actual_types.get(k, 0) - expected_types.get(k, 0)) for k in keys)
        detail = " ".join(f"{k}:{actual_types.get(k, 0)}/{expected_types.get(k, 0)}" for k in keys)
        result.checks.append(
            Check("face_types", "actual/expected", detail, "pass" if l1 == 0 else "fail",
                  note="" if l1 == 0 else f"L1={l1}")
        )

    result.checks.append(_compare_holes(gt, measured["cylinders"]))
    return result
