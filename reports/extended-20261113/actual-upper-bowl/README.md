# Actual flange reconstruction, bounded to the upper casting

This differs from the discarded upper-bowl probe: the entire actual16.25mm
flange layer is restored before recutting, not a guessed pocket starting
above the real137.74mm floor. This removes the hidden residual flat void.
The new R65 outer casting is clipped to the actual flange footprint. The
R61 concavity uses Y24.75..64.75, estimated from calibrated image edges
near24.84/64.71. All corrected upper/lower bore stations are preserved.
The complete structure atZ<=110 is exactly unchanged in both Boolean
directions. Re-import valid, one solid/shell, genus10 (the discarded partial
restoration had genus14). The volume is3.43% high; no unknown cavity is
cut to force it down. Only official scoring establishes whether it helps.

The workflow also gains a fallback for genus when tessellation has seam
cracks. It counts B-rep cells with inner-wire and degenerate-edge corrections,
restricted to valid single solids with one shell. It agrees with the mesh
on all seven measurable current practice outputs, recovers genus15 for
case5 and9 for case8, and passes tests on boxes, spherical/conical poles,
periodic cylinders/tori, annular faces and blind pockets. Multi-shell bodies
remain unverified. This adds no reference shape lookup or arbitrary holes.
Four real-CAD/deadline/topology regression tests passed in6.2s.
