# Router V6: Step-by-Step Validation and Formalization

This document walks through each step of the V6 plan, validating logic flow, identifying assumptions, and breaking into testable/automatable substeps.

---

## Overview: The Claimed Pipeline

```
Input: KiCad PCB file (placed)
  ↓
Stage 0: Design Intent Extraction
  ↓
Stage 1: Pin Escape Planning
  ↓
Stage 2: Channel Analysis
  ↓
Stage 3: Topological Routing
  ↓
Stage 4: Geometric Realization
  ↓
Stage 5: Manufacturing DRC
  ↓
Output: Routed PCB + Diagnostics
  ↓
[Feedback Loop] → Placement Adjustment → Back to Stage 1
```

---

## Critical Gap #1: Where Does Placement Come From?

### The Problem

Stage 1 (Pin Escape) requires a **placed board** as input. But the pipeline starts with "Design Intent Extraction" which doesn't produce placement.

### Possible Interpretations

| Interpretation | Implication |
|----------------|-------------|
| **A) User places in KiCad first** | Router is routing-only, placement is external |
| **B) Separate placer runs before this pipeline** | Need to define placer → router interface |
| **C) Placement is implicit in input PCB** | Same as A |
| **D) Initial placement + iterative refinement** | Feedback loop handles placement |

### What the Plan Actually Says

- Input is "KiCad PCB file" (implies components already placed)
- Feedback loop shows "Placement Adjustment"
- No explicit placement stage in the pipeline

### Resolution Required

**DECISION NEEDED:** Is this a router-only pipeline (placement is input) or a placer+router pipeline?

**Recommendation:** Make explicit:
```
ACTUAL INPUT: KiCad PCB with components PLACED but NOT routed
             (user or temper-placer handles initial placement)

FEEDBACK LOOP: Can ADJUST placement (move, rotate) but not do initial placement
```

### Testable Validation
```python
def test_input_has_placement():
    """Verify input PCB has all components placed."""
    pcb = load_kicad_pcb(input_path)
    for component in pcb.components:
        assert component.position is not None, f"{component.ref} not placed"
        assert component.position != (0, 0), f"{component.ref} at origin (unplaced?)"
```

---

## Stage 0: Design Intent Extraction

### Claimed Flow
```
Input: Schematic/netlist with attributes
Output: DesignIntent (diff_pairs, length_groups, net_classes, safety_pairs)
```

### Assumption Analysis

| Assumption | Valid? | Risk if Wrong |
|------------|--------|---------------|
| Schematic has diff pair info | MAYBE | Miss USB/LVDS coupling |
| Schematic has length groups | UNLIKELY | Miss DDR timing |
| Net classes defined in schematic | YES (KiCad) | OK |
| Safety pairs inferable | NO | Miss mains isolation |

### Gap: Where Is the Schematic?

**Problem:** KiCad PCB files (`.kicad_pcb`) do NOT contain:
- Differential pair definitions
- Length matching groups
- Schematic hierarchy

This info is in `.kicad_sch` (schematic) or `.kicad_pro` (project).

**Options:**
1. Require both PCB and schematic files as input
2. Infer from naming conventions (USB_D+/USB_D- → diff pair)
3. Require user to provide config file with design intent
4. Parse KiCad project file which links schematic

### Formalized Substeps

```
Stage 0.1: Load KiCad PCB
  Input: path to .kicad_pcb
  Output: ParsedPCB (components, nets, zones, stackup, design_rules)
  Testable: pcb.nets count > 0, pcb.components count > 0

Stage 0.2: Infer Diff Pairs from Naming
  Input: list of net names
  Output: list of DiffPair
  Rule: nets ending in +/- or P/N with same prefix → diff pair
  Testable: "USB_D+" and "USB_D-" → DiffPair("USB_D")

Stage 0.3: Load Net Classes from Design Rules
  Input: KiCad design rules section
  Output: dict[net_name, NetClass]
  Testable: net_classes["GND"].clearance == expected

Stage 0.4: Infer Safety Pairs from Net Names
  Input: net names, known HV patterns
  Output: list of SafetyPair
  Rule: nets matching AC_*, MAINS_*, LINE_* are HV
  Rule: HV paired with all LV nets for creepage
  Testable: SafetyPair("AC_L", "3V3").creepage_mm == 5.0

Stage 0.5: Load/Infer Length Groups (OPTIONAL)
  Input: schematic file OR config file
  Output: list of LengthGroup
  Note: May require user input if not in schematic
  Testable: LengthGroup("DDR_DQ").tolerance_mm == 2.5

Stage 0.6: Parse Stackup
  Input: KiCad board setup section
  Output: LayerStackup
  Testable: stackup.total_thickness_mm ≈ 1.6
```

### Validation Tests

```python
class TestStage0:
    def test_0_1_pcb_loads(self):
        pcb = load_kicad_pcb("fixtures/temper.kicad_pcb")
        assert len(pcb.nets) > 0
        assert len(pcb.components) > 0

    def test_0_2_diff_pair_inference(self):
        nets = ["USB_D+", "USB_D-", "GND", "VCC"]
        pairs = infer_diff_pairs(nets)
        assert DiffPair("USB_D", "USB_D+", "USB_D-") in pairs

    def test_0_3_net_classes_loaded(self):
        rules = load_design_rules("fixtures/temper.kicad_pcb")
        assert "Signal" in rules.net_classes
        assert rules.net_classes["Signal"].clearance_mm > 0

    def test_0_4_safety_pairs_inferred(self):
        nets = ["AC_L", "AC_N", "GND", "3V3", "MCU_TX"]
        pairs = infer_safety_pairs(nets)
        # AC_L should be paired with all low-voltage nets
        assert any(p.net_a == "AC_L" and p.net_b == "3V3" for p in pairs)

    def test_0_6_stackup_parsed(self):
        stackup = parse_stackup("fixtures/temper.kicad_pcb")
        assert len(stackup.layers) == 4
        assert stackup.layers[1].plane_net == "GND"
```

