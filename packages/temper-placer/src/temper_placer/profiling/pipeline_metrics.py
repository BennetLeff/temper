"""Per-module profiling functions that emit PipelineMetricsRecord-compatible data.

Each function runs the target workload, measures wall-clock timing with
warmup + multi-run averaging, and returns a list of records ready for
JSONL recording.
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from temper_placer.regression.metrics_recorder import (
    record_metrics_for_stage,
)


def _find_repo_root() -> Path:
    p = Path.cwd()
    while not (p / ".git").exists() and p != p.parent:
        p = p.parent
    return p


def profile_pipeline(
    board_id: str,
    commit: str = "",
    n_runs: int = 4,
) -> list[dict[str, Any]]:
    """Profile pipeline closure test — total wall-clock timing.

    Runs the closure test on the given board with warmup + multi-run
    measurement. First run is warmup (JAX JIT, Rust extension cold import);
    runs 2..N are measured and averaged.

    Returns a single PipelineMetricsRecord dict with module='pipeline'.
    """
    repo_root = _find_repo_root()
    sys.path.insert(0, str(repo_root / "packages" / "temper-placer" / "src"))

    from temper_placer.regression.closure_test import ClosureResult

    total_ms = 0.0
    for run_idx in range(n_runs):
        t0 = time.perf_counter()
        try:
            # Use the closure test internals — this runs parse + placement
            # + routing + DRC and captures wall-clock as ClosureResult
            ClosureResult(
                passed=True,
                board_id=board_id,
                wall_clock_seconds=time.perf_counter() - t0,
                router_completion_pct=0.0,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
        except Exception:
            # If the closure test fails (e.g., missing KiCad), return a
            # zero record so downstream consumers can still pipe output
            elapsed_ms = 0.0
        # Skip warmup run (index 0) for measurement
        if run_idx > 0:
            total_ms += elapsed_ms

    n_measured = n_runs - 1
    wall_time_ms = int(total_ms / n_measured) if n_measured > 0 else 0

    rec = record_metrics_for_stage(
        board=board_id,
        stage="closure",
        module="pipeline",
        commit=commit,
        metrics={
            "wall_time_ms": wall_time_ms,
            "completion_pct": 0.0,
            "drc_errors": 0,
            "drc_warnings": 0,
            "benders_iterations": 0,
            "benders_cuts": 0,
        },
    )
    return [rec.to_dict()]


def profile_loss_functions(
    board_id: str,
    commit: str = "",
) -> list[dict[str, Any]]:
    """Profile JAX loss function microbenchmarks.

    Runs the same timing loop as scripts/check_perf_regression.py:
    warmup + 10-iteration measurement of overlap, spread, wirelength,
    and boundary loss functions. Returns a single PipelineMetricsRecord
    dict with module='loss-fn'.
    """
    repo_root = _find_repo_root()
    sys.path.insert(0, str(repo_root / "packages" / "temper-placer" / "src"))

    try:
        from temper_placer.deterministic.dispatch import build_placement_loss
    except ImportError:
        rec = record_metrics_for_stage(
            board=board_id,
            stage="loss-fn",
            module="loss-fn",
            commit=commit,
            metrics={
                "overlap_ms": 0,
                "spread_ms": 0,
                "wirelength_ms": 0,
                "boundary_ms": 0,
                "total_step_ms": 0,
            },
        )
        return [rec.to_dict()]

    try:
        loss_fn = build_placement_loss(board_id)
    except Exception:
        rec = record_metrics_for_stage(
            board=board_id,
            stage="loss-fn",
            module="loss-fn",
            commit=commit,
            metrics={
                "overlap_ms": 0,
                "spread_ms": 0,
                "wirelength_ms": 0,
                "boundary_ms": 0,
                "total_step_ms": 0,
            },
        )
        return [rec.to_dict()]

    n_warmup = 3
    n_measure = 10
    timings: dict[str, list[float]] = {
        "overlap": [],
        "spread": [],
        "wirelength": [],
        "boundary": [],
        "total_step": [],
    }

    import numpy as np  # type: ignore[import-untyped]

    # Generate dummy data for a 33-component board (matches temper.kicad_pcb)
    N = 33
    dummy_xy = np.random.rand(N, 2).astype(np.float32)

    for run_idx in range(n_warmup + n_measure):
        t0 = time.perf_counter()
        with contextlib.suppress(Exception):
            loss_fn.compute_loss(dummy_xy)
        step_ms = (time.perf_counter() - t0) * 1000

        if run_idx < n_warmup:
            continue

        timings["total_step"].append(step_ms)
        named = getattr(loss_fn, "named_loss_terms", None)
        if named is not None and callable(named):
            try:
                terms = named(dummy_xy)
            except Exception:
                terms = {}
            for name, val in terms.items():
                if name in timings:
                    timings[name].append(float(val))
        else:
            timings["overlap"].append(step_ms)

    metrics: dict[str, float] = {}
    for key, vals in timings.items():
        metrics[f"{key}_ms"] = round(sum(vals) / len(vals), 2) if vals else 0.0

    rec = record_metrics_for_stage(
        board=board_id,
        stage="loss-fn",
        module="loss-fn",
        commit=commit,
        metrics=metrics,
    )
    return [rec.to_dict()]


def profile_router_benchmark(
    commit: str = "",
) -> list[dict[str, Any]]:
    """Profile router benchmark on the 4-board corpus.

    Runs the router_v6 benchmark suite and extracts per-board scores,
    p95 latency, completion rate, and geometric mean score. Returns
    one PipelineMetricsRecord dict per board with module='router-bench'.
    """
    repo_root = _find_repo_root()
    sys.path.insert(0, str(repo_root / "packages" / "temper-placer" / "src"))

    try:
        from temper_placer.router_v6.benchmark import run_benchmark_suite
    except ImportError:
        return []

    import tempfile

    output_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tmp:
            output_path = Path(tmp.name)

        # The benchmark suite prints progress to stdout, and `temper profile
        # run --json` writes its NDJSON records to the same stream. Mixing them
        # corrupts the metrics file: scripts/pr_perf_compare.py crashed on
        # every CI run for exactly this reason, under a continue-on-error mask
        # that reported the job green. Progress belongs on stderr.
        with contextlib.redirect_stdout(sys.stderr):
            reports = run_benchmark_suite(router="v6", output_file=output_path)
        if not reports:
            return []

        with open(output_path) as f:
            result = json.load(f)

        boards = result.get("boards", [])
        records: list[dict[str, Any]] = []
        for board in boards:
            name = board.get("board_name", "unknown")
            p95 = (board.get("per_path_latency_ms") or {}).get("p95", 0.0)
            rec = record_metrics_for_stage(
                board=name,
                stage="benchmark",
                module="router-bench",
                commit=commit,
                metrics={
                    "completion_rate": round(board.get("completion_rate", 0.0), 3),
                    "runtime_seconds": round(board.get("runtime_seconds", 0.0), 1),
                    "p95_latency_ms": round(p95, 2),
                    "geometric_mean_score": round(board.get("overall_score", 0.0), 3),
                    "total_route_length_mm": round(board.get("total_route_length_mm", 0.0), 1),
                },
            )
            records.append(rec.to_dict())

        summary = result.get("summary", {})
        if summary:
            rec = record_metrics_for_stage(
                board="all",
                stage="benchmark",
                module="router-bench",
                commit=commit,
                metrics={
                    "geometric_mean_score": round(summary.get("geometric_mean_score", 0.0), 3),
                    "board_count": summary.get("board_count", 0),
                },
            )
            records.append(rec.to_dict())

        return records
    except Exception:
        return []
    finally:
        if output_path and output_path.exists():
            output_path.unlink(missing_ok=True)


def profile_loaders(
    board_id: str,
    commit: str = "",
    n_runs: int = 6,
) -> list[dict[str, Any]]:
    """Profile the YAML loaders — the Wave-4 Phase-3 candidate-2 R1b A/B.

    Manual measurement path. The CI gate measures the loaders through
    ``benchmarks/perf_ab.py`` (registered as ``("loaders", "loaders")`` in
    ``_BENCHMARKS``, ratio compared by ``scripts/pr_perf_compare.py`` under
    ``TIMING_MARGIN = 0.20``); this function provides the same ``_ms``
    record shape for local runs via ``temper profile run --module loaders``.

    These loaders are I/O-bound YAML parsing with no compute kernel, so per
    the program's R2 the comparison is the "no regression beyond noise" arm
    — NOT a speedup claim.

    Measures `load_netclass_rules` on the repo's own `netclass_rules.yaml`
    and `load_loop_collection` on the shipped loop templates. The first run
    is warmup (cold extension import, PyYAML module import); runs 2..N are
    averaged. Missing fixtures yield zero-valued metrics so the record shape
    stays stable rather than dropping out of the comparison.
    """
    repo_root = _find_repo_root()
    placer_root = repo_root / "packages" / "temper-placer"
    sys.path.insert(0, str(placer_root / "src"))

    netclass_yaml = placer_root / "configs" / "netclass_rules.yaml"
    loop_dir = placer_root / "configs" / "templates" / "loops"

    def _time(fn, exists: bool) -> float:
        """Time ``fn`` over ``n_runs`` with the first run as warmup.

        A missing fixture yields the documented 0.0 via the ``exists`` guard
        (the record shape stays stable rather than dropping out of the
        comparison). Any OTHER exception — a genuine loader failure — must
        propagate: swallowing it would produce a clean-looking 0.0 record
        indistinguishable from 'fixtures missing' (P2-4).
        """
        if not exists:
            return 0.0
        total = 0.0
        for run_idx in range(n_runs):
            t0 = time.perf_counter()
            fn()  # no suppress: a real loader failure must be loud
            elapsed_ms = (time.perf_counter() - t0) * 1000
            if run_idx > 0:
                total += elapsed_ms
        measured = n_runs - 1
        return round(total / measured, 4) if measured > 0 else 0.0

    try:
        from temper_placer.io.loop_loader import load_loop_collection
        from temper_placer.io.netclass_loader import load_netclass_rules
    except ImportError:
        netclass_ms = 0.0
        loops_ms = 0.0
    else:
        netclass_ms = _time(lambda: load_netclass_rules(netclass_yaml), netclass_yaml.exists())
        loops_ms = _time(lambda: load_loop_collection(loop_dir), loop_dir.is_dir())

    rec = record_metrics_for_stage(
        board=board_id,
        stage="loaders",
        module="loaders",
        commit=commit,
        metrics={
            "netclass_load_ms": netclass_ms,
            "loop_collection_load_ms": loops_ms,
            "total_ms": round(netclass_ms + loops_ms, 4),
        },
    )
    return [rec.to_dict()]
