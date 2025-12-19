"""
Tests for component_factory fixture (temper-1my.1.3).

Validates that the footprint library integration with test fixtures works correctly.
"""

import pytest
from temper_placer.core.netlist import Component, Pin


def test_component_factory_basic(component_factory):
    """Test creating component with library bounds."""
    comp = component_factory("R1", "0805")

    assert comp.ref == "R1"
    assert comp.footprint == "0805"
    assert comp.bounds == (2.0, 1.25)  # From library


def test_component_factory_with_pins(component_factory):
    """Test creating component with pins."""
    comp = component_factory(
        "U1",
        "SOIC-8",
        pins=[
            Pin("VCC", "8", (2.0, 1.5)),
            Pin("GND", "4", (-2.0, -1.5)),
        ]
    )

    assert comp.bounds == (5.0, 4.0)  # From library
    assert len(comp.pins) == 2


def test_component_factory_large_footprint(component_factory):
    """Test with large power component."""
    comp = component_factory("Q1", "TO-247-3")

    assert comp.bounds == (16.0, 21.0)  # From library


def test_component_factory_unknown_footprint(component_factory):
    """Test that unknown footprints raise error."""
    with pytest.raises(ValueError, match="Unknown footprint"):
        component_factory("X1", "NONEXISTENT_FOOTPRINT")


def test_component_factory_warns_on_mismatch(component_factory):
    """Test warning when hardcoded bounds differ from library."""
    with pytest.warns(UserWarning, match="hardcoded bounds"):
        comp = component_factory("R1", "0805", bounds=(999.0, 999.0))

    # Should use library value, not hardcoded
    assert comp.bounds == (2.0, 1.25)


def test_library_loaded_once(footprint_library):
    """Test that library is loaded once per session (session scope)."""
    assert len(footprint_library) > 0
    assert "0805" in footprint_library
    assert "TO-247-3" in footprint_library


def test_footprint_library_has_temper_components(footprint_library):
    """Verify library has key Temper components."""
    required_footprints = [
        "TO-247-3",     # IGBTs
        "SOIC-16_W",    # Gate driver
        "QFN-56",       # ESP32-S3
        "TSSOP-20",     # MAX31865
        "0805",         # Standard passives
        "0603",         # Small passives
        "2512",         # Current sense resistors
    ]

    for fp in required_footprints:
        assert fp in footprint_library, f"Missing footprint: {fp}"


def test_footprint_specs_accurate(footprint_library):
    """Verify footprint specs match expected values."""
    # IGBTs
    to247 = footprint_library["TO-247-3"]
    assert to247.bounds == (16.0, 21.0)
    assert to247.thermal_pad is True

    # Standard resistor
    r0805 = footprint_library["0805"]
    assert r0805.bounds == (2.0, 1.25)
    assert r0805.thermal_pad is False

    # MCU
    mcu = footprint_library["QFN-56"]
    assert mcu.bounds == (7.0, 7.0)
    assert mcu.thermal_pad is True
