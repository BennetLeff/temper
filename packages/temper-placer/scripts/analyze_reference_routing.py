#!/usr/bin/env python3
"""
Compare reference board routing to Router V6 output.

Usage:
    python scripts/analyze_reference_routing.py
"""

from collections import defaultdict
from pathlib import Path

from temper_placer.io.kicad_parser import parse_kicad_pcb


def analyze_board(board_path: Path, label: str) -> dict:
    """Extract routing statistics from a board."""
    print(f"\n{'='*60}")
    print(f"Analyzing: {label}")
    print(f"Path: {board_path}")
    print('='*60)

    result = parse_kicad_pcb(board_path)

    # Access the right attributes from ParseResult
    traces = result.traces if result.traces else []
    vias = result.vias if hasattr(result, 'vias') and result.vias else []
    nets = result.netlist.nets if result.netlist else []

    # Basic counts
    stats = {
        "label": label,
        "trace_count": len(traces),
        "via_count": len(vias),
        "net_count": len(nets),
    }

    # Per-layer trace distribution
    layer_traces = defaultdict(list)
    layer_length = defaultdict(float)

    for trace in traces:
        layer_traces[trace.layer].append(trace)
        # Calculate segment length
        dx = trace.end[0] - trace.start[0]
        dy = trace.end[1] - trace.start[1]
        length = (dx**2 + dy**2)**0.5
        layer_length[trace.layer] += length

    print(f"\nLayer Distribution:")
    for layer, traces in sorted(layer_traces.items()):
        length = layer_length[layer]
        print(f"  {layer}: {len(traces)} segments, {length:.1f}mm total")

    stats["layer_distribution"] = dict(layer_traces)
    stats["layer_length"] = dict(layer_length)

    # Per-net trace count
    net_traces = defaultdict(list)
    for trace in traces:
        if trace.net:
            net_traces[trace.net].append(trace)

    print(f"\nTop 10 Nets by Segment Count:")
    sorted_nets = sorted(net_traces.items(), key=lambda x: -len(x[1]))[:10]
    for net_name, traces in sorted_nets:
        layers = set(t.layer for t in traces)
        print(f"  {net_name}: {len(traces)} segments on {layers}")

    stats["net_traces"] = {k: len(v) for k, v in net_traces.items()}

    # Via distribution by net
    if vias:
        net_vias = defaultdict(list)
        for via in vias:
            if via.net:
                net_vias[via.net].append(via)

        print(f"\nVia Usage by Net (top 10):")
        sorted_via_nets = sorted(net_vias.items(), key=lambda x: -len(x[1]))[:10]
        for net_name, vias in sorted_via_nets:
            print(f"  {net_name}: {len(vias)} vias")

        stats["net_vias"] = {k: len(v) for k, v in net_vias.items()}

    # Analyze the 8 failing nets specifically
    failing_nets = [
        "/k25", "/k02", "/k04",
        "unconnected-(U2-Pad31)", "unconnected-(U2-Pad35)", "unconnected-(U2-Pad37)",
        "vbus_sense", "GND"
    ]

    print(f"\n{'='*60}")
    print("FAILING NET ANALYSIS")
    print('='*60)

    for net_name in failing_nets:
        traces = net_traces.get(net_name, [])
        if not traces:
            # Try partial match
            for key in net_traces:
                if net_name in key or key in net_name:
                    traces = net_traces[key]
                    net_name = key
                    break

        if traces:
            layers = set(t.layer for t in traces)
            total_length = sum(
                ((t.end[0]-t.start[0])**2 + (t.end[1]-t.start[1])**2)**0.5
                for t in traces
            )

            # Get bounding box
            all_x = [t.start[0] for t in traces] + [t.end[0] for t in traces]
            all_y = [t.start[1] for t in traces] + [t.end[1] for t in traces]
            bbox = (min(all_x), min(all_y), max(all_x), max(all_y))

            via_count = len([v for v in (vias or []) if v.net == net_name])

            print(f"\n{net_name}:")
            print(f"  Segments: {len(traces)}")
            print(f"  Layers: {layers}")
            print(f"  Total length: {total_length:.1f}mm")
            print(f"  Vias: {via_count}")
            print(f"  Bounding box: ({bbox[0]:.1f}, {bbox[1]:.1f}) to ({bbox[2]:.1f}, {bbox[3]:.1f})")
        else:
            print(f"\n{net_name}: NOT FOUND in reference board")

    return stats


def compare_boards(ref_stats: dict, gen_stats: dict):
    """Compare reference and generated routing statistics."""
    print(f"\n{'='*60}")
    print("COMPARISON: Reference vs Generated")
    print('='*60)

    print(f"\n{'Metric':<30} {'Reference':>15} {'Generated':>15} {'Delta':>15}")
    print("-" * 75)

    metrics = [
        ("Total Traces", "trace_count"),
        ("Total Vias", "via_count"),
        ("Nets Defined", "net_count"),
    ]

    for label, key in metrics:
        ref_val = ref_stats.get(key, 0)
        gen_val = gen_stats.get(key, 0)
        delta = gen_val - ref_val
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        print(f"{label:<30} {ref_val:>15} {gen_val:>15} {delta_str:>15}")

    # Layer comparison
    print(f"\n{'Layer':<20} {'Ref Segments':>15} {'Ref Length':>15}")
    print("-" * 50)
    for layer in sorted(ref_stats.get("layer_length", {}).keys()):
        segs = len(ref_stats.get("layer_distribution", {}).get(layer, []))
        length = ref_stats.get("layer_length", {}).get(layer, 0)
        print(f"{layer:<20} {segs:>15} {length:>15.1f}mm")


def main():
    # Paths
    ref_path = Path("tests/fixtures/external/.cache/piantor_left/keyboard_pcb.kicad_pcb")

    if not ref_path.exists():
        print(f"ERROR: Reference board not found at {ref_path}")
        print("Run: python -m temper_placer.fixtures.download_external_boards")
        return

    # Analyze reference
    ref_stats = analyze_board(ref_path, "Reference (Human-Routed)")

    # If we have a generated board, analyze it too
    gen_path = Path("output/piantor_routed.kicad_pcb")
    if gen_path.exists():
        gen_stats = analyze_board(gen_path, "Generated (Router V6)")
        compare_boards(ref_stats, gen_stats)
    else:
        print(f"\nNote: No generated board found at {gen_path}")
        print("Run the router and export to compare.")


if __name__ == "__main__":
    main()
