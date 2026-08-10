# ORACLE COPY -- DO NOT EDIT, DO NOT "FIX".
#
# Verbatim copy of the bodies of
#   packages/temper-placer/src/temper_placer/pipeline/convergence.py
#   packages/temper-placer/src/temper_placer/pipeline/preflight.py
#   packages/temper-placer/src/temper_placer/pipeline/derivation.py
# as they existed at commit 68ea250f (origin/main, Wave-4 pipeline-feasibility
# dispatch base).
#
# This is the R1a behavioural oracle for the Rust port in
# packages/temper-orchestration/src/feasibility.rs. It must keep the ORIGINAL
# pure-Python semantics forever, including any warts. If a differential test
# fails, the Rust side is wrong until proven otherwise -- never edit this file
# to make a test pass.
#
# test_oracle_body_matches_pinned_digest (in
# tests/pipeline/test_pipeline_feasibility_rust_differential.py) recomputes
# the sha256 of everything below the marker and fails if this file drifts.
#
# Documented rewrites (the only differences from the pinned modules):
#   - derivation.py's ``from __future__ import annotations`` is hoisted to
#     the top of THIS file (a future import is only legal at module top;
#     it applies to the whole file and changes no semantics).
#   - the three module bodies are concatenated in dependency order with a
#     section separator comment; every other statement is byte-identical.
#
# --- BEGIN PINNED BODY ---
from __future__ import annotations

