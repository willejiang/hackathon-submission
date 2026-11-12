---
name: cad-reconstruction
description: Reconstruct one mechanical part as STEP from facts.json, a design brief and eight rendered views, using the deterministic cad_* tools. Load this before any CAD work in this workspace.
whenToUse: whenever the task is to build the cad model for a test_case, or to fix one that does not match its facts.
---

# CAD reconstruction

You are reconstructing ONE mechanical part. It is graded by geometric similarity to
a hidden target, so **size and handedness matter, position and orientation do not**.

`facts.json` and `description.md` are measurements and prose about the real part.
They are authoritative. The eight PNGs are renders of the same part. They are
evidence, not specification.

## Ground truth

- Never modify, round away, or reinterpret `facts.json` or `description.md`.
- Positions in the brief are millimetres from the bounding-box minimum corner, in
  the frame of the eight views.
- **When the prose contradicts the numbers, the numbers win.** A picture is evidence
  and the brief is evidence, but `facts.json` is measurement. On the practice set the
  bracket's brief places a recess at `Y = 7.0`; built there, the volume comes out
  about a third low. The renders show the recess breaking through the front face, the
  measured volume agrees with them, and that reading matches the target to 0.17 mm3.
  So do not assume every conflict is your own misreading -- but do not overrule the
  numbers either. Resolve conflicts with arithmetic, and say so in `NOTES`.

## The loop

1. `cad_case_info` — facts, brief, view paths, camera conventions. Read it fully.
2. `read_image` each view. **Silhouette first**: describe the 2D outline (extents,
   straight runs, arcs, where a hole or slot interrupts it) before anything else.
   Then extract constraints the view can actually establish: a feature is centred,
   two edges are collinear, a step is symmetric, a hole sits on a centreline.
   Do not read millimetres off a render; the brief has the millimetres.
3. Decide the structure from **function** first — what the part mounts to, what
   passes through it, what it seals, what it is machined from — then let the brief
   confirm or veto each feature. Function proposes; the specification disposes.
4. `write` a module to `solution.py`.
5. `cad_build` — does it build, and what is it? Fix provenance or build errors here.
6. `cad_verify` — do the numbers match the facts? Rows marked `*` are gating.
7. `cad_render` — do the silhouettes match the pictures? Only meaningful once the
   numbers are close.
8. `cad_submit` — once the gating facts pass.

## Trust ranking for evidence

1. `facts.json` and `description.md` — authoritative
2. the six orthographic views — geometric evidence
3. the two isometric views — spatial sanity only

You are weak at images. Your attention may latch onto shading, a specular highlight,
or a boundary that is not a CAD edge. Compensate:

- a blind pocket and a through-hole look identical in one view; `through_holes_genus`
  in facts counts the through ones, and the brief says which is which
- if the brief says "no fillets" and the render looks rounded, that is shading
- never invent a hidden cavity from a silhouette
- never take a dimension from the isometric views

## The module contract

`solution.py` must define exactly:

```python
def derive(facts):
    """facts: the parsed facts.json dict. Return a dict of parameters."""
    d = {}
    d["length"] = facts["bounding_box_mm"]["x"]   # grounded
    d["wall"] = 14.0                              # grounded (brief: 14.0 mm thick)
    d["bore_r"] = d["bore_d"] / 2                 # derived
    return d

def build(p):
    """p: the dict from derive(). Return one build123d Solid/Part."""
    ...
```

Rules that `cad_build` enforces before it builds anything:

- `derive()` may contain a numeric literal **only** when that value appears in
  facts.json or the brief, or is structural: `0 1 2 3 -1 90 180 270`.
- `build()` may contain **only** those structural literals. Every dimension passes
  through `p`. Writing `Box(19, 14, 50.8)` fails; writing `Box(p["x"], p["y"], p["z"])`
  passes.
- No `open`, no `eval`, no `export_step`, no imports beyond `build123d`, `math`,
  `itertools`, `numpy`.

