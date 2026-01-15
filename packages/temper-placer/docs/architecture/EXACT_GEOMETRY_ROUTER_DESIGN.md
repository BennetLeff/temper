# Exact Geometry Router - Design Document

## Overview

An exact geometry router replaces grid-based A* routing with continuous coordinate pathfinding using visibility graphs. This eliminates DRC errors caused by grid quantization.

## Current Status: Prototype

A prototype exists in `exact_geometry_router.py` but has a fundamental issue with dense IC footprints where pads are < 1mm apart.

## The Dense Footprint Problem

```
IC Footprint (0.65mm pitch):
┌─────────────────┐
│  ●   ●   ●   ●  │   ● = pad (0.4mm diameter)
│ CLK MOSI MISO CS│   spacing = 0.65mm
└─────────────────┘

After inflation (0.725mm = pad_radius + clearance + trace_radius):
┌─────────────────────────────────────┐
│  ████████████████████████████████   │
│  █ overlapping obstacle region █    │   
│  ████████████████████████████████   │
└─────────────────────────────────────┘

Result: All pads are INSIDE obstacles → no valid path exists
```

## Solutions for Dense Footprints

### Option 1: Escape Zone (Recommended)

Create an "escape zone" around each pad that allows routing to enter/exit.

```python
def _get_obstacles_for_net(self, layer, net_name, clearance, trace_width):
    """Build obstacles with escape zones around target pads."""
    obstacles = []
    
    target_pads = self._net_pads.get(net_name, [])
    escape_radius = 1.5  # mm - larger than typical footprint pitch
    
    for obs_net, obs_pads in self._net_pads.items():
        if obs_net == net_name:
            continue
        
        for pad_pos in obs_pads:
            # Check if this pad is within escape zone of any target pad
            near_target = any(
                self._distance(pad_pos, target) < escape_radius
                for target in target_pads
            )
            
            if near_target:
                # Use smaller inflation for nearby pads
                inflation = clearance  # No trace_width/2
            else:
                # Standard inflation
                inflation = clearance + trace_width / 2
            
            poly = Point(pad_pos).buffer(0.4 + inflation)  # pad_radius + inflation
            obstacles.append(poly)
    
    return obstacles
```

### Option 2: Two-Phase Routing

1. **Phase 1: Escape routing** - Route from pad to escape point (outside dense area)
2. **Phase 2: Channel routing** - Route between escape points using visibility graph

```python
def route_net(self, net_name, layer, pads):
    """Two-phase routing for dense footprints."""
    escape_points = []
    escape_segments = []
    
    # Phase 1: Find escape points for each pad
    for pad in pads:
        escape = self._find_escape_point(pad, layer)
        escape_points.append(escape)
        
        # Direct segment from pad to escape
        seg = ExactSegment(pad, escape, trace_width, net_name, layer)
        escape_segments.append(seg)
    
    # Phase 2: Route between escape points
    channel_segments = self._route_visibility_graph(escape_points, obstacles)
    
    return ExactRoutePath(
        segments=escape_segments + channel_segments,
        ...
    )
```

### Option 3: Integrate with Existing Grid Router

Use exact geometry only for **post-processing**:

1. Grid-based A* produces initial route (with quantization errors)
2. Exact geometry router **refines** the path to fix clearance violations
3. Best of both worlds: fast initial routing + DRC-clean output

```python
def refine_route(self, grid_route: RoutePath) -> ExactRoutePath:
    """Refine grid-based route to fix clearance violations."""
    refined_coords = []
    
    for i in range(len(grid_route.coordinates) - 1):
        p1, p2 = grid_route.coordinates[i], grid_route.coordinates[i+1]
        
        # Check clearance
        seg = LineString([p1, p2])
        if self._has_clearance_violation(seg):
            # Micro-adjust segment to fix violation
            adjusted = self._micro_adjust(seg)
            refined_coords.extend(adjusted)
        else:
            refined_coords.extend([p1, p2])
    
    return ExactRoutePath(
        coordinates=refined_coords,
        layer_name=grid_route.layer_name,
        ...
    )
```

## Pipeline Integration

### Where It Fits

```
Stage 0: Parse PCB
    │
Stage 1: Escape Vias  
    │
Stage 2: Channel Analysis
    │       └── routing_spaces, occupancy_grids
    │
Stage 3: Topological Routing (SAT)
    │       └── net ordering, channel assignments
    │
Stage 4: Geometric Realization
    │
    ├── Option A: Grid-Based A* (current)
    │       └── Fast, 100% completion, ~100 DRC errors
    │
    ├── Option B: Exact Geometry (visibility graph)
    │       └── Slow, needs escape zones, 0 DRC errors
    │
    └── Option C: Hybrid (A* + refinement)
            └── Fast initial, refined output, ~10 DRC errors
```

### Integration Code

```python
# In pipeline.py _run_stage4():

if self.use_exact_geometry:
    # Option B: Full exact geometry
    from .exact_geometry_router import ExactGeometryRouter
    
    router = ExactGeometryRouter(
        pcb=pcb,
        design_rules=pcb.design_rules,
        routing_spaces=stage2.routing_spaces,  # Use Stage 2 obstacles
    )
    exact_paths = router.route_all(channel_mapping)
    pathfinding_result = self._convert_exact_to_routepath(exact_paths)

elif self.use_hybrid:
    # Option C: Grid + refinement
    pathfinding_result = run_astar_pathfinding(...)  # Grid-based
    
    from .exact_geometry_router import refine_routes
    pathfinding_result = refine_routes(
        pathfinding_result,
        pcb.design_rules,
    )

else:
    # Option A: Grid-based only (current default)
    pathfinding_result = run_astar_pathfinding(...)
```

## Performance Comparison

| Metric | Grid A* | Exact Geometry | Hybrid |
|--------|---------|----------------|--------|
| **Speed** | ~25s | ~2-5min (est.) | ~30s |
| **DRC Errors** | ~100 | 0 | ~10 |
| **Memory** | 50MB | 100MB | 60MB |
| **Dense Footprints** | Works | Needs escape zones | Works |
| **Implementation** | Done | Prototype | Not started |

## Recommendation

**For Temper project**: Use **Option C (Hybrid)** when implemented.

Current grid-based router achieves 100% routing with 101 DRC errors.
Most errors are cosmetic (solder_mask_bridge) or acceptable (power crossings).

A hybrid approach would:
1. Keep fast routing (grid A*)
2. Fix real violations (clearance, shorts)
3. Skip unfixable issues (power crossings)

Estimated effort: 1-2 weeks for Option C vs 3-4 weeks for Option B.

## Files

- `exact_geometry_router.py` - Prototype visibility graph router
- `path_simplifier.py` - Existing path simplification (could be extended)
- `clearance_check.py` - Existing clearance checking

## Next Steps

1. [ ] Implement escape zone handling for dense footprints
2. [ ] Benchmark visibility graph performance on Temper board
3. [ ] Prototype hybrid refinement approach
4. [ ] Compare DRC results across all three options

---

**Author**: Claude (AI Agent)  
**Date**: 2026-01-15  
**Status**: Design Document