# ============================================================================
# SECTION: pipeline/convergence.py (verbatim)
# ============================================================================
"""Convergence criteria and early termination for pipeline.

This module defines when the pipeline should stop iterating, including:
- Success conditions (all phases pass, routing verified, manufacturing OK)
- Failure conditions (max iterations, timeout, infeasibility, stagnation)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class TerminationReason(Enum):
    """Enumeration of reasons why the pipeline terminated.

    Attributes:
        SUCCESS: All phases completed successfully
        MAX_ITERATIONS: Hit maximum iteration limit
        TIMEOUT: Exceeded total time budget
        INFEASIBLE: Detected fundamentally unsolvable constraint set
        NO_PROGRESS: Loss not improving (stagnation)
        USER_ABORT: User cancelled the pipeline
    """

    SUCCESS = "success"
    MAX_ITERATIONS = "max_iterations"
    TIMEOUT = "timeout"
    INFEASIBLE = "infeasible"
    NO_PROGRESS = "no_progress"
    USER_ABORT = "user_abort"
    ROUTABILITY_REGRESSION = "routability_regression"
    ROUTABILITY_CONVERGED = "routability_converged"


@dataclass
class ConvergenceCriteria:
    """Define when the pipeline should stop.

    Attributes:
        max_iterations: Maximum total pipeline iterations
        max_refinement_iterations: Maximum placement-routing refinement loops
        timeout_seconds: Total time budget in seconds
        phase_timeout_seconds: Maximum time for any single phase
        max_overlap_mm2: Maximum allowed component overlap area
        max_boundary_violation_mm: Maximum allowed boundary violation
        min_routing_completion: Minimum routing completion ratio (0.0 to 1.0)
        min_manufacturing_margin_mm: Minimum manufacturing margin
        min_loss_improvement: Minimum fractional improvement to count as progress
        stagnation_epochs: Epochs without improvement before declaring stagnation
    """

    # Iteration limits
    max_iterations: int = 5
    max_refinement_iterations: int = 3

    # Time limits
    timeout_seconds: float = 600.0  # 10 minutes total
    phase_timeout_seconds: float = 120.0  # 2 minutes per phase

    # Success thresholds
    max_overlap_mm2: float = 0.01
    max_boundary_violation_mm: float = 0.01
    min_routing_completion: float = 1.0  # 100%
    min_manufacturing_margin_mm: float = 0.05

    # Progress detection
    min_loss_improvement: float = 0.001  # 0.1% improvement
    stagnation_epochs: int = 500  # Epochs without improvement


@dataclass
class ConvergenceState:
    """Track convergence during pipeline execution.

    Attributes:
        start_time: When the pipeline started
        iteration: Current iteration count
        loss_history: History of loss values
        best_loss: Best (lowest) loss seen so far
        epochs_since_improvement: Epochs since meaningful loss improvement
        terminated: Whether termination has been triggered
        termination_reason: Why termination occurred
        failure_message: Human-readable failure description
    """

    start_time: datetime

    # Iteration tracking
    iteration: int = 0

    # Loss history
    loss_history: list[float] = field(default_factory=list)
    best_loss: float = float("inf")
    epochs_since_improvement: int = 0

    # Status
    terminated: bool = False
    termination_reason: TerminationReason | None = None
    failure_message: str | None = None


class ConvergenceChecker:
    """Check if the pipeline should terminate.

    This class tracks convergence state and provides methods to check
    various termination conditions.

    Usage:
        criteria = ConvergenceCriteria(max_iterations=5)
        checker = ConvergenceChecker(criteria)

        for iteration in range(100):
            checker.increment_iteration()

            # Record loss for stagnation detection
            checker.record_loss(current_loss)

            # Check all termination conditions
            if checker.check_all():
                print(f"Terminated: {checker.state.termination_reason}")
                break

            # Check success with metrics
            metrics = {"overlap_mm2": 0.0, "routing_completion": 1.0, ...}
            if checker.check_success(metrics):
                print("Success!")
                break
    """

    def __init__(self, criteria: ConvergenceCriteria):
        """Initialize the convergence checker.

        Args:
            criteria: Convergence criteria to use for checks
        """
        self.criteria = criteria
        self.state = ConvergenceState(start_time=datetime.now())

    def check_iteration_limit(self) -> bool:
        """Check if iteration limit has been reached.

        Returns:
            True if should terminate due to iteration limit.
        """
        if self.state.iteration >= self.criteria.max_iterations:
            self.state.terminated = True
            self.state.termination_reason = TerminationReason.MAX_ITERATIONS
            return True
        return False

    def check_timeout(self) -> bool:
        """Check if timeout has been exceeded.

        Returns:
            True if should terminate due to timeout.
        """
        elapsed = self.get_elapsed_seconds()
        if elapsed >= self.criteria.timeout_seconds:
            self.state.terminated = True
            self.state.termination_reason = TerminationReason.TIMEOUT
            return True
        return False

    def get_elapsed_seconds(self) -> float:
        """Get elapsed time since pipeline start.

        Returns:
            Elapsed time in seconds.
        """
        return (datetime.now() - self.state.start_time).total_seconds()

    def record_loss(self, loss: float) -> None:
        """Record a loss value for progress tracking.

        Args:
            loss: Current loss value
        """
        self.state.loss_history.append(loss)

        # Check if this is an improvement
        if self.state.best_loss == float("inf"):
            # First loss value
            self.state.best_loss = loss
            self.state.epochs_since_improvement = 0
        else:
            # Check for meaningful improvement
            improvement = (self.state.best_loss - loss) / self.state.best_loss
            if improvement >= self.criteria.min_loss_improvement:
                self.state.best_loss = loss
                self.state.epochs_since_improvement = 0
            else:
                self.state.epochs_since_improvement += 1

    def check_stagnation(self) -> bool:
        """Check if optimization has stagnated.

        Returns:
            True if should terminate due to stagnation.
        """
        if len(self.state.loss_history) == 0:
            return False

        if self.state.epochs_since_improvement >= self.criteria.stagnation_epochs:
            self.state.terminated = True
            self.state.termination_reason = TerminationReason.NO_PROGRESS
            return True
        return False

    def check_success(self, metrics: dict[str, float]) -> bool:
        """Check if success thresholds are met.

        Args:
            metrics: Dictionary of metric values:
                - overlap_mm2: Total component overlap area
                - boundary_violation_mm: Maximum boundary violation
                - routing_completion: Routing completion ratio (0.0 to 1.0)
                - manufacturing_margin_mm: Minimum manufacturing margin

        Returns:
            True if all success thresholds are met.
        """
        # Check overlap
        overlap = metrics.get("overlap_mm2", float("inf"))
        if overlap > self.criteria.max_overlap_mm2:
            return False

        # Check boundary
        boundary = metrics.get("boundary_violation_mm", float("inf"))
        if boundary > self.criteria.max_boundary_violation_mm:
            return False

        # Check routing
        routing = metrics.get("routing_completion", 0.0)
        if routing < self.criteria.min_routing_completion:
            return False

        # Check manufacturing margin
        margin = metrics.get("manufacturing_margin_mm", 0.0)
        if margin < self.criteria.min_manufacturing_margin_mm:
            return False

        # All thresholds passed
        self.state.terminated = True
        self.state.termination_reason = TerminationReason.SUCCESS
        return True

    def check_all(self) -> bool:
        """Check all termination conditions.

        Checks in order:
        1. Already terminated (infeasible, user abort)
        2. Iteration limit
        3. Timeout
        4. Stagnation

        Returns:
            True if any termination condition is met.
        """
        # Already terminated?
        if self.state.terminated:
            return True

        # Check conditions
        if self.check_iteration_limit():
            return True
        if self.check_timeout():
            return True
        return bool(self.check_stagnation())

    def increment_iteration(self) -> None:
        """Increment the iteration count."""
        self.state.iteration += 1

    def reset(self) -> None:
        """Reset convergence state for a fresh run."""
        self.state = ConvergenceState(start_time=datetime.now())

    def mark_infeasible(self, message: str) -> None:
        """Mark the problem as infeasible.

        Args:
            message: Human-readable description of why it's infeasible
        """
        self.state.terminated = True
        self.state.termination_reason = TerminationReason.INFEASIBLE
        self.state.failure_message = message

    def mark_user_abort(self) -> None:
        """Mark the pipeline as aborted by user."""
        self.state.terminated = True
        self.state.termination_reason = TerminationReason.USER_ABORT
        self.state.failure_message = "User aborted pipeline"

    def check_routability_regression(
        self,
        routed_nets: frozenset[str],
        total_nets: int,
        previous_routed_nets: frozenset[str] | None = None,
        regression_threshold: float = 0.95,
        stall_limit: int = 2,
    ) -> bool:
        """Check for routability regression or convergence.

        Uses net-set identity (not aggregate count) to detect:
        - REGRESSION: a previously-routed net stopped routing
        - CONVERGED: identical routed nets for stall_limit consecutive iterations

        Args:
            routed_nets: Nets that routed in the current iteration.
            total_nets: Total number of nets to route.
            previous_routed_nets: Nets that routed in the previous iteration.
            regression_threshold: Routability ratio below best-so-far that
                triggers REGRESSION (default 0.95 = 5% drop).
            stall_limit: Consecutive identical-net-set iterations to declare
                CONVERGED (default 2).

        Returns:
            True if the loop should terminate (regression or convergence).
        """
        current_ratio = len(routed_nets) / max(total_nets, 1)

        if self.state._best_routed_nets is None:
            self.state._best_routed_nets = routed_nets
            self.state._best_routability = current_ratio
            self.state._stall_count = 0
            return False

        best_routed: frozenset[str] = self.state._best_routed_nets
        best_ratio: float | None = self.state._best_routability

        # Regression: routability ratio dropped below threshold
        if current_ratio < best_ratio * regression_threshold:
            lost_nets = best_routed - routed_nets
            self.state.terminated = True
            self.state.termination_reason = TerminationReason.ROUTABILITY_REGRESSION
            self.state.failure_message = (
                f"Routability regressed: {current_ratio:.3f} < "
                f"{best_ratio * regression_threshold:.3f} (threshold). "
                + (f"Lost nets: {sorted(lost_nets)}" if lost_nets else "")
            )
            return True

        # Convergence: identical net set for stall_limit consecutive iterations
        if previous_routed_nets is not None and routed_nets == previous_routed_nets:
            self.state._stall_count += 1
            if self.state._stall_count >= stall_limit:
                self.state.terminated = True
                self.state.termination_reason = TerminationReason.ROUTABILITY_CONVERGED
                self.state.failure_message = (
                    f"Routability converged: {len(routed_nets)}/{total_nets} nets "
                    f"routed with identical net set for {stall_limit} iterations"
                )
                return True
        else:
            self.state._stall_count = 0

        # Improvement: update best
        if current_ratio > (best_ratio or 0.0):
            self.state._best_routed_nets = routed_nets
            self.state._best_routability = current_ratio

        return False


def is_converged(current_results: dict, previous_results: dict | None) -> bool:
    """Check if routing results have converged.

    Converged if:
    1. Perfect routing achieved.
    2. Results are identical to previous iteration (stagnation).
    """
    if not current_results:
        return False

    # 1. Look for perfect routing
    all_success = all(r.success for r in current_results.values())
    if all_success:
        return True

    if previous_results is None:
        return False

    # 2. Check for stagnation (identical success rate and total length)
    # Using length as proxy for path change
    curr_len = sum(r.length for r in current_results.values())
    prev_len = sum(r.length for r in previous_results.values())

    curr_succ = sum(1 for r in current_results.values() if r.success)
    prev_succ = sum(1 for r in previous_results.values() if r.success)

    return bool(curr_succ == prev_succ and abs(curr_len - prev_len) < 1e-06)

# ============================================================================
# SECTION: pipeline/preflight.py (verbatim)
# ============================================================================
"""
Preflight feasibility checker (temper-l65.6).

