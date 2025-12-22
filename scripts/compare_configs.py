#!/usr/bin/env python3
"""
Compare two optimizer configurations (A/B testing).

Runs N paired trials for Reference vs Candidate configurations.
Performs statistical significance testing on metrics.
"""

import argparse
import sys
import time
import statistics
import csv
from pathlib import Path
from dataclasses import dataclass, field
import jax
import jax.numpy as jnp
from rich.console import Console
from rich.table import Table
from scipy import stats

from temper_placer.core.state import PlacementState
from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import load_constraints, create_board_from_constraints
from temper_placer.heuristics import create_default_pipeline
from temper_placer.losses.base import LossContext
from temper_placer.losses import (
    CompositeLoss, OverlapLoss, WirelengthLoss, BoundaryLoss, SpreadLoss, WeightedLoss,
    GroupClusterLoss, GroupConfig
)
from temper_placer.optimizer import train, OptimizerConfig
from temper_placer.optimizer.config import GradNormConfig, EarlyStoppingConfig

console = Console()

@dataclass
class TrialResult:
    config_name: str
    seed: int
    init_loss: float  # Added init_loss
    final_loss: float
    hpwl: float
    overlap: float
    epochs: int
    duration: float


def create_loss_from_config(constraints, auto_group=True, netlist=None):
    """
    Recreate the loss construction logic from cli/__init__.py 
    to respect the specific weights in the constraints object.
    """
    weights = constraints.losses.get_weights() if constraints.losses else {
        "overlap": 100.0, "boundary": 50.0, "wirelength": 10.0, "spread": 5.0
    }
    
    losses = []
    
    # 1. Standard losses
    if "overlap" in weights:
        losses.append(WeightedLoss(OverlapLoss(margin=1.0, rotation_invariant=True, inflation_ramp=0.3), weights["overlap"]))
    if "boundary" in weights:
        losses.append(WeightedLoss(BoundaryLoss(), weights["boundary"]))
    if "wirelength" in weights:
        losses.append(WeightedLoss(WirelengthLoss(), weights["wirelength"]))
    if "spread" in weights:
        losses.append(WeightedLoss(SpreadLoss(), weights["spread"]))
        
    # 2. Star Point
    if "star_point" in weights or constraints.star_grounds:
         from temper_placer.losses.star_point import StarPointLoss
         w = weights.get("star_point", 1.0)
         losses.append(WeightedLoss(StarPointLoss(), w))

    # 3. Aesthetics
    from temper_placer.losses.aesthetic import create_aesthetic_losses
    losses.extend(create_aesthetic_losses(netlist, constraints))

    # 4. Manufacturing
    from temper_placer.losses.manufacturing_margin import create_manufacturing_margin_loss
    mfg_loss = create_manufacturing_margin_loss()
    if mfg_loss:
        losses.append(WeightedLoss(mfg_loss, 5.0)) # Hardcoded weight in CLI, matched here

    # 5. Grouping (Simplified for benchmark)
    if auto_group and constraints.component_groups and netlist:
        group_configs = []
        for group in constraints.component_groups:
             valid_refs = [r for r in group.components if r in netlist._component_index]
             if not valid_refs: continue
             indices = [netlist.get_component_index(r) for r in valid_refs]
             group_configs.append(GroupConfig(
                 name=group.name,
                 component_indices=jnp.array(indices, dtype=jnp.int32),
                 max_diameter_mm=group.max_spread_mm,
                 weight=2.0
             ))
        if group_configs:
            losses.append(WeightedLoss(GroupClusterLoss(group_configs), 10.0))

    return CompositeLoss(losses)


