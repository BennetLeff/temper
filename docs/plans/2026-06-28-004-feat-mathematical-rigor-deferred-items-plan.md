---
date: 2026-06-28
status: active
depth: standard
tags: [router-v6, hypothesis, pbt, ci, traceability, refactor, induction]
---

# feat: Mathematical rigor deferred items — CI benchmarks, traceability, induction dedup, segment edge-cases

## Problem Frame

The router-v6 mathematical validation pipeline (induction tests per `docs/plans/2026-06-28-007-test-router-v6-hypothesis-invariant-tests-plan.md`) shipped with four deferred quality items. Without them the test suite lacks a CI-time budget guarantee, `@req` annotations are absent from all DFM induction files, the 8 `test_*_induction.py` files independently duplicate ~400 lines of add/modify/remove boilerplate, and `_segment_to_segment_dist` has no unit coverage for degenerate geometry cases.

| Gap | Impact |
|-----|--------|
| No CI runtime budget | Full suite at `max_examples=200` may exceed ~5 min CI gate; no mechanism to skip or tier tests |
| Missing `@req` annotations | 10 test files (8 induction + base + strategy) have zero traceability; R2/R3 CI gates (`docs/TRACEABILITY.md`) report zero coverage for this plan's requirements |
| Induction boilerplate | Changing the add/modify/remove pattern requires 8-file edits; reviewing a change means reading 8 near-identical files |
| `_segment_to_segment_dist` untested on degenerates | Degenerate (zero-length, parallel, coincident-endpoint, NaN/inf) path through the Ericson 2005 algorithm is exercised only in end-to-end `verify_clearance` calls, not unit-tested |

## Scope

All changes are within `packages/temper-placer/tests/router_v6/` and the CI workflow touching that directory. No production source changes. No changes to the 007 plan document.

### In scope

1. Hypothesis profile configuration (`CI-fast` / `CI-full`), a CI benchmark job measuring total PBT suite wall-clock, hard timeout gate, and a `@pytest.mark.pbt_low_priority` marker for skippable tests.
2. `@req` annotations on all 8 induction files, `test_induction_base.py`, and `test_induction_strategy.py`, plus a `TRACEABILITY` sentinel in `tests/router_v6/`.
3. A shared induction harness (e.g., `InductionHarness` or parametrized base class) in `test_induction_base.py`; each of the 8 induction files reduces to validator-specific config + harness invocation.
4. Unit tests for `_segment_to_segment_dist` covering degenerate and edge cases.

### Deferred

- Extending CI budget enforcement to test suites outside `tests/router_v6/`.
- `@req` annotations for all other PBT files in `tests/router_v6/` beyond the induction set.
- Induction harness generalization for non-DFM validators (router stages 2-4).
- Hypothesis-driven PBT for `_segment_to_segment_dist` (the unit here is fixture-driven, not PBT).

---

## Implementation Units

### U1. CI budget benchmarks and Hypothesis profiles

**Goal:** Provide a configurable Hypothesis profile system with fast/full tiers, a benchmark CI job that measures PBT suite runtime, a hard timeout gate, and a marker for lower-priority tests.

**Dependencies:** None.

**Files:**
- `packages/temper-placer/tests/router_v6/conftest.py` (new) — Hypothesis profiles via `settings.register_profile()`
- `tests/router_v6/test_*_induction.py`, `test_induction_base.py`, `test_induction_strategy.py` (modify) — adopt `CI-fast` / `CI-full` profile via `@settings(load_profile=...)` or per-test `max_examples` override
- CI workflow file (`.github/workflows/python-tests.yml` or equivalent) — add `pbt-benchmark` job

**Approach:**

1. **Hypothesis profiles** in `conftest.py`:
   - `CI-fast`: `max_examples=50, deadline=5000, print_blob=False` — every-commit gate.
   - `CI-full`: `max_examples=200, deadline=15000, print_blob=False` — PR gate.
   - Loaded via `settings.register_profile()` in `conftest.py`; tests opt in with `@settings(load_profile=settings.get_profile("CI-fast"))`. Alternatively, a `HYPOTHESIS_PROFILE` environment variable selects the default profile.

