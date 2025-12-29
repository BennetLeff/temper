#!/usr/bin/env python3
"""
Placement-Routing Feedback Loop

This script implements the architecture-defined feedback loop:
  Placement → Routing → Evaluate → Placement Feedback → iterate

Usage:
    uv run python scripts/placement_routing_loop.py \\
        pcb/input.kicad_pcb \\
        -o pcb/output.kicad_pcb \\
        --max-iterations 5
"""

import argparse
import sys
import time
from pathlib import Path

from rich.console import Console

console = Console()


def main():
    parser = argparse.ArgumentParser(description="Placement-Routing Feedback Loop")
    parser.add_argument("input_pcb", type=Path, help="Input .kicad_pcb file")
    parser.add_argument("-o", "--output", type=Path, help="Output .kicad_pcb file")
    parser.add_argument("--max-iterations", type=int, default=10, help="Max outer loop iterations")
    parser.add_argument("--cell-size", type=float, default=0.5, help="Routing grid cell size (mm)")
    parser.add_argument("--placement-steps", type=int, default=100, help="Placement optimizer steps per iteration")
    parser.add_argument("--rrr-iters", type=int, default=5, help="RRR iterations per routing pass")
    parser.add_argument("--target-conflicts", type=int, default=0, help="Stop when conflicts <= this")
    parser.add_argument("--nudge-strength", type=float, default=2.0, help="Component nudge per iteration (mm)")
    parser.add_argument("--exclude-power-nets", action="store_true", help="Exclude power/ground nets from routing")
    
    args = parser.parse_args()
    
    if not args.output:
        args.output = args.input_pcb.with_name(args.input_pcb.stem + "_loop_output.kicad_pcb")
    
    console.print(f"[bold blue]Placement-Routing Feedback Loop[/]")
    console.print(f"Input: {args.input_pcb}")
    console.print(f"Output: {args.output}")
    console.print(f"Max iterations: {args.max_iterations}")
    
    # Import dependencies
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.routing.maze_router import MazeRouter
    from temper_placer.routing.net_ordering import order_nets
    from temper_placer.routing.layer_assignment import assign_layers
    from temper_placer.losses.routing_congestion import RoutingCongestionLoss, compute_congestion_heatmap, ConflictLocation
    import jax.numpy as jnp
    
    # Parse initial PCB
    console.print("\n[bold cyan]Step 1:[/] Parsing PCB...")
    parse_result = parse_kicad_pcb(args.input_pcb)
    board = parse_result.board
    netlist = parse_result.netlist
    # Extract positions - use initial_position like internal_route.py does
    positions = jnp.array([c.initial_position for c in netlist.components])
    
    console.print(f"  ✓ Loaded {len(netlist.components)} components, {len(netlist.nets)} nets")
    
    # Prepare routing
    from temper_placer.core.loop import LoopCollection
    loops = LoopCollection()
    net_order = order_nets(netlist, loops)
    assignments = assign_layers(netlist)
    
    # Exclude power/ground nets from routing (they should be on planes)
    POWER_NET_PATTERNS = [
        'GND', 'PGND', 'CGND', 'AGND', 'DGND', 'ISOGND',
        '+3V3', '+5V', '+15V', '+12V', 'VCC', 'VDD',
    ]
    if args.exclude_power_nets:
        original_count = len(net_order)
        net_order = [n for n in net_order if not any(p in n for p in POWER_NET_PATTERNS)]
        excluded = original_count - len(net_order)
        console.print(f"  ✓ Excluded {excluded} power/ground nets (use planes instead)")
    
    best_positions = positions
    best_conflicts = float('inf')
    congestion_heatmap = None
    no_improvement_count = 0
    
    for iteration in range(args.max_iterations):
        console.print(f"\n[bold yellow]═══ Outer Loop Iteration {iteration + 1}/{args.max_iterations} ═══[/]")
        
        # ===== 1. Run Placement (if we have congestion feedback) =====
        if congestion_heatmap is not None:
            console.print(f"\n[bold cyan]Phase A:[/] Optimizing placement with routing feedback...")
            
            # Import routing-aware losses
            from temper_placer.losses import (
                OverlapLoss,
                BoundaryLoss,
                MCUClusteringLoss,
                BusAlignmentLoss,
                RoutingChannelLoss,
            )
            from temper_placer.losses.routing_congestion import RoutingCongestionLoss
            
            # Create losses (weights applied in combined_loss)
            overlap_loss = OverlapLoss()
            boundary_loss = BoundaryLoss()
            channel_loss = RoutingChannelLoss(weight=20.0, min_channel_width=5.0)
            
            # MCU clustering - find MCU and its peripherals
            mcu_clustering = MCUClusteringLoss.from_netlist(
                netlist, mcu_ref="U_MCU", weight=10.0, max_distance=20.0
            )
            
            # Bus alignment for SPI, I2C, USB
            bus_alignment = BusAlignmentLoss.from_netlist(netlist, weight=5.0)
            
            # Congestion loss from routing feedback
            congestion_loss = RoutingCongestionLoss(
                congestion_heatmap,
                weight=30.0,
                cell_size_mm=args.cell_size,
                origin=board.origin,
            )
            
            # Simple gradient descent for placement adjustment
            import jax
            from temper_placer.losses.base import LossContext
            
            # Create context using factory method
            context = LossContext.from_netlist_and_board(netlist, board)
            
            # Combined loss function with weights
            def combined_loss(pos):
                rotations = jnp.zeros((len(netlist.components), 4))
                total = 0.0
                total += 100.0 * overlap_loss(pos, rotations, context).value
                total += 50.0 * boundary_loss(pos, rotations, context).value
                total += channel_loss(pos, rotations, context).value
                total += mcu_clustering(pos, rotations, context).value
                total += bus_alignment(pos, rotations, context).value
                total += congestion_loss(pos)
                return total
            
            # Gradient descent for N steps
            grad_fn = jax.grad(combined_loss)
            learning_rate = 0.5
            for step in range(args.placement_steps):
                grads = grad_fn(positions)
                positions = positions - learning_rate * grads
                # Clamp to board bounds
                positions = jnp.clip(
                    positions,
                    jnp.array([5.0, 5.0]),
                    jnp.array([board.width - 5.0, board.height - 5.0])
                )
            
            console.print(f"  ✓ Ran {args.placement_steps} placement optimization steps")
        
        # ===== 2. Run Routing =====
        console.print(f"\n[bold cyan]Phase B:[/] Routing...")
        
        router = MazeRouter.from_board(
            board,
            cell_size_mm=args.cell_size,
            num_layers=2,
            via_cost=10.0,
            soft_blocking=True,
        )
        
        # Block components at current positions
        router.block_components(netlist.components, positions)
        
        # Route all nets
        results = router.rrr_route_all_nets(
            netlist,
            positions,
            net_order,
            assignments,
            max_iterations=args.rrr_iters,
            history_increment=2.0,
        )
        
        # Get conflict information
        conflict_locs = router.get_conflict_locations()
        num_conflicts = len(conflict_locs)
        successful = sum(1 for r in results.values() if r.success)
        completion = (successful / len(net_order)) * 100 if net_order else 100
        
        console.print(f"  ✓ Routed: {successful}/{len(net_order)} ({completion:.1f}%)")
        console.print(f"  ✓ Conflicts: {num_conflicts}")
        
        # ===== 3. Check for convergence =====
        if num_conflicts <= args.target_conflicts:
            console.print(f"\n[bold green]✓ Target reached! ({num_conflicts} <= {args.target_conflicts})[/]")
            best_positions = positions
            best_conflicts = num_conflicts
            break
        
        if num_conflicts < best_conflicts:
            best_positions = positions
            best_conflicts = num_conflicts
            no_improvement_count = 0
            console.print(f"  [green]New best: {best_conflicts} conflicts[/]")
        else:
            no_improvement_count += 1
            if no_improvement_count >= 3:
                console.print(f"  [yellow]No improvement for {no_improvement_count} iterations, stopping early[/]")
                break
        
        # ===== 4. Build congestion heatmap for next iteration =====
        if num_conflicts > 0:
            conflicts = [
                ConflictLocation(
                    x=loc['x'],
                    y=loc['y'],
                    layer=loc['layer'],
                    nets=loc['nets'],
                )
                for loc in conflict_locs
            ]
            congestion_heatmap = compute_congestion_heatmap(
                conflicts,
                grid_size=router.grid_size,
                cell_size_mm=args.cell_size,
                origin=board.origin,
                blur_sigma=3.0,
            )
    
    # ===== Final Output =====
    console.print(f"\n[bold blue]═══ Final Result ═══[/]")
    console.print(f"Best conflicts: {best_conflicts}")
    
    # Export with best positions
    # TODO: Re-route with best positions and export
    console.print(f"\n[bold green]Done![/] Best result had {best_conflicts} conflicts")
    

