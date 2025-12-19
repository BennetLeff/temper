"""Tests using embedded test fixtures.

These tests verify the IO layer works with the minimal embedded KiCad files,
ensuring tests run on CI without external dependencies.
"""

from pathlib import Path

import pytest

from temper_placer.io.config_loader import load_constraints
from temper_placer.io.kicad_parser import parse_kicad_pcb

# Path to fixtures directory
FIXTURES = Path(__file__).parent / "fixtures"


class TestMinimalBoardParsing:
    """Tests for parsing the minimal embedded board."""

    @pytest.fixture
    def minimal_pcb_path(self):
        """Path to the minimal test PCB."""
        return FIXTURES / "minimal_board.kicad_pcb"

    def test_fixture_exists(self, minimal_pcb_path):
        """Test that the fixture file exists."""
        assert minimal_pcb_path.exists(), f"Fixture not found at {minimal_pcb_path}"

    def test_parse_minimal_board(self, minimal_pcb_path):
        """Test parsing the minimal PCB."""
        result = parse_kicad_pcb(minimal_pcb_path)

        # Should have 4 components
        assert len(result.netlist.components) == 4

        # Check component references
        refs = {c.ref for c in result.netlist.components}
        assert refs == {"R1", "R2", "C1", "U1"}

    def test_component_positions(self, minimal_pcb_path):
        """Test that component positions are parsed correctly."""
        result = parse_kicad_pcb(minimal_pcb_path)

        # Build lookup by ref
        comps = {c.ref: c for c in result.netlist.components}

        # R1 at (100, 80) - but normalized to origin (90, 70) = (10, 10)
        assert comps["R1"].initial_position is not None
        assert abs(comps["R1"].initial_position[0] - 10.0) < 0.1
        assert abs(comps["R1"].initial_position[1] - 10.0) < 0.1

        # R2 at (110, 80) = normalized (20, 10)
        assert comps["R2"].initial_position is not None
        assert abs(comps["R2"].initial_position[0] - 20.0) < 0.1
        assert abs(comps["R2"].initial_position[1] - 10.0) < 0.1

    def test_component_rotations(self, minimal_pcb_path):
        """Test that component rotations are parsed correctly."""
        result = parse_kicad_pcb(minimal_pcb_path)

        comps = {c.ref: c for c in result.netlist.components}

        # R1: 0° -> rotation index 0
        assert comps["R1"].initial_rotation == 0

        # R2: 90° -> rotation index 1
        assert comps["R2"].initial_rotation == 1

        # C1: 0° -> rotation index 0
        assert comps["C1"].initial_rotation == 0

        # U1: 180° -> rotation index 2
        assert comps["U1"].initial_rotation == 2

    def test_net_extraction(self, minimal_pcb_path):
        """Test that nets are extracted correctly."""
        result = parse_kicad_pcb(minimal_pcb_path)

        # Should have 4 nets (GND, VCC, SIG1, SIG2)
        net_names = {n.name for n in result.netlist.nets}
        assert "GND" in net_names
        assert "VCC" in net_names
        assert "SIG1" in net_names
        assert "SIG2" in net_names

    def test_component_pins(self, minimal_pcb_path):
        """Test that component pins are extracted."""
        result = parse_kicad_pcb(minimal_pcb_path)

        comps = {c.ref: c for c in result.netlist.components}

        # R1 should have 2 pins
        assert len(comps["R1"].pins) == 2

        # U1 (SOIC-8) should have 8 pins
        assert len(comps["U1"].pins) == 8

    def test_board_bounds(self, minimal_pcb_path):
        """Test that board bounds are extracted."""
        result = parse_kicad_pcb(minimal_pcb_path)

        # Board should be 50x30 mm
        assert result.board is not None
        assert abs(result.board.width - 50.0) < 0.1
        assert abs(result.board.height - 30.0) < 0.1


