---
title: Production routing DRC must measure a clean reroute with fresh extensions
date: 2026-08-30
category: test-failures
module: temper-placer production routing regression
problem_type: test_failure
component: testing_framework
symptoms:
  - "CI reported 52 shorting items while repeated local measurements reported 24"
  - "The production regression routed a board that already contained committed copper"
root_cause: incomplete_setup
resolution_type: test_fix
severity: high
tags: [drc, routing, pyo3, measurement, kicad]
---

# Production routing DRC must measure a clean reroute with fresh extensions

## Problem

The production routing regression reported a deterministic increase from 26 to
52 `shorting_items`, apparently implicating a polygon-hole marshalling fix. The
result was not measuring the same artifact as the pinned baseline: the test fed
the already-routed production board back into the router, and its CI setup did
not rebuild every discovered pyo3 extension.

## Symptoms

- Five CI DRC samples all reported 52 shorts, so the failure looked deterministic rather than flaky.
- A correctly configured three-run comparison produced byte-identical routes and identical normalized violation sets before and after the routing fix.
- The clean reroute measured 24 shorts, below the pinned ratchet of 26.

## What Didn't Work

- Raising the ratchet would have hidden an invalid measurement and weakened a mains-safety gate.
- Comparing only category counts could not show whether routing behavior changed.
- Rebuilding a hard-coded subset of extension crates could leave dependent `.so` files stale while imports still succeeded.

## Solution

PR #1538 aligned the regression with the production routing command:

1. Create a temporary routing input with existing segments, vias, and zones removed through the shared `temper_io_types.strip_existing_copper` implementation.
2. Route and measure that clean input, matching `scripts/route_board.py`.
3. Build every discovered extension with `env -u CONDA_PREFIX make extensions`.
4. Run `make extensions-check` immediately before the measurement.
5. Compare normalized DRC violation sets, including net-order normalization, before attributing a count change to routing logic.

The load-bearing implementation is in
`packages/temper-placer/tests/placer/cp_sat/test_regression_drc.py`; the CI
freshness setup is in `.github/workflows/regression.yml`.

## Why This Works

A differential is meaningful only when both sides receive the same production
input and execute the committed native code. Removing committed copper prevents
the router from appending a second route onto an existing one. Rebuilding and
checking all pyo3 crates prevents Python from silently exercising an older Rust
kernel. Violation-set comparison then distinguishes a real geometry change from
a count produced by a different artifact.

## Prevention

- Share input preparation between production commands and their regression tests.
- Treat extension freshness as part of measurement setup, not a separate build concern.
- Record the routed artifact identity and compare normalized violation sets before changing a DRC ratchet.

## Related Issues

- PR #1538
- `docs/evidence/2026-08-18-pad-core-polygon-rotation-convention.md`
- `docs/evidence/2026-08-19-measurement-instruments-that-lie.md`
