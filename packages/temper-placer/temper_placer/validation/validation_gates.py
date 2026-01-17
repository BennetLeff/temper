"""
Validation gates for production readiness checks.

This module implements validation gates defined in MEASUREMENT_SPEC.yaml:
- placement_complete: Placement optimization has converged
- routing_complete: Autorouter has finished
- production_ready: Design can be sent to fabrication
- validated: Design has been statistically validated
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from temper_placer.experiments.metrics_tracker import RunMetrics


class GateStatus(Enum):
    """Status of a validation gate."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    PENDING = "pending"


@dataclass
class GateResult:
    """Result of a validation gate check."""

    gate_name: str
    status: GateStatus
    message: str = ""
    required_metrics: list[str] = field(default_factory=list)
    failed_metrics: dict[str, float] = field(default_factory=dict)
    elapsed_ms: float = 0.0

    @property
    def passed(self) -> bool:
        return self.status == GateStatus.PASS


@dataclass
class ValidationGatesResult:
    """Combined result from all validation gates."""

    placement_complete: GateResult | None = None
    routing_complete: GateResult | None = None
    production_ready: GateResult | None = None
    validated: GateResult | None = None

    @property
    def all_passed(self) -> bool:
        return all(
            g is None or g.passed
            for g in [
                self.placement_complete,
                self.routing_complete,
                self.production_ready,
                self.validated,
            ]
        )

    def summary(self) -> str:
        lines = ["=== Validation Gates ==="]
        for name, gate in [
            ("Placement Complete", self.placement_complete),
            ("Routing Complete", self.routing_complete),
            ("Production Ready", self.production_ready),
            ("Validated", self.validated),
        ]:
            if gate is not None:
                status = "✓" if gate.passed else "✗"
                lines.append(f"  {status} {name}: {gate.message}")
            else:
                lines.append(f"    {name}: not checked")
        return "\n".join(lines)


class ValidationGate:
    """Base class for validation gates."""

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    def required_metrics(self) -> list[str]:
        return []

    def check(self, metrics: RunMetrics) -> GateResult:
        raise NotImplementedError


class PlacementCompleteGate(ValidationGate):
    """Gate: Placement optimization has converged with all geometric constraints met."""

    @property
    def name(self) -> str:
        return "placement_complete"

    @property
    def required_metrics(self) -> list[str]:
        return [
            "overlap_loss",
            "boundary_loss",
            "hv_clearance_violations",
            "zone_violations",
            "gate_loop_area_mm2",
            "bootstrap_loop_area_mm2",
            "commutation_loop_area_mm2",
            "igbt_edge_distance_mm",
        ]

    def check(self, metrics: RunMetrics) -> GateResult:
        import time

        start = time.time()

        failed: dict[str, float] = {}
        checks = [
            ("overlap_loss", metrics.overlap_loss, 0.01),
            ("boundary_loss", metrics.boundary_loss, 0.01),
            ("hv_clearance_violations", metrics.hv_clearance_violations, 0),
            ("zone_violations", metrics.zone_violations, 0),
        ]

        for name, value, threshold in checks:
            if value > threshold:
                failed[name] = value

        elapsed = (time.time() - start) * 1000

        if failed:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message=f"Failed {len(failed)} constraint(s)",
                required_metrics=self.required_metrics,
                failed_metrics=failed,
                elapsed_ms=elapsed,
            )

        if metrics.convergence_epoch == 0:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message="Did not converge",
                required_metrics=self.required_metrics,
                elapsed_ms=elapsed,
            )

        return GateResult(
            gate_name=self.name,
            status=GateStatus.PASS,
            message="All constraints met",
            required_metrics=self.required_metrics,
            elapsed_ms=elapsed,
        )


class RoutingCompleteGate(ValidationGate):
    """Gate: Autorouter has completed with acceptable results."""

    @property
    def name(self) -> str:
        return "routing_complete"

    @property
    def required_metrics(self) -> list[str]:
        return [
            "routing_completion_percent",
            "drc_errors",
        ]

    def check(self, metrics: RunMetrics) -> GateResult:
        import time

        start = time.time()
        elapsed = (time.time() - start) * 1000

        if metrics.routing_completion_percent < 0:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.SKIP,
                message="Routing not measured",
                required_metrics=self.required_metrics,
                elapsed_ms=elapsed,
            )

        failed: dict[str, float] = {}

        if metrics.routing_completion_percent < 90.0:
            failed["routing_completion_percent"] = metrics.routing_completion_percent

        if metrics.drc_errors > 0:
            failed["drc_errors"] = metrics.drc_errors

        if failed:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message=f"Failed {len(failed)} requirement(s)",
                required_metrics=self.required_metrics,
                failed_metrics=failed,
                elapsed_ms=elapsed,
            )

        return GateResult(
            gate_name=self.name,
            status=GateStatus.PASS,
            message="Routing complete with 0 DRC errors",
            required_metrics=self.required_metrics,
            elapsed_ms=elapsed,
        )


