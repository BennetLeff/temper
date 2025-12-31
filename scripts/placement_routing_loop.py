#!/usr/bin/env python3
"""
Placement-Routing Feedback Loop

This script implements the architecture-defined feedback loop:
  Placement → Routing → Evaluate → Placement Feedback → iterate

Usage:
    uv run python scripts/placement_routing_loop.py \\
        pcb/input.kicad_pcb \\
        -o pcb/output.kicad_pcb \\
        --max-iterations 5 \\
        --profile-output reports/profile.json
"""

import argparse
import json
import sys
import time
import signal
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()


@dataclass
class LoopProfileStats:
    """Per-iteration profiling statistics."""
    
    iteration: int
    # Phase timings (ms)
    placement_ms: float = 0.0
    routing_ms: float = 0.0
    congestion_analysis_ms: float = 0.0
    total_ms: float = 0.0
    
    # Router sub-stats (from router.stats.profile)
    astar_ms: float = 0.0
    rip_up_ms: float = 0.0
    prepare_costs_ms: float = 0.0
    analyze_conflicts_ms: float = 0.0
    
    # Placement sub-stats
    loss_forward_ms: float = 0.0
    loss_backward_ms: float = 0.0
    num_placement_steps: int = 0
    
    # Results
    nets_routed: int = 0
    nets_failed: int = 0
    num_conflicts: int = 0
    completion_pct: float = 0.0


@dataclass
class ProfileReport:
    """Complete profiling report across all iterations."""
    
    input_pcb: str
    start_time: str
    total_runtime_ms: float = 0.0
    iterations: list[LoopProfileStats] = field(default_factory=list)
    
    # Aggregate stats
    avg_placement_ms: float = 0.0
    avg_routing_ms: float = 0.0
    bottleneck_phase: str = ""
    
    def compute_aggregates(self):
        """Compute aggregate statistics from iteration data."""
        if not self.iterations:
            return
        placement_times = [it.placement_ms for it in self.iterations if it.placement_ms > 0]
        routing_times = [it.routing_ms for it in self.iterations]
        
        self.avg_placement_ms = sum(placement_times) / len(placement_times) if placement_times else 0
        self.avg_routing_ms = sum(routing_times) / len(routing_times) if routing_times else 0
        
        # Identify bottleneck
        if self.avg_routing_ms > self.avg_placement_ms:
            self.bottleneck_phase = "routing"
        else:
            self.bottleneck_phase = "placement"
    
    def to_json(self, path: Path):
        """Write report to JSON file."""
        self.compute_aggregates()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(asdict(self), f, indent=2)


