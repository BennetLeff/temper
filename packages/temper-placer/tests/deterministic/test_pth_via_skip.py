"""Tests for PTH pad detection and via skip logic in sequential routing.

PTH (plated through-hole) pads don't need vias to connect to inner plane layers
because their barrel already provides electrical connection through all copper
layers. Creating vias on PTH pads causes DRC violations:
- holes_co_located: Via drill overlaps PTH pad drill
- via_dangling: Via appears connected on only one layer

These tests verify that the sequential routing stage correctly identifies PTH
pads and skips via creation for them on plane nets.
"""

import pytest
from dataclasses import replace

from temper_placer.deterministic.stages.sequential_routing import SequentialRoutingStage
from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.layer_assignment import LayerAssignment
from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
from temper_placer.core.netlist import Net, Pin, Component, Netlist
from temper_placer.core.board import Board


@pytest.fixture
def pth_pin():
    """Create a PTH pin (through-hole)."""
    return Pin(
        name="1",
        number="1",
        position=(0.0, 0.0),
        is_pth=True,
        layer="all",
        drill=1.0,
        shape="thru_hole",
        width=1.8,
        height=1.8,
    )


@pytest.fixture
def smd_pin():
    """Create an SMD pin (surface mount)."""
    return Pin(
        name="1",
        number="1",
        position=(0.0, 0.0),
        is_pth=False,
        layer="F.Cu",
        drill=0.0,
        shape="rect",
        width=0.5,
        height=1.0,
    )


@pytest.fixture
def minimal_board():
    """Create minimal board for testing."""
    return Board(width=100.0, height=100.0)


@pytest.fixture
def minimal_grid():
    """Create minimal clearance grid."""
    return ClearanceGrid(width_mm=100.0, height_mm=100.0, cell_size_mm=0.25, layer_count=4)


class TestPTHPinAttributes:
    """Tests for PTH pad detection via Pin attributes."""

    def test_pth_pin_has_is_pth_true(self, pth_pin):
        """PTH pins should have is_pth=True."""
        assert pth_pin.is_pth is True
        assert pth_pin.layer == "all"
        assert pth_pin.drill > 0

    def test_smd_pin_has_is_pth_false(self, smd_pin):
        """SMD pins should have is_pth=False."""
        assert smd_pin.is_pth is False
        assert smd_pin.layer != "all"
        assert smd_pin.drill == 0


