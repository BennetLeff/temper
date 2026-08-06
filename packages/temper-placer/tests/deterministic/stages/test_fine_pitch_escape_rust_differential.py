"""Differential test: fine_pitch_escape kernels, Rust vs oracle.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). The two pure kernels
of ``deterministic/stages/fine_pitch_escape.py`` move to the
``temper-design-bundle`` crate (``temper_design_bundle_python.deterministic_leaves``);
the Python module becomes a delegation shim. The pre-migration
implementation is pinned VERBATIM as the oracle
(``_fine_pitch_escape_py_oracle.py``).

R1a: minimum pin pitch (`dx*dx` direct multiplication, `math.sqrt`,
first-min tie semantics, `None` for <2 pins) and the escape-layer selection
compare bit-identically (floats via `float.hex()`).
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
import tests.deterministic.stages._fine_pitch_escape_py_oracle as _oracle

_RS = _tdb.deterministic_leaves


class _Pin:
    def __init__(self, position):
        self.position = position


def _assert_pitch(pins):
    exp = _oracle._calculate_min_pin_pitch(pins)
    got = _RS.min_pin_pitch_py(pins)
    if exp is None:
        assert got is None
    else:
        assert got.hex() == exp.hex()


def test_pitch_basic():
    _assert_pitch([_Pin((0, 0)), _Pin((1, 0)), _Pin((0, 1))])
    _assert_pitch([_Pin((0, 0)), _Pin((0.5, 0)), _Pin((0.25, 0.25))])


def test_pitch_fewer_than_two():
    assert _RS.min_pin_pitch_py([]) is None
    assert _RS.min_pin_pitch_py([_Pin((0, 0))]) is None
    assert _oracle._calculate_min_pin_pitch([]) is None


def test_pitch_identical_pins_zero():
    """Coincident pins give distance 0.0 (kept, not inf)."""
    _assert_pitch([_Pin((1, 1)), _Pin((1, 1))])
    assert _RS.min_pin_pitch_py([_Pin((1, 1)), _Pin((1, 1))]) == 0.0


def test_pitch_float_bit_exact():
    """Non-representable coordinates pin the sqrt result bit-for-bit."""
    _assert_pitch([_Pin((0.1, 0.2)), _Pin((0.3, 0.4)), _Pin((1.7, 2.9))])


def test_pitch_negative_coords():
    _assert_pitch([_Pin((-1, -1)), _Pin((1, 1)), _Pin((3, -2))])


def test_escape_layer_defaults():
    l2 = {"PWM_H", "PWM_L", "SPI_CLK"}
    l3 = {"I_SENSE", "TEMP_SENSE"}
    cases = ["PWM_H", "SPI_CLK", "I_SENSE", "TEMP_SENSE", "GATE_H", "OTHER", ""]
    for net in cases:
        exp = _oracle._get_escape_layer_for_net(net, l2, l3)
        got = _RS.escape_layer_for_net_py(net, l2, l3, 1, 2)
        assert got == exp, f"net={net}"


def test_escape_layer_custom_layers():
    l2 = {"A"}
    l3 = {"B"}
    assert _RS.escape_layer_for_net_py("A", l2, l3, 1, 2) == (2, "In2.Cu")
    assert _RS.escape_layer_for_net_py("B", l2, l3, 1, 2) == (3, "B.Cu")
    assert _RS.escape_layer_for_net_py("C", l2, l3, 1, 2) == (1, "In1.Cu")
    assert _RS.escape_layer_for_net_py("A", l2, l3, 5, 9) == (9, "In2.Cu")
    assert _RS.escape_layer_for_net_py("C", l2, l3, 5, 9) == (5, "In1.Cu")


def test_escape_layer_precedence_layer3_wins():
    """A net in both sets goes to B.Cu (layer-3 check runs first)."""
    l2 = {"X"}
    l3 = {"X"}
    assert _RS.escape_layer_for_net_py("X", l2, l3, 1, 2) == (3, "B.Cu")
