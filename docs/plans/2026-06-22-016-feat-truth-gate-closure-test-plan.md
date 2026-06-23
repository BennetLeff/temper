---
title: "feat: Truth-Gate the Closure Test — Require Real Pipeline Results"
type: feat
status: active
date: 2026-06-22
origin: docs/ideation/2026-06-22-test-and-build-next-ideation.md
---

# feat: Truth-Gate the Closure Test

## Summary

The closure test at `packages/temper-placer/src/temper_placer/regression/closure_test.py` catches `Exception as e` and appends to warnings, never failing on import or runtime errors. A missing dependency that causes `ImportError` in either the placement or routing step silently produces `benders_iterations=0`, `router_completion_pct=0.0`, and `passed=True`. This plan adds negative assertions, a `--require-all-stages` mode, a zero-results exit code check, and wires the truth-gated closure test into CI as a PR-blocking gate.

---

## Problem Frame

The `ClosureTest.run()` method (line 66–173) has three truth gaps:

| # | Issue | Location | Consequence |
|---|-------|----------|-------------|
| 1 | Placement `Exception` → `warnings`, never `errors` | `closure_test.py:104-106` | `ImportError("No module named temper_placer.protocol")` → PASS with zero placement |
| 2 | Routing `Exception` → `warnings`, never `errors` | `closure_test.py:126-127` | `ImportError` on routing → PASS with `router_completion_pct=0.0` |
| 3 | `passed = len(errors) == 0 and ceiling_passed` | `closure_test.py:160` | Zero-results run (both steps warn) satisfies this trivially |

Additionally, `scripts/ci_closure_test.py:80` delegates to `result.passed` with no independent truth check, and the CI workflow (`python-tests.yml`) does not invoke the closure test at all — neither in the `test` job (which runs `tests/core/` only) nor the `regression` job (which runs `scripts/check_regression.py`, the optimizer regression, not the closure pipeline).

The integration tests at `packages/temper-placer/tests/integration/test_pipeline_gap.py` already assert `benders_iterations > 0` and no import warnings (lines 27-56), but these are not run in CI.

---

## Scope Boundaries

### In scope

- Add negative assertions to `ClosureResult` / `ClosureTest.run()`: `benders_iterations > 0`, `router_completion_pct > 0`, `stages_exercised >= 2`
- Add `--require-all-stages` CLI flag to `ci_closure_test.py` that fails if any pipeline stage is skipped (moves import/runtime warnings to `errors`)
- Add zero-results check: if both placement and routing produce zero, exit non-zero regardless of `passed` flag
- Wire truth-gated closure test into CI as a PR-blocking job in `.github/workflows/python-tests.yml`
- Add unit tests to `tests/regression/test_closure.py` for the new assertions

### Deferred

- `stages_exercised` tracking in `test_pipeline_gap.py` (already has per-step assertions)
- Adding closure test to Makefile `regression` target (the optimizer regression is separate)

### Out of scope

- Refactoring `ClosureTest.run()` into smaller methods
- Adding closure test to pre-commit hooks
- Per-stage timing instrumentation (addressed by plan 015)

---

## Implementation Units

### U1. Add truth assertions to `ClosureResult`

**Goal:** `ClosureResult` gains fields and a `validate()` method that checks pipeline actually ran.

**Requirements:** R1 (benders_iterations > 0), R2 (router_completion_pct > 0), R3 (stages_exercised >= 2)

**Files:**
- `packages/temper-placer/src/temper_placer/regression/closure_test.py` — `ClosureResult` dataclass

