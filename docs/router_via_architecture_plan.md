# Router Via & Layer Management Architecture Plan

## Problem Analysis

### Current Issues (55 via-related violations)
1. **Vias too close together**: 0.4mm spacing on QFN-56 pads (need ≥1mm)
2. **Via-to-track shorts**: Vias placed without considering nearby tracks
3. **Hole clearance violations**: Via drills violating pad/track clearances
4. **Post-process insertion**: Vias added AFTER routing, causing conflicts

### Root Causes
The current architecture has **fundamental design flaws**:

```
CURRENT (BROKEN):
1. Router plans paths on layers → produces tracks
2. Export script notices layer mismatch → blindly inserts vias at pads
3. DRC finds via-via, via-track, via-hole violations
4. No feedback loop - router never knew vias would exist
```

This is a **bandaid approach** - vias should be **first-class routing primitives**, not post-processing hacks.

---

## Professional PCB Router Architecture

### How Altium/KiCad/Cadence Do It

```
PROFESSIONAL APPROACH:
┌─────────────────────────────────────────────────────────┐
│ Stage 1: Global Routing (Topology)                     │
│  - Assign nets to layers                               │
│  - Plan via locations (NOT pad locations!)             │
│  - Use multi-layer pathfinding (3D graph)              │
│  - Cost function: wire length + via count + congestion │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Stage 2: Detailed Routing (Geometry)                   │
│  - Route tracks with exact geometry                    │
│  - Place vias at planned locations                     │
│  - Vias are obstacles for other nets                   │
│  - Layer transitions only at via locations             │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│ Stage 3: Cleanup & Optimization                        │
│  - Shove/push nets to resolve conflicts               │
│  - Minimize via count (via stitching)                 │
│  - Smooth paths                                        │
│  - DRC-aware micro-adjustments                         │
└─────────────────────────────────────────────────────────┐
```

---

## Proposed Architecture: Layer-Aware Exact Geometry Router

### Design Principles

1. **Vias are routing primitives, not post-process**
   - Router plans via locations during pathfinding
   - Vias have clearance zones, just like pads

2. **3D routing space (X, Y, Layer)**
   - Pathfinding operates in 3D
   - Layer changes have cost (via penalty)

3. **Via placement rules**
   - Only at "via-legal" positions (clearance from all obstacles)
   - Minimum via-to-via spacing (1.5mm for 0.4mm drill)
   - Prefer shared vias when possible

4. **Incremental obstacle updates**
   - When net N routes, its vias become obstacles for net N+1
   - Router sees via keepouts, not just pad keepouts

---

## Implementation Plan

### Phase 1: Via-Aware Data Structures (Foundation)

**1.1 Multi-Layer Routing Space**

```python
class LayerStack:
    """3D routing space: (x, y, layer)"""
    layers = ['F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu']
    
    def __init__(self):
        # Per-layer obstacle maps
        self.obstacles: dict[str, list[Polygon]] = {}
        
        # Via keepout zones (X, Y, radius) - applies to ALL layers
        self.via_keepouts: list[tuple[float, float, float]] = []
        
        # Existing vias (for reuse/sharing)
        self.placed_vias: list[Via] = []
```

**1.2 Via Clearance Model**

```python
class ViaSpec:
    """Standard via specifications"""
    diameter = 0.8      # mm - annular ring size
    drill = 0.4         # mm - hole size
    clearance = 0.2     # mm - copper clearance
    
    @property
    def keepout_radius(self) -> float:
        """Total exclusion zone for via placement"""
        # diameter/2 + clearance + safety margin
        return (self.diameter / 2) + self.clearance + 0.1
    
    @property
    def min_via_spacing(self) -> float:
        """Minimum center-to-center via spacing"""
        return 2 * self.keepout_radius  # ~1.5mm
```

**1.3 Layer Transition Graph**