Performs fast feasibility checking without full optimization to catch
infeasible designs early.
"""

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class PreflightResult(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class PreflightCheck:
    name: str
    result: PreflightResult
    message: str
    details: dict[str, Any] | None = None
    time_ms: float = 0.0


@dataclass
class PreflightReport:
    checks: list[PreflightCheck]
    overall: PreflightResult
    total_time_ms: float

    @property
    def passed(self) -> bool:
        return self.overall != PreflightResult.FAIL

    def summary(self) -> str:
        lines = ["Preflight Checks:"]
        icons = {
            PreflightResult.PASS: "[OK]",
            PreflightResult.WARN: "[WARN]",
            PreflightResult.FAIL: "[FAIL]",
        }
        for check in self.checks:
            lines.append(f"  {icons[check.result]} {check.name}: {check.message}")
        lines.append(f"\nOverall: {self.overall.value.upper()} ({self.total_time_ms:.1f}ms)")
        return "\n".join(lines)


class BoardLike(Protocol):
    width: float
    height: float
    keepouts: list[Any]


class NetlistLike(Protocol):
    components: list[Any]
    nets: list[Any]


class PreflightChecker:
    def run(
        self, board: BoardLike, netlist: NetlistLike, constraints: Any, _fab_preset: Any
    ) -> PreflightReport:
        start_time = time.time()
        results = []
        results.append(self._check_layer_count(board))
        results.append(self._check_component_area(board, netlist))
        results.append(self._check_constraint_satisfiability(netlist, constraints))
        results.append(self._check_zone_capacity(board, netlist))
        results.append(self._check_clearance_feasibility(board, netlist, constraints))
        results.append(self._check_loop_area_feasibility(netlist, constraints))
        results.append(self._check_isolation_feasibility(board, netlist, constraints))
        results.append(self._check_layer_assignment(netlist, constraints))
        results.append(self._check_routing_channels(board, netlist))
        results.append(self._check_stackup_quality(board))

        if any(r.result == PreflightResult.FAIL for r in results):
            overall = PreflightResult.FAIL
        elif any(r.result == PreflightResult.WARN for r in results):
            overall = PreflightResult.WARN
        else:
            overall = PreflightResult.PASS

        return PreflightReport(results, overall, (time.time() - start_time) * 1000)

    def _check_layer_count(self, board: BoardLike) -> PreflightCheck:
        start = time.time()
        stackup = getattr(board, "layer_stackup", None)
        if stackup is None:
            return PreflightCheck(
                "Layer Count",
                PreflightResult.FAIL,
                "Board has no layer stackup defined",
                time_ms=(time.time() - start) * 1000,
            )
        n_layers = len(stackup.layers)
        if n_layers != 4:
            names = [ly.name for ly in stackup.layers]
            return PreflightCheck(
                "Layer Count",
                PreflightResult.FAIL,
                f"Expected 4-layer stackup (F.Cu/In1.Cu/In2.Cu/B.Cu), got {n_layers} layers: {names}",
                time_ms=(time.time() - start) * 1000,
            )
        return PreflightCheck(
            "Layer Count",
            PreflightResult.PASS,
            "4-layer stackup verified (F.Cu/In1.Cu/In2.Cu/B.Cu)",
            time_ms=(time.time() - start) * 1000,
        )

    def _check_component_area(self, board: BoardLike, netlist: NetlistLike) -> PreflightCheck:
        start = time.time()
        total_area = sum(c.width * c.height for c in netlist.components)
        board_area = board.width * board.height
        keepout_area = sum(
            k[2] * k[3] if len(k) == 4 else 0 for k in getattr(board, "keepouts", [])
        )
        usable_area = board_area - keepout_area
        ratio = total_area / usable_area if usable_area > 0 else 1.0
        result = (
            PreflightResult.FAIL
            if ratio > 0.85
            else (PreflightResult.WARN if ratio > 0.7 else PreflightResult.PASS)
        )
        return PreflightCheck(
            "Component Area",
            result,
            f"Fill ratio {ratio:.1%}",
            time_ms=(time.time() - start) * 1000,
        )

    def _check_constraint_satisfiability(
        self, netlist: NetlistLike, constraints: Any
    ) -> PreflightCheck:
        start = time.time()
        impossible = []
        comp_map = {c.ref: c for c in netlist.components}
        rules = []
        if hasattr(constraints, "component_groups"):
            for g in constraints.component_groups:
                rules.extend(g.proximity_rules)
        for c in rules:
            a, b = getattr(c, "component_a", ""), getattr(c, "component_b", "")
            max_d = getattr(c, "max_distance_mm", float("inf"))
            if a in comp_map and b in comp_map:
                min_d = min(
                    (comp_map[a].width + comp_map[b].width) / 2,
                    (comp_map[a].height + comp_map[b].height) / 2,
                )
                if max_d < min_d:
                    impossible.append(f"{a}-{b}: max {max_d}mm < min {min_d:.1f}mm")
        result = PreflightResult.FAIL if impossible else PreflightResult.PASS
        if impossible:
            for issue in impossible:
                print(f"  [DEBUG] Impossible Constraint: {issue}")
        return PreflightCheck(
            "Constraint Satisfiability",
            result,
            f"Found {len(impossible)} issues" if impossible else "No issues",
            {"impossible": impossible},
            (time.time() - start) * 1000,
        )

    def _check_zone_capacity(self, board: BoardLike, netlist: NetlistLike) -> PreflightCheck:
        start = time.time()
        if not hasattr(board, "zones") or not board.zones:
            return PreflightCheck("Zone Capacity", PreflightResult.PASS, "No zones")
        violations = []
        for zone in board.zones:
            cap = zone.width * zone.height
            content = sum(
                c.width * c.height
                for c in netlist.components
                if getattr(c, "zone", "") == zone.name
            )
            if content > cap * 0.9:
                violations.append(f"Zone {zone.name} over cap")
        result = PreflightResult.FAIL if violations else PreflightResult.PASS
        return PreflightCheck(
            "Zone Capacity",
            result,
            violations[0] if violations else "OK",
            time_ms=(time.time() - start) * 1000,
        )

    def _check_clearance_feasibility(
        self, _board: BoardLike, _netlist: NetlistLike, _constraints: Any
    ) -> PreflightCheck:
        return PreflightCheck("Clearance Feasibility", PreflightResult.PASS, "Achievable")

    def _check_loop_area_feasibility(
        self, netlist: NetlistLike, constraints: Any
    ) -> PreflightCheck:
        start = time.time()
        comp_map = {c.ref: c for c in netlist.components}
        violations = []
        loops = getattr(constraints, "critical_loops", [])
        for loop in loops:
            max_a = getattr(loop, "max_area_mm2", float("inf"))
            refs = []
            if hasattr(loop, "pins") and loop.pins:
                refs = [p[0] for p in loop.pins]
            elif hasattr(loop, "nets") and loop.nets:
                continue  # Need pin info for area

            if not refs:
                continue
            total_a = sum(comp_map[r].width * comp_map[r].height for r in refs if r in comp_map)
            if max_a and max_a < total_a * 0.5:
                violations.append(f"Loop {getattr(loop, 'name', 'unknown')} too small")
        result = PreflightResult.WARN if violations else PreflightResult.PASS
        return PreflightCheck(
            "Loop Area Feasibility",
            result,
            violations[0] if violations else "OK",
            time_ms=(time.time() - start) * 1000,
        )

    def _check_isolation_feasibility(
        self, board: BoardLike, _netlist: NetlistLike, _constraints: Any
    ) -> PreflightCheck:
        start = time.time()
        iso = 6.5
        hv = sum(1 for c in _netlist.components if getattr(c, "net_class", "") == "HighVoltage")
        if hv > 0:
            barrier_a = min(board.width, board.height) * iso
            total_a = sum(c.width * c.height for c in _netlist.components)
            if total_a + barrier_a > board.width * board.height * 0.95:
                return PreflightCheck(
                    "Isolation Feasibility",
                    PreflightResult.FAIL,
                    "Barrier too large",
                    time_ms=(time.time() - start) * 1000,
                )
        return PreflightCheck(
            "Isolation Feasibility",
            PreflightResult.PASS,
            "Feasible",
            time_ms=(time.time() - start) * 1000,
        )

    def _check_layer_assignment(self, _netlist: NetlistLike, _constraints: Any) -> PreflightCheck:
        return PreflightCheck("Layer Assignment", PreflightResult.PASS, "Feasible")

    def _check_routing_channels(self, _board: BoardLike, _netlist: NetlistLike) -> PreflightCheck:
        return PreflightCheck("Routing Channels", PreflightResult.PASS, "Available")

    def _check_stackup_quality(self, board: BoardLike) -> PreflightCheck:
        start = time.time()
        stackup = getattr(board, "layer_stackup", None)
        if stackup is None:
            return PreflightCheck(
                "Stackup Quality",
                PreflightResult.WARN,
                "No stackup available for quality validation",
                time_ms=(time.time() - start) * 1000,
            )
        try:
            from temper_placer.manufacturing.stackup_validator import validate_stackup

            report = validate_stackup(stackup)
            if not report.all_passed:
                warn_msgs = "; ".join(r.message[:80] for r in report.warnings[:3])
                return PreflightCheck(
                    "Stackup Quality",
                    PreflightResult.WARN,
                    f"{len(report.warnings)} warning(s): {warn_msgs}",
                    time_ms=(time.time() - start) * 1000,
                )
            return PreflightCheck(
                "Stackup Quality",
                PreflightResult.PASS,
                "All stackup quality checks passed",
                time_ms=(time.time() - start) * 1000,
            )
        except Exception as exc:
            return PreflightCheck(
                "Stackup Quality",
                PreflightResult.WARN,
                f"Stackup validation failed: {exc}",
                time_ms=(time.time() - start) * 1000,
            )

# ============================================================================
# SECTION: pipeline/derivation.py (verbatim)
# ============================================================================
"""
Physics-based constraint derivation for PCB placement.

