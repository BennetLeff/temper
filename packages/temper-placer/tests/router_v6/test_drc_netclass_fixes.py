"""
TDD Tests for DRC Netclass Configuration Fixes

These tests validate the netclass configuration fixes needed to address
the 1070 DRC violations identified in the comprehensive analysis.

Key Issues Addressed:
1. USB Differential Pair Misconfiguration (626 violations)
2. High-Voltage Safety Clearance (150 violations)
3. Ground Connectivity (50 violations)

Expected Results After Fixes:
- USB violations: ~620 eliminated (58% reduction)
- HV violations: ~150 eliminated (14% reduction)
- Ground violations: ~50 eliminated (5% reduction)
- Total: ~820 violations eliminated (77% reduction)

Reference: /tmp/drc_analysis_report.md
"""

import pytest
import json
from pathlib import Path
from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules


def get_current_kicad_pro_config() -> dict:
    """Load the actual current configuration from temper.kicad_pro."""
    kicad_pro_path = Path("/Users/bennet/Desktop/temper/pcb/temper.kicad_pro")
    with open(kicad_pro_path) as f:
        return json.load(f)


def get_fixed_design_rules() -> DesignRules:
    """Return the FIXED design rules configuration."""
    return DesignRules(
        default_trace_width_mm=0.2,
        default_clearance_mm=0.25,
        default_via_diameter_mm=0.6,
        default_via_drill_mm=0.3,
        net_classes={
            "Default": NetClassRules(
                name="Default",
                trace_width_mm=0.2,
                clearance_mm=0.25,
                via_diameter_mm=0.6,
                via_drill_mm=0.3,
            ),
            "Power": NetClassRules(
                name="Power",
                trace_width_mm=1.0,
                clearance_mm=0.5,
                via_diameter_mm=1.0,
                via_drill_mm=0.5,
            ),
            "HighVoltage": NetClassRules(
                name="HighVoltage",
                trace_width_mm=3.0,
                clearance_mm=3.0,  # FIXED: Was 2.0mm, now 3.0mm for 240VAC safety
                via_diameter_mm=1.2,
                via_drill_mm=0.6,
            ),
            "GateDrive": NetClassRules(
                name="GateDrive",
                trace_width_mm=0.5,
                clearance_mm=0.5,
                via_diameter_mm=0.8,
                via_drill_mm=0.4,
            ),
            "HighVoltageIsolated": NetClassRules(
                name="HighVoltageIsolated",
                trace_width_mm=2.0,
                clearance_mm=6.0,
                via_diameter_mm=1.0,
                via_drill_mm=0.5,
            ),
            "ACMains": NetClassRules(
                name="ACMains",
                trace_width_mm=2.5,
                clearance_mm=6.0,
                via_diameter_mm=1.2,
                via_drill_mm=0.6,
            ),
            "FinePitch": NetClassRules(
                name="FinePitch",
                trace_width_mm=0.127,
                clearance_mm=0.1,
                via_diameter_mm=0.4,
                via_drill_mm=0.2,
            ),
            "Differential": NetClassRules(
                name="Differential",
                trace_width_mm=0.35,  # FIXED: Was 0.127mm, now 0.35mm for USB 2.0
                clearance_mm=0.3,  # FIXED: Was 0.1mm, now 0.3mm to other nets
                via_diameter_mm=0.5,
                via_drill_mm=0.25,
                diff_pair_gap_mm=0.127,  # FIXED: Was 0.1mm, now 0.127mm for USB 2.0
                diff_pair_width_mm=0.35,
            ),
            "Ground": NetClassRules(
                name="Ground",
                trace_width_mm=0.5,
                clearance_mm=0.3,
                via_diameter_mm=0.6,
                via_drill_mm=0.3,
            ),
        },
        net_class_assignments={
            "+15V": "Power",
            "+3.3V": "Power",
            "+5V_ISO": "HighVoltageIsolated",
            "DC_BUS+": "HighVoltage",
            "DC_BUS-": "HighVoltage",
            "SWITCH_NODE": "HighVoltage",
            "GATE_H": "GateDrive",
            "GATE_L": "GateDrive",
            "VBOOT_H": "HighVoltageIsolated",
            "VBOOT_L": "HighVoltageIsolated",
            "AC_L": "ACMains",
            "AC_N": "ACMains",
            "PE": "ACMains",
            "USB_D+": "Differential",
            "USB_D-": "Differential",
            "+3V3": "FinePitch",
            "GND": "Ground",  # FIXED: Was FinePitch
            "I_SENSE": "FinePitch",
            "PWM_H": "FinePitch",
            "PWM_L": "FinePitch",
        },
    )


