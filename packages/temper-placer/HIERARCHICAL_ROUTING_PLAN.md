#!/usr/bin/env python3
"""
Hierarchical Routing Implementation Plan

**Issue**: temper-edni
**Root Cause**: Clearance masks force 50x A* visit explosion (15k visits for 300-cell routes)
**Solution**: 2-pass hierarchical routing

## Implementation Strategy

### Pass 1: Coarse Routing (No Clearance)
- Route without clearance constraints
- Fast A* search finds skeleton path
- Result: Grid coordinates of ideal route

### Pass 2: Fine Routing (With Clearance)
- Use coarse path as A* heuristic guide
- Apply clearance constraints
- If fails, widen corridor along coarse path and retry

## Code Changes

### 1. Add `route_net_hierarchical()` to MazeRouter
```python
def route_net_hierarchical(
    self,
    net_name: str,
    pin_positions: list[tuple[float, float]],
    assignment,
    **kwargs
) -> RoutePath:
    \"\"\"2-pass hierarchical routing for clearance-constrained nets.\"\"\"
    
    # Pass 1: Route without clearance (fast)
    coarse_path = self._route_coarse(net_name, pin_positions, assignment, **kwargs)
    
    if not coarse_path or not coarse_path.success:
        # Coarse routing failed - fallback to standard MST
        return self.route_net_mst(net_name, pin_positions, assignment, **kwargs)
    
    # Pass 2: Route with clearance, guided by coarse path
    fine_path = self._route_fine_guided(
        net_name, pin_positions, assignment,
        guide_path=coarse_path,
        **kwargs
    )
    
    if fine_path and fine_path.success:
        return fine_path
    
    # Pass 2 failed - widen corridor and retry
    fine_path = self._route_fine_corridor(
        net_name, pin_positions, assignment,
        guide_path=coarse_path,
        corridor_width_mm=5.0,  # 5mm corridor
        **kwargs
    )
    
    return fine_path if fine_path and fine_path.success else coarse_path
```

### 2. Helper: `_route_coarse()`
- Temporarily disable clearance mask generation
- Call `route_net_mst()` with `clearance_mm=0.0`
- Return skeleton path

### 3. Helper: `_route_fine_guided()`
- Modify A* heuristic to favor cells near guide_path
- h_modified = h_original - distance_to_guide_path * bias_factor
- Bias factor ~0.5 to gently guide without forcing

### 4. Helper: `_route_fine_corridor()`
- Clear clearance mask within corridor_width of guide_path
- Call `route_net_mst()` normally
- Acts as fallback if guided routing fails

## Testing Plan
1. Test with EXP-16 (expect <500ms vs 21s)
2. Test with test_astar_05 clearance mask case (expect <50ms vs 195ms)
3. Verify no regression on clean grids

## Estimated LOC
- route_net_hierarchical: ~40 lines
- _route_coarse: ~20 lines
- _route_fine_guided: ~60 lines (heuristic modification)
- _route_fine_corridor: ~30 lines
- Total: ~150 lines