```python
class LayerGraph:
    """Models legal layer transitions via THT pads and via locations"""
    
    def get_transition_points(
        self, 
        from_layer: str, 
        to_layer: str,
        near: tuple[float, float],
        radius: float = 10.0  # search radius
    ) -> list[tuple[float, float]]:
        """Find legal via placement points for layer transition.
        
        Legal locations:
        1. THT pads (connect all layers)
        2. Open space with via clearance
        3. Not in via keepout zones
        4. Within radius of current position
        """
        candidates = []
        
        # Check for nearby THT pads (best - no via needed if routing through)
        for pad in self.tht_pads:
            if self._distance(pad.pos, near) < radius:
                candidates.append((pad.pos, 0))  # cost 0 - use existing hole
        
        # Sample grid of potential via locations
        for x in range(int(near[0]-radius), int(near[0]+radius), 1):  # 1mm grid
            for y in range(int(near[1]-radius), int(near[1]+radius), 1):
                if self._is_via_legal((x, y)):
                    cost = self._via_cost((x, y), near)
                    candidates.append(((x, y), cost))
        
        return sorted(candidates, key=lambda x: x[1])
```

---

### Phase 2: 3D Pathfinding (Core Routing)

**2.1 Multi-Layer RRT**

```python
class MultiLayerRRT:
    """RRT that can change layers via vias"""
    
    def find_path(
        self,
        start: tuple[float, float, str],  # (x, y, layer)
        goal: tuple[float, float, str],
        net_name: str
    ) -> list[PathSegment]:
        """
        PathSegment = Union[
            TrackSegment(start, end, layer),
            Via(position, from_layer, to_layer)
        ]
        """
        
        # Modified RRT with layer transitions
        tree = {start: None}
        
        for _ in range(max_iterations):
            # Sample random point in 3D space
            if random.random() < 0.1:
                # 10% chance: sample on different layer
                random_point = self._sample_with_layer_change()
            else:
                random_point = self._sample_on_current_layers()
            
            # Find nearest tree node
            nearest = self._nearest_in_3d(tree, random_point)
            
            # Extend toward random point
            new_point = self._extend_3d(nearest, random_point)
            
            # Check if extension requires layer change
            if new_point.layer != nearest.layer:
                # Need via - check if legal
                via_pos = self._find_via_location(nearest, new_point)
                if via_pos is None:
                    continue  # Can't place via here
                
                # Add via + track on new layer
                tree[new_point] = (nearest, via_pos)
            else:
                # Same layer - just add track
                if not self._path_intersects_obstacles(nearest, new_point):
                    tree[new_point] = nearest
        
        # Reconstruct path with via insertion
        return self._reconstruct_path_with_vias(tree, goal)
```

**2.2 Layer-Aware A***

Alternative approach using grid-based A* in 3D:

```python
class LayerAwareAStar:
    """A* pathfinding in (x, y, layer) space"""
    
    def __init__(self):
        self.grid_size = 0.5  # mm
        self.via_cost = 5.0   # penalty for layer change
    
    def heuristic(self, node: Node3D, goal: Node3D) -> float:
        """3D Manhattan distance + layer change penalty"""
        xy_dist = abs(node.x - goal.x) + abs(node.y - goal.y)
        layer_dist = abs(self.layer_index[node.layer] - self.layer_index[goal.layer])
        return xy_dist + (layer_dist * self.via_cost)
    
    def get_neighbors(self, node: Node3D) -> list[Node3D]:
        """Adjacent cells in 3D grid"""
        neighbors = []
        
        # Same layer: 8 directions (N, NE, E, SE, S, SW, W, NW)
        for dx, dy in [(1,0), (1,1), (0,1), (-1,1), (-1,0), (-1,-1), (0,-1), (1,-1)]:
            neighbors.append(Node3D(node.x+dx, node.y+dy, node.layer))
        
        # Layer changes: only if via can be placed here
        if self._can_place_via(node.x, node.y):
            for layer in self.layers:
                if layer != node.layer:
                    neighbors.append(Node3D(node.x, node.y, layer))
        
        return [n for n in neighbors if not self._is_blocked(n)]
```

