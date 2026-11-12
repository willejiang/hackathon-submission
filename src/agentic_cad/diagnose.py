"""Failure classification between attempts.

The point of classifying rather than just reporting is that different causes need
different fixes:

  formula_error        one equation is wrong; change the equation
  formula_missing      two dimensions were independent numbers; write the relation
  constraint_missing   a described feature was never modelled; add it
  constraint_wrong     a feature is there but contradicts the brief; resize it
  constraint_excess    material or a feature the brief does not describe; remove it
  image_misread        a visual conclusion was wrong; discard it and re-read the brief
  topology_error       not one valid connected solid
  build_error          the code did not build

The classifier below is deterministic and runs without a model, so the loop still
produces a usable diagnosis when the endpoint is unavailable. A model-based
diagnosis is layered on top when one is configured (`prompts.DIAGNOSIS_SYSTEM`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .factsgen import Comparison
from .gt import GroundTruth


@dataclass
class Cause:
    label: str
    detail: str


@dataclass
class Diagnosis:
    causes: list[Cause] = field(default_factory=list)
    measurements: str = ""
    images: str = ""

    @property
    def primary(self) -> str:
        return self.causes[0].label if self.causes else "unknown"

    def render(self) -> str:
        lines = [f"primary cause: {self.primary}", ""]
        lines.extend(f"- [{cause.label}] {cause.detail}" for cause in self.causes)
        if self.measurements:
            lines.extend(["", "measured vs expected:", self.measurements])
        if self.images:
            lines.extend(["", "silhouettes:", self.images])
        return "\n".join(lines)


def classify(
    gt: GroundTruth,
    facts_cmp: Comparison,
    img_cmp: Comparison | None,
    *,
    build_error: str = "",
) -> Diagnosis:
    """Turn measurement disagreement into named causes, most likely first."""
    causes: list[Cause] = []

    if build_error:
        lowered = build_error.lower()
        if "separate solids" in lowered or "no solid" in lowered:
            causes.append(Cause("topology_error", build_error.strip()))
        else:
            causes.append(Cause("build_error", build_error.strip().splitlines()[0][:400]))

    measured = facts_cmp.measured
    by_name = {check.name: check for check in facts_cmp.checks}

    def failed(name: str) -> bool:
        check = by_name.get(name)
        return check is not None and check.verdict in ("fail", "unverified")

    volume_fail = failed("volume_mm3")
    area_fail = failed("surface_area_mm2")
    genus_fail = failed("through_holes_genus")
    holes_fail = failed("holes")
    bbox_fail = failed("bounding_box_mm")
    faces_fail = failed("faces")
    types_fail = failed("face_types")

    if bbox_fail:
        causes.append(
            Cause(
                "constraint_wrong",
                "the envelope disagrees with bounding_box_mm. Either a stated envelope dimension was "
                "not used, or a feature extends past the envelope (a recess cut the wrong way, a rib "
                "on the wrong face, a boss overshooting).",
            )
        )

    if genus_fail:
        expected = gt.genus
        actual = measured.get("through_holes_genus")
        causes.append(
            Cause(
                "constraint_wrong",
                f"through-hole topology is wrong: expected genus {expected}, measured {actual}. "
                "A blind pocket modelled as a through cut (or the reverse) is the usual cause; "
                "check the brief word by word for 'blind', 'through' and 'does not break through'.",
            )
        )

    if holes_fail:
        causes.append(
            Cause(
                "constraint_missing",
                "at least one declared bore/boss family is absent or at the wrong axis. "
                "facts.json names each diameter, axis and count: model every entry.",
            )
        )

    if volume_fail and not area_fail:
        direction = "less" if (measured["volume_mm3"] < (gt.volume or 0)) else "more"
        causes.append(
            Cause(
                "constraint_wrong",
                f"volume is {direction} than the target while surface area is close: a feature has "
                "the right footprint but the wrong depth, or a pocket of the right size is in the "
                "wrong place. Favour depth/position changes over new features.",
            )
        )
    elif volume_fail and area_fail:
        direction = "less" if (measured["volume_mm3"] < (gt.volume or 0)) else "more"
        causes.append(
            Cause(
                "constraint_missing" if direction == "less" else "constraint_excess",
                f"volume and surface area are both {direction} than the target, so "
                f"{'a described feature was never cut' if direction == 'less' else 'material was added that the brief does not describe'}. "
                "Compare the feature list in the brief against the features you modelled, one by one.",
            )
        )

    if types_fail:
        expected_types = gt.face_types
        actual_types = measured.get("face_types", {})
        missing = sorted(set(expected_types) - set(actual_types))
        if missing:
            hint = {
                "CONE": "a chamfer or countersink is missing",
                "TORUS": "a fillet or round is missing",
                "SPHERE": "a spherical end or ball feature is missing",
                "BSPLINE": "a free-form surface is missing",
                "CYLINDER": "a cylindrical face is missing (bore, boss, or arc)",
            }
            causes.append(
                Cause(
                    "constraint_missing",
                    f"face types absent from the geometry: {', '.join(missing)}"
                    + ("; " + "; ".join(hint.get(m, "") for m in missing).strip("; ") if any(hint.get(m) for m in missing) else ""),
                )
            )
        extra = sorted(set(actual_types) - set(expected_types))
        if extra:
            causes.append(
                Cause(
                    "constraint_excess",
                    f"face types present that the target does not have: {', '.join(extra)}. "
                    "The brief does not describe that kind of feature; remove it rather than resize it.",
                )
            )

    if faces_fail and not types_fail and not holes_fail:
        expected = gt.faces
        actual = measured.get("faces")
        if isinstance(expected, int) and isinstance(actual, int):
            delta = actual - expected
            causes.append(
                Cause(
                    "constraint_excess" if delta > 0 else "constraint_missing",
                    f"face count is off by {delta:+d} ({actual} vs {expected}) with the right face "
                    "species: "
                    + ("too many distinct features or a feature split into two" if delta > 0 else "a described feature is absent"),
                )
            )

    if img_cmp is not None:
        worst = [v for v in img_cmp.views if v.iou < 0.93]
        if worst:
            view = worst[0]
            if view.overfill > view.underfill * 1.5:
                causes.append(
                    Cause(
                        "constraint_excess",
                        f"{view.stem} silhouette has {view.overfill:+.1%} extra area and only "
                        f"{view.underfill:+.1%} missing: material exists where the reference is empty. "
                        "Look for a cut you did not make, or a feature that is too large in that projection.",
                    )
                )
            elif view.underfill > view.overfill * 1.5:
                causes.append(
                    Cause(
                        "constraint_missing",
                        f"{view.stem} silhouette is missing {view.underfill:.1%} of its area with only "
                        f"{view.overfill:+.1%} extra: material is absent where the reference is solid. "
                        "Check the silhouette outline of that view against the feature list.",
                    )
                )
            else:
                causes.append(
                    Cause(
                        "image_misread",
                        f"{view.stem} disagrees both ways (over {view.overfill:+.1%}, under "
                        f"{view.underfill:+.1%}), which is the signature of a wrong interpretation of "
                        "that view rather than a wrong size: a feature is in the wrong place, or the "
                        "view's orientation/occlusion was read incorrectly.",
                    )
                )

    if not causes:
        causes.append(
            Cause(
                "formula_error",
                "every coarse check passes but acceptance did not, so the residual error is inside a "
                "formula: re-derive each dependent dimension from its grounded parents instead of "
                "adjusting the result.",
            )
        )

    return Diagnosis(
        causes=causes,
        measurements=facts_cmp.render(),
        images=img_cmp.render() if img_cmp is not None else "",
    )
