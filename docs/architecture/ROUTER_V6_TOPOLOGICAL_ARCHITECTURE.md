# Router V6: Topological-First Architecture

**Status:** Planning
**Date:** January 10, 2026
**Problem:** 1+ month of A* optimization has not produced a working autorouter for complex boards

---

## Executive Summary

Router V5 achieved 100% completion on simple boards (Piantor) but only 21% on the target Temper board. Root cause analysis shows **78.9% of failures are placement-constrained**, not algorithm failures. The current approach—optimizing A* pathfinding—is solving the wrong problem.

This document proposes Router V6: a **topological-first architecture** that:
1. Solves routing topology (crossings, layer assignment, channel allocation) BEFORE geometry
2. Provides rich structured diagnostics for every failure
3. Validates against a multi-board test suite
4. Enables placement-routing co-optimization through measurable feedback

The goal: transform PCB routing from a visual/geometric black box into a **text-based, measurable, iteratively improvable** system.

---

## Part 0: Preconditions and Scope

**Critical clarification from step validation:** This pipeline is a **ROUTER**, not a placer+router.

### Preconditions (What Must Be True Before Pipeline Runs)

| Precondition | Source | Validated By |
|--------------|--------|--------------|
| All components are placed | User in KiCad or temper-placer | Stage 1 checks positions ≠ (0,0) |
| Netlist exists | Schematic → PCB sync | Stage 0 checks net count > 0 |
| Design rules defined | KiCad board setup | Stage 0 checks clearance > 0 |
| Stackup defined | KiCad board setup | Stage 0 checks layer count |
| Board outline exists | KiCad board | Stage 2 checks outline valid |

### Explicit Non-Goals

- **Initial placement:** Use KiCad or temper-placer first
- **Schematic capture:** Input is placed PCB, not schematic
- **100% automation:** Target is 80% auto + 20% flagged

### Data Flow: Accumulated BoardState

Each stage adds to a shared state object:

```python
@dataclass(frozen=True)
class BoardState:
    # Immutable from input
    pcb: ParsedPCB

    # Added by stages (each stage returns new BoardState with additions)
    design_intent: DesignIntent | None = None        # Stage 0
    escape_plan: EscapePlan | None = None            # Stage 1
    channel_analysis: ChannelAnalysis | None = None  # Stage 2
    occupancy_grid: OccupancyGrid | None = None      # Stage 2.5
    topology: TopologySolution | None = None         # Stage 3
    routes: frozenset[Route] = frozenset()           # Stage 4
    flagged_nets: frozenset[FlaggedNet] = frozenset() # Stage 4
    mfg_report: ManufacturingReport | None = None    # Stage 5
```

---

## Part 1: Problem Analysis

### 1.1 Why V5 Stalled

| Symptom | Root Cause | Evidence |
|---------|-----------|----------|
| 78.9% net failure on Temper | Placement creates unroutable topology | Root cause analysis in benchmark docs |
| Same patches tried repeatedly | No measurable progress signal | Git history shows iteration budget, via cost, net order cycling |
| Visual debugging required | No structured failure data | Must inspect PCB visually to understand failures |
| Binary success/failure | No gradient toward solution | "Almost routed" = failed |

### 1.2 The Fundamental Mismatch

**Current mental model:**
```
Placement (fixed) → A* Pathfinding → Success/Failure (binary)
```

**Reality:**
```
Placement determines topology → Topology determines routability → Geometry is just realization
```

A* is excellent at finding paths through a maze. But if the maze has no solution, no amount of A* optimization helps. We're optimizing the wrong stage.

### 1.3 What "Topological Routing" Means

**Geometric routing** (current): Find exact (x, y, layer) coordinates for every trace segment.

**Topological routing** (proposed): Answer these questions FIRST:
- Which nets must cross each other? (crossing graph)
- What layer should each net segment use? (layer assignment)
- Which routing channels does each net traverse? (channel allocation)
- Where do vias go, coarsely? (via topology)
- **Is this even satisfiable?** (feasibility check)

Only AFTER topology is solved do we do geometric realization—and that becomes much easier.

---

## Part 2: Architecture Overview

### 2.1 Pipeline Stages

