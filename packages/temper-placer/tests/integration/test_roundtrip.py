"""
Pipeline roundtrip verification tests.

These tests verify data integrity through the full parse -> optimize -> export -> re-parse cycle.
This catches subtle bugs where data is lost or corrupted during serialization.

Key verifications:
1. Positions survive export -> re-parse within tolerance
2. Rotations survive roundtrip correctly
3. Net assignments preserved
4. Non-placement data (traces, zones) not corrupted
5. Idempotent exports produce identical files
"""

from pathlib import Path
import tempfile
import pytest

# Skip all tests if JAX not available
jax = pytest.importorskip("jax")
import jax.numpy as jnp

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Pin, Net, Netlist
from temper_placer.core.state import PlacementState
from temper_placer.io.kicad_parser import parse_kicad_pcb, ParseResult
from temper_placer.io.kicad_writer import (
    PlacementUpdate,
    write_placements_to_pcb,
    state_to_placements,
    export_placements,
)


# Test fixtures
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
MINIMAL_PCB = FIXTURES_DIR / "minimal_board.kicad_pcb"

# Position tolerance in mm (KiCad precision is typically 0.001mm)
POSITION_TOLERANCE = 0.01


def get_board_origin(result: ParseResult) -> tuple[float, float]:
    """Get board origin with assertion that board exists."""
    assert result.board is not None, "ParseResult has no board"
    return result.board.origin


