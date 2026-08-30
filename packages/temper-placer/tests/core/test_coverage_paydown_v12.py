"""Coverage paydown v12: io/, pipeline/, and misc pure-function tests.

Targets allowlist entries across:
- io/placement_exporter (5): soft_to_discrete_rotations, rotation_index_to_degrees,
  positions_to_placements, cleanup_temp_pcb, create_pcb_exporter
- io/kicad_writer (2): placements_to_json, placements_from_json
- pipeline/bottleneck_report (12): BottleneckNetEntry, BottleneckRegion,
  CongestionHeatmapData, BottleneckReport to_dict/from_dict/from_json/to_json
  + routed_count/failed_count
- pipeline/convergence (1): is_converged
- pipeline/dag_observability (2): PipelineExecutionLog.to_dict, write_execution_log_json
- pipeline/explainability (4): DecisionLogger.log_placement, log_routing, finish,
  generate_markdown_report
- pipeline/derivation (2): derive_constraints_from_spec, apply_derived_constraints
"""

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from temper_placer.io.kicad_writer import (
    PlacementUpdate,
    placements_from_json,
    placements_to_json,
)
from temper_placer.io.placement_exporter import (
    cleanup_temp_pcb,
    create_pcb_exporter,
    positions_to_placements,
    rotation_index_to_degrees,
    soft_to_discrete_rotations,
)
from temper_placer.pipeline.bottleneck_report import (
    BottleneckNetEntry,
    BottleneckRegion,
    BottleneckReport,
    CongestionHeatmapData,
)
from temper_placer.pipeline.convergence import is_converged
from temper_placer.pipeline.dag_observability import (
    PipelineExecutionLog,
    write_execution_log_json,
)
from temper_placer.pipeline.derivation import (
    apply_derived_constraints,
    derive_constraints_from_spec,
)
from temper_placer.pipeline.explainability import (
    DecisionLogger,
    generate_markdown_report,
)


# ---------------------------------------------------------------------------
# io/placement_exporter
# ---------------------------------------------------------------------------


class TestSoftToDiscreteRotations:
    """Tests for io/placement_exporter.py::soft_to_discrete_rotations."""

    def test_basic_one_hot(self):
        """Argmax of (N, 4) one-hot vectors returns discrete indices."""
        rotations = np.array(
            [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]],
        )
        result = soft_to_discrete_rotations(rotations)
        expected = np.array([0, 1, 2])
        np.testing.assert_array_equal(result, expected)

    def test_soft_values(self):
        """Argmax works with soft (non-one-hot) inputs."""
        rotations = np.array([[0.1, 0.8, 0.05, 0.05], [0.7, 0.1, 0.1, 0.1]])
        result = soft_to_discrete_rotations(rotations)
        expected = np.array([1, 0])
        np.testing.assert_array_equal(result, expected)

    def test_tie_break_first(self):
        """Argmax ties break to first maximum."""
        rotations = np.array([[0.0, 0.5, 0.5, 0.0]])
        result = soft_to_discrete_rotations(rotations)
        assert result[0] == 1

    def test_single_component(self):
        """Single component (1, 4) works."""
        rotations = np.array([[0.0, 0.0, 0.0, 1.0]])
        result = soft_to_discrete_rotations(rotations)
        assert result.shape == (1,)
        assert result[0] == 3


class TestRotationIndexToDegrees:
    """Tests for io/placement_exporter.py::rotation_index_to_degrees."""

    def test_zero(self):
        assert rotation_index_to_degrees(0) == 0.0

    def test_90(self):
        assert rotation_index_to_degrees(1) == 90.0

    def test_180(self):
        assert rotation_index_to_degrees(2) == 180.0

    def test_270(self):
        assert rotation_index_to_degrees(3) == 270.0


