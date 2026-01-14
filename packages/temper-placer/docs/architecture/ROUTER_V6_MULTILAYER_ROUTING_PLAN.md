# Router V6: Multi-Layer Routing Architecture Plan

## Executive Summary

This document outlines the architecture for a **production-quality multi-layer PCB router** that:
- Routes signals across multiple layers with explicit via insertion
- Models via costs accurately (manufacturing, signal integrity, reliability)
- Validates against ground-truth human-routed boards
- Follows professional PCB design practices

**Target Boards:**
- Temper induction heater (4-layer, SMD-heavy, high current)
- Generic 2-4 layer boards with SMD and THT components

---

## 1. Professional PCB Design Principles

### 1.1 What a Human Designer Does

```
1. PLANNING PHASE
   ├── Review layer stackup (which layers for signals vs planes)
   ├── Identify critical nets (power, high-speed, sensitive analog)
   ├── Plan escape routing for dense components (BGA, QFP)
   └── Decide layer preferences per net class

2. ROUTING PHASE
   ├── Route critical nets first (power distribution, clocks)
   ├── Use horizontal/vertical layer conventions
   ├── Minimize vias (each via = cost + signal degradation)
   ├── Place vias strategically (not in dense areas)
   └── Maintain reference plane continuity under high-speed signals

3. VERIFICATION PHASE
   ├── DRC: clearances, annular rings, drill sizes
   ├── Check impedance continuity
   ├── Verify return current paths
   └── Review via density and placement
```

### 1.2 Layer Conventions (Industry Standard)

```
4-Layer Stackup (Most Common):
┌─────────────────────────────────────────┐
│ F.Cu  - Signals (horizontal preference) │ ← Signal Layer
│ In1.Cu - Ground Plane                   │ ← Reference Plane
│ In2.Cu - Power Plane/Islands            │ ← Power Distribution
│ B.Cu  - Signals (vertical preference)   │ ← Signal Layer
└─────────────────────────────────────────┘

Layer Pair Routing:
- F.Cu ↔ B.Cu via through-hole vias
- Signal transitions should cross reference plane minimally
```

### 1.3 Via Types and Costs

| Via Type | Spans | Cost Factor | Use Case |
|----------|-------|-------------|----------|
| Through-hole | All layers | 1.0x | Standard, most common |
| Blind | Surface to inner | 2-3x | HDI boards, escape routing |
| Buried | Inner to inner | 3-5x | High-density, rare |
| Micro-via | Single layer | 2-4x | BGAs, fine pitch |

**Cost Components:**
- Manufacturing: Drilling time, plating, inspection
- Signal Integrity: Stub inductance, impedance discontinuity
- Reliability: Thermal cycling stress, plating quality
- Board Area: Via pad consumes routing space

---

## 2. Data Model

### 2.1 Core Structures

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional

class ViaType(Enum):
    THROUGH = "through"      # F.Cu to B.Cu (all layers)
    BLIND_TOP = "blind_top"  # F.Cu to inner layer
    BLIND_BOT = "blind_bot"  # Inner layer to B.Cu
    BURIED = "buried"        # Inner to inner
    MICRO = "micro"          # Single layer transition

@dataclass
class Via:
    """A via connecting layers."""
    position: tuple[float, float]  # (x, y) in mm
    via_type: ViaType
    start_layer: str  # "F.Cu", "In1.Cu", etc.
    end_layer: str
    drill_diameter: float  # mm
    pad_diameter: float    # mm
    net: str

    @property
    def annular_ring(self) -> float:
        """Copper ring width around drill."""
        return (self.pad_diameter - self.drill_diameter) / 2

@dataclass
class LayerTransition:
    """A layer change during routing."""
    position: tuple[float, float]
    from_layer: str
    to_layer: str
    via: Via

@dataclass
class MultiLayerPath:
    """A path that may span multiple layers."""
    net_name: str
    segments: list[TraceSegment]  # Each has layer attribute
    vias: list[Via]
    total_length: float
    via_count: int
    layer_transitions: int
