# LL01 acceptance review checklist (event-aware native run)

This is a review gate for a real LL01 capture.  It is not an acceptance
receipt.  A case remains `complete_review_pending` until every item below is
source-bound and the parent records a disposition.  The synthetic LL01 tests
in `parent-review.json` exercise transport and child-reaping only; they are
not electrical evidence.  At the time this checklist was written the
`full-LL01-initialized/LL01` directory contained no completed electrical reports, so an
`engineering_screen=0` from a synthetic run cannot close this gate.

## 1. Bind the run before reading a metric

* Record the exact runner source and executable hashes from `manifest.json`,
  the ngspice version and `spinit` hash, host/byte order, command line, and
  UTC start/stop times.  Retain the runner's `execution.json`, child exit
  statuses, and disk-floor observations.
* Require all five include files to match the hash map in
  `accepted-baseline-11/acceptance.json`. Verify that reversing only the
  declared `VAC_RMS` and `RLOAD` substitutions in the generated LL01
  `cold.cir` recovers the accepted baseline deck byte-for-byte; bind the
  generated deck and `case.json` hashes to the same run.
* Require native capture metadata to state little-endian ngspice real format,
  `normal15` schema, complete required-name mask, finite saved values, solver
  stop at `0.65 s`, and a nonzero point count.  A producer or compressor exit
  of zero is insufficient: a parse failure can also return zero points.
* Verify the compressed raw bytes and every derived report against recorded
  SHA-256 values.  A missing raw trace, missing report, or failed child is a
  fail-closed missing-evidence result, not a zero-violation result.

## 2. Validate lossless native transport and event semantics

Run the source-bound native decoder and `normal15-event-audit` on the complete
raw trace.  Require the exact 15-field header in
`normal15-event-audit-12/README.md`, all fields finite, no backwards time,
start within the documented 1 ns native-start tolerance, and endpoint within
the same tolerance of `0.65 s`.  Require every positive interval to be no
larger than `1/(8*130000) = 9.615384615e-7 s`, unless the case is explicitly
diagnostic and excluded from acceptance.

Equal-time rows are retained, not deduplicated or time-shifted.  For each
group, retain left/group/right rows in the events artifact; a terminal group
without a right row must be reported as incomplete and cannot receive an
invented bound.  Check that equal-time rows do not change `q`, `en`, or
`fault` unexpectedly and that their physical extrema remain in the complete
prefix extrema.  Any missing context, nonfinite row, backwards interval,
oversized gap, or truncated gzip is a hard stop.

## 3. Require both retained checker and diagnostic metrics

Feed the normalized 12-column stream to the unchanged checker with its normal
switching-step guard.  `--no-switch-check` is permitted only for an explicitly
diagnostic rerun and cannot support acceptance.  Record the checker output and
exit status separately from event-aware metrics.  The metrics program is
diagnostic by contract and must end in
`engineering_screen=REPORTED_NOT_ACCEPTED` and
`qualification=NOT_CLAIMED`; a `screens=0` line is not an acceptance verdict.

For the actual LL01 report, compare the all-row extrema, settled-window
integrals, and final three chronological 60 Hz means against the checker
limits in `checker/README.md` and record numeric margin, not only pass/fail:

| quantity | screen | LL01 evidence required |
| --- | ---: | --- |
| line RMS | 107.999--132.001 V (implemented source tolerance) | `vrms`, endpoint/start and source phase |
| settled bus envelope | 389.615 V +/-5% = 370.134--409.096 V | `vb_min`, `vb_max`, settled mean and remaining V margin |
| bus cycle drift | `<0.005` | all three means in order and drift denominator |
| input RMS | `<=15 A` | settled `irms` and margin |
| `v_d` peak | `<=500 V` | complete-prefix peak and margin |
| bus peak | `<=450 V` | complete-prefix peak and margin |
| `v_ds` peak | `<=650 V` | complete-prefix peak and margin |
| `|v_gs|` peak | `<=25 V` | complete-prefix peak and margin |
| controller state | `armed_fraction,on_fraction >=.99` | final-three-cycle fractions plus complete-prefix transition counts |
| power/energy | `Pin-Pout-dE/dt >= -max(1 W,.005*Pin)` | `Pin`, `Pout`, storage delta-rate, balance and tolerance |

The checker screens startup stress over the complete trace while regulation,
power factor, and RMS use the final three integer cycles.  Complete-prefix `v_d`, `v_ds`, gate and bus peaks have the screens above.
The inductor peak is also reported, but this normal checker has no separate
inductor peak limit; do not invent a passed current rating from that output.

## 4. Review event-aware bounds, not just sampled extrema

