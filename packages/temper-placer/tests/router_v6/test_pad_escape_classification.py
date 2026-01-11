"""
Tests for Router V6 Stage 1.2: Classify Pads by Escape Need

Part of temper-qvpt
"""

import pytest

from temper_placer.core.netlist import Component, Pin
from temper_placer.router_v6.dense_package_detection import DensePackage
from temper_placer.router_v6.pad_escape_classification import (
    ClassifiedPad,
    EscapeClass,
    classify_pads_by_escape_need,
    _is_thermal_pad,
)


def _create_qfn_component() -> Component:
    """Create a QFN-48 test component with peripheral and interior pads."""
    pins = []
    
    # Peripheral pads (edge of 7x7mm component)
    for i in range(12):
        pins.append(Pin(
            name=str(i + 1),
            number=str(i + 1),
            position=(0.5, i * 0.5),  # Left edge
            net=f"NET{i}",
            width=0.3,
            height=0.25,
            shape="rect",
            layer="F.Cu",
        ))
    
    # Interior pad (center thermal pad)
    pins.append(Pin(
        name="EPAD",
        number="49",
        position=(3.5, 3.5),  # Center of 7x7mm
        net="GND",
        width=5.0,  # Large thermal pad
        height=5.0,
        shape="rect",
        layer="F.Cu",
    ))
    
    return Component(
        ref="U1",
        footprint="QFN-48_7x7mm",
        bounds=(7.0, 7.0),
        pins=pins,
        initial_position=(50.0, 50.0),
    )


def _create_bga_component() -> Component:
    """Create a BGA component with interior pads."""
    pins = []
    
    # BGA grid: 5x5 array on 15x15mm component
    for row in range(5):
        for col in range(5):
            pins.append(Pin(
                name=f"{chr(65+row)}{col+1}",  # A1, A2, ..., E5
                number=f"{row*5 + col + 1}",
                position=(3.0 * col + 1.5, 3.0 * row + 1.5),
                net=f"NET{row}_{col}",
                width=0.5,
                height=0.5,
                shape="circle",
                layer="F.Cu",
            ))
    
    return Component(
        ref="U2",
        footprint="BGA-25_15x15mm",
        bounds=(15.0, 15.0),
        pins=pins,
        initial_position=(50.0, 50.0),
    )


def test_classify_pads_qfn_peripheral():
    """Test that QFN edge pads are classified as PERIPHERAL."""
    comp = _create_qfn_component()
    pkg = DensePackage(
        component=comp,
        pin_count=13,
        pitch_mm=0.5,
        package_type="QFN",
        requires_escape=True,
    )
    
    classified = classify_pads_by_escape_need([pkg])
    
    # Edge pads should be PERIPHERAL
    peripheral = [p for p in classified if p.escape_class == EscapeClass.PERIPHERAL]
    assert len(peripheral) == 12  # 12 edge pads


def test_classify_pads_qfn_thermal():
    """Test that QFN thermal pad is classified as THERMAL_PAD."""
    comp = _create_qfn_component()
    pkg = DensePackage(
        component=comp,
        pin_count=13,
        pitch_mm=0.5,
        package_type="QFN",
        requires_escape=True,
    )
    
    classified = classify_pads_by_escape_need([pkg])
    
    # Center thermal pad should be THERMAL_PAD
    thermal = [p for p in classified if p.escape_class == EscapeClass.THERMAL_PAD]
    assert len(thermal) == 1
    assert thermal[0].pin.name == "EPAD"


def test_classify_pads_bga_interior():
    """Test that BGA interior pads are classified as INTERIOR."""
    comp = _create_bga_component()
    pkg = DensePackage(
        component=comp,
        pin_count=25,
        pitch_mm=0.8,
        package_type="BGA",
        requires_escape=True,
    )
    
    classified = classify_pads_by_escape_need([pkg], interior_threshold_mm=1.0)
    
    # BGA should have interior pads (center of grid)
    interior = [p for p in classified if p.escape_class == EscapeClass.INTERIOR]
    assert len(interior) > 0  # Center pads are interior
    
    # Check that center pad (C3) is interior
    c3_pads = [p for p in classified if p.pin.name == "C3"]
    assert len(c3_pads) == 1
    assert c3_pads[0].escape_class == EscapeClass.INTERIOR


