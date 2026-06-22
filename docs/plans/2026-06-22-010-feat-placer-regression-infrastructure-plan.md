---
title: "Placer Regression Infrastructure"
type: feat
status: active
date: 2026-06-22
origin: "docs/ideation/2026-06-22-design-validation-ideation.md"
---

# Plan: Placer Regression Infrastructure

## Summary

After N1–N9, the temper-placer has new features (`safety_category` fields, CLI zoning,
loss functions) but no systematic regression testing that catches placement quality
regressions. The existing infrastructure (`RegressionRunner`, `check_regression.py`,
`MetricsTracker`) covers structural checks and single-board optimizer regression but
does not run end-to-end optimization on a multi-board corpus and compare placement
quality metrics (wirelength, overlap) against committed baselines. This plan builds
a benchmark corpus of 3–5 PCBs with frozen baseline metrics, a regression runner that
optimizes each and compares against baselines, a CI gate that fails on regressions
beyond threshold, and a baseline update protocol for intentional improvements.

## Problem Frame

**Current state:** The `regression/` package (`runner.py:19-183`,
`packages/temper-placer/src/temper_placer/regression/runner.py`) runs golden boards
but only compares _structural_ metrics (component count, net count, DRC errors). It
never runs the optimizer, so it cannot detect placement quality regressions (worse
wirelength, increased overlap, degraded DRC proxy scores). Two standalone scripts
exist but are disconnected: `scripts/check_regression.py:1-183` runs multi-trial
optimizer regression against a single board (`pcb/temper.kicad_pcb`) with a
single `metrics/baseline_values.json`; `scripts/check_perf_regression.py:1-113`
checks loss-function execution time regression.

**Gap:** No infrastructure runs the full optimizer on a diverse corpus and compares
placement quality metrics against version-controlled baselines in CI.

**Target state:** A `placer-regression` CI gate that:
1. Has a committed corpus of 3–5 standard PCBs with baseline metric files
2. Optimizes each corpus board with fixed seed/config, producing wirelength,
   overlap, boundary loss, and DRC proxy metrics
3. Compares each metric against the committed baseline with configurable thresholds
4. Fails CI (exit 1) when any metric degrades beyond threshold
5. Supports baseline updates via `--bless` flag (manual approval protocol)

## Scope Boundaries

**In scope:**
- Corpus of 3–5 PCBs committed to `power_pcb_dataset/corpus/` with baseline files
- `CorpusRegressionRunner` that optimizes each board and compares quality metrics
- CI workflow (`.github/workflows/placer-regression.yml`) running on PRs to `main`
- Baseline bless protocol with `--bless` flag and commit-message approval tag
- Consolidation of duplicated regression-check logic from `scripts/check_regression.py`
  and `scripts/check_perf_regression.py`

**Out of scope:**
- Routing quality regression (Router V6—covered by `ClosureTest` in `closure_test.py`)
- Performance/microbenchmark regression (already covered by `check_perf_regression.py`)
- Auto-generating baselines from external boards
- Visualization or dashboarding of regression trends
- Training variant (compact vs standard loss) parameter sweep

## Key Technical Decisions

**D1. Corpus stored in `power_pcb_dataset/corpus/`**: Each board gets a subdirectory
with the `.kicad_pcb`, a `constraints.yaml`, and a `baseline.json`. This mirrors the
existing `power_pcb_dataset/golden_manifest.yaml` pattern (line 1–8) but adds per-board
constraints and baseline metrics.

**D2. Runner builds on existing `MetricsTracker`**: The `experiments/metrics_tracker.py:102-148`
`MetricsTracker` class already records `RunMetrics` (wirelength, overlap, DRC, convergence).
The regression runner reuses this for metric collection and adds comparison logic against
the committed baseline.

**D3. Fixed-seed determinism**: Each corpus board uses a fixed seed (42 + board index)
and fixed config (8000 epochs, curriculum enabled, standard loss weights). This ensures
reproducible baseline values. Non-deterministic JAX operations pinned via
`jax.config.update('jax_platform_name', 'cpu')`.

**D4. Thresholds are per-metric, stored in baseline file**: Each `baseline.json` entry
specifies `mean`, `margin_rel` (relative tolerance, e.g. 0.05 for 5%), and `margin_abs`
(absolute floor, e.g. 2.0 for overlap). The gate uses `max(mean * margin_rel, margin_abs)`
as the allowed delta. This pattern is already used in `scripts/check_regression.py:27-56`.

