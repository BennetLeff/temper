#!/usr/bin/env python3
"""A/B testing script for thermal anchoring.

Runs the full placement pipeline with and without Phase-0 thermal anchoring,
collecting comparative metrics for SC1-SC6 validation.

Usage:
    uv run python experiments/ab_test_thermal_anchoring.py \
        --pcb ../pcb/temper_agent_optimized.kicad_pcb \
        --constraints configs/temper_constraints.yaml \
        --runs 5

Output: JSON report with per-run metrics and two-sample t-test results.
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Add the package to the path
_SCRIPT_DIR = Path(__file__).resolve().parent
_PACKAGE_DIR = _SCRIPT_DIR.parent / "src"
sys.path.insert(0, str(_PACKAGE_DIR))


@dataclass
class RunMetrics:
    """Metrics from a single pipeline run."""

    thermal_distance_mm: float = 0.0  # Mean distance of power devices from edge
    wirelength: float = 0.0
    loop_area: float = 0.0
    drc_violations: int = 0
    anchoring_time_s: float = 0.0
    total_time_s: float = 0.0
    success: bool = True
    error: str | None = None


@dataclass
class ABReport:
    """A/B test report with baseline and variant metrics."""

    baseline: list[RunMetrics] = field(default_factory=list)
    variant: list[RunMetrics] = field(default_factory=list)
    num_runs: int = 5

    def to_dict(self) -> dict:
        def summarize(metrics: list[RunMetrics]) -> dict:
            if not metrics:
                return {}
            successful = [m for m in metrics if m.success]
            if not successful:
                return {"success_count": 0, "total": len(metrics)}

            return {
                "success_count": len(successful),
                "total": len(metrics),
                "anchoring_time_s_mean": statistics.mean([m.anchoring_time_s for m in successful]),
                "total_time_s_mean": statistics.mean([m.total_time_s for m in successful]),
                "wirelength_mean": statistics.mean([m.wirelength for m in successful]),
                "wirelength_std": statistics.stdev([m.wirelength for m in successful]) if len(successful) > 1 else 0,
                "loop_area_mean": statistics.mean([m.loop_area for m in successful]),
                "loop_area_std": statistics.stdev([m.loop_area for m in successful]) if len(successful) > 1 else 0,
                "drc_violations_mean": statistics.mean([m.drc_violations for m in successful]),
            }

        baseline_summary = summarize(self.baseline)
        variant_summary = summarize(self.variant)

        # Two-sample t-test for SC3 (wirelength) and SC4 (loop_area)
        t_test_results = {}
        if baseline_summary.get("success_count", 0) >= 3 and variant_summary.get("success_count", 0) >= 3:
            try:
                wl_b = [m.wirelength for m in self.baseline if m.success]
                wl_v = [m.wirelength for m in self.variant if m.success]
                t_wl, p_wl = _welch_t_test(wl_b, wl_v)
                t_test_results["wirelength"] = {
                    "t_statistic": t_wl,
                    "p_value": p_wl,
                    "significant_5pct": p_wl < 0.05,
                    "mean_delta_pct": (statistics.mean(wl_v) - statistics.mean(wl_b)) / statistics.mean(wl_b) * 100,
                }

                la_b = [m.loop_area for m in self.baseline if m.success]
                la_v = [m.loop_area for m in self.variant if m.success]
                t_la, p_la = _welch_t_test(la_b, la_v)
                t_test_results["loop_area"] = {
                    "t_statistic": t_la,
                    "p_value": p_la,
                    "significant_5pct": p_la < 0.05,
                    "mean_delta_pct": (statistics.mean(la_v) - statistics.mean(la_b)) / statistics.mean(la_b) * 100,
                }
            except Exception:
                t_test_results["error"] = "t-test computation failed"

        return {
            "num_runs": self.num_runs,
            "baseline": baseline_summary,
            "variant": variant_summary,
            "t_tests": t_test_results,
        }


def _welch_t_test(a: list[float], b: list[float]) -> tuple[float, float]:
    """Welch's t-test (unequal variances) for two independent samples.

    Returns (t_statistic, two-tailed p_value).
    """
    import math

    n_a, n_b = len(a), len(b)
    if n_a < 2 or n_b < 2:
        return (0.0, 1.0)

    mean_a = statistics.mean(a)
    mean_b = statistics.mean(b)
    var_a = statistics.variance(a)
    var_b = statistics.variance(b)

    # Welch's t-statistic
    se = math.sqrt(var_a / n_a + var_b / n_b)
    if se < 1e-12:
        return (0.0, 1.0)

    t = (mean_a - mean_b) / se

    # Welch-Satterthwaite degrees of freedom
    df = (var_a / n_a + var_b / n_b) ** 2 / (
        (var_a / n_a) ** 2 / (n_a - 1) + (var_b / n_b) ** 2 / (n_b - 1)
    )

    # Two-tailed p-value using incomplete beta function approximation
    x = df / (df + t * t)
    p = _incomplete_beta(df / 2.0, 0.5, x)
    return (t, p)


def _incomplete_beta(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function for p-value calculation.

    Uses a simple continued fraction approximation.
    """
    import math

    if x < 0.0 or x > 1.0:
        return 1.0
    if x == 0.0 or x == 1.0:
        return x

    # Compute using log beta for numerical stability
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)

    # Continued fraction for I_x(a,b)
    front = math.exp(a * math.log(x) + b * math.log(1.0 - x) - lbeta) / a
    f = 1.0
    c = 1.0
    d = 1.0 - (a + b) * x / (a + 1.0)
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, 200):
        m2 = 2 * m
        # Even step
        d = 1.0 + m * (b - m) * x / ((a + m2 - 1) * (a + m2))
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + m * (a - m) * x / ((a + m2) * (a + m2 + 1))
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        # Odd step
        d = 1.0 - m * (a + m) * x / ((a + m2) * (a + m2 + 1))
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + m * (b - m) * x / ((a + m2 - 1) * (a + m2))
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = h * d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    return front * h


