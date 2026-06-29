"""Geometric stage: JAX gradient-descent optimization for placement."""

from __future__ import annotations

import time
from typing import Any

import jax
import jax.numpy as jnp
import numpy as np
import optax

from temper_placer.pipeline.dag_types import DataContext, StageResult


class GeometricStage:
    def __call__(self, state: Any, context: DataContext) -> StageResult:
        start_time = time.time()
        from temper_placer.core.state import PlacementState
        from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
        from temper_placer.losses.channel_capacity import ChannelCapacityLoss
        from temper_placer.losses.overlap import OverlapLoss
        from temper_placer.losses.wirelength import WirelengthLoss
        from temper_placer.optimizer.legalization import (
            project_to_trust_region,
            resolve_overlaps_priority,
        )

        print("Initializing local refinement (Step 3)...")
        deterministic_result = context.get("deterministic_result")
        if deterministic_result is None:
            from temper_placer.pipeline.topological import run_topological_phase
            state = run_topological_phase(state)
            deterministic_result = state.deterministic_result

        board = context["board"]
        netlist = context["netlist"]

        anchor_positions = np.array(deterministic_result.positions)
        positions = anchor_positions.copy()
        n = netlist.n_components

        loss_fn = CompositeLoss([
            WeightedLoss(WirelengthLoss(), weight=1.0),
            WeightedLoss(OverlapLoss(), weight=10.0),
            WeightedLoss(ChannelCapacityLoss(), weight=5.0),
        ])
        loss_context = LossContext.from_netlist_and_board(netlist, board)

        epochs = context.get("epochs", 8000)
        max_movement_mm = context.get("max_movement_mm", 2.0)
        deadline = context.get("deadline", None)
        on_epoch = context.get("on_epoch")
        print(f"Running refinement for {epochs} epochs (max {max_movement_mm}mm movement)...")

        optimizer = optax.adam(learning_rate=0.1)
        params = {"positions": jnp.array(positions)}
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

        for epoch in range(min(epochs, 500)):
            if deadline is not None and time.time() > deadline:
                break
            params, opt_state, _ = step(params, opt_state)
            if epoch % 10 == 0:
                pos_np = np.array(params["positions"])
                pos_np = project_to_trust_region(pos_np, anchor_positions, max_radius=max_movement_mm)
                from temper_placer.optimizer.legalization import clamp_to_bounds, clamp_to_zones
                pos_np = clamp_to_bounds(pos_np,
                                         np.array([c.bounds[0] for c in netlist.components]),
                                         np.array([c.bounds[1] for c in netlist.components]),
                                         board)
                pos_np = clamp_to_zones(pos_np, netlist, board)
                params["positions"] = jnp.array(pos_np)
                if on_epoch is not None:
                    loss_val = loss_fn(params["positions"],
                                       jnp.zeros((n, 4)).at[:, 0].set(1.0),
                                       loss_context).value
                    on_epoch("geometric", epoch, float(loss_val))

        final_pos = resolve_overlaps_priority(np.array(params["positions"]), netlist, board,
                                               min_separation=0.5, enforce_zones=True)
        placement_state = PlacementState.from_positions(jnp.array(final_pos))
        state.placement_state = placement_state

        elapsed = time.time() - start_time
        return StageResult(
            outputs={"placement_state": placement_state},
            duration_s=elapsed,
        )
