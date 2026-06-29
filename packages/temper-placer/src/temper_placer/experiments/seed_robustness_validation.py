import csv
import time
from dataclasses import dataclass
from pathlib import Path

import jax
import numpy as np
import yaml  # type: ignore[import-untyped]

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.geometry.transform import sample_rotation_batch
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.wirelength import WirelengthLoss
from temper_placer.optimizer import CheckpointConfig, EarlyStoppingConfig, OptimizerConfig, train

# Results directory
RESULTS_DIR = Path("robustness_results")
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class SeedRunResult:
    seed: int
    final_loss: float
    overlap_penalty: float
    boundary_penalty: float
    wirelength: float
    epochs_run: int
    elapsed_seconds: float
    converged: bool

def create_test_netlist(n_components: int = 17) -> Netlist:
    import importlib.util

    # Path to tests/fixtures/generators/synthetic_netlist.py
    # This script is in src/temper_placer/experiments/seed_robustness_validation.py
    # root is 4 levels up
    root_dir = Path(__file__).parent.parent.parent.parent
    fixtures_path = root_dir / "tests" / "fixtures" / "generators" / "synthetic_netlist.py"

    spec = importlib.util.spec_from_file_location("synthetic_netlist", fixtures_path)
    synthetic_netlist = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(synthetic_netlist)  # type: ignore[union-attr]

    return synthetic_netlist.generate_netlist(n_components=n_components, seed=12345)

def run_robust_optimization(
    netlist: Netlist,
    board: Board,
    seed: int,
    epochs: int = 400,
) -> SeedRunResult:
    # Create loss context
    context = LossContext.from_netlist_and_board(netlist, board)

    # All robustness features enabled
    composite = CompositeLoss([
        WeightedLoss(OverlapLoss(inflation_ramp=0.3), weight=100.0),
        WeightedLoss(BoundaryLoss(), weight=50.0),
        WeightedLoss(WirelengthLoss(), weight=1.0),
    ])

    config = OptimizerConfig(
        epochs=epochs,
        seed=seed,
        adaptive_overlap_enabled=True,
        jiggle_enabled=True,
        log_interval=epochs,
        checkpoint=CheckpointConfig(enabled=False),
        early_stopping=EarlyStoppingConfig(enabled=False),
    )

    start_time = time.time()
    result = train(netlist, board, composite, context, config)
    elapsed = time.time() - start_time

    # Get final metrics
    positions = result.final_state.positions
    rotation_logits = result.final_state.rotation_logits
    key = jax.random.PRNGKey(0)
    rotations = sample_rotation_batch(rotation_logits, key, temperature=0.01)

    overlap_val = float(OverlapLoss()(positions, rotations, context).value)
    boundary_val = float(BoundaryLoss()(positions, rotations, context).value)
    wirelength_val = float(WirelengthLoss()(positions, rotations, context).value)

    return SeedRunResult(
        seed=seed,
        final_loss=float(result.final_loss),
        overlap_penalty=overlap_val,
        boundary_penalty=boundary_val,
        wirelength=wirelength_val,
        epochs_run=result.total_epochs,
        elapsed_seconds=elapsed,
        converged=(overlap_val < 1.0 and boundary_val < 1.0),
    )

def main():
    n_seeds = 100
    epochs = 400
    n_components = 17

    print(f"Starting Seed Robustness Validation ({n_seeds} seeds, {epochs} epochs)")
    netlist = create_test_netlist(n_components)
    board = Board(100.0, 100.0)

    results: list[SeedRunResult] = []

    for i in range(n_seeds):
        res = run_robust_optimization(netlist, board, seed=i, epochs=epochs)
        results.append(res)
        if (i+1) % 10 == 0:
            print(f"  Progress: {i+1}/{n_seeds} seeds...")

    # Analyze results
    losses = [r.final_loss for r in results]
    overlaps = [r.overlap_penalty for r in results]
    boundaries = [r.boundary_penalty for r in results]

    failure_rate = sum(1 for r in results if not r.converged) / n_seeds
    mean_overlap = np.mean(overlaps)
    mean_boundary = np.mean(boundaries)
    cv_loss = np.std(losses) / np.mean(losses)

    print("\nRobustness Results:")
    print(f"  Failure Rate:  {failure_rate:.1%} (Baseline: 23.0%)")
    print(f"  Mean Overlap:  {mean_overlap:.4f} (Baseline: ~0.5)")
    print(f"  Mean Boundary: {mean_boundary:.4f} (Baseline: 0.0)")
    print(f"  Loss CV:       {cv_loss:.4f} (Baseline: ~0.35)")

    # Save CSV
    csv_path = RESULTS_DIR / "robustness_analysis.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "seed", "final_loss", "overlap_penalty", "boundary_penalty",
            "wirelength", "epochs_run", "elapsed_seconds", "converged"
        ])
        writer.writeheader()
        for r in results:
            writer.writerow({
                "seed": r.seed,
                "final_loss": r.final_loss,
                "overlap_penalty": r.overlap_penalty,
                "boundary_penalty": r.boundary_penalty,
                "wirelength": r.wirelength,
                "epochs_run": r.epochs_run,
                "elapsed_seconds": r.elapsed_seconds,
                "converged": r.converged
            })

    # Generate pathological report
    pathological = [r for r in results if not r.converged]
    report = {
        "total_seeds_tested": n_seeds,
        "pathological_count": len(pathological),
        "pathological_rate": failure_rate,
        "worst_seeds": [
            {
                "seed": r.seed,
                "overlap_penalty": r.overlap_penalty,
                "boundary_penalty": r.boundary_penalty,
                "final_loss": r.final_loss
            } for r in sorted(pathological, key=lambda x: x.overlap_penalty, reverse=True)
        ]
    }

    with open(RESULTS_DIR / "robustness_report.yaml", "w") as f:
        yaml.dump(report, f)

    print(f"\nSaved results to {RESULTS_DIR}")

if __name__ == "__main__":
    main()
