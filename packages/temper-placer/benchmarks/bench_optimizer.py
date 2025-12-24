
import argparse

# Add project roots to path
import sys
import time
from pathlib import Path

import pandas as pd

project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root / "src"))
sys.path.append(str(project_root)) # For tests.fixtures

from tests.fixtures.generators.synthetic_netlist import generate_netlist

from temper_placer.core.board import Board
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.optimizer.config import OptimizerConfig
from temper_placer.optimizer.train import train


def benchmark_run(n_components: int, epochs: int = 8000):
    print(f"\nBenchmarking {n_components} components for {epochs} epochs...")

    # 1. Setup
    netlist = generate_netlist(n_components=n_components)
    board = Board(width=200, height=200) # Large enough for any n

    composite = CompositeLoss([
        WeightedLoss(OverlapLoss(rotation_invariant=True), weight=100.0),
        WeightedLoss(BoundaryLoss(), weight=50.0),
        WeightedLoss(WirelengthLoss(), weight=10.0),
    ])

    context = LossContext.from_netlist_and_board(netlist, board)
    config = OptimizerConfig(
        epochs=epochs,
        checkpoint=replace(OptimizerConfig().checkpoint, enabled=False),
        early_stopping=replace(OptimizerConfig().early_stopping, enabled=False),
        validate_interval=10000 # Disable validation
    )

    # 2. Warmup (JIT compilation)
    print("  Warming up (JIT)...")
    warmup_config = replace(config, epochs=5)
    train(netlist, board, composite, context, warmup_config)

    # 3. Main Run
    print(f"  Running {epochs} epochs...")
    start_time = time.time()
    result = train(netlist, board, composite, context, config)
    duration = time.time() - start_time

    ms_per_epoch = (duration * 1000) / epochs
    print(f"  Done in {duration:.2f}s ({ms_per_epoch:.2f} ms/epoch)")

    return {
        "n_components": n_components,
        "epochs": epochs,
        "total_time_s": duration,
        "ms_per_epoch": ms_per_epoch
    }

def replace(obj, **kwargs):
    from dataclasses import replace as dc_replace
    return dc_replace(obj, **kwargs)

def main():
    parser = argparse.ArgumentParser(description="Performance Benchmark for Temper Placer")
    parser.add_argument("--epochs", type=int, default=8000, help="Number of epochs")
    parser.add_argument("--sizes", type=int, nargs="+", default=[50, 100, 200], help="Component counts")
    args = parser.parse_args()

    results = []
    for n in args.sizes:
        res = benchmark_run(n, args.epochs)
        results.append(res)

    df = pd.DataFrame(results)
    print("\nBenchmark Results:")
    print(df)

    output_path = Path("benchmark_results.csv")
    df.to_csv(output_path, index=False)
    print(f"\nSaved results to {output_path}")

if __name__ == "__main__":
    main()
