# Experiment 00PR results

**Batch verdict: pass.** Three fresh trials began at the three frozen misplaced C9 starts, with no copper. No trial was rerun; prompts, tools, limits and validators stayed fixed during the batch.

| Trial | Time | Total edits | Full run verdict | Independent board check | Final C9 pose (mm, deg) |
|---|---:|---:|---|---|---|
| 1 | 133.50 s | 3 | pass | pass | [5.8, 10.0], 90.0 |
| 2 | 73.67 s | 4 | pass | pass | [13.8, 10.0], 90.0 |
| 3 | 155.20 s | 3 | pass | pass | [5.0, 10.0], 90.0 |

The inspect-only preflight passed in 8.52 seconds, without editing.

## Agent actions

- **Trial 1:** placed C9 to the left of U3 at (5.8,10), 90 degrees; routed ground directly and +15V around the keepout. Three edits.
- **Trial 2:** initially placed C9 to the right at (14,10), 90 degrees. The pad-distance findings remained, so the next placement moved it to (13.8,10). It then routed ground above U3 and +15V below U3, avoiding the other pads. Four edits.
- **Trial 3:** placed C9 to the left at (5,10), 90 degrees; routed +15V around the keepout and ground directly. Three edits.

A `place` response can still say `fail` when placement constraints are satisfied because the copper is not complete yet. Trial 2's first placement also failed the distance requirement; its second placement resolved those specific findings. The retained trace distinguishes these cases. No agent moved C9 after routing or needed to revise an attempted copper route in this batch.

[Before/after diagram](evidence/combined-before-after.svg). Native coordinates and widths are used; pads are bounding boxes and dashed rectangles are native footprint bounds. This illustration is not the validator.

Every passing run begins with inspection of the invalid start, includes both placement and routing, finishes with a passing check and satisfies the full wire/action/snapshot audit plus independent native verification. Counts include placement, route replacement and removal in one shared budget.

## Evidence

[Full scored results](evidence/combined-zen-results.json), [preflight](evidence/combined-zen-preflight.json), [action/status summary](evidence/combined-model-status.json), [complete model/native traces](evidence/combined-zen-traces.tar.gz).

[13 combined controls](evidence/combined-qualification.json), [19 placement controls](evidence/combined-placement-regression.json), [23 routing controls](evidence/combined-routing-regression.json), [10 obstacle controls](evidence/combined-obstacle-regression.json), [three repair starts](evidence/combined-repair-regression.json), [local traces](evidence/combined-local-traces.tar.gz), [review](evidence/combined-review.json). All 22 Python tests and both Rust tests passed, with lint/format/compilation checks.

[Prepared inputs](evidence/combined-trial-inputs.json) and [predeclared acceptance](COMBINED-EXPERIMENT.md). Scripted witness poses/routes were not supplied to the model.

## Limits

This demonstrates joint placement and routing for two selected connections on a two-footprint fixture, across three known starting poses. It does not establish held-out generalization, optimal placement/routing, electrical suitability, or fabrication readiness. U3.5 remains deliberately disconnected. Moving after routing was qualified locally; whether the agent exercised that sequence is visible in its action record. No learned harness-refinement loop or hidden route search is involved.

All 19 scored upstream requests returned HTTP 200 with zero wire errors. The largest silent read gap was 126.15 seconds; the revised relay allowed the response to finish within the unchanged five-minute trial budget. OpenCode reported $0 per trial; these are not independent billing receipts. Stream failures remain disqualifying. Earlier experiments and their verdicts remain unchanged.
