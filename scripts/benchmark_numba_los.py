"""Before/after Numba LOS profiling: micro-benchmark + full pipeline cProfile.

Usage (from repo root):
    PYTHONPATH=packages/temper-placer/src \
    python3 scripts/benchmark_numba_los.py [--micro] [--pipeline N] [--output DIR]
"""

from __future__ import annotations

import argparse
import cProfile
import io
import json
import pstats
import sys
import time
from pathlib import Path

import numpy as np


REPO_ROOT = Path(__file__).resolve().parent.parent
PCB_PATH = REPO_ROOT / "pcb" / "temper.kicad_pcb"


class FakeGrid:
    def __init__(self, grid_arr):
        self.grid = grid_arr
        self.width_cells = int(grid_arr.shape[1])
        self.height_cells = int(grid_arr.shape[0])


def run_micro_benchmark(output_dir: Path | None) -> dict:
    """Time LOS calls on representative segment lengths with varied occupancy."""
    from temper_placer.router_v6.astar_core import _line_of_sight
    from temper_placer.router_v6.astar_core_numba import _line_of_sight_numba

    lengths = [5, 20, 50, 100, 200]
    num_calls = 100_000
    results = {}

    np.random.seed(42)

    for length in lengths:
        w = max(length * 2, 200)
        h = max(length * 2, 200)
        # All-free grid: forces traversal of all cells (worst-case for Python)
        grid_arr = np.zeros((h, w), dtype=np.int32)
        grid = FakeGrid(grid_arr)

        # Generate random segments of roughly the given length
        pairs = []
        for _ in range(num_calls):
            angle = np.random.uniform(0, 2 * np.pi)
            dx = int(np.cos(angle) * length)
            dy = int(np.sin(angle) * length)
            x0 = np.random.randint(10, w - 10)
            y0 = np.random.randint(10, h - 10)
            x1 = max(0, min(w - 1, x0 + dx))
            y1 = max(0, min(h - 1, y0 + dy))
            pairs.append(((x0, y0), (x1, y1)))

        # Warmup: compile Numba kernel
        _line_of_sight_numba(pairs[0][0], pairs[0][1], grid, 0)

        # Time Python LOS
        t0 = time.perf_counter()
        for p1, p2 in pairs:
            _line_of_sight(p1, p2, grid, 0)
        python_time = time.perf_counter() - t0

        # Time Numba LOS
        t0 = time.perf_counter()
        for p1, p2 in pairs:
            _line_of_sight_numba(p1, p2, grid, 0)
        numba_time = time.perf_counter() - t0

        python_per = (python_time / num_calls) * 1e6
        numba_per = (numba_time / num_calls) * 1e6
        speedup = python_time / numba_time if numba_time > 0 else float("inf")

        results[length] = {
            "python_us": round(python_per, 2),
            "numba_us": round(numba_per, 2),
            "speedup": round(speedup, 1),
            "python_total_s": round(python_time, 4),
            "numba_total_s": round(numba_time, 4),
        }

        print(f"  length={length:3d}: Python={python_per:8.2f}us/call  "
              f"Numba={numba_per:8.2f}us/call  speedup={speedup:5.1f}x")

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "micro_benchmark.json").write_text(
            json.dumps(results, indent=2)
        )

    return results


def run_pipeline_profile(num_nets: int, output_dir: Path | None) -> dict:
    """Profile full pipeline with and without Numba LOS."""
    from dataclasses import replace
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.pipeline import RouterV6Pipeline

    if not PCB_PATH.exists():
        print(f"PCB not found at {PCB_PATH}; skipping pipeline profile.")
        return {}

    parsed = parse_kicad_pcb_v6(str(PCB_PATH))

    # Use the same pick_easy_nets approach as profile_router_v6_sampling.py
    from temper_placer.core.units import deg_to_rad

    pin_positions = {}
    for comp in parsed.components:
        if comp.initial_position is None:
            continue
        cx, cy = comp.initial_position
        rot = comp.initial_rotation or 0
        rot_rad = deg_to_rad(rot * 90.0) if isinstance(rot, int) else rot
        side = comp.initial_side or 0
        for pin in comp.pins:
            try:
                ax, ay = pin.absolute_position((cx, cy), rot_rad, side=side)
            except (AttributeError, TypeError):
                ax = cx + float(pin.position[0])
                ay = cy + float(pin.position[1])
            pin_positions[(comp.ref, pin.name)] = (ax, ay)
            pin_positions[(comp.ref, pin.number)] = (ax, ay)

    net_scores: list[tuple[float, str]] = []
    for net in parsed.nets:
        coords = []
        for comp_ref, pin_name in net.pins:
            pos = pin_positions.get((comp_ref, pin_name))
            if pos is not None:
                coords.append(pos)
        if len(coords) < 2:
            continue
        xs = [c[0] for c in coords]
        ys = [c[1] for c in coords]
        bbox_diag = ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2) ** 0.5
        net_scores.append((bbox_diag, net.name))
    net_scores.sort()
    target_nets = [name for _, name in net_scores[:num_nets]]
    target_set = set(target_nets)
    filtered_nets = [n for n in parsed.nets if n.name in target_set]
    parsed = replace(parsed, nets=filtered_nets)

    results = {}
    for enable_numba in [False, True]:
        label = "numba" if enable_numba else "python"
        print(f"\n=== Pipeline profile: enable_numba_los={enable_numba} ({num_nets} nets) ===")
        pipeline = RouterV6Pipeline(verbose=True, enable_numba_los=enable_numba, max_iter=500_000)

        profiler = cProfile.Profile()
        t0 = time.perf_counter()
        profiler.enable()
        try:
            result = pipeline.run(PCB_PATH, pcb_override=parsed)
        finally:
            profiler.disable()
        elapsed = time.perf_counter() - t0

        stream = io.StringIO()
        stats = pstats.Stats(profiler, stream=stream)
        stats.sort_stats(pstats.SortKey.CUMULATIVE)
        stats.print_stats(15)

        results[label] = {
            "wall_s": round(elapsed, 2),
            "completion_rate": round(result.completion_rate, 3),
            "success_count": result.success_count,
            "failure_count": result.failure_count,
            "profile_top15": stream.getvalue(),
        }
        print(f"  Wall: {elapsed:.1f}s, completion: {result.completion_rate:.2%}")
        print(f"  Routed: {result.success_count}, Failed: {result.failure_count}")

        if output_dir:
            out_dir = output_dir / "pipeline"
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"profile_{label}.txt").write_text(stream.getvalue())

    if output_dir:
        (output_dir / "pipeline" / "comparison.json").write_text(
            json.dumps(results, indent=2, default=str)
        )

    return results


def main() -> int:
    p = argparse.ArgumentParser(
        description="Numba LOS A/B performance benchmark"
    )
    p.add_argument("--micro", action="store_true", default=True,
                   help="Run micro-benchmark (timeit per-call latency, default)")
    p.add_argument("--no-micro", action="store_true",
                   help="Skip micro-benchmark")
    p.add_argument("--pipeline", type=int, default=None, metavar="N",
                   help="Run full pipeline cProfile on N easiest nets")
    p.add_argument("--output", type=Path, default=None,
                   help="Output directory for benchmark results")
    args = p.parse_args()

    output_dir = args.output or REPO_ROOT / "benchmarks" / "los_numba"
    run_micro = not args.no_micro

    if run_micro:
        print("=== Micro-benchmark: Numba LOS vs Python LOS (100K calls each) ===")
        run_micro_benchmark(output_dir)
        print()

    if args.pipeline:
        run_pipeline_profile(args.pipeline, output_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