def run_config(
    name: str,
    config_path: Path,
    pcb_path: Path,
    epochs: int,
    trials: int,
    start_seed: int
) -> list[TrialResult]:
    
    # Reload for each config to ensure clean state
    parse_result = parse_kicad_pcb(pcb_path)
    netlist = parse_result.netlist
    constraints = load_constraints(config_path)
    board = create_board_from_constraints(constraints)
    context = LossContext.from_netlist_and_board(netlist, board)
    
    loss_fn = create_loss_from_config(constraints, netlist=netlist)
    
    # Match CLI optimizer defaults
    opt_cfg = OptimizerConfig(
        epochs=epochs,
        seed=start_seed,
        log_interval=epochs,
        use_centrality_weighting=False,
        use_grad_norm=False,
        grad_norm=GradNormConfig(),
        early_stopping=EarlyStoppingConfig(
            enabled=True, patience=500, monitor="loss", improvement_threshold=1e-5
        )
    )

    results = []
    
    # Pre-generate pipeline for Spectral init (deterministic per seed)
    pipeline = create_default_pipeline()

    with console.status(f"[bold green]Running {name}...[/]") as status:
        for i in range(trials):
            seed = start_seed + i
            opt_cfg.seed = seed
            status.update(f"[bold green]Running {name}: Trial {i+1}/{trials} (Seed {seed})[/]")
            
            # Use Spectral Init
            rng = jax.random.PRNGKey(seed)
            pres = pipeline.run(board, netlist, constraints, rng)
            init_state = pres.state
            
            # Capture Init Loss
            init_res = loss_fn(
                init_state.positions,
                jax.nn.softmax(init_state.rotation_logits, axis=-1),
                context
            )
            init_loss = float(init_res.value)
            
            start_t = time.time()
            res = train(
                netlist, board, loss_fn, context, opt_cfg, 
                initial_state=init_state, callback=None
            )
            dur = time.time() - start_t
            
            # Extract metrics
            final_res = loss_fn(
                res.final_state.positions,
                jax.nn.softmax(res.final_state.rotation_logits, axis=-1),
                context
            )
            final_bd = final_res.breakdown
            
            def get_val(bd, key_part):
                for k, v in bd.items():
                    if key_part.lower() in k.lower(): return float(v)
                return 0.0

            hpwl = get_val(final_bd, "wirelength")
            ovl = get_val(final_bd, "overlap")
            
            results.append(TrialResult(
                config_name=name,
                seed=seed,
                init_loss=init_loss,
                final_loss=float(res.final_loss),
                hpwl=hpwl,
                overlap=ovl,
                epochs=res.total_epochs,
                duration=dur
            ))
            
    return results

def calculate_derived_metrics(results: list[TrialResult]):
    """Compute derived metrics for a set of results."""
    losses = [r.final_loss for r in results]
    improvements = [r.init_loss - r.final_loss for r in results]
    durations = [r.duration for r in results]
    epochs = [r.epochs for r in results]
    
    # Efficiency: Loss Reduction / Time
    efficiencies = [imp / max(dur, 0.001) for imp, dur in zip(improvements, durations)]
    
    # Convergence Rate: Loss Reduction / Epoch
    conv_rates = [imp / max(ep, 1) for imp, ep in zip(improvements, epochs)]
    
    # Consistency: 1 / (StdDev of Final Loss)
    # Note: If stddev is 0 (deterministic), consistency is infinite. Cap it.
    std_loss = statistics.stdev(losses) if len(losses) > 1 else 0.0
    consistency = 1.0 / (std_loss + 1e-6)
    
    return {
        "efficiency": efficiencies,
        "conv_rate": conv_rates,
        "consistency": consistency
    }

