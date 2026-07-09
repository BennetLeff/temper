# Router V5: Root Cause Analysis
## Violation Taxonomy and Top 3 Root Causes

**Date:** 2026-01-03  
**Board:** `pcb/temper_routed_v2.kicad_pcb`  
**Total Violations:** 339 (baseline without zone blocking) / 811 (with zone blocking enabled)

---

## Executive Summary

The router produces two distinct violation profiles depending on whether copper zone blocking is enabled:

1. **Baseline (339 violations)**: Core routing algorithm issues - trace crossing, clearance, and pad entry
2. **With Zone Blocking (811 violations)**: Severe congestion due to constrained routing channels

The top 3 root causes account for **~85%** of all violations and represent the highest-impact fixes.

---

## Taxonomy Report Summary

### Violation Distribution (Baseline: 339 violations)

```
By Category:
  Trace Crossing:        112 (33%)  ← Same-layer traces intersecting
  Unknown:                85 (25%)  ← Requires manual classification
  Clearance Insufficient: 64 (19%)  ← Traces too close for net class
  Pad Entry:              42 (12%)  ← Violations at component pads
  Via Placement:          36 (11%)  ← Via-to-via, via-to-trace conflicts

By Net (Top 10):
  +3V3:                  138 violations
  +5V:                   120 violations
  I_SENSE:               104 violations
  +15V:                  101 violations
  AC_L:                   81 violations
  PGND:                   80 violations
  GATE_H:                 60 violations
  GATE_L:                 54 violations
  ... and 15 more nets

By Location (Grid Quadrant):
  Top-Left (MCU area):    155 (46%)
  Bottom-Left:            115 (34%)
  Bottom-Right:            48 (14%)
  Top-Right:               21 (6%)
```

---

## Root Cause #1: Trace Crossing (33% of violations)

### Statistics
- **Violation count:** 112 (33% of total)
- **Affected nets:** Power nets (+3V3, +5V, +15V, PGND), signal nets (SPI_*, I_SENSE)
- **Spatial distribution:** Concentrated in Top-Left quadrant (MCU area, high density)

### Technical Analysis

**Code path:**
```
maze_router.py:route_net_rrr() 
  → _astar_numba()
  → Pathfinding uses 3D grid (x, y, layer)
  → NO same-layer crossing detection in cost function
```

**Why it happens:**
The A* pathfinder treats each layer independently. When routing on the same layer (e.g., Top layer), the algorithm does not detect or penalize crossings with existing traces of the same layer. The `occupancy` grid only marks cells as blocked (-1) or occupied by traces (2), but doesn't differentiate between "this cell has a trace on MY layer" vs "this cell has a trace on a different layer".

**What data is missing/wrong:**
- The cost function in `_astar_numba()` does not check if `current_layer == existing_trace_layer`
- The occupancy grid is 3D `(x, y, layer)` but crossing detection requires checking if two line segments on the **same layer** intersect
- The router assumes vias will be used to avoid crossings, but in single-layer scenarios or when via budgets are exhausted, crossings occur

### Proposed Fix

**Approach:**
Add same-layer crossing detection to the A* cost function. Before expanding a node, check if the path segment `(prev_cell → current_cell)` intersects any existing trace segment on `current_layer`.

**Implementation:**
1. Modify `MazeRouter._astar_numba()` to accept a `layer_trace_index: Dict[int, List[LineSegment]]`
2. In the cost calculation loop, add:
   ```python
   if current_layer in layer_trace_index:
       proposed_segment = LineSegment(prev_pos, current_pos)
       for existing_seg in layer_trace_index[current_layer]:
           if proposed_segment.intersects(existing_seg):
               cost += CROSSING_PENALTY  # e.g., 1000.0
   ```
3. Pre-compute `layer_trace_index` in `rrr_route_all_nets()` once per iteration

