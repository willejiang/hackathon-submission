---
name: cad-reconstruction
description: Reconstruct one mechanical part as STEP from facts.json, a brief and eight views, with the deterministic cad_* tools. Load before any CAD work here.
whenToUse: whenever the task is to build the cad model for a test_case, or to fix one that does not match its facts.
---

# CAD reconstruction

One mechanical part, graded by geometric similarity: **size and handedness matter,
position and orientation do not.**

`facts.json` is measurement, the brief is prose about the same part, the eight PNGs
are renders of it. Never modify `facts.json` or the brief. Positions are mm from the
bounding-box minimum corner.

## Ground truth

- A picture is evidence, the brief is evidence, `facts.json` is measurement.
- **When the prose contradicts the numbers, the numbers win.** On the practice set a
  bracket brief puts a recess at `Y = 7.0`; built there the volume comes out a third
  low, and the renders plus the measured volume both disagree with it. Resolve
  conflicts with arithmetic, and say so in `NOTES`.
- Missing dimensions may be estimated from a render, with a same-line
  `# estimated: view name and evidence` comment on the parameter in `derive()`.
  Keep known dimensions fixed. Never invent a hidden cavity to match volume alone.
- `facts.json` is optional. If absent, the case tool recovers explicit envelope,
  volume and passage constraints from the brief; undeclared properties stay unknown.

## The loop

1. `cad_case_info` — facts, brief, view paths, cameras.
2. `read_image` the views. **Silhouette first**: the outline, then the constraints it
   establishes (centred, collinear, symmetric, on a centreline).
3. Decide structure from **function**: what it mounts to, what passes through it, what
   it seals, what it is machined from. Function proposes, the specification disposes.
4. `write solution.py`.
5. `cad_build` — does it build, and what is it?
6. `cad_verify` — numbers against facts. Rows marked `*` are gating.
7. `cad_submit` — save the first valid single solid even if diagnostic rows fail.
8. `cad_facts_scaffold` → `write measure_result.py` → `cad_measure_result` — measure
   the submitted file into the brief's own structure and compare every entry.
9. `cad_render` — silhouettes against pictures, once the numbers are close.
10. **Re-read the view that shows the disagreement, then fix what the comparison names**,
    back to 4, for at most two improvement cycles. Stop early if there is no measured
    gain or the useful facts and views agree.

## Looking at the renders

Read them again **before every edit**, not only at step 2: a repair round driven by
numbers reproduces numbers only. On the practice V6 block the box, volume and all 23 bores were
right while both head plates, the webs, the spotfaces, the rib and every rebate were
absent: visible in the renders, absent from `facts.json`.

- **Crop, zoom, then `read_image` the crop.** Fine detail needs magnification.
- **Pixel arithmetic is not looking.** Masks and profiles give outline and proportion,
  never identity.
- **Your vision is adequate.** Counting bores and bolt holes matched `facts` exactly.
- **Blind versus through is not in the picture** -- the mouths look identical.

## The module

`solution.py` defines exactly two functions:

```python
def derive(facts):          # parsed facts.json -> dict of parameters
    d = {}
    d["length"] = facts["bounding_box_mm"]["x"]   # grounded
    d["wall"] = 14.0                              # grounded (brief: 14.0 mm)
    d["bore_r"] = d["bore_d"] / 2                 # derived
    return d

def build(p):               # the dict from derive() -> one build123d solid
    ...
```

Enforced by `cad_build` before it builds:

- `derive()` may contain a literal if that value is in facts.json or the brief,
  is structural (`0 1 2 3 -1 90 180 270`), or its line explicitly documents
  `# estimated: view and evidence` / `# assumed: reason`.
- `build()` may contain **only** structural literals. `Box(19, 14, 50.8)` fails;
  `Box(p["x"], p["y"], p["z"])` passes.
- No `open`, `eval`, `export_step`; imports limited to `build123d`, `math`,
  `itertools`, `numpy`, `typing`.

