"""
TDD Tests for PowerPlaneStage.

Tests the stage that identifies power/ground nets and marks them for
plane connection instead of trace routing.
"""

import pytest
from dataclasses import replace

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.layer_assignment import LayerAssignment
from temper_placer.core.netlist import Net, Netlist, Component, Pin


# Test fixtures
@pytest.fixture
def simple_netlist():
    """Create a simple netlist with power and signal nets."""
    nets = [
        Net(name="GND", pins=[("U1", "1"), ("U2", "1")]),
        Net(name="+5V", pins=[("U1", "2"), ("U2", "2")]),
        Net(name="SPI_CLK", pins=[("U1", "3"), ("U2", "3")]),
        Net(name="GATE_HI", pins=[("U1", "4"), ("U2", "4")]),
    ]
    components = [
        Component(
            ref="U1",
            footprint="Package_SO:SOIC-8",
            bounds=(5.0, 4.0),
            pins=[
                Pin(name="1", number="1", position=(0, 0)),
                Pin(name="2", number="2", position=(1, 0)),
                Pin(name="3", number="3", position=(2, 0)),
                Pin(name="4", number="4", position=(3, 0)),
            ],
        ),
        Component(
            ref="U2",
            footprint="Package_SO:SOIC-8",
            bounds=(5.0, 4.0),
            pins=[
                Pin(name="1", number="1", position=(0, 0)),
                Pin(name="2", number="2", position=(1, 0)),
                Pin(name="3", number="3", position=(2, 0)),
                Pin(name="4", number="4", position=(3, 0)),
            ],
        ),
    ]
    return Netlist(nets=nets, components=components)


@pytest.fixture
def state_with_layer_assignments(simple_netlist):
    """Create a BoardState with layer assignments."""
    assignments = [
        LayerAssignment(net_name="GND", layer=1, is_plane=False),
        LayerAssignment(net_name="+5V", layer=2, is_plane=False),
        LayerAssignment(net_name="SPI_CLK", layer=0, is_plane=False),
        LayerAssignment(net_name="GATE_HI", layer=0, is_plane=False),
    ]
    return BoardState(
        netlist=simple_netlist,
        layer_assignments=tuple(assignments),
    )


class TestPowerPlaneStageIdentification:
    """Test that power nets are correctly identified."""

    def test_plane_nets_marked_as_plane(self, state_with_layer_assignments):
        """Power nets should be marked as plane connections."""
        from temper_placer.deterministic.stages.power_plane import PowerPlaneStage

        stage = PowerPlaneStage(plane_nets=frozenset(["GND", "+5V"]))
        result = stage.run(state_with_layer_assignments)

        # Build lookup from result
        assignments = {a.net_name: a for a in result.layer_assignments}

        assert assignments["GND"].is_plane is True
        assert assignments["+5V"].is_plane is True

    def test_signal_nets_not_marked_as_plane(self, state_with_layer_assignments):
        """Signal nets should NOT be marked as plane connections."""
        from temper_placer.deterministic.stages.power_plane import PowerPlaneStage

        stage = PowerPlaneStage(plane_nets=frozenset(["GND", "+5V"]))
        result = stage.run(state_with_layer_assignments)

        assignments = {a.net_name: a for a in result.layer_assignments}

        assert assignments["SPI_CLK"].is_plane is False
        assert assignments["GATE_HI"].is_plane is False

    def test_partial_plane_nets(self, state_with_layer_assignments):
        """Only specified nets should be marked as planes."""
        from temper_placer.deterministic.stages.power_plane import PowerPlaneStage

        # Only mark GND, not +5V
        stage = PowerPlaneStage(plane_nets=frozenset(["GND"]))
        result = stage.run(state_with_layer_assignments)

        assignments = {a.net_name: a for a in result.layer_assignments}

        assert assignments["GND"].is_plane is True
        assert assignments["+5V"].is_plane is False


class TestPowerPlaneStageLayerMapping:
    """Test that plane nets are assigned to correct layers."""

    def test_ground_assigned_to_in1(self, state_with_layer_assignments):
        """Ground nets should be assigned to In1.Cu (layer 1)."""
        from temper_placer.deterministic.stages.power_plane import PowerPlaneStage

        stage = PowerPlaneStage(plane_nets=frozenset(["GND"]), plane_layers={"GND": 1})
        result = stage.run(state_with_layer_assignments)

        assignments = {a.net_name: a for a in result.layer_assignments}
        assert assignments["GND"].layer == 1

    def test_power_assigned_to_in2(self, state_with_layer_assignments):
        """Power nets should be assigned to In2.Cu (layer 2)."""
        from temper_placer.deterministic.stages.power_plane import PowerPlaneStage

        stage = PowerPlaneStage(plane_nets=frozenset(["+5V"]), plane_layers={"+5V": 2})
        result = stage.run(state_with_layer_assignments)

        assignments = {a.net_name: a for a in result.layer_assignments}
        assert assignments["+5V"].layer == 2

    def test_default_layer_is_in1(self, state_with_layer_assignments):
        """Plane nets without explicit layer mapping should default to In1.Cu."""
        from temper_placer.deterministic.stages.power_plane import PowerPlaneStage

        stage = PowerPlaneStage(
            plane_nets=frozenset(["GND"]),
            plane_layers={},  # No explicit mapping
        )
        result = stage.run(state_with_layer_assignments)

        assignments = {a.net_name: a for a in result.layer_assignments}
        assert assignments["GND"].layer == 1  # Default to In1.Cu