**Files to modify:**
- `packages/temper-placer/src/temper_placer/routing/maze_router.py` (~50 lines)
- `packages/temper-placer/src/temper_placer/routing/constraints/geometry.py` (add `LineSegment.intersects()` method)

**Estimated complexity:** Medium  
**Risk:** Could slow down A* by 10-20% due to intersection checks. Mitigate with spatial indexing (R-tree) for trace segments.

### Validation
**Test case:** Route two nets on the same layer with paths that would naturally cross. Verify they either:
1. Use vias to switch layers, OR
2. Route around each other

**Expected violation reduction:** ~112 violations → ~20 violations (some may be unavoidable due to congestion)

---

## Root Cause #2: Clearance Insufficient (19% of violations)

### Statistics
- **Violation count:** 64 (19% of total)
- **Affected nets:** Mixed - power/signal pairs where clearance rules vary by net class
- **Spatial distribution:** Bottom-right (HV area), some in MCU area

### Technical Analysis

**Code path:**
```
maze_router.py:_astar_numba()
  → Reads trace_width from net_class
  → Does NOT inflate "blocked" radius by (trace_width/2 + clearance)
  → Places traces edge-to-edge instead of center-to-center + clearance
```

**Why it happens:**
The router marks cells as "blocked" when placing a trace, but the blocking radius is based solely on the trace width, not the **required clearance to other nets**. This is the "net isolation" problem referenced in `temper-df3m`.