def _apply_congestion_nudge(
    positions,
    congestion_heatmap,
    cell_size_mm: float,
    origin: tuple[float, float],
    nudge_strength: float,
):
    """Nudge components away from congested areas.
    
    Uses gradient of congestion heatmap to push components
    in the direction of lower congestion.
    """
    import jax.numpy as jnp
    
    grid_w, grid_h = congestion_heatmap.shape
    new_positions = []
    
    for pos in positions:
        # Convert to grid coordinates
        gx = int((pos[0] - origin[0]) / cell_size_mm)
        gy = int((pos[1] - origin[1]) / cell_size_mm)
        gx = max(1, min(grid_w - 2, gx))
        gy = max(1, min(grid_h - 2, gy))
        
        # Compute gradient (central difference)
        grad_x = (congestion_heatmap[gx + 1, gy] - congestion_heatmap[gx - 1, gy]) / 2.0
        grad_y = (congestion_heatmap[gx, gy + 1] - congestion_heatmap[gx, gy - 1]) / 2.0
        
        # Normalize and apply nudge (move against gradient)
        mag = float(jnp.sqrt(grad_x**2 + grad_y**2))
        if mag > 0.01:
            dx = -nudge_strength * (grad_x / mag)
            dy = -nudge_strength * (grad_y / mag)
            new_pos = (float(pos[0]) + dx, float(pos[1]) + dy)
        else:
            new_pos = (float(pos[0]), float(pos[1]))
        
        new_positions.append(new_pos)
    
    return jnp.array(new_positions)


if __name__ == "__main__":
    main()
