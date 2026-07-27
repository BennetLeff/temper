---
title: "fix: Test Skip Accounting"
type: fix
status: active
date: 2026-07-25
---

## Goal

The test suite has 228 measured skip sites and nobody knows how many of the
resulting test functions ever execute. Per `METHODOLOGY.md` §4 a skip is
class 6 (silently skipped) — indistinguishable from a failed check unless
accounted for. This plan measures what runs, categorizes what doesn't, and
sets a mechanical gate so the count can't go silently invisible again.

## Measured state

`.venv`, `.worktrees/`, `worktrees/` excluded throughout (git-ignored,
contain duplicate checkouts).

| Metric | Value | Command |
|---|---|---|
| Test files (`test_*.py`/`*_test.py`) | 482 | `find . -name "test_*.py" -o -name "*_test.py" \| grep -v -E '\.venv\|\.worktrees'` |
| `def test_*` functions (grep) | 5,585 | `grep -rn '^\s*def test_' --include='*.py' .` |
| LOC in test files | 126,765 | `wc -l` over the file list above |
| Collected items, `temper-placer` only | **6,311**, 5 collection errors | `cd packages/temper-placer && uv run pytest --collect-only -q` |
| Deselected by `-m "not slow"` | 163 of 6,311 | same, `-m "not slow"` |
| Skip sites | **228** (`pytest.skip`: 141, `skipif`: 76, unconditional: 11) | `grep -rn -E 'pytest\.skip\(\|@pytest\.mark\.skipif\|@pytest\.mark\.skip\(' --include='*.py' .` |
| `xfail` occurrences / files | 40 / 13 | `grep -rn xfail --include='*.py' .` |

Own numbers above measure a different exclusion boundary than the ~459/5,393/
134,581 cited in the task; not reconciled. UNMEASURED: full-suite pass/fail
(collection-only, per instruction).

**5 files fail to collect at all** (import errors — 0% execution regardless of
skip markers): `tests/test_cp_sat_bench.py`, `tests/io/test_dsn_boundary.py`,
`test_config_board_binding.py`, `test_clearance_grid_njit_fallback.py`,
`test_thermal_fdm_mms.py`.

### The bigger finding: unwired directories, not just skipped tests

`grep -rn pytest .github/workflows/*.yml` (24 workflows) is the complete set
of CI pytest invocations. Of `tests/`'s 46 subdirectories, **30 are never
named in any workflow**: `ablation, algo, analysis, architecture, closure,
comparison, constraint_types, constraints, domain, explainability,
integration, invariants, manufacturing, measurements, mechanical, ml, parity,
pcl, pipeline, profiling, property, protocol, regression, requirements,
robustness, testing, topological, unit, verification, visualization`.

Summing `def test_` in those 30 dirs: **~1,418 of ~5,238 test functions in
`temper-placer/tests` (27%) have no CI execution path**, independent of any
`pytest.skip`. This is §4 class 3 (unwired), and it dominates the skip count
in impact. `requirements/` (238 tests: safety/emc/dfm) is the worst instance —
see Categorization.

Also: `python-tests.yml:269` invokes `tests/losses/`, which does not exist.

Adjacent, not re-litigated here: that same step (lines 260–298, covering
`router_v6/ io/ deterministic/ physics/ fields/ validation/ placer/cp_sat/` —
~3,100 test functions) runs under a step-level `continue-on-error: true`
(shared `temper-N6-U8` stub) — the same dead-gate-wiring class the sibling
plan (`2026-07-25-002-...-plan.md`) catalogued for baselines, recurring for
raw test steps. Full `continue-on-error` burn-down is that plan's scope.

`kicad-cli`/`ngspice` are installed in the CI image
(`.github/docker/ci.Dockerfile:16,23-24`); `plotly`/`websockets`/`numba`/
`shapely` are direct deps; `jax` (0.8.2) is present transitively though absent
from `pyproject.toml` (UNMEASURED which package pulls it in). So the ~48
environment/optional-dep skips mostly do **not** fire in CI — they gate local
dev without the full toolchain, not CI coverage.

## Categorization (228 skip sites)