**D5. Baselines are version-controlled JSON, not YAML**: JSON is chosen for numeric
precision and CI consumption. YAML is used for human-editable manifests only. Existing
`BaselineMetrics` uses YAML (`validation/baseline_extractor.py:55-65`); this plan uses
JSON for comparison baselines to avoid YAML float formatting issues.

**D6. Bless protocol uses a dedicated script, not a CLI flag on the runner**: A
separate `scripts/bless_baselines.py` script handles baseline updates. It requires
the committer to include `Baseline-Approval:` in the commit message body with an
explanation. This follows the existing `drc_ratchet.py:139` ceiling-approval pattern.

## Implementation Units

### U1. Corpus Assembly

**Goal:** Assemble and commit 3–5 PCBs with constraints and extracted baseline metrics.

**Requirements:** R1

**Files:**
- Create: `power_pcb_dataset/corpus/` directory with subdirectories per board
- Create: `power_pcb_dataset/corpus/manifest.yaml` — corpus index
- Create: `power_pcb_dataset/corpus/<board_id>/<board_id>.kicad_pcb`
- Create: `power_pcb_dataset/corpus/<board_id>/constraints.yaml`
- Create: `power_pcb_dataset/corpus/<board_id>/baseline.json`

**Corpus candidates** (3–5 boards, picked for diversity and existing availability):

| Board ID | Source | Complexity | Rationale |
|----------|--------|-----------|-----------|
| `temper` | `pcb/temper.kicad_pcb` | medium (~120 comp.) | Project's own board; must never regress |
| `minimal` | `packages/temper-placer/tests/fixtures/minimal_board.kicad_pcb` | tiny (4 comp.) | Fastest regression check; catches parsing breaks |
| `rp2040_designguide` | `tests/fixtures/external/.cache/rp2040_designguide/RP2040-Guide.kicad_pcb` | small (~50 comp.) | Real open-source board; KiCad 6+ format |
| `bitaxe_ultra` | `tests/fixtures/external/.cache/bitaxe_ultra/bitaxeUltra.kicad_pcb` | medium (~120 comp.) | Power electronics; most relevant domain |
| `piantor_right` | `tests/fixtures/external/.cache/piantor_right/keyboard_pcb.kicad_pcb` | small (~45 comp.) | Keyboard matrix; regular grid-like placement |

**Manifest format** (`corpus/manifest.yaml`):
```yaml
version: 1
boards:
  - id: temper
    pcb: temper/temper.kicad_pcb
    constraints: temper/constraints.yaml
    baseline: temper/baseline.json
    seed: 42
    epochs: 8000
    description: "Temper induction cooker — must never regress"
  - id: minimal
    pcb: minimal/minimal_board.kicad_pcb
    constraints: minimal/constraints_minimal.yaml
    baseline: minimal/baseline.json
    seed: 43
    epochs: 2000
    description: "Minimal 4-component board — fast parse/optimize smoke test"
  # ... remaining boards
```

**Baseline format** (`corpus/<id>/baseline.json`):
```json
{
  "board_id": "temper",
  "extracted_at": "2026-06-22T00:00:00",
  "git_hash": "abc123",
  "config": {
    "seed": 42,
    "epochs": 8000,
    "curriculum": true,
    "heuristics": true,
    "compact": false
  },
  "metrics": {
    "wirelength_final": {
      "mean": 4520.3,
      "margin_rel": 0.05,
      "margin_abs": 100.0
    },
    "overlap_loss_final": {
      "mean": 0.0,
      "margin_rel": 0.10,
      "margin_abs": 2.0
    },
    "boundary_loss_final": {
      "mean": 0.0,
      "margin_rel": 0.10,
      "margin_abs": 5.0
    },
    "final_loss": {
      "mean": 234.5,
      "margin_rel": 0.05,
      "margin_abs": 20.0
    },
    "hpwl_final": {
      "mean": 4520.3,
      "margin_rel": 0.05,
      "margin_abs": 100.0
    }
  }
}
```

**Approach:**
1. Copy each board's `.kicad_pcb` and constraints YAML into `corpus/<id>/`
2. Write a `scripts/extract_corpus_baselines.py` that runs the optimizer once per
   board (fixed seed, fixed config) and writes the resulting `baseline.json`
3. Hand-review baselines for sanity (no NaN, no zero wirelength on real boards)
4. Commit the entire corpus with a `Ceiling-Approval: Initial corpus baseline`
   commit message

