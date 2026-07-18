---
title: "test_router_integration.py constructed CpSatPlacementResult with raw (N,2)/(N,) numpy arrays for positions/rotations, but the real fields are ref-keyed dicts; two tests also exercised a to_placement_result() method and a 'deterministic_fallback' ortools-unavailable status that never existed in the current design"
date: "2026-07-18"
category: test-failures
module: temper_placer
problem_type: test_failure
component: testing_framework
severity: medium
symptoms:
  - "KeyError: 'Q1' from to_placements_dict() -- the returned dict had numpy float keys instead of ref-string keys"
  - "AssertionError comparing {np.float32(10.0): np.float32(20.0), ...} to {'Q1': (10.0, 20.0), ...}"
  - "AttributeError: 'CpSatPlacementResult' object has no attribute 'to_placement_result'"
  - "AssertionError: assert 'optimal' == 'deterministic_fallback'"
root_cause: test_isolation
resolution_type: test_fix
tags:
  - temper-placer
  - cp-sat
  - test-drift
  - stale-test
  - hidden-by-ci
---

# `test_router_integration.py` assumed an array-based `CpSatPlacementResult` that no longer exists

## Problem

4 of 10 tests in `test_router_integration.py` failed. Two distinct
issues:

1. Several tests constructed `CpSatPlacementResult(positions=np.array([[10.0,
   20.0], [30.0, 40.0]], dtype=np.float32), rotations=np.array([0, 2],
   dtype=np.int32), placed_refs=["Q1", "Q2"], ...)` -- an index-aligned,
   array-based representation (a leftover from the deleted JAX-optimizer
   era, same root cause as
   [`placement-state-jnp-namerror-after-jax-removal.md`](../runtime-errors/placement-state-jnp-namerror-after-jax-removal.md)).
   The real `CpSatPlacementResult` dataclass declares
   `positions: dict[str, tuple[float, float]]` and
   `rotations: dict[str, int]` -- ref-keyed dicts, not parallel arrays.
   `to_placements_dict()`'s real implementation is `return
   dict(self.positions)` -- correct for a dict input, but calling
   `dict()` on a raw (N,2) numpy array iterates its rows and treats each
   `[x, y]` pair as a `(key, value)` tuple, producing exactly the
   observed `{np.float32(10.0): np.float32(20.0), ...}` garbage. The bug
   was entirely in the test's construction, not in `to_placements_dict()`
   itself.
2. `test_cp_sat_placement_result_to_placement_result` called
   `result.to_placement_result()`, a method that has never existed
   anywhere in `encoder.py` (grepped all of `src/` -- the only two
   mentions of the method name were both inside this test file). It
   appears to have been intended as a bridge to the older, array-based
   `placer.deterministic.PlacementResult` (still used by a few production
   callers for template-based placement, e.g. `heuristics/mcu_subsystem.py`),
   but was never implemented or was removed, with no production code
   ever needing the conversion.
3. `test_solve_placement_fallback_without_ortools` expected
   `solve_placement()` to return `status="deterministic_fallback"` when
   `ortools` is unavailable. The current `solve_placement()` does `from
   ortools.sat.python import cp_model` with no `try`/`except` at all --
   `ortools` is an unconditional, required dependency; `"deterministic_fallback"`
   never appears anywhere else in `encoder.py`. The test's own
   `mock.patch.dict("sys.modules", {"ortools": None})` also doesn't
   reliably block the import once `ortools.sat.python.cp_model` is
   already cached in `sys.modules` from an earlier test in the same
   process -- which is why the assertion failure showed a genuine
   `status="optimal"` result rather than an exception or a fallback: the
   mock had no effect, and the real solver ran normally.

## Resolution

- `test_cp_sat_placement_result_to_placements_dict` and
  `test_place_to_route_pipeline`: rewrote to construct `positions`/
  `rotations` as proper ref-keyed dicts, matching the real dataclass
  fields.
- `test_cp_sat_placement_result_to_placement_result`: removed. No
  production caller needs `to_placement_result()`; inventing a new
  bridge method with no clear spec is out of scope for a test-fix pass.
- `test_solve_placement_fallback_without_ortools`: removed. There is no
  `"deterministic_fallback"` path to test in the current architecture,
  and the test's own mocking mechanism doesn't reliably exercise an
  "ortools unavailable" scenario in this codebase's process/import
  structure anyway.

Both removals are commented in place explaining why, per this session's
established pattern of not silently deleting evidence a test once
existed.

**Verification:** `test_router_integration.py`: 8/8 pass (was 6/10,
now 8 real tests after removing 2 that tested nonexistent
functionality).

## Why This Matters

This is the third instance in this batch of the same underlying cause:
remnants of the deleted JAX-array-based placement design colliding with
the current CP-SAT dict-based design (see also
[`placement-state-jnp-namerror-after-jax-removal.md`](../runtime-errors/placement-state-jnp-namerror-after-jax-removal.md)).
Each instance was invisible until CI reached the "CP-SAT Placer Tests"
step for the first time (see
[`courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](../logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)).

## Prevention

- **When a dataclass field's type annotation changes shape (array →
  dict, or vice versa), grep every test constructing that dataclass
  directly** -- type checkers won't catch a test passing a numpy array
  where a dict is now expected if the field itself is duck-typed enough
  to accept it without immediate error (as happened here: `dict(array)`
  doesn't raise, it just silently produces nonsense).
- **`mock.patch.dict("sys.modules", {"pkg": None})` to simulate an
  unavailable package only works reliably if the package's submodules
  haven't already been imported and cached elsewhere in the same test
  process** -- for a package imported early and often (like `ortools`
  here), this technique is fragile and can silently do nothing.

## Related Issues

- [`docs/solutions/runtime-errors/placement-state-jnp-namerror-after-jax-removal.md`](../runtime-errors/placement-state-jnp-namerror-after-jax-removal.md)
  — sibling JAX-era leftover bug from the same investigation batch.
- [`docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](../logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)
  — the DRC ratchet gate fix that unblocked CI far enough to run this
  test file for the first time.
