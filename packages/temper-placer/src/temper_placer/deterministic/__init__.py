from .pipeline import DeterministicPipeline
from .state import BoardState


def create_drc_aware_pipeline(
    design_rules=None,
    config=None,
    metadata: "KiCadMetadata | None" = None,
    zone_aware=True,
):
    """Create pipeline with full DRC integration.

    Args:
        design_rules: Design rules for DRC validation
        config: Pipeline configuration
        metadata: KiCad metadata (courtyards, pad sizes, board dimensions) - REQUIRED
        zone_aware: If True, use zone-aware slot generation that avoids copper zones (default: True)

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
        ApplyPlacementsStage,
        CourtyardCheckStage,
        NetClassSetupStage,
        DRCOracleSetupStage,
        ClearanceGridStage,
        NetOrderingStage,
        LayerAssignmentStage,
        PowerPlaneStage,
        SequentialRoutingStage,
        DRCValidationStage,
        ConnectivityValidationStage,
        ViaValidationStage,
        ViaDeduplicationStage,
        TrackDeduplicationStage,
        ShortCircuitDetectionStage,
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
            # Setup - apply net class mapping early
            NetClassSetupStage(net_classes=config.net_classes if config else None),
            # Placement stages
            ZoneGeometryStage(zone_config=zone_config),
            ZoneAssignmentStage(),
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
            # DRC setup
            DRCOracleSetupStage(design_rules=design_rules),
            # Routing
            ClearanceGridStage(
                cell_size_mm=0.25,
                layer_count=4,
                max_clearance_mm=max_clearance,
                net_class_clearances=net_class_clearances,
                net_classes=config.net_classes if config else None,
                pad_sizes=pad_sizes_for_stage,  # Inject pad sizes for accurate blocking
            ),
            NetOrderingStage(net_priority=net_priority),  # EXP-6: Pass explicit priorities
            LayerAssignmentStage(net_classes=config.net_classes if config else None),
            PowerPlaneStage(),  # Mark plane nets (GND, power rails, ACMains) before routing
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
