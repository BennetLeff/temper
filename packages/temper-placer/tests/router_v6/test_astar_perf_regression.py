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
