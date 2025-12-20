"""Tests for JSON serialization of decision traces."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from temper_placer.explainability.decision import (
    Alternative,
    Decision,
    DecisionPhase,
    DecisionTrace,
    DecisionType,
)
from temper_placer.explainability.serialization import (
    deserialize_alternative,
    deserialize_decision,
    deserialize_trace,
    load_trace,
    save_trace,
    serialize_alternative,
    serialize_decision,
    serialize_trace,
    trace_from_json,
    trace_to_json,
)


class TestSerializeAlternative:
    """Tests for Alternative serialization."""

    def test_serialize_basic(self):
        """Test serializing a basic alternative."""
        alt = Alternative(
            value=(10, 20),
            rejection_reason="Too close to edge",
        )
        result = serialize_alternative(alt)

        assert result["value"] == [10, 20]  # tuple -> list
        assert result["rejection_reason"] == "Too close to edge"
        assert result["constraint_violated"] is None
        assert result["loss_if_chosen"] is None

    def test_serialize_full(self):
        """Test serializing an alternative with all fields."""
        alt = Alternative(
            value={"x": 45.0, "y": 12.5},
            rejection_reason="Violates clearance",
            constraint_violated="clearance.hv_lv",
            loss_if_chosen=125.5,
        )
        result = serialize_alternative(alt)

        assert result["value"] == {"x": 45.0, "y": 12.5}
        assert result["rejection_reason"] == "Violates clearance"
        assert result["constraint_violated"] == "clearance.hv_lv"
        assert result["loss_if_chosen"] == 125.5

    def test_deserialize_basic(self):
        """Test deserializing a basic alternative."""
        data = {
            "value": [30, 40],
            "rejection_reason": "Outside zone",
        }
        alt = deserialize_alternative(data)

        assert alt.value == [30, 40]
        assert alt.rejection_reason == "Outside zone"
        assert alt.constraint_violated is None
        assert alt.loss_if_chosen is None

    def test_roundtrip(self):
        """Test serialize -> deserialize roundtrip."""
        original = Alternative(
            value=(15.5, 22.3),
            rejection_reason="Conflicts with U1",
            constraint_violated="adjacent.Q1_U1",
            loss_if_chosen=45.7,
        )
        serialized = serialize_alternative(original)
        restored = deserialize_alternative(serialized)

        # Note: tuple becomes list in JSON
        assert restored.value == [15.5, 22.3]
        assert restored.rejection_reason == original.rejection_reason
        assert restored.constraint_violated == original.constraint_violated
        assert restored.loss_if_chosen == original.loss_if_chosen


class TestSerializeDecision:
    """Tests for Decision serialization."""

    def test_serialize_basic(self):
        """Test serializing a basic decision."""
        decision = Decision(
            id="test-123",
            subject="Q1",
            value=(45.0, 12.0),
            reason="Initial placement",
        )
        result = serialize_decision(decision)

        assert result["id"] == "test-123"
        assert result["subject"] == "Q1"
        assert result["value"] == [45.0, 12.0]
        assert result["reason"] == "Initial placement"
        assert result["phase"] == "geometric"  # default
        assert result["decision_type"] == "position_update"  # default

    def test_serialize_with_alternatives(self):
        """Test serializing a decision with alternatives."""
        decision = Decision(
            subject="U_MCU",
            value=(50, 50),
            reason="Center placement",
            alternatives=[
                Alternative(
                    value=(10, 10),
                    rejection_reason="Too close to edge",
                ),
                Alternative(
                    value=(90, 90),
                    rejection_reason="Too close to power section",
                    constraint_violated="clearance.hv_lv",
                ),
            ],
        )
        result = serialize_decision(decision)

        assert len(result["alternatives"]) == 2
        assert result["alternatives"][0]["value"] == [10, 10]
        assert result["alternatives"][1]["constraint_violated"] == "clearance.hv_lv"

    def test_serialize_all_phases(self):
        """Test serializing decisions from all phases."""
        for phase in DecisionPhase:
            decision = Decision(subject="X1", phase=phase, reason="test")
            result = serialize_decision(decision)
            assert result["phase"] == phase.value

    def test_serialize_all_types(self):
        """Test serializing all decision types."""
        for dtype in DecisionType:
            decision = Decision(subject="X1", decision_type=dtype, reason="test")
            result = serialize_decision(decision)
            assert result["decision_type"] == dtype.value

    def test_deserialize_basic(self):
        """Test deserializing a basic decision."""
        data = {
            "id": "abc-123",
            "timestamp": "2025-12-19T10:00:00",
            "phase": "topological",
            "decision_type": "initial_position",
            "subject": "C1",
            "value": [20, 30],
            "reason": "Placed near IC",
        }
        decision = deserialize_decision(data)

        assert decision.id == "abc-123"
        assert decision.phase == DecisionPhase.TOPOLOGICAL
        assert decision.decision_type == DecisionType.INITIAL_POSITION
        assert decision.subject == "C1"
        assert decision.value == [20, 30]
        assert decision.reason == "Placed near IC"

    def test_deserialize_invalid_phase(self):
        """Test deserializing with invalid phase defaults to GEOMETRIC."""
        data = {
            "id": "test",
            "subject": "X1",
            "phase": "invalid_phase",
            "reason": "test",
        }
        decision = deserialize_decision(data)
        assert decision.phase == DecisionPhase.GEOMETRIC

    def test_deserialize_invalid_type(self):
        """Test deserializing with invalid type defaults to POSITION_UPDATE."""
        data = {
            "id": "test",
            "subject": "X1",
            "decision_type": "invalid_type",
            "reason": "test",
        }
        decision = deserialize_decision(data)
        assert decision.decision_type == DecisionType.POSITION_UPDATE

    def test_roundtrip(self):
        """Test serialize -> deserialize roundtrip."""
        original = Decision(
            id="round-001",
            phase=DecisionPhase.ROUTING,
            decision_type=DecisionType.LAYER_ASSIGNMENT,
            subject="NET_VCC",
            value="L1",
            previous_value="L2",
            reason="Better signal integrity on L1",
            constraint_refs=["layer.power", "impedance.50ohm"],
            loss_contribution=12.5,
            epoch=500,
            iteration=3,
            alternatives=[
                Alternative(
                    value="L3",
                    rejection_reason="Too thin copper",
                    loss_if_chosen=25.0,
                )
            ],
        )
        serialized = serialize_decision(original)
        restored = deserialize_decision(serialized)

        assert restored.id == original.id
        assert restored.phase == original.phase
        assert restored.decision_type == original.decision_type
        assert restored.subject == original.subject
        assert restored.value == original.value
        assert restored.previous_value == original.previous_value
        assert restored.reason == original.reason
        assert restored.constraint_refs == original.constraint_refs
        assert restored.loss_contribution == original.loss_contribution
        assert restored.epoch == original.epoch
        assert restored.iteration == original.iteration
        assert len(restored.alternatives) == 1


class TestSerializeTrace:
    """Tests for DecisionTrace serialization."""

    def test_serialize_empty(self):
        """Test serializing an empty trace."""
        trace = DecisionTrace(run_id="empty-trace")
        result = serialize_trace(trace)

        assert result["run_id"] == "empty-trace"
        assert result["decisions"] == []
        assert result["final_positions"] == {}
        assert result["final_metrics"] == {}

    def test_serialize_with_decisions(self):
        """Test serializing a trace with decisions."""
        trace = DecisionTrace(run_id="test-run")
        trace.add(Decision(subject="Q1", value=(10, 20), reason="First"))
        trace.add(Decision(subject="Q2", value=(30, 40), reason="Second"))

        result = serialize_trace(trace)

        assert result["run_id"] == "test-run"
        assert len(result["decisions"]) == 2
        assert result["decisions"][0]["subject"] == "Q1"
        assert result["decisions"][1]["subject"] == "Q2"

    def test_serialize_finalized(self):
        """Test serializing a finalized trace."""
        trace = DecisionTrace(run_id="final-run")
        trace.add(Decision(subject="Q1", value=(45, 12), reason="Placed"))
        trace.finalize(
            positions={"Q1": (45.0, 12.0), "Q2": (30.0, 40.0)},
            metrics={"total_loss": 123.5, "overlap": 0.0},
        )

        result = serialize_trace(trace)

        assert result["end_time"] is not None
        assert result["final_positions"]["Q1"] == [45.0, 12.0]
        assert result["final_positions"]["Q2"] == [30.0, 40.0]
        assert result["final_metrics"]["total_loss"] == 123.5

    def test_deserialize_empty(self):
        """Test deserializing an empty trace."""
        data = {"run_id": "empty", "decisions": []}
        trace = deserialize_trace(data)

        assert trace.run_id == "empty"
        assert len(trace.decisions) == 0

    def test_deserialize_with_decisions(self):
        """Test deserializing a trace with decisions."""
        data = {
            "run_id": "loaded",
            "start_time": "2025-12-19T09:00:00",
            "decisions": [
                {"id": "d1", "subject": "C1", "value": [5, 10], "reason": "Decap"},
                {"id": "d2", "subject": "C2", "value": [15, 20], "reason": "Decap"},
            ],
        }
        trace = deserialize_trace(data)

        assert trace.run_id == "loaded"
        assert len(trace.decisions) == 2
        assert trace.decisions[0].subject == "C1"
        assert trace.decisions[1].subject == "C2"

    def test_deserialize_final_positions(self):
        """Test deserializing converts position lists to tuples."""
        data = {
            "run_id": "pos-test",
            "decisions": [],
            "final_positions": {
                "Q1": [45.0, 12.0],
                "Q2": [30.5, 40.5],
            },
        }
        trace = deserialize_trace(data)

        assert trace.final_positions["Q1"] == (45.0, 12.0)
        assert trace.final_positions["Q2"] == (30.5, 40.5)

    def test_roundtrip(self):
        """Test full serialize -> deserialize roundtrip."""
        original = DecisionTrace(
            run_id="roundtrip-test",
            config_snapshot={"epochs": 8000, "lr": 0.01},
        )
        original.add(
            Decision(
                subject="Q1",
                decision_type=DecisionType.INITIAL_POSITION,
                phase=DecisionPhase.GEOMETRIC,
                value=(45, 12),
                reason="Thermal edge",
                alternatives=[
                    Alternative(
                        value=(50, 10),
                        rejection_reason="Clearance violation",
                        constraint_violated="clearance.hv_lv",
                    )
                ],
            )
        )
        original.add(
            Decision(
                subject="Q1",
                decision_type=DecisionType.POSITION_UPDATE,
                value=(46, 13),
                previous_value=(45, 12),
                reason="Gradient adjustment",
                epoch=100,
            )
        )
        original.finalize(
            positions={"Q1": (46.0, 13.0)},
            metrics={"loss": 50.0},
        )

        serialized = serialize_trace(original)
        restored = deserialize_trace(serialized)

        assert restored.run_id == original.run_id
        assert restored.config_snapshot == original.config_snapshot
        assert len(restored.decisions) == 2
        assert restored.decisions[0].subject == "Q1"
        assert restored.decisions[0].phase == DecisionPhase.GEOMETRIC
        assert len(restored.decisions[0].alternatives) == 1
        assert restored.final_positions["Q1"] == (46.0, 13.0)
        assert restored.final_metrics["loss"] == 50.0


class TestFileIO:
    """Tests for file save/load operations."""

    def test_save_and_load(self):
        """Test saving and loading a trace to/from file."""
        trace = DecisionTrace(run_id="file-test")
        trace.add(Decision(subject="Q1", value=(10, 20), reason="Test"))
        trace.finalize(positions={"Q1": (10.0, 20.0)})

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)

        try:
            save_trace(trace, path)
            loaded = load_trace(path)

            assert loaded.run_id == trace.run_id
            assert len(loaded.decisions) == 1
            assert loaded.final_positions["Q1"] == (10.0, 20.0)
        finally:
            path.unlink()

    def test_save_creates_valid_json(self):
        """Test that saved file contains valid JSON."""
        trace = DecisionTrace(run_id="valid-json")
        trace.add(Decision(subject="X1", value="test", reason="JSON test"))

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)

        try:
            save_trace(trace, path)

            # Read and parse raw JSON
            with open(path) as f:
                data = json.load(f)

            assert data["run_id"] == "valid-json"
            assert len(data["decisions"]) == 1
        finally:
            path.unlink()

    def test_save_is_human_readable(self):
        """Test that saved JSON is indented for readability."""
        trace = DecisionTrace(run_id="readable")
        trace.add(Decision(subject="X1", value=(1, 2), reason="Test"))

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)

        try:
            save_trace(trace, path)

            with open(path) as f:
                content = f.read()

            # Should have newlines and indentation
            assert "\n" in content
            assert "  " in content  # 2-space indent
        finally:
            path.unlink()

    def test_load_nonexistent_file(self):
        """Test loading a nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_trace(Path("/nonexistent/path/file.json"))


