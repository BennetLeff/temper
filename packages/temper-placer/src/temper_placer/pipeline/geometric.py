"""
Geometric placement phase for temper-placer.

This phase uses JAX gradient descent to perform local refinement of the
placement within a trust region.
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
import numpy as np
import optax
from typing import TYPE_CHECKING

from temper_placer.core.state import PlacementState
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.optimizer.legalization import (
    project_to_trust_region,
    resolve_overlaps_priority,
    clamp_to_bounds,
    clamp_to_zones
)
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.losses.overlap import OverlapLoss

if TYPE_CHECKING:
    from temper_placer.pipeline.state import PipelineState


def run_geometric_phase(state: PipelineState) -> PipelineState:
    """Run geometric optimization (local refinement)."""
    print("Initializing local refinement (Step 3)...")
    
    # Ensure we have initial positions from topological phase
    if state.deterministic_result is None:
         from temper_placer.pipeline.topological import run_topological_phase
         state = run_topological_phase(state)
    
    anchor_positions = np.array(state.deterministic_result.positions)
    positions = anchor_positions.copy()
    n = state.netlist.n_components
    
    loss_fn = CompositeLoss([
        WeightedLoss(WirelengthLoss(), weight=1.0),
        WeightedLoss(OverlapLoss(), weight=10.0),
    ])
    context = LossContext.from_netlist_and_board(state.netlist, state.board)
    
    print(f"Running refinement for {state.config.epochs} epochs (max {state.config.max_movement_mm}mm movement)...")
    optimizer = optax.adam(learning_rate=0.1)
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

    # Perform optimization epochs
    for epoch in range(min(state.config.epochs, 500)):
        params, opt_state, _ = step(params, opt_state)
        
        # Periodic projection to trust region and constraints
        if epoch % 10 == 0:
            pos_np = np.array(params["positions"])
            pos_np = project_to_trust_region(
                pos_np, anchor_positions, max_radius=state.config.max_movement_mm
            )
            
            # Re-enforce hard constraints
            widths = np.array([c.bounds[0] for c in state.netlist.components])
            heights = np.array([c.bounds[1] for c in state.netlist.components])
            pos_np = clamp_to_bounds(pos_np, widths, heights, state.board)
            pos_np = clamp_to_zones(pos_np, state.netlist, state.board)
            
            params["positions"] = jnp.array(pos_np)

    # Final legalization pass
    final_pos = resolve_overlaps_priority(
        np.array(params["positions"]), 
        state.netlist, 
        state.board, 
        min_separation=0.5, 
        enforce_zones=True
    )
    
    state.placement_state = PlacementState.from_positions(jnp.array(final_pos))
    return state
