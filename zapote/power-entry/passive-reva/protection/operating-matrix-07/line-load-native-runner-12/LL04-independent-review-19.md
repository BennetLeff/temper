# LL04 independent review (event-aware-normal-v1)

Status: **modeled normal screens within policy; parent acceptance still
pending; no hardware or protection qualification**.

This review covers only LL04 at 120.000000 V RMS and 374.814440062 ohm. It
uses the completed case receipts under
[`full-LL04-initialized/LL04`](full-LL04-initialized/LL04), the source binding in
[`source-identity.json`](full-LL04-initialized/source-identity.json), and the
accepted baseline policy in
[`accepted-baseline-11/acceptance.json`](../accepted-baseline-11/acceptance.json).

## Source and pipeline binding

[`case.json`](full-LL04-initialized/LL04/case.json) declares the exact LL04
line/load values. A byte diff of the generated `cold.cir` against the accepted
baseline has exactly two parameter substitutions: `VAC_RMS=120 ->
120.000000000` and `RLOAD=190 -> 374.814440062000`. All five include files match the accepted baseline byte-for-byte;
the aggregate include hash matches the accepted source map. The source identity also records the runner, decoder, checker, event
audit, and metrics hashes.

The capture contains 30,400,545 rows and reaches
0.650000000000000022 s. Pipeline stages are event audit 0, metrics 0, native
decoder 0, native gzip 0; the unchanged strict checker and its
normalizer/decoder stop at the first repeated timestamp (checker exit 1,
normalizer/decoder exit 1, gzip SIGPIPE -1). This is the expected legacy
strict branch for exact equal-time data, not evidence that rows were
removed. `result.json` remains `complete_review_pending` and
`capture-metadata.json` is diagnostic-only.

## Event and numerical evidence

[`raw15-event-audit.txt`](full-LL04-initialized/LL04/raw15-event-audit.txt)
reports 32 equal-time groups, 44 repeated rows, maximum group size 3, no
missing right context, zero logic changes, and no cycle-boundary group. The
largest positive interval is 5.000000000143778e-7 s. Its E3 storage diagnostic
is a maximum componentwise spread of 3.011412260748743e-13 J and a sum of
absolute changes of 3.363569381531599e-12 J.

[`event-metrics.txt`](full-LL04-initialized/LL04/event-metrics.txt) reports
`boundary_duplicate_ambiguity=false`, 44 duplicate rows, one arm transition,
one on transition, and no duplicate logic transitions. The selected E3
sum-absolute change is 9.769728725570166e-13 J in the 12-column metrics view;
these event quantities bound representative-choice sensitivity only, not
solver error or total-energy closure.

## Screen comparison

The unchanged normal screens and margins from `event-metrics.txt` are:

| Quantity | LL04 result | Screen | Margin |
| --- | ---: | ---: | ---: |
| Line RMS | 120.000000 V | 107.999–132.001 V | 12.001 V to either bound |
| Settled bus min/max | 385.201839 / 387.442138 V | 370.13425–409.09575 V | 15.067589 / 21.653612 V |
| Final-three bus means | 386.0203162, 386.3559791, 386.6583275 V | drift < 0.005 | drift 0.001653; 0.003347 remaining |
| Input RMS | 3.843647 A | ≤ 15 A | 11.156353 A |
| `vd` prefix peak | 387.506047 V | ≤ 500 V | 112.493953 V |
| `vb` prefix peak | 387.442138 V | ≤ 450 V | 62.557862 V |
| `vds` prefix peak | 388.751460 V | ≤ 650 V | 261.248540 V |
| `|vgs|` prefix peak | 14.982215 V | ≤ 25 V | 10.017785 V |
| Armed/on fraction | 1.0 / 1.0 | each ≥ 0.99 | 0.01 |
| Power residual `Pin-Pout-dE/dt` | +31.035537 W | ≥ −max(1 W, 0.005 Pin) | 33.265256 W above −2.229719 W bound |

The complete-prefix inductor peak is 29.777999 A. The normal screen reports
this value but has no automatic inductor current-rating limit, so it remains a
reported modeled stress value. The positive residual is modeled accounting,
not measured heat or proof of total-energy closure.

## Disposition

LL04 is **PASS for the declared event-aware modeled normal screens**, subject
to the parent attaching source/raw/event/metrics hashes and changing
`complete_review_pending` only through campaign parent review. It is not a
hardware point, fault result, or protection qualification. No full fault result has been accepted; the ideal F2 and failed-short experiments remain governed
by [`branch-model-review-13-parent.json`](../faults/branch-model-review-13-parent.json).