---

## Stage 1: Pin Escape Planning

### Claimed Flow
```
Input: Placed board, design intent
Output: Escape via plan for dense packages
```

### Assumption Analysis

| Assumption | Valid? | Risk if Wrong |
|------------|--------|---------------|
| Can identify dense packages | YES | Need footprint library |
| Escape positions computable | MOSTLY | Complex for BGA |
| Escape doesn't violate DRC | MUST CHECK | Invalid escape plan |
| All pads need escape | NO | Some route on same layer |

### Gap: Which Pads Need Escape?

Not all pads need escape vias:
- Pads on board edge → route directly outward
- Pads with clear path to destination → no via needed
- Only INNER pads of dense packages need escape

**Logic needed:**
```python
def needs_escape_via(pad, component, board):
    # Outer edge pads often don't need escape
    if is_edge_pad(pad, component):
        return False

    # Check if direct routing path exists
    if has_clear_routing_path(pad, board):
        return False

    # Inner pads of dense packages need escape
    if component.package_type in ["QFN", "BGA"] and is_inner_pad(pad, component):
        return True

    return False
```

### Gap: Escape Via Placement is Geometric

Escape via position must:
1. Be within reach of the pad (trace from pad to via)
2. Not overlap other pads
3. Not violate DRC
4. Be on correct layer for routing

This is already a mini-routing problem!

### Formalized Substeps

```
Stage 1.1: Identify Dense Packages
  Input: list of components
  Output: list of components needing escape planning
  Rule: QFN, BGA, TSSOP, fine-pitch (< 0.65mm) SOIC
  Testable: QFN-48 flagged, 0805 resistor not flagged

Stage 1.2: Classify Pads by Escape Need
  Input: component, its pads, board context
  Output: dict[pad, EscapeNeed] where EscapeNeed ∈ {NONE, SAME_LAYER, VIA_ESCAPE}
  Rule: Edge pads → often SAME_LAYER
  Rule: Inner pads → often VIA_ESCAPE
  Rule: Thermal pad → special handling (via array)
  Testable: QFN center pad → VIA_ESCAPE with via array

Stage 1.3: Compute Escape Via Positions
  Input: pad, escape_need, neighboring pads, DRC rules
  Output: EscapeVia(position, layer, pattern)
  Constraint: via_position not overlapping any pad
  Constraint: trace pad→via fits between neighboring pads
  Testable: via position DRC-clean

Stage 1.4: Select Via Type
  Input: escape_via, stackup, fab_capabilities
  Output: via_type ∈ {through, blind, microvia}
  Rule: If target_layer == adjacent → microvia OK
  Rule: If target_layer == opposite → through via
  Rule: Check aspect ratio against fab limits
  Testable: L1→L2 escape → blind via if HDI, through via if standard

Stage 1.5: Validate Escape Plan
  Input: all escape vias, DRC oracle
  Output: validated plan OR list of violations
  Check: via-to-via spacing
  Check: via-to-pad spacing
  Check: trace from pad to via fits
  Testable: no DRC violations in escape plan

Stage 1.6: Reserve Escape Via Positions
  Input: validated escape plan, occupancy grid
  Output: updated occupancy grid with vias blocked
  Effect: Subsequent stages see vias as obstacles
  Testable: grid cells at via positions marked blocked
```

### Does Stage 0 → Stage 1 Flow Correctly?

**Check:** Does Stage 0 output everything Stage 1 needs?

| Stage 1 Needs | Stage 0 Provides? |
|---------------|-------------------|
| Placed board | NO - comes from input PCB |
| Component positions | NO - comes from input PCB |
| Net assignments | YES (netlist) |
| DRC rules | YES (design_rules) |
| Diff pair info | YES (design_intent.diff_pairs) |

**Gap:** Stage 0 doesn't explicitly output "placed board" - it's passed through from input.

**Fix:** Make data flow explicit:
```
Input PCB → ParsedPCB
Stage 0: ParsedPCB → DesignIntent
Stage 1: (ParsedPCB, DesignIntent) → EscapePlan
```

### Validation Tests

```python
class TestStage1:
    def test_1_1_qfn_identified(self):
        components = [QFN48(), R0805(), BGA256()]
        dense = identify_dense_packages(components)
        assert QFN48() in dense
        assert R0805() not in dense

    def test_1_2_inner_pad_needs_escape(self):
        qfn = create_qfn48()
        pad = qfn.pads[24]  # Inner pad
        need = classify_escape_need(pad, qfn, board)
        assert need == EscapeNeed.VIA_ESCAPE

    def test_1_3_escape_via_drc_clean(self):
        via = compute_escape_via(pad, board, drc_rules)
        violations = drc_oracle.check_via(via)
        assert len(violations) == 0

    def test_1_5_escape_plan_valid(self):
        plan = plan_all_escapes(board, design_intent)
        for via in plan.vias:
            assert drc_oracle.check_via(via) == []
```

---

## Stage 2: Channel Analysis

### Claimed Flow
```
Input: Placed board with escape plan, netlist
Output: Channel capacity report, bottleneck identification
```

### Assumption Analysis

| Assumption | Valid? | Risk if Wrong |
|------------|--------|---------------|
| Board decomposes into channels | PARTIALLY | Complex boards have non-channel areas |
| Voronoi/medial axis works | MOSTLY | Edge cases with concave obstacles |
| Capacity formula is accurate | APPROXIMATELY | Ignores local congestion |
| Escape vias don't affect channels | NO! | Vias consume channel capacity |

