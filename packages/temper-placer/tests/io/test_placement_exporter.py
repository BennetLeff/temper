"""
Tests for placement_exporter module.

These tests verify the bridge functionality between optimization state
(JAX arrays) and KiCad PCB files for DRC validation.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import jax.numpy as jnp
import pytest

from temper_placer.io.placement_exporter import (
    cleanup_temp_pcb,
    create_pcb_exporter,
    export_positions_to_temp_pcb,
    positions_to_placements,
    rotation_index_to_degrees,
    soft_to_discrete_rotations,
)
from temper_placer.io.kicad_writer import PlacementUpdate


class TestSoftToDiscreteRotations:
    """Tests for soft_to_discrete_rotations."""

    def test_perfect_one_hot(self):
        """Perfect one-hot vectors should convert to correct indices."""
        rotations = jnp.array(
            [
                [1.0, 0.0, 0.0, 0.0],  # 0°
                [0.0, 1.0, 0.0, 0.0],  # 90°
                [0.0, 0.0, 1.0, 0.0],  # 180°
                [0.0, 0.0, 0.0, 1.0],  # 270°
            ]
        )

        indices = soft_to_discrete_rotations(rotations)

        assert indices.shape == (4,)
        assert int(indices[0]) == 0
        assert int(indices[1]) == 1
        assert int(indices[2]) == 2
        assert int(indices[3]) == 3

    def test_soft_rotations(self):
        """Soft rotations should pick the maximum."""
        # First has highest at index 0, second at index 2
        rotations = jnp.array(
            [
                [0.7, 0.1, 0.1, 0.1],  # Should be 0
                [0.1, 0.1, 0.6, 0.2],  # Should be 2
            ]
        )

        indices = soft_to_discrete_rotations(rotations)

        assert int(indices[0]) == 0
        assert int(indices[1]) == 2

    def test_nearly_uniform(self):
        """Nearly uniform distributions should still pick one."""
        rotations = jnp.array(
            [
                [0.26, 0.25, 0.25, 0.24],  # Slightly prefer 0
            ]
        )

        indices = soft_to_discrete_rotations(rotations)

        assert int(indices[0]) == 0

    def test_empty_input(self):
        """Empty input should return empty output."""
        rotations = jnp.zeros((0, 4))
        indices = soft_to_discrete_rotations(rotations)
        assert indices.shape == (0,)


class TestRotationIndexToDegrees:
    """Tests for rotation_index_to_degrees."""

    def test_all_indices(self):
        """All indices should map to correct degrees."""
        assert rotation_index_to_degrees(0) == 0.0
        assert rotation_index_to_degrees(1) == 90.0
        assert rotation_index_to_degrees(2) == 180.0
        assert rotation_index_to_degrees(3) == 270.0


class TestPositionsToPlacements:
    """Tests for positions_to_placements."""

    def test_basic_conversion(self):
        """Basic conversion should work correctly."""
        positions = jnp.array(
            [
                [10.0, 20.0],
                [30.0, 40.0],
            ]
        )
        rotations = jnp.array(
            [
                [1.0, 0.0, 0.0, 0.0],  # 0°
                [0.0, 0.0, 1.0, 0.0],  # 180°
            ]
        )
        refs = ["U1", "R1"]

        placements = positions_to_placements(positions, rotations, refs)

        assert len(placements) == 2

        assert placements["U1"].ref == "U1"
        assert placements["U1"].x == 10.0
        assert placements["U1"].y == 20.0
        assert placements["U1"].rotation == 0.0

        assert placements["R1"].ref == "R1"
        assert placements["R1"].x == 30.0
        assert placements["R1"].y == 40.0
        assert placements["R1"].rotation == 180.0

    def test_with_origin_offset(self):
        """Origin offset should be added to positions."""
        positions = jnp.array(
            [
                [10.0, 20.0],
            ]
        )
        rotations = jnp.array(
            [
                [1.0, 0.0, 0.0, 0.0],
            ]
        )
        refs = ["U1"]
        origin = (100.0, 50.0)

        placements = positions_to_placements(positions, rotations, refs, origin)

        assert placements["U1"].x == 110.0
        assert placements["U1"].y == 70.0

    def test_mismatched_positions_raises(self):
        """Mismatched position count should raise ValueError."""
        positions = jnp.array([[10.0, 20.0], [30.0, 40.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
        refs = ["U1"]  # Only 1 ref for 2 positions

        with pytest.raises(ValueError, match="Position count.*doesn't match"):
            positions_to_placements(positions, rotations, refs)

    def test_mismatched_rotations_raises(self):
        """Mismatched rotation count should raise ValueError."""
        positions = jnp.array([[10.0, 20.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
        refs = ["U1"]

        with pytest.raises(ValueError, match="Rotation count.*doesn't match"):
            positions_to_placements(positions, rotations, refs)

    def test_empty_input(self):
        """Empty input should return empty dict."""
        positions = jnp.zeros((0, 2))
        rotations = jnp.zeros((0, 4))
        refs = []

        placements = positions_to_placements(positions, rotations, refs)

        assert placements == {}


class TestCleanupTempPcb:
    """Tests for cleanup_temp_pcb."""

    def test_deletes_existing_file(self):
        """Should delete existing file and return True."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".kicad_pcb") as f:
            temp_path = Path(f.name)

        assert temp_path.exists()
        result = cleanup_temp_pcb(temp_path)
        assert result is True
        assert not temp_path.exists()

    def test_nonexistent_file_returns_false(self):
        """Should return False for non-existent file."""
        temp_path = Path("/nonexistent/path/file.kicad_pcb")
        result = cleanup_temp_pcb(temp_path)
        assert result is False


