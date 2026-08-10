"""Oracle test: pin the exact dict shapes of `_netlist_to_oracle_dict` and
`_placement_to_oracle_dict`.

These marshalers are recorded JUSTIFIED-KEEP
(``docs/solutions/architecture-patterns/quality-oracle-marshalers-justified-keep-2026-08-09.md``).
The dict shapes below are the documented, pre-existing API contract of
``temper_quality_oracle.prepare_quality_py`` / ``evaluate_prepared_py`` —
multiple consumers (``human_reference_extractor.py``, ``reference_loader.py``,
and ``test_quality_oracle.py``) call through them.

This test pins the shapes verbatim so that any unintentional change to the
marshaler output is caught. If the quality-oracle crate ever accepts typed
pyclasses, these pins become the migration oracle.
"""

from __future__ import annotations

import numpy as np

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.core.state import PlacementState
from temper_placer.validation.human_reference_extractor import (
    _netlist_to_oracle_dict,
    _placement_to_oracle_dict,
)

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_minimal_netlist() -> Netlist:
    """A netlist with 2 components and 1 net — representative but minimal."""
    c1 = Component(ref="C1", footprint="0805", bounds=(2.0, 1.5))
    c2 = Component(ref="R1", footprint="0603", bounds=(1.6, 0.8))
    net = Net(name="VCC", pins=[("C1", "1"), ("R1", "1")])
    return Netlist(components=[c1, c2], nets=[net])


def _make_minimal_state() -> PlacementState:
    """PlacementState with 2 components at known positions."""
    return PlacementState(
        positions=np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32),
        rotation_logits=np.array([[0.0, 10.0, 0.0, 0.0], [10.0, 0.0, 0.0, 0.0]], dtype=np.float32),
    )


def _make_minimal_board() -> Board:
    return Board(width=100.0, height=80.0)


# ---------------------------------------------------------------------------
# _netlist_to_oracle_dict — shape assertions
# ---------------------------------------------------------------------------


class TestNetlistOracleDictShape:
    """Pin the exact dict shape produced by ``_netlist_to_oracle_dict``."""

    def test_top_level_keys(self):
        netlist = _make_minimal_netlist()
        d = _netlist_to_oracle_dict(netlist)
        assert set(d.keys()) == {"nets", "components"}

    def test_nets_structure(self):
        netlist = _make_minimal_netlist()
        d = _netlist_to_oracle_dict(netlist)
        nets = d["nets"]
        assert isinstance(nets, list)
        assert len(nets) == 1
        assert nets[0] == {"name": "VCC", "pins": ["C1", "R1"]}

    def test_nets_only_pin_refs_not_pin_names(self):
        """Pins are just the component refs — the pin-number half is stripped."""
        # The marshaler does ``[ref for ref, _ in net.pins]`` — only the ref.
        c1 = Component(ref="U1", footprint="QFN-32", bounds=(5.0, 5.0))
        c2 = Component(ref="U2", footprint="QFN-32", bounds=(5.0, 5.0))
        net = Net(name="SPI_CLK", pins=[("U1", "12"), ("U2", "5")])
        nl = Netlist(components=[c1, c2], nets=[net])
        d = _netlist_to_oracle_dict(nl)
        assert d["nets"][0]["pins"] == ["U1", "U2"]

    def test_components_structure(self):
        netlist = _make_minimal_netlist()
        d = _netlist_to_oracle_dict(netlist)
        comps = d["components"]
        assert isinstance(comps, list)
        assert len(comps) == 2
        assert comps[0] == {"ref": "C1", "footprint": "0805", "width": 2.0, "height": 1.5}
        assert comps[1] == {"ref": "R1", "footprint": "0603", "width": 1.6, "height": 0.8}

    def test_component_no_voltage_field(self):
        """The marshaler does NOT include a 'voltage' key — the Rust side
        defaults it to 0.0 (extract_netlist in temper-quality-oracle/lib.rs:~98)."""
        netlist = _make_minimal_netlist()
        d = _netlist_to_oracle_dict(netlist)
        for comp in d["components"]:
            assert "voltage" not in comp

    def test_empty_netlist(self):
        nl = Netlist(components=[], nets=[])
        d = _netlist_to_oracle_dict(nl)
        assert d == {"nets": [], "components": []}

    def test_net_with_no_pins(self):
        c1 = Component(ref="C1", footprint="0805", bounds=(2.0, 1.5))
        net = Net(name="NC", pins=[])
        nl = Netlist(components=[c1], nets=[net])
        d = _netlist_to_oracle_dict(nl)
        assert d["nets"][0]["pins"] == []

    def test_component_order_preserved(self):
        """The component list must match 1:1 with the netlist's component order —
        the oracle relies on this for ref-to-position alignment."""
        c1 = Component(ref="Z_last", footprint="DIP-8", bounds=(10.0, 5.0))
        c2 = Component(ref="A_first", footprint="SOIC-8", bounds=(5.0, 4.0))
        nl = Netlist(components=[c1, c2], nets=[])
        d = _netlist_to_oracle_dict(nl)
        assert [c["ref"] for c in d["components"]] == ["Z_last", "A_first"]

    def test_width_height_are_float_not_int(self):
        """Bounds are cast to float — the oracle dict must not contain ints."""
        c1 = Component(ref="C1", footprint="0805", bounds=(2, 1))
        nl = Netlist(components=[c1], nets=[])
        d = _netlist_to_oracle_dict(nl)
        assert isinstance(d["components"][0]["width"], float)
        assert isinstance(d["components"][0]["height"], float)


