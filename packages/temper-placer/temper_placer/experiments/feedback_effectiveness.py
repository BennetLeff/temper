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
        router = MazeRouter.from_board(state.board, cell_size_mm=1.0, num_layers=2)
        router.block_board_features(state.board)
        router.block_components(state.netlist.components, pos, margin=-0.2, escape_length=5)
        
        # Critical subset of nets for fast feedback loop
        target_nets = [
            n for n in state.netlist.nets 
            if n.name in {"+340V_BUS", "SW_NODE", "GND", "+15V", "GATE_HS", "GATE_LS", "I_SENSE"}
        ]
        
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
    print("Applying enhanced feedback (Multi-iteration Iterator loop)...")
    from temper_placer.pipeline.iterator import PlaceRouteIterator
    
    class StudyRouter:
        def __init__(self, route_all_fn):
            self.route_all = route_all_fn
        def route(self, pos):
            c, r = self.route_all(pos)
            class Result:
                def __init__(self, comp, rout):
                    self.completion_rate = comp
                    self.router = rout
                    self.is_feasible = lambda: comp >= 1.0
            return Result(c, r)

    def enhanced_update(pos, routing_res):
        from temper_placer.pipeline.feedback import RoutingFeedbackLoss
        from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
        from temper_placer.losses.wirelength import WirelengthLoss
        from temper_placer.losses.overlap import OverlapLoss
        from temper_placer.optimizer.legalization import project_to_trust_region
        import optax
        import jax
        
        anchor_pos = np.array(pos).copy()
        heatmap = CongestionHeatmap.from_router(routing_res.router)
        
        loss_fn = CompositeLoss([
            WeightedLoss(WirelengthLoss(), weight=1.0),
            WeightedLoss(OverlapLoss(), weight=50.0),
            WeightedLoss(RoutingFeedbackLoss(heatmap), weight=500.0),
        ])
        
        ctx = LossContext.from_netlist_and_board(state.netlist, state.board)
        n = state.netlist.n_components
        
        optimizer = optax.adam(learning_rate=0.02)
        params = {"positions": jnp.array(pos)}
        opt_state = optimizer.init(params)
        
        @jax.jit
        def step(params, opt_state):
            def f(p):
                rotations = jnp.zeros((n, 4)).at[:, 0].set(1.0)
                return loss_fn(p["positions"], rotations, ctx).value
            loss, grads = jax.value_and_grad(f)(params)
            updates, opt_state = optimizer.update(grads, opt_state)
            params = optax.apply_updates(params, updates)
            return params, opt_state, loss

        for epoch in range(200):
            params, opt_state, _ = step(params, opt_state)
            if epoch % 50 == 0:
                # Keep within trust region
                p_np = np.array(params["positions"])
                p_np = project_to_trust_region(p_np, anchor_pos, max_radius=5.0)
                params["positions"] = jnp.array(p_np)
            
        legalized = resolve_overlaps_priority(np.array(params["positions"]), state.netlist, state.board, min_separation=1.0)
        return jnp.array(legalized)

    iterator = PlaceRouteIterator(
        netlist=state.netlist,
        board=state.board,
        router=StudyRouter(route_all),
        placement_update_fn=enhanced_update,
        max_iterations=5,
        min_improvement=-1.0
    )
    
    result = iterator.run(positions)
    
    for res in result.iteration_history:
        print(f"  Iteration {res.iteration}: Completion={res.completion_rate:.2%}")

    comp_enhanced = result.iteration_history[-1].completion_rate

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
