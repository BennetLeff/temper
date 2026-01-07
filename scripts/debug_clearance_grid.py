#!/usr/bin/env python3
"""
Debug script to visualize the clearance grid after ClearanceGridStage runs.

This helps understand what the router 'sees' when deciding where to route,
and can identify issues like incorrect pad blocking or gaps in clearance zones.

Usage:
    python scripts/debug_clearance_grid.py [--output-dir DIR]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add package to path
sys.path.insert(0, str(Path(__file__).parent.parent / "packages/temper-placer/src"))

from temper_placer.deterministic import create_drc_aware_pipeline, BoardState
from temper_placer.io.config_loader import load_constraints, constraints_to_design_rules
from temper_placer.io.kicad_parser import parse_kicad_pcb

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Debug Clearance Grid Visualization")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/debug_grid"),
        help="Output directory for visualizations",
    )
    parser.add_argument(
        "--pcb",
        type=Path,
        default=None,
        help="PCB file to use (default: pcb/temper_deterministic_final.kicad_pcb)",
    )
    args = parser.parse_args()

    # Setup paths
    repo_root = Path(__file__).parent.parent
    pcb_path = args.pcb or repo_root / "pcb/temper_deterministic_final.kicad_pcb"
    config_path = repo_root / "configs/temper_deterministic_config.yaml"

    if not pcb_path.exists():
        logger.error(f"PCB not found: {pcb_path}")
        sys.exit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Clearance Grid Debug Visualization")
    print("=" * 60)
    print(f"PCB: {pcb_path}")
    print(f"Config: {config_path}")
    print(f"Output: {args.output_dir}")
    print()

    # Load board and config
    logger.info("Loading board and config...")
    parse_result = parse_kicad_pcb(pcb_path)
    constraints = load_constraints(config_path)
    design_rules = constraints_to_design_rules(constraints)

    # Apply net class mapping
    net_class_mapping = getattr(constraints, "net_classes", {})
    if net_class_mapping and parse_result.netlist:
        updated = parse_result.netlist.apply_net_class_mapping(net_class_mapping)
        logger.info(f"Applied net class mapping: {updated} nets updated")

    # Create pipeline
    pipeline = create_drc_aware_pipeline(design_rules=design_rules, config=constraints)

    # Create initial state
    state = BoardState(board=parse_result.board, netlist=parse_result.netlist)

    # Run stages up to and including ClearanceGridStage
    logger.info("Running pipeline stages up to ClearanceGridStage...")
    for stage in pipeline.stages:
        logger.info(f"  Running: {stage.name}")
        state = stage.run(state)

        if stage.name == "clearance_grid":
            break

    # Check if we have a grid
    if not state.grid:
        logger.error("No clearance grid found in state!")
        sys.exit(1)

    grid = state.grid

    # Export stats
    stats = grid.export_stats()
    stats_path = args.output_dir / "clearance_grid_stats.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)
    logger.info(f"Saved stats to {stats_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("CLEARANCE GRID STATISTICS")
    print("=" * 60)
    print(f"Grid dimensions: {stats['dimensions']['cols']} x {stats['dimensions']['rows']} cells")
    print(f"Cell size: {stats['dimensions']['cell_size_mm']}mm")
    print(f"Board size: {stats['dimensions']['width_mm']}mm x {stats['dimensions']['height_mm']}mm")
    print(f"Total cells: {stats['dimensions']['total_cells']:,}")
    print(f"Nets registered: {stats['nets_registered']}")
    print()
    print("Blocking by layer:")
    for layer_name, layer_stats in stats["blocking"].items():
        print(f"  {layer_name}:")
        print(f"    Pad blocked: {layer_stats['pad_blocked_cells']:,} cells")
        print(f"    Trace blocked: {layer_stats['trace_blocked_cells']:,} cells")
        print(
            f"    Total blocked: {layer_stats['total_blocked_cells']:,} cells ({layer_stats['blocked_percentage']:.1f}%)"
        )

    # Get component positions for overlay
    component_positions = {}
    if state.placements:
        for ref, pos in state.placements:
            component_positions[ref] = pos
    elif parse_result.netlist:
        for comp in parse_result.netlist.components:
            if comp.initial_position:
                component_positions[comp.ref] = comp.initial_position

    # Export visualizations for each layer
    print()
    print("Generating visualizations...")
    layer_names = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
    for layer_idx in range(min(grid.layer_count, 4)):
        layer_name = (
            layer_names[layer_idx] if layer_idx < len(layer_names) else f"Layer_{layer_idx}"
        )
        output_path = args.output_dir / f"clearance_grid_{layer_name.replace('.', '_')}.png"
        grid.export_visualization(
            str(output_path), layer=layer_idx, component_positions=component_positions
        )

    # Additional analysis: Check specific HV components
    print()
    print("=" * 60)
    print("HV COMPONENT PAD ANALYSIS")
    print("=" * 60)

    hv_components = ["Q1", "Q2", "C_BUS1", "C_BUS2", "U_GATE", "D1", "D2"]

    if parse_result.netlist:
        for ref in hv_components:
            try:
                comp = parse_result.netlist.get_component(ref)
                pos = component_positions.get(ref, comp.initial_position)
                if pos:
                    print(f"\n{ref} at ({pos[0]:.1f}, {pos[1]:.1f}):")
                    print(f"  Footprint: {comp.footprint}")
                    print(f"  Bounds: {comp.bounds[0]:.1f} x {comp.bounds[1]:.1f} mm")
                    print(f"  Pins: {len(comp.pins)}")
                    for pin in comp.pins[:5]:
                        net = pin.net or "NC"
                        net_class = "unknown"
                        if pin.net and parse_result.netlist:
                            try:
                                net_obj = parse_result.netlist.get_net(pin.net)
                                net_class = net_obj.net_class
                            except:
                                pass
                        pin_pos = (pos[0] + pin.position[0], pos[1] + pin.position[1])
                        print(
                            f"    Pin {pin.name}: net={net} ({net_class}), "
                            f"pos=({pin_pos[0]:.1f}, {pin_pos[1]:.1f}), "
                            f"size={pin.width:.2f}x{pin.height:.2f}, "
                            f"PTH={pin.is_pth}"
                        )
                    if len(comp.pins) > 5:
                        print(f"    ... and {len(comp.pins) - 5} more pins")
            except KeyError:
                print(f"\n{ref}: NOT FOUND in netlist")

    # Check clearance values used
    print()
    print("=" * 60)
    print("NET CLASS CLEARANCES (from pipeline)")
    print("=" * 60)

    # Find the ClearanceGridStage to get its config
    for stage in pipeline.stages:
        if stage.name == "clearance_grid":
            print(f"Max clearance (fallback): {stage.max_clearance_mm}mm")
            print("Net class clearances:")
            for name, clearance in stage.net_class_clearances.items():
                print(f"  {name}: {clearance}mm")
            break

    print()
    print(f"Visualizations saved to: {args.output_dir}")
    print("Done!")


if __name__ == "__main__":
    main()
