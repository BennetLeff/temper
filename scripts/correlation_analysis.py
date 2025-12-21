#!/usr/bin/env python3
"""
<<<<<<< HEAD
Correlation Analysis Script

Empirically determines which loss functions predict routing success by running
batch optimizations and correlating loss values with routing outcomes.

Usage:
    python scripts/correlation_analysis.py --pcb design.kicad_pcb --config constraints.yaml --samples 30
    python scripts/correlation_analysis.py --pcb design.kicad_pcb --samples 10 --quick
    python scripts/correlation_analysis.py --pcb design.kicad_pcb --samples 90 --epoch-tiers 25,100,200
"""

import argparse
import json
import multiprocessing as mp
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from scipy import stats

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "packages" / "temper-placer" / "src"))

from temper_placer.io.kicad_parser import parse_kicad_pcb
from temper_placer.routing.verifier import RoutingVerifier, RoutingVerifierConfig, VerificationLevel


@dataclass
class OptimizationResult:
    """Result from a single optimization run."""

    seed: int
    epochs: int
    loss_values: dict[str, float]
    output_pcb_path: Path


@dataclass
class RoutingResult:
    """Result from routing verification."""

    completion_pct: float
    wirelength_mm: float
    via_count: int
    routable: bool


@dataclass
class CorrelationReport:
    """Complete correlation analysis report."""

    pcb: str
    n_samples: int
    routing_mode: str
    correlations: dict[str, dict[str, float]]
    recommendations: list[dict[str, str]]
    statistics: dict[str, float]
    raw_data: Optional[dict[str, dict[str, list[float]]]] = None  # For inter-loss analysis


def perturb_positions(positions: np.ndarray, seed: int, magnitude: float = 2.0) -> np.ndarray:
    """
    Add random perturbation to component positions.

    This creates variance in optimized placements for correlation analysis
    when the optimizer converges to similar solutions across seeds.

    Args:
        positions: (N, 2) array of component positions in mm
        seed: Random seed for reproducibility
        magnitude: Max perturbation in mm (default 2mm). Set to 0 for no perturbation.

    Returns:
        Perturbed positions with noise in range [-magnitude, magnitude]

    Example:
        >>> positions = np.array([[50.0, 50.0], [25.0, 75.0]])
        >>> perturbed = perturb_positions(positions, seed=42, magnitude=2.0)
        >>> # Each component is shifted by up to 2mm in x and y
    """
    if magnitude == 0.0:
        return positions.copy()

    rng = np.random.default_rng(seed)
    noise = rng.uniform(-magnitude, magnitude, size=positions.shape)
    return positions + noise


def get_epochs_for_sample(
    sample_idx: int, epoch_tiers: Optional[list[int]] = None, n_samples: int = 90
) -> int:
    """
    Determine epoch count for a sample based on tier configuration.

    Args:
        sample_idx: 0-based sample index
        epoch_tiers: List of epoch counts for each tier (e.g., [25, 100, 200])
                    If None, returns default of 50 epochs.
        n_samples: Total number of samples (used to divide evenly across tiers)

    Returns:
        Number of epochs to use for this sample.

    Example:
        With epoch_tiers=[25, 100, 200] and 90 samples:
        - Samples 0-29: 25 epochs (under-optimized)
        - Samples 30-59: 100 epochs (standard)
        - Samples 60-89: 200 epochs (well-optimized)
    """
    if epoch_tiers is None:
        return 50  # Default

    n_tiers = len(epoch_tiers)
    samples_per_tier = n_samples // n_tiers
    tier_idx = sample_idx // samples_per_tier
    tier_idx = min(tier_idx, n_tiers - 1)  # Clamp to last tier
    return epoch_tiers[tier_idx]