### Gap: Escape Vias Affect Channel Capacity

Stage 1 places escape vias. These vias:
1. Block cells in the occupancy grid
2. Reduce available routing space in channels
3. May create new narrow passages

**The channel analysis must account for escape vias.**

Current plan says input is "board with escape plan" but doesn't explicitly say channels account for via blockage.

### Gap: Channels Are An Approximation

The medial axis / Voronoi approach produces a graph of channels. But:
1. Real routing doesn't follow channels exactly
2. Diagonal routes cross multiple channels
3. Layer changes happen anywhere, not just at channel intersections

**Risk:** Topology says "feasible" based on channels, but geometric routing fails because the channel abstraction was wrong.

### Formalized Substeps

```
Stage 2.1: Build Obstacle Map
  Input: board outline, components, zones, escape_vias
  Output: MultiPolygon of blocked regions
  Include: component courtyards (not just pads)
  Include: zone keepouts
  Include: escape via pads (on relevant layers)
  Testable: obstacle_area < board_area

Stage 2.2: Compute Routing Space
  Input: board_outline, obstacles
  Output: MultiPolygon of routable area (may be disconnected)
  Method: board_outline.difference(obstacles)
  Testable: routing_space.is_valid(), not routing_space.is_empty

Stage 2.3: Extract Channel Skeleton
  Input: routing_space polygon
  Output: graph of channel centerlines
  Method: medial_axis or Voronoi of boundary
  Testable: skeleton.is_connected() for each routing region

Stage 2.4: Compute Channel Widths
  Input: skeleton edges, routing_space boundary
  Output: width at each point along skeleton
  Method: distance transform or explicit distance calculation
  Testable: all widths > 0

Stage 2.5: Calculate Per-Layer Capacity
  Input: channel widths, design_rules, stackup
  Output: dict[channel, dict[layer, int]]  # capacity per layer
  Formula: capacity[layer] = floor(width / (trace_width + clearance))
  Adjustment: plane layers have capacity = 0
  Adjustment: layers blocked by through vias have reduced capacity
  Testable: plane layers have 0 capacity

Stage 2.6: Estimate Channel Demand
  Input: netlist, pin positions, channels
  Output: dict[channel, list[net]]  # which nets likely use each channel
  Method: for each net, find shortest path through channel graph
  Testable: demand is computed for all nets

Stage 2.7: Identify Bottlenecks
  Input: capacities, demands
  Output: list of channels where demand > 80% capacity
  Testable: bottleneck channels flagged correctly
```

### Does Stage 1 → Stage 2 Flow Correctly?

| Stage 2 Needs | Stage 1 Provides? |
|---------------|-------------------|
| Placed board | YES (passed through) |
| Escape via positions | YES |
| Updated occupancy grid | YES |
| Component geometry | NO - needs original PCB |
| Zone geometry | NO - needs original PCB |

**Gap:** Stage 1 output doesn't include component/zone geometry - it only adds escape vias.

**Fix:** Each stage should pass through the full board state, adding its contributions:
```
Stage 1 Output: BoardState {
    pcb: ParsedPCB,           # Original
    design_intent: DesignIntent,  # From Stage 0
    escape_plan: EscapePlan,      # NEW from Stage 1
}
```

### Validation Tests

```python
class TestStage2:
    def test_2_1_obstacles_include_escapes(self):
        obstacles = build_obstacle_map(board, escape_plan)
        for via in escape_plan.vias:
            assert obstacles.contains(Point(via.position))

    def test_2_2_routing_space_valid(self):
        routing_space = compute_routing_space(board, obstacles)
        assert routing_space.is_valid()
        assert routing_space.area > 0

    def test_2_3_skeleton_connected(self):
        skeleton = extract_skeleton(routing_space)
        # Each connected component of routing_space should have connected skeleton
        for region in routing_space.geoms:
            region_skeleton = skeleton.intersection(region)
            assert is_connected_graph(region_skeleton)

    def test_2_5_plane_layers_zero_capacity(self):
        capacities = calculate_capacities(channels, stackup)
        for channel in channels:
            for plane_layer in stackup.plane_layers:
                assert capacities[channel][plane_layer] == 0

    def test_2_7_bottleneck_detection(self):
        bottlenecks = identify_bottlenecks(capacities, demands)
        for bn in bottlenecks:
            assert demands[bn] / capacities[bn] > 0.8
```

---

## Stage 3: Topological Routing

### Claimed Flow
```
Input: Channel analysis, design intent, escape plan
Output: Topology solution OR unsatisfiability proof
```

### Assumption Analysis

| Assumption | Valid? | Risk if Wrong |
|------------|--------|---------------|
| Routing can be modeled as channel assignment | PARTIALLY | Some routes don't fit channel model |
| SAT solver can handle problem size | UNKNOWN | Need benchmarks |
| Topology solution implies geometric feasibility | NO! | Core risk of the approach |
| Layer assignment is per-net | TOO COARSE | Need per-segment |

### Gap: The Core Thesis Risk

**The entire V6 architecture rests on this assumption:**

> "If topology is satisfiable, geometric realization will succeed."

**This may be FALSE because:**

1. **Channel approximation:** Real traces don't follow channel centerlines exactly
2. **Local congestion:** Two nets in same channel may conflict at narrow points
3. **Via placement:** Topology says "via somewhere in channel" but actual via may not fit
4. **Diagonal routing:** Traces crossing channels diagonally use capacity differently
5. **Pin positions:** Exact pin positions may make topological solution infeasible

**Mitigation already in plan:** Target 80% auto, not 100%. Flag hard nets.

**Additional mitigation needed:** Topology solution should have **slack** - don't use 100% of channel capacity.

### Gap: Diff Pairs Need More Than Same Channel

