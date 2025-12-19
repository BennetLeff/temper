"""
Weight grid search experiment framework for loss function tuning.

This module provides infrastructure for systematically searching over loss weight
configurations to find optimal hyperparameters that maximize DRC pass rate and
minimize wirelength.

The search uses a grid over 5 key loss weights:
- overlap_weight: Hard constraint penalty for overlapping components
- boundary_weight: Hard constraint penalty for out-of-bounds placement
- clearance_weight: Soft constraint for HV-LV clearance (most DRC-correlated)
- wirelength_weight: Objective for minimizing total wire length
- thermal_weight: Objective for thermal management

Usage:
    python -m temper_placer.experiments.weight_search \
        --pcbs piantor_left,piantor_right,bitaxe_ultra \
        --epochs 2000 \
        --parallel 4 \
        --output results/weight_search.json
"""

from __future__ import annotations

import json
import multiprocessing as mp
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import jax.numpy as jnp
import numpy as np
from tqdm import tqdm


@dataclass
class WeightConfig:
    """Configuration of loss function weights to evaluate."""

    overlap_weight: float
    boundary_weight: float
    clearance_weight: float
    wirelength_weight: float
    thermal_weight: float

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, float]) -> WeightConfig:
        """Create from dictionary."""
        return cls(**d)

    def __str__(self) -> str:
        return (
            f"O:{self.overlap_weight}, B:{self.boundary_weight}, "
            f"C:{self.clearance_weight}, W:{self.wirelength_weight}, "
            f"T:{self.thermal_weight}"
        )


@dataclass
class PCBResult:
    """Result of running optimizer on a single PCB with specific weights."""

    pcb_name: str
    weight_config: WeightConfig
    drc_errors: int
    wirelength_ratio: float  # final_length / reference_length
    quality_score: float  # aggregate quality metric
    convergence_epoch: int  # epoch where loss plateaued
    final_loss: float
    runtime_seconds: float

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "pcb_name": self.pcb_name,
            "weight_config": self.weight_config.to_dict(),
            "drc_errors": self.drc_errors,
            "wirelength_ratio": self.wirelength_ratio,
            "quality_score": self.quality_score,
            "convergence_epoch": self.convergence_epoch,
            "final_loss": self.final_loss,
            "runtime_seconds": self.runtime_seconds,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> PCBResult:
        """Create from dictionary."""
        return cls(
            pcb_name=d["pcb_name"],
            weight_config=WeightConfig.from_dict(d["weight_config"]),
            drc_errors=d["drc_errors"],
            wirelength_ratio=d["wirelength_ratio"],
            quality_score=d["quality_score"],
            convergence_epoch=d["convergence_epoch"],
            final_loss=d["final_loss"],
            runtime_seconds=d["runtime_seconds"],
        )


def score_config(results: List[PCBResult]) -> float:
    """
    Compute aggregate score for a weight configuration across multiple PCBs.

    Scoring function:
    - Primary: DRC pass rate (must be high, 10x weight)
    - Secondary: Wirelength quality (lower ratio is better)
    - Tertiary: Quality score (higher is better)

    Args:
        results: List of PCBResult for different boards with same weight config.

    Returns:
        Aggregate score (higher is better).
    """
    if not results:
        return 0.0

    # Primary: DRC pass rate
    drc_pass_count = sum(1 for r in results if r.drc_errors == 0)
    drc_pass_rate = drc_pass_count / len(results)

    # Secondary: Mean wirelength ratio (only for passing boards)
    passing_results = [r for r in results if r.drc_errors == 0]
    if passing_results:
        mean_wl_ratio = np.mean([r.wirelength_ratio for r in passing_results])
        # Convert to score: 1.0 is perfect, higher ratios get lower score
        wl_score = max(0.0, 2.0 - mean_wl_ratio)
    else:
        wl_score = 0.0

    # Tertiary: Mean quality score (only for passing boards)
    if passing_results:
        mean_quality = np.mean([r.quality_score for r in passing_results])
        quality_normalized = mean_quality / 100.0  # Assume quality scores are 0-100
    else:
        quality_normalized = 0.0

    # Weighted combination: DRC is 10x more important than wirelength
    total_score = 10.0 * drc_pass_rate + wl_score + 0.5 * quality_normalized

    return float(total_score)


