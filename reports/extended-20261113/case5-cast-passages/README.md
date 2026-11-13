# Cylinder-head cast passage and blind-drill repair

Baseline0b65063 official mean .954, case5 .942; other eight outputs unchanged.
Replace only the three front-bottom spherical pockets with tapered loft
passages joining the existing front arch mouths to the measured angled
D12.7 rear bores. Front opening radius/position stay unchanged; intermediate
section curvature is an explicit casting hypothesis, not measured truth.
The target has no SPHERE faces and shows the small bore at the arch's rear.

Also restore support walls and the59-degree tips of three known D5.11 blind
drills that the earlier top-port cut had broken open. A2.54mm sleeve wall is
an explicit estimate; its overlap connects to the front casting. Recut each
original16.51mm bore and full drill tip. The target has34 cone faces; the
earlier model had31, and the repaired one has34. The loft-only control has
genus18; restoring the three blind walls gives the target genus15. This
changes actual connectivity, not just a measured label.

Independent STEP re-import: valid, one solid, one shell; volume4,254,592.97
mm3 (+0.1924%), area351,737.41mm2 (+0.7351%), IoU .98711. Independent
trimmed-mesh and B-rep vertex extents are exactly508×85.73×165.1 from origin.
OCC's default trimmed-BSpline parameter-box bound extends spuriously below
Z0 by7.585mm. Use the raw export; do not translate using that conservative
bound. No global bounding-box logic is changed in this late probe.

Physical wall samples confirm air inside each bore and solid after each
drill tip; all three sleeves attach to the existing front wall. This remains
an official score experiment. Reports are excluded from the runtime image.
