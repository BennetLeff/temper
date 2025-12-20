"""
Preflight feasibility checker (temper-l65.6).

Performs fast feasibility checking without full optimization to catch
infeasible designs early. The preflight checks run in order (fail-fast):

1. Component Area - Total area fits on board
2. Constraint Satisfiability - No contradictory constraints
3. Clearance Feasibility - Required clearances achievable
4. Layer Assignment - Nets can be assigned to layers
5. Routing Channels - Basic channel capacity exists

Example usage:
    >>> from temper_placer.pipeline.preflight import PreflightChecker
    >>>
    >>> checker = PreflightChecker()
    >>> report = checker.run(board, netlist, constraints, fab_preset)
    >>> if report.passed:
    ...     print("Preflight OK, proceed with optimization")
    >>> else:
    ...     print(report.summary())
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol
import time


class PreflightResult(Enum):
    """Result of a preflight check.

    Attributes:
        PASS: Check passed, no issues
        WARN: Check passed with warnings
        FAIL: Check failed, design infeasible
    """

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class PreflightCheck:
    """Single preflight check result.

    Attributes:
        name: Name of the check
        result: Pass/warn/fail result
        message: Human-readable result message
        details: Optional detailed information
        time_ms: Execution time in milliseconds
    """

    name: str
    result: PreflightResult
    message: str
    details: dict[str, Any] | None = None
    time_ms: float = 0.0


@dataclass
class PreflightReport:
    """Complete preflight check report.

    Attributes:
        checks: List of individual check results
        overall: Overall pass/warn/fail result
        total_time_ms: Total execution time in milliseconds
    """

    checks: list[PreflightCheck]
    overall: PreflightResult
    total_time_ms: float

    @property
    def passed(self) -> bool:
        """True if preflight passed (not FAIL)."""
        return self.overall != PreflightResult.FAIL

    def summary(self) -> str:
        """Generate human-readable summary.

        Returns:
            Formatted string with all check results.
        """
        lines = ["Preflight Checks:"]
        icons = {
            PreflightResult.PASS: "[OK]",
            PreflightResult.WARN: "[WARN]",
            PreflightResult.FAIL: "[FAIL]",
        }
        for check in self.checks:
            icon = icons[check.result]
            lines.append(f"  {icon} {check.name}: {check.message}")
        lines.append(f"\nOverall: {self.overall.value.upper()} ({self.total_time_ms:.1f}ms)")
        return "\n".join(lines)


# Protocol definitions for type hints (duck typing)
class BoardLike(Protocol):
    """Protocol for board-like objects."""

    width: float
    height: float
    keepouts: list[Any]


class ComponentLike(Protocol):
    """Protocol for component-like objects."""

    ref: str
    width: float
    height: float


class NetlistLike(Protocol):
    """Protocol for netlist-like objects."""

    components: list[Any]
    nets: list[Any]


class ConstraintsLike(Protocol):
    """Protocol for constraints-like objects."""

    constraints: list[Any]


class FabPresetLike(Protocol):
    """Protocol for fab preset-like objects."""

    min_clearance: float


class PreflightChecker:
    """Fast feasibility checker for placement pipeline.

    Performs multiple checks to determine if a design is feasible
    before running expensive optimization.
    """

    def __init__(self):
        """Initialize the preflight checker."""
        pass

    def run(
        self,
        board: BoardLike,
        netlist: NetlistLike,
        constraints: ConstraintsLike,
        fab_preset: FabPresetLike,
    ) -> PreflightReport:
        """Run all preflight checks.

        Args:
            board: Board definition with dimensions and keepouts.
            netlist: Netlist with components and nets.
            constraints: Constraint collection.
            fab_preset: Fabrication preset with clearances.

        Returns:
            PreflightReport with all check results.
        """
        start_time = time.time()
        results = []

        # Check 1: Component area
        results.append(self._check_component_area(board, netlist))

        # Check 2: Constraint satisfiability
        results.append(self._check_constraint_satisfiability(constraints))

        # Check 3: Clearance feasibility
        results.append(self._check_clearance_feasibility(board, netlist, constraints))

        # Check 4: Layer assignment (simplified)
        results.append(self._check_layer_assignment(netlist, constraints))

        # Check 5: Routing channels (simplified)
        results.append(self._check_routing_channels(board, netlist))

        # Determine overall result
        if any(r.result == PreflightResult.FAIL for r in results):
            overall = PreflightResult.FAIL
        elif any(r.result == PreflightResult.WARN for r in results):
            overall = PreflightResult.WARN
        else:
            overall = PreflightResult.PASS

        total_time = (time.time() - start_time) * 1000

        return PreflightReport(
            checks=results,
            overall=overall,
            total_time_ms=total_time,
        )

    def _check_component_area(self, board: BoardLike, netlist: NetlistLike) -> PreflightCheck:
        """Check if components fit on board.

        Args:
            board: Board definition.
            netlist: Netlist with components.

        Returns:
            PreflightCheck result.
        """
        start = time.time()

        # Calculate total component area
        total_area = sum(c.width * c.height for c in netlist.components)

        # Calculate board area
        board_area = board.width * board.height

        # Subtract keepout zones
        keepout_area = 0.0
        for keepout in board.keepouts:
            if hasattr(keepout, "area"):
                keepout_area += keepout.area
            elif hasattr(keepout, "width") and hasattr(keepout, "height"):
                keepout_area += keepout.width * keepout.height

        usable_area = board_area - keepout_area

        # Calculate fill ratio
        fill_ratio = total_area / usable_area if usable_area > 0 else 1.0

        # Determine result
        if fill_ratio > 0.85:
            result = PreflightResult.FAIL
            message = (
                f"Component area ({total_area:.1f}mm²) exceeds 85% of "
                f"usable board area ({usable_area:.1f}mm²)"
            )
        elif fill_ratio > 0.70:
            result = PreflightResult.WARN
            message = f"Component fill ratio {fill_ratio:.0%} is high (>70%)"
        else:
            result = PreflightResult.PASS
            message = f"Component fill ratio {fill_ratio:.0%} OK"

        return PreflightCheck(
            name="Component Area",
            result=result,
            message=message,
            details={
                "total_area": total_area,
                "usable_area": usable_area,
                "fill_ratio": fill_ratio,
            },
            time_ms=(time.time() - start) * 1000,
        )

    def _check_constraint_satisfiability(self, constraints: ConstraintsLike) -> PreflightCheck:
        """Check for contradictory constraints.

        Args:
            constraints: Constraint collection.

        Returns:
            PreflightCheck result.
        """
        start = time.time()
        contradictions = []

        # Check for adjacent + separated on same pair
        constraint_list = constraints.constraints
        for i, c1 in enumerate(constraint_list):
            for c2 in constraint_list[i + 1 :]:
                if self._is_contradiction(c1, c2):
                    contradictions.append(
                        f"{getattr(c1, 'a', 'X')}-{getattr(c1, 'b', 'Y')}: "
                        f"adjacent({getattr(c1, 'max_distance', 0)}mm) conflicts with "
                        f"separated({getattr(c2, 'min_distance', 0)}mm)"
                    )

        if contradictions:
            return PreflightCheck(
                name="Constraint Satisfiability",
                result=PreflightResult.FAIL,
                message=f"Found {len(contradictions)} contradiction(s)",
                details={"contradictions": contradictions},
                time_ms=(time.time() - start) * 1000,
            )

        return PreflightCheck(
            name="Constraint Satisfiability",
            result=PreflightResult.PASS,
            message="No contradictions found",
            time_ms=(time.time() - start) * 1000,
        )

    def _is_contradiction(self, c1: Any, c2: Any) -> bool:
        """Check if two constraints contradict each other.

        Args:
            c1: First constraint.
            c2: Second constraint.

        Returns:
            True if constraints contradict.
        """
        type1 = getattr(c1, "constraint_type", "")
        type2 = getattr(c2, "constraint_type", "")

        # Check adjacent vs separated contradiction
        if type1 == "adjacent" and type2 == "separated":
            if self._same_pair(c1, c2):
                max_dist = getattr(c1, "max_distance", float("inf"))
                min_dist = getattr(c2, "min_distance", 0)
                return max_dist < min_dist
        elif type1 == "separated" and type2 == "adjacent":
            if self._same_pair(c1, c2):
                max_dist = getattr(c2, "max_distance", float("inf"))
                min_dist = getattr(c1, "min_distance", 0)
                return max_dist < min_dist

        return False

    def _same_pair(self, c1: Any, c2: Any) -> bool:
        """Check if two constraints reference the same component pair.

        Args:
            c1: First constraint.
            c2: Second constraint.

        Returns:
            True if same pair (order independent).
        """
        a1, b1 = getattr(c1, "a", ""), getattr(c1, "b", "")
        a2, b2 = getattr(c2, "a", ""), getattr(c2, "b", "")
        return {a1, b1} == {a2, b2} and bool(a1) and bool(b1)

    def _check_clearance_feasibility(
        self,
        board: BoardLike,
        netlist: NetlistLike,
        constraints: ConstraintsLike,
    ) -> PreflightCheck:
        """Check if required clearances are achievable.

        Args:
            board: Board definition.
            netlist: Netlist with components.
            constraints: Constraint collection.

        Returns:
            PreflightCheck result.
        """
        start = time.time()
        issues = []

        # Find max required clearance
        max_clearance = 0.15  # Default fab clearance
        for c in constraints.constraints:
            if getattr(c, "constraint_type", "") == "separated":
                min_dist = getattr(c, "min_distance", 0)
                max_clearance = max(max_clearance, min_dist)

        # Simple check: can we fit components + clearance?
        if max_clearance > 0:
            # Get total component width (simplified)
            total_width = sum(c.width for c in netlist.components)

            # Rough estimate: need at least space for components + some clearance
            min_required_width = total_width * 0.3 + max_clearance

            if min_required_width > board.width:
                issues.append(
                    f"Required clearance ({max_clearance}mm) may not fit on "
                    f"board width ({board.width}mm)"
                )

        if issues:
            return PreflightCheck(
                name="Clearance Feasibility",
                result=PreflightResult.WARN,
                message=issues[0],
                details={"issues": issues, "max_clearance": max_clearance},
                time_ms=(time.time() - start) * 1000,
            )

        return PreflightCheck(
            name="Clearance Feasibility",
            result=PreflightResult.PASS,
            message="Clearance requirements achievable",
            time_ms=(time.time() - start) * 1000,
        )

    def _check_layer_assignment(
        self, netlist: NetlistLike, constraints: ConstraintsLike
    ) -> PreflightCheck:
        """Check if nets can be assigned to layers.

        Args:
            netlist: Netlist with nets.
            constraints: Constraint collection.

        Returns:
            PreflightCheck result.
        """
        start = time.time()

        # Simple check: count HV nets
        hv_net_count = sum(
            1
            for net in netlist.nets
            if "HV" in getattr(net, "name", "") or "DC_BUS" in getattr(net, "name", "")
        )

        # Very rough capacity estimate
        l1_capacity = 50

        if hv_net_count > l1_capacity:
            return PreflightCheck(
                name="Layer Assignment",
                result=PreflightResult.WARN,
                message=f"High HV net count ({hv_net_count}) may congest L1",
                details={"hv_nets": hv_net_count},
                time_ms=(time.time() - start) * 1000,
            )

        return PreflightCheck(
            name="Layer Assignment",
            result=PreflightResult.PASS,
            message="Layer assignment feasible",
            time_ms=(time.time() - start) * 1000,
        )

    def _check_routing_channels(self, board: BoardLike, netlist: NetlistLike) -> PreflightCheck:
        """Check if basic routing channels exist.

        Args:
            board: Board definition.
            netlist: Netlist with components.

        Returns:
            PreflightCheck result.
        """
        start = time.time()

        if not netlist.components:
            return PreflightCheck(
                name="Routing Channels",
                result=PreflightResult.PASS,
                message="No components to route",
                time_ms=(time.time() - start) * 1000,
            )

        # Calculate average component size
        total_area = sum(c.width * c.height for c in netlist.components)
        avg_component_area = total_area / len(netlist.components)
        avg_size = avg_component_area**0.5

        # Minimum channel width for routing
        min_channel_width = 1.0  # mm

        # Grid-based capacity estimate
        grid_size = avg_size + min_channel_width
        components_per_row = int(board.width / grid_size) if grid_size > 0 else 0
        components_per_col = int(board.height / grid_size) if grid_size > 0 else 0
        grid_capacity = components_per_row * components_per_col

        if grid_capacity < len(netlist.components):
            return PreflightCheck(
                name="Routing Channels",
                result=PreflightResult.WARN,
                message=(
                    f"Limited routing channel space "
                    f"(capacity ~{grid_capacity}, need {len(netlist.components)})"
                ),
                details={
                    "grid_capacity": grid_capacity,
                    "component_count": len(netlist.components),
                },
                time_ms=(time.time() - start) * 1000,
            )

        return PreflightCheck(
            name="Routing Channels",
            result=PreflightResult.PASS,
            message="Routing channels available",
            time_ms=(time.time() - start) * 1000,
        )
