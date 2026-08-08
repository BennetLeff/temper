"""Tests for core.power_topology module."""

import pytest

from temper_placer.core.power_topology import (
    IPC2221Rule,
    PowerDeliveryStrategy,
    PowerDistributionTree,
    PowerRailSpec,
    TemperPowerTopology,
)


class TestPowerRailSpec:
    """Tests for PowerRailSpec."""

    def test_required_trace_width_small_current(self):
        rail = PowerRailSpec(
            net_name="+3V3",
            max_current_a=0.5,
            voltage_v=3.3,
            source_component="U_REG",
            sink_components=("U_MCU",),
        )
        # width(mm) = current(A) * 0.15 + 0.1
        expected = 0.5 * 0.15 + 0.1
        assert rail.required_trace_width() == pytest.approx(expected)

    def test_required_trace_width_large_current(self):
        rail = PowerRailSpec(
            net_name="+15V",
            max_current_a=5.0,
            voltage_v=15.0,
            source_component="U_15V",
            sink_components=("U_GATE",),
        )
        expected = 5.0 * 0.15 + 0.1
        assert rail.required_trace_width() == pytest.approx(expected)

    def test_delivery_strategy_plane(self):
        rail = PowerRailSpec(
            net_name="+15V",
            max_current_a=5.0,
            voltage_v=15.0,
            source_component="U_15V",
            sink_components=("U_GATE",),
        )
        assert rail.delivery_strategy() == PowerDeliveryStrategy.PLANE

    def test_delivery_strategy_wide_trace(self):
        rail = PowerRailSpec(
            net_name="+5V",
            max_current_a=2.0,
            voltage_v=5.0,
            source_component="U_5V",
            sink_components=("U_3V3",),
        )
        assert rail.delivery_strategy() == PowerDeliveryStrategy.WIDE_TRACE

    def test_delivery_strategy_standard(self):
        rail = PowerRailSpec(
            net_name="+3V3",
            max_current_a=0.5,
            voltage_v=3.3,
            source_component="U_REG",
            sink_components=("U_MCU",),
        )
        assert rail.delivery_strategy() == PowerDeliveryStrategy.STANDARD_TRACE

    def test_delivery_strategy_at_boundary(self):
        # Exactly at 3.0A -> PLANE
        rail = PowerRailSpec(
            net_name="+3V",
            max_current_a=3.0,
            voltage_v=3.0,
            source_component="U_BIG",
            sink_components=("U_LOAD",),
        )
        assert rail.delivery_strategy() == PowerDeliveryStrategy.PLANE

    def test_delivery_strategy_at_one_amp(self):
        # Exactly at 1.0A -> WIDE_TRACE
        rail = PowerRailSpec(
            net_name="+1V",
            max_current_a=1.0,
            voltage_v=1.0,
            source_component="U_MED",
            sink_components=("U_LOAD",),
        )
        assert rail.delivery_strategy() == PowerDeliveryStrategy.WIDE_TRACE


class TestPowerDistributionTree:
    """Tests for PowerDistributionTree."""

    def _make_tree(self):
        """Build a small test tree: +5V -> (+3V3, VCC_BOOT)."""
        v33 = PowerRailSpec(
            net_name="+3V3",
            max_current_a=0.5,
            voltage_v=3.3,
            source_component="U_3V3",
            sink_components=("U_MCU",),
        )
        boot = PowerRailSpec(
            net_name="VCC_BOOT",
            max_current_a=0.1,
            voltage_v=15.0,
            source_component="U_GATE",
            sink_components=("U_GATE",),
        )
        v5 = PowerRailSpec(
            net_name="+5V",
            max_current_a=2.0,
            voltage_v=5.0,
            source_component="U_5V",
            sink_components=("U_3V3", "U_GATE"),
        )
        child1 = PowerDistributionTree(root=v33, children=())
        child2 = PowerDistributionTree(root=boot, children=())
        return PowerDistributionTree(root=v5, children=(child1, child2))

    def test_flatten(self):
        tree = self._make_tree()
        rails = tree.flatten()
        assert len(rails) == 3
        names = [r.net_name for r in rails]
        # DFS order: root, then children in order
        assert names == ["+5V", "+3V3", "VCC_BOOT"]

    def test_flatten_single_node(self):
        rail = PowerRailSpec(
            net_name="+15V",
            max_current_a=5.0,
            voltage_v=15.0,
            source_component="U_15V",
            sink_components=("U_GATE",),
        )
        tree = PowerDistributionTree(root=rail, children=())
        rails = tree.flatten()
        assert len(rails) == 1
        assert rails[0] is rail

    def test_find_rail_found(self):
        tree = self._make_tree()
        found = tree.find_rail("+3V3")
        assert found is not None
        assert found.net_name == "+3V3"

    def test_find_rail_root(self):
        tree = self._make_tree()
        found = tree.find_rail("+5V")
        assert found is not None
        assert found.net_name == "+5V"

    def test_find_rail_not_found(self):
        tree = self._make_tree()
        found = tree.find_rail("NONEXISTENT")
        assert found is None


class TestIPC2221Rule:
    """Tests for IPC2221Rule."""

    def test_trace_width_default(self):
        rule = IPC2221Rule()
        rail = PowerRailSpec(
            net_name="+5V",
            max_current_a=2.0,
            voltage_v=5.0,
            source_component="U_5V",
            sink_components=("U_LOAD",),
        )
        # For 1oz copper: same as rail.required_trace_width()
        expected = 2.0 * 0.15 + 0.1
        assert rule.trace_width(rail) == pytest.approx(expected)

    def test_trace_width_thicker_copper(self):
        rule = IPC2221Rule(copper_weight_oz=2.0)
        rail = PowerRailSpec(
            net_name="+5V",
            max_current_a=2.0,
            voltage_v=5.0,
            source_component="U_5V",
            sink_components=("U_LOAD",),
        )
        base = 2.0 * 0.15 + 0.1
        expected = base / (2.0**0.625)
        assert rule.trace_width(rail) == pytest.approx(expected)

    def test_route_strategy_delegates(self):
        rule = IPC2221Rule()
        rail = PowerRailSpec(
            net_name="+15V",
            max_current_a=5.0,
            voltage_v=15.0,
            source_component="U_15V",
            sink_components=("U_GATE",),
        )
        assert rule.route_strategy(rail) == PowerDeliveryStrategy.PLANE


class TestTemperPowerTopology:
    """Tests for TemperPowerTopology.create()."""

    def test_create_returns_tree(self):
        tree = TemperPowerTopology.create()
        assert isinstance(tree, PowerDistributionTree)

    def test_create_root(self):
        tree = TemperPowerTopology.create()
        assert tree.root.net_name == "+15V"
        assert tree.root.max_current_a == 5.0

    def test_create_specific_rails(self):
        tree = TemperPowerTopology.create()
        rails = tree.flatten()
        names = {r.net_name for r in rails}
        assert names == {"+15V", "+5V", "+3V3", "VCC_BOOT"}

    def test_create_delivery_strategies(self):
        tree = TemperPowerTopology.create()
        root = tree.root
        assert root.delivery_strategy() == PowerDeliveryStrategy.PLANE
        assert root.required_trace_width() == pytest.approx(5.0 * 0.15 + 0.1)


class TestPowerDeliveryStrategy:
    """Smoke test for enum values."""

    def test_enum_values(self):
        assert PowerDeliveryStrategy.PLANE.value == "plane"
        assert PowerDeliveryStrategy.WIDE_TRACE.value == "wide_trace"
        assert PowerDeliveryStrategy.STANDARD_TRACE.value == "trace"
