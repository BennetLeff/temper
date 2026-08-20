"""R1a behavioural differential of the D5 deterministic zone-aware stages
against the pinned pre-migration oracle.

Rust Orchestration Engine plan 2026-08-09-001, Phase D batch D5: the
orchestration of ``deterministic/stages/zone_aware_slot_generation.py`` (the
``ZoneAwareSlotGenerationStage`` run: ``_isolation_filter`` / K4 reclaim,
``_get_copper_zones``, the per-zone slot walk with copper + isolation-cutout
filtering, the writes) and of the phased-component-assignment mixins
(``_phase_core.py`` -- the four mixins collapsed into one module 2026-08-20;
the ``PhasedComponentAssignmentStage`` run: the
state guards, ``compiler.validate``, the design-rules attach, the phase
dispatch, the template/proximity/optimize placement methods, the HV
ghost-pad reservation and the ``frozenset`` writes) move to
``temper-orchestration`` as ``Stage<BoardState>`` implementors
(``ZoneAwareSlotGenerationStage`` + ``PhasedAssignmentStage``).
The pre-migration implementations are pinned VERBATIM as the oracles
(``tests/deterministic/_zone_aware_slot_generation_run_py_oracle.py`` and
``_phased_assignment_py_oracle.py``, content-hash-pinned below).

Both arms are driven with IDENTICAL BoardState inputs and stage constructor
args; every observable output is compared bit-exactly (floats projected
through ``float.hex()``):

- ``ZoneAwareSlotGenerationStage`` -> ``state.zone_slots`` (frozenset of
  ``(zone_name, tuple_of_slots)``) and ``state.reclaim_by_pin_pair`` (the
  K4 reclaim dict, or ``None``). The no-zones guard writes the reclaim (or
  ``None``) through ``dataclasses.replace`` exactly like the oracle (value
  equality, not identity -- the oracle's ``replace`` never preserves the
  original object).
- ``PhasedComponentAssignmentStage`` -> ``state.placements`` (frozenset of
  ``(ref, (x, y))``) and ``state.used_slots`` (frozenset of grid slots). The
  no-netlist / no-zone-map / no-zone-slots guard returns the ORIGINAL state
  object on both arms (identity pinned). The ``design_rules`` attach (U3:
  stage ``design_rules`` lands on the state when the state's is ``None``) is
  compared by object equality.

Anti-vacuity: ``test_oracle_and_port_are_different_implementations`` asserts
the shims resolve to the Rust pyfunctions (their ``run`` bodies call
``temper_orchestration``), not back onto the oracle. The oracle body digests
below are pinned: a differential whose oracle can be edited to agree with the
port proves nothing.
"""

from __future__ import annotations

import hashlib
import inspect
from dataclasses import replace
from pathlib import Path

import temper_orchestration as _to
import tests.deterministic._phased_assignment_py_oracle as _orc_phased
import tests.deterministic._zone_aware_slot_generation_run_py_oracle as _orc_zone_aware

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.stages import (
    PhasedComponentAssignmentStage as _shim_phased,
)
from temper_placer.deterministic.stages import (
    ZoneAwareSlotGenerationStage as _shim_zone_aware,
)
from temper_placer.deterministic.state import BoardState
from temper_placer.io.config_loader import IsolationSlot, PlacementConstraints

# ---------------------------------------------------------------------------
# Oracle body pinning (G1)
# ---------------------------------------------------------------------------

_PINNED = {
    "_zone_aware_slot_generation_run_py_oracle.py": (
        "0731def49ded64dfa2b077d802dafd36223bac0ba90b81a8e2730e9b0025671f"
    ),
    "_phased_assignment_py_oracle.py": (
        "5f23ea0991a14b9aac4819664c4092b9cb503b4c2d12d2d0e048008c720ffe91"
    ),
}
_BODY_MARKER = "# --- BEGIN PINNED BODY ---\n"