def run_single_experiment(
    pcb_path: Path,
    weight_config: WeightConfig,
    epochs: int,
    seed: int,
    use_heuristics: bool,
    use_curriculum: bool,
) -> PCBResult:
    """
    Run optimizer on a single PCB with specific weight configuration.

    Args:
        pcb_path: Path to .kicad_pcb file.
        weight_config: Loss weights to use.
        epochs: Number of optimization epochs.
        seed: Random seed for reproducibility.
        use_heuristics: Whether to use smart initialization.
        use_curriculum: Whether to use curriculum learning.

    Returns:
        PCBResult with optimization metrics.
    """
    import time

    # Import will be implemented - placeholder for now
    # from temper_placer.cli import optimize_pcb_with_config

    start_time = time.time()

    try:
        # TODO: Implement optimize_pcb_with_config wrapper in CLI
        # For now, return placeholder result
        # When implemented, this will call the actual optimizer with weight overrides

        runtime = time.time() - start_time

        # Placeholder result - to be replaced with actual optimization
        return PCBResult(
            pcb_name=pcb_path.stem,
            weight_config=weight_config,
            drc_errors=0,  # Placeholder
            wirelength_ratio=1.0,  # Placeholder
            quality_score=100.0,  # Placeholder
            convergence_epoch=epochs,  # Placeholder
            final_loss=0.0,  # Placeholder
            runtime_seconds=runtime,
        )

    except Exception as e:
        # Return failure result
        runtime = time.time() - start_time
        return PCBResult(
            pcb_name=pcb_path.stem,
            weight_config=weight_config,
            drc_errors=999,  # Indicate failure
            wirelength_ratio=99.99,
            quality_score=0.0,
            convergence_epoch=-1,
            final_loss=float("inf"),
            runtime_seconds=runtime,
        )


def run_weight_search(
    pcb_paths: List[Path],
    weight_space: Dict[str, List[float]],
    epochs: int = 2000,
    parallel: int = 4,
    output_path: Optional[Path] = None,
    use_heuristics: bool = True,
    use_curriculum: bool = True,
    seed: int = 42,
) -> List[Tuple[WeightConfig, List[PCBResult], float]]:
    """
    Run grid search over loss weight configurations.

    Args:
        pcb_paths: List of paths to .kicad_pcb files to test on.
        weight_space: Dict mapping weight names to lists of values to try.
        epochs: Number of optimization epochs per trial.
        parallel: Number of parallel workers.
        output_path: Optional path to save results JSON.
        use_heuristics: Use smart initialization.
        use_curriculum: Use curriculum learning.
        seed: Base random seed (incremented per trial).

    Returns:
        List of (WeightConfig, List[PCBResult], aggregate_score) tuples,
        sorted by aggregate score (best first).
    """
    # Generate all weight combinations
    weight_names = [
        "overlap_weight",
        "boundary_weight",
        "clearance_weight",
        "wirelength_weight",
        "thermal_weight",
    ]
    weight_values = [weight_space[name] for name in weight_names]
    all_combinations = list(product(*weight_values))

    print(f"Testing {len(all_combinations)} weight configurations on {len(pcb_paths)} PCBs")
    print(f"Total trials: {len(all_combinations) * len(pcb_paths)}")
    print(f"Parallel workers: {parallel}")

    # Create weight configs
    weight_configs = [
        WeightConfig(
            overlap_weight=combo[0],
            boundary_weight=combo[1],
            clearance_weight=combo[2],
            wirelength_weight=combo[3],
            thermal_weight=combo[4],
        )
        for combo in all_combinations
    ]

    # Run experiments
    all_results: Dict[int, List[PCBResult]] = {i: [] for i in range(len(weight_configs))}

    # Prepare experiment arguments
    experiment_args = []
    for config_idx, config in enumerate(weight_configs):
        for pcb_idx, pcb_path in enumerate(pcb_paths):
            trial_seed = seed + config_idx * len(pcb_paths) + pcb_idx
            experiment_args.append(
                (pcb_path, config, epochs, trial_seed, use_heuristics, use_curriculum)
            )

    # Run in parallel
    if parallel > 1:
        with mp.Pool(parallel) as pool:
            results_flat = list(
                tqdm(
                    pool.starmap(run_single_experiment, experiment_args),
                    total=len(experiment_args),
                    desc="Running experiments",
                )
            )
    else:
        results_flat = [
            run_single_experiment(*args)
            for args in tqdm(experiment_args, desc="Running experiments")
        ]

    # Group results by weight configuration
    for result_idx, result in enumerate(results_flat):
        config_idx = result_idx // len(pcb_paths)
        all_results[config_idx].append(result)

    # Score each configuration
    scored_configs: List[Tuple[WeightConfig, List[PCBResult], float]] = []
    for config_idx, config in enumerate(weight_configs):
        results = all_results[config_idx]
        score = score_config(results)
        scored_configs.append((config, results, score))

    # Sort by score (best first)
    scored_configs.sort(key=lambda x: x[2], reverse=True)

    # Save results if output path specified
    if output_path:
        output_data = {
            "weight_space": weight_space,
            "epochs": epochs,
            "use_heuristics": use_heuristics,
            "use_curriculum": use_curriculum,
            "seed": seed,
            "results": [
                {
                    "config": config.to_dict(),
                    "score": score,
                    "pcb_results": [r.to_dict() for r in results],
                }
                for config, results, score in scored_configs
            ],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"\nResults saved to {output_path}")

    return scored_configs