Diff pair constraints:
1. Same channel ✓ (in plan)
2. Adjacent slots (in plan)
3. **Same entry/exit points** (NOT in plan)
4. **No other traces between P and N** (NOT in plan)
5. **Continuous reference plane** (NOT in plan)

### Formalized Substeps

```
Stage 3.1: Build Constraint Model
  Input: channels, nets, design_intent, escape_plan
  Output: ConstraintModel with variables and constraints

  Variables:
    uses[net, channel]: bool
    layer[net, segment]: int
    order[net1, net2, channel]: int  # for same-channel nets
    via_location[net, i]: channel_node  # coarse via placement

  Testable: model has expected number of variables

Stage 3.2: Add Capacity Constraints
  Input: channel capacities (per-layer)
  Constraint: for each channel c, layer l:
    sum(uses[n,c] * width[n] for n in nets if layer[n]==l) <= capacity[c,l] * SLACK
  Note: SLACK = 0.8 to leave margin for geometric realization
  Testable: constraints correctly encoded

Stage 3.3: Add Connectivity Constraints
  Input: pin positions, channel graph
  Constraint: for each net n:
    path_exists(source[n], sink[n], {c: uses[n,c]})
  Method: encode reachability in SAT/SMT
  Testable: infeasible net reports disconnection

Stage 3.4: Add Diff Pair Constraints
  Input: design_intent.diff_pairs
  Constraint: for each DiffPair(P, N):
    uses[P, c] == uses[N, c] for all channels c  # Same channels
    |order[P,*,c] - order[N,*,c]| == 1  # Adjacent
    layer[P] == layer[N]  # Same layer
  Testable: diff pair nets assigned together

Stage 3.5: Add Layer Constraints
  Input: layer_assignment_rules
  Constraint: for HV nets:
    layer[n] in {0, 3}  # Outer only
  Constraint: for high-current nets:
    layer[n] in {0, 3}
  Testable: HV net not on inner layer

Stage 3.6: Add Reference Plane Constraints
  Input: stackup, plane_splits
  Constraint: for high-speed nets on layer L:
    not crosses_plane_split(net_path, stackup.reference_plane(L))
  Testable: high-speed net doesn't cross split

Stage 3.7: Solve
  Input: complete constraint model
  Output: Solution OR UnsatCore
  Method: Z3, MiniSat, or greedy with backtracking
  Timeout: 30 seconds (per decision gate)
  Testable: solution satisfies all constraints

Stage 3.8: Extract Topology Solution
  Input: solver solution
  Output: TopologySolution {
    channel_assignments: dict[net, list[channel]],
    layer_assignments: dict[net, dict[segment, layer]],
    via_locations: dict[net, list[channel_node]],
    crossing_orders: dict[channel, list[net]]
  }
  Testable: solution is well-formed

Stage 3.9: Generate Unsat Proof (if infeasible)
  Input: solver unsat core
  Output: UnroutabilityProof {
    conflicting_constraints: list[Constraint],
    suggested_relaxations: list[Suggestion]
  }
  Method: extract minimal unsat core, translate to human-readable
  Testable: proof identifies specific conflict
```

### Does Stage 2 → Stage 3 Flow Correctly?

| Stage 3 Needs | Stage 2 Provides? |
|---------------|-------------------|
| Channel graph | YES |
| Channel capacities | YES |
| Net-to-channel demands | YES (estimated) |
| Pin positions | NO - needs original PCB |
| Design intent | NO - from Stage 0 |
| Escape plan | NO - from Stage 1 |
| Stackup | NO - from Stage 0 |

**Gap:** Stage 3 needs data from multiple previous stages, not just Stage 2.

**Fix:** BoardState should accumulate all stage outputs:
```python
@dataclass
class BoardState:
    # Immutable from input
    pcb: ParsedPCB

    # Added by stages
    design_intent: DesignIntent | None = None       # Stage 0
    escape_plan: EscapePlan | None = None           # Stage 1
    channel_analysis: ChannelAnalysis | None = None # Stage 2
    topology: TopologySolution | None = None        # Stage 3
    routes: list[Route] | None = None               # Stage 4
    mfg_report: ManufacturingReport | None = None   # Stage 5
```

### Validation Tests

```python
class TestStage3:
    def test_3_2_capacity_not_exceeded(self):
        solution = solve_topology(model)
        for channel in channels:
            for layer in layers:
                used = sum(width[n] for n in solution.nets_in(channel, layer))
                assert used <= capacity[channel, layer]

    def test_3_4_diff_pairs_together(self):
        solution = solve_topology(model)
        for dp in design_intent.diff_pairs:
            assert solution.channels_for(dp.p) == solution.channels_for(dp.n)
            assert solution.layer_for(dp.p) == solution.layer_for(dp.n)

    def test_3_5_hv_outer_only(self):
        solution = solve_topology(model)
        for net in hv_nets:
            assert solution.layer_for(net) in [0, 3]

    def test_3_7_solves_within_timeout(self):
        start = time.time()
        result = solve_topology(model)
        elapsed = time.time() - start
        assert elapsed < 30  # Decision gate

    def test_3_9_unsat_has_proof(self):
        model = create_infeasible_model()
        result = solve_topology(model)
        assert result.status == "UNSAT"
        assert len(result.unsat_core) > 0
```

---

## Stage 4: Geometric Realization

### Claimed Flow
```
Input: Topology solution, escape plan, occupancy grid
Output: Routed PCB (target 80%, remainder flagged)
```

### Assumption Analysis

| Assumption | Valid? | Risk if Wrong |
|------------|--------|---------------|
| Topology solution is realizable | MOSTLY | Core risk |
| A* can route within channel constraints | YES | But may be slow |
| 80% success rate achievable | UNKNOWN | Need benchmarks |
| Failures can be flagged meaningfully | MUST DO | Requirement |