Also:

- millimetres, no scaling
- one connected solid — fuse multi-piece constructions
- put the bounding-box minimum corner at the origin
- `Cylinder`/`Cone` are Z-up; a hole along Y is `Rot(90, 0, 0) * Cylinder(...)`, along
  X is `Rot(0, 90, 0) * Cylinder(...)`
- a fillet the brief does not mention is a defect, not a flourish

Express relationships, do not restate numbers:

```python
d["centre"] = d["module"] * (d["z1"] + d["z2"]) / 2
d["boss_x"] = [d["centre"] * s for s in (-1, 1)]
```

## Reading the feedback

`cad_verify` gives you expected vs measured per fact. Rows marked `*` are gating.
Diagnose before editing:

| symptom | likely cause |
|---|---|
| volume and area both low | a described feature was never cut |
| volume and area both high | material the brief does not describe |
| volume off, area close | a feature has the right footprint at the wrong depth, or is in the wrong place |
| **genus too high** | **a blind hole or pocket was cut all the way through** |
| genus too low | a blind hole was missed, or a through bore was plugged |
| **`hole_depths` fails** | **blind and through are not interchangeable; the declared depth is the whole difference** |
| **area 5%+ low while volume is close** | **an entire feature family is missing — recesses, fillets, chamfers. The volume barely notices, the surface does. Read the face-type row.** |
| `face_types` names a species at 0 | that family is absent entirely: `TORUS` rounds, `BSPLINE` free-form fillets, `CONE` chamfers, `SPHERE` ball ends |
| a bore reported missing but you built it | check the axis: facts writes angled bores as a direction vector, and a bore on the wrong axis is a different bore |
| a face type present that facts lacks | a feature you invented; remove it, do not resize it |

`cad_render` gives IoU plus `overfill` and `underfill` per view. `overfill`
high means material where the reference is empty; `underfill` high means material
missing. Both high at once, with a wrong aspect ratio, means you put a feature in
the wrong place rather than sizing it wrong.

**The silhouette has a blind spot, and you have to cover it yourself.** A pocket cut
into a face does not change that face's outline. Measured: a 40 x 40 x 10 pocket
removes 3.2% of a block and changes *zero pixels* in all eight silhouettes. So IoU
can look excellent while every recess is missing — that is what happened on the
cylinder head, which scored 0.985 with its top-face pockets absent. What catches it
is `surface_area_mm2`, `through_holes_genus`, the face-type row, and the shading
*inside* the outline when you look at the picture. When the brief names a pocket,
confirm it by volume arithmetic and by the faces it adds, not by the silhouette.

Face and edge *counts* are advisory: the reference models may have been built by
fusing several bodies, so the same solid can have a different topology and still be
correct. Do not chase counts at the expense of the gating rows. But a face-type
species sitting at 0 is not a counting difference — it means you never built that
kind of feature at all.

## Never

- change a stated dimension to make a picture match
- tune a literal until a check turns green — write the formula instead
- leave a case without a file: submit something, always

## Submit early, then improve

A missing file scores zero; a mediocre file scores something. So:

1. Get a module that builds and whose gating facts pass — even if it has none of the
   recesses or fillets yet.
2. **`cad_submit` it.**
3. Keep improving, and call `cad_submit` again after each real improvement.

This is not a concession to a deadline, it is the correct order. On the practice
set one case ran out of time while still iterating and submitted nothing, wasting a
part whose gross geometry was already right. Submitting costs one tool call and can
only help.

## Budget

The whole run over nine parts has 20 minutes wall clock. Be economical: read the
views once, reason, write the module, measure, fix what the numbers say. Re-reading
images you already interpreted buys nothing. The practice set showed the split
clearly — the simple parts finish in about two minutes, and the ones with hundreds
of faces never converge in the time available, so for those spend your effort on
the gross geometry and the gating rows, submit, and move on. One perfect part and
eight zeroes loses to nine decent ones.
