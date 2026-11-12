# Case 4–6 Harness run results

Agent runs are sequential. A round is one model step plus associated tools. All three STEP candidates are valid B-reps with one solid. Case 6 timed out and did not submit; its STEP was exported afterward from the agent-written, previously successful solution.py. It fails the volume gate.

| Case | Model rounds | cad_build calls | Agent time (s) | Reported tokens incl. cache | Eight-view IoU | Volume / target | Result |
|---|---:|---:|---:|---:|---:|---:|---|
| test_case_4 | 36 | 4 | 616.321 | 2,922,705 | 0.9749 | 0.9838 | PASS local gates |
| test_case_5 | 56 | 4 | 1117.427 | 7,256,669 | 0.9869 | 0.9938 | PASS local gates |
| test_case_6 | 31 | 4 | 1200.401 | 1,935,881 | 0.9155 | 2.5622 | TIMEOUT; candidate FAIL volume |

Agent elapsed total: 2934.149 seconds; reported agent tokens: 12,115,255.

Each case has [metrics.json], [rounds.csv], [trace.md], [session-trace.jsonl], [events.jsonl], [stderr.log], and [score.json]:
- test_case_4: [metrics](test_case_4/metrics.json), [round timing and tokens](test_case_4/rounds.csv), [readable trace](test_case_4/trace.md), [lossless session trace](test_case_4/session-trace.jsonl), [score](test_case_4/score.json)
- test_case_5: [metrics](test_case_5/metrics.json), [round timing and tokens](test_case_5/rounds.csv), [readable trace](test_case_5/trace.md), [lossless session trace](test_case_5/session-trace.jsonl), [score](test_case_5/score.json)
- test_case_6: [metrics](test_case_6/metrics.json), [round timing and tokens](test_case_6/rounds.csv), [readable trace](test_case_6/trace.md), [lossless session trace](test_case_6/session-trace.jsonl), [score](test_case_6/score.json)

Case 6 round 31 was aborted during experiment.py CAD build. Its model token usage was recovered from the lossless trace because the CLI projection did not flush step_end. The stalled tool ran about nine minutes. Case 6 postprocessing (candidate export + scoring) took 19.152 seconds beyond agent time.

Token counts are provider/Harness reported agent usage, including cached input and reported retries; auxiliary background title requests may not be included. Hidden reasoning-token breakdown was not exposed. This is not a billing statement.

Case 5 advisory differences: surface area about 7.5% low, genus unverified, and bore inventory mismatch. The local angled-bore comparator reduces measured axes to X/Y/Z, so its angled-axis mismatch does not by itself prove a bore is absent.

Runtime: Node 24.22.3, dsh 0.2.2-rc.1, deepseek-flash. Source reporting helpers were refined during execution without changing active model geometry or prompts. Shell interpreter PATH fix applies to future processes; the active run used its original environment.
