# Seed Sensitivity Analysis: Robustness Features Impact

## Summary

**Result: 65% reduction in failure rate (23% → 8%)**

All robustness features enabled:
- Soft-body inflation (`inflation_ramp=0.3`)
- Adaptive per-component weighting
- Stochastic perturbation (jiggle)
- Gradient clipping (max norm 1.0)
- Subgraph partitioning

## Comparison to Baseline

| Metric | Baseline | With Robustness | Change |
|--------|----------|-----------------|--------|
| **Failure rate** | 23% (23/100) | 8% (8/100) | **-65%** ✓ |
| **Overlap violations (>=1.0)** | 2-5 seeds | 8 seeds | Worse |
| **Mean overlap** | ~0.5 | 0.36 | **-28%** ✓ |
| **Mean final loss** | ~413 | 410.10 | **-0.7%** ✓ |
| **CV final loss** | ~0.35 | 0.258 | **-26%** ✓ |
| **Boundary violations** | 0 | 0 | Same ✓ |

## Target Achievement

| Metric | Target | Achieved | Status |
|--------|--------|----------|--------|
| Failure rate | <5% | 8% | ❌ MISS (but 65% better) |
| Overlap violations | 0 seeds | 8 seeds | ❌ MISS |
| Mean overlap | <0.1 | 0.36 | ❌ MISS |
| CV final loss | <0.3 | 0.258 | ✓ PASS |

## Analysis

**Why 8 failures remain:**

The 8 failing seeds (5, 31, 43, 48, 53, 71, 79, 96) have significant overlap violations (1.4-7.3). This suggests:

1. **Insufficient epochs**: 400 epochs may not be enough for these pathological cases
2. **Hyperparameter tuning needed**: Jiggle threshold, adaptive weight ramp rate, inflation parameters
3. **Initialization issues**: Some seeds may create especially difficult initial configurations

**Recommendations:**

1. Run P2 hyperparameter tuning tasks (temper-gcp.10, temper-gcp.11)
2. Consider longer training (600-800 epochs) for production use
3. Investigate the 8 failing seeds for common patterns

## Positive Results

Despite missing the <5% target, significant improvements were achieved:

- **65% fewer failures** overall
- **26% lower variance** in final loss (more predictable)
- **28% lower mean overlap** (better quality)
- **Zero boundary violations** maintained

The optimizer is significantly more robust than baseline, even if not yet perfect.
