# Exact bore-station corrections and depth control

Official6f23f31: crankshaft R169 crowns improved case4 .961→.967.
The front groove hypothesis lowered case7 .745→.718; discard that change.

Case7 now starts from accepted .745 and fixes the independently measured
upper horizontal D26/D28/D17.5/D21 bore stations to the supplied facts; the
D21 groove was at Y84..86 instead of22.8..24.8. Add the missing inclined
D4.5 bore. Only previously removed bore-tool volumes are restored; the
added material outside those tools is zero. Lower structure belowZ110 is
unchanged. Re-import valid, one solid/shell, genus10 exactly.

Case5 tests only the known rear R2.54 valve bowl blends, keeping the accepted
.25 profile. Prior .15 and .5 profile variants were lower, and discarded.

Case9 tests longer 149.79mm relief pockets versus the accepted127mm, with
full-depth bolt supports in both. Pocket depth is an explicit uncertain
internal reconstruction assumption. All explicit bore and blind-hole
dimensions stay fixed; same exterior and projections. Re-import valid,
one solid, genus6. Official comparison decides retention.

No official improvement is claimed until measured. The runtime now reserves
20s for its single-valid-solid check and bounds all recovery attempts within
that shared allowance, rather than90s per attempted STEP. Two regression
tests passed against the CAD image in8.8s. Reports never enter the image.
