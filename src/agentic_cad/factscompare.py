"""Measure the produced solid in facts.json's own schema, then compare it key by key.

The earlier comparison was a hand-written list: one `if` per fact family. Every
family nobody wrote code for was silently skipped, which is how
`partial_cylinders_arcs`, `fillets_from_tori_minor_radii`, `fillets_rounds_from_cylinders`,
`cylindrical_shafts_and_bosses` and `cones_half_angle_deg` went unchecked while the
gate reported PASS.

This module removes that failure mode. `measure_as_facts` produces a document with
the same shape and the same keys as the input `facts.json`, and `compare_facts`
walks **the input document**, not a hardcoded list:

  * a scalar is compared with a tolerance
  * a dict of scalars is compared key by key over the union of both sides
  * a dict keyed by a measured quantity (a radius, an angle) is matched by value,
    not by string
  * a list of objects is matched as a multiset on its identity fields, then its
    payload fields are compared
  * a key the measured side cannot supply becomes an explicit `unverified` row

So a fact family added to the inputs shows up in the comparison automatically. The
worst case becomes a visible UNVERIFIED row instead of silence.
"""

from __future__ import annotations

import collections
import math
from typing import Any

from .factsgen import Check, Comparison

# Fact families whose disagreement fails the submission. Everything else is still
# reported, but as evidence rather than as a gate. Counts stay advisory because the
# reference models were built by fusing several bodies, so an identical solid can
# legitimately have a different face and edge count.
GATING_KEYS = {
    "bounding_box_mm",
    "volume_mm3",
    "surface_area_mm2",
    "solids",
    "through_holes_genus",
    "cylindrical_holes_and_bores",
}

# Relative tolerances per family. One global tolerance cannot serve a 508 mm block
# and a 2 mm fillet.
TOLERANCES = {
    "bounding_box_mm": 0.002,
    "volume_mm3": 0.02,
    "surface_area_mm2": 0.05,
    "solids": 0.0,
    "through_holes_genus": 0.0,
    "faces": 0.0,
    "edges": 0.0,
    "face_types": 0.0,
    "cylindrical_holes_and_bores": 0.08,
    "cylindrical_shafts_and_bosses": 0.08,
    "partial_cylinders_arcs": 0.10,
    "fillets_rounds_from_cylinders": 0.10,
    "fillets_from_tori_minor_radii": 0.10,
    "cones_half_angle_deg": 0.10,
}

# Absolute floors, so a 2 mm feature is not held to 0.2% of itself.
ABS_FLOORS = {
    "bounding_box_mm": 0.15,
    "volume_mm3": 0.0,
    "surface_area_mm2": 0.0,
    "cylindrical_holes_and_bores": 0.05,
    "cylindrical_shafts_and_bosses": 0.05,
    "partial_cylinders_arcs": 0.05,
    "fillets_rounds_from_cylinders": 0.05,
}

# Which fields identify a list entry, and which ones carry the payload.
IDENTITY = {
    "cylindrical_holes_and_bores": ("diameter", "axis"),
    "cylindrical_shafts_and_bosses": ("diameter", "axis"),
    "partial_cylinders_arcs": ("diameter", "type"),
    "fillets_rounds_from_cylinders": ("radius", "type"),
}
PAYLOAD = ("count", "faces", "lengths")

METADATA_PREFIX = "_"


# --------------------------------------------------------------------------- #
# measurement
# --------------------------------------------------------------------------- #


def _axis_label(direction) -> str:
    components = [abs(direction.X), abs(direction.Y), abs(direction.Z)]
    return "XYZ"[components.index(max(components))]


def _axis_vector(direction) -> tuple[float, float, float]:
    values = [direction.X, direction.Y, direction.Z]
    dominant = max(range(3), key=lambda i: abs(values[i]))
    sign = -1.0 if values[dominant] < 0 else 1.0
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return tuple(round(sign * v / norm, 4) for v in values)


