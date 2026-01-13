# Router V5 DRC Remediation: Zero-Manual-Routing Path to DRC-Clean

This issue set addresses the 568 grid conflicts and 237 geometric violations observed after achieving 100% connectivity on the full Temper board. The goal is a fully automated routing pipeline that produces DRC-clean output without any manual intervention.

---

## Epic: Zone-Aware Clearance System

type: epic
priority: 0
labels: router, drc, architecture

### Description

The current router applies uniform clearance rules across the entire board. This causes HV clearance requirements (3.0mm) to "leak" into signal areas where only 0.15-0.2mm is needed. This epic implements zone-based DRC partitioning.

**Problem Statement:**
- SPI bus violations cluster near MCU despite adequate physical space
- Power trace ballooning eats into signal routing channels
- Clearance matrix doesn't consider spatial location

**Success Criteria:**
- [ ] HV zone enforces 3.0mm clearance only within HV boundary
- [ ] Signal zone allows 0.15mm clearance for fine-pitch routing
- [ ] Power zone uses 0.5mm clearance
- [ ] Router selects clearance based on zone membership, not just net class
- [ ] Geometric violations reduced by >80%

**Architecture Impact:**
- `constraints/design_rules.py`: Add `RoutingZone` class and zone-aware lookup
- `constraints/drc_oracle.py`: Accept zone parameter in `can_place_*` methods
- `maze_router.py`: Pass zone context during pathfinding
- `c_space_builder.py`: Generate per-zone C-Space grids

---

## Task: Define RoutingZone data structure and board partitioning

type: task
priority: 1
labels: router, drc, architecture
parent: Zone-Aware Clearance System

### Description

Create the foundational data structures for zone-based routing. A zone is a polygon region on the board with its own clearance rules.

**Implementation Details:**

1. **Create `RoutingZone` class** in `constraints/design_rules.py`:
```python
@dataclass
class RoutingZone:
    name: str  # "hv", "power", "signal"
    polygon: List[Tuple[float, float]]  # Board coordinates (mm)
    clearance_mm: float  # Default clearance within zone
    allowed_net_classes: Set[str]  # Which net classes can route here
    layer_restrictions: Optional[List[str]] = None  # e.g., ["B.Cu"] for HV
```

2. **Create `ZoneManager` class**:
```python
class ZoneManager:
    def __init__(self, zones: List[RoutingZone]):
        self.zones = zones
        self._build_spatial_index()  # R-tree for O(log n) point-in-polygon

    def get_zone_at(self, x: float, y: float) -> Optional[RoutingZone]:
        """Return the zone containing this point, or None if unzoned."""

    def get_clearance(self, x: float, y: float, net_a: str, net_b: str) -> float:
        """Return clearance requirement at this location for these nets."""

    def can_route_net_at(self, x: float, y: float, net: str) -> bool:
        """Check if this net class is allowed in this zone."""
```

3. **Zone inference from board**:
   - Parse component footprints to detect HV components (AC_*, SW_NODE pads)
   - Create convex hull around HV components + 5mm buffer = HV zone
   - MCU + peripheral ICs = signal zone
   - Remaining area = power zone

**Files to Modify:**
- `constraints/design_rules.py`: Add `RoutingZone`, `ZoneManager`
- `io/kicad_parser.py`: Extract component locations for zone inference

**Testing:**
- Unit test: Point-in-polygon for known coordinates
- Integration test: Zone inference on gate driver board produces 3 zones
- Verify: HV components are fully contained in HV zone

**Acceptance Criteria:**
- [ ] `RoutingZone` dataclass defined with all fields
- [ ] `ZoneManager.get_zone_at()` returns correct zone in O(log n)
- [ ] `ZoneManager.get_clearance()` returns zone-specific clearance
- [ ] Zone inference from board components works on Temper full board

---

## Task: Integrate zone-aware clearance into ClearanceMatrix

type: task
priority: 1
labels: router, drc
parent: Zone-Aware Clearance System
deps: Define RoutingZone data structure and board partitioning

### Description

Modify the `ClearanceMatrix` class to accept zone context and return location-aware clearance values.

**Current Behavior:**
```python
def get_clearance(self, net_a: str, net_b: str) -> float:
    # Returns global clearance based only on net classes
```

**Target Behavior:**
```python
def get_clearance(self, net_a: str, net_b: str,
                  x: float = None, y: float = None,
                  zone_manager: ZoneManager = None) -> float:
    # If zone_manager provided and coordinates given:
    #   1. Get zone at (x, y)
    #   2. Check if both nets are allowed in zone
    #   3. Return zone-specific clearance
    # Else: fall back to global net-class clearance
```

**Implementation Details:**

1. **Modify `get_clearance()` signature** to accept optional zone context
2. **Add clearance hierarchy**:
   - HV net involved → Always 3.0mm (safety-critical, no override)
   - Zone-specific clearance if in defined zone
   - Net-class clearance as fallback