class TestPowerPlaneStageIntegration:
    """Integration tests for power plane stage."""

    def test_preserves_non_plane_assignments(self, state_with_layer_assignments):
        """Non-plane net assignments should be preserved."""
        from temper_placer.deterministic.stages.power_plane import PowerPlaneStage

        stage = PowerPlaneStage(plane_nets=frozenset(["GND"]))
        result = stage.run(state_with_layer_assignments)

        assignments = {a.net_name: a for a in result.layer_assignments}

        # Signal nets should retain original layer
        assert assignments["SPI_CLK"].layer == 0
        assert assignments["GATE_HI"].layer == 0

    def test_unknown_plane_nets_ignored(self, state_with_layer_assignments):
        """Plane nets not in netlist should be silently ignored."""
        from temper_placer.deterministic.stages.power_plane import PowerPlaneStage

        stage = PowerPlaneStage(plane_nets=frozenset(["GND", "NONEXISTENT_NET"]))
        result = stage.run(state_with_layer_assignments)

        # Should not raise, should process GND normally
        assignments = {a.net_name: a for a in result.layer_assignments}
        assert assignments["GND"].is_plane is True

    def test_empty_plane_nets_no_changes(self, state_with_layer_assignments):
        """Empty plane_nets should not modify any assignments."""
        from temper_placer.deterministic.stages.power_plane import PowerPlaneStage

        stage = PowerPlaneStage(plane_nets=frozenset())
        result = stage.run(state_with_layer_assignments)

        # All nets should remain non-plane
        for assignment in result.layer_assignments:
            assert assignment.is_plane is False

    def test_handles_missing_layer_assignments(self, simple_netlist):
        """Should handle state without layer_assignments gracefully."""
        from temper_placer.deterministic.stages.power_plane import PowerPlaneStage

        state = BoardState(netlist=simple_netlist, layer_assignments=None)
        stage = PowerPlaneStage(plane_nets=frozenset(["GND"]))

        result = stage.run(state)

        # Should create new assignments
        assert result.layer_assignments is not None
        assignments = {a.net_name: a for a in result.layer_assignments}
        assert assignments["GND"].is_plane is True


class TestPowerPlaneStageName:
    """Test stage metadata."""

    def test_stage_name(self):
        """Stage should have correct name."""
        from temper_placer.deterministic.stages.power_plane import PowerPlaneStage

        stage = PowerPlaneStage(plane_nets=frozenset())
        assert stage.name == "power_plane"


class TestTemperBoardPlaneNets:
    """Tests specific to Temper board configuration."""

    def test_all_temper_plane_nets(self):
        """Verify all Temper board plane nets are identified."""
        from temper_placer.deterministic.stages.power_plane import TEMPER_PLANE_NETS

        expected = {
            # Ground nets -> In1.Cu
            "GND",
            "PGND",
            "CGND",
            # Power rails -> In2.Cu
            "+15V",
            "+5V",
            "+3V3",
            # High current -> F.Cu pours (not inner planes but still plane-connected)
            "DC_BUS+",
            "DC_BUS-",
            "SW_NODE",
            # ACMains -> F.Cu copper pours
            "AC_L",
            "AC_N",
            "PE",
        }

        assert TEMPER_PLANE_NETS == expected

    def test_temper_plane_layer_mapping(self):
        """Verify Temper board layer mappings."""
        from temper_placer.deterministic.stages.power_plane import TEMPER_PLANE_LAYERS

        # Ground nets to In1.Cu (layer 1)
        assert TEMPER_PLANE_LAYERS["GND"] == 1
        assert TEMPER_PLANE_LAYERS["PGND"] == 1
        assert TEMPER_PLANE_LAYERS["CGND"] == 1

        # Power nets to In2.Cu (layer 2)
        assert TEMPER_PLANE_LAYERS["+15V"] == 2
        assert TEMPER_PLANE_LAYERS["+5V"] == 2
        assert TEMPER_PLANE_LAYERS["+3V3"] == 2

        # HV nets stay on F.Cu (layer 0) for copper pours
        assert TEMPER_PLANE_LAYERS["DC_BUS+"] == 0
        assert TEMPER_PLANE_LAYERS["DC_BUS-"] == 0
        assert TEMPER_PLANE_LAYERS["SW_NODE"] == 0
