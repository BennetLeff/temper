#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path
import jax
import jax.numpy as jnp
from rich.console import Console
from rich.table import Table

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

def main():
    parser = argparse.ArgumentParser(description="Profile execution time of individual loss functions")
    parser.add_argument("pcb", type=Path, help="KiCad PCB file")
    parser.add_argument("-c", "--config", type=Path, required=True, help="Constraints YAML")
    parser.add_argument("--iterations", type=int, default=10, help="Number of profiling iterations")
    
    args = parser.parse_args()
    console = Console()
    
    # 1. Setup
    console.print("[bold]Setting up profiling environment...[/]")
    parse_result = parse_kicad_pcb(args.pcb)
    netlist = parse_result.netlist
    constraints = load_constraints(args.config)
    board = create_board_from_constraints(constraints)
    
    # Create standard composite loss
    composite = CompositeLoss([
        WeightedLoss(OverlapLoss(), weight=100.0),
        WeightedLoss(WirelengthLoss(), weight=1.0),
        WeightedLoss(BoundaryLoss(), weight=50.0),
        WeightedLoss(SpreadLoss(), weight=5.0),
    ])
    
    context = LossContext.from_netlist_and_board(netlist, board)
    
    # Random positions for profiling
    rng = jax.random.PRNGKey(42)
    positions = jax.random.uniform(rng, (netlist.n_components, 2)) * 100.0
    rotations = jax.random.uniform(rng, (netlist.n_components, 4))
    vn = jax.random.uniform(rng, (netlist.n_nets, 2)) * 100.0
    
    # 2. Warmup (JIT compilation)
    console.print("[yellow]Warming up (JIT compilation)...[/]")
    composite(positions, rotations, context, net_virtual_nodes=vn)
    
    # 3. Profiling
    console.print(f"[bold green]Profiling {args.iterations} iterations...[/]")
    
    all_timings = []
    for i in range(args.iterations):
        timings = composite.record_timings(positions, rotations, context, net_virtual_nodes=vn)
        all_timings.append(timings)
        
    # 4. Report
    table = Table(title=f"Per-Loss Execution Time ({netlist.n_components} components)")
    table.add_column("Loss Function", style="cyan")
    table.add_column("Mean Time (ms)", justify="right")
    table.add_column("Min Time (ms)", justify="right")
    table.add_column("Max Time (ms)", justify="right")
    
    loss_names = composite.loss_names
    for name in loss_names:
        times = [t[name] for t in all_timings]
        avg = sum(times) / len(times)
        table.add_row(
            name,
            f"{avg:.4f}",
            f"{min(times):.4f}",
            f"{max(times):.4f}"
        )
        
    console.print(table)

if __name__ == "__main__":
    main()