**Approach:**
1. Add `stages_exercised: int = 0` field to `ClosureResult` (default 0 for backward compat with unit tests).
2. In `ClosureTest.run()`, increment `stages_exercised` for each pipeline step that executes without `Exception`/`ImportError` (parse, placement, routing, DRC = 4 possible; require >= 2).
3. Add `validate() -> list[str]` method to `ClosureResult` that returns a list of assertion failures:
   - `"benders_iterations <= 0: pipeline produced no placement iterations"` if `benders_iterations <= 0`
   - `"router_completion_pct <= 0: pipeline produced no routing results"` if `router_completion_pct <= 0`
   - `"stages_exercised ({n}) < 2: insufficient pipeline execution"` if `stages_exercised < 2`
   - `"zero-results: both placement and routing produced no results"` if both `benders_iterations <= 0` AND `router_completion_pct <= 0` (catches the dual-ImportError case even when stages_exercised might increment from parse+DRC)
4. Integrate `validate()` into `ClosureTest.run()` before computing `passed`; validation failures become `errors`.

**Verification:** Unit tests in U4 cover each assertion. Integration test `test_pipeline_gap.py` continues to pass (it already asserts `benders_iterations > 0`).

---

### U2. Add `--require-all-stages` mode to CI closure test script

**Goal:** When `--require-all-stages` is passed, any pipeline stage that throws `Exception` becomes an error (not a warning), causing the run to fail.

**Requirements:** R4 (require-all-stages rejects partial execution)

**Files:**
- `scripts/ci_closure_test.py` — add `--require-all-stages` flag
- `packages/temper-placer/src/temper_placer/regression/closure_test.py` — `ClosureTest.run()` accepts `require_all_stages: bool = False`

**Approach:**
1. Add `require_all_stages: bool = False` parameter to `ClosureTest.__init__` and `run()`.
2. When `require_all_stages=True`, placement/routing exceptions are appended to `errors` (not `warnings`), and DRC `ImportError` is also promoted to `errors`.
3. Pass through from `ci_closure_test.py` via `--require-all-stages` argparse flag.
4. The CI job runs with `--require-all-stages` by default.

**Verification:** Unit test: mock a placement `ImportError`, verify `result.passed` is `False` when `require_all_stages=True`. When `require_all_stages=False` (default for opencode), the graceful-degradation behavior is preserved.

---

### U3. Wire truth-gated closure test into CI

**Goal:** Add a CI job that runs the closure test on PRs and blocks merge on failure.

**Requirements:** R5 (CI gates PRs on closure test)

**Files:**
- `.github/workflows/python-tests.yml` — add new `closure` job or extend `regression` job to run on PRs

**Approach:**
1. Add a new `closure` job to `python-tests.yml` that runs on both `push: main` and `pull_request: main`.
2. The job runs `uv run python3 scripts/ci_closure_test.py --pcb pcb/temper.kicad_pcb --require-all-stages`.
3. Use the same `uv` setup steps as the `test` job.
4. Set `timeout-minutes: 20` (the closure test involves actual placement + routing + DRC).
5. Output JSON summary as a workflow artifact for debugging (`--output closure-result.json`).

**CI job structure:**
```yaml
closure:
  name: Pipeline Closure Test (Truth-Gated)
  runs-on: ubuntu-latest
  timeout-minutes: 20
  steps:
    - uses: actions/checkout@v4
    - uses: astral-sh/setup-uv@v4
      with: { version: "latest" }
    - run: uv python install 3.12
    - run: uv sync --all-packages
    - run: uv run python3 scripts/ci_closure_test.py \
        --pcb pcb/temper.kicad_pcb \
        --require-all-stages \
        --output closure-result.json
    - uses: actions/upload-artifact@v4
      if: always()
      with:
        name: closure-result
        path: closure-result.json
```

**Verification:** CI passes on a working branch. PRs from branches where `temper_placer.protocol` or `temper_placer.runner` are broken will fail the `closure` job.

---

### U4. Add unit tests for truth assertions

**Goal:** `tests/regression/test_closure.py` covers the new `validate()` method and `require_all_stages` behavior.

**Requirements:** R1–R4 test coverage

**Files:**
- `packages/temper-placer/tests/regression/test_closure.py` — new test methods

