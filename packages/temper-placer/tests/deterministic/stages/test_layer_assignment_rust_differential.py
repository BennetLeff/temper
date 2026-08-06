"""Differential test: layer_assignment compute, Rust vs oracle.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). The pure compute of
``deterministic/stages/layer_assignment.py`` moves to the
``temper-design-bundle`` crate (``temper_design_bundle_python.deterministic_leaves``);
the Python module becomes a delegation shim. The pre-migration
implementation is pinned VERBATIM as the oracle
(``_layer_assignment_py_oracle.py``).

R1a: the net-class mapping table, the manual-assignment branch (plane status
inferred from the layer index), the ``or "Signal"`` fallback, and the
`LayerAssignment` pyclass all compare bit-identically via the type-carrying
``canon``. Iteration order is the netlist net order (a list).
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
import tests.deterministic.stages._layer_assignment_py_oracle as _oracle
from tests.core._contract_canon import canon

_RS = _tdb.deterministic_leaves
LA = _tdb.LayerAssignment


def _assert_net_class(net_class):
    exp = _oracle.assign_layer_by_net_class(net_class)
    got = _RS.assign_layer_by_net_class_py(net_class)
    assert exp == got, f"net_class={net_class!r}"


def test_net_class_mapping_table():
    for nc in [
        "HighVoltage",
        "Power",
        "PowerTrace",
        "Ground",
        "Signal",
        "Differential",
        "FinePitch",
        "FinePitchPower",
    ]:
        _assert_net_class(nc)


def test_unknown_net_class_defaults():
    _assert_net_class("")
    _assert_net_class("BogusClass")
    _assert_net_class("PowerX")


class _FakeNet:
    def __init__(self, name, net_class=None):
        self.name = name
        self.net_class = net_class


def test_run_assign_layers_basic():
    nets = [
        _FakeNet("GND", "Ground"),
        _FakeNet("+5V", "Power"),
        _FakeNet("SPI_CLK", "Signal"),
        _FakeNet("DC_BUS+", "HighVoltage"),
        _FakeNet("Q_GATE", None),  # fallback path -> "Signal"
    ]
    exp = _oracle.run_assign_layers(nets, {}, {})
    got = _RS.assign_layers(nets, {}, {})
    assert canon(exp) == canon(got)
    assert len(got) == 5


def test_run_assign_layers_manual_overrides():
    nets = [
        _FakeNet("GND", "Signal"),
        _FakeNet("+5V", "Signal"),
        _FakeNet("USB", "Differential"),
    ]
    manual = {"GND": 1, "+5V": 2}
    exp = _oracle.run_assign_layers(nets, manual, {})
    got = _RS.assign_layers(nets, manual, {})
    assert canon(exp) == canon(got)
    # Manual branch infers plane status from layer index.
    by_name = {a.net_name: a for a in got}
    assert by_name["GND"].is_plane is True
    assert by_name["+5V"].is_plane is True
    assert by_name["USB"].is_plane is False


def test_run_assign_layers_net_class_overrides():
    nets = [_FakeNet("GND", None), _FakeNet("RAIL", "Ground")]
    net_classes = {"GND": "Ground"}  # config override wins over parser net_class
    exp = _oracle.run_assign_layers(nets, {}, net_classes)
    got = _RS.assign_layers(nets, {}, net_classes)
    assert canon(exp) == canon(got)


def test_empty_netlist():
    assert _oracle.run_assign_layers([], {}, {}) == []
    assert list(_RS.assign_layers([], {}, {})) == []


def test_layer_assignment_pyclass_surface():
    a = LA(net_name="GND", layer=1)
    b = _oracle.LayerAssignment(net_name="GND", layer=1)
    assert canon(a) == canon(b)
    assert a.allow_layer_change is True and a.is_plane is False
    assert type(a.layer) is int


def test_layer_assignment_repr():
    a = LA("GND", 1, True, False)
    b = _oracle.LayerAssignment("GND", 1, True, False)
    assert repr(a) == repr(b)
    assert repr(a) == "LayerAssignment(net_name='GND', layer=1, allow_layer_change=True, is_plane=False)"


def test_layer_assignment_int_preserved():
    """The dataclass coerces nothing: layer=1 stays int, layer=1.0 stays float."""
    a_int = LA("N", 1)
    a_float = LA("N", 1.0)
    assert type(a_int.layer) is int
    assert type(a_float.layer) is float
