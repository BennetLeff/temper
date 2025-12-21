"""Unit tests for Level 2 per-parameter tolerance model.

Tests the manufacturing tolerance analysis including:
- Copper weight etch tolerances
- Layer registration tolerances
- Drill size tolerances
- Clearance, trace, via, and solder mask analysis

Related issues: temper-6vj.2
"""

import pytest

from temper_placer.manufacturing.tolerances import (
    CopperWeight,
    DrillSize,
    FeatureTolerance,
    LayerType,
    ToleranceAnalyzer,
    ToleranceTable,
)


class TestCopperWeight:
    """Tests for CopperWeight enum."""

    def test_copper_weight_values(self):
        """Copper weights have correct oz values."""
        assert CopperWeight.HALF_OZ.value == 0.5
        assert CopperWeight.ONE_OZ.value == 1.0
        assert CopperWeight.TWO_OZ.value == 2.0


class TestLayerType:
    """Tests for LayerType enum."""

    def test_layer_type_values(self):
        """Layer types have string values."""
        assert LayerType.OUTER.value == "outer"
        assert LayerType.INNER.value == "inner"


class TestDrillSize:
    """Tests for DrillSize enum."""

    def test_drill_size_from_diameter_micro(self):
        """Holes < 0.3mm are micro vias."""
        assert DrillSize.from_diameter(0.15) == DrillSize.MICRO
        assert DrillSize.from_diameter(0.25) == DrillSize.MICRO
        assert DrillSize.from_diameter(0.29) == DrillSize.MICRO

    def test_drill_size_from_diameter_small(self):
        """Holes 0.3-0.6mm are small."""
        assert DrillSize.from_diameter(0.3) == DrillSize.SMALL
        assert DrillSize.from_diameter(0.4) == DrillSize.SMALL
        assert DrillSize.from_diameter(0.59) == DrillSize.SMALL

    def test_drill_size_from_diameter_standard(self):
        """Holes 0.6-1.0mm are standard."""
        assert DrillSize.from_diameter(0.6) == DrillSize.STANDARD
        assert DrillSize.from_diameter(0.8) == DrillSize.STANDARD
        assert DrillSize.from_diameter(0.99) == DrillSize.STANDARD

    def test_drill_size_from_diameter_large(self):
        """Holes >= 1.0mm are large."""
        assert DrillSize.from_diameter(1.0) == DrillSize.LARGE
        assert DrillSize.from_diameter(1.5) == DrillSize.LARGE
        assert DrillSize.from_diameter(3.0) == DrillSize.LARGE


class TestToleranceTable:
    """Tests for ToleranceTable configuration."""

    def test_default_etch_tolerances(self):
        """Default etch tolerances by copper weight."""
        table = ToleranceTable()
        assert table.get_etch_tolerance(CopperWeight.HALF_OZ) == 0.025
        assert table.get_etch_tolerance(CopperWeight.ONE_OZ) == 0.050
        assert table.get_etch_tolerance(CopperWeight.TWO_OZ) == 0.075

    def test_default_drill_tolerances(self):
        """Default drill tolerances by size category."""
        table = ToleranceTable()
        assert table.get_drill_tolerance(0.2) == 0.050  # MICRO
        assert table.get_drill_tolerance(0.4) == 0.075  # SMALL
        assert table.get_drill_tolerance(0.8) == 0.100  # STANDARD
        assert table.get_drill_tolerance(1.5) == 0.150  # LARGE

    def test_default_registration_tolerances(self):
        """Default registration tolerances by layer type."""
        table = ToleranceTable()
        assert table.get_registration(LayerType.OUTER) == 0.100
        assert table.get_registration(LayerType.INNER) == 0.150

    def test_default_solder_mask_registration(self):
        """Default solder mask registration."""
        table = ToleranceTable()
        assert table.solder_mask_registration == 0.075

    def test_custom_etch_tolerances(self):
        """Custom etch tolerances can be provided."""
        custom_etch = {
            CopperWeight.HALF_OZ: 0.020,
            CopperWeight.ONE_OZ: 0.040,
            CopperWeight.TWO_OZ: 0.060,
        }
        table = ToleranceTable(etch_tolerance=custom_etch)
        assert table.get_etch_tolerance(CopperWeight.ONE_OZ) == 0.040


