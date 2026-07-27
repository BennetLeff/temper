# INVARIANT test suite parallel split — design data and verification

**Date:** 2026-07-27
**PR:** #361

## Why

`Core Tests`' "Run extended test suites in parallel" step backgrounded five
suites (BUNDLE, INVARIANT, CPSAT, WORKFLOW, CHECKS) inside one job with a
30-minute `timeout-minutes`. INVARIANT (`tests/router_v6/ tests/io/
tests/deterministic/ tests/physics/ tests/fields/ tests/validation/
tests/placer/cp_sat/`) used to collect near-zero tests — a `tests/losses/`
missing-directory bug aborted pytest collection for the whole invocation,
masked by `continue-on-error: true` (fixed in #354). Once it started
actually running, the job stopped finishing.

Direct measurement on `main` tip `dd8226da`: run 30305743267's `Core Tests`
job started 2026-07-27T21:46:19Z and was killed by the 30-minute timeout at
22:16:23Z. Last real progress line before it went silent:

```
tests/router_v6/test_copper_balance_boundary.py::test_layer_count_invariant_holds PASSED [21%]
```

21% complete after the full budget. Extrapolated linearly, a full run is
~2.5 hours. Because INVARIANT shared the job with everything else, the
timeout killed the whole job — none of the steps *after* "Run extended test
suites in parallel" ran either (board identity gate, vulture, MPN
fabrication gates, derived-document drift gate, capacity budget gate, ...).

## Per-directory test counts

Collected via `pytest --collect-only -q -m "not slow"` from
`packages/temper-placer`, 2026-07-27:

| Directory | Tests |
|---|---:|
| `tests/router_v6/` | 2,184 (2,171 selected after `not slow`) |
| `tests/io/` | 263 |
| `tests/deterministic/` | 315 |
| `tests/physics/` | 300 |
| `tests/fields/` | 43 |
| `tests/validation/` | 443 |
| `tests/placer/cp_sat/` | 381 |
| **Total** | **3,929** (3,916 selected) |

`tests/router_v6/` alone is ~56% of the whole suite, and has no natural
subdirectory split that captures most of its tests: `metrics/` and
`benchmarks/` together hold under 50 tests out of 2,171 — 99% of
router_v6's tests live directly in ~158 top-level test files.

## Split design

**router_v6** (2,171 tests, 158 files): greedy bin-pack by per-file
collected-test count into 3 groups (largest file first, assigned to
whichever group currently has the smallest running total). Result:

| Group | Tests | Files |
|---|---:|---:|
| 1 | 724 | 53 |
| 2 | 724 | 53 |
| 3 | 723 | 52 |

Balanced to within 1 test. Per-file counts (top 10 by size) that drove the
packing: `test_creepage_boundary.py` (123), `test_routability_check.py`
(121), `test_clearance_boundary.py` (112), `test_empty_data_edge_cases.py`
(96), `test_multilayer_edge_cases.py` (91), `test_acid_trap_boundary.py`
(82), `test_adapter.py` (70), `test_thermal_relief_boundary.py` (68),
`test_annular_ring_boundary.py` (66), `test_copper_balance_boundary.py`
(61). The exact assignment per group is recorded in the workflow file
itself (`invariant-router-v6-{1,2,3}` job definitions in
`.github/workflows/python-tests.yml`), not duplicated here, so this doc
can't drift from what's actually running.

**Everything else** (`invariant-rest`, 1,745 tests): kept as one job —
`tests/io/ tests/deterministic/ tests/physics/ tests/fields/
tests/validation/ tests/placer/cp_sat/`. Not split further: no
router_v6-scale single directory among these six, and this was not
observed to dominate the 21%-after-30-min measurement (the kill point was
inside router_v6).

Raw test-count balance is a proxy for wall-clock cost, not a proof of it —
`test_copper_balance_boundary.py` (61 tests) is exactly the kind of
property/boundary file that can be far more expensive per-test than its
count suggests (hypothesis-driven, many examples per nominal test), which
is why the real-run verification below matters more than the count table
above.

## `--min-tests` floors

Kept the anti-vacuous-truth guard on every split job, at floors
deliberately below the real per-job count (same intent as the original
combined 2500 floor: catch a catastrophic collection failure like the one
that motivated this whole investigation, not track routine churn):

- `invariant-router-v6-{1,2,3}`: `--min-tests 500` each (real ~724)
- `invariant-rest`: `--min-tests 1200` (real 1,745)

## Verification

_Filled in after PR #361's own CI run completes — see the run links below
once available. This PR is not intended to merge until every
`invariant-*` job is confirmed to finish well within its 20-minute budget
on a real run, not just "configured correctly."_
