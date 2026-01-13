import pytest
from temper_placer.deterministic.geometry.via_placement import (
    PadInfo, 
    place_via_with_clearance, 
    distance
)

def test_via_valid_position_unchanged():
    pads = [PadInfo(position=(10, 10), radius=0.5, mask_expansion=0.1)]
    target = (20, 20)  # Far from pad
    result = place_via_with_clearance(target, pads, via_mask_radius=0.4)
    assert result == target

def test_via_shifted_from_adjacent_pad():
    # Required distance = via_mask(0.4) + pad_mask(0.5+0.1) + gap(0.1) = 1.1mm
    pads = [PadInfo(position=(10, 10), radius=0.5, mask_expansion=0.1)]
    target = (10.5, 10)  # Only 0.5mm from pad center - too close
    result = place_via_with_clearance(target, pads, via_mask_radius=0.4)
    
    assert result is not None
    assert result != target
    assert distance(result, pads[0].position) >= 1.1

def test_via_between_pads():
    pads = [
        PadInfo(position=(10, 10), radius=0.5, mask_expansion=0.1),
        PadInfo(position=(12, 10), radius=0.5, mask_expansion=0.1)
    ]
    # Between pads at x=11. 
    # Distance to each is 1.0mm. Required is 1.1mm.
    target = (11, 10)
    result = place_via_with_clearance(target, pads, via_mask_radius=0.4)
    
    assert result is not None
    assert result != target
    # Should shift in Y to escape
    assert abs(result[1] - 10) > 0.1
    assert distance(result, pads[0].position) >= 1.1
    assert distance(result, pads[1].position) >= 1.1

def test_no_valid_position():
    # Surround target with large pads
    pads = []
    for angle in range(0, 360, 45):
        import math
        rad = math.radians(angle)
        pads.append(PadInfo(
            position=(10 + 1.0 * math.cos(rad), 10 + 1.0 * math.sin(rad)),
            radius=1.0,
            mask_expansion=0.1
        ))
    
    target = (10, 10)
    # Search up to 0.5mm
    result = place_via_with_clearance(target, pads, via_mask_radius=0.5, max_search_radius=0.5)
    assert result is None
