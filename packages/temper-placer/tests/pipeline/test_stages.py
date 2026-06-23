"""Tests for extracted stage handler classes."""

import pytest

from temper_placer.pipeline.dag_types import DataContext, StageResult
from temper_placer.pipeline.state import PipelineState


class TestSemanticStage:
    def test_returns_stage_result(self, state):
        from temper_placer.pipeline.stages.semantic_stage import SemanticStage

        stage = SemanticStage()
        context: DataContext = {"loops": []}
        result = stage(state, context)
        assert isinstance(result, StageResult)
        assert "loops_enriched" in result.outputs

    def test_passes_loops_through(self, state):
        from temper_placer.pipeline.stages.semantic_stage import SemanticStage

        stage = SemanticStage()
        context: DataContext = {"loops": [{"name": "loop1"}]}
        result = stage(state, context)
        assert result.outputs["loops_enriched"] == [{"name": "loop1"}]


class TestPreflightStage:
    def test_requires_board_netlist_constraints_in_context(self, state):
        from temper_placer.pipeline.stages.preflight_stage import PreflightStage

        stage = PreflightStage()
        context: DataContext = {}
        with pytest.raises(KeyError):
            stage(state, context)


class TestRoutingStage:
    def test_requires_context_keys(self, state):
        from temper_placer.pipeline.stages.routing_stage import RoutingStage

        stage = RoutingStage()
        context: DataContext = {}
        with pytest.raises(KeyError):
            stage(state, context)


class TestOutputStage:
    def test_no_output_pcb_returns_empty_files(self, state):
        from temper_placer.pipeline.stages.output_stage import OutputStage

        stage = OutputStage()
        context: DataContext = {"input_pcb": None, "board": None, "netlist": None}
        result = stage(state, context)
        assert isinstance(result, StageResult)
        assert "output_files" in result.outputs

    def test_returns_physics_report(self, state):
        from temper_placer.pipeline.stages.output_stage import OutputStage

        stage = OutputStage()
        context: DataContext = {"input_pcb": None, "board": None, "netlist": None}
        result = stage(state, context)
        assert "physics_report" in result.outputs


class TestGeometricStage:
    def test_requires_context_keys(self):
        from temper_placer.pipeline.stages.geometric_stage import GeometricStage
        from temper_placer.pipeline.state import PipelineConfig, PipelineState

        stage = GeometricStage()
        config = PipelineConfig(input_pcb=__import__("pathlib").Path("/tmp/test.kicad_pcb"))
        state = PipelineState(config=config)
        class FakeResult:
            positions = __import__("numpy").array([[0.0, 0.0]])
        context: DataContext = {"deterministic_result": FakeResult()}
        with pytest.raises(KeyError):
            stage(state, context)


class TestTopologicalStage:
    def test_requires_context_keys(self, state):
        from temper_placer.pipeline.stages.topological_stage import TopologicalStage

        stage = TopologicalStage()
        context: DataContext = {}
        with pytest.raises(KeyError):
            stage(state, context)


class TestRefinementStage:
    def test_no_routing_result_returns_empty(self, state):
        from temper_placer.pipeline.stages.refinement_stage import RefinementStage

        stage = RefinementStage()
        context: DataContext = {"board": None, "netlist": None}
        result = stage(state, context)
        assert isinstance(result, StageResult)
        assert result.outputs == {}


class TestInputStage:
    def test_requires_input_pcb(self, state):
        from temper_placer.pipeline.stages.input_stage import InputStage

        stage = InputStage()
        context: DataContext = {}
        with pytest.raises(KeyError):
            stage(state, context)


class TestStageConvention:
    def test_all_stages_are_callable(self):
        from temper_placer.pipeline.stages import (
            GeometricStage,
            InputStage,
            OutputStage,
            PreflightStage,
            RefinementStage,
            RoutingStage,
            SemanticStage,
            TopologicalStage,
        )

        stages = [
            InputStage(),
            SemanticStage(),
            TopologicalStage(),
            PreflightStage(),
            GeometricStage(),
            RoutingStage(),
            RefinementStage(),
            OutputStage(),
        ]
        for stage in stages:
            assert callable(stage), f"{type(stage).__name__} is not callable"

    def test_all_stages_have_no_arg_init(self):
        from temper_placer.pipeline.stages import (
            GeometricStage,
            InputStage,
            OutputStage,
            PreflightStage,
            RefinementStage,
            RoutingStage,
            SemanticStage,
            TopologicalStage,
        )

        classes = [
            InputStage, SemanticStage, TopologicalStage, PreflightStage,
            GeometricStage, RoutingStage, RefinementStage, OutputStage,
        ]
        for cls in classes:
            instance = cls()
            assert instance is not None


class TestStageHandlerProtocol:
    def test_stage_result_has_outputs_and_duration(self):
        result = StageResult(outputs={"x": 1}, duration_s=0.5)
        assert result.outputs == {"x": 1}
        assert result.duration_s == 0.5
