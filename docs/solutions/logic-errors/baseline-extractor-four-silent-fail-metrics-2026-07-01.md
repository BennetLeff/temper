---
title: "Five silent failures in baseline metric extraction produce wrong corpus gate"
date: 2026-07-01
category: logic-errors
module: temper-placer
problem_type: logic_error
component: tooling
symptoms:
  - "All five corpus baselines recorded hpwl_final=0.0, overlap_loss_final=0.0, boundary_loss_final=0.0, and wirelength_final aliased to final_loss composite"
  - "Corpus regression gate passed on every PR despite baselines being wrong since first commit (6db810fb)"
  - "Human-reference boundary loss produced values of 58k-941k due to absolute-vs-relative coordinate mismatch"
  - "Two divergent copies of baseline_extractor.py existed (tests/fixtures/external/ and src/temper_placer/validation/), neither tested on real boards"
root_cause: logic_error
resolution_type: code_fix
severity: critical
tags:
  - baseline-extraction
  - regression-gate
  - silent-failure
  - coordinate-system
  - try-except
  - hardcoded-zero
  - temper-placer
---

# Five silent failures in baseline metric extraction produce wrong corpus gate

## Problem

`scripts/extract_corpus_baselines.py` contained five bugs in a single block (lines 117-132). Every corpus `baseline.json` file recorded wrong metrics across four of five fields, yet the regression gate passed on every PR because the gate's `margin_abs: 100.0` tolerance floor absorbed `0.0 ± 100` without complaint. Two divergent, untested copies of the extractor existed, neither exercising the full validation chain. The code had been dead since first commit.

Separately, the newly-built `human_reference_extractor.py` added `board.origin` back to parser-normalized component positions, converting them from board-relative coordinates (`[0, width]×[0, height]`) to absolute KiCad page coordinates. `BoundaryLoss` expects board-relative space, so every component appeared massively off-board — producing boundary loss values of 58k (piantor_right), 516k (bitaxe_ultra), and 941k (rp2040_designguide).

## Symptoms

