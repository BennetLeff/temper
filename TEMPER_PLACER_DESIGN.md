# Temper-Placer: JAX-Based PCB Placement Optimizer

**Project:** temper-placer  
**Version:** 0.1.0 (Design Phase)  
**Date:** 2025-12-14  
**Status:** Design Document

---

## 1. Executive Summary

`temper-placer` is a standalone, modular tool for optimizing PCB component placement using gradient-based optimization in JAX. It is designed to encode expert PCB layout knowledge into differentiable loss functions, enabling repeatable, auditable, and iteratable placement optimization.

### Goals

1. **Automate intelligent placement** for the Temper induction cooker PCB (~100 components)
2. **Encode domain expertise** in constraints (HV clearance, thermal, EMI loops)
3. **Provide repeatability** - same inputs produce same outputs
4. **Ensure Robustness** - achieve 100% convergence via soft-body inflation and adaptive weighting
5. **Enable iteration** - adjust constraints, re-run, compare results
6. **Integrate with KiCad** - read/write native file formats via kiutils

### Non-Goals (Deferred)

- Full autorouting (separate tool, future work)
- 3D model generation
- Schematic generation (separate kiutils-based tool)

### Validation-in-the-Loop

Unlike pure geometric optimizers, temper-placer integrates real validation tools:
- **KiCad DRC** (`kicad-cli pcb drc`) for design rule checking
- **ngspice** for electrical simulation validation

This ensures optimized placements are not just geometrically valid but electrically sound.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         temper-placer Pipeline                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  INPUTS                           OPTIMIZER                    OUTPUTS      │
│  ══════                           ═════════                    ═══════      │
│                                                                             │
│  ┌──────────────┐                ┌─────────────┐              ┌──────────┐ │
│  │ .kicad_pcb   │───┐            │             │              │ .kicad_  │ │
│  │ (template)   │   │            │   JAX       │              │ pcb      │ │
│  └──────────────┘   │            │   Gradient  │              │ (placed) │ │
│                     ▼            │   Descent   │              └────▲─────┘ │
│  ┌──────────────┐ ┌─────────┐   │             │   ┌─────────┐     │       │
│  │ constraints  │─▶│ Problem │──▶│   + Gumbel  │──▶│ Post-   │─────┘       │
│  │ .yaml        │ │ Setup   │   │   Softmax   │   │ Process │              │
│  └──────────────┘ └─────────┘   │   (rotation)│   └────┬────┘              │
│                     ▲            │             │        │                   │
│  ┌──────────────┐   │            └──────┬──────┘        ▼                   │
│  │ footprint    │───┘                   │         ┌──────────┐             │
│  │ library      │                       │         │ report   │             │
│  └──────────────┘                       │         │ .html    │             │
│                                         ▼         └──────────┘             │
│                                  ┌─────────────┐                            │
│                                  │ Live        │                            │
│                                  │ Visualizer  │                            │
│                                  └─────────────┘                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Core Components

| Component | Responsibility | Technology |
|-----------|---------------|------------|
| **IO Layer** | Parse KiCad files, constraints, footprints | kiutils, PyYAML |
| **Geometry Engine** | Primitives, SDF, overlap detection | JAX (differentiable) |
| **Loss Functions** | Wirelength, clearance, thermal, etc. | JAX |
| **Optimizer** | Gradient descent, Gumbel-Softmax, scheduling | JAX + optax |
| **Visualizer** | Live training plots, placement rendering | Plotly (browser-based) |
| **CLI** | User interface | Click or Typer |

---

## 3. Design Decisions

### 3.1 Discrete Rotation via Gumbel-Softmax

**Decision:** Use Gumbel-Softmax for differentiable discrete rotation sampling.

**Rationale:**
- PCB components can only be placed at 0°, 90°, 180°, 270°
- Gumbel-Softmax allows gradient flow through discrete choices
- Temperature annealing transitions from soft (exploration) to hard (exploitation)

**Implementation:**
```python
def sample_rotation(logits, key, temperature=1.0):
    """
    Sample rotation differentiably using Gumbel-Softmax.
    
    Args:
        logits: (N, 4) rotation preference logits
        key: JAX random key
        temperature: Softmax temperature (anneal from 5.0 → 0.1)
    
    Returns:
        (N, 4) one-hot rotation indicators (soft during training)
    """
    gumbel = -jnp.log(-jnp.log(jax.random.uniform(key, logits.shape) + 1e-10) + 1e-10)
    soft = jax.nn.softmax((logits + gumbel) / temperature)
    hard = jax.nn.one_hot(jnp.argmax(soft, axis=-1), 4)
    return soft + jax.lax.stop_gradient(hard - soft)  # Straight-through estimator
```

### 3.2 Routability-Aware Placement (No Full Routing)

**Decision:** Estimate routing congestion during placement; defer actual routing.

**Rationale:**
- Full simultaneous P&R is significantly more complex
- Congestion estimation provides 80% of the benefit at 20% of the complexity
- KiCad's push-and-shove router is excellent for manual routing
- Future work can add global routing as a separate module

**Implementation:**
- Divide board into grid cells (e.g., 1mm × 1mm)
- For each net, estimate which cells it will traverse (bounding box or Steiner estimate)
- Sum demand per cell; penalize cells where demand > supply
- Supply = (routable_layers) × (tracks_per_mm)

### 3.3 Layer-Aware Congestion Model

**Decision:** Model the 4-layer stackup explicitly in congestion estimation.

**Rationale:**
- Your stackup has only 2 routable layers (L1 and L4)
- L2 (GND) and L3 (PWR) are planes with limited routing
- HV traces must stay on L1 (2oz copper)
- Signal traces prefer L4

**Implementation:**
```python
@dataclass
class LayerStackup:
    layers: List[Layer]
    
    def routable_layers(self, net_class: str) -> List[int]:
        """Return layer indices where this net class can route."""
        if net_class == "HighVoltage":
            return [0]  # L1 only (2oz copper)
        elif net_class == "Power":
            return [0, 3]  # L1 or L4
        else:
            return [0, 3]  # L1 or L4 (avoid planes)
    
    def tracks_per_mm(self, layer: int, net_class: str) -> float:
        """Estimate routing tracks per mm for given layer/net class."""
        clearance = self.get_clearance(net_class)
        trace_width = self.get_trace_width(net_class)
        return 1.0 / (trace_width + clearance)
```

