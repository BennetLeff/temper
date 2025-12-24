"""Tests for placement-routing feedback loop (temper-l65.2).

Tests the FeedbackGenerator that converts routing failures to placement
adjustments, and the feedback loop that iterates until feasible.

TDD: Write tests first, then implement feedback.py to pass them.
"""


import pytest

# We'll import from the feedback module we're about to create
# These imports will fail until we implement feedback.py
from temper_placer.pipeline.feedback import (
    AdjustmentApplier,
    AdjustmentType,
    FeedbackAdjustment,
    FeedbackGenerator,
    FeedbackLoopConfig,
    FeedbackLoopResult,
    run_feedback_loop,
)

# Import types from routing module (already exists)
from temper_placer.routing import (
    FailureType,
    RoutingDiagnostic,
    RoutingReport,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def simple_no_path_diagnostic() -> RoutingDiagnostic:
    """Create a simple NO_PATH diagnostic."""
    return RoutingDiagnostic(
        net="VCC",
        failure_type=FailureType.NO_PATH,
        location=(25.0, 30.0),
        severity="critical",
        blocking_elements=["U1", "R3"],
        constraint_violated=None,
        suggested_fix="Move U1 to clear path",
        fix_confidence=0.7,
        placement_hint=None,
    )


@pytest.fixture
def congestion_diagnostic() -> RoutingDiagnostic:
    """Create a CONGESTION diagnostic."""
    return RoutingDiagnostic(
        net="DATA",
        failure_type=FailureType.CONGESTION,
        location=(50.0, 50.0),
        severity="warning",
        blocking_elements=["U1", "U2", "C1", "C2"],
        constraint_violated=None,
        suggested_fix="Spread components around (50, 50)",
        fix_confidence=0.5,
        placement_hint=None,
    )


@pytest.fixture
def layer_conflict_diagnostic() -> RoutingDiagnostic:
    """Create a LAYER_CONFLICT diagnostic."""
    return RoutingDiagnostic(
        net="HV_BUS",
        failure_type=FailureType.LAYER_CONFLICT,
        location=(0.0, 0.0),
        severity="critical",
        blocking_elements=[],
        constraint_violated="HV nets require inner layers",
        suggested_fix="Reassign HV_BUS to layer L3",
        fix_confidence=0.9,
        placement_hint=None,
    )


@pytest.fixture
def feasible_routing_report() -> RoutingReport:
    """Create a routing report that's feasible (no failures)."""
    return RoutingReport(
        feasible=True,
        completion_rate=1.0,
        routed_nets=["VCC", "GND", "DATA"],
        failed_nets=[],
        diagnostics=[],
        congestion_map=None,
        total_wirelength=150.0,
        total_vias=8,
        worst_congestion=0.6,
    )


@pytest.fixture
def failed_routing_report(simple_no_path_diagnostic, congestion_diagnostic) -> RoutingReport:
    """Create a routing report with failures."""
    return RoutingReport(
        feasible=False,
        completion_rate=0.7,
        routed_nets=["GND"],
        failed_nets=["VCC", "DATA"],
        diagnostics=[simple_no_path_diagnostic, congestion_diagnostic],
        congestion_map=None,
        total_wirelength=80.0,
        total_vias=4,
        worst_congestion=1.5,
    )


# =============================================================================
# Test AdjustmentType Enum
# =============================================================================


class TestAdjustmentType:
    """Tests for AdjustmentType enum."""

    def test_adjustment_type_exists(self):
        """AdjustmentType enum exists."""
        assert AdjustmentType is not None

    def test_has_move_type(self):
        """AdjustmentType has MOVE."""
        assert AdjustmentType.MOVE.value == "move"

    def test_has_rotate_type(self):
        """AdjustmentType has ROTATE."""
        assert AdjustmentType.ROTATE.value == "rotate"

    def test_has_spread_type(self):
        """AdjustmentType has SPREAD."""
        assert AdjustmentType.SPREAD.value == "spread"

    def test_has_swap_type(self):
        """AdjustmentType has SWAP."""
        assert AdjustmentType.SWAP.value == "swap"


# =============================================================================
# Test FeedbackAdjustment Dataclass
# =============================================================================


class TestFeedbackAdjustment:
    """Tests for FeedbackAdjustment dataclass."""

    def test_feedback_adjustment_exists(self):
        """FeedbackAdjustment dataclass exists."""
        assert FeedbackAdjustment is not None

    def test_create_move_adjustment(self):
        """Can create a move adjustment."""
        adj = FeedbackAdjustment(
            component="U1",
            adjustment_type=AdjustmentType.MOVE,
            direction=(1.0, 0.5),
            magnitude=3.0,
            reason="Clear path for VCC",
            priority=0.9,
            source_diagnostic=None,
        )
        assert adj.component == "U1"
        assert adj.adjustment_type == AdjustmentType.MOVE
        assert adj.direction == (1.0, 0.5)
        assert adj.magnitude == 3.0
        assert adj.reason == "Clear path for VCC"
        assert adj.priority == 0.9

    def test_create_spread_adjustment(self):
        """Can create a spread adjustment."""
        adj = FeedbackAdjustment(
            component="U1",
            adjustment_type=AdjustmentType.SPREAD,
            direction=None,
            magnitude=5.0,
            reason="Reduce congestion",
            priority=0.7,
            source_diagnostic=None,
        )
        assert adj.adjustment_type == AdjustmentType.SPREAD
        assert adj.direction is None

    def test_direction_optional_for_non_move(self):
        """Direction is optional for non-move adjustments."""
        adj = FeedbackAdjustment(
            component="U1",
            adjustment_type=AdjustmentType.ROTATE,
            direction=None,
            magnitude=90.0,
            reason="Try alternate orientation",
            priority=0.3,
            source_diagnostic=None,
        )
        assert adj.direction is None

    def test_has_source_diagnostic_field(self):
        """FeedbackAdjustment has source_diagnostic field."""
        diag = RoutingDiagnostic(
            net="VCC",
            failure_type=FailureType.NO_PATH,
            location=(0.0, 0.0),
            severity="critical",
            blocking_elements=["U1"],
            constraint_violated=None,
            suggested_fix="Move U1",
            fix_confidence=0.7,
            placement_hint=None,
        )
        adj = FeedbackAdjustment(
            component="U1",
            adjustment_type=AdjustmentType.MOVE,
            direction=(1.0, 0.0),
            magnitude=2.0,
            reason="Clear path",
            priority=0.9,
            source_diagnostic=diag,
        )
        assert adj.source_diagnostic == diag


# =============================================================================
# Test FeedbackGenerator Class
# =============================================================================


class TestFeedbackGeneratorInit:
    """Tests for FeedbackGenerator initialization."""

    def test_feedback_generator_exists(self):
        """FeedbackGenerator class exists."""
        assert FeedbackGenerator is not None

    def test_can_create_default_generator(self):
        """Can create generator with defaults."""
        gen = FeedbackGenerator()
        assert gen is not None

    def test_has_generate_method(self):
        """FeedbackGenerator has generate method."""
        gen = FeedbackGenerator()
        assert hasattr(gen, "generate")
        assert callable(gen.generate)


class TestFeedbackGeneratorGenerate:
    """Tests for FeedbackGenerator.generate()."""

    def test_generate_returns_list(self, failed_routing_report):
        """generate() returns a list."""
        gen = FeedbackGenerator()
        result = gen.generate(failed_routing_report)
        assert isinstance(result, list)

    def test_generate_returns_feedback_adjustments(self, failed_routing_report):
        """generate() returns list of FeedbackAdjustment."""
        gen = FeedbackGenerator()
        result = gen.generate(failed_routing_report)
        assert len(result) > 0
        for adj in result:
            assert isinstance(adj, FeedbackAdjustment)

    def test_generate_empty_for_feasible_report(self, feasible_routing_report):
        """generate() returns empty list for feasible routing."""
        gen = FeedbackGenerator()
        result = gen.generate(feasible_routing_report)
        assert result == []

    def test_generate_sorted_by_priority(self, failed_routing_report):
        """Results are sorted by priority (highest first)."""
        gen = FeedbackGenerator()
        result = gen.generate(failed_routing_report)
        priorities = [adj.priority for adj in result]
        assert priorities == sorted(priorities, reverse=True)


class TestNoPathAdjustmentGeneration:
    """Tests for generating adjustments from NO_PATH failures."""

    def test_no_path_generates_move_adjustment(self, simple_no_path_diagnostic):
        """NO_PATH diagnostic generates MOVE adjustment."""
        report = RoutingReport(
            feasible=False,
            completion_rate=0.5,
            routed_nets=[],
            failed_nets=["VCC"],
            diagnostics=[simple_no_path_diagnostic],
            congestion_map=None,
            total_wirelength=0.0,
            total_vias=0,
            worst_congestion=0.0,
        )
        gen = FeedbackGenerator()
        result = gen.generate(report)

        assert len(result) >= 1
        move_adjs = [a for a in result if a.adjustment_type == AdjustmentType.MOVE]
        assert len(move_adjs) >= 1

    def test_no_path_targets_first_blocker(self, simple_no_path_diagnostic):
        """NO_PATH targets first blocking element."""
        report = RoutingReport(
            feasible=False,
            completion_rate=0.5,
            routed_nets=[],
            failed_nets=["VCC"],
            diagnostics=[simple_no_path_diagnostic],
            congestion_map=None,
            total_wirelength=0.0,
            total_vias=0,
            worst_congestion=0.0,
        )
        gen = FeedbackGenerator()
        result = gen.generate(report)

        move_adj = next(a for a in result if a.adjustment_type == AdjustmentType.MOVE)
        assert move_adj.component == "U1"  # First blocker

    def test_no_path_has_direction(self, simple_no_path_diagnostic):
        """NO_PATH move adjustment has direction."""
        report = RoutingReport(
            feasible=False,
            completion_rate=0.5,
            routed_nets=[],
            failed_nets=["VCC"],
            diagnostics=[simple_no_path_diagnostic],
            congestion_map=None,
            total_wirelength=0.0,
            total_vias=0,
            worst_congestion=0.0,
        )
        gen = FeedbackGenerator()
        result = gen.generate(report)

        move_adj = next(a for a in result if a.adjustment_type == AdjustmentType.MOVE)
        assert move_adj.direction is not None
        assert len(move_adj.direction) == 2

    def test_no_path_has_high_priority(self, simple_no_path_diagnostic):
        """NO_PATH failures have high priority."""
        report = RoutingReport(
            feasible=False,
            completion_rate=0.5,
            routed_nets=[],
            failed_nets=["VCC"],
            diagnostics=[simple_no_path_diagnostic],
            congestion_map=None,
            total_wirelength=0.0,
            total_vias=0,
            worst_congestion=0.0,
        )
        gen = FeedbackGenerator()
        result = gen.generate(report)

        move_adj = next(a for a in result if a.adjustment_type == AdjustmentType.MOVE)
        assert move_adj.priority >= 0.8


class TestCongestionAdjustmentGeneration:
    """Tests for generating adjustments from CONGESTION failures."""

    def test_congestion_generates_spread_adjustment(self, congestion_diagnostic):
        """CONGESTION diagnostic generates SPREAD adjustment."""
        report = RoutingReport(
            feasible=False,
            completion_rate=0.7,
            routed_nets=["VCC"],
            failed_nets=["DATA"],
            diagnostics=[congestion_diagnostic],
            congestion_map=None,
            total_wirelength=50.0,
            total_vias=2,
            worst_congestion=1.5,
        )
        gen = FeedbackGenerator()
        result = gen.generate(report)

        spread_adjs = [a for a in result if a.adjustment_type == AdjustmentType.SPREAD]
        assert len(spread_adjs) >= 1

    def test_congestion_targets_blocking_component(self, congestion_diagnostic):
        """CONGESTION targets one of the blocking components."""
        report = RoutingReport(
            feasible=False,
            completion_rate=0.7,
            routed_nets=["VCC"],
            failed_nets=["DATA"],
            diagnostics=[congestion_diagnostic],
            congestion_map=None,
            total_wirelength=50.0,
            total_vias=2,
            worst_congestion=1.5,
        )
        gen = FeedbackGenerator()
        result = gen.generate(report)

        spread_adj = next(a for a in result if a.adjustment_type == AdjustmentType.SPREAD)
        assert spread_adj.component in congestion_diagnostic.blocking_elements

    def test_congestion_has_medium_priority(self, congestion_diagnostic):
        """CONGESTION failures have medium priority."""
        report = RoutingReport(
            feasible=False,
            completion_rate=0.7,
            routed_nets=["VCC"],
            failed_nets=["DATA"],
            diagnostics=[congestion_diagnostic],
            congestion_map=None,
            total_wirelength=50.0,
            total_vias=2,
            worst_congestion=1.5,
        )
        gen = FeedbackGenerator()
        result = gen.generate(report)

        spread_adj = next(a for a in result if a.adjustment_type == AdjustmentType.SPREAD)
        assert 0.4 <= spread_adj.priority <= 0.8


class TestLayerConflictHandling:
    """Tests for layer conflict diagnostics."""

    def test_layer_conflict_does_not_generate_placement_adjustment(self, layer_conflict_diagnostic):
        """LAYER_CONFLICT doesn't create placement adjustment (not fixable by moving)."""
        report = RoutingReport(
            feasible=False,
            completion_rate=0.8,
            routed_nets=["VCC", "GND"],
            failed_nets=["HV_BUS"],
            diagnostics=[layer_conflict_diagnostic],
            congestion_map=None,
            total_wirelength=100.0,
            total_vias=5,
            worst_congestion=0.5,
        )
        gen = FeedbackGenerator()
        result = gen.generate(report)

        # Layer conflicts can't be fixed by placement adjustment
        # Should return empty or no adjustment for this diagnostic
        move_or_spread = [
            a for a in result if a.adjustment_type in (AdjustmentType.MOVE, AdjustmentType.SPREAD)
        ]
        assert len(move_or_spread) == 0


# =============================================================================
# Test AdjustmentApplier Class
# =============================================================================


class TestAdjustmentApplierInit:
    """Tests for AdjustmentApplier initialization."""

    def test_adjustment_applier_exists(self):
        """AdjustmentApplier class exists."""
        assert AdjustmentApplier is not None

    def test_can_create_applier(self):
        """Can create applier."""
        applier = AdjustmentApplier()
        assert applier is not None

    def test_has_apply_method(self):
        """AdjustmentApplier has apply method."""
        applier = AdjustmentApplier()
        assert hasattr(applier, "apply")
        assert callable(applier.apply)


class TestAdjustmentApplierApply:
    """Tests for AdjustmentApplier.apply()."""

    def test_apply_returns_soft_constraints(self):
        """apply() returns list of soft constraints."""
        applier = AdjustmentApplier()
        adj = FeedbackAdjustment(
            component="U1",
            adjustment_type=AdjustmentType.MOVE,
            direction=(1.0, 0.0),
            magnitude=2.0,
            reason="Clear path",
            priority=0.9,
            source_diagnostic=None,
        )
        result = applier.apply([adj])
        assert isinstance(result, list)

    def test_apply_creates_constraint_for_move(self):
        """apply() creates constraint for MOVE adjustment."""
        applier = AdjustmentApplier()
        adj = FeedbackAdjustment(
            component="U1",
            adjustment_type=AdjustmentType.MOVE,
            direction=(1.0, 0.0),
            magnitude=2.0,
            reason="Clear path",
            priority=0.9,
            source_diagnostic=None,
        )
        result = applier.apply([adj])
        assert len(result) == 1

    def test_apply_creates_constraint_for_spread(self):
        """apply() creates constraint for SPREAD adjustment."""
        applier = AdjustmentApplier()
        adj = FeedbackAdjustment(
            component="U1",
            adjustment_type=AdjustmentType.SPREAD,
            direction=None,
            magnitude=5.0,
            reason="Reduce congestion",
            priority=0.7,
            source_diagnostic=None,
        )
        result = applier.apply([adj])
        assert len(result) == 1

    def test_apply_empty_for_empty_list(self):
        """apply() returns empty list for empty input."""
        applier = AdjustmentApplier()
        result = applier.apply([])
        assert result == []

    def test_apply_limits_to_max_adjustments(self):
        """apply() respects max_adjustments parameter."""
        applier = AdjustmentApplier(max_adjustments=2)
        adjustments = [
            FeedbackAdjustment(
                component=f"U{i}",
                adjustment_type=AdjustmentType.MOVE,
                direction=(1.0, 0.0),
                magnitude=2.0,
                reason="Clear path",
                priority=0.9 - i * 0.1,
                source_diagnostic=None,
            )
            for i in range(5)
        ]
        result = applier.apply(adjustments)
        assert len(result) <= 2


# =============================================================================
# Test FeedbackLoopConfig Dataclass
# =============================================================================


class TestFeedbackLoopConfig:
    """Tests for FeedbackLoopConfig dataclass."""

    def test_feedback_loop_config_exists(self):
        """FeedbackLoopConfig dataclass exists."""
        assert FeedbackLoopConfig is not None

    def test_default_max_iterations(self):
        """Default max_iterations is 5."""
        config = FeedbackLoopConfig()
        assert config.max_iterations == 5

    def test_default_max_adjustments_per_iteration(self):
        """Default max_adjustments_per_iteration is 3."""
        config = FeedbackLoopConfig()
        assert config.max_adjustments_per_iteration == 3

    def test_default_refinement_epochs(self):
        """Default refinement_epochs is 2000."""
        config = FeedbackLoopConfig()
        assert config.refinement_epochs == 2000

    def test_can_customize_config(self):
        """Can customize config values."""
        config = FeedbackLoopConfig(
            max_iterations=10,
            max_adjustments_per_iteration=5,
            refinement_epochs=1000,
        )
        assert config.max_iterations == 10
        assert config.max_adjustments_per_iteration == 5
        assert config.refinement_epochs == 1000


# =============================================================================
# Test FeedbackLoopResult Dataclass
# =============================================================================


class TestFeedbackLoopResult:
    """Tests for FeedbackLoopResult dataclass."""

    def test_feedback_loop_result_exists(self):
        """FeedbackLoopResult dataclass exists."""
        assert FeedbackLoopResult is not None

    def test_has_required_fields(self):
        """FeedbackLoopResult has required fields."""
        result = FeedbackLoopResult(
            converged=True,
            iterations=3,
            final_routing_report=None,
            adjustments_applied=[],
            history=[],
        )
        assert result.converged is True
        assert result.iterations == 3
        assert result.final_routing_report is None
        assert result.adjustments_applied == []
        assert result.history == []

    def test_history_tracks_iterations(self):
        """history field tracks per-iteration info."""
        result = FeedbackLoopResult(
            converged=False,
            iterations=2,
            final_routing_report=None,
            adjustments_applied=[],
            history=[
                {"iteration": 0, "completion_rate": 0.5},
                {"iteration": 1, "completion_rate": 0.7},
            ],
        )
        assert len(result.history) == 2
        assert result.history[1]["completion_rate"] == 0.7


# =============================================================================
# Test run_feedback_loop Function
# =============================================================================


class TestRunFeedbackLoopFunction:
    """Tests for run_feedback_loop function."""

    def test_run_feedback_loop_exists(self):
        """run_feedback_loop function exists."""
        assert run_feedback_loop is not None
        assert callable(run_feedback_loop)

    def test_returns_feedback_loop_result(self, feasible_routing_report):
        """run_feedback_loop returns FeedbackLoopResult."""

        def mock_router(adjustments):
            return feasible_routing_report

        result = run_feedback_loop(
            initial_report=feasible_routing_report,
            routing_function=mock_router,
        )
        assert isinstance(result, FeedbackLoopResult)

    def test_converges_immediately_if_feasible(self, feasible_routing_report):
        """Converges in 0 iterations if already feasible."""

        def mock_router(adjustments):
            return feasible_routing_report

        result = run_feedback_loop(
            initial_report=feasible_routing_report,
            routing_function=mock_router,
        )
        assert result.converged is True
        assert result.iterations == 0

    def test_iterates_until_feasible(self, failed_routing_report, feasible_routing_report):
        """Iterates until routing becomes feasible."""
        call_count = [0]

        def mock_router(adjustments):
            call_count[0] += 1
            if call_count[0] >= 2:
                return feasible_routing_report
            return failed_routing_report

        result = run_feedback_loop(
            initial_report=failed_routing_report,
            routing_function=mock_router,
        )
        assert result.converged is True
        assert result.iterations >= 1

    def test_stops_at_max_iterations(self, failed_routing_report):
        """Stops after max_iterations even if not feasible."""

        def mock_router(adjustments):
            return failed_routing_report

        config = FeedbackLoopConfig(max_iterations=3)
        result = run_feedback_loop(
            initial_report=failed_routing_report,
            routing_function=mock_router,
            config=config,
        )
        assert result.converged is False
        assert result.iterations == 3

    def test_tracks_adjustments_applied(self, failed_routing_report, feasible_routing_report):
        """Tracks all adjustments applied across iterations."""

        def mock_router(adjustments):
            return feasible_routing_report

        result = run_feedback_loop(
            initial_report=failed_routing_report,
            routing_function=mock_router,
        )
        # Should have some adjustments tracked
        assert isinstance(result.adjustments_applied, list)

    def test_calls_on_iteration_callback(self, failed_routing_report, feasible_routing_report):
        """Calls on_iteration callback each iteration."""
        callbacks = []

        def on_iteration(iteration, report, adjustments):
            callbacks.append((iteration, report.feasible))

        def mock_router(adjustments):
            return feasible_routing_report

        run_feedback_loop(
            initial_report=failed_routing_report,
            routing_function=mock_router,
            on_iteration=on_iteration,
        )
        assert len(callbacks) >= 1

    def test_stops_if_no_adjustments_generated(self, layer_conflict_diagnostic):
        """Stops early if no adjustments can be generated."""
        # Layer conflict can't be fixed by placement
        report = RoutingReport(
            feasible=False,
            completion_rate=0.8,
            routed_nets=["VCC", "GND"],
            failed_nets=["HV_BUS"],
            diagnostics=[layer_conflict_diagnostic],
            congestion_map=None,
            total_wirelength=100.0,
            total_vias=5,
            worst_congestion=0.5,
        )

        def mock_router(adjustments):
            return report

        result = run_feedback_loop(
            initial_report=report,
            routing_function=mock_router,
        )
        # Should stop early since no placement adjustments possible
        assert result.converged is False
        assert result.iterations < 5  # Less than max


class TestFeedbackLoopIntegration:
    """Integration tests for feedback loop."""

    def test_full_cycle_no_path_to_success(self):
        """Full cycle: NO_PATH failure -> adjustment -> success."""
        iteration_count = [0]

        # First iteration fails with NO_PATH
        failed_report = RoutingReport(
            feasible=False,
            completion_rate=0.5,
            routed_nets=["GND"],
            failed_nets=["VCC"],
            diagnostics=[
                RoutingDiagnostic(
                    net="VCC",
                    failure_type=FailureType.NO_PATH,
                    location=(25.0, 30.0),
                    severity="critical",
                    blocking_elements=["U1"],
                    constraint_violated=None,
                    suggested_fix="Move U1",
                    fix_confidence=0.7,
                    placement_hint=None,
                )
            ],
            congestion_map=None,
            total_wirelength=50.0,
            total_vias=2,
            worst_congestion=0.8,
        )

        # Success report
        success_report = RoutingReport(
            feasible=True,
            completion_rate=1.0,
            routed_nets=["VCC", "GND"],
            failed_nets=[],
            diagnostics=[],
            congestion_map=None,
            total_wirelength=100.0,
            total_vias=4,
            worst_congestion=0.6,
        )

        def mock_router(adjustments):
            iteration_count[0] += 1
            # After adjustment, routing succeeds
            if iteration_count[0] >= 1 and len(adjustments) > 0:
                return success_report
            return failed_report

        result = run_feedback_loop(
            initial_report=failed_report,
            routing_function=mock_router,
        )

        assert result.converged is True
        assert result.iterations >= 1
        assert len(result.adjustments_applied) > 0

    def test_history_shows_progression(self, failed_routing_report):
        """History shows completion rate progression."""
        rates = [0.5, 0.7, 0.9, 1.0]
        call_count = [0]

        def mock_router(adjustments):
            rate = rates[min(call_count[0], len(rates) - 1)]
            call_count[0] += 1
            return RoutingReport(
                feasible=(rate == 1.0),
                completion_rate=rate,
                routed_nets=[],
                failed_nets=[] if rate == 1.0 else ["NET"],
                diagnostics=[] if rate == 1.0 else failed_routing_report.diagnostics,
                congestion_map=None,
                total_wirelength=0.0,
                total_vias=0,
                worst_congestion=0.0,
            )

        config = FeedbackLoopConfig(max_iterations=5)
        result = run_feedback_loop(
            initial_report=failed_routing_report,
            routing_function=mock_router,
            config=config,
        )

        # History should show completion rates improving
        assert len(result.history) > 0
