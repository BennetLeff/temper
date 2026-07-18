---
title: "njit fallback shim in clearance_grid.py silently discards the decorated function for bare @njit usage, crashing with a confusing arity TypeError"
date: "2026-07-17"
category: logic-errors
module: temper_placer
problem_type: logic_error
component: service_object
severity: high
symptoms:
  - "TypeError: njit.<locals>.<lambda>() takes 1 positional argument but 10 were given, raised from clearance_grid.py's ClearanceGrid.block_circle() when calling _block_circle_numba(...)"
  - "Same failure mode for _block_segment_numba (arity mismatch: 'takes 1 positional argument but 12 were given')"
  - "Failure only occurs when numba fails to import (e.g. `ImportError: Numba needs NumPy 2.4 or less. Got NumPy 2.5.` in an environment with a newer NumPy) -- the deterministic pipeline works fine whenever numba imports successfully, making this look environment-specific and confusing rather than a codebase bug"
root_cause: logic_error
resolution_type: code_fix
tags:
  - temper-placer
  - numba
  - clearance-grid
  - deterministic-pipeline
  - dependency-fallback
  - decorator
---

# njit fallback shim discards the decorated function for bare `@njit` usage

## Problem

`clearance_grid.py` imports `njit` from `numba` for two performance-critical
inner loops (`_block_circle_numba`, `_block_segment_numba`), with a fallback
no-op decorator for environments where numba is unavailable:

```python
try:
    from numba import njit
except ImportError:
    def njit(*args, **kwargs):
        """No-op decorator when numba is unavailable."""
        return lambda f: f
```

Both real usages in this file are the bare decorator form:

```python
@njit
def _block_circle_numba(target_grid, cx, cy, total_radius, net_id, cell_size_mm, min_row, max_row, min_col, max_col):
    ...
```

Discovered while re-running the full deterministic pipeline end-to-end
(`pcb/temper.kicad_pcb` → `create_drc_aware_pipeline` → export → kicad-cli
DRC) to verify a courtyard-geometry fix (see
`docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`).
In this environment, `from numba import numba` raises
`ImportError: Numba needs NumPy 2.4 or less. Got NumPy 2.5.`, so the
fallback shim is exercised, and the pipeline crashed mid-run at the
`clearance_grid` stage:

```
TypeError: njit.<locals>.<lambda>() takes 1 positional argument but 10 were given
```

## Root Cause

The fallback shim is only correct for the `@njit(...)` call-with-options
style, where Python evaluates `njit(...)` first (returning a decorator),
then applies that decorator to the function. For the **bare** `@njit`
style, Python instead calls `njit(func)` directly, passing the real
function as the sole positional argument. The shim's
`def njit(*args, **kwargs): return lambda f: f` ignores `args` entirely in
both cases -- for bare usage this means the actual function
(`_block_circle_numba`) is silently discarded and replaced with a generic
1-argument identity lambda. The name `_block_circle_numba` in the module
now refers to a broken stand-in; the real 10-argument function it was
meant to wrap is gone. Any call to it crashes with an arity `TypeError`
that gives no hint the underlying cause is "numba failed to import" --
the confusing part being `njit.<locals>.<lambda>() takes 1 positional
argument` looks like a totally unrelated bug in the numba library itself
until traced back to the shim.

## What Was Ruled Out

- **Not a numba version/compatibility bug per se.** The `ImportError`
  (NumPy 2.5 vs. numba's `<=2.4` requirement) is a real, separate
  environment mismatch, but it is expected and handled behavior -- the
  `try/except ImportError` exists specifically to degrade gracefully when
  numba is unavailable. The bug is that the degradation itself is broken
  for one of the two decorator call styles it needs to support.
- **Not specific to `_block_circle_numba`.** `_block_segment_numba` (also
  bare `@njit`) fails identically, confirming this is a shim-level defect,
  not something specific to one function's signature.
- **The equivalent shim in `router_v6/astar_core_numba.py` is NOT
  affected** -- checked directly. That file only ever uses the
  call-with-options form (`@njit(cache=True, fastmath=False)`), which the
  broken shim already handled correctly (`njit(cache=True, fastmath=False)`
  legitimately returns `lambda f: f` as a decorator, and that decorator is
  then correctly applied to the real function next). The bug is isolated
  to `clearance_grid.py`'s two bare-`@njit` call sites.

## Resolution

Fixed the shim to detect the bare-decorator call and return the function
unchanged, instead of always returning a fresh identity lambda:

```python
def njit(*args, **kwargs):
    """No-op decorator when numba is unavailable."""
    if len(args) == 1 and callable(args[0]) and not kwargs:
        return args[0]
    return lambda f: f
```

Added `test_clearance_grid_njit_fallback.py` (2 tests) calling
`_block_circle_numba` and `_block_segment_numba` directly with real
arguments and asserting they execute and mutate the grid correctly.
Verified as a genuine regression guard: temporarily reverted just the
fixed line and re-ran -- both tests failed with the exact original error
message (`takes 1 positional argument but 10/12 were given`), then passed
again after restoring the fix.

With this fix, the same full pipeline run (that originally crashed at
this stage) completed end-to-end and produced a real kicad-cli DRC
comparison.

## Why This Matters

This bug was a **silent no-op until called**, not a load-time failure --
`clearance_grid.py` imports successfully and the module loads fine even
with numba unavailable; the crash only surfaces the first time
`block_circle` (or the segment equivalent) actually runs, deep into a
pipeline stage, with an error message that points at a lambda inside
`njit`'s local scope rather than anything mentioning numba or the
decorator pattern. Anyone hitting this without knowing to check "is numba
importable in this environment" would have a hard time connecting the
dots. It also fully blocked end-to-end verification of an unrelated fix
(the courtyard geometry extraction bug) until diagnosed and fixed.

## Prevention

- **A fallback shim for a decorator library must handle every calling
  convention the real decorator supports**, not just the one that happens
  to be exercised in whichever code path was tested first. `numba.njit`
  supports both bare (`@njit`) and parameterized (`@njit(...)`) usage;
  a fallback standing in for it must too.
- **When auditing a "no-op fallback" pattern for correctness, grep every
  call site of the decorator it's replacing** and check each one's exact
  syntax (bare vs. parenthesized) against the fallback's logic -- do not
  assume all call sites in a codebase use the same style. This file had
  both styles present across its two fallback-shim copies
  (`clearance_grid.py` bare-only, `astar_core_numba.py`
  parameterized-only), and only one of the two was actually broken.
- **A `TypeError` about a `lambda` deep in a stack trace, with an arity
  mismatch far from where the call was made, is a strong signal to check
  for exactly this class of bug** -- a decorator fallback/shim silently
  replacing a real function.

## Related Issues

- [`docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)
  — the investigation this bug was discovered blocking; that doc's
  end-to-end verification run is what first hit this crash.
- `packages/temper-placer/tests/deterministic/stages/test_clearance_grid_njit_fallback.py`
  — regression test file added alongside the fix.
