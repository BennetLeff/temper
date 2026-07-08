"""End-to-end SSOT chain verification for netclass-aware clearance."""
import pytest
from pathlib import Path

RULES_PATH = Path(__file__).parent.parent.parent / "configs" / "netclass_rules.yaml"


@pytest.mark.slow
@pytest.mark.integration
class TestE2ENetclassSSOT:
    @pytest.fixture(autouse=True)
    def setup(self):
        from temper_placer.io.netclass_loader import load_netclass_rules
        self.ncr = load_netclass_rules(RULES_PATH)
        self.dr = self.ncr.design_rules

    def test_yaml_loads_and_has_expected_classes(self):
        assert "HighVoltage" in self.dr.net_classes
        assert "Signal" in self.dr.net_classes
        assert self.dr.net_classes["HighVoltage"].clearance == 6.0

    def test_class_pairs_contain_safety_critical_entries(self):
        cp = self.dr.class_pairs
        assert ("ACMains", "Signal") in cp
        assert cp[("ACMains", "Signal")]["clearance"] == 6.0
        assert "IEC 60335-1" in cp[("ACMains", "Signal")]["because"]

    def test_get_rules_for_net_resolves_correctly(self):
        rules = self.dr.get_rules_for_net("", net_class="HighVoltage")
        assert rules.clearance == 6.0

    def test_generate_constraints_for_synthetic_netlist(self):
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )
        # Create mock components
        class P: pass
        class C: pass
        class N: pass
        class NL: nets = []
        pin1 = P(); pin1.component = "U1"; pin1.net = "DC_BUS+"; pin1.number = "1"
        pin2 = P(); pin2.component = "U2"; pin2.net = "SPI_CLK"; pin2.number = "1"
        pin3 = P(); pin3.component = "U3"; pin3.net = "SPI_MOSI"; pin3.number = "1"
        n1 = N(); n1.name = "DC_BUS+"; n1.pins = [pin1]
        n2 = N(); n2.name = "SPI_CLK"; n2.pins = [pin2]
        n3 = N(); n3.name = "SPI_MOSI"; n3.pins = [pin3]
        nl = NL(); nl.nets = [n1, n2, n3]
        c1 = C(); c1.ref = "U1"; c1.pins = [pin1]
        c2 = C(); c2.ref = "U2"; c2.pins = [pin2]
        c3 = C(); c3.ref = "U3"; c3.pins = [pin3]
        constraints = generate_netclass_separated_constraints(
            nl, [c1, c2, c3], self.dr
        )
        assert len(constraints) == 2
        for c in constraints:
            assert c.min_distance_mm == 6.0

    def test_same_class_no_constraints(self):
        from temper_placer.placer.cp_sat.netclass_constraints import (
            generate_netclass_separated_constraints,
        )
        class P: pass
        class C: pass
        class N: pass
        class NL: nets = []
        pin1 = P(); pin1.component = "U1"; pin1.net = "SPI_CLK"; pin1.number = "1"
        pin2 = P(); pin2.component = "U2"; pin2.net = "SPI_MOSI"; pin2.number = "1"
        n1 = N(); n1.name = "SPI_CLK"; n1.pins = [pin1]
        n2 = N(); n2.name = "SPI_MOSI"; n2.pins = [pin2]
        nl = NL(); nl.nets = [n1, n2]
        c1 = C(); c1.ref = "U1"; c1.pins = [pin1]
        c2 = C(); c2.ref = "U2"; c2.pins = [pin2]
        constraints = generate_netclass_separated_constraints(
            nl, [c1, c2], self.dr
        )
        assert len(constraints) == 0
