"""Deterministic pipeline stage classes.

Shim-debt cleanup (2026-08-20): the seven stage modules that carried
constructor state into ``run`` (``config_attach.py``, ``net_ordering.py``,
``setup.py``, ``zone_geometry.py``, ``slot_generation.py``, ``drc_sweep.py``,
``via_validation.py``) were collapsed onto the generic
:class:`RustFunctionStage` adapter: each class keeps its constructor
signature and attribute surface, and the constructor state is forwarded to
the ``temper-orchestration`` pyfunction as the adapter's ``*fn_args``. The
Rust pyfunction is the single source of truth; ``run`` is the adapter's one
shared implementation.

Two module paths survive as thin re-export shims because a pinned VERBATIM
oracle imports them by module path (the oracle bodies cannot be edited):

- ``stages/config_attach.py``  -- the pinned pipeline oracle
  (``tests/deterministic/_deterministic_pipeline_py_oracle.py``) does
  ``from temper_placer.deterministic.stages.config_attach import
  ConfigAttachStage`` inside its pinned body.
- ``stages/slot_generation.py`` -- the pinned zone-aware oracle
  (``tests/deterministic/_zone_aware_slot_generation_run_py_oracle.py``)
  imports ``SlotGenerationStage`` from that module and SUBCLASSES it (its
  pre-migration ``run`` body also calls ``self._generate_slots_for_zone``,
  so the adapter keeps that Phase-5 leaf-kernel delegation helper).

``stages/zone_geometry.py`` likewise survives, but only as the home of the
``Zone`` dataclass -- a real data type the Rust ``ZoneGeometryStage`` /
``netlist_owned`` marshalling resolves at runtime by importing
``temper_placer.deterministic.stages.zone_geometry``; the stage class moved
here. The other four modules (``net_ordering.py``, ``setup.py``,
``drc_sweep.py``, ``via_validation.py``) were deleted outright.
"""

import temper_design_bundle_python as _tdb
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
from .drc_validation import DRCValidationError, DRCValidationStage
from .fine_pitch_escape import FinePitchEscapeStage
from .hv_lv_partition import HvLvPartitionStage
from .layer_assignment import LayerAssignmentStage
from .phased_component_assignment import PhasedComponentAssignmentStage
from .placement_validation import (
    PlacementValidationError,
    PlacementValidationStage,
    PlacementViolation,
)
from .power_plane import TEMPER_PLANE_LAYERS, PowerPlaneStage

# ============================================================================
# Collapsed constructor-state shims (shim-debt cleanup 2026-08-20).
#
# Each class was previously a whole module under ``stages/`` whose ``run``
# threaded constructor state to a ``temper-orchestration`` pyfunction. The
# class names, constructor signatures and attribute surfaces are preserved
# exactly -- the ``temper-orchestration`` stage factory and the pinned
# U-E pipeline oracle construct these classes by name with the same args --
# but ``run`` is now the single ``RustFunctionStage.run`` implementation
# and the constructor state rides along as the adapter's ``*fn_args``.
# ============================================================================


class ConfigAttachStage(RustFunctionStage):
    """Attach the parsed PlacementConstraints config to BoardState.

    Shim-debt cleanup (2026-08-20): the shim module
    ``stages/config_attach.py`` was collapsed; the run orchestration is
    ``temper-orchestration``'s ``ConfigAttachStage``, reached through
    ``temper_orchestration.run_config_attach``. The module path survives
    only because the pinned pipeline oracle imports the class from it
    (see the package docstring).
    """

    def __init__(self, config) -> None:
        self._config = config
        super().__init__("config_attach", _to.run_config_attach, config)


class NetOrderingStage(RustFunctionStage):
    """Determine the order in which nets are routed.

    EXP-6: Supports explicit net priorities from config to route critical
    nets (USB, SPI) first when the board is least congested.
    """

    def __init__(self, net_priority: dict[str, int] | None = None):
        """Initialize net ordering stage.

        Args:
            net_priority: Optional dict mapping net names to priority (1=highest, 5=default).
                         Lower numbers route first.
        """
        self.net_priority = net_priority or {}
        super().__init__("net_ordering", _to.run_net_ordering, self.net_priority)


class DRCOracleSetupStage(RustFunctionStage):
    """Setup stage for initializing DRCOracle and other common utilities.

    Args:
        design_rules: Design rules configuration
        parsed_pads: Optional list of PadData from kicad_parser. If provided,
            these are used for DRC oracle instead of computing from placements.
            This ensures DRC uses the actual KiCad positions, not optimized placements.
    """

    def __init__(self, design_rules=None, parsed_pads=None):
        self.design_rules = design_rules
        self.parsed_pads = parsed_pads
        super().__init__(
            "drc_oracle_setup", _to.run_drc_oracle_setup, design_rules, parsed_pads
        )


