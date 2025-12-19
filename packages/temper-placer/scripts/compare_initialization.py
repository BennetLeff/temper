"""
Initialization Strategy Comparison Script.

This script compares different initialization methods (Random, Margin, Spectral)
across multiple seeds to quantify their impact on final loss, convergence,
and variance.

Implements temper-1my.4.4: Test initialization strategies
"""

import time
import jax
import jax.numpy as jnp
import numpy as np
import pandas as pd
from pathlib import Path
from rich.console import Console
from rich.table import Table

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.io.config_loader import load_constraints, create_board_from_constraints
from temper_placer.optimizer import train, OptimizerConfig, InitializationConfig
from temper_placer.losses import (
    CompositeLoss,
    WeightedLoss,
    OverlapLoss,
    BoundaryLoss,
    WirelengthLoss,
    SpreadLoss,
)
from temper_placer.losses.base import LossContext

console = Console()

def make_loss(weights):
    """Simple loss factory for testing."""
    return CompositeLoss([
        WeightedLoss(OverlapLoss(margin=1.0, rotation_invariant=True), weight=weights.get("overlap", 100.0)),
        WeightedLoss(BoundaryLoss(), weight=weights.get("boundary", 50.0)),
        WeightedLoss(WirelengthLoss(), weight=weights.get("wirelength", 10.0)),
        WeightedLoss(SpreadLoss(), weight=weights.get("spread", 5.0)),
    ])

def run_trial(netlist, board, composite_loss, context, method, seed, epochs=500):
    """Run a single optimization trial."""
    config = OptimizerConfig(
        epochs=epochs,
        seed=seed,
        initialization=InitializationConfig(method=method),
        log_interval=100
    )
    
    start_time = time.time()
    result = train(netlist, board, composite_loss, context, config)
    elapsed = time.time() - start_time
    
    # Get final metrics
    final_metrics = result.history[-1]
    overlap = final_metrics.loss_breakdown.get("overlap", 0.0)
    
    return {
        "method": method,
        "seed": seed,
        "final_loss": result.final_loss,
        "final_overlap": overlap,
        "epochs": result.total_epochs,
        "time_s": elapsed
    }

def main():
    # Setup
    fixtures_dir = Path("tests/fixtures")
    pcb_path = fixtures_dir / "minimal_board.kicad_pcb"
    config_path = fixtures_dir / "constraints_minimal.yaml"
    
    if not pcb_path.exists():
        console.print(f"[red]Error: PCB file not found at {pcb_path}[/]")
        return

    # Load data
    parse_result = parse_kicad_pcb(pcb_path)
    netlist = parse_result.netlist
    constraints = load_constraints(config_path)
    board = create_board_from_constraints(constraints)
    context = LossContext.from_netlist_and_board(netlist, board)
    
    default_weights = {"overlap": 100.0, "boundary": 50.0, "wirelength": 10.0, "spread": 5.0}
    composite_loss = make_loss(default_weights)
    
    methods = ["random", "spectral"]
    seeds = [42, 123, 777, 2024, 9999]
    
    results = []
    
    console.print(f"[bold blue]Starting Initialization Strategy Comparison[/]")
    console.print(f"PCB: {pcb_path.name} ({netlist.n_components} components)")
    console.print(f"Trials: {len(methods)} methods x {len(seeds)} seeds = {len(methods) * len(seeds)} total runs")
    console.print("-" * 50)

    for method in methods:
        for seed in seeds:
            console.print(f"Running [cyan]{method}[/] (seed {seed})...", end="")
            trial_result = run_trial(netlist, board, composite_loss, context, method, seed)
            results.append(trial_result)
            console.print(f" [green]Done[/] (loss: {trial_result['final_loss']:.2f})")

    # Aggregate Results
    df = pd.DataFrame(results)
    summary = df.groupby("method").agg({
        "final_loss": ["mean", "std"],
        "final_overlap": ["mean", "std"],
        "time_s": ["mean"]
    }).round(2)
    
    # Display Table
    table = Table(title="Initialization Strategy Comparison (Summary)")
    table.add_column("Method", style="cyan")
    table.add_column("Mean Loss", justify="right")
    table.add_column("Std Dev Loss", justify="right")
    table.add_column("Mean Overlap", justify="right")
    table.add_column("Mean Time (s)", justify="right")
    
    for method in methods:
        row = summary.loc[method]
        table.add_row(
            method,
            str(row[("final_loss", "mean")]),
            str(row[("final_loss", "std")]),
            str(row[("final_overlap", "mean")]),
            str(row[("time_s", "mean")])
        )
    
    console.print("\n")
    console.print(table)
    
    # Recommendation
    best_method = summary[("final_loss", "mean")].idxmin()
    improvement = (summary.loc["random", ("final_loss", "mean")] - summary.loc["spectral", ("final_loss", "mean")]) / summary.loc["random", ("final_loss", "mean")] * 100
    
    console.print(f"\n[bold green]Recommendation:[/] Use [bold cyan]{best_method}[/] initialization.")
    console.print(f"Reasoning: Spectral initialization achieved a [bold]{improvement:.1f}%[/] lower mean loss compared to random initialization on this board.")

if __name__ == "__main__":
    main()
