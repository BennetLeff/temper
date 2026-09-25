# F2-CREST normal-prefix independent review

Status: **DIAGNOSTICS REVIEW ONLY; NOT ACCEPTED**.

This review covers the bounded prefix diagnostics in this directory.  It did
not reread or mutate the full raw trace.  `batch-receipt.json` records identical
before/after raw SHA-256 values
(`d78e8e2f7c28b8ba9c10ce499af2813202ede8b2e173c39cfdc0ee3d650484fd`), audit
and metrics exit status 0, no resource stop, and `accepted: false`.

## What the selectors establish

Both selector receipts report `status: OK`, 32,237,324 full rows and
30,113,786 selected prefix rows.  The selected endpoint is the exact literal
`6.49999987987940120e-01` (0.64999998798794012 s), 12.012 ns before the
0.650000000000000022 s cutoff and within the declared 1 us maximum gap.  The
recorded F2 rising edge is 0.654166666170675426 s at
`v_acsrc_acn = 169.705627484768428 V`; it is outside this normal prefix.  The
parameters bind `RLOAD=190 ohm`.  These are mechanical selection facts, not a
normal-case acceptance or a phase-selection decision.

The normal15 audit retained all selected rows and reports 37 equal-time groups,
57 repeated rows, maximum group size 3, no missing right neighbor, no logic
changes, and no cycle-boundary groups.  Its E3 spread is
`2.730999642781291806e-13 J` and its whole-prefix E3 sum of absolute changes is
`2.581801159691144682e-12 J`.  The metrics report 57 duplicate rows,
2,474,542 settled rows, one arm transition and one on transition.  These
diagnostic counts do not replace the complete event-aware-normal-v1 acceptance
checks (finite rows, backwards-time check, endpoint, positive-gap limit,
all-row extrema, normal electrical screens, and source receipts).

## Equal-time ambiguity and margins

The audit's `same_time_max_delta` is the relevant duplicate ambiguity.  Its
largest analog values are 2.8654e-9 V for `v(acsrc)` (normalized
6.86e-6), 2.4124e-10 A for `i(Vac)` (normalized 2.91e-7), 8.8452e-11 A for
`i(Lboost)`, 3.1264e-12 V for `v(sw)`, and 2.6038e-14 V for `v(gate)`;
`v(load)` and `v(vb)` are 2.2737e-13 V.  The derived 12-column metric repeats
the current value and reports a differential AC-source value of 4.2633e-14 V;
that is a different derived channel from the raw `v(acsrc)` node above.

The audit's all-time deltas (for example, 60.534 V on `v(acsrc)` and 0.584 A
on `i(Vac)`) span ordinary positive-time solver steps.  They must not be used
as equal-time ambiguity or as evidence that a duplicate group is physically
unstable.

The full-neighbor hull bounds for representative-choice quadrature are
`3.9767e-22 J` for input power, `4.4031e-21 V²·s` for `ac2`, `2.5911e-23 A²·s` for
`i2`, `1.2959e-26 J` for load power, and `3.2690e-27 V·s` for bus voltage over
the selected prefix.  There are no boundary groups.  Relative to the reported
normal metrics (868.353172 W input power, 773.463986 W load power,
383.379954 V mean bus, 0.2708% cycle drift, and 68.107971 W energy residual),
these are negligible representative-choice effects.  They are not a bound on
global solver error, hidden unsaved state, controller-model validity, or
hardware behavior.  The `engineering_screen=REPORTED_NOT_ACCEPTED` line must
therefore remain diagnostic; `screens=0` is not inherited as acceptance.

For scale, accepted LL01/LL07 receipts use the same event-aware policy while
retaining the legacy strict-checker rejection.  Their event audits likewise
require no boundary/logic ambiguity and compare event bounds with each case's
own margins.  That precedent supports the method, but it does not transfer
their screen result or source receipt to F2-CREST.

## Required parent checks before any acceptance

1. Resolve the phase35 source-value conflict quantitatively and bind the
   phase/fault event to this exact source-hashed trace.  A passing frozen
   checker or this prefix audit alone is insufficient.
2. Complete the separately pending legacy strict-checker run and retain its
   `REJECTED_NONINCREASING_TIME` result; do not hide it by deduplicating or
   shifting timestamps.
3. Verify the completed passes against the full event-aware-normal-v1 acceptance contract for this
   prefix: finite/nondecreasing timestamps, endpoint and maximum positive gap,
   all-row extrema, final-cycle normal screens, source/include hashes, and the
   actual armed/healthy prefix conditions.  Do not infer any of these from the
   diagnostics' `screens=0`.
4. Only after the prefix is independently accepted may the F2 post-fault trace
   be judged.  The eventual fault decision still needs its full trace, detector
   timing, branch-current evidence, and fault-specific screens; this normal
   prefix does not establish interruption, fuse/arc behavior, SOA, thermal
   limits, or total-energy qualification.

Conclusion: this bounded pass found no numerical blocker in the measured
equal-time representative-choice quantities.  It is a useful evidence input
for parent review, not an acceptance receipt or a fault verdict.