```

### 2.2 3D Grid Representation

```python
@dataclass
class MultiLayerGrid:
    """3D occupancy grid for multi-layer routing."""

    layers: dict[str, OccupancyGrid]  # layer_name -> 2D grid
    via_grid: np.ndarray  # 2D grid of valid via locations
    via_keepouts: list[Polygon]  # Areas where vias prohibited

    # Layer connectivity
    layer_pairs: list[tuple[str, str]]  # Valid layer transitions
    via_costs: dict[tuple[str, str], float]  # (from, to) -> cost

    def get_cell_state(self, x: int, y: int, layer: str) -> CellState:
        """Get state of a specific 3D cell."""
        return self.layers[layer].grid[y, x]

    def can_place_via(self, x: int, y: int, from_layer: str, to_layer: str) -> bool:
        """Check if via placement is valid at this location."""
        # Check via grid
        if self.via_grid[y, x] == 0:
            return False

        # Check both layers are free at this point
        if not self.layers[from_layer].is_free(x, y):
            return False
        if not self.layers[to_layer].is_free(x, y):
            return False

        # Check via keepouts
        point = Point(self.grid_to_world(x, y))
        for keepout in self.via_keepouts:
            if keepout.contains(point):
                return False

        return True

    def get_via_cost(self, from_layer: str, to_layer: str) -> float:
        """Get cost of placing a via between layers."""
        return self.via_costs.get((from_layer, to_layer), float('inf'))
```

---

## 3. Algorithm: 3D A* with Via Insertion

### 3.1 State Space

```python
@dataclass(frozen=True)
class RoutingState:
    """State in 3D routing search."""
    x: int
    y: int
    layer: str

    def __hash__(self):
        return hash((self.x, self.y, self.layer))

# Moves in 3D space
class Move(Enum):
    # Same-layer moves (8-connected)
    RIGHT = (1, 0, None)
    LEFT = (-1, 0, None)
    UP = (0, 1, None)
    DOWN = (0, -1, None)
    DIAG_RU = (1, 1, None)
    DIAG_RD = (1, -1, None)
    DIAG_LU = (-1, 1, None)
    DIAG_LD = (-1, -1, None)

    # Layer transitions (via insertion)
    VIA_DOWN = (0, 0, "down")  # To next layer down
    VIA_UP = (0, 0, "up")      # To next layer up
```

### 3.2 Cost Function

```python
def calculate_move_cost(
    current: RoutingState,
    move: Move,
    grid: MultiLayerGrid,
    design_rules: DesignRules,
) -> float:
    """
    Calculate cost of a move, following professional design principles.

    Cost Components:
    1. Distance cost (favor shorter paths)
    2. Via cost (penalize layer changes)
    3. Direction change cost (favor straight lines)
    4. Congestion cost (avoid dense areas)
    5. Layer preference cost (honor routing conventions)
    """

    dx, dy, layer_change = move.value

    # Base distance cost
    if dx != 0 and dy != 0:
        distance_cost = 1.414  # Diagonal
    elif layer_change:
        distance_cost = 0.0    # Via has no XY distance
    else:
        distance_cost = 1.0    # Cardinal

    # Via cost (significant penalty)
    via_cost = 0.0
    if layer_change:
        target_layer = get_target_layer(current.layer, layer_change, grid)
        if target_layer:
            via_cost = grid.get_via_cost(current.layer, target_layer)
            # Additional penalty based on via type
            via_cost *= get_via_type_multiplier(current.layer, target_layer)
        else:
            return float('inf')  # Invalid layer transition

    # Direction change penalty (favor straight lines - looks professional)
    # Implemented via path history in A* (not shown here)
    direction_cost = 0.0

    # Congestion penalty (from previous routing attempts)
    congestion_cost = grid.get_congestion(current.x + dx, current.y + dy)

    # Layer preference (honor H/V conventions)
    layer_pref_cost = 0.0
    if not layer_change:
        if current.layer == "F.Cu" and dy != 0:  # Vertical on horizontal layer
            layer_pref_cost = 0.1
        elif current.layer == "B.Cu" and dx != 0:  # Horizontal on vertical layer
            layer_pref_cost = 0.1

    return (
        distance_cost +
        via_cost +
        direction_cost +
        congestion_cost * 0.5 +
        layer_pref_cost
    )