class NetClassSetupStage(RustFunctionStage):
    """Apply net class mapping from config to netlist.

    This stage should run early in the pipeline to ensure net classes
    are properly assigned before routing decisions are made.
    """

    def __init__(self, net_classes=None):
        self.net_classes = net_classes
        super().__init__("net_class_setup", _to.run_net_class_setup, net_classes)


# Alias for backward compatibility (was defined in the deleted setup.py).
SetupStage = DRCOracleSetupStage


class ZoneGeometryStage(RustFunctionStage):
    """Compute the placement zones from the board dimensions and config."""

    def __init__(self, zone_config: list[dict] | None = None):
        self.zone_config = zone_config
        super().__init__("zone_geometry", _to.run_zone_geometry, zone_config)


class SlotGenerationStage(RustFunctionStage):
    """Generate a regular grid of placement slots within each zone."""

    def __init__(self, slot_spacing_mm: float = 5.0):
        self.slot_spacing_mm = slot_spacing_mm
        super().__init__("slot_generation", _to.run_slot_generation, slot_spacing_mm)

    def _generate_slots_for_zone(self, zone, spacing: float) -> list[tuple[float, float]]:
        """Generate a regular grid of placement slots within a zone.

        Kept as a delegation helper: the pinned zone-aware oracle
        (``_zone_aware_slot_generation_run_py_oracle.py``) subclasses this
        stage and calls this method from its own pre-migration ``run`` body.
        The slot-grid walk is the Wave-4 Phase-5 Rust leaf kernel
        (``temper_design_bundle_python.deterministic_stages
        .generate_slots_for_zone``).
        """
        (x_min, y_min), (x_max, y_max) = zone.bounds
        return list(
            _tdb.deterministic_stages.generate_slots_for_zone(x_min, y_min, x_max, y_max, spacing)
        )


class DRCSweepStage(RustFunctionStage):
    """Post-routing DRC sweep that removes violating geometry."""

    def __init__(self, tolerance: float = 0.01):
        """Initialize DRC sweep.

        Args:
            tolerance: Position tolerance in mm for matching geometry
        """
        self.tolerance = tolerance
        super().__init__("drc_sweep", _to.run_drc_sweep, tolerance)


class TrackDeduplicationStage(RustFunctionStage):
    """Remove duplicate track segments."""

    def __init__(self, tolerance_mm: float = 0.05):
        self.tolerance_mm = tolerance_mm
        super().__init__("track_deduplication", _to.run_track_deduplication, tolerance_mm)


class ShortCircuitDetectionStage(RustFunctionStage):
    """Detect and remove tracks that short to other nets."""

    def __init__(self, tolerance_mm: float = 0.1):
        self.tolerance_mm = tolerance_mm
        super().__init__(
            "short_circuit_detection", _to.run_short_circuit_detection, tolerance_mm
        )


class ViaValidationStage(RustFunctionStage):
    """Validates and cleans up vias after routing.

    Removes vias that are not properly connected, which happens when:
    - Routing failed to complete a connection
    - Via was placed optimistically but target layer route failed
    - Layer transition was abandoned mid-route

    Parameters:
        tolerance_mm: Distance tolerance for considering a trace connected to a via.
                     Default 0.1mm accounts for grid snapping and floating point errors.
        require_both_layers: If True (default), removes vias not connected on both layers.
                            If False, keeps vias connected on at least one layer.
    """

    def __init__(self, tolerance_mm: float = 0.1, require_both_layers: bool = True):
        self.tolerance_mm = tolerance_mm
        self.require_both_layers = require_both_layers
        super().__init__(
            "via_validation",
            _to.run_via_validation,
            tolerance_mm,
            require_both_layers,
        )


class ViaDeduplicationStage(RustFunctionStage):
    """Remove duplicate vias at the same position."""

    def __init__(self, tolerance_mm: float = 0.05):
        self.tolerance_mm = tolerance_mm
        super().__init__("via_deduplication", _to.run_via_deduplication, tolerance_mm)


# ============================================================================
# Sprint-1 collapsed parameterless shims (2026-08-19) -- unchanged.
# ============================================================================


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


# Imported after the collapsed classes so ``zone_aware_slot_generation`` can
# resolve ``SlotGenerationStage`` (its base class) from this package's
# partially-initialized namespace.
from .zone_aware_slot_generation import ZoneAwareSlotGenerationStage  # noqa: E402

__all__ = [
    "DRCOracleSetupStage",
    "NetClassSetupStage",
    "SetupStage",
    "ConfigAttachStage",
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