# Tests that require mocking LossContext
class TestExportPositionsToTempPcb:
    """Tests for export_positions_to_temp_pcb."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock LossContext with minimal components."""
        context = MagicMock()

        # Create mock components
        comp1 = MagicMock()
        comp1.ref = "U1"
        comp2 = MagicMock()
        comp2.ref = "R1"

        context.netlist.components = [comp1, comp2]

        return context

    @pytest.fixture
    def mock_template_pcb(self, tmp_path):
        """Create a mock template PCB file."""
        template = tmp_path / "template.kicad_pcb"
        template.write_text("(kicad_pcb ...)")  # Minimal content
        return template

    def test_template_not_found_raises(self, mock_context):
        """Should raise ValueError if template doesn't exist."""
        positions = jnp.array([[10.0, 20.0], [30.0, 40.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
        template = Path("/nonexistent/template.kicad_pcb")

        with pytest.raises(ValueError, match="Template PCB not found"):
            export_positions_to_temp_pcb(positions, rotations, mock_context, template)

    @patch("temper_placer.io.placement_exporter.write_placements_to_pcb")
    def test_calls_write_placements(self, mock_write, mock_context, mock_template_pcb, tmp_path):
        """Should call write_placements_to_pcb with correct arguments."""
        positions = jnp.array([[10.0, 20.0], [30.0, 40.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])

        # Mock successful write
        mock_result = MagicMock()
        mock_result.has_warnings = False
        mock_write.return_value = mock_result

        result_path = export_positions_to_temp_pcb(
            positions,
            rotations,
            mock_context,
            mock_template_pcb,
            board_origin=(100.0, 50.0),
            temp_dir=tmp_path,
        )

        # Verify write_placements_to_pcb was called
        assert mock_write.called

        call_args = mock_write.call_args
        assert call_args.kwargs["template_pcb"] == mock_template_pcb

        # Check placements have origin offset applied
        placements = call_args.kwargs["placements"]
        assert "U1" in placements
        assert placements["U1"].x == 110.0  # 10 + 100
        assert placements["U1"].y == 70.0  # 20 + 50

        # Result should be a Path
        assert isinstance(result_path, Path)

    @patch("temper_placer.io.placement_exporter.write_placements_to_pcb")
    def test_cleans_up_on_failure(self, mock_write, mock_context, mock_template_pcb, tmp_path):
        """Should clean up temp file if write fails."""
        positions = jnp.array([[10.0, 20.0], [30.0, 40.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])

        # Mock failed write
        mock_write.side_effect = Exception("Write failed")

        with pytest.raises(RuntimeError, match="Failed to write temp PCB"):
            export_positions_to_temp_pcb(
                positions,
                rotations,
                mock_context,
                mock_template_pcb,
                temp_dir=tmp_path,
            )


class TestCreatePcbExporter:
    """Tests for create_pcb_exporter factory function."""

    def test_returns_callable(self, tmp_path):
        """Should return a callable function."""
        template = tmp_path / "template.kicad_pcb"
        template.write_text("(kicad_pcb ...)")

        exporter = create_pcb_exporter(
            template_pcb=template,
            board_origin=(100.0, 50.0),
        )

        assert callable(exporter)

    @patch("temper_placer.io.placement_exporter.export_positions_to_temp_pcb")
    def test_exporter_passes_arguments(self, mock_export, tmp_path):
        """Exporter should pass arguments to export_positions_to_temp_pcb."""
        template = tmp_path / "template.kicad_pcb"
        template.write_text("(kicad_pcb ...)")
        origin = (100.0, 50.0)

        exporter = create_pcb_exporter(
            template_pcb=template,
            board_origin=origin,
            temp_dir=tmp_path,
        )

        # Call the exporter
        positions = jnp.array([[10.0, 20.0]])
        rotations = jnp.array([[1.0, 0.0, 0.0, 0.0]])
        mock_context = MagicMock()

        mock_export.return_value = tmp_path / "output.kicad_pcb"

        exporter(positions, rotations, mock_context)

        # Verify export_positions_to_temp_pcb was called with correct args
        mock_export.assert_called_once()
        call_kwargs = mock_export.call_args.kwargs

        assert jnp.allclose(call_kwargs["positions"], positions)
        assert jnp.allclose(call_kwargs["rotations"], rotations)
        assert call_kwargs["context"] is mock_context
        assert call_kwargs["template_pcb"] == template
        assert call_kwargs["board_origin"] == origin
        assert call_kwargs["temp_dir"] == tmp_path