Read every event line from the audit artifact.  Compare its left/group/right
hull bounds for `vac`, `iin`, `inputP`, `loadP`, `ac2`, `i2`, and `VB` with the
same engineering margins above.  The audit's hull is deliberately loose and
uses the full neighboring width; it is a diagnostic upper bound, not a
directed-rounding proof.  A bound that reaches a screen, or is larger than
the reported margin, requires a finer, source-justified run before review can
close.

Review the E3 storage diagnostics for the bank capacitor, local capacitor,
and boost inductor: same-time sum-absolute impulses, maximum relative spread,
and stable factored energy changes.  Compare their uncertainty to the energy
balance tolerance and to the reported LL01 residual; do not silently treat
the residual as heat closure.  The accepted normal baseline is a reference
only (last-cycle bus means 382.8471, 383.3930, 383.8926 V; drift 0.002731;
`Pin-Pout-dE/dt = 68.1334 W`), not a substitute for recomputing LL01.

Check exact cycle-boundary handling and `boundary_duplicate_ambiguity`.
An ambiguity at a selected boundary, a terminal event without right context,
or an energy-changing equal-time group prevents an unqualified regulation or
energy conclusion even if the ordinary screen count is zero.

## 5. Explain what a zero screen count does not prove

`screens=0` only says the implemented thresholds saw no violation in the
reported fields.  It does not establish any of the following without separate
evidence: lossless native export, event ordering, omitted-node or unsaved-state
energy closure, switching-loss/thermal limits, fuse interruption, device SOA,
hardware qualification, or product compliance.  In particular, the metrics
evaluator intentionally has no hidden total-energy requirement, logic columns
have no normalized physical tolerance, and source/auxiliary/control-rail work
is outside the normal 12-column energy accounting.  The model's known
ISENSE-clamp and generic-device limitations remain applicable.

## 6. Final disposition requirements

The parent review must attach the raw/report/source hashes, exact commands,
all child exit statuses, checker result, audit result, metrics result, and a
table of measured values versus margins.  It must explicitly state whether
the result is `complete_review_pending`, `REJECTED`, or an accepted modeled
normal point under the versioned `event-aware-normal-v1` policy.  No runner
output, synthetic test, or diagnostic screen may promote LL01 automatically;
thermal, hardware, fuse, and product claims remain `NOT_CLAIMED`.

## 7. LL01 completed-case findings (read-only review)

The completed materialized case is `full-LL01-initialized/LL01` at 108 VAC RMS
and 416.460488957 ohm.  Its capture metadata is internally consistent:
29,955,738 points, native little-endian `normal15`, both name masks 65535,
zero backwards rows, 56 equal-time repeats, and endpoint
`0.650000000000000022 s`.  The raw event audit exits zero with 41 equal-time
groups (maximum three rows), no missing right context, no logic-column changes,
no boundary group, and E3 spread/sum-absolute values
`2.114162509248780221e-13 J`/`1.979933529598177109e-12 J`.  Its largest positive
gap is `5.000000000143778e-7 s`, below the audit ceiling.

The event-aware metrics are inside the frozen checker screens: settled
`vrms=108.000000 V` (exactly the lower contractual endpoint), `irms=3.869202 A`,
`Pin=405.389658 W`, `Pout=359.070534 W`, PF `0.970125`, bus envelope
`385.675669..387.716140 V`, cycle means
`386.42167125159705, 386.7252726017146, 387.00073305938747 V`, drift
`0.001499`, complete-prefix `vd=387.776829 V`, `vb=387.716140 V`,
`vds=389.022540 V`, and `|vgs|=14.982205 V`.  Armed and on fractions are both
1.0.  The positive energy residual is `31.10592253664844 W`; it is not a
negative-balance failure, and remains modeled accounting rather than heat
closure.  The complete-prefix inductor-current peak is 25.067335 A; the
checker has no automatic current-rating screen, so this value must remain a
reported stress margin for the parent/device review rather than being silently
promoted to PASS.

The unchanged checker exits 1 at the first repeated-time line, while its
decoder and gzip children report 1/-1.  This is the expected strict-checker
branch for the versioned `event-aware-normal-v1` policy (the gzip SIGPIPE is a
consequence of the checker stopping at that line), not evidence that rows were
lost.  The native event-audit and metrics pipelines both exit 0 and retain the
raw trace.  Therefore this LL01 result is numerically inside the modeled
normal screens and transport/event checks, but it remains
`complete_review_pending`: the strict checker rejection, diagnostic-only
metadata, source/hash receipts, modeled residual, and hardware/device claims
still require the parent disposition described above.
