#!/usr/bin/env python3
"""
Benchmark initialization strategies for PCB placement.

Compares:
1. Random Initialization
2. Spectral/Heuristic Initialization

Metrics:
- Initial Loss (HPWL, Overlap)
- Final Loss (after N epochs)
- Improvement %
- Convergence Speed (Epochs)
"""

import argparse
from pathlib import Path
import time
import statistics
import jax
import jax.numpy as jnp
from rich.console import Console
from rich.table import Table

from temper_placer.core.state import PlacementState
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import load_constraints, create_board_from_constraints
from temper_placer.heuristics import create_default_pipeline
from temper_placer.losses.base import LossContext
from temper_placer.losses import (
    CompositeLoss, OverlapLoss, WirelengthLoss, BoundaryLoss, SpreadLoss, WeightedLoss
)
from temper_placer.optimizer import train, OptimizerConfig
from temper_placer.optimizer.config import GradNormConfig, EarlyStoppingConfig

console = Console()

def create_standard_loss(weights: dict):
    losses = []
    if "overlap" in weights:
        losses.append(WeightedLoss(OverlapLoss(margin=1.0, rotation_invariant=True), weights["overlap"]))
    if "boundary" in weights:
        losses.append(WeightedLoss(BoundaryLoss(), weights["boundary"]))
    if "wirelength" in weights:
        losses.append(WeightedLoss(WirelengthLoss(), weights["wirelength"]))
    if "spread" in weights:
        losses.append(WeightedLoss(SpreadLoss(), weights["spread"]))
    return CompositeLoss(losses)

def run_trial(
    trial_idx: int,
    strategy_name: str,
    initial_state_fn,
    netlist,
    board,
    context,
    config,
    loss_fn
):
    # Create initial state
    init_state = initial_state_fn()

    # Measure initial metrics
    init_res = loss_fn(
        init_state.positions, 
        jax.nn.softmax(init_state.rotation_logits, axis=-1), 
        context
    )
    init_breakdown = init_res.breakdown
    init_loss = float(init_res.value)
    
    start_time = time.time()
    
    # Run training
    result = train(
        netlist,
        board,
        loss_fn,
        context,
        config,
        initial_state=init_state,
        callback=None,
    )
    
    duration = time.time() - start_time
    final_loss = float(result.final_loss)
    
    # Re-evaluate final state
    final_res = loss_fn(
        result.final_state.positions,
        jax.nn.softmax(result.final_state.rotation_logits, axis=-1),
        context
    )
    final_breakdown = final_res.breakdown
    
    def get_val(bd, key_part):
        for k, v in bd.items():
            if key_part.lower() in k.lower():
                return float(v)
        return 0.0

    init_hpwl = get_val(init_breakdown, "wirelength")
    final_hpwl = get_val(final_breakdown, "wirelength")
    
    init_ovl = get_val(init_breakdown, "overlap")
    final_ovl = get_val(final_breakdown, "overlap")

    console.print(f"  [dim]Trial {trial_idx}: InitL={init_loss:.0f} FinalL={final_loss:.0f} Epochs={result.total_epochs} Time={duration:.1f}s[/]")
    
    return {
        "Strategy": strategy_name,
        "Trial": trial_idx,
        "Init Loss": init_loss,
        "Final Loss": final_loss,
        "Init HPWL": init_hpwl,
        "Final HPWL": final_hpwl,
        "Init Overlap": init_ovl,
        "Final Overlap": final_ovl,
        "Epochs": result.total_epochs,
        "Time": duration
    }

def aggregate_results(results):
    stats = {}
    metrics = ["Init Loss", "Final Loss", "Init HPWL", "Final HPWL", "Init Overlap", "Final Overlap", "Epochs", "Time"]
    
    for m in metrics:
        vals = [r[m] for r in results]
        stats[f"{m} Mean"] = statistics.mean(vals)
        stats[f"{m} Std"] = statistics.stdev(vals) if len(vals) > 1 else 0.0
    
    return stats

