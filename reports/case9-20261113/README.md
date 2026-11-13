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

The retained candidate (`solution.py`, also archived as `solution_clean.py`,
commit 66d1942) has one valid solid, genus 6, volume +0.724%, area +1.011%, and
an eight-view silhouette IoU of 0.96109. Its official case-9 score is **0.873**,
up from **0.671**, and the team score is **0.911**, up from **0.889**.

The alternative (`solution_endround.py`, `measurements-endround.json`, commit
eab3aff) also restores the specified R50.8/R76.2 cross-section
rounds and R25.4 end-edge rounds. Re-imported STEP checks: one valid solid;
genus 6; bounding-box Y differs by only 0.005 mm; volume 15,027,132 mm3
(+1.756%); area 1,794,800 mm2 (+2.803%). Six inclined cylinders and sixteen
bolt holes retain their declared lengths. Orthographic silhouette IoU is
0.98603 and eight-view mean is 0.98244. These are local diagnostics, not
official scores. Its official case-9 score was **0.861**, with team score
**0.910**. Despite better silhouette overlap, it scored below the first
candidate, so the submitted STEP has been restored to the first candidate.

Known limitations: the X-axis crankshaft slot has a continuous axial extent but
only a partial cylindrical wall, which the local full-feature gate rejects.
Adding a complete supporting half-tube closes the water jacket and changes genus
from the stated 6 to 5, so this hypothesis was rejected. The reference's recessed
frames and small blends remain incomplete. Official evaluation is needed to
measure the actual geometric improvement.

The accompanying general measurement fix compares cylindrical families by their
full 3D axes. The two 45-degree banks must not be collapsed into the same display
label `Y`, and serialized fact vectors must be parsed as directions.
Bounding-box dictionaries also use their configured length tolerance, rather
than exact float equality; discrete face and topology counts remain exact.
