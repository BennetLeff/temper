# DRC Remediation Architecture & Implementation Plan

**Date:** 2025-12-29
**Context:** Router V3 achieves 100% connectivity with 1,134 DRC violations
**Goal:** Scalable automated DRC-clean routing for end-to-end PCB design

---

## Executive Summary

### Current State
- **routed_v5.kicad_pcb**: 100% routed, 1,134 violations, 45 unconnected items
- **Root cause**: RRR algorithm with `soft_blocking=True` allows violations to achieve connectivity
- **Violation distribution**:
  - 811 electrical (clearance: 499, shorting: 199, crossing: 113)
  - 271 manufacturing (solder mask: 101, hole issues: 170)
  - 45 topology (unconnected power islands)
  - 33 library (footprint errors)

### Recommendation
**Implement 3-layer DRC enforcement architecture:**
1. **DRCOracle** (constraint engine) - queryable design rules
2. **Router hardening** (pathfinding integration) - enforce rules during search
3. **Placer-router feedback** (iterative refinement) - adjust placement when routing fails

**Expected outcome:** 90%+ DRC-clean boards within 10 placer-router iterations

---

## Problem Analysis

### Violation Taxonomy

| Category | Error Types | Count | Router Behavior Causing Issue |
|----------|-------------|-------|-------------------------------|
| **Electrical** | clearance, shorting_items, tracks_crossing | 811 | `soft_blocking=True` allows net overlap at high cost; clearance not enforced in neighbor selection |
| **Manufacturing** | solder_mask_bridge, holes_co_located, hole_to_hole, hole_clearance | 271 | Via placement uses grid cell centers without validating proximity to other vias/pads |
| **Topology** | unconnected_items (GND: 9 islands, +3V3: 9 islands) | 45 | Power nets excluded from routing (`--exclude-power-nets`), no automatic copper pour stitching |
| **Library** | lib_footprint_issues | 33 | Malformed footprint definitions from KiCad library import |

### Router Behavior Deep Dive

**Current MazeRouter A* Neighbor Selection** (`maze_router.py:709-721`):
```python
def _get_neighbors(self, cell: GridCell, ...) -> list[GridCell]:
    neighbors = []
    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        nx, ny = cell.x + dx, cell.y + dy
        if 0 <= nx < grid_size and int(self.occupancy[nx, ny, cell.layer]) != -1:
            neighbors.append(GridCell(nx, ny, cell.layer))  # ✓ Added to search
```

**Key observation:** Only checks `occupancy != -1` (not component-blocked), does NOT reject cells occupied by other nets (`occupancy == 2`).

**When soft_blocking=True** (`fast_router.py:206-208`):
```python
# Check if cell is occupied by another net
cell_occupied = occupancy[nx, ny, nl] == 2

# If soft_blocking is disabled, occupied cells are impassable
if cell_occupied and not soft_blocking:
    continue  # ✗ Blocked - cannot route through
```

**Behavior matrix:**
| `soft_blocking` | Occupied cell treatment | Result |
|-----------------|------------------------|--------|
| `False` | Infinite cost (blocked) | Router fails if no DRC-clean path exists |
| `True` | 50.0 × (1 + congestion) penalty | Router completes with violations |

**Why RRR fails to converge:**
1. Iteration 1: Routes all nets, creating 1,000+ conflicts
2. Iteration 2-50: Rips up ~10% of nets, reroutes with 2× higher congestion cost
3. Conflict count decreases logarithmically: 1000 → 800 → 650 → 550 → ...
4. After 50 iterations: Still 200-500 conflicts remain (local minima)

**The fundamental issue:** RRR assumes a conflict-free solution exists. When placement is too tight, no amount of rip-up will resolve it.

---

## Solution Architecture

### Layer 1: DRCOracle (Constraint Engine)

**Purpose:** Centralized, queryable design rule database

**Core interface:**
```python
class DRCOracle:
    def can_place_track_segment(
        self, start: Point, end: Point, layer: int, net: str, width: float
    ) -> Tuple[bool, Optional[str]]:
        """Returns (is_valid, violation_reason)"""

    def get_valid_via_sites(
        self, target: Point, search_radius: float, net: str
    ) -> List[Point]:
        """Returns list of DRC-compliant via locations sorted by distance"""

    def register_route(self, net: str, geometry: List[Segment]):
        """Update spatial index with new routed geometry"""
```

**Key features:**
- **Spatial indexing:** cKDTree for O(log n) proximity queries (vs. O(n) linear scan)
- **Net-class awareness:** Power nets get different clearance rules
- **Layer-specific rules:** Inner layers have relaxed clearances
- **Incremental updates:** Geometry index updated after each net routed

**Implementation location:** `packages/temper-placer/src/temper_placer/routing/constraints/drc_oracle.py`