def parse_kicad_pro_to_design_rules() -> DesignRules:
    """Parse actual kicad_pro file to DesignRules."""
    config = get_current_kicad_pro_config()

    net_classes = {}
    for nc in config["net_settings"]["classes"]:
        net_classes[nc["name"]] = NetClassRules(
            name=nc["name"],
            trace_width_mm=nc.get("track_width", 0.2),
            clearance_mm=nc.get("clearance", 0.2),
            via_diameter_mm=nc.get("via_diameter", 0.6),
            via_drill_mm=nc.get("via_drill", 0.3),
            diff_pair_gap_mm=nc.get("diff_pair_gap"),
            diff_pair_width_mm=nc.get("diff_pair_width"),
        )

    return DesignRules(
        default_trace_width_mm=0.2,
        default_clearance_mm=0.2,
        default_via_diameter_mm=0.6,
        default_via_drill_mm=0.3,
        net_classes=net_classes,
        net_class_assignments=config["net_settings"]["netclass_assignments"],
    )


# =============================================================================
# Issue 1: USB Differential Pair Misconfiguration
# =============================================================================


class TestUSBDifferentialPairConfiguration:
    """
    Test USB differential pair netclass configuration.

    Current Problem:
    - USB_D+ and USB_D- are in "Differential" class with:
      - diff_pair_gap = 0.1mm (should be 0.127mm for USB 2.0)
      - clearance = 0.1mm (should be 0.3mm to other nets)

    Impact: 626 violations (58% of total) from misconfigured pair gap
    """

    def test_usb_diff_pair_gap_should_be_0_127mm(self):
        """
        USB 2.0 differential pairs require ~0.127mm gap for 90-ohm impedance.

        Current config has 0.1mm which causes false DRC violations.
        """
        design_rules = parse_kicad_pro_to_design_rules()
        usb_rules = design_rules.get_rules_for_net("USB_D+")

        # USB 2.0 spec requires approximately 0.127mm gap for 90-ohm differential
        assert usb_rules.diff_pair_gap_mm == pytest.approx(0.127, abs=0.01), (
            f"USB pair gap should be 0.127mm for USB 2.0, got {usb_rules.diff_pair_gap_mm}"
        )

    def test_usb_clearance_to_other_nets_should_be_0_3mm(self):
        """
        USB differential pairs need 0.3mm clearance to OTHER nets.

        Current config has 0.1mm which causes shorts to adjacent signals.
        """
        design_rules = parse_kicad_pro_to_design_rules()
        usb_rules = design_rules.get_rules_for_net("USB_D+")

        # Clearance to other nets should be 0.3mm minimum
        assert usb_rules.clearance_mm >= 0.3, (
            f"USB clearance to other nets should be >= 0.3mm, got {usb_rules.clearance_mm}"
        )

    def test_usb_trace_width_should_be_0_35mm(self):
        """
        USB 2.0 traces should be 0.35mm wide for proper impedance control.

        Current config has 0.127mm which is too thin.
        """
        design_rules = parse_kicad_pro_to_design_rules()
        usb_rules = design_rules.get_rules_for_net("USB_D+")

        # USB 2.0 recommends 0.35mm trace width
        assert usb_rules.trace_width_mm >= 0.3, (
            f"USB trace width should be >= 0.3mm, got {usb_rules.trace_width_mm}"
        )


# =============================================================================
# Issue 2: High-Voltage Safety Clearance
# =============================================================================


class TestHighVoltageSafetyClearance:
    """
    Test HighVoltage netclass safety clearance configuration.

    Current Problem:
    - DC_BUS+, DC_BUS-, SW_NODE are in "HighVoltage" class with:
      - clearance = 2.0mm (should be 3.0mm for 240VAC IEC 62368-1)

    Impact: 150 violations + electrical safety hazard
    """

    def test_hv_clearance_should_be_3mm_for_240vac(self):
        """
        IEC 62368-1 requires 3.0mm minimum clearance for 240VAC.

        Current 2.0mm clearance creates safety hazard.
        """
        design_rules = parse_kicad_pro_to_design_rules()
        hv_rules = design_rules.get_rules_for_net("DC_BUS+")

        assert hv_rules.clearance_mm >= 3.0, (
            f"HV clearance should be >= 3.0mm for 240VAC, got {hv_rules.clearance_mm}"
        )

    def test_ac_mains_clearance_should_be_6mm(self):
        """
        AC mains requires 6.0mm clearance for basic insulation.

        ACMains class already has 6.0mm - verify this is preserved.
        """
        design_rules = parse_kicad_pro_to_design_rules()
        ac_rules = design_rules.get_rules_for_net("AC_L")

        assert ac_rules.clearance_mm >= 6.0, (
            f"AC mains clearance should be >= 6.0mm, got {ac_rules.clearance_mm}"
        )