@dataclass
class ConflictLocation:
    x: float
    y: float
    layer: int
    nets: list[str]

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
    parser.add_argument("--profile-output", type=Path, help="Output path for profiling JSON report")
    parser.add_argument("--fixed-refs", type=str, help="Comma-separated list of component references to fix")
    parser.add_argument("--layers", type=int, default=4, help="Number of PCB layers")
    
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
    from temper_placer.losses.routing_congestion import RoutingCongestionLoss
    from temper_placer.io.kicad_writer import write_placements_to_pcb, PlacementUpdate
    from temper_placer.io.trace_writer import write_traces_to_pcb
    import jax.numpy as jnp
    
    # Parse initial PCB
    console.print("\n[bold cyan]Step 1:[/] Parsing PCB...")
    parse_result = parse_kicad_pcb(args.input_pcb)
    board = parse_result.board
    netlist = parse_result.netlist
    # Extract positions - use initial_position like internal_route.py does
    positions = jnp.array([c.initial_position for c in netlist.components])
    
    console.print(f"  ✓ Loaded {len(netlist.components)} components, {len(netlist.nets)} nets")
    console.print(f"  Nets: {', '.join([n.name for n in netlist.nets])}")
    
    # Prepare routing
    from temper_placer.core.loop import LoopCollection
    loops = LoopCollection()
    net_order = order_nets(netlist, loops)
    assignments = assign_layers(netlist)
    
    # Exclude ground AND high-power nets from routing (use copper zones instead)
    # Low-power rails (+3V3, +5V, +15V) are still routed as traces for star topology
    POWER_NET_PATTERNS = [
        # Ground nets
        'GND', 'PGND', 'CGND', 'AGND', 'DGND', 'ISOGND',
        # High-power AC/DC nets (wide traces needed, use copper zones)
        'AC_L', 'AC_N', 'DC_BUS+', 'DC_BUS-',
    ]
    
    if args.exclude_power_nets:
        original_count = len(net_order)
        net_order = [n for n in net_order if not any(p in n for p in POWER_NET_PATTERNS)]
        excluded = original_count - len(net_order)
        console.print(f"  ✓ Excluded {excluded} power/ground nets (use copper zones)")
    
    best_positions = positions
    best_conflicts = float('inf')
    congestion_heatmap = None
    no_improvement_count = 0
    
    # Parse fixed references
    fixed_refs = set(args.fixed_refs.split(",")) if args.fixed_refs else set()
    fixed_mask = jnp.array([1.0 if c.ref in fixed_refs else 0.0 for c in netlist.components])
    fixed_mask = fixed_mask[:, jnp.newaxis] # (N, 1)
    
    # Initialize profiling
    from datetime import datetime
    profile_report = ProfileReport(
        input_pcb=str(args.input_pcb),
        start_time=datetime.now().isoformat(),
    )
    loop_start_time = time.perf_counter()
    
    # Signal handling for graceful interrupt
    stop_requested = False
    def signal_handler(sig, frame):
        nonlocal stop_requested
        stop_requested = True
        console.print("\n[bold red]Interrupt received! Stopping after current step...[/]")

    original_handler = signal.signal(signal.SIGINT, signal_handler)

    from temper_placer.core.design_rules import create_temper_design_rules
    design_rules = create_temper_design_rules()

    for iteration in range(args.max_iterations):
        if stop_requested:
            break
            
        iter_start = time.perf_counter()
        iter_profile = LoopProfileStats(iteration=iteration + 1)
        
        console.print(f"\n[bold yellow]═══ Outer Loop Iteration {iteration + 1}/{args.max_iterations} ═══[/]")
        
        # ===== 1. Run Placement (if we have congestion feedback) =====
        placement_start = time.perf_counter()
        if congestion_heatmap is not None:
            console.print(f"\n[bold cyan]Phase A:[/] Optimizing placement with routing feedback...")
            
            # Import routing-aware losses
            from temper_placer.losses import (
                OverlapLoss,
                BoundaryLoss,
                MCUClusteringLoss,
                BusAlignmentLoss,
                RoutingChannelLoss,
                ComponentSpacingLoss,
            )
            from temper_placer.losses.routing_congestion import RoutingCongestionLoss
            
            # Create losses (weights applied in combined_loss)
            overlap_loss = OverlapLoss()
            boundary_loss = BoundaryLoss()
            # Increase channel width for 0.6mm vias + 0.15mm clearance (0.75mm + extra)
            channel_loss = RoutingChannelLoss(weight=30.0, min_channel_width=8.0)
            
            # MCU clustering - find MCU and its peripherals
            mcu_clustering = MCUClusteringLoss.from_netlist(
                netlist, mcu_ref="U_MCU", weight=10.0, max_distance=20.0
            )
            
            # Bus alignment for SPI, I2C, USB
            bus_alignment = BusAlignmentLoss.from_netlist(netlist, weight=5.0)
            
            # Component spacing for HV components (from config)
            component_spacing = ComponentSpacingLoss(use_rotated_bounds=True)
            
            # Congestion loss from routing feedback
            congestion_loss = RoutingCongestionLoss(
                congestion_heatmap,
                weight=50.0, # Increased from 30.0
                cell_size=args.cell_size,
                origin=jnp.array(board.origin),
                grid_size=jnp.array(router.grid_size),
            )
            
            # Simple gradient descent for placement adjustment
            import jax
            from temper_placer.losses.base import LossContext
            from temper_placer.io.config_loader import load_constraints
            
            # Load constraints to get component_spacing_rules
            config_path = Path("packages/temper-placer/configs/temper_constraints.yaml")
            constraints = load_constraints(config_path) if config_path.exists() else None
            
            # Hotfix: Clear critical loops to avoid validation errors for components 
            # (like U_GD) that might be missing in some netlist versions
            if constraints:
                constraints.critical_loops = []
            
            # Create context using factory method
            context = LossContext.from_netlist_and_board(netlist, board, constraints=constraints)
            
            # Combined loss function with weights
            def combined_loss(pos):
                rotations = jnp.zeros((len(netlist.components), 4))
                total = 0.0
                total += 1500.0 * overlap_loss(pos, rotations, context).value # Increased from 1000
                total += 300.0 * boundary_loss(pos, rotations, context).value # Increased from 200
                total += channel_loss(pos, rotations, context).value
                total += mcu_clustering(pos, rotations, context).value
                total += bus_alignment(pos, rotations, context).value
                total += 25.0 * component_spacing(pos, rotations, context).value  # NEW: Enforce HV spacing
                total += congestion_loss(pos, rotations, context).value
                return total
            
            # Gradient descent for N steps
            grad_fn = jax.grad(combined_loss)
            learning_rate = 0.05
            for step in range(args.placement_steps):
                grads = grad_fn(positions)
                
                # Safety: Replace NaNs with 0.0 (vectorized, no sync)
                grads = jnp.nan_to_num(grads, nan=0.0)

                # Apply fixed mask (only move non-fixed components)
                grads = grads * (1.0 - fixed_mask)
                
                # Gradient clipping
                grad_norm = jnp.linalg.norm(grads)
                # Avoid division by zero
                grad_norm = jnp.where(grad_norm > 1e-6, grad_norm, 1.0)
                
                # Clip scaling factor
                scale = jnp.where(grad_norm > 10.0, 10.0 / grad_norm, 1.0)
                grads = grads * scale
                
                positions = positions - learning_rate * grads
                # Clamp to board bounds
                positions = jnp.clip(
                    positions,
                    jnp.array([5.0, 5.0]),
                    jnp.array([board.width - 5.0, board.height - 5.0])
                )
            
            console.print(f"  ✓ Ran {args.placement_steps} placement optimization steps")
            iter_profile.num_placement_steps = args.placement_steps
        
        iter_profile.placement_ms = (time.perf_counter() - placement_start) * 1000.0
        
        # ===== 2. Run Routing =====
        routing_start = time.perf_counter()
        console.print(f"\n[bold cyan]Phase B:[/] Routing...")
        
        router = MazeRouter.from_board(
            board,
            cell_size_mm=args.cell_size,
            num_layers=args.layers,
            via_cost=10.0,
            soft_blocking=True,
            min_clearance=0.15,
            design_rules=design_rules,
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
        
        iter_profile.routing_ms = (time.perf_counter() - routing_start) * 1000.0
        
        # Capture router sub-stats
        iter_profile.astar_ms = router.stats.profile.astar_total_ms
        iter_profile.rip_up_ms = router.stats.profile.rip_up_ms
        iter_profile.prepare_costs_ms = router.stats.profile.prepare_costs_ms
        iter_profile.analyze_conflicts_ms = router.stats.profile.analyze_conflicts_ms
        iter_profile.nets_routed = successful
        iter_profile.nets_failed = len(net_order) - successful
        iter_profile.num_conflicts = num_conflicts
        iter_profile.completion_pct = completion
        
        console.print(f"  ✓ Routed: {successful}/{len(net_order)} ({completion:.1f}%)")
        console.print(f"  ✓ Conflicts: {num_conflicts}")
        console.print(f"  ✓ Routing took {iter_profile.routing_ms:.1f}ms (A* {iter_profile.astar_ms:.1f}ms)")
        
        # ===== 3. Check for convergence =====
        if num_conflicts <= args.target_conflicts and successful == len(net_order):
            console.print(f"\n[bold green]✓ Target reached! ({num_conflicts} <= {args.target_conflicts} and all routed)[/]")
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
        congestion_start = time.perf_counter()
        # Improved: Use router's internal history cost instead of reconstructing from points
        if num_conflicts > 0 or True: # Always use congestion feedback if available?
            # history_cost is (W, H, L)
            # Sum over layers to get 2D map
            import numpy as np
            hist = np.asarray(router.history_cost)
            # Normalize: subtract 1.0 base cost
            congestion_heatmap = jnp.array(np.sum(np.maximum(0, hist - 1.0), axis=2))
            
            max_heat = jnp.max(congestion_heatmap)
            console.print(f"  Generated congestion heatmap (max cost: {max_heat:.1f})")
        iter_profile.congestion_analysis_ms = (time.perf_counter() - congestion_start) * 1000.0 if 'congestion_start' in dir() else 0.0
        
        # Record iteration timing
        iter_profile.total_ms = (time.perf_counter() - iter_start) * 1000.0
        profile_report.iterations.append(iter_profile)
        
        console.print(f"  [dim]Iteration total: {iter_profile.total_ms:.1f}ms[/]")
        
        console.print(f"  [dim]Iteration total: {iter_profile.total_ms:.1f}ms[/]")
        
        if stop_requested:
            console.print("\n[bold red]Interrupted by user! Saving best result so far...[/]")
            break
            
    # ===== Final Output =====
    profile_report.total_runtime_ms = (time.perf_counter() - loop_start_time) * 1000.0
    console.print(f"\n[bold blue]═══ Final Result ═══[/]")
    console.print(f"Best conflicts: {best_conflicts}")
    
    # Export with best positions
    if args.output:
        console.print(f"\n[bold cyan]Phase C:[/] Exporting best result to {args.output}...")
        
        # 1. Update component positions
        placements = {}
        for i, c in enumerate(netlist.components):
            # Convert center position back to footprint origin
            # Parser stores unrotated offset in attributes
            cx_off = float(c.attributes.get("_center_offset_x", "0"))
            cy_off = float(c.attributes.get("_center_offset_y", "0"))
            
            # Use initial rotation (in degrees)
            rot_deg = float(c.initial_rotation) * 90.0 if c.initial_rotation is not None else 0.0
            
            # Rotate offset back (KiCad rotates counter-clockwise)
            import math
            rot_rad = math.radians(rot_deg)
            rotated_cx = cx_off * math.cos(rot_rad) - cy_off * math.sin(rot_rad)
            rotated_cy = cx_off * math.sin(rot_rad) + cy_off * math.cos(rot_rad)
            
            placements[c.ref] = PlacementUpdate(
                ref=c.ref,
                x=float(best_positions[i, 0]) - rotated_cx + board.origin[0],
                y=float(best_positions[i, 1]) - rotated_cy + board.origin[1],
                rotation=rot_deg,
            )
        
        # Create a temporary file for placement-only PCB
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", delete=False) as tf:
            temp_placed_pcb = Path(tf.name)
        
        try:
            write_placements_to_pcb(args.input_pcb, temp_placed_pcb, placements)
            
            # 2. Re-run routing one last time with best positions to get full results for export
            # (In a real implementation we'd cache the best 'results' object)
            router = MazeRouter.from_board(
                board,
                cell_size_mm=args.cell_size,
                num_layers=args.layers,
                via_cost=10.0,
                soft_blocking=True,
            )
            router.block_components(netlist.components, best_positions)
            final_results = router.rrr_route_all_nets(
                netlist,
                best_positions,
                net_order,
                assignments,
                max_iterations=args.rrr_iters,
            )
            
            # 3. Write traces
            items_added = write_traces_to_pcb(
                temp_placed_pcb,
                args.output,
                final_results,
                cell_size=args.cell_size,
                origin=board.origin,
                default_trace_width=0.15,
                via_size=0.6,
                via_drill=0.3,
                netlist=netlist,
            )
            console.print(f"  ✓ Exported {items_added} trace segments and vias")
            
        finally:
            if temp_placed_pcb.exists():
                temp_placed_pcb.unlink()

    console.print(f"\n[bold green]Done![/] Best result had {best_conflicts} conflicts")
    console.print(f"Total runtime: {profile_report.total_runtime_ms:.1f}ms")
    
    # Write profile report if requested
    if args.profile_output:
        profile_report.to_json(args.profile_output)
        console.print(f"[dim]Profile report written to {args.profile_output}[/]")
        
        # Print bottleneck summary
        profile_report.compute_aggregates()
        console.print(f"[bold]Bottleneck phase:[/] {profile_report.bottleneck_phase}")
        console.print(f"  Avg placement: {profile_report.avg_placement_ms:.1f}ms")
        console.print(f"  Avg routing: {profile_report.avg_routing_ms:.1f}ms")
    

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
