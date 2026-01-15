# Router Improvement Plan for Benders Convergence

## Problem Statement

The Benders closed-loop fails because the router provides vague failure diagnostics:
- `reason="rip_up_limit"` with `blocking_nets=[]`
- No channel capacity information
- No precise location of congestion
- Cut generation forced to guess → too many cuts → ILP infeasible

## Goal

Enable Benders convergence by improving router feedback quality:
- **Current:** 10 guessed cuts → ILP infeasible
- **Target:** 1-2 precise cuts → ILP feasible → routing succeeds

---

## Phase 1: Channel Capacity Tracking (Priority 1)

### Objective
Track channel utilization so failures report "channel X is at Y% capacity" instead of just "failed."

### Tasks

#### 1.1 Define ChannelState Data Structure
```python
@dataclass
class ChannelState:
    channel_id: str
    capacity: int                    # Number of tracks that fit
    used: int                        # Tracks currently routed
    nets_using: list[str]            # Which nets are using this channel
    bounding_components: tuple[str, str]  # Components defining channel width
    position: tuple[float, float]    # Center of channel
    width_mm: float                  # Current channel width
```

#### 1.2 Instrument Occupancy Grid
- Track which nets occupy which grid cells
- Compute channel utilization during routing
- Store utilization history for failure analysis

#### 1.3 Update Failure Reports
```python
@dataclass
class RoutingFailureReport:
    # Existing fields
    net_name: str
    failure_reason: str
    blocking_nets: list[str]
    
    # NEW fields
    failed_at: tuple[float, float] | None      # Exact failure location
    congested_channel: ChannelState | None     # Channel that was full
    suggested_spacing_mm: float | None         # How much more space needed
    blocking_components: list[str]             # Components to separate
```

### Success Criteria
- Failure reports include `congested_channel` with capacity data
- `blocking_components` populated for 90%+ of failures
- `suggested_spacing_mm` computed from channel analysis

---

## Phase 2: Precise Failure Diagnostics (Priority 1)

### Objective
When routing fails, identify exactly which components need to be separated and by how much.

### Tasks

#### 2.1 Failure Location Tracking
- Record (x, y) position where A* search exhausted options
- Map grid coordinates to physical PCB location
- Store in `failed_at` field

#### 2.2 Blocking Component Identification
- When A* fails, analyze the blocked cells
- Identify which component pads/bodies occupy those cells
- Compute distance to nearest components
- Populate `blocking_components` list

#### 2.3 Spacing Estimation
```python
def estimate_required_spacing(failure: RoutingFailureReport) -> float:
    """
    Estimate how much additional spacing would allow routing.
    
    Based on:
    - Number of tracks needed vs available
    - Current channel width
    - Design rules (trace width + clearance)
    """
    tracks_needed = failure.congested_channel.used + 1
    tracks_available = failure.congested_channel.capacity
    track_pitch = design_rules.trace_width + design_rules.clearance
    
    additional_tracks = tracks_needed - tracks_available
    return additional_tracks * track_pitch * 1.5  # 50% margin
```

#### 2.4 Confidence Scoring
- High confidence: Channel at 100% capacity, clear blocking components
- Medium confidence: Multiple possible blockers
- Low confidence: No clear cause identified

### Success Criteria
- `suggested_spacing_mm` accurate within 20%
- `blocking_components` matches actual blockers 80%+ of time
- Confidence scores correlate with cut effectiveness

---

## Phase 3: Steiner Tree Routing (Priority 2)

### Objective
Route multi-pin nets as optimal trees instead of sequential 2-pin paths.

### Background
Current router for 8-pin net (I_SENSE):
```
Route pin1→pin2, pin2→pin3, pin3→pin4, ...
Each segment can block future segments of SAME NET
```

Better approach:
```
Compute Steiner tree connecting all 8 pins
Route tree edges with global awareness
```

### Tasks

#### 3.1 Rectilinear Steiner Tree (RST) Implementation
```python
def compute_rectilinear_steiner_tree(pins: list[tuple[float, float]]) -> SteinerTree:
    """
    Compute minimum rectilinear Steiner tree for pins.
    
    Uses Hanan grid + MST approximation (1.5x optimal).
    """
    # 1. Build Hanan grid (horizontal/vertical lines through all pins)
    # 2. Find candidate Steiner points at grid intersections
    # 3. Compute MST over pins + Steiner points
    # 4. Remove unnecessary Steiner points
    return tree
```

#### 3.2 Tree-Aware Routing
```python
def route_steiner_tree(tree: SteinerTree, grid: OccupancyGrid) -> list[RoutePath]:
    """
    Route Steiner tree edges with global awareness.
    
    - Route trunk (longest path) first
    - Route branches in order of length
    - Each edge knows about other edges in same tree
    """
```