3. **Add `is_hv_net()` helper**:
   ```python
   HV_PATTERNS = ["AC_L", "AC_N", "SW_NODE", "GATE_H", "GATE_L", "HV_"]
   def is_hv_net(self, net: str) -> bool:
       return any(pat in net.upper() for pat in self.HV_PATTERNS)
   ```

**Files to Modify:**
- `constraints/design_rules.py`: Modify `ClearanceMatrix.get_clearance()`

**Testing:**
- `get_clearance("SPI_CLK", "SPI_MOSI", x=50, y=30)` in signal zone → 0.15mm
- `get_clearance("SPI_CLK", "AC_L", x=50, y=30)` → 3.0mm (HV override)
- `get_clearance("VCC", "GND", x=10, y=10)` in power zone → 0.5mm

**Acceptance Criteria:**
- [ ] `get_clearance()` accepts optional zone context
- [ ] HV nets always return 3.0mm regardless of zone
- [ ] Signal-to-signal in signal zone returns 0.15mm
- [ ] Backward compatible: works without zone context

---

## Task: Update DRCOracle to use zone-aware clearance

type: task
priority: 1
labels: router, drc
parent: Zone-Aware Clearance System
deps: Integrate zone-aware clearance into ClearanceMatrix

### Description

The `DRCOracle` performs real-time clearance validation during routing. It must use zone-aware clearance values.

**Current Behavior:**
```python
def can_place_track_segment(self, start, end, layer, net, width, neckdown=False):
    clearance = self.rules.get_clearance(net, other_net)
    # Uses global clearance
```

**Target Behavior:**
```python
def can_place_track_segment(self, start, end, layer, net, width,
                            neckdown=False, zone_manager=None):
    midpoint = ((start[0]+end[0])/2, (start[1]+end[1])/2)
    clearance = self.rules.get_clearance(net, other_net,
                                         x=midpoint[0], y=midpoint[1],
                                         zone_manager=zone_manager)
```

**Implementation Details:**

1. **Add `zone_manager` parameter** to all `can_place_*` methods:
   - `can_place_track_segment()`
   - `can_place_via()`

2. **Calculate segment midpoint** for zone lookup (segments can span zones; use midpoint as representative)

3. **Handle zone boundaries**:
   - If segment crosses zone boundary, use stricter clearance
   - Add `crosses_zone_boundary(start, end)` helper

4. **Update spatial queries** to include zone context in violation reporting

**Files to Modify:**
- `constraints/drc_oracle.py`: All `can_place_*` methods

**Testing:**
- Track segment fully in signal zone: validated with 0.15mm clearance
- Track segment crossing HV boundary: validated with 3.0mm clearance
- Existing tests still pass (backward compatibility)

**Acceptance Criteria:**
- [ ] All `can_place_*` methods accept `zone_manager` parameter
- [ ] Zone-specific clearance used when zone context provided
- [ ] Zone boundary crossing uses stricter clearance
- [ ] Violation messages include zone information

---

## Task: Generate per-zone C-Space grids

type: task
priority: 2
labels: router, drc, performance
parent: Zone-Aware Clearance System
deps: Define RoutingZone data structure and board partitioning

### Description

The C-Space (Configuration Space) builder inflates obstacles by `trace_width/2 + clearance`. With zone-aware clearance, we need multiple C-Space grids or a zone-indexed lookup.

**Current Behavior:**
```python
def build_cspace(self, clearance: float) -> np.ndarray:
    # Single global clearance for entire grid
```

**Target Behavior:**
```python
def build_cspace_zoned(self, zone_manager: ZoneManager) -> Dict[str, np.ndarray]:
    # Returns {"hv": grid_hv, "power": grid_power, "signal": grid_signal}
    # Each grid uses zone-specific inflation radius
```

**Implementation Details:**

1. **Option A: Multiple grids** (memory-heavy, fast lookup)
   - Generate separate C-Space per zone
   - Router selects grid based on current position
   - Memory: 3x current usage

2. **Option B: Adaptive inflation** (memory-efficient, slower)
   - Single grid with zone-indexed inflation radii
   - Query: `get_blocked(x, y, zone)` computes on-demand
   - Memory: 1x + zone index overhead

3. **Recommended: Hybrid approach**
   - Pre-compute HV zone C-Space (largest inflation, most critical)
   - Signal zone uses finer grid with smaller inflation
   - Power zone uses coarse grid (traces are wide anyway)

**Files to Modify:**
- `c_space_builder.py`: Add `build_cspace_zoned()` method
- `maze_router.py`: Select appropriate C-Space based on routing location

**Performance Considerations:**
- HV zone: 3.0mm inflation → cells blocked in large radius
- Signal zone: 0.15mm inflation → fine-pitch routing possible
- Pre-compute at router initialization, not per-net

**Acceptance Criteria:**
- [ ] `build_cspace_zoned()` generates zone-specific grids
- [ ] Router uses correct C-Space based on current routing zone
- [ ] Memory usage increase < 2x baseline
- [ ] Routing time impact < 20%

---

## Task: Pass zone context through A* pathfinding

