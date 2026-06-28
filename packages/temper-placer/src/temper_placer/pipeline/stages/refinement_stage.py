"""Refinement stage: iterative placement-routing loop."""

from __future__ import annotations

import time
from typing import Any

import jax.numpy as jnp
import numpy as np

from temper_placer.pipeline.dag_types import DataContext, StageResult


class RefinementStage:
    def __call__(self, state: Any, context: DataContext) -> StageResult:
        start_time = time.time()
        from temper_placer.pipeline.iterator import PlaceRouteIterator
        from temper_placer.router_v6.adapter import V6RouterAdapter
        from temper_placer.routing.congestion_heatmap import CongestionHeatmap
        from temper_placer.optimizer.legalization import resolve_overlaps_priority
        from temper_placer.core.state import PlacementState

        board = context["board"]
        netlist = context["netlist"]
        routing_result = context.get("routing_result")
        placement_state = context.get("placement_state")
        max_iterations = context.get("max_iterations", 5)
        routability_threshold = context.get("routability_threshold", 0.85)
        convergence_threshold = context.get("convergence_threshold", 0.01)
        deadline = context.get("deadline", None)

        if routing_result is None:
            elapsed = time.time() - start_time
            return StageResult(outputs={}, duration_s=elapsed)

        if routing_result.is_feasible(threshold=routability_threshold):
            state._refinement_complete = True
            elapsed = time.time() - start_time
            return StageResult(
                outputs={"placement_state": placement_state, "routing_result": routing_result},
                duration_s=elapsed,
            )

        print(f"Starting iterative refinement (max {max_iterations} iterations)...")

        class OrchestratorRouter:
            def __init__(self, st):
                self.state = st

            def route(self, pos):
                router = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2)
                router.block_board_features(board)
                router.block_components(netlist.components, pos, margin=-0.1, escape_length=5)

                success_count = 0
                for net in netlist.nets:
                    from temper_placer.routing.congestion import _get_pin_positions
                    pins = _get_pin_positions(netlist, net.name, pos)
                    if len(pins) < 2:
                        continue
                    res = router.route_net_adaptive(net.name, pins, None)
                    if res.success:
                        success_count += 1

                completion = success_count / len(netlist.nets)

                class Result:
                    def __init__(self, c, r):
                        self.completion_rate = c
                        self.router = r
                        self.is_feasible = lambda: c >= 1.0
                return Result(completion, router)

        def update_fn(pos, routing_res):
            if deadline is not None and time.time() > deadline:
                return jnp.array(pos)
            print("    Refining placement using JAX optimization with routing feedback loss...")
            from temper_placer.pipeline.feedback import RoutingFeedbackLoss
            from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
            from temper_placer.losses.wirelength import WirelengthLoss
            from temper_placer.losses.overlap import OverlapLoss
            from temper_placer.losses.channel_capacity import ChannelCapacityLoss
            import optax
            import jax

            heatmap = CongestionHeatmap.from_router(routing_res.router)

            loss_fn = CompositeLoss([
                WeightedLoss(WirelengthLoss(), weight=1.0),
                WeightedLoss(OverlapLoss(), weight=50.0),
                WeightedLoss(ChannelCapacityLoss(), weight=20.0),
                WeightedLoss(RoutingFeedbackLoss(heatmap), weight=100.0),
            ])

            loss_context = LossContext.from_netlist_and_board(netlist, board)
            n = netlist.n_components

            optimizer = optax.adam(learning_rate=0.05)
            params = {"positions": jnp.array(pos)}
            opt_state = optimizer.init(params)

            @jax.jit
            def step(params, opt_state):
                def f(p):
                    rotations = jnp.zeros((n, 4)).at[:, 0].set(1.0)
                    return loss_fn(p["positions"], rotations, loss_context).value
                loss, grads = jax.value_and_grad(f)(params)
                updates, opt_state = optimizer.update(grads, opt_state)
                params = optax.apply_updates(params, updates)
                return params, opt_state, loss

            for epoch in range(200):
                if deadline is not None and time.time() > deadline:
                    break
                params, opt_state, _ = step(params, opt_state)
                if epoch % 50 == 0:
                    from temper_placer.optimizer.legalization import clamp_to_bounds
                    pos_np = np.array(params["positions"])
                    pos_np = clamp_to_bounds(pos_np,
                                             np.array([c.bounds[0] for c in netlist.components]),
                                             np.array([c.bounds[1] for c in netlist.components]),
                                             board)
                    params["positions"] = jnp.array(pos_np)

            legalized = resolve_overlaps_priority(np.array(params["positions"]), netlist, board,
                                                   min_separation=1.0)
            return jnp.array(legalized)

        router = OrchestratorRouter(state)
        iterator = PlaceRouteIterator(
            netlist=netlist,
            board=board,
            router=router,
            placement_update_fn=update_fn,
            max_iterations=max_iterations,
            target_completion=routability_threshold,
            min_improvement=convergence_threshold,
        )

        current_pos = (placement_state.positions if placement_state is not None
                       else jnp.array(context["deterministic_result"].positions))
        result = iterator.run(current_pos)

        new_placement_state = PlacementState.from_positions(result.final_positions)
        state.placement_state = new_placement_state
        state.iteration = result.iterations
        state._refinement_complete = True

        print(f"Refinement complete. Best completion: {result.iteration_history[-1].completion_rate:.2%}")

        elapsed = time.time() - start_time
        return StageResult(
            outputs={
                "refinement_placement": new_placement_state,
                "refinement_routing_result": routing_result,
            },
            duration_s=elapsed,
        )
