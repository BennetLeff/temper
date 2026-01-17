"""EXP: End-to-end validation on Temper board.

This experiment runs the full PlaceRouteIterator loop on the actual Temper
induction heating board, using real constraints and the MazeRouter.

Part of temper-1d78.3
"""

import time
from pathlib import Path
from typing import Any

import jax.numpy as jnp
import numpy as np

from temper_placer.pipeline.orchestrator import PipelineConfig, PipelineOrchestrator, PipelineState
from temper_placer.pipeline.iterator import PlaceRouteIterator, PlaceRouteResult
from temper_placer.placer.adjustment import adjust_for_congestion
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.layer_assignment import assign_layers, LayerAssignment, Layer


class TemperRouter:
    """Router wrapper for the Temper board validation."""
    
    def __init__(self, state: PipelineState):
        self.state = state
        self.netlist = state.netlist
        self.board = state.board
        
    def route(self, positions: jnp.ndarray) -> Any:
        # 1. Initialize MazeRouter
        # Use 0.5mm grid for Temper board to resolve most pins while staying fast
        router = MazeRouter.from_board(self.board, cell_size_mm=0.5, num_layers=2)
        
        # 2. Block obstacles
        router.block_board_features(self.board)
        # Block existing traces and vias (crucial for pre_routed board)
        if hasattr(self.state, "traces") and self.state.traces:
            router.block_traces(self.state.traces)
        if hasattr(self.state, "vias") and self.state.vias:
            router.block_vias(self.state.vias)
            
        # Block components with escape routes
        router.block_components(self.netlist.components, positions, margin=-0.2, escape_length=5)
        
        
        
        # 3. Assign layers
        # In a real run, we'd use the full layer assignment system
        assignments = assign_layers(self.netlist, component_positions=positions)
        
        # 4. Route nets
        # Filter for power nets to keep validation focused and fast
        power_classes = {"Power", "HighVoltage", "HighCurrent"}
        target_nets = [n for n in self.netlist.nets if n.net_class in power_classes]
        
        success_count = 0
        total_nets = len(target_nets)
        
        print(f"    Routing {total_nets} power nets...")
        for net in target_nets:
            from temper_placer.routing.congestion import _get_pin_positions
            pins = _get_pin_positions(self.netlist, net.name, positions)
            
            if len(pins) < 2:
                continue
                
            assignment = assignments.get(net.name)
            if not assignment:
                assignment = LayerAssignment(net=net.name, primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP, Layer.L4_BOT})
            
            res = router.route_net_adaptive(net.name, pins, assignment)
            if res.success:
                success_count += 1
                
        completion = success_count / total_nets if total_nets > 0 else 1.0
        
        class TemperRoutingResult:
            def __init__(self, completion, router):
                self.completion_rate = completion
                self.router = router
                self.is_feasible = lambda: completion >= 0.98 # Target 98% for "feasible" 
                self.metrics = {"completion": completion, "nets_routed": success_count}
                
        return TemperRoutingResult(completion, router)


def run_temper_validation():
    print("Starting End-to-End Validation: Temper Board")
    
    # 1. Setup paths
    root_dir = Path("packages/temper-placer")
    pcb_path = Path("pre_routed_v5.kicad_pcb") # In root workspace based on file list
    if not pcb_path.exists():
        # Try relative to script if running from elsewhere
        pcb_path = Path("pre_routed_v5.kicad_pcb")
        
    constraints_path = root_dir / "configs" / "temper_constraints.yaml"
    
    print(f"  PCB: {pcb_path}")
    print(f"  Constraints: {constraints_path}")
    
    # 2. Initialize Pipeline Orchestrator to load data
    config = PipelineConfig(
        input_pcb=pcb_path,
        constraints_yaml=constraints_path,
        skip_routing=True, # We'll handle routing in the iterator
        epochs=100 # Minimal epochs for this experiment
    )
    
    orchestrator = PipelineOrchestrator(config)
    print("\nLoading design data...")
    state = orchestrator._run_input(orchestrator.state)
    
    # Map net classes from constraints to netlist (parser doesn't do this automatically)
    if hasattr(state.constraints, "net_classes"):
        for net in state.netlist.nets:
            if net.name in state.constraints.net_classes:
                net.net_class = state.constraints.net_classes[net.name]
                print(f"  Assigned {net.name} to class {net.net_class}")
    
    # 3. Get initial positions (Step 3 refinement result or topological)
    # For validation, let's start with the positions currently in the PCB
    initial_positions = []
    for comp in state.netlist.components:
        if comp.initial_position:
            initial_positions.append(comp.initial_position)
        else:
            # Fallback to board center
            initial_positions.append([state.board.width/2, state.board.height/2])
            
    initial_positions = jnp.array(initial_positions)
    
    # 4. Setup Iterator
    router = TemperRouter(state)
    
    def placement_update(pos, routing_res):
        print("    Adjusting placement based on router heatmap...")
        from temper_placer.routing.congestion_heatmap import CongestionHeatmap
        from temper_placer.optimizer.legalization import resolve_overlaps_priority
        from temper_placer.pipeline.iterative_placer import simple_congestion_repel
        
        # Build heatmap from actual router state (much more accurate than proxy)
        heatmap = CongestionHeatmap.from_router(routing_res.router)
        
        # Use simple_congestion_repel which uses the heatmap gradient
        new_pos = simple_congestion_repel(jnp.array(pos), heatmap, repel_strength=2.0)
        
        # Legalize
        legalized_pos = resolve_overlaps_priority(np.array(new_pos), state.netlist, state.board, min_separation=1.0)
        
        return jnp.array(legalized_pos)
        
    iterator = PlaceRouteIterator(
        netlist=state.netlist,
        board=state.board,
        router=router,
        placement_update_fn=placement_update,
        max_iterations=5, # More iterations for Temper
        target_completion=0.98,
        min_improvement=-1.0 # Allow worsening/exploration
    )
    
    # 5. Run Loop
    print("\nRunning Iterative Place-and-Route on Temper Board...")
    start_time = time.time()
    result = iterator.run(initial_positions)
    end_time = time.time()
    
    # 6. Report Results
    print(f"\nValidation Complete in {end_time - start_time:.2f}s")
    print(f"  Converged: {result.converged}")
    print(f"  Iterations: {result.iterations}")
    
    for i, res in enumerate(result.iteration_history):
        print(f"  Iteration {res.iteration}: Completion={res.completion_rate:.2%}")
        
    final_completion = result.iteration_history[-1].completion_rate
    initial_completion = result.iteration_history[0].completion_rate
    
    if result.converged or final_completion > initial_completion:
        print("\nSUCCESS: PlaceRouteIterator improved Temper board routability.")
    else:
        print("\nFAILURE: Routability did not improve on Temper board.")

if __name__ == "__main__":
    run_temper_validation()
