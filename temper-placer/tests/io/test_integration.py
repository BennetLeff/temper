"""Integration tests for IO layer.

These tests verify the IO layer works correctly with real KiCad files
from the Temper project.
"""

import json
import tempfile
from pathlib import Path

import pytest

from temper_placer.io import (
    parse_kicad_schematic,
    load_constraints,
    create_board_from_constraints,
    write_placements_to_pcb,
    placements_to_json,
    placements_from_json,
    PlacementUpdate,
)


# Path to the Temper project root (relative to this test file)
TEMPER_ROOT = Path(__file__).parent.parent.parent.parent


class TestSchematicParsing:
    """Integration tests for parsing Temper schematics."""

    @pytest.fixture
    def temper_schematic_path(self):
        """Path to the main Temper schematic."""
        return TEMPER_ROOT / "pcb" / "temper.kicad_sch"

    def test_parse_main_schematic_exists(self, temper_schematic_path):
        """Test that the main schematic file exists."""
        if not temper_schematic_path.exists():
            pytest.skip(f"Schematic not found at {temper_schematic_path}")

    @pytest.mark.skipif(
        not Path(__file__).parent.parent.parent.parent.joinpath("pcb", "temper.kicad_sch").exists(),
        reason="Temper schematic not found",
    )
    def test_parse_main_schematic(self, temper_schematic_path):
        """Test parsing the main Temper schematic.

        Note: This test is conditionally enabled. The Temper schematics may be
        placeholder files without actual components during early development.
        The test verifies that the parser handles hierarchical designs without
        errors, even if the result has zero components.
        """
        result = parse_kicad_schematic(temper_schematic_path, recursive=True)

        # The schematic should parse without errors
        # Note: Component count may be 0 if schematics are placeholders
        assert result.netlist is not None

        # Log parsing results for debugging
        if result.netlist.n_components == 0:
            pytest.skip("Schematic parsed but has no components - likely a placeholder design")

        # If we have components, verify basic properties
        assert result.netlist.n_components > 0, "Expected components in schematic"

        # Check that we got component references
        refs = [c.ref for c in result.netlist.components]
        assert len(refs) > 0, "Expected component references"

        # Log any warnings
        if result.has_warnings:
            print(f"Warnings during parsing: {result.warnings}")


class TestConstraintsLoading:
    """Integration tests for loading constraint configs."""

    @pytest.fixture
    def constraints_path(self):
        """Path to Temper placer constraints config."""
        return TEMPER_ROOT / "temper-placer" / "configs" / "temper_constraints.yaml"

    def test_constraints_file_exists(self, constraints_path):
        """Test that the constraints file exists."""
        if not constraints_path.exists():
            pytest.skip(f"Constraints file not found at {constraints_path}")

    def test_load_constraints(self, constraints_path):
        """Test loading the Temper constraints config."""
        if not constraints_path.exists():
            pytest.skip(f"Constraints file not found at {constraints_path}")

        constraints = load_constraints(constraints_path)

        # Should have board dimensions
        assert constraints.board_width_mm > 0, "Expected board width"
        assert constraints.board_height_mm > 0, "Expected board height"

        # Should have zones defined
        assert len(constraints.zones) > 0, "Expected placement zones"

        # Should have clearance rules
        assert len(constraints.clearances) > 0, "Expected clearance rules"

    def test_create_board_from_constraints(self, constraints_path):
        """Test creating a Board from constraints."""
        if not constraints_path.exists():
            pytest.skip(f"Constraints file not found at {constraints_path}")

        constraints = load_constraints(constraints_path)
        board = create_board_from_constraints(constraints)

        # Board should have dimensions
        assert board.width == constraints.board_width_mm
        assert board.height == constraints.board_height_mm

        # Board should have zones from constraints
        assert len(board.zones) == len(constraints.zones)


class TestPlacementJsonRoundtrip:
    """Integration tests for placement JSON serialization."""

    def test_placement_json_roundtrip(self):
        """Test that placements can be serialized to JSON and back."""
        placements = {
            "U1": PlacementUpdate(ref="U1", x=10.5, y=20.5, rotation=90.0),
            "R1": PlacementUpdate(ref="R1", x=30.0, y=40.0, rotation=0.0),
            "C1": PlacementUpdate(ref="C1", x=50.0, y=60.0, rotation=180.0),
        }

        # Convert to JSON
        data = placements_to_json(placements)

        # Write to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f, indent=2)
            temp_path = Path(f.name)

        try:
            # Read back
            with open(temp_path) as f:
                loaded_data = json.load(f)

            # Convert back to placements
            restored = placements_from_json(loaded_data)

            # Verify all data preserved
            assert len(restored) == len(placements)
            for ref in placements:
                assert ref in restored
                assert restored[ref].x == placements[ref].x
                assert restored[ref].y == placements[ref].y
                assert restored[ref].rotation == placements[ref].rotation
        finally:
            temp_path.unlink()