def compare_results(ref_results: list[TrialResult], cand_results: list[TrialResult]):
    # --- Primary Metrics ---
    metrics = ["final_loss", "hpwl", "overlap", "epochs", "duration"]
    
    table = Table(title="A/B Test Results (Welch's t-test)")
    table.add_column("Metric", style="cyan")
    table.add_column("Reference (Mean ± Std)", justify="right")
    table.add_column("Candidate (Mean ± Std)", justify="right")
    table.add_column("Delta %", justify="right")
    table.add_column("P-Value", justify="right")
    table.add_column("Signif.", justify="center")
    
    for m in metrics:
        ref_vals = [getattr(r, m) for r in ref_results]
        cand_vals = [getattr(r, m) for r in cand_results]
        
        ref_mean = statistics.mean(ref_vals)
        ref_std = statistics.stdev(ref_vals) if len(ref_vals) > 1 else 0.0
        
        cand_mean = statistics.mean(cand_vals)
        cand_std = statistics.stdev(cand_vals) if len(cand_vals) > 1 else 0.0
        
        delta = (cand_mean - ref_mean) / ref_mean * 100.0 if ref_mean != 0 else 0.0
        
        if len(ref_vals) > 1 and len(cand_vals) > 1 and (ref_std > 0 or cand_std > 0):
            t_stat, p_val = stats.ttest_ind(ref_vals, cand_vals, equal_var=False)
        else:
            p_val = 1.0
            
        is_sig = p_val < 0.05
        sig_str = "[green]YES[/]" if is_sig else "[dim]NO[/]"
        color = "green" if delta < 0 else "red"
        
        table.add_row(
            m,
            f"{ref_mean:.2f} ± {ref_std:.2f}",
            f"{cand_mean:.2f} ± {cand_std:.2f}",
            f"[{color}]{delta:+.2f}%[/]",
            f"{p_val:.4f}",
            sig_str
        )
        
    console.print("\n")
    console.print(table)
    
    # --- Derived Metrics ---
    ref_derived = calculate_derived_metrics(ref_results)
    cand_derived = calculate_derived_metrics(cand_results)
    
    d_table = Table(title="Derived Efficiency Metrics (Higher is Better)")
    d_table.add_column("Metric", style="magenta")
    d_table.add_column("Reference Mean", justify="right")
    d_table.add_column("Candidate Mean", justify="right")
    d_table.add_column("Improvement", justify="right")
    
    # Helper for derived row
    def add_derived_row(name, key):
        if key == "consistency":
            # scalar
            r_val = ref_derived[key]
            c_val = cand_derived[key]
        else:
            # list
            r_val = statistics.mean(ref_derived[key])
            c_val = statistics.mean(cand_derived[key])
            
        imp = (c_val - r_val) / r_val * 100.0 if r_val != 0 else 0.0
        color = "green" if imp > 0 else "red"
        
        d_table.add_row(
            name,
            f"{r_val:.2f}",
            f"{c_val:.2f}",
            f"[{color}]{imp:+.2f}%[/]"
        )
        
    add_derived_row("Efficiency (Loss/sec)", "efficiency")
    add_derived_row("Convergence (Loss/epoch)", "conv_rate")
    add_derived_row("Consistency (1/StdDev)", "consistency")
    
    console.print("\n")
    console.print(d_table)


def main():
    parser = argparse.ArgumentParser(description="Compare Optimizer Configurations")
    parser.add_argument("pcb", type=Path, help="Input PCB")
    parser.add_argument("ref_config", type=Path, help="Reference Config (A)")
    parser.add_argument("cand_config", type=Path, help="Candidate Config (B)")
    parser.add_argument("--epochs", type=int, default=1000)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--csv-out", type=Path, help="Save raw results to CSV")
    
    args = parser.parse_args()
    
    console.print(f"[bold]Comparing:[/]\n  A: {args.ref_config.name}\n  B: {args.cand_config.name}")
    
    ref_res = run_config("Reference", args.ref_config, args.pcb, args.epochs, args.trials, args.seed)
    cand_res = run_config("Candidate", args.cand_config, args.pcb, args.epochs, args.trials, args.seed)
    
    compare_results(ref_res, cand_res)
    
    if args.csv_out:
        with open(args.csv_out, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Config", "Seed", "FinalLoss", "HPWL", "Overlap", "Epochs", "Duration"])
            for r in ref_res + cand_res:
                writer.writerow([r.config_name, r.seed, r.final_loss, r.hpwl, r.overlap, r.epochs, r.duration])
        console.print(f"\n[dim]Saved results to {args.csv_out}[/]")

if __name__ == "__main__":
    main()