### 3.4 Ground Plane Split Awareness

**Decision:** Model ground domain crossings as routing constraints.

**Rationale:**
- Your design has PGND, CGND, and ISOGND domains
- Signals should not cross ground splits (causes return current issues)
- Only cross at designated star ground point

**Implementation:**
```python
def ground_crossing_loss(positions, netlist, ground_domains):
    """
    Penalize nets that would need to cross ground domain boundaries.
    """
    total = 0.0
    for net in netlist.nets:
        pin_positions = get_pin_positions(positions, net.pins)
        
        # Check which ground domains the net spans
        domains_touched = set()
        for pos in pin_positions:
            domains_touched.add(get_ground_domain(pos, ground_domains))
        
        # Penalize if net spans multiple domains (except at star point)
        if len(domains_touched) > 1:
            # Check if path goes through star ground
            if not path_through_star_ground(pin_positions, ground_domains.star_point):
                total += 10.0  # Heavy penalty
    
    return total
```

### 3.5 Initial Placement from .kicad_pcb

**Decision:** Read initial placement from existing KiCad file; allow random initialization as fallback.

**Rationale:**
- You may have partially placed designs to refine
- Allows "warm start" from human-guided placement
- Random initialization within zones as fallback

**Implementation:**
```python
def load_initial_placement(pcb_file: Path, constraints: Constraints) -> PlacementState:
    """
    Load initial placement from KiCad PCB file.
    
    Falls back to zone-centered random placement for unplaced components.
    """
    pcb = kiutils.board.Board.from_file(pcb_file)
    
    positions = []
    for component in constraints.components:
        footprint = find_footprint(pcb, component.ref)
        if footprint and footprint.position != (0, 0):
            # Use existing position
            positions.append(footprint.position)
        else:
            # Random position within assigned zone
            zone = constraints.get_zone(component.ref)
            positions.append(random_in_zone(zone))
    
    return PlacementState(positions=jnp.array(positions), ...)
```

### 3.6 Visualization: Plotly in Browser

**Decision:** Use Plotly with browser-based live updates via WebSocket.

**Rationale:**
- Interactive (zoom, pan, hover for component info)
- Works in any environment (remote servers, WSL, etc.)
- Real-time updates via WebSocket more robust than matplotlib animation
- Can generate static HTML reports for documentation

**Implementation:**
- Spawn lightweight HTTP server on `localhost:8765`
- WebSocket pushes placement updates every N iterations
- Browser renders board outline, components, zones, violations
- Loss curves in separate panel

### 3.7 Constraint Validation (Pre-flight Check)

**Decision:** Validate constraint satisfiability before optimization starts.

**Rationale:**
- Catch configuration errors early
- Impossible constraints waste optimization time
- Provides clear error messages

**Checks:**
- All components fit within assigned zones
- Zone areas sufficient for component total area (with margin)
- Fixed placements don't violate clearances
- No circular zone dependencies

### 3.8 Multi-Phase Training with Curriculum Learning

**Decision:** Use progressive constraint introduction (curriculum learning).

**Rationale:**
- Throwing all constraints at once creates difficult optimization landscape
- Easier to find feasible region first, then optimize
- Matches human intuition (spread out, then refine)

**Phases:**

| Phase | Focus | Constraints | LR | Epochs |
|-------|-------|-------------|-----|--------|
| 1 | Spread | Wirelength, Spread, Boundary | 1.0 | 1000 |
| 2 | Feasibility | + Overlap, Zone | 0.1 | 2000 |
| 3 | Design Rules | + HV Clearance, Ground Domains | 0.05 | 2000 |
| 4 | Performance | + Thermal, Loop Area, Congestion | 0.01 | 2000 |
| 5 | Refinement | All (hard weights), discrete rotations | 0.001 | 1000 |

---

## 4. Loss Function Specification

### 4.1 Loss Function Hierarchy

```
Total Loss
├── Hard Constraints (w = 100)
│   ├── overlap_loss        - Components must not intersect
│   ├── boundary_loss       - Components must be inside board
│   └── clearance_hv_loss   - HV isolation (10mm minimum)
│
├── Design Rules (w = 10-50)
│   ├── zone_loss           - Components in assigned zones
│   ├── ground_crossing     - No signals cross ground splits
│   └── antenna_keepout     - No components/copper near ESP32 antenna
│
├── Performance (w = 1-20)
│   ├── wirelength_loss     - Minimize total wire length (HPWL)
│   ├── congestion_loss     - Routability estimation
│   ├── thermal_loss        - IGBTs near board edge
│   └── loop_area_loss      - Minimize gate drive loop area
│
└── Regularization (w = 0.1-1, annealed)
    ├── spread_loss         - Prevent component clustering
    └── rotation_entropy    - Encourage rotation exploration
```

### 4.2 Individual Loss Functions

#### 4.2.1 Overlap Loss (Hard Constraint)

Uses signed distance functions (SDF) for smooth, differentiable overlap detection.

```python
def overlap_loss(positions: Array, rotations: Array, footprints: List[Footprint]) -> float:
    """
    Penalize overlapping components using smooth SDF.
    
    Returns sum of squared overlap amounts.
    """
    n = len(positions)
    total = 0.0
    
    for i in range(n):
        for j in range(i + 1, n):
            # Compute minimum distance between component bounding boxes
            # Negative distance = overlap
            dist = box_box_distance(
                positions[i], rotations[i], footprints[i].bounds,
                positions[j], rotations[j], footprints[j].bounds,
            )
            # Soft penalty for overlap
            total += jax.nn.relu(-dist) ** 2
    
    return total
```

#### 4.2.2 Wirelength Loss (HPWL)

Half-Perimeter Wire Length - standard metric for placement quality.