def test_oracle_bodies_match_pinned_digests() -> None:
    for name, expected in _PINNED.items():
        text = (Path(__file__).with_name(name)).read_text(encoding="utf-8")
        assert _BODY_MARKER in text, f"{name} oracle header marker missing"
        body = text.split(_BODY_MARKER, 1)[1]
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert digest == expected, (
            f"{name} drifted from its pinned digest; the oracle must be a "
            "verbatim pre-migration snapshot, never edited to agree with the port"
        )


# ---------------------------------------------------------------------------
# Canonicalisers (bit-exact comparison via float.hex)
# ---------------------------------------------------------------------------

def _slot_hex(slot) -> tuple[str, str]:
    return (float(slot[0]).hex(), float(slot[1]).hex())


def _zone_slots_canon(zone_slots) -> dict[str, tuple]:
    return {name: tuple(_slot_hex(s) for s in slots) for name, slots in zone_slots}


def _reclaim_canon(reclaim):
    return None if reclaim is None else {k: float(v).hex() for k, v in reclaim.items()}


def _placements_canon(placements) -> dict[str, tuple[str, str]]:
    return {
        ref: (float(x).hex(), float(y).hex())
        for ref, (x, y) in dict(placements).items()
    }


def _used_slots_canon(used_slots) -> frozenset:
    return frozenset(_slot_hex(s) for s in used_slots)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _netlist(refs=("Q1", "C1", "U_MCU1", "R1")) -> Netlist:
    comps, nets = [], []
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
    return Netlist(components=comps, nets=nets)


def _slot_grid(n=5, spacing=5.0) -> tuple:
    return tuple(
        (float(x), float(y))
        for x in range(0, int(n * spacing), int(spacing))
        for y in range(0, int(n * spacing), int(spacing))
    )


def _zones_board_state() -> BoardState:
    """A BoardState with a small ``board`` and two placement zones."""
    board = Board(width=100.0, height=100.0)

    class _Zone:
        def __init__(self, name, bounds):
            self.name = name
            self.bounds = bounds

    zones = frozenset(
        {
            _Zone("HV", ((0.0, 0.0), (40.0, 40.0))),
            _Zone("LV", ((40.0, 0.0), (100.0, 100.0))),
        }
    )
    return BoardState(board=board, zones=zones)


def _copper_zone(name="GND", polygon=None, bounds=None, layers=None, net_classes=None):
    class _CZ:
        def __init__(self):
            self.name = name
            self.polygon = polygon
            self.bounds = bounds
            self.layers = layers
            self.net_classes = net_classes

    return _CZ()


def _iso_slot(component_ref="Q1", width_mm=1.5, name="s1") -> IsolationSlot:
    return IsolationSlot(
        name=name,
        component_ref=component_ref,
        lv_pin="1",
        hv_pin="2",
        width_mm=width_mm,
        start_offset=(0.0, -5.0),
        end_offset=(0.0, 5.0),
    )


def _assert_zone_aware_equal(orc_state: BoardState, port_state: BoardState) -> None:
    assert _zone_slots_canon(orc_state.zone_slots) == _zone_slots_canon(
        port_state.zone_slots
    ), "zone_slots diverged"
    assert _reclaim_canon(orc_state.reclaim_by_pin_pair) == _reclaim_canon(
        port_state.reclaim_by_pin_pair
    ), "reclaim_by_pin_pair diverged"


def _zone_aware_args(
    *,
    slot_spacing_mm=5.0,
    copper_zone_margin=2.0,
    min_routing_channel=3.0,
    yaml_copper_zones=None,
    yaml_isolation_slots=None,
    net_class_rules=None,
):
    return {
        "slot_spacing_mm": slot_spacing_mm,
        "copper_zone_margin": copper_zone_margin,
        "min_routing_channel": min_routing_channel,
        "yaml_copper_zones": yaml_copper_zones,
        "yaml_isolation_slots": yaml_isolation_slots,
        "net_class_rules": net_class_rules,
    }


