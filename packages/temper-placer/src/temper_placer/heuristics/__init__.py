"""
Smart initialization heuristics for PCB placement.

This subpackage provides intelligent initial placement heuristics that:
- Reduce optimization time by starting with sensible placements
- Avoid local minima by encoding engineering knowledge
- Produce engineer-like placements that are more reviewable

Heuristics are applied in priority order:
1. Hard constraints: Keep-out zones, board boundaries
2. Structural: Connectors at edges, thermal components at edges
3. Organizational: Module clustering, decoupling cap positioning
4. Style: Signal flow direction, domain separation
"""

from temper_placer.heuristics.base import (
    ComponentPlacement,
    Heuristic,
    HeuristicPriority,
    HeuristicResult,
    PlacementContext,
)
from temper_placer.heuristics.conflict import ConflictResolver, ResolutionStrategy

# Organizational heuristics
from temper_placer.heuristics.organizational import (
    DecouplingCapHeuristic,
    DomainSeparationHeuristic,
    FunctionalModuleClusteringHeuristic,
    PowerFlowTopologyHeuristic,
    classify_power_topology,
    classify_signal_domains,
    identify_decoupling_caps,
    identify_functional_modules,
)
from temper_placer.heuristics.pipeline import HeuristicPipeline, PipelineResult

# Structural heuristics
from temper_placer.heuristics.structural import (
    ConnectorEdgeSnappingHeuristic,
    CriticalLoopHeuristic,
    KeepoutAwarenessHeuristic,
    ThermalEdgePlacementHeuristic,
    create_keepout_mask,
    identify_connectors,
    identify_thermal_components,
)

# Style heuristics
from temper_placer.heuristics.style import (
    SignalFlowPreservationHeuristic,
    StarGroundTopologyHeuristic,
    extract_signal_chains,
    identify_ground_domains,
)


def create_default_pipeline() -> HeuristicPipeline:
    """
    Create a pipeline with all default heuristics registered.

    This sets up a complete pipeline with all standard heuristics
    in the recommended configuration:

    1. HARD: KeepoutAwarenessHeuristic - Creates placement mask
    2. STRUCTURAL: ConnectorEdgeSnappingHeuristic - Connectors on edges
    3. STRUCTURAL: ThermalEdgePlacementHeuristic - Thermal components on edges
    4. STRUCTURAL: CriticalLoopHeuristic - Critical loop clustering
    5. ORGANIZATIONAL: FunctionalModuleClusteringHeuristic - Module clustering
    6. ORGANIZATIONAL: PowerFlowTopologyHeuristic - Power flow arrangement
    7. ORGANIZATIONAL: DecouplingCapHeuristic - Decoupling cap positioning
    8. ORGANIZATIONAL: DomainSeparationHeuristic - Analog/digital separation
    9. STYLE: StarGroundTopologyHeuristic - Star ground arrangement
    10. STYLE: SignalFlowPreservationHeuristic - Signal flow direction

    Returns:
        Configured HeuristicPipeline ready to use.
    """
    from temper_placer.heuristics.conflict import ResolutionStrategy

    pipeline = HeuristicPipeline(
        conflict_strategy=ResolutionStrategy.NUDGE,
        min_spacing_mm=0.5,
    )

    # Register heuristics in priority order
    # HARD constraints
    pipeline.register(KeepoutAwarenessHeuristic())

    # STRUCTURAL constraints
    pipeline.register(ConnectorEdgeSnappingHeuristic())
    pipeline.register(ThermalEdgePlacementHeuristic())
    pipeline.register(CriticalLoopHeuristic())

    # ORGANIZATIONAL constraints
    pipeline.register(FunctionalModuleClusteringHeuristic())
    pipeline.register(PowerFlowTopologyHeuristic())
    pipeline.register(DecouplingCapHeuristic())
    pipeline.register(DomainSeparationHeuristic())

    # STYLE constraints
    pipeline.register(StarGroundTopologyHeuristic())
    pipeline.register(SignalFlowPreservationHeuristic())

    return pipeline


__all__ = [
    # Base classes
    "Heuristic",
    "HeuristicPriority",
    "HeuristicResult",
    "PlacementContext",
    "ComponentPlacement",
    # Pipeline
    "HeuristicPipeline",
    "PipelineResult",
    "ConflictResolver",
    "ResolutionStrategy",
    "create_default_pipeline",
    # Structural heuristics
    "KeepoutAwarenessHeuristic",
    "ConnectorEdgeSnappingHeuristic",
    "ThermalEdgePlacementHeuristic",
    "CriticalLoopHeuristic",
    "create_keepout_mask",
    "identify_connectors",
    "identify_thermal_components",
    # Organizational heuristics
    "FunctionalModuleClusteringHeuristic",
    "PowerFlowTopologyHeuristic",
    "DecouplingCapHeuristic",
    "DomainSeparationHeuristic",
    "identify_functional_modules",
    "classify_power_topology",
    "identify_decoupling_caps",
    "classify_signal_domains",
    # Style heuristics
    "StarGroundTopologyHeuristic",
    "SignalFlowPreservationHeuristic",
    "identify_ground_domains",
    "extract_signal_chains",
]
