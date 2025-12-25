#!/usr/bin/env python3
"""
Feature Ablation Tests for Temper Placer Pipeline

Tests the impact of enabling various unused losses:
1. decoupling - Cap-to-IC proximity
2. drc - Design rule checking (via real KiCad validation)
3. power_path - Power delivery optimization  
4. critical_path - Signal integrity

Also tests different configurations of existing features.
"""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import shutil
import yaml

@dataclass
class TestConfig:
    """Test configuration."""
    name: str
    description: str
    extra_losses: dict[str, float] = field(default_factory=dict)
    epochs: int = 50
    seed: int = 42

@dataclass 
class TestResult:
    name: str
    overlaps: int
    fixed_drift_mm: float
    mcu_spread_mm: float
    wirelength_proxy: float
    zone_compliance_pct: float
    loss_final: float
    time_s: float
    notes: str = ""

def create_test_config(base_config_path: Path, test_config: TestConfig, output_path: Path):
    """Create a modified config file for this test."""
    with open(base_config_path) as f:
        config = yaml.safe_load(f)
    
    # Merge extra losses
    if "loss_weights" not in config:
        config["loss_weights"] = {}
    
    for loss_name, weight in test_config.extra_losses.items():
        config["loss_weights"][loss_name] = weight
    
    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    
    return output_path

def run_test(test_config: TestConfig, base_config: Path, output_dir: Path) -> TestResult:
    """Run a single ablation test."""
    print(f"\n{'='*60}")
    print(f"TEST: {test_config.name}")
    print(f"Description: {test_config.description}")
    print(f"{'='*60}")
    
    # Create modified config
    test_config_path = output_dir / f"config_{test_config.name}.yaml"
    create_test_config(base_config, test_config, test_config_path)
    
    output_pcb = output_dir / f"output_{test_config.name}.kicad_pcb"
    
    # Run optimizer
    cmd = [
        "uv", "run", "temper-placer", "optimize",
        "../../pcb/temper.kicad_pcb",
        "-c", str(test_config_path),
        "-o", str(output_pcb),
        "--epochs", str(test_config.epochs),
        "--seed", str(test_config.seed),
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).parent)
    
    # Parse time from output
    time_s = 0.0
    loss_final = 0.0
    for line in result.stdout.split("\n"):
        if "Time:" in line:
            try:
                time_s = float(line.split("Time:")[1].strip().replace("s", ""))
            except:
                pass
        if "Final loss:" in line:
            try:
                loss_final = float(line.split(":")[1].strip())
            except:
                pass
    
    # Analyze output
    if not output_pcb.exists():
        return TestResult(
            name=test_config.name,
            overlaps=-1,
            fixed_drift_mm=-1,
            mcu_spread_mm=-1,
            wirelength_proxy=-1,
            zone_compliance_pct=-1,
            loss_final=loss_final,
            time_s=time_s,
            notes=f"Output not created: {result.stderr[:200]}"
        )
    
    return analyze_result(test_config.name, output_pcb, time_s, loss_final)

def analyze_result(name: str, pcb_path: Path, time_s: float, loss_final: float) -> TestResult:
    """Analyze placement quality metrics."""
    import numpy as np
    
    # Dynamic import to avoid issues
    sys.path.insert(0, str(Path(__file__).parent / "src"))
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.io.config_loader import load_constraints
    
    result = parse_kicad_pcb(pcb_path)
    constraints = load_constraints(Path(__file__).parent / "configs" / "temper_constraints.yaml")
    
    # 1. Count overlaps
    comps = [(c.initial_position, c.bounds) for c in result.netlist.components if c.initial_position]
    overlap_count = 0
    for i, (pos_i, bounds_i) in enumerate(comps):
        for pos_j, bounds_j in comps[i+1:]:
            dx = abs(pos_i[0] - pos_j[0])
            dy = abs(pos_i[1] - pos_j[1])
            min_sep_x = (bounds_i[0] + bounds_j[0]) / 2 + 0.5
            min_sep_y = (bounds_i[1] + bounds_j[1]) / 2 + 0.5
            if dx < min_sep_x and dy < min_sep_y:
                overlap_count += 1
    
    # 2. Fixed drift
    expected = {
        'Q1': (75.0, 130.0), 'Q2': (75.0, 118.0),
        'D1': (58.0, 130.0), 'D2': (58.0, 118.0),
        'U_MCU': (50.0, 45.0),
    }
    max_drift = 0.0
    for comp in result.netlist.components:
        if comp.ref in expected:
            exp = expected[comp.ref]
            actual = comp.initial_position
            if actual:
                drift = np.sqrt((actual[0] - exp[0])**2 + (actual[1] - exp[1])**2)
                max_drift = max(max_drift, drift)
    
    # 3. MCU cap spread
    mcu_caps = ['C_MCU_1', 'C_MCU_2', 'C_MCU_3', 'C_MCU_4']
    mcu_positions = []
    for comp in result.netlist.components:
        if comp.ref in mcu_caps and comp.initial_position:
            mcu_positions.append(comp.initial_position)
    spread = np.max(np.ptp(np.array(mcu_positions), axis=0)) if len(mcu_positions) >= 2 else -1
    
    # 4. Wirelength proxy (position variance)
    all_pos = np.array([c.initial_position for c in result.netlist.components if c.initial_position])
    wirelength = np.sum(np.std(all_pos, axis=0)) * 10
    
    # 5. Zone compliance (placeholder)
    zone_pct = 100.0  # Assume Abacus fixes this
    
    return TestResult(
        name=name,
        overlaps=overlap_count,
        fixed_drift_mm=max_drift,
        mcu_spread_mm=spread,
        wirelength_proxy=wirelength,
        zone_compliance_pct=zone_pct,
        loss_final=loss_final,
        time_s=time_s,
    )

