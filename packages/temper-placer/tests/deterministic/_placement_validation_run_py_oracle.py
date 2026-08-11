"""
D6 run-orchestration oracle for `deterministic/stages/placement_validation.py`.

Verbatim pre-D6 snapshot of the module at the D6 dispatch base (origin/main
`13525f78`), with ONLY the documented relative-import rewrites below. The body
below `# --- BEGIN PINNED BODY ---` is byte-identical to the module; the D6
Rust port (`temper-orchestration::PlacementValidationStage`) is the
differential subject, pinned by `test_deterministic_d6_rust_differential.py`.
"""

import logging
from dataclasses import dataclass, replace

import temper_drc_rs as _drc

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage

# --- BEGIN PINNED BODY ---

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
        violations = []

        # Get component positions from board
        if not state.board:
            logger.warning("No board in state, skipping placement validation")
            return state

        component_positions = self._get_component_positions(state)

        # Validate proximity constraints
        for constraint in self._get_proximity_constraints():
            violation = self._validate_proximity(constraint, component_positions)
            if violation:
                violations.append(violation)

        # Validate signal-to-HV clearance constraints
        for constraint in self._get_signal_hv_constraints():
            violation = self._validate_signal_hv(constraint, component_positions)
            if violation:
                violations.append(violation)

        # Log results
        self._log_summary(violations)

        # Check for hard violations
        hard_violations = [v for v in violations if v.severity == "error"]
        if self.fail_on_hard_violations and hard_violations:
            raise PlacementValidationError(
                f"{len(hard_violations)} hard placement violations found:\n"
                + "\n".join(f"  - {v.message}" for v in hard_violations)
            )

        # Store violations in state (convert to tuple for frozen dataclass)
        return replace(state, placement_violations=tuple(violations))

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
        """
        if component_ref not in component_positions:
            return None

        comp_pos = component_positions[component_ref]

        # Look up pin offset from parsed pads
        if component_ref in self.parsed_pads:
            pads = self.parsed_pads[component_ref]
            if pin in pads:
                pad_info = pads[pin]
                # Pad position is relative to component origin
                return (comp_pos[0] + pad_info["x"], comp_pos[1] + pad_info["y"])

        # Fallback to component center
        return comp_pos

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
        """
        return _drc.point_to_segment_distance_py(point, seg_start, seg_end)

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