class TestFeatureTolerance:
    """Tests for FeatureTolerance dataclass."""

    def test_total_tolerance(self):
        """Total tolerance is sum of plus and minus."""
        ft = FeatureTolerance(
            feature_type="test",
            nominal_value=1.0,
            tolerance_plus=0.05,
            tolerance_minus=0.03,
            worst_case_min=0.97,
            worst_case_max=1.05,
        )
        assert ft.total_tolerance == pytest.approx(0.08)

    def test_tolerance_percentage(self):
        """Tolerance percentage calculated correctly."""
        ft = FeatureTolerance(
            feature_type="test",
            nominal_value=1.0,
            tolerance_plus=0.05,
            tolerance_minus=0.05,
            worst_case_min=0.95,
            worst_case_max=1.05,
        )
        assert ft.tolerance_pct == pytest.approx(10.0)

    def test_tolerance_percentage_zero_nominal(self):
        """Tolerance percentage is 0 for zero nominal."""
        ft = FeatureTolerance(
            feature_type="test",
            nominal_value=0.0,
            tolerance_plus=0.0,
            tolerance_minus=0.0,
            worst_case_min=0.0,
            worst_case_max=0.0,
        )
        assert ft.tolerance_pct == 0.0

    def test_meets_requirement_pass(self):
        """meets_requirement returns True when worst case >= requirement."""
        ft = FeatureTolerance(
            feature_type="clearance",
            nominal_value=0.2,
            tolerance_plus=0.0,
            tolerance_minus=0.05,
            worst_case_min=0.15,
            worst_case_max=0.2,
        )
        assert ft.meets_requirement(0.15) is True
        assert ft.meets_requirement(0.10) is True

    def test_meets_requirement_fail(self):
        """meets_requirement returns False when worst case < requirement."""
        ft = FeatureTolerance(
            feature_type="clearance",
            nominal_value=0.2,
            tolerance_plus=0.0,
            tolerance_minus=0.05,
            worst_case_min=0.15,
            worst_case_max=0.2,
        )
        assert ft.meets_requirement(0.16) is False
        assert ft.meets_requirement(0.20) is False

    def test_margin_to_requirement(self):
        """margin_to_requirement calculates correctly."""
        ft = FeatureTolerance(
            feature_type="clearance",
            nominal_value=0.2,
            tolerance_plus=0.0,
            tolerance_minus=0.05,
            worst_case_min=0.15,
            worst_case_max=0.2,
        )
        assert ft.margin_to_requirement(0.10) == pytest.approx(0.05)
        assert ft.margin_to_requirement(0.15) == pytest.approx(0.0)
        assert ft.margin_to_requirement(0.20) == pytest.approx(-0.05)

    def test_from_clearance(self):
        """from_clearance creates correct tolerance for clearance."""
        table = ToleranceTable()
        ft = FeatureTolerance.from_clearance(0.2, CopperWeight.ONE_OZ, table)

        assert ft.feature_type == "clearance"
        assert ft.nominal_value == 0.2
        # 2x etch tolerance = 2 * 0.05 = 0.1
        assert ft.tolerance_minus == pytest.approx(0.1)
        assert ft.tolerance_plus == 0.0
        assert ft.worst_case_min == pytest.approx(0.1)  # 0.2 - 0.1
        assert ft.worst_case_max == 0.2

    def test_from_trace_width(self):
        """from_trace_width creates symmetric tolerance."""
        table = ToleranceTable()
        ft = FeatureTolerance.from_trace_width(0.15, CopperWeight.ONE_OZ, table)

        assert ft.feature_type == "trace_width"
        assert ft.nominal_value == 0.15
        # Symmetric etch tolerance = 0.05
        assert ft.tolerance_plus == pytest.approx(0.05)
        assert ft.tolerance_minus == pytest.approx(0.05)
        assert ft.worst_case_min == pytest.approx(0.10)  # 0.15 - 0.05
        assert ft.worst_case_max == pytest.approx(0.20)  # 0.15 + 0.05

    def test_from_via_annular_ring(self):
        """from_via_annular_ring considers drill, etch, and registration."""
        table = ToleranceTable()
        ft = FeatureTolerance.from_via_annular_ring(
            pad_diameter=0.6,
            hole_diameter=0.3,
            copper_weight=CopperWeight.ONE_OZ,
            layer_type=LayerType.OUTER,
            table=table,
        )

        assert ft.feature_type == "annular_ring"
        # Nominal ring = (0.6 - 0.3) / 2 = 0.15
        assert ft.nominal_value == pytest.approx(0.15)

        # Total shrink = etch + drill/2 + registration
        # = 0.05 + 0.075/2 + 0.1 = 0.05 + 0.0375 + 0.1 = 0.1875
        assert ft.tolerance_minus == pytest.approx(0.1875)
        assert ft.tolerance_plus == 0.0
        # Worst case = 0.15 - 0.1875 = -0.0375, clamped to 0
        assert ft.worst_case_min == pytest.approx(0.0)


