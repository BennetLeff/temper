---
title: "OR-Tools SufficientAssumptionsForInfeasibility() returns proto variable indices, not Python list positions"
date: 2026-07-03
category: logic-errors
module: placer/cp_sat/unsat
problem_type: logic_error
component: tooling
severity: high
symptoms:
  - "`SufficientAssumptionsForInfeasibility()` returned proto variable indices (var.Index()) instead of positions in the Python assumption list"
  - "UNSAT core constraint mappings were silently incorrect without the reverse index map"
root_cause: wrong_api
resolution_type: code_fix
tags:
  - or-tools
  - cp-sat
  - unsat-core
  - proto-indices
  - assumption-variables
---

# OR-Tools `SufficientAssumptionsForInfeasibility()` returns proto variable indices, not Python list positions

## Problem

`solver.SufficientAssumptionsForInfeasibility()` returns variable **proto indices**
(the integer values from `var.Index()`), not positions in the Python assumption
variable list.  Using the return value directly to index into a `constraint_map`
dictionary keyed by list position produces silently incorrect UNSAT core mappings.

## Symptoms

- After extracting the "sufficient" core from an INFEASIBLE solve, the returned
  constraint descriptions made no sense (wrong constraints flagged).
- The mismatch was silent — no error, no warning, just wrong core output.
- Manual inspection of the core against the actual conflict was required to detect
  the issue.

## What Didn't Work

Using `solver.SufficientAssumptionsForInfeasibility()` output directly as list indices:

```python
# BAD: proto indices used as local list indices — produces wrong core
proto_indices = solver.SufficientAssumptionsForInfeasibility()
sufficient_core = [
    constraint_map[pi] for pi in proto_indices if pi in constraint_map
]
```

This silently produces incorrect results because `var.Index()` returns a proto-level
integer that has no relation to the Python list position of the assumption variable.

## Solution

Pre-build a reverse map from proto index to local list position, then translate
before looking up:

```python
def _build_proto_index_map(
    assumption_vars: Sequence[cp_model.IntVar],
) -> dict[int, int]:
    """Build {proto_index: local_index} lookup."""
    return {v.Index(): i for i, v in enumerate(assumption_vars)}


proto_to_local = _build_proto_index_map(assumption_vars)
proto_indices: list[int] = list(
    solver.SufficientAssumptionsForInfeasibility()
)
sufficient_local_indices = sorted(
    proto_to_local[pi] for pi in proto_indices if pi in proto_to_local
)
sufficient_core = [
    constraint_map[i] for i in sufficient_local_indices if i in constraint_map
]
```

The full pipeline in `extract_unsat_core()`:
1. Build the proto-to-local reverse map once at the start.
2. Solve with all assumptions enabled.
3. Retrieve proto indices from `SufficientAssumptionsForInfeasibility()`.
4. Translate to local indices via the reverse map.
5. Look up human-readable descriptions in `constraint_map`.
6. Feed local indices to the MUS refinement loop (`refine_mus()`), which operates
   on list positions.

## Why This Works

The mapping `v.Index()` → local list index is a pure function of the assumption
variable list.  Every `IntVar` created via `model.NewBoolVar()` has a deterministic
proto index set at creation time, and the `_build_proto_index_map` reverse lookup
is O(n) once built.  Assumptions are set via `model.AddAssumptions()` /
`model.ClearAssumptions()` on the model proto, not passed as kwargs to
`solver.Solve()` — the translation step bridges these two domains.

## Prevention

1. **Scrutinize OR-Tools API return types.** When an API returns integers that could
   be proto indices, test the mapping by solving a trivially infeasible model with
   exactly two assumption variables and confirming the core maps correctly.
2. **Document the proto-index semantics in the module docstring.** The `unsat.py`
   module carries an API note explaining the proto-index semantics.
3. **Test the core extraction with deliberate UNSAT models.** The 13 tests in
   `test_unsat.py` cover: trivially infeasible models, redundant constraint removal,
   all-essential constraints, timeout behavior, consecutive solves, and missing
   `constraint_map` entries — each validates that core descriptions match the
   expected conflict.
4. **Isolate the translation behind helper functions.** `_build_proto_index_map` +
   `_add_assumptions` isolates OR-Tools' proto-index quirk behind two small
   functions, so callers never touch proto indices directly.

## Related

- `docs/solutions/logic-errors/unsound-atmostk-capacity-encoding.md` — same
  "never trust solver output" pattern applied to SAT solver AtMostK encoding
- `packages/temper-placer/src/temper_placer/placer/cp_sat/unsat.py` — full
  implementation with inline API note
- `packages/temper-placer/tests/placer/cp_sat/test_unsat.py` — 13 tests
  validating core extraction correctness