**Test scenarios:**
- Each board in the corpus parses successfully via `parse_kicad_pcb`
- Each board optimizes to completion with the fixed config (no crashes)
- Baseline values are non-zero for meaningful boards (wirelength > 0)

**Verification:** `python3 -c "import json; [json.load(open(f'power_pcb_dataset/corpus/{b}/baseline.json')) for b in ['temper','minimal','rp2040_designguide','bitaxe_ultra','piantor_right']]"` succeeds.

---

### U2. Corpus Regression Runner

**Goal:** Create a `CorpusRegressionRunner` that loads the corpus manifest, optimizes
each board, compares metrics against baselines, and returns pass/fail per board.

**Requirements:** R2

**Files:**
- Create: `packages/temper-placer/src/temper_placer/regression/corpus_runner.py`
- Modify: `packages/temper-placer/src/temper_placer/regression/__init__.py`
- Create: `packages/temper-placer/tests/regression/test_corpus_runner.py`

**Approach:** Write `corpus_runner.py` containing:

1. `CorpusEntry` dataclass — mirrors manifest entries with resolved paths
2. `BaselineFile` dataclass — loads/validates `baseline.json` structure
3. `CorpusRegressionRunner` class:
   - `__init__(corpus_root: Path, repo_root: Path)` — loads manifest, validates baselines
   - `run_board(board_id: str) -> BoardResult` — single-board optimization + comparison
   - `run(boards: list[str] | None = None) -> int` — run all or filtered boards
   - Internal: calls `train_multiphase` from `optimizer/__init__.py` (same path as
     `cli/__init__.py:933-943`), collects metrics via `RunMetrics` from
     `experiments/metrics_tracker.py:30-80`, compares each metric against
     `BaselineFile.metrics[name]`

4. `check_metric(name, actual, baseline_spec) -> tuple[bool, str]` — threshold-aware
   comparison function (ported and generalized from `scripts/check_regression.py:27-56`)

**Integration with existing runner:** The existing `RegressionRunner`
(`runner.py:19-183`) remains for structural/DRC regression (no optimizer execution).
The new `CorpusRegressionRunner` is complementary — it runs the optimizer and checks
placement quality metrics. Both are accessible from the regression CLI
(`regression/cli.py:17-40`) via subcommands.

**Optimization config per board:** The runner reads `seed` and `epochs` from the
manifest. Loss weights are read from the board's `constraints.yaml` (same `losses`
section as the `optimize` CLI command at `cli/__init__.py:772-794`). If no losses
section exists, it falls back to the standard weights from
`scripts/benchmark_baselines.py:38-48`.

**Error handling:**
- Missing PCB/constraints/baseline → skip with `BoardResult(skipped=True)`
- Optimizer crash → `BoardResult(passed=False)` with error message, caught via
  try/except wrapping `train_multiphase`
- JAX OOM on large boards → consider skipping `piantor_right` if too large; executor
  must set `XLA_PYTHON_CLIENT_MEM_FRACTION=0.5`

**Test scenarios:**
- Happy path: run `minimal` corpus board, assert passed with non-zero deltas
- Metric regression: artificially lower baseline threshold, assert FAIL
- Missing manifest: returns non-zero exit code with diagnostic message
- Skipped board: corpus board with missing PCB returns skipped result, not counted
  as failure

**Verification:** `python3 -m temper_placer.regression.cli run-corpus --board minimal` prints PASS/FAIL status and metric deltas.

---

### U3. CI Workflow

**Goal:** GitHub Actions workflow that runs the corpus regression runner on every PR
to `main` and blocks merge on regression.

**Requirements:** R3

**Files:**
- Create: `.github/workflows/placer-regression.yml`

**Approach:**

```yaml
name: Placer Regression
on:
  pull_request:
    branches: [main]
    paths:
      - 'packages/temper-placer/src/**'
      - 'power_pcb_dataset/corpus/**'
      - 'packages/temper-placer/configs/**'
  push:
    branches: [main]
    paths:
      - 'packages/temper-placer/src/**'
      - 'power_pcb_dataset/corpus/**'

jobs:
  regression:
    runs-on: ubuntu-latest
    timeout-minutes: 90
    env:
      JAX_PLATFORM_NAME: cpu
      XLA_PYTHON_CLIENT_MEM_FRACTION: 0.5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - name: Install temper-placer
        run: pip install -e packages/temper-placer
      - name: Run corpus regression
        run: python3 -m temper_placer.regression.cli run-corpus --json
      - name: Upload report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: regression-report
          path: regression-report.json
```

