# LL05 independent review (event-aware-normal-v1)

Status: **complete diagnostic capture; modeled normal screens are within the
recorded policy bounds, but this review does not accept the case**. Parent
acceptance still requires its independent source/tool/raw/report hash review.
This review is read-only and does not restart the run or decompress the raw
artifact.

## Source and tool binding

`case.json` declares LL05 as 120.000000000 V RMS and 187.407220031000 ohm.
The generated `cold.cir` differs from `accepted-baseline-11/cold.cir` in the
intended two scalar substitutions only: `VAC_RMS=120` to
`VAC_RMS=120.000000000` and `RLOAD=190` to `RLOAD=187.407220031000`.
The five included files are unchanged. The case records generated-deck SHA
`f85b4a622d8bf303e3f2f1646bb2cc977b03d24b655d4b48a14abadb8677528f` and
include-closure SHA
`c614d6bf0aad5a5a200cbbf46ce564d2dc7aa4e7b0a210a6afecc17b74abaf24`,
matching the live-source check's six-file hashes.

`source-identity.json` binds the native host, decoder, normalizer, unchanged
strict checker, event audit, and metrics binaries, and records the accepted
baseline, explicit LL05 selection, five-argument host protocol, and
anonymous-pipe transport. `parent-live-source-check.json` says the circuit
files are byte-identical to the previous LL05 attempt and that only transport
changed. These are recorded bindings; the parent must attach its independent
hash verification before adoption.

## Capture and pipeline

The native host reached `sim_s=0.650000000000000022` with
`stop_reason=solver_stopped`, 30,103,973 rows, the full 16-signal diagnostic mask present,
58 repeated timestamps, zero backwards timestamps, and `first_invalid=true`.
The raw gzip exists at 2,167,895,869 bytes; this review leaves its full hash to
the parent as requested. The event audit and metrics both consumed complete
row counts and exited zero. Their complete-row counts agree on 30,103,973. The native decoder validates
the 15-field export schema; metrics report 2,472,370 settled rows. The
completed checks require the declared endpoint.

The pipeline status is: event audit 0, metrics 0, native decoder 0, native gzip
0. The unchanged strict checker branch is checker 1, checker normalizer 1,
checker decoder 1, and checker gzip -1. Its stderr records the expected
strict-time rejection at line 22,754,979 (`time not strictly increasing`);
the upstream broken-pipe termination is a consequence of that early strict rejection. It is
retained as a legacy result and is not waived or converted into an acceptance.

## Event and numerical evidence

`raw15-event-audit.txt` reports 43 equal-time groups, 58 repeated rows,
maximum group size 3, no missing right context, zero saved logic changes, and
no cycle-boundary group. The maximum positive gap is
`5.000000000143778323e-7` s. The neighboring-state bound is
`E3_spread=2.680012618597563401e-13` J and
`E3_sumabs=3.883286165680152725e-12` J. Same-time 12-column changes are small relative to the electrical margins
(largest reported equal-time delta is
`7.57480451696324e-8` in `i_ac_a`); all rows remain available for prefix
extrema.

`event-metrics.txt` reports no boundary duplicate ambiguity, one arm
transition, one on transition, and no duplicate logic transitions. It reports
`engineering_screen=REPORTED_NOT_ACCEPTED screens=0` and
`qualification=NOT_CLAIMED`; those labels are preserved here.

## Modeled normal screens and margins

Using the unchanged checker thresholds (bus nominal 389.615 V ±5%, drift
<0.005, input Irms ≤15 A, VD ≤500 V, VB ≤450 V, VDS ≤650 V, |VGS| ≤25 V,
and armed/on fractions ≥0.99), the reported LL05 values are within bounds:

| Quantity | LL05 result | Margin to screen |
| --- | ---: | ---: |
| Settled bus min / max | 381.211753 / 385.347086 V | 11.077503 / 23.748664 V to envelope |
| Final-three bus means | 382.7734063, 383.3092427, 383.8255532 V | drift 0.002749; 0.002251 remains |
| Input RMS | 7.420222 A | 7.579778 A |
| VD prefix peak | 385.458665 V | 114.541335 V |
| VB prefix peak | 385.347086 V | 64.652914 V |
| VDS prefix peak | 386.758245 V | 263.241755 V |
| Absolute VGS prefix peak | 14.982213 V | 10.017787 V |
| Armed / on fraction | 1.000000 / 1.000000 | 0.010000 each |
| Energy balance | +69.323962 W | 73.726662 W above the -4.402700 W lower bound |

The settled metrics also report 120.000000 V RMS, 880.539980 W real input
power, 783.847484 W load power, and PF 0.988897, all finite with the required
positive power signs. The complete-prefix inductor peak is 30.704239 A; the
normal screen has no automatic inductor-current limit, so it remains a
reported modeled stress rather than an acceptance failure.

## Disposition

LL05 has a complete source-bound diagnostic capture and its modeled normal
screen values are within the event-aware policy bounds. It remains
`complete_review_pending`: this document makes no automatic acceptance claim,
retains the strict checker rejection, and does not establish hardware,
thermal, protection, fuse, or total-energy qualification. Parent acceptance
must bind the raw artifact and all reports/tools independently and keep the
policy scoped to this exact 120 V / 187.407220031 ohm case.