**Design rules source:**
```python
@dataclass
class DesignRules:
    # Parsed from .kicad_pcb (design_rules) section
    track_to_track: float = 0.2  # mm
    track_to_pad: float = 0.2
    via_to_via: float = 0.4
    hole_to_hole: float = 0.5  # Mechanical constraint
    min_track_width: float = 0.2

    # Net class overrides
    power_clearance: float = 0.5  # GND, VCC, +15V
```

### Layer 2: Router Hardening (Mandatory Constraint Checking)

**Modify MazeRouter to enforce DRC during pathfinding:**

**Location:** `maze_router.py:_get_neighbor_cost()` (line 249)

**Changes:**
```python
def _get_neighbor_cost(self, current: GridCell, neighbor: GridCell, ...) -> float:
    # ... existing cost calculation (via_cost, congestion, etc.) ...

    # NEW: DRC validation
    if self.drc_oracle and not self.soft_blocking:  # Only in strict mode
        start_world = self._grid_to_world(current.x, current.y)
        end_world = self._grid_to_world(neighbor.x, neighbor.y)

        is_valid, reason = self.drc_oracle.can_place_track_segment(
            start_world, end_world,
            layer=neighbor.layer,
            net=self.current_net,  # Need to thread net context
            width=self.get_track_width(self.current_net)
        )

        if not is_valid:
            return 1e9  # Infinite cost = blocked

    return total_cost
```

**Threading net context through A\*:**
```python
# In route_net_rrr():
self.current_net = net_name  # Set before calling find_path_rrr()
try:
    path = self.find_path_rrr(start, end, layer, ...)
finally:
    self.current_net = None  # Clear after routing
```

**Via placement intelligence** (`maze_router.py:1400-1403`):
```python
# Old: Place via at grid cell center
via_x = cell.x * self.cell_size + self.origin[0]
via_y = cell.y * self.cell_size + self.origin[1]

# New: Query oracle for valid via sites
target = (cell.x * self.cell_size + self.origin[0],
          cell.y * self.cell_size + self.origin[1])
valid_sites = self.drc_oracle.get_valid_via_sites(
    target, search_radius=2.0, net=net_name
)
if not valid_sites:
    return RoutePath(success=False, failure_reason="no_valid_via_sites")
via_pos = valid_sites[0]  # Closest valid site
```

### Layer 3: Placer-Router Feedback Loop

**Current placement:** Optimized for thermal/electrical objectives, ignores routability

**Proposed:** Iterative refinement with routing congestion as a loss term

**Location:** `packages/temper-placer/src/temper_placer/pipeline/auto_layout.py`

**Pseudocode:**
```python
def iterative_place_and_route(
    netlist: Netlist,
    board: Board,
    max_iterations: int = 10
) -> Board:
    """Iterative placer-router loop."""

    for iteration in range(max_iterations):
        # 1. Run placer
        placed_board = placer.optimize(
            netlist, board,
            loss_terms=[
                ThermalBudgetLoss(),
                PowerLoopAreaLoss(),
                RoutingCongestionLoss(weight=iteration * 0.1)  # Ramp up over time
            ]
        )

        # 2. Run router in STRICT mode (soft_blocking=False)
        router = MazeRouter.from_board(
            placed_board,
            soft_blocking=False,  # Enforce DRC
            drc_oracle=DRCOracle(placed_board, DesignRules.from_board(placed_board))
        )
        route_results = router.rrr_route_all_nets(netlist, ...)

        # 3. Check success
        failed_nets = [n for n, r in route_results.items() if not r.success]
        unconnected_islands = detect_islands(placed_board)

        if not failed_nets and not unconnected_islands:
            return placed_board  # SUCCESS: DRC-clean!

        # 4. Feedback: Update placer loss function
        congestion_map = build_congestion_heatmap(route_results)
        placer.add_repulsion_from_hotspots(congestion_map)

        # 5. Specific component adjustments
        for net_name in failed_nets:
            failure = route_results[net_name]
            if failure.failure_reason == "no_valid_via_sites":
                # Move components farther apart
                components = netlist.get_components_on_net(net_name)
                placer.increase_spacing(components, delta=1.0)  # +1mm
            elif failure.failure_reason.startswith("clearance_violation"):
                # Rotate or shift blocking component
                blocking_comp = extract_blocking_component(failure.failure_reason)
                placer.nudge_component(blocking_comp, direction="away_from_congestion")

        print(f"Iteration {iteration}: {len(failed_nets)} failed nets, adjusting placement...")

    # Max iterations reached - report partial success
    raise RoutingConvergenceError(f"Could not achieve DRC-clean routing after {max_iterations} iterations")
```

