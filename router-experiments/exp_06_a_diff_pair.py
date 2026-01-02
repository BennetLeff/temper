
import logging
import sys
import jax.numpy as jnp
import numpy as np
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.config_loader import PlacementConstraints, NetClassRule, constraints_to_design_rules
from temper_placer.routing.maze_router import MazeRouter

logging.basicConfig(level=logging.INFO, format="%(message)s")

def calculate_coupling_ratio(path1, path2):
    """
    Calculate the percentage of path1 that is adjacent to path2.
    """
    if not path1.success or not path2.success:
        return 0.0
        
    coupled_cells = 0
    total_cells = len(path1.cells)
    
    # Simple adjacency check (this is an approximation, robust diff pair check is harder)
    # We check if for every cell in path1, there is a cell in path2 within 1 unit distance
    
    # Convert path2 cells to set of coordinates
    p2_coords = {(c.x, c.y, c.layer) for c in path2.cells}
    
    for c1 in path1.cells:
        # Check neighbors
        is_coupled = False
        # Neighbors: N, S, E, W, Diagram
        # Actually usually diff pairs are side-by-side.
        # Let's check distance.
        
        # Optimization: just check if any p2 cell is dist=1 away
        # This is O(N*M) or O(N) with set.
        
        # Specific check: parallel routing usually means dx=1 or dy=1
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0: continue
                if (c1.x + dx, c1.y + dy, c1.layer) in p2_coords:
                    is_coupled = True
                    break
            if is_coupled: break
            
        if is_coupled:
            coupled_cells += 1
            
    return coupled_cells / total_cells

def run_experiment():
    print("Running EXP-06-A: Differential Pair Integrity...")
    
    # 1. Setup Constraints
    constraints = PlacementConstraints(
        net_class_rules={
            "DiffPair": NetClassRule(
                name="DiffPair",
                trace_width_mm=0.2,
                clearance_mm=0.2
            )
        },
        net_classes={
            "NET_D_P": "DiffPair",
            "NET_D_N": "DiffPair"
        }
    )
    dr = constraints_to_design_rules(constraints)

    # 2. Board & Router
    router = MazeRouter(
        grid_size=(100, 100), # 10x10mm
        cell_size_mm=0.1,
        num_layers=2,
        design_rules=dr,
        min_clearance=0.1
    )
    
    # 3. Setup Diff Pair Scenario
    # Source: (2.0, 5.0) and (2.0, 5.4) -> Spaced 0.4mm (2 grid cells gap, 1 cell trace? 0.2mm trace, 0.2mm clear -> pitch 0.4mm?)
    # Sink: (8.0, 5.0) and (8.0, 5.4)
    
    # Obstacle in the middle at x=5.0
    # Block y=4.5 to y=6.0?
    # No, we want two paths.
    # Path A: Go ABOVE obstacle.
    # Path B: Go BELOW obstacle.
    # Obstacle: Rect at (5.0, 5.2), size (2.0, 2.0). 
    # This blocks the direct path.
    # Routing must go around.
    
    # But for diff pair, both mostly follow same way.
    # If gap is small, maybe they barely fit?
    
    # Let's make an obstacle that splits them.
    # Small obstacle right in the middle of where the pair "wants" to be.
    # x=5.0, y=5.2. Size=(1.0, 1.0).
    # Expected: D_P (starts at y=5.4) goes Above. D_N (starts at y=5.0) goes Below.
    # Result: Uncoupled (split) pair.
    
    c_obs = Component(ref="OBS", footprint="RECT", bounds=(2.0, 0.6), initial_position=(5.0, 5.2), initial_rotation=0, pins=[])
    
    c_s_p = Component(ref="S_P", footprint="PIN", bounds=(0.2,0.2), initial_position=(2.0, 5.4), initial_rotation=0, pins=[Pin(name="1", number="1", net="NET_D_P", position=(0,0))])
    c_s_n = Component(ref="S_N", footprint="PIN", bounds=(0.2,0.2), initial_position=(2.0, 5.0), initial_rotation=0, pins=[Pin(name="1", number="1", net="NET_D_N", position=(0,0))])
    
    c_e_p = Component(ref="E_P", footprint="PIN", bounds=(0.2,0.2), initial_position=(8.0, 5.4), initial_rotation=0, pins=[Pin(name="1", number="1", net="NET_D_P", position=(0,0))])
    c_e_n = Component(ref="E_N", footprint="PIN", bounds=(0.2,0.2), initial_position=(8.0, 5.0), initial_rotation=0, pins=[Pin(name="1", number="1", net="NET_D_N", position=(0,0))])
    
    components = [c_obs, c_s_p, c_s_n, c_e_p, c_e_n]
    netlist = Netlist(components=components, nets=[])
    pos_arr = jnp.array([c.initial_position for c in components])
    
    print("Blocking obstacles...")
    router.block_pads(components, pos_arr, netlist)
    
    print("\n=== Part 1: Independent Routing (Baseline) ===")
    # Route independently to show baseline behavior
    path_p = router.route_net_rrr("NET_D_P", [c_s_p.initial_position, c_e_p.initial_position], assignment=None)
    path_n = router.route_net_rrr("NET_D_N", [c_s_n.initial_position, c_e_n.initial_position], assignment=None)
    
    print(f"NET_D_P Success: {path_p.success}, Length: {path_p.length:.2f}mm")
    print(f"NET_D_N Success: {path_n.success}, Length: {path_n.length:.2f}mm")
    
    if path_p.success and path_n.success:
        coupling = calculate_coupling_ratio(path_p, path_n)
        length_delta = abs(path_p.length - path_n.length)
        print(f"Coupling Ratio: {coupling*100:.1f}%")
        print(f"Length Delta: {length_delta:.2f}mm")
        
        # Test length matching
        print("\n=== Part 2: Length Matching Test ===")
        from temper_placer.routing.post_processing.length_matcher import (
            LengthMatcher,
            SerpentineParams,
        )
        
        matcher = LengthMatcher()
        params = SerpentineParams(
            amplitude_mm=0.3,
            tolerance_mm=0.3,
            min_straight_length_mm=1.5,
        )
        
        # Apply length matching
        matched_p, matched_n = matcher.match_differential_pair_lengths(
            path_p, path_n, params
        )
        
        print(f"After Length Matching:")
        print(f"  NET_D_P Length: {matched_p.length:.2f}mm ({len(matched_p.cells)} cells)")
        print(f"  NET_D_N Length: {matched_n.length:.2f}mm ({len(matched_n.cells)} cells)")
        
        new_length_delta = abs(matched_p.length - matched_n.length)
        print(f"  Length Delta: {new_length_delta:.2f}mm")
        
        if new_length_delta < params.tolerance_mm:
            print(f"  ✓ SUCCESS: Length delta ({new_length_delta:.2f}mm) < tolerance ({params.tolerance_mm}mm)")
        else:
            print(f"  ✗ FAILED: Length delta ({new_length_delta:.2f}mm) >= tolerance ({params.tolerance_mm}mm)")
        
        # Original observation about coupling
        if coupling < 0.5:
             print("\nOBSERVATION: Router split the differential pair (Expected behavior for current router).")
             print("NOTE: Length matching addresses trace length, not coupling. Coupling requires Dual-Front A* (v35p.1.2).")
        else:
             print("\nSUCCESS: High coupling ratio! (Unexpectedly good behavior?)")
    else:
        print("Routing failed.")

if __name__ == "__main__":
    run_experiment()