def run_single_optimization(args: tuple) -> OptimizationResult:
    """
    Run a single optimization with a given seed using CLI.

    Args:
        args: Tuple of (pcb_path, config_path, seed, output_dir, epochs)

    Returns:
        OptimizationResult with loss values and output path
    """
    pcb_path, config_path, seed, output_dir, epochs = args

    # Create unique output paths for this seed
    output_path = Path(output_dir) / f"placement_seed_{seed}.kicad_pcb"
    loss_history_path = Path(output_dir) / f"loss_history_seed_{seed}.json"

    try:
        print(f"  Starting optimization with seed {seed}, epochs={epochs}...", flush=True)

        # Build command to run temper-placer optimize via CLI
        # Use the temper-placer command from venv instead of -m
        venv_bin = Path(sys.executable).parent
        temper_placer_cmd = venv_bin / "temper-placer"
        cmd = [
            str(temper_placer_cmd),
            "optimize",
            str(pcb_path),
            "-c",
            str(config_path) if config_path else "-",
            "-o",
            str(output_path),
            "--epochs",
            str(epochs),  # Use variable epochs
            "--seed",
            str(seed),
            "--loss-history",
            str(loss_history_path),
            "--no-heuristics",  # Disable deterministic heuristics for seed variation
        ]

        # Remove -c option if no config provided
        if not config_path:
            cmd = [c for i, c in enumerate(cmd) if c != "-c" and (i == 0 or cmd[i - 1] != "-c")]

        # Run optimizer (no cwd change - use absolute paths)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        print(f"  Seed {seed}: return code = {result.returncode}", flush=True)

        if result.returncode != 0:
            error_msg = f"Optimization with seed {seed} failed:\nSTDOUT: {result.stdout[:500]}\nSTDERR: {result.stderr[:500]}"
            print(f"Warning: {error_msg}", file=sys.stderr, flush=True)
            return OptimizationResult(
                seed=seed, epochs=epochs, loss_values={}, output_pcb_path=output_path
            )

        # Load loss history from JSON
        loss_values = {}
        if loss_history_path.exists():
            print(f"  Seed {seed}: loading loss history from {loss_history_path}", flush=True)
            with open(loss_history_path) as f:
                loss_history = json.load(f)

                # Handle new format: {"data_points": [{"epoch": ..., "breakdown": {...}}]}
                if isinstance(loss_history, dict) and "data_points" in loss_history:
                    data_points = loss_history["data_points"]
                    if len(data_points) > 0:
                        final_epoch = data_points[-1]
                        if "breakdown" in final_epoch:
                            # Extract non-normalized loss values
                            loss_values = {
                                k: float(v)
                                for k, v in final_epoch["breakdown"].items()
                                if isinstance(v, (int, float))
                                and not k.endswith("_normalized")
                                and not k.endswith("_weighted")
                            }
                            print(
                                f"  Seed {seed}: extracted {len(loss_values)} loss values",
                                flush=True,
                            )
                # Handle old format: [{"loss1": ..., "loss2": ...}, ...]
                elif isinstance(loss_history, list) and len(loss_history) > 0:
                    final_losses = loss_history[-1]
                    if isinstance(final_losses, dict):
                        loss_values = {
                            k: float(v)
                            for k, v in final_losses.items()
                            if isinstance(v, (int, float))
                        }
                        print(
                            f"  Seed {seed}: extracted {len(loss_values)} loss values", flush=True
                        )
        else:
            print(f"  Seed {seed}: loss history file not found!", flush=True)

        return OptimizationResult(
            seed=seed, epochs=epochs, loss_values=loss_values, output_pcb_path=output_path
        )

    except Exception as e:
        print(f"Warning: Optimization with seed {seed} failed: {e}", file=sys.stderr)
        return OptimizationResult(
            seed=seed, epochs=epochs, loss_values={}, output_pcb_path=output_path
        )