type: task
priority: 1
labels: router, drc
parent: Zone-Aware Clearance System
deps: Update DRCOracle to use zone-aware clearance, Generate per-zone C-Space grids

### Description

The A* pathfinder must be zone-aware to select correct clearances and C-Space during routing.

**Current Behavior:**
```python
def find_path_astar_numba(grid, start, end, ...):
    # No zone awareness
```

**Target Behavior:**
```python
def find_path_astar_numba(grid, start, end, zone_grid, zone_clearances, ...):
    # zone_grid[x,y] = zone_id (0=hv, 1=power, 2=signal)
    # zone_clearances = [3.0, 0.5, 0.15]  # indexed by zone_id
```

**Implementation Details:**

1. **Add zone grid** as Numba-compatible array:
   ```python
   zone_grid = np.zeros((width, height), dtype=np.int8)
   # Rasterize zone polygons onto grid
   ```

2. **Modify cost function**:
   ```python
   @njit
   def get_move_cost(x, y, zone_grid, zone_clearances, neighbor_net_owner):
       zone_id = zone_grid[x, y]
       required_clearance = zone_clearances[zone_id]
       # Use required_clearance for blocking decisions
   ```

3. **Zone transition penalty**:
   - Moving from signal zone to HV zone should have high cost
   - Prevents signal traces from accidentally entering HV region

4. **Update all A* variants**:
   - `find_path_astar_numba()`
   - `find_path_astar_numba_adaptive()`

**Files to Modify:**
- `fast_router.py`: Add zone parameters to Numba functions
- `maze_router.py`: Pass zone context to pathfinder

**Testing:**
- Route `SPI_CLK` in signal zone: uses 0.15mm clearance
- Attempt to route signal through HV zone: avoids or high penalty
- Zone grid rasterization matches polygon boundaries

**Acceptance Criteria:**
- [ ] Zone grid rasterized from zone polygons
- [ ] A* cost function uses zone-specific clearance
- [ ] Zone transition penalty prevents signals entering HV zone
- [ ] Numba JIT compilation succeeds with new parameters

---

## Epic: Bus-Aware Cohort Routing

type: epic
priority: 1
labels: router, signal-integrity

### Description

The SPI bus (CLK, MOSI, MISO, CS) is routed as individual nets, causing them to take divergent paths that create crossings and clearance violations. This epic implements bus-aware routing where related signals are routed as a cohort.

**Problem Statement:**
- SPI signals take different paths, creating unnecessary crossings
- Length matching is difficult when paths diverge
- Clearance violations occur when signals reconverge near destination

**Success Criteria:**
- [ ] Bus definitions extracted from netlist or user-defined
- [ ] Bus signals routed in parallel with consistent spacing
- [ ] No intra-bus crossings
- [ ] Length variation within bus < 2mm (for high-speed buses)

**Architecture Impact:**
- `routing/bus_router.py`: New module for bus-aware routing
- `maze_router.py`: Delegate bus nets to bus router
- `io/kicad_parser.py`: Extract bus definitions from labels

---

## Task: Define bus cohort data structures

type: task
priority: 2
labels: router, signal-integrity
parent: Bus-Aware Cohort Routing

### Description

Create data structures to represent signal buses and their routing constraints.

**Implementation Details:**

1. **Create `BusCohort` dataclass**:
```python
@dataclass
class BusCohort:
    name: str  # "SPI", "I2C", "JTAG"
    nets: List[str]  # ["SPI_CLK", "SPI_MOSI", "SPI_MISO", "SPI_CS"]
    spacing_mm: float  # Target spacing between traces (e.g., 0.15)
    max_length_delta_mm: float  # Max length variation (e.g., 2.0)
    reference_net: Optional[str] = None  # Net to match length against
    differential_pairs: Optional[List[Tuple[str, str]]] = None  # For USB, etc.
```

2. **Create `BusRegistry`**:
```python
class BusRegistry:
    def __init__(self):
        self.buses: Dict[str, BusCohort] = {}
        self._net_to_bus: Dict[str, str] = {}  # Reverse lookup

    def register_bus(self, bus: BusCohort):
        """Register a bus cohort."""

    def get_bus_for_net(self, net: str) -> Optional[BusCohort]:
        """Return the bus this net belongs to, if any."""

    def infer_buses_from_netlist(self, nets: List[str]) -> List[BusCohort]:
        """Auto-detect buses from naming patterns."""
```

3. **Bus inference patterns**:
   - `SPI_*` → SPI bus
   - `I2C_*` → I2C bus
   - `JTAG_*` → JTAG bus
   - `USB_D+`, `USB_D-` → USB differential pair
   - `*_P`, `*_N` suffix → differential pair

**Files to Create:**
- `routing/bus_router.py`: Bus cohort definitions

**Testing:**
- Infer SPI bus from `["SPI_CLK", "SPI_MOSI", "SPI_MISO", "VCC", "GND"]` → SPI cohort with 3 nets
- Register custom bus and retrieve by net name
- Differential pair detection for USB nets

