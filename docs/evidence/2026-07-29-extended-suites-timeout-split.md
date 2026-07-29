# Extended Test Suites timeout split — diagnosis and fix

<!-- provenance: commit=UNKNOWN dirty=UNKNOWN -->

**Date:** 2026-07-29

## Why

`.github/workflows/python-tests.yml`'s `extended-suites` job (name:
"Extended Test Suites (bundle / cp-sat / workflow / checks)",
`timeout-minutes: 25`) backgrounded four suites — BUNDLE (cargo test for
`temper-design-bundle`), CPSAT (`tests/placer/cp_sat/` +
`tests/metrics/test_external_oracle.py` + `tests/cli/test_cp_sat_flag.py`),
WORKFLOW (`packages/temper-workflow/tests/`), CHECKS
(`tools/check_kicad_layers.py` + `tests/io/test_4layer_output_properties.py`
+ transition-table drift check) — as four `&`-backgrounded processes inside
one bash step on one container, then `wait`ed on all four.

Measured on the same commit:

| Run | Wall-clock | Outcome |
|---|---:|---|
| main, run 30429718944 | 18m05s | success (every test passed) |
| PR re-run, commit N | 25m03s | **killed by `timeout-minutes: 25`** |
| PR re-run, same commit N, retry | 24m31s | success (29s of headroom) |

The 25m03s run's log showed every test that had a chance to run had
PASSED — GitHub surfaces a `timeout-minutes` expiry as
`##[error]The operation was canceled`, which reads exactly like a generic
test failure in the checks UI. That run cost a full CI cycle to disprove
as a real regression.

## Where the time actually goes

Pulled the full step log for the 18m05s run (`gh run view <job-id> --log`)
and diffed adjacent line timestamps. Because `pytest -v` only prints a
test's result line once that test *finishes*, the gap between two
consecutive result lines is (approximately) the duration of the test whose
line comes second.

Three gaps dominate everything else in the log by more than an order of
magnitude:

| Test | Gap (≈ duration) |
|---|---:|
| `tests/placer/cp_sat/test_hybrid_pour_stitch_measurement.py::TestHybridPourStitchVerification::test_hybrid_pour_reduces_unconnected_without_shorting_regression` | 665s (11m05s) |
| `tests/placer/cp_sat/test_zone_pour_production_measurement.py::TestZonePourProductionMeasurement::test_zone_pours_reduce_unconnected_items` | 163s (2m43s) |
| `tests/placer/cp_sat/test_regression_drc.py::test_production_board_routing_drc_regression` | 74s (1m14s) |

That's 902s (15m02s) of the CPSAT pytest invocation's own ~15m20s span
(07:04:42 -> 07:20:02 in that run), inside an 18m05s job. Every other test
in BUNDLE/CPSAT/WORKFLOW/CHECKS combined — well over a thousand tests —
finished in a few seconds total. All three slow tests invoke `kicad-cli`
for DRC sampling ("median of 3 DRC samples each" per their own docstrings/
assertions), so their wall-clock is sensitive to whatever else is
contending for CPU on the runner at the time — including the other three
suites this job used to background alongside them on the same container.
That shared contention, not a defect in any test, is the most likely
explanation for the same commit going from 18m05s to a 25m03s timeout kill
between re-runs: CPSAT's own runtime is dominated by wall-clock-sensitive
subprocess calls, and it was never running alone.

## Fix chosen: split the job, not raise the timeout

Per repo convention (this file already has 8 gate jobs split out of a
single former "Core Tests" job — `rust-checks`, `board-gates`,
`consistency-gates`, `provenance-gates`, `hygiene-gates`,
`requirements-tests`, plus the four `invariant-*` jobs split out of
`extended-suites` on 2026-07-27), `extended-suites` is split into two jobs:

- **`extended-bundle-workflow-checks`** — BUNDLE + WORKFLOW + CHECKS,
  still backgrounded against each other exactly as before (their combined
  cost is under a minute, so that contention was never the problem).
  `timeout-minutes: 15`.
- **`extended-cpsat`** — CPSAT alone, on its own runner.
  `timeout-minutes: 25` (unchanged from the old combined job — this suite
  alone already consumed nearly all of that budget, and it no longer has
  to share it with anything).

Both jobs duplicate the full setup block (uv/maturin/Rust crate builds,
`uv sync`, netlist build) exactly as every other split-out job in this file
already does, and both keep the `Setup barrier -- environment ready` /
`if: !cancelled() && steps.setup.outcome == 'success'` gate-independence
convention. No `needs:` relationship existed between `extended-suites` and
any other job (checked: no `needs:` keyword anywhere in this workflow, and
`extended-suites` was not referenced by name in `.github/` outside this
file's own comments), so the split introduces no new sequencing.

`continue-on-error: true` is preserved on both new jobs' test steps,
identical to the single combined step's existing
`# TODO: temper-NNN -- parallel test suite flakiness; hard-fail after
2026-09-01` annotation. This is not a new weakening — it is the same
annotation carried forward unchanged onto the two steps it used to cover
as one.

This repo has no branch-protection required-status-checks configured on
`main` (`gh api repos/.../branches/main/protection` → 404 "Branch not
protected"), so renaming the job/check has no required-check implications.

## Why not xdist, why not just raise the timeout

- **`-n auto --dist loadgroup`**: would not help. The dominant cost is
  three tests that call an external DRC tool synchronously; xdist
  parallelizes *other* tests around them but the wall-clock floor is still
  set by whichever worker draws the slowest of the three (and `tests/
  placer/cp_sat/` already runs inside a job that isn't CPU-bound by test
  *count* — it's bound by three tests' external-process time). It also
  doesn't address the actual mechanism of the bimodality: CPU contention
  between this job's own backgrounded suites has nothing to do with xdist.
- **Raising `timeout-minutes` alone**: rejected per the task's own
  instruction and this repo's established pattern (see the `test` job's
  history of 15 -> 30 -> 45 -> 35 timeout churn in the comments above
  it) — it hides the bimodality instead of removing its cause, and the
  job would eventually drift back into its own limit exactly as it did
  before. `extended-cpsat` keeps the same 25-minute number it already had,
  now with headroom instead of contention.

## Verification

- `python3 -c "import yaml; yaml.safe_load(...)"` — YAML parses.
- `SHELLCHECK_OPTS='--severity=error' actionlint -ignore 'constant
  expression "false" in condition'` — clean, no findings.
- Diffed the `run:` command strings for all four suites between the old
  combined step and the two new jobs: byte-identical test selections and
  flags (`tests/placer/cp_sat/ tests/metrics/test_external_oracle.py
  tests/cli/test_cp_sat_flag.py -v --tb=short -p no:cacheprovider
  --maxfail=10` for CPSAT; unchanged commands for BUNDLE/WORKFLOW/CHECKS).
  No test was added, removed, or deselected.
- CI (post-PR): see PR for the two new jobs' actual wall-clock against the
  historical combined-job numbers above.