```python
def wirelength_loss(positions: Array, netlist: Netlist) -> float:
    """
    Compute Half-Perimeter Wire Length (HPWL) for all nets.
    
    Uses smooth min/max (LogSumExp) for differentiability.
    """
    total = 0.0
    
    for net in netlist.nets:
        if len(net.pins) < 2:
            continue
        
        pin_positions = get_pin_positions(positions, net.pins)
        
        # LogSumExp approximation of max/min
        alpha = 10.0  # Smoothing parameter
        x_max = logsumexp(alpha * pin_positions[:, 0]) / alpha
        x_min = -logsumexp(-alpha * pin_positions[:, 0]) / alpha
        y_max = logsumexp(alpha * pin_positions[:, 1]) / alpha
        y_min = -logsumexp(-alpha * pin_positions[:, 1]) / alpha
        
        hpwl = (x_max - x_min) + (y_max - y_min)
        total += hpwl * net.weight  # Optional net weighting
    
    return total
```

#### 4.2.3 HV Clearance Loss

Enforces minimum distance between high-voltage and low-voltage components.

```python
def clearance_hv_loss(
    positions: Array,
    hv_component_indices: List[int],
    lv_component_indices: List[int],
    min_clearance: float = 10.0,  # mm
) -> float:
    """
    Penalize HV-LV component pairs that are too close.
    
    Per PCB_SPECIFICATION.md: 10mm clearance for reinforced isolation.
    """
    total = 0.0
    
    for hv_idx in hv_component_indices:
        for lv_idx in lv_component_indices:
            dist = jnp.linalg.norm(positions[hv_idx] - positions[lv_idx])
            violation = jax.nn.relu(min_clearance - dist)
            total += violation ** 2
    
    return total
```

#### 4.2.4 Thermal Loss

IGBTs must be near board edge for heatsink mounting.

```python
def thermal_loss(
    positions: Array,
    thermal_components: List[ThermalConstraint],
    board: Board,
) -> float:
    """
    Penalize thermal components far from their designated board edge.
    """
    total = 0.0
    
    for tc in thermal_components:
        pos = positions[tc.component_idx]
        
        if tc.edge == "TOP":
            dist_to_edge = board.height - pos[1]
        elif tc.edge == "BOTTOM":
            dist_to_edge = pos[1]
        elif tc.edge == "LEFT":
            dist_to_edge = pos[0]
        elif tc.edge == "RIGHT":
            dist_to_edge = board.width - pos[0]
        
        # Penalize if farther than max_distance from edge
        violation = jax.nn.relu(dist_to_edge - tc.max_distance)
        total += violation ** 2
    
    return total
```

#### 4.2.5 Loop Area Loss

Minimize area of critical current loops (gate drive, bootstrap).

```python
def loop_area_loss(
    positions: Array,
    loop_constraints: List[LoopConstraint],
    netlist: Netlist,
) -> float:
    """
    Penalize large current loop areas (EMI source).
    
    Uses shoelace formula for polygon area (differentiable).
    """
    total = 0.0
    
    for loop in loop_constraints:
        # Get pin positions forming the loop
        loop_pins = get_loop_pin_positions(positions, netlist, loop)
        
        # Compute polygon area using shoelace formula
        # area = 0.5 * |sum(x_i * y_{i+1} - x_{i+1} * y_i)|
        n = len(loop_pins)
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += loop_pins[i, 0] * loop_pins[j, 1]
            area -= loop_pins[j, 0] * loop_pins[i, 1]
        area = jnp.abs(area) / 2.0
        
        # Penalize area exceeding maximum
        violation = jax.nn.relu(area - loop.max_area)
        total += violation ** 2
    
    return total
```

#### 4.2.6 Congestion Loss

Estimate routing difficulty to guide placement.

```python
def congestion_loss(
    positions: Array,
    netlist: Netlist,
    board: Board,
    layer_stackup: LayerStackup,
    grid_size: float = 1.0,  # mm
) -> float:
    """
    Estimate routing congestion per grid cell.
    
    Penalize cells where routing demand exceeds supply.
    """
    grid_h = int(board.height / grid_size)
    grid_w = int(board.width / grid_size)
    
    # Initialize demand per cell per layer
    demand = jnp.zeros((grid_h, grid_w, len(layer_stackup.routable_layers("Default"))))
    
    for net in netlist.nets:
        pin_positions = get_pin_positions(positions, net.pins)
        
        # Estimate cells this net will traverse (bounding box heuristic)
        bbox = bounding_box(pin_positions)
        cells = get_cells_in_bbox(bbox, grid_size)
        
        # Add demand to appropriate layers
        layers = layer_stackup.routable_layers(net.net_class)
        for cell in cells:
            demand = demand.at[cell[0], cell[1], layers].add(1.0 / len(layers))
    
    # Compute supply per cell (tracks that fit)
    supply = layer_stackup.tracks_per_cell(grid_size)
    
    # Penalize overflow
    overflow = jax.nn.relu(demand - supply)
    return jnp.sum(overflow ** 2)
```

---

## 5. Training Configuration

### 5.1 Optimizer Settings

```yaml
# configs/temper/training.yaml

optimizer:
  type: adam
  learning_rate:
    initial: 1.0
    warmup_steps: 100
    decay: cosine
    final: 0.001
  gradient_clip: 1.0

training:
  total_epochs: 8000
  phases:
    - name: spread
      epochs: 1000
      lr_multiplier: 1.0
      temperature: 5.0
      weights:
        wirelength: 1.0
        boundary: 100.0
        spread: 1.0
    
    - name: feasibility
      epochs: 2000
      lr_multiplier: 0.1
      temperature: 2.0
      weights:
        wirelength: 1.0
        boundary: 100.0
        overlap: 50.0
        zone: 10.0
    
    - name: design_rules
      epochs: 2000
      lr_multiplier: 0.05
      temperature: 1.0
      weights:
        wirelength: 1.0
        boundary: 100.0
        overlap: 100.0
        zone: 20.0
        clearance_hv: 50.0
        ground_crossing: 30.0
    
    - name: performance
      epochs: 2000
      lr_multiplier: 0.01
      temperature: 0.5
      weights:
        wirelength: 1.0
        boundary: 100.0
        overlap: 100.0
        zone: 20.0
        clearance_hv: 100.0
        ground_crossing: 50.0
        thermal: 10.0
        loop_area: 20.0
        congestion: 5.0
    
    - name: refinement
      epochs: 1000
      lr_multiplier: 0.001
      temperature: 0.1
      weights:
        # All weights at final values
        wirelength: 1.0
        boundary: 100.0
        overlap: 100.0
        zone: 50.0
        clearance_hv: 100.0
        ground_crossing: 100.0
        thermal: 20.0
        loop_area: 30.0
        congestion: 10.0

post_processing:
  grid_snap: 0.5  # mm
  discrete_rotation_search: true
  final_drc_check: true
```

