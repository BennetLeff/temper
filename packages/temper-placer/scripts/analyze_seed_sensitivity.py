#!/usr/bin/env python3
"""
Seed sensitivity analysis script (temper-1my.4.2).

Runs optimizer with 100 different seeds on multiple PCBs to quantify
variance in placement quality due to random initialization.

Usage:
    python scripts/analyze_seed_sensitivity.py
    python scripts/analyze_seed_sensitivity.py --seeds 100 --epochs 400
    python scripts/analyze_seed_sensitivity.py --boards piantor_left bitaxe_ultra
"""

import argparse
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import yaml

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.io.kicad_pcb import parse_kicad_pcb
from temper_placer.losses import BoundaryLoss, OverlapLoss, WirelengthLoss
from temper_placer.losses.base import CompositeLoss, LossContext, WeightedLoss
from temper_placer.optimizer import LearningRateSchedule, OptimizerConfig, train


@dataclass
class SeedResult:
    """Result from a single seed run."""
    seed: int
    final_loss: float
    overlap_loss: float
    boundary_loss: float
    wirelength: float
    convergence_epoch: int
    runtime_seconds: float
    converged: bool

    def to_dict(self):
        return asdict(self)


@dataclass
class Statistics:
    """Statistical metrics for seed sensitivity."""
    n_seeds: int
    mean: float
    std: float
    median: float
    p50: float
    p95: float
    min: float
    max: float
    cv: float  # Coefficient of variation
    skewness: float
    kurtosis: float
    failure_rate: float


def run_single_seed(
    netlist: Netlist,
    board: Board,
    seed: int,
    epochs: int = 400,
) -> SeedResult:
    """Run optimizer with single seed and collect metrics."""
    # Create loss context
    context = LossContext.from_netlist_and_board(netlist, board)

    # Create composite loss
    composite = CompositeLoss([
        WeightedLoss(OverlapLoss(), weight=100.0),
        WeightedLoss(BoundaryLoss(), weight=50.0),
        WeightedLoss(WirelengthLoss(), weight=1.0),
    ])

    # Create config
    config = OptimizerConfig(
        epochs=epochs,
        seed=seed,
        learning_rate=LearningRateSchedule(initial=0.1),
        log_interval=epochs,  # Only log at end
    )

    # Run optimization
    start_time = time.time()
    result = train(netlist, board, composite, context, config)
    runtime = time.time() - start_time

    # Evaluate individual losses
    import jax

    from temper_placer.geometry.transform import sample_rotation_batch

    positions = result.final_state.positions
    rotation_logits = result.final_state.rotation_logits

    # Sample hard rotations
    key = jax.random.PRNGKey(0)
    rotations = sample_rotation_batch(rotation_logits, key, temperature=0.01)

    # Compute individual loss components
    overlap_val = float(OverlapLoss()(positions, rotations, context).value)
    boundary_val = float(BoundaryLoss()(positions, rotations, context).value)
    wirelength_val = float(WirelengthLoss()(positions, rotations, context).value)

    # Determine convergence (overlap < 10, boundary < 10)
    converged = (overlap_val < 10.0) and (boundary_val < 10.0)

    return SeedResult(
        seed=seed,
        final_loss=float(result.final_loss),
        overlap_loss=overlap_val,
        boundary_loss=boundary_val,
        wirelength=wirelength_val,
        convergence_epoch=result.total_epochs,
        runtime_seconds=runtime,
        converged=converged,
    )


def compute_statistics(results: list[SeedResult], metric: str = "final_loss", failure_threshold: float = 2.0) -> Statistics:
    """Compute statistical metrics from results."""
    values = np.array([getattr(r, metric) for r in results])

    mean = float(np.mean(values))
    std = float(np.std(values))
    median = float(np.median(values))
    p50 = median
    p95 = float(np.percentile(values, 95))
    min_val = float(np.min(values))
    max_val = float(np.max(values))

    # Coefficient of variation
    cv = std / mean if mean > 1e-9 else 0.0

    # Skewness and kurtosis
    from scipy import stats
    skewness = float(stats.skew(values))
    kurtosis = float(stats.kurtosis(values))

    # Failure rate (values > threshold * median)
    threshold_val = failure_threshold * median
    failures = np.sum(values > threshold_val)
    failure_rate = float(failures / len(values))

    return Statistics(
        n_seeds=len(results),
        mean=mean,
        std=std,
        median=median,
        p50=p50,
        p95=p95,
        min=min_val,
        max=max_val,
        cv=cv,
        skewness=skewness,
        kurtosis=kurtosis,
        failure_rate=failure_rate,
    )


