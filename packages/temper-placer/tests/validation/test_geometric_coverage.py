"""Tests for validation.geometric module — GeometricValidator and validate_placement."""
import numpy as np

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist, Pin
from temper_placer.core.state import PlacementState
from temper_placer.validation.geometric import (
    GeometricValidator,
    validate_placement,
)


def _make_minimal_state():
    """Create a minimal PlacementState with 1 component."""
    return PlacementState(
        positions=np.array([[25.0, 25.0]], dtype=np.float32),
        rotation_logits=np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32),
    )


def _make_minimal_netlist():
    """Create a minimal Netlist with 1 component."""
    comp = Component(ref="U1", footprint="SOIC-8", bounds=(10.0, 10.0), pins=[])
    return Netlist(components=[comp], nets=[])


def _make_minimal_board():
    """Create a minimal Board."""
    return Board(width=100.0, height=100.0)


class TestGeometricValidator:
    """Tests for GeometricValidator."""

    def test_name(self):
        v = GeometricValidator()
        assert v.name == "GeometricValidator"

    def test_is_available(self):
        v = GeometricValidator()
        assert v.is_available() is True

    def test_validate_clean_placement(self):
        v = GeometricValidator()
        state = _make_minimal_state()
        netlist = _make_minimal_netlist()
        board = _make_minimal_board()
        result = v.validate(state, netlist, board)
        assert result.valid is True
        assert result.validator_name == "GeometricValidator"
        assert "overlap_count" in result.metrics


class TestValidatePlacement:
    """Tests for validate_placement function."""

    def test_validate_placement_clean(self):
        state = _make_minimal_state()
        netlist = _make_minimal_netlist()
        board = _make_minimal_board()
        result = validate_placement(state, netlist, board)
        assert result.valid is True