---

### Phase 3: Via Placement & Management

**3.1 Via Placement Strategy**

```python
class ViaPlanner:
    """Intelligent via placement"""
    
    def place_via(
        self,
        position: tuple[float, float],
        from_layer: str,
        to_layer: str,
        net: str
    ) -> Via | None:
        """Place via with clearance checking"""
        
        # Check clearance to all obstacles on ALL layers
        for layer in self.layers:
            obstacles = self.obstacles[layer]
            via_zone = Point(position).buffer(ViaSpec.keepout_radius)
            
            for obs in obstacles:
                if via_zone.intersects(obs):
                    return None  # Blocked
        
        # Check via-to-via spacing
        for existing_via in self.placed_vias:
            dist = self._distance(position, existing_via.position)
            if dist < ViaSpec.min_via_spacing:
                # Can we share this via?
                if existing_via.net == net:
                    return existing_via  # Reuse
                else:
                    return None  # Too close, different net
        
        # Place new via
        via = Via(
            position=position,
            diameter=ViaSpec.diameter,
            drill=ViaSpec.drill,
            layers=[from_layer, to_layer],
            net=net
        )
        
        # Add via keepout to ALL layers
        self._add_via_obstacle(via)
        self.placed_vias.append(via)
        
        return via
    
    def _add_via_obstacle(self, via: Via):
        """Add via as obstacle on all layers"""
        via_zone = Point(via.position).buffer(ViaSpec.keepout_radius)
        
        for layer in self.layers:
            self.obstacles[layer].append(via_zone)
```

**3.2 Pad-to-Layer Connection**

```python
class PadLayerConnector:
    """Handle connections between pads and routing layers"""
    
    def get_connection_point(
        self,
        pad: Pad,
        routing_layer: str
    ) -> tuple[tuple[float, float], Via | None]:
        """Get entry/exit point for pad on routing layer"""
        
        pad_layers = self._get_copper_layers(pad)
        pad_pos = pad.position
        
        # Case 1: Pad on routing layer - direct connection
        if routing_layer in pad_layers:
            return (pad_pos, None)
        
        # Case 2: THT pad (all layers) - direct connection
        if '*' in pad_layers or len(pad_layers) == 4:
            return (pad_pos, None)
        
        # Case 3: SMD pad - need via near pad
        # Try to place via as close as possible to pad
        via_pos = self._find_via_near_pad(pad, min_dist=0.5)  # 0.5mm from pad edge
        
        if via_pos is None:
            # Can't place via near pad - try fanout
            via_pos = self._fanout_via_location(pad, distance=2.0)
        
        if via_pos is None:
            return None  # Can't connect - routing fails
        
        via = self.via_planner.place_via(
            position=via_pos,
            from_layer=pad_layers[0],  # pad's layer
            to_layer=routing_layer,
            net=pad.net
        )
        
        return (via_pos, via)
```

---

### Phase 4: Dense IC Escape Routing

**4.1 Fanout Via Planning**

For dense ICs (QFN-56 with 0.4mm pitch), vias can't fit at pads. Need "escape routing":