### 5.2 Convergence Criteria

```python
@dataclass
class ConvergenceCriteria:
    # Stop if loss doesn't improve by this fraction
    min_improvement: float = 1e-6
    patience: int = 500  # epochs without improvement
    
    # Stop if all hard constraints satisfied
    max_overlap: float = 0.01  # mm²
    max_boundary_violation: float = 0.01  # mm
    max_clearance_violation: float = 0.1  # mm
```

---

## 6. Constraint Configuration for Temper

### 6.1 Board Definition

```yaml
# configs/temper/board.yaml

board:
  width: 100.0   # mm
  height: 150.0  # mm
  origin: [0, 0]
  corner_radius: 3.0

mounting_holes:
  - position: [5, 5]
    diameter: 3.2
    keepout: 3.0
  - position: [95, 5]
    diameter: 3.2
    keepout: 3.0
  - position: [5, 145]
    diameter: 3.2
    keepout: 3.0
  - position: [95, 145]
    diameter: 3.2
    keepout: 3.0

layer_stackup:
  - name: L1_Top
    type: signal
    copper_weight: 2  # oz
    routable: true
  - name: L2_GND
    type: plane
    copper_weight: 1
    routable: false
  - name: L3_PWR
    type: plane
    copper_weight: 1
    routable: false
  - name: L4_Bottom
    type: signal
    copper_weight: 1
    routable: true
```

### 6.2 Zone Definitions

```yaml
# configs/temper/zones.yaml

zones:
  HIGH_VOLTAGE:
    bounds: [[0, 0], [100, 35]]
    color: "#FF6B6B"
    components:
      - D1
      - D2
      - C_BUS1
      - C_BUS2
      - R_BLEED1
      - R_BLEED2
      - NTC_INRUSH
      - K_BYPASS

  HALF_BRIDGE:
    bounds: [[0, 35], [100, 70]]
    color: "#FFA94D"
    components:
      - Q1
      - Q2
      - U_GD
      - D_BOOT
      - C_BOOT
      - RG_ON_1
      - RG_ON_2
      - RGS_1
      - RGS_2

  POWER_MANAGEMENT:
    bounds: [[0, 70], [50, 100]]
    color: "#69DB7C"
    components:
      - U_BUCK
      - L_BUCK
      - C_IN_BUCK
      - C_OUT_BUCK_1
      - C_OUT_BUCK_2
      - C_BOOT_BUCK
      - R_FB1
      - R_FB2
      - U_LDO
      - C_IN_LDO
      - C_OUT_LDO

  CONTROL:
    bounds: [[0, 100], [100, 150]]
    color: "#74C0FC"
    components:
      - U_MCU
      - C_DEC_MCU_1
      - C_DEC_MCU_2
      - C_DEC_MCU_3
      - C_DEC_MCU_4
      - C_BULK_MCU
      - U_RTD1
      - U_RTD2
      - U_ISO
      - U_OCP
      - U_OVP
      - U_THERMAL
      - U_OR
      - U_NAND
      - U_AND
      - U_INV
      - U_WDT
      - U_RECT

  SENSING:
    bounds: [[50, 70], [100, 100]]
    color: "#B197FC"
    components:
      - CT1
      - R_BURDEN
      - R_AA
      - C_AA

ground_domains:
  PGND:
    bounds: [[0, 0], [100, 70]]
    star_point: [50, 70]
  
  CGND:
    bounds: [[0, 70], [100, 150]]
    star_point: [50, 70]
  
  ISOGND:
    # Isolated - no connection to other domains
    components: [U_GD]  # High-side of gate driver
```

### 6.3 Clearance Rules

```yaml
# configs/temper/clearances.yaml

net_classes:
  HighVoltage:
    trace_width: 2.0
    clearance: 2.0
    via_diameter: 1.2
    components:
      - D1
      - D2
      - C_BUS1
      - C_BUS2
      - Q1
      - Q2

  Power:
    trace_width: 1.0
    clearance: 0.5
    via_diameter: 1.0

  Default:
    trace_width: 0.2
    clearance: 0.2
    via_diameter: 0.6

clearance_rules:
  # Reinforced isolation: HV to any LV
  - class_a: HighVoltage
    class_b: Default
    min_clearance: 10.0
    type: reinforced
  
  - class_a: HighVoltage
    class_b: Power
    min_clearance: 6.0
    type: basic
  
  # Functional isolation within HV domain
  - class_a: HighVoltage
    class_b: HighVoltage
    min_clearance: 2.0
    type: functional
```

### 6.4 Thermal Constraints

```yaml
# configs/temper/thermal.yaml

thermal_components:
  - ref: Q1
    edge: TOP
    max_distance: 5.0
    heatsink_clearance: 10.0
    reason: "IGBT requires heatsink mounting on board edge"

  - ref: Q2
    edge: TOP
    max_distance: 5.0
    heatsink_clearance: 10.0
    adjacent_to: Q1
    reason: "Half-bridge pair should be adjacent for thermal management"

thermal_zones:
  # Keep hot components away from temperature-sensitive parts
  - hot_components: [Q1, Q2, D1, D2, NTC_INRUSH]
    sensitive_components: [U_MCU, U_RTD1, U_RTD2]
    min_distance: 30.0
```

### 6.5 Loop Constraints