def analyze_board(
    board_name: str,
    netlist: Netlist,
    board: Board,
    n_seeds: int,
    epochs: int,
) -> dict:
    """Analyze seed sensitivity for one board."""
    print(f"\n{'=' * 80}")
    print(f"Analyzing {board_name}")
    print(f"  Components: {len(netlist.components)}")
    print(f"  Seeds: {n_seeds}")
    print(f"  Epochs: {epochs}")
    print(f"{'=' * 80}")

    results = []

    for i in range(n_seeds):
        if (i + 1) % 10 == 0:
            print(f"  Progress: {i + 1}/{n_seeds} seeds...")

        result = run_single_seed(netlist, board, seed=i, epochs=epochs)
        results.append(result)

    print(f"  Completed {n_seeds} runs")

    # Compute statistics for each metric
    final_loss_stats = compute_statistics(results, "final_loss")
    overlap_stats = compute_statistics(results, "overlap_loss", failure_threshold=10.0)
    boundary_stats = compute_statistics(results, "boundary_loss", failure_threshold=10.0)
    wirelength_stats = compute_statistics(results, "wirelength")
    convergence_stats = compute_statistics(results, "convergence_epoch")

    # Count successful convergences
    convergence_count = sum(1 for r in results if r.converged)
    success_rate = convergence_count / len(results)

    # Build report
    report = {
        "n_seeds": n_seeds,
        "n_components": len(netlist.components),
        "success_rate": success_rate,
        "final_loss": {
            "mean": final_loss_stats.mean,
            "std": final_loss_stats.std,
            "cv": final_loss_stats.cv,
            "p50": final_loss_stats.p50,
            "p95": final_loss_stats.p95,
            "min": final_loss_stats.min,
            "max": final_loss_stats.max,
            "skewness": final_loss_stats.skewness,
            "kurtosis": final_loss_stats.kurtosis,
        },
        "overlap_loss": {
            "mean": overlap_stats.mean,
            "std": overlap_stats.std,
            "cv": overlap_stats.cv,
            "failure_rate": overlap_stats.failure_rate,
        },
        "boundary_loss": {
            "mean": boundary_stats.mean,
            "std": boundary_stats.std,
            "cv": boundary_stats.cv,
            "failure_rate": boundary_stats.failure_rate,
        },
        "wirelength": {
            "mean": wirelength_stats.mean,
            "std": wirelength_stats.std,
            "cv": wirelength_stats.cv,
        },
        "convergence_epoch": {
            "mean": convergence_stats.mean,
            "std": convergence_stats.std,
        },
    }

    # Print summary
    print("\n  Results Summary:")
    print(f"    Final Loss:    mean={final_loss_stats.mean:.2f}, CV={final_loss_stats.cv:.3f}")
    print(f"    Overlap Loss:  mean={overlap_stats.mean:.2f}, failure_rate={overlap_stats.failure_rate:.1%}")
    print(f"    Boundary Loss: mean={boundary_stats.mean:.2f}, failure_rate={boundary_stats.failure_rate:.1%}")
    print(f"    Success Rate:  {success_rate:.1%}")

    # Check acceptance criteria
    print("\n  Acceptance Criteria:")
    cv_pass = final_loss_stats.cv < 0.3
    failure_pass = final_loss_stats.failure_rate < 0.10

    print(f"    CV < 0.3:          {'✓ PASS' if cv_pass else '✗ FAIL'} (CV={final_loss_stats.cv:.3f})")
    print(f"    Failure rate < 10%: {'✓ PASS' if failure_pass else '✗ FAIL'} (rate={final_loss_stats.failure_rate:.1%})")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Analyze seed sensitivity across multiple PCBs"
    )
    parser.add_argument(
        "--boards",
        nargs="+",
        default=["piantor_left", "bitaxe_ultra", "libresolar_bms"],
        help="Board names to analyze",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        default=100,
        help="Number of seeds to test (default: 100)",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=400,
        help="Training epochs per run (default: 400)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("seed_sensitivity_report.yaml"),
        help="Output report file (default: seed_sensitivity_report.yaml)",
    )
    args = parser.parse_args()

    print("=" * 80)
    print("Seed Sensitivity Analysis (temper-1my.4.2)")
    print("=" * 80)
    print(f"Boards: {', '.join(args.boards)}")
    print(f"Seeds per board: {args.seeds}")
    print(f"Epochs per run: {args.epochs}")
    print(f"Total runs: {len(args.boards) * args.seeds}")
    print("=" * 80)

    all_results = {}

    for board_name in args.boards:
        # Load board
        board_path = Path(f"boards/{board_name}.kicad_pcb")

        if not board_path.exists():
            print(f"\n⚠️  Board file not found: {board_path}")
            print(f"   Skipping {board_name}")
            continue

        try:
            result = parse_kicad_pcb(board_path)
            netlist = result.netlist
            board = result.board

            # Analyze
            board_report = analyze_board(
                board_name,
                netlist,
                board,
                n_seeds=args.seeds,
                epochs=args.epochs,
            )

            all_results[board_name] = board_report

        except Exception as e:
            print(f"\n✗ Error analyzing {board_name}: {e}")
            import traceback
            traceback.print_exc()
            continue

    # Save report
    if all_results:
        with open(args.output, "w") as f:
            yaml.dump(all_results, f, default_flow_style=False, sort_keys=False)

        print(f"\n{'=' * 80}")
        print(f"Report saved to: {args.output}")
        print(f"{'=' * 80}")

        # Overall summary
        all_cv = [report["final_loss"]["cv"] for report in all_results.values()]
        all_success = [report["success_rate"] for report in all_results.values()]

        print("\nOverall Summary:")
        print(f"  Boards analyzed: {len(all_results)}")
        print(f"  Average CV: {np.mean(all_cv):.3f}")
        print(f"  Average success rate: {np.mean(all_success):.1%}")

        return 0
    else:
        print("\n✗ No boards successfully analyzed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