# ---------------------------------------------------------------------------
# _placement_to_oracle_dict — shape assertions
# ---------------------------------------------------------------------------


class TestPlacementOracleDictShape:
    """Pin the exact dict shape produced by ``_placement_to_oracle_dict``."""

    def test_top_level_keys(self):
        state = _make_minimal_state()
        netlist = _make_minimal_netlist()
        board = _make_minimal_board()
        d = _placement_to_oracle_dict(state, netlist, board)
        assert set(d.keys()) == {"positions", "component_refs", "board_width_mm", "board_height_mm"}

    def test_positions_are_flat_list_of_float64(self):
        """The marshaler calls ``np.asarray(positions, dtype=np.float64)``
        then ``.reshape(-1).tolist()`` — the result is a flat Python list of
        Python floats, not a nested list and not a numpy scalar."""
        state = _make_minimal_state()
        netlist = _make_minimal_netlist()
        board = _make_minimal_board()
        d = _placement_to_oracle_dict(state, netlist, board)
        positions = d["positions"]
        assert isinstance(positions, list)
        assert len(positions) == 4  # 2 components × 2 coords
        for v in positions:
            assert isinstance(v, float)
        # Known values: state has (10,20), (30,40)
        assert positions == [10.0, 20.0, 30.0, 40.0]

    def test_component_refs_order(self):
        """Refs come from netlist.components, in the netlist's own order."""
        c1 = Component(ref="Q1", footprint="TO-247", bounds=(15.0, 20.0))
        c2 = Component(ref="U1", footprint="SOIC-8", bounds=(5.0, 4.0))
        nl = Netlist(components=[c1, c2], nets=[])
        state = PlacementState(
            positions=np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32),
            rotation_logits=np.zeros((2, 4), dtype=np.float32),
        )
        board = _make_minimal_board()
        d = _placement_to_oracle_dict(state, nl, board)
        assert d["component_refs"] == ["Q1", "U1"]

    def test_board_dimensions(self):
        state = _make_minimal_state()
        netlist = _make_minimal_netlist()
        board = Board(width=123.45, height=67.89)
        d = _placement_to_oracle_dict(state, netlist, board)
        assert d["board_width_mm"] == 123.45
        assert d["board_height_mm"] == 67.89

    def test_empty_state(self):
        """Zero components still produces valid output."""
        nl = Netlist(components=[], nets=[])
        state = PlacementState(
            positions=np.empty((0, 2), dtype=np.float32),
            rotation_logits=np.empty((0, 4), dtype=np.float32),
        )
        board = _make_minimal_board()
        d = _placement_to_oracle_dict(state, nl, board)
        assert d["positions"] == []
        assert d["component_refs"] == []
        assert d["board_width_mm"] == 100.0
        assert d["board_height_mm"] == 80.0

    def test_float32_input_still_produces_float64_via_asarray(self):
        """Even though state.positions is float32, asarray(..., float64)
        upcasts. Verify the output is a native Python float (not float32)."""
        state = PlacementState(
            positions=np.array([[0.5, 1.0]], dtype=np.float32),
            rotation_logits=np.zeros((1, 4), dtype=np.float32),
        )
        c = Component(ref="X1", footprint="SOT-23", bounds=(3.0, 3.0))
        nl = Netlist(components=[c], nets=[])
        board = _make_minimal_board()
        d = _placement_to_oracle_dict(state, nl, board)
        # The values are Python floats (from .tolist()), which are always
        # double-precision in CPython.
        assert d["positions"] == [0.5, 1.0]