class TestPositionsToPlacements:
    """Tests for io/placement_exporter.py::positions_to_placements."""

    def test_basic_conversion(self):
        positions = np.array([[10.0, 20.0], [30.0, 40.0]])
        rotations = np.array(
            [[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]],
        )
        comp_refs = ["U1", "C1"]
        result = positions_to_placements(positions, rotations, comp_refs)

        assert len(result) == 2
        assert result["U1"].ref == "U1"
        assert result["U1"].x == 10.0
        assert result["U1"].y == 20.0
        assert result["U1"].rotation == 0.0

        assert result["C1"].ref == "C1"
        assert result["C1"].x == 30.0
        assert result["C1"].y == 40.0
        assert result["C1"].rotation == 180.0

    def test_with_origin_offset(self):
        positions = np.array([[5.0, 5.0]])
        rotations = np.array([[0.0, 0.0, 0.0, 1.0]])
        comp_refs = ["J1"]
        result = positions_to_placements(
            positions, rotations, comp_refs, origin=(100.0, 50.0),
        )
        assert result["J1"].x == 105.0
        assert result["J1"].y == 55.0
        assert result["J1"].rotation == 270.0

    def test_mismatched_position_count_raises(self):
        # Rotation count must match comp_refs (checked first), so only
        # positions can be mismatched.
        positions = np.array([[1.0, 2.0]])
        rotations = np.array([[1.0, 0.0, 0.0, 0.0]])
        comp_refs = ["U1", "U2"]
        with pytest.raises(ValueError, match="Position count"):
            positions_to_placements(positions, rotations, comp_refs)

    def test_mismatched_rotation_count_raises(self):
        positions = np.array([[1.0, 2.0], [3.0, 4.0]])
        rotations = np.array([[1.0, 0.0, 0.0, 0.0]])
        comp_refs = ["U1", "U2"]
        with pytest.raises(ValueError, match="Rotation count"):
            positions_to_placements(positions, rotations, comp_refs)

    def test_empty(self):
        result = positions_to_placements(
            np.zeros((0, 2)), np.zeros((0, 4)), [],
        )
        assert result == {}


class TestCleanupTempPcb:
    """Tests for io/placement_exporter.py::cleanup_temp_pcb."""

    def test_deletes_existing_file(self):
        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            path = Path(f.name)
        try:
            assert path.exists()
            result = cleanup_temp_pcb(path)
            assert result is True
            assert not path.exists()
        finally:
            if path.exists():
                path.unlink()

    def test_returns_false_for_nonexistent(self):
        result = cleanup_temp_pcb(Path("/tmp/nonexistent_xyz_12345.kicad_pcb"))
        assert result is False


class TestCreatePcbExporter:
    """Tests for io/placement_exporter.py::create_pcb_exporter."""

    def test_returns_callable(self):
        exporter = create_pcb_exporter(
            template_pcb=Path("/nonexistent/template.kicad_pcb"),
            board_origin=(0.0, 0.0),
        )
        assert callable(exporter)

    def test_returns_callable_with_temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = create_pcb_exporter(
                template_pcb=Path("/nonexistent/template.kicad_pcb"),
                board_origin=(0.0, 0.0),
                temp_dir=Path(tmpdir),
            )
            assert callable(exporter)


# ---------------------------------------------------------------------------
# io/kicad_writer
# ---------------------------------------------------------------------------


class TestPlacementsToFromJson:
    """Tests for io/kicad_writer.py::placements_to_json / placements_from_json."""

    def test_roundtrip(self):
        placements = {
            "U1": PlacementUpdate(ref="U1", x=10.5, y=20.25, rotation=0.0),
            "C1": PlacementUpdate(ref="C1", x=30.0, y=40.0, rotation=90.0),
        }
        d = placements_to_json(placements)
        assert isinstance(d, dict)
        assert d["U1"]["x"] == 10.5
        assert d["U1"]["y"] == 20.25
        assert d["U1"]["rotation"] == 0.0

        restored = placements_from_json(d)
        assert len(restored) == 2
        assert restored["U1"].ref == "U1"
        assert restored["U1"].x == 10.5
        assert restored["U1"].y == 20.25
        assert restored["U1"].rotation == 0.0
        assert restored["C1"].ref == "C1"
        assert restored["C1"].x == 30.0
        assert restored["C1"].y == 40.0
        assert restored["C1"].rotation == 90.0

    def test_empty(self):
        assert placements_to_json({}) == {}
        assert placements_from_json({}) == {}

    def test_single(self):
        d = placements_to_json({"R1": PlacementUpdate(ref="R1", x=1.0, y=2.0, rotation=180.0)})
        assert len(d) == 1
        restored = placements_from_json(d)
        assert restored["R1"].rotation == 180.0


