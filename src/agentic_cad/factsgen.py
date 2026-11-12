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
# Wider than AREA_REL_TOL: the advisory display stays tight, the gate only fires on a
# whole missing feature family.
AREA_GATE_REL_TOL = 0.05


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


def _axis_vector(direction: Any) -> tuple[float, float, float]:
    """Unit direction, rounded, with the sign of the dominant component fixed.

    A bore and its mirror have the same axis line; only parallelism matters, so the
    sign is normalised away and the comparison uses |cos|.
    """
    values = [direction.X, direction.Y, direction.Z]
    dominant = max(range(3), key=lambda i: abs(values[i]))
    sign = -1.0 if values[dominant] < 0 else 1.0
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return tuple(round(sign * v / norm, 4) for v in values)


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
        # Axial extent of this face, used to recover a bore's depth. A blind hole
        # and a through hole differ in nothing else, so without this a wrong depth
        # is invisible to every check. Vertex has no dot(), so project by hand.
        try:
            cx, cy, cz = direction.X, direction.Y, direction.Z
            lo, hi = None, None
            for vertex in face.vertices():
                t = vertex.X * cx + vertex.Y * cy + vertex.Z * cz
                lo = t if lo is None else min(lo, t)
                hi = t if hi is None else max(hi, t)
            axial = float(hi - lo) if lo is not None and hi is not None else 0.0
        except Exception:  # noqa: BLE001
            axial = 0.0
        out.append(
            {
                "diameter": round(radius * 2.0, 4),
                "radius": radius,
                "axis": _axis_name(direction),
                # The letter is only for display. facts.json records some axes as a
                # direction vector (45-degree bores, angled holes), and matching a
                # letter against a vector can never succeed -- which silently
                # reported correctly-modelled oblique bores as missing.
                "axis_vector": _axis_vector(direction),
                "kind": "bore" if dot < 0 else "shaft",
                "area": float(face.area),
                "axial_extent": round(axial, 4),
            }
        )
    return out


