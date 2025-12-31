"""Unified automated PCB layout pipeline.

This module provides the main entry point for zero-input automated placement and routing.
"""

import time
import jax
import jax.numpy as jnp
from jax import Array
import numpy as np
from typing import Any

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.routing.maze_router import MazeRouter, RoutePath
from temper_placer.routing.net_ordering import order_nets
from temper_placer.routing.layer_assignment import assign_layers
from temper_placer.core.loop import LoopCollection
from temper_placer.losses.base import LossContext
from temper_placer.losses import (
    OverlapLoss,
    BoundaryLoss,
    MCUClusteringLoss,
    BusAlignmentLoss,
    RoutingChannelLoss,
)
from temper_placer.losses.routing_congestion import RoutingCongestionLoss, compute_congestion_heatmap, ConflictLocation
from temper_placer.pipeline.convergence import is_converged

def initial_placement(netlist: Netlist, board: Board) -> Array:
    """Compute initial component placement."""
    # Start with components at their initial positions if available, otherwise board center
    positions = []
    for comp in netlist.components:
        if comp.initial_position:
            positions.append(comp.initial_position)
        else:
            positions.append((board.width / 2, board.height / 2))
    return jnp.array(positions)

def auto_layout_pcb(
    netlist: Netlist, 
    board: Board, 
    max_outer_iterations: int = 10,
    cell_size_mm: float = 0.5,
    num_layers: int = 2,
    initial_positions: Array | None = None
) -> tuple[Array, dict[str, RoutePath]]:
    """
    Fully automated placement and routing.

    Returns:
        Final component positions and routing results.
    """
    print(f"Starting auto_layout_pcb with {max_outer_iterations} outer iterations...")
    
    # Stage 1: Initial placement
    if initial_positions is not None:
        positions = initial_positions
    else:
        positions = initial_placement(netlist, board)
    
    # Prepare routing metadata
    loops = LoopCollection()
    net_order = order_nets(netlist, loops)
    assignments = assign_layers(netlist, component_positions=positions)
    
    # Exclude power/ground nets from routing (they should be handled by planes)
    POWER_NET_PATTERNS = ['GND', 'VCC', 'VDD', '3V3', '5V', '12V', '15V']
    net_order = [n for n in net_order if not any(p in n.upper() for p in POWER_NET_PATTERNS)]
    
    prev_results = None
    best_positions = positions
    best_conflicts = float('inf')
    congestion_heatmap = None
    
    # Stage 2: Placement-routing loop
    for outer_iter in range(max_outer_iterations):
        print(f"\nOuter loop iteration {outer_iter + 1}/{max_outer_iterations}")
        
        # 2a. Placement Optimization (if we have feedback)
        if congestion_heatmap is not None:
            positions = optimize_placement_with_feedback(
                netlist, board, positions, congestion_heatmap, cell_size_mm
            )
        
        # 2b. Routing pass
        router = MazeRouter.from_board(
            board, 
            cell_size_mm=cell_size_mm, 
            num_layers=num_layers,
            soft_blocking=True
        )
        router.block_components(netlist.components, positions)
        
        # Route all nets with Rip-up and Reroute
        results = router.rrr_route_all_nets(
            netlist, 
            positions, 
            net_order, 
            assignments,
            max_iterations=5 # Inner RRR iterations
        )
        
        # 2c. Check convergence
        if is_converged(results, prev_results):
            print("Convergence detected. Stopping loop.")
            break
            
        # Update best result
        conflict_locs = router.get_conflict_locations()
        num_conflicts = len(conflict_locs)
        if num_conflicts < best_conflicts:
            best_conflicts = num_conflicts
            best_positions = positions
            
        if num_conflicts == 0:
            print("Perfect routing achieved!")
            break
            
        # 2d. Prepare feedback for next iteration
        conflicts = [
            ConflictLocation(x=loc['x'], y=loc['y'], layer=loc['layer'], nets=loc['nets'])
            for loc in conflict_locs
        ]
        congestion_heatmap = compute_congestion_heatmap(
            conflicts, 
            grid_size=router.grid_size, 
            cell_size_mm=cell_size_mm, 
            origin=board.origin
        )
        prev_results = results

    # Stage 3: Final routing pass with maximum effort
    print("\nStarting final high-effort routing pass...")
    router = MazeRouter.from_board(board, cell_size_mm=cell_size_mm, num_layers=num_layers)
    router.block_components(netlist.components, best_positions)
    final_results = router.rrr_route_all_nets(
        netlist, 
        best_positions, 
        net_order, 
        assignments, 
        max_iterations=50
    )
    
    return best_positions, final_results

def optimize_placement_with_feedback(
    netlist: Netlist, 
    board: Board, 
    current_positions: Array, 
    congestion_heatmap: Array,
    cell_size_mm: float,
    steps: int = 100
) -> Array:
    """Optimize placement using routing congestion feedback."""
    context = LossContext.from_netlist_and_board(netlist, board)
    
    overlap_loss = OverlapLoss()
    boundary_loss = BoundaryLoss()
    channel_loss = RoutingChannelLoss(weight=1.0)
    mcu_clustering = MCUClusteringLoss.from_netlist(netlist)
    bus_alignment = BusAlignmentLoss.from_netlist(netlist)
    congestion_loss = RoutingCongestionLoss(
        congestion_heatmap, 
        weight=1.0, 
        cell_size_mm=cell_size_mm, 
        origin=board.origin
    )
    
    def combined_loss(pos):
        rotations = jnp.zeros((len(netlist.components), 4))
        total = jnp.array(0.0)
        total += 100.0 * overlap_loss(pos, rotations, context).value
        total += 50.0 * boundary_loss(pos, rotations, context).value
        total += 20.0 * channel_loss(pos, rotations, context).value
        total += 10.0 * mcu_clustering(pos, rotations, context).value
        total += 5.0 * bus_alignment(pos, rotations, context).value
        total += 30.0 * congestion_loss(pos)
        return total
        
    grad_fn = jax.grad(combined_loss)
    learning_rate = 0.5
    
    # JIT-compile the update step
    # We use scan to unroll the loop on the device
    def update_step(pos, _):
        grads = grad_fn(pos)
        new_pos = pos - learning_rate * grads
        new_pos = jnp.clip(
            new_pos,
            jnp.array([5.0, 5.0]),
            jnp.array([board.width - 5.0, board.height - 5.0])
        )
        return new_pos, None

    # Run optimization loop on device
    final_positions, _ = jax.lax.scan(update_step, current_positions, None, length=steps)
        
    return final_positions
