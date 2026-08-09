"""Tests for kicad_writer serialization helpers.

Tests placements_to_json and placements_from_json roundtrip behaviour.
"""

from temper_placer.io.kicad_writer import (
    PlacementUpdate,
    placements_from_json,
    placements_to_json,
)


class TestPlacementsToJson:
    """Tests for placements_to_json."""

    def test_empty(self):
        """Empty placements produce empty dict."""
        result = placements_to_json({})
        assert result == {}

    def test_single_placement(self):
        """Single placement serializes correctly."""
        placements = {
            "U1": PlacementUpdate(ref="U1", x=10.0, y=20.0, rotation=0.0),
        }
        result = placements_to_json(placements)
        assert result == {"U1": {"x": 10.0, "y": 20.0, "rotation": 0.0}}

    def test_multiple_placements(self):
        """Multiple placements all serialize."""
        placements = {
            "U1": PlacementUpdate(ref="U1", x=10.0, y=20.0, rotation=0.0),
            "R1": PlacementUpdate(ref="R1", x=30.0, y=40.0, rotation=90.0),
            "C1": PlacementUpdate(ref="C1", x=50.0, y=60.0, rotation=270.0),
        }
        result = placements_to_json(placements)
        assert len(result) == 3
        assert result["R1"]["rotation"] == 90.0
        assert result["C1"]["x"] == 50.0

    def test_negative_coordinates(self):
        """Negative coordinates serialize correctly."""
        placements = {
            "J1": PlacementUpdate(ref="J1", x=-10.5, y=-3.2, rotation=180.0),
        }
        result = placements_to_json(placements)
        assert result["J1"]["x"] == -10.5
        assert result["J1"]["y"] == -3.2


class TestPlacementsFromJson:
    """Tests for placements_from_json."""

    def test_empty(self):
        """Empty dict produces empty placements."""
        result = placements_from_json({})
        assert result == {}

    def test_single_placement(self):
        """Single placement deserializes correctly."""
        data = {"U1": {"x": 10.0, "y": 20.0, "rotation": 0.0}}
        result = placements_from_json(data)
        assert len(result) == 1
        p = result["U1"]
        assert p.ref == "U1"
        assert p.x == 10.0
        assert p.y == 20.0
        assert p.rotation == 0.0

    def test_float_values_from_int(self):
        """Integer values are converted to float."""
        data = {"U1": {"x": 10, "y": 20, "rotation": 90}}
        result = placements_from_json(data)
        assert isinstance(result["U1"].x, float)
        assert isinstance(result["U1"].y, float)
        assert isinstance(result["U1"].rotation, float)
        assert result["U1"].x == 10.0

    def test_multiple_placements(self):
        """Multiple placements all deserialize."""
        data = {
            "U1": {"x": 10, "y": 20, "rotation": 0},
            "R1": {"x": 30, "y": 40, "rotation": 90},
        }
        result = placements_from_json(data)
        assert len(result) == 2
        assert result["U1"].ref == "U1"
        assert result["R1"].ref == "R1"


class TestRoundtrip:
    """Roundtrip tests for placements_to_json + placements_from_json."""

    def test_roundtrip_single(self):
        """Single placement survives roundtrip."""
        original = {
            "U1": PlacementUpdate(ref="U1", x=12.5, y=34.5, rotation=90.0),
        }
        restored = placements_from_json(placements_to_json(original))
        assert len(restored) == 1
        p = restored["U1"]
        assert p.ref == original["U1"].ref
        assert p.x == original["U1"].x
        assert p.y == original["U1"].y
        assert p.rotation == original["U1"].rotation

    def test_roundtrip_multiple(self):
        """Multiple placements survive roundtrip."""
        original = {
            "U1": PlacementUpdate(ref="U1", x=10.0, y=20.0, rotation=0.0),
            "R1": PlacementUpdate(ref="R1", x=30.0, y=40.0, rotation=90.0),
            "C1": PlacementUpdate(ref="C1", x=50.0, y=60.0, rotation=270.0),
        }
        restored = placements_from_json(placements_to_json(original))
        assert len(restored) == 3
        for ref, p in restored.items():
            orig = original[ref]
            assert p.ref == orig.ref
            assert p.x == orig.x
            assert p.y == orig.y
            assert p.rotation == orig.rotation