class TestToleranceAnalyzer:
    """Tests for ToleranceAnalyzer class."""

    def test_analyzer_uses_default_table(self):
        """Analyzer uses default table if none provided."""
        analyzer = ToleranceAnalyzer()
        assert analyzer.table is not None
        assert analyzer.table.get_etch_tolerance(CopperWeight.ONE_OZ) == 0.050

    def test_analyzer_uses_custom_table(self):
        """Analyzer uses custom table if provided."""
        custom_table = ToleranceTable(
            etch_tolerance={
                CopperWeight.HALF_OZ: 0.020,
                CopperWeight.ONE_OZ: 0.040,
                CopperWeight.TWO_OZ: 0.060,
            }
        )
        analyzer = ToleranceAnalyzer(table=custom_table)
        assert analyzer.table.get_etch_tolerance(CopperWeight.ONE_OZ) == 0.040

    def test_analyze_clearance_outer_layer(self):
        """Clearance shrinks by 2x etch + registration for outer layer."""
        analyzer = ToleranceAnalyzer()
        result = analyzer.analyze_clearance(0.2, CopperWeight.ONE_OZ, LayerType.OUTER)

        assert result.feature_type == "clearance"
        assert result.nominal_value == 0.2
        # Shrink = 2 * 0.05 + 0.1 = 0.2
        assert result.tolerance_minus == pytest.approx(0.2)
        # 0.2 - 0.2 = 0, clamped to 0
        assert result.worst_case_min == pytest.approx(0.0)

    def test_analyze_clearance_inner_layer(self):
        """Inner layer has worse registration."""
        analyzer = ToleranceAnalyzer()
        result = analyzer.analyze_clearance(0.3, CopperWeight.ONE_OZ, LayerType.INNER)

        # Shrink = 2 * 0.05 + 0.15 = 0.25
        assert result.tolerance_minus == pytest.approx(0.25)
        # 0.3 - 0.25 = 0.05
        assert result.worst_case_min == pytest.approx(0.05)

    def test_analyze_clearance_heavy_copper(self):
        """Heavy copper has larger etch tolerance."""
        analyzer = ToleranceAnalyzer()
        result = analyzer.analyze_clearance(0.3, CopperWeight.TWO_OZ, LayerType.OUTER)

        # Shrink = 2 * 0.075 + 0.1 = 0.25
        assert result.tolerance_minus == pytest.approx(0.25)
        assert result.worst_case_min == pytest.approx(0.05)

    def test_analyze_trace_width_symmetric(self):
        """Trace width has symmetric tolerance."""
        analyzer = ToleranceAnalyzer()
        result = analyzer.analyze_trace_width(0.15, CopperWeight.ONE_OZ)

        assert result.tolerance_plus == result.tolerance_minus
        assert result.tolerance_plus == pytest.approx(0.05)

    def test_analyze_trace_width_half_oz(self):
        """Half oz copper has tighter tolerance."""
        analyzer = ToleranceAnalyzer()
        result = analyzer.analyze_trace_width(0.15, CopperWeight.HALF_OZ)

        assert result.tolerance_plus == pytest.approx(0.025)
        assert result.tolerance_minus == pytest.approx(0.025)

    def test_analyze_via_annular_ring(self):
        """Via analysis considers drill, etch, and registration."""
        analyzer = ToleranceAnalyzer()
        result = analyzer.analyze_via(
            pad_diameter_mm=0.6,
            hole_diameter_mm=0.3,
            copper_weight=CopperWeight.ONE_OZ,
            layer_type=LayerType.OUTER,
        )

        # Nominal ring = (0.6 - 0.3) / 2 = 0.15
        assert result.nominal_value == pytest.approx(0.15)
        assert result.feature_type == "annular_ring"

    def test_analyze_solder_mask_opening(self):
        """Solder mask analysis considers registration."""
        analyzer = ToleranceAnalyzer()
        result = analyzer.analyze_solder_mask_opening(
            pad_diameter_mm=1.0,
            mask_opening_mm=1.2,
        )

        # Nominal margin = (1.2 - 1.0) / 2 = 0.1
        assert result.nominal_value == pytest.approx(0.1)
        assert result.feature_type == "solder_mask_margin"
        # Registration = 0.075
        assert result.tolerance_plus == pytest.approx(0.075)
        assert result.tolerance_minus == pytest.approx(0.075)
        # Worst case min = 0.1 - 0.075 = 0.025
        assert result.worst_case_min == pytest.approx(0.025)

    def test_check_clearance_requirement_pass(self):
        """check_clearance_requirement returns pass and margin."""
        analyzer = ToleranceAnalyzer()
        passes, margin = analyzer.check_clearance_requirement(
            clearance_mm=0.4,
            required_mm=0.15,
            copper_weight=CopperWeight.ONE_OZ,
            layer_type=LayerType.OUTER,
        )

        # Shrink = 2 * 0.05 + 0.1 = 0.2
        # Worst case = 0.4 - 0.2 = 0.2
        # Margin = 0.2 - 0.15 = 0.05
        assert passes is True
        assert margin == pytest.approx(0.05)

    def test_check_clearance_requirement_fail(self):
        """check_clearance_requirement returns fail and negative margin."""
        analyzer = ToleranceAnalyzer()
        passes, margin = analyzer.check_clearance_requirement(
            clearance_mm=0.2,
            required_mm=0.15,
            copper_weight=CopperWeight.ONE_OZ,
            layer_type=LayerType.OUTER,
        )

        # Shrink = 2 * 0.05 + 0.1 = 0.2
        # Worst case = 0.2 - 0.2 = 0.0
        # Margin = 0.0 - 0.15 = -0.15
        assert passes is False
        assert margin == pytest.approx(-0.15)


