#!/usr/bin/env python3
"""
Analysis script to correlate Steiner/HPWL estimations with actual routed trace lengths.
Part of temper-eao.

Usage:
    uv run --package temper-placer python3 scripts/analyze_steiner_correlation.py [path/to/board.kicad_pcb]
"""

import argparse
import sys
from pathlib import Path
from dataclasses import dataclass
import math

import numpy as np
from scipy import stats

from temper_placer.io.kicad_parser import parse_kicad_pcb, TraceData

@dataclass
class NetMetrics:
    name: str
    pin_count: int
    routed_length_mm: float
    hpwl_mm: float
    steiner_est_mm: float

def calculate_routed_length(traces: list[TraceData], net_name: str) -> float:
    """Calculate total length of all trace segments for a given net."""
    length = 0.0
    for trace in traces:
        if trace.net == net_name:
            dx = trace.end[0] - trace.start[0]
            dy = trace.end[1] - trace.start[1]
            segment_len = math.sqrt(dx*dx + dy*dy)
            length += segment_len
    return length

def calculate_hpwl(pins: list[tuple[float, float]]) -> float:
    """Calculate Half-Perimeter Wirelength (HPWL)."""
    if not pins:
        return 0.0
    
    xs = [p[0] for p in pins]
    ys = [p[1] for p in pins]
    
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    
    return width + height

def estimate_steiner(hpwl: float, pin_count: int) -> float:
    """
    Estimate Steiner Tree length using a correction factor on HPWL.
    
    RSMT ≈ HPWL * (1.0 + 0.1 * log2(n_pins - 1)) for n_pins > 2 (Empirical)
    """
    if pin_count <= 2:
        return hpwl
        
    # Empirical correction similar to what is used in the loss function
    # Note: Using base e or 2 depends on the specific heuristic, 
    # but the idea is it grows slowly with pin count.
    # WirelengthLoss uses: (1.0 + beta * log(n - 1))
    correction = 1.0 + 0.1 * math.log2(pin_count - 1)
    return hpwl * correction

