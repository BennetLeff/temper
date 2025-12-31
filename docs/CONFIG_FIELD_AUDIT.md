# Config Field Audit - temper_constraints.yaml

## Summary
This document audits which fields in `temper_constraints.yaml` are actually parsed and used by the code.

## ✅ USED Fields (Parsed by config_loader.py)

### Board Section
- `width_mm` → `constraints.board_width_mm`
- `height_mm` → `constraints.board_height_mm`
- `margin_mm` → `constraints.board_margin_mm`
- `keepouts` → `constraints.keepouts`

### Zones
- `name`, `bounds`, `net_classes`, `components` → `constraints.zones[]`
- `bounds_ratio` (alternative to `bounds`)

### Ground Domains
- `name`, `bounds`, `star_point` → `constraints.ground_domains[]`

### Clearances
- `from`, `to`, `clearance_mm`, `description` → `constraints.clearances[]`

### HV Clearance
- `hv_clearance_mm` → `constraints.hv_clearance_mm`

### Critical Loops
- `name`, `nets`, `pins`, `max_area_mm2`, `weight`, `description` → `constraints.critical_loops[]`

### Critical Paths
- `from`, `to`, `pins`, `max_length_mm`, `priority`, `matched_length_group` → `constraints.critical_paths[]`

### Matched Length Groups
- `tolerance_mm` → `constraints.matched_length_groups[]`

### Noise Isolation
- `sensitive_components`, `noise_sources`, `min_distance_mm`, `weight` → `constraints.noise_isolation[]`

### Star Grounds
- `net`, `weight`, `anchor`, `description` → `constraints.star_grounds[]`

### Thermal (Basic)
- `components`, `prefer_edge`, `min_spacing_mm` OR `min_separation_mm`, `max_distance_from_edge_mm`, `description`
- **Note**: Line 528 shows fallback: `min_spacing_mm` OR `min_separation_mm` (both work!)

### Thermal Properties (Advanced)
- `high_power.components`, `high_power.power_dissipation_w`, `high_power.min_separation_mm`
- `heat_sensitive.components`, `heat_sensitive.max_temp_rise_c`, `heat_sensitive.min_distance_from_heat_sources_mm`
- `thermal_pads.components`, `thermal_pads.prefer_edge`, `thermal_pads.preferred_edge_margin_mm`

### Groups
- `name`, `components`, `max_spread_mm`, `zone`, `weight`, `description`
- `proximity[]` with `pair`, `max_distance_mm`
- `template_group`, `primary_pin`, `stacked_layout`

### Component Groups (Alternative Format)
- `name`, `leader`, `followers`, `max_distance`, `zone`, `weight`, `description`
- **Note**: Line 595 shows `max_distance` is mapped to `max_spread_mm`!

### Group Separation
- `groups[]`, `min_distance_mm`, `description` → `constraints.group_separations[]`

### Fixed Components & Positions
- `fixed_components[]` → `constraints.fixed_components[]`
- `fixed_positions{}` → `constraints.fixed_positions{}`

### Zone Assignments
- `zone_assignments{}` → `constraints.zone_assignments{}`

### Net Classes
- `net_classes{}` → `constraints.net_classes{}`

### Aesthetics
- `grid_size_mm`, `grid_weight`, `alignment_weight`, `rotation_consistency_weight`
- `align_by_prefix`, `prefix_exceptions`, `max_wirelength_tax`
- `consensus_weight`, `whitespace_weight`, `grouping_weight`, `symmetry_weight`

### Manufacturing
- `target_margin_mm`, `margin_weight`, `etch_tolerance_mm`

### Losses (New Format)
- `overlap`, `boundary`, `wirelength`, `spread`, `edge_avoidance`
- `group_cluster`, `thermal`, `zone`, `clearance`, `loop_area`, `star_point`
- Each with: `weight`, `enabled`, `margin`

### Loss Weights (Legacy Format)
- Fallback if `losses` not present
- Maps `zone_membership` → `zone`

### Placement Priority
- `placement_priority{}` → `constraints.placement_priority{}`

### Routing Priority
- `routing_priority{}` → `constraints.routing_priority{}`

---

## ❌ UNUSED Fields (Not Parsed)

### minimum_spacing
- **Status**: ❌ NOT PARSED
- **Location**: Lines 234-267 in config
- **Fields**: `components[]`, `min_separation_mm`, `description`
- **Action Required**: Add parsing in `load_constraints()` around line 613

### nets
- **Status**: ❌ EMPTY (line 270)
- **Purpose**: Unknown - appears to be placeholder
- **Action**: Can be removed

---

## ⚠️ INCONSISTENCIES

### 1. max_distance vs max_spread_mm
**In Config (lines 93-101)**:
```yaml
proximity:
  - pair: ["C_BUS1", "Q1"]
    max_distance_mm: 8.0
```

**In Config (lines 306-333)**:
```yaml
component_groups:
  - name: power_stage
    leader: Q1
    max_distance: 30.0  # ← Different field name!
```

**In Code (line 595)**:
```python
max_spread_mm=group_cfg.get("max_distance", 30.0),  # Maps max_distance → max_spread_mm
```

**Resolution**: Both work, but `max_spread_mm` is the canonical name. `max_distance` is accepted for `component_groups` format.

### 2. min_spacing_mm vs min_separation_mm
**In Config (line 528)**:
```python
min_spacing = thermal_cfg.get("min_spacing_mm", thermal_cfg.get("min_separation_mm", 5.0))
```

**Resolution**: Both work for `thermal` section! Code prefers `min_spacing_mm` but falls back to `min_separation_mm`.

### 3. min_distance_mm (multiple contexts)
- Used in `proximity` rules (line 563)
- Used in `group_separation` (line 609)
- Used in `noise_isolation` (line 510)
- **NOT** used in `minimum_spacing` (not parsed at all)

---

## 📋 Recommendations

### 1. Implement minimum_spacing Parser
Add to `load_constraints()` after line 612:

```python
if "minimum_spacing" in config:
    # TODO: Parse minimum_spacing rules
    # See docs/MINIMUM_SPACING_TODO.md for implementation plan
    pass
```

### 2. Standardize Field Names
Document the canonical names:
- ✅ `max_spread_mm` (for groups)
- ✅ `min_separation_mm` (for thermal, component spacing)
- ✅ `min_distance_mm` (for group separation, noise isolation)
- ✅ `max_distance_mm` (for proximity within groups)

### 3. Remove Dead Code
- Line 270: `nets: []` can be removed (unused)

### 4. Add Validation
The config has many fields that are silently ignored if misspelled. Consider adding validation warnings for unknown keys.

---

## Field Name Mapping Table

| Config Field | Dataclass Field | Context |
|--------------|-----------------|---------|
| `max_spread_mm` | `ComponentGroup.max_spread_mm` | groups |
| `max_distance` | `ComponentGroup.max_spread_mm` | component_groups (alias) |
| `max_distance_mm` | `ProximityRule.max_distance_mm` | proximity rules |
| `min_distance_mm` | `GroupSeparation.min_distance_mm` | group_separation |
| `min_distance_mm` | `NoiseIsolationRule.min_distance_mm` | noise_isolation |
| `min_spacing_mm` | `ThermalConstraint.min_spacing_mm` | thermal |
| `min_separation_mm` | `ThermalConstraint.min_spacing_mm` | thermal (fallback) |
| `min_separation_mm` | `ThermalProperties.min_separation_mm` | thermal_properties |
| `min_separation_mm` | ❌ NOT PARSED | minimum_spacing |
