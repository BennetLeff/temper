---
title: "PlaceRouteLoop.run() dispatched on the all_gates parameter alone, silently ignoring a caller's explicit custom gate registry unless all_gates=True was also passed"
date: "2026-07-18"
category: logic-errors
module: temper_placer
problem_type: logic_error
component: service_object
severity: high
symptoms:
  - "PlaceRouteLoop(gates=[CustomGate()]).run(...) (no all_gates=True) silently falls through to the legacy classifier-based convergence path, never calling CustomGate.check() or CustomGate.to_delta()"
  - "test_compound_loop.py::TestGateDrivenConvergence had 3/4 tests failing: test_violations_inject_deltas_and_continue, test_gate_deltas_unsat_exits, test_unmeasured_blocks_convergence -- all expecting gate-driven LoopExitReason values but getting legacy-path results (no_classifiable_feedback, or an unexpected success=True)"
  - "This was invisible in CI for the entire time it existed: the 'CP-SAT Placer Tests' CI step that runs this test file never ran, because an unrelated, always-failing DRC ratchet gate earlier in the same CI job aborted the workflow before reaching it"
root_cause: logic_error
resolution_type: code_fix
tags:
  - temper-placer
  - cp-sat
  - place-route-loop
  - gate-driven-convergence
  - dispatch-bug
  - hidden-by-ci
---

# `PlaceRouteLoop.run()` ignored a caller's explicit custom gate registry unless `all_gates=True` was also passed

## Problem

`PlaceRouteLoop.__init__` accepts a `gates` parameter and its own comment
states the intended contract: "Gate registry: when non-empty, gates drive
convergence." But `run()`'s actual dispatch logic only checked the
separate `all_gates` boolean parameter (`if all_gates: return
self._run_with_gates(...)`), never looking at `self.gates` at all.
Constructing `PlaceRouteLoop(gates=[SomeCustomGate()])` and calling
`.run(...)` without also passing `all_gates=True` silently took the
legacy classifier-based convergence path -- `self.classifier.classify()`
against raw routing/DRC data, with zero awareness of the custom gate --
instead of the intended gate-driven path.

