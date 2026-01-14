"""
Tests for differential pair detection in DesignRules.

Part of Router V6 DRC fix Phase 2.
"""

import pytest

from temper_placer.router_v6.stage0_data import DesignRules, NetClassRules


class TestDifferentialPairDetection:
    """Test differential pair detection logic."""

    def test_detect_usb_diff_pair(self):
        """Test detection of USB_D+/USB_D- differential pair."""
        design_rules = DesignRules(
            default_trace_width_mm=0.15,
            default_clearance_mm=0.2,
            default_via_diameter_mm=0.6,
            default_via_drill_mm=0.3,
            net_classes={
                "DiffPair": NetClassRules(
                    name="DiffPair",
                    trace_width_mm=0.15,
                    clearance_mm=0.2,
                    via_diameter_mm=0.6,
                    via_drill_mm=0.3,
                    diff_pair_gap_mm=0.127,
                )
            },
            net_class_assignments={
                "USB_D+": "DiffPair",
                "USB_D-": "DiffPair",
            },
        )

        # Check that USB_D+ and USB_D- are detected as a pair
        is_pair, gap = design_rules.are_differential_pair("USB_D+", "USB_D-")
        assert is_pair is True
        assert gap == 0.127

        # Check symmetry
        is_pair2, gap2 = design_rules.are_differential_pair("USB_D-", "USB_D+")
        assert is_pair2 is True
        assert gap2 == 0.127

    def test_not_diff_pair_different_nets(self):
        """Test that unrelated nets are not detected as a pair."""
        design_rules = DesignRules(
            default_trace_width_mm=0.15,
            default_clearance_mm=0.2,
            default_via_diameter_mm=0.6,
            default_via_drill_mm=0.3,
            net_classes={
                "DiffPair": NetClassRules(
                    name="DiffPair",
                    trace_width_mm=0.15,
                    clearance_mm=0.2,
                    via_diameter_mm=0.6,
                    via_drill_mm=0.3,
                    diff_pair_gap_mm=0.127,
                )
            },
            net_class_assignments={
                "USB_D+": "DiffPair",
                "USB_D-": "DiffPair",
                "OTHER_NET": "DiffPair",
            },
        )

        # USB_D+ and OTHER_NET should not be a pair
        is_pair, gap = design_rules.are_differential_pair("USB_D+", "OTHER_NET")
        assert is_pair is False
        assert gap is None

    def test_not_diff_pair_different_classes(self):
        """Test that nets in different classes are not detected as a pair."""
        design_rules = DesignRules(
            default_trace_width_mm=0.15,
            default_clearance_mm=0.2,
            default_via_diameter_mm=0.6,
            default_via_drill_mm=0.3,
            net_classes={
                "DiffPair": NetClassRules(
                    name="DiffPair",
                    trace_width_mm=0.15,
                    clearance_mm=0.2,
                    via_diameter_mm=0.6,
                    via_drill_mm=0.3,
                    diff_pair_gap_mm=0.127,
                ),
                "Signal": NetClassRules(
                    name="Signal",
                    trace_width_mm=0.15,
                    clearance_mm=0.2,
                    via_diameter_mm=0.6,
                    via_drill_mm=0.3,
                ),
            },
            net_class_assignments={
                "USB_D+": "DiffPair",
                "OTHER_D-": "Signal",  # Different class
            },
        )

        # Different classes - not a pair
        is_pair, gap = design_rules.are_differential_pair("USB_D+", "OTHER_D-")
        assert is_pair is False
        assert gap is None

    def test_not_diff_pair_no_gap_defined(self):
        """Test that nets without diff_pair_gap_mm are not detected as a pair."""
        design_rules = DesignRules(
            default_trace_width_mm=0.15,
            default_clearance_mm=0.2,
            default_via_diameter_mm=0.6,
            default_via_drill_mm=0.3,
            net_classes={
                "Signal": NetClassRules(
                    name="Signal",
                    trace_width_mm=0.15,
                    clearance_mm=0.2,
                    via_diameter_mm=0.6,
                    via_drill_mm=0.3,
                    # No diff_pair_gap_mm
                ),
            },
            net_class_assignments={
                "USB_D+": "Signal",
                "USB_D-": "Signal",
            },
        )

        # Same class, matching names, but no diff_pair_gap_mm
        is_pair, gap = design_rules.are_differential_pair("USB_D+", "USB_D-")
        assert is_pair is False
        assert gap is None

    def test_detect_pcie_diff_pair(self):
        """Test detection of PCIE_TX_P/PCIE_TX_N differential pair."""
        design_rules = DesignRules(
            default_trace_width_mm=0.15,
            default_clearance_mm=0.2,
            default_via_diameter_mm=0.6,
            default_via_drill_mm=0.3,
            net_classes={
                "DiffPair": NetClassRules(
                    name="DiffPair",
                    trace_width_mm=0.15,
                    clearance_mm=0.2,
                    via_diameter_mm=0.6,
                    via_drill_mm=0.3,
                    diff_pair_gap_mm=0.127,
                )
            },
            net_class_assignments={
                "PCIE_TX_P": "DiffPair",
                "PCIE_TX_N": "DiffPair",
            },
        )

        # Check that PCIE_TX_P and PCIE_TX_N are detected as a pair
        is_pair, gap = design_rules.are_differential_pair("PCIE_TX_P", "PCIE_TX_N")
        assert is_pair is True
        assert gap == 0.127
