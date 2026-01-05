from .pipeline import DeterministicPipeline
from .state import BoardState

def create_drc_aware_pipeline(design_rules=None, config=None):
    '''Create pipeline with full DRC integration.'''
    from .stages import (
        ZoneGeometryStage, ZoneAssignmentStage, SlotGenerationStage,
        ComponentAssignmentStage, ApplyPlacementsStage,
        DRCOracleSetupStage, ClearanceGridStage, NetOrderingStage,
        LayerAssignmentStage, SequentialRoutingStage,
        DRCValidationStage, ConnectivityValidationStage
    )
    
    return DeterministicPipeline(stages=[
        # Placement stages
        ZoneGeometryStage(),
        ZoneAssignmentStage(),
        SlotGenerationStage(slot_spacing_mm=7.5),  # Increased from 5.0mm to reduce mask bridges
        ComponentAssignmentStage(),
        ApplyPlacementsStage(),
        
        # DRC setup
        DRCOracleSetupStage(design_rules=design_rules),
        
        # Routing
        ClearanceGridStage(cell_size_mm=0.25, layer_count=4),
        NetOrderingStage(),
        LayerAssignmentStage(net_classes=config.net_classes if config else None),
        SequentialRoutingStage(design_rules=design_rules),
        
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
        DRCValidationStage, ConnectivityValidationStage
    )
    
    return DeterministicPipeline(stages=[
        # Placement stages
        ZoneGeometryStage(),
        ZoneAssignmentStage(),
        SlotGenerationStage(slot_spacing_mm=7.5),  # Increased from 5.0mm to reduce mask bridges
        ComponentAssignmentStage(),
        ApplyPlacementsStage(),
        
        # Routing
        ClearanceGridStage(cell_size_mm=0.25, layer_count=4),
        NetOrderingStage(),
        LayerAssignmentStage(),
        SequentialRoutingStage(), # Use defaults
        
        # Validation
        DRCValidationStage(),
        ConnectivityValidationStage(),
    ])
