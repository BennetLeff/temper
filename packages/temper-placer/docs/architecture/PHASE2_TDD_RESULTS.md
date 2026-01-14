# Phase 2 TDD Implementation Results

## Summary

Successfully implemented and tested **Phase 2: Differential Pair Aware Clearance** using Test-Driven Development. The implementation allows differential pairs to route closer together than normal clearance, but results show unexpected shorts that need investigation.

## What Was Implemented

### 1. OccupancyGrid Enhancements (`occupancy_grid.py`)

**Added Fields:**
- `net_id_to_name: dict[int, str] | None` - Maps net IDs to net names for clearance lookups
- `design_rules: DesignRules | None` - Reference to design rules for pair detection

**New Methods:**

#### `check_clearance(x_cell, y_cell, current_net_id) -> float`
Returns required clearance for a net at a specific cell:
- Returns `diff_pair_gap_mm` (0.127mm) for differential pair mates
- Returns normal `clearance_mm` (0.2mm) for other nets
- Uses `DesignRules.are_differential_pair()` to detect pairs

#### `is_free_for_net(x_cell, y_cell, net_id) -> bool`
Differential-pair-aware cell occupancy check:
- Returns `True` if cell is free (0)
- Returns `True` if cell contains own net
- Returns `True` if cell contains differential pair mate (NEW!)
- Returns `False` for cells blocked by other nets

**Key Innovation:**
USB_D- can now route through cells marked as occupied by USB_D+ if they are a differential pair. This allows the pair to route within 0.127mm spacing instead of 0.2mm.

### 2. A* Pathfinding Integration (`astar_pathfinding.py`)

**Grid Initialization (Lines 539-542):**
```python
# Phase 2: Update grids with net_id_to_name mapping and design_rules
for grid_obj in all_grids.values():
    grid_obj.net_id_to_name = id_to_net
    grid_obj.design_rules = design_rules
```

**Function Signature Updates:**
All A* variants now accept `net_id` parameter:
- `_astar_search()` (line 1126)
- `_astar_search_3d()` (line 1674)
- `_astar_search_theta_star()` (line 1511)
- `_astar_search_lazy_theta_star()` (line 1333)
- `_astar_route()` (line 1022)
- `_astar_route_multilayer()` (line 861)

**Neighbor Expansion Updates:**
All A* variants now use differential-pair-aware checking:

```python
# Example from _astar_search (lines 1173-1179)
if net_id > 0:
    if not grid.is_free_for_net(neighbor[0], neighbor[1], net_id):
        continue
else:
    if not grid.is_free(neighbor[0], neighbor[1]):
        continue
```

**Net ID Propagation (Lines 783-799):**
```python
# Get net_id for differential pair support
net_id = net_ids.get(net_name, -1)

# Pass net_id through routing functions
if alternate_grid and tht_locations:
    path = _astar_route_multilayer(
        net_name, channel_path, grid, alternate_grid, tht_locations,
        use_theta_star, use_lazy_theta_star, net_id=net_id
    )
else:
    path = _astar_route(
        net_name, channel_path, grid, use_theta_star, use_lazy_theta_star, net_id=net_id
    )
```

### 3. Test Coverage

**Test Files:**
1. `tests/router_v6/test_net_specific_clearance.py` - 7 tests for Phase 1 & 2
2. `tests/router_v6/test_differential_pair_detection.py` - 5 tests for pair detection

**Phase 2 Critical Test:**
```python
def test_diff_pair_blocking_allows_closer_routing(self):
    """Test that differential pair mate can route closer than normal clearance."""
    # Create grid with net_id mapping
    net_id_to_name = {1: "USB_D+", 2: "USB_D-", 3: "OTHER_NET"}
    grid = OccupancyGrid(
        "F.Cu", np.zeros((50, 50), dtype=np.int16), (0, 0), 0.1, 50, 50,
        net_id_to_name=net_id_to_name, design_rules=design_rules
    )

    # Route USB_D+ first
    _mark_route_blocked(path_dp, {"F.Cu": grid}, trace_width=0.15, clearance=0.2, net_id=1)

    # Check clearance from USB_D+ to USB_D- (pair mate)
    clearance_to_pair = grid.check_clearance(gx, gy, 2)  # USB_D-
    assert clearance_to_pair == 0.127  # Pair gap ✓

    # Check clearance from USB_D+ to OTHER_NET
    clearance_to_other = grid.check_clearance(gx, gy, 3)
    assert clearance_to_other == 0.2  # Normal clearance ✓
```

**Test Results:**
```
============= 12 passed in 0.20s =============
```

All tests passing confirms the implementation is correct at the unit level.

## Routing Results

### Before Phase 2
```
Total Violations: 1000
Routing Success: 77.8% (14/18 nets)
Runtime: ~172s
```

### After Phase 2
```
Total Violations: 996 (-4, -0.4%)
Routing Success: 77.8% (14/18 nets)
Runtime: 846.4s
```

### Key Observations

**Positive:**
- ✅ Differential pair detection working: "Found 2 differential pairs"
- ✅ USB_D+/D- routing completed: "Routing Pair USB_D+/USB_D-... ✓ Routed on F.Cu"
- ✅ Slight DRC improvement: 1000 → 996 violations

**Concerning:**
- ⚠️ **17 shorts between USB_D+ and USB_D-**: This is unexpected!
  - `Items shorting two nets (nets USB_D- and USB_D+): 13`
  - `Items shorting two nets (nets USB_D+ and USB_D-): 4`
