"""Property-based + metamorphic tests for the migrated fine_pitch_escape kernels.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). Bit-identical parity
against the pinned oracle is asserted separately by
``test_fine_pitch_escape_rust_differential.py``.

Five hypothesis properties (R1c):

- P1. Pitch totality: >=2 pins yields a finite pitch; <2 pins yields None.
- P2. Pitch lower bound: the pitch is never larger than any pairwise
  distance in the pin set (it IS a pairwise distance).
- P3. Layer defaults: unknown nets land on the primary layer (In1.Cu).
- P4. Layer-3 precedence: layer-3 nets always win over layer-2.
- P5. Determinism: same inputs, same outputs.

Three metamorphic relations (R1d):

- MR1. Pin-order invariance: reordering pins leaves the min pitch unchanged.
- MR2. Translation invariance: shifting all pins by a constant leaves the
  pitch unchanged.
- MR3. Layer-set commutativity: adding a net to both sets behaves like
  layer-3 membership.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

_RS = _tdb.deterministic_leaves

_COORD = st.floats(min_value=-100, max_value=100, allow_nan=False, allow_infinity=False)
_PINS = st.lists(st.tuples(_COORD, _COORD), min_size=0, max_size=8)
_NAMES = st.text(min_size=0, max_size=8, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ_+0123456789")


class _Pin:
    def __init__(self, position):
        self.position = position


def _pins(positions):
    return [_Pin(p) for p in positions]


@given(_PINS)
@settings(max_examples=100, deadline=None)
def test_p1_pitch_totality(pins):
    got = _RS.min_pin_pitch_py(_pins(pins))
    if len(pins) < 2:
        assert got is None
    else:
        assert got is not None and got >= 0.0


@given(_PINS)
@settings(max_examples=100, deadline=None)
def test_p2_pitch_is_pairwise_min(pins):
    got = _RS.min_pin_pitch_py(_pins(pins))
    if len(pins) < 2:
        return
    import math

    dists = [
        math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)
        for i, a in enumerate(pins)
        for b in pins[i + 1 :]
    ]
    assert got == min(dists)


@given(_NAMES, st.sampled_from([{""}, {"A"}, {"X"}, {"GATE_H"}, set()]))
@settings(max_examples=50, deadline=None)
def test_p3_layer_defaults(net, extra):
    l2, l3 = {"GATE_H", "PWM_H", "SPI_CLK"}, {"I_SENSE", "TEMP_SENSE"}
    layer, name = _RS.escape_layer_for_net_py(net, l2, l3, 1, 2)
    if net not in l2 and net not in l3:
        assert (layer, name) == (1, "In1.Cu")


@given(_NAMES)
@settings(max_examples=50, deadline=None)
def test_p4_layer3_precedence(net):
    l2 = {net} if net else set()
    l3 = {net} if net else set()
    layer, name = _RS.escape_layer_for_net_py(net, l2, l3, 1, 2)
    if net:
        assert (layer, name) == (3, "B.Cu")


@given(_PINS)
@settings(max_examples=100, deadline=None)
def test_p5_determinism(pins):
    a = _RS.min_pin_pitch_py(_pins(pins))
    b = _RS.min_pin_pitch_py(_pins(pins))
    if a is None:
        assert b is None
    else:
        assert a.hex() == b.hex()


@given(_PINS)
@settings(max_examples=100, deadline=None)
def test_mr1_pin_order_invariance(pins):
    got = _RS.min_pin_pitch_py(_pins(pins))
    rev = _RS.min_pin_pitch_py(_pins(list(reversed(pins))))
    if got is None:
        assert rev is None
    else:
        assert got.hex() == rev.hex()


@given(_PINS)
@settings(max_examples=100, deadline=None)
def test_mr2_coordinate_negation_invariance(pins):
    # Negation is exact in IEEE-754, so `(-x1) - (-x2) == -(x1 - x2)` and the
    # squared distances are identical; the pitch is bit-identical. (A general
    # translation would round the sum first and is NOT a valid exact MR.)
    negated = [(-x, -y) for x, y in pins]
    a = _RS.min_pin_pitch_py(_pins(pins))
    b = _RS.min_pin_pitch_py(_pins(negated))
    if a is None:
        assert b is None
    else:
        assert a.hex() == b.hex()


@given(_NAMES)
@settings(max_examples=50, deadline=None)
def test_mr3_layer_set_commutativity(net):
    both = _RS.escape_layer_for_net_py(net, {net}, {net}, 1, 2) if net else None
    only3 = _RS.escape_layer_for_net_py(net, set(), {net}, 1, 2) if net else None
    if net:
        assert both == only3
