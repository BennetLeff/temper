#!/usr/bin/env python3
"""
Deep comparison of failing nets vs reference board routing.

Analyzes /k25, /k02, /k04 and their blockers (/k24, /k15) to understand
how the human-routed reference solved the same constraints.
"""

from collections import defaultdict
from pathlib import Path
import math

from temper_placer.io.kicad_parser import parse_kicad_pcb


def analyze_net_routing(traces: list, vias: list, net_name: str) -> dict:
    """Extract detailed routing info for a specific net."""

    # Filter traces for this net
    net_traces = [t for t in traces if t.net == net_name]
    net_vias = [v for v in vias if v.net == net_name] if vias else []

    if not net_traces:
        return None

    # Calculate bounding box
    all_x = []
    all_y = []
    for t in net_traces:
        all_x.extend([t.start[0], t.end[0]])
        all_y.extend([t.start[1], t.end[1]])

    bbox = {
        "min_x": min(all_x),
        "max_x": max(all_x),
        "min_y": min(all_y),
        "max_y": max(all_y),
    }
    bbox["width"] = bbox["max_x"] - bbox["min_x"]
    bbox["height"] = bbox["max_y"] - bbox["min_y"]
    bbox["center"] = ((bbox["min_x"] + bbox["max_x"]) / 2,
                      (bbox["min_y"] + bbox["max_y"]) / 2)

    # Layer usage
    layers = defaultdict(list)
    for t in net_traces:
        layers[t.layer].append(t)

    # Total length per layer
    layer_lengths = {}
    for layer, layer_traces in layers.items():
        total = sum(
            math.sqrt((t.end[0]-t.start[0])**2 + (t.end[1]-t.start[1])**2)
            for t in layer_traces
        )
        layer_lengths[layer] = total

    # Trace widths used
    widths = set(t.width for t in net_traces)

    # Get all segment endpoints (potential pin locations)
    endpoints = set()
    for t in net_traces:
        endpoints.add(t.start)
        endpoints.add(t.end)

    return {
        "net_name": net_name,
        "segment_count": len(net_traces),
        "via_count": len(net_vias),
        "layers": dict(layers),
        "layer_lengths": layer_lengths,
        "bbox": bbox,
        "trace_widths": widths,
        "endpoints": endpoints,
        "vias": [(v.position, v.size) for v in net_vias] if net_vias else [],
    }


def check_spatial_overlap(net_a: dict, net_b: dict) -> dict:
    """Check if two nets' bounding boxes overlap."""
    if not net_a or not net_b:
        return {"overlaps": False}

    a = net_a["bbox"]
    b = net_b["bbox"]

    # Check overlap
    x_overlap = not (a["max_x"] < b["min_x"] or b["max_x"] < a["min_x"])
    y_overlap = not (a["max_y"] < b["min_y"] or b["max_y"] < a["min_y"])

    overlaps = x_overlap and y_overlap

    # Calculate overlap region if exists
    if overlaps:
        overlap_x = max(0, min(a["max_x"], b["max_x"]) - max(a["min_x"], b["min_x"]))
        overlap_y = max(0, min(a["max_y"], b["max_y"]) - max(a["min_y"], b["min_y"]))
        overlap_area = overlap_x * overlap_y
    else:
        overlap_area = 0

    # Distance between centers
    dist = math.sqrt(
        (a["center"][0] - b["center"][0])**2 +
        (a["center"][1] - b["center"][1])**2
    )

    return {
        "overlaps": overlaps,
        "overlap_area": overlap_area,
        "center_distance": dist,
        "same_layers": bool(set(net_a["layers"].keys()) & set(net_b["layers"].keys())),
        "shared_layers": list(set(net_a["layers"].keys()) & set(net_b["layers"].keys())),
    }


def print_net_analysis(info: dict, label: str = ""):
    """Pretty print net analysis."""
    if not info:
        print(f"  {label}: NOT FOUND IN REFERENCE")
        return

    print(f"\n  {label}{info['net_name']}:")
    print(f"    Segments: {info['segment_count']}")
    print(f"    Vias: {info['via_count']}")
    print(f"    Layers: {list(info['layers'].keys())}")
    for layer, length in info['layer_lengths'].items():
        seg_count = len(info['layers'][layer])
        print(f"      {layer}: {seg_count} segments, {length:.1f}mm")
    print(f"    Bbox: ({info['bbox']['min_x']:.1f}, {info['bbox']['min_y']:.1f}) to ({info['bbox']['max_x']:.1f}, {info['bbox']['max_y']:.1f})")
    print(f"    Bbox size: {info['bbox']['width']:.1f} x {info['bbox']['height']:.1f}mm")
    print(f"    Trace widths: {info['trace_widths']}")
    if info['vias']:
        print(f"    Via positions: {info['vias'][:5]}...")  # First 5


