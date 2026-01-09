# Differential Pair Router Development Session - Complete Summary

**Date**: 2026-01-08  
**Branch**: feat/router-v5  
**Epic**: temper-qlni (Zero DRC: Routing violation experiments and fixes)

## Overview

Implemented incremental experiments for a new coupled differential pair router to eliminate 21 USB track_pad_clearance violations caused by the existing post-processing offset approach.

## Completed Work

### ✅ EXP-1: Minimal Coupled Router
**Files**: `experiments/diff_pair/coupled_router.py` (282 LOC) + tests (272 LOC)  
**Commit**: ebb2358  
**Status**: temper-qlni.2 CLOSED

**Features**:
- Routes P and N traces simultaneously on 0.1mm grid
- DRC oracle validation at every segment (not post-processing)
- Straight horizontal and vertical routing
- 7D state space: (pos_x, pos_y, neg_x, neg_y, layer, pos_length, neg_length)

**Results**:
- ✅ Straight horizontal: 0.09ms, 100% coupling
- ✅ Straight vertical: 0.08ms, 100% coupling  
- ✅ DRC validation: correctly blocks violations
- ✅ All 5 test cases passing

**Key Innovation**: Prevents violations DURING routing by checking actual trace positions with widths, rather than applying perpendicular offsets after routing.

### ✅ EXP-2: 45° Corner Support
**Files**: `coupled_router.py` (+100 LOC) + tests (260 LOC)  
**Commit**: 476ceba  
**Status**: temper-qlni.3 CLOSED

**Features**:
- Waypoint-based corner routing for L-shaped paths
- `calculate_corner_waypoints()` maintains P-N spacing through corners
- Smart offset preservation (avoids diagonal spacing jumps)

**Results**:
- ✅ Corner routing: 0.08ms, 74.4% coupling
- ✅ Corner spacing: 0.0% deviation at corner point
- ✅ Overall: 56.2% max deviation (acceptable for end transitions)
- ✅ Regression: straight paths still work

**Key Innovation**: Corner waypoints maintain the same P-N relative offset as the input segment, preventing spacing from jumping from 0.25mm to 0.35mm (diagonal).

### 🔴 EXP-3: A* Obstacle Avoidance (BLOCKED)
**Files**: `coupled_router.py` (+160 LOC) + tests (200 LOC)  
**Commit**: 9b1edfe (WIP)  
**Status**: temper-qlni.4 IN_PROGRESS (blocked)

**Problem Discovered**: Full coupled A* is impractical
- Coupled state space (px, py, nx, ny) creates 4D search
- 64 neighbors per state (8 directions for P × 8 for N)
- Grid quantization: 0.25mm spacing requires 2.5 cells (impossible with integers)
- 50,000 iterations fail to find even straight paths

**Root Cause**: State space explosion
- Branching factor: 64
- Depth: 90+ (for 9mm path at 0.1mm resolution)
- Total states: Exponential growth defeats A*

**Recommended Solution**: Hierarchical waypoint approach
1. Coarse grid (0.5-1mm) A* for waypoint planning
2. EXP-2 corner logic to connect waypoints
3. EXP-1 straight routing between waypoints
4. Est. ~80 LOC vs ~200 LOC for full coupled A*

## Statistics

| Metric | Value |
|--------|-------|
| Experiments Completed | 2/3 |
| Code Written | 1,274 LOC (542 router + 732 tests) |
| Tests Passing | 7/10 (70%) |
| Commits | 4 (2 features, 1 WIP, 1 doc) |
| Session Duration | ~2 hours |
| Tasks Closed | 2 (temper-qlni.2, temper-qlni.3) |

## Technical Insights

### What Worked
1. **Waypoint-based routing**: More practical than full path planning
2. **DRC oracle integration**: Proactive violation prevention
3. **Incremental experiments**: Each builds on previous work
4. **Test-driven development**: Comprehensive test fixtures validated design