### Gap: How Does Topology Constrain A*?

The plan says "A* is easier because topology constrains it" but doesn't specify HOW.

**Options:**
1. **Hard constraint:** A* can ONLY use cells in assigned channels
2. **Soft constraint:** Penalty for leaving assigned channels
3. **Waypoint constraint:** Must pass through channel waypoints

**Option 1 (hard) risks:** Tight spots within channel may block routing
**Option 2 (soft) risks:** May find route outside channels, violating capacity
**Option 3 (waypoint) risks:** Waypoint placement affects routability

**Recommendation:** Use Option 1 (hard constraint) with fallback:
```python
def route_net_with_topology(net, topology, grid):
    # First try: strict channel following
    result = astar_in_channels(net, topology.channels_for(net), grid)
    if result.success:
        return result

    # Fallback: allow channel overflow with high penalty
    result = astar_with_soft_channels(net, topology, grid, overflow_penalty=100)
    if result.success:
        result.flag("CHANNEL_OVERFLOW")
        return result

    # Failed
    return RouteFailure(net, "No path even with overflow")
```

### Gap: Via Placement During Routing

Topology says "via somewhere in this channel intersection." But geometric routing needs exact via position.

**The A* must:**
1. Know which layer transitions are allowed (from topology)
2. Find valid via positions that don't violate DRC
3. Snap vias to grid
4. Update occupancy for subsequent nets

### Formalized Substeps

```
Stage 4.1: Initialize Routing Order
  Input: topology, net_classes
  Output: ordered list of nets to route
  Order: diff pairs first, then by length (longest first? shortest first?)
  Note: Topology may suggest order based on channel conflicts
  Testable: order is deterministic

Stage 4.2: For Each Net - Setup Constraints
  Input: net, topology.channels_for(net), topology.layer_for(net)
  Output: RoutingConstraints {
    allowed_channels: set[channel],
    allowed_layers: dict[segment, set[layer]],
    via_regions: list[Polygon],  # Where vias can go
    width: float,
    clearance: float
  }
  Testable: constraints match topology

Stage 4.3: For Each Net - Find Geometric Path
  Input: net, constraints, occupancy_grid
  Output: RoutePath | RouteFailure
  Method: A* or bidirectional A* constrained to channels
  Constraint: stay within allowed_channels (hard or soft)
  Constraint: layer transitions only in via_regions
  Testable: path is within channels or flagged

Stage 4.4: For Each Net - Place Vias
  Input: path with layer transitions, via_regions, drc_rules
  Output: list[Via] with exact positions
  Constraint: via position in allowed region
  Constraint: via doesn't violate DRC
  Method: snap to grid, check clearance
  Testable: all vias DRC-clean

Stage 4.5: For Each Net - Validate Route
  Input: complete route (traces + vias)
  Output: validation result
  Check: connectivity (all pins connected)
  Check: DRC (clearance, width)
  Check: reference plane continuity (if high-speed)
  Testable: validation passes or specific failure

Stage 4.6: For Each Net - Update Occupancy
  Input: validated route, occupancy_grid
  Output: updated occupancy_grid
  Effect: routed traces block cells for subsequent nets
  Testable: routed cells marked as occupied

Stage 4.7: Handle Routing Failures
  Input: failed net, failure reason
  Output: FlaggedNet with diagnostics
  Info: where it failed, what blocked it, suggestions
  Testable: failure has actionable diagnostics

Stage 4.8: Length Matching (for groups)
  Input: routed length group, tolerance
  Output: adjusted routes with serpentines OR failure
  Method: identify shortest/longest, add serpentine to shortest
  Constraint: serpentine fits in channel
  Testable: all lengths within tolerance

Stage 4.9: Compile Results
  Input: all routed nets, all flagged nets
  Output: RoutingResult {
    routes: list[Route],
    flagged: list[FlaggedNet],
    statistics: RoutingStats
  }
  Testable: routed + flagged = total nets
```

### Does Stage 3 → Stage 4 Flow Correctly?

| Stage 4 Needs | Stage 3 Provides? |
|---------------|-------------------|
| Channel assignments | YES |
| Layer assignments | YES |
| Via locations (coarse) | YES |
| Occupancy grid | NO - needs to be built |
| DRC rules | NO - from Stage 0 |

**Gap:** Stage 4 needs an occupancy grid. Where is it built?

Looking back: Stage 2 builds obstacle map. Stage 1 updates with escape vias. But "occupancy grid" (discrete cells) is different from "obstacle map" (polygons).

**Fix:** Add explicit grid building step, probably in Stage 2 or as Stage 2.5:
```
Stage 2.5: Build Occupancy Grid
  Input: board, obstacles, escape_vias, cell_size
  Output: 3D grid (x, y, layer) with blocked cells
  Testable: grid dimensions match board / cell_size
```

### Validation Tests

```python
class TestStage4:
    def test_4_1_routing_order_deterministic(self):
        order1 = compute_routing_order(topology)
        order2 = compute_routing_order(topology)
        assert order1 == order2

    def test_4_3_route_within_channels(self):
        route = route_net(net, constraints, grid)
        if route.success:
            for segment in route.segments:
                # Segment should be within assigned channels
                assert any(ch.contains(segment) for ch in constraints.allowed_channels)

    def test_4_4_vias_drc_clean(self):
        route = route_net(net, constraints, grid)
        for via in route.vias:
            assert drc_oracle.check_via(via) == []

    def test_4_5_route_connected(self):
        route = route_net(net, constraints, grid)
        if route.success:
            graph = build_connectivity(route)
            assert all_pins_connected(net.pins, graph)

    def test_4_7_failure_has_diagnostics(self):
        # Intentionally create a blocked net
        result = route_net(blocked_net, constraints, congested_grid)
        assert result.status == "FAILED"
        assert result.failure_point is not None
        assert len(result.blocking_nets) > 0

    def test_4_8_length_matching(self):
        routes = route_length_group(group, constraints, grid)
        lengths = [route.length_mm for route in routes]
        assert max(lengths) - min(lengths) <= group.tolerance_mm
```

