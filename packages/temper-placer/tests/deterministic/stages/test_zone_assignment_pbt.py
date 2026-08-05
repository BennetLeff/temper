"""Property-based + metamorphic tests for the migrated zone_assignment compute.

Wave 4, Phase 5, first slice (deterministic leaf stages). These properties
exercise the migrated
``temper_design_bundle_python.deterministic_stages.assign_component_zones``
(the delegation shim ``deterministic/stages/zone_assignment.py`` calls it);
bit-identical parity against the pinned pre-migration Python is asserted
separately by ``test_zone_assignment_rust_differential.py``.

Five hypothesis properties (R1c):

- P1. Totality: every component maps to one of the four zones and nothing
  raises.
- P2. ``U_MCU`` prefix wins: a ``U_MCU*`` component is MCU regardless of
  its nets.
- P3. HV nets force HV (when no protocol net and no ``U_MCU`` prefix).
- P4. Isolated default: a component with no nets and no ``U_MCU`` prefix is
  Signal.
- P5. Determinism: the same netlist produces the identical zone map.

Three metamorphic relations (R1d):

- MR1. Signal-net addition: adding a ``Signal``-classed net whose name
  contains no SPI/I2C/UART substring never changes a component's zone.
- MR2. Class demotion: if a component's only non-Signal trigger is a
  ``HighVoltage`` net (no protocol nets, no ``U_MCU`` prefix), reclassifying
  that net to ``Power`` maps its zone HV -> Power.
- MR3. Protocol-suffix invariance: appending ``_2`` to a net name preserves
  its protocol-substring classification (the ``in`` test is substring-based).
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.netlist import Component, Net, Netlist, Pin

_RS = _tdb.deterministic_stages
RS_ASSIGN = _RS.assign_component_zones

_ZONES = ("MCU", "HV", "Power", "Signal")
_REFS = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Nd"), whitelist_characters="_"),
    min_size=1,
    max_size=12,
)


def _mk(ref, nets, classes):
    pins = [Pin(str(i), str(i), (0.0, 0.0), net=n) for i, n in enumerate(nets)]
    comps = [Component(ref=ref, footprint="FP", bounds=(1, 1), pins=pins)]
    net_objs = [Net(n, [(ref, str(i))], net_class=classes[n]) for i, n in enumerate(nets)]
    return Netlist(components=comps, nets=net_objs)


def _zones_of(netlist):
    return dict(RS_ASSIGN(netlist))


@given(
    _REFS,
    st.lists(st.text(min_size=1, max_size=12), max_size=5),
    st.lists(st.sampled_from(["Signal", "Power", "HighVoltage"]), max_size=5),
)
@settings(max_examples=150, deadline=None)
def test_p1_totality(ref, net_names, classes):
    nets = net_names[: len(classes)]
    classes = classes[: len(nets)]
    if len(set(nets)) != len(nets):
        return  # duplicate net names would collapse pins; skip
    z = _zones_of(_mk(ref, nets, dict(zip(nets, classes))))
    assert len(z) == 1
    assert z[ref] in _ZONES


@given(st.text(min_size=6, max_size=12), st.lists(st.text(min_size=1, max_size=10), max_size=4))
@settings(max_examples=100, deadline=None)
def test_p2_mcu_prefix_wins(ref, net_names):
    if not ref.startswith("U_MCU"):
        ref = "U_MCU" + ref
    classes = dict.fromkeys(net_names, "Power")
    z = _zones_of(_mk(ref, net_names, classes))
    assert z[ref] == "MCU"


@given(st.text(min_size=1, max_size=10))
@settings(max_examples=100, deadline=None)
def test_p3_hv_net_forces_hv(ref):
    if ref.startswith("U_MCU"):
        ref = "Q" + ref
    z = _zones_of(_mk(ref, ["HVNET"], {"HVNET": "HighVoltage"}))
    assert z[ref] == "HV"


@given(st.text(min_size=1, max_size=10))
@settings(max_examples=100, deadline=None)
def test_p4_isolated_default(ref):
    if ref.startswith("U_MCU"):
        ref = "R" + ref
    z = _zones_of(_mk(ref, [], {}))
    assert z[ref] == "Signal"


@given(_REFS, st.lists(st.text(min_size=1, max_size=8), max_size=4))
@settings(max_examples=80, deadline=None)
def test_p5_determinism(ref, net_names):
    classes = dict.fromkeys(net_names, "Signal")
    n1 = _mk(ref, net_names, classes)
    n2 = _mk(ref, net_names, classes)
    assert _zones_of(n1) == _zones_of(n2)


@given(_REFS, st.lists(st.text(min_size=1, max_size=8), max_size=4))
@settings(max_examples=100, deadline=None)
def test_mr1_signal_net_addition_neutral(ref, net_names):
    extra = "SIG_PLAIN"
    classes = dict.fromkeys(net_names, "Signal")
    base = _zones_of(_mk(ref, net_names, classes))
    extended = _zones_of(_mk(ref, net_names + [extra], {**classes, extra: "Signal"}))
    assert base[ref] == extended[ref]


@given(st.text(min_size=1, max_size=10))
@settings(max_examples=100, deadline=None)
def test_mr2_class_demotion(ref):
    if ref.startswith("U_MCU"):
        ref = "Q" + ref
    # The ONLY trigger is the HighVoltage net; no protocol substring.
    net = "RAIL_1"
    assert not any(p in net.upper() for p in ["SPI", "I2C", "UART"])
    hv = _zones_of(_mk(ref, [net], {net: "HighVoltage"}))
    pw = _zones_of(_mk(ref, [net], {net: "Power"}))
    assert hv[ref] == "HV"
    assert pw[ref] == "Power"


@given(_REFS, st.sampled_from(["SPI", "I2C", "UART"]))
@settings(max_examples=100, deadline=None)
def test_mr3_protocol_suffix_invariance(ref, proto):
    net = f"{proto}_CLK"
    suffixed = f"{net}_2"
    base = _zones_of(_mk(ref, [net], {net: "Signal"}))
    ext = _zones_of(_mk(ref, [suffixed], {suffixed: "Signal"}))
    assert base[ref] == "MCU"
    assert ext[ref] == "MCU"
