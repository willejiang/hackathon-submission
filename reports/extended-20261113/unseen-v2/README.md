# Eleven additional parts, without fact sheets

Frozen source:74f3e93 plus explicit-dimension prompt clarification later committed in78bdecd.
Run as UID1000, nine workers,1110s total cap,120s export reserve. Facts and truth
were not mounted during generation. Independent evaluation was run after completion.

Finished in1022s:11/11 agent models, zero boxes, zero missing. All11 independently
re-imported valid, with exactly one solid. Oil pan reached its agent timeout and
successfully recovered an earlier saved snapshot. This is not an official score.

| Part | Volume/target | Area/target | Silhouette IoU |
|---|---:|---:|---:|
| engine_a__camshaft | 1.0001 | 1.0000 | 0.9872 |
| engine_a__camshaft_bushing | 1.0000 | 1.0000 | 0.9958 |
| engine_a__engine_belt_wheel | 1.0001 | 0.9962 | 0.9933 |
| engine_a__engine_belt_wheel_pt2 | 1.0001 | 1.3364 | 0.9910 |
| engine_a__engine_intake_manifold | 0.9941 | 1.1719 | 0.5920 |
| engine_a__engine_oil_pan | 0.9974 | 1.1615 | 0.9766 |
| engine_a__engine_side_cover | 1.0019 | 1.1564 | 0.9201 |
| engine_a__engine_valve_cover | 1.0001 | 1.3920 | 0.9758 |
| engine_a__rocking_arm_spring | 0.9998 | 1.0032 | 0.9503 |
| engine_a__turbo_shell | 1.0126 | 0.6043 | 0.9415 |
| tubing_spider | 1.2932 | 1.1869 | 0.7869 |

Intake manifold and tubing spider remain inaccurate. Surface area also differs
substantially for several covers and wheels despite good silhouettes/volume.
Completeness and scalar agreement do not establish hidden-set0.98 accuracy.

The later single-solid post-export gate is not part of this generation run. It
is covered by two real-CAD/deadline regression tests. Its original90s-per-read
fallback was changed to a shared20s cap, with20s reserved before the final check.