**Path filtering**: The workflow triggers only when temper-placer source or corpus
files change. This avoids running expensive optimization on firmware/docs-only PRs.

**Timeout**: 90 minutes is generous for 5 boards at ~8000 epochs each. The `minimal`
board (2000 epochs) provides a fast-fail smoke test early in the loop.

**Summary output**: The runner writes `regression-report.json` with per-board
results and metric deltas. On failure, the workflow generates a summary table
for the PR checks tab, following the pattern in `scripts/check_regression.py:150-176`
(`GITHUB_STEP_SUMMARY`).

**Baseline approval bypass**: If the commit message contains
`Ceiling-Approval: <reason>`, the CI step that checks ceiling increases is skipped
for that commit (same pattern as `drc_ratchet.py:139`).

**Verification:** Push a PR that modifies a loss function; CI runs the corpus
regression and reports pass/fail for all 5 boards.

---

### U4. Baseline Bless Protocol

**Goal:** Script and process for updating baseline metrics after intentional
placement quality improvements.

**Requirements:** R4

**Files:**
- Create: `scripts/bless_baselines.py`
- Create: `power_pcb_dataset/corpus/BASELINE_POLICY.md` (human-readable policy doc)

**Approach:**

`scripts/bless_baselines.py`:
```
Usage: bless_baselines.py [--board BOARD_ID] [--all] [--dry-run]

Re-extracts baseline metrics for corpus boards after an intentional
quality improvement. Requires human approval via commit message tag.

Flags:
  --board BOARD_ID  Update baseline for a specific board
  --all             Update all corpus boards
  --dry-run         Show what would change without writing files
```

The script:
1. Loads the corpus manifest from `power_pcb_dataset/corpus/manifest.yaml`
2. For each selected board, runs the optimizer with the manifest-specified config
3. Computes new metric values
4. Shows a diff of old vs. new baseline values
5. If `--dry-run` is not set, overwrites `baseline.json`
6. Prints the required commit message format:
   ```
   Ceiling-Approval: Bless baselines after [description of improvement]
   
   - temper: wirelength_final 4520 -> 3980 (-12%)
   - bitaxe_ultra: overlap_loss_final 0.5 -> 0.0
   ```

**Policy** (in `BASELINE_POLICY.md`):
- Baselines may only be updated when placement quality **improves** (lower wirelength,
  lower overlap). A baseline that **worsens** (higher wirelength) requires an explicit
  justification in the commit message.
- The `Ceiling-Approval:` tag is mandatory in the commit body.
- Baseline-only PRs should include a before/after comparison in the PR description.
- CI validates that `Ceiling-Approval:` is present when `baseline.json` files change.

**CI enforcement:** The `placer-regression.yml` workflow includes a step that checks
if `baseline.json` was modified in the PR. If yes, it parses the commit message for
`Ceiling-Approval:` and fails if absent. This uses the existing
`drc_ratchet.py:121-148` `detect_ceiling_raise` pattern.

**Test scenarios:**
- Bless a single board: `--board minimal` updates only `minimal/baseline.json`
- Dry run: `--board temper --dry-run` prints diff, no file writes
- Missing approval: PR modifies baseline without `Ceiling-Approval:` → CI fails

**Verification:** `python3 scripts/bless_baselines.py --board minimal --dry-run`
prints old→new metric comparison.

---

### U5. Script Consolidation

**Goal:** Remove duplicated regression-check logic from `scripts/` and route all
regression checking through the unified corpus runner.

**Requirements:** R2 (quality check), R3 (CI gate)

**Files:**
- Deprecate: `scripts/check_regression.py` — replaced by U2 corpus runner
- Deprecate: `scripts/check_perf_regression.py` — keep for microbenchmarks (out of
  scope for this plan, but add a deprecation comment pointing to the corpus runner
  for placement quality)

**Approach:**
1. Add a deprecation banner to `scripts/check_regression.py`:
   ```python
   # DEPRECATED: Use `python3 -m temper_placer.regression.cli run-corpus` instead.
   # This script is kept for reference but will be removed after the corpus
   # regression runner is validated in CI for 2 weeks.
   ```
2. Copy the `check_metric` logic from `scripts/check_regression.py:27-56` into
   the new `corpus_runner.py` (already covered in U2).
3. `scripts/check_perf_regression.py` remains untouched (covers loss-function
   execution time, which is a separate concern from placement quality).

**Verification:** `grep -r "check_regression.py" .github/` returns no matches
(no CI depends on the deprecated script).

