"""Tests for KiCad PCB writer."""

import json
import tempfile
from pathlib import Path

import pytest

from temper_placer.io.kicad_writer import (
    PlacementUpdate,
    WriteResult,
    placements_from_json,
    placements_to_json,
    state_to_placements,
)
from temper_placer.core.state import PlacementState


class TestPlacementUpdate:
    """Tests for PlacementUpdate dataclass."""

    def test_basic_update(self):
        update = PlacementUpdate(ref="U1", x=10.0, y=20.0, rotation=90.0)
        assert update.ref == "U1"
        assert update.x == 10.0
        assert update.y == 20.0
        assert update.rotation == 90.0


class TestWriteResult:
    """Tests for WriteResult dataclass."""

    def test_no_warnings(self):
        result = WriteResult(
            output_path=Path("/tmp/test.kicad_pcb"),
            components_updated=10,
            components_skipped=2,
            warnings=[],
        )
        assert not result.has_warnings
        assert result.components_updated == 10
        assert result.components_skipped == 2

    def test_with_warnings(self):
        result = WriteResult(
            output_path=Path("/tmp/test.kicad_pcb"),
            components_updated=10,
            components_skipped=2,
            warnings=["Component X not found"],
        )
        assert result.has_warnings
        assert len(result.warnings) == 1


class TestPlacementsJson:
    """Tests for JSON serialization of placements."""

    def test_placements_to_json(self):
        placements = {
            "U1": PlacementUpdate(ref="U1", x=10.0, y=20.0, rotation=90.0),
            "R1": PlacementUpdate(ref="R1", x=30.0, y=40.0, rotation=0.0),
        }
        data = placements_to_json(placements)

        assert data["U1"]["x"] == 10.0
        assert data["U1"]["y"] == 20.0
        assert data["U1"]["rotation"] == 90.0
        assert data["R1"]["x"] == 30.0
        assert data["R1"]["rotation"] == 0.0

    def test_placements_from_json(self):
        data = {
            "U1": {"x": 10.0, "y": 20.0, "rotation": 90.0},
            "R1": {"x": 30.0, "y": 40.0, "rotation": 0.0},
        }
        placements = placements_from_json(data)

        assert placements["U1"].ref == "U1"
        assert placements["U1"].x == 10.0
        assert placements["U1"].y == 20.0
        assert placements["U1"].rotation == 90.0
        assert placements["R1"].ref == "R1"

    def test_roundtrip(self):
        """Test that to_json -> from_json preserves data."""
        original = {
            "U1": PlacementUpdate(ref="U1", x=10.5, y=20.5, rotation=180.0),
            "C1": PlacementUpdate(ref="C1", x=0.0, y=0.0, rotation=270.0),
        }

        data = placements_to_json(original)
        restored = placements_from_json(data)

        for ref in original:
            assert restored[ref].ref == original[ref].ref
            assert restored[ref].x == original[ref].x
            assert restored[ref].y == original[ref].y
            assert restored[ref].rotation == original[ref].rotation

    def test_json_serializable(self):
        """Test that placements_to_json output is JSON-serializable."""
        placements = {
            "U1": PlacementUpdate(ref="U1", x=10.0, y=20.0, rotation=90.0),
        }
        data = placements_to_json(placements)

        # Should not raise
        json_str = json.dumps(data)
        assert isinstance(json_str, str)

        # Should round-trip through JSON
        restored_data = json.loads(json_str)
        restored = placements_from_json(restored_data)
        assert restored["U1"].x == 10.0


class TestStateToPlacementsConversion:
    """Tests for converting PlacementState to placements."""

    def test_basic_conversion(self):
        """Test converting a simple state to placements."""
        import jax.numpy as jnp

        # Create a state with 3 components
        positions = jnp.array([[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]])
        # Rotation logits: strongly prefer specific rotations
        # Component 0: 0 degrees, Component 1: 90 degrees, Component 2: 180 degrees
        logits = jnp.array(
            [
                [10.0, 0.0, 0.0, 0.0],  # 0 deg
                [0.0, 10.0, 0.0, 0.0],  # 90 deg
                [0.0, 0.0, 10.0, 0.0],  # 180 deg
            ]
        )
        state = PlacementState.from_positions(positions, rotation_logits=logits)
        component_refs = ["U1", "R1", "C1"]

        placements = state_to_placements(state, component_refs)

        assert len(placements) == 3
        assert placements["U1"].x == 10.0
        assert placements["U1"].y == 20.0
        assert placements["U1"].rotation == 0.0  # 0 * 90
        assert placements["R1"].x == 30.0
        assert placements["R1"].rotation == 90.0  # 1 * 90
        assert placements["C1"].rotation == 180.0  # 2 * 90

    def test_conversion_with_origin(self):
        """Test that origin offset is applied."""
        import jax.numpy as jnp

        positions = jnp.array([[10.0, 20.0]])
        state = PlacementState.from_positions(positions)
        component_refs = ["U1"]

        placements = state_to_placements(state, component_refs, origin=(100.0, 50.0))

        assert placements["U1"].x == 110.0  # 10 + 100
        assert placements["U1"].y == 70.0  # 20 + 50
