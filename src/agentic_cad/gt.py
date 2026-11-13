"""Authoritative ground truth for one test case.

`facts.json` and `description.md` are the specification. Nothing downstream may
change them, and every geometric parameter must be traceable either to a value in
them or to a formula over such values. This module is the single place that loads
and exposes them.

Provenance vocabulary (used by `provenance.py` and by the prompt):

    grounded   the value appears explicitly in facts.json or description.md
    derived    computed from grounded values through a named formula
    estimated  inferred from the rendered views (never presented as ground truth)
    assumed    a provisional free parameter needed to build a candidate

Only `grounded` and `derived` may end up in a submitted part without being
labelled; `estimated`/`assumed` values must be declared and are the first things
to revisit when verification disagrees.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class HoleSpec:
    """One entry of `cylindrical_holes_and_bores`."""

    diameter: float
    axis: str
    count: int
    lengths: tuple[float, ...]
    centres: tuple[tuple[float, float, float], ...]


@dataclass
class GroundTruth:
    """Immutable-in-spirit view of one test case's authoritative inputs."""

    name: str
    facts: dict[str, Any]
    description: str
    views: list[Path]
    context: Path | None

    # --- convenience accessors ------------------------------------------------
    @property
    def bbox(self) -> tuple[float, float, float]:
        box = self.facts.get("bounding_box_mm") or {}
        return (
            float(box.get("x") or 0.0),
            float(box.get("y") or 0.0),
            float(box.get("z") or 0.0),
        )

    @property
    def volume(self) -> float | None:
        value = self.facts.get("volume_mm3")
        return float(value) if isinstance(value, (int, float)) else None

    @property
    def surface_area(self) -> float | None:
        value = self.facts.get("surface_area_mm2")
        return float(value) if isinstance(value, (int, float)) else None

    @property
    def solids(self) -> int | None:
        value = self.facts.get("solids")
        return int(value) if isinstance(value, int) else None

    @property
    def genus(self) -> int | None:
        value = self.facts.get("through_holes_genus")
        return int(value) if isinstance(value, int) else None

    @property
    def faces(self) -> int | None:
        value = self.facts.get("faces")
        return int(value) if isinstance(value, int) else None

    @property
    def edges(self) -> int | None:
        value = self.facts.get("edges")
        return int(value) if isinstance(value, int) else None

    @property
    def face_types(self) -> dict[str, int]:
        value = self.facts.get("face_types") or {}
        return {str(k): int(v) for k, v in value.items()}

    @property
    def holes(self) -> list[HoleSpec]:
        out: list[HoleSpec] = []
        for row in self.facts.get("cylindrical_holes_and_bores") or []:
            if not isinstance(row, dict):
                continue
            out.append(
                HoleSpec(
                    diameter=float(row.get("diameter") or 0.0),
                    axis=str(row.get("axis") or "?"),
                    count=int(row.get("count") or 0),
                    lengths=tuple(float(v) for v in (row.get("lengths") or [])),
                    centres=tuple(
                        tuple(float(c) for c in centre)
                        for centre in (row.get("centres") or [])
                        if isinstance(centre, (list, tuple)) and len(centre) == 3
                    ),
                )
            )
        return out

    @property
    def shafts(self) -> list[dict[str, Any]]:
        return [r for r in (self.facts.get("cylindrical_shafts_and_bosses") or []) if isinstance(r, dict)]

    @property
    def partial_cylinders(self) -> list[dict[str, Any]]:
        return [r for r in (self.facts.get("partial_cylinders_arcs") or []) if isinstance(r, dict)]

    @property
    def fillets(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        cyl = [r for r in (self.facts.get("fillets_rounds_from_cylinders") or []) if isinstance(r, dict)]
        tori = self.facts.get("fillets_from_tori_minor_radii") or {}
        return cyl, dict(tori)

    # --- prompt material ------------------------------------------------------
    def fact_sheet(self) -> str:
        """Render the facts as a compact, stable block for the model.

        Kept deterministic (sorted keys, fixed rounding) so prompt caching works
        and so a diff between two runs means a real change.
        """
        lines = [f"# facts.json ({self.name})", "```json", json.dumps(self.facts, indent=1, sort_keys=True), "```"]
        lines.append("")
        lines.append("# description.md")
        lines.append("```markdown")
        lines.append(self.description.strip())
        lines.append("```")
        return "\n".join(lines)

    def known_numbers(self) -> set[float]:
        """Every number that appears in the authoritative inputs.

        Used by the provenance check: a literal in a derived formula is legal when
        it is one of these (or a trivially structural 0/1/2), otherwise the model
        must justify it.
        """
        values: set[float] = set()

        def walk(node: Any) -> None:
            if isinstance(node, bool):
                return
            if isinstance(node, (int, float)):
                values.add(round(float(node), 6))
            elif isinstance(node, str):
                for token in re.findall(r"-?\d+(?:\.\d+)?", node):
                    try:
                        values.add(round(float(token), 6))
                    except ValueError:
                        pass
            elif isinstance(node, dict):
                for value in node.values():
                    walk(value)
            elif isinstance(node, (list, tuple)):
                for value in node:
                    walk(value)

        walk(self.facts)
        for token in re.findall(r"-?\d+(?:\.\d+)?", self.description):
            try:
                values.add(round(float(token), 6))
            except ValueError:
                pass
        return values

    def numbers_in_description(self) -> list[float]:
        out: list[float] = []
        for token in re.findall(r"-?\d+(?:\.\d+)?", self.description):
            try:
                out.append(float(token))
            except ValueError:
                pass
        return out


def load_case(case_dir: Path) -> GroundTruth:
    """Load one `test_case_<n>` directory."""
    facts_path = case_dir / "facts.json"
    description_path = case_dir / "description.md"
    facts: dict[str, Any] = {}
    if facts_path.is_file():
        try:
            facts = json.loads(facts_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            facts = {}
    description = description_path.read_text(encoding="utf-8") if description_path.is_file() else ""
    if not facts:
        facts = facts_from_description(description)
    images = case_dir / "images"
    views = sorted(images.glob("view_*.png")) if images.is_dir() else []
    context = case_dir / "context.png"
    return GroundTruth(
        name=case_dir.name,
        facts=facts,
        description=description,
        views=views,
        context=context if context.is_file() else None,
    )


def facts_from_description(description: str) -> dict[str, Any]:
    """Recover only explicitly stated scalar constraints when facts.json is absent.

    The extended practice README describes hidden inputs without the debugging
    fact sheet. Do not invent a hole inventory, surface area, or any other
    measurements: the model still receives the complete design brief and views.
    Nothing is written back into the input directory.
    """
    number = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
    text = description.replace("\u00a0", " ")
    facts: dict[str, Any] = {"_input_source": "description.md"}
    envelope = re.search(
        rf"\bEnvelope\s*:\s*\**\s*({number})\s*[xX×]\s*({number})\s*[xX×]\s*({number})\s*mm\b",
        text, re.IGNORECASE,
    )
    if envelope:
        values = [float(value.replace(",", "")) for value in envelope.groups()]
        if all(value > 0 for value in values):
            facts["bounding_box_mm"] = dict(zip("xyz", values))
    volume = re.search(rf"\bvolume\s*[:=]?\s*({number})\s*(mm|cm)\s*(?:\^\s*3|³|3)\b", text, re.IGNORECASE)
    if volume:
        value = float(volume.group(1).replace(",", ""))
        if value > 0:
            facts["volume_mm3"] = value * (1000 if volume.group(2).lower() == "cm" else 1)
    passages = re.search(r"\b(\d+)\s+through[\s\-‑–]+passages\b", text, re.IGNORECASE)
    if passages:
        facts["through_holes_genus"] = int(passages.group(1))
    return facts
