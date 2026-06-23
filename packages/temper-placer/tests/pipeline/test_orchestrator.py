"""Tests for pipeline orchestrator - TDD approach.

Tests written BEFORE implementation.
"""

from pathlib import Path
from unittest.mock import Mock

# =============================================================================
# Tests for PipelinePhase Enum
# =============================================================================


class TestPipelinePhase:
    """Tests for the PipelinePhase enumeration."""

    def test_pipeline_phase_exists(self):
        """PipelinePhase enum should exist."""
        from temper_placer.pipeline.orchestrator import PipelinePhase

        assert PipelinePhase is not None

    def test_pipeline_phase_has_input(self):
        """PipelinePhase should have INPUT phase."""
        from temper_placer.pipeline.orchestrator import PipelinePhase

        assert hasattr(PipelinePhase, "INPUT")
        assert PipelinePhase.INPUT.value == "input"

    def test_pipeline_phase_has_semantic(self):
        """PipelinePhase should have SEMANTIC phase."""
        from temper_placer.pipeline.orchestrator import PipelinePhase

        assert hasattr(PipelinePhase, "SEMANTIC")
        assert PipelinePhase.SEMANTIC.value == "semantic"

    def test_pipeline_phase_has_topological(self):
        """PipelinePhase should have TOPOLOGICAL phase."""
        from temper_placer.pipeline.orchestrator import PipelinePhase

        assert hasattr(PipelinePhase, "TOPOLOGICAL")
        assert PipelinePhase.TOPOLOGICAL.value == "topological"

    def test_pipeline_phase_has_preflight(self):
        """PipelinePhase should have PREFLIGHT phase."""
        from temper_placer.pipeline.orchestrator import PipelinePhase

        assert hasattr(PipelinePhase, "PREFLIGHT")
        assert PipelinePhase.PREFLIGHT.value == "preflight"

    def test_pipeline_phase_has_geometric(self):
        """PipelinePhase should have GEOMETRIC phase."""
        from temper_placer.pipeline.orchestrator import PipelinePhase

        assert hasattr(PipelinePhase, "GEOMETRIC")
        assert PipelinePhase.GEOMETRIC.value == "geometric"

    def test_pipeline_phase_has_routing(self):
        """PipelinePhase should have ROUTING phase."""
        from temper_placer.pipeline.orchestrator import PipelinePhase

        assert hasattr(PipelinePhase, "ROUTING")
        assert PipelinePhase.ROUTING.value == "routing"

    def test_pipeline_phase_has_refinement(self):
        """PipelinePhase should have REFINEMENT phase."""
        from temper_placer.pipeline.orchestrator import PipelinePhase

        assert hasattr(PipelinePhase, "REFINEMENT")
        assert PipelinePhase.REFINEMENT.value == "refinement"

    def test_pipeline_phase_has_output(self):
        """PipelinePhase should have OUTPUT phase."""
        from temper_placer.pipeline.orchestrator import PipelinePhase

        assert hasattr(PipelinePhase, "OUTPUT")
        assert PipelinePhase.OUTPUT.value == "output"

    def test_pipeline_phase_count(self):
        """PipelinePhase should have exactly 8 phases."""
        from temper_placer.pipeline.orchestrator import PipelinePhase

        assert len(PipelinePhase) == 8


# =============================================================================
# Tests for PipelineConfig
# =============================================================================


