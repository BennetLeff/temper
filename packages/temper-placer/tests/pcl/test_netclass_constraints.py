"""Test CP-SAT netclass constraint generation using DesignRules."""
import pytest
from pathlib import Path


RULES_PATH = Path(__file__).parent.parent.parent / "configs" / "netclass_rules.yaml"


def _make_mock_component(ref: str, net_name: str = ""):
    """Create a minimal mock component with ref and a connected pin."""
    class MockPin:
        def __init__(self, number, component, net):
            self.number = number
            self.component = component
            self.net = net
    class MockComp:
        def __init__(self, ref, pins):
            self.ref = ref
            self.pins = pins
    class MockNet:
        def __init__(self, name, pins):
            self.name = name
            self.pins = pins

    pin = MockPin("1", ref, net_name)
    net = MockNet(net_name, [pin])
    comp = MockComp(ref, [pin])
    return comp, net


@pytest.fixture
def rules():
    from temper_placer.io.netclass_loader import load_netclass_rules
    return load_netclass_rules(RULES_PATH)


class TestResolveComponentNetClass:
    """Unit tests for _resolve_component_net_class."""

    def test_mixed_pins_returns_max_severity(self, rules):
        from temper_placer.placer.cp_sat.netclass_constraints import (
            _resolve_component_net_class,
        )

        class MockPin:
            def __init__(self, number, net):
                self.number = number
                self.component = "Q2"
                self.net = net

        class MockComp:
            def __init__(self, ref, pins):
                self.ref = ref
                self.pins = pins

        comp = MockComp(
            "Q2",
            [
                MockPin("1", "GATE_H"),    # Signal
                MockPin("2", "DC_BUS-"),   # HighVoltage
                MockPin("3", "SW_NODE"),   # Signal
            ],
        )
        result = _resolve_component_net_class(comp, None)
        assert result == "HighVoltage", (
            f"Expected HighVoltage (max severity across all pins), got {result}"
        )

    def test_all_signal_pins_returns_signal(self, rules):
        from temper_placer.placer.cp_sat.netclass_constraints import (
            _resolve_component_net_class,
        )

        class MockPin:
            def __init__(self, number, net):
                self.number = number
                self.component = "U1"
                self.net = net

        class MockComp:
            def __init__(self, ref, pins):
                self.ref = ref
                self.pins = pins

        comp = MockComp(
            "U1",
            [
                MockPin("1", "SPI_CLK"),
                MockPin("2", "SPI_MOSI"),
            ],
        )
        result = _resolve_component_net_class(comp, None)
        assert result == "Signal"


class TestCrossClassGeneration:
    def test_cross_class_pair_count(self, rules):
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )
        c1, n1 = _make_mock_component("U1", "DC_BUS+")  # HighVoltage
        c2, n2 = _make_mock_component("U2", "SPI_CLK")  # Signal
        c3, n3 = _make_mock_component("U3", "SPI_MOSI") # Signal

        class MockNetlist:
            nets = [n1, n2, n3]

        constraints = generate_netclass_separated_constraints(
            MockNetlist(), [c1, c2, c3], rules.design_rules
        )
        # U1(HV) vs U2(Signal) + U1(HV) vs U3(Signal) = 2 constraints
        assert len(constraints) == 2

    def test_cross_class_clearance_value(self, rules):
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )
        c1, n1 = _make_mock_component("U1", "DC_BUS+")
        c2, n2 = _make_mock_component("U2", "SPI_CLK")
        class MockNetlist:
            nets = [n1, n2]
        constraints = generate_netclass_separated_constraints(
            MockNetlist(), [c1, c2], rules.design_rules
        )
        assert constraints[0].min_distance_mm == 6.0

    def test_constraint_tier_is_hard(self, rules):
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )
        from temper_placer.pcl.constraints import ConstraintTier
        c1, n1 = _make_mock_component("U1", "DC_BUS+")
        c2, n2 = _make_mock_component("U2", "SPI_CLK")
        class MockNetlist:
            nets = [n1, n2]
        constraints = generate_netclass_separated_constraints(
            MockNetlist(), [c1, c2], rules.design_rules
        )
        assert constraints[0].tier == ConstraintTier.HARD


class TestSameClassNoGeneration:
    def test_all_signal_no_constraints(self, rules):
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )
        c1, n1 = _make_mock_component("U1", "SPI_CLK")
        c2, n2 = _make_mock_component("U2", "SPI_MOSI")
        class MockNetlist:
            nets = [n1, n2]
        constraints = generate_netclass_separated_constraints(
            MockNetlist(), [c1, c2], rules.design_rules
        )
        assert len(constraints) == 0