# Via cost calibration (based on industry practices)
VIA_BASE_COST = 10.0  # Equivalent to ~10 grid cells of routing

def get_via_type_multiplier(from_layer: str, to_layer: str) -> float:
    """Via cost multiplier based on type."""
    if is_through_via(from_layer, to_layer):
        return 1.0  # Standard
    elif is_blind_via(from_layer, to_layer):
        return 2.5  # More expensive
    elif is_buried_via(from_layer, to_layer):
        return 4.0  # Most expensive
    return 1.0
```

### 3.3 3D A* Implementation

```python
def astar_3d(
    start: RoutingState,
    goal: RoutingState,
    grid: MultiLayerGrid,
    design_rules: DesignRules,
    max_vias: int = 4,  # Limit via count per net segment
) -> MultiLayerPath | None:
    """
    3D A* pathfinding with via insertion.

    Key differences from 2D A*:
    1. State includes layer
    2. Via insertion is a valid move
    3. Via budget prevents excessive layer changes
    """
    from heapq import heappush, heappop

    # Priority queue: (f_cost, state, via_count)
    frontier = []
    heappush(frontier, (0, start, 0))

    came_from: dict[RoutingState, tuple[RoutingState, Move]] = {start: None}
    cost_so_far: dict[RoutingState, float] = {start: 0}
    via_count: dict[RoutingState, int] = {start: 0}

    while frontier:
        _, current, curr_vias = heappop(frontier)

        # Goal reached?
        if current.x == goal.x and current.y == goal.y:
            # Allow goal on any layer (will add via if needed)
            if current.layer == goal.layer:
                return reconstruct_path(came_from, current)
            elif curr_vias < max_vias:
                # Try to reach goal layer
                pass  # Continue searching

        # Explore moves
        for move in Move:
            next_state, is_via = apply_move(current, move, grid)

            if next_state is None:
                continue  # Invalid move

            # Check via budget
            new_via_count = curr_vias + (1 if is_via else 0)
            if new_via_count > max_vias:
                continue

            # Calculate cost
            move_cost = calculate_move_cost(current, move, grid, design_rules)
            new_cost = cost_so_far[current] + move_cost

            if next_state not in cost_so_far or new_cost < cost_so_far[next_state]:
                cost_so_far[next_state] = new_cost
                via_count[next_state] = new_via_count

                # Heuristic: 3D distance to goal
                priority = new_cost + heuristic_3d(next_state, goal, grid)
                heappush(frontier, (priority, next_state, new_via_count))
                came_from[next_state] = (current, move)

    return None  # No path found

def heuristic_3d(state: RoutingState, goal: RoutingState, grid: MultiLayerGrid) -> float:
    """
    3D heuristic for A*.

    Includes:
    - XY distance (octile for 8-connected)
    - Layer distance (minimum vias needed)
    """
    # XY distance (octile)
    dx = abs(state.x - goal.x)
    dy = abs(state.y - goal.y)
    xy_dist = max(dx, dy) + 0.414 * min(dx, dy)

    # Layer distance
    if state.layer != goal.layer:
        layer_dist = VIA_BASE_COST  # At least one via needed
    else:
        layer_dist = 0

    return xy_dist + layer_dist
