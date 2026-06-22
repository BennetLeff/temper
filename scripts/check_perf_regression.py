#!/usr/bin/env python3
# NOTE: This script covers loss-function execution time regression
# (microbenchmarks). For placement quality regression (wirelength, overlap,
# boundary), use the corpus regression runner instead:
#   python3 -m temper_placer.regression.cli run-corpus
#
# See packages/temper-placer/src/temper_placer/regression/corpus_runner.py
# and power_pcb_dataset/corpus/ for the multi-board optimization regression.
import sys
import json
import argparse
import os
from pathlib import Path
from rich.console import Console

# Add package source to path
package_dir = Path(__file__).resolve().parent.parent / "packages" / "temper-placer" / "src"
if str(package_dir) not in sys.path:
    sys.path.append(str(package_dir))

from temper_placer.io.config_loader import load_constraints, create_board_from_constraints
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.losses.base import LossContext, CompositeLoss, WeightedLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.regularization import SpreadLoss
import jax

def main():
    parser = argparse.ArgumentParser(description="Check for performance regression")
    parser.add_argument("--baseline", type=Path, default="metrics/performance_baseline.json")
    parser.add_argument("--pcb", type=Path, default="pcb/temper.kicad_pcb")
    parser.add_argument("-c", "--config", type=Path, default="packages/temper-placer/configs/temper_constraints.yaml")
    parser.add_argument("--iterations", type=int, default=10)
    
    args = parser.parse_args()
    console = Console()
    
    if not args.baseline.exists():
        console.print(f"[red]Baseline not found: {args.baseline}[/]")
        sys.exit(1)
        
    with open(args.baseline) as f:
        baseline = json.load(f)
        
    # Setup
    parse_result = parse_kicad_pcb(args.pcb)
    netlist = parse_result.netlist
    constraints = load_constraints(args.config)
    board = create_board_from_constraints(constraints)
    
    composite = CompositeLoss([
        WeightedLoss(OverlapLoss(), weight=100.0),
        WeightedLoss(WirelengthLoss(), weight=1.0),
        WeightedLoss(BoundaryLoss(), weight=50.0),
        WeightedLoss(SpreadLoss(), weight=5.0),
    ])
    context = LossContext.from_netlist_and_board(netlist, board)
    
    rng = jax.random.PRNGKey(42)
    positions = jax.random.uniform(rng, (netlist.n_components, 2)) * 100.0
    rotations = jax.random.uniform(rng, (netlist.n_components, 4))
    vn = jax.random.uniform(rng, (netlist.n_nets, 2)) * 100.0
    
    # Warmup
    composite(positions, rotations, context, net_virtual_nodes=vn)
    
    # Measure
    all_times = []
    for _ in range(args.iterations):
        timings = composite.record_timings(positions, rotations, context, net_virtual_nodes=vn)
        all_times.append(timings)
        
    # Check
    failures = []
    results_table = []
    
    for loss_name, spec in baseline["metrics"].items():
        if loss_name == "total_step_ms":
            actual = sum(sum(t.values()) for t in all_times) / args.iterations
        else:
            actual = sum(t[loss_name] for t in all_times) / args.iterations
            
        target = spec["mean_ms"]
        margin = spec["margin_rel"]
        limit = target * (1 + margin)
        
        passed = actual <= limit
        status = "✅ PASS" if passed else "❌ FAIL"
        if not passed:
            failures.append(loss_name)
            
        results_table.append({
            "name": loss_name,
            "actual": actual,
            "target": target,
            "margin": margin,
            "status": status
        })

    # Report
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a") as f:
            f.write("\n## Performance Regression Check Results\n\n")
            f.write("| Loss Function | Target (ms) | Actual (ms) | Margin | Status |\n")
            f.write("| --- | --- | --- | --- | --- |\n")
            for res in results_table:
                f.write(f"| {res['name']} | {res['target']:.2f} | {res['actual']:.2f} | {res['margin']*100:.0f}% | {res['status']} |\n")
            
    if failures:
        console.print(f"[bold red]PERFORMANCE REGRESSION DETECTED: {', '.join(failures)}[/]")
        sys.exit(1)
    else:
        console.print("[bold green]PERFORMANCE VERIFIED[/]")
        sys.exit(0)

if __name__ == "__main__":
    main()
