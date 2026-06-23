from .pipeline import DeterministicPipeline
from .state import BoardState
from .stages.base import Stage
from .stages.hv_lv_partition import HvLvPartitionStage, PartitionError

__all__ = ["DeterministicPipeline", "BoardState", "HvLvPartitionStage", "PartitionError"]


class ConfigAttachStage(Stage):
    """Prepend-only stage that writes ``config`` onto ``BoardState``.

    Stages such as ``HvLvPartitionStage`` read their block from
    ``state.config``; without this stage the field stays ``None`` and the
    partition never engages.

    This stage is idempotent: a no-op when ``config`` is None.
    """

    def __init__(self, config):
        self._config = config

    @property
    def name(self) -> str:
        return "config_attach"

    def run(self, state: BoardState) -> BoardState:
        if self._config is None:
            return state
        return state.with_config(self._config)


def create_drc_aware_pipeline(
    design_rules=None,
    config=None,
    metadata: "KiCadMetadata | None" = None,
    zone_aware=True,
    parsed_pads=None,
):
    """Create pipeline with full DRC integration.

    Args:
        design_rules: Design rules for DRC validation
        config: Pipeline configuration
        metadata: KiCad metadata (courtyards, pad sizes, board dimensions) - REQUIRED
        zone_aware: If True, use zone-aware slot generation that avoids copper zones (default: True)
        parsed_pads: Optional list of PadData from kicad_parser.parse_kicad_pcb().pads.
            If provided, DRC oracle uses these exact positions instead of computing
            from component placements. This ensures DRC validates against actual
            KiCad positions, not optimizer-generated positions.

    Raises:
        TypeError: If metadata is not provided
    """
    if metadata is None:
        raise TypeError("create_drc_aware_pipeline() requires 'metadata' parameter (KiCadMetadata)")

    from .stages import (
        ZoneGeometryStage,
        ZoneAssignmentStage,
        SlotGenerationStage,
        ZoneAwareSlotGenerationStage,
        ComponentAssignmentStage,
        PhasedComponentAssignmentStage,
        HvLvPartitionStage,
        ApplyPlacementsStage,
        CourtyardCheckStage,
        NetClassSetupStage,
        DRCOracleSetupStage,
        ClearanceGridStage,
        NetOrderingStage,
        LayerAssignmentStage,
        PowerPlaneStage,
        FinePitchEscapeStage,
        SequentialRoutingStage,
        DRCValidationStage,
        ConnectivityValidationStage,
        ViaValidationStage,
        ViaDeduplicationStage,
        TrackDeduplicationStage,
        ShortCircuitDetectionStage,
        PlacementValidationStage,
    )
    from .stages.sequential_routing import DiffPairConfig

    # Build zone config from YAML config if available
    zone_config = None
    slot_spacing = 10.0  # Default: larger spacing to avoid overlaps
    max_clearance = 2.5  # Default: conservative for HV boards
    net_class_clearances = {}
    fixed_placements = {}
    yaml_copper_zones = []
    differential_pairs = []
    net_priority = {}  # EXP-6: Explicit net routing priority
    placement_constraints = {}  # EXP-12: Placement validation constraints
    hv_exclusion_zones = []  # EXP-13: HV zones that signals must route around

    # Extract net class clearances from design_rules if available
    if design_rules and hasattr(design_rules, "net_classes"):
        for name, rules in design_rules.net_classes.items():
            net_class_clearances[name] = rules.clearance

    # Extract/override from config if available
    if config:
        zone_config = getattr(config, "zones", None)
        slot_config = getattr(config, "slot_generation", None)
        fixed_placements = getattr(config, "fixed_positions", {})
        yaml_copper_zones = getattr(config, "copper_zones", [])
        if slot_config and "spacing_mm" in slot_config:
            slot_spacing = slot_config["spacing_mm"]

        # Get net class rules from config
        config_rules = getattr(config, "net_class_rules", None)
        if config_rules:
            for name, rules in config_rules.items():
                if hasattr(rules, "clearance_mm"):
                    net_class_clearances[name] = rules.clearance_mm
                elif isinstance(rules, dict):
                    net_class_clearances[name] = rules.get("clearance_mm", 0.2)

        if net_class_clearances:
            max_clearance = max(net_class_clearances.values()) + 0.3  # Add margin for trace width

        # Extract differential pairs from config
        config_diff_pairs = getattr(config, "differential_pairs", None)
        if config_diff_pairs:
            for dp in config_diff_pairs:
                if isinstance(dp, dict):
                    differential_pairs.append(
                        DiffPairConfig(
                            net_pos=dp.get("net_pos", ""),
                            net_neg=dp.get("net_neg", ""),
                            spacing_mm=dp.get("spacing_mm", 0.15),
                            coupling_tolerance_mm=dp.get("coupling_tolerance_mm", 0.5),
                            max_skew_mm=dp.get("max_skew_mm", 0.5),
                        )
                    )
                elif hasattr(dp, "net_pos"):
                    # Already a config object
                    differential_pairs.append(
                        DiffPairConfig(
                            net_pos=getattr(dp, "net_pos", ""),
                            net_neg=getattr(dp, "net_neg", ""),
                            spacing_mm=getattr(dp, "spacing_mm", 0.15),
                            coupling_tolerance_mm=getattr(dp, "coupling_tolerance_mm", 0.5),
                            max_skew_mm=getattr(dp, "max_skew_mm", 0.5),
                        )
                    )

        # EXP-6: Extract net priority from config
        config_net_priority = getattr(config, "net_priority", None)
        if config_net_priority:
            net_priority = dict(config_net_priority)

        # EXP-12: Extract placement validation constraints
        signal_hv = getattr(config, "signal_hv_clearances", None) or []
        proximity = getattr(config, "placement_proximity", None) or []
        # feat/hv-lv-guard-strip: PlacementValidationStage always reads
        # ``self.constraints.get(...)`` even when no constraints were
        # declared, so the dict must be non-empty to survive the
        # ``constraints or []`` fallback in the stage.
        placement_constraints = {
            "signal_hv_clearances": signal_hv,
            "placement_proximity": proximity,
        }

        # EXP-13: Extract HV exclusion zones for routing
        hv_exclusion_zones = getattr(config, "hv_exclusion_zones", [])

        # Create DesignRules from config if not explicitly provided
        # This ensures SequentialRoutingStage gets proper trace widths from net class rules
        if design_rules is None and config_rules:
            from temper_placer.core.design_rules import DesignRules, NetClassRules

            # Convert config NetClassRule objects to core NetClassRules
            converted_net_classes = {}
            for name, rule in config_rules.items():
                converted_net_classes[name] = NetClassRules(
                    name=name,
                    trace_width=getattr(rule, "trace_width_mm", 0.25),
                    clearance=getattr(rule, "clearance_mm", 0.2),
                    via_diameter=getattr(rule, "via_size_mm", 0.6),
                    via_drill=getattr(rule, "via_drill_mm", 0.3),
                    via_template=getattr(rule, "via_template", None),
                    creepage_mm=getattr(rule, "creepage_mm", 0.0),
                    dru_priority=getattr(rule, "dru_priority", 0),
                )

            # Get net class assignments from config
            net_class_assignments = getattr(config, "net_classes", {})

            design_rules = DesignRules(
                net_classes=converted_net_classes,
                net_class_assignments=net_class_assignments,
            )

    # Select slot generation stage based on zone_aware flag
    if zone_aware:
        slot_stage = ZoneAwareSlotGenerationStage(
            slot_spacing_mm=slot_spacing,
            copper_zone_margin=2.0,
            min_routing_channel=3.0,
            yaml_copper_zones=yaml_copper_zones,
        )
    else:
        slot_stage = SlotGenerationStage(slot_spacing_mm=slot_spacing)

    # Convert metadata pad_sizes to format expected by stages
    # Stage expects Dict[(ref, pad_num), pad_object] but we have Dict[(ref, pad_num), PadSize]
    pad_sizes_for_stage = {}
    for key, pad_size in metadata.pad_sizes.items():
        # Create a simple object with the attributes that stages need
        class PadInfo:
            def __init__(self, pad_size_obj):
                self.size = type("Size", (), {"X": pad_size_obj.width, "Y": pad_size_obj.height})()
                self.number = pad_size_obj.pad_number
                self.shape = getattr(pad_size_obj, "shape", "rect")
                self.rotation = getattr(pad_size_obj, "rotation", 0.0)

        pad_sizes_for_stage[key] = PadInfo(pad_size)

    # Select component assignment stage based on constraint config
    # Use PhasedComponentAssignmentStage if config has placement_priority or constraint rules
    use_phased_placement = config is not None and (
        getattr(config, "placement_priority", None)
        or getattr(config, "component_spacing_rules", None)
        or getattr(config, "component_groups", None)
    )

    if use_phased_placement:
        component_stage = PhasedComponentAssignmentStage(
            constraints=config,
            slot_spacing=slot_spacing,
            fixed_placements=fixed_placements,
        )
    else:
        component_stage = ComponentAssignmentStage(
            slot_spacing=slot_spacing,
            fixed_placements=fixed_placements,
        )

    return DeterministicPipeline(
        stages=[
            # feat/hv-lv-guard-strip: attach the parsed config to state so
            # downstream stages (HvLvPartitionStage in particular) can read
            # their own block from ``state.config``.
            ConfigAttachStage(config),
            # Setup - apply net class mapping early
            NetClassSetupStage(net_classes=config.net_classes if config else None),
            # Placement stages
            ZoneGeometryStage(zone_config=zone_config),
            ZoneAssignmentStage(),
            # feat/hv-lv-guard-strip: HV/LV domain map MUST run before
            # component assignment so phased_component_assignment (and the
            # standard fallback) can filter slots by domain.
            HvLvPartitionStage(),
            slot_stage,  # Use zone-aware or standard slot generation
            component_stage,  # Use phased or standard component assignment
            ApplyPlacementsStage(),
            # DRC-FIX-4: Resolve courtyard overlaps and clamp to board bounds
            CourtyardCheckStage(
                courtyards=metadata.courtyards,
                board_width=metadata.board_width,
                board_height=metadata.board_height,
                margin=5.0,
            ),
            # DRC-FIX-5: Re-apply placements after clamping to sync component.initial_position
            ApplyPlacementsStage(),
            # EXP-12: Validate placement constraints before routing
            PlacementValidationStage(
                constraints=placement_constraints,
                fail_on_hard_violations=False,  # Log warnings, don't abort
                parsed_pads=parsed_pads,
            ),
            # DRC setup - use parsed_pads for correct KiCad positions
            DRCOracleSetupStage(
                design_rules=config if config else design_rules,
                parsed_pads=parsed_pads,
            ),
            # Routing
            ClearanceGridStage(
                cell_size_mm=0.25,
                layer_count=4,
                max_clearance_mm=max_clearance,
                net_class_clearances=net_class_clearances,
                net_classes=config.net_classes if config else None,
                pad_sizes=pad_sizes_for_stage,  # Inject pad sizes for accurate blocking
                hv_exclusion_zones=hv_exclusion_zones,  # EXP-13: Block zones for signal nets
            ),
            NetOrderingStage(net_priority=net_priority),  # EXP-6: Pass explicit priorities
            LayerAssignmentStage(net_classes=config.net_classes if config else None),
            PowerPlaneStage(),  # Mark plane nets (GND, power rails, ACMains) before routing
            FinePitchEscapeStage(
                pin_pitch_threshold_mm=0.65,
                escape_layer=1,
            ),  # Place escape vias for fine-pitch ICs before main routing
            SequentialRoutingStage(
                design_rules=design_rules,
                differential_pairs=differential_pairs,
                pad_sizes=pad_sizes_for_stage,  # Inject pad sizes for terminal identification
            ),
            # Post-routing cleanup (order matters!)
            TrackDeduplicationStage(),  # Remove duplicate tracks first
            ShortCircuitDetectionStage(),  # Remove tracks that short
            ViaDeduplicationStage(),  # Remove duplicate vias
            ViaValidationStage(),  # Remove dangling vias
            # Validation
            DRCValidationStage(),
            ConnectivityValidationStage(),
        ]
    )


