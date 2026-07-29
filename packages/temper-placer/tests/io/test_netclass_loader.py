"""Test netclass loader: YAML -> DesignRules."""

from pathlib import Path

import pytest

# Path to the fixture YAML
RULES_PATH = Path(__file__).parent.parent.parent / "configs" / "netclass_rules.yaml"


class TestNetclassLoader:
    @pytest.fixture(autouse=True)
    def setup(self):
        from temper_placer.io.netclass_loader import load_netclass_rules

        self.ncr = load_netclass_rules(RULES_PATH)
        self.dr = self.ncr.design_rules

    def test_loads_all_9_classes(self):
        """All net classes in configs/netclass_rules.yaml are loaded into
        DesignRules.net_classes.

        10, not 9: this fixture's own netclass_rules.yaml has carried
        HighVoltageIsolated since 2026-07-28 (docs/evidence/
        2026-07-28-hv-isolated-rules-and-creepage-triage.md), which this
        test's expected set was never updated to match -- pre-existing
        staleness, found and fixed alongside the same class's addition to
        TEMPER_NET_CLASSES in design_rules.py (docs/evidence/
        2026-07-28-netclass-defect-reconciliation.md).
        """
        expected = {
            "ACMains",
            "HighVoltage",
            "HighVoltageIsolated",
            "FinePitch",
            "Power",
            "GateDrive",
            "GND",
            "HighSpeed",
            "Signal",
            "HighCurrent",
        }
        assert set(self.dr.net_classes.keys()) == expected

    def test_class_clearance_values(self):
        """Each class has correct clearance from YAML."""
        assert self.dr.net_classes["HighVoltage"].clearance == 6.0
        assert self.dr.net_classes["Signal"].clearance == 0.15
        assert self.dr.net_classes["Power"].clearance == 0.25

    def test_get_rules_for_net_returns_class_rules(self):
        """get_rules_for_net resolves by class name."""
        rules = self.dr.get_rules_for_net("", net_class="HighVoltage")
        assert rules.clearance == 6.0
        rules = self.dr.get_rules_for_net("", net_class="Signal")
        assert rules.clearance == 0.15

    def test_net_class_assignments_inherited(self):
        """TEMPER_NET_ASSIGNMENTS are populated."""
        assert "AC_L" in self.dr.net_class_assignments
        assert self.dr.net_class_assignments["AC_L"] == "ACMains"

    def test_class_pairs_loaded(self):
        """Safety-critical class_pairs are loaded."""
        assert hasattr(self.dr, "class_pairs")
        cp = self.dr.class_pairs
        assert ("ACMains", "Signal") in cp
        assert cp[("ACMains", "Signal")]["clearance"] == 6.0
        assert "IEC 60335-1" in cp[("ACMains", "Signal")]["because"]

    def test_class_pairs_are_direction_agnostic(self):
        """Class pair keys are sorted tuples."""
        cp = self.dr.class_pairs
        assert ("HighVoltage", "Signal") in cp
        assert cp[("HighVoltage", "Signal")]["clearance"] == 6.0

    def test_default_clearance(self):
        """Default clearance is loaded."""
        assert self.dr.default_clearance == 0.2

    def test_layer_field_loaded(self):
        """Each class carries its SSOT `layer` field (W2 R2)."""
        assert self.dr.net_classes["ACMains"].layer == "F.Cu"
        assert self.dr.net_classes["HighVoltage"].layer == "F.Cu"
        assert self.dr.net_classes["HighCurrent"].layer == "F.Cu"
        assert self.dr.net_classes["Signal"].layer == "F.Cu"
        assert self.dr.net_classes["GateDrive"].layer == "B.Cu"
        assert self.dr.net_classes["Power"].layer == "B.Cu"
        assert self.dr.net_classes["FinePitch"].layer == "B.Cu"
        assert self.dr.net_classes["HighSpeed"].layer == "B.Cu"
        assert self.dr.net_classes["GND"].layer == "In1.Cu"