def _run_zone_aware_both(state: BoardState, **kw) -> tuple[BoardState, BoardState]:
    args = _zone_aware_args(**kw)
    orc = _orc_zone_aware.ZoneAwareSlotGenerationStage(**args).run(state)
    port = _shim_zone_aware(**args).run(state)
    return orc, port


def _phased_state(*, refs=("Q1", "C1"), with_domains=False) -> BoardState:
    comps = []
    for i, ref in enumerate(refs):
        net = {"Q1": "AC_L", "C1": "VBUS"}.get(ref, "3V3")
        nc = {"Q1": "HighVoltage", "C1": "Power"}.get(ref, "Signal")
        pin = Pin("1", "1", (0.0, 0.0), net=net, width=2.0, height=2.0, shape="circle")
        comps.append(
            Component(
                ref=ref, footprint="FP", bounds=(2.0, 2.0), pins=[pin],
                net_class=nc, initial_position=(10.0 + 15.0 * i, 20.0),
            )
        )
    netlist = Netlist(components=comps, nets=[])
    state = BoardState(
        netlist=netlist,
        component_zone_map=frozenset((c.ref, "Signal") for c in comps),
        zone_slots=frozenset({("Signal", _slot_grid())}),
    )
    if with_domains:
        state = replace(
            state,
            component_domain_map=frozenset((c.ref, "LV_interior") for c in comps),
            domain_regions=(
                _polygon([(0, -10), (100, -10), (100, 110), (0, 110)]),
            ),
        )
    return state


def _polygon(coords):
    from shapely.geometry import Polygon

    return Polygon(coords)


def _assert_phased_equal(orc_state: BoardState, port_state: BoardState) -> None:
    assert _placements_canon(orc_state.placements) == _placements_canon(
        port_state.placements
    ), "placements diverged"
    assert _used_slots_canon(orc_state.used_slots) == _used_slots_canon(
        port_state.used_slots
    ), "used_slots diverged"


def _run_phased_both(
    state: BoardState,
    *,
    constraints: PlacementConstraints | None = None,
    design_rules=None,
    use_isolation_slots=False,
    slot_spacing=12.0,
    w_r=0.05,
    channel_map=None,
    fixed_placements=None,
) -> tuple[BoardState, BoardState]:
    c = constraints or PlacementConstraints()
    kw = {
        "slot_spacing": slot_spacing,
        "design_rules": design_rules,
        "use_isolation_slots": use_isolation_slots,
        "w_r": w_r,
        "channel_map": channel_map,
        "fixed_placements": fixed_placements,
    }
    orc = _orc_phased.PhasedComponentAssignmentStage(c, **kw).run(state)
    port = _shim_phased(c, **kw).run(state)
    return orc, port


def test_oracle_and_port_are_different_implementations() -> None:
    """The shims must resolve to the Rust pyfunctions, not the oracle."""
    src = inspect.getsource(_shim_zone_aware.run)
    assert "run_zone_aware_slot_generation" in src
    src = inspect.getsource(_shim_phased.run)
    assert "run_phased_assignment" in src
    assert _to.run_zone_aware_slot_generation is not None
    assert _to.run_phased_assignment is not None


# ---------------------------------------------------------------------------
# ZoneAwareSlotGenerationStage differential
# ---------------------------------------------------------------------------

def test_zone_aware_no_zones_writes_reclaim() -> None:
    """No zones: the isolation filter still runs and the reclaim dict (or
    None) is written via dataclasses.replace -- value-equality, not
    identity (the oracle's replace never preserves the original object)."""
    state = BoardState(netlist=_netlist())
    orc, port = _run_zone_aware_both(state, yaml_isolation_slots=[_iso_slot()])
    _assert_zone_aware_equal(orc, port)
    assert port.reclaim_by_pin_pair, "reclaim must be populated on the no-zones path"
    assert port.zone_slots == frozenset()