```yaml
# configs/temper/loops.yaml

critical_loops:
  - name: gate_drive_high
    description: "High-side gate drive loop - minimize for EMI"
    components: [U_GD, Q1]
    pins:
      - [U_GD, OUTA]
      - [Q1, GATE]
      - [Q1, EMITTER]
      - [U_GD, VSSA]
    max_area: 100.0  # mm²
    priority: critical

  - name: gate_drive_low
    description: "Low-side gate drive loop"
    components: [U_GD, Q2]
    pins:
      - [U_GD, OUTB]
      - [Q2, GATE]
      - [Q2, EMITTER]
      - [U_GD, VSSB]
    max_area: 100.0
    priority: critical

  - name: bootstrap
    description: "Bootstrap charging loop"
    components: [D_BOOT, C_BOOT, U_GD]
    pins:
      - [D_BOOT, ANODE]
      - [D_BOOT, CATHODE]
      - [C_BOOT, POS]
      - [C_BOOT, NEG]
    max_area: 50.0
    priority: high

  - name: buck_switch
    description: "Buck converter switch node loop"
    components: [U_BUCK, L_BUCK, C_IN_BUCK]
    max_area: 25.0
    priority: high
```

### 6.6 Special Zones

```yaml
# configs/temper/special_zones.yaml

antenna_keepout:
  component: U_MCU
  antenna_position: top  # Antenna is at top of module
  keepout_radius: 15.0   # mm
  no_copper: true
  no_components: true
  no_ground_plane: true

fixed_placements:
  # Components with fixed positions (won't be optimized)
  - ref: U_MCU
    position: [50, 125]
    rotation: 0
    reason: "Centered in control zone for antenna clearance"
    locked: false  # Can be refined, but starts here

connector_zones:
  - name: AC_INPUT
    edge: LEFT
    position_range: [0, 35]
    components: [J_AC]
  
  - name: COIL_OUTPUT
    edge: TOP
    position_range: [40, 60]
    components: [J_COIL]
  
  - name: PROGRAMMING
    edge: BOTTOM
    position_range: [40, 60]
    components: [J_PROG]
```

---

## 7. Module Specifications

### 7.1 Core Data Structures

```python
# src/temper_placer/core/state.py

from dataclasses import dataclass
from jax import Array

@dataclass
class PlacementState:
    """Mutable state during optimization."""
    positions: Array          # (N, 2) component center positions
    rotation_logits: Array    # (N, 4) Gumbel-Softmax logits for rotation
    
    def get_rotations(self, temperature: float, key) -> Array:
        """Sample rotations using Gumbel-Softmax."""
        return gumbel_softmax(self.rotation_logits, temperature, key)


@dataclass
class Component:
    """Component definition."""
    ref: str                  # Reference designator (e.g., "U1")
    footprint: str            # Footprint name
    bounds: tuple             # (width, height) in mm
    pins: List[Pin]           # Pin definitions with relative positions
    net_class: str            # Net class for clearance rules
    zone: str                 # Assigned zone
    fixed: bool = False       # If True, position is locked


@dataclass 
class Pin:
    """Pin definition."""
    name: str
    number: str
    position: tuple           # Relative to component center
    net: str                  # Connected net name


@dataclass
class Net:
    """Net definition."""
    name: str
    pins: List[Tuple[str, str]]  # List of (component_ref, pin_name)
    net_class: str


@dataclass
class Netlist:
    """Complete netlist."""
    components: List[Component]
    nets: List[Net]
    
    def get_component_index(self, ref: str) -> int:
        """Get array index for component by reference."""
        for i, c in enumerate(self.components):
            if c.ref == ref:
                return i
        raise ValueError(f"Component {ref} not found")
```

### 7.2 Loss Function Interface

```python
# src/temper_placer/losses/base.py

from abc import ABC, abstractmethod
from typing import Dict
from jax import Array

class LossFunction(ABC):
    """Base class for loss functions."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this loss."""
        pass
    
    @abstractmethod
    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: "OptimizationContext",
    ) -> float:
        """Compute loss value."""
        pass
    
    def weight_schedule(self, epoch: int, total_epochs: int) -> float:
        """Return weight for this loss at given epoch. Override for custom schedules."""
        return 1.0


class CompositeLoss:
    """Combines multiple loss functions with weights."""
    
    def __init__(self, losses: List[LossFunction], weights: Dict[str, float]):
        self.losses = losses
        self.weights = weights
    
    def __call__(
        self,
        positions: Array,
        rotations: Array,
        context: "OptimizationContext",
        epoch: int,
    ) -> Tuple[float, Dict[str, float]]:
        """Compute weighted sum of losses, return total and breakdown."""
        breakdown = {}
        total = 0.0
        
        for loss_fn in self.losses:
            value = loss_fn(positions, rotations, context)
            weight = self.weights.get(loss_fn.name, 1.0)
            schedule_mult = loss_fn.weight_schedule(epoch, context.total_epochs)
            
            weighted = value * weight * schedule_mult
            breakdown[loss_fn.name] = value
            total += weighted
        
        return total, breakdown
```

### 7.3 Visualization Specification

```python
# src/temper_placer/visualization/live_plot.py

class LiveVisualizer:
    """
    Real-time visualization of placement optimization.
    
    Architecture:
    - Runs HTTP server on localhost:8765
    - Serves static HTML/JS viewer
    - Pushes updates via WebSocket
    - Updates every N iterations (configurable)
    """
    
    def __init__(self, port: int = 8765, update_interval: int = 50):
        self.port = port
        self.update_interval = update_interval
        self.server = None
        self.clients = []
    
    def start(self):
        """Start visualization server."""
        # Spawn server thread
        # Open browser to http://localhost:{port}
        pass
    
    def update(self, state: PlacementState, losses: Dict[str, float], epoch: int):
        """Push update to connected clients."""
        if epoch % self.update_interval != 0:
            return
        
        payload = {
            "epoch": epoch,
            "positions": state.positions.tolist(),
            "rotations": jnp.argmax(state.rotation_logits, axis=-1).tolist(),
            "losses": losses,
        }
        
        for client in self.clients:
            client.send_json(payload)
    
    def stop(self):
        """Shutdown server."""
        pass
```

**Visualization Features:**

1. **Board View:**
   - Board outline with mounting holes
   - Zone boundaries (color-coded)
   - Component rectangles (positioned, rotated)
   - Color by: zone, net class, violation status
   - Hover: component details, connected nets

2. **Loss Curves:**
   - Total loss (log scale)
   - Per-term breakdown (stacked area or lines)
   - Constraint violation counts