**Acceptance Criteria:**
- [ ] `BusCohort` dataclass with all required fields
- [ ] `BusRegistry` with registration and lookup
- [ ] Automatic bus inference from netlist patterns
- [ ] Differential pair detection

---

## Task: Implement parallel bus routing algorithm

type: task
priority: 1
labels: router, signal-integrity
parent: Bus-Aware Cohort Routing
deps: Define bus cohort data structures

### Description

Implement a routing algorithm that routes all nets in a bus cohort in parallel, maintaining consistent spacing.

**Algorithm:**

1. **Find reference path** for the bus:
   - Route the first net in the cohort (e.g., SPI_CLK)
   - This becomes the "spine" path

2. **Generate parallel paths** for remaining nets:
   - Offset the spine path by `spacing_mm` for each additional net
   - Maintain parallelism through corners (use arc or 45° miters)

3. **Handle obstacles**:
   - If parallel path hits obstacle, route around as group
   - All nets in cohort must fit through the same channel

4. **Length matching**:
   - Calculate path lengths for all nets in cohort
   - Add serpentine meanders to shorter nets (post-processing)

**Implementation Details:**

```python
class BusRouter:
    def route_bus(self, bus: BusCohort, start_pins: List[Pin],
                  end_pins: List[Pin]) -> List[RoutedPath]:
        """Route all nets in a bus cohort together."""

        # 1. Route reference net (first in cohort)
        ref_path = self.maze_router.route_net(bus.nets[0], ...)

        # 2. Generate parallel offsets
        for i, net in enumerate(bus.nets[1:]):
            offset = (i + 1) * bus.spacing_mm
            parallel_path = self._offset_path(ref_path, offset)

            # 3. Validate parallel path is clear
            if not self._path_is_clear(parallel_path, net):
                # Re-route reference with wider channel requirement
                ref_path = self._route_with_channel_width(
                    bus.nets[0], channel_width=len(bus.nets) * bus.spacing_mm
                )

        return all_paths
```

**Files to Modify:**
- `routing/bus_router.py`: Add `BusRouter` class
- `maze_router.py`: Delegate bus nets to `BusRouter`

**Testing:**
- Route 4-net SPI bus: all paths parallel, spacing consistent
- Bus through corner: all nets maintain relative positions
- Obstacle avoidance: all nets route around together

**Acceptance Criteria:**
- [ ] `BusRouter.route_bus()` routes all nets in parallel
- [ ] Spacing maintained within 10% of target
- [ ] No intra-bus crossings
- [ ] Works with existing A* pathfinder

---

## Task: Add length matching post-processing for buses

type: task
priority: 2
labels: router, signal-integrity
parent: Bus-Aware Cohort Routing
deps: Implement parallel bus routing algorithm

### Description

After bus routing, add serpentine meanders to shorter nets to match length within tolerance.

**Algorithm:**

1. **Calculate path lengths**:
   ```python
   lengths = {net: calculate_path_length(path) for net, path in bus_paths.items()}
   max_length = max(lengths.values())
   ```

2. **Identify nets needing meanders**:
   ```python
   for net, length in lengths.items():
       delta = max_length - length
       if delta > bus.max_length_delta_mm:
           add_serpentine(net, delta)
   ```

3. **Generate serpentine pattern**:
   - Find straight segment with space for meander
   - Calculate meander parameters: amplitude, period
   - Insert meander vertices into path

**Implementation Details:**

```python
def add_serpentine(self, path: RoutedPath, extra_length_mm: float) -> RoutedPath:
    """Add serpentine meander to increase path length."""

    # Find longest straight segment
    segment = self._find_best_meander_location(path)

    # Calculate meander geometry
    # extra_length ≈ 2 * num_periods * amplitude
    num_periods = 4  # Typical
    amplitude = extra_length_mm / (2 * num_periods)

    # Generate meander vertices
    meander_vertices = self._generate_serpentine(
        segment.start, segment.end, amplitude, num_periods
    )

    # Replace segment with meander
    return path.replace_segment(segment, meander_vertices)
```

**Files to Modify:**
- `routing/bus_router.py`: Add `add_serpentine()` method
- `post_processing/length_matcher.py`: Standalone length matching utility

**Testing:**
- 4-net bus with 5mm length variation → all within 0.5mm after matching
- Meander fits within available space (no DRC violations)
- Meander doesn't cross other nets

**Acceptance Criteria:**
- [ ] Path length calculation accurate to 0.1mm
- [ ] Serpentine generation produces valid geometry
- [ ] Length delta reduced to < `max_length_delta_mm`
- [ ] Meanders pass DRC validation

---

## Task: Integrate bus router into main routing flow

type: task
priority: 1
labels: router
parent: Bus-Aware Cohort Routing
deps: Implement parallel bus routing algorithm

### Description

Modify the main routing flow to detect buses and delegate to the bus router.

**Implementation Details:**

