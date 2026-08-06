"""Differential test: power_plane reassignment compute, Rust vs oracle.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). The pure compute of
``deterministic/stages/power_plane.py`` moves to the ``temper-design-bundle``
crate (``temper_design_bundle_python.deterministic_leaves``); the Python
module becomes a delegation shim. The pre-migration implementation is pinned
VERBATIM as the oracle (``_power_plane_py_oracle.py``).

R1a: the three-pass reassignment (existing-upgrade → new plane nets →
remaining nets), the ``plane_layers.get(net_name, 1)`` default, and the
emission order compare bit-identically via the type-carrying ``canon``.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
import tests.deterministic.stages._power_plane_py_oracle as _oracle
from tests.core._contract_canon import canon

_RS = _tdb.deterministic_leaves
LA = _tdb.LayerAssignment


def _assert_equal(existing, plane_nets, plane_layers, all_nets):
    exp = _oracle.recompute_plane_assignments(existing, plane_nets, plane_layers, all_nets)
    got = _RS.recompute_plane_assignments(existing, plane_nets, plane_layers, all_nets)
    assert canon(exp) == canon(got), f"existing={existing} plane_nets={plane_nets}"


def test_basic_upgrade():
    existing = [LA("GND", 1, True, False), LA("SPI_CLK", 0, True, False)]
    _assert_equal(existing, ["GND", "+5V"], {"GND": 1, "+5V": 2}, ["GND", "SPI_CLK", "+5V"])


def test_plane_nets_not_in_existing_added():
    existing = [LA("SPI_CLK", 0, True, False)]
    _assert_equal(existing, ["GND"], {"GND": 1}, ["GND", "SPI_CLK"])


def test_default_layer_is_in1():
    existing = []
    _assert_equal(existing, ["GND"], {}, ["GND"])


def test_signal_nets_added_layer0():
    existing = []
    _assert_equal(existing, [], {}, ["SPI_CLK", "GATE_HI"])


def test_existing_non_plane_preserved():
    existing = [LA("SPI_CLK", 0, False, False)]
    got = _RS.recompute_plane_assignments(existing, [], {}, ["SPI_CLK"])
    assert got[0].allow_layer_change is False  # allow_layer_change preserved
    assert got[0].layer == 0


def test_unknown_plane_nets_ignored():
    existing = [LA("GND", 1, True, False)]
    _assert_equal(existing, ["GND", "NONEXISTENT"], {"GND": 1}, ["GND"])


def test_plane_net_present_in_netlist_only():
    """A plane net not in the netlist is silently dropped (netlist filter)."""
    existing = []
    _assert_equal(existing, ["GND"], {"GND": 1}, [])


def test_empty_inputs():
    assert list(_RS.recompute_plane_assignments([], [], {}, [])) == []
    assert _oracle.recompute_plane_assignments([], [], {}, []) == []


def test_plane_override_is_plane_and_layer():
    existing = [LA("GND", 0, True, False)]
    got = _RS.recompute_plane_assignments(existing, ["GND"], {"GND": 2}, ["GND"])
    assert got[0].is_plane is True
    assert got[0].layer == 2


def test_order_emission():
    """Existing (in order) -> new plane nets (plane_nets order) -> remaining (net order)."""
    existing = [LA("A", 0, True, False), LA("B", 0, True, False)]
    got = _RS.recompute_plane_assignments(existing, ["Z"], {"Z": 2}, ["A", "B", "Z", "C"])
    assert [a.net_name for a in got] == ["A", "B", "Z", "C"]
