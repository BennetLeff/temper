# LL08 independent review (event-aware-normal-v1)

Status: **complete diagnostic capture; reported normal screens are within the
recorded policy bounds, but this review does not accept the case**. Parent
acceptance still requires independent source, executable, raw-artifact, and
report hash checks. This review is read-only and does not restart the run or
re-decompress the raw artifact.

## Source and tool binding

`full-LL08/LL08/case.json` identifies LL08 as 132.000000000 V RMS and
187.407220031000 ohm. `parent-launch-source-verification.json` records the
exact two substitutions from accepted-baseline-11 (`VAC_RMS=120` to 132 and
`RLOAD=190` to 187.407220031), with the five include files unchanged. The
generated deck SHA is
`cca34e1517db547f335a0ba9ff278fb5e80bcb8186158d98f19d303928421063`; the
include-closure SHA is
`c614d6bf0aad5a5a200cbbf46ce564d2dc7aa4e7b0a210a6afecc17b74abaf24`.

`source-identity.json` binds the direct normal host, native decoder,
normalizer, unchanged strict checker, event audit, and metrics binaries. It
also records the accepted baseline, explicit LL08 selection, five-argument
host protocol, first-invalid snapshot, and anonymous-pipe transport. The
native export is normal15 while the callback mask is 65535 (the full
diagnostic inventory); this is the expected 15-versus-16 distinction. The
parent must independently verify these recorded hashes before adoption.

## Capture and pipeline

The native capture reached endpoint
`sim_s=0.650000000000000022` with `stop_reason=solver_stopped`, 30,447,163
exported rows, all 15 vectors, 71 repeated timestamps, zero backwards rows,
and `first_invalid=true`. The retained gzip is 2,192,811,017 bytes; its full
hash is deliberately left to the parent’s independent check.

The pipeline status in `native-pipeline.json` is event audit 0 and metrics 0.
The independent decoder, normalizer, and gzip legs for metrics also exited 0.
The unchanged strict checker branch is checker 1, normalizer 1, decoder 1,
and gzip -1. Its stderr records
`REJECTED: line 23024534: time not strictly increasing`; the upstream broken
pipe is the consequence of the strict checker stopping at that duplicate.
This legacy rejection is retained and is not waived or converted into an
acceptance.

## Event and numerical evidence

`raw15-event-audit.txt` reports 44 equal-time groups, 71 repeated rows,
maximum group size 3, no missing right context, zero saved logic changes, and
no cycle-boundary group. The largest positive time gap is
`5.000000000143778323e-7` s. Neighboring-state energy bounds are
`E3_spread=3.835964977521012438e-13` J and
`E3_sumabs=5.319893721057594993e-12` J. The largest same-time 12-column delta
is `9.478851437094704124e-8` in `i(Vac)`; the raw logic columns have zero
same-time changes. All rows remain available for prefix extrema.

`event-metrics.txt` reports no boundary duplicate ambiguity, one arm
transition, one on transition, and no duplicate logic transitions. It reports
`engineering_screen=REPORTED_NOT_ACCEPTED screens=0` and
`qualification=NOT_CLAIMED`; those labels are preserved here.

## Modeled normal screens and margins

Using the unchanged screens (bus nominal 389.615 V plus or minus 5%, drift
below 0.005, input Irms at most 15 A, VD at most 500 V, VB at most 450 V,
VDS at most 650 V, absolute VGS at most 25 V, and armed/on fractions at least
0.99), the reported LL08 values are within bounds:

- Settled bus min/max: 381.772480 / 385.749283 V. Margins to the bus envelope
  [370.134250, 409.095750] V are 11.638230 V and 23.346467 V.
- Final-three bus means: 383.3053144, 383.8107789, and 384.2666931 V;
  drift is 0.002508, leaving approximately 0.002492 to the limit.
- Input RMS is 6.698508 A, leaving 8.301492 A to the 15 A screen.
- Whole-prefix peaks are VD 385.852732 V, VB 385.749283 V, VDS
  387.146217 V, and absolute VGS 14.982220 V. Remaining margins are
  114.147268 V, 64.250717 V, 262.853783 V, and 10.017780 V respectively.
- Armed and on fractions are both 1.000000, leaving 0.010000 to each
  minimum.
- Real input power is 872.226383 W, load power is 785.858708 W, and PF is
  0.986455. Energy residual is +61.201923 W; against the unchanged lower
  screen of approximately -4.361132 W, this is approximately 65.563055 W
  above the bound.

The complete-prefix inductor peak is 35.376249 A; no automatic normal screen
limits that quantity, so it remains a reported modeled stress. This result is
limited to this exact 132 V / 187.407220031 ohm simulated point and does not
establish hardware, thermal, protection, fuse, or total-energy qualification.

## Disposition

LL08 has a complete source-bound diagnostic capture and reported normal
screens within the event-aware policy bounds. It remains
`complete_review_pending`: this document makes no automatic acceptance claim,
retains the strict checker rejection and broken-pipe consequence, and leaves
the raw SHA and final acceptance decision to the parent.