| Category | Count | Fires in CI? | Example |
|---|---|---|---|
| Fixture/board not found | ~96 | Mixed | `router_v6/test_finish_board_gate.py:97` — DRC-clean gate skips on missing `/tmp/temper_routed.kicad_pcb`; per `STRATEGY.md` the committed board has 0 segments/vias/zones, so this **always** skips today |
| External-tool-gated (kicad-cli, ngspice, rust) | ~23 | No — tools present in CI image | `placer/cp_sat/test_regression_drc.py:82` |
| Optional-dep-gated (plotly/websockets/numba/shapely/jax) | ~25 | No — deps installed | `visualization/test_status.py:278` |
| Known-broken/deferred ("not yet implemented", retired API) | ~13 | Yes, if wired (many aren't) | `requirements/emc/test_emi_filter.py:199` — **safety-relevant** |
| Unconditional skip (dead test) | 11 | Always | `router_v6/test_stage3_monolith_parity.py:6` |
| Golden-parity module-level skip (no fixtures ever generated) | 4 modules | Always | `router_v6/test_stage2_golden_parity.py:80` |
| Platform-gated | 1 | N/A | `cli/test_cli_error_handling.py:107` |
| Everything else | ~55 | Mixed | — |

## Vacuity findings (§4 class 4 / §5 Vacuity axis)

- **Test-side**: 25 `assert all(...)` sites in `packages/temper-placer/tests`.
  Spot-checked ~10; most preceded by a cardinality assert
  (e.g. `test_terminal_tree_execution.py:34` asserts `len==2` before line 36's
  `assert all(...)`) — correctly guarded.
- **Production-code, unguarded** (the gate implementations, not tests): 5
  `all()`-based aggregate-pass properties in `src/`; **4 of 5 have no
  non-empty precondition**:
  - `placer/cp_sat/_loop_gates.py:43` `_all_gates_green_results` — empty
    `_gate_results` → `True`. Called live at `_loop_core.py:718`.
  - `validation/drc_result.py:208` `RunResult.passed` — zero checks run →
    DRC "passes." Direct analogue of the §7 reference failure's blind metric.
  - `validation/validation_gates.py:55` `all_passed` over 4 named gates — if
    **none** have run, `all_passed` is `True`.
  - `manufacturing/stackup_validator.py:55` `all_passed` — same pattern.
  - Correctly guarded counterexample (fix pattern already exists):
    `pipeline/convergence.py:375-376` — `if not current_results: return
    False` precedes its `all(...)`.

## Requirements

- **R1.** ~~The 4 unguarded `all()` sites get a non-empty assertion or explicit
  "no gates ran" failure, per §12.~~ **DONE** (verified 2026-07-27): all four
  now guard explicitly and cite METHODOLOGY §4/§5 --
  `_loop_gates.py:35`, `drc_result.py:207`, `validation_gates.py:54`,
  `manufacturing/stackup_validator.py:54`.
- **R2.** Wire `requirements/` (238 tests: safety/emc/dfm) into a CI step with
  no `continue-on-error` — highest-priority unwired directory.
- **R3.** ~~Fix the phantom `tests/losses/` path in `python-tests.yml:269`.~~
  **DONE** (2026-07-27). Worse than a path typo: pytest aborts on a missing
  path, so all seven sibling directories ran **zero** tests. Confirmed in the
  log of run 30291488317. Fixed, and `scripts/pytest_guard.py` now asserts a
  floor on tests actually executed so the invocation cannot silently collapse
  to zero again -- a partial R4, applied where the damage was proven.
- **R4.** Skip-budget gate: CI check comparing skip-site count (`pytest.skip`,
  `skipif`, unconditional `skip`) against `origin/main`; growth fails without
  an explicit override token (same convention as the sibling plan's R1).
- **R5.** Per the seven-dead-gate-wiring precedent in
  `2026-07-25-002-...-plan.md`, R4's gate must itself be verified as invoked
  by a no-`continue-on-error` workflow step — a skip-counter nobody runs is
  the same failure it exists to catch.
- **R6.** Triage the ~96 "fixture not found" skips file by file: checked-in
  minimal fixture, generated-in-CI step, or legitimately local-only.
- **R7.** For the 30 unwired directories, one-line disposition each (wire in /
  merge into an invoked directory / confirm intentionally dev-only) —
  follow-up, not solved here.
- **R8.** Retire the 11 unconditional dead-test skips file by file: un-skip
  against current code, or delete.

## Priority order

1. R1 — vacuity in live gate code (cheapest, safety-relevant, 4 sites)
2. R2 — wire `requirements/` (zero CI exposure today)
3. R3 — phantom path, one-line fix
4. R5 before R4 — verify-invoked built in from day one
5. R4 — skip-budget ratchet
6. R6 — fixture-not-found triage (largest bucket, slowest)
7. R8, then R7

## Out of scope

- Full `continue-on-error` burn-down — `2026-07-25-002-...-plan.md`'s R2;
  only the one instance masking safety-relevant tests is flagged here.
- Running the full suite for real pass/fail counts (collection-only, as
  instructed).
- Baseline/allowlist files — covered by the sibling plan.
- Deleting tests wholesale — accounting and triage only.

## Review record (2026-07-25)

Independently re-verified before acceptance. The load-bearing claims held:

| Claim | Verified |
|---|---|
| `tests/requirements/` (238 tests: safety, emc, dfm, review, validators) named in **no** workflow | confirmed — `grep -rn "tests/requirements" .github/workflows/` returns nothing |
| `RunResult.passed` vacuously true on empty | confirmed — `drc_result.py:207` `all(...)` over a `default_factory=list` field |
| `_all_gates_green_results` vacuously green | confirmed — `_loop_gates.py:43`, live-called at `_loop_core.py:718` |
| Main Python test step's failure discarded | confirmed — `python-tests.yml` collects exit codes correctly (`FAIL=0` / `wait $pid \|\| FAIL=1` / `exit $FAIL`) and then carries `continue-on-error: true` |

**The `_all_gates_green_results` case is the sharpest.** Its own docstring
states *"An UNMEASURED gate is never green (core invariant)"* — and with an
empty `_gate_results`, it returns green. The code violates the invariant its
docstring asserts, in exactly the empty-collection case METHODOLOGY §5
names.

Corrections and additions:

1. **File count discrepancy.** Plan reports 482 test files; independent count
   is 461 repo-wide (459 under `temper-placer`). Scope definition differs —
   reconcile before any number here is quoted elsewhere.
2. **`pipeline/convergence.py:375` is cited as the correctly-guarded pattern.**
   Reviewer could not confirm a non-empty guard on that call site. Treat as
   UNVERIFIED rather than as the reference example.
3. **22 `continue-on-error` steps across 7 workflows carry the literal
   placeholder ticket `temper-NNN`** — not a real ticket. The `2026-09-01`
   hard-fail dates attached to them are therefore untracked by anything.

R-scope addition: the four vacuous production gates are **not test-side
defects** and should not wait on skip accounting. They are live blind metrics
of the same shape as the §7 reference failure and warrant their own
fast-tracked fix.