# ---------------------------------------------------------------------------
# pipeline/bottleneck_report
# ---------------------------------------------------------------------------

_NET_ENTRY_DICT = {
    "net_name": "VOUT",
    "net_class": "Power",
    "failure_reason": "congestion",
    "pin_positions": [[0.0, 0.0], [10.0, 20.0]],
}

_REGION_DICT = {
    "x_min": 0.0,
    "y_min": 10.0,
    "x_max": 50.0,
    "y_max": 60.0,
    "affected_components": ["U1", "C1"],
}

_HEATMAP_DICT = {
    "net_class": "Power",
    "grid": [[0.1, 0.2], [0.3, 0.4]],
    "cell_size": 1.0,
}


class TestBottleneckNetEntry:
    """Tests for BottleneckNetEntry.to_dict / from_dict."""

    def test_to_dict(self):
        entry = BottleneckNetEntry(
            net_name="VOUT",
            net_class="Power",
            failure_reason="congestion",
            pin_positions=[(0.0, 0.0), (10.0, 20.0)],
        )
        d = entry.to_dict()
        assert d == _NET_ENTRY_DICT

    def test_from_dict(self):
        entry = BottleneckNetEntry.from_dict(_NET_ENTRY_DICT)
        assert entry.net_name == "VOUT"
        assert entry.net_class == "Power"
        assert entry.failure_reason == "congestion"
        assert entry.pin_positions == [(0.0, 0.0), (10.0, 20.0)]

    def test_roundtrip(self):
        entry = BottleneckNetEntry(
            net_name="GND",
            net_class="Signal",
            failure_reason="overflow",
            pin_positions=[(5.0, 5.0)],
        )
        restored = BottleneckNetEntry.from_dict(entry.to_dict())
        assert restored == entry


class TestBottleneckRegion:
    """Tests for BottleneckRegion.to_dict / from_dict."""

    def test_to_dict(self):
        region = BottleneckRegion(
            x_min=0.0, y_min=10.0, x_max=50.0, y_max=60.0,
            affected_components=["U1", "C1"],
        )
        d = region.to_dict()
        assert d == _REGION_DICT

    def test_from_dict(self):
        region = BottleneckRegion.from_dict(_REGION_DICT)
        assert region.x_min == 0.0
        assert region.y_min == 10.0
        assert region.x_max == 50.0
        assert region.y_max == 60.0
        assert region.affected_components == ["U1", "C1"]

    def test_roundtrip(self):
        region = BottleneckRegion(
            x_min=1.0, y_min=2.0, x_max=3.0, y_max=4.0,
            affected_components=["R1"],
        )
        restored = BottleneckRegion.from_dict(region.to_dict())
        assert restored == region


class TestCongestionHeatmapData:
    """Tests for CongestionHeatmapData.to_dict / from_dict."""

    def test_to_dict(self):
        hd = CongestionHeatmapData(
            net_class="Power",
            grid=[[0.1, 0.2], [0.3, 0.4]],
            cell_size=1.0,
        )
        d = hd.to_dict()
        assert d == _HEATMAP_DICT

    def test_from_dict(self):
        hd = CongestionHeatmapData.from_dict(_HEATMAP_DICT)
        assert hd.net_class == "Power"
        assert hd.grid == [[0.1, 0.2], [0.3, 0.4]]
        assert hd.cell_size == 1.0

    def test_roundtrip(self):
        hd = CongestionHeatmapData(
            net_class="Signal", grid=[[0.0]], cell_size=0.5,
        )
        restored = CongestionHeatmapData.from_dict(hd.to_dict())
        assert restored == hd


