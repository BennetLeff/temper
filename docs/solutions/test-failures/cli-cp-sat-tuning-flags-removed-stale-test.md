---
title: "test_cp_sat_flag.py asserted --cp-sat-timeout/-workers/-grid-scale exist on `optimize`, but all three were removed from the CLI with no underlying solver support left for two of them"
date: "2026-07-18"
category: test-failures
module: temper_placer
problem_type: test_failure
component: testing_framework
severity: medium
symptoms:
  - "test_cp_sat_options_exist, test_cp_sat_timeout_default_value, test_cp_sat_workers_default_value all failed: AssertionError, '--cp-sat-timeout option not found' / '--cp-sat-workers option not found'"
  - "grep for cp_sat_timeout/cp_sat_workers/cp_sat_grid_scale across cli/__init__.py returns zero matches -- the flags do not exist anywhere in the current CLI"
root_cause: test_isolation
resolution_type: test_fix
tags:
  - temper-placer
  - cli
  - cp-sat
  - stale-test
  - hidden-by-ci
---

# CP-SAT tuning CLI flags removed from `optimize`; tests never updated

## Problem

`test_cp_sat_flag.py` had three tests asserting `--cp-sat-timeout`,
`--cp-sat-workers`, and `--cp-sat-grid-scale` appear in `temper-placer
optimize --help`. All three failed: none of these flags exist in the
current CLI at all.

## Investigation

These flags were added in `2f3d4601` ("add CP-SAT feasibility-first
placer (U0-U8)"), wired through to a `solve_placement()` call that
accepted `timeout_ms`, `workers`, and `grid_scale` parameters. The
current `optimize()` command's `solve_placement()` call site
(`cli/__init__.py:631`) passes only `netlist`, `board`,
`extra_constraints`, `seed`, `hint_positions` -- no timeout, no workers,
no grid scale. The current `solve_placement()` signature
(`placer/cp_sat/encoder.py:936`) still accepts `timeout_ms` (defaulting
to a hardcoded 1000ms, unconfigurable from the CLI), but has **no
`workers` or `grid_scale` parameter at all** -- there is nothing left to
wire `--cp-sat-workers`/`--cp-sat-grid-scale` to even if the flags were
restored.

A later test-maintenance commit (`1cacf238`, "update CLI test assertions
for JAX retirement") touched adjacent tests in the same file but left
these three untouched -- they were already stale by that point and went
unnoticed, same root cause as every other finding in this batch: the CI
step that runs this test file (`CP-SAT Placer Tests`) had never executed
to completion on this branch, blocked by an unrelated, earlier hard
failure (see
[`courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](../logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)).

## Resolution

Not a code regression to fix -- the flags were deliberately dropped and
two of the three have no underlying capability left to restore without
inventing new solver-tuning functionality (out of scope for a test-fix
pass). Updated the tests to assert the current, real state:

- Replaced `test_cp_sat_options_exist` with
  `test_cp_sat_tuning_flags_not_currently_exposed`, asserting all three
  flags are **absent** (not present), with a comment explaining why and
  pointing here, plus an explicit note to convert it back to a positive
  existence check rather than deleting it if the flags are ever
  intentionally restored.
- Removed `test_cp_sat_timeout_default_value` and
  `test_cp_sat_workers_default_value` as fully redundant with the new
  consolidated absence check.

**Verification:** `test_cp_sat_flag.py`: 6/6 pass (was 3/6).

## Why This Matters

`--cp-sat-timeout` in particular represents a real, currently-missing
capability: `solve_placement()` already supports a configurable
`timeout_ms`, but the CLI hardcodes it to the function's 1000ms default
with no way for a user to override it for a larger/harder board that
needs more solve time. This doc flags that gap explicitly rather than
silently deleting all evidence it was ever considered -- restoring just
`--cp-sat-timeout` (wiring an existing, real parameter through) would be
a small, well-scoped follow-up if wanted; `--cp-sat-workers` and
`--cp-sat-grid-scale` would need new solver-side work first.

## Prevention

- **When a CLI test asserts an option exists, and that assertion starts
  failing, check the option's underlying implementation before deciding
  whether to fix the CLI or fix the test** -- `git log -S` on the exact
  option string across the CLI file quickly shows whether it was ever
  wired to anything real, and whether the removal was deliberate
  (accompanying a larger refactor) or accidental.
- Consistent with the rest of this batch: **CI steps gated behind an
  earlier hard-fail step hide arbitrarily large amounts of test drift**
  -- these tests had presumably been broken since whichever refactor
  removed the flags, invisible in CI the entire time.

## Related Issues

- [`docs/solutions/logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md`](../logic-errors/courtyard-check-stage-finds-zero-collisions-real-drc-finds-43.md)
  — the DRC ratchet gate fix that unblocked CI far enough to run this
  test file for the first time.