Found while investigating why `test_compound_loop.py::TestGateDrivenConvergence`
had 3 of 4 tests failing, first surfaced by CI actually reaching this test
file for the first time (see
[`courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)'s
sibling investigations for the DRC ratchet gate fix that unblocked CI far
enough to run this step at all).

## Root Cause

```python
# ---- Build gate registry for all_gates path --------------------------
if all_gates:
    ...
    gates = [DrcGate(), RoutingGate(), StackupGate(), PhysicsGate(), QualityGate()]
else:
    gates = list(self.gates) if self.gates else []
...
# ---- Gate-driven path (U4) -------------------------------------------
if all_gates:                                  # <-- BUG: ignores `gates`
    return self._run_with_gates(...)
```

The local `gates` variable at line ~281 was already correctly built to
reflect either the `all_gates=True` 5-gate default set, or the
constructor's `self.gates` (whatever was passed, or the constructor's own
2-gate default). But the dispatch condition immediately below it checked
the *parameter* `all_gates` again, completely bypassing the `gates`
variable it had just built. Any caller relying on the constructor's
documented `gates=` customization path -- without separately also
setting `all_gates=True` -- got the wrong convergence logic with no
error, warning, or type mismatch; both paths return the same `LoopResult`
type, so nothing signals the mismatch except wrong `reason` values deep
in the result.

## Why a Naive Fix (dispatch on `if gates:`) Is Wrong

The obvious fix -- change the dispatch condition to check the local
`gates` variable's truthiness instead of `all_gates` -- is unsafe here.
`PlaceRouteLoop()`'s default constructor (no `gates=` argument) already
populates `self.gates = [DrcGate(), RoutingGate()]` -- **non-empty** --
confirmed as intentional by `TestDefaultRegistry::test_default_constructor_registers_two_gates`,
an existing, correct, passing test. If dispatch checked "is `gates`
non-empty" unconditionally, **every** caller using the plain default
constructor (the one and only production call site,
`cli/__init__.py:419`, plus a dozen+ other test files across
`test_loop.py`, `test_loop_termination_pbt.py`,
`test_loop_field_feedback.py`, `test_place_route_loop_temper.py`,
`test_all_gates_convergence.py`) would silently switch from the legacy
path to the gate-driven path by default, even without `all_gates=True`
-- a sweeping behavior change to the CLI's real production default,
verified as NOT what those tests or that call site expect.

A second data point pins down the correct semantics precisely:
`TestBackwardCompat::test_empty_gates_preserves_classifier_path`
constructs `PlaceRouteLoop(gates=[])` (an **explicit empty list**, not
the implicit default) and asserts the **legacy** path runs. So the
correct signal isn't "was `gates=` passed at all" (`gates is not None`)
either -- `gates=[]` is explicitly passed but must still mean legacy.

## Solution

The correct dispatch signal is: **did the caller pass a non-empty
explicit `gates=` list to the constructor** (`bool(gates)` at
construction time, stored as `self._gates_explicit`), OR is
`all_gates=True`. `gates=None` (default) and `gates=[]` (explicit empty)
are both falsy and both correctly mean "use the legacy path unless
`all_gates=True` is also set" -- matching both `TestDefaultRegistry` and
`TestBackwardCompat`. Only a genuinely non-empty custom list means "drive
convergence off this gate registry":

```python
# In __init__:
self._gates_explicit = bool(gates)   # None and [] are both falsy

# In run():
if all_gates or self._gates_explicit:
    return self._run_with_gates(...)
```

**Verification performed:**
- All 4 previously-failing `TestGateDrivenConvergence` tests now pass.
- `TestBackwardCompat::test_empty_gates_preserves_classifier_path` and
  `TestDefaultRegistry` (both testing the cases a naive `if gates:` fix
  would have broken) still pass.
- Full `test_compound_loop.py`: 21/21 pass (was 18/21).
- Ran every other test file constructing `PlaceRouteLoop()` with the
  plain default constructor (`test_loop.py`, `test_loop_termination_pbt.py`,
  `test_loop_field_feedback.py`, 37 tests total) -- all pass, confirming
  the production-default code path is unchanged.
- Diffed the full `placer/cp_sat/` test suite (346 tests) with and
  without this fix via `git stash`: byte-for-byte identical failure set
  (30 pre-existing, unrelated failures -- `test_gate.py`'s
  `AcceptanceGate.inner_gate()` API mismatch, `test_physics_gate.py`/
  `test_quality_gate.py`/`test_stackup_gate.py`'s own separate issues,
  `test_regression_drc.py`'s config↔netlist drift, etc.) both before and
  after -- confirms zero new regressions, exactly the 3 target tests
  fixed.

## Why This Matters

This bug meant `PlaceRouteLoop`'s documented, tested extension point
(pass a custom `gates=[...]` list to drive convergence off arbitrary
gate logic) silently didn't work unless the caller ALSO remembered to
pass `all_gates=True` -- at which point the custom gates would be
discarded anyway, since the `all_gates=True` branch always rebuilds its
own fixed 5-gate list, ignoring `self.gates` entirely. There was no
actual way to run the loop against a genuinely custom single- or
few-gate registry before this fix. It went undetected because the only
tests exercising this path were in a CI step (`CP-SAT Placer Tests`)
that had never once executed on this branch -- an earlier, unrelated,
always-failing DRC ratchet gate aborted the CI job before reaching it.
Fixing that unrelated gate (see the courtyard-investigation docs) is
what let CI reach this test file for the first time and surface the bug.

## Prevention

- **A constructor parameter's documented contract ("when non-empty,
  drives X") must be checked against the SAME state the contract
  describes at the point of use.** This bug arose because `run()`
  checked a different, unrelated flag (`all_gates`) instead of the
  `self.gates`/`gates` state the docstring/comment was actually
  describing.
- **Before "simplifying" a dispatch condition to match a stated
  intent, check for BOTH the empty-default and explicit-empty cases
  as separate test scenarios** -- `gates=None` (default, non-empty
  internally) and `gates=[]` (explicit, empty) look similar but must
  route identically here, while `gates=[custom]` must route
  differently. A truthiness check that only accounts for two of these
  three shapes breaks one of the existing, correct tests.
- **CI steps gated behind an earlier hard-fail step can hide arbitrarily
  large amounts of untested surface area indefinitely.** This bug and
  the DRC ratchet bug that hid it are two independent instances of the
  same underlying risk in this repo's CI configuration -- worth
  reviewing whether other steps in `.github/workflows/regression.yml`
  are similarly gated behind a step that can silently go stale.

## Related Issues

- [`docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)
  — the courtyard investigation whose DRC-ratchet-gate fix (a separate,
  unrelated bug) let CI reach this test file for the first time.
