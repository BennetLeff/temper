"""Tests for core.stackup module — JLCPCB JLC04161H-7628 stackup definition."""

import pytest

from temper_placer.core.stackup import (
    LayerConfig,
    Stackup,
    characteristic_impedance_microstrip,
    jlc04161h_7628,
)


class TestLayerConfig:
    def test_f_cu_layer(self):
        lc = LayerConfig("F.Cu", 0, "signal", 1.0, 0.035)
        assert lc.name == "F.Cu"
        assert lc.kicad_index == 0
        assert lc.type == "signal"
        assert lc.copper_weight_oz == 1.0
        assert lc.thickness_mm == 0.035

    def test_b_cu_uses_kicad_index_31(self):
        """B.Cu uses KiCad's internal index 31, not the sequential 3."""
        lc = LayerConfig("B.Cu", 31, "signal", 1.0, 0.035)
        assert lc.kicad_index == 31
        assert lc.name == "B.Cu"

    def test_inner_plane_layers(self):
        lc = LayerConfig("In1.Cu", 1, "plane", 0.5, 0.017)
        assert lc.type == "plane"
        assert lc.copper_weight_oz == 0.5
        assert lc.thickness_mm == 0.017

    def test_mixed_layer_type(self):
        lc = LayerConfig("F.Cu", 0, "mixed", 1.0, 0.035)
        assert lc.type == "mixed"


class TestStackup:
    def test_jlc04161h_7628_basics(self):
        s = jlc04161h_7628()
        assert s.name == "JLCPCB JLC04161H-7628"
        assert len(s.layers) == 4
        assert s.total_thickness_mm == 1.6
        assert s.prepreg_outer_mm == 0.2
        assert s.core_inner_mm == 1.1
        assert s.dielectric_constant == 4.5

    def test_jlc_layer_names(self):
        s = jlc04161h_7628()
        names = [ly.name for ly in s.layers]
        assert names == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]

    def test_jlc_kicad_indices(self):
        s = jlc04161h_7628()
        indices = [ly.kicad_index for ly in s.layers]
        assert indices == [0, 1, 2, 31]

    def test_jlc_copper_weights(self):
        s = jlc04161h_7628()
        weights = [ly.copper_weight_oz for ly in s.layers]
        # 1oz outer, 0.5oz inner
        assert weights == [1.0, 0.5, 0.5, 1.0]

    def test_jlc_copper_thicknesses(self):
        s = jlc04161h_7628()
        thicknesses = [ly.thickness_mm for ly in s.layers]
        # 35um outer, 17um inner
        assert thicknesses == [0.035, 0.017, 0.017, 0.035]

    def test_jlc_layer_types(self):
        s = jlc04161h_7628()
        types = [ly.type for ly in s.layers]
        assert types == ["signal", "plane", "plane", "signal"]

    def test_total_thickness_sum_consistency(self):
        """Copper + dielectric should sum to approximately total_thickness_mm."""
        s = jlc04161h_7628()
        copper_sum = sum(ly.thickness_mm for ly in s.layers)
        dielectric_sum = 2 * s.prepreg_outer_mm + s.core_inner_mm  # 0.2+1.1+0.2
        computed_total = copper_sum + dielectric_sum
        # Allow small rounding tolerance
        assert computed_total == pytest.approx(s.total_thickness_mm, abs=0.01)


class TestCharacteristicImpedanceMicrostrip:
    def test_impedance_for_typical_usb_trace(self):
        """A 0.3mm-wide trace on F.Cu over 0.2mm prepreg should be ~50-60 ohm."""
        s = jlc04161h_7628()
        z0 = characteristic_impedance_microstrip(0.3, s)
        # 0.3mm on 0.2mm prepreg, er=4.5: expect ~55 ohm
        assert 45 <= z0 <= 65

    def test_impedance_increases_with_wider_trace(self):
        """Wider trace -> lower impedance (more capacitance to plane)."""
        s = jlc04161h_7628()
        z0_narrow = characteristic_impedance_microstrip(0.2, s)
        z0_wide = characteristic_impedance_microstrip(0.5, s)
        assert z0_narrow > z0_wide

    def test_impedance_decreases_with_higher_er(self):
        """Higher dielectric constant -> lower impedance."""
        s_low_er = Stackup(
            name="test-low-er",
            layers=[LayerConfig("F.Cu", 0, "signal", 1.0, 0.035)],
            total_thickness_mm=1.6,
            prepreg_outer_mm=0.2,
            core_inner_mm=1.1,
            dielectric_constant=3.5,
        )
        s_high_er = Stackup(
            name="test-high-er",
            layers=[LayerConfig("F.Cu", 0, "signal", 1.0, 0.035)],
            total_thickness_mm=1.6,
            prepreg_outer_mm=0.2,
            core_inner_mm=1.1,
            dielectric_constant=5.0,
        )
        z0_low = characteristic_impedance_microstrip(0.3, s_low_er)
        z0_high = characteristic_impedance_microstrip(0.3, s_high_er)
        assert z0_low > z0_high

    def test_impedance_decreases_with_thinner_dielectric(self):
        """Thinner prepreg -> lower impedance (field is more concentrated)."""
        s_thin = Stackup(
            name="test-thin",
            layers=[LayerConfig("F.Cu", 0, "signal", 1.0, 0.035)],
            total_thickness_mm=1.6,
            prepreg_outer_mm=0.1,
            core_inner_mm=1.3,
            dielectric_constant=4.5,
        )
        s_thick = Stackup(
            name="test-thick",
            layers=[LayerConfig("F.Cu", 0, "signal", 1.0, 0.035)],
            total_thickness_mm=1.6,
            prepreg_outer_mm=0.4,
            core_inner_mm=0.7,
            dielectric_constant=4.5,
        )
        z0_thin = characteristic_impedance_microstrip(0.3, s_thin)
        z0_thick = characteristic_impedance_microstrip(0.3, s_thick)
        assert z0_thin < z0_thick

    def test_jlc_usb_trace_90ohm_differential(self):
        """Verify 0.3mm trace on JLC stackup yields single-ended Z0 in the 50-60 ohm
        range, which with typical USB pair spacing (0.2mm) gives ~90 ohm diff."""
        s = jlc04161h_7628()
        z0 = characteristic_impedance_microstrip(0.3, s)
        # Single-ended 50-60 ohm with 0.2mm spacing ~ 90 ohm diff pair
        assert 48 <= z0 <= 62, (
            f"Expected Z0 ~50-60 ohm for 0.3mm trace on JLC04161H-7628, got {z0:.1f}"
        )
