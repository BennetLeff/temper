"""Property-based + metamorphic tests for the Rust reference-loader kernels.

Wave 4, Phase 3, candidate 5 (plan ``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``,
R1c/R1d). These properties exercise the migrated kernels
(``temper_design_bundle_python.compute_design_stats`` /
``infer_quality_config``, re-exported by ``temper_placer.io.reference_loader``);
parity against the pinned oracle is asserted separately by
``test_reference_loader_rust_differential.py``.

Properties:

- P1. compute_design_stats parity: for any generated netlist, the Rust and
  oracle stats agree bit-identically (floats via ``float.hex()``).
- P2. Empty-input semantics: an empty netlist yields ``n_components=0``,
  ``n_nets=0``, ``n_pins_per_net=0.0``, zero areas, and empty footprint
  types on both arms.
- P3. Component-area accounting: total area equals the sum of per-component
  ``w * h`` (Python arithmetic semantics preserved).
- P4. infer_quality_config parity: for any generated netlist, both arms
  classify the same thermal/HV/LV sets and loops.
- P5. Loop cap: at most 3 loops are inferred, each with >= 2 refs.
- P6. Stats rounding uses CPython round(): a .5-tick average rounds
  half-to-even, identically on both arms.

Metamorphic relations:

- MR1. Component permutation leaves ``n_components``/``n_nets``/footprint
  sets unchanged (set-valued stats are order-independent).
- MR2. Appending an unused component grows ``n_components`` by exactly one
  and leaves ``n_pins_per_net`` unchanged.
- MR3. Area scales additively: doubling one component's bounds doubles its
  contribution to ``component_area_mm2``.
"""

from __future__ import annotations

from types import SimpleNamespace

import temper_design_bundle_python as _tdb

import tests.io._reference_loader_py_oracle as _oracle

COMPUTE_STATS = _tdb.compute_design_stats
INFER_QUALITY = _tdb.infer_quality_config

MAX_EXAMPLES = 60


def _f(v):
    return None if v is None else float(v).hex()


def _stats_key(stats):
    out = []
    for key in sorted(stats.keys()):
        v = stats[key]
        if isinstance(v, float):
            out.append((key, "float", v.hex()))
        elif isinstance(v, int) and not isinstance(v, bool):
            out.append((key, "int", v))
        elif isinstance(v, list):
            out.append((key, "list", tuple(sorted(v))))
        elif isinstance(v, set):
            out.append((key, "set", tuple(sorted(v))))
        else:
            out.append((key, type(v).__name__, v))
    return tuple(out)


def _netlist(components, nets):
    from temper_placer.core.netlist import Netlist

    return Netlist(components=components, nets=nets)


def _parse_result(netlist, board=None, warnings=()):
    return SimpleNamespace(netlist=netlist, board=board, warnings=warnings)


from hypothesis import given, settings
from hypothesis import strategies as st


@st.composite
def netlist_strategy(draw):
    from temper_placer.core.netlist import Component, Net

    n_comps = draw(st.integers(0, 6))
    comps = []
    for i in range(n_comps):
        comps.append(
            Component(
                ref=f"C{i}",
                footprint=draw(st.sampled_from(["R_0805", "Package_SO:SOIC-8", "TO-247-3",
                                                "C_1206", "Package_QFP:QFP-64"])),
                bounds=(draw(st.floats(min_value=0.5, max_value=30.0, allow_nan=False,
                                       allow_infinity=False)),
                        draw(st.floats(min_value=0.5, max_value=30.0, allow_nan=False,
                                       allow_infinity=False))),
            )
        )
    n_nets = draw(st.integers(0, 4))
    nets = []
    for i in range(n_nets):
        pin_count = draw(st.integers(0, 4))
        pins = [(f"C{j % max(n_comps, 1)}", "1") for j in range(pin_count)]
        nets.append(Net(name=f"N{i}", pins=pins, net_class="Signal"))
    return comps, nets


@given(netlist_strategy())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p1_compute_design_stats_parity(comps_nets):
    comps, nets = comps_nets
    result = _parse_result(_netlist(comps, nets), None, [])
    assert _stats_key(COMPUTE_STATS(result)) == _stats_key(_oracle.compute_design_stats(result))


@given(netlist_strategy())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p2_empty_input_semantics(comps_nets):
    comps, nets = comps_nets
    if comps or nets:
        return
    result = _parse_result(_netlist([], []), None, [])
    rs = COMPUTE_STATS(result)
    py = _oracle.compute_design_stats(result)
    assert rs["n_components"] == py["n_components"] == 0
    assert rs["n_nets"] == py["n_nets"] == 0
    assert rs["n_pins_per_net"] == py["n_pins_per_net"] == 0.0
    assert rs["component_area_mm2"] == py["component_area_mm2"] == 0.0
    assert rs["board_area_mm2"] == py["board_area_mm2"] == 0.0
    assert rs["density"] == py["density"] == 0
    assert rs["footprint_types"] == py["footprint_types"] == []


@given(netlist_strategy())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p3_component_area_accounting(comps_nets):
    comps, nets = comps_nets
    result = _parse_result(_netlist(comps, nets), None, [])
    rs = COMPUTE_STATS(result)
    # component_area_mm2 is round(total, 1) — compare within the rounding
    # granularity against the exact Python sum, on both arms.
    py = _oracle.compute_design_stats(result)
    assert rs["component_area_mm2"] == py["component_area_mm2"]
    exact = round(sum(c.bounds[0] * c.bounds[1] for c in comps), 1)
    assert rs["component_area_mm2"] == exact


