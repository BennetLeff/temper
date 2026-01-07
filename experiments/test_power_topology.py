"""
TDD Tests for Power Distribution Topology (Task temper-zy08)

Tests power rail modeling and routing strategy selection.
Following functional programming principles with immutable types.
"""

import pytest
from temper_placer.core.power_topology import (
    PowerDeliveryStrategy,
    PowerRailSpec,
    PowerDistributionTree,
    IPC2221Rule,
    TemperPowerTopology,
)


# ============================================================================
# Phase 1: Pure Function Tests
# ============================================================================


def test_power_rail_required_trace_width_2a():
    """GIVEN 2A rail
    WHEN calculating trace width
    THEN returns 0.4mm (2 * 0.15 + 0.1)"""
    rail = PowerRailSpec(
        net_name="+5V",
        max_current_a=2.0,
        voltage_v=5.0,
        source_component="U_5V",
        sink_components=("U_3V3",),
    )
    assert abs(rail.required_trace_width() - 0.4) < 0.01


def test_power_rail_required_trace_width_5a():
    """GIVEN 5A rail (high current)
    WHEN calculating trace width
    THEN returns 0.85mm (5 * 0.15 + 0.1)"""
    rail = PowerRailSpec(
        net_name="+15V",
        max_current_a=5.0,
        voltage_v=15.0,
        source_component="U_15V",
        sink_components=("U_GATE", "U_5V"),
    )
    assert abs(rail.required_trace_width() - 0.85) < 0.01


def test_power_rail_required_trace_width_low_current():
    """GIVEN 0.1A rail (very low current)
    WHEN calculating trace width
    THEN returns 0.115mm (0.1 * 0.15 + 0.1)"""
    rail = PowerRailSpec(
        net_name="VCC_BOOT",
        max_current_a=0.1,
        voltage_v=15.0,
        source_component="U_GATE",
        sink_components=("U_GATE",),
    )
    assert abs(rail.required_trace_width() - 0.115) < 0.01


def test_power_rail_delivery_strategy_plane():
    """GIVEN 5A rail (>3A)
    WHEN determining strategy
    THEN returns PLANE"""
    rail = PowerRailSpec("+15V", 5.0, 15.0, "U_15V", ())
    assert rail.delivery_strategy() == PowerDeliveryStrategy.PLANE


def test_power_rail_delivery_strategy_wide_trace():
    """GIVEN 2A rail (>=1A, <3A)
    WHEN determining strategy
    THEN returns WIDE_TRACE"""
    rail = PowerRailSpec("+5V", 2.0, 5.0, "U_5V", ())
    assert rail.delivery_strategy() == PowerDeliveryStrategy.WIDE_TRACE


def test_power_rail_delivery_strategy_standard_trace():
    """GIVEN 0.5A rail (<1A)
    WHEN determining strategy
    THEN returns STANDARD_TRACE"""
    rail = PowerRailSpec("+3V3", 0.5, 3.3, "U_3V3", ())
    assert rail.delivery_strategy() == PowerDeliveryStrategy.STANDARD_TRACE


def test_power_rail_delivery_strategy_boundary_3a():
    """GIVEN exactly 3A rail (boundary case)
    WHEN determining strategy
    THEN returns PLANE (>=3A)"""
    rail = PowerRailSpec("+12V", 3.0, 12.0, "U_12V", ())
    assert rail.delivery_strategy() == PowerDeliveryStrategy.PLANE


def test_power_rail_delivery_strategy_boundary_1a():
    """GIVEN exactly 1A rail (boundary case)
    WHEN determining strategy
    THEN returns WIDE_TRACE (>=1A)"""
    rail = PowerRailSpec("+5V", 1.0, 5.0, "U_5V", ())
    assert rail.delivery_strategy() == PowerDeliveryStrategy.WIDE_TRACE


def test_power_rail_immutable():
    """GIVEN PowerRailSpec instance
    WHEN attempting to modify
    THEN raises FrozenInstanceError"""
    rail = PowerRailSpec("+5V", 2.0, 5.0, "U_5V", ())
    with pytest.raises(Exception):  # dataclass frozen error
        rail.max_current_a = 3.0  # type: ignore[misc]


# ============================================================================
# Phase 2: Temper-Specific Power Topology
# ============================================================================
# Phase 2: Temper-Specific Power Topology
# ============================================================================


def test_power_tree_flattens_correctly():
    """GIVEN tree: +15V -> (+5V -> +3V3, VCC_BOOT)
    WHEN flattening
    THEN returns all 4 rails in DFS order"""
    tree = TemperPowerTopology.create()
    flat = tree.flatten()

    assert len(flat) == 4
    net_names = [r.net_name for r in flat]
    assert "+15V" in net_names
    assert "+5V" in net_names
    assert "+3V3" in net_names
    assert "VCC_BOOT" in net_names