3. **Constraint Status:**
   - Red/yellow/green indicators for each constraint type
   - List of current violations with severity

4. **Controls:**
   - Pause/resume optimization
   - Step forward N iterations
   - Export current state
   - Adjust weights live (advanced)

---

## 8. CLI Specification

```bash
# Primary commands
temper-placer optimize [OPTIONS]      # Run placement optimization
temper-placer validate [OPTIONS]      # Validate constraints (pre-flight)
temper-placer export [OPTIONS]        # Export placements to KiCad
temper-placer visualize [OPTIONS]     # View existing placement
temper-placer report [OPTIONS]        # Generate HTML report

# Example usage
temper-placer optimize \
    --pcb pcb/temper.kicad_pcb \
    --constraints configs/temper/ \
    --output results/placement.json \
    --visualize \
    --epochs 8000

temper-placer export \
    --placements results/placement.json \
    --pcb pcb/temper.kicad_pcb \
    --output pcb/temper_placed.kicad_pcb

temper-placer report \
    --placements results/placement.json \
    --constraints configs/temper/ \
    --output results/report.html
```

---

## 9. Testing Strategy

### 9.1 Unit Tests

- **Geometry:** SDF correctness, overlap detection, rotation transforms
- **Losses:** Each loss function with known inputs/outputs
- **Optimizer:** Gradient computation, convergence on toy problems

### 9.2 Integration Tests

- **Simple board:** 10 components, basic zones, verify convergence
- **Temper board:** Full 100 components, verify all constraints satisfied

### 9.3 Regression Tests

- **Determinism:** Same seed → same output
- **Performance:** Optimization completes in < 5 minutes for 100 components

---

## 10. Validation-in-the-Loop Architecture

### 10.1 Overview

Unlike pure geometric optimizers, temper-placer integrates real validation tools into the optimization loop. This ensures placements are not just geometrically valid but electrically sound.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Validation-in-the-Loop Architecture                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐                   │
│  │  Geometric  │     │   KiCad     │     │   ngspice   │                   │
│  │  Loss Fns   │     │   DRC       │     │   Simulation│                   │
│  │  (JAX)      │     │   (CLI)     │     │   (CLI)     │                   │
│  └──────┬──────┘     └──────┬──────┘     └──────┬──────┘                   │
│         │                   │                   │                           │
│         │ Differentiable    │ Non-diff          │ Non-diff                  │
│         │ (every iter)      │ (periodic)        │ (periodic)                │
│         │                   │                   │                           │
│         └───────────────────┼───────────────────┘                           │
│                             │                                               │
│                             ▼                                               │
│                   ┌─────────────────────┐                                   │
│                   │   Loss Aggregator   │                                   │
│                   │   + Penalty Terms   │                                   │
│                   └──────────┬──────────┘                                   │
│                              │                                               │
│                              ▼                                               │
│                   ┌─────────────────────┐                                   │
│                   │   Optimizer Step    │                                   │
│                   │   (gradient-based   │                                   │
│                   │    for geometric,   │                                   │
│                   │    penalty for      │                                   │
│                   │    validation)      │                                   │
│                   └─────────────────────┘                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 10.2 KiCad DRC Integration

**Purpose:** Validate design rules that are difficult to model geometrically (complex clearances, zone fills, via rules).

**Implementation:**

```python
# src/temper_placer/validation/drc.py

import subprocess
import json
from pathlib import Path
from typing import List, Dict

@dataclass
class DRCViolation:
    """Single DRC violation from KiCad."""
    severity: str          # "error" | "warning"
    rule: str              # e.g., "clearance", "track_width"
    description: str
    position: tuple        # (x, y) in mm
    items: List[str]       # Affected items (net names, refs)


class KiCadDRCValidator:
    """
    Run KiCad DRC headlessly and parse results.
    
    Uses `kicad-cli pcb drc` (KiCad 7+).
    """
    
    def __init__(self, kicad_cli_path: str = "kicad-cli"):
        self.kicad_cli = kicad_cli_path
    
    def run_drc(self, pcb_path: Path, output_path: Path = None) -> List[DRCViolation]:
        """
        Run DRC on a KiCad PCB file.
        
        Args:
            pcb_path: Path to .kicad_pcb file
            output_path: Optional path for JSON report
        
        Returns:
            List of DRC violations
        """
        if output_path is None:
            output_path = pcb_path.with_suffix(".drc.json")
        
        cmd = [
            self.kicad_cli,
            "pcb", "drc",
            "--output", str(output_path),
            "--format", "json",
            "--severity-all",
            str(pcb_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if output_path.exists():
            return self._parse_drc_report(output_path)
        else:
            raise RuntimeError(f"DRC failed: {result.stderr}")
    
    def _parse_drc_report(self, report_path: Path) -> List[DRCViolation]:
        """Parse KiCad DRC JSON report."""
        with open(report_path) as f:
            data = json.load(f)
        
        violations = []
        for item in data.get("violations", []):
            violations.append(DRCViolation(
                severity=item.get("severity", "error"),
                rule=item.get("type", "unknown"),
                description=item.get("description", ""),
                position=tuple(item.get("pos", [0, 0])),
                items=item.get("items", []),
            ))
        
        return violations
    
    def compute_drc_penalty(self, violations: List[DRCViolation]) -> float:
        """
        Convert DRC violations to a penalty value.
        
        Errors are weighted more heavily than warnings.
        """
        penalty = 0.0
        for v in violations:
            if v.severity == "error":
                penalty += 10.0
            elif v.severity == "warning":
                penalty += 1.0
        return penalty
```

**Integration with Optimizer:**

```python
class DRCLoss:
    """
    Non-differentiable loss based on KiCad DRC.
    
    Run periodically (not every iteration) due to overhead.
    """
    
    def __init__(self, validator: KiCadDRCValidator, run_interval: int = 100):
        self.validator = validator
        self.run_interval = run_interval
        self.last_penalty = 0.0
        self.last_violations = []
    
    def __call__(self, pcb_path: Path, epoch: int) -> float:
        """
        Compute DRC penalty.
        
        Only runs actual DRC every `run_interval` epochs;
        returns cached value otherwise.
        """
        if epoch % self.run_interval == 0:
            self.last_violations = self.validator.run_drc(pcb_path)
            self.last_penalty = self.validator.compute_drc_penalty(self.last_violations)
        
        return self.last_penalty
```