def run_routing_verification(
    pcb_path: Path,
    quick: bool = False,
    perturb_seed: Optional[int] = None,
    perturb_magnitude: float = 0.0,
) -> Optional[RoutingResult]:
    """
    Run routing verification on a placed PCB.

    Args:
        pcb_path: Path to placed KiCad PCB
        quick: If True, use faster GEOMETRIC level; otherwise use MAZE level
        perturb_seed: If provided, apply position perturbation with this seed
        perturb_magnitude: Max perturbation in mm (default 0 = no perturbation)

    Returns:
        RoutingResult or None if routing failed
    """
    try:
        # Import additional modules needed for routing
        from temper_placer.core.loop import LoopCollection
        import jax.numpy as jnp

        # Parse the placed PCB
        parse_result = parse_kicad_pcb(pcb_path)

        # Check that we have a valid board
        if parse_result.board is None:
            print(f"Warning: No board found in {pcb_path}", file=sys.stderr)
            return None

        # Extract positions from placed components
        positions = jnp.array([c.initial_position for c in parse_result.netlist.components])

        # Apply perturbation if requested (for variance in correlation analysis)
        if perturb_seed is not None and perturb_magnitude > 0:
            positions_np = np.array(positions)
            positions_np = perturb_positions(
                positions_np, seed=perturb_seed, magnitude=perturb_magnitude
            )
            positions = jnp.array(positions_np)

        # Create empty loop collection (no critical loops defined)
        loops = LoopCollection(loops=[])

        # Configure verifier based on quick mode
        if quick:
            # GEOMETRIC is faster but less accurate
            level = VerificationLevel.GEOMETRIC
        else:
            # MAZE does actual A* pathfinding
            level = VerificationLevel.MAZE

        config = RoutingVerifierConfig(
            level=level,
            cell_size_mm=1.0,  # 1mm grid for balance of speed/accuracy
            num_layers=2,
        )
        verifier = RoutingVerifier(config)

        # Run verification
        result = verifier.verify(
            netlist=parse_result.netlist,
            positions=positions,
            board=parse_result.board,
            loops=loops,
        )

        return RoutingResult(
            completion_pct=result.completion_rate * 100.0,
            wirelength_mm=result.total_wirelength,
            via_count=result.total_vias,
            routable=result.feasible,
        )

    except Exception as e:
        print(f"Warning: Routing verification failed for {pcb_path}: {e}", file=sys.stderr)
        return None


