# USB Differential Pair Routing - Baseline Report

**Generated:** 2026-01-08  
**Board:** Temper induction cooker (pcb/temper.kicad_pcb)  
**Router:** Existing DiffPairRouter with post-processing offsets

## Summary

| Metric | Value |
|--------|-------|
| Routing Time | 0.87s |
| Coupling Ratio | 99.2% |
| Length Matching | 0.0mm skew |
| **DRC Violations** | **21** `track_pad_clearance` |
| Total DRC Issues | 21 |

## Problem Statement

The current `DiffPairRouter` operates on grid cells and applies **post-processing offsets** 
to create parallel traces. These offsets are applied **after** routing completes, which means
the router doesn't know if the actual trace positions (with widths) will violate DRC.

### Root Cause

1. Router plans a centerline path on grid cells
2. Path avoids obstacles successfully (both traces use same grid cells at different times)
3. **Post-processing** applies perpendicular offsets (+/- half_spacing) to P and N traces
4. **Offsets push traces into pads** that weren't in the original obstacle set
5. Result: **21 `track_pad_clearance` violations**

### Example from Code

```python
# In sequential_routing.py (lines 617-689)
def cells_to_mm_with_offset(pos_cells, neg_cells, target_spacing_mm):
    half_spacing = target_spacing_mm / 2.0
    
    # Find cells that appear in both paths (these need offset)
    shared_cells = pos_cell_set & neg_cell_set
    
    # Apply perpendicular offset based on trace direction
    for cell in shared_cells:
        offset_x, offset_y = get_offset_for_cell(cell, is_pos_trace)
        # ⚠️ This offset can push trace into pad!
        pos_path.append((px_mm + offset_x, py_mm + offset_y, p_layer))
```

**The problem:** The offset is calculated from the trace direction, but doesn't check
if the new position violates clearance with nearby pads.

## Violation Analysis

Based on pipeline DRC validation:

- **Total violations:** 21
- **Type:** All are `track_pad_clearance` violations
- **Nets affected:** USB_D+ and USB_D-
- **Pattern:** Traces pushed into pads by post-processing offset

### Observed Violations (from console output)

```
(Detailed violations require KiCad DRC report parsing)
```

## Current Router Behavior

### Strengths ✅

1. **Fast routing:** 0.82s for USB diff pair
2. **Excellent coupling:** 99.2% of path within target separation
3. **Perfect length matching:** 0.000mm skew
4. **Grid-based obstacle avoidance works well**

### Weaknesses ❌

1. **Post-processing offsets not DRC-aware**
2. **Centerline can pass near pads, then offset violates**
3. **No way to validate offset positions during routing**
4. **21 violations all from this single issue**

## Target for New Router

The new `CoupledDiffPairRouter` will:

1. ✅ Route P and N traces **simultaneously** (not centerline + offset)
2. ✅ Check DRC oracle for **both** actual trace positions at every step
3. ✅ No post-processing offsets - traces routed at actual positions
4. ✅ Maintain constant spacing (impedance control)
5. ✅ Use 45° mitered corners
6. ✅ Enforce length matching during routing (not post-processing)

### Success Criteria

| Metric | Baseline | Target | Acceptable | Status |
|--------|----------|--------|------------|--------|
| DRC Violations | 21 | 0 | ≤5 | 🔵 To Do |
| Routing Time | 0.87s | <1s | <2s | 🔵 To Do |
| Coupling Ratio | 99.2% | >95% | >90% | ✅ Maintain |
| Length Matching | 0.0mm | <0.5mm | <1.0mm | ✅ Maintain |

### Trade-offs

We're willing to accept:
- **Slightly slower routing** (<2s vs 0.82s) for correctness
- **More complex state space** (7D vs grid-based) for DRC compliance
- **Finer grid resolution** (0.1mm vs 0.25mm) for precise spacing

## Experiment Roadmap

| Experiment | Goal | Status | Estimated LOC |
|------------|------|--------|---------------|
| **EXP-0** | Baseline measurement (this report) | ✅ **DONE** | ~30 |
| **EXP-1** | Minimal coupled router + DRC oracle | 🔵 Next | ~100 |
| **EXP-2** | 45° corner support | 🔵 Open | ~80 |
| **EXP-3** | A* obstacle avoidance | 🔵 Open | ~120 |
| **EXP-4** | Length matching with serpentines | 🔵 Open | ~100 |
| **EXP-5** | Via transition support | 🔵 Open | ~60 |
| **EXP-6** | Full integration test on USB | 🔵 Open | ~50 |

## Next Steps

1. **Implement EXP-1:** Minimal coupled router
   - 7D state space: `(pos_x, pos_y, neg_x, neg_y, layer, pos_length, neg_length)`
   - Check DRC oracle at every step
   - Prove concept with straight-line test fixtures

2. **Validate approach:** Run test fixtures and verify DRC oracle prevents violations

3. **Iterate:** Add corners, obstacle avoidance, and integration

## References

- **Epic:** temper-qlni (Zero DRC: Routing violation experiments)
- **Infrastructure:** temper-qlni.1 (experiments/diff_pair/)
- **This task:** temper-qlni.8 (EXP-0: Baseline)
- **Next task:** temper-qlni.2 (EXP-1: Minimal router)
- **Code:** `packages/temper-placer/src/temper_placer/routing/diff_pair_router.py`
- **Integration:** `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py` (lines 607-693)