class TestStringIO:
    """Tests for JSON string serialization."""

    def test_to_json(self):
        """Test converting trace to JSON string."""
        trace = DecisionTrace(run_id="string-test")
        trace.add(Decision(subject="X1", value=42, reason="Answer"))

        json_str = trace_to_json(trace)

        assert isinstance(json_str, str)
        data = json.loads(json_str)
        assert data["run_id"] == "string-test"

    def test_from_json(self):
        """Test creating trace from JSON string."""
        json_str = '{"run_id": "from-string", "decisions": []}'
        trace = trace_from_json(json_str)

        assert trace.run_id == "from-string"
        assert len(trace.decisions) == 0

    def test_roundtrip_string(self):
        """Test JSON string roundtrip."""
        original = DecisionTrace(run_id="string-roundtrip")
        original.add(Decision(subject="Y1", value=(5, 10), reason="Test"))

        json_str = trace_to_json(original)
        restored = trace_from_json(json_str)

        assert restored.run_id == original.run_id
        assert len(restored.decisions) == 1

    def test_compact_json(self):
        """Test compact JSON output (no indentation)."""
        trace = DecisionTrace(run_id="compact")
        trace.add(Decision(subject="Z1", value=1, reason="Compact"))

        compact = trace_to_json(trace, indent=None)

        # Should not have extra whitespace
        assert "\n" not in compact