- `hpwl_final` was always 0.0 across all five corpus boards — the wrong function name (`compute_hpwl` doesn't exist; correct is `compute_total_hpwl`) raised `ImportError` caught by bare `try:except:pass`
- `overlap_loss_final` and `boundary_loss_final` were hardcoded as `{"mean": 0.0}` in the writer template, never measured from optimizer output
- `wirelength_final` was aliased to `result.final_loss` (the composite training loss including overlap, boundary, wirelength, and spread), not the wirelength breakdown
- `test_placement_comparison.py` read a `human_placement` field from committed baselines that didn't populate it — dead code exercising dead data
- Human-reference boundary loss reported 58,117 on a board that should have ~495 — the coordinate-space mismatch dwarfed all other metrics
- The corpus regression gate passed on every PR. `margin_abs: 100.0` made `0.0 ± 100` always within tolerance

## What Didn't Work

- **Patching the extractor in place**: the two divergent copies differed in schema, metric computation path, and output format. Neither was tested. Consolidation into a single canonical module was cleaner than picking one and retrofitting the other.
- **Partial fixes**: fixing only `compute_hpwl → compute_total_hpwl` would still leave three hardcoded-zero metrics and the mislabeled alias. All five errors compounded; fixing four of five would still produce wrong numbers.
- **Keeping separate `baseline.json` and `human_reference.yaml` in one file**: the old `baseline_extractor.py` stored everything in one output file. Cohabiting them risked a future bless-script change silently overwriting the human number — the same class of silent-failure bug being removed.

## Solution

**Fix 1: Rewrite the metrics block in `extract_corpus_baselines.py`**

Before (the five-bug block):
```python
# Broken: wrong function name, wrong signature, bare try/except
hpwl_val = 0.0
try:
    from temper_placer.losses.wirelength import compute_hpwl  # doesn't exist
    hpwl_val = float(compute_hpwl(result.final_state, netlist))  # wrong signature
except Exception:
    pass  # silently writes 0.0

return {
    "wirelength_final": {"mean": float(result.final_loss), ...},  # aliased to final_loss
    "overlap_loss_final": {"mean": 0.0, ...},   # hardcoded
    "boundary_loss_final": {"mean": 0.0, ...},   # hardcoded
    "final_loss": {"mean": float(result.final_loss), ...},
    "hpwl_final": {"mean": hpwl_val, ...},  # always 0.0
}
```

After (corrected):
```python
# Correct: softmax rotations, compute breakdown, use correct function
rotations = jax.nn.softmax(result.final_state.rotation_logits, axis=-1)
loss_result = make_loss(weights)(result.final_state.positions, rotations, context)
breakdown = loss_result.breakdown if loss_result.breakdown else {}

hpwl_val = float(compute_total_hpwl(result.final_state.positions, rotations, context))

return {
    "wirelength_final": {"mean": float(breakdown.get("wirelength", 0.0)), ...},
    "overlap_loss_final": {"mean": float(breakdown.get("overlap", 0.0)), ...},
    "boundary_loss_final": {"mean": float(breakdown.get("boundary", 0.0)), ...},
    "final_loss": {"mean": float(result.final_loss), ...},
    "hpwl_final": {"mean": hpwl_val, ...},
}
```

**Fix 2: Remove the origin addition in `human_reference_extractor.py`**

The parser already normalizes `component.initial_position` to board-relative coordinates. Adding `board.origin` pushed components into absolute KiCad page space where `BoundaryLoss` saw them outside `[0, width]×[0, height]`.

```python
# Before (wrong — absolute coordinates)
px = float(comp.initial_position[0]) + float(board.origin[0])
py = float(comp.initial_position[1]) + float(board.origin[1])

# After (correct — board-relative coordinates, matching BoundaryLoss expectations)
px = float(comp.initial_position[0])
py = float(comp.initial_position[1])
```

HPWL and overlap loss are translation-invariant and were unaffected by this fix.

**Before/after impact on piantor_right**:

| Metric | Before (wrong) | After (correct) |
|--------|---------------|-----------------|
| hpwl_final | 0.0 | 1238.6 |
| overlap_loss_final | 0.0 | 9.5 |
| wirelength_final | 19108.2 (== final_loss) | 1278.4 (actual wirelength) |
| boundary_loss (human ref) | 58116.7 | 494.7 |

## Why This Works

1. **Rotation logits must be softmax'd before loss evaluation.** Training loops apply Gumbel-Softmax internally, but post-hoc evaluation (both the baseline extractor and corpus runner) must apply `jax.nn.softmax()` explicitly. Passing raw logits produces garbage values — this was independently discovered in a prior incident (`docs/solutions/logic-errors/corpus-rotation-logits-boundary-regression-2026-06-28.md`).

2. **Composite loss breakdown gives individual metric values without re-running individual loss functions.** Following the `corpus_runner.py:447-472` pattern, calling the same composite loss on final positions/rotations splits into per-loss breakdown values.

3. **The parser's coordinate normalization is the contract.** The KiCad parser subtracts `board.origin` during component extraction. Loss functions expect positions in the same `[0, board_width]×[0, board_height]` space. Adding origin back breaks this contract.

4. **No `try:except:pass` anywhere.** Every computation failure now raises loudly. A missing import or NaN metric halts the extraction, not silently records 0.0.

## Prevention

- **Ban bare `except Exception: pass` in metrics or gate code.** Any computation that produces a number for CI comparison must either succeed or fail loudly. A linter rule or CI check for `except.*Exception.*:\s*pass` near metric computation would catch this class.
- **End-to-end smoke test:** after regeneration, assert `hpwl_final_mean > 0` on every board with ≥2 components. A single assertion would have caught all four wrong metrics.
- **Single source of truth for extraction.** Remove divergent copies — the two `baseline_extractor.py` files existed side by side with different schemas because each was developed in isolation.
- **Test on boards with non-zero origin.** Half the corpus boards have `board.origin == (0,0)`, which masked the coordinate-space bug. The other half (piantor_right `(66, 43)`, bitaxe `(77, 48)`, rp2040 `(...)`) exposed it immediately.
- **Compare against human reference as a sanity check.** The human-reference oracle now catches implausible values (boundary loss should be single-to-double-digit on correctly-placed boards, not five-to-six figures).

## Related Issues

- `docs/solutions/logic-errors/corpus-rotation-logits-boundary-regression-2026-06-28.md` — prior silent-failure from raw logits in corpus runner (same loss-function boundary mismatch class)
- `docs/solutions/architecture-patterns/ci-gate-quality-enforcement.md` — structural prevention pattern for `try:except:pass` failure class
- `docs/solutions/architecture-patterns/pipeline-observability-observer-cross-validation-pattern-2026-06-29.md` — observer-exception swallowing pattern
- `docs/solutions/architecture-patterns/pad-position-ssot-placer-2026-06-28.md` — coordinate-space convention SSOT (parallel failure: inline math vs canonical function)
