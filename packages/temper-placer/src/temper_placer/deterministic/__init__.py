from .pipeline import DeterministicPipeline
from .state import BoardState

def create_drc_aware_pipeline(design_rules=None, config=None):
    '''Create pipeline with full DRC integration.'''
    from .stages import (
        ZoneGeometryStage, ZoneAssignmentStage, SlotGenerationStage,
        ComponentAssignmentStage, ApplyPlacementsStage,
        DRCOracleSetupStage, ClearanceGridStage, NetOrderingStage,
        LayerAssignmentStage, SequentialRoutingStage,
        DRCValidationStage, ConnectivityValidationStage,
        ViaValidationStage, ViaDeduplicationStage,
        TrackDeduplicationStage, ShortCircuitDetectionStage
    )

    # Build zone config from YAML config if available
    zone_config = None
    slot_spacing = 10.0  # Default: larger spacing to avoid overlaps
    max_clearance = 2.5  # Default: conservative for HV boards
    net_class_clearances = {}
    fixed_placements = {}

    # Extract net class clearances from design_rules if available
    if design_rules and hasattr(design_rules, 'net_classes'):
        for name, rules in design_rules.net_classes.items():
            net_class_clearances[name] = rules.clearance

    # Extract/override from config if available
    if config:
        zone_config = getattr(config, 'zones', None)
        slot_config = getattr(config, 'slot_generation', None)
        fixed_placements = getattr(config, 'fixed_positions', {})
        if slot_config and 'spacing_mm' in slot_config:
            slot_spacing = slot_config['spacing_mm']
        
        # Get net class rules from config
        config_rules = getattr(config, 'net_class_rules', None)
        if config_rules:
            for name, rules in config_rules.items():
                if hasattr(rules, 'clearance_mm'):
                    net_class_clearances[name] = rules.clearance_mm
                elif isinstance(rules, dict):
                    net_class_clearances[name] = rules.get('clearance_mm', 0.2)
        
        if net_class_clearances:
            max_clearance = max(net_class_clearances.values()) + 0.3  # Add margin for trace width

    return DeterministicPipeline(stages=[
        # Placement stages
        ZoneGeometryStage(zone_config=zone_config),
        ZoneAssignmentStage(),
        SlotGenerationStage(slot_spacing_mm=slot_spacing),
        ComponentAssignmentStage(slot_spacing=slot_spacing, fixed_placements=fixed_placements),
        ApplyPlacementsStage(),

        # DRC setup
        DRCOracleSetupStage(design_rules=design_rules),

        # Routing
        ClearanceGridStage(
            cell_size_mm=0.25, 
            layer_count=4, 
            max_clearance_mm=max_clearance,
            net_class_clearances=net_class_clearances
        ),
        NetOrderingStage(),
        LayerAssignmentStage(net_classes=config.net_classes if config else None),
        SequentialRoutingStage(design_rules=design_rules),

        # Post-routing cleanup (order matters!)
        TrackDeduplicationStage(),    # Remove duplicate tracks first
        ShortCircuitDetectionStage(), # Remove tracks that short
        ViaDeduplicationStage(),      # Remove duplicate vias
        ViaValidationStage(),         # Remove dangling vias

        # Validation
        DRCValidationStage(),
        ConnectivityValidationStage(),
    ])

def create_legacy_pipeline():
    '''Create legacy pipeline without DRC oracle integration.'''
    from .stages import (
        ZoneGeometryStage, ZoneAssignmentStage, SlotGenerationStage,
        ComponentAssignmentStage, ApplyPlacementsStage,
        ClearanceGridStage, NetOrderingStage,
        LayerAssignmentStage, SequentialRoutingStage,
        DRCValidationStage, ConnectivityValidationStage,
        ViaValidationStage, ViaDeduplicationStage,
        TrackDeduplicationStage
    )

    return DeterministicPipeline(stages=[
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
    ])
