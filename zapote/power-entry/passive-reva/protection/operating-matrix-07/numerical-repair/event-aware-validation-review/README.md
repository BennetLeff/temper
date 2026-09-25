# Event-aware timestamp validation: adverse review

Status: read-only review. No checker, normalizer, circuit, solver option, or
acceptance result was changed. This document does not grant a normal-operation
pass.

The question is whether a diagnostic view can distinguish a finite, short
same-time callback group from the terminal hard-driver stall while preserving
the original strict qualification gate. The answer is yes as a *separate
diagnostic classifier*, but the proposed classifier cannot replace the
strict checker yet.

## Evidence being reviewed

The unchanged checker in `checker/operating_point_checker.rs`:

* requires the exact twelve-column header and twelve finite values per row
  (lines 98–125);
* rejects every `dt <= 0` and keeps the existing 1 ms gap and switching-step
  checks (lines 126–143);
* requires startup coverage, an exact declared endpoint within 1 ns, and at
  least three mains cycles (lines 209–224);
* integrates with trapezoids over positive intervals (lines 194–204), uses
  `binary_search` for boundary samples (lines 167–192), and computes stored
  energy only from VB, VD, and boost current (lines 206–208); and
* scans every retained row for device peaks (lines 259–274), while settled
  bus envelope and regulation use the final cycle window (lines 250–258).

The diagnostic callback already records duplicate, backwards, and nonfinite
time separately and retains the first-invalid named-vector snapshot. Its
unchanged 120 s less-than-1-us simulation-progress watchdog remains a host
resource diagnostic, not an electrical limit (`numerical-repair/nonstopping-first-invalid/run/progress.rs:131–180, 243–274`).

The retained full-B event audit is not an acceptance result. It found
30,108,912 finite rows, 45 equal-time groups, 111 rows in those groups, and
66 repeated intervals. The first group is at
`0.5015549144856806807 s`; the largest group has three rows and that group's
largest reported equal-time change is `3.858561129624220026e-8` in
`v(xdriver.drv_delay)`, followed by a positive one-ULP step. Across all equal
groups, the event audit reports a larger `i(Vac)` delta of
`8.954151153872658142e-8 A` and a largest `v(xdriver.drv_delay)` delta of
`4.431854583230474355e-8 V`. The unchanged checker rejects the trace. The
original hard-driver run is the adverse counterexample: 1,126,438
non-increasing intervals and no useful forward advance at
`0.348534537976268155 s`.

## Smallest defensible diagnostic classifier

This is the boundary of what can be proposed without changing the original
qualification contract:

1. Parse the exact header and every field. Retain every row in original order.
   Reject nonfinite values and backwards time immediately. Permit `dt == 0`
   only in this diagnostic path, and report every equal-time group with its
   row count, analog deltas, logic changes, and following positive step.
2. Keep the existing completeness requirements unchanged: startup prefix,
   declared endpoint, three-cycle coverage, and the existing maximum positive
   gap and switching-step screens. A trace that does not reach its endpoint is
   still incomplete even if it has many finite callbacks.
3. For each equal group, report source-tolerance-scaled deltas by physical
   type, rather than inventing one scalar threshold. For a voltage diagnostic
   screen, use `vntol + reltol * max(abs(prev), abs(curr))`; for a current,
   use `abstol + reltol * max(abs(prev), abs(curr))`. The current deck values
   are `vntol=1e-7 V`, `abstol=1e-10 A`, and `reltol=2e-4`. Do not compare a
   voltage delta against `abstol`, or a logic state against either tolerance.
4. Treat `dt == 0` rows as zero measure in ordinary trapezoidal integrals, but
   also calculate and report the known-storage energy change across each equal
   group using the checker’s VB/VD/IL expression. A nonzero group energy is an
   instantaneous-update ambiguity, not silently zero energy. If a saved state
   is missing, the bound is incomplete and the diagnostic must say so.
5. Preserve every row for all-row extrema and event ordering. A same-time
   overvoltage or current peak must not disappear because the last row is safe.
   Record changes in `armed`/`on` and other discrete outputs explicitly;
   settled fractions alone cannot see a zero-measure off pulse.
6. Require eventual positive progress after every equal group and require the
   full endpoint. Keep the existing wall-progress watchdog for terminal stalls
   and report the minimum positive step and duplicate count. Do not turn a
   minimum positive step observed in one trace into a new acceptance limit.

The source-tolerance calculation is evidence for triage only. It is a new
numerical diagnostic screen, not an automatic physical-model qualification
rule. Ngspice’s
`reltol`, `vntol`, and `abstol` constrain convergence equations; they do not
by themselves prove that a saved-row delta is a physically valid state update.
Using the formula above as a new pass gate would be a new physical-model
qualification requirement, not a harmless timestamp-policy clarification.

## Adverse cases the classifier must defeat

