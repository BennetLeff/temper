# Correlation Analysis Findings

**Date:** 2025-12-20  
**Issue:** temper-h0n9.1  
**Samples:** 30 placements with routing verification  
**Config:** temper_minimal.yaml  

## ⚠️ CAUTION: Preliminary Results - Do Not Act On Yet

**Status:** These findings require validation before use.

The analysis revealed several methodological issues that must be resolved:

| Issue | Concern | Tracking |
|-------|---------|----------|
| Config mismatch | 16 losses measured but config only specifies 4 | temper-h0n9.5 |
| Spread paradox | Spread hurts routing (counterintuitive) | temper-h0n9.6 |
| Weak effect size | R² < 20% for all predictors | temper-h0n9.7 |
| No success cases | All 30 samples failed routing (26% mean) | temper-h0n9.7 |
| Potential confounding | Losses may correlate with each other | temper-h0n9.8 |

**Action:** Complete investigation tasks (temper-h0n9.5 through temper-h0n9.9) before proceeding to weight tuning (temper-h0n9.4).

---

## Executive Summary

The correlation analysis with 30 samples reveals that only a few loss functions have meaningful correlation with routing success. Most losses show zero or near-zero correlation, indicating they may not meaningfully impact routability.

### Key Findings

1. **Overlap losses are the strongest predictor of routing success** (r = -0.38)
2. **Spread loss negatively correlates with completion** (r = -0.40) - unexpected
3. **Wirelength loss correlates with actual routed wirelength** (r = 0.47) - validates the metric
4. **Boundary losses are constant (all zero)** - not contributing to optimization
5. **Most other losses show zero correlation** - need investigation

## Detailed Results

### Losses with Significant Correlation

| Loss Function | vs_completion | vs_wirelength | vs_via_count | Interpretation |
|---------------|---------------|---------------|--------------|----------------|
| **overlap** | -0.377 | 0.0 | -0.374 | Higher overlap → worse routing. Expected. |
| **overlap_per_component** | -0.377 | 0.0 | -0.374 | Same as overlap (normalized). |
| **spread** | -0.398 | 0.0 | 0.0 | Spreading hurts routing. Surprising. |
| **wirelength** | 0.0 | 0.475 | 0.0 | Validates metric; not routing-linked. |

### Losses with Zero Correlation

| Loss Function | Possible Reason |
|---------------|-----------------|
| alignment | May be constant across samples |
| alignment_per_group | May be constant across samples |
| group_cluster* | Clustering may not impact routing at this scale |
| pin_grid_alignment | May be constant or irrelevant |
| rotation_consistency | May be constant across samples |

### Constant Losses (Skipped)

The following losses were skipped because they had zero standard deviation (constant values):

- `boundary` (std=0.00)
- `boundary_edge_violation` (std=0.00)
- `boundary_keepout_violation` (std=0.00)
- `boundary_per_component` (std=0.00)

**Interpretation:** All placements had boundary loss = 0, meaning no boundary violations. This is good for validity but means boundary loss doesn't differentiate between placements.

## Statistical Summary

| Metric | Value |
|--------|-------|
| Mean routing completion | 26.5% |
| Std dev completion | 5.7% |
| Samples with failed routing | 30 (100%) |
| Samples analyzed | 30 |

**Note:** All 30 samples had "failed" routing (not 100% complete), but completion varied from ~15% to ~40%, providing sufficient variance for correlation analysis.

## Anomalies and Unexpected Results

### 1. Spread Loss Negative Correlation (Unexpected)

**Finding:** Spread loss has r = -0.40 with routing completion.

**Expected:** We expected spread to help routing by giving components room.

**Observed:** Higher spread correlates with WORSE routing completion.

**Possible explanations:**
1. **Longer traces:** Spreading components increases wirelength, making routing harder
2. **Board utilization:** On a constrained board, spreading may push components into difficult areas
3. **Configuration issue:** The spread loss may need tuning or different parameters