1. **Modify `MazeRouter.route_all_nets()`**:
```python
def route_all_nets(self, nets: List[str], ...):
    # 1. Identify buses
    bus_registry = BusRegistry()
    bus_registry.infer_buses_from_netlist(nets)

    # 2. Separate bus nets from individual nets
    bus_nets = set()
    for bus in bus_registry.buses.values():
        bus_nets.update(bus.nets)

    individual_nets = [n for n in nets if n not in bus_nets]

    # 3. Route buses first (they need channel space)
    bus_router = BusRouter(self)
    for bus in bus_registry.buses.values():
        bus_router.route_bus(bus, ...)

    # 4. Route remaining individual nets
    for net in individual_nets:
        self.route_net(net, ...)
```

2. **Routing order**:
   - Buses first (need contiguous channels)
   - Power nets second (wide traces)
   - Individual signals last (most flexible)

**Files to Modify:**
- `maze_router.py`: Modify `route_all_nets()` to use bus router

**Testing:**
- Full board routing with SPI bus detected and routed together
- Bus nets not routed twice (once by bus router, once individually)
- Routing order: buses → power → signals

**Acceptance Criteria:**
- [ ] Buses auto-detected from netlist
- [ ] Bus router invoked before individual net routing
- [ ] No duplicate routing of bus nets
- [ ] Full board routes successfully with bus awareness

---

## Epic: Post-Route Geometry Optimization

type: epic
priority: 1
labels: router, drc, post-processing

### Description

After achieving 100% connectivity, apply geometry optimization passes to eliminate remaining DRC violations. This includes nudging traces apart, optimizing via placement, and ballooning power traces.

**Problem Statement:**
- 237 geometric violations remain after routing
- Traces are placed at grid resolution, not optimal positions
- Power traces are narrow where they could be wider

**Success Criteria:**
- [ ] Geometric violations reduced to 0
- [ ] No manual intervention required
- [ ] Power traces expanded for thermal capacity
- [ ] Total routing time increase < 50%

---

## Task: Implement force-directed trace nudger

type: task
priority: 0
labels: router, drc, post-processing
parent: Post-Route Geometry Optimization

### Description

Create a post-processing pass that uses force-directed optimization to push traces apart until clearance requirements are met.

**Algorithm:**

1. **Identify violations**:
   ```python
   violations = drc_oracle.find_all_violations(routed_paths)
   # Each violation: (trace_a, trace_b, current_dist, required_dist)
   ```

2. **Calculate repulsion forces**:
   ```python
   for violation in violations:
       segment_a, segment_b = violation.segments
       push_vector = compute_normal(segment_a, segment_b)
       force_magnitude = (required_dist - current_dist) / 2

       forces[segment_a] += push_vector * force_magnitude
       forces[segment_b] -= push_vector * force_magnitude
   ```

3. **Apply forces with constraints**:
   - Endpoints are fixed (connected to pins)
   - Movement limited per iteration (stability)
   - Check for new violations after each move

4. **Iterate until convergence**:
   ```python
   for iteration in range(max_iterations):
       violations = find_violations()
       if not violations:
           break
       forces = compute_forces(violations)
       apply_forces(forces, max_move=0.1)  # 0.1mm per iteration
   ```

**Implementation Details:**

```python
class TraceNudger:
    def __init__(self, drc_oracle: DRCOracle, max_iterations: int = 100):
        self.oracle = drc_oracle
        self.max_iterations = max_iterations

    def nudge_to_clearance(self, paths: Dict[str, RoutedPath]) -> Dict[str, RoutedPath]:
        """Nudge traces until all clearance violations resolved."""

        for iteration in range(self.max_iterations):
            violations = self._find_violations(paths)
            if not violations:
                logger.info(f"Converged after {iteration} iterations")
                break

            forces = self._compute_repulsion_forces(violations)
            paths = self._apply_forces(paths, forces)

        return paths

    def _compute_repulsion_forces(self, violations: List[Violation]) -> Dict[SegmentId, Vector]:
        """Compute force vectors to push segments apart."""

    def _apply_forces(self, paths: Dict[str, RoutedPath],
                      forces: Dict[SegmentId, Vector]) -> Dict[str, RoutedPath]:
        """Apply forces while maintaining connectivity."""
```

**Files to Create:**
- `post_processing/trace_nudger.py`: `TraceNudger` class

**Testing:**
- Two parallel traces at 0.1mm apart, required 0.2mm → nudged to 0.2mm
- Pin-connected endpoints remain fixed
- Complex crossing scenario resolves without creating new violations

**Acceptance Criteria:**
- [ ] `TraceNudger.nudge_to_clearance()` reduces violations
- [ ] Endpoints remain connected to original pins
- [ ] No new violations created during nudging
- [ ] Converges within 100 iterations for typical cases

---

## Task: Implement via optimization pass

type: task
priority: 2
labels: router, drc, post-processing
parent: Post-Route Geometry Optimization
deps: Implement force-directed trace nudger

### Description

Optimize via placement to reduce via-to-via and via-to-trace clearance violations.

**Optimization Strategies:**

1. **Via consolidation**: Merge nearby vias on same net
2. **Via repositioning**: Move vias to reduce clearance violations
3. **Via elimination**: Remove redundant layer transitions

