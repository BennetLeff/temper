#!/usr/bin/env python3
"""
EXP-06-A: Differential Pair Integrity Verification

Tests differential pair router against obstacle-splitting scenario.

SUCCESS CRITERIA:
- Coupling ratio >80% (pairs route together)
- No pair splitting around obstacles
- Length matching: max_skew <0.5mm
- Routes successfully complete

This verifies the Router V6 differential pair implementation addresses
the EXP-06-A gap identified in earlier experiments.
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.routing.diff_pair_router import DiffPairRouter
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def create_obstacle_test_pcb():
    """
    Create test PCB with obstacle between differential pair endpoints.
    
    Layout:
    [J1_P]----+         +----[J2_P]
              |  [OBS]  |
    [J1_N]----+         +----[J2_N]
    
    Obstacle forces router to choose: split or navigate together.
    """
    netlist = Netlist()
    
    # Start connectors (left side)
    j1_p = Component(name="J1_P", refdes="J1_P")
    j1_p.pins = [Pin(name="1", number="1", x=10.0, y=30.0)]
    
    j1_n = Component(name="J1_N", refdes="J1_N")
    j1_n.pins = [Pin(name="1", number="1", x=10.0, y=25.0)]
    
    # End connectors (right side)
    j2_p = Component(name="J2_P", refdes="J2_P")
    j2_p.pins = [Pin(name="1", number="1", x=50.0, y=30.0)]
    
    j2_n = Component(name="J2_N", refdes="J2_N")
    j2_n.pins = [Pin(name="1", number="1", x=50.0, y=25.0)]
    
    # Obstacle component (blocks direct path)
    obs = Component(name="OBS", refdes="U_OBS")
    obs.pins = [Pin(name="1", number="1", x=30.0, y=27.5)]  # Center
    
    netlist.components = [j1_p, j1_n, j2_p, j2_n, obs]
    
    # Differential pair nets
    net_p = Net(name="DP_P")
    net_p.add_pin_ref("J1_P", "1")
    net_p.add_pin_ref("J2_P", "1")
    
    net_n = Net(name="DP_N")
    net_n.add_pin_ref("J1_N", "1")
    net_n.add_pin_ref("J2_N", "1")
    
    netlist.nets = [net_p, net_n]
    
    return netlist


def run_exp_06_a():
    """Run EXP-06-A verification test."""
    print("\n" + "=" * 70)
    print("EXP-06-A: Differential Pair Integrity Verification")
    print("=" * 70 + "\n")
    
    # Create test PCB
    netlist = create_obstacle_test_pcb()
    board = Board(width_mm=60.0, height_mm=40.0)
    
    # Create router
    router = DiffPairRouter(
        grid_size=(300, 200, 2),  # 60mm/0.2mm = 300 cells wide
        cell_size_mm=0.2,
        target_separation_mm=0.2,  # 0.2mm separation (typical for diff pairs)
        max_skew_mm=0.5,
        beam_width=1000,
    )
    
    # Create obstacles from obstacle component
    # Block a 10mm x 10mm area around the obstacle
    obstacles = set()
    obs_center_x = int(30.0 / 0.2)  # 150 cells
    obs_center_y = int(27.5 / 0.2)  # 137 cells
    obs_radius = int(5.0 / 0.2)  # 25 cells (5mm radius)
    
    for dx in range(-obs_radius, obs_radius + 1):
        for dy in range(-obs_radius, obs_radius + 1):
            if dx*dx + dy*dy <= obs_radius*obs_radius:
                for layer in range(2):
                    obstacles.add((obs_center_x + dx, obs_center_y + dy, layer))
    
    print(f"🎯 Test Setup:")
    print(f"   Board: {board.width_mm}mm x {board.height_mm}mm")
    print(f"   Grid: {router.grid_size} @ {router.cell_size_mm}mm/cell")
    print(f"   Obstacle: 10mm diameter at (30.0, 27.5)")
    print(f"   Start: P=(10.0, 30.0), N=(10.0, 25.0)")
    print(f"   Goal:  P=(50.0, 30.0), N=(50.0, 25.0)")
    print(f"   Blocked cells: {len(obstacles)}\n")
    
    # Route the pair
    print("🔧 Routing differential pair...")
    result = router.route_pair(
        start_pins=((10.0, 30.0), (10.0, 25.0)),
        goal_pins=((50.0, 30.0), (50.0, 25.0)),
        obstacles=obstacles,
        enable_length_matching=True,
    )
    
    # Display results
    print(f"\n📊 Results:")
    print(f"   Success: {result.success}")
    
    if result.success:
        print(f"   Coupling Ratio: {result.coupling_ratio:.1f}%")
        print(f"   Max Skew: {result.max_skew_mm:.3f}mm")
        print(f"   Avg Separation: {result.avg_separation_mm:.3f}mm")
        print(f"   P trace length: {len(result.pos_cells)} cells")
        print(f"   N trace length: {len(result.neg_cells)} cells")
        print(f"   States explored: {router.states_explored}")
        print(f"   States pruned (coupling): {router.states_pruned}")
        print(f"   Beam pruned: {router.beam_pruned}")
    else:
        print(f"   Failure: {result.failure_reason}")
    
    # Verify success criteria
    print(f"\n✅ Success Criteria:")
    
    criteria_met = []
    criteria_met.append(("Routes complete", result.success))
    
    if result.success:
        criteria_met.append(("Coupling >80%", result.coupling_ratio > 80.0))
        criteria_met.append(("Skew <0.5mm", result.max_skew_mm < 0.5))
        
        # Check for splitting (heuristic: if traces diverge significantly)
        avg_sep = result.avg_separation_mm
        criteria_met.append(("No excessive splitting", avg_sep < 1.0))
    
    for criterion, passed in criteria_met:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {status}: {criterion}")
    
    all_passed = all(passed for _, passed in criteria_met)
    
    print("\n" + "=" * 70)
    if all_passed:
        print("🎉 EXP-06-A: PASS - Differential pair routing verified!")
    else:
        print("❌ EXP-06-A: FAIL - Some criteria not met")
    print("=" * 70 + "\n")
    
    return all_passed


if __name__ == "__main__":
    success = run_exp_06_a()
    sys.exit(0 if success else 1)