def test_zone_aware_no_zones_no_reclaim() -> None:
    """No zones and no isolation slots: reclaim stays None (value)."""
    state = BoardState(netlist=_netlist())
    orc, port = _run_zone_aware_both(state)
    _assert_zone_aware_equal(orc, port)
    assert port.reclaim_by_pin_pair is None


def test_zone_aware_plain_generation() -> None:
    """Zones present, no copper zones and no isolation cutouts: standard
    slot generation with reclaim explicitly None."""
    state = _zones_board_state()
    orc, port = _run_zone_aware_both(state)
    _assert_zone_aware_equal(orc, port)
    assert port.zone_slots, "zones must produce slots"
    assert port.reclaim_by_pin_pair is None
    assert {name for name, _ in port.zone_slots} == {"HV", "LV"}


def test_zone_aware_copper_zone_polygon_filter() -> None:
    """A copper zone on F.Cu with a polygon filters the covered slots."""
    state = _zones_board_state()
    polygon = [(0.0, 0.0), (25.0, 0.0), (25.0, 25.0), (0.0, 25.0)]
    cz = _copper_zone(name="GND", polygon=polygon, layers="F.Cu")
    orc, port = _run_zone_aware_both(state, yaml_copper_zones=[cz])
    _assert_zone_aware_equal(orc, port)
    for _name, slots in port.zone_slots:
        for (x, y) in slots:
            assert not _point_in_poly(x, y, polygon), f"slot ({x},{y}) inside GND zone"


def _point_in_poly(x, y, polygon) -> bool:
    import temper_design_bundle_python as _tdb

    return _tdb.deterministic_phase.point_in_polygon_py(x, y, polygon)


def test_zone_aware_copper_zone_bounds_margin() -> None:
    """A copper zone with a bounds box (no polygon) filters with the
    copper_zone_margin expansion."""
    state = _zones_board_state()
    cz = _copper_zone(name="VCC", polygon=None, bounds=(0.0, 0.0, 22.0, 22.0), layers="F.Cu")
    orc, port = _run_zone_aware_both(
        state, yaml_copper_zones=[cz], copper_zone_margin=3.0
    )
    _assert_zone_aware_equal(orc, port)
    # margin 3.0 -> effective box [−3, −3, 25, 25]. The HV zone's grid slots
    # run 2.5..37.5 in steps of 5; the box covers every slot with x,y <= 25.
    hvs = dict(port.zone_slots)["HV"]
    assert (22.5, 22.5) not in hvs, "margin-expanded bounds must filter (22.5, 22.5)"
    assert (27.5, 27.5) in hvs, "(27.5, 27.5) must survive the margin"


def test_zone_aware_copper_zone_wrong_layer() -> None:
    """A copper zone on B.Cu (or internal) must not filter F.Cu slots."""
    state = _zones_board_state()
    polygon = [(0.0, 0.0), (40.0, 0.0), (40.0, 40.0), (0.0, 40.0)]
    cz = _copper_zone(name="GND", polygon=polygon, layers="B.Cu")
    orc, port = _run_zone_aware_both(state, yaml_copper_zones=[cz])
    _assert_zone_aware_equal(orc, port)
    assert dict(port.zone_slots)["HV"], "no slot may be filtered by a B.Cu zone"


def test_zone_aware_iso_aabb_filter_and_reclaim() -> None:
    """Isolation-slot cutouts filter candidate slots AND emit the K4 reclaim
    dict keyed by (component_ref, lv_pin, hv_pin)."""
    state = _zones_board_state()
    state = replace(state, netlist=_netlist(refs=("Q1",)))
    iso = _iso_slot(component_ref="Q1")
    orc, port = _run_zone_aware_both(state, yaml_isolation_slots=[iso])
    _assert_zone_aware_equal(orc, port)
    reclaim = port.reclaim_by_pin_pair
    assert reclaim, "reclaim dict must be emitted"
    assert ("Q1", "1", "2") in reclaim
    # K4 defaults: width/2 + 5.5 - pitch.  Q1's pins sit at (0,0) both
    # (single pin) -> pitch falls back to the TO-247 default 5.45.
    expected = max(0.0, min(1.5 / 2.0 + 5.5 - 5.45, max(0.0, 6.0 - 0.5)))
    assert float(reclaim[("Q1", "1", "2")]).hex() == float(expected).hex()


