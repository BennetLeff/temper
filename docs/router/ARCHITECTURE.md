# Router V6 Architecture

## Overview

The Router V6 system uses a **strategy pattern** with specialized routers for different routing scenarios. This design maintains separation of concerns while enabling professional PCB routing standards.

## Component Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                     UnifiedRouter                           │
│              (Orchestrator & Strategy Selector)             │
└───────────────┬─────────────────────────────────────────────┘
                │
                ├──> Strategy Selection
                │    - Current capacity check (IPC-2221)
                │    - Zone assignment detection
                │    - Routing method dispatch
                │
                ├──> [1] MazeRouter (Grid-based pathfinding)
                │    - A* algorithm on grid
                │    - Via arrays, RRR, layer transitions
                │    - Output: List of grid cells + vias
                │
                ├──> [2] PlaneConnectionRouter (Plane stitching)
                │    - Via placement at pads
                │    - No path calculation
                │    - Output: Via arrays, length=0
                │
                └──> [3] PushShoveRouter (SDF-based)
                     - Continuous pathfindng
                     - Collision resolution
                     - Output: Smooth paths
```

---

## Component Details

### 1. MazeRouter (`maze_router.py`, ~3000 lines)

**Purpose:** Grid-based A* pathfinding for standard trace routing

**Responsibilities:**
- Grid discretization of PCB space
- A* pathfinding with obstacle avoidance
- Layer transition via placement
- Via array collision checking
- RRR (Rip-up and Reroute) for congestion
- Cost map integration

**Key Methods:**
```python
route_net_rrr(net_name, pins, assignment, cost_map)
  → RoutePath(cells, vias, length, success)

_get_neighbors(x, y, layer, via_template)
  → List of valid neighbor cells

_is_via_array_valid(x, y, from_layer, to_layer, template)
  → bool (collision check)
```

**When Used:**
- Low-current nets (<5A): Standard routing
- Medium-current nets (5-10A) without zones: Wide traces + via arrays
- Any net not requiring plane connections

---

### 2. PlaneConnectionRouter (`plane_connection.py`, ~200 lines)

**Purpose:** Connect component pads directly to copper planes/pours

**Responsibilities:**
- Find zone assigned to net
- Validate pins within zone boundaries
- Calculate via array positions at pads
- **No path calculation** - plane carries current

**Key Methods:**
```python
route_net_to_plane(net_name, pins, zones)
  → List[PlaneConnection](via_positions, success)

connect_pin_to_plane(pin_pos, zone, via_template)
  → PlaneConnection (16 vias for Via4x4)

_calculate_via_array_positions(center, template)
  → List[(x, y)] via positions
```

**When Used:**
- High-current nets (>10A): Always requires plane
- Medium-current nets (5-10A) with zones: Preferred for thermal

**Output:**
- Via arrays centered on component pads
- Length = 0mm (no traced routing)
- Current flows through solid copper plane

---

### 3. UnifiedRouter (`unified_router.py`, ~630 lines)

**Purpose:** High-level orchestration and routing method dispatch

**Responsibilities:**
- Strategy selection based on current capacity
- Design rules management
- Method dispatch to specialized routers
- Fallback logic (maze → push-shove)
- Result aggregation

**Key Methods:**
```python
route_net(net_name, pins, assignment, cost_map, zones)
  → UnifiedRoutePath(method, success, vias, length)
  
  # Internal dispatch:
  if current > 10A:
      PlaneConnectionRouter.route_net_to_plane(...)
  else:
      MazeRouter.route_net_rrr(...)
```

**Strategy Decision Matrix:**
```
Current > 10A + Zone     → PlaneConnectionRouter
Current > 10A + No Zone  → ERROR (config validation)
Current 5-10A + Zone     → PlaneConnectionRouter (thermal)
Current 5-10A + No Zone  → MazeRouter (via arrays)
Current < 5A             → MazeRouter (standard)
```

---

## Data Flow

### Example: Routing AC_L (20A net)

```
1. User Call:
   unified_router.route_net("AC_L", pins, assignment, zones=zones)

