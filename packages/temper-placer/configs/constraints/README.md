# PCL Constraint Sets

Pre-built Placement Constraint Language (PCL) files for common power electronics topologies.

## Available Constraint Sets

### 1. `half_bridge_base.yaml`
**Core placement rules for half-bridge power stages**

Applicable to:
- Half-bridge converters
- Full-bridge converters
- Synchronous buck converters

Covers:
- Critical loop area limits (commutation, gate drive)
- Component adjacency (switches, gate driver, bus caps)
- Decoupling capacitor placement
- Bootstrap circuit layout

Use this as a base for any half-bridge topology.

### 2. `safety_isolation.yaml`
**IEC 60335-1 compliant isolation for mains-powered equipment**

Covers:
- Reinforced isolation requirements (10mm @ 400V)
- High-voltage to low-voltage separation
- EMI isolation from switching components
- Zone definitions (HV_ZONE, LV_ZONE, ISOLATION_BARRIER)

Use this for any mains-powered consumer appliance.

### 3. `thermal_management.yaml`
**Placement rules for thermal performance**

Covers:
- Heatsink mounting constraints (TO-247 packages)
- Temperature-sensitive component isolation
- Electrolytic capacitor derating
- Thermal sensor placement

Use this when power dissipation > 5W or when reliability is critical.

### 4. `temper_induction_cooker.yaml`
**Complete constraint set for Temper project**

Combines all base sets plus project-specific rules:
- Specific component references (Q1, Q2, U_GATE, etc.)
- Zone polygons for 120mm x 80mm board
- Connector placement for enclosure
- Resonant tank layout
- Current sensing circuit

Use this as a reference for your own project-specific constraint files.

## Usage

### Basic Optimization
```bash
# Use a constraint set
temper-placer optimize input.kicad_pcb \
    -c configs/constraints/half_bridge_base.yaml \
    -o output.kicad_pcb
```

### With Custom Board Config
```bash
# Combine constraints with board-specific config
temper-placer optimize input.kicad_pcb \
    -c configs/constraints/temper_induction_cooker.yaml \
    --config configs/temper_constraints.yaml \
    -o output.kicad_pcb
```

### Validation Only
```bash
# Check if constraints are satisfiable
temper-placer validate input.kicad_pcb \
    -c configs/constraints/safety_isolation.yaml
```

### Lint Constraints
```bash
# Check for contradictions and errors
temper-placer pcl lint configs/constraints/temper_induction_cooker.yaml
```

## Creating Your Own Constraint Sets

### 1. Start with Base Template
Copy one of the base templates and modify:
```bash
cp configs/constraints/half_bridge_base.yaml my_converter.yaml
```

### 2. Update Metadata
```yaml
metadata:
  name: "My Converter Constraints"
  project: "my_project"
  author: "Your Name"
  date: "2025-12-19"
```

### 3. Define Zones (Optional)
```yaml
zones:
  - name: POWER_ZONE
    type: hv
    polygon: [[0, 0], [50, 0], [50, 60], [0, 60]]
```

### 4. Add Constraints
```yaml
constraints:
  - type: adjacent
    a: Q1
    b: C1
    max_distance_mm: 5
    tier: 1
    because: "Your rationale here (minimum 10 characters)"
```

### 5. Validate
```bash
temper-placer pcl lint my_converter.yaml
```

## Constraint Tiers

All constraints have a tier (1-3) that determines priority:

| Tier | Name | Weight | Usage |
|------|------|--------|-------|
| 1 | HARD | 1e6 | Safety, compliance, critical loops |
| 2 | STRONG | 1e3 | Performance, EMI, thermal |
| 3 | SOFT | 1e1 | Aesthetics, preferences |

**Escalation:** Constraints can escalate to higher tiers during optimization if:
- Violation is severe (exceeds threshold)
- Violation persists across many iterations

See `src/temper_placer/pcl/tiers.py` for escalation logic.

## Constraint Types Reference

### Loop Area
```yaml
- type: loop_area
  loop_name: commutation_loop
  max_area_mm2: 500
  tier: 1
  because: "EMI scales with loop area"
```

### Adjacent
```yaml
- type: adjacent
  a: Q1
  b: Q2
  max_distance_mm: 10
  metric: edge_to_edge  # or center_to_center, pin_to_pin
  pin_a: DRAIN  # optional
  pin_b: SOURCE  # optional
  tier: 1
  because: "Minimize commutation loop"
```

### Separated
```yaml
- type: separated
  a: HV_ZONE
  b: LV_ZONE
  min_distance_mm: 10.0
  tier: 1
  because: "IEC 60335-1 reinforced isolation"
```

### Enclosing
```yaml
- type: enclosing
  outer: POWER_ZONE
  inner: [Q1, Q2, C1, C2]
  margin_mm: 2.0  # optional
  tier: 1
  because: "Contain power components in zone"
```

### Aligned
```yaml
- type: aligned
  components: [C1, C2, C3]
  axis: horizontal  # or vertical
  tolerance_mm: 1.0  # optional
  tier: 3
  because: "Aesthetic alignment"
```

### On Side
```yaml
- type: on_side
  components: [J1, J2]
  side: top  # top, bottom, left, right
  edge: top  # optional: flush, near, overhang
  max_distance_from_edge_mm: 5  # optional
  tier: 1
  because: "Connectors at board edge"
```

### Anchored
```yaml
# With region
- type: anchored
  component: U1
  region: CENTER_ZONE
  tier: 2
  because: "MCU centered for antenna clearance"

# Or with absolute position
- type: anchored
  component: U1
  position: [60.0, 40.0]  # x, y in mm
  tier: 2
  because: "Fixed position for mechanical alignment"
```

## Best Practices

1. **Always include 'because' field** (minimum 10 characters)
   - Explain WHY the constraint exists
   - Reference standards (IEC 60335-1, EMC directives)
   - Cite physical reasons (loop area, thermal, isolation)

2. **Use appropriate tiers**
   - Tier 1: Safety, compliance, critical performance
   - Tier 2: Performance, EMI, thermal
   - Tier 3: Aesthetics, preferences

3. **Start with base templates**
   - Don't reinvent the wheel
   - Leverage proven patterns
   - Customize for your specific components

4. **Validate early**
   - Run linter before optimization
   - Check for contradictions
   - Verify component references

5. **Document zone polygons**
   - Use real board dimensions
   - Include keepout regions
   - Document zone purposes

## Examples

See `tests/pcl/fixtures/half_bridge.yaml` for a complete working example with all constraint types.

## Contributing

When adding new constraint sets:
1. Follow naming convention: `{topology}_{aspect}.yaml`
2. Include comprehensive metadata
3. Add comments explaining constraints
4. Test with actual KiCad PCB
5. Submit with validation report

## License

These constraint sets are part of the Temper project and follow the same license.
