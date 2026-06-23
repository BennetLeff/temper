"""Shared fixtures for pipeline DAG tests."""

from pathlib import Path

import pytest
import yaml

from temper_placer.pipeline.state import PipelineConfig, PipelineState


@pytest.fixture
def sample_config(tmp_path):
    """Create a PipelineConfig with a synthetic PCB for testing."""
    pcb_path = tmp_path / "test.kicad_pcb"
    pcb_path.write_text("(kicad_pcb (version 20211014))")
    return PipelineConfig(
        input_pcb=pcb_path,
        output_pcb=tmp_path / "output.kicad_pcb",
        epochs=100,
        seed=42,
        max_movement_mm=2.0,
        max_iterations=3,
        routability_threshold=0.85,
        convergence_threshold=0.01,
    )


@pytest.fixture
def dry_run_config(tmp_path):
    """Create a PipelineConfig with dry_run=True."""
    pcb_path = tmp_path / "test.kicad_pcb"
    pcb_path.write_text("(kicad_pcb (version 20211014))")
    return PipelineConfig(
        input_pcb=pcb_path,
        dry_run=True,
        epochs=100,
    )


@pytest.fixture
def skip_routing_config(tmp_path):
    """Create a PipelineConfig with skip_routing=True."""
    pcb_path = tmp_path / "test.kicad_pcb"
    pcb_path.write_text("(kicad_pcb (version 20211014))")
    return PipelineConfig(
        input_pcb=pcb_path,
        skip_routing=True,
        epochs=100,
    )


@pytest.fixture
def state(sample_config):
    """Create a PipelineState from sample_config."""
    return PipelineState(config=sample_config)


@pytest.fixture
def default_manifest_path():
    """Path to the default pipeline manifest."""
    return (
        Path(__file__).parent.parent.parent
        / "configs"
        / "pipeline_default.yaml"
    )


@pytest.fixture
def minimal_manifest(tmp_path):
    """Create a minimal 2-stage DAG manifest for testing."""
    manifest = {
        "pipeline": {"name": "minimal-test", "version": "1.0.0"},
        "stages": [
            {
                "name": "producer",
                "handler": "temper_placer.pipeline.stages.input_stage.InputStage",
                "requires": [],
                "provides": ["data_a"],
                "timeout_s": 5,
            },
            {
                "name": "consumer",
                "handler": "temper_placer.pipeline.stages.semantic_stage.SemanticStage",
                "requires": ["data_a"],
                "provides": ["data_b"],
                "timeout_s": 5,
            },
        ],
    }
    manifest_path = tmp_path / "minimal_manifest.yaml"
    with open(manifest_path, "w") as f:
        yaml.dump(manifest, f)
    return manifest_path


@pytest.fixture
def mock_observer():
    """Create a mock observer that records lifecycle events."""

    class MockObserver:
        def __init__(self):
            self.events = []

        def on_stage_start(self, stage_name, iteration, context):
            self.events.append(("start", stage_name, iteration))

        def on_stage_complete(self, stage_name, duration_s, outputs):
            self.events.append(("complete", stage_name, duration_s))

        def on_stage_skip(self, stage_name, reason):
            self.events.append(("skip", stage_name, reason))

        def on_stage_error(self, stage_name, error):
            self.events.append(("error", stage_name, str(error)))

        def on_feedback_triggered(self, contract_name, from_stage, to_stage, attempt):
            self.events.append(("feedback", contract_name, from_stage, to_stage, attempt))

        def on_pipeline_complete(self, success, total_duration_s, stage_timings):
            self.events.append(("pipeline_complete", success, total_duration_s))

    return MockObserver()


@pytest.fixture
def passthrough_manifest(tmp_path):
    """2-stage linear manifest using PassthroughStage handlers (safe no-ops)."""
    manifest = {
        "pipeline": {"name": "passthrough-test", "version": "1.0.0"},
        "stages": [
            {
                "name": "input",
                "handler": "tests.pipeline.conftest.PassthroughStage",
                "requires": [],
                "provides": ["board", "netlist", "constraints", "loops"],
            },
            {
                "name": "output",
                "handler": "tests.pipeline.conftest.PassthroughStage",
                "requires": ["board", "netlist"],
                "provides": ["output_files", "physics_report"],
            },
        ],
    }
    manifest_path = tmp_path / "passthrough_manifest.yaml"
    with open(manifest_path, "w") as f:
        yaml.dump(manifest, f)
    return manifest_path


class PassthroughStage:
    """Stage handler that does nothing but return success."""

    def __init__(self, outputs=None):
        self._outputs = outputs or {}

    def __call__(self, state, context):
        from temper_placer.pipeline.dag_types import StageResult
        return StageResult(outputs=self._outputs, duration_s=0.0)