**Implementation Details:**

```python
class ViaOptimizer:
    def optimize_vias(self, paths: Dict[str, RoutedPath]) -> Dict[str, RoutedPath]:
        """Optimize via placement for DRC compliance."""

        # 1. Consolidate nearby vias on same net
        paths = self._consolidate_vias(paths)

        # 2. Identify via-related violations
        via_violations = self._find_via_violations(paths)

        # 3. Reposition vias to resolve violations
        for violation in via_violations:
            via = violation.via
            new_position = self._find_valid_position(via, violation.clearance_needed)
            if new_position:
                paths = self._move_via(paths, via, new_position)

        # 4. Remove unnecessary vias (same-layer connections)
        paths = self._remove_redundant_vias(paths)

        return paths
```

**Files to Create:**
- `post_processing/via_optimizer.py`: `ViaOptimizer` class

**Testing:**
- Two vias 0.3mm apart on same net → consolidated to one
- Via too close to trace → repositioned
- Via between same-layer segments → removed

**Acceptance Criteria:**
- [ ] Via consolidation reduces via count
- [ ] Via repositioning resolves clearance violations
- [ ] Redundant vias removed
- [ ] Connectivity preserved after optimization

---

## Task: Integrate post-processing into routing pipeline

type: task
priority: 1
labels: router, post-processing
parent: Post-Route Geometry Optimization
deps: Implement force-directed trace nudger, Implement via optimization pass

### Description

Add post-processing passes to the main routing pipeline, executed after all nets are routed.

**Implementation Details:**

1. **Modify `MazeRouter.route_all_nets()`**:
```python
def route_all_nets(self, nets: List[str], ...):
    # ... existing routing logic ...

    # Post-processing pipeline
    paths = self._run_post_processing(routed_paths)

    return paths

def _run_post_processing(self, paths: Dict[str, RoutedPath]) -> Dict[str, RoutedPath]:
    """Run all post-processing optimization passes."""

    logger.info("Starting post-processing pipeline")

    # 1. Via optimization (reduces via count, fixes via DRC)
    via_optimizer = ViaOptimizer(self.drc_oracle)
    paths = via_optimizer.optimize_vias(paths)
    logger.info(f"Via optimization complete: {via_optimizer.stats}")

    # 2. Trace nudging (fixes trace clearance DRC)
    nudger = TraceNudger(self.drc_oracle)
    paths = nudger.nudge_to_clearance(paths)
    logger.info(f"Trace nudging complete: {nudger.stats}")

    # 3. Trace ballooning (expand power traces)
    ballooner = TraceBallooner(self.geometry)
    paths = ballooner.balloon_power_traces(paths)
    logger.info(f"Trace ballooning complete: {ballooner.stats}")

    # 4. Final DRC validation
    violations = self.drc_oracle.find_all_violations(paths)
    if violations:
        logger.warning(f"Post-processing complete with {len(violations)} remaining violations")
    else:
        logger.info("Post-processing complete: 0 DRC violations")

    return paths
```

2. **Add progress tracking** for long post-processing runs

3. **Add early termination** if DRC clean achieved

**Files to Modify:**
- `maze_router.py`: Add `_run_post_processing()` method

**Testing:**
- Full board routing produces DRC-clean output
- Post-processing time logged
- Remaining violations reported if any

**Acceptance Criteria:**
- [ ] Post-processing runs automatically after routing
- [ ] All post-processing passes integrated in correct order
- [ ] Final DRC validation performed
- [ ] Statistics logged for each pass

---

## Epic: Automated Critical Net Pre-Routing

type: epic
priority: 1
labels: router, automation

### Description

Before general autorouting, automatically identify and pre-route critical nets (power distribution, clock signals) using optimized strategies. This ensures critical nets get optimal paths before routing channels become congested.

**Problem Statement:**
- Project requires zero manual routing
- Critical nets (power, clocks) need priority routing
- Current approach routes alphabetically, not by criticality

**Success Criteria:**
- [ ] Critical nets identified automatically from netlist
- [ ] Power nets routed with wide traces and via arrays
- [ ] Clock nets routed with shortest paths over ground
- [ ] Pre-routed nets locked before general routing

---

## Task: Implement automatic critical net detection

type: task
priority: 2
labels: router, automation
parent: Automated Critical Net Pre-Routing

### Description

Automatically identify critical nets from the netlist based on naming patterns and connectivity analysis.

**Critical Net Categories:**

1. **Power Distribution**:
   - Patterns: `VCC`, `VDD`, `V+`, `V-`, `VBAT`, `+3.3V`, `+5V`, `+12V`
   - Also: nets connected to power pins of ICs

2. **Ground Networks**:
   - Patterns: `GND`, `AGND`, `DGND`, `PGND`, `VSS`, `0V`

3. **Clock Signals**:
   - Patterns: `CLK`, `CLOCK`, `OSC`, `XTAL`
   - Also: nets with clock attribute in symbol

