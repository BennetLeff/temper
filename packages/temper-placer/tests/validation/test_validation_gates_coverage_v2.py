"""Tests for validation.validation_gates module — Gate classes and check functions."""
from unittest.mock import MagicMock

from temper_placer.validation.validation_gates import (
    GateResult,
    GateStatus,
    PlacementCompleteGate,
    ProductionReadyGate,
    RoutingCompleteGate,
    ValidatedGate,
    ValidationGate,
    ValidationGatesResult,
    check_all_gates,
    check_gate,
)


class TestValidationGateABC:
    """Tests for ValidationGate ABC."""

    def test_name_property(self):
        class MyGate(ValidationGate):
            def check(self, metrics):
                return GateResult(gate_name=self.name, status=GateStatus.PASS)
        g = MyGate()
        assert g.name == "MyGate"

    def test_required_metrics_default(self):
        class MyGate(ValidationGate):
            def check(self, metrics):
                return GateResult(gate_name=self.name, status=GateStatus.PASS)
        g = MyGate()
        assert g.required_metrics == []


class TestPlacementCompleteGate:
    """Tests for PlacementCompleteGate."""

    def test_name(self):
        g = PlacementCompleteGate()
        assert g.name == "placement_complete"

    def test_required_metrics(self):
        g = PlacementCompleteGate()
        metrics = g.required_metrics
        assert "overlap_loss" in metrics
        assert "boundary_loss" in metrics
        assert "hv_clearance_violations" in metrics
        assert "zone_violations" in metrics

    def test_check_pass(self):
        g = PlacementCompleteGate()
        metrics = MagicMock()
        metrics.overlap_loss = 0.0
        metrics.boundary_loss = 0.0
        metrics.hv_clearance_violations = 0
        metrics.zone_violations = 0
        metrics.convergence_epoch = 100
        result = g.check(metrics)
        assert result.passed is True
        assert result.gate_name == "placement_complete"
        assert result.status == GateStatus.PASS

    def test_check_fail_overlap(self):
        g = PlacementCompleteGate()
        metrics = MagicMock()
        metrics.overlap_loss = 0.05  # > 0.01 threshold
        metrics.boundary_loss = 0.0
        metrics.hv_clearance_violations = 0
        metrics.zone_violations = 0
        metrics.convergence_epoch = 100
        result = g.check(metrics)
        assert result.passed is False
        assert "overlap_loss" in result.failed_metrics

    def test_check_fail_hv_clearance(self):
        g = PlacementCompleteGate()
        metrics = MagicMock()
        metrics.overlap_loss = 0.0
        metrics.boundary_loss = 0.0
        metrics.hv_clearance_violations = 2  # > 0 threshold
        metrics.zone_violations = 0
        metrics.convergence_epoch = 100
        result = g.check(metrics)
        assert result.passed is False
        assert "hv_clearance_violations" in result.failed_metrics

    def test_check_fail_no_convergence(self):
        g = PlacementCompleteGate()
        metrics = MagicMock()
        metrics.overlap_loss = 0.0
        metrics.boundary_loss = 0.0
        metrics.hv_clearance_violations = 0
        metrics.zone_violations = 0
        metrics.convergence_epoch = 0  # did not converge
        result = g.check(metrics)
        assert result.passed is False
        assert "converge" in result.message.lower()


class TestRoutingCompleteGate:
    """Tests for RoutingCompleteGate."""

    def test_name(self):
        g = RoutingCompleteGate()
        assert g.name == "routing_complete"

    def test_required_metrics(self):
        g = RoutingCompleteGate()
        assert "routing_completion_percent" in g.required_metrics
        assert "drc_errors" in g.required_metrics

    def test_check_skip_not_measured(self):
        g = RoutingCompleteGate()
        metrics = MagicMock()
        metrics.routing_completion_percent = -1.0
        metrics.drc_errors = 0
        result = g.check(metrics)
        assert result.status == GateStatus.SKIP
        assert "not measured" in result.message.lower()

    def test_check_pass(self):
        g = RoutingCompleteGate()
        metrics = MagicMock()
        metrics.routing_completion_percent = 100.0
        metrics.drc_errors = 0
        result = g.check(metrics)
        assert result.passed is True
        assert result.status == GateStatus.PASS

    def test_check_fail_drc_errors(self):
        g = RoutingCompleteGate()
        metrics = MagicMock()
        metrics.routing_completion_percent = 100.0
        metrics.drc_errors = 5
        result = g.check(metrics)
        assert result.passed is False