2. **Low-priority marker**: `@pytest.mark.pbt_low_priority` registered in `pyproject.toml`. Tests carrying this marker are skipped under the CI-fast profile when `--skip-low-priority` is passed. Induction tests that use `max_examples=200` are tagged.

3. **Benchmark CI job**: A standalone job that runs `pytest tests/router_v6/ -m "property" --durations=0` and captures total wall-clock time. Fails if elapsed > 300 seconds (5 min). Output is a JSON artifact for trend tracking.

4. **Hard timeout**: A conftest `pytest_sessionfinish` hook or a wrapper script that enforces a total test-suite timeout (via `timeout` command or `pytest-timeout` with `--timeout=300` on the session).

**Test scenarios:**
- `CI-fast` profile runs the induction suite in < 60 seconds on CI hardware.
- `CI-full` profile runs the full property test suite in < 300 seconds.
- `pytest -m "not pbt_low_priority"` excludes tagged tests.
- Benchmark job writes a `pbt-timing.json` artifact with per-test durations.
- Timeout gate triggers when suite exceeds 300s; CI log shows which test was running.

---

### U2. @req traceability annotations for induction files

**Goal:** Add `@req(<plan-id>, <req-id>)` annotations to all 10 files (8 induction + base + strategy) per `docs/TRACEABILITY.md`, place a `TRACEABILITY` sentinel, and register the plan in `docs/traceability-registry.yaml`.

**Dependencies:** U3 (induction files are being refactored; annotate after or during refactor). The plan document itself must be committed first so the CI gate can parse it.

**Files:**
- `packages/temper-placer/tests/router_v6/TRACEABILITY` (new) — empty sentinel (accepts all active plans)
- `packages/temper-placer/tests/router_v6/test_induction_base.py` (modify)
- `packages/temper-placer/tests/router_v6/test_induction_strategy.py` (modify)
- `packages/temper-placer/tests/router_v6/test_acid_trap_induction.py` (modify)
- `packages/temper-placer/tests/router_v6/test_annular_ring_induction.py` (modify)
- `packages/temper-placer/tests/router_v6/test_clearance_induction.py` (modify)
- `packages/temper-placer/tests/router_v6/test_copper_balance_induction.py` (modify)
- `packages/temper-placer/tests/router_v6/test_creepage_induction.py` (modify)
- `packages/temper-placer/tests/router_v6/test_manufacturing_report_induction.py` (modify)
- `packages/temper-placer/tests/router_v6/test_thermal_relief_induction.py` (modify)
- `packages/temper-placer/tests/router_v6/test_teardrop_induction.py` (modify)
- `docs/traceability-registry.yaml` (modify) — add plan entry

**Approach:**

1. **Sentinel**: Create empty `TRACEABILITY` file in `tests/router_v6/`. This opts in the entire directory for `@req` scanning.