class ProductionReadyGate(ValidationGate):
    """Gate: Design can be sent to fabrication."""

    @property
    def name(self) -> str:
        return "production_ready"

    @property
    def required_metrics(self) -> list[str]:
        return [
            "overlap_loss",
            "boundary_loss",
            "hv_clearance_violations",
            "zone_violations",
            "gate_loop_area_mm2",
            "bootstrap_loop_area_mm2",
            "commutation_loop_area_mm2",
            "igbt_edge_distance_mm",
            "routing_completion_percent",
            "drc_errors",
            "creepage_estimate",
            "spice_gate_overshoot",
            "spice_power_ripple",
        ]

    def check(self, metrics: RunMetrics) -> GateResult:
        import time

        start = time.time()

        placement_gate = PlacementCompleteGate()
        placement_result = placement_gate.check(metrics)

        if not placement_result.passed:
            elapsed = (time.time() - start) * 1000
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message=f"Placement not ready: {placement_result.message}",
                required_metrics=self.required_metrics,
                failed_metrics=placement_result.failed_metrics,
                elapsed_ms=elapsed,
            )

        failed: dict[str, float] = {}

        if metrics.routing_completion_percent >= 0 and metrics.routing_completion_percent < 90.0:
            failed["routing_completion_percent"] = metrics.routing_completion_percent

        if metrics.drc_errors > 0:
            failed["drc_errors"] = metrics.drc_errors

        elapsed = (time.time() - start) * 1000

        if failed:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message=f"Failed {len(failed)} requirement(s)",
                required_metrics=self.required_metrics,
                failed_metrics=failed,
                elapsed_ms=elapsed,
            )

        return GateResult(
            gate_name=self.name,
            status=GateStatus.PASS,
            message="Production ready",
            required_metrics=self.required_metrics,
            elapsed_ms=elapsed,
        )


class ValidatedGate(ValidationGate):
    """Gate: Design has been statistically validated."""

    @property
    def name(self) -> str:
        return "validated"

    @property
    def required_metrics(self) -> list[str]:
        return [
            "failure_rate",
            "loss_cv",
        ]

    def check(self, metrics: RunMetrics) -> GateResult:
        import time

        start = time.time()
        elapsed = (time.time() - start) * 1000

        failure_rate = getattr(metrics, "failure_rate", None)
        loss_cv = getattr(metrics, "loss_cv", None)

        if failure_rate is None or loss_cv is None:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.SKIP,
                message="Statistical validation not performed",
                required_metrics=self.required_metrics,
                elapsed_ms=elapsed,
            )

        failed: dict[str, float] = {}

        if failure_rate > 5.0:
            failed["failure_rate"] = failure_rate

        if loss_cv > 0.15:
            failed["loss_cv"] = loss_cv

        if failed:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message=f"Failed {len(failed)} statistical requirement(s)",
                required_metrics=self.required_metrics,
                failed_metrics=failed,
                elapsed_ms=elapsed,
            )

        return GateResult(
            gate_name=self.name,
            status=GateStatus.PASS,
            message="Statistically validated",
            required_metrics=self.required_metrics,
            elapsed_ms=elapsed,
        )


def check_all_gates(metrics: RunMetrics) -> ValidationGatesResult:
    """
    Run all validation gates on a single run's metrics.

    Args:
        metrics: RunMetrics from a single training run

    Returns:
        ValidationGatesResult with results from all gates
    """
    return ValidationGatesResult(
        placement_complete=PlacementCompleteGate().check(metrics),
        routing_complete=RoutingCompleteGate().check(metrics),
        production_ready=ProductionReadyGate().check(metrics),
        validated=ValidatedGate().check(metrics),
    )


def check_gate(metrics: RunMetrics, gate_name: str) -> GateResult | None:
    """
    Run a specific validation gate.

    Args:
        metrics: RunMetrics from a single training run
        gate_name: Name of the gate to check

    Returns:
        GateResult or None if gate name is not recognized
    """
    gates: dict[str, type[ValidationGate]] = {
        "placement_complete": PlacementCompleteGate,
        "routing_complete": RoutingCompleteGate,
        "production_ready": ProductionReadyGate,
        "validated": ValidatedGate,
    }

    gate_class = gates.get(gate_name)
    if gate_class is None:
        return None

    return gate_class().check(metrics)
