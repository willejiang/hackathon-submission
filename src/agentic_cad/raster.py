"""Orthographic silhouette rasterisation, in the reference frame.

The eight reference views were measured to establish their framing, rather than
guessed:

  test_case_1 (bbox 19 x 19 x 50.8)  front/back/left/right aspect 0.3753 ~ 19/50.8
                                     top/bottom aspect 1.0000 ~ 19/19
  test_case_3 (bbox 21.59 x 132.08 x 132.08)
                                     front/back aspect 0.1663 ~ 21.59/132.08
                                     left/right    1.0000
                                     top/bottom    0.1663

In every case the silhouette's largest extent occupies 986 px of the 1024 px frame
with a 19 px margin, centred. So each view is fitted independently: uniform scale,
max projected extent -> 986 px, then centred. That makes the comparison a pure
shape test -- position and absolute scale are normalised away, which is what
silhouette IoU is for, and why bounding box and volume are checked numerically
instead.

Silhouettes only: no shading, no depth buffer, no OpenGL. A triangle soup projected
onto a plane and filled is exactly the information the comparison needs, and it
runs headless in the container.
"""

from __future__ import annotations

import math
import os
import tempfile
from dataclasses import dataclass
from typing import Any

import numpy as np

FRAME_PX = 1024
FIT_PX = 986  # the reference views leave a 19 px margin on every side


@dataclass(frozen=True)
class View:
    """One camera: screen basis vectors and the direction it looks along."""

    stem: str
    u: tuple[float, float, float]  # image right, in model space
    v: tuple[float, float, float]  # image up, in model space


def _unit(v: tuple[float, float, float]) -> tuple[float, float, float]:
    n = math.sqrt(sum(c * c for c in v))
    return (v[0] / n, v[1] / n, v[2] / n)


def _iso_basis(camera: tuple[float, float, float]) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Screen basis for a camera sitting in direction `camera` from the part.

    `right = normalise(forward x world_up)`, `up = right x forward`, with
    `forward = -camera`. Falls back to a Y-ish up when the camera is straight down
    or up a world axis, which only the six orthographic views can be.
    """
    c = _unit(camera)
    forward = (-c[0], -c[1], -c[2])
    world_up = (0.0, 0.0, 1.0)
    right = (
        forward[1] * world_up[2] - forward[2] * world_up[1],
        forward[2] * world_up[0] - forward[0] * world_up[2],
        forward[0] * world_up[1] - forward[1] * world_up[0],
    )
    if math.sqrt(sum(x * x for x in right)) < 1e-9:
        right = (1.0, 0.0, 0.0)
    right = _unit(right)
    up = _unit(
        (
            right[1] * forward[2] - right[2] * forward[1],
            right[2] * forward[0] - right[0] * forward[2],
            right[0] * forward[1] - right[1] * forward[0],
        )
    )
    return right, up


def _iso_view(stem: str, camera: tuple[float, float, float]) -> View:
    u, v = _iso_basis(camera)
    return View(stem=stem, u=u, v=v)


# The six orthographic views use the axes stated in the challenge README verbatim.
# Deriving them generically would risk a mirrored image, and a mirrored silhouette
# scores as a total mismatch.
VIEWS: tuple[View, ...] = (
    View("view_0_front", u=(1.0, 0.0, 0.0), v=(0.0, 0.0, 1.0)),
    View("view_1_back", u=(-1.0, 0.0, 0.0), v=(0.0, 0.0, 1.0)),
    View("view_2_left", u=(0.0, -1.0, 0.0), v=(0.0, 0.0, 1.0)),
    View("view_3_right", u=(0.0, 1.0, 0.0), v=(0.0, 0.0, 1.0)),
    View("view_4_top", u=(1.0, 0.0, 0.0), v=(0.0, 1.0, 0.0)),
    View("view_5_bottom", u=(1.0, 0.0, 0.0), v=(0.0, -1.0, 0.0)),
    _iso_view("view_6_iso_front_right_top", (1.0, -1.0, 1.0)),
    _iso_view("view_7_iso_back_left_bottom", (-1.0, 1.0, -1.0)),
)

ORTHO_VIEWS = tuple(view for view in VIEWS if view.stem.startswith(("view_0", "view_1", "view_2", "view_3", "view_4", "view_5")))
ISO_VIEWS = tuple(view for view in VIEWS if "iso" in view.stem)


def mesh_of(shape: Any) -> tuple[np.ndarray, np.ndarray]:
    """Triangle mesh of a shape, as (vertices Nx3, triangles Mx3)."""
    from .meshutil import triangulate

    return triangulate(shape)


def project(vertices: np.ndarray, view: View) -> np.ndarray:
    """Project model-space vertices onto the view's 2D screen basis."""
    u = np.array(view.u, dtype=np.float64)
    v = np.array(view.v, dtype=np.float64)
    return np.column_stack((vertices @ u, vertices @ v))


def _fit(uv: np.ndarray, size: int = FRAME_PX, fit_px: int = FIT_PX) -> tuple[np.ndarray, float]:
    """Scale the projection so its largest extent is `fit_px`, and centre it.

    Returned in *maths* orientation: +x right, +y up, centred on the frame. The
    flip into image rows happens in `silhouette`, because PIL counts rows downward
    and a view's `v` means "up" in model space. Getting that wrong mirrors every
    vertically asymmetric part and is invisible on the symmetric ones -- which is
    exactly how it survived the first two test cases.
    """
    lo = uv.min(axis=0)
    hi = uv.max(axis=0)
    extent = hi - lo
    largest = float(extent.max())
    if largest <= 1e-9:
        return uv, 1.0
    scale = fit_px / largest
    centre_model = (lo + hi) / 2.0
    scaled = (uv - centre_model) * scale
    return scaled + (size / 2.0), scale


def silhouette(
    vertices: np.ndarray,
    triangles: np.ndarray,
    view: View,
    *,
    size: int = FRAME_PX,
    fit_px: int = FIT_PX,
) -> np.ndarray:
    """Filled binary silhouette of the mesh in one view.

    Row 0 of the returned array is the top of the image, so the model's `v` axis
    (image up) is negated on the way in.
    """
    from PIL import Image, ImageDraw

    uv = project(vertices, view)
    projected, _ = _fit(uv, size=size, fit_px=fit_px)

    # maths (y up) -> image (row down)
    points = np.column_stack((projected[:, 0] + 0.5, size - projected[:, 1] + 0.5))

    image = Image.new("1", (size, size), 0)
    draw = ImageDraw.Draw(image)
    for tri in triangles:
        p0, p1, p2 = points[tri[0]], points[tri[1]], points[tri[2]]
        draw.polygon(
            [(float(p0[0]), float(p0[1])), (float(p1[0]), float(p1[1])), (float(p2[0]), float(p2[1]))],
            fill=1,
        )
    return np.asarray(image, dtype=bool)


def render_all(shape: Any, *, views: tuple[View, ...] = VIEWS, size: int = FRAME_PX) -> dict[str, np.ndarray]:
    """Silhouettes for every view, keyed by stem."""
    vertices, triangles = mesh_of(shape)
    return {view.stem: silhouette(vertices, triangles, view, size=size) for view in views}
