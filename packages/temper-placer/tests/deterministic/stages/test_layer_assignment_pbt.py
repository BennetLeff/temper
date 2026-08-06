"""Property-based + metamorphic tests for the migrated layer_assignment compute.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). Bit-identical parity
against the pinned oracle is asserted separately by
``test_layer_assignment_rust_differential.py``.

Five hypothesis properties (R1c):

- P1. Total mapping: every net class (and unknown classes) resolves to a
  (layer, is_plane) pair; plane classes are exactly the inner-plane ones.
- P2. Plane status consistency: `is_plane == (layer == 1 or layer == 2)`
  for the mapping-table classes.
- P3. Manual override wins: a manual assignment shadows the net class.
- P4. Config override wins: `net_classes` overrides the parser net_class.
- P5. Net order preserved: the assignment list follows netlist net order.

Three metamorphic relations (R1d):

- MR1. Assignment-total: the set of assigned net names equals the netlist
  net-name set (no net is dropped, none invented).
- MR2. Manual-only invariance: when every net has a manual assignment, the
  net-class table is irrelevant — the output depends only on the manual map.
- MR3. Signal-default: a missing/empty net class falls back to the Signal
  row exactly like the oracle's `or "Signal"`.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

_RS = _tdb.deterministic_leaves
LA = _tdb.LayerAssignment

_NET_CLASSES = [
    "HighVoltage",
    "Power",
    "PowerTrace",
    "Ground",
    "Signal",
    "Differential",
    "FinePitch",
    "FinePitchPower",
    "Unknown",
    "",
]
_NAMES = st.text(min_size=1, max_size=8, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ+_-0123456789")


class _FakeNet:
    def __init__(self, name, net_class=None):
        self.name = name
        self.net_class = net_class


def _mk(net_class):
    return [_FakeNet(f"N{i}", net_class) for i in range(3)]


@given(st.sampled_from(_NET_CLASSES))
@settings(max_examples=50, deadline=None)
def test_p1_total_mapping(net_class):
    layer, is_plane = _RS.assign_layer_by_net_class_py(net_class)
    assert layer in (0, 1, 2, 3)
    assert isinstance(is_plane, bool)
    assert (0, False) <= (layer, is_plane)


@given(st.sampled_from(_NET_CLASSES))
@settings(max_examples=50, deadline=None)
def test_p2_plane_status_consistent(net_class):
    layer, is_plane = _RS.assign_layer_by_net_class_py(net_class)
    assert is_plane == (layer in (1, 2))


@given(st.sampled_from(_NET_CLASSES), st.integers(min_value=0, max_value=3))
@settings(max_examples=50, deadline=None)
def test_p3_manual_override_wins(net_class, layer):
    nets = _mk(net_class)
    got = list(_RS.assign_layers(nets, {"N0": layer}, {}))
    assert got[0].layer == layer
    assert got[0].is_plane == (layer in (1, 2))


@given(st.sampled_from(_NET_CLASSES), st.sampled_from(_NET_CLASSES))
@settings(max_examples=50, deadline=None)
def test_p4_config_override_wins(parser_nc, config_nc):
    nets = [_FakeNet("N0", parser_nc)]
    got = list(_RS.assign_layers(nets, {}, {"N0": config_nc}))
    exp_layer, exp_plane = _RS.assign_layer_by_net_class_py(config_nc)
    assert got[0].layer == exp_layer
    assert got[0].is_plane == exp_plane


@given(st.lists(_NAMES, min_size=0, max_size=6))
@settings(max_examples=50, deadline=None)
def test_p5_net_order_preserved(names):
    nets = [_FakeNet(n, "Signal") for n in names]
    got = list(_RS.assign_layers(nets, {}, {}))
    assert [a.net_name for a in got] == names


@given(st.lists(_NAMES, min_size=0, max_size=6))
@settings(max_examples=50, deadline=None)
def test_mr1_assignment_total(names):
    nets = [_FakeNet(n, "Signal") for n in names]
    got = list(_RS.assign_layers(nets, {}, {}))
    assert {a.net_name for a in got} == set(names)
    assert len(got) == len(names)


@given(st.lists(_NAMES, min_size=1, max_size=6), st.integers(min_value=0, max_value=3))
@settings(max_examples=50, deadline=None)
def test_mr2_manual_only_invariance(names, layer):
    manual = {n: layer for n in names}
    a = list(_RS.assign_layers([_FakeNet(n, "Ground") for n in names], manual, {}))
    b = list(_RS.assign_layers([_FakeNet(n, "Signal") for n in names], manual, {}))
    assert [(x.net_name, x.layer, x.is_plane) for x in a] == [
        (x.net_name, x.layer, x.is_plane) for x in b
    ]


@given(_NAMES)
@settings(max_examples=50, deadline=None)
def test_mr3_signal_default(name):
    none_nc = list(_RS.assign_layers([_FakeNet(name, None)], {}, {}))
    empty_nc = list(_RS.assign_layers([_FakeNet(name, "")], {}, {}))
    signal = list(_RS.assign_layers([_FakeNet(name, "Signal")], {}, {}))
    assert none_nc[0].layer == signal[0].layer
    assert empty_nc[0].layer == signal[0].layer
    assert none_nc[0].is_plane == signal[0].is_plane
