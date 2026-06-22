"""
Corner envelope sweep orchestrator.

Reads a corner definition YAML, generates the corner grid, runs ngspice at
each corner combination (with optional parallelism), and collects results
into a structured JSON file.

Usage:
    python -m tools.spice.corner_sweep augmented.cir --mode corners --output results.json
"""

from __future__ import annotations

import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import yaml
from tools.spice.corner_results import CornerResult, save_results
from tools.spice.sim_runner import run_simulation


@dataclass
class AxisDef:
    """Definition of one corner sweep axis."""

    name: str
    unit: str
    min_val: float
    max_val: float
    num_points: int
    spice_param: str
    sets_temp: bool = False

    @property
    def values(self) -> list[float]:
        if self.num_points <= 1:
            return [self.min_val]
        step = (self.max_val - self.min_val) / (self.num_points - 1)
        return [self.min_val + i * step for i in range(self.num_points)]

    @property
    def minmax_values(self) -> list[float]:
        return [self.min_val, self.max_val]


def load_corner_def(yaml_path: str | Path) -> tuple[str, list[AxisDef]]:
    """Load corner sweep configuration from YAML."""
    with open(yaml_path) as f:
        config = yaml.safe_load(f)

    mode = config.get("mode", "corners")
    axes: list[AxisDef] = []

    for name, adef in config.get("axes", {}).items():
        axes.append(
            AxisDef(
                name=name,
                unit=adef["unit"],
                min_val=adef["min"],
                max_val=adef["max"],
                num_points=adef["num_points"],
                spice_param=adef["spice_param"],
                sets_temp=adef.get("sets_temp", False),
            )
        )

    return mode, axes, config.get("parallel", {}).get("max_workers", 1)


def generate_corner_grid(
    axes: list[AxisDef], mode: str = "corners"
) -> list[dict[str, float]]:
    """Generate the corner parameter grid.

    Args:
        axes: List of axis definitions.
        mode: "full" for factorial, "corners" for min/max only.

    Returns:
        List of parameter dicts, one per corner.
    """
    if mode == "corners":
        value_sets = [a.minmax_values for a in axes]
    else:
        value_sets = [a.values for a in axes]

    corners: list[dict[str, float]] = [{}]

    for axis, values in zip(axes, value_sets, strict=True):
        new_corners: list[dict[str, float]] = []
        for corner in corners:
            for val in values:
                nc = dict(corner)
                nc[axis.name] = val
                new_corners.append(nc)
        corners = new_corners

    return corners


def _run_single_corner(
    cir_file: str,
    corner_params: dict[str, float],
    axes: list[AxisDef],
) -> CornerResult:
    """Run simulation for a single corner (picklable for multiprocessing)."""
    sparam: dict[str, float] = {}
    temp_c: float | None = None

    for axis in axes:
        val = corner_params[axis.name]
        if axis.sets_temp:
            temp_c = val
        else:
            sparam[axis.spice_param] = val

    return run_simulation(cir_file, params=sparam if sparam else None, temp_c=temp_c)


def run_corner_sweep(
    cir_file: str | Path,
    corner_def_path: str | Path | None = None,
    mode: str = "corners",
    max_workers: int = 1,
    output_path: str | Path | None = None,
) -> list[CornerResult]:
    """Run a corner envelope sweep.

    Args:
        cir_file: Path to augmented .cir netlist.
        corner_def_path: Path to corner definition YAML.
        mode: "full" or "corners".
        max_workers: Number of parallel ngspice processes.
        output_path: Where to write results JSON.

    Returns:
        List of CornerResult, one per corner.
    """
    if corner_def_path is None:
        corner_def_path = Path(__file__).parent / "corners" / "default_corners.yaml"

    config_mode, axes, config_workers = load_corner_def(corner_def_path)
    if mode == "corners" or config_mode == "corners":
        mode = "corners"

    corners = generate_corner_grid(axes, mode)

    workers = max_workers or config_workers or 1
    results: list[CornerResult] = []

    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(
                    _run_single_corner, str(cir_file), corner, axes
                ): corner
                for corner in corners
            }
            for future in as_completed(future_map):
                results.append(future.result())
    else:
        for corner in corners:
            result = _run_single_corner(str(cir_file), corner, axes)
            results.append(result)

    if output_path:
        save_results(results, str(output_path))

    return results


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run corner envelope sweep")
    parser.add_argument("cir_file", help="Path to augmented .cir netlist")
    parser.add_argument(
        "--mode",
        choices=["full", "corners"],
        default="corners",
        help="Sweep mode",
    )
    parser.add_argument(
        "--corners-def",
        help="Path to corner definition YAML",
    )
    parser.add_argument(
        "--output",
        help="Output path for results JSON",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel workers",
    )
    args = parser.parse_args()

    start = time.time()
    results = run_corner_sweep(
        args.cir_file,
        corner_def_path=args.corners_def,
        mode=args.mode,
        max_workers=args.workers,
        output_path=args.output,
    )
    elapsed = time.time() - start

    converged = sum(1 for r in results if not r.convergence_error)
    failed = sum(1 for r in results if r.convergence_error)

    print(f"Corner sweep complete: {len(results)} corners in {elapsed:.1f}s")
    print(f"  Converged: {converged}")
    print(f"  Failed: {failed}")

    if args.output:
        print(f"Results written to {args.output}")


if __name__ == "__main__":
    main()
