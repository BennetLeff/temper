"""Tests for temper_placer.core.board_layer_roles.

Covers the parser against synthetic board fragments (fast, no real board
file needed) and, separately, against the real committed
``pcb/temper.kicad_pcb`` (the same board every other repo gate measures) to
pin down what this module says about the actual 6-layer declaration this
change makes -- a regression here means the SSOT reader has drifted from
the SSOT it reads.
"""

from pathlib import Path

import pytest

from temper_placer.core.board_layer_roles import (
    ENGINE_SUPPORTED_SIGNAL_LAYERS,
    LayerRole,
    is_signal_layer,
    parse_declared_layer_roles,
    routable_signal_layers,
    signal_layer_names,
)

_FOUR_LAYER_FRAGMENT = """
(kicad_pcb (version 20211014) (generator kiutils)
  (layers
    (0 "F.Cu" signal)
    (1 "In1.Cu" power)
    (2 "In2.Cu" power)
    (31 "B.Cu" signal)
    (44 "Edge.Cuts" user)
    (37 "F.SilkS" user "F.Silkscreen")
  )
)
"""

_SIX_LAYER_FRAGMENT = """
(kicad_pcb (version 20211014) (generator kiutils)
  (layers
    (0 "F.Cu" signal)
    (3 "In3.Cu" signal)
    (1 "In1.Cu" power)
    (2 "In2.Cu" power)
    (4 "In4.Cu" signal)
    (31 "B.Cu" signal)
    (44 "Edge.Cuts" user)
  )
)
"""

REPO_ROOT = Path(__file__).resolve().parents[4]
REAL_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"


class TestParseDeclaredLayerRoles:
    def test_four_layer_fragment(self):
        roles = parse_declared_layer_roles(_FOUR_LAYER_FRAGMENT)
        assert roles == {
            "F.Cu": LayerRole.SIGNAL,
            "In1.Cu": LayerRole.POWER,
            "In2.Cu": LayerRole.POWER,
            "B.Cu": LayerRole.SIGNAL,
        }

    def test_non_copper_layers_are_skipped(self):
        roles = parse_declared_layer_roles(_FOUR_LAYER_FRAGMENT)
        assert "Edge.Cuts" not in roles
        assert "F.SilkS" not in roles

    def test_declared_order_preserved(self):
        roles = parse_declared_layer_roles(_SIX_LAYER_FRAGMENT)
        assert list(roles.keys()) == ["F.Cu", "In3.Cu", "In1.Cu", "In2.Cu", "In4.Cu", "B.Cu"]

    def test_missing_layers_block_raises(self):
        with pytest.raises(ValueError, match="layers"):
            parse_declared_layer_roles("(kicad_pcb (version 1))")

    def test_no_recognized_copper_layer_raises(self):
        with pytest.raises(ValueError, match="no '.Cu' layer"):
            parse_declared_layer_roles(
                '(kicad_pcb (layers (44 "Edge.Cuts" user)))'
            )


class TestSignalLayerNames:
    def test_four_layer_signal_names(self):
        assert signal_layer_names(_FOUR_LAYER_FRAGMENT) == ["F.Cu", "B.Cu"]

    def test_six_layer_signal_names(self):
        assert signal_layer_names(_SIX_LAYER_FRAGMENT) == ["F.Cu", "In3.Cu", "In4.Cu", "B.Cu"]

    def test_power_layers_excluded(self):
        names = signal_layer_names(_SIX_LAYER_FRAGMENT)
        assert "In1.Cu" not in names
        assert "In2.Cu" not in names


class TestRoutableSignalLayers:
    def test_four_layer_all_signal_layers_are_engine_supported(self):
        assert routable_signal_layers(_FOUR_LAYER_FRAGMENT) == ["F.Cu", "B.Cu"]

    def test_six_layer_new_signal_layers_are_routable(self):
        """UNFROZEN 2026-08-13
        (docs/evidence/2026-08-13-router-nlayer-routing.md): declaring
        In3.Cu/In4.Cu signal alone would not make the router capable of
        routing there -- but real occupancy-grid (routing_space.py /
        occupancy_grid.py, already N-layer generic) and via-aware A*
        (_astar_nlayer.py, tested) support for exactly these two layers
        now exists, so ENGINE_SUPPORTED_SIGNAL_LAYERS was widened to match
        -- see the module docstring's evidence list. In1.Cu/In2.Cu stay
        excluded: they are declared POWER, not SIGNAL, so
        signal_layer_names never includes them regardless of engine
        capability.
        """
        assert routable_signal_layers(_SIX_LAYER_FRAGMENT) == [
            "F.Cu",
            "In3.Cu",
            "In4.Cu",
            "B.Cu",
        ]

    def test_engine_supported_set_is_the_four_signal_layers(self):
        assert ENGINE_SUPPORTED_SIGNAL_LAYERS == frozenset(
            {"F.Cu", "In3.Cu", "In4.Cu", "B.Cu"}
        )


class TestIsSignalLayer:
    def test_signal_layer_is_true(self):
        assert is_signal_layer("F.Cu", _SIX_LAYER_FRAGMENT) is True
        assert is_signal_layer("In3.Cu", _SIX_LAYER_FRAGMENT) is True

    def test_power_layer_is_false(self):
        assert is_signal_layer("In1.Cu", _SIX_LAYER_FRAGMENT) is False
        assert is_signal_layer("In2.Cu", _SIX_LAYER_FRAGMENT) is False

    def test_unknown_layer_name_is_false_not_an_error(self):
        assert is_signal_layer("In99.Cu", _SIX_LAYER_FRAGMENT) is False

    def test_unparsable_content_is_false_not_an_error(self):
        assert is_signal_layer("F.Cu", "not a kicad board at all") is False


@pytest.mark.skipif(not REAL_BOARD.is_file(), reason="real board file not present in this checkout")
class TestAgainstTheRealBoard:
    """Pins this module's reading of the real, committed board -- catches
    drift between this SSOT reader and the SSOT it reads, independent of
    the synthetic-fragment tests above.
    """

    def test_real_board_declares_six_copper_layers(self):
        content = REAL_BOARD.read_text(encoding="utf-8")
        roles = parse_declared_layer_roles(content)
        assert set(roles) == {"F.Cu", "In3.Cu", "In1.Cu", "In2.Cu", "In4.Cu", "B.Cu"}

    def test_real_board_signal_layers(self):
        content = REAL_BOARD.read_text(encoding="utf-8")
        assert set(signal_layer_names(content)) == {"F.Cu", "In3.Cu", "In4.Cu", "B.Cu"}

    def test_real_board_power_layers_unchanged(self):
        content = REAL_BOARD.read_text(encoding="utf-8")
        roles = parse_declared_layer_roles(content)
        assert roles["In1.Cu"] is LayerRole.POWER
        assert roles["In2.Cu"] is LayerRole.POWER

    def test_real_board_routable_layers_now_four(self):
        """UNFROZEN 2026-08-13: the real board declares F.Cu/In3.Cu/In4.Cu/
        B.Cu signal, and the engine now genuinely supports routing on all
        four (see ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED's docstring for
        the evidence) -- so this SSOT accessor's answer for the real,
        committed board must match, not stay pinned at the pre-2026-08-13
        pair.
        """
        content = REAL_BOARD.read_text(encoding="utf-8")
        assert routable_signal_layers(content) == ["F.Cu", "In3.Cu", "In4.Cu", "B.Cu"]