class TestSpecialValues:
    """Tests for handling special value types."""

    def test_numpy_array_simulation(self):
        """Test handling objects with tolist() method (numpy/jax arrays)."""

        class MockArray:
            def __init__(self, data):
                self._data = data

            def tolist(self):
                return self._data

        decision = Decision(
            subject="X1",
            value=MockArray([1.0, 2.0, 3.0]),
            reason="Array test",
        )
        result = serialize_decision(decision)

        assert result["value"] == [1.0, 2.0, 3.0]

    def test_nested_dict(self):
        """Test serializing nested dictionary values."""
        decision = Decision(
            subject="X1",
            value={
                "position": (10, 20),
                "rotation": 90,
                "zone": "power",
            },
            reason="Complex value",
        )
        result = serialize_decision(decision)

        assert result["value"]["position"] == [10, 20]
        assert result["value"]["rotation"] == 90
        assert result["value"]["zone"] == "power"

    def test_none_values(self):
        """Test handling None values."""
        decision = Decision(
            subject="X1",
            value=None,
            previous_value=None,
            reason="None test",
        )
        result = serialize_decision(decision)

        assert result["value"] is None
        assert result["previous_value"] is None

    def test_list_of_tuples(self):
        """Test serializing list of tuples."""
        decision = Decision(
            subject="NET_X",
            value=[(0, 0), (10, 10), (20, 20)],  # Path points
            reason="Path selection",
        )
        result = serialize_decision(decision)

        assert result["value"] == [[0, 0], [10, 10], [20, 20]]