# =============================================================================
# Issue 3: Ground Connectivity
# =============================================================================


class TestGroundConnectivity:
    """
    Test Ground netclass configuration for proper connectivity.

    Current Problem:
    - GND is assigned to "FinePitch" class with:
      - clearance = 0.1mm (too tight for zone filling)
      - Causes 50+ unconnected ground pins

    Impact: Circuit won't function properly
    """

    def test_ground_clearance_should_enable_zone_filling(self):
        """
        Ground nets need sufficient clearance for copper zone filling.

        Current 0.1mm clearance is too tight for proper thermal reliefs.
        """
        design_rules = parse_kicad_pro_to_design_rules()
        gnd_rules = design_rules.get_rules_for_net("GND")

        # Ground should have at least 0.25mm clearance for zone filling
        assert gnd_rules.clearance_mm >= 0.25, (
            f"Ground clearance should be >= 0.25mm, got {gnd_rules.clearance_mm}"
        )

    def test_power_ground_trace_width_should_be_sufficient(self):
        """
        Power ground traces need adequate width for current return.

        Ground zone traces should be at least 0.5mm wide.
        """
        design_rules = parse_kicad_pro_to_design_rules()
        gnd_rules = design_rules.get_rules_for_net("GND")

        # Power ground should have sufficient trace width
        assert gnd_rules.trace_width_mm >= 0.5, (
            f"Ground trace width should be >= 0.5mm, got {gnd_rules.trace_width_mm}"
        )


# =============================================================================
# Validation: Fixed Configuration Tests
# =============================================================================


class TestFixedConfiguration:
    """
    Test that the FIXED configuration passes all requirements.

    These tests use the fixed configuration to validate expected behavior.
    """

    def test_fixed_usb_diff_pair_gap(self):
        """Fixed USB pair gap should be 0.127mm."""
        design_rules = get_fixed_design_rules()
        usb_rules = design_rules.get_rules_for_net("USB_D+")
        assert usb_rules.diff_pair_gap_mm == 0.127

    def test_fixed_usb_clearance(self):
        """Fixed USB clearance should be 0.3mm."""
        design_rules = get_fixed_design_rules()
        usb_rules = design_rules.get_rules_for_net("USB_D+")
        assert usb_rules.clearance_mm == 0.3

    def test_fixed_usb_trace_width(self):
        """Fixed USB trace width should be 0.35mm."""
        design_rules = get_fixed_design_rules()
        usb_rules = design_rules.get_rules_for_net("USB_D+")
        assert usb_rules.trace_width_mm == 0.35

    def test_fixed_hv_clearance(self):
        """Fixed HV clearance should be 3.0mm."""
        design_rules = get_fixed_design_rules()
        hv_rules = design_rules.get_rules_for_net("DC_BUS+")
        assert hv_rules.clearance_mm == 3.0

    def test_fixed_ground_class_exists(self):
        """Fixed config should have Ground class."""
        design_rules = get_fixed_design_rules()
        assert "Ground" in design_rules.net_classes
        assert design_rules.net_class_assignments.get("GND") == "Ground"

    def test_fixed_pair_detection_works(self):
        """Fixed config should detect USB differential pair."""
        design_rules = get_fixed_design_rules()
        is_pair, gap = design_rules.are_differential_pair("USB_D+", "USB_D-")
        assert is_pair
        assert gap == 0.127


# =============================================================================
# Expected DRC Improvement Summary
# =============================================================================

EXPECTED_DRC_IMPROVEMENTS = {
    "USB Differential Pair Fix": {
        "violations_eliminated": 620,
        "percentage_of_total": "58%",
        "changes": [
            "diff_pair_gap: 0.1mm -> 0.127mm",
            "clearance: 0.1mm -> 0.3mm",
            "trace_width: 0.127mm -> 0.35mm",
        ],
    },
    "High Voltage Safety Fix": {
        "violations_eliminated": 150,
        "percentage_of_total": "14%",
        "changes": [
            "clearance: 2.0mm -> 3.0mm (IEC 62368-1)",
        ],
    },
    "Ground Connectivity Fix": {
        "violations_eliminated": 50,
        "percentage_of_total": "5%",
        "changes": [
            "Create dedicated Ground class",
            "clearance: 0.1mm -> 0.3mm",
            "trace_width: 0.127mm -> 0.5mm",
        ],
    },
    "Total Expected Improvement": {
        "violations_eliminated": 820,
        "percentage_of_total": "77%",
        "remaining_violations": 250,
    },
}