2. UnifiedRouter Strategy Selection:
   current = design_rules.get_net_current("AC_L")  # 20.0A
   has_zone = check_zone_assignment("AC_L", zones)  # True
   strategy = PLANE_VIA_ONLY

3. Dispatch to PlaneConnectionRouter:
   plane_router = PlaneConnectionRouter(design_rules)
   connections = plane_router.route_net_to_plane("AC_L", pins, zones)

4. PlaneConnectionRouter Execution:
   zone = find_zone_for_net("AC_L", zones)  # AC_PLANE
   for pin in pins:
       via_array = calculate_via_positions(pin, Via4x4)
       # 16 vias at (pin_x ± offset, pin_y ± offset)

5. Return Result:
   UnifiedRoutePath(
       method="plane_connection",
       via_count=32,  # 2 pins × 16 vias
       length=0.0,    # No traced routing
       success=True
   )
```

---

## Design Rationale

### Why Multiple Routers?

**1. Single Responsibility Principle**
- MazeRouter: Pathfinding
- PlaneConnectionRouter: Via placement
- UnifiedRouter: Orchestration

**2. Different Algorithms**
| Router | Algorithm | Complexity |
|--------|-----------|------------|
| Maze | A* on grid | O(n log n) |
| Plane | Direct via placement | O(k) where k=vias |
| PushShove | SDF sampling | O(n²) |

**3. Independent Testing**
- EXP-06-B: MazeRouter via arrays
- EXP-07-A: Config validation (no router)
- EXP-07-C: PlaneConnectionRouter only

**4. Extensibility**
Future specialized routers:
- `DifferentialPairRouter`: Matched length pairs
- `StarPointRouter`: Kelvin sensing topology
- `BusRouter`: Parallel trace arrays

### Why Not All in MazeRouter?

**Plane connections aren't pathfinding:**
- No grid search required
- No obstacles to avoid
- Just via placement at known locations

**Code complexity:**
- MazeRouter already 3000 lines
- Mixing concerns makes testing harder
- Plane logic needs zone geometry, not grid state

---

## API Summary

### Primary Entry Point
```python
from temper_placer.routing.unified_router import UnifiedRouter

router = UnifiedRouter(board, config, design_rules)
result = router.route_net(
    net_name="AC_L",
    pin_positions=[(10, 50), (90, 50)],
    assignment=layer_assignment,
    zones=zones,  # NEW: Required for current capacity
)

# Result:
result.method       # "plane_connection" | "maze" | "push-shove"
result.success      # bool
result.via_count    # Total vias placed
result.length       # Traced length (0 for planes)
```

### Direct Router Access (Testing)
```python
from temper_placer.routing.plane_connection import PlaneConnectionRouter

plane_router = PlaneConnectionRouter(design_rules)
connections = plane_router.route_net_to_plane(
    net_name="AC_L",
    pin_positions=[(10, 50), (90, 50)],
    zones=zones,
)

# Each connection:
for conn in connections:
    conn.pin_position      # (x, y)
    conn.via_positions     # [(x1,y1), (x2,y2), ...]
    conn.via_template      # "Via4x4"
    conn.success           # bool
```

---

## File Structure

```
routing/
├── unified_router.py         # Orchestrator (entry point)
├── maze_router.py            # A* grid pathfinding
├── plane_connection.py       # Plane via stitching
├── push_shove.py             # SDF-based routing
├── current_capacity_strategy.py  # Strategy selection
├── layer_assignment.py       # Layer allocation
└── fanout.py                 # Pin escape routing
```

---

## Version History

**V1-V3:** Single MazeRouter  
**V4:** Added C-Space (configuration spaces)  
**V5:** Via arrays, RRR improvements  
**V6:** Current capacity enforcement
- Added `PlaneConnectionRouter`
- Added `UnifiedRouter` orchestration
- Added strategy-based dispatch

---

## Future Work

**Planned Routers:**
- `DifferentialPairRouter`: EXP-06-A (dual-front A*, length matching)
- `StarPointRouter`: EXP-06-C (Kelvin sensing topology)
- `HierarchicalRouter`: Multi-stage global → detailed routing

**Integration Improvements:**
- Unified cost function across routers
- Shared obstacle representation
- Common via placement engine