class TestBottleneckReport:
    """Tests for BottleneckReport to_dict/from_dict/to_json/from_json + properties."""

    def _make_report(self) -> BottleneckReport:
        return BottleneckReport(
            schema_version="1.0.0",
            failed_nets=[
                BottleneckNetEntry(
                    net_name="VOUT",
                    net_class="Power",
                    failure_reason="congestion",
                    pin_positions=[(0.0, 0.0)],
                ),
            ],
            routed_nets=["GND", "VIN"],
            congestion_heatmaps={
                "Power": CongestionHeatmapData(
                    net_class="Power", grid=[[0.5]], cell_size=1.0,
                ),
            },
            bottleneck_regions=[
                BottleneckRegion(
                    x_min=0.0, y_min=0.0, x_max=10.0, y_max=10.0,
                    affected_components=["U1"],
                ),
            ],
            routability_ratio=0.75,
            total_nets=4,
        )

    def test_to_dict(self):
        report = self._make_report()
        d = report.to_dict()
        assert d["schema_version"] == "1.0.0"
        assert len(d["failed_nets"]) == 1
        assert d["routed_nets"] == ["GND", "VIN"]
        assert "Power" in d["congestion_heatmaps"]
        assert len(d["bottleneck_regions"]) == 1
        assert d["routability_ratio"] == 0.75
        assert d["total_nets"] == 4

    def test_from_dict(self):
        d = self._make_report().to_dict()
        report = BottleneckReport.from_dict(d)
        assert report.schema_version == "1.0.0"
        assert len(report.failed_nets) == 1
        assert report.routed_nets == ["GND", "VIN"]
        assert "Power" in report.congestion_heatmaps
        assert len(report.bottleneck_regions) == 1
        assert report.routability_ratio == 0.75
        assert report.total_nets == 4

    def test_to_json(self):
        report = self._make_report()
        json_str = report.to_json()
        assert isinstance(json_str, str)
        parsed = json.loads(json_str)
        assert parsed["schema_version"] == "1.0.0"

    def test_from_json(self):
        json_str = self._make_report().to_json()
        report = BottleneckReport.from_json(json_str)
        assert report.total_nets == 4
        assert len(report.routed_nets) == 2

    def test_roundtrip_json(self):
        report = self._make_report()
        restored = BottleneckReport.from_json(report.to_json())
        assert restored.to_dict() == report.to_dict()

    def test_routed_count(self):
        report = BottleneckReport(routed_nets=["A", "B", "C"])
        assert report.routed_count == 3

    def test_routed_count_empty(self):
        report = BottleneckReport()
        assert report.routed_count == 0

    def test_failed_count(self):
        report = BottleneckReport(
            failed_nets=[
                BottleneckNetEntry(
                    "A", "Power", "x", [(0.0, 0.0)],
                ),
                BottleneckNetEntry(
                    "B", "Signal", "y", [(1.0, 1.0)],
                ),
            ],
        )
        assert report.failed_count == 2

    def test_failed_count_empty(self):
        report = BottleneckReport()
        assert report.failed_count == 0

    def test_read_write(self, tmp_path):
        report = self._make_report()
        path = tmp_path / "bottleneck.json"
        report.write(path)
        assert path.exists()
        restored = BottleneckReport.read(path)
        assert restored.to_dict() == report.to_dict()

    def test_default_construction(self):
        """BottleneckReport defaults are sensible."""
        report = BottleneckReport()
        assert report.schema_version == "1.0.0"
        assert report.failed_nets == []
        assert report.routed_nets == []
        assert report.congestion_heatmaps == {}
        assert report.bottleneck_regions == []
        assert report.routability_ratio == 0.0
        assert report.total_nets == 0


# ---------------------------------------------------------------------------
# pipeline/convergence
# ---------------------------------------------------------------------------