Millimetres, no scaling; one connected solid (fuse what you build in pieces);
bbox minimum at the origin; `Cylinder`/`Cone` are Z-up, so a bore along Y is
`Rot(90, 0, 0) * Cylinder(...)`, along X `Rot(0, 90, 0) * Cylinder(...)`.

Sketch coordinates are local XY, not world XZ. For an outline expressed as
`(x, z)` points and thickness `t` along Y, use
`Pos(0, t, 0) * extrude(Plane.XZ * profile, amount=t)` (XZ's normal is -Y).
For `(y, z)` points extruded along X, use `extrude(Plane.YZ * profile, amount=t)`.
Check the first coarse body's bounding-box axes before adding detailed features;
swapped height and thickness mean a wrong sketch plane, not a scaling problem.

Express relationships, do not restate numbers:
`d["centre"] = d["module"] * (d["z1"] + d["z2"]) / 2`.

## Measuring your own output

`facts.json` is not one schema: an extra field here, a different species set there,
radius dictionaries keyed by whatever this part has. A fixed measurer drops what it
did not anticipate, so **you** write one from the structure given:

1. `cad_facts_scaffold` — this case's facts.json with every number replaced by `null`;
   keys, nesting and list lengths only. You never see the expected values.
2. `write measure_result.py` defining `def measure(shape)` returning that structure.
   Aggregate each family once, by the fields facts uses to identify it, summing
   `faces`; one entry per axis leaves duplicate identities.
3. `cad_measure_result` — imports your submitted STEP, runs your measurer, checks the
   document's shape, compares every entry, writes `facts_from_result.json`. The harness
   also measures the solid with its own measurer and the gate takes the worse verdict,
   so a permissive measurer cannot hide a defect.

Refused before it runs, since one that could read the case directory could copy the
answers: no `open`/`eval`/`exec`, no `os`/`sys`/`json`/`pathlib`/`io`/`subprocess`;
imports limited to `build123d`/`OCP`/`math`/`itertools`/`numpy`/`typing`.

Conventions: axis labels `X`/`Y`/`Z` or `[x, y, z]`; surface names are
`face.geom_type.name`; degrees; millimetres.

## Reading the feedback

| symptom | likely cause |
|---|---|
| **genus too high** | **a blind hole or pocket was cut through** |
| genus too low | a blind hole missed, or a through bore plugged |
| **`hole_depths` fails** | **blind and through are not interchangeable** |
| **area 5%+ low, volume close** | **a whole feature family is missing** — read the face-type row |
| a species at 0 | that family is absent: `TORUS` rounds, `BSPLINE` fillets, `CONE` chamfers, `SPHERE` ball ends |
| a bore reported missing but you built it | check the axis: angled bores are direction vectors, and the wrong axis is a different bore |

`cad_render` gives IoU plus `overfill` and `underfill` per view. Both high with a bad
aspect ratio means a feature is in the wrong place, not the wrong size.

**Silhouettes cannot see a recess.** Measured: a 40 x 40 x 10 pocket removes 3.2% of
a block and changes zero pixels in all eight views. A part can score 0.985 with every
top-face pocket missing — that happened. `surface_area`, `genus` and the face-type row
are what catch it, plus the shading inside the outline when you look.

Counts are advisory: the references were built by fusing bodies, so the same solid can
have a different topology. A species at 0 is different — you never built that feature.

## Submit first, then improve

A missing file scores zero. Get a valid single solid and `cad_submit` it without
waiting for all diagnostic gates. Then make at most two targeted improvement cycles,
submitting after a measured gain. Never replace a good internal structure with
an arbitrary volume-matching void. One practice
run iterated to the deadline and submitted nothing; another submitted early and
finished with 15 of 16 bore families.

Nine parts share the clock. Simple ones take about two minutes. One perfect part and
eight zeroes loses to nine decent ones.
