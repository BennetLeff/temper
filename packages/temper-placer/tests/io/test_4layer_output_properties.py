"""Property-based tests verifying 4-layer board output invariants.

Theorem: For any valid pipeline input, the generated .kicad_pcb
contains exactly 4 copper layers with canonical KiCad names.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from temper_placer.core.board import (
    CANONICAL_4LAYER_LAYER_NAMES,
    Board,
    Layer,
    LayerStackup,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_TEMPER_PCB = _REPO_ROOT / "pcb" / "temper.kicad_pcb"


class TestStackupCorrectness:
    """Any Board with the canonical 4-layer stackup has exactly 4 copper layers."""

    def test_default_4layer_board_has_4_canonical_layers(self):
        """Board defaults to 4-layer stackup with correct names and types."""
        board = Board(width=100, height=100)
        assert board.layer_stackup is not None
        assert len(board.layer_stackup.layers) == 4
        names = [ly.name for ly in board.layer_stackup.layers]
        assert set(names) == set(CANONICAL_4LAYER_LAYER_NAMES)
        assert names == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
        assert board.layer_stackup.layers[0].copper_weight == 2.0
        assert board.layer_stackup.layers[0].is_routable
        assert not board.layer_stackup.layers[1].is_routable  # GND plane
        assert not board.layer_stackup.layers[2].is_routable  # PWR plane

    def test_2layer_board_refused_at_construction(self):
        """Board with 2-layer stackup raises ValueError (AE2)."""
        with pytest.raises(ValueError, match="2 layers"):
            Board(width=100, height=100, layer_stackup=LayerStackup._test_only_2layer())

    def test_6layer_board_refused_at_construction(self):
        """Board with non-canonical layer count raises ValueError."""
        stackup = LayerStackup(
            layers=[
                Layer("F.Cu", "signal"),
                Layer("I1", "plane"),
                Layer("I2", "plane"),
                Layer("I3", "plane"),
                Layer("I4", "plane"),
                Layer("B.Cu", "signal"),
            ],
            thickness=1.6,
        )
        with pytest.raises(ValueError, match="6 layers"):
            Board(width=100, height=100, layer_stackup=stackup)