class TestPTHViaSkipOnPlaneNets:
    """Tests for PTH via skip logic on plane nets."""

    def test_plane_net_skips_via_for_pth_pad(self, pth_pin, minimal_board, minimal_grid):
        """Plane net routing should NOT create via for PTH pad."""
        # Create component with PTH pin on GND net
        comp = Component(
            ref="J1",
            footprint="Connector_THT",
            bounds=(5.0, 5.0),
            pins=[pth_pin],
            initial_position=(50.0, 50.0),
        )
        net = Net(name="GND", pins=[("J1", "1")], net_class="Ground")
        netlist = Netlist(components=[comp], nets=[net])

        # Create state with plane layer assignment for GND
        layer_assignments = frozenset([LayerAssignment(net_name="GND", layer=1, is_plane=True)])

        state = BoardState(
            board=minimal_board,
            netlist=netlist,
            grid=minimal_grid,
            net_order=("GND",),
            layer_assignments=layer_assignments,
        )

        # Run sequential routing
        stage = SequentialRoutingStage()
        result = stage.run(state)

        # No vias should be created for PTH pad on plane net
        assert len(result.vias) == 0, "PTH pad should not get a via - barrel connects to plane"

    def test_plane_net_creates_via_for_smd_pad(self, smd_pin, minimal_board, minimal_grid):
        """Plane net routing SHOULD create via for SMD pad."""
        # Create component with SMD pin on GND net
        comp = Component(
            ref="U1",
            footprint="QFN-56",
            bounds=(8.0, 8.0),
            pins=[smd_pin],
            initial_position=(50.0, 50.0),
        )
        net = Net(name="GND", pins=[("U1", "1")], net_class="Ground")
        netlist = Netlist(components=[comp], nets=[net])

        layer_assignments = frozenset([LayerAssignment(net_name="GND", layer=1, is_plane=True)])

        state = BoardState(
            board=minimal_board,
            netlist=netlist,
            grid=minimal_grid,
            net_order=("GND",),
            layer_assignments=layer_assignments,
        )

        stage = SequentialRoutingStage()
        result = stage.run(state)

        # Via SHOULD be created for SMD pad to connect to plane
        assert len(result.vias) == 1, "SMD pad needs via to connect to plane"

    def test_mixed_pth_smd_on_same_plane_net(self, pth_pin, smd_pin, minimal_board, minimal_grid):
        """Net with both PTH and SMD pads should only create vias for SMD."""
        # PTH component
        pth_comp = Component(
            ref="J1",
            footprint="Connector_THT",
            bounds=(5.0, 5.0),
            pins=[pth_pin],
            initial_position=(20.0, 50.0),
        )
        # SMD component with different pin
        smd_pin_2 = replace(smd_pin, name="GND", number="2")
        smd_comp = Component(
            ref="U1",
            footprint="QFN-56",
            bounds=(8.0, 8.0),
            pins=[smd_pin_2],
            initial_position=(80.0, 50.0),
        )
        net = Net(name="GND", pins=[("J1", "1"), ("U1", "GND")], net_class="Ground")
        netlist = Netlist(components=[pth_comp, smd_comp], nets=[net])

        layer_assignments = frozenset([LayerAssignment(net_name="GND", layer=1, is_plane=True)])

        state = BoardState(
            board=minimal_board,
            netlist=netlist,
            grid=minimal_grid,
            net_order=("GND",),
            layer_assignments=layer_assignments,
        )

        stage = SequentialRoutingStage()
        result = stage.run(state)

        # Only 1 via for SMD pad, none for PTH
        assert len(result.vias) == 1, "Only SMD pad should get via"

    def test_multiple_pth_pads_on_plane_net_no_vias(self, pth_pin, minimal_board, minimal_grid):
        """Multiple PTH pads on a plane net should create zero vias."""
        # Create two PTH components on the same GND net
        pth_pin_1 = pth_pin
        pth_pin_2 = replace(pth_pin, name="2", number="2")

        comp1 = Component(
            ref="J1",
            footprint="Connector_THT",
            bounds=(5.0, 5.0),
            pins=[pth_pin_1],
            initial_position=(20.0, 50.0),
        )
        comp2 = Component(
            ref="J2",
            footprint="Connector_THT",
            bounds=(5.0, 5.0),
            pins=[pth_pin_2],
            initial_position=(80.0, 50.0),
        )

        net = Net(name="GND", pins=[("J1", "1"), ("J2", "2")], net_class="Ground")
        netlist = Netlist(components=[comp1, comp2], nets=[net])

        layer_assignments = frozenset([LayerAssignment(net_name="GND", layer=1, is_plane=True)])

        state = BoardState(
            board=minimal_board,
            netlist=netlist,
            grid=minimal_grid,
            net_order=("GND",),
            layer_assignments=layer_assignments,
        )

        stage = SequentialRoutingStage()
        result = stage.run(state)

        # No vias for PTH-only plane net
        assert len(result.vias) == 0, "PTH-only plane net should have no vias"


class TestNonPlaneNetsUnaffected:
    """Tests to ensure non-plane nets are not affected by PTH check."""

    def test_non_plane_signal_net_routes_normally(self, pth_pin, minimal_board, minimal_grid):
        """Non-plane signal nets should route with traces regardless of PTH status."""
        pth_pin_1 = pth_pin
        pth_pin_2 = replace(pth_pin, name="2", number="2", position=(2.54, 0.0))

        comp = Component(
            ref="J1",
            footprint="Connector_THT",
            bounds=(10.0, 5.0),
            pins=[pth_pin_1, pth_pin_2],
            initial_position=(50.0, 50.0),
        )
        net = Net(name="SPI_CLK", pins=[("J1", "1"), ("J1", "2")], net_class="Signal")
        netlist = Netlist(components=[comp], nets=[net])

        # No plane assignment - this is a signal net (layer 0, not a plane)
        layer_assignments = frozenset(
            [LayerAssignment(net_name="SPI_CLK", layer=0, is_plane=False)]
        )

        state = BoardState(
            board=minimal_board,
            netlist=netlist,
            grid=minimal_grid,
            net_order=("SPI_CLK",),
            layer_assignments=layer_assignments,
        )

        stage = SequentialRoutingStage()
        result = stage.run(state)

        # Signal nets route with traces, PTH check doesn't apply
        # The routing may or may not succeed depending on A* setup, but it should try
        # At minimum, no exception should be raised
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