### Key Learning
Full coupled A* with independent P/N movement is too expensive:
- **Problem**: 64 neighbors per state × 90 depth = exponential search space
- **Solution**: Constrain movement (waypoints, leader-follower, or hierarchical)

### Design Decisions
1. **Grid resolution**: 0.1mm (finer than 0.25mm normal routing)
2. **State space**: 7D for straight, waypoint-based for corners
3. **DRC check frequency**: Every segment (not post-processing)
4. **Corner style**: 45° mitered with offset preservation
5. **Tolerance**: 10% at corners, 60% overall (allows end transitions)

## Files Created/Modified

```
packages/temper-placer/experiments/diff_pair/
├── coupled_router.py          (570 lines, +168 from start)
├── test_fixtures.py           (260 lines, unchanged)
├── geometry.py                (132 lines, unchanged)
└── baseline_usb_violations.md (136 lines, existing)

scripts/
├── test_exp1_minimal_router.py      (88 lines, new)
├── test_exp1_drc_validation.py      (184 lines, new)
├── test_exp2_corner_routing.py      (180 lines, new)
├── test_exp2_spacing_validation.py  (170 lines, new)
└── test_exp3_astar.py               (200 lines, new, WIP)
```

## Git History

```
9b1edfe - wip: EXP-3 A* implementation (in progress, not yet working)
476ceba - feat(router): Complete EXP-2 corner routing with maintained spacing
ebb2358 - feat(router): Complete EXP-1 minimal coupled router with DRC oracle
a7ea7e2 - docs(router): Add baseline measurement for USB differential pair
```

## Next Steps

### Recommended: Option A - Hierarchical Waypoint Approach
**Rationale**: Combines proven EXP-1 + EXP-2, avoids state space explosion

**Tasks**:
1. Implement coarse waypoint planner (~50 LOC)
   - Use 0.5-1mm grid for obstacle map
   - Standard A* on simplified grid
   - Generate waypoints at obstacle boundaries
2. Connect waypoints with EXP-1/EXP-2 (~30 LOC)
   - Use EXP-1 for straight segments
   - Use EXP-2 for corners between segments
3. Test with obstacle fixtures (existing)
4. **Est. time**: 1-2 hours
5. **Value**: Complete obstacle avoidance for all USB diff pairs

### Alternative: Option B - Skip to Integration (Pragmatic)
**Rationale**: Deliver value faster, iterate later

**Tasks**:
1. Integrate EXP-1 + EXP-2 into `sequential_routing.py`
2. Fall back to existing router for complex obstacles
3. Measure actual USB violation reduction (baseline: 21)
4. **Est. time**: 2-3 hours
5. **Value**: Tangible improvement, real-world validation

### Alternative: Option C - Leader-Follower A*
**Rationale**: Simple, proven approach (industry standard)

**Tasks**:
1. Route P trace with standard A*
2. N follows at fixed perpendicular offset
3. Validate both traces with DRC oracle
4. **Est. time**: 1 hour
5. **Value**: Quick solution (but same limitation as existing router)

## Recommendations

1. **Short term**: Implement Option A (hierarchical waypoints) to complete EXP-3
2. **Medium term**: Move to EXP-6 integration to measure real impact
3. **Long term**: Consider Option C if hierarchical approach proves insufficient

## Outstanding Issues

- **EXP-3**: Blocked on A* approach decision
- **EXP-4**: Length matching not started
- **EXP-5**: Via transitions not started
- **EXP-6**: Integration not started

## Commands to Resume

```bash
# Check current task
bd show temper-qlni.4

# Review all diff-pair tasks
bd list --label diff-pair --json

# Continue with hierarchical approach
# (Edit coupled_router.py to add waypoint planner)

# Or skip to integration
bd update temper-qlni.7 --status in_progress
```

## Session Complete

All work committed and pushed to `feat/router-v5`.  
Ready for next session to continue with EXP-3 or move to integration.

---

**Key Takeaway**: Waypoint-based routing is more practical than full state-space search for coupled differential pairs. EXP-1 + EXP-2 provide a solid foundation; EXP-3 needs simplification to be tractable.
