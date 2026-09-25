# LL07 independent review (event-aware-normal-v1)

Status: **complete diagnostic capture; modeled normal screens are within the
recorded policy bounds, but this review does not accept the case**. Parent
acceptance still requires independent source, tool, raw-artifact, and report
hash review. This review is read-only and does not restart the run or
re-decompress the raw artifact.

## Source and tool binding

`full-LL07/LL07/case.json` declares LL07 as 132.000000000 V RMS and
374.814440062000 ohm. The generated deck differs from the accepted baseline in
exactly two scalar substitutions: `VAC_RMS=120` to `VAC_RMS=132.000000000` and
`RLOAD=190` to `RLOAD=374.814440062000`. The five included files are unchanged;
the generated-deck SHA is
`4b00042daf2b0bedab0725e07d6d0af35b2bf8fe856af8a4b49e6f0aab78f4f7`, and the
include-closure SHA remains
`c614d6bf0aad5a5a200cbbf46ce564d2dc7aa4e7b0a210a6afecc17b74abaf24`.

`source-identity.json` binds the native host, decoder, normalizer, unchanged
strict checker, event audit, and metrics binaries, and records the accepted
baseline, explicit LL07 selection, five-argument host protocol, and
anonymous-pipe transport. The capture metadata has a 16-bit all-seen mask
(`65535`) for the callback diagnostics while the native export schema is
explicitly `normal15`; this is the expected distinction between diagnostic
signals and exported fields. These are recorded bindings; the parent must
attach its independent hash verification before adoption.

## Capture and pipeline

The native host reached `sim_s=0.650000000000000022` with
`stop_reason=solver_stopped`, 30,812,694 exported rows, all 15 exported
vectors present, 28 repeated timestamps, zero backwards timestamps, and
`first_invalid=true`. The raw gzip exists at 2,220,002,011 bytes; this review
leaves its full hash to the parent as requested. The event audit and metrics
consumed the complete row count and exited zero.

The pipeline status is: event audit 0, metrics 0, native decoder 0, native gzip
0. The unchanged strict checker branch is checker 1, checker normalizer 1,
checker decoder 1, and checker gzip -1. Its stderr records the expected
strict-time rejection at line 24,394,494 (`time not strictly increasing`);
the upstream broken pipe is a consequence of that early strict rejection.
It is retained as a legacy result and is not waived or converted into an
acceptance.

## Event and numerical evidence

`raw15-event-audit.txt` reports 21 equal-time groups, 28 repeated rows,
maximum group size 3, no missing right context, zero saved logic changes, and
no cycle-boundary group. The maximum positive gap is
`5.000000000143778323e-7` s. The neighboring-state bound is
`E3_spread=2.856949272030378227e-13` J and
`E3_sumabs=2.220678013092473615e-12` J. The report records the exact same-time
12-column maxima; the largest is `5.522627777310163e-8` A in input current,
while the two normalized logic columns have zero same-time delta. All three
saved raw logic vectors (q, en and fault) are also unchanged within groups. All rows remain
available for prefix extrema.

`event-metrics.txt` reports no boundary duplicate ambiguity, one arm
transition, one on transition, and no duplicate logic transitions. It reports
`engineering_screen=REPORTED_NOT_ACCEPTED screens=0` and
`qualification=NOT_CLAIMED`; those labels are preserved here.

## Modeled normal screens and margins

Using the unchanged checker thresholds—bus nominal 389.615 V plus or minus 5%,
drift below 0.005, input Irms at most 15 A, VD at most 500 V, VB at most
450 V, VDS at most 650 V, VGS magnitude at most 25 V, and armed/on fractions
at least 0.99—the reported LL07 values are within bounds:

- Settled bus min/max: 385.328039 / 387.506868 V. The margins to the bus
  envelope [370.134250, 409.095750] V are 15.193789 V and 21.588882 V.
- Final-three bus means: 386.1289741, 386.4426457, and 386.7323586 V;
  drift is 0.001563, leaving 0.003437 to the limit.
- Input RMS is 3.505044 A, leaving 11.494956 A to the 15 A screen.
- Whole-prefix peaks are VD 387.566527 V, VB 387.506868 V, VDS
  388.809757 V, and VGS magnitude 14.982226 V. Their remaining margins are
  112.433473 V, 62.493132 V, 261.190243 V, and 10.017774 V respectively.
- Armed and on fractions are both 1.000000, leaving 0.010000 to each
  minimum.
- Real input power is 442.290077 W, load power is 398.384114 W, and PF is
  0.955960. The energy balance is +28.0477047 W; with the checker tolerance
  of 2.2114504 W, it is 30.259155 W above the lower bound.

The complete-prefix inductor peak is 34.364070 A; the normal screen has no
automatic inductor-current limit, so it remains a reported modeled stress
rather than an acceptance failure. The 132 V source point is inside the
checker’s 132.001 V upper RMS contract by 0.001 V, so that boundary should
remain explicit in parent review.

## Disposition

LL07 has a complete source-bound diagnostic capture and its modeled normal
screen values are within the event-aware policy bounds. It remains
`complete_review_pending`: this document makes no automatic acceptance claim,
retains the strict checker rejection and its upstream broken-pipe consequence,
and does not establish hardware, thermal, protection, fuse, or total-energy
qualification. Parent acceptance must bind the raw artifact and all
reports/tools independently and keep the policy scoped to this exact 132 V /
374.814440062 ohm case.
