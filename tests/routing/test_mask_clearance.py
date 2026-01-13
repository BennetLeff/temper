
import pytest
from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

def test_trace_width_inflation_violation():
    """
    Verify that blocking without accounting for trace width allows 
    traces to violate clearance requirements.
    """
    # Grid 5x5mm, 0.1mm resolution for precision
    grid = ClearanceGrid(width_mm=5.0, height_mm=5.0, cell_size_mm=0.1)
    
    # Pad at (2.0, 2.0) with Radius=0.5mm
    pad_pos = (2.0, 2.0)
    pad_radius = 0.5
    
    # Required Electrical Clearance = 0.2mm
    clearance = 0.2
    
    # We pretend to be ClearanceGridStage
    # Currently it blocks: radius + clearance
    # Block radius = 0.5 + 0.2 = 0.7mm
    grid.block_circle(pad_pos, radius_mm=pad_radius, clearance_mm=clearance)
    
    # Use a trace of width 0.25mm (radius 0.125mm)
    trace_width = 0.25
    trace_half_width = trace_width / 2.0
    
    # Test a point at distance 0.71mm from center
    # This is currently "Available" (0.71 > 0.70)
    # But physically: 
    #   Trace Center = 2.71
    #   Trace Inner Edge = 2.71 - 0.125 = 2.585
    #   Pad Edge = 2.0 + 0.5 = 2.500
    #   Gap = 2.585 - 2.500 = 0.085mm
    #   Required Gap = 0.2mm
    #   FAIL!
    
    test_x = pad_pos[0] + 0.71
    test_y = pad_pos[1]
    
    # Assert that the grid CURRENTLY thinks this is valid (reproducing the bug)
    assert grid.is_available(test_x, test_y), "Grid should falsely report this as available (bug reproduction)"
    
    # Now, calculate what the 'Safety Radius' SHOULD be
    # Safety = PadRadius + Clearance + TraceHalfWidth
    #        = 0.5 + 0.2 + 0.125 = 0.825mm
    
    safety_limit_x = pad_pos[0] + 0.825 + 0.01 # Just outside
    
    # If we apply the fix (inflation), the point at 0.71 should be BLOCKED.
    # We can't test the fix in this same test unless we modify the grid.
    
def test_mask_clearance_calculation():
    """Verify the logic for mask clearance vs electrical clearance."""
    electrical_clearance = 0.2
    mask_expansion = 0.05
    min_web = 0.1
    
    required_mask_spacing = mask_expansion + min_web # 0.15
    
    # If we only enforce electrical (0.2), we effectively enforce:
    # Gap = 0.2
    # Mask Web = Gap - mask_expansion_pad - mask_expansion_trace (approx)
    #          = 0.2 - 0.05 - 0.05 = 0.1mm (Just barely enough!)
    
    # BUT if we have Grid Quantization error (e.g. 0.05mm error), 
    # we might dip below 0.1mm.
    pass
