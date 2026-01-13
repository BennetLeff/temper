#!/usr/bin/env python3
"""
Ablation Tests for Temper Placer Pipeline

This script runs systematic tests to determine which parts of the
placement pipeline contribute to good outcomes.

Tests:
1. Heuristics only (minimal epochs)
2. Optimizer only (no heuristics)
3. Full pipeline
4. Different loss combinations
5. Fixed positions vs free placement

Metrics measured:
- Fixed component drift (should be 0 for fixed)
- Overlap count
- Total wirelength (HPWL)
- Zone compliance (% in correct zone)
- Component group spread
"""

import json
from pathlib import Path
from dataclasses import dataclass
import subprocess
import sys

@dataclass
class TestResult:
    name: str
    fixed_drift_mm: float  # Max drift of fixed components
    overlap_count: int
    wirelength_mm: float
    zone_compliance_pct: float
    group_spread_mm: float
    notes: str = ""

def run_optimizer(name: str, epochs: int, heuristics: bool = True, 
                  no_auto_group: bool = False, seed: int = 42) -> str:
    """Run optimizer with specified settings and return output path."""
    output_path = f"ablation_{name}.kicad_pcb"
    
    cmd = [
        "uv", "run", "temper-placer", "optimize",
        "../../pcb/temper.kicad_pcb",
        "-c", "configs/temper_constraints.yaml",
        "-o", output_path,
        "--epochs", str(epochs),
        "--seed", str(seed),
    ]
    
    if not heuristics:
        cmd.append("--no-heuristics")
    
    if no_auto_group:
        cmd.append("--no-auto-group")
    
    print(f"\n{'='*60}")
    print(f"Running: {name}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).parent)
    
    if result.returncode != 0:
        print(f"ERROR: {result.stderr}")
        return None
    
    print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
    
    return output_path

def analyze_placement(output_path: str, test_name: str) -> TestResult:
    """Analyze placement quality metrics."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.config_loader import load_constraints
    import numpy as np
    
    if not Path(output_path).exists():
        return TestResult(
            name=test_name,
            fixed_drift_mm=-1,
            overlap_count=-1,
            wirelength_mm=-1,
            zone_compliance_pct=-1,
            group_spread_mm=-1,
            notes="Output file not created"
        )
    
    result = parse_kicad_pcb(Path(output_path))
    constraints = load_constraints(Path("configs/temper_constraints.yaml"))
    
    # 1. Check fixed component drift
    expected_fixed = {
        'Q1': (75.0, 130.0),
        'Q2': (75.0, 118.0),
        'D1': (58.0, 130.0),
        'D2': (58.0, 118.0),
        'C_BUS1': (89.0, 130.0),
        'C_BUS2': (89.0, 118.0),
        'U_GATE': (40.0, 124.0),
    }
    
    max_drift = 0.0
    for comp in result.netlist.components:
        if comp.ref in expected_fixed:
            exp = expected_fixed[comp.ref]
            actual = comp.initial_position
            if actual:
                drift = np.sqrt((actual[0] - exp[0])**2 + (actual[1] - exp[1])**2)
                max_drift = max(max_drift, drift)
    
    # 2. Count overlaps
    positions = np.array([c.initial_position for c in result.netlist.components if c.initial_position])
    bounds = np.array([c.bounds for c in result.netlist.components if c.initial_position])
    
    overlap_count = 0
    n = len(positions)
    for i in range(n):
        for j in range(i+1, n):
            dx = abs(positions[i, 0] - positions[j, 0])
            dy = abs(positions[i, 1] - positions[j, 1])
            min_sep_x = (bounds[i, 0] + bounds[j, 0]) / 2 + 0.5
            min_sep_y = (bounds[i, 1] + bounds[j, 1]) / 2 + 0.5
            if dx < min_sep_x and dy < min_sep_y:
                overlap_count += 1
    
    # 3. Estimate wirelength (sum of distances between connected components)
    # Simplified: use position spread as proxy
    wirelength = np.sum(np.std(positions, axis=0)) * 10  # Rough proxy
    
    # 4. Zone compliance
    zone_assignments = {
        'Q1': 'power_zone', 'Q2': 'power_zone', 'D1': 'power_zone',
        'U_MCU': 'control_zone', 'U_LDO_3V3': 'control_zone',
    }
    in_zone = 0
    total_assigned = 0
    for comp in result.netlist.components:
        if comp.ref in zone_assignments:
            total_assigned += 1
            pos = comp.initial_position
            if pos:
                # Check if in expected zone
                zone_name = zone_assignments[comp.ref]
                for zone in constraints.zones:
                    if zone.name == zone_name:
                        x1, y1, x2, y2 = zone.bounds
                        if x1 <= pos[0] <= x2 and y1 <= pos[1] <= y2:
                            in_zone += 1
                        break
    
    zone_pct = (in_zone / total_assigned * 100) if total_assigned > 0 else 0
    
    # 5. Component group spread (MCU decoupling as example)
    mcu_caps = ['C_MCU_1', 'C_MCU_2', 'C_MCU_3', 'C_MCU_4']
    mcu_positions = []
    for comp in result.netlist.components:
        if comp.ref in mcu_caps and comp.initial_position:
            mcu_positions.append(comp.initial_position)
    
    if len(mcu_positions) >= 2:
        mcu_positions = np.array(mcu_positions)
        spread = np.max(np.ptp(mcu_positions, axis=0))
    else:
        spread = -1
    
    return TestResult(
        name=test_name,
        fixed_drift_mm=max_drift,
        overlap_count=overlap_count,
        wirelength_mm=wirelength,
        zone_compliance_pct=zone_pct,
        group_spread_mm=spread,
    )

def main():
    results = []
    
    # Test 1: Minimal epochs (heuristics + quick optimizer)
    output = run_optimizer("minimal_5ep", epochs=5, heuristics=True)
    if output:
        results.append(analyze_placement(output, "Minimal (5 epochs)"))
    
    # Test 2: Heuristics + more epochs
    output = run_optimizer("medium_50ep", epochs=50, heuristics=True)
    if output:
        results.append(analyze_placement(output, "Medium (50 epochs)"))
    
    # Test 3: No heuristics, optimizer only
    output = run_optimizer("optimizer_only", epochs=100, heuristics=False)
    if output:
        results.append(analyze_placement(output, "Optimizer Only (100 ep)"))
    
    # Test 4: Heuristics only (very few epochs)
    output = run_optimizer("heuristics_focus", epochs=1, heuristics=True)
    if output:
        results.append(analyze_placement(output, "Heuristics Focus (1 ep)"))
    
    # Test 5: Full pipeline
    output = run_optimizer("full_300ep", epochs=300, heuristics=True)
    if output:
        results.append(analyze_placement(output, "Full (300 epochs)"))
    
    # Print summary
    print("\n" + "="*80)
    print("ABLATION TEST RESULTS")
    print("="*80)
    print(f"{'Test Name':<25} {'Fixed Drift':<12} {'Overlaps':<10} {'Zone %':<10} {'MCU Spread':<12}")
    print("-"*80)
    
    for r in results:
        print(f"{r.name:<25} {r.fixed_drift_mm:>8.2f}mm   {r.overlap_count:>6}     {r.zone_compliance_pct:>6.1f}%    {r.group_spread_mm:>8.1f}mm")
        if r.notes:
            print(f"  Notes: {r.notes}")
    
    # Save results
    with open("ablation_results.json", "w") as f:
        json.dump([{
            "name": r.name,
            "fixed_drift_mm": r.fixed_drift_mm,
            "overlap_count": r.overlap_count,
            "wirelength_mm": r.wirelength_mm,
            "zone_compliance_pct": r.zone_compliance_pct,
            "group_spread_mm": r.group_spread_mm,
            "notes": r.notes,
        } for r in results], f, indent=2)
    
    print("\nResults saved to ablation_results.json")
    
    # Print recommendation
    print("\n" + "="*80)
    print("RECOMMENDATIONS")
    print("="*80)
    
    if results:
        best = min(results, key=lambda r: r.fixed_drift_mm + r.overlap_count * 10)
        print(f"Best configuration: {best.name}")
        print(f"  - Fixed component drift: {best.fixed_drift_mm:.2f}mm (target: 0)")
        print(f"  - Overlaps: {best.overlap_count} (target: 0)")
        print(f"  - Zone compliance: {best.zone_compliance_pct:.1f}%")
        print(f"  - MCU cap spread: {best.group_spread_mm:.1f}mm (target: <15mm)")

if __name__ == "__main__":
    main()