```python
class ICFanoutPlanner:
    """Plan via locations for dense ICs"""
    
    def plan_fanout(self, ic: Component) -> dict[str, tuple[float, float]]:
        """Pre-plan via locations for IC escape routing.
        
        For 0.4mm pitch IC:
        - Vias need 1.5mm spacing
        - Pads have 0.4mm spacing
        - Solution: Place vias in "via field" away from IC
        """
        via_field = self._define_via_field(ic)
        
        pin_to_via = {}
        
        # Group pins by side
        sides = self._group_pins_by_side(ic)
        
        for side, pins in sides.items():
            # Allocate via positions in field
            via_positions = self._allocate_vias_for_side(
                pins, 
                via_field,
                spacing=ViaSpec.min_via_spacing
            )
            
            for pin, via_pos in zip(pins, via_positions):
                pin_to_via[pin.net] = via_pos
        
        return pin_to_via
    
    def _define_via_field(self, ic: Component) -> Polygon:
        """Define area for via placement around IC"""
        ic_bbox = ic.bounding_box
        
        # Via field: 2-5mm from IC edge
        via_field = ic_bbox.buffer(5.0) - ic_bbox.buffer(2.0)
        
        # Remove areas blocked by other components
        for obs in self.obstacles:
            via_field = via_field - obs.buffer(ViaSpec.keepout_radius)
        
        return via_field
```

**4.2 Escape + Via Routing**

```python
def route_dense_ic_net(
    self,
    net_name: str,
    ic_pads: list[Pad],
    routing_layer: str
) -> RoutePath:
    """Route from dense IC with automatic fanout"""
    
    # Step 1: Plan via locations (BEFORE routing)
    via_plan = self.fanout_planner.plan_fanout(ic_pads[0].component)
    
    # Step 2: Escape route from pad to via on pad's layer
    pad = ic_pads[0]
    via_pos = via_plan[net_name]
    
    escape_path = self.route_escape(
        start=pad.position,
        goal=via_pos,
        layer=pad.layer,
        avoid_ic_pads=True
    )
    
    if escape_path is None:
        return None
    
    # Step 3: Place via
    via = self.via_planner.place_via(
        position=via_pos,
        from_layer=pad.layer,
        to_layer=routing_layer,
        net=net_name
    )
    
    if via is None:
        return None
    
    # Step 4: Route from via to destination on routing layer
    main_path = self.route_main(
        start=(via_pos, routing_layer),
        goal=ic_pads[1],
        net_name=net_name
    )
    
    # Combine: escape + via + main
    return RoutePath([escape_path, via, main_path])
```

---

### Phase 5: Integration with Existing Router

**5.1 Refactor ExactGeometryRouter**

```python
class LayerAwareExactRouter:
    """Exact geometry router with native via support"""
    
    def __init__(self, pcb, design_rules, kicad_file):
        # Existing initialization
        self.pcb = pcb
        self.design_rules = design_rules
        
        # NEW: Multi-layer routing space
        self.layer_stack = LayerStack()
        self.via_planner = ViaPlanner(self.layer_stack)
        self.fanout_planner = ICFanoutPlanner(self.via_planner)
        
        # Build base obstacles (per-layer)
        self._build_multi_layer_obstacles()
        
        # Pre-plan via locations for dense ICs
        self._preplan_dense_ic_fanouts()
    
    def route_net(
        self,
        net_name: str,
        pads: list[tuple[float, float, str]]  # (x, y, layer)
    ) -> RoutePath:
        """Route net with automatic layer transitions"""
        
        # Check if net requires layer changes
        pad_layers = set(p[2] for p in pads)
        routing_layer = self.design_rules.get_layer_constraint(net_name)
        
        if routing_layer not in pad_layers:
            # Need vias - use fanout-aware routing
            return self._route_with_vias(net_name, pads, routing_layer)
        else:
            # All pads on same layer as routing - simple case
            return self._route_single_layer(net_name, pads, routing_layer)
    
    def _route_with_vias(self, net_name, pads, routing_layer):
        """Route with via insertion at optimal locations"""
        
        segments = []
        
        # For each pad, get connection point on routing layer
        connection_points = []
        for pad in pads:
            conn_pt, via = self.pad_connector.get_connection_point(pad, routing_layer)
            if via:
                segments.append(via)
            connection_points.append(conn_pt)
        
        # Now route between connection points on routing layer
        main_route = self._route_between_points(
            connection_points,
            routing_layer,
            net_name
        )
        
        segments.extend(main_route.segments)
        
        return RoutePath(segments, net_name)
```