4. **High-Speed Buses**:
   - Patterns: `SPI_*`, `I2C_*`, `USB_*`, `JTAG_*`

5. **High-Current Paths**:
   - Patterns: `MOTOR_*`, `HEATER_*`, `SW_NODE`, `GATE_*`

**Implementation Details:**

```python
class CriticalNetDetector:
    def detect_critical_nets(self, netlist: Netlist) -> Dict[str, CriticalNetCategory]:
        """Identify critical nets and categorize them."""

        critical = {}

        for net in netlist.nets:
            category = self._categorize_net(net)
            if category:
                critical[net.name] = category

        return critical

    def _categorize_net(self, net: Net) -> Optional[CriticalNetCategory]:
        """Determine if net is critical and its category."""

        # Check naming patterns
        name = net.name.upper()

        if any(p in name for p in ["VCC", "VDD", "V+", "VBAT"]):
            return CriticalNetCategory.POWER
        if any(p in name for p in ["GND", "VSS", "AGND"]):
            return CriticalNetCategory.GROUND
        if any(p in name for p in ["CLK", "CLOCK", "OSC"]):
            return CriticalNetCategory.CLOCK
        # ... more patterns

        # Check connectivity
        if self._connects_to_power_pin(net):
            return CriticalNetCategory.POWER

        return None
```

**Files to Create:**
- `routing/critical_net_detector.py`: `CriticalNetDetector` class

**Testing:**
- Detect VCC, GND, CLK from Temper netlist
- Identify SPI bus as high-speed
- Detect power nets by IC power pin connectivity

**Acceptance Criteria:**
- [ ] All power/ground nets detected
- [ ] Clock signals identified
- [ ] High-speed buses categorized
- [ ] Works on Temper full board netlist

---

## Task: Implement power distribution network (PDN) pre-router

type: task
priority: 1
labels: router, automation, power
parent: Automated Critical Net Pre-Routing
deps: Implement automatic critical net detection

### Description

Automatically route power distribution networks before general signal routing.

**PDN Routing Strategy:**

1. **Star topology from regulators**:
   - Identify voltage regulator outputs
   - Route radially to all load pins
   - Use widest traces that fit

2. **Via arrays for layer transitions**:
   - 2x2 minimum for power vias
   - Reduces inductance and resistance