---

## Stage 5: Manufacturing DRC

### Claimed Flow
```
Input: Routed PCB
Output: Manufacturing-ready PCB
```

### Assumption Analysis

| Assumption | Valid? | Risk if Wrong |
|------------|--------|---------------|
| Can detect acid traps | YES | Well-defined geometry |
| Can check annular ring | YES | Drill vs pad size |
| Can add teardrops | YES | Standard algorithm |
| Can balance copper | YES | Add thieving |
| Creepage calculable | COMPLEX | Need surface distance |

### Gap: Creepage Calculation is Hard

Creepage is **surface distance** along PCB, not straight-line distance.

Computing creepage requires:
1. Find all paths along PCB surface between two nets
2. Account for board edges (can go around)
3. Account for slots (create barriers)
4. Account for traces of same net (don't block themselves)
5. Find MINIMUM such path

**This is essentially a shortest-path problem on the PCB surface graph.**

### Gap: What Happens When Mfg DRC Fails?

The plan doesn't show what happens if Stage 5 finds violations.

**Options:**
1. **Auto-fix:** Add teardrops, fix acid traps automatically
2. **Re-route:** Go back to Stage 4 with new constraints
3. **Flag:** Report violations, user fixes manually
4. **Reject:** Fail the pipeline

**Recommendation:** Tiered approach:
```
AUTO-FIX: Teardrops, copper thieving (cosmetic)
FLAG: Acid traps, annular ring issues (need reroute)
BLOCK: Creepage violations (safety critical, cannot ship)
```

### Formalized Substeps

```
Stage 5.1: Acid Trap Detection
  Input: routed traces
  Output: list of acute angle locations
  Rule: angle < 90° between trace segments
  Fix: chamfer corners automatically
  Testable: no angles < 90° after fix

Stage 5.2: Annular Ring Check
  Input: vias, drill sizes, pad sizes
  Output: list of insufficient annular ring
  Rule: (pad_diameter - drill_diameter) / 2 >= min_annular_ring
  Fix: none (requires via redesign)
  Testable: all vias have sufficient ring

Stage 5.3: Teardrop Insertion
  Input: trace-pad junctions, trace-via junctions
  Output: updated traces with teardrops
  Method: add curved or chamfered transition
  Testable: teardrops don't violate clearance

Stage 5.4: Thermal Relief Check
  Input: pads connected to planes
  Output: list of pads needing thermal relief
  Rule: plane-connected pads need spoke pattern
  Fix: add thermal relief spokes
  Testable: all plane-connected pads have relief

Stage 5.5: Copper Balance Analysis
  Input: routed board, per-layer copper area
  Output: CopperBalance { layer: percentage }
  Target: 40-60% per layer
  Fix: add copper thieving to low-copper areas
  Testable: all layers in 35-65% range after thieving

Stage 5.6: Creepage Verification (Safety Critical)
  Input: safety_pairs, routed geometry
  Output: CreepageReport { pair: (required, actual, pass/fail) }
  Method: compute surface shortest path
  BLOCK: any creepage failure
  Testable: all safety pairs meet requirement

Stage 5.7: Clearance Verification (Final)
  Input: all geometry
  Output: ClearanceReport
  Check: trace-trace, trace-pad, via-via, via-trace
  BLOCK: any clearance failure
  Testable: no clearance violations

Stage 5.8: Generate Manufacturing Report
  Input: all check results
  Output: ManufacturingReport {
    status: PASS | FAIL | WARNINGS,
    violations: list[Violation],
    auto_fixes_applied: list[Fix],
    copper_balance: dict[layer, float],
    creepage_compliance: bool
  }
  Testable: report is complete
```

### Does Stage 4 → Stage 5 Flow Correctly?

| Stage 5 Needs | Stage 4 Provides? |
|---------------|-------------------|
| Routed traces | YES |
| Via positions | YES |
| Flagged nets | YES |
| Safety pairs | NO - from Stage 0 |
| Stackup | NO - from Stage 0 |

**Same pattern:** Stage 5 needs accumulated state from all stages.

### Validation Tests

```python
class TestStage5:
    def test_5_1_no_acid_traps(self):
        board = apply_acid_trap_fix(routed_board)
        traps = detect_acid_traps(board)
        assert len(traps) == 0

    def test_5_2_annular_ring_sufficient(self):
        violations = check_annular_ring(routed_board, min_ring=0.1)
        assert len(violations) == 0

    def test_5_5_copper_balanced(self):
        balanced = apply_copper_thieving(routed_board)
        for layer in balanced.layers:
            pct = copper_percentage(balanced, layer)
            assert 0.35 <= pct <= 0.65

    def test_5_6_creepage_compliance(self):
        """SAFETY CRITICAL - must pass."""
        report = verify_creepage(routed_board, safety_pairs)
        for pair, result in report.items():
            assert result.actual_mm >= result.required_mm, \
                f"SAFETY: {pair} creepage {result.actual_mm} < {result.required_mm}"

    def test_5_8_report_complete(self):
        report = generate_mfg_report(routed_board)
        assert report.status in ["PASS", "FAIL", "WARNINGS"]
        assert report.creepage_compliance is not None
```

---

## Feedback Loop: Placement Adjustment

### Claimed Flow
```
If routing fails or produces poor results:
  Generate feedback → Adjust placement → Re-run from Stage 1
```

### Assumption Analysis

| Assumption | Valid? | Risk if Wrong |
|------------|--------|---------------|
| Feedback identifies what to move | PARTIALLY | May be ambiguous |
| Small moves improve routability | USUALLY | May make worse |
| Convergence is guaranteed | NO | May oscillate |
| Rotation suggestions work | MAYBE | Not validated |

### Gap: Convergence Not Guaranteed

The plan mentions "damping" and "iteration limit" but doesn't formally guarantee convergence.

**Failure modes:**
1. **Oscillation:** Move A right → improves X, breaks Y → Move A left → improves Y, breaks X → repeat
2. **Local minimum:** No single move helps, but global rearrangement would
3. **Divergence:** Each iteration makes things worse

### Gap: What Triggers Feedback Loop?

Plan doesn't clearly specify when to enter feedback loop:
- Score below threshold?
- Any flagged nets?
- Specific violation types?

### Formalized Substeps

```
Feedback 1: Evaluate Routing Quality
  Input: RoutingResult from Stage 4
  Output: QualityScore and ImprovementNeeded flag
  Metrics:
    - completion_rate: routed / total
    - via_count: lower is better
    - total_length: lower is better (within reason)
    - drc_violations: 0 is required
  Threshold: completion_rate >= 0.8 AND drc_violations == 0
  Testable: score computed correctly

Feedback 2: Identify Congested Regions
  Input: flagged nets, channel analysis
  Output: CongestionMap { region: severity }
  Method: overlay all failure points, find clusters
  Testable: congested regions identified

Feedback 3: Generate Placement Suggestions
  Input: congestion_map, flagged_nets, current_placement
  Output: list[PlacementSuggestion]

  For each congested region:
    - Identify components contributing to congestion
    - Compute move direction (away from congestion)
    - Compute move magnitude (small: 1-2mm)
    - Check move doesn't violate placement rules

  For each flagged net:
    - Identify blocking components
    - Suggest rotation if pin escape is blocked
    - Suggest side change if layer transition needed

  Testable: suggestions are valid (don't overlap, in bounds)

Feedback 4: Apply Suggestions with Damping
  Input: suggestions, current_placement, damping_factor
  Output: new_placement

  Method:
    - Sort suggestions by expected impact
    - Apply top N suggestions (not all)
    - Scale move distances by damping_factor (0.5-0.8)
    - Re-check placement validity

  Testable: new placement is valid

Feedback 5: Check Convergence
  Input: history of scores
  Output: ConvergenceStatus

  Conditions:
    - CONVERGED: score improved < 1% for 3 iterations
    - OSCILLATING: score alternating up/down for 4 iterations
    - IMPROVING: score improving > 1%
    - DIVERGING: score worsening for 3 iterations

  Action:
    - CONVERGED or DIVERGING: stop iteration
    - OSCILLATING: reduce damping, try again
    - IMPROVING: continue

  Testable: convergence detected correctly

Feedback 6: Iteration Control
  Input: iteration_count, convergence_status, quality_score
  Output: Continue | Stop(reason)

  Rules:
    - Stop if quality_score meets threshold
    - Stop if iteration_count > max_iterations (10)
    - Stop if CONVERGED or DIVERGING
    - Continue if IMPROVING or OSCILLATING (with adjustment)

  Testable: stops at correct conditions
```

### Validation Tests

```python
class TestFeedback:
    def test_fb_1_quality_score(self):
        result = route_board(board)
        score = evaluate_quality(result)
        assert 0 <= score.completion_rate <= 1
        assert score.drc_violations >= 0

    def test_fb_3_suggestions_valid(self):
        suggestions = generate_placement_suggestions(congestion, flagged, placement)
        for s in suggestions:
            new_pos = apply_suggestion(placement, s)
            assert is_valid_placement(new_pos)

    def test_fb_5_convergence_detection(self):
        # Simulated improving scores
        history = [0.5, 0.6, 0.65, 0.68, 0.69, 0.695]
        status = check_convergence(history)
        assert status == ConvergenceStatus.CONVERGED

    def test_fb_5_oscillation_detection(self):
        history = [0.5, 0.6, 0.5, 0.6, 0.5]
        status = check_convergence(history)
        assert status == ConvergenceStatus.OSCILLATING

    def test_fb_6_max_iterations(self):
        for i in range(15):
            result = iterate_placement(board)
            if result.stop:
                break
        assert i <= 10  # Max iterations
```

---

## Holistic Analysis: Does A Lead to B Lead to C?

### Data Flow Diagram

```
                    ┌─────────────────────┐
                    │   Input: KiCad PCB  │
                    │   (placed, unrouted)│
                    └──────────┬──────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Stage 0: Design Intent                                               │
│ IN:  .kicad_pcb                                                      │
│ OUT: ParsedPCB + DesignIntent                                        │
│ GAP: Diff pairs may not be in PCB, need schematic or inference       │
└──────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Stage 1: Pin Escape                                                  │
│ IN:  ParsedPCB + DesignIntent                                        │
│ OUT: EscapePlan (via positions, types)                               │
│ GAP: Escape planning is itself a routing problem                     │
└──────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Stage 2: Channel Analysis                                            │
│ IN:  ParsedPCB + EscapePlan                                          │
│ OUT: ChannelGraph + Capacities + Demands                             │
│ GAP: Must account for escape vias blocking channels                  │
└──────────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Stage 3: Topological Routing                                         │
│ IN:  ChannelGraph + DesignIntent + EscapePlan                        │
│ OUT: TopologySolution OR UnsatProof                                  │
│ GAP: Topology feasibility ≠ geometric feasibility (core risk)        │
└──────────────────────────────────────────────────────────────────────┘
                               │
              ┌────────────────┴────────────────┐
              │ UNSAT                           │ SAT
              ▼                                 ▼
┌─────────────────────────┐    ┌───────────────────────────────────────┐
│ Generate UnsatProof     │    │ Stage 4: Geometric Realization        │
│ → Feedback Loop         │    │ IN:  TopologySolution + OccupancyGrid │
│                         │    │ OUT: Routes (80%) + FlaggedNets (20%) │
└─────────────────────────┘    │ GAP: Grid must be built somewhere     │
                               └───────────────────────────────────────┘
                                               │
                                               ▼
                               ┌───────────────────────────────────────┐
                               │ Stage 5: Manufacturing DRC            │
                               │ IN:  Routes + SafetyRules             │
                               │ OUT: MfgReport + AutoFixes            │
                               │ GAP: What if creepage fails?          │
                               └───────────────────────────────────────┘
                                               │
                               ┌───────────────┴───────────────┐
                               │ PASS                          │ FAIL
                               ▼                               ▼
                    ┌─────────────────────┐        ┌─────────────────────┐
                    │ Output: Routed PCB  │        │ Feedback Loop       │
                    └─────────────────────┘        │ → Placement Adjust  │
                                                   │ → Back to Stage 1   │
                                                   └─────────────────────┘
```

### Identified Gaps Summary

| Gap | Location | Severity | Fix |
|-----|----------|----------|-----|
| Placement source unclear | Pre-Stage 0 | HIGH | Document as precondition |
| Diff pair source unclear | Stage 0 | MEDIUM | Inference + config fallback |
| Escape is mini-routing | Stage 1 | MEDIUM | Acknowledge, simplify |
| Escape vias affect channels | Stage 1→2 | HIGH | Explicit via blockage |
| Topology ≠ Geometry | Stage 3→4 | HIGH | Slack factor + 80% target |
| Grid not built | Stage 2/4 | MEDIUM | Add explicit grid stage |
| Mfg failure path | Stage 5 | MEDIUM | Define tiered response |
| Convergence not guaranteed | Feedback | MEDIUM | Formal stopping criteria |

### Missing Pieces for Full Automation

| Piece | Required For | Status in Plan |
|-------|--------------|----------------|
| Schematic parsing | Diff pairs, length groups | Implied, not specified |
| Footprint library | Dense package identification | Assumed available |
| Fab capability config | Via types, drill limits | Not specified |
| Impedance calculator | Trace width for Z0 | Formula given, not impl |
| Creepage calculator | Safety verification | Complex, underspecified |
| Serpentine generator | Length matching | Mentioned, not detailed |

---

## Summary: Formalized Pipeline

```
PRECONDITIONS:
  - Input PCB has all components placed
  - Input PCB has netlist (from schematic)
  - Input PCB has design rules defined
  - (Optional) Config file with diff pairs, length groups if not inferrable

STAGE 0: Design Intent Extraction
  0.1: Load KiCad PCB
  0.2: Infer diff pairs from naming
  0.3: Load net classes from design rules
  0.4: Infer safety pairs (HV nets)
  0.5: Load/infer length groups
  0.6: Parse stackup
  → Output: BoardState { pcb, design_intent }

STAGE 1: Pin Escape Planning
  1.1: Identify dense packages
  1.2: Classify pads by escape need
  1.3: Compute escape via positions
  1.4: Select via types
  1.5: Validate escape plan (DRC)
  1.6: Reserve via positions in grid
  → Output: BoardState { ..., escape_plan }

STAGE 2: Channel Analysis
  2.1: Build obstacle map
  2.2: Compute routing space
  2.3: Extract channel skeleton
  2.4: Compute channel widths
  2.5: Build occupancy grid
  2.6: Calculate per-layer capacity
  2.7: Estimate channel demand
  2.8: Identify bottlenecks
  → Output: BoardState { ..., channel_analysis, occupancy_grid }

STAGE 3: Topological Routing
  3.1: Build constraint model
  3.2: Add capacity constraints (with slack)
  3.3: Add connectivity constraints
  3.4: Add diff pair constraints
  3.5: Add layer constraints
  3.6: Add reference plane constraints
  3.7: Solve (timeout 30s)
  3.8: Extract topology solution
  3.9: Generate unsat proof (if failed)
  → Output: BoardState { ..., topology } OR UnsatProof

STAGE 4: Geometric Realization
  4.1: Initialize routing order
  4.2: For each net: setup constraints from topology
  4.3: For each net: find geometric path (A*)
  4.4: For each net: place vias
  4.5: For each net: validate route
  4.6: For each net: update occupancy
  4.7: Handle failures (flag with diagnostics)
  4.8: Length matching (serpentines)
  4.9: Compile results
  → Output: BoardState { ..., routes, flagged_nets }

STAGE 5: Manufacturing DRC
  5.1: Acid trap detection + fix
  5.2: Annular ring check
  5.3: Teardrop insertion
  5.4: Thermal relief check
  5.5: Copper balance + thieving
  5.6: Creepage verification (BLOCKING)
  5.7: Clearance verification (BLOCKING)
  5.8: Generate manufacturing report
  → Output: BoardState { ..., mfg_report }

FEEDBACK LOOP (if quality < threshold):
  F.1: Evaluate routing quality
  F.2: Identify congested regions
  F.3: Generate placement suggestions
  F.4: Apply suggestions with damping
  F.5: Check convergence
  F.6: Iteration control
  → If continue: back to Stage 1
  → If stop: output best result

POSTCONDITIONS:
  - All nets either routed OR flagged with diagnostics
  - No DRC violations (clearance)
  - No safety violations (creepage)
  - Manufacturing checks pass
  - Copper balanced per layer
```
