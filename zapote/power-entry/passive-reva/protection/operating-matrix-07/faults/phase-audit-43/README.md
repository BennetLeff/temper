# Phase evidence with equal-time source ranges

This successor consumes every decoded fault42 row and reports phase evidence.
Its JSON always has `acceptance:false`; a successful scan does not accept an
operating point or protection outcome. The original phase35 source and its
full-capture rejection remain unchanged.

## Recorded discrepancy

F2-CREST38 has 32,237,324 rows, ending at 0.662 s. Its raw SHA-256 is
`d78e8e2f7c28b8ba9c10ce499af2813202ede8b2e173c39cfdc0ee3d650484fd`.
Phase35 rejected any unequal source values at an equal timestamp in the local
interval, regardless of their magnitude. Parent extraction from the complete
adapter report confirmed two local groups, six raw group rows, and maximum
signed source spread 2.842170943040401e-14 V. The groups occur at
0.651585501386003 s and 0.654166666666700 s. Neither contains a marker threshold
transition. Details and row identities are in `measured-equal-groups.json` and
`measured-groups-parent-verification.json`.

The unique recorded rising edge is at 0.654166666170675426 s. Measuring these
small differences alone does not establish the local peak or a phase pass.
The successor must scan the complete saved trace.

## Sufficient bounds under the unchanged 1% criterion

Let D be the largest signed source range within any equal-time group in the
unchanged local interval; P the maximum absolute source over every local row;
and E the first recorded source value in the unique rising-edge group.
The edge group must lie inside that same interval.

For any choice of representative within each equal-time group, the resulting
edge magnitude A lies in [max(0,abs(E)-D), abs(E)+D]. Its local peak M lies in
[max(0,P-D), P]. These follow from the absolute-value function changing by no
more than the change in its argument. Also A <= M, since the local sample set
includes the selected edge sample. Thus sufficient criteria are:

- Crest: max(0,abs(E)-D) >= (1-tolerance)*P.
- Zero: abs(E)+D <= tolerance*max(0,P-D), with a positive peak lower bound.

For crest, the lower bound implies A >= (1-tolerance)*M; no independent upper
overshoot condition is needed because A <= M. For zero, the inequality bounds
A by tolerance*M even for the smallest possible selected peak. A failed
sufficient bound is an unresolved/rejected phase diagnostic, not evidence that
every possible representative fails the underlying criterion.

The implementation reports observed D separately from its outward-rounded
upper bound. It rounds subtractions, additions and criterion products outward,
including D and the crest factor before multiplication. Overflow rejects.
This is a bound on representative-choice ambiguity in sampled data, not on
continuous-time behavior or total solver/model error.

## Guards and output

The exact42-column schema, finite values in every column, nondecreasing time,
complete endpoint within1ns, local coverage, initial-low marker, one global
rising edge and expected edge time within2ns remain required. An equal-time
marker threshold transition is always rejected. The edge and first/last
maximal groups need strict earlier/later neighbors inside the local interval.
Separated equal maxima are reported by count and span; they are not called a
continuous plateau. No rows or timestamps are changed.

Counts explicitly distinguish all trace rows from `local_equal_groups` and
`local_equal_group_raw_rows`. Normal startup coverage, healthy operation,
global sampling-gap and protection checks are established by the separate
prefix and fault pipelines, not by this phase tool alone.

## Verification

Parent compilation uses `rustc --edition=2021 -D warnings`, with10 passing
unit tests and15 independent black-box CLI probes in `parent-cli-probes/`.
The probes include source ambiguity, marker ambiguity, a tied peak on the
local boundary, nonfinite unused fields, header errors, time order/endpoint
errors, multiple edges, and cases just inside/outside the1% criterion.
`parent-review.json` binds source, binary and test receipts. The complete
saved-raw scan and its own all-child statuses are retained separately under
`full-F2-CREST38/`; a parent case disposition must review its measured result.
