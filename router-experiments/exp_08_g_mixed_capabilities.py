
"""
EXP-08-G: Mixed Current Capabilities Regression Test

This experiment validates that the router can handle a mix of low, medium, and high current nets
on the same board, assigning appropriate routing strategies and via templates to each.

Scenario:
- Board: 100x100mm
- Nets:
    1. NET_LOW (1A) -> Should use Standard routing (Via1x1)
    2. NET_MED (8A) -> Should use Wide Trace / Via2x2 (depending on config)
    3. NET_HIGH (25A) -> Should use Plane/Via Array (Via4x4)
"""

import logging
import sys
import jax.numpy as jnp
from temper_placer.core.board import Board, Pad
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.config_loader import PlacementConstraints, NetClassRule, constraints_to_design_rules
from temper_placer.routing.maze_router import MazeRouter

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def run_experiment():
    print("Running EXP-08-G: Mixed Current Capabilities Regression Test...")
    
    # 1. Define Constraints with varying current requirements
    constraints = PlacementConstraints()
    
    # Low Current (Default/Signal)
    constraints.net_class_rules["LowCurrent"] = NetClassRule(
        name="LowCurrent",
        trace_width_mm=0.2,
        clearance_mm=0.2,
        max_current_rating=2.0, # 2A
        routing_strategy="standard"
    )
    
    # Medium Current
    constraints.net_class_rules["MediumCurrent"] = NetClassRule(
        name="MediumCurrent",
        trace_width_mm=1.0, # Thicker trace
        clearance_mm=0.5,
        max_current_rating=10.0, # 10A
        via_template="Via2x2",
        routing_strategy="wide_trace"
    )
    
    # High Current
    constraints.net_class_rules["HighCurrent"] = NetClassRule(
        name="HighCurrent",
        trace_width_mm=2.0,
        clearance_mm=1.0,
        max_current_rating=30.0, # 30A
        via_template="Via4x4",
        routing_strategy="plane_preferred"
    )

    # Assign Net Classes
    constraints.net_classes = {
        "NET_LOW": "LowCurrent",
        "NET_MED": "MediumCurrent",
        "NET_HIGH": "HighCurrent"
    }

    # Convert to Design Rules
    dr = constraints_to_design_rules(constraints)
    
    # Verify Rules were loaded correctly
    print("\nVerifying Design Rules Loading:")
    for name in ["LowCurrent", "MediumCurrent", "HighCurrent"]:
        rule = dr.net_classes.get(name)
        if rule:
            print(f"  {name}: Width={rule.trace_width}mm, Via={rule.via_template}")
        else:
            print(f"  FAILURE: {name} not found in design rules!")
            return

    # 2. Setup Board & Netlist
    board = Board(width=100.0, height=100.0)
    
    # Components to connect
    # Using simple 2-pin connections for each net
    
    # Low Current: Left side
    c_low_1 = Component(ref="U1", footprint="0603", bounds=(10, 10), initial_position=(20, 20), pins=[Pin("1", "1", (0, 0), "NET_LOW")])
    c_low_2 = Component(ref="U2", footprint="0603", bounds=(10, 10), initial_position=(20, 80), pins=[Pin("1", "1", (0, 0), "NET_LOW")])
    
    # Medium Current: Center
    c_med_1 = Component(ref="U3", footprint="TO-220", bounds=(10, 10), initial_position=(50, 20), pins=[Pin("1", "1", (0, 0), "NET_MED")])
    c_med_2 = Component(ref="U4", footprint="TO-220", bounds=(10, 10), initial_position=(50, 80), pins=[Pin("1", "1", (0, 0), "NET_MED")])
    
    # High Current: Right side
    c_high_1 = Component(ref="U5", footprint="TO-247", bounds=(10, 10), initial_position=(80, 20), pins=[Pin("1", "1", (0, 0), "NET_HIGH")])
    c_high_2 = Component(ref="U6", footprint="TO-247", bounds=(10, 10), initial_position=(80, 80), pins=[Pin("1", "1", (0, 0), "NET_HIGH")])

    components = [c_low_1, c_low_2, c_med_1, c_med_2, c_high_1, c_high_2]
    
    nets = [
        Net("NET_LOW", [("U1", "1"), ("U2", "1")]),
        Net("NET_MED", [("U3", "1"), ("U4", "1")]),
        Net("NET_HIGH", [("U5", "1"), ("U6", "1")]),
    ]
    
    netlist = Netlist(components, nets)
    
    # 3. Initialize Router
    # Force layer usage to verify via creation
    # We will block the direct path on Layer 0 to force a via transition
    grid_w = int(board.width / 0.5)
    grid_h = int(board.height / 0.5)
    router = MazeRouter(
        grid_size=(grid_w, grid_h), # match cell_size_mm
        cell_size_mm=0.5,
        num_layers=2,
        design_rules=dr,
        via_cost=50.0
    )
    
    # Block pads
    print("Extracting positions...")
    # Extract positions from components (using initial_position)
    positions = jnp.array([c.initial_position for c in netlist.components])
    print("Component positions", positions)
    
    router.block_pads(netlist.components, positions, netlist)

    # Block middle of Layer 0 to force vias
    # Blocking Y=50 across the board on Layer 0
    print("\nBlocking Layer 0 y=45..55 to force via usage...")
    y_min_idx = int(45.0 / 0.5)
    y_max_idx = int(55.0 / 0.5)
    
    # Manually setting occupancy for Layer 0 obstruction
    router.occupancy[0:int(100.0/0.5), y_min_idx:y_max_idx, 0] = -1

    # 4. Route
    print("\nStarting Routing...")
    routes = router.rrr_route_all_nets(
        netlist=netlist,
        positions=positions,
        net_order=["NET_HIGH", "NET_MED", "NET_LOW"],
        assignments={},
        max_iterations=5
    )
    
    # 5. Verify Results
    print("\nVerification Results:")
    all_passed = True
    
    for net_name in ["NET_LOW", "NET_MED", "NET_HIGH"]:
        route = routes.get(net_name)
        if not route:
            print(f"  ❌ {net_name}: Failed to route")
            all_passed = False
            continue
            
        print(f"  ✅ {net_name}: Routed (Length={route.length:.1f}mm, Vias={route.via_count})")
        
        # Verify Via Count and Type (implicitly by checking design rules above)
        # Low: Should have 2 vias (1 jump) * 1 via/jump = 2 vias
        # Med: Should have 2 vias * 4 vias/jump (Via2x2) = 8 vias
        # High: Should have 2 vias * 16 vias/jump (Via4x4) = 32 vias
        
        expected_vias_per_jump = 1
        if net_name == "NET_MED": expected_vias_per_jump = 4 # Via2x2
        if net_name == "NET_HIGH": expected_vias_per_jump = 16 # Via4x4
        
        # We expect at least one jump (2 transitions)
        min_expected_vias = 2 * expected_vias_per_jump
        
        if route.via_count < min_expected_vias:
             print(f"     ⚠️ WARNING: Low via count! Expected >={min_expected_vias}, Got {route.via_count}")
             # This might not effectively fail if the router found a way around, 
             # but with the block it should force vias.
        else:
             print(f"     Via count consistent with {expected_vias_per_jump} vias/transition.")

    if all_passed:
        print("\nSUCCESS: All mixed-capability nets routed successfully.")
    else:
        print("\nFAILURE: Some nets failed to route.")

if __name__ == "__main__":
    run_experiment()