class TestIsConverged:
    """Tests for pipeline/convergence.py::is_converged."""

    def test_empty_current_returns_false(self):
        """Empty current_results -> False."""
        from dataclasses import dataclass

        @dataclass
        class FakeResult:
            success: bool = False
            length: float = 0.0

        assert is_converged({}, None) is False

    def test_all_success_returns_true(self):
        from dataclasses import dataclass

        @dataclass
        class FakeResult:
            success: bool = True
            length: float = 100.0

        results = {"s1": FakeResult(success=True, length=100.0)}
        assert is_converged(results, None) is True

    def test_no_previous_returns_false(self):
        from dataclasses import dataclass

        @dataclass
        class FakeResult:
            success: bool = False
            length: float = 100.0

        results = {"s1": FakeResult(success=False, length=100.0)}
        assert is_converged(results, None) is False

    def test_identical_stagnation_returns_true(self):
        from dataclasses import dataclass

        @dataclass
        class FakeResult:
            success: bool = False
            length: float = 100.0

        current = {"a": FakeResult(success=False, length=100.0)}
        previous = {"a": FakeResult(success=False, length=100.0)}
        assert is_converged(current, previous) is True

    def test_different_returns_false(self):
        from dataclasses import dataclass

        @dataclass
        class FakeResult:
            success: bool = False
            length: float = 100.0

        current = {"a": FakeResult(success=False, length=100.0)}
        previous = {"a": FakeResult(success=False, length=99.0)}
        assert is_converged(current, previous) is False


# ---------------------------------------------------------------------------
# pipeline/dag_observability
# ---------------------------------------------------------------------------


class TestPipelineExecutionLog:
    """Tests for PipelineExecutionLog.to_dict."""

    def test_to_dict_basic(self):
        log = PipelineExecutionLog(
            dag_topology=[{"name": "s1", "deps": []}],
            stage_order=["s1"],
            stage_timings={"s1": 1.5},
            retry_counts={"s1": 0},
            feedback_activations=[],
            success=True,
            total_duration_s=1.5,
            events=[],
        )
        d = log.to_dict()
        assert d["dag_topology"] == [{"name": "s1", "deps": []}]
        assert d["stage_order"] == ["s1"]
        assert d["stage_timings"] == {"s1": 1.5}
        assert d["success"] is True
        assert d["total_duration_s"] == 1.5
        assert d["events"] == []

    def test_to_dict_defaults(self):
        log = PipelineExecutionLog()
        d = log.to_dict()
        assert d["dag_topology"] == []
        assert d["success"] is False
        assert d["total_duration_s"] == 0.0

    def test_write_execution_log_json(self, tmp_path):
        log = PipelineExecutionLog(success=True, total_duration_s=2.0)
        result_path = write_execution_log_json(log, tmp_path)
        assert result_path.exists()
        assert result_path.name == "pipeline_execution.json"
        with open(result_path) as f:
            data = json.load(f)
        assert data["success"] is True
        assert data["total_duration_s"] == 2.0


# ---------------------------------------------------------------------------
# pipeline/explainability
# ---------------------------------------------------------------------------


class TestDecisionLogger:
    """Tests for DecisionLogger.log_placement, log_routing, finish."""

    def test_log_placement(self):
        logger = DecisionLogger()
        logger.log_placement("U1", (10, 20), "test placement")
        assert len(logger.trace.decisions) == 1
        d = logger.trace.decisions[0]
        assert d.subject == "U1"
        assert d.decision_type == "placement"
        assert d.reason == "test placement"

    def test_log_placement_with_constraints_and_alternatives(self):
        from temper_placer.core.decision import Alternative

        logger = DecisionLogger()
        alt = Alternative(value=(5, 5), rejection_reason="too far")
        logger.log_placement(
            "U2", (10, 20), "optimal position",
            constraints=["max_dist", "keepout"],
            alternatives=[alt],
        )
        assert len(logger.trace.decisions) == 1
        d = logger.trace.decisions[0]
        assert d.constraint_refs == ["max_dist", "keepout"]
        assert len(d.alternatives_considered) == 1
        assert d.alternatives_considered[0].value == (5, 5)

    def test_log_routing(self):
        logger = DecisionLogger()
        logger.log_routing("NET1", "layer1", "direct route")
        assert len(logger.trace.decisions) == 1
        d = logger.trace.decisions[0]
        assert d.subject == "NET1"
        assert d.decision_type == "routing"

    def test_finish(self):
        logger = DecisionLogger()
        logger.log_placement("U1", (0, 0), "base")
        trace = logger.finish({"wire_length": 42.0, "drc_errors": 0.0})
        assert trace.final_metrics == {"wire_length": 42.0, "drc_errors": 0.0}
        assert trace.end_time is not None


