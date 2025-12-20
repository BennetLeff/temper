# Placement Constraint Language (PCL) Reference Guide

**Version:** 1.0  
**Date:** 2025-12-19  
**Project:** temper-placer

---

## Table of Contents

1. [Introduction](#introduction)
2. [Quick Start](#quick-start)
3. [Constraint Types](#constraint-types)
4. [Tier System](#tier-system)
5. [The 'because' Field](#the-because-field)
6. [Zones](#zones)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)
9. [CLI Commands](#cli-commands)
10. [Python API](#python-api)

---

## Introduction

### What is PCL?

The **Placement Constraint Language (PCL)** is a declarative YAML-based language for expressing component placement requirements. It bridges the gap between human design intent and automated placement optimization.

PCL constraints are:
- **Declarative:** Say WHAT you need, not HOW to achieve it
- **Auditable:** Every constraint requires a 'because' field explaining WHY
- **Tiered:** Balance competing requirements with priority tiers
- **Physics-based:** Express electrical, thermal, and mechanical requirements

### Why Constraint-Based Placement?

Traditional PCB layout is manual and time-consuming. Automated placement without constraints produces sub-optimal results (poor loop areas, thermal issues, manufacturability problems).

PCL lets you encode domain expertise as constraints that guide the optimizer:
- **Electrical:** Loop areas, adjacency, isolation
- **Thermal:** Heat dissipation, temperature-sensitive components
- **Mechanical:** Connector placement, mounting requirements
- **Safety:** Creepage, clearance, isolation barriers

The optimizer then finds placements that satisfy these constraints while minimizing wirelength and overlap.

---

## Quick Start

### Minimal Example

```yaml
version: "1.0"

constraints:
  - type: adjacent
    a: U1
    b: C1
    max_distance_mm: 5
    tier: 1
    because: "Decoupling capacitor must be within 5mm of IC for effective high-frequency filtering"
```

### Running the Optimizer

```bash
# Optimize with constraints
temper-placer optimize input.kicad_pcb \
    -c constraints.yaml \
    -o output.kicad_pcb

# Validate constraints first
temper-placer pcl lint constraints.yaml

# Check for linting errors
temper-placer pcl validate constraints.yaml --netlist input.kicad_pcb
```

---

## Constraint Types

### 1. Adjacent Constraint

**Purpose:** Keep two components close together.

**Syntax:**
```yaml
- type: adjacent
  a: <component_ref>
  b: <component_ref>
  max_distance_mm: <float>
  metric: edge_to_edge | center_to_center | pin_to_pin  # optional
  pin_a: <pin_name>  # optional, for pin_to_pin
  pin_b: <pin_name>  # optional, for pin_to_pin
  tier: 1 | 2 | 3
  because: "<rationale>"
  id: "<unique_id>"  # optional
```

**Parameters:**
| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `a` | Yes | - | First component reference (e.g., "U1") |
| `b` | Yes | - | Second component reference |
| `max_distance_mm` | Yes | - | Maximum allowed distance in mm |
| `metric` | No | `edge_to_edge` | How to measure distance |
| `pin_a` | No | - | Specific pin on component A (for pin_to_pin) |
| `pin_b` | No | - | Specific pin on component B (for pin_to_pin) |
| `tier` | Yes | - | Priority (1=HARD, 2=STRONG, 3=SOFT) |
| `because` | Yes | - | Rationale (≥10 characters) |

**Examples:**

```yaml
# Half-bridge IGBTs
- type: adjacent
  a: Q1
  b: Q2
  max_distance_mm: 10
  metric: edge_to_edge
  tier: 1
  because: "IGBTs share heatsink and must minimize commutation loop area for low EMI"

# Decoupling capacitor (pin-to-pin)
- type: adjacent
  a: U1
  b: C1
  max_distance_mm: 3
  metric: pin_to_pin
  pin_a: VCC
  pin_b: "+"
  tier: 1
  because: "VCC decoupling must be immediate for stable power supply and noise rejection"

# Aesthetic alignment (soft constraint)
- type: adjacent
  a: LED1
  b: LED2
  max_distance_mm: 10
  metric: center_to_center
  tier: 3
  because: "LEDs equally spaced for aesthetic appearance on front panel"
```

**Use Cases:**
- Power stage components (minimize loop inductance)
- Decoupling capacitors
- Crystal oscillators near MCU
- Differential pairs
- Aesthetic grouping

---

### 2. Separated Constraint

**Purpose:** Keep components or zones apart.

**Syntax:**
```yaml
- type: separated
  a: <component_or_zone_ref>
  b: <component_or_zone_ref>
  min_distance_mm: <float>
  metric: edge_to_edge | center_to_center  # optional
  tier: 1 | 2 | 3
  because: "<rationale>"
```

**Parameters:**
| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `a` | Yes | - | First component/zone reference |
| `b` | Yes | - | Second component/zone reference |
| `min_distance_mm` | Yes | - | Minimum required distance in mm |
| `metric` | No | `edge_to_edge` | How to measure distance |
| `tier` | Yes | - | Priority (1=HARD, 2=STRONG, 3=SOFT) |
| `because` | Yes | - | Rationale (≥10 characters) |

**Examples:**

```yaml
# Safety isolation (IEC 60335-1)
- type: separated
  a: HV_ZONE
  b: LV_ZONE
  min_distance_mm: 10.0
  tier: 1
  because: "IEC 60335-1 requires 10mm reinforced isolation at 400V working voltage"

# Thermal isolation
- type: separated
  a: Q1  # IGBT
  b: U_RTD  # RTD interface IC
  min_distance_mm: 40
  tier: 2
  because: "IGBT heat (>30W) affects RTD accuracy. 40mm needed for <1°C error"

# EMI isolation
- type: separated
  a: U_GATE  # Gate driver
  b: U_MCU
  min_distance_mm: 20
  tier: 2
  because: "Gate driver output edges (50V/ns) can couple into MCU signals"
```

**Use Cases:**
- Safety isolation (reinforced/basic)
- Thermal management
- EMI/noise isolation
- Keep high-voltage away from low-voltage
- Antenna keepouts

---

### 3. Enclosing Constraint

**Purpose:** Require components to be inside a zone.

**Syntax:**
```yaml
- type: enclosing
  outer: <zone_name>
  inner: [<component_ref>, ...]
  margin_mm: <float>  # optional
  tier: 1 | 2 | 3
  because: "<rationale>"
```

**Parameters:**
| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `outer` | Yes | - | Zone name (defined in `zones` section) |
| `inner` | Yes | - | List of component references |
| `margin_mm` | No | 0.0 | Minimum margin from zone boundary |
| `tier` | Yes | - | Priority (1=HARD, 2=STRONG, 3=SOFT) |
| `because` | Yes | - | Rationale (≥10 characters) |

**Examples:**

```yaml
# High-voltage zone containment
- type: enclosing
  outer: HV_ZONE
  inner: [Q1, Q2, C_BUS1, C_BUS2, J_AC]
  margin_mm: 2.0
  tier: 1
  because: "All high-voltage components must stay within HV zone for safety isolation"

# Power plane enclosure
- type: enclosing
  outer: PGND_PLANE
  inner: [Q1, Q2, C_BUS1, C_BUS2]
  tier: 2
  because: "Power components need solid ground reference plane for low impedance return"

# Manufacturing keep-out
- type: enclosing
  outer: BOARD_OUTLINE
  inner: [U1, U2, U3, C1, C2, R1, R2]
  margin_mm: 3.0
  tier: 1
  because: "All components must be 3mm from board edge for panel routing clearance"
```

**Use Cases:**
- Zone-based design (HV/LV separation)
- Manufacturing keepouts
- PCB outline constraints
- Thermal zones
- Shielded regions

---

### 4. Aligned Constraint

**Purpose:** Align components along an axis.

**Syntax:**
```yaml
- type: aligned
  components: [<component_ref>, ...]
  axis: x | y | horizontal | vertical
  tolerance_mm: <float>  # optional
  tier: 1 | 2 | 3
  because: "<rationale>"
```

**Parameters:**
| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `components` | Yes | - | List of components (≥2) to align |
| `axis` | Yes | - | Alignment axis (x, y, horizontal, vertical) |
| `tolerance_mm` | No | 0.5 | Alignment tolerance |
| `tier` | Yes | - | Priority (1=HARD, 2=STRONG, 3=SOFT) |
| `because` | Yes | - | Rationale (≥10 characters) |

**Examples:**

```yaml
# Connector alignment
- type: aligned
  components: [J1, J2, J3]
  axis: horizontal
  tolerance_mm: 1.0
  tier: 2
  because: "Connectors aligned horizontally for clean appearance and consistent cable routing"

# Decoupling capacitors
- type: aligned
  components: [C_DEC1, C_DEC2, C_DEC3, C_DEC4]
  axis: y
  tolerance_mm: 0.5
  tier: 3
  because: "Decoupling caps aligned vertically for aesthetic appearance and uniform current distribution"

# Bus capacitors (structural)
- type: aligned
  components: [C_BUS1, C_BUS2]
  axis: horizontal
  tier: 2
  because: "Bus caps aligned for symmetrical current paths and shared thermal management"
```

**Use Cases:**
- Aesthetic alignment
- Connector banks
- LED arrays
- Symmetrical power distribution
- Manufacturing ease

---

### 5. OnSide Constraint

**Purpose:** Place components on a board edge.

**Syntax:**
```yaml
- type: on_side
  components: [<component_ref>, ...]
  side: top | bottom | left | right
  edge: flush | near | overhang  # optional
  max_distance_from_edge_mm: <float>  # optional, for edge=near
  tier: 1 | 2 | 3
  because: "<rationale>"
```

**Parameters:**
| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `components` | Yes | - | List of components to place on edge |
| `side` | Yes | - | Board side (top, bottom, left, right) |
| `edge` | No | `near` | How component relates to edge |
| `max_distance_from_edge_mm` | No | 5.0 | Max distance for `edge=near` |
| `tier` | Yes | - | Priority (1=HARD, 2=STRONG, 3=SOFT) |
| `because` | Yes | - | Rationale (≥10 characters) |

**Edge Types:**
- **`flush`:** Component must be flush against board edge
- **`near`:** Component within `max_distance_from_edge_mm` of edge
- **`overhang`:** Component can overhang edge (connectors)

**Examples:**

```yaml
# TO-247 heatsink mounting
- type: on_side
  components: [Q1, Q2]
  side: top
  edge: flush
  tier: 1
  because: "TO-247 packages require board edge mounting for external heatsink access"

# Connectors
- type: on_side
  components: [J_AC, J_COIL]
  side: top
  edge: overhang
  tier: 1
  because: "AC input and coil output connectors at top edge for enclosure access"

# Debug header
- type: on_side
  components: [J_DEBUG]
  side: bottom
  edge: near
  max_distance_from_edge_mm: 10
  tier: 3
  because: "Debug connector near bottom edge for development access without obstructing power"
```

**Use Cases:**
- Heatsink-mounted components (TO-247, TO-220)
- Connectors (must be accessible)
- Edge-mount LEDs
- Test points
- Mounting holes

---

### 6. Anchored Constraint

**Purpose:** Fix component at specific location or within region.

**Syntax:**

```yaml
# Option 1: Anchor to region
- type: anchored
  component: <component_ref>
  region: <zone_name>
  tier: 1 | 2 | 3
  because: "<rationale>"

# Option 2: Anchor to absolute position
- type: anchored
  component: <component_ref>
  position: [<x_mm>, <y_mm>]
  tier: 1 | 2 | 3
  because: "<rationale>"
```

**Parameters:**
| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `component` | Yes | - | Component reference |
| `region` | Conditional | - | Zone name (use region OR position) |
| `position` | Conditional | - | [x, y] in mm (use region OR position) |
| `tier` | Yes | - | Priority (1=HARD, 2=STRONG, 3=SOFT) |
| `because` | Yes | - | Rationale (≥10 characters) |

**Examples:**

```yaml
# MCU centered for antenna
- type: anchored
  component: U_MCU
  region: CENTER_ZONE
  tier: 2
  because: "MCU centered in PCB for symmetrical antenna clearance and balanced layout"

# Fixed mounting position
- type: anchored
  component: J1
  position: [60.0, 5.0]
  tier: 1
  because: "Connector must align with enclosure cutout at (60mm, 5mm) for mechanical fit"

# Reference designator anchor
- type: anchored
  component: U_REF
  region: PRECISION_ZONE
  tier: 1
  because: "Voltage reference in precision zone away from switching noise for accurate ADC"
```

**Use Cases:**
- Mechanical alignment (connectors, mounting holes)
- Antenna clearance
- MCU centered for balanced layout
- Reference components in quiet zones
- User interface elements (buttons, LEDs)

---

### 7. LoopArea Constraint

**Purpose:** Limit current loop area for EMI control.

**Syntax:**
```yaml
- type: loop_area
  loop_name: <string>
  max_area_mm2: <float>
  tier: 1 | 2 | 3
  because: "<rationale>"
```

**Parameters:**
| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `loop_name` | Yes | - | Name of current loop |
| `max_area_mm2` | Yes | - | Maximum loop area in mm² |
| `tier` | Yes | - | Priority (1=HARD, 2=STRONG, 3=SOFT) |
| `because` | Yes | - | Rationale (≥10 characters) |

**Examples:**

```yaml
# Commutation loop
- type: loop_area
  loop_name: commutation_loop
  max_area_mm2: 500
  tier: 1
  because: "Commutation loop EMI scales with area. 500mm² max for acceptable radiated EMI at 25kHz"

# Gate drive loops
- type: loop_area
  loop_name: gate_drive_high
  max_area_mm2: 100
  tier: 1
  because: "Gate drive loop affects switching speed and noise immunity. <100mm² for clean switching"

# Bootstrap loop
- type: loop_area
  loop_name: bootstrap_loop
  max_area_mm2: 50
  tier: 2
  because: "Bootstrap charging loop should be tight for fast high-side supply charging"
```

**Use Cases:**
- Power electronics (commutation loops)
- Gate drive circuits
- Switching regulators
- High-frequency loops (>100kHz)
- EMI-critical designs

**Note:** Loop definitions are specified separately in loop configuration files. See Epic 1 (Loop-Centric Data Model) for loop definition syntax.

---

## Tier System

PCL uses a three-tier priority system to balance competing requirements.

### Tier Definitions

| Tier | Name | Weight | Behavior | Use For |
|------|------|--------|----------|---------|
| **1** | HARD | 1e6 | Never violate. Optimizer fails if impossible. | Safety, compliance, critical electrical |
| **2** | STRONG | 1e3 | Heavy penalty. Can escalate to HARD. | Performance, EMI, thermal |
| **3** | SOFT | 1e1 | Light penalty. Preference only. | Aesthetics, conventions, nice-to-have |

### Tier Selection Guidelines

**Use Tier 1 (HARD) for:**
- Safety requirements (IEC, UL, CE)
- Creepage/clearance minimums
- Critical loop areas (<500mm²)
- Mechanical fit (connectors, mounting)
- Absolute electrical requirements

**Use Tier 2 (STRONG) for:**
- EMI performance
- Thermal management
- Signal integrity
- Power distribution
- Most electrical constraints

**Use Tier 3 (SOFT) for:**
- Aesthetic alignment
- Organizational preferences
- Nice-to-have spacing
- Convention (left-to-right flow)
- Manufacturing ease (but not DFM rules)

### Penalty Calculation

Constraints translate to quadratic penalties:

```
penalty = weight × (violation²)
```

Where weight depends on tier:
- HARD: 1e6 (effectively infinite)
- STRONG: 1e3
- SOFT: 1e1

This creates smooth gradients for optimization while strongly discouraging violations.

### Escalation

Constraints can **escalate** to higher tiers during optimization:

**Severity-based escalation:**
- SOFT → STRONG if violation > 5mm
- STRONG → HARD if violation > 2mm

**Persistence-based escalation:**
- Escalate if violated for 5+ consecutive iterations

Escalated constraints get **2× penalty multiplier** and print warnings.

**Example escalation:**
```
Constraint c1 escalated to STRONG (reason: SEVERITY)
  Original: SOFT (weight=10)
  Current: STRONG (weight=1000, escalated_multiplier=2x)
  Effective weight: 2000
```

---

## The 'because' Field

### Why Mandatory?

Every constraint **MUST** include a `because` field (≥10 characters) explaining WHY the constraint exists.

**Benefits:**
1. **Explainability:** Future you/others understand the rationale
2. **Auditability:** Design review can verify reasoning
3. **Maintenance:** Easy to update when requirements change
4. **Documentation:** Constraints self-document the design

### Good vs Bad Rationales

**❌ Bad (too vague):**
```yaml
because: "Should be close"  # Why? How close? What breaks if not?
because: "For EMI"  # Which EMI mechanism? What frequency?
because: "Safety"  # Which standard? What voltage?
```

**✅ Good (specific, actionable):**
```yaml
because: "Commutation loop EMI scales with area. 500mm² max for EN 55011 Class B at 25kHz switching"
because: "IEC 60335-1 Table 16 requires 10mm reinforced isolation at 400V working voltage"
because: "Decoupling cap must be <3mm from VCC pin for effective >10MHz filtering per datasheet"
because: "TO-247 package requires board edge mounting for external heatsink access and thermal management"
```

### Formula for Good Rationale

```
because: "<physical_reason> + <quantitative_requirement> + <consequence or standard>"
```

**Examples:**
```yaml
# Physical + Quantitative + Standard
because: "Electrolytic lifetime halves every 10°C. Keep >15mm from IGBT to stay <85°C ambient for 10-year life"

# Physical + Quantitative + Consequence
because: "Gate drive loop inductance >10nH causes ringing. <100mm² area keeps L<5nH for clean switching"

# Quantitative + Standard + Consequence
because: "IEC 60335-1 requires 8mm working voltage clearance. 10mm used for 25% safety margin"
```

---

## Zones

Zones define regions on the PCB for component placement and isolation.

### Defining Zones

```yaml
zones:
  - name: HV_ZONE
    type: hv | lv | keepout | placement | thermal
    description: "Human-readable description"
    polygon: [[x1, y1], [x2, y2], [x3, y3], ...]  # mm coordinates
```

**Zone Types:**
- **`hv`:** High-voltage region (>50V)
- **`lv`:** Low-voltage region (<50V)
- **`keepout`:** No components allowed (isolation barrier)
- **`placement`:** General placement region
- **`thermal`:** Thermal management zone

### Example Zone Definition

```yaml
zones:
  - name: HV_ZONE
    type: hv
    description: "High-voltage power stage (IGBTs, gate driver, DC bus)"
    polygon: [[0, 0], [60, 0], [60, 80], [0, 80]]
    
  - name: MCU_ZONE
    type: lv
    description: "Microcontroller and low-voltage control circuits"
    polygon: [[70, 0], [120, 0], [120, 80], [70, 80]]
  
  - name: ISOLATION_BARRIER
    type: keepout
    description: "10mm isolation barrier between HV and LV zones"
    polygon: [[60, 0], [70, 0], [70, 80], [60, 80]]
```

### Using Zones in Constraints

```yaml
# Separation between zones
- type: separated
  a: HV_ZONE
  b: MCU_ZONE
  min_distance_mm: 10.0
  tier: 1
  because: "IEC 60335-1 reinforced isolation requirement"

# Containment within zone
- type: enclosing
  outer: HV_ZONE
  inner: [Q1, Q2, C_BUS1, C_BUS2]
  tier: 1
  because: "All high-voltage components must stay in HV zone for safety"
```

---

## Best Practices

### 1. Start with Physics-Based Constraints

**Order of importance:**
1. **Safety** (isolation, clearance) → Tier 1
2. **Electrical** (loop areas, adjacency) → Tier 1-2
3. **Thermal** (heat dissipation, derating) → Tier 2
4. **Mechanical** (connectors, mounting) → Tier 1-2
5. **Aesthetic** (alignment, grouping) → Tier 3

**Why:** Physics-based constraints are non-negotiable. Add aesthetic constraints only after electrical requirements are satisfied.

### 2. Use Tier 1 Sparingly

Too many HARD constraints make the problem unsatisfiable. Reserve Tier 1 for:
- Safety/compliance
- Critical electrical (loop areas <500mm²)
- Mechanical fit

Most constraints should be Tier 2 (STRONG).

### 3. Test Incrementally

Add constraints gradually and test after each addition:

```bash
# Start with critical constraints
temper-placer optimize input.kicad_pcb -c critical_only.yaml -o test1.kicad_pcb

# Add more constraints
temper-placer optimize input.kicad_pcb -c critical_plus_thermal.yaml -o test2.kicad_pcb

# Full constraint set
temper-placer optimize input.kicad_pcb -c complete.yaml -o final.kicad_pcb
```

This helps identify which constraint causes infeasibility.

### 4. Use the Linter

Always run the linter before optimization:

```bash
temper-placer pcl lint constraints.yaml
```

Catches:
- Contradictions (adjacent + separated)
- Circular dependencies
- Invalid component references
- Unreasonable distances

### 5. Document Zone Rationale

Zones should have clear descriptions:

```yaml
zones:
  - name: HV_ZONE
    type: hv
    description: "High-voltage (>50V). IEC 60335-1 isolation required. Contains power stage."
    polygon: [[0, 0], [60, 0], [60, 80], [0, 80]]
```

### 6. Prefer Component Patterns Over Hardcoded References

**❌ Bad (hardcoded):**
```yaml
constraints:
  - type: adjacent
    a: C1
    b: U1
    # ...
  - type: adjacent
    a: C2
    b: U2
    # ...
```

**✅ Good (pattern or programmatic):**
Use scripting to generate constraints or naming conventions (e.g., `C_DEC*` for decoupling caps).

### 7. Version Control Your Constraint Files

Constraints are code. Use git to track changes:

```bash
git add constraints/
git commit -m "feat(constraints): add thermal isolation for IGBTs"
```

### 8. Start from Templates

Use pre-built constraint sets as starting points:
- `half_bridge_base.yaml`
- `safety_isolation.yaml`
- `thermal_management.yaml`

Customize for your specific design.

---

## Troubleshooting

### Common Errors

#### 1. "oldString not found in content"
**Cause:** Typo in component reference or component doesn't exist in netlist.

**Fix:**
```bash
# Check component exists
temper-placer netlist list input.kicad_pcb | grep Q1

# Fix typo in constraint file
# a: Q1  # wrong
  a: Q1  # correct
```

#### 2. "Constraint c1 and c2 contradict each other"
**Cause:** Adjacent + Separated constraints conflict.

**Example:**
```yaml
- type: adjacent
  a: Q1
  b: Q2
  max_distance_mm: 5  # Q1-Q2 must be <5mm
  
- type: separated
  a: Q1
  b: Q2
  min_distance_mm: 20  # Q1-Q2 must be >20mm ← CONTRADICTION
```

**Fix:** Remove one constraint or adjust distances to be compatible.

#### 3. "Circular adjacency detected: Q1 → Q2 → Q3 → Q1"
**Cause:** Circular chain of adjacency constraints.

**Warning:** This is a *warning*, not an error. Circular adjacencies can sometimes be satisfied geometrically (triangle arrangement).

**Fix:** Review if all adjacencies are necessary. Consider relaxing some to Tier 3 (SOFT).

#### 4. "Hard constraint c1 violated (violation=5.2mm)"
**Cause:** Tier 1 constraint cannot be satisfied.

**Fix:**
1. Relax constraint (increase max_distance or decrease min_distance)
2. Downgrade to Tier 2 (STRONG)
3. Remove constraint if not actually critical
4. Check if board size is too small

#### 5. "Component ref 'HV_ZONE' not found in netlist"
**Cause:** Using zone name where component reference expected.

**Fix:**
```yaml
# ❌ Wrong
- type: adjacent
  a: HV_ZONE  # Zone, not component
  b: Q1

# ✅ Correct
- type: separated
  a: HV_ZONE  # Zones use separated
  b: MCU_ZONE
```

### Performance Tips

#### Slow Optimization

**Symptoms:**
- Optimization takes >10 minutes
- Many escalations printed
- Loss plateaus without improvement

**Causes:**
- Too many constraints
- Over-constrained problem
- Conflicting constraints

**Fixes:**
1. **Reduce constraints:** Start with critical only
2. **Relax tiers:** Change some Tier 1 → Tier 2
3. **Increase epochs:** Add `--epochs 10000`
4. **Check linter:** `temper-placer pcl lint constraints.yaml`

#### Unsatisfiable Constraints

**Symptoms:**
- Optimizer fails immediately
- "Hard constraint violated" errors
- All placements have huge loss

**Debugging workflow:**
```bash
# 1. Lint for contradictions
temper-placer pcl lint constraints.yaml

# 2. Check component references
temper-placer pcl validate constraints.yaml --netlist input.kicad_pcb

# 3. Try with only Tier 1 constraints
temper-placer optimize input.kicad_pcb \
    --constraint-tier 1 \
    -c constraints.yaml \
    -o test.kicad_pcb

# 4. Add constraints incrementally
# Remove 50% of constraints, test, binary search
```

### Debugging Tips

**Enable verbose logging:**
```bash
temper-placer optimize input.kicad_pcb \
    -c constraints.yaml \
    --verbose \
    -o output.kicad_pcb
```

**Check constraint violations:**
```bash
# After optimization, view constraint report
temper-placer report output.kicad_pcb \
    -c constraints.yaml \
    --format markdown > report.md
```

**Visualize placement:**
```bash
# Enable live visualization
temper-placer optimize input.kicad_pcb \
    -c constraints.yaml \
    --visualize \
    -o output.kicad_pcb
```

---

## CLI Commands

### Optimization

```bash
# Basic optimization
temper-placer optimize input.kicad_pcb -c constraints.yaml -o output.kicad_pcb

# With visualization
temper-placer optimize input.kicad_pcb -c constraints.yaml --visualize -o output.kicad_pcb

# Specify epochs
temper-placer optimize input.kicad_pcb -c constraints.yaml --epochs 8000 -o output.kicad_pcb

# Reproducible (fixed seed)
temper-placer optimize input.kicad_pcb -c constraints.yaml --seed 42 -o output.kicad_pcb
```

### Validation

```bash
# Lint constraint file (check for contradictions)
temper-placer pcl lint constraints.yaml

# Validate component references against netlist
temper-placer pcl validate constraints.yaml --netlist input.kicad_pcb

# Dry-run (check satisfiability without optimization)
temper-placer validate input.kicad_pcb -c constraints.yaml
```

### Reporting

```bash
# Generate constraint report
temper-placer report output.kicad_pcb -c constraints.yaml

# Export violations to JSON
temper-placer report output.kicad_pcb -c constraints.yaml --format json > violations.json
```

---

## Python API

### Loading Constraints

```python
from temper_placer.pcl import parse_pcl_file, ConstraintCollection

# Load from file
collection = parse_pcl_file("constraints.yaml")

# Access constraints
print(f"Total constraints: {len(collection.constraints)}")
print(f"Hard constraints: {len(collection.by_tier(1))}")

# Filter by type
adjacent_constraints = collection.by_type("adjacent")
```

### Creating Constraints Programmatically

```python
from temper_placer.pcl import (
    AdjacentConstraint,
    SeparatedConstraint,
    ConstraintTier,
    DistanceMetric,
)

# Create constraint
constraint = AdjacentConstraint(
    a="Q1",
    b="Q2",
    max_distance_mm=10.0,
    metric=DistanceMetric.EDGE_TO_EDGE,
    tier=ConstraintTier.HARD,
    because="IGBTs share heatsink and must minimize commutation loop",
)

# Check involvement
if constraint.involves_component("Q1"):
    print("Q1 is constrained")
```

### Converting to Loss Functions

```python
from temper_placer.pcl.loss_bridge import constraint_to_loss
from temper_placer.core import Netlist

# Load netlist
netlist = Netlist.from_kicad_pcb("input.kicad_pcb")

# Convert constraint to loss
loss_fn = constraint_to_loss(constraint, netlist, board=None)

# Use in optimizer
from temper_placer.losses import LossContext
context = LossContext(...)
loss_result = loss_fn(positions, rotations, context, epoch=0)
```

### Tier Management

```python
from temper_placer.pcl.tiers import (
    TieredConstraintManager,
    EscalationConfig,
)

# Create manager
config = EscalationConfig(
    severity_thresholds={ConstraintTier.SOFT: 5.0, ConstraintTier.STRONG: 2.0},
    persistence_window=5,
)

manager = TieredConstraintManager(collection.constraints, config)

# During optimization loop
violations = {"c1": 2.5, "c2": 7.0}  # Computed violations
manager.update(violations)  # Check for escalations

# Get current penalty weights
weights = manager.get_penalty_weights()
print(f"Constraint c1 weight: {weights['c1']}")
```

### Linting

```python
from temper_placer.pcl.linter import lint_constraints
from temper_placer.core import Netlist, Board

netlist = Netlist.from_kicad_pcb("input.kicad_pcb")
board = Board(width=120, height=80, zones=[], keepout_regions=[])

result = lint_constraints(collection.constraints, netlist, board)

if not result.passed:
    print("Linting failed!")
    for error in result.errors:
        print(f"  ERROR: {error}")
    for warning in result.warnings:
        print(f"  WARNING: {warning}")
```

---

## Appendix: Complete Example

### Full Constraint File

```yaml
version: "1.0"

metadata:
  name: "Half-Bridge Example"
  project: "example_converter"
  author: "PCL User"
  date: "2025-12-19"

zones:
  - name: POWER_ZONE
    type: hv
    description: "High-voltage power stage"
    polygon: [[0, 0], [50, 0], [50, 60], [0, 60]]
    
  - name: CONTROL_ZONE
    type: lv
    description: "Microcontroller and control"
    polygon: [[60, 0], [100, 0], [100, 60], [60, 60]]

constraints:
  # Critical loop areas
  - type: loop_area
    loop_name: commutation_loop
    max_area_mm2: 500
    tier: 1
    because: "Commutation loop EMI scales with area. 500mm² max for EN 55011 Class B compliance at 25kHz switching"

  # Power stage adjacency
  - type: adjacent
    a: Q1
    b: Q2
    max_distance_mm: 10
    metric: edge_to_edge
    tier: 1
    because: "IGBTs share heatsink and must minimize commutation loop inductance for low overshoot"

  - type: adjacent
    a: U_GATE
    b: Q1
    max_distance_mm: 15
    tier: 1
    because: "Gate driver to IGBT distance affects gate drive loop inductance and switching speed"

  # Decoupling
  - type: adjacent
    a: U_GATE
    b: C_VCC
    max_distance_mm: 3
    pin_a: VCC
    metric: pin_to_pin
    tier: 1
    because: "Gate driver VCC decoupling must be <3mm for effective >10MHz noise filtering per datasheet"

  # Safety isolation
  - type: separated
    a: POWER_ZONE
    b: CONTROL_ZONE
    min_distance_mm: 10.0
    tier: 1
    because: "IEC 60335-1 Table 16 requires 10mm reinforced isolation at 400V working voltage for consumer equipment"

  # Thermal
  - type: on_side
    components: [Q1, Q2]
    side: top
    edge: flush
    tier: 1
    because: "TO-247 packages require board edge mounting for external heatsink thermal management"

  - type: separated
    a: Q1
    b: U_MCU
    min_distance_mm: 30
    tier: 2
    because: "IGBT heat (>30W dissipation) and switching noise require isolation from MCU for reliable operation"

  # Zone containment
  - type: enclosing
    outer: POWER_ZONE
    inner: [Q1, Q2, U_GATE, C_BUS1, C_BUS2]
    tier: 1
    because: "All high-voltage power components must stay within designated power zone for safety isolation"

  # Aesthetic
  - type: aligned
    components: [C_BUS1, C_BUS2]
    axis: horizontal
    tolerance_mm: 1.0
    tier: 3
    because: "Bus capacitors aligned horizontally for clean appearance and symmetrical current distribution"
```

---

## Further Reading

- **Epic 1:** Loop-Centric Data Model (loop definitions)
- **Epic 3:** Topological Placement Phase (constraint satisfiability)
- **Loss Functions:** `src/temper_placer/losses/` (implementation details)
- **Pre-built Templates:** `configs/constraints/` (half-bridge, safety, thermal)

---

**Version:** 1.0  
**Last Updated:** 2025-12-19  
**Project:** temper-placer  
**License:** See project LICENSE file
