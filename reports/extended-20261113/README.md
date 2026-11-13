# Extended practice: input compatibility and bounded reconstruction

The supplied archive contains 20 parts: the nine original practice inputs are
identical, while eleven parts are additional. There are no reference STEP files.
The archive README says hidden inputs omit `facts.json`; the current submission
README describes the same input format as practice. The workflow now handles
both formats without modifying the supplied inputs.

Changes:

- Recover only envelope, volume and passage counts explicitly stated in the brief
  when the debugging fact sheet is absent. Unknown properties stay unknown.
- Permit dimensional estimates in `derive()` only with an explicit same-line
  explanation. Imports, file I/O and process-execution restrictions remain enforced.
- Save the first valid solid before all diagnostics pass, then perform bounded
  improvement cycles. Correct the contradictory submit/stop instructions.
- Rank saved candidates using dimensions, volume, area, topology and eight-view
  projection, rather than envelope and volume alone. Keep the existing submission
  as a candidate, and retain each improved selection before the deadline.
- Save each snapshot's source, and clarify sketch-plane coordinate conventions.

## Validation

77 offline tests pass, including same-volume plates with differently placed holes,
missing-fact inputs, explicit estimated parameters, forbidden execution, and deadline
preservation. All 20 briefs yield an explicit envelope and volume without a fact file.

Four additional parts were tested without `facts.json`: camshaft bushing, oil pan,
side cover and tubing spider. With the same 420-second cap and base image, the existing
workflow generated 2/4 valid single solids (two missing), versus 4/4 for the updated
workflow. The updated run finished in 362 seconds. See `benchmark.json`.

This is one matched smoke test, not an official score or evidence of 0.98 accuracy.
The side cover still has excessive volume and the spider needs further geometric
work. A complete nine-case run under the 20-minute limit is also being checked.

## Case 8 controlled probe

The submitted practice output changes only case 8: restore eight small internal
blind-bottom plugs in the four cross-drillings, based on the side views. This is
an explicitly uncertain interpretation because the prose describes through holes.
It is being checked by official evaluation; a lower score must not replace the
previous best part when assembling the retained submission.

Independent re-import checks: valid single solid; volume ratio 1.00191 (previous
0.99735); area ratio 1.08533 (previous 1.09320); genus 13 (previous 21, target 11).
Local eight-view IoU is about 0.95193, versus 0.94932. These are diagnostics, not
the organisers' 3D surface/volume score.
