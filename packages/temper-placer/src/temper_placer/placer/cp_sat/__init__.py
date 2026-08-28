"""CP-SAT constraint encoder for PCL constraint types.

Public API surface for the CP-SAT placement solver module.
"""

from temper_placer.placer.cp_sat.audit import (
    AuditReport,
    AuditViolation,
    Placement,
    PlacementAuditor,
)
from temper_placer.placer.cp_sat.constraint_restoration_campaign import (
    RestorationCampaignResult,
    RestorationCampaignStatus,
    RestorationLimits,
    RestorationStage,
    RestorationStageResult,
    RestorationStageStatus,
    default_restoration_stages,
    distance_tier_restoration_stages,
    neighborhood_batched_creepage_constraints,
    run_constraint_restoration_campaign,
)
from temper_placer.placer.cp_sat.creepage_lower_bounds import (
    CreepageLowerBoundReport,
    ThresholdCliqueBound,
    analyze_creepage_lower_bounds,
)
from temper_placer.placer.cp_sat.encoder import (
    UNSUPPORTED_TYPES,
    CpSatPlacementResult,
    EncoderContext,
    encode_constraints,
    solve_placement,
)
from temper_placer.placer.cp_sat.envelope_preparation import (
    PreparedEnvelopeInputs,
    prepare_envelope_inputs,
)
from temper_placer.placer.cp_sat.envelope_solver import (
    EnvelopeBounds,
    EnvelopeSolveResult,
    EnvelopeSolveStatus,
    EnvelopeStatus,
    PairRequirement,
    PartitionPlan,
    solve_envelopes,
)
from temper_placer.placer.cp_sat.feedback import ConstraintDelta, FeedbackClassifier
from temper_placer.placer.cp_sat.gate import AcceptanceGate
from temper_placer.placer.cp_sat.local_subenvelope_solver import (
    ComponentPairRequirement,
    ComponentSpec,
    LocalComponentBounds,
    LocalSubEnvelopeSolveResult,
    LocalSubEnvelopeSolveStatus,
    LocalSubEnvelopeStatus,
    pack_local_sub_envelope,
    solve_local_envelope,
    solve_local_sub_envelope,
)
from temper_placer.placer.cp_sat.loop import LoopResult, PlaceRouteLoop
from temper_placer.placer.cp_sat.model import (
    ComponentVars,
    CpSatModel,
    CpSolverSolution,
    SolveStatus,
)
from temper_placer.placer.cp_sat.production_stripped_instance import (
    ProductionStrippedDiagnostics,
    ProductionStrippedInstance,
    ProductionStrippedProbeReport,
    prepare_production_stripped_instance,
    run_production_stripped_probe,
)
from temper_placer.placer.cp_sat.stripped_creepage_solver import (
    StrippedCreepageSolveResult,
    StrippedCreepageSolveStatus,
    solve_stripped_creepage,
)
from temper_placer.placer.cp_sat.stripped_warm_start import (
    StrippedWarmStartResult,
    solve_production_stripped_instance_warm_start,
    solve_stripped_creepage_warm_start,
)

__all__ = [
    "AcceptanceGate",
    "AuditReport",
    "AuditViolation",
    "ComponentVars",
    "ConstraintDelta",
    "CreepageLowerBoundReport",
    "ComponentPairRequirement",
    "ComponentSpec",
    "EnvelopeBounds",
    "EnvelopeSolveResult",
    "EnvelopeSolveStatus",
    "EnvelopeStatus",
    "PreparedEnvelopeInputs",
    "CpSatPlacementResult",
    "CpSatModel",
    "CpSolverSolution",
    "EncoderContext",
    "FeedbackClassifier",
    "LoopResult",
    "LocalComponentBounds",
    "LocalSubEnvelopeSolveResult",
    "LocalSubEnvelopeSolveStatus",
    "LocalSubEnvelopeStatus",
    "StrippedCreepageSolveResult",
    "StrippedCreepageSolveStatus",
    "ProductionStrippedDiagnostics",
    "ProductionStrippedInstance",
    "ProductionStrippedProbeReport",
    "RestorationCampaignResult",
    "RestorationCampaignStatus",
    "RestorationLimits",
    "RestorationStage",
    "RestorationStageResult",
    "RestorationStageStatus",
    "StrippedWarmStartResult",
    "ThresholdCliqueBound",
    "PlaceRouteLoop",
    "Placement",
    "PlacementAuditor",
    "PairRequirement",
    "PartitionPlan",
    "SolveStatus",
    "solve_placement",
    "UNSUPPORTED_TYPES",
    "encode_constraints",
    "solve_envelopes",
    "pack_local_sub_envelope",
    "solve_local_envelope",
    "solve_local_sub_envelope",
    "solve_stripped_creepage",
    "prepare_production_stripped_instance",
    "run_production_stripped_probe",
    "default_restoration_stages",
    "distance_tier_restoration_stages",
    "neighborhood_batched_creepage_constraints",
    "run_constraint_restoration_campaign",
    "solve_production_stripped_instance_warm_start",
    "solve_stripped_creepage_warm_start",
    "analyze_creepage_lower_bounds",
    "prepare_envelope_inputs",
]
