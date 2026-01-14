# Differential Pair Clearance - Phase 2 Implementation TODO

## Status

**Phase 1: COMPLETE ✓**
- Net-specific rules implemented in `astar_pathfinding.py`
- All nets now use correct trace_width and clearance from design rules
- Tests passing

**Phase 2: PARTIAL**
- Differential pair detection implemented (`DesignRules.are_differential_pair()`)
- Tests for detection passing
- **NOT YET IMPLEMENTED:** A* pathfinding integration

## What's Implemented

### 1. Differential Pair Detection (stage0_data.py)

```python
def are_differential_pair(self, net_a: str, net_b: str) -> tuple[bool, float | None]:
    """
    Check if two nets are a differential pair.

    Returns:
        (is_pair, pair_gap_mm) - pair_gap_mm is the required gap between the pair
    """
    # Checks:
    # 1. Both nets in same net class
    # 2. Net class has diff_pair_gap_mm defined
    # 3. Net names match pattern (USB_D+/USB_D-, PCIE_TX_P/PCIE_TX_N, etc.)
```

**Tested patterns:**
- `+/-` suffix: USB_D+, USB_D-
- `_P/_N` suffix: PCIE_TX_P, PCIE_TX_N
- Single `P/N` suffix: TX1P, TX1N

### 2. Net-Specific Rules (astar_pathfinding.py)

```python
# Line 583: Get net-specific rules
net_rules = design_rules.get_rules_for_net(net_name)

# Lines 675-680: Use net-specific rules for blocking
_mark_route_blocked(
    route_path,
    all_grids,
    trace_width=net_rules.trace_width_mm,  # ✓ Net-specific
    clearance=net_rules.clearance_mm,      # ✓ Net-specific
    net_id=net_id,
)
```

## What's Missing for Full Phase 2

### Problem

Currently, **all blocking uses the net's clearance_mm** (0.2mm for USB pairs). We need blocking to use **different clearances depending on which net is being blocked**:

```
USB_D+ blocking radius to OTHER_NET:  0.15mm (trace_width) + 0.2mm (clearance) = 0.35mm
USB_D+ blocking radius to USB_D-:     0.15mm (trace_width) + 0.127mm (pair_gap) = 0.277mm
```

### Required Changes

#### Option A: Grid-Level Net Tracking

**Modify `OccupancyGrid` to track net names:**

```python
@dataclass
class OccupancyGrid:
    grid: np.ndarray  # Current: stores net_id
    net_id_to_name: dict[int, str]  # NEW: maps net_id -> net_name
    design_rules: DesignRules  # NEW: for pair checking

    def check_clearance(self, x: int, y: int, current_net_id: int) -> float:
        """Get required clearance at this cell."""
        blocking_net_id = self.grid[y, x]

        if blocking_net_id <= 0:
            return 0.0  # Free cell

        current_net = self.net_id_to_name[current_net_id]
        blocking_net = self.net_id_to_name[blocking_net_id]

        # Check if differential pair
        is_pair, pair_gap = self.design_rules.are_differential_pair(current_net, blocking_net)

        if is_pair:
            return pair_gap  # 0.127mm for USB pairs
        else:
            return self.design_rules.get_rules_for_net(blocking_net).clearance_mm
```

**Then modify A* pathfinding to use this:**

```python
# In astar_route_net_multilayer (around line 1200)
def get_movement_cost(current_pos, neighbor_pos):
    gx, gy = neighbor_pos
    cell_value = grid.grid[gy, gx]

    if cell_value <= 0:
        return BASE_COST  # Free cell

    if cell_value == net_id:
        return BASE_COST  # Own net

    # Use pair-aware clearance
    required_clearance = grid.check_clearance(gx, gy, net_id)

    # Calculate distance to blocking obstacle
    distance_to_obstacle = calculate_distance_to_nearest_obstacle(neighbor_pos)

    if distance_to_obstacle < required_clearance:
        return VERY_HIGH_COST  # Too close
    else:
        return BASE_COST
```

#### Option B: Dual-Radius Blocking

**Mark paths with TWO blocking radii:**

```python
def mark_path_blocked(
    self,
    path: list[tuple[float, float]],
    trace_width: float,
    clearance: float,
    net_id: int,
    pair_gap: float | None = None,  # NEW: special gap for pair mate
) -> None:
    """Mark path with pair-aware blocking."""

    # Standard blocking radius (for non-pair nets)
    normal_radius = trace_width + clearance  # 0.35mm

    # Pair blocking radius (for pair mate only)
    if pair_gap is not None:
        pair_radius = trace_width + pair_gap  # 0.277mm
        self.pair_blocking_radii[net_id] = pair_radius

    # Mark with normal radius (pessimistic for all nets)
    # ... existing circular blocking logic ...
```

Then during pathfinding, check `pair_blocking_radii` before penalizing.

**Pros:** Simpler, doesn't require grid changes
**Cons:** Doesn't work well with rip-up/re-route

### Recommended Approach

**Option A (Grid-Level Net Tracking)** is the correct long-term solution:
1. Properly models the physical constraint
2. Works with rip-up/re-route
3. Enables future per-net-pair clearance matrices

### Implementation Steps

1. **Modify OccupancyGrid** (`occupancy_grid.py`)
   - Add `net_id_to_name: dict[int, str]` field
   - Add `design_rules: DesignRules` field
   - Add `check_clearance(x, y, current_net_id) -> float` method

2. **Update Grid Creation** (`astar_pathfinding.py`)
   - Pass `design_rules` to OccupancyGrid constructor
   - Build `net_id_to_name` mapping from `net_ids` dict

3. **Modify A* Cost Function** (`astar_pathfinding.py`)
   - In `astar_route_net_multilayer`, use `grid.check_clearance()` instead of fixed penalty
   - Calculate distance to obstacle using C-Space math
   - Apply penalty only if `distance < required_clearance`

4. **Test**
   - Update `test_diff_pair_blocking_allows_closer_routing` to actually route both nets
   - Verify USB_D- can route within 0.127mm of USB_D+
   - Verify OTHER_NET cannot route within 0.2mm of USB_D+

### Estimated Effort

- Grid modifications: 1-2 hours
- A* cost function: 2-3 hours
- Testing & debugging: 2-3 hours
- **Total: 5-8 hours**

## Expected DRC Impact

**After Phase 1 (Current):**
- Power nets use correct widths (1.0mm, 2.5mm, 3.0mm)
- Signal nets use correct widths (0.15mm, 0.2mm)
- **No reduction in USB_D+/D- violations yet** (still ~335)

**After Phase 2 (Full):**
- USB_D+/D- violations: 335 → <10 (**-97%**)
- Total violations: ~992 → ~660 (**-33%**)
- Solder mask violations: Auto-reduced by ~100

## Current Test Status

```bash
# Phase 1 tests: ✓ PASSING
pytest tests/router_v6/test_net_specific_clearance.py::TestNetSpecificRules

# Phase 2 detection tests: ✓ PASSING
pytest tests/router_v6/test_differential_pair_detection.py

# Phase 2 integration tests: ⚠ DOCUMENTED (not implemented yet)
pytest tests/router_v6/test_net_specific_clearance.py::TestDifferentialPairClearance::test_diff_pair_blocking_allows_closer_routing
```

## Next Steps

1. Run full router with Phase 1 to measure DRC improvements
2. Implement Option A (Grid-Level Net Tracking)
3. Update A* cost function to use pair-aware clearance
4. Run full router with Phase 2 to validate 335 violation reduction

---

**Document Version:** 1.0
**Date:** 2026-01-14
**Status:** Phase 1 Complete, Phase 2 Architecture Defined