class TestCoordinateRoundTrip:
    """Test that parsing then writing preserves component positions.

    This tests the fix for coordinate system asymmetry (temper-r2i.4).
    The parser normalizes positions to origin-relative coordinates,
    and the writer adds the origin back. A round-trip should preserve
    the original absolute KiCad coordinates.
    """

    @pytest.fixture
    def pcb_with_nonzero_origin(self, tmp_path):
        """Create a PCB with non-zero origin for testing coordinate handling."""
        content = """(kicad_pcb (version 20240108) (generator "test")
  (general
    (thickness 1.6)
  )
  (paper "A4")
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
  )
  (net 0 "")
  (net 1 "GND")
  (footprint "Resistor_SMD:R_0805_2012Metric" (layer "F.Cu")
    (property "Reference" "R1")
    (property "Value" "10k")
    (at 75 55 0)
    (pad "1" smd rect (at -0.9 0) (size 1.0 1.2) (layers "F.Cu") (net 1 "GND"))
    (pad "2" smd rect (at 0.9 0) (size 1.0 1.2) (layers "F.Cu") (net 1 "GND"))
  )
  (footprint "Capacitor_SMD:C_0805_2012Metric" (layer "F.Cu")
    (property "Reference" "C1")
    (property "Value" "100nF")
    (at 85 65 90)
    (pad "1" smd rect (at -0.9 0) (size 1.0 1.2) (layers "F.Cu") (net 1 "GND"))
    (pad "2" smd rect (at 0.9 0) (size 1.0 1.2) (layers "F.Cu") (net 1 "GND"))
  )
  (gr_line (start 50 30) (end 150 30) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start 150 30) (end 150 130) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start 150 130) (end 50 130) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start 50 130) (end 50 30) (layer "Edge.Cuts") (width 0.1))
)
"""
        # Board outline: (50, 30) to (150, 130) -> origin = (50, 30), size = 100x100
        # Component R1 at (75, 55) absolute = (25, 25) origin-relative
        # Component C1 at (85, 65) absolute = (35, 35) origin-relative
        pcb_path = tmp_path / "test_origin.kicad_pcb"
        pcb_path.write_text(content)
        return pcb_path

    def test_parse_normalizes_to_origin_relative(self, pcb_with_nonzero_origin):
        """Test that parser converts to origin-relative coordinates."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb

        result = parse_kicad_pcb(pcb_with_nonzero_origin)

        # Board should be extracted
        assert result.board is not None

        # Board origin should be (50, 30)
        assert result.board.origin == (50.0, 30.0)
        assert result.board.width == 100.0
        assert result.board.height == 100.0

        # Component positions should be origin-relative
        comp_by_ref = {c.ref: c for c in result.netlist.components}

        # R1 at (75, 55) absolute -> (25, 25) origin-relative
        r1 = comp_by_ref["R1"]
        assert r1.initial_position is not None
        assert abs(r1.initial_position[0] - 25.0) < 0.001
        assert abs(r1.initial_position[1] - 25.0) < 0.001

        # C1 at (85, 65) absolute -> (35, 35) origin-relative
        c1 = comp_by_ref["C1"]
        assert c1.initial_position is not None
        assert abs(c1.initial_position[0] - 35.0) < 0.001
        assert abs(c1.initial_position[1] - 35.0) < 0.001

    def test_state_to_placements_adds_origin(self):
        """Test that state_to_placements adds origin back."""
        import jax.numpy as jnp
        from temper_placer.core.state import PlacementState
        from temper_placer.io.kicad_writer import state_to_placements

        # Create state with origin-relative positions
        positions = jnp.array([[25.0, 25.0], [35.0, 35.0]])
        rotation_logits = jnp.array([[10.0, 0.0, 0.0, 0.0], [0.0, 10.0, 0.0, 0.0]])
        state = PlacementState(positions=positions, rotation_logits=rotation_logits)

        # Convert to placements with origin (50, 30)
        placements = state_to_placements(state, ["R1", "C1"], origin=(50.0, 30.0))

        # Should have absolute positions
        assert abs(placements["R1"].x - 75.0) < 0.001
        assert abs(placements["R1"].y - 55.0) < 0.001
        assert abs(placements["C1"].x - 85.0) < 0.001
        assert abs(placements["C1"].y - 65.0) < 0.001

    def test_full_round_trip_preserves_positions(self, pcb_with_nonzero_origin, tmp_path):
        """Test that parse -> export -> parse preserves positions."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.io.kicad_writer import write_placements_to_pcb, state_to_placements
        from temper_placer.core.state import PlacementState
        import jax.numpy as jnp

        # Step 1: Parse original PCB
        result = parse_kicad_pcb(pcb_with_nonzero_origin)
        assert result.board is not None
        comp_by_ref = {c.ref: c for c in result.netlist.components}
        component_refs = list(comp_by_ref.keys())

        # Step 2: Create state from parsed positions (origin-relative)
        positions = jnp.array(
            [comp_by_ref[ref].initial_position for ref in component_refs], dtype=jnp.float32
        )
        # Use rotation logits that will produce the same discrete rotations
        rotation_logits = jnp.zeros((len(component_refs), 4))
        for i, ref in enumerate(component_refs):
            rot_idx = comp_by_ref[ref].initial_rotation or 0
            rotation_logits = rotation_logits.at[i, rot_idx].set(10.0)

        state = PlacementState(positions=positions, rotation_logits=rotation_logits)

        # Step 3: Export with origin
        placements = state_to_placements(state, component_refs, origin=result.board.origin)
        output_path = tmp_path / "round_trip_output.kicad_pcb"
        write_placements_to_pcb(pcb_with_nonzero_origin, output_path, placements)

        # Step 4: Parse the output
        result2 = parse_kicad_pcb(output_path)
        comp_by_ref2 = {c.ref: c for c in result2.netlist.components}

        # Step 5: Compare positions (should match original)
        for ref in component_refs:
            orig = comp_by_ref[ref]
            parsed = comp_by_ref2[ref]

            assert orig.initial_position is not None
            assert parsed.initial_position is not None

            # Origin-relative positions should match
            assert abs(orig.initial_position[0] - parsed.initial_position[0]) < 0.001, (
                f"{ref}: x mismatch: {orig.initial_position[0]} vs {parsed.initial_position[0]}"
            )
            assert abs(orig.initial_position[1] - parsed.initial_position[1]) < 0.001, (
                f"{ref}: y mismatch: {orig.initial_position[1]} vs {parsed.initial_position[1]}"
            )
            assert orig.initial_rotation == parsed.initial_rotation, (
                f"{ref}: rotation mismatch: {orig.initial_rotation} vs {parsed.initial_rotation}"
            )


