"""Differential tests: Rust resource-bound kernels vs the pure-Python
reference (``temper_placer/router_v6/resource_bound.py``, the bin-packing
resource-exhaustion theorem).

The pre-migration implementations are pinned VERBATIM in
``_resource_bound_py_oracle.py`` (exactly the six functions the Rust
kernel implements — NOT ``_net_bboxes_from_pcb``, which stays Python).
Any change to ``packages/temper-drc-rs/src/resource_bound.rs`` or the
Python delegation shim that disagrees with the oracle fails here.

The wiring tests (``test_*_delegates_to_rust``) monkeypatch the Rust
kernel to raise and call the shipped module function, so red here means
"not yet wired to Rust", not "numerically wrong" — the house pattern for
this migration wave.
"""

from __future__ import annotations

import random

import numpy as np
import pytest

import tests.router_v6._resource_bound_py_oracle as _oracle
from temper_placer.router_v6 import resource_bound as _rb
from temper_placer.router_v6.occupancy_grid import OccupancyGrid

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_grid(
    width_cells: int = 40,
    height_cells: int = 40,
    cell_size: float = 0.1,
    origin: tuple[float, float] = (0.0, 0.0),
    blocked_ratio: float = 0.0,
    seed: int = 42,
) -> OccupancyGrid:
    rng = np.random.RandomState(seed)
    grid = np.zeros((height_cells, width_cells), dtype=np.int8)
    if blocked_ratio > 0:
        n_block = int(width_cells * height_cells * blocked_ratio)
        placed = 0
        while placed < n_block:
            x = rng.randint(0, width_cells)
            y = rng.randint(0, height_cells)
            if grid[y, x] == 0:
                grid[y, x] = 1
                placed += 1
    return OccupancyGrid(
        layer_name="F.Cu",
        grid=grid,
        origin=origin,
        cell_size=cell_size,
        width_cells=width_cells,
        height_cells=height_cells,
    )


def _random_bboxes(rng: random.Random, n: int, span: float = 40.0) -> dict[str, tuple[float, float, float, float]]:
    bboxes: dict[str, tuple[float, float, float, float]] = {}
    for i in range(n):
        x1 = rng.uniform(0.0, span)
        y1 = rng.uniform(0.0, span)
        x2 = x1 + rng.uniform(0.1, span * 0.3)
        y2 = y1 + rng.uniform(0.1, span * 0.3)
        bboxes[f"N{i}"] = (x1, y1, x2, y2)
    return bboxes


def _boom(*_a, **_kw):
    raise RuntimeError("MUTANT: kernel not wired")


# ---------------------------------------------------------------------------
# Wiring: shipped module must delegate to temper_drc_rs, not a stale copy.
# ---------------------------------------------------------------------------


def test_compute_conflict_clusters_delegates_to_rust(monkeypatch):
    monkeypatch.setattr(_rb._drc, "resource_bound_compute_conflict_clusters", _boom)
    with pytest.raises(RuntimeError, match="MUTANT"):
        _rb._compute_conflict_clusters({"A": (0.0, 0.0, 1.0, 1.0), "B": (0.5, 0.5, 1.5, 1.5)})


def test_cluster_union_bbox_delegates_to_rust(monkeypatch):
    monkeypatch.setattr(_rb._drc, "resource_bound_cluster_union_bbox", _boom)
    with pytest.raises(RuntimeError, match="MUTANT"):
        _rb._cluster_union_bbox(["A"], {"A": (0.0, 0.0, 1.0, 1.0)})


def test_capacity_in_bbox_delegates_to_rust(monkeypatch):
    monkeypatch.setattr(_rb._drc, "resource_bound_capacity_in_bbox", _boom)
    grid = _make_grid()
    with pytest.raises(RuntimeError, match="MUTANT"):
        _rb._capacity_in_bbox(grid, (0.0, 0.0, 1.0, 1.0))


def test_compute_fill_factor_delegates_to_rust(monkeypatch):
    monkeypatch.setattr(_rb._drc, "resource_bound_compute_fill_factor", _boom)
    with pytest.raises(RuntimeError, match="MUTANT"):
        _rb._compute_fill_factor(0.2, {"A": 10.0})


def test_max_routable_nets_delegates_to_rust(monkeypatch):
    monkeypatch.setattr(_rb._drc, "resource_bound_max_routable_nets", _boom)
    grid = _make_grid()
    with pytest.raises(RuntimeError, match="MUTANT"):
        _rb.max_routable_nets(grid, {"A": (0.0, 0.0, 1.0, 1.0)}, 0.2)


