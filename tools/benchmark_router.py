#!/usr/bin/env python3
"""
Benchmark script for maze router.

Measures routing completion rate, runtime, and via count on real PCB layouts.
"""

import time
from pathlib import Path
import sys

# Add temper-placer to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.io.reference_loader import load_reference_pcb
from temper_placer.router_v6._routing_shim.maze_router import MazeRouter, order_nets_for_routing


def benchmark_router(pcb_path: Path, net_ordering: str = "shortest_first"):
    """
    Benchmark router on a single PCB file.
    
    Args:
        pcb_path: Path to .kicad_pcb file
        net_ordering: Net ordering strategy
    
    Returns:
        dict with metrics
    """
    print(f"\n{'='*60}")
    print(f"Benchmarking: {pcb_path.name}")
    print(f"Net ordering: {net_ordering}")
    print(f"{'='*60}")
    
    try:
        # Load PCB
        print("Loading PCB...")
        design = load_reference_pcb(pcb_path)
        
        print(f"  Components: {design.netlist.n_components}")
        print(f"  Nets: {design.netlist.n_nets}")
        print(f"  Board: {design.board.width:.1f}mm x {design.board.height:.1f}mm")
        
        # Create router using current API
        import math
        cell_size = 1.0  # 1mm grid
        width_cells = int(math.ceil(design.board.width / cell_size))
        height_cells = int(math.ceil(design.board.height / cell_size))
        
        router = MazeRouter(
            grid_size=(width_cells, height_cells),
            cell_size_mm=cell_size,
            num_layers=2,
            origin=design.board.origin,
            via_cost=5.0,
        )
        
        # Block components using block_components method
        print("Blocking components...")
        import jax.numpy as jnp
        positions = jnp.array([[float(design.state.positions[i][0]), 
                               float(design.state.positions[i][1])] 
                              for i in range(len(design.netlist.components))])
        router.block_components(design.netlist.components, positions, margin=0.5)
        
        # Pre-calculate pin positions for all nets
        print("Calculating pin positions...")
        net_pin_positions = {}
        
        for net in design.netlist.nets:
            pin_locs = []
            for comp_ref, pin_name in net.pins:
                try:
                    comp_idx = design.netlist.get_component_index(comp_ref)
                    comp = design.netlist.get_component(comp_ref)
                    pin = comp.get_pin(pin_name)
                    
                    # Get component position
                    comp_pos = design.state.positions[comp_idx]
                    
                    # Add pin offset if available
                    if pin and hasattr(pin, 'position'):
                        pin_x = float(comp_pos[0]) + float(pin.position[0])
                        pin_y = float(comp_pos[1]) + float(pin.position[1])
                    else:
                        pin_x = float(comp_pos[0])
                        pin_y = float(comp_pos[1])
                    
                    pin_locs.append((pin_x, pin_y))
                except (KeyError, AttributeError):
                    continue
            
            if len(pin_locs) >= 2:
                net_pin_positions[net.name] = pin_locs
        
        # Order nets
        print(f"Ordering nets ({net_ordering})...")
        net_names = list(net_pin_positions.keys())
        ordered_nets_names = order_nets_for_routing(
            net_names,
            net_pin_positions,
            strategy=net_ordering
        )
        
        # Route nets
        print("Routing nets...")
        start_time = time.time()
        
        routed_count = 0
        failed_count = 0
        total_vias = 0
        total_wirelength = 0.0
        
        for net_name in ordered_nets_names:
            pin_positions = net_pin_positions[net_name]
            
            # Skip if less than 2 pins (should be filtered already but safety check)
            if len(pin_positions) < 2:
                continue
            
            # Try to route
            try:
                from temper_placer.router_v6._routing_shim.layer_assignment import LayerAssignment, Layer
                assignment = LayerAssignment(
                    net=net_name,
                    primary_layer=Layer.L1_TOP,
                    allowed_layers={Layer.L1_TOP, Layer.L4_BOT},
                    vias_required=True
                )
                result = router.route_net(net_name, pin_positions, assignment)
                if result and result.success:
                    routed_count += 1
                    if hasattr(result, 'length'):
                        total_wirelength += result.length
                    if hasattr(result, 'via_count'):
                        total_vias += result.via_count
                else:
                    failed_count += 1
                    # print(f"Failed to route {net_name}: result.success is False")
            except Exception as e:
                failed_count += 1
                print(f"Failed to route {net_name}: {e}")
                # import traceback
                # traceback.print_exc()
                continue
        
        elapsed = time.time() - start_time
        
        # Calculate metrics
        total_nets = len(ordered_nets_names)
        completion_rate = routed_count / total_nets if total_nets > 0 else 0.0
        avg_wirelength = total_wirelength / routed_count if routed_count > 0 else 0.0
        
        # Print results
        print(f"\n{'='*60}")
        print(f"RESULTS")
        print(f"{'='*60}")
        print(f"Total nets:        {total_nets}")
        print(f"Routed:            {routed_count}")
        print(f"Failed:            {failed_count}")
        print(f"Completion rate:   {completion_rate*100:.1f}%")
        print(f"Total vias:        {total_vias}")
        print(f"Avg wirelength:    {avg_wirelength:.2f} mm")
        print(f"Runtime:           {elapsed:.2f}s")
        print(f"{'='*60}\n")
        
        return {
            "pcb": pcb_path.name,
            "components": design.netlist.n_components,
            "total_nets": total_nets,
            "routed": routed_count,
            "failed": failed_count,
            "completion_rate": completion_rate,
            "total_vias": total_vias,
            "avg_wirelength": avg_wirelength,
            "runtime": elapsed,
            "net_ordering": net_ordering,
        }
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Run benchmarks on temper.kicad_pcb and reference layouts."""
    
    # Find temper.kicad_pcb
    temper_pcb = Path("hardware/temper.kicad_pcb")
    
    results = []
    
    # Benchmark temper.kicad_pcb with different net orderings
    if temper_pcb.exists():
        print("\n" + "="*60)
        print("BENCHMARKING TEMPER.KICAD_PCB")
        print("="*60)
        
        for ordering in ["shortest_first", "power_first", "arbitrary"]:
            result = benchmark_router(temper_pcb, net_ordering=ordering)
            if result:
                results.append(result)
    else:
        print(f"Warning: {temper_pcb} not found, skipping")
    
    # Benchmark reference layouts
    ref_dir = Path("packages/temper-validation/data/reference_layouts")
    if ref_dir.exists():
        print("\n" + "="*60)
        print("BENCHMARKING REFERENCE LAYOUTS")
        print("="*60)
        
        # Find all .kicad_pcb files
        pcb_files = list(ref_dir.rglob("*.kicad_pcb"))
        print(f"Found {len(pcb_files)} reference PCBs")
        
        # Benchmark first 5 (to keep runtime reasonable)
        for pcb_file in pcb_files[:5]:
            result = benchmark_router(pcb_file, net_ordering="shortest_first")
            if result:
                results.append(result)
    
    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"{'PCB':<30} {'Nets':>6} {'Routed':>7} {'Rate':>6} {'Time':>7}")
    print("-"*60)
    
    for r in results:
        print(f"{r['pcb']:<30} {r['total_nets']:>6} {r['routed']:>7} "
              f"{r['completion_rate']*100:>5.1f}% {r['runtime']:>6.1f}s")
    
    # Calculate averages
    if results:
        avg_completion = sum(r['completion_rate'] for r in results) / len(results)
        avg_runtime = sum(r['runtime'] for r in results) / len(results)
        
        print("-"*60)
        print(f"{'AVERAGE':<30} {'':<6} {'':<7} {avg_completion*100:>5.1f}% {avg_runtime:>6.1f}s")
        print("="*60)
        
        # Check success criteria
        print("\nSUCCESS CRITERIA:")
        print(f"  Completion >50%: {'✓ PASS' if avg_completion > 0.5 else '✗ FAIL'} ({avg_completion*100:.1f}%)")
        print(f"  Runtime <60s:    {'✓ PASS' if avg_runtime < 60 else '✗ FAIL'} ({avg_runtime:.1f}s)")


if __name__ == "__main__":
    main()
