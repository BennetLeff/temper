"""Property-based + metamorphic tests for the loop-extraction compute
(``temper_placer.core.loop_extractor``).

Wave 4 — ``core/loop_extractor.py`` (R11/R12/R13 backend). The extraction
compute migrated to ``temper-rust-router-core::loop_extractor``; the Rust
kernel's bit-parity against this Python reference is pinned by
``test_loop_extractor_rust_differential.py`` (verbatim pre-migration
oracle). This file owns the closed-form/structural INVARIANTS of the
extraction behavior, asserted against the residual Python compute that the
differential proves identical to the Rust kernel — the Rust kernel itself is
not mutation-addressable from Python (it is only reachable through the JSON
bridge), so the vacuity guards mutate the reference implementation a
degenerate kernel would trivially satisfy.

Module-to-property map (G4 — every surface reached by at least one
property):

- ``classify_component``           → P1
- ``detect_half_bridge_topology``  → P2
- ``trace_commutation_loop``       → P3
- ``trace_gate_drive_loop``        → P4
- ``merge_loops``                  → P5
- ``trace_bootstrap_loop``         → P6
- extraction pipeline invariants   → MR1–MR3

Properties P1..P6 (>= 5), each with a ``test_pN_fails_for_<mutant>``
companion proving it is fail-capable. Metamorphic relations MR1–MR3 (>= 3),
each with an exactness claim.

Properties reference the module attribute (``le.<fn>``) rather than a
hoisted import so the monkeypatch mutants rebind the name the property
actually resolves.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import temper_placer.core.loop_extractor as le
from temper_placer.core.loop import Loop, LoopCollection, LoopPriority, LoopType
from temper_placer.core.loop_extractor import ComponentClassification
from temper_placer.core.netlist import Component, Netlist, Pin

# ---------------------------------------------------------------------------
# Netlist builders (constrained to the parity-holding subset, mirroring the
# differential corpus generator).
# ---------------------------------------------------------------------------


def _pin(name: str, net: str) -> Pin:
    return Pin(name, "1", (0.0, 0.0), net)


def _netlist(components: list[Component]) -> Netlist:
    return Netlist(components=components, nets=[])


def _switch(
    ref: str,
    mpn: str,
    footprint: str,
    gate_net: str,
    rail: tuple[str, str],
    sw_node: str,
) -> Component:
    """Build a power switch. ``rail`` is ``(pin_name, net)`` for the DC rail
    (e.g. ('COLLECTOR', 'DC+')); the switch-node pin is the counterpart
    (EMITTER/SOURCE or DRAIN/COLLECTOR)."""
    rail_pin_name, rail_net = rail
    if rail_pin_name in ("COLLECTOR", "DRAIN"):
        sw_pin_name = "EMITTER" if rail_pin_name == "COLLECTOR" else "SOURCE"
    else:
        sw_pin_name = "COLLECTOR" if rail_pin_name == "EMITTER" else "DRAIN"
    return Component(
        ref=ref,
        footprint=footprint,
        bounds=(1.0, 1.0),
        pins=[_pin("GATE", gate_net), _pin(rail_pin_name, rail_net), _pin(sw_pin_name, sw_node)],
        attributes={"MPN": mpn},
    )


def _half_bridge(
    hi_ref: str = "Q1",
    lo_ref: str = "Q2",
    hi_mpn: str = "IKW40N120H3",
    lo_mpn: str = "IRFP250N",
    hi_fp: str = "TO-247",
    lo_fp: str = "TO-220",
    cap_ref: str = "C_BUS1",
    cap_value: str = "470uF",
    with_driver: bool = False,
    with_resistor: bool = False,
    with_boot: bool = False,
) -> Netlist:
    comps = [
        _switch(hi_ref, hi_mpn, hi_fp, "GATE_H", ("COLLECTOR", "DC+"), "SW"),
        _switch(lo_ref, lo_mpn, lo_fp, "GATE_L", ("SOURCE", "DC-"), "SW"),
        Component(
            ref=cap_ref,
            footprint="CP_Radial_D10.0mm",
            bounds=(1.0, 1.0),
            pins=[_pin("1", "DC+"), _pin("2", "DC-")],
            attributes={"value": cap_value},
        ),
    ]
    if with_driver:
        comps.insert(2, Component(
            ref="U1",
            footprint="SOIC-8",
            bounds=(1.0, 1.0),
            pins=[_pin("OUTA", "GATE_H_DRV"), _pin("OUTB", "GATE_L_DRV")],
            attributes={"MPN": "UCC21550"},
        ))
    if with_resistor:
        comps.append(Component(
            ref="RG_H",
            footprint="R_0805",
            bounds=(1.0, 1.0),
            pins=[_pin("1", "GATE_H_DRV"), _pin("2", "GATE_H")],
            attributes={"value": "10R"},
        ))
    if with_boot:
        comps.append(Component(
            ref="C_BOOT",
            footprint="C_0805",
            bounds=(1.0, 1.0),
            pins=[_pin("1", "VCC_BOOT"), _pin("2", "SW")],
            attributes={"value": "1uF"},
        ))
        comps.append(Component(
            ref="D_BOOT",
            footprint="SOD-123",
            bounds=(1.0, 1.0),
            pins=[_pin("A", "VCC_15V"), _pin("K", "VCC_BOOT")],
            attributes={"MPN": "BAT54"},
        ))
    return _netlist(comps)


# ---------------------------------------------------------------------------
# Hypothesis strategies.
# ---------------------------------------------------------------------------

_IGBT_MPNS = ["IKW40N120H3", "IRG4PC50U", "IK75N60"]
_MOSFET_MPNS = ["IRFP250N", "IRFB4110", "IRF840"]
_ALL_MPNS = _IGBT_MPNS + _MOSFET_MPNS
_TO_FPS = ["TO-247", "TO-220", "TO-263"]

_component_spec = st.builds(
    lambda ref, footprint, mpn, value: Component(
        ref=ref,
        footprint=footprint,
        bounds=(1.0, 1.0),
        pins=[_pin("GATE", "N_GATE"), _pin("1", "N1"), _pin("2", "N2")],
        attributes={"MPN": mpn, "value": value},
    ),
    ref=st.sampled_from(
        ["Q1", "Q2", "QH", "QL", "C1", "C_BOOT", "C_BUS", "D1", "D_BOOT", "R1", "RG_H", "U1", "X1"]
    ),
    footprint=st.sampled_from(_TO_FPS + ["R_0805", "C_0805", "SOD-123", "SOIC-8"]),
    mpn=st.sampled_from(_ALL_MPNS + [""]),
    value=st.sampled_from(["470uF", "1uF", "1000uF", "10R", ""]),
)

_half_bridge_spec = st.builds(
    lambda hi_mpn, lo_mpn, hi_fp, lo_fp, cap_value: _half_bridge(
        hi_mpn=hi_mpn, lo_mpn=lo_mpn, hi_fp=hi_fp, lo_fp=lo_fp, cap_value=cap_value
    ),
    hi_mpn=st.sampled_from(_ALL_MPNS),
    lo_mpn=st.sampled_from(_ALL_MPNS),
    hi_fp=st.sampled_from(_TO_FPS),
    lo_fp=st.sampled_from(_TO_FPS),
    cap_value=st.sampled_from(["470uF", "1000uF", "2200uF"]),
)

_loop_name = st.sampled_from(
    ["auto_commutation", "commutation", "auto_gate_drive_Q1",
     "gate_drive_high", "auto_bootstrap", "custom"]
)


def _make_loop(name: str, loop_type: str) -> Loop:
    lt = LoopType(loop_type)
    return Loop(
        name=name,
        loop_type=lt,
        description=f"loop {name}",
        components=["Q1"],
        nets=["N1"],
        priority=LoopPriority.MEDIUM,
        max_area_mm2=100.0,
    )


_loop_collection = st.builds(
    lambda names: LoopCollection(loops=[_make_loop(n, "custom") for n in names]),
    names=st.lists(_loop_name, min_size=0, max_size=5, unique=True),
)


# ---------------------------------------------------------------------------
# P1: classification category is a function of the ref prefix / signal.
# ---------------------------------------------------------------------------


@given(comp=_component_spec)
@settings(max_examples=50, deadline=30000)
def test_p1_classification_categories(comp):
    cls = le.classify_component(comp)
    ref = comp.ref.upper()
    if ref.startswith("C"):
        assert cls.category == "capacitor"
    elif ref.startswith("D"):
        assert cls.category == "diode"
    elif ref.startswith("Q"):
        mpn = comp.attributes.get("MPN", "").upper()
        fp = comp.footprint.upper()
        if any(p in mpn for p in ["IK", "IHW", "IRG", "STGP", "FGA", "IRGP"]):
            assert cls.category == "power_switch"
            assert cls.subcategory == "igbt"
        elif any(p in mpn for p in ["FET", "SI", "IRF", "BSC", "IPP", "STP"]):
            assert cls.category == "power_switch"
            assert cls.subcategory == "mosfet"
        elif any(pkg in fp for pkg in ["TO-247", "TO-220", "TO-263"]):
            assert cls.category == "power_switch"
    assert 0.0 <= cls.confidence <= 1.0


@pytest.fixture
def _patch_classify(monkeypatch):
    """Mutant: every component classifies as 'other'."""

    def _all_other(component):
        return ComponentClassification(ref=component.ref, category="other", confidence=0.0)

    monkeypatch.setattr("temper_placer.core.loop_extractor.classify_component", _all_other)


def test_p1_fails_for_constant_kernel(_patch_classify):
    """A degenerate classifier that always says 'other' breaks P1."""
    comp = Component(
        ref="C1", footprint="C_0805", bounds=(1.0, 1.0),
        pins=[_pin("1", "N1")], attributes={},
    )
    with pytest.raises(AssertionError):
        test_p1_classification_categories.hypothesis.inner_test(comp)


# ---------------------------------------------------------------------------
# P2: half-bridge detection requires >= 2 power switches sharing a net.
# ---------------------------------------------------------------------------


@given(netlist=_half_bridge_spec)
@settings(max_examples=50, deadline=30000)
def test_p2_half_bridge_detection(netlist):
    pair = le.detect_half_bridge_topology(netlist)
    assert pair is not None
    high, low = pair
    assert high.ref in ("Q1", "QH")
    assert low.ref in ("Q2", "QL")
    # High and low share exactly the switch-node net.
    high_nets = {p.net for p in high.pins if p.net}
    low_nets = {p.net for p in low.pins if p.net}
    assert high_nets & low_nets == {"SW"}


def test_p2_fails_for_always_none_detector(monkeypatch):
    """A detector that always returns None breaks P2 (the generated input
    genuinely contains a half bridge)."""
    monkeypatch.setattr(
        "temper_placer.core.loop_extractor.detect_half_bridge_topology",
        lambda _netlist: None,
    )
    netlist = _half_bridge()
    with pytest.raises(AssertionError):
        test_p2_half_bridge_detection.hypothesis.inner_test(netlist)


# ---------------------------------------------------------------------------
# P3: commutation loop structure.
# ---------------------------------------------------------------------------


@given(netlist=_half_bridge_spec)
@settings(max_examples=50, deadline=30000)
def test_p3_commutation_loop_structure(netlist):
    high, low = le.detect_half_bridge_topology(netlist)
    loop = le.trace_commutation_loop(netlist, high, low)
    assert loop is not None
    assert loop.name == "auto_commutation"
    assert loop.loop_type == LoopType.COMMUTATION
    assert loop.priority == LoopPriority.CRITICAL
    assert loop.max_area_mm2 == 500.0
    # Components: [bus_cap, high, low].
    assert loop.components[1:] == [high.ref, low.ref]
    # Nets: [dc_plus, switch_node, dc_minus].
    assert len(loop.nets) == 3


def test_p3_fails_for_always_none_tracer(monkeypatch):
    """A commutation tracer that always returns None breaks P3."""
    monkeypatch.setattr(
        "temper_placer.core.loop_extractor.trace_commutation_loop",
        lambda _netlist, _high, _low: None,
    )
    netlist = _half_bridge()
    with pytest.raises(AssertionError):
        test_p3_commutation_loop_structure.hypothesis.inner_test(netlist)


# ---------------------------------------------------------------------------
# P4: gate-drive loop naming and typing follow the is_high_side flag.
# ---------------------------------------------------------------------------


@given(is_high=st.booleans())
@settings(max_examples=50, deadline=30000)
def test_p4_gate_drive_loop_naming_and_type(is_high):
    netlist = _half_bridge()
    switch = netlist.components[0] if is_high else netlist.components[1]
    loop = le.trace_gate_drive_loop(netlist, switch, None, is_high_side=is_high)
    assert loop is not None
    assert loop.name == f"auto_gate_drive_{switch.ref}"
    if is_high:
        assert loop.loop_type == LoopType.GATE_DRIVE_HIGH
    else:
        assert loop.loop_type == LoopType.GATE_DRIVE_LOW
    assert loop.priority == LoopPriority.CRITICAL
    assert loop.max_area_mm2 == 100.0


def test_p4_fails_for_swapped_loop_type(monkeypatch):
    """A tracer that always swaps high/low breaks P4 on the high side."""
    orig = le.trace_gate_drive_loop

    def _swapped(netlist, switch, driver, is_high_side):
        return orig(netlist, switch, driver, not is_high_side)

    monkeypatch.setattr("temper_placer.core.loop_extractor.trace_gate_drive_loop", _swapped)
    with pytest.raises(AssertionError):
        test_p4_gate_drive_loop_naming_and_type.hypothesis.inner_test(True)


# ---------------------------------------------------------------------------
# P5: merge_loops manual-override precedence.
# ---------------------------------------------------------------------------


@given(auto=_loop_collection, manual=_loop_collection)
@settings(max_examples=50, deadline=30000)
def test_p5_merge_manual_precedence(auto, manual):
    merged = le.merge_loops(auto, manual)
    merged_names = [loop.name for loop in merged.loops]
    manual_names = {loop.name for loop in manual.loops}
    manual_base = {n.replace("auto_", "") for n in manual_names}
    # Expected set: every manual loop, plus every auto loop without a
    # manual override (exact-name match or base-name match).
    expected = set(manual_names)
    for loop in auto.loops:
        base = loop.name.replace("auto_", "")
        if loop.name in manual_names or base in manual_base:
            continue  # overridden by a manual loop
        expected.add(loop.name)
    assert set(merged_names) == expected
    assert len(merged_names) == len(set(merged_names))  # no duplicates


def test_p5_fails_for_no_dedup_merger(monkeypatch):
    """A merger that appends every auto loop without checking overrides
    breaks P5 when an auto loop is overridden by a manual one."""
    def _no_dedup(auto, manual):
        return LoopCollection(loops=list(manual.loops) + list(auto.loops))

    monkeypatch.setattr("temper_placer.core.loop_extractor.merge_loops", _no_dedup)
    auto = LoopCollection(loops=[_make_loop("auto_commutation", "commutation")])
    manual = LoopCollection(loops=[_make_loop("commutation", "commutation")])
    with pytest.raises(AssertionError):
        test_p5_merge_manual_precedence.hypothesis.inner_test(auto, manual)


# ---------------------------------------------------------------------------
# P6: bootstrap loop requires a BOOT capacitor; components order.
# ---------------------------------------------------------------------------


@given(with_boot=st.booleans())
@settings(max_examples=50, deadline=30000)
def test_p6_bootstrap_loop_presence(with_boot):
    netlist = _half_bridge(with_driver=True, with_boot=with_boot)
    driver = netlist.components[2]
    loop = le.trace_bootstrap_loop(netlist, driver)
    if with_boot:
        assert loop is not None
        assert loop.name == "auto_bootstrap"
        assert loop.loop_type == LoopType.BOOTSTRAP
        assert loop.priority == LoopPriority.HIGH
        assert loop.components == ["D_BOOT", "C_BOOT"]
        assert loop.max_area_mm2 == 50.0
    else:
        assert loop is None


def test_p6_fails_for_always_bootstrap_tracer(monkeypatch):
    """A tracer that fabricates a bootstrap loop breaks P6 on a netlist with
    no bootstrap circuit."""
    netlist = _half_bridge(with_driver=True, with_boot=False)
    driver = netlist.components[2]
    assert le.trace_bootstrap_loop(netlist, driver) is None  # sanity
    monkeypatch.setattr(
        "temper_placer.core.loop_extractor.trace_bootstrap_loop",
        lambda _netlist, _driver: _make_loop("auto_bootstrap", "bootstrap"),
    )
    with pytest.raises(AssertionError):
        test_p6_bootstrap_loop_presence.hypothesis.inner_test(False)


# ---------------------------------------------------------------------------
# Sanity: the input classes genuinely discriminate (anti-vacuity).
# ---------------------------------------------------------------------------


def test_input_classes_discriminate():
    """Each generated input class can be classified both ways by the
    reference — a constant answer would violate one branch."""
    assert le.classify_component(
        _switch("Q1", "IKW40N120H3", "TO-247", "G", ("COLLECTOR", "D"), "S")
    ).category == "power_switch"
    assert le.classify_component(
        Component(ref="X1", footprint="X", bounds=(1.0, 1.0), pins=[], attributes={})
    ).category == "other"
    assert le.detect_half_bridge_topology(_half_bridge()) is not None
    assert le.detect_half_bridge_topology(
        _netlist([_switch("Q1", "IKW40N120H3", "TO-247", "G", ("COLLECTOR", "D"), "S")])
    ) is None
    boot = _half_bridge(with_driver=True, with_boot=True)
    assert le.trace_bootstrap_loop(boot, boot.components[2]) is not None


# ---------------------------------------------------------------------------
# MR1: net-rename invariance (exact).
# ---------------------------------------------------------------------------


def _renamed(netlist: Netlist, prefix: str) -> Netlist:
    """Bijective prefix rename of every net."""
    comps = []
    for comp in netlist.components:
        comps.append(Component(
            ref=comp.ref,
            footprint=comp.footprint,
            bounds=comp.bounds,
            pins=[Pin(p.name, p.number, p.position, prefix + p.net) for p in comp.pins],
            attributes=dict(comp.attributes),
        ))
    return _netlist(comps)


@given(netlist=_half_bridge_spec)
@settings(max_examples=30, deadline=30000)
def test_mr1_net_rename_invariance(netlist):
    """Renaming every net by a constant prefix preserves loop identity:
    same name/type/components/max_area, nets renamed in lockstep. Exact —
    string substitution preserves every comparison."""
    renamed = _renamed(netlist, "X_")
    hi, lo = le.detect_half_bridge_topology(netlist)
    loop = le.trace_commutation_loop(netlist, hi, lo)
    rhi, rlo = le.detect_half_bridge_topology(renamed)
    rloop = le.trace_commutation_loop(renamed, rhi, rlo)
    assert rloop is not None and loop is not None
    assert rloop.name == loop.name
    assert rloop.loop_type == loop.loop_type
    assert list(rloop.components) == list(loop.components)
    assert rloop.max_area_mm2 == loop.max_area_mm2
    assert list(rloop.nets) == ["X_" + n for n in loop.nets]


# ---------------------------------------------------------------------------
# MR2: unrelated-component insertion invariance (exact).
# ---------------------------------------------------------------------------


@given(netlist=_half_bridge_spec)
@settings(max_examples=30, deadline=30000)
def test_mr2_unrelated_insertion_invariance(netlist):
    """Inserting a decoupling cap and a resistor on nets that touch nothing
    in the extraction leaves every loop bit-identical — the 'first match'
    searches are unaffected because the new components do not touch DC+,
    DC-, SW, or any gate net."""
    extra = [
        Component(ref="C_DEC", footprint="C_0805", bounds=(1.0, 1.0),
                  pins=[_pin("1", "AUX"), _pin("2", "AUX2")], attributes={"value": "100nF"}),
        Component(ref="R_SENSE", footprint="R_0805", bounds=(1.0, 1.0),
                  pins=[_pin("1", "AUX3"), _pin("2", "AUX4")], attributes={"value": "1R"}),
    ]
    augmented = _netlist(list(netlist.components) + extra)

    hi, lo = le.detect_half_bridge_topology(netlist)
    ahi, alo = le.detect_half_bridge_topology(augmented)
    loop = le.trace_commutation_loop(netlist, hi, lo)
    aloop = le.trace_commutation_loop(augmented, ahi, alo)
    assert aloop is not None and loop is not None
    assert list(aloop.components) == list(loop.components)
    assert list(aloop.nets) == list(loop.nets)
    assert aloop.max_area_mm2 == loop.max_area_mm2


# ---------------------------------------------------------------------------
# MR3: bus-capacitor ref/value invariance (exact modulo the renamed ref).
# ---------------------------------------------------------------------------


def test_mr3_bus_cap_ref_value_invariance():
    """Renaming the bus cap (C_BUS1 -> C_DC) and changing its value
    (470uF -> 2200uF) leaves the loop structure identical except the
    renamed ref — extraction keys on the ref prefix 'C', not the value."""
    base = _half_bridge(cap_ref="C_BUS1", cap_value="470uF")
    variant = _half_bridge(cap_ref="C_DC", cap_value="2200uF")

    hi, lo = le.detect_half_bridge_topology(base)
    loop = le.trace_commutation_loop(base, hi, lo)
    vhi, vlo = le.detect_half_bridge_topology(variant)
    vloop = le.trace_commutation_loop(variant, vhi, vlo)
    assert loop is not None and vloop is not None
    assert vloop.name == loop.name
    assert vloop.loop_type == loop.loop_type
    assert list(vloop.components) == ["C_DC", "Q1", "Q2"]
    assert list(vloop.nets) == list(loop.nets)
    assert vloop.max_area_mm2 == loop.max_area_mm2
