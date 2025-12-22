# PCL (Placement Constraint Language) Reference Guide

## Overview
The Placement Constraint Language (PCL) is a YAML-based DSL used by `temper-placer` to define topological and geometric relationships between components on a PCB. PCL moves beyond simple net-based optimization by allowing engineers to express physical intent, safety requirements, and structural patterns.

## Constraint Tiers
PCL uses a three-tier priority system to guide the optimizer:

| Tier | Name | Behavior |
|------|------|----------|
| **1** | **Hard** | Must be satisfied. Failure to satisfy blocks final placement. |
| **2** | **Strong** | Heavy penalty. The optimizer will prioritize these over wirelength. |
| **3** | **Soft** | Optimization target. Used for aesthetics and non-critical preferences. |

---

## Core Constraint Types

### 1. Adjacent
Keep two components within a specified distance of each other.

**Syntax:**
```yaml
- type: adjacent
  a: <component_ref>
  b: <component_ref>
  max_distance_mm: <float>
  metric: edge_to_edge | center_to_center | pin_to_pin  # Optional, default: edge_to_edge
  tier: 1 | 2 | 3
  because: "Rationale for the constraint"
```

**Example:**
```yaml
- type: adjacent
  a: Q1
  b: U_GATE
  max_distance_mm: 15
  tier: 1
  because: "Minimize gate drive loop inductance"
```

### 2. Separated
Ensure a minimum distance between components or zones.

**Syntax:**
```yaml
- type: separated
  a: <ref_or_zone>
  b: <ref_or_zone>
  min_distance_mm: <float>
  tier: 1 | 2 | 3
  because: "Rationale for the constraint"
```

**Example:**
```yaml
- type: separated
  a: HV_ZONE
  b: MCU_ZONE
  min_distance_mm: 10
  tier: 1
  because: "Reinforced isolation per IEC 60335-1"
```

### 3. Enclosing
Force components to stay within a defined zone.

**Syntax:**
```yaml
- type: enclosing
  outer: <zone_name>
  inner: [<component_refs>]
  tier: 1 | 2 | 3
  because: "Rationale for the constraint"
```

### 4. Aligned
Align a group of components along an axis.

**Syntax:**
```yaml
- type: aligned
  components: [<component_refs>]
  axis: horizontal | vertical
  tier: 3
  because: "Aesthetic alignment"
```

### 5. On Side / On Edge
Constrain components to specific board boundaries.

**Syntax:**
```yaml
- type: on_side
  components: [<component_refs>]
  edge: top | bottom | left | right
  max_distance_from_edge_mm: <float>
  tier: 1 | 2 | 3
  because: "Rationale for the constraint"
```

### 6. Loop Area
Minimize the area of a defined current loop.

**Syntax:**
```yaml
- type: loop_area
  loop_name: <name>
  max_area_mm2: <float>
  tier: 1 | 2 | 3
  because: "EMI minimization"
```

---

## The 'because' Field
Every constraint **must** include a `because` field. This ensures that the design intent is documented and can be audited in the Decision Trace.

**Good:** `because: "Minimize commutation loop area to reduce radiated EMI"`  
**Bad:** `because: "Required"`

---

## Best Practices
1.  **Start with Physics**: Define electrical loops and HV clearances as Tier 1.
2.  **Use Zones**: Group functional blocks into zones to simplify high-level layout.
3.  **Aesthetics Last**: Add alignment and spacing constraints as Tier 3 only after the design is feasible.
4.  **Run the Linter**: Use `temper-placer pcl lint` to catch contradictory constraints (e.g., A must be near B but also 20mm away).