**Approach:**
1. Add `TestClosureResultValidation` class:
   - `test_validate_all_passing` — `benders_iterations=5, router_completion_pct=95.0, stages_exercised=4` → validate returns `[]`
   - `test_validate_zero_benders` — `benders_iterations=0` → validate returns error about placement
   - `test_validate_zero_router` — `router_completion_pct=0.0` → validate returns error about routing
   - `test_validate_stages_below_two` — `stages_exercised=1` → validate returns error about insufficient stages
   - `test_validate_zero_results` — both zero → validate returns zero-results error
   - `test_validate_backward_compat` — default-constructed `ClosureResult()` (all zeros) → validate returns failures; existing unit tests that don't call `validate()` continue to pass
2. Add `TestClosureTestRequireAllStages` class:
   - `test_require_all_stages_placement_error` — mock placement to raise `ImportError`, with `require_all_stages=True` → `result.passed is False`, placement error in `result.errors`
   - `test_default_graceful_degradation` — same mock without `require_all_stages` → placement warning in `result.warnings`, `result.passed` depends on DRC ceiling

**Verification:** `uv run pytest packages/temper-placer/tests/regression/test_closure.py -v` passes.

---

## System-Wide Impact

- **`closure_test.py`** — `ClosureResult` gains `stages_exercised` and `validate()`. `ClosureTest.run()` gains `require_all_stages` parameter (default `False` preserves existing graceful-degradation behavior).
- **`ci_closure_test.py`** — gains `--require-all-stages` flag. Zero-results check added before returning exit code.
- **`python-tests.yml`** — new `closure` job added, runs on PRs. Existing `regression` job unchanged (push-to-main only).
- **`build-status`** — new required check `Pipeline Closure Test (Truth-Gated)` appears on PRs. Branch protection may need updating to require this check.
- **No changes to placer algorithms, RouterV6, protocol, or DRC.**

---

## Risk Analysis & Mitigation

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Closure test is slow (~5 min), slows CI feedback | Medium | High | Use `timeout-minutes: 20` with buffer. If too slow for PR feedback loop, consider a `--fast` mode (e.g., skip DRC) as follow-up. |
| `--require-all-stages` flags a pre-existing import issue not yet fixed | Medium | Medium | The plan's purpose IS to surface this. If CI goes red on first run, fix the import (that's the bug this plan catches). |
| `stages_exercised` counter off-by-one for edge-case boards | Low | Low | Counter is explicit per-step in `run()`. Parse failure returns early (stages_exercised never incremented). Tests cover. |
| Backward compat: existing callers of `ClosureTest.run()` break | Low | Low | `validate()` is called inside `run()` only; `require_all_stages` defaults `False`. `test_pipeline_gap.py` already asserts `benders_iterations > 0` so its assertions are stronger than `validate()`. |

---

## Test Strategy

- **U4 unit tests** cover `ClosureResult.validate()` edge cases and `require_all_stages` behavior.
- **Existing integration tests** (`test_pipeline_gap.py`) continue to pass — their assertions are already stricter (`benders_iterations > 0`).
- **Existing regression unit tests** (`test_closure.py:TestClosureResult`, `TestClosureTest`) continue to pass — `validate()` is only called inside `run()`, not in dataclass tests.
- **CI closure job** exercises the full pipeline on the temper board with `--require-all-stages`, providing end-to-end verification.

## Verification

1. `uv run pytest packages/temper-placer/tests/regression/test_closure.py -v` — all new and existing tests pass.
2. `uv run python3 scripts/ci_closure_test.py --pcb pcb/temper.kicad_pcb --require-all-stages` — produces non-zero results and `benders_iterations > 0`, `router_completion_pct > 0`.
3. `uv run python3 scripts/ci_closure_test.py --pcb /nonexistent.kicad_pcb --require-all-stages` — exits non-zero.
4. CI `closure` job passes on the PR that implements this plan.
5. GitHub branch protection updated to require `Pipeline Closure Test (Truth-Gated)` check.
