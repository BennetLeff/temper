
import pytest
from temper_placer.core.placement_drc import validate_placement_drc, PinInfo

def test_drc_short_circuit():
    """Test detection of physical shorts (dist < radii sum)."""
    # Two pins, radius 0.5mm, distance 0.5mm (Short)
    pins = [
        PinInfo(x=10.0, y=10.0, net_name="NET_A", component_name="U1", pin_name="1", diameter_mm=1.0),
        PinInfo(x=10.5, y=10.0, net_name="NET_B", component_name="U2", pin_name="2", diameter_mm=1.0)
    ]
    
    violations = validate_placement_drc(pins, min_clearance_mm=0.2)
    assert len(violations) == 1
    assert violations[0].violation_type == "SHORT"
    assert "Pads overlapping" in violations[0].message

def test_drc_clearance_violation():
    """Test detection of clearance violation (dist < radii sum + clearance)."""
    # Two pins, radius 0.5mm, required clearance 0.2mm
    # Required dist = 0.5 + 0.5 + 0.2 = 1.2mm
    # Actual dist = 1.1mm (Violation)
    pins = [
        PinInfo(x=10.0, y=10.0, net_name="NET_A", component_name="U1", pin_name="1", diameter_mm=1.0),
        PinInfo(x=11.1, y=10.0, net_name="NET_B", component_name="U2", pin_name="2", diameter_mm=1.0)
    ]
    
    violations = validate_placement_drc(pins, min_clearance_mm=0.2)
    assert len(violations) == 1
    assert violations[0].violation_type == "CLEARANCE"
    assert "Clearance violation" in violations[0].message

def test_drc_no_violation():
    """Test that valid placement passes."""
    # Distance 1.3mm > 1.2mm required
    pins = [
        PinInfo(x=10.0, y=10.0, net_name="NET_A", component_name="U1", pin_name="1", diameter_mm=1.0),
        PinInfo(x=11.3, y=10.0, net_name="NET_B", component_name="U2", pin_name="2", diameter_mm=1.0)
    ]
    
    violations = validate_placement_drc(pins, min_clearance_mm=0.2)
    assert len(violations) == 0

def test_same_net_no_violation():
    """Test that same net items don't strictly violate placement DRC."""
    # Overlapping but same net
    pins = [
        PinInfo(x=10.0, y=10.0, net_name="NET_A", component_name="U1", pin_name="1", diameter_mm=1.0),
        PinInfo(x=10.1, y=10.0, net_name="NET_A", component_name="U2", pin_name="2", diameter_mm=1.0)
    ]
    
    violations = validate_placement_drc(pins, min_clearance_mm=0.2)
    assert len(violations) == 0
