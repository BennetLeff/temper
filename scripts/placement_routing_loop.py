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
import signal
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from rich.console import Console

console = Console()

# Adapter for compatibility with loop script
@dataclass
class RoutePathCompat:
    success: bool
    length: float = 0.0




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
    parser.add_argument("--cell-size", type=float, default=0.2, help="Routing grid cell size (mm)")
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

    console.print("[bold blue]Placement-Routing Feedback Loop[/]")
    console.print(f"Input: {args.input_pcb}")
    console.print(f"Output: {args.output}")
    console.print(f"Max iterations: {args.max_iterations}")

    # Import dependencies
    import numpy as np

    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.kicad_writer import PlacementUpdate, write_placements_to_pcb
    from temper_placer.io.trace_writer import write_traces_to_pcb
    from temper_placer.routing.layer_assignment import assign_layers
    from temper_placer.routing.net_ordering import order_nets

    # Parse initial PCB
    console.print("\n[bold cyan]Step 1:[/] Parsing PCB...")
    parse_result = parse_kicad_pcb(args.input_pcb)
    board = parse_result.board
    netlist = parse_result.netlist
    # Extract positions
    positions = np.array([c.initial_position for c in netlist.components])

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
    best_routing_results = {}
    congestion_heatmap = None
    no_improvement_count = 0

    # Parse fixed references
    fixed_refs = set(args.fixed_refs.split(",")) if args.fixed_refs else set()
    fixed_mask = np.array([1.0 if c.ref in fixed_refs else 0.0 for c in netlist.components])
    fixed_mask = fixed_mask[:, np.newaxis] # (N, 1)

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

        # ===== 1. Run Placement =====
        placement_start = time.perf_counter()
        
        # Iteration 0: Use Hierarchical Benders to find a valid global placement
        if iteration == 0:
            console.print("\n[bold cyan]Phase A (Init):[/] Running Hierarchical Benders Placement...")
            from temper_placer.io.benders_adapter import BendersAdapter
            from temper_placer.placement.hierarchical_loop import HierarchicalBendersLoop
            
            # Convert internal data to Benders format
            benders_input = BendersAdapter.convert(board, netlist)
            
            # Run Optimizer
            hb_loop = HierarchicalBendersLoop(input_data=benders_input, pcb_file=str(args.input_pcb))
            hb_result = hb_loop.run()
            
            if hb_result.final_positions:
                console.print(f"  ✓ Benders Placement Successful ({len(hb_result.final_positions)} components)")
                # Update positions array
                new_pos_list = []
                for comp in netlist.components:
                    if comp.ref in hb_result.final_positions:
                        raw_pos = hb_result.final_positions[comp.ref]
                        # Clamp to board (safety)
                        px = max(0.0, min(board.width, raw_pos[0]))
                        py = max(0.0, min(board.height, raw_pos[1]))
                        new_pos_list.append((px, py))
                    else:
                        # Fallback (should not happen if Benders works)
                        new_pos_list.append(comp.initial_position)
                positions = np.array(new_pos_list)
            else:
                console.print("  [red]Warning: Benders Placement failed to return positions. Using default.[/]")

        # Subsequent Iterations: Placeholder for future discrete refinement logic
        elif congestion_heatmap is not None:
             pass

        iter_profile.placement_ms = (time.perf_counter() - placement_start) * 1000.0

        iter_profile.placement_ms = (time.perf_counter() - placement_start) * 1000.0

        # ===== 1.5. Validate Placement DRC =====
        # Check for unroutable pin placements (pins of different nets too close)
        # This prevents Phase B from wasting time on impossible routing
        console.print("\n[bold cyan]Phase A.5:[/] Checking Placement DRC...")

        import numpy as np

        from temper_placer.core.placement_drc import PinInfo, validate_placement_drc

        # Convert JAX positions to numpy
        current_positions = np.array(positions)
        drc_pins = []

        for i, comp in enumerate(netlist.components):
            cx, cy = current_positions[i]
            # Assume 0 rotation as per loop logic (rotations = zeros)
            rads = 0.0

            for pin in comp.pins:
                # Use absolute_position fromPin class
                px, py = pin.absolute_position((cx, cy), rads)

                # Determine meaningful net name
                net_name = pin.net if pin.net else "UNCONNECTED"

                drc_pins.append(PinInfo(
                    x=px, y=py,
                    net_name=net_name,
                    component_name=comp.ref,
                    pin_name=pin.name,
                    diameter_mm=1.0 # Approximate, or ideally pin.width
                ))

        placment_violations = validate_placement_drc(drc_pins, min_clearance_mm=0.2)
        if placment_violations:
            console.print(f"[bold red]Found {len(placment_violations)} Placement DRC Violations![/]")
            # Log first few
            for v in placment_violations[:5]:
                console.print(f"  [red]Violation:[/] {v.message}")
            if len(placment_violations) > 5:
                console.print(f"  ...and {len(placment_violations)-5} more.")
        else:
            console.print("  [green]✓ Placement DRC Passed[/]")


        # ===== 2. Run Routing =====
        routing_start = time.perf_counter()
        console.print("\n[bold cyan]Phase B:[/] Routing (Exact Geometry V6)...")

        # Create temporary PCB with current placement to ensure router sees valid positions
        temp_pcb_path = Path("temp_placement_v6.kicad_pcb")
        from temper_placer.io.kicad_writer import export_placements, PlacementUpdate
        from temper_placer.core.state import PlacementState
        
        # Build placement state
        placements_dict = {}
        processed_refs = []
        for i, comp in enumerate(netlist.components):
            p = PlacementUpdate(
                ref=comp.ref,
                x=float(positions[i][0]),
                y=float(positions[i][1]),
                rotation=0.0
            )
            placements_dict[comp.ref] = p
            processed_refs.append(comp.ref)
            
        dummy_state = PlacementState(
            positions=positions,
            rotation_logits=np.zeros((len(positions), 4)),
            net_virtual_nodes=None
        )
        
        export_placements(
            template_pcb=args.input_pcb,
            output_pcb=temp_pcb_path,
            state=dummy_state,
            component_refs=processed_refs,
            components=netlist.components
        )
        
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        parse_result = parse_kicad_pcb(temp_pcb_path, normalize=False)
        
        if not parse_result.board:
             console.print("[red]Failed to parse temp PCB![/]")
             continue

        from temper_placer.router_v6.stage0_data import (
            ParsedPCB, 
            StackupInfo, 
            LayerInfo, 
            DesignRules as V6DesignRules,
            NetClassRules as V6NetClassRules
        )
        
        if not hasattr(parse_result, 'stackup') or not parse_result.stackup:
             stackup = StackupInfo(
                layers=[
                    LayerInfo(0, "F.Cu", "signal", 35.0),
                    LayerInfo(1, "In1.Cu", "plane", 35.0, "GND"), 
                    LayerInfo(2, "In2.Cu", "plane", 35.0, "+15V"),
                    LayerInfo(3, "B.Cu", "signal", 35.0)
                ],
                total_thickness_mm=1.6,
                layer_count=4
             )
        else:
             stackup = parse_result.stackup

        # Convert Legacy DesignRules to V6 DesignRules
        v6_net_classes = {}
        for name, rules in design_rules.net_classes.items():
            # Legacy NetClassRules fields: name, trace_width, clearance, via_diameter, via_drill
             v6_net_classes[name] = V6NetClassRules(
                 name=rules.name,
                 clearance_mm=rules.clearance,
                 trace_width_mm=rules.trace_width,
                 via_diameter_mm=rules.via_diameter,
                 via_drill_mm=rules.via_drill,
             )
             
        v6_design_rules = V6DesignRules(
             net_classes=v6_net_classes,
             net_class_assignments=design_rules.net_class_assignments,
             default_clearance_mm=design_rules.default_clearance,
             default_trace_width_mm=design_rules.default_trace_width,
             default_via_diameter_mm=design_rules.default_via_diameter,
             default_via_drill_mm=design_rules.default_via_drill,
        )

        parsed_pcb = ParsedPCB(
            components=parse_result.netlist.components,
            nets=parse_result.netlist.nets,
            zones=parse_result.zones if hasattr(parse_result, 'zones') else [],
            board=parse_result.board,
            design_rules=v6_design_rules,
            stackup=stackup,
            source_path=temp_pcb_path,
            tracks=parse_result.traces,
        )

        from temper_placer.router_v6.exact_geometry_router import ExactGeometryRouter
        router = ExactGeometryRouter(parsed_pcb, v6_design_rules, kicad_file=str(temp_pcb_path))
        
        try:
            raw_results = router.route_all()
        except Exception as e:
            console.print(f"[red]Routing failed with error: {e}[/]")
            import traceback
            traceback.print_exc()
            raw_results = {}

        results = {}
        nets_routed_count = 0
        target_nets = set(n.name for n in netlist.nets)
        if args.exclude_power_nets:
             target_nets = {n for n in target_nets if not any(p in n for p in POWER_NET_PATTERNS)}

        for net_name in target_nets:
            if net_name in raw_results:
                results[net_name] = RoutePathCompat(success=True, length=raw_results[net_name].total_length())
                nets_routed_count += 1
            else:
                results[net_name] = RoutePathCompat(success=False)

        # Get conflict information (Assumed 0 for ExactGeometryRouter as it enforces DRC)
        conflict_locs = [] 
        num_conflicts = 0 
        successful = nets_routed_count
        completion = (successful / len(net_order)) * 100 if net_order else 100

        iter_profile.routing_ms = (time.perf_counter() - routing_start) * 1000.0

        # Capture router sub-stats
        iter_profile.nets_routed = successful
        iter_profile.nets_failed = len(net_order) - successful
        iter_profile.num_conflicts = num_conflicts
        iter_profile.completion_pct = completion

        console.print(f"  ✓ Routed: {successful}/{len(net_order)} ({completion:.1f}%)")
        console.print(f"  ✓ Conflicts: {num_conflicts}")
        console.print(f"  ✓ Routing took {iter_profile.routing_ms:.1f}ms")

        # ===== 3. Check for convergence =====
        if num_conflicts <= args.target_conflicts and successful >= len(net_order) * 0.95:
            console.print(f"\n[bold green]✓ Target reached! ({num_conflicts} <= {args.target_conflicts} and routed > 95%)[/]")
            best_positions = positions
            best_conflicts = num_conflicts
            best_routing_results = raw_results
            break

        if num_conflicts < best_conflicts:
            best_positions = positions
            best_conflicts = num_conflicts
            best_routing_results = raw_results
            no_improvement_count = 0
            console.print(f"  [green]New best: {best_conflicts} conflicts[/]")
        else:
            no_improvement_count += 1
            if no_improvement_count >= 3:
                console.print(f"  [yellow]No improvement for {no_improvement_count} iterations, stopping early[/]")
                break

        # ===== 4. Build congestion heatmap for next iteration =====
        congestion_start = time.perf_counter()
        # Mock for now as ExactGeometryRouter doesn't expose history grid yet
        congestion_heatmap = np.zeros((640, 480)) 
        
        iter_profile.congestion_analysis_ms = (time.perf_counter() - congestion_start) * 1000.0
        iter_profile.total_ms = (time.perf_counter() - iter_start) * 1000.0
        profile_report.iterations.append(iter_profile)

        console.print(f"  [dim]Iteration total: {iter_profile.total_ms:.1f}ms[/]")

        console.print(f"  [dim]Iteration total: {iter_profile.total_ms:.1f}ms[/]")

        if stop_requested:
            console.print("\n[bold red]Interrupted by user! Saving best result so far...[/]")
            break

    # ===== Final Output =====
    profile_report.total_runtime_ms = (time.perf_counter() - loop_start_time) * 1000.0
    console.print("\n[bold blue]═══ Final Result ═══[/]")
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

            # 2. Export exact routes
            from temper_placer.io.trace_writer import write_exact_routes_to_pcb

            if best_routing_results:
                items_added = write_exact_routes_to_pcb(
                    temp_placed_pcb,
                    args.output,
                    best_routing_results
                )
                console.print(f"  ✓ Exported {items_added} trace/via items")
            else:
                 console.print("  [yellow]Warning: No routing results available to export.[/]")

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
        mag = float(np.sqrt(grad_x**2 + grad_y**2))
        if mag > 0.01:
            dx = -nudge_strength * (grad_x / mag)
            dy = -nudge_strength * (grad_y / mag)
            new_pos = (float(pos[0]) + dx, float(pos[1]) + dy)
        else:
            new_pos = (float(pos[0]), float(pos[1]))

        new_positions.append(new_pos)

    return np.array(new_positions)


if __name__ == "__main__":
    main()
