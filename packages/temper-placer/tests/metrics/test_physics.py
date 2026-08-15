"""Tests for physics.py module."""

import numpy as np

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist
from temper_placer.core.state import PlacementState
from temper_placer.metrics.physics import (
    EMIMetrics,
    GeometricMetrics,
    PhysicsReport,
    RoutabilityMetrics,
    ThermalMetrics,
    measure_emi,
    measure_geometric,
    measure_thermal,
)


class TestPhysicsReportToDict:
    def test_to_dict_defaults(self):
        """PhysicsReport.to_dict() works with default field values."""
        report = PhysicsReport()
        d = report.to_dict()
        assert isinstance(d, dict)
        assert "geometric" in d
        assert "emi" in d
        assert "thermal" in d
        assert "routability" in d
        assert d["geometric"]["overlap_count"] == 0

    def test_to_dict_with_values(self):
        """PhysicsReport.to_dict() serializes populated fields."""
        report = PhysicsReport(
            geometric=GeometricMetrics(overlap_count=3, overlap_area_mm2=1.5),
            emi=EMIMetrics(gate_loop_area_mm2=10.0),
            thermal=ThermalMetrics(max_junction_temp_c=85.0),
            routability=RoutabilityMetrics(completion_pct=95.0),
        )
        d = report.to_dict()
        assert d["geometric"]["overlap_count"] == 3
        assert d["geometric"]["overlap_area_mm2"] == 1.5
        assert d["emi"]["gate_loop_area_mm2"] == 10.0
        assert d["thermal"]["max_junction_temp_c"] == 85.0
        assert d["routability"]["completion_pct"] == 95.0


class TestMeasureGeometric:
    def test_empty_netlist(self):
        """measure_geometric with empty netlist returns zero metrics."""
        state = PlacementState(
            positions=np.zeros((0, 2), dtype=np.float32),
            rotation_logits=np.zeros((0, 4), dtype=np.float32),
        )
        netlist = Netlist()
        board = Board(width=100, height=100)
        result = measure_geometric(state, netlist, board)
        assert isinstance(result, GeometricMetrics)
        assert result.overlap_count == 0

    def test_single_component(self):
        """measure_geometric with one component in bounds returns zero violations."""
        state = PlacementState(
            positions=np.array([[50.0, 50.0]], dtype=np.float32),
            rotation_logits=np.array([[1, 0, 0, 0]], dtype=np.float32),
        )
        netlist = Netlist(
            components=[Component(ref="U1", footprint="SOIC-8", bounds=(5, 4))],
            nets=[],
        )
        board = Board(width=100, height=100)
        result = measure_geometric(state, netlist, board)
        assert isinstance(result, GeometricMetrics)
        assert result.overlap_count == 0
        assert result.boundary_violation_count == 0


class TestMeasureEMI:
    def test_no_loops(self):
        """measure_emi with no loop_refs returns empty metrics."""
        state = PlacementState(
            positions=np.zeros((0, 2), dtype=np.float32),
            rotation_logits=np.zeros((0, 4), dtype=np.float32),
        )
        netlist = Netlist()
        result = measure_emi(state, netlist, None)
        assert result.gate_loop_area_mm2 == 0.0
        assert result.total_loop_area_mm2 == 0.0

    def test_empty_loop_list(self):
        """measure_emi with empty loop list returns empty metrics."""
        state = PlacementState(
            positions=np.zeros((0, 2), dtype=np.float32),
            rotation_logits=np.zeros((0, 4), dtype=np.float32),
        )
        netlist = Netlist()
        result = measure_emi(state, netlist, [])
        assert result.total_loop_area_mm2 == 0.0


class TestMeasureThermal:
    def test_no_power_dissipation(self):
        """measure_thermal with no power dissipation returns default values."""
        state = PlacementState(
            positions=np.zeros((0, 2), dtype=np.float32),
            rotation_logits=np.zeros((0, 4), dtype=np.float32),
        )
        netlist = Netlist()
        board = Board(width=100, height=100)
        result = measure_thermal(state, netlist, board, None)
        assert result.max_junction_temp_c == 60.0  # ambient (design-limit)
        assert result.thermal_margin_c == 0.0

    def test_empty_power_dict(self):
        """measure_thermal with empty power dict returns default values."""
        state = PlacementState(
            positions=np.zeros((0, 2), dtype=np.float32),
            rotation_logits=np.zeros((0, 4), dtype=np.float32),
        )
        netlist = Netlist()
        board = Board(width=100, height=100)
        result = measure_thermal(state, netlist, board, {})
        assert result.max_junction_temp_c == 60.0
        assert result.thermal_margin_c == 0.0