def measure_as_facts(shape: Any) -> tuple[dict[str, Any], list[str]]:
    """Measure the solid into facts.json's schema.

    Returns the document and the list of keys that could not be measured, so the
    caller can surface them instead of quietly omitting them.
    """
    from .meshutil import genus, triangulate

    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Torus
    except Exception:  # noqa: BLE001
        BRepAdaptor_Surface = None

    box = shape.bounding_box()
    faces = list(shape.faces())
    face_types: collections.Counter = collections.Counter()

    tori: collections.Counter = collections.Counter()
    cones: collections.Counter = collections.Counter()
    cylinders: list[dict[str, Any]] = []

    for face in faces:
        kind = face.geom_type.name
        face_types[kind] += 1

        if BRepAdaptor_Surface is not None:
            try:
                adaptor = BRepAdaptor_Surface(face.wrapped)
                surface_type = adaptor.GetType()
                if surface_type == GeomAbs_Torus:
                    tori[round(adaptor.Torus().MinorRadius(), 2)] += 1
                    continue
                if surface_type == GeomAbs_Cone:
                    cones[round(math.degrees(adaptor.Cone().SemiAngle()), 1)] += 1
                    continue
            except Exception:  # noqa: BLE001
                pass

        if kind != "CYLINDER":
            continue
        try:
            axis = face.axis_of_rotation
            centre = face.center()
            direction = axis.direction
            radial = (centre - axis.position) - direction * ((centre - axis.position).dot(direction))
            radial_len = math.sqrt(radial.X**2 + radial.Y**2 + radial.Z**2)
            if radial_len < 1e-9:
                continue
            normal = face.normal_at(centre)
            dot = (normal.X * radial.X + normal.Y * radial.Y + normal.Z * radial.Z) / radial_len
            cx, cy, cz = direction.X, direction.Y, direction.Z
            lo = hi = None
            for vertex in face.vertices():
                t = vertex.X * cx + vertex.Y * cy + vertex.Z * cz
                lo = t if lo is None else min(lo, t)
                hi = t if hi is None else max(hi, t)
            cylinders.append(
                {
                    "diameter": round(face.radius * 2.0, 4),
                    "radius": face.radius,
                    "axis": _axis_label(direction),
                    "axis_vector": _axis_vector(direction),
                    "kind": "bore" if dot < 0 else "shaft",
                    "area": float(face.area),
                    "axial_extent": float(hi - lo) if lo is not None and hi is not None else 0.0,
                    "centre": (round(centre.X, 3), round(centre.Y, 3), round(centre.Z, 3)),
                }
            )
        except Exception:  # noqa: BLE001
            continue

    groups = _group_cylinders(cylinders)
    partial = [g for g in groups if not g["full"]]
    full = [g for g in groups if g["full"]]

    measured: dict[str, Any] = {
        "bounding_box_mm": {
            "x": round(box.size.X, 4),
            "y": round(box.size.Y, 4),
            "z": round(box.size.Z, 4),
        },
        "volume_mm3": round(float(shape.volume), 4),
        "surface_area_mm2": round(float(shape.area), 4),
        "solids": len(list(shape.solids())),
        "faces": len(faces),
        "edges": len(list(shape.edges())),
        "face_types": dict(sorted(face_types.items())),
        "cylindrical_holes_and_bores": [
            {"diameter": g["diameter"], "axis": g["axis"], "axis_vector": g["axis_vector"],
             "count": g["faces"], "lengths": [round(g["axial_extent"], 3)]}
            for g in full if g["kind"] == "bore"
        ],
        "cylindrical_shafts_and_bosses": [
            {"diameter": g["diameter"], "axis": g["axis"], "axis_vector": g["axis_vector"],
             "count": g["faces"], "lengths": [round(g["axial_extent"], 3)]}
            for g in full if g["kind"] == "shaft"
        ],
        # facts.json names these families by curvature, not by whether the material is
        # inside or outside the surface -- "concave"/"convex" for arcs, "convex round"
        # and "concave fillet" for rounds. Emitting the internal bore/shaft vocabulary
        # here made every arc disagree with the model's measurer on a label alone,
        # which buried the disagreements that were real.
        "partial_cylinders_arcs": [
            {"diameter": g["diameter"],
             "type": "convex" if g["kind"] == "shaft" else "concave",
             "faces": g["faces"]}
            for g in partial
        ],
        "fillets_rounds_from_cylinders": [
            {"radius": round(g["diameter"] / 2.0, 4),
             "type": "convex round" if g["kind"] == "shaft" else "concave fillet",
             "faces": g["faces"]}
            for g in partial
        ],
        "fillets_from_tori_minor_radii": {f"{k:g}": v for k, v in sorted(tori.items())},
        "cones_half_angle_deg": {f"{k:g}": v for k, v in sorted(cones.items())},
    }

    try:
        vertices, triangles = triangulate(shape)
        measured["through_holes_genus"] = genus(vertices, triangles)
    except Exception:  # noqa: BLE001
        measured["through_holes_genus"] = None

    unmeasured = [k for k, v in measured.items() if v is None]
    return measured, unmeasured