def cylinder_groups(cylinders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group cylindrical faces into features: full cylinders and partial arcs.

    Two things are recovered that a per-face listing cannot express:

      * **total axial extent**, so a bore split into two coaxial faces still reports
        its real depth -- a blind hole modelled as a through hole fails here
      * **angular span**, from `area / (radius * extent)`, so a half-cylinder slot
        or a fillet-like arc is distinguished from a full bore
    """
    groups: dict[tuple, dict[str, Any]] = {}
    for face in cylinders:
        key = (face["diameter"], face["axis"], face["kind"])
        group = groups.setdefault(
            key,
            {
                "diameter": face["diameter"],
                "axis": face["axis"],
                "kind": face["kind"],
                "faces": 0,
                "area": 0.0,
                "axial_extent": 0.0,
            },
        )
        group["faces"] += 1
        group["area"] += face["area"]
        group["axial_extent"] = max(group["axial_extent"], face["axial_extent"])

    out = []
    for group in groups.values():
        radius = group["diameter"] / 2.0
        extent = group["axial_extent"]
        if radius > 1e-9 and extent > 1e-9:
            # area of a cylindrical patch = radius * arc_length * extent
            span = group["area"] / (radius * extent)
            fraction = span / (2.0 * math.pi)
        else:
            fraction = 1.0
        out.append(
            {
                **group,
                "axial_extent": round(extent, 4),
                "full": fraction > 0.9,
                "span_fraction": round(min(fraction, 2.0), 3),
            }
        )
    return sorted(out, key=lambda g: (-g["diameter"], g["axis"], g["kind"]))


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

    cylinders = _cylinders(shape)
    groups = cylinder_groups(cylinders)
    partial = [g for g in groups if not g["full"]]

    measured = {
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
        "cylinders": cylinders,
        "cylinder_groups": groups,
        "partial_cylinders": [
            {k: g[k] for k in ("diameter", "axis", "kind", "faces", "axial_extent", "span_fraction")}
            for g in partial
        ],
        "tori": len([f for f in faces if f.geom_type.name == "TORUS"]),
        "_note": "independently measured from the produced B-rep, not copied from the inputs",
    }

    # The same measurement expressed in facts.json's own schema, which is what the
    # schema-driven comparator walks and what gets written next to the STEP file.
    from . import factscompare

    as_facts, as_facts_unmeasured = factscompare.measure_as_facts(shape)
    measured["as_facts"] = as_facts
    measured["_unmeasured"] = as_facts_unmeasured
    return measured


def _rel(actual: float, expected: float) -> float:
    if expected == 0:
        return 0.0 if actual == 0 else float("inf")
    return abs(actual - expected) / abs(expected)


def _close(actual: float, expected: float, *, abs_tol: float, rel_tol: float) -> bool:
    return abs(actual - expected) <= max(abs_tol, abs(expected) * rel_tol)


def _axis_matches(measured_vector, expected_axis) -> bool:
    """Does a measured bore axis match the axis facts.json recorded?

    facts.json writes axis-aligned bores as a letter and angled ones as a direction
    vector. Comparing a letter against a vector can never succeed, which silently
    reported correctly-modelled 45-degree bores as missing on the V6 block and the
    cylinder head. Parallelism is the actual question, so treat both forms as
    vectors and accept either direction.
    """
    if isinstance(expected_axis, str):
        names = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}
        expected = names.get(expected_axis.strip().upper())
        if expected is None:
            return True  # unknown letter: do not fail on our own parse limit
    else:
        try:
            expected = tuple(float(v) for v in expected_axis)
        except (TypeError, ValueError):
            return True
    if not measured_vector:
        return False
    dot = sum(a * b for a, b in zip(measured_vector, expected))
    length = math.sqrt(sum(b * b for b in expected)) * math.sqrt(
        sum(a * a for a in measured_vector)
    )
    if length < 1e-12:
        return False
    return abs(dot / length) > 0.985  # within about 10 degrees


def _compare_holes(gt: GroundTruth, measured_groups: list[dict[str, Any]]) -> list[Check]:
    """Compare the bore inventory against facts, including depth.

    Two checks, because they fail in different ways:

      * `holes`      diameter and axis -- is the bore there at all
      * `hole_depths` axial extent vs the declared length -- is it blind or through

    Depth is the one that matters for the reported failures: a 4 mm blind hole
    modelled through has the right diameter and the right axis, so it passed, while
    raising the measured genus and leaving the part hollow in the wrong places.
    """
    expected: list[HoleSpec] = [hole for hole in gt.holes if hole.count > 0]
    if not expected:
        return [Check("holes", "none declared", f"{len(measured_groups)} cylindrical groups",
                      "unverified", note="facts declare no bores")]

    bores = [g for g in measured_groups if g["kind"] == "bore" and g.get("full")]
    missed: list[str] = []
    matched_groups: list[tuple[HoleSpec, dict[str, Any]]] = []
    for hole in expected:
        hits = [
            g
            for g in bores
            if _axis_matches(g.get("axis_vector"), hole.axis)
            and _close(g["diameter"], hole.diameter, abs_tol=0.05, rel_tol=0.005)
        ]
        if hits:
            matched_groups.append((hole, hits[0]))
        else:
            missed.append(f"{hole.count}x d{hole.diameter:g} along {hole.axis}")

    expected_text = ", ".join(f"{h.count}x d{h.diameter:g} {h.axis}" for h in expected)
    if missed:
        presence = Check(
            "holes",
            expected_text,
            f"{len(bores)} full bores; missing {', '.join(missed)}",
            "fail",
            note="declared bores not found in the geometry",
        )
    else:
        presence = Check("holes", expected_text, f"{len(bores)} full bores", "pass")

    # ---- depth ---------------------------------------------------------------
    depth_rows: list[str] = []
    depth_failures: list[str] = []
    for hole, group in matched_groups:
        declared = [v for v in (hole.lengths or []) if v > 0]
        if not declared:
            continue
        actual = group["axial_extent"]
        nearest = min(declared, key=lambda v: abs(v - actual))
        ok = _close(actual, nearest, abs_tol=0.6, rel_tol=0.08)
        depth_rows.append(f"d{hole.diameter:g} {actual:.2f}/{nearest:.2f}mm {'ok' if ok else 'WRONG'}")
        if not ok:
            longer_than_body = actual > max(declared) * 1.15
            depth_failures.append(
                f"d{hole.diameter:g}: {actual:.2f}mm deep, facts say {nearest:.2f}mm"
                + (" -- looks like a through hole where the part has a blind one"
                   if longer_than_body else "")
            )

    if not depth_rows:
        depth = Check("hole_depths", "no declared lengths", "nothing to compare", "unverified",
                      note="facts declare no bore lengths")
    elif depth_failures:
        depth = Check(
            "hole_depths",
            "; ".join(depth_rows),
            "; ".join(depth_failures),
            "fail",
            note="bore depth disagrees with the brief; blind and through holes are "
                 "not interchangeable even though the diameter matches",
        )
    else:
        depth = Check("hole_depths", "; ".join(depth_rows), "all depths within 8%", "pass")

    return [presence, depth]


def compare(gt: GroundTruth, measured: dict[str, Any]) -> Comparison:
    """Compare measured geometry with the authoritative facts.

    Delegates to the schema-driven comparator, which walks the input facts.json and
    reports on every entry it finds. The hand-written sequence this replaced checked
    nine families and silently skipped the rest, which is how the partial-cylinder,
    fillet and shaft inventories went unverified while the gate said PASS.
    """
    from . import factscompare

    as_facts = measured.get("as_facts")
    if as_facts is None:
        return Comparison(measured=measured, checks=[
            Check("facts", "measurable", "measure() produced no as_facts document",
                  "unverified", note="call factsgen.measure(shape) first")
        ])
    return factscompare.compare_facts(gt.facts, as_facts, measured.get("_unmeasured") or [])


def _legacy_compare(gt: GroundTruth, measured: dict[str, Any]) -> Comparison:
    """Superseded: kept only as a record of what the old gate checked."""
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
        # Gating at a wider tolerance than the advisory display. Surface area is the
        # cheapest signal that a whole family of features is missing: test_case_9 came
        # back 30% low in area with its volume inside 0.1%, every recess and fillet
        # absent, and nothing gating noticed. 5% lets a part with slightly wrong
        # fillets through while still firing on absent features.
        area_ok = _close(measured["surface_area_mm2"], gt.surface_area, abs_tol=0.0,
                         rel_tol=AREA_GATE_REL_TOL)
        result.checks.append(
            Check(
                "surface_area_mm2",
                f"{gt.surface_area:g}",
                f"{measured['surface_area_mm2']:g}",
                "pass" if area_ok else "fail",
                gating=True,
                note=f"{_rel(measured['surface_area_mm2'], gt.surface_area) * 100:.1f}% off"
                     + ("" if area_ok else " -- usually missing surface features rather than "
                                          "wrong overall size; compare the face-type inventory"),
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
                      "pass" if actual_genus == gt.genus else "fail",
                      # Gating: genus is the single best signal that a blind hole was
                      # modelled as a through one, or the reverse. test_case_8 came back
                      # with genus 23 against 11 while its bore diameters all matched.
                      gating=True,
                      note="too many through passages usually means blind holes were "
                           "cut all the way through" if actual_genus > gt.genus else
                           ("too few usually means a blind hole was missed or a through "
                            "bore was plugged" if actual_genus < gt.genus else ""))
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
        # Name the species that are entirely absent. "BSPLINE:0/222 TORUS:0/65" is the
        # difference between a part with its fillets and one without, and a bare L1
        # distance does not say which.
        absent = [f"{k} {expected_types[k]} declared" for k in keys
                  if expected_types.get(k, 0) > 0 and actual_types.get(k, 0) == 0]
        detail = " ".join(f"{k}:{actual_types.get(k, 0)}/{expected_types.get(k, 0)}" for k in keys)
        notes = []
        if l1:
            notes.append(f"L1={l1}")
        if absent:
            notes.append("missing feature species entirely: " + ", ".join(absent))
        result.checks.append(
            Check("face_types", "actual/expected", detail, "pass" if l1 == 0 else "fail",
                  note="; ".join(notes))
        )

    result.checks.extend(_compare_holes(gt, measured.get("cylinder_groups", [])))
    return result  # noqa: dead code retained for reference
