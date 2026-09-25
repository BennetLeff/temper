# LL03 independent review (event-aware-normal-v1)

Status: **modeled normal screens within policy; parent acceptance still
pending; no hardware or protection qualification**.

This review covers only LL03 at 108.000000 V RMS and 115.683469155 ohm. It
uses the completed case receipts under
[`full-LL03-initialized/LL03`](full-LL03-initialized/LL03), the source binding in
[`source-identity.json`](full-LL03-initialized/source-identity.json), and the
baseline policy in [`accepted-baseline-11/acceptance.json`](../accepted-baseline-11/acceptance.json).

## Source and pipeline binding

[`case.json`](full-LL03-initialized/LL03/case.json) declares LL03's exact
line/load values. A byte diff of the generated `cold.cir` against the accepted
baseline has exactly two parameter substitutions: `VAC_RMS=120 -> 108.000000000`
and `RLOAD=190 -> 115.683469155000`. All five include files match the accepted baseline byte-for-byte; the
aggregate include hash in `source-identity.json` matches the baseline receipt.
The event-aware policy, runner, decoder, checker, and metrics hashes are
recorded in that receipt.

The completed pipeline reports 29,479,028 rows and endpoint 0.650000000000000022
s. The stage statuses are: event audit 0, metrics 0, native decoder 0,
native gzip 0; the unchanged strict checker and its normalizer/decoder stop at
the first repeated timestamp (checker exit 1, normalizer/decoder exit 1, gzip
SIGPIPE -1). This is the expected legacy branch for exact equal-time data, not
a claim that rows were discarded. `result.json` remains
`complete_review_pending` and `capture-metadata.json` is diagnostic-only.

## Event and numerical evidence

[`raw15-event-audit.txt`](full-LL03-initialized/LL03/raw15-event-audit.txt)
reports 70 equal-time groups, 101 repeated rows, maximum group size 3, no
missing right context, zero logic changes, and no cycle-boundary group. The
largest positive interval is 5.000000000143778e-7 s. Its selected E3 storage
uncertainty is a maximum componentwise spread of
2.468859021614997e-13 J and a sum of absolute changes of
5.906381440834878e-12 J.

[`event-metrics.txt`](full-LL03-initialized/LL03/event-metrics.txt) reports
`boundary_duplicate_ambiguity=false`, 101 duplicate rows, one arm transition,
one on transition, and no duplicate logic transitions. The event-aware metrics
retain every row; they do not deduplicate or move timestamps. The E3 selected
storage sum is 8.738708881554286e-12 J in the 12-column metrics view (the
15-column audit's E3 subset is the separately reported 5.906e-12 J). Both are
representative-choice diagnostics, not a global solver-error or energy-closure
bound.

## Screen comparison

The unchanged normal screens and margins from `event-metrics.txt` are:

| Quantity | LL03 result | Screen | Margin |
| --- | ---: | ---: | ---: |
| Line RMS | 108.000000 V | 107.999–132.001 V | 0.001 V to lower bound |
| Settled bus min/max | 375.857870 / 382.392349 V | 370.134–409.096 V | 5.724 / 26.704 V |
| Final-three bus means | 378.373159, 379.2026057, 379.9456084 V | drift < 0.005 | drift 0.004156; 0.000844 remaining |
| Input RMS | 13.412054 A | ≤ 15 A | 1.587946 A |
| `vd` prefix peak | 382.584396 V | ≤ 500 V | 117.415604 V |
| `vb` prefix peak | 382.392349 V | ≤ 450 V | 67.607651 V |
| `vds` prefix peak | 383.958912 V | ≤ 650 V | 266.041088 V |
| `|vgs|` prefix peak | 14.982208 V | ≤ 25 V | 10.017792 V |
| Armed/on fraction | 1.0 / 1.0 | each ≥ 0.99 | 0.01 |
| Power residual `Pin-Pout-dE/dt` | +155.749957 W | ≥ −max(1 W, 0.005 Pin) | 162.944357 W above −7.194400 W bound |

The complete-prefix inductor peak is 30.039218 A. The normal screen reports
this value but has no automatic inductor current-rating limit, so it remains a
reported modeled stress value. The positive 155.75 W residual is modeled
accounting, not measured heat or proof of total-energy closure.

## Disposition

LL03 is **PASS for the declared event-aware modeled normal screens**, subject
to the parent attaching the source, raw, event, and metrics hashes and changing
`complete_review_pending` only through the campaign's parent review. It is not
an accepted hardware point, not a fault result, and not evidence of fuse
interruption, device SOA, thermal margin, or protection behavior. No full fault
case has yet been accepted; the ideal F2 and failed-short experiments remain governed by
[`branch-model-review-13-parent.json`](../faults/branch-model-review-13-parent.json).