class TestGenerateMarkdownReport:
    """Tests for pipeline/explainability.py::generate_markdown_report."""

    def test_generates_report(self):
        from datetime import datetime

        from temper_placer.core.decision import Decision, DecisionTrace

        trace = DecisionTrace(
            run_id="test-run-1",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 1, 12, 5, 0),
            final_metrics={"wire_length": 100.0},
        )
        d = Decision(
            id="d1",
            decision_type="placement",
            subject="U1",
            value=(10, 20),
            reason="optimal",
        )
        trace.add_decision(d)

        report = generate_markdown_report(trace)
        assert "# Placement Decision Trace: test-run-1" in report
        assert "wire_length" in report
        assert "U1" in report
        assert "optimal" in report

    def test_generates_report_with_alternatives(self):
        from datetime import datetime

        from temper_placer.core.decision import Alternative, Decision, DecisionTrace

        trace = DecisionTrace(
            run_id="run-2",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 1, 12, 5, 0),
            final_metrics={},
        )
        alt = Alternative(value=(1, 1), rejection_reason="too close")
        d = Decision(
            id="d2",
            decision_type="placement",
            subject="U2",
            value=(10, 10),
            reason="best",
            alternatives_considered=[alt],
        )
        trace.add_decision(d)

        report = generate_markdown_report(trace)
        assert "too close" in report

    def test_empty_report(self):
        from datetime import datetime

        from temper_placer.core.decision import DecisionTrace

        trace = DecisionTrace(
            run_id="empty",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            final_metrics={},
        )
        report = generate_markdown_report(trace)
        assert "empty" in report


# ---------------------------------------------------------------------------
# pipeline/derivation
# ---------------------------------------------------------------------------


class TestDeriveConstraintsFromSpec:
    """Tests for pipeline/derivation.py::derive_constraints_from_spec."""

    def test_derives_from_spec(self):
        from temper_placer.core.specification import (
            EMISpec,
            PcbSpecification,
            SafetySpec,
            SignalIntegritySpec,
            ThermalSpec,
        )

        spec = PcbSpecification(
            emi=EMISpec(max_loop_area_mm2={"buck_loop": 100.0}),
            thermal=ThermalSpec(power_dissipation={"U1": 2.0}),
            signal_integrity=SignalIntegritySpec(max_length_mm={"CLK": 50.0}),
            safety=SafetySpec(mains_voltage_v=120.0, pollution_degree=2),
        )
        netlist = _make_trivial_netlist()
        derived = derive_constraints_from_spec(spec, netlist)

        assert "buck_loop_max_dist" in derived
        assert "buck_loop_max_area_mm2" in derived
        assert "U1_min_clearance" in derived
        assert "CLK_max_placement_dist" in derived
        assert "hv_lv_isolation_mm" in derived

    def test_no_safety_spec_falls_back(self):
        from temper_placer.core.specification import (
            EMISpec,
            PcbSpecification,
            SignalIntegritySpec,
            ThermalSpec,
        )

        spec = PcbSpecification(
            emi=EMISpec(max_loop_area_mm2={}),
            thermal=ThermalSpec(power_dissipation={}),
            signal_integrity=SignalIntegritySpec(max_length_mm={}),
            safety=None,
        )
        netlist = _make_trivial_netlist()
        with pytest.warns(UserWarning, match="No safety spec"):
            derived = derive_constraints_from_spec(spec, netlist)
        assert derived["hv_lv_isolation_mm"] == 6.5


def _make_trivial_netlist():
    from temper_placer.core.netlist import Component, Netlist

    return Netlist(components=[], nets=[])


class TestApplyDerivedConstraints:
    """Tests for pipeline/derivation.py::apply_derived_constraints."""

    def test_returns_netlist_when_pcl_is_none(self):
        netlist = _make_trivial_netlist()
        derived = {"U1_min_clearance": 4.0}
        result = apply_derived_constraints(netlist, derived, pcl_constraints=None)
        assert result is netlist

    def test_adds_to_pcl_constraints(self):
        from temper_placer.pcl.parser import ConstraintCollection

        netlist = _make_trivial_netlist()
        derived = {"U1_min_clearance": 4.0}
        pcl = ConstraintCollection(constraints=[])
        result = apply_derived_constraints(netlist, derived, pcl_constraints=pcl)
        assert result is pcl
