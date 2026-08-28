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

    A bench that depends on a surface that has not landed on this branch yet
    (e.g. the deterministic-hubs arm before its kernels merge) returns None;
    ``run_benchmarks`` skips it with a stderr note. The entry stays in
    ``_BENCHMARKS`` (the registry CI reads from main to distinguish
    NEW_BENCHMARK from NO_BASELINE), and the arm activates the moment the
    surface exists -- no second change needed.

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

Capture SEVERAL runs of the SAME commit -- the margins depend on it:
    Since 2026-08-05 the gate's per-benchmark margins are derived from the
    spread of baseline rows that share a ``git_commit``. Within one commit the
    code is identical, so that spread is noise by construction; across commits
    it may be real performance change, and using it would absorb genuine
    regressions into the margin. Groups of 5 same-commit rows are the unit;
    ``workflow_dispatch`` runs in parallel (PR #734), so five dispatches on one
    ref produce one group in one sitting. See
    docs/evidence/2026-08-05-perf-ab-per-benchmark-margin.md and
    ``scripts/pr_perf_compare.py --derive-margins``.

    Five arms are currently NOT GATED because their fixed-commit noise leaves
    no band between noise and the smallest real regression on record (+50.7%):
    physics-emi/predict (42.8%), parse-engine/parse_kicad_pcb (32.5%),
    board-netlist/contracts_construction (30.9%), drc-geometry/point_rect
    (26.0%), physics-heat_removal/build_h_field (24.4%). The remedy lives in
    THIS file, not in the gate: the noisiest arms are the ones with the
    smallest timed region (build_h_field runs 1.6us; cell_capacity_batch runs
    590us and measures 3.7%). Raising DEFAULT_REPEATS for those arms, or
    batching them the way bench_physics_emi already batches 500 calls, is what
    earns them their gate back.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import random
import statistics
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

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
# Wave 4 Phase 5: deterministic hubs
# (deterministic/{bottleneck_map,channels,seed_filter,feedback/*} ->
# temper-design-bundle deterministic_hubs)
# ---------------------------------------------------------------------------
# Registered as the #767 R1b follow-up (docs/evidence/2026-08-04-wave4-phase5-
# deterministic-hubs-records.md): the earlier "ratio 0.909" record was
# withdrawn because it had no committed artifact -- no bench function,
# fixture, `_BENCHMARKS` entry, or script. This arm is that artifact.
#
# It A/Bs the bottleneck-map `score_at` hot path against the verbatim oracle
# the behavioral differential pins, and the Rust arm replicates the shim's
# exact per-call call shape (deterministic/bottleneck_map.py `score_at`):
# the O(n) `list(self.scores)` marshalling copy sits INSIDE the timed region,
# per call -- the unmeasured hot-path cost the R1b record names (100x100 map
# = 10,000 floats copied per lookup; `filter_seed` calls `score_at` once per
# seed ref). The parity assertion is the harness's own behavioral gate, same
# convention as every other arm.
#
# Availability: the kernels (and the oracle module this arm loads) land in
# the deterministic-hubs slice (PR #767). Until that merge, this arm returns
# None and the harness skips it (see `run_benchmarks`) -- a registered-but-
# dormant arm, not a crash that takes every other benchmark down with it.
# The kernels and the oracle ship in the same slice, so they appear and
# disappear together; once #767 is on main the arm activates with no further
# change.

_DETERMINISTIC_HUBS_ORACLE_DIR = REPO_ROOT / "packages" / "temper-placer" / "tests" / "deterministic"


def _hubs_bottleneck_fixture() -> tuple[dict[str, Any], list[tuple[float, float]]]:
    """Fixed realistic BottleneckMap + sidecar payload shape for the hubs arm.

    Built from the same fixed seed as the other fixtures so the A/B ratio is
    comparable across runs. The payload dict is shaped exactly like a
    ``placement.channels.json`` sidecar (the shape ``_from_sidecar_payload``
    consumes): ``cell_size_mm``/``width``/``height``/``origin_xy``/``scores``.
    100x100 cells = the R1b record's example of the per-call
    ``list(self.scores)`` marshalling cost (10,000 floats per lookup). The
    probe set is a seeded lattice across the map plus the boundary/OOB and
    overflow probes the differential drives (cell edges, just-inside /
    just-outside the extent, huge quotients).
    """
    rng = random.Random(_BENCH_SEED)
    payload: dict[str, Any] = {
        "cell_size_mm": 1.0,
        "width": 100,
        "height": 100,
        "origin_xy": [0.0, 0.0],
        "scores": [round(rng.uniform(0.0, 1.0), 4) for _ in range(100 * 100)],
    }
    probes: list[tuple[float, float]] = [
        (round(rng.uniform(0.0, 100.0), 3), round(rng.uniform(0.0, 100.0), 3))
        for _ in range(256)
    ]
    probes += [
        (0.0, 0.0),
        (50.0, 50.0),
        (99.999, 99.999),
        (100.0, 50.0),  # exactly on the extent edge -> col >= width -> 0.0
        (100.5, 50.0),  # just beyond the extent
        (-0.001, 50.0),  # just before the origin -> 0.0
        (50.0, -0.001),
        (1e308, 1e308),  # huge-quotient probe (floor-div of a 1e308 co-ord)
    ]
    return payload, probes


# ---------------------------------------------------------------------------
# Wave 4 Phase 4: physics kernels (temper_placer/physics/* -> temper-thermal)
# ---------------------------------------------------------------------------
# The oracles are imported from the Phase-4 differential files, exactly as the
# behavioral A/B pins them.  Fixtures are fixed-shape and fixed-seed so the
# A/B ratio is comparable across runs.  The parity assertion inside each bench
# is the perf harness's own behavioral gate: a perf number for an
# implementation that disagrees with its oracle is meaningless.


def _physics_oracle(path_name: str, file_name: str) -> ModuleType:
    return _load_module_from_path(
        f"_perf_ab_{path_name}",
        REPO_ROOT / "packages" / "temper-placer" / "tests" / "physics" / file_name,
    )


# REMOVED 2026-08-24: bench_physics_emi and bench_physics_safety.
#
# #1411 deleted BOTH arms of each A/B -- the temper-thermal pyfunction
# bridges (`predict_radiated_emissions_py` and `estimate_filter_delay_py`,
# two of the 8 it removed from emi.rs/safety.rs) and the paired oracles
# (`tests/physics/test_emi_rust_differential.py` and
# `test_safety_rust_differential.py`).  This file was missed in that sweep,
# so it kept benchmarking two implementations that no longer exist, and died
# on the first of them:
#
#   FileNotFoundError: oracle module not found:
#     packages/temper-placer/tests/physics/test_emi_rust_differential.py
#
# That crash is why `PR Performance Comparison` -- and through it the
# `Required Python Tests` aggregator, the only required check on main -- has
# been red on every PR since.  `bench_physics_safety` never ran at all:
# `run_benchmarks` iterates `sorted(_BENCHMARKS)` and emi comes first, so its
# own identically-dead oracle stayed invisible behind the traceback.
#
# Their rows in power_pcb_dataset/metrics/perf_ab_baseline.jsonl are
# deliberately NOT deleted, and neither are their entries in
# pr_perf_compare.py's PER_BENCHMARK_TIMING_MARGIN / UNGATEABLE_BENCHMARKS.
# That file is an append-only measurement history ("nothing writes this file
# automatically, by design"); the gate fails on a PR record with no baseline
# row, never on a baseline row with no PR record, so the orphaned history is
# inert.  The comparator's two tables are keyed against that history --
# `test_no_benchmark_is_gated_tighter_than_its_measured_noise` derives its
# keys from the baseline records themselves -- so dropping the entries while
# the rows remain would break that invariant, not tidy it.

def _heat_removal_fixture():
    mod = _physics_oracle("heat_removal", "test_heat_removal_rust_differential.py")
    cfg = mod._cfg(16, 16, 1.0)
    devices = {"Q1": (3.0, 3.0), "Q2": (8.0, 5.0), "Q3": (12.0, 12.0), "Q4": (5.0, 11.0)}
    device_thermal = {k: mod._dev_cfg(k, 0.25, 1.0) for k in devices}
    xs = [devices[k][0] for k in devices]
    ys = [devices[k][1] for k in devices]
    r_cs = [device_thermal[k].R_theta_cs for k in devices]
    r_sa = [device_thermal[k].R_theta_sa for k in devices]
    return mod, cfg, devices, device_thermal, xs, ys, r_cs, r_sa


def bench_physics_heat_removal() -> tuple[float, float]:
    """A/B build_h_field (Rust grid kernel) vs the verbatim oracle."""
    import temper_thermal as _tt

    mod, cfg, devices, device_thermal, xs, ys, r_cs, r_sa = _heat_removal_fixture()

    def run_rust() -> Any:
        raw = _tt.build_h_field_py(
            cfg.cell_size_mm, cfg.origin_mm[0], cfg.origin_mm[1],
            cfg.height_cells, cfg.width_cells, xs, ys, r_cs, r_sa,
        )
        return len(raw)

    def run_oracle() -> Any:
        return mod._oracle_build_h_field(cfg, devices, device_thermal).size

    import numpy as np

    raw = _tt.build_h_field_py(
        cfg.cell_size_mm, cfg.origin_mm[0], cfg.origin_mm[1],
        cfg.height_cells, cfg.width_cells, xs, ys, r_cs, r_sa,
    )
    got = np.frombuffer(raw, dtype=np.float64).reshape((cfg.height_cells, cfg.width_cells))
    want = mod._oracle_build_h_field(cfg, devices, device_thermal)
    if not np.array_equal(got, want):
        raise AssertionError("perf A/B arms disagree for physics-heat_removal")
    return _time_us(run_rust, DEFAULT_WARMUP, DEFAULT_REPEATS), _time_us(
        run_oracle, DEFAULT_WARMUP, DEFAULT_REPEATS
    )


def bench_physics_copper_masks() -> tuple[float, float]:
    """A/B the copper-coverage masks (Rust grid kernel) vs the oracle."""
    import temper_thermal as _tt

    mod = _physics_oracle("copper", "test_copper_coverage_phase4_rust_differential.py")
    h, w = 24, 24
    keepouts = [(10.0, 10.0, 20.0, 20.0), (50.0, 0.0, 60.0, 30.0)]
    holes = [(80.0, 80.0, 5.0)]  # oracle form (mx, my, keepout_radius)
    holes_flat = [80.0, 80.0, 5.0]  # Rust flat form
    keep_flat = [v for k in keepouts for v in k]

    def run_rust() -> Any:
        ib, ko, act = _tt.copper_masks_py(h, w, 0.0, 0.0, 5.0, 100.0, 100.0, False, None, keep_flat, holes_flat)
        return len(ib) + len(ko) + len(act)

    def run_oracle() -> Any:
        a, b, c = mod._oracle_masks(h, w, 0.0, 0.0, 5.0, 100.0, 100.0, None, keepouts, holes)
        return a.size + b.size + c.size

    import numpy as np

    ib, ko, act = _tt.copper_masks_py(h, w, 0.0, 0.0, 5.0, 100.0, 100.0, False, None, keep_flat, holes_flat)
    got = np.frombuffer(act, dtype=np.bool_).reshape((h, w))
    want = mod._oracle_masks(h, w, 0.0, 0.0, 5.0, 100.0, 100.0, None, keepouts, holes)[2]
    if not np.array_equal(got, want):
        raise AssertionError("perf A/B arms disagree for physics-copper_masks")
    return _time_us(run_rust, DEFAULT_WARMUP, DEFAULT_REPEATS), _time_us(
        run_oracle, DEFAULT_WARMUP, DEFAULT_REPEATS
    )


def bench_physics_device_check() -> tuple[float, float]:
    """A/B device_cross_check (Rust scalar chain) vs the verbatim oracle."""
    import temper_thermal as _tt

    oracle = _physics_oracle("tj", "test_tj_cross_check_rust_differential.py")._oracle_device_cross_check
    args = (50.0, 5.0, 0.6, 0.25, 1.0, 40.0, 150.0, 5.0)

    def run_rust() -> Any:
        return [_tt.device_cross_check_py(*args) for _ in range(500)][-1]

    def run_oracle() -> Any:
        return [oracle(*args) for _ in range(500)][-1]

    if run_rust() != run_oracle():
        raise AssertionError("perf A/B arms disagree for physics-device_check")
    return _time_us(run_rust, DEFAULT_WARMUP, DEFAULT_REPEATS), _time_us(
        run_oracle, DEFAULT_WARMUP, DEFAULT_REPEATS
    )


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
# Wave 4 Phase 4 -- topological placement (temper-placement-topology)
# ---------------------------------------------------------------------------


def _topological_oracles() -> tuple[ModuleType, ModuleType, ModuleType]:
    """The verbatim pinned oracles the R1a differential uses.

    These are imported under their real ``tests.topological.*`` names rather
    than loaded from a path, because they import each other by that package
    name -- loading them standalone would break the sibling imports.
    """
    import importlib

    placer_root = str(REPO_ROOT / "packages/temper-placer")
    if placer_root not in sys.path:
        sys.path.insert(0, placer_root)

    graph = importlib.import_module("tests.topological._graph_py_oracle")
    prop = importlib.import_module("tests.topological._propagation_py_oracle")
    force = importlib.import_module("tests.topological._force_refinement_py_oracle")
    return graph, prop, force


@cache
def _topological_bench_fixture() -> ModuleType:
    """The fixture module the R1a differential also imports.

    One source of inputs for both gates, so the benchmark cannot reach a
    parameterisation the behavioral A/B has not compared. Before this existed
    the differential covered ``iterations in [0, 1, 2, 8, 17, 100]`` on its own
    small graphs and the benchmark ran ``(120, 0.05)`` on a 26-component one,
    so the perf job was the only gate that ever executed those parameters.

    Memoised because ``_topological_fixture`` runs inside the timed closures:
    re-executing the module on every repeat would land in the measurement.
    """
    return _load_module_from_path(
        "_perf_ab_topo_bench_fixture",
        REPO_ROOT / "packages/temper-placer/tests/topological/_topo_bench_fixture.py",
    )


def _topological_fixture(graph_cls: Any, n: int | None = None) -> Any:
    """A deterministic connected constraint graph, from the shared module."""
    fixture = _topological_bench_fixture()
    return fixture.build_graph(graph_cls, fixture.BENCH_N if n is None else n)


@contextmanager
def _two_vector_norm_pinned_to_the_ported_contract() -> Iterator[None]:
    """Make both arms evaluate the 2-vector norm the *same* way, by contract.

    Force refinement's only step that IEEE-754 does not pin to a single answer
    is the squared length inside ``np.linalg.norm``. For a 2-vector NumPy
    evaluates ``sqrt(v.dot(v))``, and ``v.dot(v)`` is a BLAS ``ddot``: on the
    OpenBLAS that ships in NumPy's manylinux wheels the n<16 tail loop is
    selected by CPUID at load time, and whether it contracts ``dot += x[i]*y[i]``
    into an FMA differs between kernels. ``temper-placement-topology``'s
    ``numeric::norm2`` is the unfused ``sqrt(x*x + y*y)``, which is what the
    port was verified against -- so on a runner whose ddot contracts, the two
    arms compute genuinely different distances, 1 ULP apart on ~8% of vectors.

    That is not a tolerance problem that more iterations would wash out. The
    benchmark's fixture is a bounded but non-converging force simulation (its
    per-iteration step is still O(1) at iteration 400) and a single ULP grows
    to 1.2e-1 mm by iteration 120, so an exact comparison of the endpoint has
    no error budget at all. It fails at *iteration 1* on a 73-edge graph,
    because with ~8% of norms at risk some edge diverges immediately.

    So this pins the primitive rather than the result: for the duration of the
    parity check ``np.linalg.norm`` on a 2-vector is the association
    ``numeric.rs`` documents and ``norm2`` implements. It is exactly the same
    move the shim already makes for edge order -- make the shared input
    explicit instead of letting the environment choose it -- and like that one
    it normalises nothing about the *computation*: no sorting, no compensated
    accumulation, no tolerance, and the parity assertion itself is untouched.

    This can never hide a real divergence, because it is only ever a no-op on a
    platform CI is green on: ``test_norm_contract_holds_on_this_platform`` in
    the differential asserts, over 20k randomised vectors, that this platform's
    ``np.linalg.norm`` already *is* this association. If a runner violates the
    contract, that test fails and names it; the flake used to surface here
    instead, as an unexplained "arms disagree" 40 minutes into a perf job.

    Deliberately NOT wrapped around the timed runs -- only the parity check.
    A Python-level norm has a different cost from ``np.linalg.norm``, and the
    gated metric is a ratio against a committed baseline.
    """
    import numpy as np

    real_norm = np.linalg.norm

    def norm(x: Any, *args: Any, **kwargs: Any) -> Any:
        if not args and not kwargs and getattr(x, "shape", None) == (2,):
            a = float(x[0])
            b = float(x[1])
            return math.sqrt(a * a + b * b)
        return real_norm(x, *args, **kwargs)

    np.linalg.norm = norm
    try:
        yield
    finally:
        np.linalg.norm = real_norm


def bench_topological_propagation() -> tuple[float, float]:
    """A/B the O(n^3) Floyd-Warshall bound propagation."""
    from temper_placer.topological.graph import TopologicalGraph
    from temper_placer.topological.propagation import ConstraintPropagator

    graph_oracle, prop_oracle, _ = _topological_oracles()

    def run_rust() -> Any:
        g, refs = _topological_fixture(TopologicalGraph)
        p = ConstraintPropagator(g)
        ok = p.propagate()
        return ok, [(p.get_bound(a, b).min_distance, p.get_bound(a, b).max_distance)
                    for a in refs for b in refs]

    def run_oracle() -> Any:
        g, refs = _topological_fixture(graph_oracle.TopologicalGraph)
        p = prop_oracle.ConstraintPropagator(g)
        ok = p.propagate()
        return ok, [(p.get_bound(a, b).min_distance, p.get_bound(a, b).max_distance)
                    for a in refs for b in refs]

    if run_rust() != run_oracle():
        raise AssertionError(
            "perf A/B arms disagree for topological propagation -- the "
            "behavioral A/B (test_topological_rust_differential.py) should be "
            "failing too"
        )
    return _time_us(run_rust, DEFAULT_WARMUP, DEFAULT_REPEATS), _time_us(
        run_oracle, DEFAULT_WARMUP, DEFAULT_REPEATS
    )


def bench_topological_force_refinement() -> tuple[float, float]:
    """A/B the iterative force-directed refinement loop."""
    from temper_placer.core.board import Zone
    from temper_placer.topological.force_refinement import apply_force_refinement
    from temper_placer.topological.graph import TopologicalGraph

    graph_oracle, _, force_oracle = _topological_oracles()
    fixture = _topological_bench_fixture()

    zones = fixture.bench_zones(Zone)
    iterations = fixture.BENCH_ITERATIONS
    lr = fixture.BENCH_LEARNING_RATE

    def run_rust() -> Any:
        g, refs = _topological_fixture(TopologicalGraph)
        return apply_force_refinement(
            fixture.bench_positions(refs),
            g,
            zones,
            fixture.bench_zone_assignments(refs),
            iterations,
            lr,
        )

    def run_oracle() -> Any:
        g, refs = _topological_fixture(graph_oracle.TopologicalGraph)
        return force_oracle.apply_force_refinement(
            fixture.bench_positions(refs),
            g,
            zones,
            fixture.bench_zone_assignments(refs),
            iterations,
            lr,
        )

    with _two_vector_norm_pinned_to_the_ported_contract():
        arms_agree = run_rust() == run_oracle()
    if not arms_agree:
        raise AssertionError(
            "perf A/B arms disagree for topological force refinement -- the "
            "behavioral A/B should be failing too "
            "(test_apply_force_refinement_identical_at_benchmark_parameters "
            "runs this exact fixture at these exact parameters)"
        )
    return _time_us(run_rust, DEFAULT_WARMUP, DEFAULT_REPEATS), _time_us(
        run_oracle, DEFAULT_WARMUP, DEFAULT_REPEATS
    )


# ---------------------------------------------------------------------------
# Wave 4 Phase 4: geometry/drc_inflate.py DRC-proxy kernels
# ---------------------------------------------------------------------------

# Fixed shape and seed, same reason as the bottleneck fixture above. 40
# components is 780 pairs, past numpy's 128-element pairwise blocksize, so both
# arms exercise the blocked reduction rather than its small-input shortcut.
_DRC_COMPONENTS = 40
_DRC_SEED = 20260804
_SMOOTH_RELU_SAMPLES = 4096


def _drc_inflate_oracle() -> ModuleType:
    return _load_module_from_path(
        "_perf_ab_drc_inflate_oracle",
        REPO_ROOT / "packages/temper-placer/tests/geometry/_drc_inflate_py_oracle.py",
    )


def _drc_fixture() -> tuple[Any, Any, Any]:
    """Deterministic float32 placement — the dtype every shipped call site uses."""
    import numpy as np

    rng = np.random.default_rng(_DRC_SEED)
    positions = rng.uniform(-40.0, 40.0, size=(_DRC_COMPONENTS, 2)).astype(np.float32)
    hw = rng.uniform(0.5, 6.0, size=(_DRC_COMPONENTS,)).astype(np.float32)
    hh = rng.uniform(0.5, 6.0, size=(_DRC_COMPONENTS,)).astype(np.float32)
    return positions, hw, hh


def bench_drc_proxy_score() -> tuple[float, float]:
    """A/B ``compute_drc_proxy_score`` (Rust) vs the verbatim oracle."""
    from temper_placer.geometry.drc_inflate import compute_drc_proxy_score

    oracle_fn = _drc_inflate_oracle().compute_drc_proxy_score
    positions, hw, hh = _drc_fixture()

    def run_rust() -> Any:
        return compute_drc_proxy_score(positions, hw, hh, clearance_mm=0.2, beta=10.0)

    def run_oracle() -> Any:
        return oracle_fn(positions, hw, hh, clearance_mm=0.2, beta=10.0)

    # The behavioural gate is bit-exact, so this parity check is too: a
    # performance number for an arm that no longer agrees is meaningless.
    if float(run_rust()).hex() != float(run_oracle()).hex():
        raise AssertionError(
            "perf A/B arms disagree for drc_proxy_score -- the behavioral A/B "
            "(test_drc_inflate_rust_differential.py) should be failing too"
        )
    return _time_us(run_rust, DEFAULT_WARMUP, DEFAULT_REPEATS), _time_us(
        run_oracle, DEFAULT_WARMUP, DEFAULT_REPEATS
    )


def bench_smooth_relu_array() -> tuple[float, float]:
    """A/B the vectorised softplus (Rust) vs the verbatim numpy oracle.

    Registered separately from ``drc_proxy_score`` because it is the arm most
    likely to regress: numpy's elementwise loop is already vectorised, so this
    is the honest place for the ratio to be visible rather than buried inside
    an O(n^2) caller.
    """
    import numpy as np

    from temper_placer.geometry.drc_inflate import _smooth_relu_array

    oracle_fn = _drc_inflate_oracle()._smooth_relu_array
    xs = np.random.default_rng(_DRC_SEED).uniform(-8.0, 8.0, size=_SMOOTH_RELU_SAMPLES)

    def run_rust() -> Any:
        return _smooth_relu_array(xs, alpha=10.0)

    def run_oracle() -> Any:
        return oracle_fn(xs, alpha=10.0)

    got, want = run_rust(), run_oracle()
    if [float(v).hex() for v in got] != [float(v).hex() for v in want]:
        raise AssertionError(
            "perf A/B arms disagree for smooth_relu_array -- the behavioral "
            "A/B should be failing too"
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
                initial_rotation_quadrant=rng.randint(0, 3),
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


# ---------------------------------------------------------------------------
# Wave 4 Phase 3 candidate 2: the YAML loaders (Rust orchestration vs the
# verbatim pre-migration Python loaders, on the repo's own shipped fixtures)
# ---------------------------------------------------------------------------


def _scalar_hex(value: Any) -> tuple[str, Any]:
    """Type-preserving canonical key for a leaf (floats via ``.hex()``)."""
    if isinstance(value, float):
        return ("float", value.hex())
    if isinstance(value, bool):
        return ("bool", value)
    return (type(value).__name__, value)


def _event_fields(ev):
    """Canonical key for a LoopEvent's six fields (None-preserving)."""
    return tuple(
        None if v is None else _scalar_hex(v)
        for v in (
            ev.di_dt,
            ev.dv_dt,
            ev.frequency_hz,
            ev.peak_current_a,
            ev.rms_current_a,
            ev.ringing_freq_hz,
        )
    )


def _canon_netclass_rules(result: Any) -> tuple[Any, ...]:
    """Deterministic fingerprint of a loaded netclass rules result — every
    field of the ``DesignRules`` instance, mirroring the differential's
    ``_design_rules_fields`` so a mutation confined to an omitted field
    cannot pass the inline parity sanity."""
    dr = result.design_rules

    def net_class_fields(nc):
        return tuple(sorted((k, _scalar_hex(v)) for k, v in nc.model_dump().items()))

    def class_pairs_fields(pairs):
        return tuple(
            (
                key,
                tuple(sorted((k, _scalar_hex(v)) for k, v in value.items())),
            )
            for key, value in sorted(pairs.items())
        )

    def via_template_fields(vt):
        return (
            vt.name,
            vt.rows,
            vt.cols,
            _scalar_hex(vt.via_diameter_mm),
            _scalar_hex(vt.via_drill_mm),
            _scalar_hex(vt.pitch_mm),
        )

    return (
        _scalar_hex(dr.default_trace_width),
        _scalar_hex(dr.default_clearance),
        _scalar_hex(dr.default_via_diameter),
        _scalar_hex(dr.default_via_drill),
        tuple(sorted((name, net_class_fields(nc)) for name, nc in dr.net_classes.items())),
        tuple(sorted(dr.net_overrides.items())),
        tuple(sorted(dr.net_class_assignments.items())),
        tuple(dr.differential_pairs),
        tuple(dr.bus_cohorts),
        tuple(sorted(dr.net_topologies.items())),
        tuple(sorted((name, via_template_fields(vt)) for name, vt in dr.via_templates.items())),
        class_pairs_fields(result.class_pairs),
    )


def _canon_loop_collection(coll: Any) -> tuple[Any, ...]:
    """Deterministic fingerprint of a loaded loop collection — every
    constructor field of every loop plus the collection fields, mirroring
    the differential's ``_loop_fields``/``_collection_fields`` so a mutation
    confined to an omitted field cannot pass the inline parity sanity."""
    loops = tuple(
        sorted(
            (
                loop.name,
                (loop.loop_type.name, loop.loop_type.value),
                loop.description,
                tuple(
                    (p.component_ref, p.pin_name, p.net_name, type(p.net_name).__name__)
                    for p in loop.pins
                ),
                tuple(loop.components),
                tuple(loop.nets),
                _scalar_hex(loop.max_area_mm2),
                (loop.priority.name, loop.priority.value),
                _event_fields(loop.events),
                loop.return_layer,
                loop.return_net,
                loop.source,
                None
                if loop.get_current_area() is None
                else _scalar_hex(loop.get_current_area()),
            )
            for loop in coll.loops
        )
    )
    return (coll.name, coll.description, loops)


def bench_loaders() -> tuple[float, float]:
    """A/B the migrated YAML loaders vs the verbatim pre-migration Python.

    Both arms parse the SAME files with the SAME PyYAML tokenizer and call
    the SAME contract constructors; the delta is the mapping/orchestration
    layer (Rust in ``temper-design-bundle`` vs Python). This is the R2
    "no regression beyond noise" arm for a pure-delegation, I/O-shaped
    surface — NOT a speedup claim.
    """
    from temper_placer.io.loop_loader import load_loop_collection
    from temper_placer.io.netclass_loader import load_netclass_rules

    netclass_oracle = _load_module_from_path(
        "_perf_ab_netclass_loader_oracle",
        REPO_ROOT / "packages/temper-placer/tests/io/_netclass_loader_py_oracle.py",
    )
    loop_oracle = _load_module_from_path(
        "_perf_ab_loop_loader_oracle",
        REPO_ROOT / "packages/temper-placer/tests/io/_loop_loader_py_oracle.py",
    )
    netclass_yaml = REPO_ROOT / "packages/temper-placer/configs/netclass_rules.yaml"
    loop_dir = REPO_ROOT / "packages/temper-placer/configs/templates/loops"

    def run_rust() -> None:
        load_netclass_rules(netclass_yaml)
        load_loop_collection(loop_dir)

    def run_oracle() -> None:
        netclass_oracle.load_netclass_rules(netclass_yaml)
        loop_oracle.load_loop_collection(loop_dir)

    # Parity sanity inside the perf harness (the full A/B is the differential
    # suite): a performance number for an implementation that no longer
    # agrees with its oracle is meaningless.
    if _canon_netclass_rules(load_netclass_rules(netclass_yaml)) != _canon_netclass_rules(
        netclass_oracle.load_netclass_rules(netclass_yaml)
    ):
        raise AssertionError(
            "perf A/B arms disagree for loaders/netclass -- the behavioral "
            "A/B (test_loaders_rust_differential.py) should be failing too"
        )
    if _canon_loop_collection(load_loop_collection(loop_dir)) != _canon_loop_collection(
        loop_oracle.load_loop_collection(loop_dir)
    ):
        raise AssertionError(
            "perf A/B arms disagree for loaders/loop_collection -- the "
            "behavioral A/B (test_loaders_rust_differential.py) should be "
            "failing too"
        )
    return _time_us(run_rust, DEFAULT_WARMUP, DEFAULT_REPEATS), _time_us(
        run_oracle, DEFAULT_WARMUP, DEFAULT_REPEATS
    )


# ---------------------------------------------------------------------------
# Wave 4 Phase 2: pcl/tag_dispatch.py + pcl/_parse_utils.py
# ---------------------------------------------------------------------------
#
# Both arms drive the fixture in
# packages/temper-placer/tests/pcl/_pcl_bench_fixture.py, which
# tests/pcl/test_pcl_bench_fixture_parity.py asserts full oracle parity over.
# That import is the #714 gate made structural: the benchmark cannot reach an
# input the differential has not compared, because there is one source of
# inputs. (#714 passed a differential at iterations [0,1,2,8,17,100] and then
# failed Linux CI on a benchmark that ran 120.)


def _pcl_fixture_module() -> ModuleType:
    return _load_module_from_path(
        "_perf_ab_pcl_bench_fixture",
        REPO_ROOT / "packages/temper-placer/tests/pcl/_pcl_bench_fixture.py",
    )


def _pcl_tag_oracle_module() -> ModuleType:
    return _load_module_from_path(
        "_perf_ab_pcl_tag_oracle",
        REPO_ROOT / "packages/temper-placer/tests/pcl/_tag_dispatch_py_oracle.py",
    )


def _pcl_parse_oracle_module() -> ModuleType:
    return _load_module_from_path(
        "_perf_ab_pcl_parse_oracle",
        REPO_ROOT / "packages/temper-placer/tests/pcl/_parse_utils_py_oracle.py",
    )


def bench_pcl_tag_resolve_sweep() -> tuple[float, float]:
    """A/B the tag-expression sweep over a netlist: Rust pyclasses vs oracle.

    This is the call the Phase-2 pivot exists for. In the oracle arm the
    expression tree is a graph of Python dataclasses re-walked per component;
    in the Rust arm the same tree is a graph of pyo3 pyclasses, so the whole
    400-component sweep happens without re-marshalling it.
    """
    from temper_placer.pcl import tag_dispatch as live

    fixture = _pcl_fixture_module()
    oracle = _pcl_tag_oracle_module()

    netlist = fixture.bench_netlist()
    specs = fixture.bench_expr_specs()
    live_exprs = [fixture.build_expr(s, live) for s in specs]
    oracle_exprs = [fixture.build_expr(s, oracle) for s in specs]

    def run_rust() -> Any:
        return [[c.ref for c in live.components(e, netlist)] for e in live_exprs]

    def run_oracle() -> Any:
        return [[c.ref for c in oracle.components(e, netlist)] for e in oracle_exprs]

    # Parity assertion inside the perf harness: a performance number for an
    # implementation that no longer agrees with its oracle is meaningless.
    if run_rust() != run_oracle():
        raise AssertionError(
            "perf A/B arms disagree for pcl tag_resolve_sweep -- the behavioral "
            "A/B (test_tag_dispatch_rust_differential.py) should be failing too"
        )
    return _time_us(run_rust, DEFAULT_WARMUP, DEFAULT_REPEATS), _time_us(
        run_oracle, DEFAULT_WARMUP, DEFAULT_REPEATS
    )


def bench_pcl_parse_distance_batch() -> tuple[float, float]:
    """A/B ``_parse_distance_with_unit`` over the mixed-branch corpus."""
    from temper_placer.pcl import _parse_utils as live_parse

    fixture = _pcl_fixture_module()
    oracle = _pcl_parse_oracle_module()
    values = fixture.bench_distance_inputs()

    def _drive(fn: Callable[[Any], Any]) -> Any:
        out = []
        for v in values:
            try:
                out.append(("ok", fn(v)))
            except Exception as exc:  # noqa: BLE001 - errors are part of the API
                out.append(("err", type(exc).__name__, str(exc)))
        return out

    def run_rust() -> Any:
        return _drive(live_parse._parse_distance_with_unit)

    def run_oracle() -> Any:
        return _drive(oracle._parse_distance_with_unit)

    if run_rust() != run_oracle():
        raise AssertionError(
            "perf A/B arms disagree for pcl parse_distance_batch -- the "
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

_PARSE_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"


def bench_parse_kicad_pcb() -> tuple[float, float]:
    """A/B the Rust parse engine vs the verbatim kiutils oracle on the
    production board.

    The parse surface is I/O-shaped (file text in, model out), so this is the
    *no-regression-beyond-noise* arm of R1b -- no speedup claim is made. The
    arms' outputs are asserted equal (the pyclass __eq__ chain, identical to
    the behavioral differential's assertion) so a performance number for an
    engine that drifted from its oracle is rejected on the spot.
    """
    import temper_design_bundle_python as _tdb

    # The verbatim oracle is the same module the behavioral differential pins
    # (loaded by explicit path, like the bottleneck oracles).
    oracle_pkg = _load_module_from_path(
        "_perf_ab_parse_engine_oracle_pkg",
        REPO_ROOT / "packages/temper-placer/tests/io/_parse_engine_py_oracle/__init__.py",
    )
    _oracle_parser = oracle_pkg.kicad_parser

    content = _PARSE_BOARD.read_text(encoding="utf-8")

    def run_rust() -> Any:
        return _tdb.parse_engine.parse_kicad_pcb(content, normalize=True)

    def run_oracle() -> Any:
        return _oracle_parser.parse_kicad_pcb(_PARSE_BOARD, normalize=True)

    # Parity assertion: the pyclass/dataclass __eq__ chain cannot be used
    # directly here -- pyo3's __eq__ returns NotImplemented for foreign types
    # but the reverse dataclass comparison is not guaranteed to be consulted
    # symmetrically, so `rust == oracle` can be False for identical values.
    # repr() is exact (floats round-trip) and both arms render the same
    # dataclass-style shape, so repr equality is the bit-exact check.
    if repr(run_rust()) != repr(run_oracle()):
        raise AssertionError(
            "perf A/B arms disagree for parse-engine parse_kicad_pcb -- the "
            "behavioral A/B (test_parse_engine_rust_differential.py) should "
            "be failing too"
        )
    return _time_us(run_rust, DEFAULT_WARMUP, DEFAULT_REPEATS), _time_us(
        run_oracle, DEFAULT_WARMUP, DEFAULT_REPEATS
    )


# ---------------------------------------------------------------------------
# Wave 4 Phase 3 candidate 5: config/reference loaders (pure-delegation arms)
# ---------------------------------------------------------------------------

# The verbatim pre-migration oracles live in the differential test files
# (tests/io/_config_loader_py_oracle.py etc.); importing them here keeps the
# perf A/B measuring the same reference the behavioural A/B pins.
_LOADER_ORACLE_DIR = REPO_ROOT / "packages/temper-placer/tests/io"
_CONFIG_FIXTURE = REPO_ROOT / "packages/temper-placer/configs/temper_constraints.yaml"
_FOOTPRINT_FIXTURE = REPO_ROOT / "packages/temper-placer/configs/footprint_library.yaml"


def bench_config_loader_preprocess() -> tuple[float, float]:
    """A/B the Rust ``preprocess_config`` transform vs the verbatim oracle.

    Pure-delegation surface: both arms walk the same dict through the same
    Python class constructors (the pydantic/pyclass leaves are called back on
    both sides), so the honest claim is no-regression-beyond-noise, not a
    speedup. The parity assertion inside keeps a performance number from being
    meaningful for an implementation that no longer agrees with its oracle.
    """
    import temper_design_bundle_python as _tdb

    oracle = _load_module_from_path(
        "_perf_ab_config_loader_oracle", _LOADER_ORACLE_DIR / "_config_loader_py_oracle.py"
    )
    raw = yaml.safe_load(_CONFIG_FIXTURE.read_text(encoding="utf-8"))

    def run_rust() -> str:
        return repr(_tdb.preprocess_config(raw))

    def run_oracle() -> str:
        return repr(oracle._preprocess_config(raw))

    if run_rust() != run_oracle():
        raise AssertionError(
            "perf A/B arms disagree for config-loader preprocess -- the "
            "behavioural A/B (test_config_loader_rust_differential.py) should "
            "be failing too"
        )
    return _time_us(run_rust, DEFAULT_WARMUP, DEFAULT_REPEATS), _time_us(
        run_oracle, DEFAULT_WARMUP, DEFAULT_REPEATS
    )


def bench_footprint_library_load() -> tuple[float, float]:
    """A/B the Rust ``from_yaml_string`` vs the verbatim oracle.

    Both arms call PyYAML's ``safe_load`` back across the boundary (YAML 1.1),
    then do the downstream validation — again a pure-delegation
    no-regression-beyond-noise arm.
    """
    import temper_io_types as _io

    oracle = _load_module_from_path(
        "_perf_ab_footprint_library_oracle",
        _LOADER_ORACLE_DIR / "_footprint_library_py_oracle.py",
    )
    content = _FOOTPRINT_FIXTURE.read_text(encoding="utf-8")

    def run_rust() -> str:
        return repr(_io.FootprintLibrary.from_yaml_string(content).footprints)

    def run_oracle() -> str:
        return repr(oracle.FootprintLibrary.from_yaml_string(content).footprints)

    if run_rust() != run_oracle():
        raise AssertionError(
            "perf A/B arms disagree for footprint-library load -- the "
            "behavioural A/B (test_footprint_library_rust_differential.py) "
            "should be failing too"
        )
    return _time_us(run_rust, DEFAULT_WARMUP, DEFAULT_REPEATS), _time_us(
        run_oracle, DEFAULT_WARMUP, DEFAULT_REPEATS
    )


# ---------------------------------------------------------------------------
# Wave 4 Phase 3 candidate 1: board/netlist contract construction
# ---------------------------------------------------------------------------

# The verbatim pre-migration oracles live in the differential test files
# (tests/core/_board_py_oracle.py / _netlist_py_oracle.py); importing them
# here keeps the perf A/B measuring the same reference the behavioural A/B
# pins (same pattern as the config-loader arms above).
_CORE_ORACLE_DIR = REPO_ROOT / "packages/temper-placer/tests/core"

# Fixed synthetic fixture (plain data, built once). A Temper-shaped board
# (4 zones, 4 mounting holes, 2 ground domains) plus a 3-component /
# 4-net netlist with a multi-pin net, a self-referential net and a net that
# references an unknown component -- the same shapes the behavioural
# differentials drive. Fixed, because the A/B ratio is only comparable
# across runs if both arms see byte-identical input every time.
_CONTRACTS_ZONES = (
    ("HV_ZONE", (0, 0, 50, 80)),
    ("POWER_ZONE", (50, 0, 100, 80)),
    ("MCU_ZONE", (0, 80, 100, 130)),
    ("UI_ZONE", (0, 130, 100, 150)),
)
_CONTRACTS_HOLES = ((5, 5), (95, 5), (5, 145), (95, 145))
_CONTRACTS_GROUNDS = (
    ("PGND", (0, 0, 50, 150), (50, 75)),
    ("CGND", (50, 0, 100, 150), (50, 75)),
)


def _contracts_build_board(mod: Any) -> Any:
    """Build the representative Board (including `build_indices`) on `mod`."""
    board = mod.Board(
        width=100.0,
        height=150.0,
        origin=(0.0, 0.0),
        zones=[mod.Zone(name, bounds) for name, bounds in _CONTRACTS_ZONES],
        mounting_holes=[mod.MountingHole(pos, 3.2) for pos in _CONTRACTS_HOLES],
        ground_domains=[
            mod.GroundDomain(name, bounds, star_point=sp)
            for name, bounds, sp in _CONTRACTS_GROUNDS
        ],
    )
    board.build_indices()
    return board


def _contracts_build_netlist(mod: Any) -> Any:
    """Build the representative Netlist (including `build_indices`) on `mod`."""

    def pin(name: str, num: str) -> Any:
        return mod.Pin(name, num, (0.0, 0.0), net=None)

    r1 = mod.Component("R1", "R_0402", (1.0, 0.5), pins=[pin("1", "1"), pin("2", "2")])
    r2 = mod.Component("R2", "R_0402", (1.0, 0.5), pins=[pin("1", "1"), pin("2", "2")])
    u1 = mod.Component(
        "U1", "QFN-32", (5.0, 5.0), pins=[pin("A", "1"), pin("B", "2")], fixed=True
    )
    nets = [
        mod.Net("GND", [("R1", "1"), ("R2", "1"), ("U1", "A")]),
        mod.Net("VCC", [("R1", "2"), ("U1", "B")]),
        mod.Net("SELF", [("U1", "A"), ("U1", "B")]),
        mod.Net("DANGLING", [("NOPE", "1"), ("R2", "2")]),
    ]
    netlist = mod.Netlist(components=[r1, r2, u1], nets=nets)
    netlist.build_indices()
    return netlist


def bench_contracts_construction() -> tuple[float, float]:
    """A/B Board/Netlist construction (Rust pyclasses) vs the verbatim oracles.

    Pure-delegation surface: the pyclass constructors mirror the dataclass
    ``__init__`` field-for-field and the ``build_indices`` rebuild is
    identical, so this is the *no-regression-beyond-noise* arm of R1b -- no
    speedup claim is made. The parity assertion builds both arms from the
    same argument tuples and compares the full reprs (the same bit-exact
    check the behavioural differentials pin), so a performance number for an
    implementation that drifted from its oracle is rejected on the spot.
    """
    import temper_design_bundle_python as _tdb

    board_oracle = _load_module_from_path(
        "_perf_ab_board_oracle", _CORE_ORACLE_DIR / "_board_py_oracle.py"
    )
    netlist_oracle = _load_module_from_path(
        "_perf_ab_netlist_oracle", _CORE_ORACLE_DIR / "_netlist_py_oracle.py"
    )
    rs_board = _tdb.board_contracts
    rs_netlist = _tdb.netlist_contracts

    def run_rust() -> str:
        return repr(
            (
                _contracts_build_board(rs_board),
                _contracts_build_netlist(rs_netlist),
            )
        )

    def run_oracle() -> str:
        return repr(
            (
                _contracts_build_board(board_oracle),
                _contracts_build_netlist(netlist_oracle),
            )
        )

    if run_rust() != run_oracle():
        raise AssertionError(
            "perf A/B arms disagree for board/netlist contracts_construction -- "
            "the behavioural A/B (test_board_rust_differential.py / "
            "test_netlist_rust_differential.py) should be failing too"
        )
    return _time_us(run_rust, DEFAULT_WARMUP, DEFAULT_REPEATS), _time_us(
        run_oracle, DEFAULT_WARMUP, DEFAULT_REPEATS
    )


# ---------------------------------------------------------------------------
# Wave 4 Phase B: router_v6/net_ordering -> temper-rust-router
# ---------------------------------------------------------------------------
# Fixtures come from the differential's OWN corpus module -- the `BENCH_*`
# lists, which are *subsets* of the lists the differential compares row by
# row, and `test_bench_corpus_is_covered_by_differential` asserts the
# containment.  That is the structural answer to PR #714, which passed its
# differential at 100 iterations and then failed CI on a benchmark that ran
# 120: here the benchmark cannot reach a parameter the differential has not
# already compared, because it draws from the same rows.


def _net_ordering_corpus() -> ModuleType:
    return _load_module_from_path(
        "_perf_ab_net_ordering_cases",
        REPO_ROOT / "packages/temper-placer/tests/router_v6/_net_ordering_cases.py",
    )


def _net_ordering_oracle() -> ModuleType:
    return _load_module_from_path(
        "_perf_ab_net_ordering_oracle",
        REPO_ROOT / "packages/temper-placer/tests/router_v6/_net_ordering_py_oracle.py",
    )


def bench_net_ordering_order_nets() -> tuple[float, float]:
    """A/B ``order_nets`` (Rust) vs the verbatim oracle."""
    import temper_rust_router as rust

    sys.path.insert(0, str(REPO_ROOT / "packages/temper-placer"))
    from tests.router_v6._net_ordering_builders import build_loops, build_order_netlist

    cases = _net_ordering_corpus()
    oracle = _net_ordering_oracle()
    rows = cases.BENCH_ORDER_DESIGNS

    def run_rust() -> Any:
        return [rust.order_nets_py(c, n, ls, cfg) for _l, c, n, ls, cfg in rows]

    def run_oracle() -> Any:
        return [
            oracle.order_nets(build_order_netlist(c, n), build_loops(ls), cfg)
            for _l, c, n, ls, cfg in rows
        ]

    if run_rust() != run_oracle():
        raise AssertionError(
            "perf A/B arms disagree for net_ordering order_nets -- the "
            "behavioral A/B (test_net_ordering_rust_differential.py) should "
            "be failing too"
        )
    return _time_us(run_rust, DEFAULT_WARMUP, DEFAULT_REPEATS), _time_us(
        run_oracle, DEFAULT_WARMUP, DEFAULT_REPEATS
    )


def bench_net_ordering_hpwl() -> tuple[float, float]:
    """A/B ``compute_hpwl``/``compute_bbox_area`` (Rust) vs the oracle."""
    import temper_rust_router as rust

    sys.path.insert(0, str(REPO_ROOT / "packages/temper-placer"))
    from tests.router_v6._net_ordering_builders import build_netlist

    cases = _net_ordering_corpus()
    oracle = _net_ordering_oracle()
    rows = cases.BENCH_HPWL_DESIGNS

    def run_rust() -> Any:
        return [
            (rust.net_compute_hpwl_py(net, comps), rust.net_compute_bbox_area_py(net, comps))
            for _l, comps, net in rows
        ]

    def run_oracle() -> Any:
        out = []
        for _l, comps, net in rows:
            netlist = build_netlist(comps)
            out.append(
                (oracle.compute_hpwl(net, netlist), oracle.compute_bbox_area(net, netlist))
            )
        return out

    if run_rust() != run_oracle():
        raise AssertionError(
            "perf A/B arms disagree for net_ordering hpwl/area -- the "
            "behavioral A/B should be failing too"
        )
    return _time_us(run_rust, DEFAULT_WARMUP, DEFAULT_REPEATS), _time_us(
        run_oracle, DEFAULT_WARMUP, DEFAULT_REPEATS
    )



# ---------------------------------------------------------------------------
# Wave 4: router_v6 DRC constraint geometry
# (router_v6/constraints_geometry.py -> temper-geometry)
# ---------------------------------------------------------------------------
# The oracle is the same verbatim pre-migration copy the differential pins,
# and the INPUT CORPUS is the same module the differential iterates
# (`tests/router_v6/_constraints_geometry_cases.py`).  Sharing the corpus is
# structural, not stylistic: PR #714 passed its differential at iterations
# [0, 1, 2, 8, 17, 100] and then failed CI on a benchmark that ran 120.
# `test_benchmark_corpus_is_covered_by_differential` asserts the containment
# from the test side as well, so neither half can drift.


def _drc_geometry_modules() -> tuple[ModuleType, ModuleType]:
    """(verbatim oracle, shared input corpus)."""
    tests_dir = REPO_ROOT / "packages" / "temper-placer" / "tests" / "router_v6"
    oracle = _load_module_from_path(
        "_perf_ab_drc_geometry_oracle", tests_dir / "_constraints_geometry_py_oracle.py"
    )
    cases = _load_module_from_path(
        "_perf_ab_drc_geometry_cases", tests_dir / "_constraints_geometry_cases.py"
    )
    return oracle, cases


def _drc_geometry_ab(build_arms: Callable[[Any, Any, Any], tuple[Callable[[], Any], Callable[[], Any]]], label: str):
    """Shared scaffolding: build both arms, assert parity, then time both.

    Parity is asserted by `float.hex()` over the whole result list -- the
    same no-tolerance rule the behavioral gate uses.  A perf number for an
    implementation that disagrees with its oracle is meaningless.
    """
    from temper_placer.router_v6 import constraints_geometry as shim

    oracle, cases = _drc_geometry_modules()
    run_rust, run_oracle = build_arms(shim, oracle, cases)

    got, want = run_rust(), run_oracle()
    if [repr(v) for v in got] != [repr(v) for v in want]:
        raise AssertionError(f"perf A/B arms disagree for {label}")
    return _time_us(run_rust, DEFAULT_WARMUP, DEFAULT_REPEATS), _time_us(
        run_oracle, DEFAULT_WARMUP, DEFAULT_REPEATS
    )


def _hexes(values: list[float]) -> list[str]:
    return [v.hex() if isinstance(v, float) else repr(v) for v in values]


def bench_drc_geometry_point_segment() -> tuple[float, float]:
    """A/B point_to_segment_distance over the shared differential corpus."""

    def build(shim, oracle, cases):
        corpus = cases.BENCH_POINT_SEGMENTS

        def arm(m):
            def run():
                out = []
                for px, py, x1, y1, x2, y2 in corpus:
                    out.append(
                        m.point_to_segment_distance(
                            m.Point(px, py), m.LineSegment(m.Point(x1, y1), m.Point(x2, y2))
                        )
                    )
                return _hexes(out)

            return run

        return arm(shim), arm(oracle)

    return _drc_geometry_ab(build, "drc-geometry-point-segment")


def bench_drc_geometry_segment_segment() -> tuple[float, float]:
    """A/B segment_to_segment_distance (the composite: 1 intersect test +
    4 point-to-segment calls) over the shared corpus."""

    def build(shim, oracle, cases):
        corpus = cases.BENCH_SEGMENT_PAIRS

        def arm(m):
            def run():
                out = []
                for c in corpus:
                    a = m.LineSegment(m.Point(c[0], c[1]), m.Point(c[2], c[3]))
                    b = m.LineSegment(m.Point(c[4], c[5]), m.Point(c[6], c[7]))
                    out.append(m.segment_to_segment_distance(a, b))
                return _hexes(out)

            return run

        return arm(shim), arm(oracle)

    return _drc_geometry_ab(build, "drc-geometry-segment-segment")


def bench_drc_geometry_point_rect() -> tuple[float, float]:
    """A/B point_to_rotated_rect_distance over the shared corpus."""

    def build(shim, oracle, cases):
        # `rotation` is finite in every BENCH_POINT_RECTS row; infinite
        # rotations raise (error parity is a behavioral gate, not a perf one).
        corpus = [c for c in cases.BENCH_POINT_RECTS if all(v == v for v in c)]

        def arm(m):
            def run():
                out = []
                for px, py, cx, cy, w, h, rot in corpus:
                    out.append(
                        m.point_to_rotated_rect_distance(
                            m.Point(px, py), m.RotatedRect(m.Point(cx, cy), (w, h), rot)
                        )
                    )
                return _hexes(out)

            return run

        return arm(shim), arm(oracle)

    return _drc_geometry_ab(build, "drc-geometry-point-rect")


def bench_drc_geometry_segment_rect() -> tuple[float, float]:
    """A/B segment_to_rotated_rect_distance -- the deepest composite in the
    module (2 point-to-rect calls, 4 corners, then up to 4 segment-to-segment
    distances, each itself 5 calls)."""

    def build(shim, oracle, cases):
        corpus = [c for c in cases.BENCH_SEGMENT_RECTS if all(v == v for v in c)]

        def arm(m):
            def run():
                out = []
                for sx, sy, ex, ey, cx, cy, w, h, rot in corpus:
                    out.append(
                        m.segment_to_rotated_rect_distance(
                            m.LineSegment(m.Point(sx, sy), m.Point(ex, ey)),
                            m.RotatedRect(m.Point(cx, cy), (w, h), rot),
                        )
                    )
                return _hexes(out)

            return run

        return arm(shim), arm(oracle)

    return _drc_geometry_ab(build, "drc-geometry-segment-rect")


_BENCHMARKS: dict[tuple[str, str], Callable[[], tuple[float, float] | None]] = {
    ("bottleneck-geometry", "cell_capacity_batch"): bench_bottleneck_cell_capacity,
    # NOTE (net-ordering): these two entries have NO row yet in
    # power_pcb_dataset/metrics/perf_ab_baseline.jsonl, so the perf gate fails
    # closed until one is captured.  It is deliberately NOT captured locally:
    # this module's own header measured a consistent -11% darwin/linux
    # platform bias, and a darwin-captured baseline would make the gate miss
    # every regression between +20% and +35% while reporting a spurious
    # "IMPROVED" on clean PRs.  Capture via .github/workflows/pr-perf-check.yml
    # in capture mode before this PR merges.
    ("net-ordering", "order_nets"): bench_net_ordering_order_nets,
    ("net-ordering", "compute_hpwl"): bench_net_ordering_hpwl,
    ("bottleneck-geometry", "hard_blocked_batch"): bench_bottleneck_hard_blocked,
    ("topological", "constraint_propagation"): bench_topological_propagation,
    ("topological", "force_refinement"): bench_topological_force_refinement,
    ("drc-inflate", "drc_proxy_score"): bench_drc_proxy_score,
    ("drc-inflate", "smooth_relu_array"): bench_smooth_relu_array,
    ("dsn-exporter", "export_pcb"): bench_dsn_export_pcb,
    ("loaders", "loaders"): bench_loaders,
    # Wave 4 Phase 2. NOTE: these two keys have no row in
    # power_pcb_dataset/metrics/perf_ab_baseline.jsonl yet, so they fail the
    # gate closed until a baseline is captured ON CI (linux/x86_64) via
    # .github/workflows/pr-perf-check.yml and appended in a reviewed PR. That
    # is deliberate and is this file's own documented procedure: a
    # darwin-captured row carries the measured ~-11% platform bias, which
    # would make the gate miss every regression between +20% and +35%.
    ("pcl-tag-dispatch", "tag_resolve_sweep"): bench_pcl_tag_resolve_sweep,
    ("pcl-parse-utils", "parse_distance_batch"): bench_pcl_parse_distance_batch,
    ("physics-heat_removal", "build_h_field"): bench_physics_heat_removal,
    ("physics-copper_coverage", "copper_masks"): bench_physics_copper_masks,
    ("physics-tj_cross_check", "device_cross_check"): bench_physics_device_check,
    ("config-loader", "preprocess_config"): bench_config_loader_preprocess,
    ("footprint-library", "from_yaml_string"): bench_footprint_library_load,
    ("parse-engine", "parse_kicad_pcb"): bench_parse_kicad_pcb,
    ("board-netlist", "contracts_construction"): bench_contracts_construction,
    ("drc-geometry", "point_segment"): bench_drc_geometry_point_segment,
    ("drc-geometry", "segment_segment"): bench_drc_geometry_segment_segment,
    ("drc-geometry", "point_rect"): bench_drc_geometry_point_rect,
    ("drc-geometry", "segment_rect"): bench_drc_geometry_segment_rect,
}


def run_benchmarks(commit: str = "") -> list[dict[str, Any]]:
    """Run every registered A/B and return PipelineMetricsRecord-shaped dicts.

    A bench may return None to signal "registered but not runnable on this
    tree" (the deterministic-hubs arm before its kernels land): it is
    skipped with a stderr note rather than emitting a fabricated record --
    a dormant arm must not crash the other benchmarks or invent a ratio.
    """
    records: list[dict[str, Any]] = []
    for (module, stage), fn in sorted(_BENCHMARKS.items()):
        result = fn()
        if result is None:
            print(
                f"{module}/{stage}: skipped -- benchmark surface not present "
                "on this tree",
                file=sys.stderr,
            )
            continue
        rust_us, oracle_us = result
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
