
import pytest
import numpy as np
from temper_placer.routing.maze_router import MazeRouter, GridCell
from temper_placer.core.design_rules import DesignRules, NetClassRules
from temper_placer.routing.constraints import DRCOracle
from temper_placer.routing.constraints.design_rules import ClearanceMatrix

def test_register_routed_path_dynamic_geometry():
    # Setup
    rules = NetClassRules(
        name="HighCurrent",
        trace_width=2.0,
        clearance=0.5,
        via_diameter=1.2,
        via_drill=0.6
    )
    
    design_rules = DesignRules(net_classes={"HighCurrent": rules})
    matrix = ClearanceMatrix()
    matrix.add_net_class_rules(rules)
    oracle = DRCOracle(rules=matrix)
    # Ensure num_layers=2 to match GridCell(..., layer=1)
    router = MazeRouter(grid_size=(100, 100), cell_size_mm=0.1, num_layers=2, drc_oracle=oracle, design_rules=design_rules)
    
    # Path with a via
    cells = [
        GridCell(10, 10, 0),
        GridCell(11, 10, 0),
        GridCell(11, 10, 1),
        GridCell(12, 10, 1)
    ]
    
    # Register path
    router._register_routed_path(cells, "TEST_NET", rules=rules)
    
    # Verify in DRCOracle
    tracks = [t for t in oracle.geometry.tracks if t.net == "TEST_NET"]
    vias = [v for v in oracle.geometry.vias if v.net == "TEST_NET"]
    
    assert len(tracks) == 2
    assert len(vias) == 1
    
    # Check track width
    assert tracks[0].width == 2.0
    
    # Check via geometry
    assert vias[0].diameter == 1.2
    assert vias[0].drill == 0.6

def test_register_routed_path_neckdown():
    # Setup
    rules = NetClassRules(
        name="Power",
        trace_width=1.0,
        clearance=0.3
    )
    
    design_rules = DesignRules(net_classes={"Power": rules})
    matrix = ClearanceMatrix()
    matrix.add_net_class_rules(rules)
    oracle = DRCOracle(rules=matrix)
    router = MazeRouter(grid_size=(100, 100), cell_size_mm=0.1, num_layers=1, drc_oracle=oracle, design_rules=design_rules)
    
    # Set neckdown mask for some cells
    router.neckdown_mask[11, 10, 0] = True
    
    # Path through neckdown zone
    cells = [
        GridCell(10, 10, 0),
        GridCell(11, 10, 0),
        GridCell(12, 10, 0)
    ]
    
    # Register path
    router._register_routed_path(cells, "POWER_NET", rules=rules)
    
    # Verify track widths
    tracks = [t for t in oracle.geometry.tracks if t.net == "POWER_NET"]
    assert len(tracks) == 2
    
    # First track segment (10,10) to (11,10) involves (11,10) which is neckdown
    # neckdown_width = max(0.1, 1.0 - 0.05) = 0.95
    assert tracks[0].width == pytest.approx(0.95)
    assert tracks[1].width == pytest.approx(0.95)

def test_route_net_mst_passes_rules():
    # Setup
    rules = NetClassRules(
        name="HighCurrent",
        trace_width=2.0,
        clearance=0.5,
        via_diameter=1.2,
        via_drill=0.6
    )
    design_rules = DesignRules(net_classes={"HighCurrent": rules})
    matrix = ClearanceMatrix()
    matrix.add_net_class_rules(rules)
    oracle = DRCOracle(rules=matrix)
    router = MazeRouter(grid_size=(100, 100), cell_size_mm=1.0, num_layers=2, drc_oracle=oracle, design_rules=design_rules)
    
    # Use a net name that will match HighCurrent patterns or explicitly assign it
    net_name = "COIL_A"
    pin_positions = [(10.0, 10.0), (20.0, 10.0)]
    # Use simple assignment
    from temper_placer.routing.layer_assignment import LayerAssignment, Layer
    assignment = LayerAssignment(net=net_name, primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP})
    
    router.route_net_mst(net_name, pin_positions, assignment)
    
    # Verify track width in oracle
    tracks = [t for t in oracle.geometry.tracks if t.net == net_name]
    assert len(tracks) > 0
    assert tracks[0].width == 2.0
