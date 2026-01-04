"""EXP: Measure current feedback effectiveness.

Part of temper-9rjx.1
"""

import time
from pathlib import Path
import jax.numpy as jnp
import numpy as np

from temper_placer.pipeline.orchestrator import PipelineConfig, PipelineOrchestrator
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.routing.layer_assignment import assign_layers, LayerAssignment, Layer
from temper_placer.routing.congestion_heatmap import CongestionHeatmap
from temper_placer.pipeline.iterative_placer import simple_congestion_repel
from temper_placer.optimizer.legalization import resolve_overlaps_priority

def run_feedback_effectiveness_study():
    print("Starting Experiment: Feedback Effectiveness Study")
    
    # 1. Load Temper board
    root_dir = Path("packages/temper-placer")
    pcb_path = Path("pre_routed_v5.kicad_pcb")
    constraints_path = root_dir / "configs" / "temper_constraints.yaml"
    
    config = PipelineConfig(
        input_pcb=pcb_path,
        constraints_yaml=constraints_path,
        skip_routing=True
    )
    
    orchestrator = PipelineOrchestrator(config)
    state = orchestrator._run_input(orchestrator.state)
    
    # Map net classes
    if hasattr(state.constraints, "net_classes"):
        for net in state.netlist.nets:
            if net.name in state.constraints.net_classes:
                net.net_class = state.constraints.net_classes[net.name]

    # Initial positions from PCB
    positions = []
    for comp in state.netlist.components:
        positions.append(comp.initial_position or [state.board.width/2, state.board.height/2])
    positions = jnp.array(positions)

    def route_all(pos):
        router = MazeRouter.from_board(state.board, cell_size_mm=0.5, num_layers=2)
        router.block_board_features(state.board)
        router.block_components(state.netlist.components, pos, margin=-0.1, escape_length=5)
        
        target_classes = {"Power", "HighVoltage", "HighCurrent", "Signal", "GateDrive"}
        target_nets = [n for n in state.netlist.nets if n.net_class in target_classes]
        
        success_count = 0
        for net in target_nets:
            from temper_placer.routing.congestion import _get_pin_positions
            pins = _get_pin_positions(state.netlist, net.name, pos)
            if len(pins) < 2: continue
            
            res = router.route_net_adaptive(net.name, pins, None)
            if res.success: success_count += 1
            
        completion = success_count / len(target_nets) if target_nets else 1.0
        return completion, router

    # 2. Baseline routing
    print("Baseline routing pass...")
    initial_completion, initial_router = route_all(positions)
    print(f"  Initial Completion: {initial_completion:.2%}")

    # 3. Apply feedback once (Baseline)
    print("Applying baseline feedback (congestion-based repel)...")
    heatmap = CongestionHeatmap.from_router(initial_router)
    
    repel_strength = 1.0
    new_pos_base = simple_congestion_repel(positions, heatmap, repel_strength=repel_strength)
    legalized_base = resolve_overlaps_priority(np.array(new_pos_base), state.netlist, state.board, min_separation=1.0)
    
    comp_base, _ = route_all(jnp.array(legalized_base))
    print(f"  Baseline Completion: {comp_base:.2%}")

    # 4. Apply enhanced feedback (JAX optimization)
    print("Applying enhanced feedback (JAX optimization + RoutingFeedbackLoss)...")
    from temper_placer.pipeline.feedback import RoutingFeedbackLoss
    from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
    from temper_placer.losses.wirelength import WirelengthLoss
    from temper_placer.losses.overlap import OverlapLoss
    import optax
    import jax

    loss_fn = CompositeLoss([
        WeightedLoss(WirelengthLoss(), weight=1.0),
        WeightedLoss(OverlapLoss(), weight=50.0),
        WeightedLoss(RoutingFeedbackLoss(heatmap), weight=100.0),
    ])
    
    context = LossContext.from_netlist_and_board(state.netlist, state.board)
    n = state.netlist.n_components
    
    optimizer = optax.adam(learning_rate=0.05)
    params = {"positions": jnp.array(positions)}
    opt_state = optimizer.init(params)
    
    @jax.jit
    def step(params, opt_state):
        def f(p):
            rotations = jnp.zeros((n, 4)).at[:, 0].set(1.0)
            return loss_fn(p["positions"], rotations, context).value
        loss, grads = jax.value_and_grad(f)(params)
        updates, opt_state = optimizer.update(grads, opt_state)
        params = optax.apply_updates(params, updates)
        return params, opt_state, loss

    for epoch in range(200):
        params, opt_state, loss = step(params, opt_state)
        if epoch % 50 == 0:
            print(f"    Epoch {epoch}: Loss={loss:.4f}")
            
    print(f"    Final refinement loss: {loss:.4f}")
    
    # Check movement
    movement = jnp.linalg.norm(params["positions"] - positions, axis=1)
    print(f"    Max component movement: {jnp.max(movement):.2f}mm")
    print(f"    Avg component movement: {jnp.mean(movement):.2f}mm")
        
    legalized_enhanced = resolve_overlaps_priority(np.array(params["positions"]), state.netlist, state.board, min_separation=1.0)
    comp_enhanced, _ = route_all(jnp.array(legalized_enhanced))
    print(f"  Enhanced Completion: {comp_enhanced:.2%}")

    # 5. Analyze
    print(f"\nResults Summary:")
    print(f"  Initial Completion: {initial_completion:.2%}")
    print(f"  Baseline Completion: {comp_base:.2%}")
    print(f"  Enhanced Completion: {comp_enhanced:.2%}")
    
    improvement = comp_enhanced - initial_completion
    print(f"  Total Improvement: {improvement:+.2%}")

    if comp_enhanced > comp_base:
        print("SUCCESS: Enhanced feedback outperformed baseline.")
    elif comp_enhanced > initial_completion:
        print("SUCCESS: Enhanced feedback improved over initial.")
    else:
        print("NOTICE: No significant improvement in one pass.")

if __name__ == "__main__":
    run_feedback_effectiveness_study()