class TestMinimalConstraints:
    """Tests for loading the minimal constraints file."""

    @pytest.fixture
    def constraints_path(self):
        """Path to the minimal constraints file."""
        return FIXTURES / "constraints_minimal.yaml"

    def test_fixture_exists(self, constraints_path):
        """Test that the fixture file exists."""
        assert constraints_path.exists(), f"Fixture not found at {constraints_path}"

    def test_load_constraints(self, constraints_path):
        """Test loading the minimal constraints."""
        config = load_constraints(constraints_path)

        # Check board dimensions
        assert config.board_width_mm == 50.0
        assert config.board_height_mm == 30.0

    def test_zones_loaded(self, constraints_path):
        """Test that zones are loaded."""
        config = load_constraints(constraints_path)

        assert len(config.zones) == 1
        assert config.zones[0].name == "main"

    def test_component_groups_loaded(self, constraints_path):
        """Test that component groups are loaded."""
        config = load_constraints(constraints_path)

        assert len(config.component_groups) == 2

        # Find groups by name
        groups = {g.name: g for g in config.component_groups}

        assert "passives" in groups
        assert "ics" in groups

        assert set(groups["passives"].components) == {"R1", "R2", "C1"}
        assert set(groups["ics"].components) == {"U1"}


class TestFixtureIntegration:
    """Integration tests using both fixtures together."""

    @pytest.fixture
    def minimal_pcb_path(self):
        return FIXTURES / "minimal_board.kicad_pcb"

    @pytest.fixture
    def constraints_path(self):
        return FIXTURES / "constraints_minimal.yaml"

    def test_parse_and_load_together(self, minimal_pcb_path, constraints_path):
        """Test that PCB and constraints can be loaded together."""
        pcb_result = parse_kicad_pcb(minimal_pcb_path)
        config = load_constraints(constraints_path)

        # Components from PCB should match groups in constraints
        pcb_refs = {c.ref for c in pcb_result.netlist.components}

        constraint_refs = set()
        for group in config.component_groups:
            constraint_refs.update(group.components)

        assert pcb_refs == constraint_refs

    def test_board_dimensions_match(self, minimal_pcb_path, constraints_path):
        """Test that board dimensions match between PCB and constraints."""
        pcb_result = parse_kicad_pcb(minimal_pcb_path)
        config = load_constraints(constraints_path)

        # Board dimensions should match
        assert pcb_result.board is not None
        assert abs(pcb_result.board.width - config.board_width_mm) < 0.1
        assert abs(pcb_result.board.height - config.board_height_mm) < 0.1


class TestLargeBoardParsing:
    """Tests for parsing the large 100+ component board fixture."""

    @pytest.fixture
    def large_pcb_path(self):
        """Path to the large test PCB."""
        return FIXTURES / "large_board.kicad_pcb"

    def test_fixture_exists(self, large_pcb_path):
        """Test that the large board fixture file exists."""
        assert large_pcb_path.exists(), f"Fixture not found at {large_pcb_path}"

    def test_parse_large_board(self, large_pcb_path):
        """Test parsing the large PCB with 100+ components."""
        result = parse_kicad_pcb(large_pcb_path)

        # Should have 110 components
        assert len(result.netlist.components) == 110

    def test_component_types(self, large_pcb_path):
        """Test that all expected component types are present."""
        result = parse_kicad_pcb(large_pcb_path)

        refs = {c.ref for c in result.netlist.components}

        # Check for resistors (R1-R50)
        assert sum(1 for r in refs if r.startswith("R")) == 50

        # Check for capacitors (C1-C30)
        assert sum(1 for r in refs if r.startswith("C")) == 30

        # Check for ICs (U1-U10)
        assert sum(1 for r in refs if r.startswith("U")) == 10

        # Check for inductors (L1-L5)
        assert sum(1 for r in refs if r.startswith("L")) == 5

        # Check for connectors (J1-J5)
        assert sum(1 for r in refs if r.startswith("J")) == 5

        # Check for diodes (D1-D5)
        assert sum(1 for r in refs if r.startswith("D")) == 5

        # Check for transistors (Q1-Q5)
        assert sum(1 for r in refs if r.startswith("Q")) == 5

    def test_nets_extracted(self, large_pcb_path):
        """Test that nets are extracted from the large board."""
        result = parse_kicad_pcb(large_pcb_path)

        # Should have 35+ nets (some may be merged)
        assert len(result.netlist.nets) >= 30

        # Check for key power nets
        net_names = {n.name for n in result.netlist.nets}
        assert "GND" in net_names
        assert "VCC" in net_names
        assert "VCC_3V3" in net_names

    def test_board_dimensions(self, large_pcb_path):
        """Test that board dimensions are correct."""
        result = parse_kicad_pcb(large_pcb_path)

        # Board should be 100x150 mm
        assert result.board is not None
        assert abs(result.board.width - 100.0) < 0.1
        assert abs(result.board.height - 150.0) < 0.1

    def test_component_positions_valid(self, large_pcb_path):
        """Test that all components have valid positions."""
        result = parse_kicad_pcb(large_pcb_path)

        for comp in result.netlist.components:
            assert comp.initial_position is not None, f"{comp.ref} has no position"
            x, y = comp.initial_position
            # All positions should be within board bounds (with some margin)
            assert 0 <= x <= 150, f"{comp.ref} x={x} out of bounds"
            assert 0 <= y <= 200, f"{comp.ref} y={y} out of bounds"

    def test_component_pins_connected(self, large_pcb_path):
        """Test that components have proper pin connections."""
        result = parse_kicad_pcb(large_pcb_path)

        comps = {c.ref: c for c in result.netlist.components}

        # MCU (U1) should have 48 pins
        assert len(comps["U1"].pins) == 48

        # Op-amps (U2-U5) should have 8 pins each
        for i in range(2, 6):
            assert len(comps[f"U{i}"].pins) == 8, f"U{i} should have 8 pins"

        # Resistors should have 2 pins
        assert len(comps["R1"].pins) == 2

    def test_no_parse_warnings(self, large_pcb_path):
        """Test that parsing generates no warnings."""
        result = parse_kicad_pcb(large_pcb_path)
        assert len(result.warnings) == 0, f"Unexpected warnings: {result.warnings}"


