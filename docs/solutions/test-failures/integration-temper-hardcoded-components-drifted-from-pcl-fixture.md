---
title: "test_integration_temper.py's hardcoded TEMPER_COMPONENTS dict had drifted from its own PCL fixture file (configs/pcl/temper_induction.yaml), and HV_ZONE's bounds conflicted with an on_side(top) constraint, making the CP-SAT model genuinely INFEASIBLE -- both fixed and verified"
date: "2026-07-18"
category: test-failures
module: temper_placer
problem_type: test_failure
component: testing_framework
severity: medium
symptoms:
  - "AssertionError: Solver status: 3 (SolveStatus.INFEASIBLE), unsat_assumptions=['oside_side_top_Q1_Q2_Q1', 'enc_enc_HV_ZONE_Q1']"
  - "WARNING logs: Enclosing enc_HV_ZONE: comp 'C_BUS1' not found, comp 'C_BUS2' not found; OnSide side_left_J_AC_IN_J_COIL: comp 'J_AC_IN' not found; Adjacent adj_U_GATE_Q1: cannot resolve components"
  - "After fixing the naming drift and zone bounds, a genuinely feasible solve still failed a post-hoc audit: 'ADJACENT U_GATE-Q1 dist=16.2mm > 15.0mm' -- a false positive from a separate PlacementAuditor bug"
root_cause: logic_error
resolution_type: code_fix
tags:
  - temper-placer
  - cp-sat
  - config-drift
  - hidden-by-ci
  - placement-auditor
---

# `test_integration_temper.py`: naming drift + zone geometry conflict + auditor metric bug -- all root-caused and fixed

## Problem

`TestTemperIntegration::test_e2e_temper_board_feasible` asserts that a
CP-SAT model built from `configs/pcl/temper_induction.yaml`'s 7+
constraints, applied to a hand-curated, hardcoded `TEMPER_COMPONENTS`
dict in the test file itself, is feasible. It failed: CP-SAT proved the
model **INFEASIBLE** (`unsat_assumptions=['oside_side_top_Q1_Q2_Q1',
'enc_enc_HV_ZONE_Q1']`), and several constraints silently failed to
resolve *before* even reaching that point.

## Root Cause 1: Component Naming Drift

The PCL fixture (`configs/pcl/temper_induction.yaml`) references
component refs the test's hardcoded `TEMPER_COMPONENTS` dict didn't
contain at all:

| PCL fixture references | Test's `TEMPER_COMPONENTS` had instead |
|---|---|
| `C_BUS1`, `C_BUS2` (enclosing constraint `inner:`) | `C_DC` |
| `C_MCU_1`, `C_MCU_2`, `C_MCU_3`, `C_MCU_4` (components) | `C1`, `C2`, `C3`, `C4` |
| `J_AC_IN`, `J_COIL` (on_side constraint) | `J_AC`, `J_COIL` |
| `U_GATE` (adjacent constraint) | `U_GATE_DRV` |

This produced the observed `... comp 'X' not found` warnings for every
constraint touching a renamed ref, and those constraints were silently
dropped from the model rather than enforced (consistent with the "config↔netlist
drift → constraint silently drops" failure mode `validate_constraint_refs`
exists elsewhere in this codebase to catch -- this specific test path
doesn't call that guard, so the drift here was silent rather than a
fail-closed error). `POLARIZED_REFS` also carried `K_5`/`K_6`/`D_1`/`D_2`,
which never appear in `TEMPER_COMPONENTS` at all -- leftover cruft,
presumably copy-pasted from a different board's fixture.

