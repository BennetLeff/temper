# Configuration Reference

*Auto-generated from Pydantic model introspection.*

## Table of Contents

- [PlacementConstraints](#placementconstraints)
- [clearances](#clearances)
- [aesthetics](#aesthetics)
- [manufacturing](#manufacturing)
- [critical_loops](#critical_loops)
- [critical_paths](#critical_paths)
- [matched_length_groups](#matched_length_groups)
- [noise_isolation](#noise_isolation)
- [star_grounds](#star_grounds)
- [thermal_constraints](#thermal_constraints)
- [initialization](#initialization)
- [component_groups](#component_groups)
- [proximity_rules](#proximity_rules)
- [group_separations](#group_separations)
- [component_spacing_rules](#component_spacing_rules)
- [manufacturing_constraints](#manufacturing_constraints)
- [net_class_rules](#net_class_rules)
- [differential_pairs](#differential_pairs)
- [feedback](#feedback)
- [escape_clearances](#escape_clearances)
- [routing_corridors](#routing_corridors)
- [signal_hv_clearances](#signal_hv_clearances)
- [placement_proximity](#placement_proximity)
- [hv_exclusion_zones](#hv_exclusion_zones)
- [isolation_slots](#isolation_slots)
- [seed_filter](#seed_filter)
- [noise_domains](#noise_domains)
- [isolation_barriers](#isolation_barriers)
- [snubber_requirements](#snubber_requirements)

## PlacementConstraints

Complete set of placement constraints.

- **Frozen**: False
- **Extra keys**: forbid

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `board_width_mm` | `float` | 100.0 | gt=0, le=2500 | Board width in mm |
| `board_height_mm` | `float` | 150.0 | gt=0, le=2500 | Board height in mm |
| `board_margin_mm` | `float` | 3.0 | ge=0, le=100 | Board edge margin in mm |
| `keepouts` | `list[tuple]` | [] | — | Rectangular keepout regions |
| `zones` | `list[Zone]` | [] | — | Placement zone definitions |
| `slot_generation` | `dict | None` | None | — | Slot generation configuration |
| `ground_domains` | `list[GroundDomain]` | [] | — | Ground domain definitions |
| `clearances` | `list[ClearanceRule]` | [] | — | Inter-class clearance rules |
| `hv_clearance_mm` | `float` | 10.0 | ge=0 | Default HV-LV clearance in mm |
| `aesthetics` | `AestheticConstraints` | AestheticConstraints() | — | Aesthetic layout configuration |
| `manufacturing` | `ManufacturingConstraints` | ManufacturingConstraints() | — | Manufacturing constraint configuration |
| `critical_loops` | `list[CriticalLoop]` | [] | — | Critical current loop definitions |
| `critical_paths` | `list[CriticalPath]` | [] | — | Critical signal path definitions |
| `matched_length_groups` | `list[MatchedLengthGroup]` | [] | — | Matched length group definitions |
| `noise_isolation` | `list[NoiseIsolationRule]` | [] | — | Noise isolation rule definitions |
| `star_grounds` | `list[StarGroundConfig]` | [] | — | Star ground configuration definitions |
| `thermal_constraints` | `list[ThermalConstraint]` | [] | — | Basic thermal constraint definitions |
| `thermal_properties` | `temper_placer._constraint_types.thermal.ThermalProperties | None` | None | — | Extended thermal properties |
| `initialization` | `PlacementInitialization` | PlacementInitialization() | — | Initialization-phase configuration |
| `component_groups` | `list[ComponentGroup]` | [] | — | Component group definitions |
| `group_separations` | `list[GroupSeparation]` | [] | — | Group separation rule definitions |
| `component_spacing_rules` | `list[ComponentSpacingRule]` | [] | — | Component spacing rule definitions |
| `manufacturing_constraints` | `list[ManufacturingConstraint]` | [] | — | Manufacturing orientation and side constraints |
| `fixed_components` | `list[str]` | [] | — | List of component references that are fixed |
| `fixed_positions` | `dict` | {} | — | Fixed component position map |
| `zone_assignments` | `dict` | {} | — | Component-to-zone assignment map |
| `net_classes` | `dict` | {} | — | Net-to-class assignment map |
| `net_class_rules` | `dict` | {} | — | Per-class design rule definitions |
| `differential_pairs` | `list[DifferentialPairRule]` | [] | — | Differential pair definitions |
| `net_topologies` | `list[NetGraph]` | [] | — | Net topology constraint definitions |
| `pcl_constraints` | `list` | [] | — | PCL constraint objects |
| `feedback` | `FeedbackConfig` | FeedbackConfig() | — | DRC feedback loop configuration |
| `copper_zones` | `list` | [] | — | Copper zone definitions for routing |
| `layer_stackup` | `temper_placer.core.board.LayerStackup | None` | None | — | Layer stackup definition |
| `losses` | `temper_placer._constraint_types.config.LossesConfig | None` | None | — | Loss function configuration |
| `net_classification` | `temper_placer.core.net_types.NetClassification | None` | None | — | Type-safe net classification |
| `placement_priority` | `dict` | {} | — | Placement priority configuration |
| `routing_priority` | `dict` | {} | — | Routing priority configuration |
| `net_priority` | `dict` | {} | — | Per-net routing priority map |
| `escape_clearances` | `list[EscapeClearance]` | [] | — | Escape clearance definitions |
| `routing_corridors` | `list[RoutingCorridor]` | [] | — | Routing corridor definitions |
| `signal_hv_clearances` | `list[SignalToHVClearance]` | [] | — | Signal-to-HV clearance constraints |
| `placement_proximity` | `list[PlacementProximityConstraint]` | [] | — | Placement proximity constraint definitions |
| `hv_exclusion_zones` | `list[HVExclusionZone]` | [] | — | HV exclusion zone definitions |
| `isolation_slots` | `list[IsolationSlot]` | [] | — | Isolation slot definitions |
| `placer` | `dict` | {} | — | Placer-level toggle configuration |
| `seed_filter` | `SeedFilterConfig` | SeedFilterConfig() | — | Seed filter configuration |
| `noise_domains` | `list[NoiseDomain]` | [] | — | Noise coupling domain definitions |
| `isolation_barriers` | `list[IsolationBarrier]` | [] | — | Isolation barrier definitions |
| `snubber_requirements` | `list[SnubberRequirement]` | [] | — | Snubber circuit requirement definitions |
| `bleed_resistor` | `temper_placer._constraint_types.safety.BleedResistor | None` | None | — | Bleed resistor specification |
| `skin_effect_derating` | `temper_placer._constraint_types.safety.SkinEffectDerating | None` | None | — | Skin-effect derating configuration |

## clearances

Clearance rule between net classes or components.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `from_class` | `str` | PydanticUndefined | — | Source net class (e.g., 'HV') |
| `to_class` | `str` | PydanticUndefined | — | Target net class (e.g., 'LV') |
| `clearance_mm` | `float` | PydanticUndefined | ge=0 | Required clearance in mm |
| `description` | `str` | '' | — | Human-readable description |

## aesthetics

Aesthetic and professional layout constraints.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `grid_size_mm` | `float` | 0.5 | gt=0 | Grid size for alignment snapping |
| `grid_weight` | `float` | 1.0 | ge=0 | Weight for grid alignment objective |
| `alignment_weight` | `float` | 1.0 | ge=0 | Weight for component alignment objective |
| `rotation_consistency_weight` | `float` | 1.0 | ge=0 | Weight for rotation consistency objective |
| `align_by_prefix` | `bool` | True | — | Align components with same reference designator prefix |
| `prefix_exceptions` | `list[str]` | [] | — | Prefixes excluded from alignment |
| `max_wirelength_tax` | `float` | 2.5 | ge=1.0 | Maximum wirelength increase factor for aesthetics |
| `consensus_weight` | `float` | 1.0 | ge=0 | Weight for isomorphic group layout consensus |
| `whitespace_weight` | `float` | 0.0 | ge=0 | Weight for whitespace distribution |
| `grouping_weight` | `float` | 0.0 | ge=0 | Weight for visual grouping and separation |
| `symmetry_weight` | `float` | 0.0 | ge=0 | Weight for symmetry enforcement |

## manufacturing

Manufacturing margin and variability constraints.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `target_margin_mm` | `float` | 0.1 | gt=0 | Target manufacturing margin in mm |
| `margin_weight` | `float` | 0.0 | ge=0 | Weight for manufacturing margin objective |
| `etch_tolerance_mm` | `float` | 0.02 | ge=0 | Etch tolerance in mm |

## critical_loops

Definition of a critical current loop to minimize.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `name` | `str` | PydanticUndefined | — | Loop name |
| `nets` | `list[str]` | [] | — | List of net names in the loop |
| `pins` | `list[tuple[str, str]] | None` | None | — | Optional list of (component, pin) tuples |
| `max_area_mm2` | `float | None` | None | ge=0 | Maximum allowed loop area in mm^2 |
| `weight` | `float` | 1.0 | ge=0 | Importance weight for this loop |
| `description` | `str` | '' | — | Human-readable description |

## critical_paths

Definition of a critical signal path between two components.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `name` | `str` | PydanticUndefined | — | Unique path name |
| `from_comp` | `str` | PydanticUndefined | — | Starting component reference |
| `to_comp` | `str` | PydanticUndefined | — | Ending component reference |
| `pins` | `tuple[str, str] | None` | None | — | Optional (from_pin, to_pin) tuple |
| `max_length_mm` | `float` | 50.0 | gt=0 | Maximum allowed path length in mm |
| `priority` | `str` | 'normal' | — | Priority level: critical, high, or normal |
| `matched_length_group` | `str | None` | None | — | Optional matched length group name |

## matched_length_groups

Group of signal paths that must have matched lengths.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `name` | `str` | PydanticUndefined | — | Unique group name |
| `tolerance_mm` | `float` | 5.0 | gt=0 | Maximum length difference in mm |

## noise_isolation

Rule for physical isolation between sensitive components and noise sources.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `name` | `str` | PydanticUndefined | — | Unique name for the isolation rule |
| `sensitive_components` | `list[str]` | PydanticUndefined | — | List of sensitive component references |
| `noise_sources` | `list[str]` | PydanticUndefined | — | List of noise source component references |
| `min_distance_mm` | `float` | 10.0 | ge=0 | Minimum required separation in mm |
| `weight` | `float` | 1.0 | ge=0 | Importance weight |

## star_grounds

Definition of a star ground constraint.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `net` | `str` | PydanticUndefined | — | Net name for star ground |
| `weight` | `float` | 1.0 | ge=0 | Importance weight |
| `anchor` | `tuple[float, float] | None` | None | — | Optional (x, y) anchor position in mm |
| `description` | `str` | '' | — | Human-readable description |

## thermal_constraints

Thermal placement constraint for heat-generating components.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `components` | `list[str]` | PydanticUndefined | — | List of component references |
| `prefer_edge` | `bool` | True | — | Place near board edge |
| `min_spacing_mm` | `float` | 5.0 | ge=0 | Minimum spacing between thermal components in mm |
| `max_distance_from_edge_mm` | `float` | 20.0 | gt=0 | Maximum distance from board edge in mm |
| `description` | `str` | '' | — | Human-readable description |

## initialization

Initialization-phase configuration for the placer pipeline.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `thermal_anchoring` | `bool` | False | — | Enable thermal anchoring during initialization |
| `anchoring_grid_resolution` | `int` | 50 | ge=1 | Grid resolution for thermal anchoring |

## component_groups

Group of components that should be placed together.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `name` | `str` | PydanticUndefined | — | Group name |
| `components` | `list[str]` | PydanticUndefined | — | List of component references in this group |
| `max_spread_mm` | `float` | 30.0 | gt=0 | Maximum diameter of group bounding box in mm |
| `zone` | `str | None` | None | — | Required zone for the group |
| `proximity_rules` | `list[ProximityRule]` | [] | — | Proximity rules within group |
| `weight` | `float` | 1.0 | ge=0 | Importance weight (higher = stronger clustering) |
| `description` | `str` | '' | — | Human-readable description |
| `template_group` | `str | None` | None | — | Optional ID for identical internal layouts |
| `primary_pin` | `str | None` | None | — | Pin number/name defining the front of the group |
| `stacked_layout` | `bool` | False | — | Organize group in a 2D matrix with dynamic gutters |

## proximity_rules

Proximity constraint between two components.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `component_a` | `str` | PydanticUndefined | — | First component reference |
| `component_b` | `str` | PydanticUndefined | — | Second component reference |
| `max_distance_mm` | `float` | 10.0 | gt=0 | Maximum allowed distance between components in mm |
| `description` | `str` | '' | — | Human-readable description |
| `tier` | `str` | 'soft' | — | Constraint tier: hard or soft |

## group_separations

Minimum separation between two groups.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `group_a` | `str` | PydanticUndefined | — | First group name |
| `group_b` | `str` | PydanticUndefined | — | Second group name |
| `min_distance_mm` | `float` | 20.0 | ge=0 | Minimum separation distance in mm |
| `description` | `str` | '' | — | Human-readable description |

## component_spacing_rules

Minimum edge-to-edge spacing between specific component pairs.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `component_a` | `str` | PydanticUndefined | — | First component reference |
| `component_b` | `str` | PydanticUndefined | — | Second component reference |
| `min_separation_mm` | `float` | PydanticUndefined | ge=0 | Minimum edge-to-edge separation in mm |
| `description` | `str` | '' | — | Human-readable description |
| `weight` | `float` | 1.0 | ge=0 | Importance weight |
| `tier` | `str` | 'soft' | — | Constraint tier: hard or soft |

## manufacturing_constraints

Manufacturing constraint for orientations and assembly side.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `components` | `list[str]` | PydanticUndefined | — | List of component references |
| `allowed_orientations` | `list[float] | None` | None | — | Allowed rotation angles in degrees |
| `side` | `str | None` | None | — | Allowed board side: top, bottom, both |
| `tier` | `str` | 'hard' | — | Constraint tier: hard or soft |
| `because` | `str` | '' | — | Justification for the constraint |
| `weight` | `float` | 1.0 | ge=0 | Importance weight |

## net_class_rules

Design rules for a specific net class.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `name` | `str` | PydanticUndefined | — | Net class name (e.g., 'HighVoltage') |
| `trace_width_mm` | `float` | 0.2 | gt=0 | Trace width in mm |
| `clearance_mm` | `float` | 0.2 | ge=0 | Clearance to other traces in mm |
| `via_size_mm` | `float` | 0.6 | gt=0 | Via pad diameter in mm |
| `via_drill_mm` | `float` | 0.3 | gt=0 | Via drill diameter in mm |
| `via_template` | `str | None` | None | — | Via array template name |
| `creepage_mm` | `float` | 0.0 | ge=0 | Creepage distance in mm |
| `allow_neckdown` | `bool` | True | — | Allow trace neckdown |
| `description` | `str` | '' | — | Human-readable description |
| `voltage_v` | `float` | 0.0 | ge=0 | Working voltage for creepage calculation |
| `max_current_rating` | `float | None` | None | — | Maximum current in Amps |
| `routing_strategy` | `str | None` | None | — | Routing strategy: plane_required, plane_preferred, wide_trace, standard |
| `via_cost_multiplier` | `float` | 1.0 | ge=0 | Multiplier for via cost (higher = fewer vias) |
| `target_impedance` | `float | None` | None | — | Target impedance in Ohms |

## differential_pairs

Configuration for a differential pair from YAML.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `net_pos` | `str` | PydanticUndefined | — | Positive net name |
| `net_neg` | `str` | PydanticUndefined | — | Negative net name |
| `spacing_mm` | `float` | 0.2 | gt=0 | Nominal gap between differential traces in mm |
| `coupling_tolerance_mm` | `float` | 0.5 | ge=0 | Maximum deviation from nominal spacing in mm |
| `impedance_ohm` | `float | None` | None | — | Target differential impedance in Ohms |
| `max_skew_mm` | `float` | 0.5 | ge=0 | Maximum length mismatch in mm |
| `description` | `str` | '' | — | Human-readable description |

## feedback

Configuration for the automated DRC feedback loop.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `max_iterations` | `int` | 5 | ge=0, le=1000 | Maximum number of DRC feedback iterations |
| `violation_threshold` | `int` | 5 | ge=0 | Minimum violations to trigger expansion |
| `expansion_per_violation` | `float` | 0.5 | ge=0 | Expansion distance per violation in mm |

## escape_clearances

Keep area clear around fine-pitch ICs for escape routing.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `component` | `str` | PydanticUndefined | — | Component reference (e.g., 'U_MCU') |
| `clearance_mm` | `float | None` | None | — | Override clearance in mm; computed from pin density if None |
| `priority_sides` | `list[str]` | [] | — | Priority routing sides (e.g., ['bottom', 'right']) |
| `tier` | `str` | 'soft' | — | Constraint tier: hard or soft |
| `description` | `str` | '' | — | Human-readable description |

## routing_corridors

Preserve routing channel between components.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `name` | `str` | PydanticUndefined | — | Corridor name |
| `from_component` | `str` | PydanticUndefined | — | Source component reference |
| `to_component` | `str` | PydanticUndefined | — | Target component reference |
| `width_mm` | `float` | PydanticUndefined | gt=0 | Corridor width in mm |
| `keep_clear` | `bool` | True | — | If True, don't place components in corridor |
| `nets` | `list[str]` | [] | — | Associated net names |
| `tier` | `str` | 'soft' | — | Constraint tier: hard or soft |
| `description` | `str` | '' | — | Human-readable description |

## signal_hv_clearances

Constraint ensuring signal paths maintain clearance from HV component pins.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `name` | `str` | PydanticUndefined | — | Unique constraint identifier |
| `signal_component` | `str` | PydanticUndefined | — | Signal source component reference |
| `signal_pin` | `str` | PydanticUndefined | — | Signal source pin number |
| `target_component` | `str` | PydanticUndefined | — | Target component reference |
| `target_pin` | `str` | PydanticUndefined | — | Target pin number |
| `hv_component` | `str` | PydanticUndefined | — | Component with HV pins to avoid |
| `hv_pins` | `list[str]` | PydanticUndefined | — | List of HV pin numbers to avoid |
| `required_clearance_mm` | `float` | 6.0 | ge=0 | Minimum clearance from signal path to HV pins |
| `max_path_length_mm` | `float` | 20.0 | gt=0 | Maximum allowed signal path length in mm |
| `tier` | `str` | 'hard' | — | Constraint tier: hard (fail) or soft (warn) |
| `description` | `str` | '' | — | Human-readable description |

## placement_proximity

Constraint ensuring a component output pin is close to a target input pin.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `name` | `str` | PydanticUndefined | — | Unique constraint identifier |
| `from_component` | `str` | PydanticUndefined | — | Source component reference |
| `from_pin` | `str` | PydanticUndefined | — | Source pin number |
| `to_component` | `str` | PydanticUndefined | — | Target component reference |
| `to_pin` | `str` | PydanticUndefined | — | Target pin number |
| `max_distance_mm` | `float` | 15.0 | gt=0 | Maximum pin-to-pin distance in mm |
| `tier` | `str` | 'hard' | — | Constraint tier: hard or soft |
| `description` | `str` | '' | — | Human-readable description |

## hv_exclusion_zones

Defines a rectangular zone around HV components that signals must avoid.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `name` | `str` | PydanticUndefined | — | Unique zone identifier |
| `center` | `tuple` | PydanticUndefined | — | (x, y) center position in mm |
| `size` | `tuple` | PydanticUndefined | — | (width, height) in mm |
| `clearance_mm` | `float` | 6.0 | ge=0 | Required creepage clearance in mm |
| `excluded_nets` | `list[str]` | [] | — | Net names that must avoid this zone |
| `component_refdes` | `str | None` | None | — | Optional parent component reference |
| `description` | `str` | '' | — | Human-readable description |

## isolation_slots

Defines a PCB slot for creepage isolation between HV and LV pins.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `name` | `str` | PydanticUndefined | — | Unique slot identifier |
| `component_ref` | `str` | PydanticUndefined | — | Component reference for positioning |
| `start_offset` | `tuple` | PydanticUndefined | — | (dx, dy) offset from component origin to slot start |
| `end_offset` | `tuple` | PydanticUndefined | — | (dx, dy) offset from component origin to slot end |
| `width_mm` | `float` | 1.5 | gt=0 | Slot width in mm |
| `lv_pin` | `str` | '' | — | Low-voltage pin number being isolated |
| `hv_pin` | `str` | '' | — | High-voltage pin number |
| `description` | `str` | '' | — | Human-readable description |

## seed_filter

Configuration for the bottleneck-map seed filter.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `enabled` | `bool` | True | — | Whether the seed filter is active |
| `threshold` | `float` | 0.7 | ge=0, le=1 | Bottleneck probability threshold for seed filtering |
| `hv_threshold` | `float` | 0.5 | ge=0, le=1 | HV-specific bottleneck probability threshold |

## noise_domains

Noise coupling domain: emitters and victims that must not run parallel.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `emitters` | `list[str]` | PydanticUndefined | — | List of emitter net names |
| `victims` | `list[str]` | PydanticUndefined | — | List of victim net names |
| `max_parallel_run_mm` | `float` | 5.0 | ge=0 | Maximum allowed parallel run length in mm |

## isolation_barriers

An isolation barrier line across the board.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `name` | `str` | PydanticUndefined | — | Barrier name |
| `x_mm` | `float` | PydanticUndefined | — | X-position of the barrier in mm |
| `y_span` | `tuple` | PydanticUndefined | — | (y_start, y_end) span of the barrier in mm |
| `layers` | `str | list[str]` | 'all' | — | Layer name(s) for the barrier |

## snubber_requirements

Snubber circuit requirement near an IGBT pair.

- **Frozen**: True
- **Extra keys**: ignore

| Field | Type | Default | Constraints | Description |
|-------|------|---------|-------------|-------------|
| `igbt_pair` | `tuple` | PydanticUndefined | — | IGBT component reference pair |
| `type` | `str` | 'RC' | — | Snubber type: RC, RCD, etc. |
| `across` | `str` | 'collector_emitter' | — | Across which terminals: collector_emitter |

*Generated from `temper_placer._constraint_types.config.PlacementConstraints`*
