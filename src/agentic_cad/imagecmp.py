"""Silhouette comparison between rendered views and the reference renders.

Three decisions, all deliberate:

  * **only silhouettes are compared.** The references are shaded CAD renders with
    lighting; RGB similarity would measure the renderer, not the part. The outline
    is also the one thing a weak image reader can be trusted to get right, which is
    why the workflow is told to reason about silhouettes first.

  * **both sides are normalised before overlap is computed.** Each mask is cropped
    to its own bounding box, scaled so its largest extent fills the same fraction
    of the canvas, and centred; aspect ratio is preserved. The reference framings
    are not uniform -- the six orthographic views fit the largest extent to 986 px
    of 1024, while the two isometric views use a smaller scale -- so reproducing
    the framing exactly would be guesswork. Normalising makes the test
    scale- and translation-invariant and leaves shape and proportion as the only
    things that can fail. Absolute size is already covered by the numeric facts
    check, a far better instrument for it.

  * **overlap is reported as three numbers, not one.** A single IoU says a view is
    wrong; `overfill` (extra material) and `underfill` (missing material) say which
    kind of wrong, and that is what the diagnosis step needs. A differing aspect
    ratio is reported separately because it means the part's proportions changed,
    which a normalised IoU partially hides.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Distance from the reference background below which a pixel is background.
# The reference renders are pure-white-background CAD images; a pixel belongs to
# the object once it is meaningfully darker than white.
BACKGROUND_DELTA = 10

# Fraction of the comparison canvas the object's largest extent should occupy.
NORMALISED_FIT = 0.96

# Pixels of translation to search after normalisation, so rasterisation
# differences do not dominate the score.
_ALIGN_SEARCH_PX = 8


def reference_mask(path: Path) -> np.ndarray:
    """Binary silhouette of a reference render."""
    from PIL import Image
    from scipy import ndimage

    rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.int16)
    # A part lit by the renderer is never brighter than the background, so the
    # minimum channel is the safest single indicator of "something is here".
    mask = (255 - rgb.min(axis=2)) > BACKGROUND_DELTA
    # Specular highlights can bleach a few interior pixels to pure white; close
    # those without touching genuine holes, which are far larger than 1-2 px.
    mask = ndimage.binary_closing(mask, structure=np.ones((3, 3), dtype=bool))
    return mask


def normalise(mask: np.ndarray, size: int = 512, fit: float = NORMALISED_FIT) -> np.ndarray:
    """Crop to the object, scale its largest extent, and centre it.

    Aspect ratio is preserved, so a part that is too long or too wide still fails
    the overlap test instead of being rescaled into agreement.
    """
    from PIL import Image

    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    if not rows.any() or not cols.any():
        return np.zeros((size, size), dtype=bool)

    r0, r1 = np.where(rows)[0][[0, -1]]
    c0, c1 = np.where(cols)[0][[0, -1]]
    cropped = mask[r0 : r1 + 1, c0 : c1 + 1]

    height, width = cropped.shape
    target = max(1, int(round(size * fit)))
    scale = target / max(height, width)
    new_w = max(1, int(round(width * scale)))
    new_h = max(1, int(round(height * scale)))

    image = Image.fromarray((cropped.astype(np.uint8) * 255), mode="L").resize(
        (new_w, new_h), Image.BILINEAR
    )
    resized = np.asarray(image) > 127

    canvas = np.zeros((size, size), dtype=bool)
    top = (size - new_h) // 2
    left = (size - new_w) // 2
    canvas[top : top + new_h, left : left + new_w] = resized
    return canvas


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    union = np.count_nonzero(a | b)
    if union == 0:
        return 1.0
    return np.count_nonzero(a & b) / union


def _best_shift(reference: np.ndarray, render: np.ndarray) -> tuple[int, int, float]:
    best = (0, 0, _iou(reference, render))
    for dy in range(-_ALIGN_SEARCH_PX, _ALIGN_SEARCH_PX + 1):
        for dx in range(-_ALIGN_SEARCH_PX, _ALIGN_SEARCH_PX + 1):
            if dx == 0 and dy == 0:
                continue
            shifted = np.roll(np.roll(render, dy, axis=0), dx, axis=1)
            score = _iou(reference, shifted)
            if score > best[2]:
                best = (dx, dy, score)
    return best


@dataclass
class ViewScore:
    stem: str
    iou: float
    overfill: float   # extra material: rendered where the reference is empty
    underfill: float  # missing material: empty where the reference is solid
    shift: tuple[int, int]
    aspect_ref: float
    aspect_render: float

    @property
    def aspect_error(self) -> float:
        if self.aspect_ref == 0:
            return 0.0
        return self.aspect_render / self.aspect_ref - 1.0

    def render(self) -> str:
        return (
            f"{self.stem:32} IoU={self.iou:.3f} over={self.overfill:+.3f} under={self.underfill:+.3f} "
            f"aspect {self.aspect_render:.3f}/{self.aspect_ref:.3f} ({self.aspect_error:+.1%})"
        )


def _aspect(mask: np.ndarray) -> float:
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    if not rows.any() or not cols.any():
        return 0.0
    r0, r1 = np.where(rows)[0][[0, -1]]
    c0, c1 = np.where(cols)[0][[0, -1]]
    return float((c1 - c0 + 1) / (r1 - r0 + 1))


def compare_view(stem: str, reference: np.ndarray, render: np.ndarray, *, size: int = 512) -> ViewScore:
    """Normalised silhouette comparison for one view."""
    ref_norm = normalise(reference, size=size)
    render_norm = normalise(render, size=size)

    dx, dy, iou = _best_shift(ref_norm, render_norm)
    shifted = np.roll(np.roll(render_norm, dy, axis=0), dx, axis=1)

    ref_area = float(np.count_nonzero(ref_norm))
    if ref_area == 0:
        return ViewScore(stem, iou, 0.0, 0.0, (dx, dy), _aspect(reference), _aspect(render))

    extra = float(np.count_nonzero(shifted & ~ref_norm))
    missing = float(np.count_nonzero(ref_norm & ~shifted))
    return ViewScore(
        stem=stem,
        iou=iou,
        overfill=extra / ref_area,
        underfill=missing / ref_area,
        shift=(dx, dy),
        aspect_ref=_aspect(reference),
        aspect_render=_aspect(render),
    )


@dataclass
class Comparison:
    views: list[ViewScore]

    @property
    def mean_iou(self) -> float:
        return sum(v.iou for v in self.views) / len(self.views) if self.views else 0.0

    @property
    def mean_iou_ortho(self) -> float:
        ortho = [v for v in self.views if "iso" not in v.stem]
        return sum(v.iou for v in ortho) / len(ortho) if ortho else 0.0

    @property
    def mean_iou_iso(self) -> float:
        iso = [v for v in self.views if "iso" in v.stem]
        return sum(v.iou for v in iso) / len(iso) if iso else 0.0

    @property
    def worst(self) -> list[ViewScore]:
        return sorted(self.views, key=lambda v: v.iou)[:3]

    def render(self) -> str:
        lines = [
            f"mean IoU all={self.mean_iou:.3f} ortho={self.mean_iou_ortho:.3f} iso={self.mean_iou_iso:.3f}"
        ]
        lines.extend(v.render() for v in self.views)
        return "\n".join(lines)

    def advise(self) -> str:
        """What the diagnosis step should hear about the images."""
        lines: list[str] = []
        for view in self.worst:
            if view.iou >= 0.97:
                continue
            if abs(view.aspect_error) > 0.05:
                kind = f"proportions are wrong (aspect {view.aspect_render:.2f} vs {view.aspect_ref:.2f})"
            elif view.overfill > view.underfill:
                kind = "extra material"
            else:
                kind = "missing material"
            lines.append(
                f"- {view.stem}: IoU {view.iou:.3f}, {kind} "
                f"(over {view.overfill:+.1%}, under {view.underfill:+.1%})"
            )
        if not lines:
            lines.append("- silhouettes agree with the references on all eight views")
        return "\n".join(lines)


def compare_all(reference_dir: Path, rendered: dict[str, np.ndarray]) -> Comparison:
    """Compare every rendered silhouette with the matching reference file."""
    scores: list[ViewScore] = []
    for stem, mask in rendered.items():
        path = reference_dir / f"{stem}.png"
        if not path.is_file():
            continue
        scores.append(compare_view(stem, reference_mask(path), mask))
    return Comparison(views=scores)
