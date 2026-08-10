"""Differential test: Phase-A U6 oracle marshalers in Rust
(temper_drc_rs.OracleInput / OracleOutput) vs the pinned Python marshalers
(Wave-4 discipline contract G1/G2).

The two Python marshalers being migrated are:

  | Python marshaler              | File                         | Rust target    |
  |-------------------------------|------------------------------|----------------|
  | ``_netlist_to_oracle_dict``   | human_reference_extractor.py | ``OracleInput``  |
  | ``_placement_to_oracle_dict`` | human_reference_extractor.py | ``OracleOutput`` |

They build the flat dicts that ``temper_quality_oracle.prepare_quality_py`` /
``evaluate_prepared_py`` consume (the quality-oracle crate's pinned dict API;
see ``test_marshaler_dict_shapes.py`` and the JUSTIFIED-KEEP record
``docs/solutions/architecture-patterns/quality-oracle-marshalers-justified-keep-2026-08-09.md``
whose re-decidable trigger the rust-orchestration-engine plan's Phase-A table
fires). After Phase A the Python shim bodies collapse to
``_tdrc.OracleInput.from_netlist(...).to_dict()`` — the dict-building tax
moves to Rust, the U5 ``DrcBoardSnapshot`` pattern.

The ``_oracle_*`` blocks below are VERBATIM copies of the pre-migration
implementations AS COMMITTED (``human_reference_extractor.py`` lines 382–417
at ``edc19ffa``, origin/main). Do NOT edit them — they are the reference.

The Rust symbols ``_tdrc.OracleInput`` / ``_tdrc.OracleOutput`` do not exist
yet (RED); this file fails to collect until the Phase-A U6 Rust
implementation lands (G1 test-before-code).

Comparison convention: dicts/floats canonicalized to float.hex() strings,
so equality is bit-exact ``==`` (never tolerance).
"""

from __future__ import annotations

import numpy as np
import temper_drc_rs as _tdrc

# Rust symbols under test — must exist or this file fails to collect (RED).
ORACLE_INPUT = _tdrc.OracleInput
ORACLE_OUTPUT = _tdrc.OracleOutput

from temper_placer.core.board import Board  # noqa: E402
from temper_placer.core.netlist import Component, Net, Netlist  # noqa: E402
from temper_placer.core.state import PlacementState  # noqa: E402


# ---------------------------------------------------------------------------
# Oracle 1 — _netlist_to_oracle_dict (human_reference_extractor.py, verbatim)
# ---------------------------------------------------------------------------


def _oracle_netlist_to_oracle_dict(netlist):
    """Pre-migration ``_netlist_to_oracle_dict``, verbatim
    (human_reference_extractor.py)."""
    return {
        "nets": [{"name": net.name, "pins": [ref for ref, _ in net.pins]} for net in netlist.nets],
        "components": [
            {
                "ref": comp.ref,
                "footprint": comp.footprint,
                "width": float(comp.bounds[0]),
                "height": float(comp.bounds[1]),
            }
            for comp in netlist.components
        ],
    }


# ---------------------------------------------------------------------------
# Oracle 2 — _placement_to_oracle_dict (human_reference_extractor.py, verbatim)
# ---------------------------------------------------------------------------


def _oracle_placement_to_oracle_dict(state, netlist, board):
    """Pre-migration ``_placement_to_oracle_dict``, verbatim
    (human_reference_extractor.py)."""
    positions = np.asarray(state.positions, dtype=np.float64)
    return {
        "positions": positions.reshape(-1).tolist(),
        "component_refs": [c.ref for c in netlist.components],
        "board_width_mm": float(board.width),
        "board_height_mm": float(board.height),
    }


# ---------------------------------------------------------------------------
# Canonicalisation helpers
# ---------------------------------------------------------------------------