class TestIntegration:
    """Integration tests for tolerance analysis workflow."""

    def test_temper_typical_clearance_check(self):
        """Test typical Temper board clearance check.

        Temper PCB uses 1oz copper outer layers with safety clearances.
        """
        analyzer = ToleranceAnalyzer()

        # High voltage clearance: design 1.5mm, require 1.0mm
        result = analyzer.analyze_clearance(1.5, CopperWeight.ONE_OZ, LayerType.OUTER)
        assert result.meets_requirement(1.0) is True
        assert result.margin_to_requirement(1.0) > 0

        # Signal clearance: design 0.2mm, require 0.15mm
        result = analyzer.analyze_clearance(0.2, CopperWeight.ONE_OZ, LayerType.OUTER)
        # This fails because shrink = 0.2mm, so worst case = 0
        assert result.meets_requirement(0.15) is False

    def test_temper_trace_width_for_current(self):
        """Test trace width for current carrying capacity.

        Need minimum 0.5mm trace for 1A after tolerance.
        """
        analyzer = ToleranceAnalyzer()
        result = analyzer.analyze_trace_width(0.6, CopperWeight.ONE_OZ)

        # Worst case min = 0.6 - 0.05 = 0.55
        assert result.worst_case_min == pytest.approx(0.55)
        assert result.meets_requirement(0.5) is True

    def test_via_minimum_annular_ring(self):
        """Test via meets minimum annular ring requirement.

        Many fabs require minimum 0.1mm annular ring.
        """
        analyzer = ToleranceAnalyzer()

        # Standard via: 0.8mm pad, 0.4mm hole
        result = analyzer.analyze_via(0.8, 0.4, CopperWeight.ONE_OZ, LayerType.OUTER)
        # Nominal ring = (0.8 - 0.4) / 2 = 0.2
        # Shrink = 0.05 + 0.075/2 + 0.1 = 0.1875
        # Worst case = 0.2 - 0.1875 = 0.0125
        # This actually fails the 0.1mm requirement!
        assert result.meets_requirement(0.1) is False

        # Larger via: 1.0mm pad, 0.4mm hole
        result = analyzer.analyze_via(1.0, 0.4, CopperWeight.ONE_OZ, LayerType.OUTER)
        # Nominal ring = (1.0 - 0.4) / 2 = 0.3
        # Worst case = 0.3 - 0.1875 = 0.1125
        assert result.meets_requirement(0.1) is True

    def test_workflow_design_to_production(self):
        """Complete workflow: design value to production requirement."""
        # Designer wants 0.25mm clearance for 100V isolation
        design_clearance = 0.25
        voltage_requirement = 0.15  # Per IPC for 100V

        # Check different scenarios
        analyzer = ToleranceAnalyzer()

        # Standard process
        result = analyzer.analyze_clearance(design_clearance, CopperWeight.ONE_OZ, LayerType.OUTER)
        standard_passes = result.meets_requirement(voltage_requirement)

        # Tight tolerance process (custom table)
        tight_table = ToleranceTable(
            etch_tolerance={
                CopperWeight.HALF_OZ: 0.015,
                CopperWeight.ONE_OZ: 0.025,
                CopperWeight.TWO_OZ: 0.040,
            },
            registration={LayerType.OUTER: 0.050, LayerType.INNER: 0.075},
        )
        tight_analyzer = ToleranceAnalyzer(table=tight_table)
        tight_result = tight_analyzer.analyze_clearance(
            design_clearance, CopperWeight.ONE_OZ, LayerType.OUTER
        )
        # Shrink = 2 * 0.025 + 0.050 = 0.1
        # Worst case = 0.25 - 0.1 = 0.15
        tight_passes = tight_result.meets_requirement(voltage_requirement)

        # Standard process fails, tight process passes
        assert standard_passes is False
        assert tight_passes is True
