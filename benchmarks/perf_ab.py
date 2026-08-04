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

Capturing a baseline -- CAPTURE IT ON CI, NOT LOCALLY:
    The ratio cancels machine *speed*, but not the relative scaling of CPython
    against Rust across architectures. Measured 2026-08-04, same commit, same
    code: darwin/arm64 0.176739 vs linux/x86_64 (CI container) 0.157191 for
    cell_capacity_batch, and 0.368986 vs 0.328949 for hard_blocked_batch -- a
    consistent -11% platform bias on both.

    That bias is not cosmetic. A darwin-captured baseline of 0.176739 needs a
    CI reading above 0.212087 to trip the 20% margin, which is +34.9% against
    what CI actually measures on unmodified code -- so the gate would silently
    miss every regression between +20% and +35%, while reporting a spurious
    "IMPROVED" on every clean PR.

    To capture: trigger .github/workflows/pr-perf-check.yml on main -- it runs
    on every main push into its trigger paths, and on demand via
    workflow_dispatch. In capture mode it skips the comparison and publishes the
    measured rows twice: inline in the job summary (copy-paste ready) and as the
    ``perf-ab-baseline-rows-<run>-<attempt>`` artifact. Append them to
    power_pcb_dataset/metrics/perf_ab_baseline.jsonl in a reviewed PR. Nothing
    writes this file automatically, by design: it is the bar a hard merge gate
    measures against, and every appended row moves it.

Baseline WIDTH -- keep 5+ rows per (module, board, stage):
    The comparison takes a rolling median of the trailing 5 rows per key. With
    one row the "median" is that row, so nothing is smoothed and the full CI
    spread lands against the 20% margin. That is not hypothetical: from
    2026-08-04 the baseline held exactly one row per stage, because this
    workflow triggered on ``pull_request`` only and no main row could ever be
    measured. PR #544 -- a one-line ``typing.cast()`` in
    router_v6/channel_widths.py, a runtime no-op in a module this benchmark
    does not touch -- was reported as a +26.6% regression on hard_blocked_batch.
    The same reading scores +15.7% against a 5-row baseline and passes.

    The single row was also a systematic low outlier, not merely noisy: every
    one of the five later CI readings landed above it, by +4.4% to +26.6%
    (mean ~+10.5%). A biased baseline spends half the margin as a constant
    offset before any real variance is measured. Leave-one-out over the same
    five readings against a 5-row median: max excursion 15.7%, zero gate trips.

    Only append rows measured on a commit that does not modify the benchmarked
    module -- a row from a commit that changed the kernel ratchets the bar to
    whatever that change did, which is exactly what the gate exists to catch.
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


# ---------------------------------------------------------------------------
# Wave 4 Phase 3 candidate 6: the DSN emitter (temper_placer/io/dsn_exporter.py)
# ---------------------------------------------------------------------------

_DSN_SEED = 20260804
_DSN_COMPONENTS = 40
_DSN_PINS_PER_COMPONENT = 8


def _dsn_fixture() -> tuple[Any, Any]:
    """A deterministic board+netlist of realistic size for the DSN emitter.

    Fixed seed and shape: the ratio is only comparable across runs if both arms
    serialize byte-identical input every time.
    """
    from temper_placer.core.board import Board, Layer, LayerStackup
    from temper_placer.core.netlist import Component, Net, Netlist, Pin

    rng = random.Random(_DSN_SEED)
    components = []
    for i in range(_DSN_COMPONENTS):
        pins = [
            Pin(
                name=f"P{j}",
                number=str(j + 1),
                position=(rng.uniform(-3.0, 3.0), rng.uniform(-3.0, 3.0)),
                width=rng.choice([0.3, 0.5, 0.6, 1.0]),
                height=rng.choice([0.4, 0.8, 1.5]),
                shape=rng.choice(["rect", "circle", "thru_hole", "oval"]),
                layer=rng.choice(["F.Cu", "B.Cu", "all"]),
            )
            for j in range(_DSN_PINS_PER_COMPONENT)
        ]
        components.append(
            Component(
                ref=f"{rng.choice('URCQJ')}{i}",
                footprint=f"Lib{i % 7}:Foot_{i % 11}",
                bounds=(5.0, 4.0),
                pins=pins,
                initial_position=(rng.uniform(0.0, 90.0), rng.uniform(0.0, 60.0)),
                initial_rotation=rng.randint(0, 3),
            )
        )

    refs = [c.ref for c in components]
    nets = [
        Net(
            name=rng.choice(["GND", "VCC3V3", "+5V", "DC_BUS-", f"NET{k}", f"sig_vdd{k}v"]),
            pins=[
                (rng.choice(refs), str(rng.randint(1, _DSN_PINS_PER_COMPONENT)))
                for _ in range(rng.randint(2, 6))
            ],
        )
        for k in range(60)
    ]

    board = Board(
        width=100.0,
        height=70.0,
        keepouts=[
            (rng.uniform(0, 90), rng.uniform(0, 60), rng.uniform(0, 90), rng.uniform(0, 60))
            for _ in range(12)
        ],
        layer_stackup=LayerStackup(
            layers=[
                Layer(name="F.Cu", layer_type="signal"),
                Layer(name="In1.Cu", layer_type="plane"),
                Layer(name="In2.Cu", layer_type="mixed"),
                Layer(name="B.Cu", layer_type="signal"),
            ]
        ),
    )
    return board, Netlist(components=components, nets=nets)


def _dsn_oracle_module() -> ModuleType:
    # The exporter oracle imports its sibling primitives oracle as
    # `tests.io._dsn_py_oracle`, so the package root has to be importable.
    # (pytest puts it there via rootdir; this harness runs outside pytest.)
    placer_root = str(REPO_ROOT / "packages/temper-placer")
    if placer_root not in sys.path:
        sys.path.insert(0, placer_root)
    return _load_module_from_path(
        "_perf_ab_dsn_exporter_oracle",
        REPO_ROOT / "packages/temper-placer/tests/io/_dsn_exporter_py_oracle.py",
    )


def bench_dsn_export_pcb() -> tuple[float, float]:
    """A/B the full ``export_pcb`` serialization (Rust) vs the verbatim oracle.

    Per R2 this is the *no-regression-beyond-noise* arm: DSN export is
    I/O-shaped string building, not a compute kernel, and a large part of the
    remaining cost is on the Python side of the boundary either way (attribute
    reads off the duck-typed Board/Netlist, and the schema hash). No speedup is
    claimed; the gate is that the ratio does not drift upward.
    """
    from temper_placer.io.dsn_exporter import DSNExporter

    oracle_cls = _dsn_oracle_module().DSNExporter
    board, netlist = _dsn_fixture()

    def run_rust() -> Any:
        return str(DSNExporter(board, netlist).export_pcb("bench"))

    def run_oracle() -> Any:
        return str(oracle_cls(board, netlist).export_pcb("bench"))

    # Parity assertion inside the perf harness: a performance number for an
    # implementation that no longer agrees with its oracle is meaningless.
    # Byte equality, because bytes are this surface's contract.
    if run_rust() != run_oracle():
        raise AssertionError(
            "perf A/B arms disagree for dsn export_pcb -- the behavioral A/B "
            "(test_dsn_rust_differential.py) should be failing too"
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
    ("dsn-exporter", "export_pcb"): bench_dsn_export_pcb,
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
