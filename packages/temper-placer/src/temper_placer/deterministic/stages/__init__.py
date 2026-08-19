import temper_orchestration as _to

from .base import RustFunctionStage
from .clearance_grid import ClearanceGridStage
from .component_assignment import ComponentAssignmentStage
from .connectivity_validation import (
    ConnectivityValidationError,
    ConnectivityValidationStage,
    ConnectivityViolation,
)
from .courtyard_check import CourtyardCheckStage
from .drc_sweep import DRCSweepStage, ShortCircuitDetectionStage, TrackDeduplicationStage
from .drc_validation import DRCValidationError, DRCValidationStage
from .fine_pitch_escape import FinePitchEscapeStage
from .hv_lv_partition import HvLvPartitionStage
from .layer_assignment import LayerAssignmentStage
from .net_ordering import NetOrderingStage
from .phased_component_assignment import PhasedComponentAssignmentStage
from .placement_validation import (
    PlacementValidationError,
    PlacementValidationStage,
    PlacementViolation,
)
from .power_plane import TEMPER_PLANE_LAYERS, PowerPlaneStage
from .setup import DRCOracleSetupStage, NetClassSetupStage
from .slot_generation import SlotGenerationStage
from .via_validation import ViaDeduplicationStage, ViaValidationStage
from .zone_aware_slot_generation import ZoneAwareSlotGenerationStage
from .zone_geometry import ZoneGeometryStage


class ApplyPlacementsStage(RustFunctionStage):
    """Apply placements from BoardState to Component.initial_position.

    Shim-debt cleanup (2026-08-19): the one-line shim module
    ``stages/apply_placements.py`` was deleted; the run orchestration is
    ``temper-orchestration``'s ``ApplyPlacementsStage`` (Phase D D7),
    reached through ``temper_orchestration.run_apply_placements``. This
    class survives by name because the pinned U-E pipeline oracle and the
    ``temper-orchestration`` stage factory construct it with no arguments.
    """

    def __init__(self) -> None:
        super().__init__("apply_placements", _to.run_apply_placements)


class ZoneAssignmentStage(RustFunctionStage):
    """Assign components to zones based on net classes and component types.

    Shim-debt cleanup (2026-08-19): the one-line shim module
    ``stages/zone_assignment.py`` was deleted; the run orchestration is
    ``temper-orchestration``'s ``ZoneAssignmentStage`` (Phase D D2), reached
    through ``temper_orchestration.run_zone_assignment``. This class
    survives by name because the pinned U-E pipeline oracle and the
    ``temper-orchestration`` stage factory construct it with no arguments.
    """

    def __init__(self) -> None:
        super().__init__("zone_assignment", _to.run_zone_assignment)

__all__ = [
    "DRCOracleSetupStage",
    "NetClassSetupStage",
    "ZoneAssignmentStage",
    "ZoneGeometryStage",
    "SlotGenerationStage",
    "ZoneAwareSlotGenerationStage",
    "ComponentAssignmentStage",
    "PhasedComponentAssignmentStage",
    "ApplyPlacementsStage",
    "ClearanceGridStage",
    "NetOrderingStage",
    "LayerAssignmentStage",
    "PowerPlaneStage",
    "TEMPER_PLANE_LAYERS",
    "DRCValidationStage",
    "DRCValidationError",
    "ConnectivityValidationStage",
    "ConnectivityViolation",
    "ConnectivityValidationError",
    "CourtyardCheckStage",
    "ViaValidationStage",
    "ViaDeduplicationStage",
    "DRCSweepStage",
    "TrackDeduplicationStage",
    "ShortCircuitDetectionStage",
    "FinePitchEscapeStage",
    "PlacementValidationStage",
    "PlacementViolation",
    "PlacementValidationError",
    "HvLvPartitionStage",
]
