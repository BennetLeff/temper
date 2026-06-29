---
title: "Corpus runner passes raw rotation logits to loss functions, producing garbage metrics"
date: "2026-06-28"
category: "logic-errors"
module: "temper-placer regression / corpus runner"
problem_type: "logic_error"
component: "tooling"
severity: "critical"
symptoms:
  - "boundary_loss_final: 250,411,616 — mathematically impossible with board clamping active"
  - "corpus regression metrics silently inflated 6 orders of magnitude, no crash"
  - "post-hoc loss evaluation computes garbage rotated component dimensions"
root_cause: "wrong_api"
resolution_type: "code_fix"
tags: ["corpus-runner", "temper-placer", "jax", "gumbel-softmax", "boundary-loss", "rotation-logits", "loss-evaluation"]
---

# Corpus runner passes raw rotation logits to loss functions, producing garbage metrics

## Problem

The corpus regression runner passed `result.final_state.rotation_logits` (raw logits like `[5, -10, -10, -10]`) directly to loss functions that expect soft one-hot rotation vectors from Gumbel-Softmax sampling. This caused `batch_get_rotated_bounds()` to compute nonsensical rotated component dimensions, producing boundary loss values of ~250,000,000 when the true value was approximately 0. Regression tracking for boundary-related metrics was completely broken.

## Symptoms

- **Boundary loss reported at 250,411,616** — physically impossible with board clamping active (theoretical max < 100,000 for a 100×150mm board with 33 components)
- **All loss metrics inflated by six orders of magnitude** in corpus regression reports, while training metrics remained correct
- **No crash or exception** — the bug was silent; `rotation_logits` has the same shape `(N, 4)` as softmax rotations, so no type error was raised
- **Regression tracking useless** for boundary-related components — the metric was pure noise

## What Didn't Work

The investigation followed a mathematical invariant approach that progressively narrowed the search space:

1. **Adding boundary weight to curriculum refinement phase**: Had no effect because the training loop already used correct Gumbel-Softmax sampled rotations internally — the bug was in the separate post-hoc metric evaluation
2. **Auditing the JIT trace for clamping**: Confirmed that `jnp.clip` to board bounds IS present in the compiled graph — ruled out the clamping mechanism
3. **Source inspection of `make_train_step`**: Confirmed the clamping code and `loss_context` guard both exist — ruled out JIT omission
4. **Local corpus runner reproduction**: Running the full 8000-epoch corpus pipeline locally produced boundary_loss=0, while the `uv run` command produced 212M — narrowed the bug to the **metric collection pass**, not the optimizer itself

The invariant test suite (Theorems I–IX in `test_placement_invariants.py`) proved the clamping mechanism works and the training produces correct positions. A 6-stage reproduction test (`test_corpus_reproduction.py`) then confirmed the exact line where the divergence occurs — the post-hoc loss evaluation in `corpus_runner.py:352`.

## Solution

One line change in `packages/temper-placer/src/temper_placer/regression/corpus_runner.py` — apply `jax.nn.softmax()` to the rotation logits before passing them to the loss function:

**Before:**
```python
# Compute final individual loss values from breakdown
composite = make_loss(weights)
loss_result = composite(
    result.final_state.positions,
    result.final_state.rotation_logits,  # BUG: raw logits, not softmax
    context,
)
```

**After:**
```python
# Compute final individual loss values from breakdown
composite = make_loss(weights)
# Softmax the rotation logits to get rotation probabilities.
# Passing raw logits to loss functions (which expect soft one-hot
# rotations from Gumbel-Softmax) causes massively inflated rotated
# bounds and boundary loss values (observed: 250M vs actual ~0).
rotations = jax.nn.softmax(
    result.final_state.rotation_logits, axis=-1
)
loss_result = composite(
    result.final_state.positions,
    rotations,  # Correct: soft one-hot rotations
    context,
)
```

## Why This Works

`PlacementState` stores rotation as **logits** — unnormalized preference scores for each of 4 orientations (0°, 90°, 180°, 270°). During training, `train_step` samples these logits through Gumbel-Softmax to produce soft one-hot rotation vectors:

```
logits:    [  5, -10, -10, -10]   ← stored in PlacementState
softmax:   [~1.0, ~0, ~0, ~0]    ← what loss functions expect
```

`batch_get_rotated_bounds()` inside BoundaryLoss treats the rotation array as interpolation weights per orientation. Raw logits carry large positive and negative values that, when multiplied by component dimension tensors, produce nonsensical rotated bounding boxes — effectively claiming components have physically impossible dimensions spanning hundreds of millions of units. After softmax, the same vector correctly selects a single discrete orientation.

The training loop never hit this bug because its internal Gumbel-Softmax call already produces soft one-hot samples. Only the separate re-evaluation in the corpus runner skipped that step.

## Prevention

1. **Corpus reproduction test** (`test_corpus_reproduction.py`): A 6-stage diagnostic test that mirrors the corpus runner pipeline and asserts invariants at each step — parsed positions, heuristic pipeline output, LossContext fidelity, and post-training boundary loss
2. **Mathematical invariant test suite** (`test_placement_invariants.py`): 29 tests across 9 theorems that prove clamping works, boundary loss is bounded, and positional invariants hold — this was the diagnostic tool that isolated this bug
3. **Type-level distinction**: Consider using type aliases (`RotationLogits = Array` vs `RotationSoftmax = Array`) to make the distinction visible at the call site, or wrapping the softmax application in the `PlacementState` API itself
4. **Assert post-hoc consistency**: When both training-time and post-hoc loss evaluations exist, assert they agree within tolerance — a mismatch would have caught this immediately

## Related

- `docs/plans/2026-06-22-010-feat-placer-regression-infrastructure-plan.md` — design context for the corpus runner
- `docs/solutions/architecture-patterns/pad-position-ssot-placer-2026-06-28.md` — related pattern where rotation representation also caused bugs
- `packages/temper-placer/tests/core/test_placement_invariants.py` — Theorem VIII: regression-specific invariant tests
- `docs/solutions/architecture-patterns/ci-profiling-platform-canonical-metrics-contract-2026-06-28.md` — the profiling platform's weekly drift detection and PR comparison would catch this class of garbage-value regression before it ships; the trend check's sigma-based detection surfaces anomalous metric shifts from single commits
- `packages/temper-placer/tests/core/test_corpus_reproduction.py` — 6-stage diagnostic reproduction test