class TestMinimalKicadFixtures:
    """Tests using minimal KiCad fixture files.

    These tests use minimal hand-crafted KiCad files to test parsing
    and writing without depending on the full Temper design.
    """

    @pytest.fixture
    def minimal_pcb_content(self):
        """Minimal valid .kicad_pcb content for testing."""
        return """(kicad_pcb (version 20240108) (generator "test")
  (general
    (thickness 1.6)
  )
  (paper "A4")
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
  )
  (net 0 "")
  (net 1 "GND")
  (net 2 "VCC")
  (footprint "Resistor_SMD:R_0805_2012Metric" (layer "F.Cu")
    (property "Reference" "R1")
    (property "Value" "10k")
    (at 100 100 0)
    (pad "1" smd rect (at -0.9 0) (size 1.0 1.2) (layers "F.Cu") (net 1 "GND"))
    (pad "2" smd rect (at 0.9 0) (size 1.0 1.2) (layers "F.Cu") (net 2 "VCC"))
  )
  (footprint "Capacitor_SMD:C_0805_2012Metric" (layer "F.Cu")
    (property "Reference" "C1")
    (property "Value" "100nF")
    (at 110 100 90)
    (pad "1" smd rect (at -0.9 0) (size 1.0 1.2) (layers "F.Cu") (net 1 "GND"))
    (pad "2" smd rect (at 0.9 0) (size 1.0 1.2) (layers "F.Cu") (net 2 "VCC"))
  )
  (gr_line (start 0 0) (end 150 0) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start 150 0) (end 150 100) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start 150 100) (end 0 100) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start 0 100) (end 0 0) (layer "Edge.Cuts") (width 0.1))
)
"""

    def test_write_and_read_minimal_pcb(self, minimal_pcb_content):
        """Test writing placements to a minimal PCB and reading back."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write minimal PCB
            pcb_path = Path(tmpdir) / "test.kicad_pcb"
            pcb_path.write_text(minimal_pcb_content)

            # Parse it
            result = parse_kicad_pcb(pcb_path)

            # Should have found 2 components
            assert result.netlist.n_components == 2

            # Should have found GND and VCC nets
            net_names = {n.name for n in result.netlist.nets}
            assert "GND" in net_names
            assert "VCC" in net_names

            # Board should have been extracted from Edge.Cuts
            assert result.board is not None
            assert result.board.width == 150.0
            assert result.board.height == 100.0

            # Now write new placements
            placements = {
                "R1": PlacementUpdate(ref="R1", x=50.0, y=50.0, rotation=0.0),
                "C1": PlacementUpdate(ref="C1", x=75.0, y=50.0, rotation=180.0),
            }

            output_path = Path(tmpdir) / "output.kicad_pcb"
            write_result = write_placements_to_pcb(
                template_pcb=pcb_path,
                output_pcb=output_path,
                placements=placements,
            )

            # Should have updated both components
            assert write_result.components_updated == 2
            assert write_result.components_skipped == 0

            # Parse the output
            output_result = parse_kicad_pcb(output_path)

            # Verify positions were updated
            comp_by_ref = {c.ref: c for c in output_result.netlist.components}
            assert comp_by_ref["R1"].initial_position == (50.0, 50.0)
            assert comp_by_ref["C1"].initial_position == (75.0, 50.0)
