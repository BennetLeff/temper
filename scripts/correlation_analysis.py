#!/usr/bin/env python3
"""
Correlation Analysis Script

Empirically determines which loss functions predict routing success by running
batch optimizations and correlating loss values with routing outcomes.

Usage:
    python scripts/correlation_analysis.py --pcb design.kicad_pcb --config constraints.yaml --samples 30
    python scripts/correlation_analysis.py --pcb design.kicad_pcb --samples 10 --quick
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


def run_single_optimization(args: tuple) -> OptimizationResult:
    """
    Run a single optimization with a given seed using CLI.

    Args:
        args: Tuple of (pcb_path, config_path, seed, output_dir)

    Returns:
        OptimizationResult with loss values and output path
    """
    pcb_path, config_path, seed, output_dir = args

    # Create unique output paths for this seed
    output_path = Path(output_dir) / f"placement_seed_{seed}.kicad_pcb"
    loss_history_path = Path(output_dir) / f"loss_history_seed_{seed}.json"

    try:
        print(f"  Starting optimization with seed {seed}...", flush=True)

        # Build command to run temper-placer optimize via CLI
        cmd = [
            sys.executable,
            "-m",
            "temper_placer.cli",
            "optimize",
            str(pcb_path),
            "-c",
            str(config_path) if config_path else "-",
            "-o",
            str(output_path),
            "--epochs",
            "50",  # Low epochs to maintain position variation across seeds
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
            return OptimizationResult(seed=seed, loss_values={}, output_pcb_path=output_path)

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

        return OptimizationResult(seed=seed, loss_values=loss_values, output_pcb_path=output_path)

    except Exception as e:
        print(f"Warning: Optimization with seed {seed} failed: {e}", file=sys.stderr)
        return OptimizationResult(seed=seed, loss_values={}, output_pcb_path=output_path)


def run_routing_verification(pcb_path: Path, quick: bool = False) -> Optional[RoutingResult]:
    """
    Run routing verification on a placed PCB.

    Args:
        pcb_path: Path to placed KiCad PCB
        quick: If True, use faster GEOMETRIC level; otherwise use MAZE level

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


def compute_correlations(
    loss_data: dict[str, list[float]], routing_data: dict[str, list[float]]
) -> dict[str, dict[str, float]]:
    """
    Compute Pearson correlations between loss values and routing metrics.

    Args:
        loss_data: Dict mapping loss name to list of values across samples
        routing_data: Dict mapping routing metric to list of values across samples

    Returns:
        Dict mapping loss name to dict of correlations vs each routing metric
    """
    correlations = {}

    for loss_name, loss_values in loss_data.items():
        if not loss_values or len(loss_values) < 3:
            continue  # Need at least 3 samples for correlation

        loss_corrs = {}
        for metric_name, metric_values in routing_data.items():
            if len(metric_values) != len(loss_values):
                continue

            try:
                r_value, p_value_result = stats.pearsonr(loss_values, metric_values)
                r = float(r_value)  # type: ignore
                p = float(p_value_result)  # type: ignore

                # Only include if statistically significant (p < 0.05)
                if p < 0.05:
                    loss_corrs[f"vs_{metric_name}"] = r
                else:
                    loss_corrs[f"vs_{metric_name}"] = 0.0  # Not significant
            except Exception:
                loss_corrs[f"vs_{metric_name}"] = 0.0

        if loss_corrs:
            correlations[loss_name] = loss_corrs

    return correlations


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
    pcb_path: Path, config_path: Optional[Path], n_samples: int, quick: bool = False
) -> CorrelationReport:
    """
    Run full correlation analysis.

    Args:
        pcb_path: Path to input KiCad PCB
        config_path: Path to constraints YAML (optional)
        n_samples: Number of optimization samples to run
        quick: If True, skip routing verification

    Returns:
        CorrelationReport with correlations and recommendations
    """
    print(f"Starting correlation analysis with {n_samples} samples...")
    print(f"Mode: {'quick (no routing)' if quick else 'full (with routing)'}")

    # Convert paths to absolute for subprocess calls
    pcb_path = pcb_path.resolve()
    if config_path:
        config_path = config_path.resolve()

    # Create temporary directory for outputs
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Step 1: Run batch optimizations in parallel
        print("\n[1/3] Running batch optimizations...")
        optimization_args = [
            (pcb_path, config_path, seed, temp_path) for seed in range(1, n_samples + 1)
        ]

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
            routing_result = run_routing_verification(opt_result.output_pcb_path, quick=quick)
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
            "failed_routes": sum(1 for r in routing_results if not r.routable),
        }

        print(f"\nFound {len(correlations)} loss functions with significant correlations")
        print(f"Generated {len(recommendations)} recommendations")

        return CorrelationReport(
            pcb=str(pcb_path),
            n_samples=len(routing_results),
            routing_mode="quick" if quick else "full",
            correlations=correlations,
            recommendations=recommendations,
            statistics=statistics,
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
    parser.add_argument("--output", type=Path, help="Output JSON file (default: stdout)")

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

    try:
        # Run analysis
        report = run_correlation_analysis(args.pcb, args.config, args.samples, quick=args.quick)

        # Convert to JSON
        report_json = {
            "pcb": report.pcb,
            "n_samples": report.n_samples,
            "routing_mode": report.routing_mode,
            "timestamp": datetime.now().isoformat(),
            "correlations": report.correlations,
            "recommendations": report.recommendations,
            "statistics": report.statistics,
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


if __name__ == "__main__":
    main()
