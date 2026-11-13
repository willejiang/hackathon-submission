# V6 candidate: preserve the cylinder walls

This is an experiment record, excluded from the submission image by `.dockerignore`.
`solution.py` reconstructs the part from the supplied facts, with the existing
snapshot model as the starting point. `measurements.json` records independent
measurements of the generated solid. The submitted STEP is
`artifacts/outputs/test_case_9.stp`.

The previous output matched volume and projected outline but its scaled internal
cavity removed cylinder walls and opened nominally blind holes. This candidate
keeps full-length cylinder sleeves, adds the R12.7 supports for the sixteen blind
bolt holes, and extends through cuts slightly beyond rounded input coordinates
to remove microscopic caps. The blind-hole bottoms stay at their stated depth.

Re-imported STEP checks: one valid solid; genus 6; exact bounding box; volume
14,874,713 mm3 (+0.724%); area 1,763,494 mm2 (+1.011%). Six inclined cylinders
and sixteen bolt holes retain their declared lengths. Orthographic silhouette
IoU is 0.98565 and eight-view mean is 0.96109. These are local diagnostics,
not official scores.

Known limitations: the X-axis crankshaft slot has a continuous axial extent but
the cavity removes part of its curved wall. The reference's recessed frames and
rounds are also incomplete. The local full-feature gate is therefore still red;
this submission tests the geometric improvement against the official evaluator.

The accompanying general measurement fix compares cylindrical families by their
full 3D axes. The two 45-degree banks must not be collapsed into the same display
label `Y`, and serialized fact vectors must be parsed as directions.