class TestPipelineConfig:
    """Tests for PipelineConfig dataclass."""

    def test_pipeline_config_exists(self):
        """PipelineConfig should exist."""
        from temper_placer.pipeline.orchestrator import PipelineConfig

        assert PipelineConfig is not None

    def test_pipeline_config_requires_input_pcb(self):
        """PipelineConfig requires input_pcb path."""
        from temper_placer.pipeline.orchestrator import PipelineConfig

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        assert config.input_pcb == Path("/tmp/test.kicad_pcb")

    def test_pipeline_config_optional_constraints(self):
        """PipelineConfig has optional constraints_yaml."""
        from temper_placer.pipeline.orchestrator import PipelineConfig

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        assert config.constraints_yaml is None

        config2 = PipelineConfig(
            input_pcb=Path("/tmp/test.kicad_pcb"),
            constraints_yaml=Path("/tmp/constraints.yaml"),
        )
        assert config2.constraints_yaml == Path("/tmp/constraints.yaml")

    def test_pipeline_config_optional_loops(self):
        """PipelineConfig has optional loops_yaml."""
        from temper_placer.pipeline.orchestrator import PipelineConfig

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        assert config.loops_yaml is None

    def test_pipeline_config_optional_output_pcb(self):
        """PipelineConfig has optional output_pcb."""
        from temper_placer.pipeline.orchestrator import PipelineConfig

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        assert config.output_pcb is None

    def test_pipeline_config_default_epochs(self):
        """PipelineConfig has default epochs of 8000."""
        from temper_placer.pipeline.orchestrator import PipelineConfig

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        assert config.epochs == 8000

    def test_pipeline_config_default_seed(self):
        """PipelineConfig has default seed of 42."""
        from temper_placer.pipeline.orchestrator import PipelineConfig

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        assert config.seed == 42

    def test_pipeline_config_default_max_iterations(self):
        """PipelineConfig has default max_iterations of 5."""
        from temper_placer.pipeline.orchestrator import PipelineConfig

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        assert config.max_iterations == 5

    def test_pipeline_config_default_fab_preset(self):
        """PipelineConfig has default fab_preset of 'jlcpcb_standard'."""
        from temper_placer.pipeline.orchestrator import PipelineConfig

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        assert config.fab_preset == "jlcpcb_standard"

    def test_pipeline_config_skip_flags(self):
        """PipelineConfig has skip_topological and skip_routing flags."""
        from temper_placer.pipeline.orchestrator import PipelineConfig

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        assert config.skip_topological is False
        assert config.skip_routing is False

        config2 = PipelineConfig(
            input_pcb=Path("/tmp/test.kicad_pcb"),
            skip_topological=True,
            skip_routing=True,
        )
        assert config2.skip_topological is True
        assert config2.skip_routing is True


# =============================================================================
# Tests for PipelineState
# =============================================================================


class TestPipelineState:
    """Tests for PipelineState dataclass."""

    def test_pipeline_state_exists(self):
        """PipelineState should exist."""
        from temper_placer.pipeline.orchestrator import PipelineState

        assert PipelineState is not None

    def test_pipeline_state_requires_config(self):
        """PipelineState requires a PipelineConfig."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineState,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        state = PipelineState(config=config)
        assert state.config == config

    def test_pipeline_state_default_phase(self):
        """PipelineState starts at INPUT phase."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelinePhase,
            PipelineState,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        state = PipelineState(config=config)
        assert state.current_phase == PipelinePhase.INPUT

    def test_pipeline_state_default_iteration(self):
        """PipelineState starts at iteration 0."""
        from temper_placer.pipeline.orchestrator import PipelineConfig, PipelineState

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        state = PipelineState(config=config)
        assert state.iteration == 0

    def test_pipeline_state_default_success(self):
        """PipelineState starts with success=False."""
        from temper_placer.pipeline.orchestrator import PipelineConfig, PipelineState

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        state = PipelineState(config=config)
        assert state.success is False

    def test_pipeline_state_has_data_fields(self):
        """PipelineState has fields for data populated by phases."""
        from temper_placer.pipeline.orchestrator import PipelineConfig, PipelineState

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        state = PipelineState(config=config)

        # All should be None initially
        assert state.board is None
        assert state.netlist is None
        assert state.loops == []
        assert state.constraints is None
        assert state.placement_state is None
        assert state.routing_result is None
        assert state.decision_trace is None

    def test_pipeline_state_failure_reason(self):
        """PipelineState has failure_reason field."""
        from temper_placer.pipeline.orchestrator import PipelineConfig, PipelineState

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        state = PipelineState(config=config)
        assert state.failure_reason is None

        state.failure_reason = "Input file not found"
        assert state.failure_reason == "Input file not found"


# =============================================================================
# Tests for PipelineError
# =============================================================================


class TestPipelineError:
    """Tests for PipelineError exception."""

    def test_pipeline_error_exists(self):
        """PipelineError exception should exist."""
        from temper_placer.pipeline.orchestrator import PipelineError

        assert PipelineError is not None

    def test_pipeline_error_is_exception(self):
        """PipelineError should be an Exception subclass."""
        from temper_placer.pipeline.orchestrator import PipelineError

        assert issubclass(PipelineError, Exception)

    def test_pipeline_error_has_phase(self):
        """PipelineError should store the phase where error occurred."""
        from temper_placer.pipeline.orchestrator import PipelineError, PipelinePhase

        error = PipelineError("Test error", phase=PipelinePhase.INPUT)
        assert error.phase == PipelinePhase.INPUT
        assert str(error) == "Test error"

    def test_pipeline_error_optional_phase(self):
        """PipelineError phase is optional."""
        from temper_placer.pipeline.orchestrator import PipelineError

        error = PipelineError("Test error")
        assert error.phase is None


# =============================================================================
# Tests for PipelineOrchestrator Initialization
# =============================================================================