2. **Requirements mapping** (from the induction work's parent plan, `docs/plans/2026-06-28-007-*`):
   - R9 (Clearance minimum), R10 (Annular ring minimum), R11 (Creepage distance) — map to the DRC induction tests.
   - FR12 (Empty-board induction base), FR13 (Addition), FR13b (Modification), FR13c (Removal), FR14 (Strategy bootstrap), SC5 (Non-compliant detection) — map to specific test functions.

3. **Annotation placement**: One `@req` per test function, placed on the line immediately above or on the `def` line. Example:
   ```python
   # @req(N10, FR13): clearance induction — add compliant route
   def test_clearance_add_compliant_route() -> None:
   ```

4. **Registry entry**: Add the short plan ID (e.g., `N10`) to `docs/traceability-registry.yaml` with path to this plan document and scope listing all 10 files.

**Test scenarios:**
- `uv run python scripts/check_traceability.py --check-annotations` passes (no invalid `@req` tags).
- `uv run python scripts/check_traceability.py --check-coverage` passes (all non-deferred requirements covered).
- Every `@req` tag in the 10 files references a live requirement in this plan document.
- Sentinel file presence is confirmed; empty sentinel means all active plan IDs accepted.

---

### U3. Induction boilerplate deduplication

**Goal:** Extract the shared add/modify/remove induction pattern from the 8 `test_*_induction.py` files into a parametrized harness in `test_induction_base.py`, reducing the per-file boilerplate from ~50 lines to ~20 lines.

**Dependencies:** None.

**Files:**
- `packages/temper-placer/tests/router_v6/test_induction_base.py` (modify) — add `InductionHarness` class
- `packages/temper-placer/tests/router_v6/test_acid_trap_induction.py` (modify)
- `packages/temper-placer/tests/router_v6/test_annular_ring_induction.py` (modify)
- `packages/temper-placer/tests/router_v6/test_clearance_induction.py` (modify)
- `packages/temper-placer/tests/router_v6/test_copper_balance_induction.py` (modify)
- `packages/temper-placer/tests/router_v6/test_creepage_induction.py` (modify)
- `packages/temper-placer/tests/router_v6/test_manufacturing_report_induction.py` (modify)
- `packages/temper-placer/tests/router_v6/test_thermal_relief_induction.py` (modify)
- `packages/temper-placer/tests/router_v6/test_teardrop_induction.py` (modify)

**Approach:**

1. **Shared harness** in `test_induction_base.py`: A base class or helper that provides:
   - `make_empty_rr()` → `RoutingResults(compiled_routes={}, failed_nets=[])`
   - `make_compliant_route(net_name, coordinates, layer, width_mm, vias)` → `CompiledRoute`
   - `assert_no_violations(report)` — common assertion pattern
   - `run_add_induction(validator_fn, make_compliant_input)` — parametrized add test
   - `run_modify_induction(validator_fn, before_routes, modify_fn)` — parametrized modify test
   - `run_remove_induction(validator_fn, initial_routes, remove_key)` — parametrized remove test

2. **Per-file reduction**: Each `test_*_induction.py` imports the harness and provides only:
   - The validator function under test
   - Validator-specific fixture data (e.g., compliant route coordinates, net names)
   - Validator-specific assertions (e.g., `report.trap_count`, `report.violation_count`)
   - Any non-standard tests (e.g., `test_acid_trap_detects_non_compliant`, `test_clearance_add_non_compliant_detected`)

3. **pytest markers**: Preserve `@pytest.mark.dependency(depends=["induction-base"])` on harness-invoked tests.

4. **Non-standard tests**: Files with validator-specific edge cases (acid trap non-compliant, clearance non-compliant) keep those tests as standalone functions but use the harness's `make_empty_rr()` and `make_compliant_route()` helpers.

**Design decision**: Use a class-based harness (not `pytest.mark.parametrize`) because:
- Each validator has a different return type (`AcidTrapReport`, `ClearanceReport`, etc.) and different assertion fields.
- The modify/remove tests need per-validator route construction logic that doesn't fit neatly into parametrize tuples.
- A class-based mixin keeps the per-file structure readable while avoiding over-abstraction.

**Test scenarios:**
- All 8 induction files pass the same tests they did before refactoring.
- `pytest tests/router_v6/test_*_induction.py -v` shows the same test names.
- Adding a 9th induction file (for a new validator) requires < 30 lines of boilerplate.
- `pytest.mark.dependency` chain still works: `induction-base` → individual add/modify/remove tests.
- Harness helpers are importable by other test modules (e.g., `test_induction_strategy.py`).

---

### U4. Segment-to-segment distance degenerate case tests

**Goal:** Unit-test `_segment_to_segment_dist` in `clearance_check.py` for degenerate and edge cases that are not exercised by the induction tests.

**Dependencies:** None.

**Files:**
- `packages/temper-placer/tests/router_v6/test_clearance_segment_dist.py` (new)

**Approach:**

Create a focused unit test file that imports `_segment_to_segment_dist` directly from `temper_placer.router_v6.clearance_check`. Use `pytest.mark.parametrize` to exercise each degenerate class.

**Test categories (mapped to code paths in `clearance_check.py:303-397`):**

| Category | Code path | Input | Expected behavior |
|----------|-----------|-------|-------------------|
| Both zero-length | `a_len2 < eps and c_len2 < eps` (line 324) | `(p, p), (q, q)` | Distance = `\|p - q\|`, cp1 = p, cp2 = q |
| AB zero-length, CD normal | `a_len2 < eps` (line 329) | `(p, p), (c, d)` | Delegates to `_point_to_segment_dist(p, c, d)` |
| CD zero-length, AB normal | `c_len2 < eps` (line 334) | `(a, b), (p, p)` | Delegates to `_point_to_segment_dist(p, a, b)` |
| Parallel segments (det near zero) | `det <= eps` (line 355) | Parallel horizontal/vertical segments | Falls through to boundary check (lines 367-396); correct closest-point pair |
| Coincident endpoints | Boundary fallback (line 381-395) | Segments sharing an endpoint | Distance = 0, cp1 = shared point, cp2 = shared point |
| Collinear overlapping | Boundary fallback | Segments along same line, overlapping | Distance = 0 |
| Collinear separated | Boundary fallback | Segments along same line, gap | Distance = gap |
| NaN in AB | `_point_to_segment_dist` len2 check (line 289) | `(a, (nan, y))` | Returns finite distance (NaN-guarded in callers) or propagates as handled |
| +inf/-inf in coordinates | `math.isfinite` guards in `get_segments` (line 174) | Coordinates with inf | Degenerate path handled; test at the `_segment_to_segment_dist` level observes behavior |
| Identical segments | Boundary fallback | A=B and C=D | Distance = 0 |
| Perpendicular crossing | Interior minimum (line 359-365) | Crossing segments | Distance = 0, correct interior closest points |
| Single-point mutual projection | Interior minimum | Segments where closest points are both interior | Correct non-zero distance |

**Test scenarios:**
- `test_both_zero_length`: `_segment_to_segment_dist((0,0),(0,0), (3,4),(3,4))` → distance = 5.0
- `test_ab_zero_length`: `_segment_to_segment_dist((0,0),(0,0), (3,0),(3,5))` → distance = 3.0 (point to segment)
- `test_cd_zero_length`: `_segment_to_segment_dist((0,0),(5,0), (3,4),(3,4))` → distance = 4.0 (point to segment)
- `test_parallel_separated`: Two horizontal segments at y=0 and y=5 → distance = 5.0
- `test_coincident_endpoint`: `_segment_to_segment_dist((0,0),(5,0), (5,0),(5,5))` → distance = 0.0
- `test_collinear_overlapping`: `_segment_to_segment_dist((0,0),(5,0), (3,0),(8,0))` → distance = 0.0
- `test_collinear_separated`: `_segment_to_segment_dist((0,0),(2,0), (5,0),(8,0))` → distance = 3.0
- `test_nan_in_ab_b` (behavioral): `_segment_to_segment_dist((0,0),(float('nan'),0), (10,0),(10,5))` — does not crash; distance is defined (NaN propagates through `_point_to_segment_dist` len2 check → degenerate path)
- `test_perpendicular_crossing`: `_segment_to_segment_dist((0,0),(5,0), (2.5,-2),(2.5,2))` → distance = 0.0
- `test_identical_segments`: `_segment_to_segment_dist((0,0),(5,0), (0,0),(5,0))` → distance = 0.0

**Verification:** All 10+ parametrized cases pass. No crash on any degenerate input. NaN/inf tests document current behavior (even if it means documenting `NaN` propagation as acceptable until a NaN guard is added to `_segment_to_segment_dist` itself).

---

## Risk Assessment

- **U1**: Registering Hypothesis profiles globally may affect non-induction PBT tests if those tests don't override `max_examples`. Mitigation: profiles are opt-in per test file, not enforced globally via `conftest.py`.
- **U2**: Adding `@req` annotations before U3 lands creates churn. Mitigation: apply U2 after U3, or annotate the refactored harness in U3 and let individual files carry annotations on the harness-invoking functions.
- **U3**: Over-abstraction risk — the harness might not be able to express the acid-trap non-compliant test or clearance non-compliant test cleanly. Mitigation: keep non-standard tests as standalone functions; the harness covers only the shared add/modify/remove pattern.
- **U4**: `_segment_to_segment_dist` is a private function; importing it in tests couples to implementation details. Mitigation: the function is already a documented algorithm implementation (`clearance_check.py:303` docstring cites Ericson 2005); unit-testing it at this granularity is appropriate for a mathematical primitive.
