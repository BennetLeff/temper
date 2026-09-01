"""Differential test: deterministic zone_assignment compute, Rust vs oracle.

Wave 4, **Phase 5, first slice** (deterministic leaf stages). The pure
compute of ``temper_placer/deterministic/stages/zone_assignment.py`` moves
to the Rust orchestration stage, which calls a shared pyo3-free data-model
kernel. The pre-migration implementation is pinned VERBATIM as the oracle
(``_zone_assignment_py_oracle.py``).

Both arms consume the SAME Netlist pyclass: the Rust stage reads
``nets`` / ``components`` / ``net.name`` / ``net.net_class`` / ``net.pins``
at its object-adaptation boundary, so inputs are identical by construction.

Numerical/order traps pinned here:
- the oracle's zone-map DICT insertion order follows ``netlist.components``
  order, while the stage's owned ``frozenset`` intentionally exposes only
  mapping content; the differential compares those contents as a set;
- ``net_class_map`` falls back to ``"Signal"`` for a missing/None
  ``net_class`` via the oracle's ``getattr(net, "net_class", "Signal")``
  (the pyclass default is ``"Signal"`` — pinned by construction);
- empty-input semantics: a netlist with components but no nets assigns
  every component ``"Signal"`` (unless it matches the ``U_MCU`` prefix);
  a netlist with no components produces an empty map (asserted).
"""

from __future__ import annotations

import random

import temper_orchestration as _to
import tests.deterministic.stages._zone_assignment_py_oracle as _oracle
from tests.core._contract_canon import canon

from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.state import BoardState

def _netlist(components, nets):
    return Netlist(components=components, nets=nets)


def _comp(ref, net_names=None):
    pins = []
    for i, n in enumerate(net_names or []):
        pins.append(Pin(f"{i + 1}", str(i + 1), (0.0, 0.0), net=n))
    return Component(ref=ref, footprint="FP", bounds=(1, 1), pins=pins)


def _assert_assign_equal(netlist):
    exp = _oracle.assign_components_to_zones(netlist)
    got = dict(_to.run_zone_assignment(BoardState(netlist=netlist)).component_zone_map)
    # The stage contract writes a frozenset, so its iteration order is not
    # observable. Compare mapping content as a set while retaining the
    # oracle's dict computation for its duplicate-key semantics.
    assert canon(frozenset(exp.items())) == canon(frozenset(got.items())), (
        f"zone mismatch for {netlist!r}"
    )


def test_hv_net_class():
    netlist = _netlist(
        [_comp("Q1", ["AC_L"])],
        [Net("AC_L", [("Q1", "1")], net_class="HighVoltage")],
    )
    _assert_assign_equal(netlist)


def test_power_net_class():
    netlist = _netlist(
        [_comp("C1", ["VBUS"])],
        [Net("VBUS", [("C1", "1")], net_class="Power")],
    )
    _assert_assign_equal(netlist)


def test_mcu_prefix_and_protocol_nets():
    netlist = _netlist(
        [
            _comp("U_MCU1"),
            _comp("R1", ["SPI_CLK"]),
            _comp("R2", ["I2C_SDA"]),
            _comp("R3", ["uart_tx"]),
        ],
        [
            Net("SPI_CLK", [("R1", "1")], net_class="Signal"),
            Net("I2C_SDA", [("R2", "1")], net_class="Signal"),
            Net("uart_tx", [("R3", "1")], net_class="Signal"),
        ],
    )
    _assert_assign_equal(netlist)


def test_rule_priority():
    """A component on a Power-classed SPI net is MCU (rule 2 beats rule 4)."""
    netlist = _netlist(
        [_comp("R1", ["SPI_CLK"])],
        [Net("SPI_CLK", [("R1", "1")], net_class="Power")],
    )
    exp = _oracle.assign_components_to_zones(netlist)
    assert exp["R1"] == "MCU"
    _assert_assign_equal(netlist)


def test_empty_semantics():
    # No nets -> all Signal (or MCU by prefix).
    netlist = _netlist([_comp("R1"), _comp("U_MCU2")], [])
    exp = _oracle.assign_components_to_zones(netlist)
    assert exp == {"R1": "Signal", "U_MCU2": "MCU"}
    _assert_assign_equal(netlist)
    # No components -> empty map.
    empty = _netlist([], [Net("N", [("X", "1")])])
    assert _oracle.assign_components_to_zones(empty) == {}
    assert (
        dict(_to.run_zone_assignment(BoardState(netlist=empty)).component_zone_map)
        == {}
    )


def test_net_class_none_falls_through_to_signal():
    """A present-but-None ``net_class`` (reachable via the pyclass's settable
    attribute — the constructor's ``None`` is coerced to the "Signal"
    default by ``opt_or``, but ``net.net_class = None`` assignment stores
    None as-is, the same assignment path ``io/_parse_nets.py`` uses) fails
    both ``==`` comparisons in the oracle and falls through to Signal; the
    Rust must NOT TypeError on the None."""
    net = Net("X", [("R1", "1")])
    net.net_class = None
    netlist = _netlist([_comp("R1", ["X"])], [net])
    exp = _oracle.assign_components_to_zones(netlist)
    assert exp == {"R1": "Signal"}
    _assert_assign_equal(netlist)


def test_net_class_missing_attribute_falls_through_to_signal():
    """Duck-typed net WITHOUT a ``net_class`` attribute: the oracle's
    ``getattr(net, "net_class", "Signal")`` default fires (falls through to
    Signal); the Rust must NOT AttributeError."""

    class _PlainNet:
        """Minimal duck-typed net with no ``net_class`` attribute."""

        def __init__(self, name, pins):
            self.name = name
            self.pins = pins

    netlist = _netlist(
        [_comp("R1", ["X"])],
        [_PlainNet("X", [("R1", "1")])],
    )
    exp = _oracle.assign_components_to_zones(netlist)
    assert exp == {"R1": "Signal"}
    _assert_assign_equal(netlist)


def test_component_on_multiple_nets():
    """comp_nets appends net names in netlist order (insertion order pinned)."""
    netlist = _netlist(
        [_comp("U1", ["A", "B", "C"])],
        [
            Net("A", [("U1", "1")], net_class="Signal"),
            Net("B", [("U1", "2")], net_class="HighVoltage"),
            Net("C", [("U1", "3")], net_class="Power"),
        ],
    )
    _assert_assign_equal(netlist)
    exp = _oracle.assign_components_to_zones(netlist)
    assert exp["U1"] == "HV"  # rule 3 beats rule 4 for B-then-C scan order


def test_randomized_netlists():
    rng = random.Random(55)
    for _ in range(60):
        n_refs = rng.randrange(1, 6)
        refs = [f"C{rng.randrange(1000)}" for _ in range(n_refs)]
        if rng.random() < 0.3:
            refs[0] = "U_MCU9"
        n_nets = rng.randrange(0, 6)
        net_names = [f"NET_{i}" for i in range(n_nets)]

        # Assign each component a random subset of nets (component pins carry
        # the net name; net membership lists mirror that).
        comp_nets_of = {
            r: rng.sample(net_names, rng.randrange(0, min(3, n_nets) + 1)) for r in refs
        }
        components = [_comp(r, comp_nets_of[r]) for r in refs]
        nets = []
        for n in net_names:
            members = [(r, "1") for r in refs if n in comp_nets_of[r]]
            if not members and refs:
                members = [(refs[0], "1")]
            nc = rng.choice(["Signal", "Power", "HighVoltage"])
            nets.append(Net(n, members, net_class=nc))
        netlist = _netlist(components, nets)
        _assert_assign_equal(netlist)