def test_demand_budget_summary_delegates_to_rust(monkeypatch):
    monkeypatch.setattr(_rb._drc, "resource_bound_demand_budget_summary", _boom)
    grid = _make_grid()
    with pytest.raises(RuntimeError, match="MUTANT"):
        _rb.demand_budget_summary(grid, {"A": (0.0, 0.0, 1.0, 1.0)}, 0.2)


# ---------------------------------------------------------------------------
# _compute_conflict_clusters
# ---------------------------------------------------------------------------


def _cluster_sets(clusters):
    return {frozenset(c) for c in clusters}


def test_conflict_clusters_matches_oracle_membership_randomized():
    rng = random.Random(2026)
    for trial in range(200):
        n = rng.randint(0, 15)
        bboxes = _random_bboxes(rng, n)
        oracle_clusters = _oracle._compute_conflict_clusters(bboxes)
        rust_clusters = _rb._compute_conflict_clusters(bboxes)
        assert len(oracle_clusters) == len(rust_clusters), f"trial {trial}"
        assert _cluster_sets(oracle_clusters) == _cluster_sets(rust_clusters), f"trial {trial}"


def test_conflict_clusters_outer_order_matches_input_order():
    """Outer cluster order follows dict insertion order in BOTH oracle and
    kernel (not hash order) -- pin that the Rust kernel preserves it."""
    bboxes = {
        "Z": (0.0, 0.0, 5.0, 5.0),
        "A": (100.0, 100.0, 105.0, 105.0),
        "M": (200.0, 200.0, 205.0, 205.0),
    }
    oracle_clusters = _oracle._compute_conflict_clusters(bboxes)
    rust_clusters = _rb._compute_conflict_clusters(bboxes)
    # Each net is isolated (no overlap) -> one singleton cluster per net,
    # in insertion order Z, A, M.
    assert [c[0] for c in oracle_clusters] == ["Z", "A", "M"]
    assert [c[0] for c in rust_clusters] == ["Z", "A", "M"]


def test_conflict_clusters_empty_and_single():
    assert _rb._compute_conflict_clusters({}) == _oracle._compute_conflict_clusters({}) == []
    single = {"A": (0.0, 0.0, 1.0, 1.0)}
    assert _rb._compute_conflict_clusters(single) == _oracle._compute_conflict_clusters(single) == [["A"]]


def test_conflict_clusters_overlap_ratio_exactly_at_threshold_is_not_a_conflict():
    """Boundary: overlap/min_area == overlap_threshold EXACTLY (both are the
    same IEEE-754 double, 1.0/10.0 == 0.1) must NOT count as a conflict --
    the oracle's comparison is strict `>`, not `>=`. A `>=` mutant merges
    these two nets into one cluster; the correct kernel keeps them
    separate. Random floats essentially never land exactly on the
    threshold, so this exact-equality case needs its own fixture."""
    bboxes = {
        "A": (0.0, 0.0, 10.0, 1.0),
        "B": (0.0, 0.0, 1.0, 10.0),
    }
    # Sanity: the fixture actually hits the exact double-precision boundary.
    ox = min(10.0, 1.0) - max(0.0, 0.0)
    oy = min(1.0, 10.0) - max(0.0, 0.0)
    overlap = ox * oy
    min_area = min(10.0 * 1.0, 1.0 * 10.0)
    assert overlap / min_area == 0.1

    oracle_clusters = _oracle._compute_conflict_clusters(bboxes)
    rust_clusters = _rb._compute_conflict_clusters(bboxes)
    assert len(oracle_clusters) == 2, "oracle: exact-threshold overlap must NOT conflict"
    assert _cluster_sets(oracle_clusters) == _cluster_sets(rust_clusters) == {frozenset(["A"]), frozenset(["B"])}


def test_conflict_clusters_deterministic_across_repeated_calls():
    """The Rust kernel sorts explicitly -- repeated calls on the same
    input must return the identical structure (not just membership),
    unlike the PYTHONHASHSEED-dependent oracle."""
    bboxes = _random_bboxes(random.Random(7), 12)
    first = _rb._compute_conflict_clusters(bboxes)
    for _ in range(5):
        assert _rb._compute_conflict_clusters(bboxes) == first


# ---------------------------------------------------------------------------
# _cluster_union_bbox
# ---------------------------------------------------------------------------


