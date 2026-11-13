# Official geometry probe batch

Baseline: 975c898, official mean 0.935. Case 5 improved from 0.792 to 0.942.
Only cases 7, 8, and 9 change in this batch. Official results are pending.

- Case 7: replace the guessed solid casting with a thin curved upper bowl,
  measured mounting stations, two side ribs, visible front recesses, and a
  short transition joining the two explicitly measured central bores.
- Case 8: shorten four bolt lobes, restore narrow bolt mouths, deepen visible
  foot pockets, and correct the oil-hole start/end positions. The opposed
  blind Z drillings follow the image but conflict with the through-hole prose;
  this is an explicit hypothesis to check with the official scorer.
- Case 9: replace the shared hidden cavity with separate crankcase and bank
  pockets, preserve cylinder sleeves and blind-bolt supports, and correct
  the exterior valley profile and its R50.8 concave blends.

All candidates were independently re-imported as valid single STEP solids.
Local volume/area/silhouette checks are diagnostics, not official scores.
The case 8 reproduction expects base.stp and ears.stp alongside reproduce.py;
remove their pump- prefix before running. All report data is excluded from
the runtime Docker image. See each JSON and manifest for metrics and hashes.