def test_power_tree_finds_rail_root():
    """GIVEN tree with +15V at root
    WHEN searching for '+15V'
    THEN returns correct spec"""
    tree = TemperPowerTopology.create()
    rail = tree.find_rail("+15V")

    assert rail is not None
    assert rail.net_name == "+15V"
    assert rail.max_current_a == 5.0


def test_power_tree_finds_rail_leaf():
    """GIVEN tree with +3V3 as leaf node
    WHEN searching for '+3V3'
    THEN returns correct spec"""
    tree = TemperPowerTopology.create()
    rail = tree.find_rail("+3V3")

    assert rail is not None
    assert rail.net_name == "+3V3"
    assert rail.max_current_a == 0.5
    assert rail.source_component == "U_3V3"


def test_power_tree_finds_rail_not_found():
    """GIVEN tree without '+12V'
    WHEN searching for '+12V'
    THEN returns None"""
    tree = TemperPowerTopology.create()
    rail = tree.find_rail("+12V")

    assert rail is None


def test_temper_topology_v15_is_plane():
    """GIVEN Temper power topology
    WHEN checking +15V strategy
    THEN uses PLANE (5A > 3A threshold)"""
    tree = TemperPowerTopology.create()
    v15 = tree.find_rail("+15V")

    assert v15 is not None
    assert v15.delivery_strategy() == PowerDeliveryStrategy.PLANE


def test_temper_topology_v5_is_wide_trace():
    """GIVEN Temper power topology
    WHEN checking +5V strategy
    THEN uses WIDE_TRACE (2A in [1A, 3A] range)"""
    tree = TemperPowerTopology.create()
    v5 = tree.find_rail("+5V")

    assert v5 is not None
    assert v5.delivery_strategy() == PowerDeliveryStrategy.WIDE_TRACE


def test_temper_topology_v33_is_standard_trace():
    """GIVEN Temper power topology
    WHEN checking +3V3 strategy
    THEN uses STANDARD_TRACE (0.5A < 1A)"""
    tree = TemperPowerTopology.create()
    v33 = tree.find_rail("+3V3")

    assert v33 is not None
    assert v33.delivery_strategy() == PowerDeliveryStrategy.STANDARD_TRACE


def test_temper_topology_vcc_boot_is_standard_trace():
    """GIVEN Temper power topology
    WHEN checking VCC_BOOT strategy
    THEN uses STANDARD_TRACE (0.1A < 1A)"""
    tree = TemperPowerTopology.create()
    vcc_boot = tree.find_rail("VCC_BOOT")

    assert vcc_boot is not None
    assert vcc_boot.delivery_strategy() == PowerDeliveryStrategy.STANDARD_TRACE


# ============================================================================
# Phase 3: IPC-2221 Rule Engine
# ============================================================================
# Phase 3: IPC-2221 Rule Engine
# ============================================================================


def test_ipc2221_rule_1oz_copper():
    """GIVEN 1oz copper rule, 2A rail
    WHEN calculating trace width
    THEN returns 0.4mm"""
    rule = IPC2221Rule(copper_weight_oz=1.0)
    rail = PowerRailSpec("+5V", 2.0, 5.0, "U_5V", ())

    width = rule.trace_width(rail)
    assert abs(width - 0.4) < 0.01


def test_ipc2221_rule_2oz_copper_narrower():
    """GIVEN 2oz copper vs 1oz copper, same 2A rail
    WHEN calculating trace width
    THEN 2oz width < 1oz width (thicker copper carries more)"""
    rule_1oz = IPC2221Rule(copper_weight_oz=1.0)
    rule_2oz = IPC2221Rule(copper_weight_oz=2.0)
    rail = PowerRailSpec("+5V", 2.0, 5.0, "U_5V", ())

    width_1oz = rule_1oz.trace_width(rail)
    width_2oz = rule_2oz.trace_width(rail)

    assert width_2oz < width_1oz
    # 2oz should be ~60% of 1oz width (2^-0.625 ≈ 0.65)
    assert 0.5 < (width_2oz / width_1oz) < 0.7


def test_ipc2221_rule_route_strategy_delegates():
    """GIVEN IPC2221 rule
    WHEN determining route strategy
    THEN delegates to PowerRailSpec logic"""
    rule = IPC2221Rule()

    rail_plane = PowerRailSpec("+15V", 5.0, 15.0, "U", ())
    rail_wide = PowerRailSpec("+5V", 2.0, 5.0, "U", ())
    rail_std = PowerRailSpec("+3V3", 0.5, 3.3, "U", ())

    assert rule.route_strategy(rail_plane) == PowerDeliveryStrategy.PLANE
    assert rule.route_strategy(rail_wide) == PowerDeliveryStrategy.WIDE_TRACE
    assert rule.route_strategy(rail_std) == PowerDeliveryStrategy.STANDARD_TRACE


# ============================================================================
# Summary
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