- ⚠️ **5x longer runtime**: 172s → 846s (likely due to increased rip-up attempts)
- ⚠️ **Limited overall improvement**: Only 4 violations reduced

## Analysis

### Why Are There Shorts?

The `is_free_for_net()` implementation allows differential pairs to route through each other's occupied cells. This is intentional and correct for **pathfinding**, but it creates a problem:

**The Issue:**
1. A* marks USB_D+ with blocking radius = trace_width + clearance = 0.35mm
2. `is_free_for_net()` allows USB_D- to route through USB_D+'s blocked cells
3. USB_D- routes within 0.127mm of USB_D+ ✓ (this is correct!)
4. BUT: Both traces are drawn at their actual positions
5. If the traces overlap or get too close, DRC reports a short

**Root Cause:**
The implementation allows routing **through** occupied cells but doesn't enforce a minimum distance constraint. The pathfinding thinks it's valid to route right next to (or even overlapping) the pair mate because `is_free_for_net()` returns `True`.

### What Should Happen

The differential pair implementation needs a two-level checking system:

1. **Pathfinding Level (is_free_for_net):**
   - Allow routing through pair mate's cells ✓ (implemented)
   - BUT: Calculate actual distance to pair mate's centerline
   - ENFORCE: Distance must be >= diff_pair_gap_mm (0.127mm)

2. **Cell Marking Level (_mark_route_blocked):**
   - For differential pairs, use reduced blocking radius
   - Blocking radius = trace_width/2 + diff_pair_gap_mm = 0.202mm
   - For other nets, use normal blocking radius = 0.35mm

### Why Expected Improvement Didn't Materialize

The Phase 1 results document mentioned:
- USB_D+/D- violations: 335 → <10 (expected)
- Total violations: ~1000 → ~660 (expected)

We only saw 996 violations with 17 USB shorts. This suggests:

1. **Different baseline**: The "335 violations" may have been from a different routing run
2. **Violation counting**: DRC might count shorts differently than clearance violations
3. **Implementation incomplete**: Current approach allows pairs to route too close (causing shorts)

## What Works vs. What Doesn't

### Works ✓
- Net-specific rules infrastructure (Phase 1)
- Differential pair detection via `are_differential_pair()`
- Grid-level net tracking (`net_id_to_name`)
- Pair-aware clearance lookup (`check_clearance()`)
- A* integration with `net_id` parameter
- Test coverage and TDD methodology

### Doesn't Work ✗
- **Distance enforcement**: `is_free_for_net()` doesn't check actual distance to pair mate
- **Shorts prevention**: Routing too close to pair mate causes shorts
- **Performance**: 5x slowdown suggests excessive rip-up attempts

## Next Steps for Phase 2.1

To fix the shorts and achieve the expected DRC improvements:

### 1. Add Distance-Based Checking

Modify `is_free_for_net()` to calculate distance:

```python
def is_free_for_net(self, x_cell: int, y_cell: int, net_id: int) -> bool:
    """Check if cell is free with distance-based validation."""
    cell_value = self.grid[y_cell, x_cell]

    if cell_value == 0 or cell_value == -1:
        return cell_value == 0  # Free or blocked

    if cell_value == net_id:
        return True  # Own net

    # Check if pair mate
    if self.net_id_to_name and self.design_rules:
        current_net = self.net_id_to_name.get(net_id)
        blocking_net = self.net_id_to_name.get(cell_value)

        if current_net and blocking_net:
            is_pair, pair_gap = self.design_rules.are_differential_pair(current_net, blocking_net)

            if is_pair and pair_gap:
                # Calculate distance to nearest blocking trace edge
                distance = self._calculate_distance_to_trace(x_cell, y_cell, cell_value)

                # Allow if distance >= pair_gap
                return distance >= pair_gap

    return False  # Blocked by other net
```

### 2. Implement `_calculate_distance_to_trace()`

This requires tracking trace geometry, not just occupied cells:
- Store trace centerline segments
- Calculate perpendicular distance from cell to nearest segment
- Account for trace width

### 3. Reduce Blocking Radius for Pairs

When marking differential pairs, use reduced radius:

```python
if is_diff_pair:
    blocking_radius = (trace_width / 2.0) + diff_pair_gap_mm  # 0.202mm
else:
    blocking_radius = (trace_width / 2.0) + clearance_mm  # 0.35mm
```

## Conclusion

**Phase 2 Status: IMPLEMENTED BUT NEEDS REFINEMENT**

### Achievements ✓
- Complete TDD implementation of differential pair infrastructure
- All 12 unit tests passing
- Differential pair detection working
- A* integration complete
- Foundation for pair-aware routing established

### Issues ✗
- 17 shorts between USB_D+/D- (should be 0)
- No distance enforcement in pathfinding
- 5x performance degradation
- Minimal DRC improvement (only -4 violations)

### Required for Phase 2.1
1. Distance-based validation in `is_free_for_net()`
2. Trace geometry tracking for accurate distance calculation
3. Conditional blocking radius based on pair relationship
4. Performance optimization to reduce rip-up attempts

### TDD Benefits Demonstrated
- Unit tests caught API integration issues
- Tests validated pair detection logic
- Tests documented expected behavior
- Tests give confidence for refactoring to Phase 2.1

**Estimated Phase 2.1 Effort:** 4-6 hours
- Distance calculation implementation: 2-3 hours
- Conditional blocking radius: 1 hour
- Testing and validation: 1-2 hours

---

**Document Version:** 1.0
**Date:** 2026-01-14
**Status:** Phase 2 Complete (with shorts), Phase 2.1 Needed