**Congestion heatmap construction:**
```python
def build_congestion_heatmap(route_results: Dict[str, RoutePath]) -> np.ndarray:
    """Build 2D heatmap of routing difficulty."""
    heatmap = np.zeros((grid_width, grid_height))

    for net_name, result in route_results.items():
        if not result.success:
            # Mark failed net's bounding box as high congestion
            bbox = compute_net_bounding_box(net_name)
            heatmap[bbox] += 10.0
        else:
            # Mark routed path by difficulty
            for cell, difficulty in zip(result.cells, result.cell_difficulties):
                heatmap[cell.x, cell.y] += difficulty

    # Smooth with Gaussian filter
    from scipy.ndimage import gaussian_filter
    return gaussian_filter(heatmap, sigma=2.0)
```

---

## Implementation Roadmap

### Sprint 1: Quick Wins (1-2 days)

**Goal:** Eliminate 300+ violations with minimal code changes

**Tasks:**
1. **Fix library footprint issues (33 violations)**
   - Run: `kicad-cli fp check --footprint "*.kicad_mod"`
   - Auto-patch: `scripts/fix_footprint_clearances.py`

2. **Eliminate duplicate vias (83 holes_co_located)**
   - Modify: `temper_placer/io/trace_writer.py`
   - Deduplicate via list before writing to PCB
   ```python
   via_set = set()  # (x, y, net)
   for via in all_vias:
       key = (round(via.x, 3), round(via.y, 3), via.net)  # 1μm precision
       if key not in via_set:
           via_set.add(key)
           write_via_to_pcb(via)
   ```

3. **Enforce occupancy grid (eliminate 113 tracks_crossing)**
   - Already implemented in commit 144c052!
   - **Action:** Run router with `--soft-blocking` flag DISABLED (default)
   - Verify by routing test net and checking for `tracks_crossing` in DRC

**Expected outcome:** Violations reduced from 1,134 → ~800

### Sprint 2: DRCOracle MVP (1 week)

**Goal:** Build queryable constraint engine

**Deliverables:**
- `drc_oracle.py`: Core constraint checking logic
- `design_rules.py`: Parser for KiCad design rules
- `spatial_index.py`: cKDTree wrapper for geometry queries
- Unit tests: `tests/routing/test_drc_oracle.py`

**Success criteria:**
- Oracle can validate track segment clearance in <1ms per query
- Oracle detects all clearance violations from routed_v5.kicad_pcb
- Oracle suggests valid via sites within 2mm radius of target

### Sprint 3: Router Integration (1 week)

**Goal:** Router enforces DRC during pathfinding

**Changes:**
- `maze_router.py`: Add `drc_oracle` parameter, thread `current_net` through A*
- `fast_router.py`: Add optional clearance validation in Numba kernel
- `trace_writer.py`: Use oracle for via site selection

**Testing:**
- Route simple 2-net board: expect DRC-clean or routing failure (not violations)
- Route complex board: compare strict mode (DRC-enforced) vs. soft mode (current)

**Expected outcome:**
- Strict mode: 50-80% nets routed, 0 DRC violations
- Soft mode: 100% routed, 1,134 violations (baseline)

### Sprint 4: Placer-Router Loop (2 weeks)

**Goal:** Close the feedback loop

**Deliverables:**
- `auto_layout.py`: Iterative placement refinement
- `congestion_loss.py`: Placer loss term for routing hotspots
- End-to-end test: Route temper PCB with automated placement adjustment

**Success criteria:**
- Iteration 1: 60% nets routed DRC-clean
- Iteration 5: 90% nets routed DRC-clean
- Iteration 10: 95%+ or convergence failure detected

### Sprint 5: Island Detection & Copper Pours (1 week)

**Goal:** Eliminate 45 unconnected topology errors

**Approach:**
1. **Power plane generation:**
   - Use KiCad zones API to create copper pours on inner layers
   - GND plane on In1.Cu
   - VCC/+15V plane on In2.Cu

2. **Stitching via insertion:**
   - After signal routing, run flood-fill on power nets
   - Detect isolated islands
   - Auto-insert vias to bridge islands (prioritize low-congestion areas)

**Location:** `packages/temper-placer/src/temper_placer/routing/power_plane_stitcher.py`

**Pseudocode:**
```python
def stitch_power_planes(board: Board, netlist: Netlist) -> Board:
    """Insert stitching vias to connect isolated power islands."""
    power_nets = ["GND", "PGND", "CGND", "+3V3", "+5V", "+15V", "VCC"]

    for net_name in power_nets:
        islands = detect_islands_for_net(board, net_name)

        if len(islands) > 1:
            # Find minimum spanning tree connecting island centroids
            centroids = [island.centroid for island in islands]
            mst_edges = compute_mst(centroids)

            # Insert vias along MST edges
            for edge in mst_edges:
                via_positions = sample_via_sites_along_edge(edge, spacing=5.0)  # 5mm spacing
                for pos in via_positions:
                    insert_power_via(board, pos, net_name, layers=["F.Cu", "In1.Cu"])

    return board
```