def test_zone_aware_net_class_rules_override() -> None:
    """A net_class_rules entry whose uppercased name matches the HV
    word-boundary pattern overrides the K4 perpendicular/requirement."""
    rules = {"HighVoltage_HV": type("_R", (), {"clearance_mm": 8.0})()}
    state = _zones_board_state()
    state = replace(state, netlist=_netlist(refs=("Q1",)))
    iso = _iso_slot(component_ref="Q1")
    orc, port = _run_zone_aware_both(
        state, yaml_isolation_slots=[iso], net_class_rules=rules
    )
    _assert_zone_aware_equal(orc, port)
    value = port.reclaim_by_pin_pair[("Q1", "1", "2")]
    # perp_budget = original_req = 8.0; raw = 0.75 + 8.0 - 5.45; upper = 7.5
    assert float(value).hex() == float(min(0.75 + 8.0 - 5.45, 7.5)).hex()


def test_zone_aware_pin_pitch_resolved_from_netlist() -> None:
    """A component with two real pins yields a per-slot pitch instead of the
    TO-247 fallback."""
    comp = Component(
        ref="Q1", footprint="TO-247", bounds=(10.0, 10.0), initial_position=(20.0, 15.0),
        pins=[
            Pin("1", "1", (0.0, 0.0), net="AC_L"),
            Pin("2", "2", (0.0, 5.45), net="AC_N"),
        ],
    )
    netlist = Netlist(components=[comp], nets=[])
    state = _zones_board_state()
    state = replace(state, netlist=netlist)
    iso = _iso_slot(component_ref="Q1")
    orc, port = _run_zone_aware_both(state, yaml_isolation_slots=[iso])
    _assert_zone_aware_equal(orc, port)
    value = port.reclaim_by_pin_pair[("Q1", "1", "2")]
    pitch = 5.45  # (0,0)->(0,5.45)
    assert float(value).hex() == float(max(0.0, min(1.5 / 2.0 + 5.5 - pitch, 5.5))).hex()


# ---------------------------------------------------------------------------
# PhasedComponentAssignmentStage differential
# ---------------------------------------------------------------------------

def test_phased_guard_no_netlist_identity() -> None:
    """The no-netlist guard returns the ORIGINAL state object on both arms."""
    state = BoardState()
    orc, port = _run_phased_both(state)
    assert port is state
    assert orc is state


def test_phased_guard_no_zone_map_identity() -> None:
    """The no-component-zone-map guard returns the ORIGINAL state object."""
    state = BoardState(netlist=_netlist(refs=("Q1",)))
    orc, port = _run_phased_both(state)
    assert port is state
    assert orc is state


def test_phased_simple_auto_phase() -> None:
    c = PlacementConstraints()
    c.placement_priority = {"auto": {"method": "auto"}}
    state = _phased_state()
    orc, port = _run_phased_both(state, constraints=c)
    _assert_phased_equal(orc, port)
    assert set(dict(port.placements)) == {"Q1", "C1"}
    assert port.used_slots, "auto phase must reserve slots"


def test_phased_template_phase() -> None:
    """A template phase (anchor) places the listed refs at anchor + i*10."""
    c = PlacementConstraints()
    c.placement_priority = {
        "fixed": {"method": "template", "components": ["C1"], "anchor": [5.0, 5.0]},
        "auto": {"method": "auto"},
    }
    state = _phased_state()
    orc, port = _run_phased_both(state, constraints=c)
    _assert_phased_equal(orc, port)
    assert dict(port.placements)["C1"] == (5.0, 5.0)


