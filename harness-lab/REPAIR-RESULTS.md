# Experiment 00R-R results

**Batch verdict: pass.** One fresh scored trial ran for each of the three qualified bad starts. No scored trial was rerun and the apparatus was unchanged throughout.

| Starting defect | Time | Copper edits | Full run verdict | Independent board check |
|---|---:|---:|---|---|
| Keepout intrusion | 85.11 s | 1 | pass | pass |
| Copper clearance | 61.41 s | 1 | pass | pass |
| Disconnected ground | 25.96 s | 1 | pass | pass |

The inspection preflight passed in 8.95 seconds with zero edits.

## What the agent changed

- **Keepout intrusion:** replaced +15V with a detour below the keepout; ground stayed intact.
- **Copper clearance:** replaced +15V with a path clear of U3.2. The original clearance was 0.075 mm against the fixture’s 0.2 mm requirement; ground stayed intact.
- **Disconnected ground:** replaced the broken ground route with a direct pad-to-pad connection; +15V stayed intact.

The retained action record includes the exact vertices, initial findings, introduced/resolved finding IDs, snapshots and independent checks. Every passing trial also satisfied the repair-specific requirement to inspect the failing start first, request a route edit and observe resolution of the intended defect IDs.

[Before/after diagram](evidence/repair-before-after.svg). This is a diagram from native coordinates and track widths; pads are native bounding boxes rather than exact rounded contours. It is illustrative, not the validator.

## Evidence and limits

[Full scored results](evidence/repair-zen-results.json), [preflight](evidence/repair-zen-preflight.json), [case/action summary](evidence/repair-model-status.json), [complete model and native traces](evidence/repair-zen-traces.tar.gz).

[Repair qualification](evidence/repair-qualification.json), [10 obstacle controls](evidence/repair-obstacle-regression.json), [23 routing regression cases](evidence/repair-routing-regression.json), [retained local traces and unscored draft](evidence/repair-local-traces.tar.gz), [local review](evidence/repair-review.json). All 18 Python tests and both Rust tests passed, along with lint, formatting and compilation checks. Native adapter and Rust judge source are unchanged.

The first local clearance draft produced shorts instead of the intended clearance finding. It was retained as an unscored draft; the frozen clearance case was corrected and independently qualified before preflight.

This tests repair from three supplied bad states on one tiny board. It does not demonstrate held-out generalization, feedback causality, recovery from the agent’s own rejected edit, or electrical/manufacturing suitability. The model used the existing routing prompt and tools without diagnosis hints or reference repair coordinates. The healthy net was allowed to change; minimal changes were not a pass requirement.

All 12 scored upstream requests returned HTTP 200 with zero transport errors. The largest silent read interval was 71.75 seconds in the keepout trial; the revised relay allowed it to complete within the trial deadline. OpenCode reported $0 for each trial; this is not an independent billing receipt. Transport failures remain disqualifying under the strict stream policy.

[Predeclared plan and exact acceptance](REPAIR-EXPERIMENT.md).