class TestLargeBoardConstraints:
    """Tests for the large board constraints file."""

    @pytest.fixture
    def constraints_path(self):
        """Path to the large board constraints file."""
        return FIXTURES / "constraints_large.yaml"

    def test_fixture_exists(self, constraints_path):
        """Test that the constraints file exists."""
        assert constraints_path.exists(), f"Fixture not found at {constraints_path}"

    def test_load_constraints(self, constraints_path):
        """Test loading the large board constraints."""
        config = load_constraints(constraints_path)

        # Check board dimensions
        assert config.board_width_mm == 100.0
        assert config.board_height_mm == 150.0

    def test_zones_defined(self, constraints_path):
        """Test that multiple zones are defined."""
        config = load_constraints(constraints_path)

        # Should have multiple zones
        assert len(config.zones) >= 5

        zone_names = {z.name for z in config.zones}
        assert "power" in zone_names
        assert "control" in zone_names
        assert "analog" in zone_names


class TestLargeBoardIntegration:
    """Integration tests for the large board fixture."""

    @pytest.fixture
    def large_pcb_path(self):
        return FIXTURES / "large_board.kicad_pcb"

    @pytest.fixture
    def constraints_path(self):
        return FIXTURES / "constraints_large.yaml"

    def test_parse_and_load_together(self, large_pcb_path, constraints_path):
        """Test that large PCB and constraints can be loaded together."""
        pcb_result = parse_kicad_pcb(large_pcb_path)
        config = load_constraints(constraints_path)

        # Both should load without error
        assert pcb_result is not None
        assert config is not None

    def test_board_dimensions_match(self, large_pcb_path, constraints_path):
        """Test that board dimensions match between PCB and constraints."""
        pcb_result = parse_kicad_pcb(large_pcb_path)
        config = load_constraints(constraints_path)

        assert pcb_result.board is not None
        assert abs(pcb_result.board.width - config.board_width_mm) < 0.1
        assert abs(pcb_result.board.height - config.board_height_mm) < 0.1

    def test_assigned_components_exist(self, large_pcb_path, constraints_path):
        """Test that components assigned in constraints exist in PCB."""
        pcb_result = parse_kicad_pcb(large_pcb_path)
        config = load_constraints(constraints_path)

        pcb_refs = {c.ref for c in pcb_result.netlist.components}

        # All components in assignments should exist in PCB
        for group in config.component_groups:
            for ref in group.components:
                assert ref in pcb_refs, f"Component {ref} in constraints not found in PCB"
