"""Tests for dag_observability module."""

import json
from pathlib import Path

from temper_placer.pipeline.dag_observability import (
    PipelineExecutionLog,
    StageEvent,
    write_execution_log_json,
)


class TestPipelineExecutionLog:
    """Tests for PipelineExecutionLog.to_dict."""

    def test_to_dict_empty(self):
        """Empty log produces expected dict structure."""
        log = PipelineExecutionLog()
        d = log.to_dict()
        assert isinstance(d, dict)
        assert d["dag_topology"] == []
        assert d["stage_order"] == []
        assert d["stage_timings"] == {}
        assert d["retry_counts"] == {}
        assert d["feedback_activations"] == []
        assert d["success"] is False
        assert d["total_duration_s"] == 0.0
        assert d["events"] == []

    def test_to_dict_with_data(self):
        """Log with data serializes correctly."""
        event = StageEvent(
            name="stage_0",
            kind="load_pcb",
            iteration=0,
            duration_s=0.5,
            outputs={"routed": 42},
        )
        log = PipelineExecutionLog(
            dag_topology=[{"from": "a", "to": "b"}],
            stage_order=["a", "b"],
            stage_timings={"a": 1.0, "b": 2.0},
            retry_counts={"a": 1},
            feedback_activations=[{"contract": "sidecar", "attempt": 1}],
            success=True,
            total_duration_s=3.5,
            events=[event],
        )
        d = log.to_dict()
        assert d["success"] is True
        assert d["total_duration_s"] == 3.5
        assert d["stage_order"] == ["a", "b"]
        assert len(d["events"]) == 1
        assert d["events"][0]["name"] == "stage_0"
        assert d["events"][0]["kind"] == "load_pcb"

    def test_to_dict_events_exclude_none_fields(self):
        """StageEvent None fields are excluded from serialization."""
        event = StageEvent(name="simple", kind="pass")
        log = PipelineExecutionLog(events=[event])
        d = log.to_dict()
        evt = d["events"][0]
        assert "name" in evt
        assert "kind" in evt
        # Fields with None defaults should not appear
        assert "error" not in evt
        assert "feedback_contract" not in evt


class TestWriteExecutionLogJson:
    """Tests for write_execution_log_json."""

    def test_writes_json_file(self, tmp_path: Path):
        """Writes a valid JSON file and returns the path."""
        log = PipelineExecutionLog(
            success=True,
            total_duration_s=2.0,
            stage_order=["load", "route"],
        )
        out_path = write_execution_log_json(log, tmp_path)
        assert out_path.exists()
        assert out_path.suffix == ".json"
        data = json.loads(out_path.read_text())
        assert data["success"] is True
        assert data["total_duration_s"] == 2.0
        assert data["stage_order"] == ["load", "route"]

    def test_creates_output_dir(self, tmp_path: Path):
        """Creates output directory if it does not exist."""
        out_dir = tmp_path / "nested" / "logs"
        log = PipelineExecutionLog()
        out_path = write_execution_log_json(log, out_dir)
        assert out_path.parent.exists()
        assert out_path.exists()

    def test_file_named_pipeline_execution_json(self, tmp_path: Path):
        """Output file is named pipeline_execution.json."""
        log = PipelineExecutionLog()
        out_path = write_execution_log_json(log, tmp_path)
        assert out_path.name == "pipeline_execution.json"
