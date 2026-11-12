"""In-memory triangulation shared by measurement and rendering.

Deliberately no temporary files: both the genus check and the rasteriser need the
same triangles, and a STEP/STL round trip through the OS temp directory is both
slower and fragile (a container with no usable TMPDIR breaks it). build123d can
tessellate a shape in place, so that is what is used.
"""

from __future__ import annotations

from typing import Any

import numpy as np

# Linear deflection in millimetres. Small enough that a fillet on a 200 mm part
# still resolves, coarse enough that a 500 mm engine block does not explode into
# millions of triangles inside the 20 minute budget.
DEFAULT_TOLERANCE_MM = 0.08
DEFAULT_ANGULAR_TOLERANCE_RAD = 0.25


def triangulate(
    shape: Any,
    *,
    tolerance: float = DEFAULT_TOLERANCE_MM,
    angular_tolerance: float = DEFAULT_ANGULAR_TOLERANCE_RAD,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (vertices Nx3 float64, triangles Mx3 int64) for a shape."""
    vertices, triangles = shape.tessellate(tolerance, angular_tolerance)
    xyz = np.array([[v.X, v.Y, v.Z] for v in vertices], dtype=np.float64)
    faces = np.asarray(triangles, dtype=np.int64)
    return xyz, faces


def euler_number(vertices: np.ndarray, faces: np.ndarray) -> int | None:
    """Euler characteristic of the triangulated surface, or None if not closed.

    Winding and duplicate vertices are repaired first: build123d and OCP emit
    per-face vertex lists, so the same geometric point appears many times and a
    naive V-E+F would be nonsense.
    """
    try:
        import trimesh
    except Exception:  # noqa: BLE001
        return None
    try:
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=True)
        mesh.merge_vertices()
        mesh.fix_normals()
        if not mesh.is_watertight:
            return None
        return int(mesh.euler_number)
    except Exception:  # noqa: BLE001
        return None


def genus(vertices: np.ndarray, faces: np.ndarray) -> int | None:
    """Genus of a closed single shell: chi = 2 - 2g."""
    chi = euler_number(vertices, faces)
    if chi is None:
        return None
    return int(round((2 - chi) / 2))