| Case | How a weak event-aware rule falsely passes | Required treatment |
| --- | --- | --- |
| Terminal stall | A callback loop has `dt == 0` forever, so “non-decreasing” looks healthy. | Require endpoint and existing wall-progress watchdog; never accept a partial trace. |
| Millions of tiny positive steps | Every `dt > 0`, but simulation advances less than 1 us for minutes. | Report minimum step and wall rate; retain the existing progress screen. No arbitrary new `dt` floor. |
| Peak then return in an equal group | Last equal row is safe although an earlier row exceeds VDS/VB/current. | Scan all rows, including every member of the group, for the existing stress extrema. |
| Discrete logic toggles at one time | `on_fraction` remains 1 because a zero-duration off pulse has zero integral. | Record every logic transition and classify the settled-state claim as unresolved until independently qualified. |
| Missing internal node | Saved terminal columns are finite, so a hidden capacitor/controller state change is invisible. | Require an expected diagnostic-name mask for the diagnostic claim; missing vectors prevent a state-complete conclusion. |
| Zero-time bus charge | VB changes across equal rows but `dt * power` contributes zero, hiding an energy impulse. | Report `DeltaE_equal_group`; bound it from all relevant saved storage states or mark energy balance unresolved. |
| Duplicate exactly at a cycle boundary | `binary_search` can choose one of several equal rows, changing interpolation and cycle metrics. | Evaluate first-row and last-row boundary conventions and require metric agreement, or mark the metric ambiguous. |
| Analog delta below tolerance but latch changes | A small terminal delta hides a discrete internal event or event ordering change. | Tolerances screen analog deltas only; event/state identity remains a separate unresolved item. |

## What may be reported and what remains blocked

The following can be reported diagnostically without changing the original
claim, provided the raw rows and hashes are retained: duplicate-group count
and locations, finite/backwards status, positive progress after each group,
all-row extrema, source-scaled analog deltas, and settled-cycle metrics under
an explicitly stated first/last duplicate convention.

The numerical treatment of a duplicate timestamp does not itself require a
state-complete physical model. It can be validated for the modeled observable
columns if the raw rows are retained, both duplicate-boundary conventions
give the same metric classification within a predeclared observable-error
budget, and the trace reaches its endpoint with bounded forward progress.

Separate physical claims remain bounded by the existing model: thermal or
hidden-state qualification, instantaneous protection response, energy balance
when an unmeasured storage state may change, and the correctness of controller
event ordering cannot be inferred from terminal columns alone. Those are model
limits to state explicitly; they are not reasons to pretend the timestamp
metric calculation is impossible.

## Required tests before any policy discussion

No full simulation is required for these tests, but all must be independent of
the retained full-B verdict:

1. Rust parser fixtures for finite equal groups, backwards/nonfinite time,
   missing fields, wrong header, endpoint truncation, maximum-gap violation,
   equal groups at startup/end/cycle boundaries, and a repeated-time terminal
   stream.
2. Tolerance-unit fixtures for voltage, current, and logic columns. Include a
   value below each source-scaled analog bound, a value above it, and a logic
   toggle with zero analog delta. No cross-unit tolerance is allowed.
3. Integrator differential fixtures: strict positive-time trace; the same
   trace with equal rows inserted; an equal group with a known VB/VD/IL energy
   change; and an equal group at a cycle boundary. Positive-interval integrals
   must be invariant where `DeltaE_equal_group == 0`; otherwise the result must
   be flagged with an explicit energy ambiguity rather than accepted.
4. Extrema and event fixtures where the first equal row exceeds a stress limit,
   the last row is safe, and `armed/on` toggles only inside the equal group.
   This catches last-row-only and fraction-only false passes.
5. Progress fixtures for one equal group followed by a positive step and for a
   persistent same-time stream. The first may be a diagnostic event; the
   second must fail completeness/watchdog classification.
6. Bind the classifier to the exact ngspice 45.2 source audit and the retained
   full-plant traces. The source audit already identifies the callback as an
   accepted output-point path and documents the binary64 spacing mechanism;
   the retained hard-driver trace supplies the terminal-stall adversary, while
   the full-B trace supplies a finite duplicate group followed by progress.
   A reduced event deck and callback synthetic tests are useful confidence
   experiments, but they are optional and must not be treated as acceptance
   evidence.

## Necessary evidence versus optional confidence

Before considering event-aware handling for this modeled circuit, the
necessary evidence is finite raw-row retention with hashes; no backwards or
nonfinite times; exact endpoint/startup/positive-gap coverage; all-row extrema;
and a two-convention metric audit. The audit should compute each original
observable twice, selecting the first versus last row when an equal group
straddles an integration boundary, then report the absolute difference as the
observable error budget `B_M = |M_first - M_last|`. For known storage, report
the independent same-time spread `B_E = max(E_group) - min(E_group)` using the
existing `E(VB,VD,IL)` expression; this is not silently folded into `dt *
power`. The budgets must be predeclared from the existing metric
precision/engineering margin, rather than invented after seeing the result.
Any metric whose classification changes is ambiguous and cannot be used for an
accepted claim. The existing strict checker must still report the duplicate
trace as rejected until the project explicitly changes policy.

The old hard-driver non-advancing trace is already the required adverse
terminal-stall case; the completed full-B trace is the required finite-group
case. No third mandatory reproducer is needed to establish this numerical
distinction. Optional confidence work includes reduced event decks, more
internal saved nodes, tolerance sensitivity, and hardware correlation. Those
experiments can improve interpretation of the circuit model but do not replace
the two-convention observable audit or authorize a pass.

Until those tests and the observable-error audit exist, retain the strict
`dt > 0` checker as the sole qualification gate. A separate
non-decreasing/event report is useful for explaining the 501.55 ms result, but
it must never be substituted for the rejected strict result or used to launch
the normal grid/fault campaign.
