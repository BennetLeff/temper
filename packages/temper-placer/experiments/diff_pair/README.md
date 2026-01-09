# Differential Pair Routing Experiments

This directory contains incremental experiments for developing a true coupled differential pair router that validates against the DRC oracle at every routing step.

## Problem Statement

**Current Issue:** The existing `DiffPairRouter` operates on grid cells and applies post-processing offsets to create parallel traces. These offsets can push traces into obstacles (pads) that weren't in the original obstacle set, resulting in **21 track_pad_clearance violations** (all on USB_D+ and USB_D- differential pairs).

**Root Cause:** Post-processing offsets are applied **after** routing is complete, so the router doesn't know if the actual trace positions (with widths) will violate DRC.

## New Approach

The **CoupledDiffPairRouter** routes P and N traces simultaneously and checks the DRC oracle for **both** actual trace positions (with widths) at every routing step.

### Key Features

1. **7D State Space**: `(pos_x, pos_y, neg_x, neg_y, layer, pos_length, neg_length)`
2. **Finer Grid**: 0.1mm resolution (vs 0.25mm for normal routing)
3. **DRC Oracle Integration**: Check clearances at every step, not post-routing
4. **Simultaneous Routing**: Both traces route together, maintaining coupling
5. **45° Mitered Corners**: Industry standard for controlled impedance
6. **Trombone Serpentines**: Length matching during routing

## Experiment Roadmap

| Experiment | Description | Status | LOC |
|------------|-------------|--------|-----|
| **EXP-0** | Baseline measurement and documentation | 🔵 Open | ~30 |
| **EXP-1** | Minimal coupled router (straight lines + DRC oracle) | 🔵 Open | ~100 |
| **EXP-2** | 45° corner support | 🔵 Open | ~80 |
| **EXP-3** | A* with obstacle avoidance | 🔵 Open | ~120 |
| **EXP-4** | Length matching with serpentines | 🔵 Open | ~100 |
| **EXP-5** | Via transition support | 🔵 Open | ~60 |
| **EXP-6** | Full integration test on USB | 🔵 Open | ~50 |

## File Structure

```
experiments/diff_pair/
├── __init__.py              # Package exports
├── README.md                # This file
├── test_fixtures.py         # Test cases (8 fixtures)
├── run_experiments.py       # Experiment runner
├── coupled_router.py        # Router implementation (incremental)
├── geometry.py              # Geometry helpers
└── baselines/               # Baseline measurements
    └── usb_violations.md    # EXP-0 results
```

## Test Fixtures

8 diverse test fixtures covering:

1. **straight_horizontal**: Basic horizontal routing
2. **straight_vertical**: Basic vertical routing
3. **single_corner_45deg**: L-shaped path with 45° corner
4. **obstacle_single_pad**: Route around circular pad
5. **narrow_corridor**: Tight coupling through corridor
6. **drc_violation_pad_clearance**: Negative test (should fail)
7. **length_mismatch_serpentine**: Triggers serpentine insertion
8. **via_transition_simple**: Via pair placement

## Usage

```python
from temper_placer.experiments.diff_pair import (
    create_test_fixtures,
    run_experiment,
    run_all_experiments,
    CoupledDiffPairRouter
)

# Create router instance
router = CoupledDiffPairRouter(
    grid_resolution_mm=0.1,
    trace_width_mm=0.127,
    target_spacing_mm=0.25,
    drc_oracle=drc_oracle
)

# Run all experiments
results = run_all_experiments(router, drc_oracle, verbose=True)

# Or run specific experiments by tag
results = run_all_experiments(router, drc_oracle, tag_filter="straight")
```

## Success Criteria

### Per-Experiment
- Routes complete successfully
- DRC violations reduced or prevented
- Coupling ratio >80%
- Length matching <0.5mm
- Routing time <2s per pair

### Overall (EXP-6)
- **Baseline**: 21 violations, 0.91s routing time
- **Target**: ≤5 violations, <2s routing time
- **Acceptable**: Slight time increase for correctness

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Grid resolution: 0.1mm | Finer than normal (0.25mm) for precise diff pair control |
| Corner style: 45° mitered | Industry standard for controlled impedance |
| Serpentine: Trombone | Simpler geometry than arc-based |
| Divergence: P outer, N inner | Consistent strategy around obstacles |
| Length matching: During routing | Prevents post-routing failures |
| Performance: Correctness first | Acceptable <2s vs 0.91s for zero violations |

## Integration Plan

Once experiments validate the approach:

1. Add `drc_oracle` parameter to `DiffPairRouter.__init__()`
2. Remove post-processing offset logic in `sequential_routing.py`
3. Route with actual trace positions checked at every step
4. Fall back to existing router if new router fails (safety net)
5. Validate on full Temper board

## Related Issues

- **temper-qlni**: Zero DRC Epic
- **temper-qlni.1**: EXP-INFRA (this directory)
- **temper-qlni.2**: EXP-1 (minimal router)
- **temper-qlni.3**: EXP-2 (corners)
- **temper-qlni.4**: EXP-3 (obstacle avoidance)
- **temper-qlni.5**: EXP-4 (length matching)
- **temper-qlni.6**: EXP-5 (vias)
- **temper-qlni.7**: EXP-6 (integration)
- **temper-qlni.8**: EXP-0 (baseline)
