# LL09 independent review (event-aware-normal-v1)

Status: **complete diagnostic capture; reported normal screens are within the
recorded policy bounds, but this review does not accept LL09**. The parent
owns the acceptance decision and the independent source/tool checks. This
review did not restart the solver, re-decompress the raw archive, or mutate
any receipt.

## Source and tool binding

`full-LL09/LL09/case.json` identifies LL09 as 132.000000000 V RMS and
104.115122239000 ohm. `parent-launch-source-verification.json` records the
only two deck substitutions, `VAC_RMS=132` and `RLOAD=104.115122239`; its five
include hashes are retained unchanged. The generated deck hash is
`4a34122626d8732c8377eb7c59f39fd2bf5c8922e11cfa76eb77e4e61921e4e4`, and the
include-closure hash is
`c614d6bf0aad5a5a200cbbf46ce564d2dc7aa4e7b0a210a6afecc17b74abaf24`.

`full-LL09/source-identity.json` binds the direct normal host, native
decoder, normalizer, unchanged strict checker, event audit, and metrics
executables. It records the accepted baseline, explicit LL09 selection,
five-argument host protocol, first-invalid snapshot, pigz-4 compression, and
anonymous-pipe transport. The native export is normal15 while the callback
mask is 65535; this is the expected exported-versus-diagnostic inventory
difference. Parent should independently verify these recorded hashes before
adoption.

## Capture and pipeline

The native capture reached `sim_s=0.650000000000000022` with
`stop_reason=solver_stopped`, 30,141,001 exported rows, all 15 vectors,
73 repeated timestamps, zero backwards rows, and `first_invalid=true`.
`native-export-receipt.json` records 3,616,920,574 bytes, 65,536-byte
buffering, 3,616,920,120 borrowed data bytes, and 27,630 ms export time.
The parent independently recorded the completed gzip as
2,168,688,596 bytes with SHA-256
`84812ef89e0c987d28343078c9fd17a5468a019a71505595023f74d4e064e2ba` and a
successful `pigz -t`; this review treats that as parent evidence rather than
rehashing the multi-gigabyte file.

The event-audit and metrics legs exited 0. The unchanged strict checker leg
is checker 1, normalizer 1, decoder 1, and gzip -1. Its stderr says
`REJECTED: line 22822239: time not strictly increasing`; the upstream broken
pipe is the expected consequence of that checker stopping at a repeated
timestamp. This legacy rejection is retained and is not waived or converted
into acceptance.

## Event and numerical evidence

`raw15-event-audit.txt` reports 52 equal-time groups, 73 repeated rows,
maximum group size 3, no missing right context, zero saved logic changes,
and no cycle-boundary group. The largest positive time gap is
`5.000000000143778323e-7` s. Neighboring-state energy bounds are
`E3_spread=3.416191082604673775e-13` J and
`E3_sumabs=6.018832531153315349e-12` J. The largest same-time 12-column
change is `9.724362914909079e-8` in `i(Vac)`; the logic columns have zero
same-time changes. The metrics report no boundary ambiguity, one arm
transition, one on transition, and no duplicate logic transitions.

## Modeled normal screens and margins

The unchanged screens are bus nominal 389.615 V plus or minus 5%, drift below
0.005, input Irms at most 15 A, VD at most 500 V, VB at most 450 V, VDS at
most 650 V, absolute VGS at most 25 V, and armed/on fractions at least 0.99.
The reported LL09 values remain inside those bounds:

- Settled bus min/max are 377.460743 / 384.028908 V. Margins to the bus
  envelope [370.134250, 409.095750] V are 7.326493 V and 25.066842 V.
- Final-three bus means are 380.1064328657151, 380.81548953493893, and
  381.45614338406915 V. Drift recomputed by the parent from those means is 0.0035508752329663981,
  leaving 0.001449124767033602 to the 0.005 limit.
- Input RMS is 11.889830 A, leaving 3.110170 A to the 15 A screen.
- Whole-prefix peaks are VD 384.205093 V, VB 384.028908 V, VDS 385.569081 V,
  and absolute VGS 14.982205 V. Remaining margins are 115.794907 V,
  65.971092 V, 264.430919 V, and 10.017795 V respectively.
- Armed and on fractions are both 1.000000, leaving 0.010000 to each minimum.
- Real input power is 1559.826045 W, load power is 1392.349522 W, and PF is
  0.993863. Energy residual is +132.705271834 W. Against the unchanged lower
  screen of `-max(1, 0.005*Pin) = -7.799130225` W, that is about
  140.504402059 W above the bound.

The complete-prefix inductor peak is 36.870698 A; no automatic normal screen
limits that quantity, so it remains a reported modeled stress. These values
cover this exact 132 V / 104.115122239 ohm simulated point only. They do not
establish hardware, thermal, protection, fuse, or total-energy qualification,
and they do not establish a continuous envelope between the discrete grid
points.

## Disposition

LL09 has a complete source-bound diagnostic capture and reported normal
screens within the event-aware policy bounds. It remains
`complete_review_pending`: this document makes no automatic acceptance claim,
retains the strict checker rejection and broken-pipe consequence, and leaves
the final acceptance decision to the parent.
