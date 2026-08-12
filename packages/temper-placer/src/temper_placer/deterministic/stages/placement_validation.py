"""Placement validation stage for HV-signal clearance constraints.

This stage validates that component placements satisfy signal-to-HV clearance
constraints before routing begins. This catches placement issues that would
make safe routing geometrically impossible.

EXP-11: Gate drive signals must route to MOSFET gates without approaching
HV collector/emitter pins within 6mm (IEC 60335-1 creepage).

The pure geometry + constraint kernels are implemented in Rust in the
``temper-drc-rs`` crate (Wave 4 **Phase 5, batch 2** — deterministic leaf
stages): ``_point_to_segment_distance``, ``_validate_proximity`` and
``_validate_signal_hv`` delegate to ``temper_drc_rs``. The parsed-pads
``_get_pin_position`` offset resolution additionally delegates to
``temper_drc_rs.resolve_pin_position_py`` (Wave 4 orchestration-port).

Phase D batch D6 of the Rust Orchestration Engine plan (2026-08-09-001): the
**run orchestration** (the no-board guard, the component-position extraction,
the proximity / signal-HV constraint sweeps, the hard-violation filter, the
``PlacementValidationError`` raise decision + message text and the
``placement_violations`` write) is implemented in Rust
(``temper-orchestration``'s ``PlacementValidationStage`` /
``run_placement_validation``), crossing the FFI once per stage call. This
module keeps the public API: the ``PlacementValidationStage`` /
``PlacementViolation`` / ``PlacementValidationError`` names and the directly
exercised per-constraint helper methods (``_validate_proximity`` /
``_validate_signal_hv`` / ``_get_pin_position`` / ``_get_component_positions``
/ ``_get_proximity_constraints`` / ``_get_signal_hv_constraints`` /
``_point_to_segment_distance`` / ``_log_summary`` — pinned by
``test_drc_leaf_rust_differential.py``) stay as the pre-D6 bodies; the Rust
stage CALLS the validation helpers back on this instance (the D4/D5 mixin
boundary). The pre-migration implementation is pinned VERBATIM in
``tests/deterministic/_placement_validation_run_py_oracle.py``.
"""

import logging
from dataclasses import dataclass

import temper_drc_rs as _drc
import temper_geometry as _tg
import temper_orchestration as _to

from ..state import BoardState
from .base import Stage

logger = logging.getLogger(__name__)


@dataclass
class PlacementViolation:
    """A placement constraint violation."""

    constraint_name: str
    violation_type: str  # "proximity", "hv_clearance", "path_blocked"
    message: str
    severity: str  # "error" or "warning"
    component_a: str | None = None
    component_b: str | None = None
    actual_distance_mm: float | None = None
    required_distance_mm: float | None = None


class PlacementValidationError(Exception):
    """Raised when placement violations exceed configured thresholds."""

    pass


