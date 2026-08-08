"""Tests for core.manufacturing module."""

import pytest

from temper_placer.core.manufacturing import (
    get_fab_presets,
    inflated_clearance,
    inflated_width,
)


class TestFabPresets:
    """Tests for get_fab_presets and FabPreset."""

    def test_get_fab_presets_nonempty(self):
        presets = get_fab_presets()
        assert isinstance(presets, dict)
        assert len(presets) > 0

    def test_presets_contain_jlcpcb(self):
        presets = get_fab_presets()
        names_lower = {k.lower() for k in presets}
        assert any("jlcpcb" in n for n in names_lower)


class TestToleranceArithmetic:
    """Tests for inflated_clearance and inflated_width."""

    def test_inflated_clearance_default_tolerance(self):
        """Default tolerance subtracts 0.1."""
        result = inflated_clearance(0.5)
        assert result == pytest.approx(0.4)

    def test_inflated_clearance_custom_tolerance(self):
        result = inflated_clearance(0.5, tolerance=0.2)
        assert result == pytest.approx(0.3)

    def test_inflated_clearance_zero_nominal(self):
        """Nominal - tolerance, clamped to 0."""
        result = inflated_clearance(0.05, tolerance=0.1)
        assert result == 0.0

    def test_inflated_clearance_negative_clamped(self):
        """Negative result clamped to 0.0."""
        result = inflated_clearance(0.1, tolerance=0.2)
        assert result == 0.0

    def test_inflated_width_default_tolerance(self):
        """Default tolerance adds 0.1."""
        result = inflated_width(0.5)
        assert result == pytest.approx(0.6)

    def test_inflated_width_custom_tolerance(self):
        result = inflated_width(0.5, tolerance=0.15)
        assert result == pytest.approx(0.65)

    def test_inflated_width_zero_nominal(self):
        result = inflated_width(0.0, tolerance=0.1)
        assert result == pytest.approx(0.1)

    def test_roundtrip_different(self):
        """Clearance shrinks, width grows."""
        nom = 0.5
        tol = 0.1
        c = inflated_clearance(nom, tol)
        w = inflated_width(nom, tol)
        assert c < nom
        assert w > nom
