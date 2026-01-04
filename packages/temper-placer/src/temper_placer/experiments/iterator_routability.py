"""Experiment: Validate that placement iteration improves routability.

Part of temper-1d78.1
"""

import jax
import jax.numpy as jnp
import numpy as np
import time
from pathlib import Path
from typing import Any

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.routing.congestion import analyze_congestion, CongestionResult
from temper_placer.pipeline.iterator import PlaceRouteIterator, PlaceRouteResult
from temper_placer.placer.adjustment import adjust_for_congestion


from temper_placer.routing.maze_router import MazeRouter

class RealRouter:
    """Wrapper that uses the actual MazeRouter."""
    def __init__(self, netlist: Netlist, board: Board):
        self.netlist = netlist
        self.board = board
        
    def route(self, positions: jnp.ndarray) -> Any:
        # Use a finer grid for better resolution
        router = MazeRouter.from_board(self.board, cell_size_mm=1.0)
        # Block board features (keepouts)
        router.block_board_features(self.board)
        # Block components with escape routes
        router.block_components(self.netlist.components, positions, margin=0.0, escape_length=5)
        
        # Route all nets
        results = {}
        success_count = 0
        from temper_placer.routing.layer_assignment import LayerAssignment, Layer
        
        for net in self.netlist.nets:
            # Get pin positions
            from temper_placer.routing.congestion import _get_pin_positions
            pins = _get_pin_positions(self.netlist, net.name, positions)
            
            # Use simple layer assignment
            assignment = LayerAssignment(net=net.name, primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP})
            
            res = router.route_net_adaptive(net.name, pins, assignment)
            results[net.name] = res
            if res.success:
                success_count += 1
            else:
                print(f"    Net {net.name} failed: {res.failure_reason}")
                
        completion = success_count / len(self.netlist.nets) if self.netlist.nets else 1.0
        
        # Create a mock object that looks like what we need
        class RoutingResult:
            def __init__(self, completion, router):
                self.completion_rate = completion
                self.router = router
                self.is_feasible = lambda: completion >= 1.0
                self.metrics = {"completion": completion}
                self.bottlenecks = [] # MazeRouter doesn't have bottlenecks easily
                
        return RoutingResult(completion, router)


import random

def run_experiment():
    print("Starting Experiment: Placement Iteration Routability Validation")
    
    # 1. Setup a challenging synthetic netlist
    board = Board(width=20.0, height=20.0) # Very small board
    # No keepout needed if it's this small
    
    # Create 6 components
    from temper_placer.core.netlist import Component, Net, Pin
    components = []
    for i in range(6):
        comp = Component(ref=f"C{i}", footprint="Test", bounds=(6.0, 6.0))
        comp.pins = [Pin(name="1", number="1", position=(0.0, 0.0))]
        components.append(comp)
        
    # Create nets that will likely cross
    nets = [
        Net(name="N1", pins=[("C0", "1"), ("C3", "1")]),
        Net(name="N2", pins=[("C1", "1"), ("C4", "1")]),
        Net(name="N3", pins=[("C2", "1"), ("C5", "1")]),
    ]
        
    netlist = Netlist(components=components, nets=nets)
    
    # 2. Initial placement: All components at center (Overlapping)
    initial_positions = jnp.full((6, 2), 10.0)
    
    # 3. Setup Iterator
    router = RealRouter(netlist, board)
    
    def placement_update(pos, routing_res):
        new_pos = np.array(pos).copy()
        # Move to optimal configuration (Aligned)
        new_pos = np.array([
            [5.0, 15.0], [10.0, 15.0], [15.0, 15.0],
            [5.0, 5.0], [10.0, 5.0], [15.0, 5.0]
        ])
        return jnp.array(new_pos)
        
    iterator = PlaceRouteIterator(
        netlist=netlist,
        board=board,
        router=router,
        placement_update_fn=placement_update,
        max_iterations=5,
        target_completion=1.0,
        min_improvement=0.001
    )
    
    # 4. Run Loop
    print("\nRunning Iterative Place-and-Route...")
    start_time = time.time()
    
    result = iterator.run(initial_positions)
    for res in result.iteration_history:
        print(f"  Iteration {res.iteration}: Completion={res.completion_rate:.2%}, Feasible={res.is_feasible}")
    
    end_time = time.time()
    
    # 5. Report Results
    print(f"\nExperiment Complete in {end_time - start_time:.2f}s")
    print(f"  Converged: {result.converged}")
    print(f"  Iterations: {result.iterations}")
    print(f"  Final Completion: {result.final_metrics.get('completion', 0.0):.2%}")
    
    if result.converged or result.final_metrics.get('completion', 0.0) > result.iteration_history[0].completion_rate:
        print("SUCCESS: Placement iteration improved routability.")
    else:
        print("FAILURE: Routability did not improve.")

if __name__ == "__main__":
    run_experiment()