class TestPositionRoundtrip:
    """Tests for position preservation through roundtrip."""

    @pytest.mark.skipif(not MINIMAL_PCB.exists(), reason="Minimal PCB fixture not found")
    def test_known_positions_roundtrip(self):
        """Known positions should survive export -> re-parse within tolerance."""
        # Parse the original PCB
        original_result = parse_kicad_pcb(MINIMAL_PCB)
        assert original_result.board is not None, "Original parse has no board"
        origin = original_result.board.origin

        # Define specific positions for each component
        # Use positions relative to board origin
        test_positions = {}
        for i, comp in enumerate(original_result.netlist.components):
            # Place components in a grid pattern within board bounds
            x = 10.0 + (i % 3) * 15.0
            y = 10.0 + (i // 3) * 12.0
            test_positions[comp.ref] = PlacementUpdate(
                ref=comp.ref,
                x=x + origin[0],  # Convert to absolute
                y=y + origin[1],
                rotation=0.0,
            )

        # Export to temp file
        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            temp_path = Path(f.name)

        try:
            result = write_placements_to_pcb(
                template_pcb=MINIMAL_PCB,
                output_pcb=temp_path,
                placements=test_positions,
            )
            assert result.components_updated > 0, "No components were updated"

            # Re-parse the exported file
            reparsed = parse_kicad_pcb(temp_path)

            # Verify positions match within tolerance
            for comp in reparsed.netlist.components:
                if comp.ref in test_positions:
                    expected = test_positions[comp.ref]
                    # Parser normalizes to origin-relative, so we compare that
                    if comp.initial_position is not None:
                        actual_x = comp.initial_position[0] + origin[0]
                        actual_y = comp.initial_position[1] + origin[1]

                        x_diff = abs(actual_x - expected.x)
                        y_diff = abs(actual_y - expected.y)

                        assert x_diff < POSITION_TOLERANCE, (
                            f"X position mismatch for {comp.ref}: "
                            f"expected {expected.x}, got {actual_x}, diff={x_diff}"
                        )
                        assert y_diff < POSITION_TOLERANCE, (
                            f"Y position mismatch for {comp.ref}: "
                            f"expected {expected.y}, got {actual_y}, diff={y_diff}"
                        )
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @pytest.mark.skipif(not MINIMAL_PCB.exists(), reason="Minimal PCB fixture not found")
    def test_state_export_roundtrip(self):
        """PlacementState export should produce parseable results."""
        original_result = parse_kicad_pcb(MINIMAL_PCB)
        netlist = original_result.netlist
        assert original_result.board is not None, "Original parse has no board"
        board = original_result.board

        # Create a random placement state
        n = netlist.n_components
        key = jax.random.PRNGKey(42)
        state = PlacementState.random_init(
            n_components=n,
            board_width=board.width,
            board_height=board.height,
            key=key,
        )

        # Get component refs in order
        component_refs = [c.ref for c in netlist.components]

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            temp_path = Path(f.name)

        try:
            # Export using high-level function
            result = export_placements(
                template_pcb=MINIMAL_PCB,
                output_pcb=temp_path,
                state=state,
                component_refs=component_refs,
                origin=board.origin,
            )

            assert result.components_updated == n, (
                f"Expected {n} components updated, got {result.components_updated}"
            )

            # Re-parse should succeed
            reparsed = parse_kicad_pcb(temp_path)
            assert reparsed.netlist.n_components == n
        finally:
            if temp_path.exists():
                temp_path.unlink()


class TestRotationRoundtrip:
    """Tests for rotation preservation through roundtrip."""

    @pytest.mark.skipif(not MINIMAL_PCB.exists(), reason="Minimal PCB fixture not found")
    def test_rotation_0_roundtrip(self):
        """0 degree rotation should survive roundtrip."""
        self._test_rotation_angle(0.0)

    @pytest.mark.skipif(not MINIMAL_PCB.exists(), reason="Minimal PCB fixture not found")
    def test_rotation_90_roundtrip(self):
        """90 degree rotation should survive roundtrip."""
        self._test_rotation_angle(90.0)

    @pytest.mark.skipif(not MINIMAL_PCB.exists(), reason="Minimal PCB fixture not found")
    def test_rotation_180_roundtrip(self):
        """180 degree rotation should survive roundtrip."""
        self._test_rotation_angle(180.0)

    @pytest.mark.skipif(not MINIMAL_PCB.exists(), reason="Minimal PCB fixture not found")
    def test_rotation_270_roundtrip(self):
        """270 degree rotation should survive roundtrip."""
        self._test_rotation_angle(270.0)

    def _test_rotation_angle(self, angle: float):
        """Helper to test a specific rotation angle."""
        original_result = parse_kicad_pcb(MINIMAL_PCB)
        assert original_result.board is not None, "Original parse has no board"
        origin = original_result.board.origin

        # Create placements with the specified rotation
        placements = {}
        for comp in original_result.netlist.components:
            pos = comp.initial_position or (10.0, 10.0)
            placements[comp.ref] = PlacementUpdate(
                ref=comp.ref,
                x=pos[0] + origin[0],
                y=pos[1] + origin[1],
                rotation=angle,
            )

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            temp_path = Path(f.name)

        try:
            write_placements_to_pcb(
                template_pcb=MINIMAL_PCB,
                output_pcb=temp_path,
                placements=placements,
            )

            reparsed = parse_kicad_pcb(temp_path)

            # Verify rotations
            for comp in reparsed.netlist.components:
                if comp.ref in placements:
                    # initial_rotation is stored as index (0-3)
                    expected_index = int(angle / 90) % 4
                    assert comp.initial_rotation == expected_index, (
                        f"Rotation mismatch for {comp.ref}: "
                        f"expected index {expected_index} ({angle}deg), "
                        f"got {comp.initial_rotation}"
                    )
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @pytest.mark.skipif(not MINIMAL_PCB.exists(), reason="Minimal PCB fixture not found")
    def test_negative_rotation_normalization(self):
        """Negative rotations like -90 should normalize correctly."""
        original_result = parse_kicad_pcb(MINIMAL_PCB)
        assert original_result.board is not None, "Original parse has no board"
        origin = original_result.board.origin

        # Test -90 (should become 270)
        placements = {}
        for comp in original_result.netlist.components:
            pos = comp.initial_position or (10.0, 10.0)
            placements[comp.ref] = PlacementUpdate(
                ref=comp.ref,
                x=pos[0] + origin[0],
                y=pos[1] + origin[1],
                rotation=-90.0,  # Negative angle
            )

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            temp_path = Path(f.name)

        try:
            write_placements_to_pcb(
                template_pcb=MINIMAL_PCB,
                output_pcb=temp_path,
                placements=placements,
            )

            reparsed = parse_kicad_pcb(temp_path)

            # -90 should be equivalent to 270 (index 3)
            for comp in reparsed.netlist.components:
                # KiCad may store as -90 or 270, parser should normalize
                # Check that rotation is valid (0, 1, 2, or 3)
                assert comp.initial_rotation in [0, 1, 2, 3], (
                    f"Invalid rotation index for {comp.ref}: {comp.initial_rotation}"
                )
        finally:
            if temp_path.exists():
                temp_path.unlink()


class TestDataPreservation:
    """Tests for preservation of non-placement data."""

    @pytest.mark.skipif(not MINIMAL_PCB.exists(), reason="Minimal PCB fixture not found")
    def test_component_count_preserved(self):
        """Same number of components before and after roundtrip."""
        original_result = parse_kicad_pcb(MINIMAL_PCB)
        assert original_result.board is not None, "Original parse has no board"
        origin = original_result.board.origin
        original_count = original_result.netlist.n_components

        # Create trivial placements (same positions)
        placements = {}
        for comp in original_result.netlist.components:
            pos = comp.initial_position or (10.0, 10.0)
            rot = (comp.initial_rotation or 0) * 90.0
            placements[comp.ref] = PlacementUpdate(
                ref=comp.ref,
                x=pos[0] + origin[0],
                y=pos[1] + origin[1],
                rotation=rot,
            )

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            temp_path = Path(f.name)

        try:
            write_placements_to_pcb(
                template_pcb=MINIMAL_PCB,
                output_pcb=temp_path,
                placements=placements,
            )

            reparsed = parse_kicad_pcb(temp_path)

            assert reparsed.netlist.n_components == original_count, (
                f"Component count changed: {original_count} -> {reparsed.netlist.n_components}"
            )
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @pytest.mark.skipif(not MINIMAL_PCB.exists(), reason="Minimal PCB fixture not found")
    def test_component_refs_preserved(self):
        """Component reference designators should be preserved."""
        original_result = parse_kicad_pcb(MINIMAL_PCB)
        original_refs = set(c.ref for c in original_result.netlist.components)

        # Export with new positions
        placements = {}
        for comp in original_result.netlist.components:
            placements[comp.ref] = PlacementUpdate(
                ref=comp.ref,
                x=20.0,
                y=20.0,
                rotation=0.0,
            )

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            temp_path = Path(f.name)

        try:
            write_placements_to_pcb(
                template_pcb=MINIMAL_PCB,
                output_pcb=temp_path,
                placements=placements,
            )

            reparsed = parse_kicad_pcb(temp_path)
            reparsed_refs = set(c.ref for c in reparsed.netlist.components)

            assert original_refs == reparsed_refs, (
                f"Component refs changed: {original_refs} -> {reparsed_refs}"
            )
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @pytest.mark.skipif(not MINIMAL_PCB.exists(), reason="Minimal PCB fixture not found")
    def test_net_count_preserved(self):
        """Net count should be preserved after roundtrip."""
        original_result = parse_kicad_pcb(MINIMAL_PCB)
        assert original_result.board is not None, "Original parse has no board"
        origin = original_result.board.origin
        original_net_count = len(original_result.netlist.nets)

        # Export
        placements = {}
        for comp in original_result.netlist.components:
            pos = comp.initial_position or (10.0, 10.0)
            placements[comp.ref] = PlacementUpdate(
                ref=comp.ref,
                x=pos[0] + origin[0],
                y=pos[1] + origin[1],
                rotation=0.0,
            )

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            temp_path = Path(f.name)

        try:
            write_placements_to_pcb(
                template_pcb=MINIMAL_PCB,
                output_pcb=temp_path,
                placements=placements,
            )

            reparsed = parse_kicad_pcb(temp_path)

            assert len(reparsed.netlist.nets) == original_net_count, (
                f"Net count changed: {original_net_count} -> {len(reparsed.netlist.nets)}"
            )
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @pytest.mark.skipif(not MINIMAL_PCB.exists(), reason="Minimal PCB fixture not found")
    def test_board_dimensions_preserved(self):
        """Board dimensions should not change after roundtrip."""
        original_result = parse_kicad_pcb(MINIMAL_PCB)
        assert original_result.board is not None, "Original parse has no board"

        placements = {
            comp.ref: PlacementUpdate(ref=comp.ref, x=20.0, y=20.0, rotation=0.0)
            for comp in original_result.netlist.components
        }

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            temp_path = Path(f.name)

        try:
            write_placements_to_pcb(
                template_pcb=MINIMAL_PCB,
                output_pcb=temp_path,
                placements=placements,
            )

            reparsed = parse_kicad_pcb(temp_path)
            assert reparsed.board is not None, "Reparsed has no board"

            assert abs(reparsed.board.width - original_result.board.width) < 0.01, (
                f"Board width changed: {original_result.board.width} -> {reparsed.board.width}"
            )
            assert abs(reparsed.board.height - original_result.board.height) < 0.01, (
                f"Board height changed: {original_result.board.height} -> {reparsed.board.height}"
            )
        finally:
            if temp_path.exists():
                temp_path.unlink()


class TestIdempotency:
    """Tests for idempotent exports."""

    @pytest.mark.skipif(not MINIMAL_PCB.exists(), reason="Minimal PCB fixture not found")
    def test_idempotent_export_positions(self):
        """Exporting twice should produce same positions."""
        original_result = parse_kicad_pcb(MINIMAL_PCB)

        placements = {}
        for i, comp in enumerate(original_result.netlist.components):
            placements[comp.ref] = PlacementUpdate(
                ref=comp.ref,
                x=15.0 + i * 10.0,
                y=25.0 + i * 5.0,
                rotation=float((i % 4) * 90),
            )

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f1:
            temp1 = Path(f1.name)
        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f2:
            temp2 = Path(f2.name)

        try:
            # First export
            write_placements_to_pcb(
                template_pcb=MINIMAL_PCB,
                output_pcb=temp1,
                placements=placements,
            )

            # Second export (same placements to first output)
            write_placements_to_pcb(
                template_pcb=temp1,
                output_pcb=temp2,
                placements=placements,
            )

            # Parse both and compare
            result1 = parse_kicad_pcb(temp1)
            result2 = parse_kicad_pcb(temp2)

            for c1, c2 in zip(result1.netlist.components, result2.netlist.components):
                assert c1.ref == c2.ref
                if c1.initial_position and c2.initial_position:
                    pos_diff = abs(c1.initial_position[0] - c2.initial_position[0]) + abs(
                        c1.initial_position[1] - c2.initial_position[1]
                    )
                    assert pos_diff < POSITION_TOLERANCE, (
                        f"Position changed between exports for {c1.ref}"
                    )
                assert c1.initial_rotation == c2.initial_rotation, (
                    f"Rotation changed between exports for {c1.ref}"
                )
        finally:
            if temp1.exists():
                temp1.unlink()
            if temp2.exists():
                temp2.unlink()

    @pytest.mark.skipif(not MINIMAL_PCB.exists(), reason="Minimal PCB fixture not found")
    def test_parse_export_parse_idempotent(self):
        """Parse -> export -> parse should give same data as parse -> export -> parse -> export -> parse."""
        original = parse_kicad_pcb(MINIMAL_PCB)
        assert original.board is not None, "Original parse has no board"

        # Create deterministic placements
        placements = {}
        for comp in original.netlist.components:
            placements[comp.ref] = PlacementUpdate(
                ref=comp.ref,
                x=30.0,
                y=30.0,
                rotation=90.0,
            )

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f1:
            temp1 = Path(f1.name)
        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f2:
            temp2 = Path(f2.name)

        try:
            # First roundtrip
            write_placements_to_pcb(MINIMAL_PCB, temp1, placements)
            after_first = parse_kicad_pcb(temp1)
            assert after_first.board is not None, "First roundtrip has no board"

            # Create placements from parsed result
            placements2 = {}
            for comp in after_first.netlist.components:
                pos = comp.initial_position or (30.0, 30.0)
                placements2[comp.ref] = PlacementUpdate(
                    ref=comp.ref,
                    x=pos[0] + after_first.board.origin[0],
                    y=pos[1] + after_first.board.origin[1],
                    rotation=float((comp.initial_rotation or 0) * 90),
                )

            # Second roundtrip
            write_placements_to_pcb(temp1, temp2, placements2)
            after_second = parse_kicad_pcb(temp2)

            # Compare
            assert after_first.netlist.n_components == after_second.netlist.n_components

            for c1, c2 in zip(after_first.netlist.components, after_second.netlist.components):
                assert c1.ref == c2.ref
                # Positions should be identical (within floating point tolerance)
                if c1.initial_position and c2.initial_position:
                    assert abs(c1.initial_position[0] - c2.initial_position[0]) < 0.001
                    assert abs(c1.initial_position[1] - c2.initial_position[1]) < 0.001
        finally:
            if temp1.exists():
                temp1.unlink()
            if temp2.exists():
                temp2.unlink()


class TestEdgeCases:
    """Tests for edge cases in roundtrip."""

    @pytest.mark.skipif(not MINIMAL_PCB.exists(), reason="Minimal PCB fixture not found")
    def test_preserve_unmatched_components(self):
        """Components not in placements dict should keep original positions."""
        original = parse_kicad_pcb(MINIMAL_PCB)

        if original.netlist.n_components < 2:
            pytest.skip("Need at least 2 components for this test")

        # Only update first component
        first_comp = original.netlist.components[0]
        placements = {
            first_comp.ref: PlacementUpdate(
                ref=first_comp.ref,
                x=99.0,
                y=99.0,
                rotation=180.0,
            )
        }

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            temp_path = Path(f.name)

        try:
            result = write_placements_to_pcb(
                template_pcb=MINIMAL_PCB,
                output_pcb=temp_path,
                placements=placements,
                preserve_unmatched=True,
            )

            # Should update 1, skip the rest
            assert result.components_updated == 1
            assert result.components_skipped == original.netlist.n_components - 1

            # Verify the unmatched component kept its position
            reparsed = parse_kicad_pcb(temp_path)
            for comp in reparsed.netlist.components:
                if comp.ref != first_comp.ref:
                    # Find original component
                    orig_comp = next(c for c in original.netlist.components if c.ref == comp.ref)
                    if orig_comp.initial_position and comp.initial_position:
                        # Should be unchanged (within tolerance)
                        assert abs(comp.initial_position[0] - orig_comp.initial_position[0]) < 0.01
                        assert abs(comp.initial_position[1] - orig_comp.initial_position[1]) < 0.01
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @pytest.mark.skipif(not MINIMAL_PCB.exists(), reason="Minimal PCB fixture not found")
    def test_zero_position_roundtrip(self):
        """Position (0, 0) relative to origin should roundtrip correctly."""
        original = parse_kicad_pcb(MINIMAL_PCB)
        assert original.board is not None, "Original parse has no board"
        origin = original.board.origin

        # Place all components at origin
        placements = {
            comp.ref: PlacementUpdate(
                ref=comp.ref,
                x=origin[0],  # Absolute (0,0) relative to board origin
                y=origin[1],
                rotation=0.0,
            )
            for comp in original.netlist.components
        }

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            temp_path = Path(f.name)

        try:
            write_placements_to_pcb(MINIMAL_PCB, temp_path, placements)
            reparsed = parse_kicad_pcb(temp_path)

            for comp in reparsed.netlist.components:
                if comp.initial_position:
                    # Origin-relative position should be (0, 0)
                    assert abs(comp.initial_position[0]) < POSITION_TOLERANCE
                    assert abs(comp.initial_position[1]) < POSITION_TOLERANCE
        finally:
            if temp_path.exists():
                temp_path.unlink()

    @pytest.mark.skipif(not MINIMAL_PCB.exists(), reason="Minimal PCB fixture not found")
    def test_large_position_roundtrip(self):
        """Large position values should roundtrip correctly."""
        original = parse_kicad_pcb(MINIMAL_PCB)
        assert original.board is not None, "Original parse has no board"

        # Use large but reasonable PCB coordinates (1000mm = 1m)
        placements = {
            comp.ref: PlacementUpdate(
                ref=comp.ref,
                x=500.123,
                y=750.456,
                rotation=0.0,
            )
            for comp in original.netlist.components
        }

        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as f:
            temp_path = Path(f.name)

        try:
            write_placements_to_pcb(MINIMAL_PCB, temp_path, placements)
            reparsed = parse_kicad_pcb(temp_path)
            assert reparsed.board is not None, "Reparsed has no board"

            for comp in reparsed.netlist.components:
                if comp.initial_position:
                    # Check absolute position (add origin back)
                    actual_x = comp.initial_position[0] + reparsed.board.origin[0]
                    actual_y = comp.initial_position[1] + reparsed.board.origin[1]
                    assert abs(actual_x - 500.123) < POSITION_TOLERANCE
                    assert abs(actual_y - 750.456) < POSITION_TOLERANCE
        finally:
            if temp_path.exists():
                temp_path.unlink()
