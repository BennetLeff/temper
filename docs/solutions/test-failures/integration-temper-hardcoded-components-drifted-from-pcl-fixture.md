---
title: "test_integration_temper.py's hardcoded TEMPER_COMPONENTS dict has drifted from its own PCL fixture file (configs/pcl/temper_induction.yaml), causing several constraints to silently fail to resolve and the remaining CP-SAT model to prove genuinely INFEASIBLE"
date: "2026-07-18"
category: test-failures
module: temper_placer
problem_type: test_failure
component: testing_framework
severity: medium
symptoms:
  - "AssertionError: Solver status: 3 (SolveStatus.INFEASIBLE), unsat_assumptions=['oside_side_top_Q1_Q2_Q1', 'enc_enc_HV_ZONE_Q1']"
  - "WARNING logs: Enclosing enc_HV_ZONE: comp 'C_BUS1' not found, comp 'C_BUS2' not found; OnSide side_left_J_AC_IN_J_COIL: comp 'J_AC_IN' not found; Adjacent adj_U_GATE_Q1: cannot resolve components"
root_cause: test_isolation
resolution_type: documentation_update
tags:
  - temper-placer
  - cp-sat
  - config-drift
  - hidden-by-ci
  - unresolved
---

# `test_integration_temper.py`'s hardcoded component dict has drifted from its PCL fixture file

## Problem

`TestTemperIntegration::test_e2e_temper_board_feasible` asserts that a
CP-SAT model built from `configs/pcl/temper_induction.yaml`'s 7+
constraints, applied to a hand-curated, hardcoded `TEMPER_COMPONENTS`
dict in the test file itself, is feasible. It fails: CP-SAT proves the
model **INFEASIBLE** (`unsat_assumptions=['oside_side_top_Q1_Q2_Q1',
'enc_enc_HV_ZONE_Q1']`), and several constraints silently fail to
resolve *before* even reaching that point.

## Investigation

The PCL fixture (`configs/pcl/temper_induction.yaml`) references
component refs the test's hardcoded `TEMPER_COMPONENTS` dict doesn't
contain at all:

| PCL fixture references | Test's `TEMPER_COMPONENTS` has instead |
|---|---|
| `C_BUS1`, `C_BUS2` (enclosing constraint `inner:`) | `C_DC` |
| `C_MCU_1`, `C_MCU_2`, `C_MCU_3`, `C_MCU_4` (components) | `C1`, `C2`, `C3`, `C4` |
| `J_AC_IN`, `J_COIL` (on_side constraint) | `J_AC`, `J_COIL` |

This produces the observed `... comp 'X' not found` warnings for every
constraint touching a renamed ref, and those constraints are silently
dropped from the model rather than enforced (consistent with the "config↔netlist
drift → constraint silently drops" failure mode `validate_constraint_refs`
exists elsewhere in this codebase to catch -- this specific test path
doesn't call that guard, so the drift here is silent rather than a
fail-closed error).

Even with the naming drift aside, the **remaining, successfully-resolved**
constraints (`oside_side_top_Q1_Q2_Q1`, `enc_enc_HV_ZONE_Q1`, among
others) are still jointly infeasible on the test's hardcoded 100×60mm
board with `TEMPER_ZONES` bounds `HV_ZONE: (5,5,50,55)` /
`MCU_ZONE: (60,5,95,55)`. Whether fixing the naming drift alone
(restoring the dropped constraints to active enforcement) would resolve
or worsen this infeasibility is unknown without doing the fix and
re-running -- it's plausible the currently-passing subset is only
"passing" because several genuinely conflicting constraints are being
silently ignored.

## Resolution

**Not fixed in this pass.** This requires either:
1. Renaming `TEMPER_COMPONENTS`'/`TEMPER_ZONES`'s refs to match the
   current `temper_induction.yaml` fixture exactly, then iteratively
   checking whether the resulting (now fully-enforced) constraint set is
   geometrically feasible on the test's board/zone dimensions -- and if
   not, determining whether the board/zones need adjusting or the
   fixture's constraints are themselves too strict for this synthetic
   layout, or
2. Determining whether `configs/pcl/temper_induction.yaml` itself has
   drifted away from what this test was originally written against (i.e.
   the fixture changed, not the test), in which case the fixture or the
   test's board/zone geometry may need reconciling instead.

Both paths require real engineering judgment about the intended
component layout, not a mechanical rename -- explicitly out of scope for
this investigation pass, which focused on identifying and fixing
CI-hidden test/wiring bugs, not re-deriving PCL fixture intent. Flagged
here rather than silently left broken or force-fixed with unverified
guesswork.

## Why This Matters

Same root pattern as every other finding in this batch -- invisible
until CI reached the "CP-SAT Placer Tests" step for the first time (see
[`courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](../logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md))
-- but this one is a genuine open question rather than a fixable bug:
whether `temper_induction.yaml`'s current constraint set can ever be
satisfied on the geometry this test assumes.

## Prevention

- **A hardcoded component dict duplicating a YAML fixture's component
  list is a drift hazard by construction** -- any future PCL fixture
  edit (rename, add, remove a component) silently desyncs the test
  unless it's caught by an explicit resolution check. Consider having
  this test derive its component list from `parse_pcl_file(PCL_FIXTURE)`
  directly (the constraint objects already carry every referenced ref)
  rather than maintaining a separate, parallel hardcoded dict.

## Related Issues

- [`docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](../logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)
  — the DRC ratchet gate fix that unblocked CI far enough to run this
  test file for the first time.
- [`docs/solutions/test-failures/regression-drc-tests-missing-zone-loop-wiring.md`](regression-drc-tests-missing-zone-loop-wiring.md)
  — sibling finding in the same batch that also surfaced a genuine,
  not-mechanically-fixable question rather than a simple bug.