def print_top_configs(
    scored_configs: List[Tuple[WeightConfig, List[PCBResult], float]],
    top_k: int = 10,
) -> None:
    """
    Print summary of top-k weight configurations.

    Args:
        scored_configs: List of (config, results, score) sorted by score.
        top_k: Number of top configurations to print.
    """
    print("\n" + "=" * 80)
    print("WEIGHT SEARCH RESULTS")
    print("=" * 80)
    print(f"Total configurations tested: {len(scored_configs)}")

    # Count configs with 100% DRC pass
    perfect_configs = [
        (config, results, score)
        for config, results, score in scored_configs
        if all(r.drc_errors == 0 for r in results)
    ]
    print(f"Configurations with 100% DRC pass: {len(perfect_configs)}")

    print(f"\nTop {top_k} Configurations:")
    print("-" * 80)
    print(f"{'Rank':<6} {'DRC Pass':<10} {'Avg WL Ratio':<14} {'Score':<8} {'Weights'}")
    print("-" * 80)

    for rank, (config, results, score) in enumerate(scored_configs[:top_k], 1):
        drc_pass_count = sum(1 for r in results if r.drc_errors == 0)
        drc_pass_pct = f"{100 * drc_pass_count / len(results):.0f}%"

        passing_results = [r for r in results if r.drc_errors == 0]
        if passing_results:
            avg_wl = np.mean([r.wirelength_ratio for r in passing_results])
            avg_wl_str = f"{avg_wl:.3f}x"
        else:
            avg_wl_str = "N/A"

        print(
            f"{rank:<6} {drc_pass_pct:<10} {avg_wl_str:<14} {score:<8.2f} "
            f"O={config.overlap_weight}, B={config.boundary_weight}, "
            f"C={config.clearance_weight}, W={config.wirelength_weight}, "
            f"T={config.thermal_weight}"
        )

    # Print recommended production weights
    if scored_configs:
        best_config, _, best_score = scored_configs[0]
        print("\n" + "=" * 80)
        print("RECOMMENDED PRODUCTION WEIGHTS")
        print("=" * 80)
        print(f"  overlap_weight: {best_config.overlap_weight}")
        print(f"  boundary_weight: {best_config.boundary_weight}")
        print(f"  clearance_weight: {best_config.clearance_weight}")
        print(f"  wirelength_weight: {best_config.wirelength_weight}")
        print(f"  thermal_weight: {best_config.thermal_weight}")
        print(f"\nAggregate Score: {best_score:.2f}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run weight grid search experiment")
    parser.add_argument(
        "--pcbs",
        type=str,
        required=True,
        help="Comma-separated list of PCB names or paths",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=2000,
        help="Number of optimization epochs per trial",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=4,
        help="Number of parallel workers",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/weight_search.json"),
        help="Output JSON file path",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Base random seed",
    )
    parser.add_argument(
        "--no-heuristics",
        action="store_true",
        help="Disable smart initialization",
    )
    parser.add_argument(
        "--no-curriculum",
        action="store_true",
        help="Disable curriculum learning",
    )

    args = parser.parse_args()

    # Parse PCB paths
    pcb_names = args.pcbs.split(",")
    pcb_paths = [Path(name.strip()) for name in pcb_names]

    # Default weight search space (from issue requirements)
    WEIGHT_SPACE: Dict[str, List[float]] = {
        "overlap_weight": [50.0, 100.0, 150.0, 200.0],
        "boundary_weight": [25.0, 50.0, 75.0, 100.0],
        "clearance_weight": [100.0, 150.0, 200.0, 300.0],
        "wirelength_weight": [1.0, 5.0, 10.0, 20.0],
        "thermal_weight": [0.0, 10.0, 25.0, 50.0],
    }

    # Run search
    scored_configs = run_weight_search(
        pcb_paths=pcb_paths,
        weight_space=WEIGHT_SPACE,
        epochs=args.epochs,
        parallel=args.parallel,
        output_path=args.output,
        use_heuristics=not args.no_heuristics,
        use_curriculum=not args.no_curriculum,
        seed=args.seed,
    )

    # Print results
    print_top_configs(scored_configs, top_k=10)