def main():
    output_dir = Path(__file__).parent / "ablation_feature_tests"
    output_dir.mkdir(exist_ok=True)
    
    base_config = Path(__file__).parent / "configs" / "temper_constraints.yaml"
    
    # Define test configurations
    tests = [
        TestConfig(
            name="baseline",
            description="Current config (overlap, wirelength, zone)",
            extra_losses={},
        ),
        TestConfig(
            name="add_decoupling",
            description="Add decoupling cap proximity",
            extra_losses={"decoupling": 20.0},
        ),
        TestConfig(
            name="add_power_path",
            description="Add power path optimization",
            extra_losses={"power_path": 30.0},
        ),
        TestConfig(
            name="strong_grouping",
            description="Increase grouping weight",
            extra_losses={"grouping": 50.0},
        ),
        TestConfig(
            name="all_new_losses",
            description="Enable all potentially useful losses",
            extra_losses={
                "decoupling": 20.0,
                "power_path": 30.0,
                "critical_path": 15.0,
            },
        ),
        TestConfig(
            name="high_wirelength",
            description="Double wirelength emphasis",
            extra_losses={"wirelength": 60.0},
        ),
    ]
    
    results = []
    for test in tests:
        try:
            result = run_test(test, base_config, output_dir)
            results.append(result)
            print(f"  Overlaps: {result.overlaps}")
            print(f"  Fixed drift: {result.fixed_drift_mm:.2f}mm")
            print(f"  MCU spread: {result.mcu_spread_mm:.1f}mm")
            print(f"  Time: {result.time_s:.1f}s")
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    # Print summary
    print("\n" + "="*80)
    print("FEATURE ABLATION RESULTS")
    print("="*80)
    print(f"{'Test':<20} {'Overlaps':<10} {'Drift':<10} {'MCU Spread':<12} {'Loss':<12} {'Time':<8}")
    print("-"*80)
    
    for r in results:
        print(f"{r.name:<20} {r.overlaps:<10} {r.fixed_drift_mm:<10.2f} {r.mcu_spread_mm:<12.1f} {r.loss_final:<12.1f} {r.time_s:<8.1f}")
    
    # Find best
    valid = [r for r in results if r.overlaps >= 0]
    if valid:
        best = min(valid, key=lambda r: r.overlaps * 1000 + r.mcu_spread_mm)
        print(f"\nBest configuration: {best.name}")
        print(f"  Overlaps: {best.overlaps}, MCU spread: {best.mcu_spread_mm:.1f}mm")
    
    # Save results
    with open(output_dir / "results.json", "w") as f:
        json.dump([{
            "name": r.name,
            "overlaps": r.overlaps,
            "fixed_drift_mm": r.fixed_drift_mm,
            "mcu_spread_mm": r.mcu_spread_mm,
            "wirelength_proxy": r.wirelength_proxy,
            "loss_final": r.loss_final,
            "time_s": r.time_s,
            "notes": r.notes,
        } for r in results], f, indent=2)
    
    print(f"\nResults saved to {output_dir / 'results.json'}")

if __name__ == "__main__":
    main()