```

---

## 4. Via Placement Strategy

### 4.1 Via Location Constraints

```python
def build_via_validity_grid(
    pcb: ParsedPCB,
    grid: MultiLayerGrid,
) -> np.ndarray:
    """
    Build grid marking valid via locations.

    Professional rules:
    1. Not under components (unless via-in-pad allowed)
    2. Not in keepout zones
    3. Minimum distance from other vias
    4. Minimum distance from board edge
    5. Prefer grid-aligned positions
    """
    via_grid = np.ones((grid.height_cells, grid.width_cells), dtype=np.int8)

    # Rule 1: Component keepouts
    for comp in pcb.components:
        courtyard = comp.get_courtyard()
        mark_polygon_blocked(via_grid, courtyard, grid)

    # Rule 2: Explicit keepout zones
    for zone in pcb.keepouts:
        if zone.no_vias:
            mark_polygon_blocked(via_grid, zone.polygon, grid)

    # Rule 3: Via-to-via spacing (will be checked dynamically)

    # Rule 4: Board edge clearance
    edge_clearance = pcb.design_rules.min_via_to_edge_mm
    board_outline = pcb.board.boundary
    inner_boundary = board_outline.buffer(-edge_clearance)
    mark_outside_polygon_blocked(via_grid, inner_boundary, grid)

    # Rule 5: Prefer grid alignment (soft preference in cost, not validity)

    return via_grid
```

### 4.2 Via-to-Plane Connections

```python
def connect_to_plane(
    pin_position: tuple[float, float],
    pin_layer: str,
    target_plane: str,  # "GND", "+15V", etc.
    grid: MultiLayerGrid,
    pcb: ParsedPCB,
) -> Via | None:
    """
    Create via connection from a pin to a power/ground plane.

    Professional practice:
    - Direct drop to plane layer
    - Thermal relief at plane connection
    - Via sizing based on current requirements
    """
    # Find which layer has this plane
    plane_layer = None
    for layer in pcb.stackup.layers:
        if layer.plane_net == target_plane:
            plane_layer = layer.name
            break

    if not plane_layer:
        return None  # No plane for this net

    # Check via validity at pin position
    gx, gy = grid.world_to_grid(*pin_position)
    if not grid.can_place_via(gx, gy, pin_layer, plane_layer):
        # Try nearby locations
        for dx, dy in [(1,0), (-1,0), (0,1), (0,-1)]:
            if grid.can_place_via(gx+dx, gy+dy, pin_layer, plane_layer):
                gx, gy = gx+dx, gy+dy
                break
        else:
            return None  # No valid via location

    # Size via based on net class
    net_class = pcb.design_rules.get_net_class(target_plane)

    return Via(
        position=grid.grid_to_world(gx, gy),
        via_type=get_via_type(pin_layer, plane_layer),
        start_layer=pin_layer,
        end_layer=plane_layer,
        drill_diameter=net_class.via_drill_mm,
        pad_diameter=net_class.via_diameter_mm,
        net=target_plane,
    )
```

---

## 5. Validation Strategy

### 5.1 Ground Truth Comparison

```python
@dataclass
class RoutingComparison:
    """Comparison between generated and reference routing."""

    # Quantitative metrics
    total_via_count: tuple[int, int]  # (generated, reference)
    total_trace_length: tuple[float, float]
    layer_distribution: dict[str, tuple[float, float]]  # layer -> (gen, ref) lengths

    # Per-net metrics
    net_metrics: dict[str, NetComparisonMetrics]

    # Quality scores
    via_efficiency: float  # ref_vias / gen_vias (higher = better)
    length_efficiency: float  # ref_length / gen_length
    layer_balance_score: float  # How well layer usage matches

@dataclass
class NetComparisonMetrics:
    """Per-net comparison metrics."""
    net_name: str
    gen_vias: int
    ref_vias: int
    gen_length: float
    ref_length: float
    gen_layers: set[str]
    ref_layers: set[str]

    @property
    def via_delta(self) -> int:
        return self.gen_vias - self.ref_vias

    @property
    def length_ratio(self) -> float:
        return self.gen_length / self.ref_length if self.ref_length > 0 else float('inf')