@given(netlist_strategy())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p4_infer_quality_config_parity(comps_nets):
    comps, nets = comps_nets
    design = SimpleNamespace(netlist=_netlist(comps, nets))
    rs = INFER_QUALITY(design)
    py = _oracle.infer_quality_config(design)
    for key in ("thermal_components", "hv_components", "lv_components"):
        assert set(rs[key]) == set(py[key])
    assert rs["loop_components"] == py["loop_components"]
    assert rs["min_hv_lv_clearance"] == py["min_hv_lv_clearance"] == 4.0
    assert rs["zone_assignments"] == py["zone_assignments"] == {}


@given(netlist_strategy())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p5_loop_cap(comps_nets):
    comps, nets = comps_nets
    design = SimpleNamespace(netlist=_netlist(comps, nets))
    loops = INFER_QUALITY(design)["loop_components"]
    assert len(loops) <= 3
    for loop in loops:
        assert len(loop) >= 2


@given(netlist_strategy())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_p6_rounding_matches_cpython(comps_nets):
    comps, nets = comps_nets
    result = _parse_result(_netlist(comps, nets), None, [])
    rs = COMPUTE_STATS(result)
    py = _oracle.compute_design_stats(result)
    assert rs["n_pins_per_net"] == py["n_pins_per_net"]
    assert rs["board_area_mm2"] == py["board_area_mm2"]
    assert rs["component_area_mm2"] == py["component_area_mm2"]
    assert rs["density"] == py["density"]


@given(netlist_strategy())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr1_component_permutation(comps_nets):
    comps, nets = comps_nets
    if not comps:
        return
    a = _parse_result(_netlist(comps, nets), None, [])
    b = _parse_result(_netlist(list(reversed(comps)), nets), None, [])
    rs_a = COMPUTE_STATS(a)
    rs_b = COMPUTE_STATS(b)
    assert rs_a["n_components"] == rs_b["n_components"]
    assert rs_a["footprint_types"] == rs_b["footprint_types"]
    assert rs_a["component_area_mm2"] == rs_b["component_area_mm2"]


@given(netlist_strategy())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr2_append_unused_component(comps_nets):
    from temper_placer.core.netlist import Component

    comps, nets = comps_nets
    base = _parse_result(_netlist(comps, nets), None, [])
    extra = Component(ref="ZZ_NEW", footprint="R_0805", bounds=(1.0, 1.0))
    grown = _parse_result(_netlist(comps + [extra], nets), None, [])
    rs_base = COMPUTE_STATS(base)
    rs_grown = COMPUTE_STATS(grown)
    assert rs_grown["n_components"] == rs_base["n_components"] + 1
    assert rs_grown["n_nets"] == rs_base["n_nets"]
    assert rs_grown["n_pins_per_net"] == rs_base["n_pins_per_net"]
    assert rs_grown["footprint_types"] == sorted(set(rs_base["footprint_types"] + ["R_0805"]))


@given(netlist_strategy())
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_mr3_area_scales_additively(comps_nets):
    from temper_placer.core.netlist import Component

    comps, nets = comps_nets
    if not comps:
        return
    base = _parse_result(_netlist(comps, nets), None, [])
    doubled = _parse_result(_netlist([Component(
        ref=c.ref, footprint=c.footprint, bounds=(c.bounds[0] * 2, c.bounds[1] * 2)
    ) for c in comps], nets), None, [])
    rs_base = COMPUTE_STATS(base)
    rs_doubled = COMPUTE_STATS(doubled)
    # area quadruples when both dimensions double; each arm rounds to 0.1 mm²,
    # so the honest bound is ±0.2 from the rounding alone — 0.5 keeps headroom
    # without hiding a real change (a dropped doubling would be a 4x gap).
    assert rs_doubled["component_area_mm2"] >= 4 * rs_base["component_area_mm2"] - 0.5
    assert rs_doubled["component_area_mm2"] == _oracle.compute_design_stats(doubled)["component_area_mm2"]


# ---------------------------------------------------------------------------
# R20 suite hardening — discriminator moved from the differential. #850's
# differential-disabled re-run found M9 (the loops[:3] cap) survives the
# suites-only run: `test_p5_loop_cap` only pins the upper bound `<= 3`, and the
# generated netlists never carry GATE_* nets, so the property is vacuous for
# the cap. The differential's exact-count fixture (5 gate nets -> 3 loops) is
# the discriminator; it is deterministic, so it is pinned here. The
# differential keeps its own assertion.
# ---------------------------------------------------------------------------


def test_p5b_loop_cap_exact_count():
    """infer_quality_config takes only the first 3 pins of each qualifying
    gate net (the oracle's ``net.pins[:3]``): a 5-pin GATE net yields a
    3-ref loop. A port that dropped the ``.take(3)`` pin cap emits 5-ref
    loops and fails the exact-content pin (surviving mutant M9)."""
    from temper_placer.core.netlist import Component, Net, Netlist

    comps = [Component(ref=f"C{i}", footprint="R_0805", bounds=(2.0, 1.25)) for i in range(8)]
    nets = [
        Net(name=f"GATE_{i}", pins=[(f"C{j}", "1") for j in range(5)], net_class="Signal")
        for i in range(2)
    ]
    design = SimpleNamespace(netlist=Netlist(components=comps, nets=nets))
    loops = INFER_QUALITY(design)["loop_components"]
    assert loops == [["C0", "C1", "C2"], ["C0", "C1", "C2"]]
    # Non-vacuity: the fixture's gate nets carry 5 pins each, so the 3-ref
    # pin cap is genuinely exercised (a dropped cap would yield 5-ref loops).
    assert all(len(net.pins) == 5 > 3 for net in nets)