### 10.3 ngspice Simulation Integration

**Purpose:** Validate electrical behavior - ensure placements don't create parasitic issues that break circuit function.

**Simulation Types:**

| Simulation | Purpose | When to Run |
|------------|---------|-------------|
| **Gate Drive Loop Inductance** | Verify EMI constraints | Every N iterations |
| **Power Integrity** | Check voltage drop on power rails | After major changes |
| **Bootstrap Charging** | Verify bootstrap circuit works | Periodically |
| **Thermal** | Estimate temperature distribution | Final validation |

**Implementation:**

```python
# src/temper_placer/validation/spice.py

import subprocess
from pathlib import Path
from typing import Dict, List
import re

@dataclass
class SimulationResult:
    """Result from ngspice simulation."""
    success: bool
    metrics: Dict[str, float]  # e.g., {"loop_inductance": 15e-9, "peak_current": 22.5}
    raw_output: str


class NgspiceValidator:
    """
    Run ngspice simulations for electrical validation.
    
    Uses placement-dependent parasitics extracted from layout.
    """
    
    def __init__(self, ngspice_path: str = "ngspice"):
        self.ngspice = ngspice_path
        self.template_dir = Path(__file__).parent / "spice_templates"
    
    def estimate_loop_inductance(
        self,
        positions: Dict[str, tuple],  # component_ref -> (x, y)
        loop_components: List[str],   # ordered list of components in loop
    ) -> float:
        """
        Estimate current loop inductance based on placement.
        
        Uses simplified model: L ≈ μ₀ * Area / (2π * trace_height)
        
        Args:
            positions: Component positions
            loop_components: Components forming the loop (ordered)
        
        Returns:
            Estimated inductance in Henries
        """
        # Calculate loop area from component positions
        area = self._calculate_loop_area(positions, loop_components)
        
        # Simplified inductance model
        # L = μ₀ * A / h where h is effective height (trace to return plane)
        mu_0 = 4 * 3.14159e-7  # H/m
        h = 0.2e-3  # 0.2mm trace height (rough estimate)
        
        inductance = mu_0 * area / h
        return inductance
    
    def run_gate_drive_simulation(
        self,
        positions: Dict[str, tuple],
        netlist_path: Path,
    ) -> SimulationResult:
        """
        Simulate gate drive circuit with placement-dependent parasitics.
        
        Extracts loop inductance from placement and adds to SPICE model.
        """
        # Estimate parasitics from placement
        gate_loop_L = self.estimate_loop_inductance(
            positions, 
            ["U_GD", "Q1", "Q2"]  # Gate driver to IGBTs
        )
        
        # Generate SPICE netlist with parasitics
        spice_content = self._generate_gate_drive_netlist(
            netlist_path,
            gate_loop_inductance=gate_loop_L,
        )
        
        # Run simulation
        return self._run_ngspice(spice_content)
    
    def run_bootstrap_simulation(
        self,
        positions: Dict[str, tuple],
    ) -> SimulationResult:
        """
        Verify bootstrap capacitor charges correctly.
        
        Checks that V_BOOT reaches sufficient voltage.
        """
        bootstrap_loop_L = self.estimate_loop_inductance(
            positions,
            ["D_BOOT", "C_BOOT", "U_GD"]
        )
        
        spice_content = self._load_template("bootstrap_charging.cir")
        spice_content = spice_content.replace(
            "{{LOOP_INDUCTANCE}}", 
            f"{bootstrap_loop_L:.2e}"
        )
        
        result = self._run_ngspice(spice_content)
        
        # Extract V_BOOT from results
        v_boot = self._extract_metric(result.raw_output, "v_boot_final")
        result.metrics["v_boot"] = v_boot
        result.success = v_boot > 12.0  # Need >12V for gate drive
        
        return result
    
    def _run_ngspice(self, netlist_content: str) -> SimulationResult:
        """Run ngspice simulation."""
        # Write temporary netlist
        temp_path = Path("/tmp/temper_placer_sim.cir")
        temp_path.write_text(netlist_content)
        
        cmd = [self.ngspice, "-b", "-o", "/tmp/sim_output.txt", str(temp_path)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        output = Path("/tmp/sim_output.txt").read_text() if Path("/tmp/sim_output.txt").exists() else result.stdout
        
        return SimulationResult(
            success=result.returncode == 0,
            metrics={},
            raw_output=output,
        )
    
    def compute_spice_penalty(self, results: List[SimulationResult]) -> float:
        """Convert simulation results to penalty."""
        penalty = 0.0
        for r in results:
            if not r.success:
                penalty += 50.0  # Heavy penalty for failed simulation
            
            # Add penalty for marginal results
            if "v_boot" in r.metrics and r.metrics["v_boot"] < 14.0:
                penalty += (14.0 - r.metrics["v_boot"]) * 5.0
        
        return penalty
```

### 10.4 Validation Schedule

Not all validations run every iteration (too slow). Instead, use a schedule:

```yaml
# configs/temper/validation.yaml

validation:
  drc:
    enabled: true
    interval: 100       # Run every 100 epochs
    penalty_weight: 10.0
    fail_on_error: false  # Continue optimization even with DRC errors
  
  spice:
    enabled: true
    interval: 200       # Run every 200 epochs
    penalty_weight: 20.0
    simulations:
      - gate_drive
      - bootstrap
    
  # Increase frequency near end of optimization
  final_phase:
    drc_interval: 20
    spice_interval: 50
```

### 10.5 Handling Non-Differentiable Losses

DRC and SPICE results are non-differentiable. Integration approaches:

**Option 1: Penalty Method (Simple)**
- Add validation penalty to total loss
- Gradient only flows through differentiable terms
- Validation penalty acts as "barrier" pushing solution toward valid region

**Option 2: Surrogate Model (Advanced)**
- Train a differentiable surrogate model that predicts DRC/SPICE results
- Update surrogate periodically with actual validation results
- Use surrogate gradient during optimization