This module derives geometric placement constraints from high-level
physical performance specifications (EMI, Thermal, Signal Integrity).
"""

import math
import warnings
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from temper_placer.core.netlist import Netlist
    from temper_placer.core.specification import PcbSpecification

from temper_placer.core.net_types import VoltageClass


def _mains_voltage_to_class(voltage_v: float) -> VoltageClass:
    """Map a mains voltage in volts to the nearest IEC 60335-1 voltage class."""
    if voltage_v <= 50:
        return VoltageClass.LOW_VOLTAGE
    elif voltage_v <= 130:
        return VoltageClass.MAINS_120V
    elif voltage_v <= 264:
        return VoltageClass.MAINS_240V
    else:
        return VoltageClass.HIGH_VOLTAGE


def derive_constraints_from_spec(
    spec: PcbSpecification,
    netlist: Netlist,  # noqa: ARG001
) -> dict[str, Any]:
    """
    Derive geometric constraints from physical specifications.

    Returns a dictionary of derived parameters (e.g. max distances).
    """
    derived = {}

    # 1. EMI -> Max Distance and Max Area
    for loop_name, max_area in spec.emi.max_loop_area_mm2.items():
        # L = sqrt(Area). Max side length of a square loop.
        max_side = math.sqrt(max_area)
        # Conservative estimate for max component spacing (center-to-center)
        # Assuming 20% routing overhead
        derived[f"{loop_name}_max_dist"] = max_side * 0.8
        # Store the max area directly for quality metric scoring
        derived[f"{loop_name}_max_area_mm2"] = max_area

    # 2. Thermal -> Min Spacing
    # Simple model: heat sources should be spaced to avoid thermal overlap
    # Required spacing proportional to power dissipation
    power_map = spec.thermal.power_dissipation
    for ref, power in power_map.items():
        # Heuristic: 2mm per Watt spacing
        derived[f"{ref}_min_clearance"] = power * 2.0

    # 3. Signal Integrity -> Max Length
    for net_name, max_len in spec.signal_integrity.max_length_mm.items():
        # Max placement distance should be less than max length
        # Assuming 1.5x routing overhead (Manhattan + detours)
        derived[f"{net_name}_max_placement_dist"] = max_len / 1.5

    # 4. Safety -> Isolation (Creepage/Clearance)
    if spec.safety is not None:
        vc = _mains_voltage_to_class(spec.safety.mains_voltage_v)
        derived["hv_lv_isolation_mm"] = vc.get_clearance_mm(
            pollution_degree=spec.safety.pollution_degree
        )
    else:
        # Default to 6.5mm for reinforced isolation (340V)
        warnings.warn(
            "No safety spec provided — falling back to hardcoded 6.5mm isolation.",
            stacklevel=2,
        )
        derived["hv_lv_isolation_mm"] = 6.5

    return derived


def apply_derived_constraints(
    netlist: Netlist,
    derived: dict[str, Any],
    pcl_constraints: Any = None,
) -> Any:
    """
    Apply derived constraints back to PCL constraint collection.

    When pcl_constraints is provided, synthesized constraints from
    derivation are added to it. Returns the modified collection or
    netlist fallback.

    This resolves the TODO at derivation.py:65 — back-propagation
    of derived parameters to the PCL constraint IR.
    """
    if pcl_constraints is None:
        return netlist

    from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint

    for key, value in derived.items():
        if key.endswith("_min_clearance"):
            ref = key.replace("_min_clearance", "")
            pcl_constraints.add(
                SeparatedConstraint(
                    a=ref,
                    b="*",
                    min_distance_mm=float(value),
                    tier=ConstraintTier.STRONG,
                    because=f"Derived from thermal spec: {ref} min clearance {value}mm",
                )
            )

    return pcl_constraints