**Recommendation:** Review spread loss implementation and consider reducing its weight or adjusting parameters.

### 2. Many Zero-Correlation Losses

**Finding:** 12 of 20 losses show exactly 0.0 correlation.

**Possible causes:**
1. **Constant values:** These losses may not vary across different random seeds
2. **Small variance:** The variance may be too small to detect correlation
3. **Actually irrelevant:** These losses may truly not impact routing

**Recommendation:** Investigate each zero-correlation loss to determine if it varies across samples. Create issue temper-h0n9.2 if not already tracking this.

### 3. Wirelength-Completion Disconnect

**Finding:** Wirelength loss correlates with actual wirelength (r=0.47) but NOT with completion (r=0.0).

**Interpretation:** The wirelength loss correctly predicts wire length, but wire length doesn't predict whether routing will succeed. This suggests:
1. Routing failures are due to local congestion, not global wirelength
2. Overlap/spread are more predictive of local congestion

## Recommendations for Loss Weight Tuning

Based on correlation strength, recommended weight adjustments:

```yaml
# Current (equal weights assumed)
losses:
  overlap: 1.0        # r=-0.38 with completion
  spread: 1.0         # r=-0.40 with completion (REDUCE!)
  wirelength: 1.0     # r=0.0 with completion
  boundary: 1.0       # constant, not contributing

# Recommended (correlation-informed)
losses:
  overlap: 2.0        # Increase - best predictor of routing
  spread: 0.3         # Decrease significantly - hurts routing
  wirelength: 0.5     # Reduce - doesn't predict routing success
  boundary: 1.0       # Keep - still needed for constraint satisfaction
```

### Priority Actions

1. **Increase overlap weight** - Strongest predictor of routing success
2. **Decrease or reconsider spread** - Currently hurting routing completion
3. **Investigate constant losses** - Ensure they're working correctly
4. **Re-run with adjusted weights** - Validate improvement

## Comparison with Domain Knowledge

| Loss | Expected Correlation | Observed | Match? |
|------|---------------------|----------|--------|
| overlap | Strong negative | Moderate negative | ✓ Partial |
| wirelength | Moderate negative | Zero | ✗ Unexpected |
| spread | Weak positive | Moderate negative | ✗ Inverted |
| boundary | Strong negative | Constant | ⚠️ Not testable |
| group_cluster | Moderate positive | Zero | ⚠️ Need investigation |

## Next Steps (Scientific Method)

### Required Before Weight Tuning

| Task | Purpose | Priority |
|------|---------|----------|
| temper-h0n9.5 | Verify optimizer respects config (why 16 losses?) | P1 |
| temper-h0n9.6 | Investigate spread loss definition (inverted?) | P1 |
| temper-h0n9.9 | Enhance script to save raw data | P2 |
| temper-h0n9.8 | Compute inter-loss correlations (confounding?) | P1 |
| temper-h0n9.7 | Increase variance for better signal | P2 |

### Blocked Until Investigation Complete

| Task | Purpose | Blocked By |
|------|---------|------------|
| temper-h0n9.4 | Apply weight tuning | h0n9.5, h0n9.6, h0n9.8 |

### Investigation Questions

1. **Why does the optimizer report 16 losses when config specifies 4?**
   - Are there hardcoded defaults?
   - Is the config being applied correctly?

2. **Why does spread loss hurt routing?**
   - Is "spread" measuring something different than expected?
   - Is it confounded with another variable?

3. **Are losses correlated with each other?**
   - If spread and overlap correlate, one may be redundant
   - Need raw data to compute inter-loss correlations

4. **Can we get more variance in routing outcomes?**
   - Current: 15-38% completion range
   - Need: Include some 50%+ success cases

## Raw Data Reference

Full correlation data saved to: `metrics/correlation_analysis_30samples.json`

---

*Analysis performed by correlation_analysis.py*  
*30 samples, 50 epochs each, with FreeRouting verification*