def test_classify_pads_needs_escape_via():
    """Test ClassifiedPad.needs_escape_via property."""
    comp = _create_qfn_component()
    pkg = DensePackage(
        component=comp,
        pin_count=13,
        pitch_mm=0.5,
        package_type="QFN",
        requires_escape=True,
    )
    
    classified = classify_pads_by_escape_need([pkg])
    
    # Peripheral pads don't need escape vias
    peripheral = [p for p in classified if p.escape_class == EscapeClass.PERIPHERAL]
    assert all(not p.needs_escape_via for p in peripheral)
    
    # Thermal pad doesn't need escape via (different handling)
    thermal = [p for p in classified if p.escape_class == EscapeClass.THERMAL_PAD]
    assert all(not p.needs_escape_via for p in thermal)


def test_classify_pads_custom_threshold():
    """Test custom interior threshold."""
    comp = _create_bga_component()
    pkg = DensePackage(
        component=comp,
        pin_count=25,
        pitch_mm=0.8,
        package_type="BGA",
        requires_escape=True,
    )
    
    # With small threshold (0.5mm), most pads are interior (only edges are peripheral)
    classified_small = classify_pads_by_escape_need([pkg], interior_threshold_mm=0.5)
    interior_small = [p for p in classified_small if p.escape_class == EscapeClass.INTERIOR]
    
    # With large threshold (10.0mm), even more pads are interior
    classified_large = classify_pads_by_escape_need([pkg], interior_threshold_mm=10.0)
    interior_large = [p for p in classified_large if p.escape_class == EscapeClass.INTERIOR]
    
    # Larger threshold = more interior pads
    # (all 25 pads should be interior with 10mm threshold since max dist is < 10mm)
    assert len(interior_large) >= len(interior_small)
    assert len(interior_large) == 25  # All pads interior with large threshold


def test_is_thermal_pad_by_name():
    """Test thermal pad detection by name."""
    test_cases = [
        ("EPAD", True),
        ("PAD", True),
        ("THERMAL", True),
        ("GND", True),
        ("EP", True),
        ("VSS", True),
        ("PIN1", False),
        ("A1", False),
    ]
    
    comp = Component(
        ref="U1",
        footprint="QFN-48",
        bounds=(7.0, 7.0),
        pins=[],
        initial_position=(50.0, 50.0),
    )
    
    for pin_name, expected in test_cases:
        pin = Pin(
            name=pin_name,
            number="1",
            position=(3.5, 3.5),
            net="GND",
            width=1.0,
            height=1.0,
            shape="rect",
            layer="F.Cu",
        )
        # Temporarily add pin for avg calculation
        comp.pins = [pin]
        
        is_thermal = _is_thermal_pad(pin, comp)
        assert is_thermal == expected, f"Wrong thermal detection for {pin_name}"


def test_is_thermal_pad_by_position_and_size():
    """Test thermal pad detection by center position and large size."""
    # Create small signal pads
    signal_pins = [
        Pin(
            name=str(i),
            number=str(i),
            position=(i * 0.5, 0.0),
            net=f"NET{i}",
            width=0.3,
            height=0.25,
            shape="rect",
            layer="F.Cu",
        )
        for i in range(4)
    ]
    
    # Create large center pad
    center_pad = Pin(
        name="99",  # Not a thermal name
        number="99",
        position=(3.5, 3.5),  # Center of 7x7mm
        net="GND",
        width=4.0,  # Much larger than signal pads
        height=4.0,
        shape="rect",
        layer="F.Cu",
    )
    
    comp = Component(
        ref="U1",
        footprint="QFN-48",
        bounds=(7.0, 7.0),
        pins=signal_pins + [center_pad],
        initial_position=(50.0, 50.0),
    )
    
    # Center pad should be detected as thermal (center + large)
    assert _is_thermal_pad(center_pad, comp) is True
    
    # Signal pads should not be thermal
    assert _is_thermal_pad(signal_pins[0], comp) is False


def test_classify_pads_multiple_packages():
    """Test classifying pads from multiple dense packages."""
    comp1 = _create_qfn_component()
    comp2 = _create_bga_component()
    
    pkgs = [
        DensePackage(comp1, 13, 0.5, "QFN", True),
        DensePackage(comp2, 25, 0.8, "BGA", True),
    ]
    
    classified = classify_pads_by_escape_need(pkgs)
    
    # Should have pads from both components
    u1_pads = [p for p in classified if p.component_ref == "U1"]
    u2_pads = [p for p in classified if p.component_ref == "U2"]
    
    assert len(u1_pads) == 13  # QFN-48 + 1 thermal
    assert len(u2_pads) == 25  # BGA-25