class PlacementValidationStage(Stage):
    """Validates component placements against signal-to-HV clearance constraints.

    This stage runs early in the pipeline (before routing) to catch placement
    issues that would make safe routing impossible.

    Validates:
    1. PlacementProximityConstraint: Pin-to-pin distances
    2. SignalToHVClearance: Signal path feasibility given HV obstacles

    Example constraint:
        Gate driver pin 15 (OUTA) must be within 15mm of Q1 pin 1 (gate),
        and the resulting signal path must maintain 6mm clearance from
        Q1 pins 2-3 (DC_BUS+ and SW_NODE).
    """

    def __init__(
        self,
        constraints: dict | None = None,
        fail_on_hard_violations: bool = True,
        parsed_pads: dict | None = None,
    ):
        """
        Args:
            constraints: Optional dict of placement-validation constraints, e.g.
                {"placement_proximity": [...], "signal_hv_clearances": [...]}
                (uses state.config if None)
            fail_on_hard_violations: If True, raise error on "hard" tier violations
            parsed_pads: Dict of component_ref -> {pin -> (x, y)} positions from KiCad parser
        """
        self.constraints = constraints or {}
        self.fail_on_hard_violations = fail_on_hard_violations
        self.parsed_pads = parsed_pads or {}

    @property
    def name(self) -> str:
        return "placement_validation"

    def run(self, state: BoardState) -> BoardState:
        """Run the placement-validation orchestration in Rust (Phase D D6);
        crosses the FFI once per stage call and surfaces the raise decision as
        the module's ``PlacementValidationError``."""
        out_state, message = _to.run_placement_validation(state, self)
        if message is not None:
            raise PlacementValidationError(message)
        return out_state

    def _get_component_positions(self, state: BoardState) -> dict:
        """Extract component positions from board state."""
        positions = {}
        if state.board and hasattr(state.board, "components"):
            for comp in state.board.components:
                positions[comp.ref] = (comp.x, comp.y)
        return positions

    def _get_pin_position(
        self, component_ref: str, pin: str, component_positions: dict
    ) -> tuple[float, float] | None:
        """Get absolute position of a pin on a component.

        Uses parsed_pads from KiCad parser for accurate pin positions.
        Falls back to component center if pin data not available.

        The parsed-pads offset resolution (the pure compute) lives in the
        ``temper_drc_rs.resolve_pin_position_py`` kernel (Wave 4
        orchestration-port); this method is the marshalling shim.
        """
        return _drc.resolve_pin_position_py(
            component_ref, pin, component_positions, self.parsed_pads
        )

    def _get_proximity_constraints(self):
        """Get proximity constraints from config."""
        return self.constraints.get("placement_proximity", [])

    def _get_signal_hv_constraints(self):
        """Get signal-to-HV clearance constraints from config."""
        return self.constraints.get("signal_hv_clearances", [])

    def _validate_proximity(
        self, constraint, component_positions: dict
    ) -> PlacementViolation | None:
        """Validate a PlacementProximityConstraint."""
        from_pos = self._get_pin_position(
            constraint.from_component, constraint.from_pin, component_positions
        )
        to_pos = self._get_pin_position(
            constraint.to_component, constraint.to_pin, component_positions
        )

        result = _drc.validate_proximity_py(constraint, from_pos, to_pos)
        if result is None or not result[0]:
            return None
        _flag, severity, actual, required, message, comp_a, comp_b = result

        if severity == "warning" and (from_pos is None or to_pos is None):
            return PlacementViolation(
                constraint_name=constraint.name,
                violation_type="missing_component",
                message=message,
                severity=severity,
                component_a=comp_a or None,
                component_b=comp_b or None,
            )

        return PlacementViolation(
            constraint_name=constraint.name,
            violation_type="proximity",
            message=message,
            severity=severity,
            component_a=comp_a or None,
            component_b=comp_b or None,
            actual_distance_mm=actual,
            required_distance_mm=required,
        )

    def _validate_signal_hv(
        self, constraint, component_positions: dict
    ) -> PlacementViolation | None:
        """Validate a SignalToHVClearance constraint.

        Checks that the signal path from signal_pin to target_pin doesn't
        pass too close to any HV pins.

        The validation uses a simplified geometric check:
        1. Calculate straight-line distance from signal_pin to target_pin
        2. For each HV pin, calculate distance from HV pin to the signal line segment
        3. If any HV pin is within required_clearance_mm of the line, violation
        """
        signal_pos = self._get_pin_position(
            constraint.signal_component, constraint.signal_pin, component_positions
        )
        target_pos = self._get_pin_position(
            constraint.target_component, constraint.target_pin, component_positions
        )

        hv_positions = []
        for hv_pin in constraint.hv_pins:
            hv_pos = self._get_pin_position(
                constraint.hv_component, hv_pin, component_positions
            )
            if hv_pos:
                hv_positions.append((hv_pin, hv_pos))

        result = _drc.validate_signal_hv_py(
            constraint, signal_pos, target_pos, hv_positions
        )
        if result is None or not result[0]:
            return None
        _flag, severity, actual, required, message, comp_a, comp_b, violation_type = result

        if violation_type == "missing_component":
            return PlacementViolation(
                constraint_name=constraint.name,
                violation_type=violation_type,
                message=message,
                severity=severity,
            )

        return PlacementViolation(
            constraint_name=constraint.name,
            violation_type=violation_type,
            message=message,
            severity=severity,
            component_a=comp_a or None,
            component_b=comp_b or None,
            actual_distance_mm=actual,
            required_distance_mm=required,
        )

    def _point_to_segment_distance(
        self,
        point: tuple[float, float],
        seg_start: tuple[float, float],
        seg_end: tuple[float, float],
    ) -> float:
        """Calculate minimum distance from a point to a line segment.

        Uses projection formula to find closest point on segment.

        Issue #987: delegates to temper-geometry's canonical kernel (the
        temper_drc_rs binding this used to call was deleted in the dedupe).
        """
        return _tg.point_to_segment_distance_py(*point, *seg_start, *seg_end)

    def _log_summary(self, violations: list[PlacementViolation]):
        if not violations:
            logger.info("Placement validation passed: 0 violations")
            return

        errors = [v for v in violations if v.severity == "error"]
        warnings = [v for v in violations if v.severity == "warning"]

        if errors:
            logger.error(f"Placement validation: {len(errors)} errors, {len(warnings)} warnings")
            for v in errors:
                logger.error(f"  [ERROR] {v.message}")
        elif warnings:
            logger.warning(f"Placement validation: {len(warnings)} warnings")

        for v in warnings:
            logger.warning(f"  [WARN] {v.message}")