def main():
    ref_path = Path("tests/fixtures/external/.cache/piantor_left/keyboard_pcb.kicad_pcb")

    if not ref_path.exists():
        print(f"ERROR: Reference board not found at {ref_path}")
        return

    print("=" * 70)
    print("REFERENCE BOARD ANALYSIS: Failing Nets & Their Blockers")
    print("=" * 70)

    result = parse_kicad_pcb(ref_path)
    traces = result.traces if result.traces else []
    vias = result.vias if hasattr(result, 'vias') and result.vias else []

    print(f"\nBoard has {len(traces)} trace segments, {len(vias)} vias")

    # Nets to analyze: failures + blockers
    nets_of_interest = {
        "failures": ["/k25", "/k02", "/k04"],
        "blockers": ["/k24", "/k15"],
        "similar": ["/k00", "/k01", "/k03", "/k10", "/k12", "/k14", "/k20", "/k22"],  # Working matrix nets for comparison
    }

    # Analyze each net
    all_analyses = {}

    for category, nets in nets_of_interest.items():
        print(f"\n{'='*70}")
        print(f"CATEGORY: {category.upper()}")
        print("=" * 70)

        for net in nets:
            info = analyze_net_routing(traces, vias, net)
            all_analyses[net] = info
            print_net_analysis(info, f"[{category}] ")

    # Spatial overlap analysis
    print(f"\n{'='*70}")
    print("SPATIAL OVERLAP ANALYSIS")
    print("=" * 70)

    pairs_to_check = [
        ("/k25", "/k24"),  # /k25 blocked by /k24
        ("/k04", "/k15"),  # /k04 blocked by /k15
        ("/k02", "/k00"),  # /k02 vs similar working net
        ("/k02", "/k04"),  # Both failures - related?
    ]

    for net_a, net_b in pairs_to_check:
        info_a = all_analyses.get(net_a)
        info_b = all_analyses.get(net_b)

        if not info_a or not info_b:
            print(f"\n  {net_a} vs {net_b}: Cannot compare (one or both not in reference)")
            continue

        overlap = check_spatial_overlap(info_a, info_b)

        print(f"\n  {net_a} vs {net_b}:")
        print(f"    Bounding boxes overlap: {overlap['overlaps']}")
        print(f"    Overlap area: {overlap['overlap_area']:.1f}mm²")
        print(f"    Center distance: {overlap['center_distance']:.1f}mm")
        print(f"    Share layers: {overlap['same_layers']} {overlap['shared_layers']}")

    # Key insight: How does reference handle overlapping nets?
    print(f"\n{'='*70}")
    print("KEY INSIGHTS")
    print("=" * 70)

    # Check if any failing nets use different layers than blockers
    for failure, blocker in [("/k25", "/k24"), ("/k04", "/k15")]:
        f_info = all_analyses.get(failure)
        b_info = all_analyses.get(blocker)

        if f_info and b_info:
            f_layers = set(f_info["layers"].keys())
            b_layers = set(b_info["layers"].keys())

            print(f"\n  {failure} (blocked by {blocker}):")
            print(f"    Failure layers: {f_layers}")
            print(f"    Blocker layers: {b_layers}")

            if f_layers != b_layers:
                print(f"    → DIFFERENT LAYERS! Reference uses layer separation")
            elif f_info["via_count"] > 0 or b_info["via_count"] > 0:
                print(f"    → Uses vias: {failure}={f_info['via_count']}, {blocker}={b_info['via_count']}")
            else:
                print(f"    → Same layer, no vias - check routing paths")

    # Summary statistics for all keyboard matrix nets
    print(f"\n{'='*70}")
    print("KEYBOARD MATRIX NET SUMMARY")
    print("=" * 70)

    matrix_nets = [n for n in all_analyses.keys() if n.startswith("/k")]

    layer_usage = defaultdict(int)
    via_usage = []

    for net in matrix_nets:
        info = all_analyses.get(net)
        if info:
            for layer in info["layers"].keys():
                layer_usage[layer] += 1
            via_usage.append((net, info["via_count"]))

    print(f"\n  Layer usage across {len(matrix_nets)} matrix nets:")
    for layer, count in sorted(layer_usage.items()):
        print(f"    {layer}: {count} nets")

    print(f"\n  Via usage:")
    with_vias = [(n, v) for n, v in via_usage if v > 0]
    without_vias = [(n, v) for n, v in via_usage if v == 0]
    print(f"    Nets with vias: {len(with_vias)}")
    print(f"    Nets without vias: {len(without_vias)}")
    if with_vias:
        print(f"    Via counts: {with_vias}")


if __name__ == "__main__":
    main()