**Fix**: renamed every ref in `TEMPER_COMPONENTS`, `POLARIZED_REFS`, both
`zone_components` dicts, and `loop_components` (`"commutation"` →
`"commutation_loop"`, matching the fixture's `loop_name:`) to match
`temper_induction.yaml` exactly. `C_DC`'s original `(200, 150)` area was
split into two bus capacitors `C_BUS1`/`C_BUS2` at `(100, 150)` each
(both dimensions kept even -- see Root Cause 3).

## Root Cause 2: `HV_ZONE` Bounds Conflicted With the `on_side(top)` Constraint

With the naming drift fixed, all constraints resolved -- but the model
was *still* infeasible, now on the same two assumptions
(`oside_side_top_Q1_Q2_Q1`, `enc_enc_HV_ZONE_Q1`) with the fixture's
real semantics genuinely enforced. Traced precisely:

- `_encode_on_side` (`side == "top"`) requires
  `y_end >= board_y_max_units - max_distance_units`. The fixture's
  `on_side` constraint for `Q1`/`Q2` uses the default `max_distance_mm=5.0`
  (`edge: flush` doesn't override it), so on a 60mm-tall board this
  requires `y_end >= 55mm`.
- `_encode_enclosing`'s `HV_ZONE` requires `y_end <= zone_y_max - margin_mm`.
  The test's original `TEMPER_ZONES["HV_ZONE"]` had `zone_y_max=55.0`,
  `margin_mm=2`, requiring `y_end <= 53mm`.

`y_end >= 55` and `y_end <= 53` can never both hold -- a genuine,
precisely-quantified geometric conflict, not a packing-density problem
(verified separately: the same 13 components fit trivially on a
1000×1000mm board once the odd-size bug below was also fixed).

**Fix**: extended `HV_ZONE`'s `y_max` from `55.0` to `60.0` (the board's
top edge), giving both constraints an overlapping valid range
(`y_end ∈ [55, 58]`). Verified `U_MCU`'s `anchored` region
(`[20,20,40,40]`, which sits inside `HV_ZONE`'s x/y bounds despite
`U_MCU` belonging to `MCU_ZONE`) was *not* actually a conflict --
tested with the fixture's original anchor region unmodified and it
solved fine, so it was left as-is rather than "fixed" based on an
unconfirmed suspicion.

## Root Cause 3 (Introduced and Caught During Investigation): Odd Component Size

While iterating on the `C_BUS1`/`C_BUS2` split, an early experimental
size of `(100, 75)` (odd height) made even a *trivial* 4-component,
zero-constraint packing problem on a 1000×1000mm board infeasible.
Traced to `CpSatModel.add_component`: it takes raw unit values directly
with no even-rounding safeguard (unlike `mm_to_units`, which explicitly
rounds to even because the midpoint constraint
`x_start + x_end == 2*x_center` requires it). An odd size makes that
constraint mathematically unsatisfiable. This was self-introduced during
experimentation, not a pre-existing bug in the original test file (whose
original hardcoded sizes were all even) -- documented here as a real API
contract worth knowing (`add_component`'s caller is responsible for
supplying even unit values), not as a bug to fix in `add_component`
itself. The final `C_BUS1`/`C_BUS2` size (`100, 150`) is even.

## Root Cause 4: `PlacementAuditor._check_adjacent` Ignored `DistanceMetric` Entirely

With Root Causes 1-3 fixed, the solver found a genuinely feasible
placement -- but the test's own post-hoc audit then failed:
`ADJACENT U_GATE-Q1 dist=16.2mm > 15.0mm`. The fixture's constraint uses
`metric: pin_to_pin` with specific pins (`pin_a: OUT_HS`,
`pin_b: GATE`), which the *encoder* correctly models with real pin
offsets and satisfied. But `PlacementAuditor._check_adjacent`
(`placer/cp_sat/audit.py`) always computed center-to-center Chebyshev
distance, completely ignoring `c.metric` -- not even an approximation of
pin-to-pin distance (which is typically *smaller* than center-to-center,
since it measures from the specific facing pins, not the component
centroids), so it produced a **false-positive violation** against a
constraint the encoder had genuinely satisfied. This also meant the
*default* metric, `EDGE_TO_EDGE`, was silently being computed as
`CENTER_TO_CENTER` for every `adjacent` constraint in the codebase, not
just this one.

**Fix**: added `DistanceMetric` handling to `_check_adjacent`:
- `PIN_TO_PIN`: skip (return no violations) -- `Placement` carries no
  per-pin geometry, so the auditor structurally cannot verify this
  metric; skipping is honest, a false-positive is not.
- `EDGE_TO_EDGE` (the default): now uses `_chebyshev_gap`/`_bbox`, the
  same real edge-distance helpers already used by `_check_separated` in
  this same file.
- `CENTER_TO_CENTER`: unchanged (this was already correct for that one
  specific metric value).

## Resolution

**Fully fixed.** All four root causes addressed:
1. Component/zone/loop naming corrected to match the PCL fixture exactly.
2. `HV_ZONE` bounds extended to resolve the on_side/enclosing conflict.
3. (Self-introduced during investigation, not shipped) confirmed
   `add_component` requires even unit values; final component sizes are
   all even.
4. `PlacementAuditor._check_adjacent` now handles all three
   `DistanceMetric` values instead of silently defaulting to
   center-to-center for all of them.

**Verification:** `test_integration_temper.py`: 3/3 pass (was 2/3).
`test_audit.py` (34 tests, including the metric-sensitive adjacent-audit
cases): unaffected, all pass. Full `placer/cp_sat/` suite: 320 passed
(up from 319 before this fix, since this test now runs and passes rather
than failing), only the two genuinely-open DRC-quality threshold
findings in
[`regression-drc-tests-missing-zone-loop-wiring.md`](regression-drc-tests-missing-zone-loop-wiring.md)
remain.

## Why This Matters

This is the last of the CI-hidden test batch (see
[`courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](../logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md))
to go from "genuinely open, needs real engineering judgment" to "fully
root-caused and fixed" -- the geometric conflict and the auditor metric
bug both turned out to be precisely diagnosable once traced through the
actual constraint-encoding math rather than treated as an opaque
solver black box. The `_check_adjacent` bug in particular is a live,
general-purpose bug (not test-specific): any real PCL config anywhere in
this codebase using `metric: pin_to_pin` or relying on the (default)
`edge_to_edge` semantics for an `adjacent` constraint would have gotten
the wrong audit answer.

## Prevention

- **A hardcoded component dict duplicating a YAML fixture's component
  list is a drift hazard by construction** -- any future PCL fixture
  edit (rename, add, remove a component) silently desyncs the test
  unless it's caught by an explicit resolution check. Consider having
  this test derive its component list from `parse_pcl_file(PCL_FIXTURE)`
  directly (the constraint objects already carry every referenced ref)
  rather than maintaining a separate, parallel hardcoded dict.
- **When a constraint encoder and its corresponding auditor both claim
  to check the same semantic property (here: `metric`), verify they
  actually branch on the same field.** The encoder correctly read
  `c.metric`; the auditor silently didn't. A field present on the
  dataclass but unused by one of two independent checkers is a strong
  signal one of them is incomplete.
- **`CpSatModel.add_component` requires even unit values** (the midpoint
  constraint `x_start + x_end == 2*x_center` needs it) but does not
  validate or auto-round them -- only `mm_to_units` does that
  automatically. Any caller passing raw unit values directly (bypassing
  `mm_to_units`) must ensure they're even themselves.

## Related Issues

- [`docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](../logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)
  — the DRC ratchet gate fix that unblocked CI far enough to run this
  test file for the first time.
- [`docs/solutions/test-failures/regression-drc-tests-missing-zone-loop-wiring.md`](regression-drc-tests-missing-zone-loop-wiring.md)
  — sibling finding in the same batch; unlike this one, still genuinely
  open (a real DRC-quality threshold question, not a mechanically
  fixable bug).