class TestProductionReadyGate:
    """Tests for ProductionReadyGate."""

    def test_name(self):
        g = ProductionReadyGate()
        assert g.name == "production_ready"

    def test_required_metrics(self):
        g = ProductionReadyGate()
        assert "drc_errors" in g.required_metrics

    def test_check_pass(self):
        g = ProductionReadyGate()
        metrics = MagicMock()
        # PlacementCompleteGate check needs these
        metrics.overlap_loss = 0.0
        metrics.boundary_loss = 0.0
        metrics.hv_clearance_violations = 0
        metrics.zone_violations = 0
        metrics.convergence_epoch = 100
        metrics.routing_completion_percent = 100.0
        metrics.drc_errors = 0
        result = g.check(metrics)
        assert result.passed is True

    def test_check_fail_drc(self):
        g = ProductionReadyGate()
        metrics = MagicMock()
        metrics.overlap_loss = 0.0
        metrics.boundary_loss = 0.0
        metrics.hv_clearance_violations = 0
        metrics.zone_violations = 0
        metrics.convergence_epoch = 100
        metrics.routing_completion_percent = 100.0
        metrics.drc_errors = 3
        result = g.check(metrics)
        assert result.passed is False


class TestValidatedGate:
    """Tests for ValidatedGate."""

    def test_name(self):
        g = ValidatedGate()
        assert g.name == "validated"

    def test_required_metrics(self):
        g = ValidatedGate()
        assert "failure_rate" in g.required_metrics
        assert "loss_cv" in g.required_metrics

    def test_check_pass(self):
        g = ValidatedGate()
        metrics = MagicMock()
        metrics.failure_rate = 1.0
        metrics.loss_cv = 0.05
        result = g.check(metrics)
        assert result.passed is True

    def test_check_fail(self):
        g = ValidatedGate()
        metrics = MagicMock()
        metrics.failure_rate = 10.0
        metrics.loss_cv = 0.05
        result = g.check(metrics)
        assert result.passed is False


class TestCheckGate:
    """Tests for check_gate function."""

    def test_check_gate_pass(self):
        metrics = MagicMock()
        metrics.overlap_loss = 0.0
        metrics.boundary_loss = 0.0
        metrics.hv_clearance_violations = 0
        metrics.zone_violations = 0
        metrics.convergence_epoch = 100
        result = check_gate(metrics, "placement_complete")
        assert result is not None
        assert result.passed is True

    def test_check_gate_fail(self):
        metrics = MagicMock()
        metrics.overlap_loss = 1.0
        metrics.boundary_loss = 0.0
        metrics.hv_clearance_violations = 0
        metrics.zone_violations = 0
        metrics.convergence_epoch = 100
        result = check_gate(metrics, "placement_complete")
        assert result is not None
        assert result.passed is False

    def test_check_gate_unknown(self):
        metrics = MagicMock()
        result = check_gate(metrics, "nonexistent_gate")
        assert result is None


class TestCheckAllGates:
    """Tests for check_all_gates function."""

    def _make_pass_metrics(self):
        metrics = MagicMock()
        metrics.overlap_loss = 0.0
        metrics.boundary_loss = 0.0
        metrics.hv_clearance_violations = 0
        metrics.zone_violations = 0
        metrics.convergence_epoch = 100
        metrics.routing_completion_percent = 100.0
        metrics.drc_errors = 0
        metrics.failure_rate = 1.0
        metrics.loss_cv = 0.05
        return metrics

    def test_all_pass(self):
        metrics = self._make_pass_metrics()
        result = check_all_gates(metrics)
        assert result.all_passed is True
        assert result.placement_complete is not None
        assert result.placement_complete.passed is True

    def test_one_fail(self):
        metrics = self._make_pass_metrics()
        metrics.drc_errors = 5
        result = check_all_gates(metrics)
        assert result.production_ready is not None
        assert result.production_ready.passed is False
        assert result.all_passed is False
