"""Execute a generated module and turn it into a submission-ready solid.

Responsibilities, and nothing else:

  - run `derive(facts)` then `build(p)` in a fresh namespace
  - require exactly one connected solid, in millimetres
  - translate the solid so the minimum corner of its bounding box is at the origin
  - export STEP for the submission

The generated code is not sandboxed: it runs in this process. What protects the
run is `provenance.check`, which rejects file I/O, process spawning and disallowed
imports before execution, plus the fact that this container is disposable. If that
trust model ever changes, this is the place to add a subprocess boundary.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .gt import GroundTruth


@dataclass
class BuildResult:
    ok: bool
    shape: Any = None
    error: str = ""
    stage: str = ""
    warnings: list[str] = field(default_factory=list)
    params_preview: str = ""

    def failure_text(self) -> str:
        head = f"build failed in {self.stage or 'unknown stage'}: {self.error}"
        return head + ("\n" + "\n".join(self.warnings) if self.warnings else "")


def _trim_traceback(exc: BaseException, *, depth: int = 6) -> str:
    lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    tail = lines[-depth:]
    return "".join(tail).strip()


def run_module(gt: GroundTruth, source: str) -> BuildResult:
    """Execute one generated module and return the built solid."""
    namespace: dict[str, Any] = {"__name__": "generated_part", "__builtins__": __builtins__}
    try:
        exec(compile(source, "<generated>", "exec"), namespace)  # noqa: S102 - reviewed by provenance.check
    except Exception as exc:  # noqa: BLE001 - the generated code may raise anything
        return BuildResult(ok=False, stage="import", error=f"{type(exc).__name__}: {exc}")

    if not callable(namespace.get("derive")):
        return BuildResult(ok=False, stage="contract", error="no callable `derive(facts)`")
    if not callable(namespace.get("build")):
        return BuildResult(ok=False, stage="contract", error="no callable `build(p)`")

    try:
        params = namespace["derive"](gt.facts)
    except Exception as exc:  # noqa: BLE001
        return BuildResult(ok=False, stage="derive", error=_trim_traceback(exc))

    if not isinstance(params, dict):
        return BuildResult(ok=False, stage="derive", error=f"derive() returned {type(params).__name__}, expected dict")

    try:
        shape = namespace["build"](params)
    except Exception as exc:  # noqa: BLE001
        return BuildResult(ok=False, stage="build", error=_trim_traceback(exc))

    if shape is None:
        return BuildResult(ok=False, stage="build", error="build() returned None")

    try:
        solids = list(shape.solids())
    except Exception as exc:  # noqa: BLE001
        return BuildResult(ok=False, stage="build", error=f"returned object is not a shape: {exc}")

    if not solids:
        return BuildResult(ok=False, stage="build", error="build() produced no solid")
    if len(solids) > 1:
        volumes = ", ".join(f"{solid.volume:.1f}" for solid in solids[:6])
        return BuildResult(
            ok=False,
            stage="build",
            error=(
                f"build() produced {len(solids)} separate solids (volumes mm^3: {volumes}); "
                "the part must be one connected solid - fuse the pieces or remove the stray geometry"
            ),
        )

    solid = solids[0]
    try:
        solid = _normalise(solid)
    except Exception as exc:  # noqa: BLE001
        return BuildResult(ok=False, stage="normalise", error=_trim_traceback(exc))

    preview = ", ".join(f"{key}={value:.4g}" if isinstance(value, (int, float)) else f"{key}={type(value).__name__}"
                        for key, value in list(params.items())[:12])
    return BuildResult(ok=True, shape=solid, params_preview=preview)


def _normalise(solid: Any) -> Any:
    """Translate the solid so its bounding-box minimum corner sits at the origin.

    The submission does not care about position, but the reference views are drawn
    in a frame whose origin is the bounding-box minimum corner, so putting the part
    there makes the render comparison a pure shape test.
    """
    box = solid.bounding_box()
    offset = box.min
    if abs(offset.X) < 1e-9 and abs(offset.Y) < 1e-9 and abs(offset.Z) < 1e-9:
        return solid
    from build123d import Pos  # local import keeps module import cheap

    return Pos(-offset.X, -offset.Y, -offset.Z) * solid


def export_step(shape: Any, path: Path) -> None:
    """Write the STEP file the submission is graded on."""
    from build123d import export_step as _export

    path.parent.mkdir(parents=True, exist_ok=True)
    _export(shape, str(path))


def reopen_step(path: Path) -> Any:
    """Re-import a STEP file and return the first solid.

    Used by verification: the submitted artifact must survive a round trip, and it
    is the re-imported geometry that gets measured, never the in-memory shape.
    """
    from build123d import import_step

    shape = import_step(str(path))
    solids = list(shape.solids())
    if not solids:
        raise ValueError("no solid in the STEP file")
    return solids[0] if len(solids) == 1 else shape
