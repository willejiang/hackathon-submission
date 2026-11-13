# Case 8 follow-up geometry probes

All work is confined to this directory and remote `/home/ubuntu/case8-opt2`.
`base.stp` is the official 0.916 blind-X pump model; `ears.stp` is the
validated short-ear checkpoint from case8-opt v2. `reproduce.py` constructs the
subsequent probe solids and checks STEP round-trip validity/single-solidness.
`probe.py` measures independent facts and silhouette overlap against the input.

Recommended probes:

| Candidate | Volume/target | Area/target | Local IoU | Status |
|---|---:|---:|---:|---|
| ears-bolt-mouths-v9 | .98594 | 1.05756 | .95965 | valid, single solid/shell |
| ears-bolt-blind-mainclear-v11 | 1.00943 | 1.03943 | .97935 | valid, single solid/shell |
| ears-bolt-blind-deeppockets-v13 | .99439 | 1.03226 | .98714 | valid, single solid/shell |
| ears-bolt-blind-oil-deeppockets-v14 | .99482 | 1.03268 | .98714 | valid, single solid/shell |

v14 includes v13 and moves the two 30.2-mm vertical oil passages from the old
STEP's Z=0..30.2 to facts' Z=5..35.2. A 0.015-mm Y offset prevents a coincident
tangency to the Y-facing drilling ends.

Evidence and limitations:
- Four outside ears have short spherical-ended lobes in front/back/iso views;
  the two lower corner bosses remain full height.
- Original bolt openings have large 2-mm-deep conical counterbores, whereas the
  reference shows narrow 7-mm mouths. v9 restores nominal 12-mm boss annuli.
- Exact top and bottom views shade all eight bolt openings gold, with a visible
  conical drill point. v11 tests opposing blind drillings with 59-degree tips.
  This **conflicts with the text's through-hole interpretation**, so it needs
  the official overlap/surface scorer; local masks alone cannot establish truth.
- Side-bolt stops are short and the 20-mm transverse main bore is recut after
  all Z-hole work, preserving the clear main opening.
- Front-view 6-mm holes are mostly background white with a thin inner material
  strip. This supports pocket floors at X=7/73 (v13), rather than X=5/75 (v12).
  v13 achieves .999 front/back silhouette IoU and has rounded side pockets.
- v11/v13/v14 return `genus=None` because tessellation is not watertight at some
  curved seams. Their reimported B-reps are valid, positive-volume single solids
  with one shell. No multi-solid or negative-volume variant is recommended.
- R18 foot-arc subtraction was separately tested as v5/v8; it slightly reduced
  silhouette overlap and is not in recommended variants.

Run in the offline image, with this directory mounted at /work and the part
input mounted at /case, and source at /app/src:
`python /work/reproduce.py`
Then evaluate using `probe.assess` from `/work/probe.py`.
