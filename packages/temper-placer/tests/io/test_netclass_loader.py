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

        11, not 9: this fixture's own netclass_rules.yaml has carried
        HighVoltageIsolated since 2026-07-28 (docs/evidence/
        2026-07-28-hv-isolated-rules-and-creepage-triage.md), which this
        test's expected set was never updated to match -- pre-existing
        staleness, found and fixed alongside the same class's addition to
        TEMPER_NET_CLASSES in design_rules.py (docs/evidence/
        2026-07-28-netclass-defect-reconciliation.md). GateDrive then split
        into GateDriveHV/GateDriveSELV, also 2026-07-28 (R4).
        """
        expected = {
            "ACMains",
            "HighVoltage",
            "HighVoltageIsolated",
            "FinePitch",
            "Power",
            "GateDriveHV",
            "GateDriveSELV",
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
        assert self.dr.net_classes["GateDriveHV"].layer == "B.Cu"
        assert self.dr.net_classes["GateDriveSELV"].layer == "B.Cu"
        assert self.dr.net_classes["Power"].layer == "B.Cu"
        assert self.dr.net_classes["FinePitch"].layer == "B.Cu"
        assert self.dr.net_classes["HighSpeed"].layer == "B.Cu"
        assert self.dr.net_classes["GND"].layer == "In1.Cu"


class TestGateDriveSplit:
    """R4 (U7): GateDrive split into GateDriveHV/GateDriveSELV across U7's
    reinforced isolation barrier -- GATE_HS/GATE_LS (HV, floats on SW_NODE)
    vs PWM_HS/PWM_LS (SELV, MCU-side).

    docs/plans/2026-07-28-003-refactor-ato-net-classification-ssot-plan.md
    U7: "Both currently read safety_category: 'LV' -- leaving the HV-side
    class as LV would reproduce the exact failure the split exists to fix."
    """

    @pytest.fixture(autouse=True)
    def setup(self):
        from temper_placer.io.netclass_loader import load_netclass_rules

        self.ncr = load_netclass_rules(RULES_PATH)
        self.dr = self.ncr.design_rules

    def test_old_class_name_is_gone(self):
        """The pre-split name must not silently linger as a third class."""
        assert "GateDrive" not in self.dr.net_classes

    def test_safety_category_differs_in_the_direction_the_split_demands(self):
        """The two split classes must NOT share safety_category, and the
        HV-side one must not be 'LV' -- that was the exact defect the split
        exists to fix."""
        hv = self.dr.net_classes["GateDriveHV"].safety_category
        selv = self.dr.net_classes["GateDriveSELV"].safety_category
        assert hv != selv
        assert hv == "HV"
        assert hv != "LV"

    def test_split_preserves_every_other_rule_value(self):
        """R4 changes the class MODEL, not the numbers: clearance, trace
        width, and via dimensions must be byte-identical to the pre-split
        class for both halves."""
        hv = self.dr.net_classes["GateDriveHV"]
        selv = self.dr.net_classes["GateDriveSELV"]
        for rules in (hv, selv):
            assert rules.clearance == 0.25
            assert rules.trace_width == 0.4
            assert rules.via_diameter == 0.8
            assert rules.via_drill == 0.4
            assert rules.layer == "B.Cu"

    def test_gate_hs_ls_resolve_to_the_hv_side_class(self):
        assert self.dr.net_class_assignments["GATE_HS"] == "GateDriveHV"
        assert self.dr.net_class_assignments["GATE_LS"] == "GateDriveHV"

    def test_pwm_hs_ls_resolve_to_the_selv_side_class(self):
        assert self.dr.net_class_assignments["PWM_HS"] == "GateDriveSELV"
        assert self.dr.net_class_assignments["PWM_LS"] == "GateDriveSELV"

    def test_no_class_pairs_entry_names_the_retired_class(self):
        """An orphaned 'GateDrive' key in class_pairs would be a dead,
        unreachable rule -- the same drift shape this whole plan exists to
        remove."""
        cp = self.dr.class_pairs
        for a, b in cp:
            assert a != "GateDrive"
            assert b != "GateDrive"

    def test_every_class_pairs_entry_for_one_half_has_an_equivalent_for_the_other(self):
        """Any class_pairs entry that existed for GateDrive must be
        duplicated for BOTH new classes, so neither half silently loses a
        rule the other keeps.

        Symmetric by construction today: GateDrive had zero class_pairs
        entries in configs/netclass_rules.yaml before the split (verified
        by grep), so there is nothing to duplicate -- this test guards the
        invariant going forward rather than merely documenting today's
        empty case.
        """
        cp = self.dr.class_pairs
        other = {"GateDriveHV": "GateDriveSELV", "GateDriveSELV": "GateDriveHV"}
        for (a, b), value in cp.items():
            for name, twin in other.items():
                if name not in (a, b):
                    continue
                twin_key = tuple(sorted((twin, b if a == name else a)))
                assert twin_key in cp, (
                    f"class_pairs has {(a, b)} but no equivalent {twin_key} "
                    f"for the other half of the GateDrive split"
                )
                assert cp[twin_key]["clearance"] == value["clearance"]