def main():
    parser = argparse.ArgumentParser(description="Benchmark Initialization Strategies")
    parser.add_argument("pcb", type=Path, help="Input KiCad PCB file")
    parser.add_argument("-c", "--config", type=Path, required=True, help="Constraints YAML")
    parser.add_argument("--epochs", type=int, default=1000, help="Optimization epochs")
    parser.add_argument("--trials", type=int, default=5, help="Number of trials per strategy")
    parser.add_argument("--seed", type=int, default=42, help="Base random seed")
    
    args = parser.parse_args()
    
    # Setup
    parse_result = parse_kicad_pcb(args.pcb)
    netlist = parse_result.netlist
    constraints = load_constraints(args.config)
    board = create_board_from_constraints(constraints)
    
    # Create Loss
    weights = {"overlap": 100.0, "boundary": 50.0, "wirelength": 1.0, "spread": 5.0}
    loss_fn = create_standard_loss(weights)
    context = LossContext.from_netlist_and_board(netlist, board)
    
    # Optimizer Config (Enable Early Stopping)
    opt_cfg = OptimizerConfig(
        epochs=args.epochs,
        seed=args.seed,
        log_interval=args.epochs, 
        use_centrality_weighting=False,
        use_grad_norm=False,
        grad_norm=GradNormConfig(),
        early_stopping=EarlyStoppingConfig(
            enabled=True,
            patience=500, # Be fairly patient
            monitor="loss",
            improvement_threshold=1e-5
        )
    )
    
    all_raw_results = []
    agg_results = {}
    
    # --- Random Baseline ---
    console.print(f"\n[bold cyan]Running Random Baseline ({args.trials} trials)...[/]")
    random_raw = []
    for i in range(args.trials):
        seed = args.seed + i
        rng = jax.random.PRNGKey(seed)
        
        def init_fn():
            return PlacementState.random_init(
                n_components=netlist.n_components,
                board_width=board.width,
                board_height=board.height,
                key=rng,
                n_nets=netlist.n_nets
            )
            
        opt_cfg.seed = seed
        res = run_trial(i+1, "Random", init_fn, netlist, board, context, opt_cfg, loss_fn)
        random_raw.append(res)
        all_raw_results.append(res)
        
    agg_results["Random"] = aggregate_results(random_raw)

    # --- Spectral Baseline ---
    console.print(f"\n[bold cyan]Running Spectral Baseline ({args.trials} trials)...[/]")
    spectral_raw = []
    pipeline = create_default_pipeline()

    for i in range(args.trials):
        seed = args.seed + i
        rng = jax.random.PRNGKey(seed)
        
        def init_fn():
             # Spectral is deterministic for a given graph, but might have some random noise if injected.
             # Actually create_default_pipeline uses a seed.
             pres = pipeline.run(board, netlist, constraints, rng)
             return pres.state

        opt_cfg.seed = seed
        res = run_trial(i+1, "Spectral", init_fn, netlist, board, context, opt_cfg, loss_fn)
        spectral_raw.append(res)
        all_raw_results.append(res)

    agg_results["Spectral"] = aggregate_results(spectral_raw)
    
    # --- Reporting ---
    
    # 1. Detailed Stats Table
    table = Table(title=f"Benchmark Statistics (N={args.trials}, Epochs={args.epochs})")
    table.add_column("Strategy", style="cyan")
    table.add_column("Init Loss", justify="right")
    table.add_column("Final Loss", justify="right")
    table.add_column("Init HPWL", justify="right")
    table.add_column("Final HPWL", justify="right")
    table.add_column("Epochs", justify="right")
    
    for strategy, stats in agg_results.items():
        table.add_row(
            strategy,
            f"{stats['Init Loss Mean']:.1f} ± {stats['Init Loss Std']:.1f}",
            f"{stats['Final Loss Mean']:.1f} ± {stats['Final Loss Std']:.1f}",
            f"{stats['Init HPWL Mean']:.1f} ± {stats['Init HPWL Std']:.1f}",
            f"{stats['Final HPWL Mean']:.1f} ± {stats['Final HPWL Std']:.1f}",
            f"{stats['Epochs Mean']:.1f} ± {stats['Epochs Std']:.1f}"
        )
    console.print("\n")
    console.print(table)
    
    # 2. Deltas & Speedup
    rand_stats = agg_results["Random"]
    spec_stats = agg_results["Spectral"]
    
    init_loss_delta = rand_stats["Init Loss Mean"] - spec_stats["Init Loss Mean"]
    init_loss_pct = (init_loss_delta / rand_stats["Init Loss Mean"]) * 100.0
    
    final_qual_delta = rand_stats["Final Loss Mean"] - spec_stats["Final Loss Mean"]
    
    # Speedup: How much faster is Spectral? (Lower epochs is better)
    # Speedup = Random Epochs / Spectral Epochs
    if spec_stats['Epochs Mean'] > 0:
        speedup = rand_stats['Epochs Mean'] / spec_stats['Epochs Mean']
    else:
        speedup = 0.0
        
    console.print("\n[bold]Comparison (Spectral vs Random):[/]")
    console.print(f"  Initial Quality Improvement: [green]{init_loss_pct:.1f}%[/] (Loss Delta: {init_loss_delta:.1f})")
    console.print(f"  Convergence Speedup:         [green]{speedup:.2f}x[/] (Epochs: {rand_stats['Epochs Mean']:.1f} vs {spec_stats['Epochs Mean']:.1f})")
    console.print(f"  Final Quality Advantage:     {final_qual_delta:.1f} loss units")

if __name__ == "__main__":
    main()
