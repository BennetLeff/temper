#!/usr/bin/env python3
# DEPRECATED: Use `python3 -m temper_placer.regression.cli run-corpus` instead.
# This script is kept for reference but will be removed after the corpus
# regression runner is validated in CI for 2 weeks.
#
# The corpus runner (packages/temper-placer/src/temper_placer/regression/
# corpus_runner.py) provides multi-board optimization regression, per-metric
# threshold comparison, JSON reporting, and CI integration.
import sys
import json
import argparse
from pathlib import Path
import statistics
import jax
from rich.console import Console
from rich.table import Table

# Add scripts dir to path to allow importing from benchmark_baselines
scripts_dir = Path(__file__).resolve().parent
if str(scripts_dir) not in sys.path:
    sys.path.append(str(scripts_dir))

from benchmark_baselines import (
    run_trial, create_standard_loss, aggregate_results, OptimizerConfig,
    GradNormConfig, EarlyStoppingConfig, create_default_pipeline,
    PlacementState, load_constraints, create_board_from_constraints,
    parse_kicad_pcb, LossContext
)

console = Console()

def check_metric(name, actual, baseline):
    """
    Check if metric is within allowed margin.
    Returns (passed, message)
    """
    target = baseline["mean"]
    # margin_rel: relative tolerance (e.g. 0.1 for 10%)
    # margin_abs: absolute tolerance
    # We use the larger allowed deviation of the two
    
    # For loss/epochs/hpwl, LOWER is usually better or we want to stay within range.
    # Strictly speaking for regression, "degrading" means getting HIGHER (worse).
    # If we get LOWER (better), that is usually fine.
    # So we mainly check if actual > target + margin.
    
    delta_rel = target * baseline.get("margin_rel", 0.1)
    delta_abs = baseline.get("margin_abs", 0.0)
    allowed_delta = max(delta_rel, delta_abs)
    
    limit = target + allowed_delta
    
    style = "green"
    status = "PASS"
    
    if actual > limit:
        style = "red"
        status = "FAIL"
        msg = f"[{style}]{status}[/]: {name} {actual:.1f} > {limit:.1f} (Baseline: {target:.1f} + {allowed_delta:.1f})"
        return False, msg
    else:
        msg = f"[{style}]{status}[/]: {name} {actual:.1f} <= {limit:.1f} (Baseline: {target:.1f})"
        return True, msg

def main():
    parser = argparse.ArgumentParser(description="Check for performance regression against baseline")
    parser.add_argument("--baseline", type=Path, default="metrics/baseline_values.json", help="Path to golden metrics")
    parser.add_argument("--pcb", type=Path, default="pcb/temper.kicad_pcb", help="PCB file")
    parser.add_argument("-c", "--config", type=Path, default="packages/temper-placer/configs/temper_constraints.yaml", help="Constraints")
    parser.add_argument("--trials", type=int, default=5, help="Number of trials")
    
    args = parser.parse_args()
    
    # Load Baseline
    if not args.baseline.exists():
        console.print(f"[red]Baseline file not found: {args.baseline}[/]")
        sys.exit(1)
        
    with open(args.baseline) as f:
        golden = json.load(f)
        
    metrics_spec = golden["metrics"]
    
    # Setup Benchmark Environment
    console.print(f"[bold]Running Regression Check with {args.trials} trials...[/]")
    
    if not args.pcb.exists():
        console.print(f"[red]PCB file not found: {args.pcb}[/]")
        sys.exit(1)

    parse_result = parse_kicad_pcb(args.pcb)
    netlist = parse_result.netlist
    constraints = load_constraints(args.config)
    board = create_board_from_constraints(constraints)
    
    # MUST MATCH BENCHMARK WEIGHTS
    weights = {"overlap": 100.0, "boundary": 50.0, "wirelength": 1.0, "spread": 5.0} 
    loss_fn = create_standard_loss(weights)
    context = LossContext.from_netlist_and_board(netlist, board)
    
    # Configuration
    opt_cfg = OptimizerConfig(
        epochs=2000, # Allow enough epochs for convergence matching baseline
        seed=42,
        log_interval=2000,
        early_stopping=EarlyStoppingConfig(
            enabled=True,
            patience=500,
            monitor="loss",
            improvement_threshold=1e-5
        )
    )
    
    pipeline = create_default_pipeline()
    
    results = []
    
    # Run Trials
    for i in range(args.trials):
        seed = 42 + i # Deterministic seeds for reproducibility
        rng = jax.random.PRNGKey(seed)
        
        def init_fn():
             pres = pipeline.run(board, netlist, constraints, rng)
             return pres.state

        opt_cfg.seed = seed
        res = run_trial(i+1, "Spectral", init_fn, netlist, board, context, opt_cfg, loss_fn)
        results.append(res)
        
    stats = aggregate_results(results)
    
    # Compare
    failures = []
    
    # Mapping: Stats Name -> Baseline Key
    mapping = [
        ("Init Loss Mean", "init_loss"),
        ("Final Loss Mean", "final_loss"),
        ("Epochs Mean", "epochs"),
        ("Final HPWL Mean", "hpwl_final"),
    ]
    
    console.print("\n[bold]Regression Analysis:[/]")
    
    for stat_key, base_key in mapping:
        actual = stats[stat_key]
        spec = metrics_spec.get(base_key)
        if not spec:
            continue
            
        passed, msg = check_metric(base_key, actual, spec)
        console.print(msg)
        if not passed:
            failures.append(base_key)
            
    import os
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a") as f:
            f.write("## Optimizer Regression Check Results\n\n")
            f.write("| Metric | Baseline | Current (Mean) | Margin | Status |\n")
            f.write("| --- | --- | --- | --- | --- |\n")
            for stat_key, base_key in mapping:
                actual = stats[stat_key]
                spec = metrics_spec.get(base_key)
                if not spec: continue
                target = spec["mean"]
                margin_rel = spec.get("margin_rel", 0.1)
                margin_abs = spec.get("margin_abs", 0.0)
                allowed_delta = max(target * margin_rel, margin_abs)
                status = "❌ FAIL" if actual > target + allowed_delta else "✅ PASS"
                f.write(f"| {base_key} | {target:.2f} | {actual:.2f} | {margin_rel*100:.0f}% | {status} |\n")
            
            if failures:
                f.write("\n> [!CAUTION]\n")
                f.write(f"> Regression detected in: {', '.join(failures)}\n")
            else:
                f.write("\n> [!IMPORTANT]\n")
                f.write("> All metrics are within performance limits.\n")

    if failures:
        console.print(f"\n[bold red]REGRESSION DETECTED in: {', '.join(failures)}[/]")
        sys.exit(1)
    else:
        console.print("\n[bold green]ALL METRICS PASSED[/]")
        sys.exit(0)

if __name__ == "__main__":
    main()