---

## Performance Considerations

### Concern: DRC checking on every A* neighbor expansion is slow

**Baseline performance:**
- Current router: ~100 nets/second (no DRC checking)
- With oracle: ~10-50 nets/second (estimated 10-50× slowdown)

**Mitigation strategies:**

1. **Lazy validation:** Only check final path, not intermediate A* nodes
   - Pro: Fast (no slowdown)
   - Con: Router may explore invalid paths, wasting search effort

2. **Cached clearance grid:** Pre-compute clearance keepouts for all existing geometry
   - Pro: O(1) lookup instead of O(log n) spatial query
   - Con: Cache invalidation complexity

3. **Hybrid approach:** Grid-based coarse check + oracle fine check
   ```python
   # Coarse check: Is cell in clearance grid? (O(1))
   if clearance_grid[nx, ny, nl] != 0:
       return 1e9  # Blocked

   # Fine check: Exact geometry distance (only if coarse check passes)
   if not oracle.can_place_track_segment(...):
       return 1e9  # Blocked
   ```

4. **Numba integration:** Compile clearance checking into Numba kernel
   - Requires passing spatial index data to Numba (non-trivial)
   - Potential 100× speedup for clearance queries

**Recommendation:** Start with **lazy validation** (Strategy 1) for MVP. Optimize only if routing time becomes a bottleneck.

---

## Validation Metrics

**Track these metrics to measure progress:**

```python
@dataclass
class RoutingQualityMetrics:
    # Connectivity
    completion_rate: float  # % of nets successfully routed
    unconnected_islands: int  # Topology failures

    # DRC compliance
    total_violations: int
    violation_breakdown: Dict[str, int]  # clearance: 499, shorting: 199, ...

    # Routing quality
    total_wirelength: float  # mm
    via_count: int
    avg_track_width: float

    # Performance
    routing_time_ms: float
    placer_iterations: int
    drc_query_count: int
```

**Success criteria for each sprint:**
| Sprint | Completion Rate | Violations | Notes |
|--------|-----------------|------------|-------|
| 0 (Baseline) | 100% | 1,134 | soft_blocking=True |
| 1 (Quick wins) | 100% | ~800 | Deduplication + library fixes |
| 2 (Oracle MVP) | N/A | N/A | Tooling sprint |
| 3 (Router integration) | 50-80% | 0-50 | strict mode enforces DRC |
| 4 (Placer loop, iter 1) | 60% | 0 | Placement not yet optimized |
| 4 (Placer loop, iter 10) | 90%+ | 0 | Converged solution |
| 5 (Power stitching) | 95%+ | 0 | All islands resolved |

---

## Hypergraph Router Future-Proofing

**Current plan:** Transition to physics-informed hypergraph router

**DRCOracle compatibility:**
- Oracle is **router-agnostic** - any routing algorithm can query it
- Hypergraph router will call `oracle.can_place_track_segment()` during edge placement
- Same spatial index, same design rules, same API

**Hypergraph-specific enhancements:**
```python
class HypergraphDRCOracle(DRCOracle):
    """Extended oracle for hypergraph constraint encoding."""

    def encode_clearance_as_hyperedge(
        self, track1: Track, track2: Track
    ) -> HyperEdge:
        """Represent clearance constraint as hyperedge.

        The hypergraph solver will enforce this constraint during
        energy minimization (physics-based routing).
        """
        required_distance = self.get_clearance(track1.net, track2.net)
        return RepulsionEdge(
            nodes=[track1, track2],
            repulsion_strength=1.0 / required_distance
        )
```

**Key insight:** DRCOracle serves as the **bridge** between discrete grid routing (current) and continuous hypergraph optimization (future).

---

## Conclusion

**Strategic takeaway:**
Your router already has the infrastructure to prevent violations (commit 144c052). The issue is **architectural**: constraints are checked after routing (reactive) instead of during routing (proactive).

**Implementation priority:**
1. **Sprint 1 (Quick wins)**: Get to 800 violations in 2 days
2. **Sprint 2-3 (DRCOracle + Router)**: Build constraint enforcement pipeline (2 weeks)
3. **Sprint 4 (Placer loop)**: Close the feedback loop (2 weeks)
4. **Sprint 5 (Power planes)**: Eliminate topology errors (1 week)

**Total timeline:** 5-6 weeks to DRC-clean automated routing

**Next steps:**
1. Confirm priority: Quality-first (your answer) → Start with Sprint 2 (DRCOracle)
2. Analyze current router in strict mode: `./scripts/route_v3.sh` (without `--soft-blocking`)
3. Design DRCOracle API contracts and spatial index structure
4. Implement MVP and integrate with MazeRouter

---

**Document version:** 1.0
**Author:** Claude (Router Analysis Agent)
**Review:** Pending user feedback
