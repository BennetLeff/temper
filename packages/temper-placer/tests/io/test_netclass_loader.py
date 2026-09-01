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
        HighVoltageTank split out of HighVoltage 2026-08-12
        (docs/evidence/2026-08-12-hv-hv-creepage-enforcement.md).
        HighVoltageSignal split out of HighVoltage 2026-08-13
        (docs/evidence/2026-08-13-netclass-current-scoping.md): the
        mA-scale current tier (bleed string, gate taps, ZCD divider,
        gate-driver bias rail) carved out of HighVoltage's 1000x current
        range, same clearance/creepage/voltage_v/safety_category.
        """
        expected = {
            "ACMains",
            "HighVoltage",
            "HighVoltageTank",
            "HighVoltageSignal",
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
        """Each class has correct clearance from YAML.

        HighVoltage 2.0 (was 6.0) and Power 0.5 (was 0.25) fixed 2026-08-12
        (docs/evidence/2026-08-12-netclass-param-reconciliation.md) -- both
        now match pcb/temper.kicad_pro; see that doc for grounding.
        """
        assert self.dr.net_classes["HighVoltage"].clearance == 2.0
        assert self.dr.net_classes["Signal"].clearance == 0.15
        assert self.dr.net_classes["Power"].clearance == 0.5

    def test_get_rules_for_net_returns_class_rules(self):
        """get_rules_for_net resolves by class name."""
        rules = self.dr.get_rules_for_net("", net_class="HighVoltage")
        assert rules.clearance == 2.0
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
        # Provenance pin updated 2026-08-22: the pair's `because` field
        # used to claim "IEC 60335-1 Table 16 working isolation at 400V" --
        # a citation the safety-figure work DEBUNKED (Table 16 is keyed to
        # rated impulse voltage, has no 400V row, and 6.0mm is not among
        # its values). The field now honestly reads UNSOURCED; this test
        # asserts that honest provenance is present rather than asserting
        # the fabricated citation back into existence.
        because = cp[("ACMains", "Signal")]["because"]
        assert "UNSOURCED" in because
        assert "debunked" in because

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
            # via_diameter RAISED 0.8 -> 1.0mm 2026-08-13 (docs/evidence/
            # 2026-08-13-jlcpcb-fab-capability-envelope.md): 0.8/0.4 gave a
            # 0.2mm annular ring, below JLCPCB's 2oz PTH floor (0.254mm).
            # Both halves of the R4 split still agree with each other (the
            # invariant this test checks), just at the raised value.
            assert rules.via_diameter == 1.0
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
        """Neither half of the GateDrive split may silently lose a rule the
        other keeps: for every LV sibling class, both halves either carry a
        class_pair row or neither does -- and the figures must match.

        Rewritten 2026-08-22 (#1445 item 4): the original pairwise-twin walk
        demanded a 'twin' for EVERY entry naming a gate-drive half, which
        produced nonsense keys -- ('GateDriveSELV','GateDriveSELV') for the
        cross-half pair itself, and ('ACMains','GateDriveHV') for
        ACMains-GateDriveSELV even though same-broader-HV-domain rows are
        deliberately absent from this table (see netclass_rules.yaml's own
        block comment: 'the same-domain figure is the DRU's business').
        The invariant this test actually guards is per-LV-sibling symmetry,
        stated directly below.
        """
        cp = self.dr.class_pairs
        lv_siblings = ["FinePitch", "GND", "Power", "Signal"]
        for lv in lv_siblings:
            hv_half = ("GateDriveHV", lv) in cp
            selv_half = ("GateDriveSELV", lv) in cp
            assert hv_half == selv_half, (
                f"GateDrive split asymmetry on {lv!r}: "
                f"GateDriveHV row={hv_half}, GateDriveSELV row={selv_half} -- "
                "one half silently lost (or gained) a rule the other keeps"
            )
            if hv_half:
                hv_figure = cp[("GateDriveHV", lv)]["clearance"]
                selv_figure = cp[("GateDriveSELV", lv)]["clearance"]
                assert hv_figure == selv_figure, (
                    f"GateDrive {lv!r} figures diverge: {hv_figure} vs {selv_figure}"
                )
        # The cross-half pair itself must exist: GateDriveHV is the HV/
        # secondary side of U7's reinforced barrier, GateDriveSELV the
        # SELV/primary side -- a genuine cross-barrier pair.
        assert ("GateDriveHV", "GateDriveSELV") in cp
