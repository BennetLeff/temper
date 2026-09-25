# LL06 independent review (event-aware-normal-v1)

Status: **complete diagnostic capture; modeled normal screens are within the
recorded policy bounds, but this review does not accept the case**. Parent
acceptance still requires independent source, tool, raw-artifact, and report
hash review. This review is read-only and does not restart the run or
re-decompress the raw artifact.

## Source and tool binding

`full-LL06/LL06/case.json` declares LL06 as 120.000000000 V RMS and
104.115122239000 ohm. Its generated deck SHA is
`27abc73a6c10c653441d3861885617dce6f1dfba1bc509e8ef6af03c9afcdaab`, and its
source deck and include-closure hashes match the accepted baseline's source
map. The live-source check records the same five include-file hashes as the
baseline and confirms recovery by reversing exactly the two parameter
substitutions. Thus the intended changes are `VAC_RMS=120` to
`VAC_RMS=120.000000000` and `RLOAD=190` to `RLOAD=104.115122239000`.

`source-identity.json` binds the native host, decoder, normalizer, unchanged
strict checker, event audit, and metrics binaries, and records the accepted
baseline, explicit LL06 selection, five-argument host protocol, and
anonymous-pipe transport. These are recorded bindings; the parent must attach
its independent hash verification before adoption.

## Capture and pipeline

The native host reached `sim_s=0.650000000000000022` with
`stop_reason=solver_stopped`, 29,845,886 rows, the full16-signal diagnostic mask present,
64 repeated timestamps, zero backwards timestamps, and `first_invalid=true`.
The raw gzip exists at 2,145,942,203 bytes; this review leaves its full hash
to the parent as requested. The event audit and metrics consumed the complete
row count and exited zero. The native decoder validates all15 export fields. Their reports agree on the declared endpoint and
29,845,886 total rows.

The pipeline status is: event audit 0, metrics 0, native decoder 0, native gzip
0. The unchanged strict checker branch is checker 1, checker normalizer 1,
checker decoder 1, and checker gzip -1. Its stderr records the expected
strict-time rejection at line 22,589,747 (`time not strictly increasing`);
the upstream broken-pipe termination is a consequence of that early strict rejection. It is
retained as a legacy result and is not waived or converted into an acceptance.

## Event and numerical evidence

`raw15-event-audit.txt` reports 47 equal-time groups, 64 repeated rows,
maximum group size 3, no missing right context, zero saved logic changes, and
no cycle-boundary group. The maximum positive gap is
`5.000000000143778323e-7` s. The neighboring-state bound is
`E3_spread=2.685374742921569942e-13` J and
`E3_sumabs=3.964557354365183056e-12` J. Same-time 12-column changes are small relative to the electrical margins (largest reported equal-time delta is
`7.49470210337222e-8` in `i_ac_a`); all rows remain available for prefix
extrema.

`event-metrics.txt` reports no boundary duplicate ambiguity, one arm
transition, one on transition, and no duplicate logic transitions. It reports
`engineering_screen=REPORTED_NOT_ACCEPTED screens=0` and
`qualification=NOT_CLAIMED`; those labels are preserved here.

## Modeled normal screens and margins

Using the unchanged checker thresholds (bus nominal 389.615 V ±5%, drift
<0.005, input Irms ≤15 A, VD ≤500 V, VB ≤450 V, VDS ≤650 V, |VGS| ≤25 V,
and armed/on fractions ≥0.99), the reported LL06 values are within bounds:

| Quantity | LL06 result | Margin to screen |
| --- | ---: | ---: |
| Settled bus min / max | 376.244081 / 382.998346 V | 6.109831 / 26.097404 V to envelope |
| Final-three bus means | 378.9056671, 379.6420785, 380.3730652 V | drift 0.003873; 0.001127 remains |
| Input RMS | 13.198676 A | 1.801324 A |
| VD prefix peak | 383.190576 V | 116.809424 V |
| VB prefix peak | 382.998346 V | 67.001654 V |
| VDS prefix peak | 384.563792 V | 265.436208 V |
| Absolute VGS prefix peak | 14.982199 V | 10.017801 V |
| Armed / on fraction | 1.000000 / 1.000000 | 0.010000 each |
| Energy balance | +153.214137 W | 161.086238 W above the -7.872101 W lower bound |

The settled metrics also report 120.000000 V RMS, 1,574.420283 W real input
power, 1,383.936186 W load power, and PF 0.994052, all finite with the
required positive power signs. The complete-prefix inductor peak is 32.104756
A; the normal screen has no automatic inductor-current limit, so it remains a
reported modeled stress rather than an acceptance failure. LL06 is closer to
the 15 A input-current screen than LL05, with 1.801324 A of remaining margin.

## Disposition

LL06 has a complete source-bound diagnostic capture and its modeled normal
screen values are within the event-aware policy bounds. It remains
`complete_review_pending`: this document makes no automatic acceptance claim,
retains the strict checker rejection, and does not establish hardware,
thermal, protection, fuse, or total-energy qualification. Parent acceptance
must bind the raw artifact and all reports/tools independently and keep the
policy scoped to this exact 120 V / 104.115122239 ohm case.