#### 3.3 Integration with Existing Router
- Detect multi-pin nets (>2 pins)
- Use Steiner tree for multi-pin, A* for 2-pin
- Maintain backward compatibility

### Success Criteria
- I_SENSE (8 pins) routes successfully
- Multi-pin net routing time < 2x single A* call
- No regression on 2-pin nets

---

## Phase 4: Global Routing (Priority 3)

### Objective
Assign nets to routing regions before detailed routing to prevent congestion.

### Tasks

#### 4.1 Channel Graph Construction
```python
@dataclass
class ChannelGraph:
    nodes: list[RoutingRegion]  # Regions between components
    edges: list[ChannelEdge]    # Connections between regions
    
def build_channel_graph(pcb: ParsedPCB, components: list) -> ChannelGraph:
    """Build graph of routing regions from component placement."""
```

#### 4.2 Global Route Assignment
```python
def global_route(nets: list[Net], channel_graph: ChannelGraph) -> dict[str, list[Channel]]:
    """
    Assign each net to a sequence of channels.
    
    Objectives:
    - Minimize total wirelength
    - Balance channel utilization
    - Respect channel capacity
    """
```

#### 4.3 Congestion-Aware Net Ordering
```python
def compute_routing_order(nets: list[Net], global_routes: dict) -> list[str]:
    """
    Order nets for detailed routing based on:
    - Criticality (timing, power)
    - Congestion contribution
    - Flexibility (alternative routes available)
    """
```

#### 4.4 Integration
- Run global routing after channel skeleton extraction
- Use global routes to guide detailed A* routing
- Report congestion from global routing phase

### Success Criteria
- Congestion detected before detailed routing
- Net ordering reduces rip-up iterations by 50%
- No routing oscillation

---

## Phase 5: Benders Integration (Priority 1)

### Objective
Connect improved router diagnostics to cut generation.

### Tasks

#### 5.1 Update Cut Generation
```python
def generate_cuts_from_router_failures(failures: list[RoutingFailureReport]) -> list[RoutabilityCut]:
    cuts = []
    
    for failure in failures:
        if failure.blocking_components and failure.suggested_spacing_mm:
            # PRECISE cut from router data
            for comp in failure.blocking_components:
                cuts.append(RoutabilityCut(
                    component_pair=(comp, failure.net_components[0]),
                    gap_required=failure.suggested_spacing_mm,
                    confidence=0.9,  # High - router told us exactly
                ))
        else:
            # Fall back to heuristics (current behavior)
            ...
    
    return cuts
```

#### 5.2 Incremental Cut Strategy
- Add max 2-3 cuts per iteration
- Prioritize by confidence
- Track cut effectiveness across iterations

#### 5.3 Infeasibility Handling
- If ILP infeasible, remove last cuts
- Return best feasible placement
- Report which cuts caused infeasibility

### Success Criteria
- Benders converges in ≤5 iterations
- No ILP infeasibility from router cuts
- 95%+ routing success after convergence

---

## Implementation Order

```
Phase 1 (Channel Tracking) ──┐
                              ├──► Phase 5 (Benders Integration)
Phase 2 (Precise Diagnostics)─┘
                              
Phase 3 (Steiner Trees) ──────► Independent improvement

Phase 4 (Global Routing) ─────► Future enhancement
```

**Recommended sequence:**
1. Phase 1 + 2 together (feedback quality)
2. Phase 5 (integrate with Benders)
3. Phase 3 (multi-pin nets)
4. Phase 4 (global routing - future)

---

## Estimated Effort

| Phase | Effort | Impact on Benders |
|-------|--------|-------------------|
| 1. Channel Tracking | 4-6h | High - enables precise cuts |
| 2. Precise Diagnostics | 4-6h | High - enables precise cuts |
| 3. Steiner Trees | 8-12h | Medium - fewer failures |
| 4. Global Routing | 12-20h | Medium - prevents congestion |
| 5. Benders Integration | 2-4h | High - uses improved data |

**Total for Benders convergence (Phases 1, 2, 5):** 10-16 hours
**Total including Steiner trees:** 18-28 hours
**Total including global routing:** 30-48 hours

---

## Success Metrics

### Before
- Router: 14/17 nets (82%)
- Benders: 10 cuts → ILP infeasible
- Convergence: ❌

### After Phase 1+2+5
- Router: 14/17 nets (82%) - same
- Benders: 2 cuts → ILP feasible → iterate
- Convergence: ✅ in 3-5 iterations

### After Phase 3
- Router: 16/17 nets (94%)
- Benders: 1 cut → converge in 2 iterations
- Convergence: ✅ faster

### After Phase 4
- Router: 17/17 nets (100%)
- Benders: 0 cuts needed
- Convergence: ✅ immediate
