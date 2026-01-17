"""EXP: Tune feedback weights for optimal convergence.

Part of temper-9rjx.3
"""

import jax.numpy as jnp
import numpy as np
from pathlib import Path
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Net, Pin
from temper_placer.routing.maze_router import MazeRouter
from temper_placer.pipeline.iterator import PlaceRouteIterator
from temper_placer.routing.congestion_heatmap import CongestionHeatmap
from temper_placer.pipeline.feedback import RoutingFeedbackLoss
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.optimizer.legalization import resolve_overlaps_priority
import optax
import jax

def run_feedback_tuning():
    print("Starting Experiment: Feedback Weight Tuning")
    
    # 1. Create a responsive test case
    board = Board(width=40.0, height=40.0)
    components = []
    for i in range(4):
        comp = Component(ref=f"C{i}", footprint="Test", bounds=(8.0, 8.0))
        comp.pins = [Pin(name="1", number="1", position=(0.0, 0.0))]
        components.append(comp)
        
    nets = [
        Net(name="N1", pins=[("C0", "1"), ("C2", "1")]),
        Net(name="N2", pins=[("C1", "1"), ("C3", "1")]),
        Net(name="N3", pins=[("C0", "1"), ("C1", "1")]),
        Net(name="N4", pins=[("C2", "1"), ("C3", "1")]),
    ]
    netlist = Netlist(components=components, nets=nets)
    
    # Challenging crossing placement
    initial_pos = jnp.array([
        [15.0, 25.0], [25.0, 25.0],
        [25.0, 15.0], [15.0, 15.0]
    ])

    def route_fn(pos):
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=1)
        router.block_components(netlist.components, pos, margin=-0.1, escape_length=5)
        success_count = 0
        from temper_placer.routing.layer_assignment import LayerAssignment, Layer
        for net in netlist.nets:
            from temper_placer.routing.congestion import _get_pin_positions
            pins = _get_pin_positions(netlist, net.name, pos)
            assignment = LayerAssignment(net=net.name, primary_layer=Layer.L1_TOP, allowed_layers={Layer.L1_TOP})
            res = router.route_net_adaptive(net.name, pins, assignment)
            if res.success: success_count += 1
        completion = success_count / len(netlist.nets)
        
        class Result:
            def __init__(self, c, r):
                self.completion_rate = c
                self.router = r
                self.is_feasible = lambda: c >= 1.0
        return Result(completion, router)

    # 2. Sweep weights
    feedback_weights = [10.0, 100.0, 500.0, 1000.0]
    results = []

    for w in feedback_weights:
        print(f"\nTesting Feedback Weight: {w}")
        
        def update_fn(pos, routing_res):
            heatmap = CongestionHeatmap.from_router(routing_res.router)
            loss_fn = CompositeLoss([
                WeightedLoss(WirelengthLoss(), weight=1.0),
                WeightedLoss(OverlapLoss(), weight=100.0),
                WeightedLoss(RoutingFeedbackLoss(heatmap), weight=w),
            ])
            ctx = LossContext.from_netlist_and_board(netlist, board)
            n = netlist.n_components
            optimizer = optax.adam(learning_rate=0.05)
            params = {"positions": jnp.array(pos)}
            opt_state = optimizer.init(params)
            
            @jax.jit
            def step(params, opt_state):
                def f(p):
                    rot = jnp.zeros((n, 4)).at[:, 0].set(1.0)
                    return loss_fn(p["positions"], rot, ctx).value
                l, g = jax.value_and_grad(f)(params)
                u, o = optimizer.update(g, opt_state)
                p = optax.apply_updates(params, u)
                return p, o, l

            for _ in range(100):
                params, opt_state, _ = step(params, opt_state)
            
            legalized = resolve_overlaps_priority(np.array(params["positions"]), netlist, board, min_separation=0.0)
            return jnp.array(legalized)

        iterator = PlaceRouteIterator(
            netlist=netlist, board=board, router=StudyRouter(route_fn),
            placement_update_fn=update_fn, max_iterations=10, min_improvement=-1.0
        )
        
        res = iterator.run(initial_pos)
        final_comp = res.iteration_history[-1].completion_rate
        print(f"  Iteration History:")
        for h in res.iteration_history:
            print(f"    {h.iteration}: {h.completion_rate:.2%}")
        results.append((w, final_comp))

    # 3. Summary
    print("\nTuning Summary:")
    for w, comp in results:
        print(f"  Weight {w:4}: {comp:.2%}")

class StudyRouter:
    def __init__(self, fn):
        self.fn = fn
    def route(self, pos):
        return self.fn(pos)

if __name__ == "__main__":
    run_feedback_tuning()