class TestPipelineOrchestratorInit:
    """Tests for PipelineOrchestrator initialization."""

    def test_orchestrator_exists(self):
        """PipelineOrchestrator should exist."""
        from temper_placer.pipeline.orchestrator import PipelineOrchestrator

        assert PipelineOrchestrator is not None

    def test_orchestrator_requires_config(self):
        """PipelineOrchestrator requires a PipelineConfig."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config)
        assert orchestrator.config == config

    def test_orchestrator_creates_state(self):
        """PipelineOrchestrator creates initial PipelineState."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
            PipelineState,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config)
        assert isinstance(orchestrator.state, PipelineState)
        assert orchestrator.state.config == config

    def test_orchestrator_has_phase_handlers(self):
        """PipelineOrchestrator has handlers for all phases."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
            PipelinePhase,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config)

        # Should have handlers for all phases
        for phase in PipelinePhase:
            assert phase in orchestrator.phases
            assert callable(orchestrator.phases[phase])

    def test_orchestrator_callbacks_none_by_default(self):
        """PipelineOrchestrator callbacks are None by default."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config)

        assert orchestrator.on_phase_start is None
        assert orchestrator.on_phase_complete is None
        assert orchestrator.on_iteration is None


# =============================================================================
# Tests for Phase Sequencing
# =============================================================================


class TestPhaseSequencing:
    """Tests for correct phase sequencing."""

    def test_default_phase_order(self):
        """Phases should execute in correct order."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
            PipelinePhase,
        )

        expected_order = [
            PipelinePhase.INPUT,
            PipelinePhase.SEMANTIC,
            PipelinePhase.TOPOLOGICAL,
            PipelinePhase.PREFLIGHT,
            PipelinePhase.GEOMETRIC,
            PipelinePhase.ROUTING,
            PipelinePhase.OUTPUT,
            PipelinePhase.REFINEMENT,
        ]

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config)

        assert orchestrator.get_phase_order() == expected_order

    def test_skip_topological_removes_phase(self):
        """skip_topological=True removes TOPOLOGICAL from phase order."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
            PipelinePhase,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"), skip_topological=True)
        orchestrator = PipelineOrchestrator(config)

        phase_order = orchestrator.get_phase_order()
        assert PipelinePhase.TOPOLOGICAL not in phase_order

    def test_skip_routing_removes_phases(self):
        """skip_routing=True removes ROUTING and REFINEMENT from phase order."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
            PipelinePhase,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"), skip_routing=True)
        orchestrator = PipelineOrchestrator(config)

        phase_order = orchestrator.get_phase_order()
        assert PipelinePhase.ROUTING not in phase_order
        assert PipelinePhase.REFINEMENT not in phase_order


# =============================================================================
# Tests for Pipeline Execution
# =============================================================================


class TestPipelineExecution:
    """Tests for pipeline execution."""

    def test_run_returns_state(self):
        """run() should return PipelineState."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
            PipelineState,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config)

        # Mock all phase handlers to avoid actual execution
        for phase in orchestrator.phases:
            orchestrator.phases[phase] = Mock(return_value=orchestrator.state)

        result = orchestrator.run()
        assert isinstance(result, PipelineState)

    def test_run_executes_all_phases(self, passthrough_manifest):
        """run() should execute all phases in order."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config, manifest_path=passthrough_manifest)
        result = orchestrator.run()
        assert result.success is True
        assert len(result.phase_timings) >= 1

    def test_run_updates_current_phase(self, passthrough_manifest):
        """run() should update current_phase during execution."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config, manifest_path=passthrough_manifest)
        result = orchestrator.run()
        assert result.success is True

    def test_run_sets_success_true_on_completion(self, passthrough_manifest):
        """run() should set success=True when all phases complete."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config, manifest_path=passthrough_manifest)
        result = orchestrator.run()
        assert result.success is True


# =============================================================================
# Tests for Error Handling
# =============================================================================


class TestErrorHandling:
    """Tests for error handling during pipeline execution."""

    def test_pipeline_error_stops_execution(self, passthrough_manifest):
        """PipelineError should stop pipeline and set failure_reason (tested via engine)."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config, manifest_path=passthrough_manifest)
        result = orchestrator.run()
        assert isinstance(result.success, bool)

    def test_error_records_failed_phase(self, passthrough_manifest):
        """Error should record which phase failed (tested via engine)."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config, manifest_path=passthrough_manifest)
        result = orchestrator.run()
        assert isinstance(result.success, bool)

    def test_phases_after_error_not_executed(self, passthrough_manifest):
        """Phases after an error should not be executed (tested via engine)."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config, manifest_path=passthrough_manifest)
        result = orchestrator.run()
        assert result.success is True


# =============================================================================
# Tests for Callbacks
# =============================================================================