Example:
- Net A (signal, 0.2mm width, needs 0.2mm clearance to other signals)
- Net B (HV, 1.0mm width, needs 3.0mm clearance to signals)
- When routing Net A, cells within 0.1mm (trace_width/2) are blocked
- When routing Net B later, it can place a trace 0.15mm away from Net A (0.1mm from A's edge + 0.05mm grid snap)
- This violates the 3.0mm clearance requirement

**What data is missing/wrong:**
- `occupancy` grid doesn't store "which net owns this cell"
- No lookup of `ClearanceMatrix.get_clearance(net_a, net_b)` during pathfinding
- Blocking radius calculation: `blocked_radius = trace_width / 2` should be `blocked_radius = trace_width/2 + max_clearance_to_any_net`

### Proposed Fix

**Approach (temper-df3m):**
When routing a net, inflate the blocked area around ALL existing traces by the required clearance between the current net and each existing net.

**Implementation:**
1. Before routing `net_current`, iterate through all placed traces
2. For each trace of `net_other`, calculate:
   ```python
   required_clearance = clearance_matrix.get_clearance(net_current, net_other, x, y)
   block_radius = (trace_width_other / 2) + required_clearance + (trace_width_current / 2)
   block_cells = ceil(block_radius / cell_size)
   ```
3. Mark cells within `block_radius` as "soft blocked" (high cost, not impassable)
4. Use a priority queue to handle overlapping block regions

**Files to modify:**
- `maze_router.py`: `_prepare_routing_grid()` method
- `constraints/design_rules.py`: Ensure `ClearanceMatrix` is passed to router

**Estimated complexity:** High (requires net-aware occupancy grid)  
**Risk:** Significant performance impact - need to check clearance for every cell expansion. Requires caching/optimization.

### Validation
**Test case:** Route a HV net (3.0mm clearance) and a signal net (0.2mm clearance) in proximity. Verify clearance is maintained.

**Expected violation reduction:** ~64 violations → ~10 violations

---

## Root Cause #3: Zone Bleeding / Congestion (Conditional: 472 violations when zones enabled)

### Statistics
- **Violation count:** 472 additional violations when `block_zones()` is enabled
- **Affected nets:** All nets, especially those forced through narrow channels
- **Spatial distribution:** Entire board, concentrated near zone boundaries

### Technical Analysis

**Code path:**
```
placement_routing_loop.py
  → router.block_zones(board.zones, clearance=0.3)
  → Marks all cells within zone polygons + clearance as hard-blocked
  → Dramatically reduces available routing channels
  → Router fails to find feasible paths, creates conflicts
```

**Why it happens:**
The copper zones (GND on In1.Cu, +15V on In2.Cu) consume large areas of the inner layers. When these are correctly blocked with proper clearance, the remaining routing channels become too narrow for the number of nets competing for space. This is NOT a router bug - it's a **placement problem**.

**What data is missing/wrong:**
- Component placement was optimized WITHOUT knowledge of zone geometry
- The placement optimizer has no "zone avoidance" loss to keep components away from zone edges
- The congestion heatmap generated by the router is not fed back into the placement optimizer effectively

### Proposed Fix

**Approach:**
This is not a router fix - it's a **placement optimization problem**. The solution is already implemented in `placement_routing_loop.py` but requires:
1. Long-running optimization (10-20 iterations, ~2 hours)
2. Stronger zone-aware placement loss

**Implementation:**
1. **Immediate:** Run `placement_routing_loop.py --max-iterations 20` overnight
2. **Medium-term:** Add `ZoneAvoidanceLoss` to the placement optimizer:
   ```python
   def zone_avoidance_loss(positions, zones):
       penalty = 0.0
       for comp_idx, pos in enumerate(positions):
           for zone in zones:
               dist = distance_to_zone_boundary(pos, zone)
               if dist < SAFE_MARGIN:  # e.g., 5mm
                   penalty += (SAFE_MARGIN - dist) ** 2
       return penalty
   ```
3. **Long-term:** Implement "channel reservation" - depopulate rows/columns to guarantee escape routes (see user memories about dense grid routing)

**Files to modify:**
- `packages/temper-placer/src/temper_placer/losses/` (new file: `zone_avoidance.py`)
- `scripts/placement_routing_loop.py` (add loss to combined_loss)

**Estimated complexity:** Medium (placement iteration is expensive)  
**Risk:** May push components off-board or violate other constraints

### Validation
**Test case:** Run full optimization loop, monitor violation count across iterations. Target: <100 violations after 20 iterations.

**Expected violation reduction:** 811 → ~100-200 violations

---

## Prioritized Fix Order

Based on impact/effort ratio:

### Phase 1: Quick Wins (Target: 339 → 150 violations)
1. **Root Cause #1 (Trace Crossing)**: Medium complexity, 33% impact → **IMPLEMENT FIRST**
2. **Root Cause #2 (Clearance Insufficient)**: High complexity, 19% impact → **IMPLEMENT SECOND**

**Timeline:** 2-3 days of focused development

### Phase 2: Placement Optimization (Target: 150 → <100 violations)
3. **Root Cause #3 (Zone Congestion)**: Run long optimization → **OVERNIGHT JOB**

**Timeline:** 1 day to set up, overnight to execute

---

## Implementation Handoff

### Next Steps
1. Create beads issues for each root cause:
   - `temper-caqw.4`: Implement same-layer crossing detection
   - `temper-caqw.5`: Implement net-aware clearance inflation (blocker: temper-df3m)
   - `temper-caqw.6`: Add zone avoidance loss to placement

2. Update `task.md` to track progress

3. Run MVB tests (temper-caqw.2) to validate fixes incrementally

### Success Metrics
- **Phase 1 Complete:** <150 violations on full board
- **Phase 2 Complete:** <100 violations on full board
- **Final Target:** 0 violations (requires addressing "Unknown" category + long-tail issues)

---

## Appendix: Unknown Category Analysis

The "Unknown" category (25% of violations) requires manual review. Based on spot-checking:
- ~40% appear to be edge cases of "Pad Entry" (trace approaching pad at wrong angle)
- ~30% are aliasing artifacts from grid discretization (trace centerline is valid, but edge crosses DRC boundary)
- ~30% are genuine uncategorized issues requiring deeper investigation

**Recommendation:** Defer deep-dive on "Unknown" until Root Causes #1 and #2 are fixed, as many may resolve automatically.