def compare_to_reference(
    generated: RoutingResults,
    reference_path: Path,
) -> RoutingComparison:
    """
    Compare generated routing to human-routed reference.

    Professional validation criteria:
    1. Via count should be ≤ reference (fewer is better)
    2. Trace length should be ≤ 1.2x reference
    3. Layer distribution should be similar
    4. All nets that route in reference should route in generated
    """
    ref = parse_kicad_pcb(reference_path)

    # Build per-net metrics
    net_metrics = {}

    for net_name in generated.compiled_routes:
        gen_route = generated.compiled_routes[net_name]
        ref_traces = [t for t in ref.traces if t.net == net_name]
        ref_vias = [v for v in ref.vias if v.net == net_name]

        net_metrics[net_name] = NetComparisonMetrics(
            net_name=net_name,
            gen_vias=len(gen_route.vias),
            ref_vias=len(ref_vias),
            gen_length=gen_route.path.path_length,
            ref_length=sum(trace_length(t) for t in ref_traces),
            gen_layers=set(s.layer for s in gen_route.segments),
            ref_layers=set(t.layer for t in ref_traces),
        )

    # Aggregate metrics
    # ... (calculate totals and scores)

    return RoutingComparison(...)
```

### 5.2 Test Suite Structure

```python
# tests/router_v6/test_multilayer_routing.py

import pytest
from pathlib import Path

class TestMultiLayerRouting:
    """Test suite for multi-layer routing correctness."""

    # === UNIT TESTS ===

    def test_via_placement_respects_keepouts(self, sample_grid):
        """Vias must not be placed in keepout zones."""
        # Place keepout
        sample_grid.add_keepout(Polygon(...))

        # Attempt via in keepout
        result = sample_grid.can_place_via(x, y, "F.Cu", "B.Cu")
        assert result == False

    def test_via_cost_calculation(self):
        """Via costs should reflect manufacturing reality."""
        through_cost = calculate_via_cost("F.Cu", "B.Cu", ViaType.THROUGH)
        blind_cost = calculate_via_cost("F.Cu", "In1.Cu", ViaType.BLIND_TOP)

        # Blind vias should cost more
        assert blind_cost > through_cost

    def test_3d_astar_finds_path_with_via(self, blocked_grid):
        """A* should insert via when direct path blocked."""
        # Block direct F.Cu path
        blocked_grid.layers["F.Cu"].block_region(...)

        # Route should succeed using B.Cu + via
        result = astar_3d(start, goal, blocked_grid, rules)

        assert result is not None
        assert result.via_count >= 1

    def test_via_budget_respected(self, grid):
        """Router should not exceed via limit."""
        result = astar_3d(start, goal, grid, rules, max_vias=2)

        assert result.via_count <= 2

    # === INTEGRATION TESTS ===

    @pytest.mark.parametrize("board_name", [
        "piantor_left",
        "rp2040_designguide",
        "splitflap_sensor",
    ])
    def test_routes_reference_board(self, board_name):
        """Router should successfully route reference boards."""
        board_path = get_fixture_path(board_name)

        result = RouterV6Pipeline(verbose=False).run(board_path)

        # Should route at least 90% of nets
        assert result.completion_rate >= 0.90

    @pytest.mark.parametrize("board_name", [
        "piantor_left",
        "rp2040_designguide",
    ])
    def test_via_count_reasonable(self, board_name):
        """Generated via count should not exceed 2x reference."""
        board_path = get_fixture_path(board_name)
        ref_path = get_routed_fixture_path(board_name)

        result = RouterV6Pipeline().run(board_path)
        comparison = compare_to_reference(result, ref_path)

        gen_vias, ref_vias = comparison.total_via_count
        assert gen_vias <= ref_vias * 2.0

    # === GROUND TRUTH TESTS ===

    def test_matches_known_good_solution(self):
        """
        Golden test: specific board should produce known routing.

        This test uses a small, hand-verified board where we know
        the optimal routing. Any regression will fail this test.
        """
        result = route_golden_board()

        assert result.via_count == GOLDEN_VIA_COUNT
        assert abs(result.total_length - GOLDEN_LENGTH) < 1.0  # 1mm tolerance

    # === DRC TESTS ===

    def test_no_drc_violations(self, routed_board):
        """Routed board should pass DRC."""
        violations = run_drc(routed_board)

        # Filter out known acceptable violations
        real_violations = [v for v in violations if not v.is_acceptable]

        assert len(real_violations) == 0

    def test_via_annular_ring(self, routed_board):
        """All vias should have sufficient annular ring."""
        for via in routed_board.vias:
            assert via.annular_ring >= MIN_ANNULAR_RING
