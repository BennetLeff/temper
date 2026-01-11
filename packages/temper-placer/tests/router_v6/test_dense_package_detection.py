"""
Tests for Router V6 Stage 1.1: Identify Dense Packages

Part of temper-wpwf
"""

import pytest

from temper_placer.core.netlist import Component, Pin
from temper_placer.router_v6.dense_package_detection import (
    DensePackage,
    identify_dense_packages,
    _estimate_pitch,
    _infer_package_type,
)


def _create_test_component(ref: str, footprint: str, pin_count: int, bounds: tuple[float, float] = (7.0, 7.0)) -> Component:
    """Helper to create test components."""
    pins = [
        Pin(
            name=str(i + 1),
            number=str(i + 1),
            position=(0.0, i * 0.5),
            net="GND" if i == 0 else f"NET{i}",
            width=0.3,
            height=0.3,
            shape="rect",
            layer="F.Cu",
        )
        for i in range(pin_count)
    ]
    return Component(
        ref=ref,
        footprint=footprint,
        bounds=bounds,
        pins=pins,
        initial_position=(50.0, 50.0),
    )


def test_identify_dense_packages_qfn():
    """Test QFN package detection."""
    comp = _create_test_component("U1", "QFN-48_0.5mm", 48)
    
    dense = identify_dense_packages([comp])
    
    assert len(dense) == 1
    assert dense[0].component.ref == "U1"
    assert dense[0].pin_count == 48
    assert dense[0].pitch_mm == 0.5
    assert dense[0].package_type == "QFN"
    assert dense[0].requires_escape is True  # 0.5mm < 0.5mm threshold (fine pitch)


def test_identify_dense_packages_bga():
    """Test BGA package detection."""
    comp = _create_test_component("U2", "BGA-256_0.8mm", 256, bounds=(15.0, 15.0))
    
    dense = identify_dense_packages([comp])
    
    assert len(dense) == 1
    assert dense[0].package_type == "BGA"
    assert dense[0].requires_escape is True  # BGA always requires escape
    assert dense[0].is_bga is True
    assert dense[0].is_qfn is False


def test_identify_dense_packages_coarse_pitch():
    """Test that coarse-pitch packages are not marked as requiring escape."""
    comp = _create_test_component("U3", "SOIC-16_1.27mm", 16)
    
    dense = identify_dense_packages([comp])
    
    # SOIC-16 with 1.27mm pitch is NOT dense
    assert len(dense) == 1
    assert dense[0].pitch_mm == 1.27
    assert dense[0].requires_escape is False  # 1.27mm > 0.5mm threshold


def test_identify_dense_packages_min_pin_filter():
    """Test that low pin count components are filtered."""
    comp = _create_test_component("R1", "0805", 2)
    
    dense = identify_dense_packages([comp], min_pin_count=16)
    
    # 2-pin resistor should be filtered out
    assert len(dense) == 0


def test_identify_dense_packages_multiple():
    """Test multiple components."""
    comps = [
        _create_test_component("U1", "QFN-48_0.5mm", 48),
        _create_test_component("U2", "BGA-256_0.8mm", 256),
        _create_test_component("U3", "SOIC-16_1.27mm", 16),
        _create_test_component("R1", "0805", 2),
    ]
    
    dense = identify_dense_packages(comps)
    
    # Should find QFN-48 and BGA-256 and SOIC-16 (but SOIC doesn't require escape)
    assert len(dense) == 3
    refs = {d.component.ref for d in dense}
    assert refs == {"U1", "U2", "U3"}
    
    # Check which require escape
    escape_refs = {d.component.ref for d in dense if d.requires_escape}
    assert escape_refs == {"U1", "U2"}  # QFN and BGA


def test_estimate_pitch_from_footprint_name():
    """Test pitch estimation from footprint name."""
    test_cases = [
        ("QFN-48_0.5mm", 0.5),
        ("TQFP-100_0.4mm", 0.4),
        ("BGA-256_0.8mm", 0.8),
        ("SOIC-16_1.27mm", 1.27),
    ]
    
    for footprint, expected_pitch in test_cases:
        comp = _create_test_component("U1", footprint, 16)
        pitch = _estimate_pitch(comp)
        assert pitch == expected_pitch, f"Wrong pitch for {footprint}"


def test_estimate_pitch_from_pin_positions():
    """Test pitch calculation from actual pin positions."""
    # Create component with pins at 0.5mm spacing
    pins = [
        Pin(name=str(i), number=str(i), position=(0.0, i * 0.5), net=f"NET{i}",
             width=0.2, height=0.2, shape="rect", layer="F.Cu")
        for i in range(4)
    ]
    comp = Component(
        ref="U1",
        footprint="CUSTOM",  # No pitch in name
        bounds=(5.0, 5.0),
        pins=pins,
        initial_position=(50.0, 50.0),
    )
    
    pitch = _estimate_pitch(comp)
    assert abs(pitch - 0.5) < 0.01  # Should calculate 0.5mm from positions


def test_infer_package_type():
    """Test package type inference."""
    test_cases = [
        ("QFN-48_0.5mm", "QFN"),
        ("BGA-256_0.8mm", "BGA"),
        ("FBGA-484", "BGA"),
        ("TQFP-100", "TQFP"),
        ("LQFP-64", "TQFP"),
        ("SOIC-16", "SOIC"),
        ("SSOP-28", "SOIC"),
        ("SOT-23", "SOT"),
        ("UNKNOWN_PKG", "UNKNOWN"),
    ]
    
    for footprint, expected_type in test_cases:
        comp = _create_test_component("U1", footprint, 16)
        pkg_type = _infer_package_type(comp)
        assert pkg_type == expected_type, f"Wrong type for {footprint}"


def test_dense_package_properties():
    """Test DensePackage dataclass properties."""
    comp = _create_test_component("U1", "QFN-48_0.5mm", 48)
    pkg = DensePackage(
        component=comp,
        pin_count=48,
        pitch_mm=0.5,
        package_type="QFN",
        requires_escape=True,
    )
    
    assert pkg.is_qfn is True
    assert pkg.is_bga is False
    
    # Test BGA
    comp_bga = _create_test_component("U2", "BGA-256", 256)
    pkg_bga = DensePackage(
        component=comp_bga,
        pin_count=256,
        pitch_mm=0.8,
        package_type="BGA",
        requires_escape=True,
    )
    
    assert pkg_bga.is_qfn is False
    assert pkg_bga.is_bga is True


def test_identify_dense_packages_custom_threshold():
    """Test custom dense threshold."""
    comp = _create_test_component("U1", "SOIC-16_0.65mm", 16)
    
    # With default threshold (0.5mm), 0.65mm is not dense
    dense_default = identify_dense_packages([comp])
    assert dense_default[0].requires_escape is False
    
    # With custom threshold (1.0mm), 0.65mm is dense
    dense_custom = identify_dense_packages([comp], dense_threshold_mm=1.0)
    assert dense_custom[0].requires_escape is True