**Revised based on PCB designer review:** Pin escape is elevated to Stage 1 (it's 50-70% of routing difficulty). Manufacturing DRC added as final stage.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ROUTER V6 PIPELINE (REVISED)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │   STAGE 0    │    │   STAGE 1    │    │   STAGE 2    │                  │
│  │   Design     │───▶│  Pin Escape  │───▶│   Channel    │                  │
│  │   Intent     │    │   Planning   │    │   Analysis   │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
│        │                    │                    │                          │
│        ▼                    ▼                    ▼                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │ Diff pairs,  │    │ Escape vias  │    │ Channel      │                  │
│  │ length grps, │    │ for QFN/BGA/ │    │ capacity     │                  │
│  │ net classes  │    │ fine-pitch   │    │ report       │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
│                                                 │                          │
│                                                 ▼                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │   STAGE 5    │    │   STAGE 4    │    │   STAGE 3    │                  │
│  │   Mfg DRC    │◀───│   Geometric  │◀───│  Topological │                  │
│  │   + Cleanup  │    │  Realization │    │   Routing    │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
│        │                    │                    │                          │
│        ▼                    ▼                    ▼                          │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │ Copper bal,  │    │ Routed PCB   │    │ Topology     │                  │
│  │ acid traps,  │    │ (maybe 80%   │    │ solution     │                  │
│  │ teardrops    │    │  + flagged)  │    │ + proof      │                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                  │
│        │                                        │                          │
│        └────────────────────┬───────────────────┘                          │
│                             ▼                                              │
│                    ┌──────────────┐                                        │
│                    │  Structured  │                                        │
│                    │  Diagnostics │                                        │
│                    └──────────────┘                                        │
│                             │                                              │
│                             ▼                                              │
│                    ┌──────────────┐                                        │
│                    │  Placement   │◀─── Feedback Loop (X, Y, Rotation,     │
│                    │  Adjustment  │                     Side)              │
│                    └──────────────┘                                        │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Stage Descriptions

#### Stage 0: Design Intent Extraction
**Input:** Schematic/netlist with attributes
**Output:** Annotated net list with constraints

- Extract differential pairs (USB_D+/D-, LVDS, etc.)
- Extract length matching groups (DDR data, clock)
- Extract net classes with width/clearance/current requirements
- Parse no-connect pins (don't flag as unrouted)
- Identify safety-critical net pairs (mains vs SELV → creepage rules)

**Key insight:** The schematic contains design intent that's lost in a flat netlist. Preserve it.

```python
@dataclass
class DesignIntent:
    diff_pairs: list[DiffPair]           # Coupled routing required
    length_groups: list[LengthGroup]     # Must match within tolerance
    net_classes: dict[str, NetClass]     # Width, clearance, current
    safety_pairs: list[SafetyPair]       # Creepage requirements
    no_connects: set[str]                # Don't flag as unrouted
```

#### Stage 1: Pin Escape Planning
**Input:** Placed board, design intent
**Output:** Escape via plan for dense packages

**This is 50-70% of routing difficulty.** Plan escape routes BEFORE channel routing.

- Identify dense packages: QFN, BGA, TSSOP, fine-pitch SOIC
- Compute dog-bone fanout positions for SMD pads
- Plan via-in-pad or adjacent vias for BGA inner balls
- Assign escape layers (inner balls → inner layers)
- Reserve via positions in occupancy grid

```python
@dataclass
class EscapeVia:
    source_pad: Pad
    via_position: tuple[float, float]
    target_layer: int
    pattern: Literal["dog_bone", "via_in_pad", "stub"]
```

**Key insight:** If a QFN pad can't escape, no amount of channel routing helps. Solve escape first.

#### Stage 2: Channel Analysis
**Input:** Placed board with escape plan, netlist
**Output:** Channel capacity report, bottleneck identification

- Decompose board into routing regions (component clusters, zones)
- Identify routing channels between regions
- Calculate channel capacity: `width / (trace_width + clearance)`
- **For diff pairs:** capacity = width / (2*trace + 3*spacing)
- **For high-current nets:** use current-based width, not default
- Calculate channel demand: sum of nets needing to cross
- Flag bottlenecks: `demand > capacity`

**Key insight:** This is purely analytical—no pathfinding yet. Produces text-based metrics.

#### Stage 3: Topological Routing
**Input:** Channel analysis, design intent, escape plan
**Output:** Topology solution OR unsatisfiability proof

- Model routing as a constraint satisfaction problem
- Variables: net-to-channel assignment, layer assignment, crossing order
- Constraints: channel capacity, layer availability, design rules
- **Diff pair constraint:** P and N must use same channel, adjacent slots
- **Length group constraint:** Group members must have similar topology (same via count)
- Solve with SAT/SMT or greedy heuristic with backtracking

**Key insight:** If unsatisfiable, we get a PROOF of which constraints conflict—actionable feedback for placement.

#### Stage 4: Geometric Realization
**Input:** Topology solution, escape plan, occupancy grid
**Output:** Routed PCB (target: 80% of nets, remainder flagged)

- Given topology, A* becomes much easier (most decisions already made)
- Layer assignment known → fewer dimensions to search
- Channel assignment known → bounded search region
- Via locations known (coarsely) → just snap to grid
- **Length matching:** Add serpentine/meander where needed
- **Flag hard nets:** If A* fails after topology says feasible, flag for human review

**Key insight:** This is V5's A*, but with a much simpler problem. Target 80% auto, not 100%.

#### Stage 5: Manufacturing DRC + Cleanup
**Input:** Routed PCB
**Output:** Manufacturing-ready PCB

Post-routing checks and fixes:
- **Copper balancing:** Add thieving copper to empty areas (target 40-60% per layer)
- **Acid trap detection:** Flag acute angles (<90°) that trap etchant
- **Annular ring check:** Via pad must extend beyond drill hole
- **Teardrop insertion:** Gradual transitions at pad-trace junctions
- **Thermal relief:** Spoke patterns for plane-connected pads
- **Creepage verification:** Check surface distance for safety-critical pairs (≠ clearance)

```python
@dataclass
class ManufacturingReport:
    copper_balance: dict[str, float]  # layer → percentage
    acid_traps: list[AcidTrap]
    annular_ring_violations: list[Via]
    creepage_violations: list[SafetyViolation]  # CRITICAL - mains safety
    teardrops_added: int
```

**Key insight:** A routable board isn't a manufacturable board. This stage catches issues fabs will reject.

---

## Part 3: Detailed Design

### 3.1 Channel Model

#### Definition
A **channel** is a rectangular routing region between two obstacles (components, board edges, zones).

```
        ┌─────────────┐
        │  Component  │
        │     A       │
        └─────────────┘
              │
    ══════════╪══════════  ← Channel (horizontal)
              │              Capacity = width / pitch
        ┌─────────────┐
        │  Component  │
        │     B       │
        └─────────────┘
```

#### Channel Properties
```python
@dataclass
class Channel:
    id: str
    region: Rectangle           # Bounding box
    orientation: Literal["H", "V"]  # Horizontal or Vertical
    layers: list[str]           # Available copper layers

    # Capacity
    width_mm: float             # Physical width
    capacity: int               # Number of traces that fit

    # Demand (computed)
    nets_assigned: list[str]    # Nets using this channel
    demand: int                 # len(nets_assigned)

    # Metrics
    utilization: float          # demand / capacity
    is_bottleneck: bool         # utilization > 0.8
```

#### Channel Extraction Algorithm

**Note:** This pseudocode addresses the critique that the algorithm was underspecified.

```python
def extract_channels(board, components, zones, design_rules):
    """
    Extract routing channels from board geometry.

    Returns ChannelGraph with capacity-annotated edges.
    """
    # Step 1: Create obstacle map (components + zones + keepouts)
    obstacles = []
    for comp in components:
        # Use bounding box, not centroid - components aren't points
        bbox = comp.bounding_box
        inflated = bbox.buffer(design_rules.default_clearance)
        obstacles.append(inflated)

    for zone in zones:
        if zone.is_keepout or zone.net in ["GND", "PGND"]:
            obstacles.append(zone.polygon)

    # Step 2: Compute routing space (board minus obstacles)
    routing_space = board.outline
    for obs in obstacles:
        routing_space = routing_space.difference(obs)

    # Handle edge case: routing_space may be MultiPolygon
    if routing_space.is_empty:
        raise UnroutableBoard("No routing space after obstacle subtraction")

    # Step 3: Skeletonize to get channel centerlines
    # Using medial axis transform (Voronoi of boundary)
    skeleton = medial_axis(routing_space)

    # Step 4: Convert skeleton to channel graph
    channels = []
    for edge in skeleton.edges:
        # Width = distance from centerline to nearest obstacle
        width = min_distance_to_boundary(edge.midpoint, routing_space)

        # Capacity = how many traces fit
        pitch = design_rules.default_trace_width + design_rules.default_clearance
        capacity = floor(2 * width / pitch)  # 2* because width is half-width from center

        if capacity >= 1:
            channels.append(Channel(
                id=generate_id(),
                geometry=edge,
                width=width,
                capacity=capacity,
                layers=board.routing_layers
            ))

    # Step 5: Build graph with junctions
    graph = ChannelGraph()
    for ch in channels:
        graph.add_edge(ch)

    # Connect channels that share endpoints (junction nodes)
    graph.merge_junctions(tolerance=0.1)  # 0.1mm snap

    return graph
```

**Edge cases handled:**
1. Large components (IGBT modules): Uses bounding box, not centroid
2. Overlapping obstacles: `difference()` handles union implicitly
3. Disconnected routing regions: Returns MultiPolygon, each is separate routing domain
4. Zero-capacity channels: Filtered out (capacity >= 1 check)
5. Board edges: Included in obstacle set implicitly via `board.outline`

### 3.1b Safety and Current-Based Design Rules (Power Electronics)

**Per PCB designer review:** These are critical for Temper (induction cooker with mains voltage).

#### Creepage vs Clearance (Different Things!)

```python
@dataclass
class SafetyRules:
    """IEC 62368-1 safety requirements for mains-connected equipment."""

    # Clearance: shortest distance through AIR
    # Creepage: shortest distance along PCB SURFACE

    clearance_mm: dict[tuple[str, str], float]  # net pair → air distance
    creepage_mm: dict[tuple[str, str], float]   # net pair → surface distance

    # Temper-specific (240VAC mains, pollution degree 2):
    # Mains (AC_L, AC_N) to SELV (3.3V logic): clearance=3mm, creepage=5mm
    # Mains to protective earth: clearance=2mm, creepage=3mm

    def check_creepage(self, net_a: str, net_b: str, board: Board) -> float:
        """Calculate actual creepage considering slots/cutouts."""
        # Slots INCREASE creepage by forcing current to go around
        direct_distance = board.surface_distance(net_a, net_b)
        required = self.creepage_mm.get((net_a, net_b), 0)
        return direct_distance - required  # Positive = OK, negative = violation
```

#### Current-Based Trace Width (IPC-2152)

```python
def required_trace_width_mm(
    current_amps: float,
    copper_oz: float = 1.0,
    temp_rise_c: float = 20.0,
    is_external: bool = True
) -> float:
    """
    Calculate minimum trace width for current capacity.

    For Temper 40A traces: ~12mm width on 2oz copper!
    This is why high-current paths often use copper pours, not traces.
    """
    k = 0.048 if is_external else 0.024
    thickness_mils = copper_oz * 1.37  # 1oz copper = 1.37 mils thick

    # IPC-2152: I = k * dT^0.44 * A^0.725
    # Solving for A: A = (I / (k * dT^0.44))^(1/0.725)
    area_mils2 = (current_amps / (k * (temp_rise_c ** 0.44))) ** (1 / 0.725)
    width_mils = area_mils2 / thickness_mils

    return width_mils * 0.0254  # mils to mm
```

**Impact on channel capacity:**
- Signal net (0.2mm): capacity = width / 0.4mm
- 5A power net (1.0mm): capacity = width / 1.2mm
- 40A power net (12mm): **doesn't fit in channels** → use copper pour

### 3.1c Multilayer Board Model (Critical for 4+ Layer Boards)

**Gap identified:** The original plan treated layers as simple integer indices. Real multilayer boards are complex physical structures with interdependencies.

#### Stackup Definition

```python
@dataclass
class LayerStackup:
    """Physical PCB stackup - determines impedance, via rules, everything."""

    layers: list[CopperLayer]
    dielectrics: list[DielectricLayer]
    total_thickness_mm: float

    # Example 4-layer stackup:
    # L1 (F.Cu)   - Signal    - 35µm (1oz)
    # Prepreg    - 0.2mm     - Er=4.3
    # L2 (In1.Cu) - GND Plane - 35µm
    # Core       - 1.0mm     - Er=4.5
    # L3 (In2.Cu) - PWR Plane - 35µm
    # Prepreg    - 0.2mm     - Er=4.3
    # L4 (B.Cu)   - Signal    - 35µm

    def get_reference_plane(self, signal_layer: int) -> int | None:
        """Return adjacent plane layer for return current."""
        ...

    def impedance_for_width(self, width_mm: float, layer: int) -> float:
        """Calculate trace impedance given width and stackup geometry."""
        ...

@dataclass
class CopperLayer:
    index: int
    name: Literal["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    layer_type: Literal["signal", "plane", "mixed"]
    thickness_oz: float  # 1oz = 35µm

    # For plane layers
    plane_net: str | None  # "GND", "+15V"
    plane_splits: list[Polygon] | None  # Regions of different nets
```

#### Via Types (Not All Vias Are Equal)

```python
@dataclass
class ViaType:
    """Different via types have different costs and constraints."""

    name: Literal["through", "blind", "buried", "microvia"]
    start_layer: int
    end_layer: int
    drill_mm: float
    pad_mm: float
    max_aspect_ratio: float  # depth/drill, typically 10:1 for through

    # Cost multipliers for fab
    fab_cost_multiplier: float  # 1.0=through, 2.0=blind, 4.0=buried

# Available via types depend on fab capability:
STANDARD_FAB_VIAS = [
    ViaType("through", 0, 3, drill=0.3, pad=0.6, aspect=10, cost=1.0),
]

HDI_FAB_VIAS = [
    ViaType("through", 0, 3, drill=0.2, pad=0.45, aspect=12, cost=1.0),
    ViaType("blind", 0, 1, drill=0.15, pad=0.35, aspect=1, cost=2.0),
    ViaType("blind", 2, 3, drill=0.15, pad=0.35, aspect=1, cost=2.0),
    ViaType("microvia", 0, 1, drill=0.1, pad=0.25, aspect=1, cost=1.5),
]
```

#### Layer Assignment Rules

```python
@dataclass
class LayerAssignmentRules:
    """Which nets can route on which layers."""

    signal_layers: list[int]  # [0, 3] for typical 4-layer
    plane_layers: dict[int, str]  # {1: "GND", 2: "+15V"}

    # Net class restrictions
    hv_outer_only: frozenset[str]  # Must be on L1/L4 for creepage
    high_current_outer: frozenset[str]  # Need wide traces

    # Impedance requirements
    impedance_targets: dict[str, float]  # net_class → Ohms
    # "USB": 90Ω differential, "Signal": 50Ω single-ended

    def allowed_layers(self, net: Net) -> list[int]:
        if net.name in self.hv_outer_only:
            return [0, 3]  # Creepage requires outer layers
        if net.current_rating and net.current_rating > 5:
            return [0, 3]  # High current needs thick outer traces
        return self.signal_layers
```

#### Reference Plane Continuity (Signal Integrity)

```
CRITICAL CONCEPT: Every high-speed trace needs a continuous return path.

GOOD: Trace over solid plane       BAD: Trace over plane split
      ════════════════════              ════════════════════
      ████████████████████              ████████╳╳╳█████████
      ↑ return current flows           ↑ return current blocked!
        smoothly under trace             EMI, crosstalk, ringing
```

```python
def check_reference_plane(trace: Trace, stackup: LayerStackup) -> list[Violation]:
    """Verify trace has continuous reference plane for return current."""
    violations = []

    ref_layer = stackup.get_reference_plane(trace.layer)
    if ref_layer is None:
        return [Violation("No reference plane for layer")]

    plane = stackup.layers[ref_layer]

    # Check plane splits
    for split in (plane.plane_splits or []):
        if trace.geometry.crosses(split.boundary):
            violations.append(Violation(
                f"Trace crosses plane split - add stitching via",
                severity="HIGH" if trace.is_high_speed else "MEDIUM"
            ))

    return violations
```

#### Channel Capacity is Per-Layer

```python
@dataclass
class Channel:
    id: str
    region: Rectangle
    orientation: Literal["H", "V"]

    # NOT a single capacity - capacity varies by layer!
    layer_capacities: dict[int, int]  # layer → trace count

    # Plane layers have zero capacity (no routing)
    # Inner signal layers may have reduced capacity (via blockage)

    def effective_capacity(self, net: Net, rules: LayerAssignmentRules) -> int:
        """Capacity available for this specific net."""
        allowed = rules.allowed_layers(net)
        return sum(
            self.layer_capacities.get(layer, 0)
            for layer in allowed
        )
```

### 3.2 Topological Routing Model

#### Variables
```python
# For each net n and channel c:
uses[n, c]: bool        # Does net n use channel c?

# For each net n and each SEGMENT (not just net):
layer[n, segment]: LayerIndex  # Which layer for this segment

# For each pair of nets (n1, n2) sharing a channel:
order[n1, n2]: int      # Relative ordering (n1 < n2 means n1 is "below")

# For each net n at each via point:
via_location[n, i]: GridCell  # Coarse via position
via_type[n, i]: ViaType       # through/blind/buried/microvia
```

#### Constraints
```python
# Capacity constraint: channel demand ≤ capacity
for c in channels:
    sum(uses[n, c] for n in nets) <= c.capacity

# Connectivity constraint: net must have path from source to sink
for n in nets:
    path_exists(n.source, n.sink, uses[n, :])  # Graph reachability

# Layer constraint: vias required for layer changes
for n in nets:
    if changes_layer(n):
        exists(via_location[n, i])

# Crossing constraint: same-layer crossings need resolution
for (n1, n2) in crossing_pairs:
    if layer[n1] == layer[n2]:
        different_layer_or_ordered(n1, n2)

# Design rule constraints
for n in nets:
    trace_width[n] <= channel_width(uses[n, :])
    clearance_satisfied(n, neighbors(n))
```

#### Solver Options

**Option A: SAT/SMT (z3, minisat)**
- Encode constraints as boolean/integer formulas
- Guaranteed complete: finds solution or proves unsatisfiable
- Provides unsat core (which constraints conflict)
- May be slow for large problems

**Option B: Greedy + Backtracking**
- Assign nets to channels in priority order
- Backtrack on capacity overflow
- Faster but incomplete (may miss solutions)
- Good for initial implementation

**Option C: ILP (Integer Linear Programming)**
- Model as optimization: minimize total wirelength, crossings, vias
- Solvers: Gurobi, CPLEX, or-tools
- Good balance of completeness and performance

**Recommendation:** Start with Option B (greedy), add Option A (SAT) for verification.

### 3.3 Structured Failure Diagnostics

Every routing attempt produces a `RoutingReport`:

```python
@dataclass
class NetRoutingReport:
    net_id: str
    status: Literal["ROUTED", "FAILED", "PARTIAL"]

    # Progress metrics
    score: float                    # 0.0 to 1.0
    source: PadLocation
    sink: PadLocation
    furthest_reached: GridCell
    distance_remaining: float       # mm to goal

    # Failure analysis (if failed)
    failure_point: GridCell | None
    blocking_nets: list[str]        # What's in the way
    blocking_obstacles: list[str]   # Components, zones, etc.

    # Search statistics
    iterations_used: int
    frontier_size_at_failure: int
    alternatives_explored: int

    # Suggestions
    suggestions: list[RoutingSuggestion]

@dataclass
class RoutingSuggestion:
    type: Literal["MOVE_COMPONENT", "ADD_VIA", "CHANGE_LAYER", "WIDEN_CHANNEL"]
    description: str
    target: str                     # Component or net affected
    estimated_impact: float         # How much this might help (0-1)
```

#### Example Failure Report
```json
{
  "net_id": "SPI_CLK",
  "status": "FAILED",
  "score": 0.34,
  "source": {"component": "U1", "pad": "15", "cell": [45, 62]},
  "sink": {"component": "U3", "pad": "8", "cell": [89, 71]},
  "furthest_reached": [52, 68],
  "distance_remaining": 37.2,
  "failure_point": [52, 68],
  "blocking_nets": ["GND", "SPI_MOSI", "VCC"],
  "blocking_obstacles": ["C12 keepout"],
  "iterations_used": 8743,
  "frontier_size_at_failure": 0,
  "alternatives_explored": 127,
  "suggestions": [
    {
      "type": "MOVE_COMPONENT",
      "description": "Move C12 south by 2mm to create routing channel",
      "target": "C12",
      "estimated_impact": 0.7
    },
    {
      "type": "ADD_VIA",
      "description": "Add escape via at (48, 65) to route on B.Cu",
      "target": "SPI_CLK",
      "estimated_impact": 0.5
    }
  ]
}
```

### 3.4 Multi-Board Test Suite

#### Board Selection Criteria
- Open source (KiCad format preferred)
- Variety of complexity levels
- Variety of domains (digital, power, RF, mixed)
- Known-good reference routing available

#### Proposed Test Suite

| Board | Source | Layers | Nets | Complexity | Purpose |
|-------|--------|--------|------|------------|---------|
| Piantor Right | splitkb | 2 | 32 | Simple | Baseline sanity check |
| Arduino Uno | Arduino | 2 | ~50 | Simple | Digital reference |
| Adafruit Feather | Adafruit | 2 | ~80 | Medium | Dense digital |
| LibreSolar MPPT | LibreSolar | 4 | ~60 | Medium | Power electronics |
| LibreSolar BMS | LibreSolar | 4 | ~100 | Hard | Complex power |
| Temper Induction | Internal | 4 | ~80 | Hard | Target board |

#### Scoring Metrics

```python
@dataclass
class BoardScore:
    board_id: str

    # Primary metrics
    completion_rate: float          # Nets routed / total nets

    # Efficiency metrics (vs ground truth if available)
    trace_length_ratio: float       # Our length / reference length
    via_count_ratio: float          # Our vias / reference vias

    # Quality metrics
    drc_violations: int
    unconnected_items: int

    # Composite score
    overall_score: float            # Weighted combination
```

#### Aggregate Scoring
```python
def suite_score(board_scores: list[BoardScore]) -> float:
    """Geometric mean of completion rates across all boards."""
    rates = [b.completion_rate for b in board_scores]
    return geometric_mean(rates)
```

**Why geometric mean:** Prevents gaming by perfecting easy boards while ignoring hard ones. A 0% on any board tanks the score.

### 3.5 Placement-Routing Co-Optimization

#### Feedback Interface

```python
@dataclass
class RoutingFeedback:
    """Feedback from router to placer."""

    # Overall routability
    estimated_routability: float    # 0.0 to 1.0

    # Regional congestion
    congestion_map: dict[str, float]  # region_id -> congestion (0-1)

    # Specific issues
    bottleneck_channels: list[ChannelBottleneck]
    blocked_nets: list[NetRoutingReport]

    # Actionable suggestions
    placement_suggestions: list[PlacementSuggestion]

@dataclass
class PlacementSuggestion:
    component: str
    # 4 degrees of freedom (per PCB designer review)
    current_position: tuple[float, float]
    suggested_position: tuple[float, float]
    current_rotation: Literal[0, 90, 180, 270]
    suggested_rotation: Literal[0, 90, 180, 270]  # Often critical for pin escape!
    current_side: Literal["top", "bottom"]
    suggested_side: Literal["top", "bottom"]
    reason: str
    expected_improvement: float
```

#### Co-Optimization Loop

```python
def cooptimize(board: Board, max_iterations: int = 10) -> Board:
    """Iterate placement and routing until convergent."""

    for i in range(max_iterations):
        # Route with current placement
        routing_result = topological_route(board)

        if routing_result.completion_rate == 1.0:
            return board  # Success!

        # Get feedback
        feedback = routing_result.generate_feedback()

        # Check for convergence (no improvement)
        if not feedback.has_actionable_suggestions():
            log.warning(f"Converged without solution at {routing_result.completion_rate:.1%}")
            break

        # Adjust placement based on feedback
        board = adjust_placement(board, feedback)

        log.info(f"Iteration {i}: {routing_result.completion_rate:.1%} routed")

    return board
```

### 3.6 Hierarchical Decomposition

Route in phases to isolate where failures occur:

```python
@dataclass
class RoutingPhase:
    name: str
    net_filter: Callable[[Net], bool]
    priority: int

ROUTING_PHASES = [
    # Phase 1: Short intra-cluster routes (highest success rate)
    RoutingPhase(
        name="intra_cluster",
        net_filter=lambda n: n.span_mm < 10 and n.crosses_zones == 0,
        priority=1
    ),

    # Phase 2: Medium routes within same zone
    RoutingPhase(
        name="intra_zone",
        net_filter=lambda n: n.crosses_zones == 0,
        priority=2
    ),

    # Phase 3: Cross-zone routes (hardest)
    RoutingPhase(
        name="cross_zone",
        net_filter=lambda n: n.crosses_zones > 0,
        priority=3
    ),

    # Phase 4: Power/ground (special handling)
    RoutingPhase(
        name="power_ground",
        net_filter=lambda n: n.net_class in ["Power", "Ground"],
        priority=4
    ),
]
```

**Benefit:** When phase 3 fails but phases 1-2 succeed, you know the problem is cross-zone routing specifically.

---

## Part 4: Implementation Roadmap

### Critical Addition: Prototype Gate (Week 0)

> **Before ANY infrastructure work, validate the core thesis.**

Build a **throwaway prototype** (max 3 days) that:
1. Takes ONE net from Temper board (e.g., SPI_CLK)
2. Manually defines 3-4 channels it could use
3. Encodes as SAT/constraint problem (can use z3 directly)
4. Solves and prints channel assignment
5. Attempts geometric realization with constrained A*
6. Verifies the path is DRC-clean

**GO/NO-GO GATE:**
- **GO:** Prototype works, topology→geometry separation is viable
- **NO-GO:** Prototype fails or takes >1 week → Implement Solution B (incremental V5 fixes) instead

This gate exists because the critique identified that **topology/geometry separation is a research hypothesis, not an engineering fact.**

---

### Phase 1: Foundation (Week 1-2)

#### 1.1 Multi-Board Test Suite
- [ ] Download and prepare 6+ test boards (MUST include 3+ power electronics)
- [ ] Create benchmark runner script
- [ ] Implement scoring metrics
- [ ] Establish V5 baseline scores

**Required boards:**
| Board | Domain | Layers | Source |
|-------|--------|--------|--------|
| Piantor | Digital | 2 | beekeeb/piantor |
| Arduino Uno | Digital | 2 | Arduino official |
| Adafruit Feather | Mixed | 2 | Adafruit |
| LibreSolar MPPT | Power | 4 | LibreSolar |
| VESC 6 | Power (motor) | 4 | Benjamin Vedder |
| LibreSolar BMS | Power (battery) | 4 | LibreSolar |

#### 1.2 Structured Diagnostics
- [ ] Define `NetRoutingReport` dataclass
- [ ] Modify V5 router to emit reports
- [ ] Implement routing score (0-1) per net
- [ ] Add failure point and blocking analysis

**Exit criteria:** Can run `pytest benchmarks/` and get a score for each board.

### Phase 2: Channel Analysis (Week 3-4)

#### 2.1 Channel Extraction
- [ ] Implement Voronoi-based channel detection
- [ ] Calculate channel capacity from design rules
- [ ] Identify bottleneck channels

#### 2.2 Channel Visualization
- [ ] ASCII grid representation of channels
- [ ] JSON export of channel graph
- [ ] Congestion heatmap generation

**Exit criteria:** Given a placed board, can report "Channel X is at 120% capacity (bottleneck)".

### Phase 3: Topological Router (Week 5-8)

#### 3.1 Constraint Model
- [ ] Define topological variables (uses, layer, order)
- [ ] Implement capacity constraints
- [ ] Implement connectivity constraints
- [ ] Implement crossing constraints

#### 3.2 Greedy Solver
- [ ] Net priority ordering
- [ ] Channel assignment with backtracking
- [ ] Layer assignment heuristics
- [ ] Via placement heuristics

#### 3.3 SAT Solver Integration (Optional)
- [ ] Encode constraints in z3
- [ ] Extract unsat core on failure
- [ ] Compare greedy vs SAT solutions

**Exit criteria:** Topological router produces valid topology OR explains why impossible.

### Phase 4: Geometric Realization (Week 9-10)

#### 4.1 Topology-Guided A*
- [ ] Constrain A* to assigned channels
- [ ] Constrain A* to assigned layers
- [ ] Use topology via locations as waypoints

#### 4.2 Integration
- [ ] Chain topological → geometric stages
- [ ] Verify DRC compliance
- [ ] Compare efficiency to V5

**Exit criteria:** End-to-end routing with topology-first approach, measured against test suite.

**GO/NO-GO GATE (Week 10):**
- **GO:** Test suite score > V5 baseline
- **NO-GO:** Score ≤ baseline → Stop V6, ship V5 with Phase 1-2 diagnostics as the product

### Phase 5: Co-Optimization (Week 11-12)

#### 5.1 Feedback Generation
- [ ] Generate congestion map from routing
- [ ] Generate placement suggestions from failures
- [ ] Implement `RoutingFeedback` interface

#### 5.2 Placement Adjustment
- [ ] Simple adjustment: move components away from bottlenecks
- [ ] Integration with existing placer
- [ ] Iteration loop with convergence detection

**Exit criteria:** Placement-routing loop improves completion rate on at least 2 boards.

---

### Decision Points Summary

| Week | Gate | Metric | Go | No-Go Action |
|------|------|--------|-----|--------------|
| 0 | Prototype | Single-net topology→geometry works | Continue to Phase 1 | **STOP.** Implement Solution B |
| 4 | Channel Quality | Temper channels look reasonable (manual) | Continue to Phase 3 | Revisit extraction algorithm |
| 6 | SAT Performance | Problem solves in <30 seconds | Continue | Switch to greedy-only |
| 10 | Suite Score | Score > V5 baseline | Continue to Phase 5 | **STOP.** Ship V5 + diagnostics |
| 12 | Co-opt Benefit | Feedback improves ≥2 boards | Complete | Ship without co-optimization |

---

### Fallback: Solution B (Incremental V5 Fixes)

If prototype gate fails or score doesn't improve, implement these targeted V5 fixes instead:

| Fix | Lines | Expected Impact | Time |
|-----|-------|-----------------|------|
| Same-layer crossing detection | ~50 | -33% violations | 3 days |
| Net-aware clearance inflation | ~200 | -19% violations | 1 week |
| Multi-layer retry logic | ~100 | +30% completion | 3 days |
| Escape routing for dense pins | ~300 | +25% completion | 1 week |
| **Total** | ~650 | 60-70% completion | 3-4 weeks |

**Solution B is lower risk, faster to ship, and still valuable.** V6 topology can be added later as an enhancement layer.

---

## Part 5: Success Metrics

### Revised Goal (Per PCB Designer Review)

**Old goal:** 100% automatic completion
**New goal:** 80% auto-routed + 100% of remaining nets flagged with actionable guidance

This matches industry practice. No production autorouter achieves 100%.

### Primary Metric: Test Suite Score
```
Target: 80% geometric mean AUTO-ROUTED across 6-board suite
         + 100% of flagged nets have actionable guidance
Current (V5): ~60% estimated (100% Piantor, 21% Temper, others unknown)
```

### Secondary Metrics

| Metric | Current (V5) | Target (V6) |
|--------|-------------|-------------|
| Piantor completion | 100% | 100% |
| Temper auto-routed | 21% | 70%+ |
| Temper flagged with guidance | 0% | 100% of remainder |
| DRC violations (Piantor) | 178 | <50 |
| **Manufacturing DRC** | Not checked | 0 violations |
| **Creepage violations** | Not checked | 0 (safety critical) |
| Diagnostic coverage | ~10% | 100% |
| Failure explanation rate | 0% | 90% |

### New Metrics (From PCB Designer Review)

| Metric | Target | Why It Matters |
|--------|--------|----------------|
| Pin escape success rate | >95% | Escape is 50-70% of difficulty |
| Diff pair coupling maintained | 100% | Signal integrity |
| Length matching within tolerance | 100% of groups | Timing |
| Copper balance per layer | 40-60% | Manufacturability |
| Creepage compliance | 100% | Safety certification |

### Process Metrics

| Metric | Description |
|--------|-------------|
| Build-measure-iterate cycle time | Time from code change to suite score |
| Diagnostic actionability | % of failures with actionable suggestions |
| Regression rate | % of changes that decrease suite score |

---

## Part 6: Risks and Mitigations

### Risk 1: Topological model too abstract
**Description:** Channel model may not capture all routing constraints.
**Mitigation:** Start with simple channel model, refine based on where geometric realization fails. The diagnostic system will reveal gaps.

### Risk 2: SAT solver performance
**Description:** Constraint solving may be too slow for large boards.
**Mitigation:** Use greedy solver as primary, SAT for verification/debugging only. Set solver timeout.

### Risk 3: Ground truth boards unavailable
**Description:** May not find enough open-source boards with reference routing.
**Mitigation:** Can still measure completion rate without ground truth. Trace length can be compared to Manhattan lower bound.

### Risk 4: Placement feedback loop diverges
**Description:** Co-optimization may oscillate instead of converging.
**Mitigation:** Implement damping (small moves only), convergence detection, iteration limit.

### Risk 5: Over-engineering (again)
**Description:** Building elaborate infrastructure that doesn't improve routing.
**Mitigation:** Measure suite score continuously. If score doesn't improve for 2 weeks, reassess approach.

---

## Part 7: Open Questions

1. **Channel granularity:** How fine should channels be? Per-component-pair or larger regions?

2. **SAT encoding efficiency:** What's the right encoding for routing constraints?

3. **Crossing resolution:** When two nets must cross on the same layer, what's the resolution strategy?

4. **Power net handling:** Should power/ground use the same topology model or special-case?

5. **Incremental routing:** Can we re-route only affected nets when placement changes?

---

## Appendix A: Prior Art

### Academic
- **Left-Edge Algorithm** (Hashimoto & Stevens, 1971): Channel routing foundation
- **Dogleg Channel Router** (Deutsch, 1976): Handling vertical constraints
- **Rubber-Band Routing** (Lauther, 1980): Topological sketch refinement
- **SILK Router** (Chan et al., 2000): Multilayer topology-first routing

### Industrial
- **Cadence Allegro PCB Router**: Fanout-first, then topology, then geometry
- **Altium ActiveRoute**: Interactive topological routing
- **PADS Router**: Sketch routing concept

### Open Source
- **FreeRouting**: Java-based autorouter, uses topological rip-up-and-reroute
- **KiCad Push-and-Shove**: Interactive, not auto, but topological concepts

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **Channel** | Rectangular routing region between obstacles |
| **Topology** | Abstract routing structure (crossings, layers) without exact coordinates |
| **Geometry** | Exact (x, y, layer) coordinates for trace segments |
| **Capacity** | Number of traces a channel can accommodate |
| **Demand** | Number of traces that need to use a channel |
| **Bottleneck** | Channel where demand exceeds capacity |
| **Crossing** | Two nets passing over/under each other |
| **Realization** | Converting topology to geometry |

---

---

## Part 8: V5 Learnings Integration

This section explicitly maps what was learned in V5 to design decisions in V6, ensuring we build on hard-won knowledge rather than repeating mistakes.

### 8.1 Learnings from Root Cause Analysis

| V5 Root Cause | What Was Learned | How V6 Addresses It |
|---------------|------------------|---------------------|
| **Same-layer trace crossing (33%)** | A* treats layers independently; no crossing detection in cost function | V6 topology layer resolves crossings BEFORE geometry. If two nets must cross, they're assigned different layers or via points at topology stage |
| **Clearance insufficient (19%)** | Blocking radius = trace_width/2 only; no net-to-net clearance inflation | Channel capacity calculation includes clearance: `capacity = width / (trace_width + clearance)`. Nets can't be assigned to same channel if clearance requirements overflow |
| **Zone congestion (472 violations)** | This is a PLACEMENT problem, not routing | V6 placement feedback loop: routing failures generate `RoutingFeedback` with congestion map, placement adjusts |

### 8.2 Learnings from Failed Net Analysis

| V5 Finding | Evidence | V6 Response |
|------------|----------|-------------|
| **78.9% of failures are placement-constrained** | Run #33: 15/19 nets failed due to no escape path | V6 checks routability at topology stage BEFORE spending A* iterations. `TopologicalRouter.is_satisfiable()` returns proof of which constraint fails |
| **"Stop tuning via_cost - issue is architectural"** | Run #34: Reducing via_cost from 50→25 gave 0% improvement, 0 vias placed | V6 doesn't tune parameters blindly. Channel analysis tells you WHERE the bottleneck is. Structured diagnostics tell you WHY |
| **Router never retried on alternative layers** | Run #34: "Router generated ZERO vias" despite lower via cost | V6 topology stage assigns layers explicitly. Geometric realization doesn't need to "discover" layer changes |
| **Dense pin fields create chokepoints** | SPI_CLK, SPI_MOSI, SPI_MISO all failed at MCU cluster | V6 channel analysis identifies chokepoints before routing. Phase decomposition routes intra-cluster nets first |
| **Multi-drop nets (3+ pins) especially hard** | SPI bus: "Clock signal must fan out to 3 devices. Central routing node blocked" | V6 topological routing solves multi-pin topology (star vs daisy-chain) before geometry |

### 8.3 Learnings from Piantor Benchmark

| V5 Achievement | What Worked | How V6 Preserves It |
|----------------|-------------|---------------------|
| **100% completion on simple board** | Sequential routing + bidirectional A* for long routes | V6 keeps bidirectional A* for geometric realization. Topology makes it easier by constraining search space |
| **Ghost pad bug fix** | ClearanceGridStage was blocking on nameless pads | V6 inherits fixed ClearanceGridStage code |
| **Iteration limit bug fix** | A* respects limit now (was hanging at 109k) | V6 keeps iteration budgeting; topology reduces iterations needed by 10-100x |
| **0.125mm coordinate offset fix** | DRCOracle and router now agree on coordinates | V6 inherits coordinate harmonization |
| **Zone filling integration** | `scripts/fill_zones.py` resolves dangling stubs | V6 keeps zone filling post-process |

### 8.4 Learnings from Experiment Progression

| Experiment | Hypothesis | Result | V6 Takeaway |
|------------|-----------|--------|-------------|
| **EXP-A: Reverse net order** | Routing /k00 first will help | FALSIFIED - no improvement | Net order tuning is not the solution. V6 uses topological ordering (dependencies, not heuristics) |
| **EXP-B: Increase A* budget** | More iterations = more routes | PARTIALLY CONFIRMED (10k→200k helped long routes) | V6 keeps high budget for geometric phase, but topology reduces search space so it's less needed |
| **EXP-5: Route locking** | Preserve successful routes across iterations | CONFIRMED - critical for stability | V6 keeps route locking in geometric phase |
| **EXP-6: CoupledDiffPairRouter** | Differential pairs need simultaneous routing | CONFIRMED - USB D+/D- work | V6 keeps differential pair support; topology assigns them to same channel with coupling constraint |

### 8.5 Architectural Insights from V5 Documentation

| Document | Key Insight | V6 Design Decision |
|----------|-------------|-------------------|
| `deterministic_placement_routing_architecture.md` | "Routing failures are assumed to be placement failures unless proven otherwise" | V6 implements this literally: topology stage returns `UnroutabilityProof` when failing, which feeds placement adjustment |
| `deterministic_placement_routing_architecture.md` | "Routing is the proof, not the source of correctness" | V6 separates concerns: topology proves routability, geometry realizes it |
| `hypergraph_experiments.md` | Sparse hypergraph is 16x faster than naive loop for wirelength | V6 can use hypergraph for channel demand calculation if needed |
| `hypergraph_experiments.md` | "Five Whys: Do we actually need HGNN? No - analytical physics weighting is enough for Phase 1" | V6 uses analytical channel capacity, not ML |

### 8.6 Code That V6 Reuses

**Directly reused:**
- `bidirectional_astar.py` - proven 10-100x speedup for long routes
- `clearance_grid.py` - fixed ghost pad bug, coordinate alignment
- `drc_oracle.py` - validated DRC checking
- `kicad_exporter.py` - coordinate snapping, zone integration
- `design_rules.py` - ClearanceMatrix, net class rules

**Modified/Extended:**
- `sequential_routing.py` - becomes "geometric realization" stage, receives topology solution instead of raw netlist
- `net_ordering.py` - replaced by topological ordering from SAT/constraint solver
- `layer_assignment.py` - replaced by topology-stage layer assignment with proof

**New in V6:**
- `channel_analysis.py` - Voronoi-based channel extraction
- `topological_router.py` - SAT/constraint-based topology solver
- `routing_diagnostics.py` - structured failure reports
- `placement_feedback.py` - routing→placement feedback interface

### 8.7 Anti-Patterns to Avoid (Learned from V5)

| Anti-Pattern | V5 Evidence | V6 Guardrail |
|--------------|-------------|--------------|
| **Tuning parameters without understanding** | "Stop tuning via_cost" - 5 experiments with no improvement | V6 requires structured diagnostics before any parameter change. "Why is this parameter the bottleneck?" |
| **Binary success/failure measurement** | Run #33: "4/19 routed" gives no actionable info | V6 requires 0-100% score per net, blocking analysis, suggestions |
| **Single test board** | Piantor 100% success masked that Temper was 21% | V6 requires 6-board test suite, geometric mean scoring |
| **Visual debugging** | "Exporting Clearance Grid Visualization..." - helpful but not scalable | V6 exports machine-readable JSON diagnostics alongside images |
| **Optimizing wrong abstraction level** | Month of A* improvements for placement problem | V6 topology stage fails fast with proof, redirects to placement |

### 8.8 What V6 Does NOT Change

These V5 decisions were correct and are preserved:

1. **Deterministic pipeline architecture** - stages with immutable BoardState
2. **DRC Oracle integration** - validate during pathfinding, not after
3. **Grid-based routing** - 0.1-0.25mm cells for discretization
4. **Net class design rules** - HV/Power/Signal clearance differentiation
5. **Zone filling as post-process** - let KiCad handle copper pours
6. **Differential pair coupling** - CoupledDiffPairRouter pattern
7. **Bidirectional A* for long routes** - proven performance benefit

---

## Part 9: Critical Success Factors

Based on V5 experience, these are the make-or-break factors for V6:

### 9.1 Measure Continuously
V5 problem: Ran experiments without aggregate scoring. Didn't know if changes helped overall.

V6 requirement: **Every commit runs the 6-board benchmark.** Score is tracked in CI. Regressions are caught immediately.

### 9.2 Fail Fast with Explanation
V5 problem: A* ran 200k iterations then returned "failed". No information about why.

V6 requirement: **Topology stage returns in <1 second** with either solution or `UnroutabilityProof`. Never spend compute on impossible problems.

### 9.3 Feedback to Placement
V5 problem: Router said "failed" but placement optimizer had no idea what to fix.

V6 requirement: **Every failure generates actionable feedback.** "Move C12 south 2mm" not "routing failed".

### 9.4 Hierarchical Debugging
V5 problem: When 78% of nets failed, where do you start?

V6 requirement: **Phase decomposition isolates failures.** "Phase 1 (intra-cluster): 95%. Phase 3 (cross-zone): 17%." Now you know where to look.

### 9.5 Ground Truth Comparison
V5 achievement: Piantor comparison showed router is 1% longer traces, 127% more vias - but vias are necessary for different ground plane strategy.

V6 requirement: **Every test board has ground truth metrics.** Know whether differences are regressions or valid design choices.

---

## Part 10: Type Safety, Testing, and Validity Guarantees

The router deals with complex geometric and constraint data. Type systems and tests can catch entire categories of bugs before they manifest as routing failures.

### 10.1 Type-Driven Development Strategy

#### Newtypes for Units (Prevent mm/mil Confusion)

The biggest class of bugs in PCB tools is unit confusion. Use newtypes:

```python
from typing import NewType

# Physical units - can't accidentally mix them
Millimeters = NewType('Millimeters', float)
Mils = NewType('Mils', float)  # 1 mil = 0.0254mm
Microns = NewType('Microns', float)

# Grid units - distinct from physical
GridCells = NewType('GridCells', int)

# Layer indices - prevent layer/coordinate confusion
LayerIndex = NewType('LayerIndex', int)

# Net IDs - prevent string/net confusion
NetId = NewType('NetId', str)

# Example function signatures that can't be called wrong:
def route_segment(
    start: tuple[Millimeters, Millimeters],
    end: tuple[Millimeters, Millimeters],
    width: Millimeters,
    layer: LayerIndex
) -> TraceSegment: ...

# This FAILS type checking - can't pass Mils where Millimeters expected:
# route_segment((100, 200), (300, 400), 8, 0)  # Are these mm or mils? Type error!
```

#### Literal Types for Constrained Values

```python
from typing import Literal

Rotation = Literal[0, 90, 180, 270]
Side = Literal["top", "bottom"]
LayerName = Literal["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
NetClass = Literal["Signal", "Power", "HighVoltage", "Ground", "Differential"]

# Can't pass invalid rotation:
def rotate_component(comp: Component, angle: Rotation) -> Component: ...
# rotate_component(c, 45)  # Type error! 45 is not in Literal[0, 90, 180, 270]
```

#### Phantom Types for State Machines

Track pipeline stages at the type level:

```python
from typing import Generic, TypeVar

# Phantom type parameters
class Unplaced: pass
class Placed: pass
class EscapePlanned: pass
class TopologyResolved: pass
class Routed: pass

T = TypeVar('T', Unplaced, Placed, EscapePlanned, TopologyResolved, Routed)

@dataclass
class BoardState(Generic[T]):
    board: Board
    netlist: Netlist
    # ... other fields

# Functions that transform state:
def place_components(state: BoardState[Unplaced]) -> BoardState[Placed]: ...
def plan_escapes(state: BoardState[Placed]) -> BoardState[EscapePlanned]: ...
def solve_topology(state: BoardState[EscapePlanned]) -> BoardState[TopologyResolved]: ...
def realize_geometry(state: BoardState[TopologyResolved]) -> BoardState[Routed]: ...

# Can't skip stages - type error if you try:
# realize_geometry(place_components(initial))  # Error: Expected EscapePlanned, got Placed
```

### 10.2 Property-Based Testing

Instead of individual test cases, define **properties that must always hold**.

#### Geometric Invariants

```python
from hypothesis import given, strategies as st

@given(st.lists(st.tuples(st.floats(-100, 100), st.floats(-100, 100)), min_size=2))
def test_channel_extraction_covers_routing_space(points):
    """Every point in routing space must be reachable via some channel."""
    board = create_test_board(points)
    channels = extract_channels(board)

    for point in sample_routing_space(board, n=100):
        assert any(channel.contains(point) for channel in channels), \
            f"Point {point} not covered by any channel"


@given(net=st.sampled_from(test_netlist.nets))
def test_routed_net_is_connected(net):
    """After routing, all pins of a net must be electrically connected."""
    routed = route_net(net, board)

    if routed.status == "ROUTED":
        graph = build_connectivity_graph(routed.traces, routed.vias)
        pin_nodes = [graph.find_node(pin.position) for pin in net.pins]
        assert all_connected(pin_nodes), \
            f"Net {net.name} claims routed but pins not connected"


@given(trace=st.from_type(TraceSegment))
def test_trace_width_satisfies_current(trace):
    """Trace width must be sufficient for net's current rating."""
    net = get_net(trace.net_id)
    if net.current_rating:
        required = required_trace_width_mm(net.current_rating)
        assert trace.width >= required, \
            f"Trace width {trace.width}mm < required {required}mm for {net.current_rating}A"
```

#### Topological Invariants

```python
@given(topology=st.from_type(TopologySolution))
def test_channel_capacity_not_exceeded(topology):
    """No channel should have more nets assigned than its capacity."""
    for channel in topology.channels:
        assigned = [n for n in topology.nets if topology.uses(n, channel)]
        total_demand = sum(net_width(n) for n in assigned)
        assert total_demand <= channel.capacity, \
            f"Channel {channel.id} oversubscribed: {total_demand} > {channel.capacity}"


@given(topology=st.from_type(TopologySolution))
def test_crossing_nets_on_different_layers(topology):
    """If two nets cross in a channel, they must be on different layers."""
    for (n1, n2) in topology.crossing_pairs:
        if topology.same_channel(n1, n2):
            assert topology.layer(n1) != topology.layer(n2), \
                f"Crossing nets {n1}, {n2} on same layer {topology.layer(n1)}"
```

#### Safety Invariants (Critical)

```python
@given(board=st.from_type(RoutedBoard))
def test_creepage_compliance(board):
    """All safety-critical net pairs must meet creepage requirements."""
    safety_rules = get_safety_rules(board)

    for (net_a, net_b), required_creepage in safety_rules.creepage_mm.items():
        actual_creepage = board.surface_distance(net_a, net_b)
        assert actual_creepage >= required_creepage, \
            f"SAFETY VIOLATION: {net_a}-{net_b} creepage {actual_creepage}mm < {required_creepage}mm"


@given(board=st.from_type(RoutedBoard))
def test_clearance_compliance(board):
    """All net pairs must meet clearance requirements."""
    for trace_a in board.traces:
        for trace_b in board.traces:
            if trace_a.net != trace_b.net and trace_a.layer == trace_b.layer:
                distance = min_distance(trace_a, trace_b)
                required = get_clearance(trace_a.net, trace_b.net)
                assert distance >= required, \
                    f"Clearance violation: {trace_a.net}-{trace_b.net} = {distance}mm < {required}mm"
```

### 10.3 Test Hierarchy

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           TEST PYRAMID                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│                        ┌─────────────┐                                  │
│                        │   E2E       │  ← Full board routing (slow)     │
│                        │   Tests     │    6 boards × 3 configs = 18     │
│                        └─────────────┘                                  │
│                    ┌─────────────────────┐                              │
│                    │   Integration       │  ← Stage combinations        │
│                    │   Tests             │    escape→channel, etc.      │
│                    └─────────────────────┘                              │
│              ┌─────────────────────────────────┐                        │
│              │   Property-Based Tests          │  ← Invariants hold     │
│              │   (Hypothesis)                  │    for all inputs      │
│              └─────────────────────────────────┘                        │
│        ┌─────────────────────────────────────────────┐                  │
│        │   Unit Tests                                │  ← Individual    │
│        │   (per function/class)                      │    components    │
│        └─────────────────────────────────────────────┘                  │
│  ┌─────────────────────────────────────────────────────────┐            │
│  │   Static Analysis (mypy, pyright)                       │  ← Types   │
│  │   + Linting (ruff)                                      │            │
│  └─────────────────────────────────────────────────────────┘            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 10.4 Specific Test Suites

#### Pin Escape Tests
```python
class TestPinEscape:
    def test_qfn_all_pads_escape(self):
        """All QFN pads must have escape via assigned."""

    def test_bga_inner_balls_to_inner_layers(self):
        """BGA inner balls must escape to inner layers."""

    def test_dog_bone_clearance(self):
        """Dog-bone vias must not violate pad clearance."""

    def test_escape_via_drill_rules(self):
        """Escape vias must meet drill size and aspect ratio rules."""
```

#### Channel Analysis Tests
```python
class TestChannelAnalysis:
    def test_channels_cover_routing_space(self):
        """Union of channels covers entire routing space."""

    def test_channel_capacity_formula(self):
        """Capacity = floor(width / pitch) is correct."""

    def test_diff_pair_capacity_doubled(self):
        """Diff pairs consume 2x capacity + spacing."""

    def test_bottleneck_detection(self):
        """Channels with demand > 80% capacity flagged as bottleneck."""
```

#### Topology Tests
```python
class TestTopology:
    def test_sat_unsat_proof(self):
        """Unsatisfiable topology returns conflict clause."""

    def test_diff_pair_same_channel(self):
        """Diff pair P/N always assigned to same channel."""

    def test_length_group_similar_topology(self):
        """Length group members have same via count ±1."""

    def test_crossing_resolution(self):
        """All crossings resolved via layer or ordering."""
```

#### Safety Tests (Must Pass for Certification)
```python
class TestSafety:
    """These tests are BLOCKING for production release."""

    def test_mains_selv_creepage(self):
        """AC_L/AC_N to 3.3V logic: ≥5mm creepage."""

    def test_mains_selv_clearance(self):
        """AC_L/AC_N to 3.3V logic: ≥3mm clearance."""

    def test_earth_mains_creepage(self):
        """Protective earth to mains: ≥3mm creepage."""

    def test_no_trace_under_slot(self):
        """No traces routed under isolation slots."""
```

### 10.5 Continuous Integration Pipeline

```yaml
# .github/workflows/router-ci.yml
name: Router V6 CI

on: [push, pull_request]

jobs:
  type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install mypy pyright
      - run: mypy packages/temper-placer/src --strict
      - run: pyright packages/temper-placer/src

  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/unit -v --cov=temper_placer

  property-tests:
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/property -v --hypothesis-seed=42

  safety-tests:
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/safety -v
      # FAIL THE BUILD if any safety test fails
      - run: |
          if [ $? -ne 0 ]; then
            echo "SAFETY TESTS FAILED - BLOCKING MERGE"
            exit 1
          fi

  benchmark:
    runs-on: ubuntu-latest
    steps:
      - run: python benchmarks/run_suite.py --output results.json
      - run: python benchmarks/check_regression.py results.json
      # Fail if score dropped >5% from baseline

  integration:
    needs: [type-check, unit-tests, property-tests, safety-tests]
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/integration -v --timeout=300
```

### 10.6 Invariant Documentation

Every module should document its invariants:

```python
"""
Channel Analysis Module

INVARIANTS (enforced by tests):
1. channels.union().contains(routing_space) - full coverage
2. ∀ channel: capacity >= 1 - no zero-capacity channels
3. ∀ channel: width > 0 - no degenerate channels
4. channel_graph.is_connected() - all regions reachable

PRECONDITIONS:
- board.components all have bounding_box defined
- board.zones all have polygon defined
- design_rules.default_clearance > 0

POSTCONDITIONS:
- len(channels) >= 1 (at least one channel exists)
- all channel.id are unique
"""
```

### 10.7 Golden File Testing

For regression testing, compare against known-good outputs:

```python
def test_piantor_golden():
    """Piantor routing must match golden file."""
    result = route_board("fixtures/piantor_right.kicad_pcb")

    golden = load_golden("fixtures/piantor_right.golden.json")

    # Structural comparison (not exact bytes)
    assert result.nets_routed == golden.nets_routed
    assert result.total_wirelength == pytest.approx(golden.total_wirelength, rel=0.05)
    assert result.via_count == pytest.approx(golden.via_count, rel=0.10)
    assert result.drc_violations <= golden.drc_violations  # Must not regress
```

---

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-10 | 0.1 | Initial planning document |
| 2026-01-10 | 0.2 | Added Part 8 (V5 Learnings Integration) and Part 9 (Critical Success Factors) |
| 2026-01-10 | 0.3 | Post-critique revision: Added prototype gate, decision points, Solution B fallback, algorithm pseudocode, expanded test suite requirements. See `ROUTER_V6_CRITIQUE.md` for full analysis. |
| 2026-01-10 | 0.4 | PCB designer review: Added pin escape as Stage 1, 4-DOF placement model (rotation/side), creepage vs clearance, current-based width, manufacturing DRC stage, revised success metric to 80% auto + flagging. See `ROUTER_V6_PCB_DESIGNER_REVIEW.md`. |
| 2026-01-10 | 0.5 | Added Part 10: Type Safety, Testing, and Validity Guarantees - newtypes for units, phantom types for pipeline stages, property-based testing, CI pipeline, safety tests. |
| 2026-01-10 | 0.6 | Multilayer board support: Added stackup model, via types (through/blind/buried/microvia), layer assignment rules, reference plane continuity checking, per-layer channel capacity. See `ROUTER_V6_MULTILAYER_ANALYSIS.md`. |
| 2026-01-10 | 0.7 | Step-by-step validation: Added Part 0 (Preconditions/Scope), explicit BoardState data flow, identified 8 critical gaps, formalized 50+ substeps with test cases. See `ROUTER_V6_STEP_VALIDATION.md`. |