def create_legacy_pipeline():
    """Create legacy pipeline without DRC oracle integration."""
    from .stages import (
        ZoneGeometryStage,
        ZoneAssignmentStage,
        SlotGenerationStage,
        ComponentAssignmentStage,
        HvLvPartitionStage,
        ApplyPlacementsStage,
        ClearanceGridStage,
        NetOrderingStage,
        LayerAssignmentStage,
        SequentialRoutingStage,
        DRCValidationStage,
        ConnectivityValidationStage,
        ViaValidationStage,
        ViaDeduplicationStage,
        TrackDeduplicationStage,
    )

    return DeterministicPipeline(
        stages=[
            # Placement stages
            ZoneGeometryStage(),
            ZoneAssignmentStage(),
            # feat/hv-lv-guard-strip: HV/LV domain map MUST run before
            # component assignment so the domain filter is applied.
            HvLvPartitionStage(),
            SlotGenerationStage(slot_spacing_mm=7.5),  # Balanced spacing
            ComponentAssignmentStage(),
            ApplyPlacementsStage(),
            # Routing
            ClearanceGridStage(cell_size_mm=0.25, layer_count=4),
            NetOrderingStage(),
            LayerAssignmentStage(),
            SequentialRoutingStage(),  # Use defaults
            # Post-routing cleanup
            TrackDeduplicationStage(),
            ViaDeduplicationStage(),
            ViaValidationStage(),
            # Validation
            DRCValidationStage(),
            ConnectivityValidationStage(),
        ]
    )