def bootstrap_correlation_ci(
    x: list[float],
    y: list[float],
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """
    Compute bootstrap confidence interval for Pearson correlation.

    Args:
        x: First variable values
        y: Second variable values
        n_bootstrap: Number of bootstrap samples
        confidence: Confidence level (default 0.95 for 95% CI)

    Returns:
        Tuple of (lower_bound, upper_bound) for the correlation CI
    """
    n = len(x)
    if n < 3:
        return (0.0, 0.0)

    x_arr = np.array(x)
    y_arr = np.array(y)
    bootstrap_rs = []

    rng = np.random.default_rng(42)  # Reproducible bootstrap
    for _ in range(n_bootstrap):
        indices = rng.choice(n, size=n, replace=True)
        x_sample = x_arr[indices]
        y_sample = y_arr[indices]

        # Check for constant samples (can't compute correlation)
        if np.std(x_sample) < 1e-10 or np.std(y_sample) < 1e-10:
            continue

        try:
            result = stats.pearsonr(x_sample, y_sample)
            r = float(result.statistic)  # type: ignore[union-attr]
            bootstrap_rs.append(r)
        except Exception:
            continue

    if len(bootstrap_rs) < n_bootstrap * 0.5:
        return (0.0, 0.0)  # Too many failures

    bootstrap_rs.sort()
    alpha = 1 - confidence
    lower_idx = int(len(bootstrap_rs) * alpha / 2)
    upper_idx = int(len(bootstrap_rs) * (1 - alpha / 2))

    return (bootstrap_rs[lower_idx], bootstrap_rs[upper_idx])


def holm_bonferroni_correction(
    p_values: list[float], alpha: float = 0.05
) -> list[tuple[float, bool, float]]:
    """
    Apply Holm-Bonferroni correction for multiple comparisons (step-down procedure).

    More powerful than Bonferroni while still controlling family-wise error rate.

    Args:
        p_values: List of p-values from multiple tests
        alpha: Overall significance level

    Returns:
        List of (p_value, significant, adjusted_alpha) tuples in original order
    """
    m = len(p_values)
    if m == 0:
        return []

    # Index and sort by p-value
    indexed = [(p, i) for i, p in enumerate(p_values)]
    indexed.sort()

    results: list[tuple[float, bool, float]] = [(0.0, False, 0.0)] * m
    rejected = True

    for rank, (p, orig_idx) in enumerate(indexed, 1):
        adjusted_alpha = alpha / (m - rank + 1)
        if rejected and p < adjusted_alpha:
            results[orig_idx] = (p, True, adjusted_alpha)
        else:
            rejected = False
            results[orig_idx] = (p, False, adjusted_alpha)

    return results


@dataclass
class CorrelationResult:
    """Detailed result for a single correlation test."""

    loss_name: str
    metric_name: str
    r: float
    p_value: float
    significant: bool
    corrected_alpha: float
    ci_lower: float
    ci_upper: float


def compute_correlations(
    loss_data: dict[str, list[float]], routing_data: dict[str, list[float]]
) -> dict[str, dict[str, float]]:
    """
    Compute Pearson correlations between loss values and routing metrics.

    Uses Holm-Bonferroni correction for multiple comparisons and reports
    bootstrap confidence intervals.

    Args:
        loss_data: Dict mapping loss name to list of values across samples
        routing_data: Dict mapping routing metric to list of values across samples

    Returns:
        Dict mapping loss name to dict of correlations vs each routing metric
    """
    correlations = {}

    # First pass: collect all p-values for correction
    all_tests: list[CorrelationResult] = []

    for loss_name, loss_values in loss_data.items():
        if not loss_values or len(loss_values) < 3:
            continue  # Need at least 3 samples for correlation

        # Skip constant losses (std = 0) - they cannot correlate with anything
        loss_std = np.std(loss_values)
        if loss_std < 1e-10:
            print(f"  Skipping constant loss '{loss_name}' (std={loss_std:.2e})", flush=True)
            continue

        for metric_name, metric_values in routing_data.items():
            if len(metric_values) != len(loss_values):
                continue

            try:
                result = stats.pearsonr(loss_values, metric_values)
                r = float(result.statistic)  # type: ignore[union-attr]
                p = float(result.pvalue)  # type: ignore[union-attr]

                # Compute bootstrap CI
                ci_lower, ci_upper = bootstrap_correlation_ci(loss_values, metric_values)

                all_tests.append(
                    CorrelationResult(
                        loss_name=loss_name,
                        metric_name=metric_name,
                        r=r,
                        p_value=p,
                        significant=False,  # Will be updated after correction
                        corrected_alpha=0.05,  # Will be updated
                        ci_lower=ci_lower,
                        ci_upper=ci_upper,
                    )
                )
            except Exception:
                pass

    # Apply Holm-Bonferroni correction
    if all_tests:
        p_values = [t.p_value for t in all_tests]
        corrections = holm_bonferroni_correction(p_values, alpha=0.05)

        for i, (p, sig, adj_alpha) in enumerate(corrections):
            all_tests[i].significant = sig
            all_tests[i].corrected_alpha = adj_alpha

        # Report multiple comparison correction
        n_sig_before = sum(1 for t in all_tests if t.p_value < 0.05)
        n_sig_after = sum(1 for t in all_tests if t.significant)
        if n_sig_before != n_sig_after:
            print(
                f"  Multiple comparison correction: {n_sig_before} -> {n_sig_after} significant tests "
                f"(Holm-Bonferroni, family α=0.05)",
                flush=True,
            )

    # Build output dictionary
    for test in all_tests:
        if test.loss_name not in correlations:
            correlations[test.loss_name] = {}

        key = f"vs_{test.metric_name}"
        if test.significant:
            correlations[test.loss_name][key] = test.r
            # Also store CI for significant results
            correlations[test.loss_name][f"{key}_ci"] = [test.ci_lower, test.ci_upper]
        else:
            correlations[test.loss_name][key] = 0.0  # Not significant after correction

    return correlations


def compute_inter_loss_correlations(
    loss_data: dict[str, list[float]],
) -> dict[str, dict[str, float]]:
    """
    Compute pairwise Pearson correlations between all loss functions.

    This helps identify confounded losses (pairs that correlate strongly
    with each other, meaning they may measure similar things).

    Args:
        loss_data: Dict mapping loss name to list of values across samples

    Returns:
        Dict mapping loss_a -> loss_b -> correlation coefficient
        The matrix is symmetric (r(a,b) == r(b,a)) with diagonal = 1.0
    """
    loss_names = sorted(loss_data.keys())
    matrix: dict[str, dict[str, float]] = {}

    for loss_a in loss_names:
        matrix[loss_a] = {}
        values_a = loss_data[loss_a]

        # Skip if too few samples or constant
        if len(values_a) < 3 or np.std(values_a) < 1e-10:
            for loss_b in loss_names:
                matrix[loss_a][loss_b] = 0.0 if loss_a != loss_b else 1.0
            continue

        for loss_b in loss_names:
            if loss_a == loss_b:
                matrix[loss_a][loss_b] = 1.0
                continue

            values_b = loss_data[loss_b]

            # Skip if constant or length mismatch
            if len(values_b) != len(values_a) or np.std(values_b) < 1e-10:
                matrix[loss_a][loss_b] = 0.0
                continue

            try:
                result = stats.pearsonr(values_a, values_b)
                r_value = result[0]  # correlation coefficient
                matrix[loss_a][loss_b] = float(r_value)  # type: ignore[arg-type]
            except Exception:
                matrix[loss_a][loss_b] = 0.0

    return matrix


def generate_recommendations(correlations: dict[str, dict[str, float]]) -> list[dict[str, str]]:
    """
    Generate actionable recommendations based on correlation coefficients.

    Args:
        correlations: Dict mapping loss name to correlations vs routing metrics

    Returns:
        List of recommendation dicts with loss, action, and reason
    """
    recommendations = []

    for loss_name, loss_corrs in correlations.items():
        # Focus on correlation with completion (most important metric)
        r_completion = loss_corrs.get("vs_completion", 0.0)
        abs_r = abs(r_completion)

        # Generate action based on correlation strength
        if abs_r > 0.7:
            # Strong correlation
            if r_completion < 0:
                action = "increase"
                reason = f"Strong negative correlation with completion (r={r_completion:.2f}) - this loss blocks routing"
            else:
                action = "keep"
                reason = f"Strong positive correlation with completion (r={r_completion:.2f})"
        elif abs_r >= 0.3:
            # Moderate correlation
            action = "keep"
            reason = f"Moderate correlation with completion (r={r_completion:.2f})"
        else:
            # Weak correlation
            action = "review"
            reason = f"Weak correlation with routing metrics (r={r_completion:.2f}) - may not impact routability"

        recommendations.append({"loss": loss_name, "action": action, "reason": reason})

    return recommendations


def run_correlation_analysis(
    pcb_path: Path,
    config_path: Optional[Path],
    n_samples: int,
    quick: bool = False,
    epoch_tiers: Optional[list[int]] = None,
    perturb_magnitude: float = 0.0,
) -> CorrelationReport:
    """
    Run full correlation analysis.

    Args:
        pcb_path: Path to input KiCad PCB
        config_path: Path to constraints YAML (optional)
        n_samples: Number of optimization samples to run
        quick: If True, skip routing verification
        epoch_tiers: List of epoch counts for variance experiment (e.g., [25, 100, 200])
        perturb_magnitude: Max position perturbation in mm (default 0 = no perturbation)

    Returns:
        CorrelationReport with correlations and recommendations
    """
    print(f"Starting correlation analysis with {n_samples} samples...")
    print(f"Mode: {'quick (no routing)' if quick else 'full (with routing)'}")
    if epoch_tiers:
        print(f"Epoch tiers: {epoch_tiers} (samples per tier: {n_samples // len(epoch_tiers)})")
    if perturb_magnitude > 0:
        print(f"Position perturbation: ±{perturb_magnitude}mm")

    # Convert paths to absolute for subprocess calls
    pcb_path = pcb_path.resolve()
    if config_path:
        config_path = config_path.resolve()

    # Create temporary directory for outputs
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Step 1: Run batch optimizations in parallel
        print("\n[1/3] Running batch optimizations...")
        optimization_args = []
        for idx, seed in enumerate(range(1, n_samples + 1)):
            epochs = get_epochs_for_sample(idx, epoch_tiers, n_samples)
            optimization_args.append((pcb_path, config_path, seed, temp_path, epochs))

        # Run optimizations sequentially for now (multiprocessing has issues with subprocess)
        optimization_results = []
        for args in optimization_args:
            result = run_single_optimization(args)
            optimization_results.append(result)

        # Filter out failed runs
        valid_results = [r for r in optimization_results if r.loss_values]
        print(f"Completed {len(valid_results)}/{n_samples} optimizations successfully")

        if len(valid_results) < 3:
            raise ValueError("Too few successful optimizations (need at least 3 for correlation)")

        # Step 2: Run routing verification (or skip with --quick)
        print("\n[2/3] Running routing verification...")
        routing_results = []
        for opt_result in valid_results:
            # Use seed as perturb_seed for reproducibility
            routing_result = run_routing_verification(
                opt_result.output_pcb_path,
                quick=quick,
                perturb_seed=opt_result.seed if perturb_magnitude > 0 else None,
                perturb_magnitude=perturb_magnitude,
            )
            if routing_result:
                routing_results.append(routing_result)

        print(
            f"Completed {len(routing_results)}/{len(valid_results)} routing verifications successfully"
        )

        if len(routing_results) < 3:
            raise ValueError("Too few successful routing runs (need at least 3 for correlation)")

        # Step 3: Compute correlations
        print("\n[3/3] Computing correlations...")

        # Aggregate loss values across samples
        loss_data = {}
        for opt_result in valid_results[: len(routing_results)]:  # Match routing results length
            for loss_name, loss_value in opt_result.loss_values.items():
                if loss_name not in loss_data:
                    loss_data[loss_name] = []
                loss_data[loss_name].append(loss_value)

        # Aggregate routing metrics
        routing_data = {
            "completion": [r.completion_pct for r in routing_results],
            "wirelength": [r.wirelength_mm for r in routing_results],
            "via_count": [float(r.via_count) for r in routing_results],
        }

        # Compute correlations
        correlations = compute_correlations(loss_data, routing_data)

        # Generate recommendations
        recommendations = generate_recommendations(correlations)

        # Compute statistics
        completion_values = routing_data["completion"]
        statistics = {
            "mean_completion_pct": float(np.mean(completion_values)),
            "std_completion_pct": float(np.std(completion_values, ddof=1)),
            "min_completion_pct": float(np.min(completion_values)),
            "max_completion_pct": float(np.max(completion_values)),
            "failed_routes": sum(1 for r in routing_results if not r.routable),
            "samples_above_50pct": sum(1 for c in completion_values if c > 50.0),
        }

        # Add per-tier statistics if using epoch tiers
        if epoch_tiers:
            matched_results = list(zip(valid_results[: len(routing_results)], routing_results))
            tier_stats = {}
            for tier_idx, tier_epochs in enumerate(epoch_tiers):
                tier_completions = [
                    rr.completion_pct for opt, rr in matched_results if opt.epochs == tier_epochs
                ]
                if tier_completions:
                    tier_stats[f"tier_{tier_epochs}_epochs"] = {
                        "n": len(tier_completions),
                        "mean": float(np.mean(tier_completions)),
                        "std": float(np.std(tier_completions, ddof=1))
                        if len(tier_completions) > 1
                        else 0.0,
                        "min": float(np.min(tier_completions)),
                        "max": float(np.max(tier_completions)),
                    }
            statistics["tier_breakdown"] = tier_stats

        print(f"\nFound {len(correlations)} loss functions with significant correlations")
        print(f"Generated {len(recommendations)} recommendations")
        print(
            f"Routing completion: mean={statistics['mean_completion_pct']:.1f}%, std={statistics['std_completion_pct']:.1f}%"
        )
        print(
            f"Range: {statistics['min_completion_pct']:.1f}% - {statistics['max_completion_pct']:.1f}%"
        )
        print(f"Samples >50% completion: {statistics['samples_above_50pct']}")

        # Build raw_data for downstream analysis (e.g., inter-loss correlations)
        raw_data = {
            "losses": loss_data,
            "routing": routing_data,
        }

        return CorrelationReport(
            pcb=str(pcb_path),
            n_samples=len(routing_results),
            routing_mode="quick" if quick else "full",
            correlations=correlations,
            recommendations=recommendations,
            statistics=statistics,
            raw_data=raw_data,
        )


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Correlation analysis between placement losses and routing outcomes"
    )
    parser.add_argument("--pcb", type=Path, required=True, help="Path to KiCad PCB file")
    parser.add_argument("--config", type=Path, help="Path to constraints YAML file (optional)")
    parser.add_argument(
        "--samples", type=int, default=30, help="Number of optimization samples (default: 30)"
    )
    parser.add_argument(
        "--quick", action="store_true", help="Skip routing verification for faster iteration"
    )
    parser.add_argument(
        "--epoch-tiers",
        type=str,
        help="Comma-separated epoch counts for variance experiment (e.g., '25,100,200'). "
        "Samples will be split evenly across tiers.",
    )
    parser.add_argument("--output", type=Path, help="Output JSON file (default: stdout)")
    parser.add_argument(
        "--perturb",
        type=float,
        default=0.0,
        help="Apply random position perturbation (in mm) after optimization. "
        "Useful when optimizer converges to similar placements. Default: 0 (disabled).",
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.pcb.exists():
        print(f"Error: PCB file not found: {args.pcb}", file=sys.stderr)
        sys.exit(1)

    if args.config and not args.config.exists():
        print(f"Error: Config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    if args.samples < 3:
        print("Error: Need at least 3 samples for correlation analysis", file=sys.stderr)
        sys.exit(1)

    # Parse epoch tiers
    epoch_tiers = None
    if args.epoch_tiers:
        try:
            epoch_tiers = [int(x.strip()) for x in args.epoch_tiers.split(",")]
            if len(epoch_tiers) < 2:
                print("Error: --epoch-tiers requires at least 2 tiers", file=sys.stderr)
                sys.exit(1)
            # Validate sample count is divisible by tiers (or close to it)
            samples_per_tier = args.samples // len(epoch_tiers)
            if samples_per_tier < 3:
                print(
                    f"Error: Need at least 3 samples per tier. "
                    f"With {len(epoch_tiers)} tiers, need at least {3 * len(epoch_tiers)} samples.",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(f"Using epoch tiers: {epoch_tiers} ({samples_per_tier} samples per tier)")
        except ValueError:
            print(f"Error: Invalid epoch-tiers format: {args.epoch_tiers}", file=sys.stderr)
            sys.exit(1)

    try:
        # Run analysis
        report = run_correlation_analysis(
            args.pcb,
            args.config,
            args.samples,
            quick=args.quick,
            epoch_tiers=epoch_tiers,
            perturb_magnitude=args.perturb,
        )

        # Convert to JSON
        report_json = {
            "pcb": report.pcb,
            "n_samples": report.n_samples,
            "routing_mode": report.routing_mode,
            "timestamp": datetime.now().isoformat(),
            "correlations": report.correlations,
            "recommendations": report.recommendations,
            "statistics": report.statistics,
            "raw_data": report.raw_data,
        }

        # Output
        if args.output:
            with open(args.output, "w") as f:
                json.dump(report_json, f, indent=2)
            print(f"\nCorrelation report saved to: {args.output}")
        else:
            print("\n" + json.dumps(report_json, indent=2))

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

=======
Correlation analysis script for placement losses vs routing success.
Identifies which loss functions are best predictors of routability.
"""

import json
import math
from pathlib import Path
import argparse
import sys

def parse_args():
    parser = argparse.ArgumentParser(description="Analyze correlation between placement losses and routing")
    parser.add_argument("--data", type=str, default="metrics/measurements.jsonl", help="Path to measurements.jsonl")
    return parser.parse_args()

def calculate_correlation(x, y):
    """Simple Pearson correlation coefficient."""
    n = len(x)
    if n < 2: return 0.0
    
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    
    numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    sum_sq_x = sum((x[i] - mean_x)**2 for i in range(n))
    sum_sq_y = sum((y[i] - mean_y)**2 for i in range(n))
    
    if sum_sq_x == 0 or sum_sq_y == 0:
        return 0.0
        
    return numerator / math.sqrt(sum_sq_x * sum_sq_y)

def main():
    args = parse_args()
    data_path = Path(args.data)
    
    if not data_path.exists():
        print(f"Error: Data file not found: {data_path}")
        return

    # Load and group data by task
    tasks = {}
    with open(data_path) as f:
        for line in f:
            try:
                record = json.loads(line)
                task_id = record.get("task")
                if not task_id: continue
                
                if task_id not in tasks:
                    tasks[task_id] = {}
                
                tasks[task_id][record["metric"]] = record["value"]
            except:
                continue

    # Identify relevant metrics
    all_metrics = set().union(*[t.keys() for t in tasks.values()])
    placer_metrics = [m for m in all_metrics if m.startswith("placer_")]
    routing_success = "routing_completion_pct"
    
    if not routing_success in set().union(*[t.keys() for t in tasks.values()]):
        print(f"Error: {routing_success} not found in data. Run more routing evaluations first.")
        return

    print(f"Analyzing correlation with {routing_success} across {len(tasks)} tasks...\n")
    print(f"{'Metric':<30} | {'Correlation':<12}")
    print("-" * 45)

    correlations = []
    for metric in placer_metrics:
        x, y = [], []
        for t_id, metrics in tasks.items():
            if metric in metrics and routing_success in metrics:
                x.append(metrics[metric])
                y.append(metrics[routing_success])
        
        if len(x) >= 3:
            corr = calculate_correlation(x, y)
            correlations.append((metric, corr))

    # Sort by absolute correlation
    correlations.sort(key=lambda c: abs(c[1]), reverse=True)

    for metric, corr in correlations:
        print(f"{metric:<30} | {corr:>11.4f}")
>>>>>>> 2d319f0 (feat(placer): NSGA-II, Crawler, NetCentroidLoss, and structural refinements)

if __name__ == "__main__":
    main()
