---
title: "U6 deterministic-suite 'regressions' were a stale-base re-solve: upstream #1136/#1137/#1149 had already fixed them; only harness artifacts remained"
date: "2026-08-14"
category: test-failures
module: temper_orchestration
problem_type: test_failure
component: deterministic_validation
severity: low
---

## What happened

A session dispatched against the U6 owned-marshal integration was given a
worktree cut from `849c0ce63` (13 commits behind `origin/main`) and reported a
~36-failure deterministic-suite baseline as "the real bugs behind U6". It then
spent significant effort re-solving them: lenient `frozenset_read`/`Route`/
`Via` marshallers in `temper-orchestration`, `(f64, f64)` int-coord
normalization, and completion of the d6 `_DrvViolation`/`_LayerAssignment`
test fakes.

All of it was already landed upstream, between the worktree base and
`origin/main`:

- `41cc7957b` (#1136): stale O-C3 fixtures + the routes/vias non-Trace/Via
  marshalling gap — the Via-in-routes pass-through and the d6 fake fields.
- `d351d71b9` (#1137): canonical repr-order tie-break for Trace/Via dedup
  "first wins" — the dedup index tests.
- `fe6094806` (#1149): d6_stages_runner flake + MR1/MR3 hypothesis bugs in
  temper-design-bundle.

## Verification

On a fresh `origin/main` worktree with **all 10 pyo3/maturin extensions
rebuilt** (`make extensions`; a stale `.so` in the venv made the
`Component.initial_rotation_quadrant` rename (d8d772961) and the short-circuit
stage appear broken — `scripts/check_stale_extensions.py` before believing a
number):

```
tests/deterministic: 1551 passed, 3 failed, 1 skipped
```

The 3 failures are `test_hash_order_determinism.py` child-interpreter tests,
which pass 13/13 in the provisioned shared venv
(`/home/bennet/Desktop/temper/.venv`) with proper activation — a worktree-venv
child-`python` resolution artifact, not a regression.

## Why this matters

The session's lenient marshaller changes were deliberately **not** landed:
upstream chose to conform the fixtures/code to the strict owned marshal
instead, and the tests pass on `origin/main` byte-for-byte without them.
Landing the lenient alternative would have diverged the codebase from an
already-merged design decision.

This is the same failure mode `scripts/assert-base.sh` exists to catch
(AGENTS.md "Base-Commit Assertion"): measure/verify against the actual
dispatched base before treating a red suite as a real regression. The
recovery cost here was an avoided merge of redundant code — the cheap version
of that incident's `docs/evidence/2026-07-26-measurement-provenance.md` cost.
