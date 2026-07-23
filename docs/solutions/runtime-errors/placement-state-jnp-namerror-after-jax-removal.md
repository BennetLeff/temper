---
title: "PlacementState.from_positions_dict() raised NameError: name 'jnp' is not defined -- a leftover JAX reference after the JAX gradient-descent optimizer was deleted"
date: "2026-07-18"
category: runtime-errors
module: temper_placer
problem_type: runtime_error
component: service_object
severity: high
symptoms:
  - "NameError: name 'jnp' is not defined, raised from core/state.py:129 inside PlacementState.from_positions_dict()"
  - "4/8 tests in test_external_oracle.py failed with this error; score_placement() and anything else constructing a PlacementState from a plain positions dict was completely broken"
root_cause: config_error
resolution_type: code_fix
tags:
  - temper-placer
  - jax-removal
  - placement-state
  - hidden-by-ci
---

# `PlacementState.from_positions_dict()` raised `NameError: name 'jnp' is not defined`

## Problem

`core/state.py`'s `PlacementState.from_positions_dict()` called
`jnp.array(...)` and `jnp.zeros(...)` (JAX's `jax.numpy` module,
conventionally aliased `jnp`), but the file only imports plain `numpy as
np` -- `jnp` was never imported anywhere in the module. Any call to this
factory (used by `score_placement()` in `metrics/external_oracle.py`)
raised `NameError` immediately.

Found while working through a backlog of CI test failures newly exposed
after fixing two unrelated CI-blocking bugs (see
[`courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](../logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)
and
[`place-route-loop-run-ignores-constructor-gates-without-all-gates-flag.md`](../logic-errors/place-route-loop-run-ignores-constructor-gates-without-all-gates-flag.md)):
the "CP-SAT Placer Tests" CI step had never run to completion on this
branch before, so this bug (and ~30 others in the same batch) had never
been observed in CI.

## Root Cause

The `PlacementState.positions` field is typed `NDArray` (from
`numpy.typing`), and the class's docstring at the time said "This factory
wraps numpy/Python data into JAX arrays internally" -- a direct
contradiction between the declared numpy type and the JAX-array
construction code. This is a leftover from before the JAX
gradient-descent placement optimizer was removed from the codebase (per
`power_pcb_dataset/baselines/temper_production_baseline.yaml`'s header:
"Extraction method changed from JAX gradient-descent (deleted 2026-07) to
CP-SAT"). `jax` (version 0.10.2) happens to still be installed in this
environment as a leftover dependency, but it was removed from
`pyproject.toml` and no longer imported anywhere in this file --
`from_positions_dict` was the one function left calling `jnp.*` without
ever importing it.

## Resolution

Replaced `jnp.array`/`jnp.float32`/`jnp.zeros` with `np.array`/
`np.float32`/`np.zeros` (numpy is already imported in this file, and the
field's own type annotation already declared `NDArray`, not a JAX array
type). Corrected the docstring's "wraps ... into JAX arrays" claim to
say numpy arrays.

**Verification:** all 8 tests in `test_external_oracle.py` pass (4 were
failing). Ran the broader set of tests touching `PlacementState`
(`test_state.py`, all of `tests/metrics/`, `test_validation.py`,
`test_scorecard.py`, 79 tests) -- all pass, no regressions.

## Why This Matters

This function is a public factory (`PlacementState.from_positions_dict`)
whose entire purpose, per its own docstring, is letting callers construct
placement state "without needing to import JAX" -- but it crashed on
every single call because of exactly the JAX dependency it claimed to
avoid. Any code path calling `score_placement()` or otherwise using this
factory was completely broken.

## Prevention

- **When removing a framework/library from a codebase (here: JAX), grep
  for every remaining reference to its conventional import alias (`jnp`,
  `jax`, etc.), not just its `import` statements** -- removing `import
  jax.numpy as jnp` without removing/replacing every `jnp.*` call site
  leaves a `NameError` landmine that only fires the first time the
  affected function is actually called, not at import/collection time.
- Related to this investigation's broader theme: **a CI step that never
  runs (blocked by an earlier, unrelated hard failure) can hide an
  arbitrarily large amount of broken code indefinitely** -- this bug had
  presumably existed since whenever the JAX optimizer was deleted, with
  no test ever catching it in CI.

## Related Issues

- [`docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](../logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)
  — the DRC ratchet gate fix that unblocked CI far enough to run the test
  step that caught this bug for the first time.