def _float_hex_recursive(obj):
    """Recursively convert floats to hex strings for bit-exact comparison."""
    if isinstance(obj, float):
        return float(obj).hex()
    if isinstance(obj, dict):
        return {k: _float_hex_recursive(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_float_hex_recursive(v) for v in obj]
    return obj


def _canon(d):
    return _float_hex_recursive(d)


# ---------------------------------------------------------------------------
# Canonical fixtures
# ---------------------------------------------------------------------------


def _make_netlist() -> Netlist:
    """3 components / 3 nets — a mixed net with a dangling pin ref order,
    a net with no pins, and an int-bounds-free (all-float) component set."""
    c1 = Component(ref="C1", footprint="0805", bounds=(2.0, 1.5))
    c2 = Component(ref="R1", footprint="0603", bounds=(1.6, 0.8))
    c3 = Component(ref="U1", footprint="QFN-32", bounds=(5.0, 5.0))
    net_a = Net(name="VCC", pins=[("C1", "1"), ("U1", "12")])
    net_b = Net(name="GND", pins=[("C1", "2"), ("R1", "1"), ("U1", "5")])
    net_c = Net(name="NC", pins=[])
    return Netlist(components=[c1, c2, c3], nets=[net_a, net_b, net_c])


def _make_state(dtype=np.float32) -> PlacementState:
    """A PlacementState with 3 components at known positions."""
    return PlacementState(
        positions=np.array([[10.0, 20.0], [30.0, 40.0], [50.0, 60.0]], dtype=dtype),
        rotation_logits=np.zeros((3, 4), dtype=np.float32),
    )


def _make_board() -> Board:
    return Board(width=100.0, height=80.0)


# ---------------------------------------------------------------------------
# Differential — OracleInput.from_netlist
# ---------------------------------------------------------------------------


def test_oracle_input_from_netlist_matches_oracle():
    """G1/G2: OracleInput.from_netlist(netlist).to_dict() must be
    bit-identical to the pinned _netlist_to_oracle_dict output."""
    netlist = _make_netlist()
    py_dict = _oracle_netlist_to_oracle_dict(netlist)
    rust = ORACLE_INPUT.from_netlist(netlist)
    assert isinstance(rust, _tdrc.OracleInput)
    assert _canon(rust.to_dict()) == _canon(py_dict)


def test_oracle_input_from_netlist_empty():
    """Edge: an empty netlist round-trips to empty dict lists."""
    netlist = Netlist(components=[], nets=[])
    py_dict = _oracle_netlist_to_oracle_dict(netlist)
    rust = ORACLE_INPUT.from_netlist(netlist)
    assert rust.to_dict() == {"nets": [], "components": []}
    assert _canon(rust.to_dict()) == _canon(py_dict)


def test_oracle_input_pins_are_refs_in_order_no_dedup():
    """Pins are `[ref for ref, _ in net.pins]` — component refs in pin order,
    duplicates preserved (the marshaler does NOT dedup, unlike the DRC
    nets_from_list)."""
    c1 = Component(ref="C1", footprint="0805", bounds=(2.0, 1.5))
    net = Net(name="VCC", pins=[("C1", "1"), ("C1", "2"), ("C1", "3")])
    nl = Netlist(components=[c1], nets=[net])
    py_dict = _oracle_netlist_to_oracle_dict(nl)
    rust = ORACLE_INPUT.from_netlist(nl)
    assert rust.to_dict()["nets"][0]["pins"] == ["C1", "C1", "C1"]
    assert _canon(rust.to_dict()) == _canon(py_dict)


def test_oracle_input_component_order_preserved():
    """The components list preserves netlist component order (the extractor
    relies on 1:1 alignment with positions rows)."""
    netlist = _make_netlist()
    rust = ORACLE_INPUT.from_netlist(netlist)
    refs = [c["ref"] for c in rust.to_dict()["components"]]
    assert refs == ["C1", "R1", "U1"]
    assert [c.ref for c in netlist.components] == ["C1", "R1", "U1"]


def test_oracle_input_component_shape_no_voltage():
    """Each component dict carries exactly ref/footprint/width/height — no
    'voltage' key (extract_netlist defaults it to 0.0 on the Rust side)."""
    netlist = _make_netlist()
    rust = ORACLE_INPUT.from_netlist(netlist)
    for cd in rust.to_dict()["components"]:
        assert set(cd.keys()) == {"ref", "footprint", "width", "height"}


# ---------------------------------------------------------------------------
# Differential — OracleOutput.from_state
# ---------------------------------------------------------------------------


def test_oracle_output_from_state_matches_oracle():
    """G1/G2: OracleOutput.from_state(state, netlist, board).to_dict() must be
    bit-identical to the pinned _placement_to_oracle_dict output."""
    state = _make_state()
    netlist = _make_netlist()
    board = _make_board()
    py_dict = _oracle_placement_to_oracle_dict(state, netlist, board)
    rust = ORACLE_OUTPUT.from_state(state, netlist, board)
    assert isinstance(rust, _tdrc.OracleOutput)
    assert _canon(rust.to_dict()) == _canon(py_dict)


def test_oracle_output_from_state_float32_upcast_is_exact():
    """The float32 → float64 upcast (`np.asarray(dtype=np.float64)`) is exact
    and the flattened row-major order must match the oracle bit-for-bit."""
    rng = np.random.default_rng(7)
    positions = rng.standard_normal((5, 2)).astype(np.float32)
    state = PlacementState(positions=positions, rotation_logits=np.zeros((5, 4), dtype=np.float32))
    netlist = _make_netlist()
    board = _make_board()
    py_dict = _oracle_placement_to_oracle_dict(state, netlist, board)
    rust = ORACLE_OUTPUT.from_state(state, netlist, board)
    assert _canon(rust.to_dict()) == _canon(py_dict)


def test_oracle_output_from_state_float64_direct():
    """A float64 positions array passes through unchanged (no copy/upcast)."""
    state = _make_state(dtype=np.float64)
    netlist = _make_netlist()
    board = _make_board()
    py_dict = _oracle_placement_to_oracle_dict(state, netlist, board)
    rust = ORACLE_OUTPUT.from_state(state, netlist, board)
    assert _canon(rust.to_dict()) == _canon(py_dict)


def test_oracle_output_from_state_empty_positions():
    """Edge: an empty positions array produces an empty flat list, with refs
    / board dims still present."""
    state = PlacementState(positions=np.zeros((0, 2), dtype=np.float32),
                           rotation_logits=np.zeros((0, 4), dtype=np.float32))
    netlist = Netlist(components=[], nets=[])
    board = _make_board()
    py_dict = _oracle_placement_to_oracle_dict(state, netlist, board)
    rust = ORACLE_OUTPUT.from_state(state, netlist, board)
    assert rust.to_dict() == {
        "positions": [],
        "component_refs": [],
        "board_width_mm": 100.0,
        "board_height_mm": 80.0,
    }
    assert _canon(rust.to_dict()) == _canon(py_dict)