def test_cluster_union_bbox_matches_oracle_randomized():
    rng = random.Random(99)
    for _ in range(200):
        n = rng.randint(1, 10)
        bboxes = _random_bboxes(rng, n)
        cluster = list(bboxes.keys())
        rng.shuffle(cluster)
        exp = _oracle._cluster_union_bbox(cluster, bboxes)
        got = _rb._cluster_union_bbox(cluster, bboxes)
        assert got == exp


def test_cluster_union_bbox_empty():
    assert _rb._cluster_union_bbox([], {}) == _oracle._cluster_union_bbox([], {}) == (0.0, 0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# _capacity_in_bbox
# ---------------------------------------------------------------------------


def test_capacity_in_bbox_matches_oracle_randomized():
    rng = random.Random(123)
    for trial in range(100):
        width = rng.randint(5, 60)
        height = rng.randint(5, 60)
        cell_size = rng.uniform(0.05, 1.0)
        grid = _make_grid(width, height, cell_size, blocked_ratio=rng.uniform(0.0, 0.5), seed=trial)
        bw = width * cell_size
        bh = height * cell_size
        x1 = rng.uniform(-bw * 0.2, bw)
        y1 = rng.uniform(-bh * 0.2, bh)
        x2 = x1 + rng.uniform(0.0, bw * 0.5)
        y2 = y1 + rng.uniform(0.0, bh * 0.5)
        exp = _oracle._capacity_in_bbox(grid, (x1, y1, x2, y2))
        got = _rb._capacity_in_bbox(grid, (x1, y1, x2, y2))
        assert got == exp, f"trial {trial}: {(x1, y1, x2, y2)}"


def test_capacity_in_bbox_all_free():
    grid = _make_grid(50, 50, 1.0)
    exp = _oracle._capacity_in_bbox(grid, (0.0, 0.0, 10.0, 10.0))
    got = _rb._capacity_in_bbox(grid, (0.0, 0.0, 10.0, 10.0))
    assert got == exp
    assert 100 <= got <= 130


def test_capacity_in_bbox_out_of_bounds():
    grid = _make_grid(10, 10, 1.0)
    exp = _oracle._capacity_in_bbox(grid, (100.0, 100.0, 200.0, 200.0))
    got = _rb._capacity_in_bbox(grid, (100.0, 100.0, 200.0, 200.0))
    assert got == exp
    assert got <= 1.0


def test_capacity_in_bbox_zero_size_grid():
    """width_cells == 0 exercises the oracle's `width_cells - 1 == -1`
    clamp path (the redundant post-swap guard's actual trigger)."""
    grid = OccupancyGrid(
        layer_name="F.Cu",
        grid=np.zeros((0, 0), dtype=np.int8),
        origin=(0.0, 0.0),
        cell_size=1.0,
        width_cells=0,
        height_cells=0,
    )
    exp = _oracle._capacity_in_bbox(grid, (0.0, 0.0, 10.0, 10.0))
    got = _rb._capacity_in_bbox(grid, (0.0, 0.0, 10.0, 10.0))
    assert got == exp == 0.0


# ---------------------------------------------------------------------------
# _compute_fill_factor (np.sqrt scalar + np.clip NaN-propagation hazard)
# ---------------------------------------------------------------------------


def test_compute_fill_factor_matches_oracle_randomized():
    rng = random.Random(321)
    for _ in range(300):
        trace_width = rng.uniform(0.0, 2.0)
        n = rng.randint(1, 10)
        areas = {f"N{i}": rng.uniform(0.001, 5000.0) for i in range(n)}
        exp = _oracle._compute_fill_factor(trace_width, areas)
        got = _rb._compute_fill_factor(trace_width, areas)
        assert got.hex() == exp.hex()


def test_compute_fill_factor_empty():
    assert _rb._compute_fill_factor(0.2, {}) == _oracle._compute_fill_factor(0.2, {}) == 0.5


def test_compute_fill_factor_clip_bounds():
    areas = {"A": 1.0}
    # Tiny trace_width -> clamps to 0.01 lower bound.
    got_lo = _rb._compute_fill_factor(1e-6, areas)
    exp_lo = _oracle._compute_fill_factor(1e-6, areas)
    assert got_lo == exp_lo == 0.01
    # Huge trace_width -> clamps to 1.0 upper bound.
    got_hi = _rb._compute_fill_factor(1e6, areas)
    exp_hi = _oracle._compute_fill_factor(1e6, areas)
    assert got_hi == exp_hi == 1.0


def test_compute_fill_factor_nan_trace_width_propagates_like_numpy_clip():
    """Measured (numpy 2.4.6): np.clip(x, lo, hi) is NaN-propagating
    (np.minimum(hi, np.maximum(x, lo))), a THIRD distinct behavior from
    CPython's builtin min/max (keeps first NaN) and f64::max/min (discards
    NaN). A trace_width of NaN must propagate to a NaN fill_factor, not a
    silently clamped 0.01/1.0."""
    areas = {"A": 1.0}
    exp = _oracle._compute_fill_factor(float("nan"), areas)
    got = _rb._compute_fill_factor(float("nan"), areas)
    assert exp != exp  # oracle is NaN
    assert got != got  # kernel matches: also NaN


# ---------------------------------------------------------------------------
# max_routable_nets / demand_budget_summary — full pipeline
# ---------------------------------------------------------------------------


def test_max_routable_nets_matches_oracle_randomized():
    rng = random.Random(555)
    for trial in range(100):
        width = rng.randint(10, 60)
        height = rng.randint(10, 60)
        cell_size = rng.uniform(0.05, 0.5)
        grid = _make_grid(width, height, cell_size, blocked_ratio=rng.uniform(0.0, 0.3), seed=trial)
        n = rng.randint(0, 20)
        bboxes = _random_bboxes(rng, n, span=width * cell_size)
        trace_width = rng.uniform(0.05, 0.5)
        exp = _oracle.max_routable_nets(grid, bboxes, trace_width)
        got = _rb.max_routable_nets(grid, bboxes, trace_width)
        assert got == exp, f"trial {trial}"


def test_max_routable_nets_explicit_fill_factor_matches_oracle():
    rng = random.Random(777)
    for _ in range(50):
        grid = _make_grid(30, 30, 1.0)
        bboxes = _random_bboxes(rng, rng.randint(1, 10), span=30.0)
        ff = rng.uniform(0.01, 1.0)
        exp = _oracle.max_routable_nets(grid, bboxes, 0.2, fill_factor=ff)
        got = _rb.max_routable_nets(grid, bboxes, 0.2, fill_factor=ff)
        assert got == exp


def test_max_routable_nets_empty():
    grid = _make_grid()
    assert _rb.max_routable_nets(grid, {}, 0.2) == _oracle.max_routable_nets(grid, {}, 0.2) == 0


def test_demand_budget_summary_matches_oracle_randomized():
    rng = random.Random(888)
    for trial in range(100):
        width = rng.randint(10, 60)
        height = rng.randint(10, 60)
        cell_size = rng.uniform(0.05, 0.5)
        grid = _make_grid(width, height, cell_size, blocked_ratio=rng.uniform(0.0, 0.3), seed=trial)
        n = rng.randint(0, 20)
        bboxes = _random_bboxes(rng, n, span=width * cell_size)
        trace_width = rng.uniform(0.05, 0.5)
        exp = _oracle.demand_budget_summary(grid, bboxes, trace_width)
        got = _rb.demand_budget_summary(grid, bboxes, trace_width)
        assert got.keys() == exp.keys(), f"trial {trial}"
        assert got["max_routable"] == exp["max_routable"], f"trial {trial}"
        assert got["total_nets"] == exp["total_nets"], f"trial {trial}"
        assert got["cluster_count"] == exp["cluster_count"], f"trial {trial}"
        assert got["fill_factor"] == exp["fill_factor"], f"trial {trial}"
        assert got["total_capacity_mm2"] == exp["total_capacity_mm2"], f"trial {trial}"
        assert got["total_demand_mm2"] == exp["total_demand_mm2"], f"trial {trial}"
        assert got["utilization"] == exp["utilization"], f"trial {trial}"


def test_demand_budget_summary_empty():
    grid = _make_grid()
    exp = _oracle.demand_budget_summary(grid, {}, 0.2)
    got = _rb.demand_budget_summary(grid, {}, 0.2)
    assert got == exp


def test_demand_budget_summary_empty_with_explicit_fill_factor():
    """The empty-net_bboxes branch passes ``fill_factor`` through literally
    (not via ``_compute_fill_factor``) -- pin that the kernel's empty path
    does the same, not silently substituting 0.5."""
    grid = _make_grid()
    exp = _oracle.demand_budget_summary(grid, {}, 0.2, fill_factor=0.77)
    got = _rb.demand_budget_summary(grid, {}, 0.2, fill_factor=0.77)
    assert got == exp
    assert got["fill_factor"] == 0.77