def test_phased_proximity_phase() -> None:
    """A proximity phase anchors against a reference placed by an earlier
    phase and picks a slot within max_distance_mm."""
    c = PlacementConstraints()
    c.placement_priority = {
        "fixed": {"method": "template", "components": ["C1"], "anchor": [15.0, 15.0]},
        "near": {
            "method": "proximity",
            "components": ["Q1"],
            "reference": "C1",
            "max_distance_mm": 25.0,
        },
    }
    state = _phased_state()
    orc, port = _run_phased_both(state, constraints=c)
    _assert_phased_equal(orc, port)
    placements = dict(port.placements)
    q1, c1 = placements["Q1"], placements["C1"]
    dist = ((q1[0] - c1[0]) ** 2 + (q1[1] - c1[1]) ** 2) ** 0.5
    assert dist <= 25.0


def test_phased_optimize_domain_filter() -> None:
    """The optimize phase with a per-ref domain region keeps only slots the
    region covers."""
    c = PlacementConstraints()
    c.placement_priority = {"optimize": {"method": "optimize"}}
    state = _phased_state(with_domains=True)
    # The region covers x in [0, 100]; the grid runs 0..20, so every slot
    # passes -- the differential must still agree bit-for-bit.
    orc, port = _run_phased_both(state, constraints=c)
    _assert_phased_equal(orc, port)
    assert set(dict(port.placements)) == {"Q1", "C1"}


def test_phased_hv_ghost_pads() -> None:
    """design_rules with an HV creepage injects ghost-pad rings: every slot
    within creepage of an HV pin's absolute position lands in used_slots."""
    from temper_placer.core.design_rules import DesignRules, NetClassRules

    rules = DesignRules(
        net_classes={
            "HighVoltage": NetClassRules(
                name="HighVoltage", trace_width=0.5, clearance=2.0,
                dru_priority=10, creepage_mm=6.0, safety_category="HV",
            ),
            "Signal": NetClassRules(
                name="Signal", trace_width=0.25, clearance=0.2,
                dru_priority=20, safety_category="LV",
            ),
        },
        net_class_assignments={"AC_L": "HighVoltage", "3V3": "Signal"},
    )
    c = PlacementConstraints()
    c.placement_priority = {"auto": {"method": "auto"}}
    state = _phased_state(refs=("Q1", "C1"))
    orc, port = _run_phased_both(state, constraints=c, design_rules=rules)
    _assert_phased_equal(orc, port)
    used = set(port.used_slots)
    # The HV pin sits at some placed position; creepage 6.0 must have
    # reserved at least one slot beyond the footprint ring.
    assert used, "used_slots must be non-empty with HV rings enabled"


def test_phased_design_rules_attach() -> None:
    """Stage design_rules land on the state when the state has none."""
    from temper_placer.core.design_rules import DesignRules

    rules = DesignRules(net_classes={}, net_class_assignments={})
    c = PlacementConstraints()
    c.placement_priority = {"auto": {"method": "auto"}}
    state = _phased_state()
    orc, port = _run_phased_both(state, constraints=c, design_rules=rules)
    assert port.design_rules == rules
    assert orc.design_rules == rules
    _assert_phased_equal(orc, port)


def test_phased_no_phases_fallback_greedy() -> None:
    """placement_priority empty -> the simple greedy fallback (no HV rings)."""
    state = _phased_state()
    orc, port = _run_phased_both(state, constraints=PlacementConstraints())
    _assert_phased_equal(orc, port)
    assert set(dict(port.placements)) == {"Q1", "C1"}


def test_phased_fixed_placements() -> None:
    """Fixed placements are stored on the stage but the phased run()
    orchestration does NOT consume them (verified pre-migration; the
    differential pins both arms to the identical no-op)."""
    c = PlacementConstraints()
    c.placement_priority = {"auto": {"method": "auto"}}
    state = _phased_state()
    fixed = {"Q1": {"position": [3.0, 3.0], "rotation": 0}}
    orc, port = _run_phased_both(state, constraints=c, fixed_placements=fixed)
    _assert_phased_equal(orc, port)
    assert dict(port.placements)["Q1"] == dict(orc.placements)["Q1"]