3. **Ground pour preparation**:
   - Mark areas for ground pour (don't route individual GND traces)
   - Add thermal relief vias to GND pins

**Implementation Details:**

```python
class PDNRouter:
    def route_power_distribution(self, power_nets: List[str],
                                  ground_nets: List[str]) -> Dict[str, RoutedPath]:
        """Route power distribution network."""

        paths = {}

        # 1. Identify power sources (regulators, connectors)
        sources = self._find_power_sources(power_nets)

        # 2. Route from each source to loads
        for net in power_nets:
            if net in ground_nets:
                continue  # Ground handled separately

            source = sources.get(net)
            loads = self._get_load_pins(net)

            # Star routing from source to loads
            for load_pin in loads:
                path = self._route_power_trace(source, load_pin, net)
                path.width = self._calculate_power_width(net, load_pin)
                paths[f"{net}_{load_pin.component}"] = path

        # 3. Add via arrays at layer transitions
        self._add_via_arrays(paths)

        return paths

    def _route_power_trace(self, source: Pin, load: Pin, net: str) -> RoutedPath:
        """Route a single power trace with wide width."""

    def _add_via_arrays(self, paths: Dict[str, RoutedPath]):
        """Replace single vias with 2x2 arrays for power nets."""
```

**Files to Create:**
- `routing/pdn_router.py`: `PDNRouter` class

**Testing:**
- VCC routed from regulator to all IC VCC pins
- Power traces use maximum feasible width
- Via arrays at layer transitions

**Acceptance Criteria:**
- [ ] Power nets routed with star topology
- [ ] Trace widths appropriate for current capacity
- [ ] Via arrays for layer transitions
- [ ] Ground pins prepared for pour (not individually routed)

---

## Task: Implement clock net pre-router

type: task
priority: 2
labels: router, automation, signal-integrity
parent: Automated Critical Net Pre-Routing
deps: Implement automatic critical net detection

### Description

Automatically route clock signals with signal integrity best practices.

**Clock Routing Strategy:**

1. **Shortest path over reference plane**:
   - Route on outer layer with ground plane beneath
   - Minimize length for reduced EMI

2. **Avoid vias**:
   - Each via adds inductance discontinuity
   - Route on single layer if possible

3. **Guard traces** (optional):
   - Add GND traces parallel to clock for shielding
   - Especially for high-frequency clocks

**Implementation Details:**

```python
class ClockRouter:
    def route_clock_nets(self, clock_nets: List[str]) -> Dict[str, RoutedPath]:
        """Route clock signals with SI best practices."""

        paths = {}

        for net in clock_nets:
            pins = self._get_net_pins(net)

            # Find shortest Manhattan path
            path = self._route_shortest_path(pins, prefer_layer="F.Cu")

            # Verify reference plane continuity
            if not self._has_continuous_reference(path):
                logger.warning(f"Clock {net} crosses reference plane gap")

            paths[net] = path

        return paths

    def _route_shortest_path(self, pins: List[Pin], prefer_layer: str) -> RoutedPath:
        """Route with minimum length, avoiding vias."""

        # Use A* with heavy via penalty
        self.maze_router.via_cost = 100.0  # High penalty
        path = self.maze_router.route_net(pins, prefer_layer=prefer_layer)
        self.maze_router.via_cost = 1.0  # Reset

        return path
```

**Files to Create:**
- `routing/clock_router.py`: `ClockRouter` class

**Testing:**
- Clock nets routed with minimal length
- Via count minimized or zero
- Routing over ground plane verified

**Acceptance Criteria:**
- [ ] Clock nets routed with minimum length
- [ ] Vias avoided where possible
- [ ] Reference plane continuity checked
- [ ] Warning if clock crosses plane gap

---

## Task: Integrate pre-routing into main flow with locking

type: task
priority: 1
labels: router, automation
parent: Automated Critical Net Pre-Routing
deps: Implement power distribution network (PDN) pre-router, Implement clock net pre-router

### Description

Integrate all pre-routing strategies into the main routing flow and lock pre-routed nets.

**Implementation Details:**

1. **Routing order**:
```python
def route_all_nets(self, nets: List[str], ...):
    # Phase 1: Detect critical nets
    critical = CriticalNetDetector().detect_critical_nets(self.netlist)

    # Phase 2: Pre-route in priority order
    # 2a. Power distribution
    power_nets = [n for n, cat in critical.items() if cat == CriticalNetCategory.POWER]
    pdn_paths = PDNRouter(self).route_power_distribution(power_nets, ground_nets)
    self._lock_paths(pdn_paths)

    # 2b. Clock signals
    clock_nets = [n for n, cat in critical.items() if cat == CriticalNetCategory.CLOCK]
    clock_paths = ClockRouter(self).route_clock_nets(clock_nets)
    self._lock_paths(clock_paths)

    # 2c. High-speed buses
    bus_paths = BusRouter(self).route_detected_buses(critical)
    self._lock_paths(bus_paths)

    # Phase 3: Route remaining nets
    remaining = [n for n in nets if n not in self._locked_nets]
    self._route_individual_nets(remaining)

    # Phase 4: Post-processing
    return self._run_post_processing(all_paths)
```

2. **Locking mechanism**:
```python
def _lock_paths(self, paths: Dict[str, RoutedPath]):
    """Mark paths as locked - cannot be ripped up."""
    for net, path in paths.items():
        self._locked_nets.add(net)
        # Block cells in occupancy grid permanently
        for segment in path.segments:
            self._mark_permanently_blocked(segment)
```

**Files to Modify:**
- `maze_router.py`: Add pre-routing phases and locking

**Testing:**
- Pre-routed nets not ripped up during RRR
- Routing order: PDN → clocks → buses → signals
- Locked nets marked in occupancy grid

**Acceptance Criteria:**
- [ ] Pre-routing integrated into `route_all_nets()`
- [ ] Correct routing order enforced
- [ ] Locked paths not modified during RRR
- [ ] Full board routes with pre-routing enabled

---

## Task: Validation - Run full board routing with all improvements

type: task
priority: 0
labels: router, validation
deps: Pass zone context through A* pathfinding, Integrate bus router into main routing flow, Integrate post-processing into routing pipeline, Integrate pre-routing into main flow with locking

### Description

Final validation task: run the complete router-v5 with all improvements on the full Temper board and verify DRC-clean output.

**Validation Steps:**

1. **Run routing**:
   ```bash
   python -m temper_placer.experiments.run_full_board_v5 \
       --board temper_full.kicad_pcb \
       --grid 0.2 \
       --output routed_v5_final.kicad_pcb
   ```

2. **Verify metrics**:
   - [ ] Connectivity: 100%
   - [ ] Grid conflicts: 0
   - [ ] Geometric violations: 0
   - [ ] Routing time: < 300 seconds

3. **Run KiCad DRC**:
   ```bash
   kicad-cli pcb drc routed_v5_final.kicad_pcb --output drc_report.json
   # Target: 0 errors
   ```

4. **Visual inspection**:
   - Power traces visibly wider than signals
   - SPI bus traces parallel
   - No traces in HV zone unless HV nets
   - Vias not clustered excessively

5. **Compare to baseline**:
   | Metric | Baseline (v5-current) | Target (v5-final) |
   |--------|----------------------|-------------------|
   | Grid conflicts | 568 | 0 |
   | Geometric violations | 237 | 0 |
   | Routing time | 182s | < 300s |

**Success Criteria:**
- [ ] Zero DRC violations from router output
- [ ] Zero DRC violations from KiCad validator
- [ ] No manual intervention required
- [ ] Performance regression < 2x

**If violations remain:**
1. Log all remaining violations with net names and locations
2. Create follow-up tasks for specific violation patterns
3. Document any violations that require board redesign (placement issues)

