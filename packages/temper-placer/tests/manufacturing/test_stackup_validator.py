"""Tests for stackup validation checks (R8-R11)."""

from __future__ import annotations

import pytest

from temper_placer.core.board import Layer, LayerStackup
from temper_placer.manufacturing.stackup_validator import (
    COPPER_BALANCE_MAX_PCT,
    COPPER_BALANCE_MIN_PCT,
    StackupValidationResult,
    validate_stackup,
)


@pytest.fixture
def canonical_stackup() -> LayerStackup:
    return LayerStackup.default_4layer()


@pytest.fixture
def balanced_fill() -> dict[str, float]:
    return {"F.Cu": 35.0, "In1.Cu": 65.0, "In2.Cu": 65.0, "B.Cu": 30.0}


@pytest.fixture
def unbalanced_fill() -> dict[str, float]:
    return {"F.Cu": 95.0, "In1.Cu": 10.0, "In2.Cu": 90.0, "B.Cu": 3.0}


@pytest.fixture
def temper_default_fill() -> dict[str, float]:
    """Canonical Temper fill estimates (inner planes near-solid, outer sparse)."""
    return {"F.Cu": 35.0, "In1.Cu": 95.0, "In2.Cu": 95.0, "B.Cu": 30.0}


@pytest.fixture
def usb_differential_nets() -> frozenset[str]:
    return frozenset({"USB_D+", "USB_D-"})


class TestCopperSymmetry:
    """R8: Effective copper weight symmetry check."""

    def test_balanced_stackup_passes(self, canonical_stackup, balanced_fill):
        report = validate_stackup(canonical_stackup, copper_fill_percentages=balanced_fill)
        result = _find_result(report, "Copper Symmetry")
        assert result.passed, result.message

    def test_unbalanced_stackup_warns(self, canonical_stackup, unbalanced_fill):
        report = validate_stackup(canonical_stackup, copper_fill_percentages=unbalanced_fill)
        result = _find_result(report, "Copper Symmetry")
        assert not result.passed

    def test_no_fill_data_uses_defaults(self, canonical_stackup):
        """When no explicit fill data, Temper defaults are used (35/95/95/30)."""
        report = validate_stackup(canonical_stackup, copper_fill_percentages={})
        result = _find_result(report, "Copper Symmetry")
        assert result.passed
        assert "22.4%" in result.message


class TestReturnPathAdjacency:
    """R9: Return-path adjacency check for differential nets."""

    def test_l4_adjacent_to_pwr_warns_with_diff_nets(self, canonical_stackup, usb_differential_nets):
        report = validate_stackup(canonical_stackup, differential_nets=usb_differential_nets)
        result = _find_result(report, "Return-Path Adjacency")
        assert not result.passed
        assert "L4" in result.message

    def test_no_diff_nets_skips_check(self, canonical_stackup):
        report = validate_stackup(canonical_stackup, differential_nets=frozenset())
        result = _find_result(report, "Return-Path Adjacency")
        assert result.passed
        assert "No differential nets" in result.message

    def test_stitching_vias_suppress_warning(self, canonical_stackup, usb_differential_nets):
        report = validate_stackup(
            canonical_stackup,
            differential_nets=usb_differential_nets,
            has_stitching_vias=True,
        )
        result = _find_result(report, "Return-Path Adjacency")
        assert result.passed
        assert "stitching GND vias" in result.message


class TestControlledImpedance:
    """R10: Controlled-impedance specification check."""

    def test_no_spec_with_diff_nets_warns(self, usb_differential_nets):
        report = validate_stackup(
            LayerStackup.default_4layer(),
            differential_nets=usb_differential_nets,
            impedance_spec_ohms=None,
        )
        result = _find_result(report, "Controlled Impedance")
        assert not result.passed
        assert "90" in result.message

    def test_valid_spec_passes(self, usb_differential_nets):
        report = validate_stackup(
            LayerStackup.default_4layer(),
            differential_nets=usb_differential_nets,
            impedance_spec_ohms=90.0,
        )
        result = _find_result(report, "Controlled Impedance")
        assert result.passed

    def test_zero_impedance_warns(self, usb_differential_nets):
        report = validate_stackup(
            LayerStackup.default_4layer(),
            differential_nets=usb_differential_nets,
            impedance_spec_ohms=0.0,
        )
        result = _find_result(report, "Controlled Impedance")
        assert not result.passed

    def test_out_of_range_impedance_warns(self, usb_differential_nets):
        report = validate_stackup(
            LayerStackup.default_4layer(),
            differential_nets=usb_differential_nets,
            impedance_spec_ohms=150.0,
        )
        result = _find_result(report, "Controlled Impedance")
        assert not result.passed

    def test_no_diff_nets_skips(self, canonical_stackup):
        report = validate_stackup(canonical_stackup, differential_nets=frozenset())
        result = _find_result(report, "Controlled Impedance")
        assert "No differential nets" in result.message


class TestCopperBalance:
    """R11: Copper density balance check."""

    def test_balanced_fill_passes(self, canonical_stackup, balanced_fill):
        report = validate_stackup(canonical_stackup, copper_fill_percentages=balanced_fill)
        result = _find_result(report, "Copper Balance")
        assert result.passed

    def test_extreme_imbalance_warns(self, canonical_stackup, unbalanced_fill):
        report = validate_stackup(canonical_stackup, copper_fill_percentages=unbalanced_fill)
        result = _find_result(report, "Copper Balance")
        assert not result.passed, f"Expected warning, got: {result.message}"
        assert "warping" in result.message.lower()

    def test_no_fill_data_uses_defaults(self, canonical_stackup):
        """Default Temper fills (95% inner planes) trigger balance warning."""
        report = validate_stackup(canonical_stackup, copper_fill_percentages={})
        result = _find_result(report, "Copper Balance")
        assert not result.passed
        assert "95%" in result.message

    def test_temper_default_fill_warns(self, canonical_stackup, temper_default_fill):
        """Temper inner planes at 95% exceed the 75% upper threshold."""
        report = validate_stackup(canonical_stackup, copper_fill_percentages=temper_default_fill)
        result = _find_result(report, "Copper Balance")
        assert not result.passed
        assert "95%" in result.message


class TestValidationReport:
    """Integration tests for the full validation report."""

    def test_all_passed_when_all_checks_pass(self, canonical_stackup, balanced_fill):
        report = validate_stackup(
            canonical_stackup,
            copper_fill_percentages=balanced_fill,
        )
        assert report.all_passed

    def test_summary_format(self, canonical_stackup, balanced_fill):
        report = validate_stackup(
            canonical_stackup,
            copper_fill_percentages=balanced_fill,
        )
        summary = report.summary()
        assert "Copper Symmetry" in summary
        assert "Copper Balance" in summary
        assert "Return-Path" in summary
        assert "Impedance" in summary

    def test_warnings_list_contains_only_failures(self, canonical_stackup, usb_differential_nets):
        report = validate_stackup(
            canonical_stackup,
            differential_nets=usb_differential_nets,
            impedance_spec_ohms=None,
        )
        assert not report.all_passed
        for w in report.warnings:
            assert not w.passed


def _find_result(report, check_name: str) -> StackupValidationResult:
    for r in report.results:
        if r.check_name == check_name:
            return r
    raise KeyError(f"Check '{check_name}' not found in report")
