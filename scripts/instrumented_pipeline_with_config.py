#!/usr/bin/env python3
"""Instrumented pipeline test with proper config loading.

This script runs the pipeline on the temper board with the full config
(including differential pair settings) and logs USB trace counts.
"""

import sys
from pathlib import Path

sys.path.insert(0, "packages/temper-placer/src")

from collections import defaultdict


def count_usb_traces(routes):
    """Count USB D+/D- traces."""
    from temper_placer.core.board import Trace

    if not routes:
        return 0, 0
    usb_dp = sum(1 for t in routes if isinstance(t, Trace) and t.net == "USB_D+")
    usb_dm = sum(1 for t in routes if isinstance(t, Trace) and t.net == "USB_D-")
    return usb_dp, usb_dm


def check_usb_connectivity(routes, net_name="USB_D+"):
    """Check connectivity of a net's traces."""
    from temper_placer.core.board import Trace

    traces = [t for t in routes if isinstance(t, Trace) and t.net == net_name]
    if not traces:
        return {"count": 0, "components": 0, "endpoints": 0, "x_span": (0, 0)}

    adj = defaultdict(set)
    for t in traces:
        start = (round(t.start[0], 3), round(t.start[1], 3))
        end = (round(t.end[0], 3), round(t.end[1], 3))
        adj[start].add(end)
        adj[end].add(start)

    # Count connected components
    visited = set()
    components = 0
    for node in adj:
        if node not in visited:
            components += 1
            stack = [node]
            while stack:
                n = stack.pop()
                if n not in visited:
                    visited.add(n)
                    stack.extend(adj[n] - visited)

    endpoints = sum(1 for p, n in adj.items() if len(n) == 1)
    x_coords = [t.start[0] for t in traces] + [t.end[0] for t in traces]

    return {
        "count": len(traces),
        "components": components,
        "endpoints": endpoints,
        "x_span": (min(x_coords), max(x_coords)) if x_coords else (0, 0),
    }


def run_instrumented_pipeline():
    """Run pipeline with instrumentation on USB traces."""
    print("=" * 70)
    print("INSTRUMENTED PIPELINE TEST (with config)")
    print("=" * 70)

    # Import pipeline components
    from temper_placer.deterministic import create_drc_aware_pipeline
    from temper_placer.deterministic.state import BoardState
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.kicad_writer import write_routes_to_pcb
    from temper_placer.io.config_loader import load_constraints

    # Load config
    config_path = Path("configs/temper_deterministic_config.yaml")
    if not config_path.exists():
        print(f"ERROR: Config not found at {config_path}")
        return False

    config = load_constraints(config_path)
    print(f"Loaded config from {config_path}")
    print(f"  Differential pairs: {len(config.differential_pairs)}")
    for dp in config.differential_pairs:
        print(f"    - {dp.net_pos}/{dp.net_neg} spacing={dp.spacing_mm}mm")

    # Load board
    board_path = Path("pcb/temper.kicad_pcb")
    if not board_path.exists():
        print(f"ERROR: Board not found at {board_path}")
        return False

    result = parse_kicad_pcb(board_path)
    print(f"Loaded board from {board_path}")
    print(f"  Components: {len(result.netlist.components)}")
    print(f"  Nets: {len(result.netlist.nets)}")

    # Extract metadata for DRC-aware pipeline
    from temper_placer.io.kicad_metadata import extract_kicad_metadata

    metadata = extract_kicad_metadata(board_path)
    print(f"  Metadata: {len(metadata.courtyards)} courtyards, {len(metadata.pad_sizes)} pads")

    # Create initial state from parsed result
    initial_state = BoardState(
        netlist=result.netlist,
        board=result.board,
    )

    # Create pipeline WITH CONFIG
    print("\nCreating pipeline with differential pair config...")
    pipeline = create_drc_aware_pipeline(config=config, metadata=metadata)

    # Monkey-patch stages to add instrumentation
    print("Instrumenting stages...")

    for stage in pipeline.stages:
        original_run = stage.run
        stage_name = stage.name

        def make_instrumented_run(orig_run, name):
            def instrumented_run(state):
                before_dp, before_dm = count_usb_traces(state.routes)
                result = orig_run(state)
                after_dp, after_dm = count_usb_traces(result.routes)

                delta_dp = after_dp - before_dp
                delta_dm = after_dm - before_dm

                if delta_dp != 0 or delta_dm != 0:
                    print(
                        f"  *** {name}: USB_D+ {before_dp}->{after_dp} ({delta_dp:+d}), "
                        f"USB_D- {before_dm}->{after_dm} ({delta_dm:+d}) ***"
                    )
                elif before_dp > 0 or after_dp > 0:  # Only log if there are traces
                    print(f"  {name}: USB_D+ {after_dp}, USB_D- {after_dm}")
                return result

            return instrumented_run

        stage.run = make_instrumented_run(original_run, stage_name)

    # Run pipeline
    print("\n" + "=" * 70)
    print("RUNNING PIPELINE (watching USB traces)")
    print("=" * 70)

    try:
        state = pipeline.run(initial_state)
    except Exception as e:
        print(f"\nPipeline error: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Final analysis
    print("\n" + "=" * 70)
    print("FINAL ANALYSIS")
    print("=" * 70)

    dp_stats = check_usb_connectivity(state.routes, "USB_D+")
    dm_stats = check_usb_connectivity(state.routes, "USB_D-")

    print(f"\nUSB_D+ final state:")
    print(f"  Traces: {dp_stats['count']}")
    print(f"  Connected components: {dp_stats['components']} (should be 1)")
    print(f"  Endpoints: {dp_stats['endpoints']} (should be 2)")
    if dp_stats["count"] > 0:
        print(f"  X span: {dp_stats['x_span'][0]:.2f} to {dp_stats['x_span'][1]:.2f} mm")

    print(f"\nUSB_D- final state:")
    print(f"  Traces: {dm_stats['count']}")
    print(f"  Connected components: {dm_stats['components']} (should be 1)")
    print(f"  Endpoints: {dm_stats['endpoints']} (should be 2)")
    if dm_stats["count"] > 0:
        print(f"  X span: {dm_stats['x_span'][0]:.2f} to {dm_stats['x_span'][1]:.2f} mm")

    # Save output for inspection
    output_dir = Path("output/instrumented_with_config")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "iteration_1.kicad_pcb"

    try:
        write_routes_to_pcb(
            template_pcb=board_path,
            output_pcb=output_path,
            routes=state.routes,
            vias=state.vias if state.vias else frozenset(),
        )
        print(f"\nOutput saved to: {output_path}")
    except Exception as e:
        print(f"Failed to save output: {e}")

    # Verdict
    if dp_stats["count"] > 0 and dm_stats["count"] > 0:
        if dp_stats["components"] == 1 and dm_stats["components"] == 1:
            print("\n✓ USB traces are continuous!")
            return True
        else:
            print("\n*** USB traces have gaps! ***")
            print("Check the stage deltas above to identify the culprit.")
            return False
    else:
        print("\n*** USB traces were not routed! ***")
        print("Check if differential pair routing is being triggered.")
        return False


if __name__ == "__main__":
    success = run_instrumented_pipeline()
    sys.exit(0 if success else 1)
