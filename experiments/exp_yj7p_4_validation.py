
import sys
import os
from pathlib import Path
import jax.numpy as jnp
from kiutils.board import Board as KiBoard

# Add packages to path
sys.path.insert(0, str(Path("packages/temper-placer/src").absolute()))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.unified_router import UnifiedRouter, RoutingConfig, RoutingStrategy
from temper_placer.routing.layer_assignment import assign_layers

def run_validation_experiment(pcb_path: str):
    print(f"=== Validation Experiment: Escape Routing Impact on {pcb_path} ===")
    
    # 1. Parse PCB
    try:
        result = parse_kicad_pcb(Path(pcb_path))
        netlist = result.netlist
        board = result.board
    except Exception as e:
        print(f"Failed to parse PCB: {e}")
        return

    # Extract positions for UnifiedRouter
    positions_list = []
    for comp in netlist.components:
        positions_list.append([comp.initial_position[0], comp.initial_position[1], 0.0])
    positions = jnp.array(positions_list)
    
    # Setup routing order and assignments
    net_order = [n.name for n in netlist.nets]
    assignments = assign_layers(netlist)
    
    # 2. Run WITHOUT Escape Routing
    print("\nRunning WITHOUT Escape Routing...")
    config_no_escape = RoutingConfig(
        strategy=RoutingStrategy.MAZE_ONLY,
        enable_escape_routing=False,
        maze_cell_size=0.5 # Fine grid for BGA
    )
    router_no_escape = UnifiedRouter(board, config_no_escape)
    results_no_escape = router_no_escape.route_all_nets(
        netlist, positions, net_order, assignments
    )
    
    stats_no_escape = router_no_escape.get_statistics(results_no_escape)
    print(f"  Completion: {stats_no_escape['completion_rate']:.1%}")
    print(f"  Successful Nets: {stats_no_escape['successful']}/{stats_no_escape['total_nets']}")

    # 3. Run WITH Escape Routing
    print("\nRunning WITH Escape Routing...")
    # We need a fresh ki_board to add fanouts to
    ki_board = KiBoard.from_file(pcb_path)
    
    config_with_escape = RoutingConfig(
        strategy=RoutingStrategy.MAZE_ONLY,
        enable_escape_routing=True,
        maze_cell_size=0.5
    )
    router_with_escape = UnifiedRouter(board, config_with_escape)
    results_with_escape = router_with_escape.route_all_nets(
        netlist, positions, net_order, assignments, ki_board=ki_board
    )
    
    stats_with_escape = router_with_escape.get_statistics(results_with_escape)
    print(f"  Completion: {stats_with_escape['completion_rate']:.1%}")
    print(f"  Successful Nets: {stats_with_escape['successful']}/{stats_with_escape['total_nets']}")
    print(f"  Vias Placed: {stats_with_escape['total_vias']}")

    # 4. Conclusion
    improvement = stats_with_escape['completion_rate'] - stats_no_escape['completion_rate']
    print(f"\nConclusion: Escape routing provided {improvement:+.1%} improvement in completion rate.")
    
    if stats_with_escape['completion_rate'] > stats_no_escape['completion_rate']:
        print("VALIDATION SUCCESS: Escape routing improves completion for dense grids.")
    else:
        print("VALIDATION NEUTRAL/FAILED: No improvement detected in this test case.")

if __name__ == "__main__":
    pcb = "packages/temper-placer/router-experiments/results/EXP02E_BGA_Escape_input.kicad_pcb"
    if len(sys.argv) > 1:
        pcb = sys.argv[1]
    run_validation_experiment(pcb)