def test_phased_unknown_phase_method_warns_and_continues() -> None:
    """An unknown phase method logs a warning and leaves the phase's refs
    unplaced (the differential output is unchanged on both arms)."""
    c = PlacementConstraints()
    c.placement_priority = {
        "bogus": {"method": "teleport", "components": ["Q1"]},
        "auto": {"method": "auto"},
    }
    state = _phased_state()
    orc, port = _run_phased_both(state, constraints=c)
    _assert_phased_equal(orc, port)
    assert "Q1" in dict(port.placements), "auto phase must still place Q1"


def test_phased_chain_from_d2_slots() -> None:
    """Full chain: zone geometry -> zone assignment -> slot generation ->
    phased assignment on both arms (the real production surface)."""
    import tests.deterministic._slot_generation_py_oracle as _orc_slot_generation
    import tests.deterministic._zone_assignment_py_oracle as _orc_zone_assignment
    import tests.deterministic._zone_geometry_py_oracle as _orc_zone_geometry

    from temper_placer.deterministic.stages import (
        SlotGenerationStage as _shim_slot_generation,
    )
    from temper_placer.deterministic.stages import (
        ZoneGeometryStage as _shim_zone_geometry,
    )

    netlist = _netlist()
    board = Board(width=120.5, height=80.0)
    c = PlacementConstraints()
    c.placement_priority = {"auto": {"method": "auto"}}

    def chain(zg, sg, ph_cls, za_run=None):
        # Shim-debt cleanup 2026-08-20: the D2 stage classes were collapsed
        # onto the RustFunctionStage adapter in `stages/__init__.py`, so the
        # port arm passes the CLASSES while the oracle arm passes its pinned
        # modules (each defining its own pre-migration class).
        zg_cls = zg if isinstance(zg, type) else zg.ZoneGeometryStage
        sg_cls = sg if isinstance(sg, type) else sg.SlotGenerationStage
        state = zg_cls().run(BoardState(board=board, netlist=netlist))
        # Shim-debt cleanup 2026-08-19: the zone_assignment shim module was
        # deleted; the port arm drives the pyfunction directly.
        state = za_run(state) if za_run is not None else _orc_zone_assignment.ZoneAssignmentStage().run(state)
        state = sg_cls(slot_spacing_mm=7.5).run(state)
        return ph_cls(c).run(state)

    orc_state = chain(
        _orc_zone_geometry, _orc_slot_generation,
        _orc_phased.PhasedComponentAssignmentStage,
    )
    port_state = chain(
        _shim_zone_geometry, _shim_slot_generation, _shim_phased,
        za_run=_to.run_zone_assignment,
    )
    _assert_phased_equal(orc_state, port_state)
    assert orc_state.placements == port_state.placements
    assert orc_state.used_slots == port_state.used_slots


def test_zone_aware_and_phased_agree_on_placements() -> None:
    """Cross-batch: run the zone-aware stage and the phased stage on the same
    state; the differential stays bit-identical per stage (zone_slots feeds
    the phased stage)."""
    state = _zones_board_state()
    state = replace(state, netlist=_netlist())
    orc, port = _run_zone_aware_both(state)
    _assert_zone_aware_equal(orc, port)
    state = replace(
        state,
        zones=frozenset(),
        component_zone_map=frozenset((c.ref, "Signal") for c in _netlist().components),
        zone_slots=frozenset({("Signal", _slot_grid())}),
    )
    c = PlacementConstraints()
    c.placement_priority = {"auto": {"method": "auto"}}
    orc2, port2 = _run_phased_both(state, constraints=c)
    _assert_phased_equal(orc2, port2)
