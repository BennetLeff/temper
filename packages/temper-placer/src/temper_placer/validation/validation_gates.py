"""
Validation gates for production readiness checks.

This module implements validation gates defined in MEASUREMENT_SPEC.yaml:
- placement_complete: Placement optimization has converged
- routing_complete: Autorouter has finished
- production_ready: Design can be sent to fabrication
- validated: Design has been statistically validated

Wave 4 entry-5 migration (port-inventory): the gate DECISION logic
(threshold comparisons, failed-metric selection, message composition) runs
in the ``temper_drc_rs`` ``validation_glue`` kernels
(``gate_placement_complete`` / ``gate_routing_complete`` /
``gate_production_ready`` / ``gate_validated``); the four ``check()``
methods are delegation shims (the pre-migration bodies are pinned verbatim
as the oracle in
``tests/validation/test_validation_glue_rust_differential.py``). The
wall-clock ``elapsed_ms``, the ``GateResult``/``GateStatus``/
``ValidationGatesResult`` dataclasses, the ``ValidationGate`` ABC and
``check_all_gates``/``check_gate`` orchestration stay Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class GateStatus(Enum):
    """Status of a validation gate."""

    PASS = "pass"
    FAIL = "fail"
    SKIP = "skip"
    PENDING = "pending"


# Kernel status string -> GateStatus (the kernels emit exactly these
# values; pinned by test_validation_glue_rust_differential.py).
_GATE_STATUS: dict[str, GateStatus] = {
    "pass": GateStatus.PASS,
    "fail": GateStatus.FAIL,
    "skip": GateStatus.SKIP,
}


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
        """True iff every gate slot was actually checked and passed.

        A gate slot left ``None`` means it was never run, not that it
        is exempt.  The previous ``g is None or g.passed`` treated an
        unrun gate the same as a passed one, so a default-constructed
        (all-``None``) report -- the archetypal "evaluated nothing"
        case -- reported PASS (docs/METHODOLOGY.md §4/§5,
        anti-vacuous-truth).  Fail closed instead: unrun is not passed.
        """
        gates = [
            self.placement_complete,
            self.routing_complete,
            self.production_ready,
            self.validated,
        ]
        return all(g is not None and g.passed for g in gates)

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

    def check(self, metrics: Any) -> GateResult:
        raise NotImplementedError


class PlacementCompleteGate(ValidationGate):
    """Gate: Placement optimization has converged with all geometric constraints met."""

    @property
    def name(self) -> str:
        return "placement_complete"

    @property
    def required_metrics(self) -> list[str]:
        # U5 remediation (plan 2026-08-02-019): the four loop-area/edge metrics
        # (gate_loop_area_mm2, bootstrap_loop_area_mm2, commutation_loop_area_mm2,
        # igbt_edge_distance_mm) were phantom declarations — RunMetrics never
        # carried them and check() never read them. Removed; see the tracked
        # finding R37-PHANTOM-REQUIRED-METRICS in
        # temper_placer.validation.gate_input_registry.
        return [
            "overlap_loss",
            "boundary_loss",
            "hv_clearance_violations",
            "zone_violations",
        ]

    def check(self, metrics: Any) -> GateResult:
        import time

        start = time.time()

        # Wave 4 entry-5: the threshold comparison, failed-metric selection
        # and message composition run in ``temper_drc_rs.gate_placement_complete``
        # (validation_glue.rs); elapsed_ms (wall-clock) is measured here.
        import temper_drc_rs as _tdrc  # type: ignore[import-untyped]

        status, message, failed = _tdrc.gate_placement_complete(
            overlap_loss=float(metrics.overlap_loss),
            boundary_loss=float(metrics.boundary_loss),
            hv_clearance_violations=float(metrics.hv_clearance_violations),
            zone_violations=float(metrics.zone_violations),
            convergence_epoch=metrics.convergence_epoch,
        )

        elapsed = (time.time() - start) * 1000

        return GateResult(
            gate_name=self.name,
            status=_GATE_STATUS[status],
            message=message,
            required_metrics=self.required_metrics,
            failed_metrics=dict(failed),
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

    def check(self, metrics: Any) -> GateResult:
        import time

        start = time.time()

        # Wave 4 entry-5: see PlacementCompleteGate.check — the decision
        # runs in ``temper_drc_rs.gate_routing_complete``.
        import temper_drc_rs as _tdrc  # type: ignore[import-untyped]

        status, message, failed = _tdrc.gate_routing_complete(
            routing_completion_percent=float(metrics.routing_completion_percent),
            drc_errors=float(metrics.drc_errors),
        )

        elapsed = (time.time() - start) * 1000

        return GateResult(
            gate_name=self.name,
            status=_GATE_STATUS[status],
            message=message,
            required_metrics=self.required_metrics,
            failed_metrics=dict(failed),
            elapsed_ms=elapsed,
        )


class ProductionReadyGate(ValidationGate):
    """Gate: Design can be sent to fabrication."""

    @property
    def name(self) -> str:
        return "production_ready"

    @property
    def required_metrics(self) -> list[str]:
        # U5 remediation (plan 2026-08-02-019): the four phantom loop-area/edge
        # metrics were removed (see PlacementCompleteGate.required_metrics for
        # the attribution).
        return [
            "overlap_loss",
            "boundary_loss",
            "hv_clearance_violations",
            "zone_violations",
            "routing_completion_percent",
            "drc_errors",
            "creepage_estimate",
            "spice_gate_overshoot",
            "spice_power_ripple",
        ]

    def check(self, metrics: Any) -> GateResult:
        import time

        start = time.time()

        # Wave 4 entry-5: the placement-gate run (and, on a placement
        # failure, the "Placement not ready: ..." propagation) happens
        # inside ``temper_drc_rs.gate_production_ready``.
        import temper_drc_rs as _tdrc  # type: ignore[import-untyped]

        status, message, failed = _tdrc.gate_production_ready(
            overlap_loss=float(metrics.overlap_loss),
            boundary_loss=float(metrics.boundary_loss),
            hv_clearance_violations=float(metrics.hv_clearance_violations),
            zone_violations=float(metrics.zone_violations),
            convergence_epoch=metrics.convergence_epoch,
            routing_completion_percent=float(metrics.routing_completion_percent),
            drc_errors=float(metrics.drc_errors),
        )

        elapsed = (time.time() - start) * 1000

        return GateResult(
            gate_name=self.name,
            status=_GATE_STATUS[status],
            message=message,
            required_metrics=self.required_metrics,
            failed_metrics=dict(failed),
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

    def check(self, metrics: Any) -> GateResult:
        import time

        start = time.time()

        # Wave 4 entry-5: see PlacementCompleteGate.check — the decision
        # runs in ``temper_drc_rs.gate_validated``.
        import temper_drc_rs as _tdrc  # type: ignore[import-untyped]

        failure_rate = getattr(metrics, "failure_rate", None)
        loss_cv = getattr(metrics, "loss_cv", None)

        status, message, failed = _tdrc.gate_validated(
            failure_rate if failure_rate is None else float(failure_rate),
            loss_cv if loss_cv is None else float(loss_cv),
        )

        elapsed = (time.time() - start) * 1000

        return GateResult(
            gate_name=self.name,
            status=_GATE_STATUS[status],
            message=message,
            required_metrics=self.required_metrics,
            failed_metrics=dict(failed),
            elapsed_ms=elapsed,
        )


def check_all_gates(metrics: Any) -> ValidationGatesResult:
    """
    Run all validation gates on a single run's metrics.

    Args:
        metrics: Run-metrics object (duck-typed) from a single training run

    Returns:
        ValidationGatesResult with results from all gates
    """
    return ValidationGatesResult(
        placement_complete=PlacementCompleteGate().check(metrics),
        routing_complete=RoutingCompleteGate().check(metrics),
        production_ready=ProductionReadyGate().check(metrics),
        validated=ValidatedGate().check(metrics),
    )


def check_gate(metrics: Any, gate_name: str) -> GateResult | None:
    """
    Run a specific validation gate.

    Args:
        metrics: Run-metrics object (duck-typed) from a single training run
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
