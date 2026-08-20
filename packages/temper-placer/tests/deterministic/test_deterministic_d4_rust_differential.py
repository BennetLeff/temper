"""R1a: behavioural differential of the D4 deterministic assignment stages
against the pinned pre-migration oracle.

Rust Orchestration Engine plan 2026-08-09-001, Phase D batch D4: the
orchestration of ``deterministic/stages/component_assignment.py`` (the
``ComponentAssignmentStage`` run: state guards, ``_domain_lookups``, the
GEOS domain filter precomputed into the per-ref ``domain_ok`` set, the
sheetpath-first/ref-fallback fixed-placement resolution, the greedy-kernel
call and the ``frozenset(placements.items())`` write) moves to
``temper-orchestration`` as a ``Stage<BoardState>`` implementor
(``ComponentAssignmentStage``, component_assignment_stage.rs); the DRC
fence validator of ``phased_component_assignment_validator.py`` (the
creepage-coverage and non-over-claim loops: ``_creepage_mm`` /
``_absolute_hv_pins`` extraction, the fallback ``used_slots`` recompute,
the legitimate-origin set and the two failure scans) moves to a Rust kernel
(``run_phased_validator_hv``, phased_component_assignment_validator_stage.rs)
that returns raw ``(field, slot, reason)`` failure triples; the
router_v6-bound ``StageDRCFailure`` construction stays in the Python shim.
The pre-migration implementations are pinned VERBATIM as the oracles
(``tests/deterministic/_component_assignment_py_oracle.py`` and
``_phased_component_assignment_validator_py_oracle.py``, content-hash-pinned
below).

Both arms are driven with IDENTICAL BoardState inputs and stage constructor
args; every observable output is compared bit-exactly:

- ``ComponentAssignmentStage`` -> ``state.placements`` (frozenset of
  ``(ref, (x, y))``), projected through ``float.hex()`` (the frozenset is
  order-free -- the ordering semantics are pinned through content: which
  component won the best slot). The identity guards are pinned on BOTH arms
  as returning the ORIGINAL state object.
- ``validate_phased_component_assignment_hv`` -> the ``StageDRCFailure``
  list, projected to ``(field, value.hex, reason)`` IN ORDER -- coverage
  failures first (pin order, then slot order), then over-claim failures (in
  ``used_slots`` set-iteration order, reproduced identically by the Rust
  port building the same Python ``set``). The reason strings (f-strings over
  the original slot/creepage/pin objects) are compared byte-for-byte.

Anti-vacuity: ``test_oracle_and_port_are_different_implementations`` asserts
the shims resolve to the Rust pyfunctions (their ``run`` / validator bodies
call ``temper_orchestration``), not back onto the oracle. The oracle body
digests below are pinned: a differential whose oracle can be edited to agree
with the port proves nothing.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import temper_orchestration as _to
import tests.deterministic._component_assignment_py_oracle as _orc_component_assignment
import tests.deterministic._phased_component_assignment_validator_py_oracle as _orc_validator
from temper_placer.core.design_rules import DesignRules, NetClassRules
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.stages import component_assignment as _shim_component_assignment
from temper_placer.deterministic.stages import (
    phased_component_assignment_validator as _shim_validator,
)
from temper_placer.deterministic.state import BoardState

# ---------------------------------------------------------------------------
# Oracle body pinning (G1)
# ---------------------------------------------------------------------------

_PINNED = {
    "_component_assignment_py_oracle.py": "787160a49b97cac09ad1bc6798460176bc34f7bcc4f60ee302903f9801af2b51",
    "_phased_component_assignment_validator_py_oracle.py": "e55337be4835ad1a8c7d4299ec9996efa173546744fea32558e9bdb4208cf81e",
}
_BODY_MARKER = "# --- BEGIN PINNED BODY ---\n"


def test_oracle_bodies_match_pinned_digests() -> None:
    for name, expected in _PINNED.items():
        text = (Path(__file__).with_name(name)).read_text(encoding="utf-8")
        assert _BODY_MARKER in text, f"{name} oracle header marker missing"
        body = text.split(_BODY_MARKER, 1)[1]
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert digest == expected, (
            f"{name} oracle body changed; it must stay verbatim "
            f"(expected {expected}, got {digest})"
        )


def test_oracle_and_port_are_different_implementations() -> None:
    """Anti-vacuity: the shims must delegate to the Rust pyfunctions."""
    assert (
        _shim_component_assignment.ComponentAssignmentStage
        is not _orc_component_assignment.ComponentAssignmentStage
    )
    assert (
        _shim_validator.validate_phased_component_assignment_hv
        is not _orc_validator.validate_phased_component_assignment_hv
    )
    # The shim run()/validator bodies call the temper_orchestration
    # pyfunctions -- the Rust port -- by bytecode name.
    assert "run_component_assignment" in (
        _shim_component_assignment.ComponentAssignmentStage.run.__code__.co_names
    )
    assert "run_phased_validator_hv" in (
        _shim_validator.validate_phased_component_assignment_hv.__code__.co_names
    )


# ---------------------------------------------------------------------------
# Bit-exact comparison canon
# ---------------------------------------------------------------------------

def _placement_canon(placements) -> tuple:
    """Frozenset of (ref, (x, y)) placements -> sorted (ref, hex, hex) tuples.
    The frozenset is order-free; the canon pins value bit-exactness."""
    return tuple(
        sorted((ref, (x.hex(), y.hex())) for ref, (x, y) in placements)
    )


def _failure_canon(failures) -> tuple:
    """Project StageDRCFailure lists onto (field, value.hex, reason) IN ORDER,
    with the slot value carried bit-exactly."""
    out = []
    for f in failures:
        x, y = f.value
        out.append((f.field, (x.hex(), y.hex()), f.reason))
    return tuple(out)


# ---------------------------------------------------------------------------
# Corpus builders -- ComponentAssignmentStage
# ---------------------------------------------------------------------------

def _pin(number="1", net="NET", position=(0.0, 0.0)):
    return Pin(name=number, number=number, position=position, net=net)


def _component(ref, bounds=(4.0, 2.0), pins=None, sheetpath=None):
    return Component(
        ref=ref, footprint="FP", bounds=bounds,
        pins=pins or [_pin()], sheetpath=sheetpath,
    )


def _netlist(*components, nets=None):
    if nets is None:
        nets = []
    return Netlist(components=list(components), nets=list(nets))


def _slot_state(
    *components,
    zone_map=None,
    zone_slots=None,
    domain_map=None,
    domain_regions=None,
    placements=None,
):
    """A BoardState with a netlist plus (optionally) the D4 stage's slot-map
    fields. ``zone_slots`` is a frozenset of (zone, tuple_of_slots) pairs --
    exactly what SlotGenerationStage writes and what the stage's
    ``dict(state.zone_slots)`` consumes."""
    if zone_map is None:
        zone_map = frozenset((c.ref, "Signal") for c in components)
    if zone_slots is None:
        zone_slots = frozenset(
            {("Signal", ((0.0, 0.0), (5.0, 5.0), (10.0, 10.0), (15.0, 15.0)))}
        )
    return BoardState(
        netlist=_netlist(*components),
        component_zone_map=zone_map,
        zone_slots=zone_slots,
        component_domain_map=domain_map or frozenset(),
        domain_regions=domain_regions or (),
        placements=placements or frozenset(),
    )


def _run_both_ca(kwargs, state):
    """Run the oracle and the port ComponentAssignmentStage with identical
    constructor args; return (oracle_state, port_state)."""
    orc = _orc_component_assignment.ComponentAssignmentStage(**kwargs).run(state)
    port = _shim_component_assignment.ComponentAssignmentStage(**kwargs).run(state)
    return orc, port


# ---------------------------------------------------------------------------
# ComponentAssignmentStage -- guards and trivial paths
# ---------------------------------------------------------------------------

def test_no_netlist_guard_identity() -> None:
    state = BoardState()
    orc = _orc_component_assignment.ComponentAssignmentStage().run(state)
    port = _shim_component_assignment.ComponentAssignmentStage().run(state)
    assert orc is state
    assert port is state
    assert orc.placements == frozenset() and port.placements == frozenset()


def test_empty_zone_slots_guard_identity() -> None:
    """Netlist present but zone_slots empty -> the guard returns state."""
    state = _slot_state(_component("R1"), zone_slots=frozenset())
    orc = _orc_component_assignment.ComponentAssignmentStage().run(state)
    port = _shim_component_assignment.ComponentAssignmentStage().run(state)
    assert orc is state
    assert port is state


def test_empty_component_zone_map_guard_identity() -> None:
    state = _slot_state(_component("R1"), zone_map=frozenset())
    orc = _orc_component_assignment.ComponentAssignmentStage().run(state)
    port = _shim_component_assignment.ComponentAssignmentStage().run(state)
    assert orc is state
    assert port is state


# ---------------------------------------------------------------------------
# ComponentAssignmentStage -- greedy assignment
# ---------------------------------------------------------------------------

def test_basic_assignment_placements_bit_exact() -> None:
    comps = [
        _component("R1", bounds=(4.0, 2.0), pins=[_pin(net="N1")]),
        _component("R2", bounds=(4.0, 2.0), pins=[_pin("2", net="N1")]),
        _component("C1", bounds=(2.0, 1.0)),
    ]
    nl = _netlist(*comps, nets=[Net("N1", [("R1", "1"), ("R2", "2")], net_class="Signal")])
    state = BoardState(
        netlist=nl,
        component_zone_map=frozenset((c.ref, "Signal") for c in comps),
        zone_slots=frozenset(
            {("Signal", ((0.0, 0.0), (5.0, 5.0), (10.0, 10.0), (15.0, 15.0)))}
        ),
    )
    orc, port = _run_both_ca({}, state)
    assert _placement_canon(port.placements) == _placement_canon(orc.placements)
    assert len(port.placements) == 3


def test_largest_first_order_pinned() -> None:
    """Larger footprints place first (blocking radius); the content pins who
    got the best slot."""
    comps = [
        _component("SMALL", bounds=(1.0, 1.0)),
        _component("BIG", bounds=(10.0, 8.0)),
        _component("MED", bounds=(4.0, 4.0)),
    ]
    state = BoardState(
        netlist=_netlist(*comps),
        component_zone_map=frozenset((c.ref, "Signal") for c in comps),
        zone_slots=frozenset(
            {("Signal", ((0.0, 0.0), (5.0, 5.0), (10.0, 10.0)))}
        ),
    )
    orc, port = _run_both_ca({}, state)
    assert _placement_canon(port.placements) == _placement_canon(orc.placements)
    # ``get_size`` is the larger bound dimension, so the sort key (-size, ref)
    # puts BIG first: it grabs (0,0), its footprint radius (~7.4) takes
    # (5,5) too, MED lands on the last free slot and SMALL is starved. A
    # wrong sort order would hand BIG a worse slot or place SMALL.
    assert dict(port.placements)["BIG"] == (0.0, 0.0)
    assert dict(port.placements)["MED"] == (10.0, 10.0)
    assert "SMALL" not in dict(port.placements)


def test_fixed_placements_dict_and_list_forms() -> None:
    """Fixed placements resolve from both the dict (``{"position": [...]}``)
    and the bare list/tuple form; the fixed entries lead the dict order."""
    comps = [
        _component("R1", bounds=(4.0, 2.0)),
        _component("R2", bounds=(4.0, 2.0)),
    ]
    state = _slot_state(
        *comps,
        zone_slots=frozenset({("Signal", ((0.0, 0.0), (5.0, 5.0), (10.0, 10.0)))}),
    )
    fixed = {"R1": {"position": (2.0, 2.0)}, "R2": (8.0, 8.0)}
    orc, port = _run_both_ca({"fixed_placements": fixed}, state)
    assert _placement_canon(port.placements) == _placement_canon(orc.placements)
    assert dict(port.placements)["R1"] == (2.0, 2.0)
    assert dict(port.placements)["R2"] == (8.0, 8.0)


def test_fixed_placements_sheetpath_first() -> None:
    """A fixed key that matches BOTH a sheetpath and a ref resolves to the
    sheetpath component (``comp_by_sheetpath.get(key) or comp_by_ref.get(key)``)."""
    comps = [
        _component("U1", bounds=(4.0, 2.0), sheetpath="/main/u1"),
        _component("U2", bounds=(4.0, 2.0)),
    ]
    state = _slot_state(
        *comps,
        zone_slots=frozenset({("Signal", ((0.0, 0.0), (5.0, 5.0), (10.0, 10.0)))}),
    )
    # The sheetpath key resolves U1; a bare ref key resolves U2.
    fixed = {"/main/u1": (2.0, 2.0), "U2": (8.0, 8.0)}
    orc, port = _run_both_ca({"fixed_placements": fixed}, state)
    assert _placement_canon(port.placements) == _placement_canon(orc.placements)
    assert dict(port.placements)["U1"] == (2.0, 2.0)
    assert dict(port.placements)["U2"] == (8.0, 8.0)


def test_fixed_placements_unknown_key_ignored() -> None:
    """A fixed key matching no component (sheetpath or ref) is skipped."""
    comps = [_component("R1", bounds=(4.0, 2.0))]
    state = _slot_state(
        *comps,
        zone_slots=frozenset({("Signal", ((0.0, 0.0), (5.0, 5.0)))}),
    )
    fixed = {"NO_SUCH_COMP": (0.0, 0.0), "R1": (5.0, 5.0)}
    orc, port = _run_both_ca({"fixed_placements": fixed}, state)
    assert _placement_canon(port.placements) == _placement_canon(orc.placements)
    assert dict(port.placements)["R1"] == (5.0, 5.0)


def test_cross_zone_fallback() -> None:
    """When a zone's slots are exhausted, the kernel falls back to other
    zones -- the fallback scans the zone dict in insertion order."""
    comps = [_component("A"), _component("B"), _component("C")]
    state = BoardState(
        netlist=_netlist(*comps),
        component_zone_map=frozenset((c.ref, "HV") for c in comps),
        zone_slots=frozenset(
            {
                ("HV", ((0.0, 0.0),)),
                ("Signal", ((5.0, 5.0), (10.0, 10.0))),
            }
        ),
    )
    orc, port = _run_both_ca({}, state)
    assert _placement_canon(port.placements) == _placement_canon(orc.placements)


# ---------------------------------------------------------------------------
# ComponentAssignmentStage -- domain filter (shapely/GEOS stays Python, the
# precomputed predicate and the kernel call move to Rust)
# ---------------------------------------------------------------------------

def _domain_state(*comps, region_polys, domain_for, slots_by_zone, zones=None):
    """A state carrying the HvLvPartitionStage outputs: the per-ref domain
    map (frozenset of (ref, domain)), the corridor polygons tuple and the
    per-ref zone map."""
    if zones is None:
        zones = {c.ref: "HV" for c in comps}
    return BoardState(
        netlist=_netlist(*comps),
        component_zone_map=frozenset(zones.items()),
        zone_slots=frozenset(slots_by_zone.items()),
        component_domain_map=frozenset(domain_for.items()),
        domain_regions=tuple(region_polys),
    )


def test_domain_filter_confinement() -> None:
    """The domain filter drops slots outside the component's region; the
    port's precomputed ``domain_ok`` reproduces the GEOS ``covers`` filter
    exactly."""
    from shapely.geometry import Polygon

    comps = [_component("HV1"), _component("HV2"), _component("LV1")]
    hv_region = Polygon([(0, -10), (6, -10), (6, 70), (0, 70)])
    lv_region = Polygon([(49, -10), (70, -10), (70, 70), (49, 70)])
    state = _domain_state(
        *comps,
        region_polys=[hv_region, lv_region],
        domain_for={"HV1": "HV_edge", "HV2": "HV_edge", "LV1": "LV_interior"},
        zones={"HV1": "HV", "HV2": "HV", "LV1": "LV"},
        slots_by_zone={
            "HV": ((0.0, 0.0), (5.0, 5.0), (10.0, 10.0)),
            "LV": ((50.0, 50.0), (55.0, 55.0), (60.0, 60.0)),
        },
    )
    orc, port = _run_both_ca({}, state)
    assert _placement_canon(port.placements) == _placement_canon(orc.placements)
    # HV_edge covers x <= 6 -> (0,0),(5,5); the (10,10) HV slot is filtered
    # out. LV_interior covers x >= 49 -> all three LV slots survive.
    assert dict(port.placements)["HV1"] == (0.0, 0.0)
    assert dict(port.placements)["HV2"] == (5.0, 5.0)
    assert dict(port.placements)["LV1"] == (50.0, 50.0)


def test_domain_filter_empty_covered_set_unfiltered() -> None:
    """A component whose region covers NO slot in its zone gets no
    ``domain_ok`` entry and is therefore left UNFILTERED (the migrated
    kernel's empty-covered semantics, pinned by the Phase-5 differential) --
    not silently skipped. Both arms agree."""
    from shapely.geometry import Polygon

    comps = [_component("HV1"), _component("LV1")]
    far_region = Polygon([(1000, 1000), (1006, 1000), (1006, 1060), (1000, 1060)])
    state = _domain_state(
        *comps,
        region_polys=[far_region],
        domain_for={"HV1": "LV_interior", "LV1": "LV_interior"},
        zones={"HV1": "HV", "LV1": "LV"},
        slots_by_zone={"HV": ((0.0, 0.0), (5.0, 5.0)), "LV": ((50.0, 50.0), (55.0, 55.0))},
    )
    orc, port = _run_both_ca({}, state)
    assert _placement_canon(port.placements) == _placement_canon(orc.placements)
    # HV1: region covers nothing in the HV zone -> no domain_ok entry ->
    # placed at the first HV slot. LV1: same -> first LV slot.
    assert dict(port.placements) == {"HV1": (0.0, 0.0), "LV1": (50.0, 50.0)}


def test_domain_filter_noop_when_partition_disabled() -> None:
    """Empty component_domain_map / domain_regions -> the filter is a no-op
    (NFR6 backward compat)."""
    comps = [_component("A", bounds=(4.0, 2.0)), _component("B", bounds=(4.0, 2.0))]
    state = _slot_state(
        *comps,
        zone_slots=frozenset({("Signal", ((0.0, 0.0), (5.0, 5.0)))}),
    )
    orc, port = _run_both_ca({}, state)
    assert _placement_canon(port.placements) == _placement_canon(orc.placements)
    assert len(port.placements) == 2


def test_boundary_slot_kept_by_covers() -> None:
    """``region.covers(Point)`` keeps boundary points (``contains`` would
    drop a slot sitting exactly on the corridor edge) -- pinned on both arms
    by ordering the boundary slot FIRST, so a ``contains``-semantics mutation
    would hand the component the second slot instead."""
    from shapely.geometry import Polygon

    comps = [_component("HV1")]
    # The slot (6.0, 5.0) sits exactly on the x=6 corridor edge and leads
    # the slot order.
    edge_region = Polygon([(0, -10), (6, -10), (6, 70), (0, 70)])
    state = _domain_state(
        *comps,
        region_polys=[edge_region],
        domain_for={"HV1": "HV_edge"},
        zones={"HV1": "HV"},
        slots_by_zone={"HV": ((6.0, 5.0), (0.0, 0.0), (10.0, 10.0))},
    )
    orc, port = _run_both_ca({}, state)
    assert _placement_canon(port.placements) == _placement_canon(orc.placements)
    assert dict(port.placements)["HV1"] == (6.0, 5.0)


# ---------------------------------------------------------------------------
# Validator corpus builders
# ---------------------------------------------------------------------------

def _hv_netlist():
    """The canonical 1-HV + 1-LV netlist from test_phased_component_assignment_validator.py."""
    q1 = Component(
        ref="Q1",
        footprint="TO247",
        bounds=(10.0, 10.0),
        initial_position=(0.0, 0.0),
        pins=[
            Pin(name="1", number="1", position=(0.0, 0.0), net="DC_BUS+"),
            Pin(name="2", number="2", position=(5.0, 0.0), net="DC_BUS+"),
        ],
    )
    c1 = Component(
        ref="C1",
        footprint="0603",
        bounds=(2.0, 2.0),
        initial_position=(30.0, 30.0),
        pins=[Pin(name="1", number="1", position=(0.0, 0.0), net="VCC")],
    )
    return Netlist(
        components=[q1, c1],
        nets=[
            Net(name="DC_BUS+", pins=[("Q1", "1"), ("Q1", "2")], net_class="HighVoltage"),
            Net(name="VCC", pins=[("C1", "1")], net_class="Power"),
        ],
    )


def _hv_design_rules(creepage_mm=6.0) -> DesignRules:
    return DesignRules(
        net_classes={
            "HighVoltage": NetClassRules(
                name="HighVoltage", trace_width=0.5, clearance=2.0,
                dru_priority=10, creepage_mm=creepage_mm, safety_category="HV",
            ),
            "Power": NetClassRules(
                name="Power", trace_width=0.25, clearance=0.2,
                dru_priority=20, safety_category="LV",
            ),
        },
        net_class_assignments={"DC_BUS+": "HighVoltage", "VCC": "Power"},
    )


def _slot_grid(spacing=5.0, extent=100):
    slots = tuple(
        (float(x), float(y))
        for x in range(0, extent, int(spacing))
        for y in range(0, extent, int(spacing))
    )
    return slots


def _validator_state(
    netlist=None,
    rules=None,
    placements=None,
    used_slots=None,
    zone_slots=None,
):
    slots = zone_slots if zone_slots is not None else _slot_grid()
    return BoardState(
        netlist=netlist or _hv_netlist(),
        design_rules=rules if rules is not None else _hv_design_rules(),
        component_zone_map=frozenset(
            (c.ref, "Signal") for c in (netlist or _hv_netlist()).components
        ),
        zone_slots=frozenset({("Signal", slots)}),
        placements=placements or frozenset(),
        used_slots=used_slots or frozenset(),
    )


def _run_both_validator(state):
    """Run both validator arms and return the (oracle, port) failure lists."""
    orc = _orc_validator.validate_phased_component_assignment_hv(state)
    port = _shim_validator.validate_phased_component_assignment_hv(state)
    return orc, port


def _assert_validator_equal(state):
    orc, port = _run_both_validator(state)
    assert _failure_canon(orc) == _failure_canon(port), (
        f"oracle={orc}\nport={port}"
    )
    return orc, port


# ---------------------------------------------------------------------------
# Validator -- degenerate paths
# ---------------------------------------------------------------------------

def test_validator_no_netlist_no_failures() -> None:
    state = _validator_state(netlist=None)
    orc, port = _assert_validator_equal(state)
    assert orc == port == []


def test_validator_zero_creepage_no_failures() -> None:
    state = _validator_state(rules=_hv_design_rules(creepage_mm=0.0))
    orc, port = _assert_validator_equal(state)
    assert orc == port == []


def test_validator_saturation_creepage_no_failures() -> None:
    """creepage >= the slot-grid diagonal saturates coverage; both arms
    short-circuit to an empty failure list."""
    state = _validator_state(rules=_hv_design_rules(creepage_mm=10_000.0))
    orc, port = _assert_validator_equal(state)
    assert orc == port == []


def test_validator_empty_zone_slots_no_failures() -> None:
    state = _validator_state(zone_slots=())
    orc, port = _assert_validator_equal(state)
    assert orc == port == []


# ---------------------------------------------------------------------------
# Validator -- clean board / fallback recompute path
# ---------------------------------------------------------------------------

def test_validator_fallback_recompute_clean_board() -> None:
    """No ``used_slots`` on the state -> the validator recomputes it from
    placements (footprint + HV rings); a board whose used_slots ARE the
    legitimate rings yields zero failures on both arms."""
    netlist = _hv_netlist()
    placements = frozenset({("Q1", (0.0, 0.0)), ("C1", (30.0, 30.0))})
    state = _validator_state(netlist=netlist, placements=placements)
    orc, port = _assert_validator_equal(state)
    assert orc == port == []


def test_validator_used_slots_attr_precedence() -> None:
    """When ``used_slots`` is non-empty it is used DIRECTLY (not recomputed);
    a used_slots missing the HV pin's creepage ring flags the gap."""
    netlist = _hv_netlist()
    placements = frozenset({("Q1", (0.0, 0.0)), ("C1", (30.0, 30.0))})
    state = _validator_state(netlist=netlist, placements=placements)
    # Recompute the FULL legitimate used_slots via the same kernels the
    # validator uses, then delete one slot inside the Q1.1 creepage ring
    # (Q1.1 sits at (0,0); (0,5) is at distance 5 <= 6).
    spacing = 5.0
    all_slots = _slot_grid()
    import temper_design_bundle_python as _tdb

    _rs = _tdb.deterministic_leaves
    idx = _rs.build_slot_index_py(all_slots, spacing)
    legit = set(_rs.slots_within_radius_py((0.0, 0.0), 6.0, idx, spacing))
    missing = (0.0, 5.0)
    assert missing in legit
    legit.discard(missing)
    state = replace(state, used_slots=frozenset(legit))
    orc, port = _assert_validator_equal(state)
    coverage = [f for f in port if "hv_creepage_unblocked" in f.field]
    assert coverage, f"expected a coverage failure, got {port}"
    # The missing slot is exactly the reported one.
    assert any(f.value == missing for f in coverage)
    # The reason for the (0,5) gap pins the creepage value, the absolute pin
    # position and the pin name (Q1.1 sits at placed (0,0) + relative (0,0)).
    gap = next(f for f in coverage if f.value == missing)
    assert "6.0" in gap.reason
    assert "at (0.0,0.0)" in gap.reason
    assert "Q1.1" in gap.reason


def test_validator_overclaim_failure() -> None:
    """A used slot outside every footprint/HV ring is an over-claim."""
    netlist = _hv_netlist()
    placements = frozenset({("Q1", (0.0, 0.0)), ("C1", (30.0, 30.0))})
    state = _validator_state(netlist=netlist, placements=placements)
    far = (95.0, 95.0)
    state = replace(state, used_slots=frozenset({far}))
    orc, port = _assert_validator_equal(state)
    overclaim = [f for f in port if f.field == "used_slot_overclaim"]
    assert overclaim, f"expected an over-claim failure, got {port}"
    assert overclaim[0].value == far
    assert "used_slots but is not within" in overclaim[0].reason


def test_validator_coverage_and_overclaim_order() -> None:
    """Coverage failures (pin order, then slot order) precede over-claim
    failures (used_slots set order); the combined list matches the oracle
    entry-for-entry."""
    netlist = _hv_netlist()
    placements = frozenset({("Q1", (0.0, 0.0)), ("C1", (30.0, 30.0))})
    state = _validator_state(netlist=netlist, placements=placements)
    # Tamper: drop two ring slots AND add a phantom far slot.
    import temper_design_bundle_python as _tdb

    _rs = _tdb.deterministic_leaves
    spacing = 5.0
    idx = _rs.build_slot_index_py(_slot_grid(), spacing)
    ring = set(_rs.slots_within_radius_py((0.0, 0.0), 6.0, idx, spacing))
    ring.discard((0.0, 5.0))
    ring.discard((5.0, 0.0))
    ring.add((95.0, 95.0))
    state = replace(state, used_slots=frozenset(ring))
    orc, port = _assert_validator_equal(state)
    assert len(port) >= 3
    fields = [f.field for f in port]
    assert all("hv_creepage_unblocked" in f for f in fields[:-1])
    assert fields[-1] == "used_slot_overclaim"


def test_validator_full_placer_end_to_end() -> None:
    """Run the D5 Python phased placer on a canonical board, then drive both
    validator arms on its output (placements + used_slots) -- the real
    production surface, bit-identical."""
    from temper_placer.deterministic.stages.phased_component_assignment import (
        PhasedComponentAssignmentStage,
    )
    from temper_placer.io.config_loader import PlacementConstraints

    state = _validator_state()
    constraints = PlacementConstraints()
    constraints.placement_priority = {"auto": {"method": "auto"}}
    result = PhasedComponentAssignmentStage(
        constraints, design_rules=state.design_rules
    ).run(state)
    orc, port = _assert_validator_equal(result)
    assert orc == port == [], f"placer output must validate clean, got {port}"


# ---------------------------------------------------------------------------
# Pipeline chain: zone_geometry -> zone_assignment -> slot_generation ->
# component_assignment on both arms
# ---------------------------------------------------------------------------

def test_assignment_chain_identical() -> None:
    from temper_placer.deterministic.stages import (
        slot_generation as _shim_slot_generation,
    )
    from temper_placer.deterministic.stages import (
        zone_geometry as _shim_zone_geometry,
    )

    import tests.deterministic._slot_generation_py_oracle as _orc_slot_generation
    import tests.deterministic._zone_assignment_py_oracle as _orc_zone_assignment
    import tests.deterministic._zone_geometry_py_oracle as _orc_zone_geometry

    from temper_placer.core.board import Board

    comps, nets = [], []
    refs = ("Q1", "C1", "U_MCU1", "R1")
    for i, ref in enumerate(refs):
        net = {"Q1": "AC_L", "C1": "VBUS", "U_MCU1": "3V3", "R1": "SENSE"}[ref]
        nc = {"Q1": "HighVoltage", "C1": "Power", "U_MCU1": "Signal", "R1": "Signal"}[ref]
        pin = Pin("1", "1", (0.0, 0.0), net=net, width=2.0, height=2.0, shape="circle")
        comps.append(
            Component(
                ref=ref, footprint="FP", bounds=(2.0, 2.0), pins=[pin],
                net_class=nc, initial_position=(15.0 * i + 10.0, 40.0),
            )
        )
        nets.append(Net(net, [(ref, "1")], net_class=nc))
    netlist = Netlist(components=comps, nets=nets)
    board = Board(width=120.5, height=80.0)

    def chain(zg, sg, ca, za_run=None):
        state = zg.ZoneGeometryStage().run(BoardState(board=board, netlist=netlist))
        # Shim-debt cleanup 2026-08-19: the zone_assignment shim module was
        # deleted; the port arm drives the pyfunction directly.
        state = za_run(state) if za_run is not None else _orc_zone_assignment.ZoneAssignmentStage().run(state)
        state = sg.SlotGenerationStage(slot_spacing_mm=7.5).run(state)
        return ca.ComponentAssignmentStage(slot_spacing=7.5).run(state)

    orc_state = chain(
        _orc_zone_geometry, _orc_slot_generation,
        _orc_component_assignment,
    )
    port_state = chain(
        _shim_zone_geometry, _shim_slot_generation,
        _shim_component_assignment, za_run=_to.run_zone_assignment,
    )
    assert _placement_canon(port_state.placements) == _placement_canon(
        orc_state.placements
    )
    assert len(port_state.placements) == 4
    # The D4 stage's own output is what it wrote: a placements frozenset over
    # the produced slots (zone_slots from the D2 chain).
    slots = {s for _, zslots in port_state.zone_slots for s in zslots}
    assert set(dict(port_state.placements).values()) <= slots
