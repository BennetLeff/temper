# Fault-capture timing policy review

This is a read-only review of the prepared Matrix 07 fault tools.  It does not
launch a fault simulation, change the checker, or waive a timestamp failure.
The accepted normal baseline is the scoped model receipt in
[`../accepted-baseline-11/acceptance.json`](../accepted-baseline-11/acceptance.json):
30,108,912 rows from `2e-10` through `0.65 s`, 66 exact-equal intervals in 45
groups, no backwards/nonfinite rows, maximum positive gap about `500 ns`, and
zero saved logic changes inside its equal groups.  Its legacy strict checker
still rejects the trace; that rejection is deliberately retained.

## What the current fault path actually requires

The transport and checker each enforce strict increase.  In
[`adapter-09/fault_normalize.rs`](adapter-09/fault_normalize.rs),
`StreamState::observe` (lines 308--320) rejects `dt <= 0` and any gap over its configured
`MAX_GAP` (the runbook uses `25 ns`), requires the first row at zero, and
checks the declared endpoint.  The same adapter retains the fault mutation and
F2 transitions, requires exactly one injection rising edge in its event window,
and checks the prefault ARM/PERMIT/q/en/fault slice.  In
[`fault_checks.rs`](fault_checks.rs), `parse_trace` (lines 134--165) also rejects `row.t <=
previous.t`, requires at least 100 rows, a start within `1 ns` of zero, and an
endpoint within `1 ns` of `TSTOP`.  [`tracked-host-09/verify_trace.rs`](tracked-host-09/verify_trace.rs) independently rejects a
non-increasing 42-column export and can enforce the `25 ns` pacing gap.

Therefore a fault raw trace containing the same kind of callback groups as the
accepted normal trace cannot pass the current adapter/checker unchanged.  It
is not defensible to deduplicate a group, nudge its timestamps, or call the
strict failure a blanket waiver.  The normal receipt proves that equal
timestamps are a possible finite-output callback condition; it does not prove
that a fault callback group has harmless state ordering.

The predeclared fault timing remains useful and must stay unchanged.  The
runbook and timing preflight choose F2-CREST near `0.6541666666667 s` with a
`2 ms` detector/search and `2 ms` observation, F2-ZERO near
`0.6583333333333 s` with `10 ms` and `10 ms`, and F2-START only after a
measured healthy armed prefix (at least `10 ms`) with a measured event.  The
checker searches around the injected `t_F`; detector latency, F2-open order,
gate/channel turn-off and passive-current peaks remain separate observations.
The declared `25 ns` local pacing is an instrument constraint for the fault
window, not a reason to widen a gap after a failed capture.

## Minimum defensible case policy

1. Retain the complete raw fault stream, with exact binary64 times and every
   normal, fault, branch-current, and marker column.  Keep FIFO compression and
   watchdog/provenance receipts, but never alter rows to satisfy strict parsing.
2. Validate the entire cold prefix and endpoint before interpreting the fault:
   finite fields, nondecreasing time, start/end, positive-gap ceiling,
   all-row node/current peaks, and equal-time groups.  Emit a bounded event
   artifact containing every group row plus immediate LEFT/RIGHT context and
   source row numbers.  Require each finite group to have positive progress;
   count logic/ARM/PERMIT/fault transitions within a group instead of selecting
   a representative row.  A terminal group with no RIGHT context is an
   incomplete capture for interval bounds even though its saved-state extrema
   remain reportable.
3. Apply the existing fault `check` rules to the same, unchanged row sequence
   after parsing is made event-aware.  The smallest credible implementation is
   a reviewed fault-checker revision whose parser changes only strict `<=` to
   backward-time rejection and records equal groups; its detector edge, F2-open
   precedence, prefault healthy slice, node screens, turn-off budget,
   observation window, and failed-short `PROTECTION_GAP` semantics remain the
   existing code.  A separate suffix cannot be passed to the current checker:
   it would fail the start-at-zero/endpoint contract and would discard the
   cold-prefix state needed for the prefault ARM/PERMIT/q/en check.
4. Keep full-prefix evidence and fault-window evidence distinct in the report.
   The full trace supplies startup/endpoint and all-row stress.  The event
   window supplies the exact injection and detector rows, F2-control edge,
   gate/channel cessation, and body/inductor residual peaks.  If a detector
   transition is only distinguishable by two rows at one timestamp, preserve
   callback order and classify it as indeterminate unless the revised checker
   has an explicit row-order rule; never infer a positive delay from a
   representative row.
5. Preserve the strict checker as a compatibility instrument.  Run it on a
   fault capture only when the raw sequence is already strictly increasing,
   and retain its result beside the event-aware result.  A strict rejection is
   a timing/schema result, not protection evidence; an event-aware result is
   not permission to hide malformed or incomplete output.

This policy keeps the accepted normal baseline's 66 groups visible, allows a
new fault trace to demonstrate either no groups or its own groups, and makes
the minimum new parser/checker scope explicit.  It adds no tolerance, source
phase change, detector-window widening, timestamp repair, or hardware claim.