---

## Migration Path

### Stage 1: Foundation (Week 1)
- [ ] Implement `LayerStack`, `ViaSpec`, `ViaPlanner`
- [ ] Add via keepout zones to obstacle model
- [ ] Update `_build_base_obstacles` to be layer-aware
- [ ] Write unit tests for via clearance checking

### Stage 2: Via-Aware Routing (Week 2)
- [ ] Implement `PadLayerConnector`
- [ ] Modify `route_net` to use `get_connection_point()`
- [ ] Add via insertion to routing (not export)
- [ ] Update obstacle tracking to include placed vias

### Stage 3: Dense IC Fanout (Week 3)
- [ ] Implement `ICFanoutPlanner`
- [ ] Add escape routing with via planning
- [ ] Handle QFN/BGA packages specifically
- [ ] Test on U_MCU (QFN-56)

### Stage 4: 3D Pathfinding (Week 4)
- [ ] Implement `MultiLayerRRT` or `LayerAwareAStar`
- [ ] Add layer transition cost to pathfinding
- [ ] Enable router to choose optimal layer per segment
- [ ] Benchmark against current RRT

### Stage 5: Optimization (Week 5)
- [ ] Via sharing (multiple nets through one via)
- [ ] Via minimization pass
- [ ] DRC-aware micro-adjustments
- [ ] Performance tuning

---

## Success Metrics

### Immediate (Stage 1-2)
- ✅ Zero duplicate vias
- ✅ All vias have ≥1.5mm spacing
- ✅ Via-to-track clearance violations < 5
- ✅ Vias placed during routing, not post-process

### Medium-term (Stage 3-4)
- ✅ 100% of routable nets route successfully (16/16)
- ✅ Via count < 30 (currently 26, target via sharing)
- ✅ USB_D+/D- route as proper differential pair
- ✅ QFN-56 nets (USB, SPI) route with proper fanout

### Long-term (Stage 5)
- ✅ DRC violations < 20 (excluding power nets)
- ✅ Production-ready: Gerber export with no manual fixes
- ✅ Routing time < 2 minutes for full board
- ✅ Architecture supports 6+ layer boards

---

## References

### Professional Router Architectures
1. **Lee's Algorithm** (1961) - First maze router, foundation of grid-based routing
2. **Hightower's Line-Probe** (1969) - Escape routing for dense ICs
3. **Mikami-Tabuchi** (1968) - Grid expansion with via minimization
4. **Soukup's Algorithm** (1978) - Grid-based with directional bias
5. **Modern Approaches**:
   - Cadence Allegro: Global routing → Detailed routing → ECO
   - Altium: Rule-driven push-and-shove with via optimization
   - KiCad PNS: Push-and-shove with dynamic via insertion

### Key Papers
- "A Path Connection Algorithm for VLSI Layout" - Lee (1961)
- "Wire Routing by Optimizing Channel Assignment" - Yoshimura (1982)
- "Multilayer Routing for High-Density PCBs" - Kahng (2002)

### Implementation Inspirations
- KiCad PNS (Push-and-Shove): https://github.com/KiCad/kicad-source-mirror/tree/master/pcbnew/router
- FreeRouting: https://github.com/freerouting/freerouting
- TopoR: Commercial, but documented approach in patents

---

## Notes

This plan addresses **root causes**, not symptoms:

❌ **Bandaid**: Check via-via distance in export script  
✅ **Structural**: Via planner with clearance model during routing

❌ **Bandaid**: Increase via size to avoid clearance issues  
✅ **Structural**: Fanout planning for dense ICs with via field allocation

❌ **Bandaid**: Try different via positions randomly  
✅ **Structural**: 3D pathfinding that treats vias as deliberate layer transitions

The key insight: **Vias are not "fixes" for layer mismatches - they're integral routing decisions** that should be planned alongside tracks, with proper cost modeling and clearance checking.