```

### 5.3 Validation Boards (Ground Truth)

```
tests/fixtures/validation/
├── golden_2layer_simple/
│   ├── input.kicad_pcb      # Unrouted
│   ├── reference.kicad_pcb  # Human-routed (golden)
│   └── expected_metrics.json # Via count, lengths, etc.
│
├── golden_4layer_power/
│   ├── input.kicad_pcb
│   ├── reference.kicad_pcb
│   └── expected_metrics.json
│
└── regression/
    ├── piantor_left/
    ├── rp2040_designguide/
    └── temper_gate_driver/  # Target board subset
```

---

## 6. Implementation Phases

### Phase 1: Foundation (Week 1-2)
```
□ Implement MultiLayerGrid data structure
□ Implement Via data model
□ Add via validity checking
□ Unit tests for via placement rules
```

### Phase 2: 3D Routing (Week 3-4)
```
□ Implement RoutingState (x, y, layer)
□ Implement 3D A* with via moves
□ Calibrate via costs
□ Test on simple 2-layer boards
```

### Phase 3: Via-to-Plane (Week 5)
```
□ Implement plane connection logic
□ Generate thermal reliefs
□ Handle power net routing
□ Test on boards with power planes
```

### Phase 4: Validation (Week 6)
```
□ Implement ground truth comparison
□ Create golden test boards
□ Benchmark against reference boards
□ Document quality metrics
```

### Phase 5: Optimization (Week 7-8)
```
□ Tune via costs for realistic results
□ Add congestion-aware routing
□ Implement rip-up for multi-layer
□ Performance optimization
```

---

## 7. Success Criteria

### Quantitative Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Routing completion | ≥95% | Nets routed / total nets |
| Via efficiency | ≤1.5x reference | Gen vias / ref vias |
| Length efficiency | ≤1.2x reference | Gen length / ref length |
| DRC pass rate | 100% | Violations = 0 |
| Runtime | <60s for 50-net board | Wall clock time |

### Qualitative Criteria

- [ ] Routes look "professional" (straight lines, minimal jogs)
- [ ] Via placement is logical (not random scatter)
- [ ] Layer usage follows conventions (H/V preferences)
- [ ] Power distribution uses planes correctly
- [ ] Would pass review by experienced PCB designer

---

## 8. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Via costs hard to calibrate | Use reference boards to tune empirically |
| 3D A* too slow | Implement hierarchical routing (coarse then fine) |
| Complex layer stackups | Start with 2/4-layer, add complexity later |
| Edge cases in via placement | Comprehensive unit test coverage |
| Regressions during development | Golden tests catch regressions immediately |

---

## Appendix A: Reference Implementations

**Open Source:**
- FreeRouting (Java): Push-and-shove with via insertion
- KiCad's internal router: Basic autorouter
- Horizon EDA: Modern autorouter

**Commercial (for inspiration):**
- Cadence Allegro PCB Router
- Altium ActiveRoute
- PADS Router

**Academic:**
- "Multi-Layer Maze Routing" (Lee, 1961)
- "Negotiated Congestion" (McMurchie & Ebeling, 1995)
- "PathFinder" algorithm