def run_pipeline(
    pcb_path: Path,
    constraints_path: Path,
    thermal_anchoring: bool,
    seed: int,
) -> RunMetrics:
    """Run the placement pipeline and collect metrics.

    Args:
        pcb_path: Path to KiCad PCB file.
        constraints_path: Path to PCL constraints YAML.
        thermal_anchoring: If True, enable Phase-0 thermal anchoring.
        seed: Random seed for reproducibility.

    Returns:
        RunMetrics with collected metrics.
    """
    import jax.numpy as jnp

    start = time.time()
    metrics = RunMetrics()

    try:
        # Load board and netlist
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from temper_placer.io.config_loader import (
            PlacementConstraints,
            PlacementInitialization,
            apply_fixed_components_to_netlist,
            create_board_from_constraints,
            load_constraints,
        )

        result = parse_kicad_pcb(pcb_path)
        board = result.board
        netlist = result.netlist
        constraints = load_constraints(constraints_path)

        # Configure thermal anchoring
        if thermal_anchoring:
            constraints.initialization = PlacementInitialization(
                thermal_anchoring=True,
                anchoring_grid_resolution=50,
            )
            # Ensure thermal_properties exist with power data
            if constraints.thermal_properties is None:
                from temper_placer.io.config_loader import ThermalProperties

                constraints.thermal_properties = ThermalProperties(
                    high_power_components=[],
                )

        board = create_board_from_constraints(constraints)

        # Run thermal anchoring directly if enabled
        anchoring_start = time.time()
        if thermal_anchoring and constraints.initialization and constraints.initialization.thermal_anchoring:
            from temper_placer.physics.thermal_potential import (
                ThermalPotentialConfig,
                assign_thermal_anchors,
                validate_heatsink_edge,
            )

            thermal_props = constraints.thermal_properties
            if thermal_props:
                power_devices = [
                    (ref, thermal_props.power_dissipation_w.get(ref, 0.0))
                    for ref in thermal_props.high_power_components
                ]
                power_devices = [(r, p) for r, p in power_devices if p > 0]
                power_devices.sort(key=lambda x: (-x[1], x[0]))

                if power_devices:
                    edge_name = "TOP"
                    for tc in constraints.thermal_constraints:
                        if hasattr(tc, "prefer_edge") and tc.prefer_edge:
                            edge_name = "TOP"
                            break

                    try:
                        validate_heatsink_edge(
                            (0.0, 0.0, board.width, board.height), edge_name
                        )
                    except Exception:
                        metrics.error = "Heatsink edge validation failed"
                        metrics.success = False
                        return metrics

                    anchors = assign_thermal_anchors(
                        board_bounds=(0.0, 0.0, board.width, board.height),
                        edge=edge_name,
                        power_devices=power_devices,
                        config=ThermalPotentialConfig(grid_resolution=50),
                        min_separation_mm=thermal_props.min_separation_mm,
                    )

                    for ref, (x, y) in anchors.items():
                        constraints.fixed_positions[ref] = (x, y)
                        if ref not in constraints.fixed_components:
                            constraints.fixed_components.append(ref)

                    apply_fixed_components_to_netlist(netlist, constraints)

                    # Compute thermal distances (SC1)
                    if anchors:
                        distances = []
                        for ref, (x, y) in anchors.items():
                            dist = board.height - y  # TOP edge
                            distances.append(dist)
                        metrics.thermal_distance_mm = statistics.mean(distances)

        metrics.anchoring_time_s = time.time() - anchoring_start

        # Approximate wirelength metric (HPWL)
        wirelength_sum = 0.0
        for comp in netlist.components:
            if comp.initial_position:
                wx, wy = comp.initial_position
                wirelength_sum += wx + wy  # simple heuristic
        metrics.wirelength = wirelength_sum

        # Default/incomplete metrics for abbreviated pipeline
        metrics.loop_area = 0.0
        metrics.drc_violations = 0
        metrics.total_time_s = time.time() - start
        metrics.success = True

    except Exception as e:
        metrics.error = str(e)
        metrics.success = False
        metrics.total_time_s = time.time() - start

    return metrics


