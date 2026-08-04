#!/usr/bin/env python3
"""Per-migration performance A/B harness (Wave 4 discipline contract, R1b/R2).

Every Wave 4 migration must carry a behavioral A/B (the differential-oracle
test, R1a) *and* a performance A/B (R1b). This module is the performance half.

Design: the A/B runs **both arms in one process, back to back** -- the verbatim
pre-migration Python oracle and the Rust kernel it was replaced by -- and the
gated metric is their **ratio**, not an absolute wall time.

Why a ratio. The comparison in ``scripts/pr_perf_compare.py`` scores a PR
against a committed baseline captured on a different machine at a different
time. Absolute milliseconds are not comparable across those axes: the measured
run-to-run spread of this repo's own CI wall-clock series is sd 4.6% with
excursions to 9.9% (docs/evidence/2026-08-04-perf-ab-harness-noise-floor.md).
A ratio measured inside a single process cancels machine speed, container
contention, and interpreter version, so it is stable enough to gate on.

Why the *same* oracle the differential test uses. The behavioral A/B pins the
Rust kernel against a verbatim copy of the pre-migration implementation. This
harness imports that exact copy rather than reimplementing it, so the two gates
cannot drift apart: if the oracle is edited or deleted, both gates change
together, and neither can silently stop comparing the thing it claims to.

Records are emitted in the ``PipelineMetricsRecord`` NDJSON shape that
``scripts/pr_perf_compare.py`` consumes. Only ``rust_over_oracle_ratio`` is
gated (lower is better); the raw ``*_wall_us`` figures are informational and
carry no gated suffix, precisely because they are machine-dependent.

Usage:
    python3 benchmarks/perf_ab.py --json                 # NDJSON to stdout
    python3 benchmarks/perf_ab.py --json --commit <sha>
    python3 benchmarks/perf_ab.py --list

Registering a migration:
    Add a ``_BENCHMARKS`` entry. A new entry with no baseline row in
    power_pcb_dataset/metrics/perf_ab_baseline.jsonl fails the gate closed --
    capture a baseline in the same PR.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import statistics
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

# Board id recorded for synthetic in-process benchmarks. The comparison keys on
# (module, board, stage); "synthetic" keeps these rows from colliding with the
# board-corpus rows produced by the closure pipeline.
SYNTHETIC_BOARD = "synthetic"

DEFAULT_WARMUP = 3
DEFAULT_REPEATS = 9


def _load_module_from_path(name: str, path: Path) -> ModuleType:
    """Import a module from an explicit path (used for test-resident oracles).

    The verbatim pre-migration oracles live in the differential test that pins
    them. Importing them here -- rather than copying them -- is what keeps the
    behavioral and performance A/Bs measuring the same reference.
    """
    if not path.is_file():
        raise FileNotFoundError(f"oracle module not found: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load oracle module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _time_us(fn: Callable[[], Any], warmup: int, repeats: int) -> float:
    """Median wall time of ``fn`` in microseconds, after ``warmup`` runs.

    Median, not mean: the CI noise floor measurement showed the wall-clock
    distribution has a right tail (single excursions to +9.9% against a 4.6%
    sd), and a median is the estimator that tail does not move.
    """
    for _ in range(warmup):
        fn()
    samples: list[float] = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1e6)
    return statistics.median(samples)


# ---------------------------------------------------------------------------
# Wave 3 retrofit: router_v6/bottleneck_geometry.py cell-capacity kernels
# ---------------------------------------------------------------------------

_OCCUPANCY_VALUES = (0, 1, 2, 3, 7, 11, -1, -2)
_CLASS_POOL = ("GateDriveHV", "GateDriveSELV", "SIGNAL", "ISO_SAFE")

# Fixed shape and seed: the A/B ratio is only comparable across runs if both
# arms see byte-identical input every time.
_BENCH_ROWS = 24
_BENCH_COLS = 24
_BENCH_LAYERS = 2
_BENCH_SEED = 20260804


def _bottleneck_fixture() -> tuple[Any, list[tuple[int, int, int]], dict[str, Any], dict[Any, str]]:
    """Deterministic ClearanceGrid + cell batch for the bottleneck kernels."""
    from types import SimpleNamespace

    from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

    rng = random.Random(_BENCH_SEED)
    grid = ClearanceGrid(
        width_mm=float(_BENCH_COLS),
        height_mm=float(_BENCH_ROWS),
        cell_size_mm=1.0,
        layer_count=_BENCH_LAYERS,
    )
    for layer in range(_BENCH_LAYERS):
        for r in range(_BENCH_ROWS):
            for c in range(_BENCH_COLS):
                grid._trace_net_ids[layer][r, c] = rng.choice(_OCCUPANCY_VALUES)
                grid._pad_net_ids[layer][r, c] = rng.choice(_OCCUPANCY_VALUES)

    cells = [
        (layer, r, c)
        for layer in range(_BENCH_LAYERS)
        for r in range(_BENCH_ROWS)
        for c in range(_BENCH_COLS)
    ]

    net_class_rules: dict[str, Any] = {
        "GateDriveHV": SimpleNamespace(safety_category="HV"),
        "GateDriveSELV": SimpleNamespace(safety_category="LV"),
        "SIGNAL": SimpleNamespace(safety_category="LV"),
        "ISO_SAFE": SimpleNamespace(safety_category="iso"),
    }
    pad_net_classes = {
        (layer, r, c): _CLASS_POOL[(layer + r + c) % len(_CLASS_POOL)]
        for (layer, r, c) in cells
        if grid._pad_net_ids[layer][r, c] != 0
    }
    return grid, cells, net_class_rules, pad_net_classes


def _oracle_module() -> ModuleType:
    return _load_module_from_path(
        "_perf_ab_bottleneck_oracle",
        REPO_ROOT
        / "packages/temper-placer/tests/router_v6/test_bottleneck_geometry_rust_differential.py",
    )


def bench_bottleneck_cell_capacity() -> tuple[float, float]:
    """A/B ``_compute_cell_capacity_batch`` (Rust) vs the verbatim oracle."""
    from temper_placer.router_v6.bottleneck_geometry import _compute_cell_capacity_batch

    oracle = _oracle_module()._oracle_compute_cell_capacity
    grid, cells, rules, pad_classes = _bottleneck_fixture()

    def run_rust() -> Any:
        return _compute_cell_capacity_batch(cells, grid, rules, pad_classes, "SIGNAL")

    def run_oracle() -> Any:
        return [
            oracle(
                cell=cell,
                layer=cell[0],
                grid=grid,
                net_class_rules=rules,
                net_name="NET_X",
                pad_net_classes=pad_classes,
                current_net_class="SIGNAL",
            )
            for cell in cells
        ]

    # Parity assertion inside the perf harness: a performance number for an
    # implementation that no longer agrees with its oracle is meaningless.
    if run_rust() != run_oracle():
        raise AssertionError(
            "perf A/B arms disagree for bottleneck cell_capacity -- the "
            "behavioral A/B (test_bottleneck_geometry_rust_differential.py) "
            "should be failing too"
        )
    return _time_us(run_rust, DEFAULT_WARMUP, DEFAULT_REPEATS), _time_us(
        run_oracle, DEFAULT_WARMUP, DEFAULT_REPEATS
    )


def bench_bottleneck_hard_blocked() -> tuple[float, float]:
    """A/B ``_hard_blocked_batch`` (Rust) vs the verbatim oracle."""
    from temper_placer.router_v6.bottleneck_geometry import _hard_blocked_batch

    oracle = _oracle_module()._oracle_is_hard_blocked
    grid, cells, _rules, _pad_classes = _bottleneck_fixture()

    def run_rust() -> Any:
        return _hard_blocked_batch(cells, grid)

    def run_oracle() -> Any:
        return [oracle(grid, cell) for cell in cells]

    if run_rust() != run_oracle():
        raise AssertionError(
            "perf A/B arms disagree for bottleneck hard_blocked -- the "
            "behavioral A/B should be failing too"
        )
    return _time_us(run_rust, DEFAULT_WARMUP, DEFAULT_REPEATS), _time_us(
        run_oracle, DEFAULT_WARMUP, DEFAULT_REPEATS
    )


# (module, stage) -> callable returning (rust_us, oracle_us).
#
# `module` and `stage` become the comparison key together with `board`, so they
# must stay stable once a baseline row exists. Renaming one is a baseline reset
# and fails the gate closed until the baseline row is renamed with it.
_BENCHMARKS: dict[tuple[str, str], Callable[[], tuple[float, float]]] = {
    ("bottleneck-geometry", "cell_capacity_batch"): bench_bottleneck_cell_capacity,
    ("bottleneck-geometry", "hard_blocked_batch"): bench_bottleneck_hard_blocked,
}


def run_benchmarks(commit: str = "") -> list[dict[str, Any]]:
    """Run every registered A/B and return PipelineMetricsRecord-shaped dicts."""
    records: list[dict[str, Any]] = []
    for (module, stage), fn in sorted(_BENCHMARKS.items()):
        rust_us, oracle_us = fn()
        if oracle_us <= 0:
            raise AssertionError(
                f"{module}/{stage}: oracle arm measured {oracle_us}us -- the "
                "benchmark is not exercising the reference implementation"
            )
        records.append(
            {
                "schema_version": 2,
                "timestamp": datetime.now(UTC).isoformat(),
                "git_commit": commit,
                "board": SYNTHETIC_BOARD,
                "stage": stage,
                "module": module,
                "metrics": {
                    # Gated: dimensionless, machine-independent, lower is better.
                    "rust_over_oracle_ratio": round(rust_us / oracle_us, 6),
                    # Informational only -- `_wall_us` carries no gated suffix
                    # because absolute times are not comparable across runners.
                    "rust_wall_us": round(rust_us, 3),
                    "oracle_wall_us": round(oracle_us, 3),
                },
            }
        )
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default="", help="Git commit hash for the records")
    parser.add_argument(
        "--json", action="store_true", help="Emit NDJSON records to stdout"
    )
    parser.add_argument(
        "--list", action="store_true", help="List registered benchmarks and exit"
    )
    args = parser.parse_args(argv)

    if args.list:
        for module, stage in sorted(_BENCHMARKS):
            print(f"{module}/{SYNTHETIC_BOARD}/{stage}")
        return 0

    records = run_benchmarks(args.commit)
    if not records:
        print("no benchmarks registered", file=sys.stderr)
        return 1

    if args.json:
        for record in records:
            print(json.dumps(record))
    else:
        for record in records:
            metrics = record["metrics"]
            print(
                f"{record['module']}/{record['stage']}: "
                f"ratio={metrics['rust_over_oracle_ratio']:.6f} "
                f"rust={metrics['rust_wall_us']:.1f}us "
                f"oracle={metrics['oracle_wall_us']:.1f}us",
                file=sys.stderr,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