def _group_cylinders(cylinders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse cylindrical faces into features.

    Total axial extent is taken as the max over the group so a bore split into two
    coaxial faces still reports its real depth; the angular span comes from
    `area / (radius * extent)`, which is what separates a full bore from a
    half-cylinder slot.
    """
    groups: dict[tuple, dict[str, Any]] = {}
    for face in cylinders:
        key = (face["diameter"], face["axis"], face["kind"])
        group = groups.setdefault(
            key,
            {"diameter": face["diameter"], "axis": face["axis"], "kind": face["kind"],
             "faces": 0, "area": 0.0, "axial_extent": 0.0,
             "axis_vector": face["axis_vector"]},
        )
        group["faces"] += 1
        group["area"] += face["area"]
        group["axial_extent"] = max(group["axial_extent"], face["axial_extent"])

    out = []
    for group in groups.values():
        radius = group["diameter"] / 2.0
        extent = group["axial_extent"]
        if radius > 1e-9 and extent > 1e-9:
            fraction = (group["area"] / (radius * extent)) / (2.0 * math.pi)
        else:
            fraction = 1.0
        out.append({**group, "full": fraction > 0.9, "span_fraction": round(min(fraction, 2.0), 3)})
    return sorted(out, key=lambda g: (-g["diameter"], g["axis"]))


# --------------------------------------------------------------------------- #
# comparison
# --------------------------------------------------------------------------- #


def _close(actual: float, expected: float, key: str, field: str | None = None) -> bool:
    rel = TOLERANCES.get(key, 0.02)
    absolute = ABS_FLOORS.get(key, 0.0)
    if field in ("lengths",):
        rel = max(rel, 0.08)
    scale = max(abs(expected), 1e-9)
    return abs(actual - expected) <= max(absolute, rel * scale)


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, list):
        return "[" + ", ".join(_fmt(v) for v in value) + "]"
    return str(value)


def _scalar_check(name: str, expected: Any, actual: Any) -> Check:
    gating = name.split(".")[0].split("[")[0] in GATING_KEYS
    if actual is None:
        return Check(name, _fmt(expected), "not measured", "unverified",
                     gating=gating, note="the measured side could not supply this family")
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        ok = _close(float(actual), float(expected), name.split(".")[0])
        delta = ""
        if isinstance(expected, (int, float)) and expected:
            delta = f"{abs(actual - expected) / abs(expected) * 100:.1f}% off"
        return Check(name, _fmt(expected), _fmt(actual), "pass" if ok else "fail",
                     gating=gating, note=delta if not ok else "")
    return Check(name, _fmt(expected), _fmt(actual),
                 "pass" if expected == actual else "fail", gating=gating)


def _dict_check(key: str, expected: dict, actual: dict | None) -> list[Check]:
    gating = key in GATING_KEYS
    if actual is None:
        return [Check(key, _fmt(expected), "not measured", "unverified", gating=gating)]
    checks: list[Check] = []
    # Match keys by value, not by string: a radius dict is keyed "1.0" and a
    # measured radius is 1.0000000001.
    measured_keys = list(actual.keys())
    used: set = set()
    for name, value in expected.items():
        try:
            target = float(name)
        except (TypeError, ValueError):
            target = None
        match = None
        if target is not None:
            best = None
            for candidate in measured_keys:
                if candidate in used:
                    continue
                try:
                    distance = abs(float(candidate) - target)
                except (TypeError, ValueError):
                    continue
                if best is None or distance < best[0]:
                    best = (distance, candidate)
            if best is not None and best[0] <= max(0.05, 0.10 * abs(target)):
                match = best[1]
        elif name in actual:
            match = name
        if match is None:
            checks.append(Check(f"{key}[{name}]", _fmt(value), "0", "fail", gating=gating,
                                note="this species is absent from the geometry"))
            continue
        used.add(match)
        checks.append(Check(f"{key}[{name}]", _fmt(value), _fmt(actual[match]),
                            "pass" if actual[match] == value else "fail", gating=gating))
    for candidate in measured_keys:
        if candidate not in used and actual[candidate]:
            checks.append(Check(f"{key}[{candidate}]", "0", _fmt(actual[candidate]), "fail",
                                gating=gating, note="present in the geometry, not declared"))
    return checks


def _entry_matches(reference: dict, measured: dict, key: str) -> bool:
    identity = IDENTITY.get(key)
    if not identity:
        return False
    for field in identity:
        expected = reference.get(field)
        actual = measured.get(field)
        if field == "axis":
            if not _axis_parallel(reference.get("axis_vector"), expected, actual):
                return False
        elif isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
            if not _close(float(actual), float(expected), key):
                return False
        elif expected != actual:
            return False
    return True


def _axis_parallel(measured_vector, expected, actual_label) -> bool:
    if isinstance(expected, str):
        return str(expected).strip().upper() == str(actual_label).strip().upper()
    if not measured_vector:
        return False
    try:
        expected_vector = [float(v) for v in expected]
    except (TypeError, ValueError):
        return True
    norm = math.sqrt(sum(v * v for v in expected_vector)) or 1.0
    dot = sum(a * b for a, b in zip(measured_vector, expected_vector))
    return abs(dot / norm) > 0.985


def _list_check(key: str, expected: list, actual: list | None) -> list[Check]:
    gating = key in GATING_KEYS
    if actual is None:
        return [Check(key, f"{len(expected)} entries", "not measured", "unverified", gating=gating)]
    if not expected and not actual:
        return [Check(key, "none declared", "none measured", "pass", gating=gating)]

    remaining = list(actual)
    checks: list[Check] = []
    for reference in expected:
        match = next((m for m in remaining if _entry_matches(reference, m, key)), None)
        label = ", ".join(f"{k}={_fmt(reference[k])}" for k in IDENTITY.get(key, ()) if k in reference)
        if match is None:
            checks.append(Check(f"{key}: {label}", "declared", "absent", "fail", gating=gating,
                                note="declared feature not found in the geometry"))
            continue
        remaining.remove(match)
        # Compare the payload fields the reference carries.
        failures = []
        for field in PAYLOAD:
            if field not in reference:
                continue
            expected_value = reference[field]
            actual_value = match.get(field)
            if field == "lengths":
                declared = [v for v in expected_value if isinstance(v, (int, float))]
                got = [v for v in (actual_value or []) if isinstance(v, (int, float))]
                if declared and got:
                    nearest = min(declared, key=lambda v: abs(v - got[0]))
                    if not _close(got[0], nearest, key, field):
                        longer = got[0] > max(declared) * 1.15
                        failures.append(
                            f"depth {got[0]:.2f}mm vs declared {nearest:.2f}mm"
                            + (" (through where the part is blind)" if longer else "")
                        )
            elif isinstance(expected_value, (int, float)) and isinstance(actual_value, (int, float)):
                if not _close(float(actual_value), float(expected_value), key):
                    failures.append(f"{field} {_fmt(actual_value)} vs {_fmt(expected_value)}")
        verdict = "fail" if failures else "pass"
        checks.append(Check(f"{key}: {label}", _fmt(reference.get("count", reference.get("faces", ""))),
                            _fmt(match.get("count", match.get("faces", ""))), verdict,
                            gating=gating, note="; ".join(failures)))

    for extra in remaining:
        label = ", ".join(f"{k}={_fmt(extra[k])}" for k in IDENTITY.get(key, ()) if k in extra)
        checks.append(Check(f"{key}: {label}", "0", "present", "fail", gating=gating,
                            note="feature in the geometry that the brief does not declare"))
    return checks


def compare_facts(reference: dict[str, Any], measured: dict[str, Any],
                  unmeasured: list[str] | None = None) -> Comparison:
    """Walk the reference document and report on every entry it contains."""
    result = Comparison(measured=measured)
    for key in reference:
        if key.startswith(METADATA_PREFIX):
            continue
        expected = reference[key]
        actual = measured.get(key)
        if isinstance(expected, dict):
            result.checks.extend(_dict_check(key, expected, actual))
        elif isinstance(expected, list):
            result.checks.extend(_list_check(key, expected, actual))
        else:
            result.checks.append(_scalar_check(key, expected, actual))

    for key in (unmeasured or []):
        if key not in reference:
            continue
        result.checks.append(Check(key, "measurable", "not measured", "unverified",
                                   note="the measurement layer could not compute this family"))
    return result


# --------------------------------------------------------------------------- #
# cross-checking the model's measurer against the harness's own
# --------------------------------------------------------------------------- #


def cross_check(model_comparison: Comparison, reference_comparison: Comparison) -> tuple[Comparison, list[dict]]:
    """Merge two comparisons of the same solid, and report where they disagree.

    The measurer is model-written so it can adapt to a schema that varies per case.
    The cost of that is that it can also be *lax*: grouping families that facts keeps
    separate makes them match when they should not, and the structure check cannot
    see it because the document still has every family.

    Measured instance: scoring the same bracket STEP, the built-in measurer reported
    three missing bore families and a model-written one reported a single one.

    So both run, and the gate is the union -- a family either measurer calls wrong is
    wrong. Divergence is reported separately, because it is evidence about the
    measurer rather than about the part.
    """
    merged = Comparison(measured=model_comparison.measured)
    by_name = {check.name: check for check in model_comparison.checks}
    reference_by_name = {check.name: check for check in reference_comparison.checks}

    divergences: list[dict] = []
    for name, check in reference_by_name.items():
        mine = by_name.get(name)
        if mine is None:
            merged.checks.append(
                Check(name, check.expected, check.actual, check.verdict, gating=check.gating,
                      note="; ".join(filter(None, [
                          check.note,
                          "reported by the harness's own measurer; your document does not "
                          "contain this row",
                      ])))
            )
            if check.verdict in ("fail", "unverified"):
                divergences.append({"row": name, "your_measurer": "no such row",
                                    "harness": check.verdict,
                                    "harness_says": f"expected {check.expected}, measured {check.actual}"})
            continue

        # The union of the two verdicts, and the stricter evidence text.
        verdict = mine.verdict if mine.verdict == "fail" or check.verdict != "fail" else check.verdict
        if check.verdict == "fail":
            verdict = "fail"
        gating = mine.gating or check.gating
        note = mine.note
        if mine.verdict != check.verdict:
            divergences.append({"row": name, "your_measurer": mine.verdict,
                                "harness": check.verdict,
                                "harness_says": f"expected {check.expected}, measured {check.actual}"})
            note = "; ".join(filter(None, [note, "the two measurers disagree on this row"]))
            if check.verdict == "fail":
                note = "; ".join(filter(None, [check.note, "harness measurement disagrees"]))
        merged.checks.append(Check(name, mine.expected, mine.actual, verdict, gating=gating, note=note))

    seen = set(reference_by_name)
    for name, check in by_name.items():
        if name not in seen:
            merged.checks.append(check)
            if check.verdict in ("fail", "unverified"):
                divergences.append({"row": name, "your_measurer": check.verdict,
                                    "harness": "no such row",
                                    "harness_says": "the harness's measurer did not report this row"})

    merged.checks.append(
        Check("cross_measurement",
              "the two measurers agree",
              f"{len(divergences)} row(s) disagree",
              "pass" if not divergences else "fail",
              gating=False,
              note="" if not divergences else
                   "your measurer is more permissive than the harness's; the gate uses the "
                   "union, so fixing these rows is the way to a green gate")
    )
    return merged, divergences
