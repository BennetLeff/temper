"""R1a: behavioural differential of the D2 deterministic zone stages
against the pinned pre-migration oracle.

Rust Orchestration Engine plan 2026-08-09-001, Phase D batch D2: the
orchestration of ``deterministic/stages/{zone_geometry,zone_assignment,
slot_generation}.py`` moves to ``temper-orchestration`` as ``Stage<BoardState>``
implementors (``ZoneGeometryStage`` + ``ZoneAssignmentStage`` +
``SlotGenerationStage``). Shim-debt cleanup (2026-08-19): the one-line shim
module ``stages/zone_assignment.py`` was deleted -- the zone-assignment arm
of this differential now drives the ``temper_orchestration.run_zone_assignment``
pyfunction (the production path) directly against the oracle. The
pre-migration implementations are pinned VERBATIM as the oracles
(``tests/deterministic/_*_py_oracle.py``, content-hash-pinned below).

Both arms are driven with IDENTICAL BoardState inputs and stage constructor
args; every observable field of the resulting BoardState is compared:

- ``zone_geometry``     -> ``state.zones`` (frozenset of ``Zone`` objects,
  compared structurally as ``(name, bounds)`` — the oracle's ``Zone``
  dataclass and the shim's ``Zone`` dataclass are different classes, so
  element ``==`` cannot compare them; the canon recurses on the nested
  bounds with ``float.hex()`` and keeps ``int`` vs ``float`` distinct)
- ``zone_assignment``   -> ``state.component_zone_map`` (frozenset of
  ``(ref, zone)`` str pairs)
- ``slot_generation``   -> ``state.zone_slots`` (frozenset of
  ``(zone_name, tuple_of_slots)`` entries)

The guards are pinned on BOTH arms as identity-preserving: a state missing
the stage's input is returned unchanged (same object), including the
BoardState ``frozenset()`` defaults — the truthiness guard fires on an
EMPTY ``zones`` too, so a pre-populated ``zone_slots`` survives an
empty-zones pass.

Anti-vacuity: ``test_oracle_and_port_are_different_implementations`` asserts
the shims resolve to the Rust pyfunctions (their ``run`` calls
``temper_orchestration``), not back onto the oracle. The oracle body digests
below are pinned: a differential whose oracle can be edited to agree with the
port proves nothing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import temper_orchestration as _to

from temper_placer.core.board import Board, Zone as CopperZone
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages import slot_generation as _shim_slot_generation
from temper_placer.deterministic.stages import zone_geometry as _shim_zone_geometry

import tests.deterministic._slot_generation_py_oracle as _orc_slot_generation
import tests.deterministic._zone_assignment_py_oracle as _orc_zone_assignment
import tests.deterministic._zone_geometry_py_oracle as _orc_zone_geometry

# ---------------------------------------------------------------------------
# Oracle body pinning (G1)
# ---------------------------------------------------------------------------

_PINNED = {
    "_zone_geometry_py_oracle.py": "fbb85e5a9c5f4f8c1247a6d174bdfc45adda4d90fd097497d15200bb24049616",
    "_zone_assignment_py_oracle.py": "158e7ae7b517609a755f1b696f9fedd4b70949e45cdbbca88815f8b1c3281358",
    "_slot_generation_py_oracle.py": "0cea1ece152d4cfa2502c633006f8b6e2ca03ac3bd27ef60488c47a38bc9ce2f",
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
    assert _shim_zone_geometry.ZoneGeometryStage is not _orc_zone_geometry.ZoneGeometryStage
    assert _shim_slot_generation.SlotGenerationStage is not _orc_slot_generation.SlotGenerationStage
    # The shims' run() bodies call the temper_orchestration pyfunctions --
    # the Rust port -- by bytecode name.
    assert "run_zone_geometry" in _shim_zone_geometry.ZoneGeometryStage.run.__code__.co_names
    assert "run_slot_generation" in _shim_slot_generation.SlotGenerationStage.run.__code__.co_names
    # The zone-assignment shim module was deleted (shim-debt cleanup
    # 2026-08-19): the production path is the pyfunction directly, and the
    # oracle's class must NOT resolve to it (a differential whose oracle
    # grew a Rust call proves nothing).
    assert callable(_to.run_zone_assignment)
    assert (
        "run_zone_assignment"
        not in _orc_zone_assignment.ZoneAssignmentStage.run.__code__.co_names
    )


# ---------------------------------------------------------------------------
# Bit-exact comparison canon
# ---------------------------------------------------------------------------

def _canon(value):
    """Structural canon with bit-exact floats (``float.hex()``) and the
    int-vs-float type carried (``0`` != ``0.0`` — the layout kernel keeps
    int leaves on integer boards)."""
    if isinstance(value, float):
        return ("float", value.hex())
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, tuple):
        return tuple(_canon(v) for v in value)
    if isinstance(value, frozenset):
        return frozenset(_canon(v) for v in value)
    if isinstance(value, list):
        return tuple(_canon(v) for v in value)
    raise AssertionError(f"unhandled canon type: {type(value).__name__}")


def _zones_canon(zones) -> frozenset:
    """The oracle's and the shim's ``Zone`` dataclasses are different
    classes, so frozenset ``==`` between them is always False; the zones are
    projected to ``(name, bounds)`` before canon."""
    return _canon(frozenset((z.name, z.bounds) for z in zones))


# ---------------------------------------------------------------------------
# Corpus
# ---------------------------------------------------------------------------

def _netlist(*refs: str) -> Netlist:
    """A netlist with one component per ref; ``(ref, net, net_class)`` is
    derived positionally from the ref (``Q*`` -> HighVoltage AC_L,
    ``C*`` -> Power VBUS, ``U_MCU*`` -> Signal 3V3, ``U2`` -> Signal
    SPI_MOSI, ``R*`` -> Signal SENSE)."""
    rows = []
    for i, ref in enumerate(refs):
        if ref.startswith("Q"):
            net, net_class = "AC_L", "HighVoltage"
        elif ref.startswith("C"):
            net, net_class = "VBUS", "Power"
        elif ref.startswith("U_MCU"):
            net, net_class = "3V3", "Signal"
        elif ref.startswith("U"):
            net, net_class = "SPI_MOSI", "Signal"
        else:
            net, net_class = "SENSE", "Signal"
        rows.append(
            (
                Component(
                    ref=ref,
                    footprint="FP",
                    bounds=(1.0, 1.0),
                    pins=[Pin(str(i), "1", (0.0, 0.0), net=net)],
                    initial_position=(10.0 * i, 10.0),
                ),
                Net(net, [(ref, "1")], net_class=net_class),
            )
        )
    comps, nets = zip(*rows) if rows else ((), ())
    return Netlist(components=list(comps), nets=list(nets))


_MIXED_REFS = ("Q1", "C1", "U_MCU1", "U2", "R1")


def _copper_zone_config() -> list:
    """A config of core/board.py ``Zone`` objects (flat 4-tuple bounds) as
    ``config_loader`` produces them."""
    return [
        CopperZone(name="Top", bounds=(5, 5, 60, 95)),
        CopperZone(name="Bottom", bounds=(70, 10, 90, 80)),
    ]


# ---------------------------------------------------------------------------
# zone_geometry
# ---------------------------------------------------------------------------

def test_zone_geometry_no_board_guard() -> None:
    state = BoardState()
    orc = _orc_zone_geometry.ZoneGeometryStage().run(state)
    port = _shim_zone_geometry.ZoneGeometryStage().run(state)
    assert orc is state  # oracle guard returns the state unchanged
    assert port is state  # port guard returns the state unchanged (identity)
    assert orc.zones == port.zones == frozenset()


def test_zone_geometry_default_layout_int_board() -> None:
    state = BoardState(board=Board(width=100, height=100))
    orc = _orc_zone_geometry.ZoneGeometryStage().run(state)
    port = _shim_zone_geometry.ZoneGeometryStage().run(state)
    assert _zones_canon(orc.zones) == _zones_canon(port.zones)
    assert {z.name for z in port.zones} == {"HV", "Power", "Signal", "MCU"}


def test_zone_geometry_default_layout_float_board() -> None:
    state = BoardState(board=Board(width=105.3, height=77.2))
    orc = _orc_zone_geometry.ZoneGeometryStage().run(state)
    port = _shim_zone_geometry.ZoneGeometryStage().run(state)
    assert _zones_canon(orc.zones) == _zones_canon(port.zones)


def test_zone_geometry_dict_config_with_ratio() -> None:
    config = [{"name": "Custom", "bounds_ratio": [0.1, 0.2, 0.5, 0.8]}]
    state = BoardState(board=Board(width=100, height=100))
    orc = _orc_zone_geometry.ZoneGeometryStage(config).run(state)
    port = _shim_zone_geometry.ZoneGeometryStage(config).run(state)
    assert _zones_canon(orc.zones) == _zones_canon(port.zones)
    (zone,) = port.zones
    assert zone.name == "Custom"
    assert _canon(zone.bounds) == _canon(((10.0, 20.0), (50.0, 80.0)))


def test_zone_geometry_dict_config_missing_ratio_defaults() -> None:
    config = [{"name": "Full"}]
    state = BoardState(board=Board(width=100, height=100))
    orc = _orc_zone_geometry.ZoneGeometryStage(config).run(state)
    port = _shim_zone_geometry.ZoneGeometryStage(config).run(state)
    assert _zones_canon(orc.zones) == _zones_canon(port.zones)
    (zone,) = port.zones
    assert _canon(zone.bounds) == _canon(((0.0, 0.0), (100.0, 100.0)))


def test_zone_geometry_copper_zone_objects() -> None:
    """The core/board.py ``Zone`` objects branch: flat 4-tuple bounds are
    nested; the name is passed through."""
    state = BoardState(board=Board(width=100, height=100))
    orc = _orc_zone_geometry.ZoneGeometryStage(_copper_zone_config()).run(state)
    port = _shim_zone_geometry.ZoneGeometryStage(_copper_zone_config()).run(state)
    assert _zones_canon(orc.zones) == _zones_canon(port.zones)
    by_name = {z.name: z for z in port.zones}
    # The CopperZone pyclass stores its bounds as a Rect of floats
    # (5.0, not 5) with a flat 4-tuple shape -> nested by the stage.
    assert _canon(by_name["Top"].bounds) == _canon(((5.0, 5.0), (60.0, 95.0)))
    assert _canon(by_name["Bottom"].bounds) == _canon(((70.0, 10.0), (90.0, 80.0)))


def test_zone_geometry_mixed_config_and_unknown_format(capsys) -> None:
    """Dicts, CopperZone objects and an unknown-format entry (``42``) in one
    config: the unknown entry prints the identical warning on both arms."""
    config = [
        {"name": "A", "bounds_ratio": [0, 0, 0.5, 1]},
        42,
        CopperZone(name="B", bounds=(10, 10, 20, 20)),
    ]
    state = BoardState(board=Board(width=100, height=100))
    orc = _orc_zone_geometry.ZoneGeometryStage(config).run(state)
    orc_out = capsys.readouterr().out
    port = _shim_zone_geometry.ZoneGeometryStage(config).run(state)
    port_out = capsys.readouterr().out
    assert orc_out == port_out == "WARNING: Unknown zone format: <class 'int'>\n"
    assert _zones_canon(orc.zones) == _zones_canon(port.zones)


def test_zone_geometry_empty_config_uses_default_layout() -> None:
    """An EMPTY config list is falsy -> the default 4-zone layout branch."""
    state = BoardState(board=Board(width=100, height=100))
    orc = _orc_zone_geometry.ZoneGeometryStage([]).run(state)
    port = _shim_zone_geometry.ZoneGeometryStage([]).run(state)
    assert _zones_canon(orc.zones) == _zones_canon(port.zones)
    assert {z.name for z in port.zones} == {"HV", "Power", "Signal", "MCU"}


# ---------------------------------------------------------------------------
# zone_assignment
# ---------------------------------------------------------------------------

def test_zone_assignment_no_netlist_guard() -> None:
    state = BoardState()
    orc = _orc_zone_assignment.ZoneAssignmentStage().run(state)
    port = _to.run_zone_assignment(state)
    assert orc is state
    assert port is state
    assert orc.component_zone_map == port.component_zone_map == frozenset()


def test_zone_assignment_mixed_netlist() -> None:
    state = BoardState(netlist=_netlist(*_MIXED_REFS))
    orc = _orc_zone_assignment.ZoneAssignmentStage().run(state)
    port = _to.run_zone_assignment(state)
    assert _canon(orc.component_zone_map) == _canon(port.component_zone_map)
    assert dict(port.component_zone_map) == {
        "Q1": "HV",
        "C1": "Power",
        "U_MCU1": "MCU",
        "U2": "MCU",  # SPI net
        "R1": "Signal",
    }


def test_zone_assignment_priority_mcu_prefix_beats_hv_net() -> None:
    """U_MCU ref wins over a HighVoltage net (rule priority order)."""
    c = Component(
        ref="U_MCU1",
        footprint="FP",
        bounds=(1.0, 1.0),
        pins=[Pin("1", "1", (0.0, 0.0), net="AC_L")],
    )
    state = BoardState(
        netlist=Netlist(
            components=[c],
            nets=[Net("AC_L", [("U_MCU1", "1")], net_class="HighVoltage")],
        )
    )
    orc = _orc_zone_assignment.ZoneAssignmentStage().run(state)
    port = _to.run_zone_assignment(state)
    assert _canon(orc.component_zone_map) == _canon(port.component_zone_map)
    assert dict(port.component_zone_map) == {"U_MCU1": "MCU"}


def test_zone_assignment_empty_netlist() -> None:
    state = BoardState(netlist=_netlist())
    orc = _orc_zone_assignment.ZoneAssignmentStage().run(state)
    port = _to.run_zone_assignment(state)
    assert _canon(orc.component_zone_map) == _canon(port.component_zone_map)
    assert port.component_zone_map == frozenset()


# ---------------------------------------------------------------------------
# slot_generation
# ---------------------------------------------------------------------------

def test_slot_generation_no_zones_guard() -> None:
    state = BoardState()
    orc = _orc_slot_generation.SlotGenerationStage().run(state)
    port = _shim_slot_generation.SlotGenerationStage().run(state)
    assert orc is state
    assert port is state
    assert orc.zone_slots == port.zone_slots == frozenset()


def test_slot_generation_empty_zones_does_not_clobber_slots() -> None:
    """The truthiness guard fires on an EMPTY ``zones`` frozenset too: a
    pre-populated ``zone_slots`` survives the pass untouched on both arms."""
    state = BoardState(zones=frozenset(), zone_slots=frozenset({("old", ())}))
    orc = _orc_slot_generation.SlotGenerationStage().run(state)
    port = _shim_slot_generation.SlotGenerationStage().run(state)
    assert orc is state
    assert port is state
    assert orc.zone_slots == port.zone_slots == frozenset({("old", ())})


def test_slot_generation_from_default_zones() -> None:
    state = _orc_zone_geometry.ZoneGeometryStage().run(
        BoardState(board=Board(width=100, height=100))
    )
    orc = _orc_slot_generation.SlotGenerationStage(slot_spacing_mm=5.0).run(state)
    port = _shim_slot_generation.SlotGenerationStage(slot_spacing_mm=5.0).run(
        _shim_zone_geometry.ZoneGeometryStage().run(
            BoardState(board=Board(width=100, height=100))
        )
    )
    assert _canon(orc.zone_slots) == _canon(port.zone_slots)
    assert {name for name, _ in port.zone_slots} == {"HV", "Power", "Signal", "MCU"}


def test_slot_generation_custom_spacing_drifts_bit_identical() -> None:
    """spacing=0.1 (not exactly representable) exercises the naive ``+=``
    drift; both arms must carry the identical accumulated bits."""
    state = _shim_zone_geometry.ZoneGeometryStage().run(
        BoardState(board=Board(width=10.3, height=10.3))
    )
    orc = _orc_slot_generation.SlotGenerationStage(slot_spacing_mm=0.1).run(state)
    port = _shim_slot_generation.SlotGenerationStage(slot_spacing_mm=0.1).run(state)
    assert _canon(orc.zone_slots) == _canon(port.zone_slots)


def test_slot_generation_zero_extent_zone() -> None:
    """A zero-extent zone (spacing >= extent) yields an empty slot tuple."""
    zones = frozenset(
        {
            _orc_zone_geometry.Zone(name="Tiny", bounds=((0, 0), (0, 0))),
            _shim_zone_geometry.Zone(name="Tiny2", bounds=((0, 0), (0, 0))),
        }
    )
    state = BoardState(zones=zones)
    orc = _orc_slot_generation.SlotGenerationStage(slot_spacing_mm=5.0).run(state)
    port = _shim_slot_generation.SlotGenerationStage(slot_spacing_mm=5.0).run(state)
    assert _canon(orc.zone_slots) == _canon(port.zone_slots)
    assert {name for name, _ in port.zone_slots} == {"Tiny", "Tiny2"}
    assert all(len(slots) == 0 for _, slots in port.zone_slots)


def test_slot_generation_wide_spacing_empty_grid() -> None:
    """spacing >= zone extent -> empty slot tuple for every zone."""
    state = _shim_zone_geometry.ZoneGeometryStage().run(
        BoardState(board=Board(width=100, height=100))
    )
    orc = _orc_slot_generation.SlotGenerationStage(slot_spacing_mm=500.0).run(state)
    port = _shim_slot_generation.SlotGenerationStage(slot_spacing_mm=500.0).run(state)
    assert _canon(orc.zone_slots) == _canon(port.zone_slots)
    assert all(len(slots) == 0 for _, slots in port.zone_slots)


# ---------------------------------------------------------------------------
# Pipeline chain
# ---------------------------------------------------------------------------

def test_zone_stage_chain_identical() -> None:
    """zone_geometry -> zone_assignment -> slot_generation on both arms;
    the chained state matches field-for-field."""
    from dataclasses import replace as _dataclass_replace

    board = Board(width=120.5, height=80.0)

    orc_state = _orc_zone_geometry.ZoneGeometryStage().run(BoardState(board=board))
    orc_state = _orc_zone_assignment.ZoneAssignmentStage().run(
        _dataclass_replace(orc_state, netlist=_netlist(*_MIXED_REFS))
    )
    orc_state = _orc_slot_generation.SlotGenerationStage(slot_spacing_mm=7.5).run(orc_state)

    port_state = _shim_zone_geometry.ZoneGeometryStage().run(BoardState(board=board))
    port_state = _to.run_zone_assignment(
        _dataclass_replace(port_state, netlist=_netlist(*_MIXED_REFS))
    )
    port_state = _shim_slot_generation.SlotGenerationStage(slot_spacing_mm=7.5).run(port_state)

    assert _zones_canon(orc_state.zones) == _zones_canon(port_state.zones)
    assert _canon(orc_state.component_zone_map) == _canon(port_state.component_zone_map)
    assert _canon(orc_state.zone_slots) == _canon(port_state.zone_slots)