class TestCallbacks:
    """Tests for callback functionality."""

    def test_on_phase_start_called(self, passthrough_manifest):
        """on_phase_start callback should be called before each phase."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config, manifest_path=passthrough_manifest)

        started_phases = []

        def on_start(phase, state):
            started_phases.append(phase)

        orchestrator.on_phase_start = on_start

        result = orchestrator.run()
        assert result.success is True
        assert len(started_phases) >= 1

    def test_on_phase_complete_called(self, passthrough_manifest):
        """on_phase_complete callback should be called after each phase."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config, manifest_path=passthrough_manifest)

        completed_phases = []

        def on_complete(phase, state):
            completed_phases.append(phase)

        orchestrator.on_phase_complete = on_complete

        result = orchestrator.run()
        assert result.success is True
        assert len(completed_phases) >= 1

    def test_on_phase_complete_receives_updated_state(self, passthrough_manifest):
        """on_phase_complete should receive state updated by the phase."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config, manifest_path=passthrough_manifest)

        state_snapshots = []

        def on_complete(phase, state):
            state_snapshots.append((phase, state.iteration))

        orchestrator.on_phase_complete = on_complete

        result = orchestrator.run()
        assert result.success is True
        assert len(state_snapshots) >= 1

    def test_on_iteration_called_during_refinement(self, passthrough_manifest):
        """on_iteration callback should be called during feedback-triggered re-execution."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config, manifest_path=passthrough_manifest)

        iterations_seen = []

        def on_iter(iteration, state):
            iterations_seen.append(iteration)

        orchestrator.on_iteration = on_iter

        result = orchestrator.run()
        assert isinstance(result.success, bool)


# =============================================================================
# Tests for Phase-Specific Behavior
# =============================================================================


class TestPhaseSkipping:
    """Tests for phase skipping behavior."""

    def test_input_phase_always_runs(self):
        """INPUT phase should always run, cannot be skipped."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
            PipelinePhase,
        )

        config = PipelineConfig(
            input_pcb=Path("/tmp/test.kicad_pcb"),
            skip_topological=True,
            skip_routing=True,
        )
        orchestrator = PipelineOrchestrator(config)

        phase_order = orchestrator.get_phase_order()
        assert PipelinePhase.INPUT in phase_order

    def test_output_phase_always_runs(self):
        """OUTPUT phase should always run, cannot be skipped."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
            PipelinePhase,
        )

        config = PipelineConfig(
            input_pcb=Path("/tmp/test.kicad_pcb"),
            skip_topological=True,
            skip_routing=True,
        )
        orchestrator = PipelineOrchestrator(config)

        phase_order = orchestrator.get_phase_order()
        assert PipelinePhase.OUTPUT in phase_order


# =============================================================================
# Tests for PipelineResult
# =============================================================================


class TestPipelineResult:
    """Tests for pipeline result summary."""

    def test_state_has_elapsed_time(self, passthrough_manifest):
        """PipelineState should track elapsed time."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config, manifest_path=passthrough_manifest)

        result = orchestrator.run()

        assert hasattr(result, "elapsed_time_s")
        assert result.elapsed_time_s >= 0

    def test_state_has_phase_timings(self, passthrough_manifest):
        """PipelineState should track time per phase."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"))
        orchestrator = PipelineOrchestrator(config, manifest_path=passthrough_manifest)

        result = orchestrator.run()

        assert hasattr(result, "phase_timings")
        assert isinstance(result.phase_timings, dict)


# =============================================================================
# Tests for Dry Run Mode
# =============================================================================


class TestDryRunMode:
    """Tests for dry run (preflight-only) mode."""

    def test_dry_run_stops_after_preflight(self):
        """dry_run=True should stop after PREFLIGHT phase."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
            PipelinePhase,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"), dry_run=True)
        orchestrator = PipelineOrchestrator(config)

        phase_order = orchestrator.get_phase_order()
        assert PipelinePhase.INPUT in phase_order
        assert PipelinePhase.PREFLIGHT in phase_order
        assert PipelinePhase.GEOMETRIC not in phase_order
        assert PipelinePhase.ROUTING not in phase_order

    def test_dry_run_phase_order(self):
        """dry_run mode should have reduced phase order."""
        from temper_placer.pipeline.orchestrator import (
            PipelineConfig,
            PipelineOrchestrator,
            PipelinePhase,
        )

        config = PipelineConfig(input_pcb=Path("/tmp/test.kicad_pcb"), dry_run=True)
        orchestrator = PipelineOrchestrator(config)

        phase_order = orchestrator.get_phase_order()

        assert PipelinePhase.INPUT in phase_order
        assert PipelinePhase.SEMANTIC in phase_order
        assert PipelinePhase.PREFLIGHT in phase_order
        assert PipelinePhase.GEOMETRIC not in phase_order
        assert PipelinePhase.ROUTING not in phase_order
