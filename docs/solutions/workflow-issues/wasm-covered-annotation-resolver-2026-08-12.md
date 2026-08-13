---
title: "wasm-covered annotation resolver — gating Python PBT reduction on the wasm registry at the commit"
date: "2026-08-12"
category: workflow-issues
module: ci-python-tests
problem_type: workflow_issue
component: development_workflow
severity: high
applies_when:
  - "a Python hypothesis property suite is mirrored by the wasm tier and someone wants to reduce/skip the Python run to save CI time"
  - "any future offload must not be keyed off the deployed Workers' census (the advisory arm) — only the registry at the current commit"
  - "a pytest_guard floor counts executed tests, so a marker skip would silently break the floor"
symptoms:
  - "The spike (docs/evidence/2026-08-12-ci-offload-to-wasm-tier-spike.md) showed the timing T1-T4 compare_stage cluster is the only Python PBT group already wasm-mirrored (203 registered timing tests; p7-p10 x 20 seeds + compare_stage_guards_zero_baseline), but there was no mechanism to reduce the Python run without risking a stale Worker silently skipping CI coverage"
  - "A naive skip/deselect of the four T1-T4 tests drops the timing step's executed count from 63 to 59, failing its own pytest_guard --min-tests 63 floor (pytest_guard counts executed, non-skipped tests from JUnit XML)"
root_cause: missing_validation
resolution_type: tooling_addition
tags:
  - wasm-tier
  - ci-offload
  - pytest-guard
  - fail-closed
  - annotation-resolver
  - registry-at-commit
  - timing-cluster
---

# `wasm-covered` annotation resolver

The first CI offload from
`docs/evidence/2026-08-12-ci-offload-to-wasm-tier-spike.md` follow-up (1):
a mechanism that lets a workflow step declare "these Python properties are
covered by the wasm tier" and have that declaration **verified against the
registry at the current commit** — never the deployed Workers' census — and
**fail closed**: if the mirror disappears, the Python tests run at full
strength, not silently skipped.

## The mechanism

- **`scripts/check_wasm_covered.py`** (dual role, one file):

  1. **CLI resolver** (`--cluster timing`): computes the test-fn names the
     registry generator would register for the cluster's crate module at
     THIS commit — using `gen_wasm_test_registry.py`'s own collection
     machinery, so it can never disagree with the fast-gates `--check`
     drift gate or the nightly `local-sweep-r19` build. Exit 0 = every
     claimed mirror is registered AND every Python test the annotation
     would reduce still exists (bidirectional — a renamed Python test
     fails resolution too). Exit 1 = stale annotation, naming the missing
     entries.

  2. **Pytest plugin** (`-p check_wasm_covered`, importable because the
     step prepends `$GITHUB_WORKSPACE/scripts` to `PYTHONPATH`): when the
     env var `WASM_COVERED_<CLUSTER>` is set, drops the cluster's
     hypothesis properties to a token `max_examples=5` via the
     `_hypothesis_internal_use_settings` attribute the hypothesis pytest
     plugin reads at runtest time (verified: hypothesis reports "Stopped
     because settings.max_examples=5"). When the env var is unset the
     plugin does nothing — the full-strength suite runs.

- **Workflow wiring** (`.github/workflows/python-tests.yml`, "Run Phase-5
  cli differentials" step): the step's `run:` block calls the resolver in
  an `if`. On success it exports `WASM_COVERED_TIMING=1`; on failure it
  prints a `::warning::` and leaves the env var unset. Either way the same
  `pytest_guard.py --min-tests 63` invocation runs — the only difference
  is how many examples the four T1-T4 properties draw (5 vs 120).

## Why token examples and not a skip/deselect

`pytest_guard.py` counts **executed** tests from JUnit XML
(`tests - skipped`). The timing step collects exactly 63 tests and its
floor is 63; removing the four T1-T4 properties by skip or `--deselect`
drops the executed count to 59 and fails the guard. Running them at 5
examples keeps all 63 tests executing (floor preserved, both branches)
while moving the coverage authority to the wasm tier. `p95` (T5/T7 —
CPython `decimal`, structurally unmirrorable), the MT/MP relations and
`trace_commands` are not in the annotation and keep their full 120
examples; the two differential files remain the bit-exact retained
oracles regardless.

## Fail-closed proof (as tested)

- Delete/rename `compare_stage_guards_zero_baseline` or any of the 80
  `p7..p10_*_seed_*` fns → resolver exits 1 → no `WASM_COVERED_TIMING` →
  plugin reduces nothing → all 63 tests run at full strength in the same
  CI step, with a `::warning::` in the log. Coverage reverts to the
  Python suite; it never silently shrinks.
- Exact-name semantics: the resolver enumerates the claimed registry names
  (`p7_..._seed_000` .. `_019`, and the exact unit-test name) rather than
  prefix-matching, so a renamed `..._seed_000_DELETED` does not satisfy a
  claim on `..._seed_000`.

## How a future mirror plugs in

When a future campaign lands (the spike's highest-value targets: the 36 s
validation DRC PBTs and the 33 s Wave-4 round-2 PBTs, once R1c property
campaigns exist):

1. Add a `Cluster` entry to `CLUSTERS` in `scripts/check_wasm_covered.py`
   naming the crate/module, the Python test fns to reduce, and the exact
   mirror names the annotation claims (enumerate seed campaigns as
   `prefix` + seed count).
2. In the target workflow step, add the `wasm-covered:` comment block, wrap
   the step's `run:` in the same `if resolver; then export
   WASM_COVERED_<CLUSTER>=1; else ::warning::; fi` pattern, and add
   `-p check_wasm_covered`.
3. Keep the step's `--min-tests` floor unchanged — token examples preserve
   the executed count by construction; if the step's floor is ever below
   the post-reduction count, the reduction is too aggressive, not the
   floor.

The deployed Workers' census is never the gate: registry-at-commit
(fast-gates `--check`) is the authority, and the nightly local sweep
builds from the same commit.
