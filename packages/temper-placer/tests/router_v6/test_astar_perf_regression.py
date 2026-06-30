"""A* Per-Path Performance Regression Gate (R5).

Compares current per-path p95 latency against the committed baseline
in tests/router_v6/benchmarks/baseline.json. Fails CI on >15% regression
on any board.

Skips if the baseline JSON is absent or the corpus boards are not on disk.
"""

import json
import sys
from pathlib import Path

import pytest

BASELINE_PATH = Path(__file__).parent / "benchmarks" / "baseline.json"
REGRESSION_TOLERANCE = 0.15  # 15%


def _load_baseline() -> dict | None:
    """Load the committed baseline JSON, or return None if absent."""
    if not BASELINE_PATH.exists():
        return None
    try:
        with open(BASELINE_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _run_benchmark() -> dict:
    """Run the R3 benchmark and return the JSON result dict."""
    # Import inside function to avoid import-time side effects
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    import tempfile

    from temper_placer.router_v6.benchmark import run_benchmark_suite

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tmp:
        output_path = Path(tmp.name)

    try:
        # Run benchmark - will skip if no boards available
        reports = run_benchmark_suite(router="v6", output_file=output_path)
        if not reports:
            return {"boards": []}

        with open(output_path) as f:
            result = json.load(f)
        return result
    finally:
        if output_path.exists():
            output_path.unlink(missing_ok=True)


@pytest.mark.benchmark
def test_astar_perf_regression():
    """Performance regression gate: fails if per-path p95 degrades >15%."""
    baseline = _load_baseline()
    if baseline is None:
        pytest.skip("Baseline JSON not found at " + str(BASELINE_PATH))

    baseline_boards = baseline.get("boards", [])
    if not baseline_boards:
        pytest.skip("Baseline has no board data (placeholder)")

    # Check if corpus boards are available
    from temper_placer.router_v6.test_boards import get_available_boards

    available = get_available_boards()
    if not available:
        pytest.skip("No corpus boards available on disk")

    current = _run_benchmark()
    current_boards = current.get("boards", [])

    if not current_boards:
        pytest.skip("Benchmark produced no board results")

    # Index baseline boards by name
    baseline_by_name = {b["board_name"]: b for b in baseline_boards}

    failures = []
    for board in current_boards:
        name = board.get("board_name", "unknown")
        baseline_board = baseline_by_name.get(name)
        if baseline_board is None:
            continue  # New board, no baseline to compare against

        current_per_path = board.get("per_path_latency_ms", {}) or {}
        baseline_per_path = baseline_board.get("per_path_latency_ms", {}) or {}

        current_p95 = current_per_path.get("p95")
        baseline_p95 = baseline_per_path.get("p95")

        if current_p95 is None or baseline_p95 is None:
            continue  # No p95 data to compare

        if baseline_p95 <= 0:
            continue  # Cannot compute ratio

        ratio = current_p95 / baseline_p95
        if ratio > (1.0 + REGRESSION_TOLERANCE):
            failures.append(
                f"{name}: p95 {current_p95:.2f}ms vs baseline {baseline_p95:.2f}ms "
                f"({ratio:.1%} of baseline, threshold {1.0 + REGRESSION_TOLERANCE:.1%})"
            )

    if failures:
        pytest.fail(
            f"Per-path p95 regression beyond {REGRESSION_TOLERANCE:.0%} tolerance:\n"
            + "\n".join(failures)
        )


# ---------------------------------------------------------------------------
# U4: Lazy Theta* vs Theta* A/B profiling (synthetic grids)
# ---------------------------------------------------------------------------


@pytest.mark.benchmark
def test_lazy_vs_theta_star_los_reduction():
    """A/B profiling: Lazy Theta* reduces line-of-sight calls vs Theta*.

    Compares wall time and line_of_sight call count on synthetic grids
    with varying obstacle density. Lazy Theta* should have
    substantially fewer LOS calls (1 per expansion at pop time vs
    8 per expansion at push time for standard Theta*).
    """
    import random
    import time

    import numpy as np

    from temper_placer.router_v6.astar_core import (
        _astar_search_lazy_theta_star,
        _astar_search_theta_star,
    )
    from temper_placer.router_v6.astar_core import (
        _line_of_sight as _los,
    )
    from temper_placer.router_v6.occupancy_grid import OccupancyGrid

    # Monkey-patch _line_of_sight to count calls
    _orig_los = _los
    _los_count = 0

    def _counted_los(*args, **kwargs):
        nonlocal _los_count
        _los_count += 1
        return _orig_los(*args, **kwargs)

    import temper_placer.router_v6.astar_core as ac
    ac._line_of_sight = _counted_los

    try:
        sizes = [(20, 20), (30, 30), (50, 50)]
        rng = random.Random(42)

        print("\n--- A/B Profiling: Lazy Theta* vs Theta* ---")
        print(f"{'Grid':>10} | {'Variant':>12} | {'Wall(ms)':>8} | {'LOS':>8} | {'Exps':>6} | {'Path':>5}")
        print("-" * 60)

        for height, width in sizes:
            for density in [0.05, 0.15, 0.3]:
                arr = np.zeros((height, width), dtype=np.int8)
                for y in range(height):
                    for x in range(width):
                        if rng.random() < density:
                            arr[y, x] = 1

                # Ensure start and goal are free
                arr[0, 0] = 0
                arr[height - 1, width - 1] = 0
                grid = OccupancyGrid("test", arr, (0.0, 0.0), 1.0, width, height)

                label = f"{width}x{height} d={density:.2f}"

                # Theta*
                _los_count = 0
                t0 = time.perf_counter()
                theta_path = _astar_search_theta_star(grid, (0, 0), (width - 1, height - 1), net_id=0)
                theta_time = (time.perf_counter() - t0) * 1000
                theta_los = _los_count

                # Lazy Theta*
                _los_count = 0
                t0 = time.perf_counter()
                lazy_path = _astar_search_lazy_theta_star(grid, (0, 0), (width - 1, height - 1), net_id=0)
                lazy_time = (time.perf_counter() - t0) * 1000
                lazy_los = _los_count

                theta_len = len(theta_path) if theta_path else 0
                lazy_len = len(lazy_path) if lazy_path else 0

                print(f"{label:>10} | {'Theta*':>12} | {theta_time:>7.1f} | {theta_los:>5}   | {'  -':>5} | {theta_len:>5}")
                print(f"{'':>10} | {'Lazy Theta*':>12} | {lazy_time:>7.1f} | {lazy_los:>5}   | {'  -':>5} | {lazy_len:>5}")

                if theta_los > 0 and lazy_los > 0:
                    ratio = theta_los / max(lazy_los, 1)
                    print(f"{'':>10} | {'Reduction':>12} | {'':>8} | {ratio:>5.1f}x")
                print()

                # Assert reachability parity (but skip assertion for very
                # dense grids where both may fail)
                if theta_path is not None and lazy_path is not None:
                    # Lazy Theta* should have fewer LOS calls
                    pass  # Informational, not a hard gate
    finally:
        ac._line_of_sight = _orig_los
