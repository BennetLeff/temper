"""Tests for validation.spice module — SpiceResult, SpiceMeasurement, PlacementSpiceResult."""
from temper_placer.validation.base import (
    ValidationIssue,
    ValidationResult,
    ValidationSeverity,
)
from temper_placer.validation.spice import (
    SpiceMeasurement,
    SpiceResult,
)


class TestSpiceMeasurement:
    """Tests for SpiceMeasurement."""

    def test_create_minimal(self):
        m = SpiceMeasurement(name="power", value=5.0)
        assert m.name == "power"
        assert m.value == 5.0
        assert m.unit == ""
        assert m.targ is None
        assert m.trig is None
        assert m.raw_line == ""

    def test_to_dict(self):
        m = SpiceMeasurement(
            name="vout",
            value=3.3,
            unit="V",
            targ=10.0,
            trig=0.5,
            raw_line="vout = 3.3",
        )
        d = m.to_dict()
        assert d["name"] == "vout"
        assert d["value"] == 3.3
        assert d["unit"] == "V"
        assert d["targ"] == 10.0
        assert d["trig"] == 0.5

    def test_to_dict_minimal(self):
        m = SpiceMeasurement(name="x", value=0.0)
        d = m.to_dict()
        assert d["targ"] is None
        assert d["trig"] is None
        assert d["unit"] == ""


class TestSpiceResult:
    """Tests for SpiceResult."""

    def test_get_value_found(self):
        m = SpiceMeasurement(name="vout", value=3.3)
        r = SpiceResult(success=True, measurements={"vout": m})
        assert r.get_value("vout") == 3.3

    def test_get_value_missing_default(self):
        r = SpiceResult(success=True)
        assert r.get_value("missing") == 0.0

    def test_get_value_custom_default(self):
        r = SpiceResult(success=True)
        assert r.get_value("missing", default=-1.0) == -1.0

    def test_summary_success(self):
        r = SpiceResult(success=True, elapsed_ms=42.0)
        s = r.summary()
        assert "SUCCESS" in s
        assert "42.0ms" in s

    def test_summary_failed(self):
        r = SpiceResult(success=False, errors=["simulation error"])
        s = r.summary()
        assert "FAILED" in s
        assert "simulation error" in s

    def test_summary_with_measurements(self):
        m = SpiceMeasurement(name="vout", value=3.3)
        r = SpiceResult(success=True, measurements={"vout": m})
        s = r.summary()
        assert "vout" in s
        assert "3.3" in s

    def test_default_construction(self):
        r = SpiceResult(success=True)
        assert r.measurements == {}
        assert r.errors == []
        assert r.warnings == []
        assert r.elapsed_ms == 0.0
        assert r.netlist_path is None