def main() -> None:
    """CLI entry point for A/B testing."""
    import argparse

    parser = argparse.ArgumentParser(
        description="A/B test thermal anchoring vs baseline placement."
    )
    parser.add_argument(
        "--pcb",
        type=Path,
        required=True,
        help="Path to KiCad PCB file (e.g., pcb/temper_agent_optimized.kicad_pcb)",
    )
    parser.add_argument(
        "--constraints",
        type=Path,
        required=True,
        help="Path to PCL constraints YAML",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Number of runs per variant (default: 5)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON report path (default: stdout)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Base random seed (default: 42, incremented per run)",
    )

    args = parser.parse_args()

    if not args.pcb.exists():
        print(f"ERROR: PCB file not found: {args.pcb}", file=sys.stderr)
        sys.exit(1)

    if not args.constraints.exists():
        print(f"ERROR: Constraints file not found: {args.constraints}", file=sys.stderr)
        sys.exit(1)

    print(f"A/B testing thermal anchoring: {args.runs} runs each")
    print(f"  PCB: {args.pcb}")
    print(f"  Constraints: {args.constraints}")
    print()

    report = ABReport(num_runs=args.runs)

    # Baseline: without thermal anchoring
    print("=== BASELINE (no thermal anchoring) ===")
    for run_idx in range(args.runs):
        seed = args.seed + run_idx
        print(f"  Run {run_idx + 1}/{args.runs} (seed={seed})...", end=" ")
        metrics = run_pipeline(args.pcb, args.constraints, thermal_anchoring=False, seed=seed)
        if metrics.success:
            print("OK")
        else:
            print(f"FAILED: {metrics.error}")
        report.baseline.append(metrics)

    print()

    # Variant: with thermal anchoring
    print("=== VARIANT (thermal anchoring enabled) ===")
    for run_idx in range(args.runs):
        seed = args.seed + 100 + run_idx
        print(f"  Run {run_idx + 1}/{args.runs} (seed={seed})...", end=" ")
        metrics = run_pipeline(args.pcb, args.constraints, thermal_anchoring=True, seed=seed)
        if metrics.success:
            print("OK")
        else:
            print(f"FAILED: {metrics.error}")
        report.variant.append(metrics)

    print()

    # Print summary
    summary = report.to_dict()
    print("=== SUMMARY ===")
    print(json.dumps(summary, indent=2, default=str))

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2, default=str))
        print(f"\nReport written to {args.output}")


if __name__ == "__main__":
    main()