**Option 3: Evolutionary/Hybrid (Most Robust)**
- Use gradient descent for differentiable losses
- Use evolutionary strategies (CMA-ES) for handling validation feedback
- Best of both worlds but more complex

**Recommended for v0.1:** Option 1 (Penalty Method) - simplest, works well in practice.

```python
def total_loss_with_validation(
    state: PlacementState,
    context: OptimizationContext,
    epoch: int,
    pcb_path: Path,
) -> Tuple[float, Dict[str, float]]:
    """
    Total loss including non-differentiable validation penalties.
    """
    # Differentiable losses (computed every iteration)
    diff_loss, diff_breakdown = differentiable_losses(state, context)
    
    # Non-differentiable validation (computed periodically)
    drc_penalty = context.drc_loss(pcb_path, epoch)
    spice_penalty = context.spice_loss(state, epoch)
    
    # Combine (gradients only flow through diff_loss)
    total = diff_loss + drc_penalty + spice_penalty
    
    breakdown = {
        **diff_breakdown,
        "drc_penalty": drc_penalty,
        "spice_penalty": spice_penalty,
    }
    
    return total, breakdown
```

### 10.6 Validation-Aware Training Loop

```python
def train_with_validation(
    initial_state: PlacementState,
    context: OptimizationContext,
    config: TrainingConfig,
) -> PlacementState:
    """
    Training loop with validation-in-the-loop.
    """
    state = initial_state
    optimizer = optax.adam(config.learning_rate)
    opt_state = optimizer.init(state)
    
    pcb_writer = KiCadWriter(context.template_pcb)
    drc_validator = KiCadDRCValidator()
    spice_validator = NgspiceValidator()
    
    for epoch in range(config.total_epochs):
        # Compute differentiable loss and gradients
        (loss, breakdown), grads = jax.value_and_grad(
            differentiable_losses, has_aux=True
        )(state, context)
        
        # Apply gradient update
        updates, opt_state = optimizer.update(grads, opt_state)
        state = optax.apply_updates(state, updates)
        
        # Periodic validation
        if epoch % config.drc_interval == 0:
            # Export current placement to PCB
            pcb_path = pcb_writer.write_temp(state)
            
            # Run DRC
            violations = drc_validator.run_drc(pcb_path)
            drc_penalty = drc_validator.compute_drc_penalty(violations)
            
            # Log violations
            if violations:
                logger.warning(f"Epoch {epoch}: {len(violations)} DRC violations")
        
        if epoch % config.spice_interval == 0:
            # Run SPICE simulations
            positions = state_to_positions_dict(state, context.netlist)
            
            bootstrap_result = spice_validator.run_bootstrap_simulation(positions)
            if not bootstrap_result.success:
                logger.warning(f"Epoch {epoch}: Bootstrap simulation failed")
        
        # Early stopping on perfect validation
        if drc_penalty == 0 and spice_penalty == 0 and loss < config.convergence_threshold:
            logger.info(f"Converged at epoch {epoch}")
            break
    
    return state
```

---

## 11. Optimizer Robustness Features

To resolve local minima and "Overlap Deadlocks," the following advanced optimization strategies are implemented:

### 11.1 Soft-Body Component Inflation

**Concept**: Components start as small points and "inflate" to their true physical dimensions over time.

**Implementation**:
- Add `inflation_ramp` parameter to `OverlapLoss`.
- Ramp the effective component size from a fraction (e.g., 0.3) to 1.0 over the first 30% of training.
- **Benefit**: Allows components to "glide" through each other early in training to reach their assigned zones, avoiding early entanglement.

### 11.2 Adaptive Per-Component Loss Weighting

**Concept**: Dynamically increase the repulsion force for specific components that remain stuck in overlaps.

**Implementation**:
- Maintain a weight vector $W \in \mathbb{R}^N$ initialized to 1.0.
- Every iteration, if component $i$ has an overlap violation $> \epsilon$:
  $W_i \leftarrow W_i \times (1 + \text{rate})$
- Use $W_i$ to scale the overlap gradient for component $i$.
- **Benefit**: Breaks symmetric deadlocks where `WirelengthLoss` and `OverlapLoss` gradients cancel out.

### 11.3 Stochastic Perturbation (Jiggle)

**Concept**: Inject "thermal energy" into the system when optimization stalls.

**Implementation**:
- Monitor the Exponential Moving Average (EMA) of component displacement.
- If $\text{EMA} < \text{threshold}$ AND constraints are still violated:
  $\text{pos} \leftarrow \text{pos} + \mathcal{N}(0, \sigma)$
- **Benefit**: Provides a mechanism to jump out of narrow local minima that gradient descent cannot escape.

---

## 12. Future Extensions

1. **Global Routing:** Add Steiner tree estimation for better congestion modeling
2. **Detailed Routing:** Integrate with FreeRouting or custom maze router
3. **Learning from Examples:** Train cost function weights from human-placed boards
4. **Multi-board Optimization:** Panelization, assembly optimization
5. **Thermal Simulation:** Integrate FEM thermal solver into loss function
6. **3D Clearance:** Height-aware placement for stacked components

---

## 13. Dependencies

```toml
# pyproject.toml

[project]
name = "temper-placer"
version = "0.1.0"
requires-python = ">=3.10"

dependencies = [
    "jax>=0.4.20",
    "jaxlib>=0.4.20",
    "optax>=0.1.7",
    "kiutils>=1.4.0",
    "numpy>=1.24.0",
    "pyyaml>=6.0",
    "plotly>=5.18.0",
    "websockets>=12.0",
    "click>=8.1.0",
    "rich>=13.0.0",  # For CLI output
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",
    "mypy>=1.7.0",
]
```

---

## 14. Glossary

| Term | Definition |
|------|------------|
| **HPWL** | Half-Perimeter Wire Length - sum of bounding box half-perimeters |
| **SDF** | Signed Distance Function - distance to shape boundary (negative = inside) |
| **Gumbel-Softmax** | Technique for differentiable sampling from categorical distribution |
| **Congestion** | Routing demand vs. supply ratio in a region |
| **Creepage** | Shortest distance along surface between conductors |
| **Clearance** | Shortest distance through air between conductors |

---

**END OF DESIGN DOCUMENT**