def analyze_board(pcb_path: Path) -> None:
    print(f"Analyzing {pcb_path}...")
    
    try:
        result = parse_kicad_pcb(pcb_path)
    except Exception as e:
        print(f"Error parsing PCB: {e}")
        return

    if not result.traces:
        print("Warning: No traces found in file. Ensure it is a fully routed board.")
        return

    netlist = result.netlist
    
    # Map net names to pin positions
    net_pins: dict[str, list[tuple[float, float]]] = {}
    
    # We need absolute positions of pins. 
    # parse_kicad_pcb normalizes components to board origin.
    # But TraceData is absolute. 
    # Let's check kicad_parser.py again.
    # _extract_traces_from_pcb returns raw coordinates from kiutils.
    # _extract_components_from_pcb subtracts board origin.
    # We need to be careful with coordinates if we want to visualize, 
    # but for HPWL, relative vs absolute doesn't matter as long as consistent.
    # However, trace lengths are absolute distance, so that's fine.
    # Pin positions for HPWL must match scale.
    # The components have 'initial_position' which is normalized.
    # We should add board origin back to component positions to match traces?
    # Or just calc HPWL on normalized positions (width/height is same).
    # YES, HPWL is translation invariant.
    
    # Build net_pins map
    for comp in netlist.components:
        cx, cy = comp.initial_position
        # We need to account for rotation...
        # Component.pins has relative positions (offsets).
        
        # Simple rotation application
        # 0: 0, 1: 90, 2: 180, 3: 270 (approx)
        # Assuming CCW
        rad = comp.initial_rotation * (math.pi / 2.0)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)
        
        for pin in comp.pins:
            if not pin.net:
                continue
                
            # Rotate pin offset
            ox = pin.position[0]
            oy = pin.position[1]
            
            rx = ox * cos_a - oy * sin_a
            ry = ox * sin_a + oy * cos_a
            
            # Absolute-ish position (normalized to board origin)
            px = cx + rx
            py = cy + ry
            
            if pin.net not in net_pins:
                net_pins[pin.net] = []
            net_pins[pin.net].append((px, py))

    # Collect metrics
    metrics: list[NetMetrics] = []
    
    skip_nets = {"GND", "PGND", "CGND", "+3V3", "+5V", "+15V", "VCC_BOOT"} # Skip power planes usually
    
    for net in netlist.nets:
        name = net.name
        
        # Get routed length from all segments
        routed_len = calculate_routed_length(result.traces, name)
        
        # If not routed (or minimal), skip analysis for this net
        if routed_len < 0.1:
            continue
            
        pins = net_pins.get(name, [])
        if len(pins) < 2:
            continue
        
        if name in skip_nets:
            continue
            
        hpwl = calculate_hpwl(pins)
        steiner = estimate_steiner(hpwl, len(pins))
        
        metrics.append(NetMetrics(
            name=name,
            pin_count=len(pins),
            routed_length_mm=routed_len,
            hpwl_mm=hpwl,
            steiner_est_mm=steiner
        ))
        
    if not metrics:
        print("No significant signal nets found to analyze.")
        return

    print("\n" + "="*50)
    print(f"Analysis Results for {pcb_path.name}")
    print("="*50)
    print(f"Nets Analyzed: {len(metrics)}")
    
    # Statistics
    routed = np.array([m.routed_length_mm for m in metrics])
    params = np.array([m.steiner_est_mm for m in metrics])
    hpwls = np.array([m.hpwl_mm for m in metrics])
    
    if len(metrics) > 1:
        # Correlation for Steiner
        pearson_r, _ = stats.pearsonr(params, routed)
        spearman_r, _ = stats.spearmanr(params, routed)
        
        # Correlation for HPWL
        pearson_hpwl, _ = stats.pearsonr(hpwls, routed)
        
        print("-" * 30)
        print(f"Correlation (Steiner Estimate vs Actual):")
        print(f"  Pearson r:  {pearson_r:.4f} (Linear correlation)")
        print(f"  Spearman r: {spearman_r:.4f} (Rank correlation)")
        print("-" * 30)
        print(f"Correlation (HPWL vs Actual):")
        print(f"  Pearson r:  {pearson_hpwl:.4f}")
    else:
        print("-" * 30)
        print("Not enough nets for correlation analysis (< 2).")

    # Ratio analysis
    ratios = routed / params
    avg_ratio = np.mean(ratios)
    median_ratio = np.median(ratios)
    
    print("-" * 30)
    print(f"Route Quality (Efficiency):")
    print(f"  Avg Ratio (Routed / Est):    {avg_ratio:.2f}")
    print(f"  Median Ratio (Routed / Est): {median_ratio:.2f}")
    print(f"  (Closer to 1.0 means closer to ideal Steiner tree)")
    print("-" * 30)
    print("Outliers (Largest Ratio - Least Efficient Routes):")
    
    # Sort by ratio descending
    sorted_metrics = sorted(metrics, key=lambda m: m.routed_length_mm / m.steiner_est_mm, reverse=True)
    
    print(f"{'Net Name':<20} | {'Pins':<4} | {'Routed':<8} | {'Est':<8} | {'Ratio':<6}")
    print("-" * 60)
    for m in sorted_metrics[:5]:
        ratio = m.routed_length_mm / m.steiner_est_mm
        print(f"{m.name:<20} | {m.pin_count:<4} | {m.routed_length_mm:6.1f}mm | {m.steiner_est_mm:6.1f}mm | {ratio:.2f}x")
        
    if len(metrics) > 5:
        print("\nBest Routes (Most Efficient):")
        for m in sorted_metrics[-5:]:
            ratio = m.routed_length_mm / m.steiner_est_mm
            print(f"{m.name:<20} | {m.pin_count:<4} | {m.routed_length_mm:6.1f}mm | {m.steiner_est_mm:6.1f}mm | {ratio:.2f}x")

def main():
    parser = argparse.ArgumentParser(description="Analyze Steiner vs Routed Length Correlation")
    parser.add_argument("pcb_files", nargs="+", type=Path, help="KiCad PCB files to analyze")
    args = parser.parse_args()
    
    for pcb in args.pcb_files:
        analyze_board(pcb)

if __name__ == "__main__":
    main()