---

## System-Wide Impact

| Component | Change | Rationale |
|-----------|--------|-----------|
| `power_pcb_dataset/corpus/` | New directory | Houses corpus boards, constraints, and baselines |
| `packages/temper-placer/src/temper_placer/regression/corpus_runner.py` | New module | Optimizer-based regression runner |
| `packages/temper-placer/src/temper_placer/regression/__init__.py` | Modify | Export `CorpusRegressionRunner` |
| `packages/temper-placer/src/temper_placer/regression/cli.py` | Modify | Add `run-corpus` subcommand |
| `.github/workflows/placer-regression.yml` | New file | CI gate on PRs |
| `scripts/bless_baselines.py` | New file | Baseline update tool |
| `scripts/check_regression.py` | Deprecate | Replaced by corpus runner |
| `power_pcb_dataset/corpus/BASELINE_POLICY.md` | New file | Human-readable policy |

**No changes to:**
- `RegressionRunner` (`runner.py`) — remains for structural/DRC regression
- `DrcRatchet` (`drc_ratchet.py`) — complementary DRC-only gate
- `ClosureTest` (`closure_test.py`) — covers router DRC, separate CI path
- `MetricsTracker` / `RunMetrics` — reused, not modified

## Risk Analysis

| Risk | Probability | Impact | Mitigation |
|------|-----------|--------|------------|
| JAX OOM on CI runners | Medium | High — flaky CI | Set `XLA_PYTHON_CLIENT_MEM_FRACTION=0.5`; order boards smallest-first so fast-fail boards (minimal, rp2040) catch issues before OOM-prone boards |
| JAX/XLA non-determinism across machines | Medium | Medium — false regression alarms | Pin `JAX_PLATFORM_NAME=cpu`; use `jax.config.update('jax_platform_name', 'cpu')`; accept larger `margin_abs` for boards with known variance |
| Corpus boards become unparseable after parser changes | Low | High — all boards skip | Parser changes that break the corpus must be accompanied by corpus baseline updates (caught by CI); `parse_kicad_pcb` is already battle-tested on these boards |
| CI timeout on 5 full optimizations | Medium | Medium — CI blocked | `timeout-minutes: 90` is conservative; the `minimal` board (2000 epochs, ~30s) runs first as fast-fail; consider splitting into parallel jobs per board if needed |
| Regression alarm fatigue (too many false positives) | Medium | High — team ignores CI | Start with generous thresholds (`margin_rel: 0.05` for wirelength, `margin_abs: 20` for final_loss); tighten after 2 weeks of stable CI |
| Corpus divergence from temper project PCB | High (long-term) | Medium — corpus tests irrelevant board | The `temper` board in the corpus must be updated whenever `pcb/temper.kicad_pcb` changes; CI path filter triggers on `pcb/**` changes |

## Test Strategy

### Unit Tests
- `test_corpus_runner.py`: Test `CorpusRegressionRunner` with a mock optimizer that
  returns pre-scripted `RunMetrics`. Verify pass/fail for metrics within/outside
  threshold. Test missing manifest, missing baseline, missing PCB paths.
- `test_bless_baselines.py`: Test dry-run mode, single-board vs all-boards, missing
  approval tag detection in commit message parsing.

### Integration Tests
- Using the existing `minimal_board.kicad_pcb` fixture at
  `packages/temper-placer/tests/fixtures/minimal_board.kicad_pcb`:41, create a
  minimal corpus entry and run the full pipeline (parse → optimize → compare).
  Verify runner reports PASS with realistic metrics.
- Test the `check_metric` function against the pre-computed `metrics.json` at
  `packages/temper-placer/tests/fixtures/drc_test_placements/metrics.json:1-141`
  which has 5 quality levels with known loss values.

### CI Verification
- After merge: manually trigger the workflow via `workflow_dispatch` to verify
  it runs on the merged `main`.
- First PR to test: modify a loss function weight in
  `packages/temper-placer/src/temper_placer/losses/overlap.py`, push a PR, verify CI
  catches the wirelength/overlap delta.

### Edge Cases
- Board with zero components: `empty_board.kicad_pcb` at
  `packages/temper-placer/tests/fixtures/empty_board.kicad_pcb` — runner should
  skip with a clear message rather than crash.
- Board with only fixed components (all constrained in `constraints.yaml`) — runner
  should optimize movable components only and report metrics correctly.
- JAX import failure: runner should report a clear error and non-zero exit code,
  not silently pass.
