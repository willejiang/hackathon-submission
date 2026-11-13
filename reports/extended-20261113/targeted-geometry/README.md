# Isolated follow-up geometry

Case5 tests a more gradual six-valve chamber loft (profile exponent .5 vs
accepted .25); all explicit bore dimensions and exterior features stay fixed.
Unspecified internal curvature is a hypothesis, not ground truth.

Case7 changes only the accepted casting above Z110: restore the shallow
flange pocket, add the image-supported R65 shell and cut the R61 concave
bowl. Keep accepted lower plate, main hub, flange and ear boundaries.
The protected lower-slab JSON proves both directional Boolean differences
are zero. The topology changes and requires official evaluation.
Reproduction: place accepted STEP from975c898 as accepted745.stp beside
case7.py and assess.py, using the practice input as /case and work as /work.

Case9 adds the stated R6.35 concave frame transitions by rounding the
crankcase cutting tool's end rims before subtraction. All six bores, blind
bolt depths, exterior geometry and cooling-pocket depth remain unchanged.
Rounding the tool avoids the failed direct solid-edge fillet. Independent
STEP re-import is valid, one solid, genus6; silhouette IoU .99151.

All local metrics are diagnostics. Official results are pending. This folder
is excluded from the runtime image and is not read by the autonomous agent.

Official78bdecd: case7 rear stop .721 (down from .745); case8 through Z
drillings .854 (down from .936); case9 full-depth bolt supports .940 (up
from .934). Therefore this next probe retains pump v14 and uses the full
bolt supports with the additional R6.35 frame blends. Case7 uses the upper
bowl hybrid, with no rear stop. Case5 tests the .5 profile.

The CAD tool descriptions now agree with the existing runner/skill: submit
a first valid solid before all diagnostics pass, and compare views early.
The earlier descriptions incorrectly said to wait for all gates/numbers.
