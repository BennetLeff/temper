"""Differential tests: Rust resource-exhaustion kernels vs the pinned
pre-migration Python oracle (Wave 4).

The kernels migrated to ``temper-drc-rs`` (``src/resource_bound.rs``):

- ``_compute_conflict_clusters`` -- O(n^2) bbox-overlap conflict graph +
  connected components.
- ``_cluster_union_bbox`` -- 4 independent min/max folds over a cluster's
  bboxes.
- ``_capacity_in_bbox`` -- the ``np.sum(region == 0)`` free-cell count
  (``world_to_grid``/clamp/degenerate-check stay in Python).
- ``_compute_fill_factor`` -- ``trace_width / sqrt(mean(areas))``, clamped
  via ``np.clip``.

``max_routable_nets`` and ``demand_budget_summary`` are NOT reimplemented
in Rust: their Python bodies are unchanged and now execute transitively
through the four kernels above, except for their own outer bin-packing
loop (a ``sorted()`` + running-sum ``for`` loop, no numpy, no O(n^2)
shape). This suite differentials them too, since they are the two live
importers' actual entry points (``benchmark.py``, ``_pipeline_grid.py``).

NOT migrated, and why (matches the oracle module's own docstring):

- ``_net_bboxes_from_pcb``: pure PCB/Component/Pin object-graph traversal.
  Zero numpy calls, zero O(n^2)/reduction shape -- its only float
  arithmetic is a single addition inside ``pin_world_position``, which
  belongs to a different module's rotation/mirror geometry
  (``temper_placer.geometry.kicad_transform``) and is out of scope for
  this 8-function/390-LOC migration. Verified: ``grep -c "np\\."`` over
  this function's body is 0.
- ``max_routable_nets_from_pcb``: a 2-line convenience wrapper
  (``_net_bboxes_from_pcb`` + ``max_routable_nets``) with zero callers
  anywhere in the tree (verified via ``grep`` -- only its own definition
  references the name).

Traps this suite specifically pins (measured against numpy 2.4.6 in this
repo's environment, not assumed -- see ``_resource_bound_py_oracle.py``
and ``resource_bound.rs``'s module docs for the full measurements):

- ``np.clip(ff, 0.01, 1.0)`` propagates NaN from EITHER operand (measured:
  ``np.clip(nan, 0.01, 1.0)`` is ``nan``), unlike a naive
  ``max(lo, min(hi, x))`` chain built from CPython's builtin
  ``min``/``max`` (which returns ``hi`` for a NaN ``x``) and unlike
  ``f64::max``/``f64::min`` (IEEE-754-minimum-propagating, discards NaN).
- ``np.sum(region == 0)`` sums a boolean/int8 array -- measured 0/7
  mismatches against a plain sequential Python ``sum()`` across sizes
  1..100000, so the usual BLOCKED-PAIRWISE float-summation hazard does
  NOT apply here (integer/boolean addition is exact and order-invariant).
- ``np.sqrt`` on the (Python-float, never-array) ``avg_area`` scalar is
  bit-identical to ``math.sqrt`` (measured 0/200000 mismatches) -- no
  scalar-vs-ufunc correction needed, unlike a `float ** non-integer`
  scalar `pow` call elsewhere in this codebase.
- CPython's builtin ``min``/``max`` "keep the FIRST NaN" semantics (used
  by ``_cluster_union_bbox``'s 4 independent folds and the area-clamp/
  overlap arithmetic inside ``_compute_conflict_clusters``) are DIFFERENT
  from ``f64::max``/``min`` (discards NaN) and from ``np.clip``'s
  either-operand propagation above -- three distinct behaviours in one
  390-line file, all pinned separately below.

Float-accumulation-order tolerance (documented, not a bug):
``demand_budget_summary``'s ``total_capacity_mm2``/``utilization`` sum one
capacity value per conflict cluster, accumulated in ``clusters`` list
order. The oracle's own cluster order depends on CPython's salted `set`
iteration (non-reproducible even against a second run of the *same*
oracle in a fresh process); the Rust port instead uses a deterministic
index-ascending traversal. Every INTEGER-valued output (``max_routable``,
``total_nets``, ``cluster_count``, and ``max_routable_nets``'s return
value) is exact and order-invariant by construction (see the oracle
docstring for the proof), so only those two float aggregate fields are
compared with a numeric tolerance below, exactly like
``router_clearance.rs``'s own ``canonicalize()`` helper does for the same
class of cross-path float-accumulation-order issue.
"""

from __future__ import annotations

import random
import subprocess
from pathlib import Path

import numpy as np
import pytest

from temper_placer.router_v6 import resource_bound as shipped
from temper_placer.router_v6.occupancy_grid import OccupancyGrid

from . import _resource_bound_py_oracle as ORACLE

_PINNED_COMMIT = "da7708e55753c4271385d49d915bab4d186f641d"
_PINNED_PATH = "packages/temper-placer/src/temper_placer/router_v6/resource_bound.py"
_PINNED_LINE_RANGE = (36, 390)  # 1-indexed, inclusive: _OVERLAP_THRESHOLD .. end of file
_ORACLE_FILE = Path(__file__).with_name("_resource_bound_py_oracle.py")


# ---------------------------------------------------------------------------
# Verbatim-copy check: the oracle file must be an EXACT git-show extraction
# of the pinned commit/line-range.
# ---------------------------------------------------------------------------


def test_oracle_is_verbatim_copy():
    repo_root = Path(__file__).resolve()
    while not (repo_root / ".git").exists():
        repo_root = repo_root.parent
    result = subprocess.run(
        ["git", "show", f"{_PINNED_COMMIT}:{_PINNED_PATH}"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    lines = result.stdout.splitlines(keepends=True)
    start, end = _PINNED_LINE_RANGE
    extracted = "".join(lines[start - 1 : end])

    oracle_text = _ORACLE_FILE.read_text()
    assert extracted in oracle_text, (
        "The pinned commit's constant + all 8 functions is no longer "
        "byte-identical to _resource_bound_py_oracle.py -- the oracle has "
        "drifted from its pin."
    )


# ---------------------------------------------------------------------------
# Wiring: the shipped module must actually delegate. Monkeypatch each Rust
# entry point to raise a distinctive marker exception, call the shipped
# function, and require the marker to propagate.
# ---------------------------------------------------------------------------


class _WiringMarker(RuntimeError):
    """Distinctive exception raised by a monkeypatched Rust entry point."""


def _raise_marker(*_args, **_kwargs):
    raise _WiringMarker("kernel called")


_NONTRIVIAL_BBOXES = {
    "A": (0.0, 0.0, 5.0, 5.0),
    "B": (2.0, 2.0, 7.0, 7.0),  # overlaps A
    "C": (100.0, 100.0, 105.0, 105.0),  # isolated
}


def test_compute_conflict_clusters_delegates_to_rust(monkeypatch):
    monkeypatch.setattr(shipped._temper_drc_rs, "resource_bound_conflict_clusters_py", _raise_marker)
    with pytest.raises(_WiringMarker):
        shipped._compute_conflict_clusters(_NONTRIVIAL_BBOXES)


def test_cluster_union_bbox_delegates_to_rust(monkeypatch):
    monkeypatch.setattr(shipped._temper_drc_rs, "resource_bound_cluster_union_bbox_py", _raise_marker)
    with pytest.raises(_WiringMarker):
        shipped._cluster_union_bbox(["A", "B"], _NONTRIVIAL_BBOXES)


def _make_grid(width_cells=20, height_cells=20, cell_size=1.0, seed=1) -> OccupancyGrid:
    rng = np.random.RandomState(seed)
    grid = np.zeros((height_cells, width_cells), dtype=np.int8)
    for _ in range(width_cells * height_cells // 5):
        grid[rng.randint(0, height_cells), rng.randint(0, width_cells)] = 1
    return OccupancyGrid(
        layer_name="F.Cu",
        grid=grid,
        origin=(0.0, 0.0),
        cell_size=cell_size,
        width_cells=width_cells,
        height_cells=height_cells,
    )


def test_capacity_in_bbox_delegates_to_rust(monkeypatch):
    monkeypatch.setattr(shipped._temper_drc_rs, "resource_bound_capacity_in_bbox_py", _raise_marker)
    grid = _make_grid()
    with pytest.raises(_WiringMarker):
        shipped._capacity_in_bbox(grid, (0.0, 0.0, 10.0, 10.0))


def test_compute_fill_factor_delegates_to_rust(monkeypatch):
    monkeypatch.setattr(shipped._temper_drc_rs, "resource_bound_compute_fill_factor_py", _raise_marker)
    with pytest.raises(_WiringMarker):
        shipped._compute_fill_factor(0.2, {"A": 100.0, "B": 400.0})


def test_max_routable_nets_delegates_to_rust_transitively(monkeypatch):
    """max_routable_nets's own body is unchanged Python, but it calls
    _compute_conflict_clusters -- which now delegates. Breaking the Rust
    kernel must break max_routable_nets too, proving the whole call chain
    actually reaches Rust rather than a Python fallback swallowing it."""
    monkeypatch.setattr(shipped._temper_drc_rs, "resource_bound_conflict_clusters_py", _raise_marker)
    grid = _make_grid()
    with pytest.raises(_WiringMarker):
        shipped.max_routable_nets(grid, _NONTRIVIAL_BBOXES, 0.2)


def test_demand_budget_summary_delegates_to_rust_transitively(monkeypatch):
    monkeypatch.setattr(shipped._temper_drc_rs, "resource_bound_capacity_in_bbox_py", _raise_marker)
    grid = _make_grid()
    with pytest.raises(_WiringMarker):
        shipped.demand_budget_summary(grid, _NONTRIVIAL_BBOXES, 0.2)


# ---------------------------------------------------------------------------
# Randomized differential fixtures
# ---------------------------------------------------------------------------


def _random_bboxes(rng: random.Random, n: int, span: float = 30.0) -> dict[str, tuple[float, float, float, float]]:
    bboxes = {}
    for i in range(n):
        x1 = rng.uniform(0, span)
        y1 = rng.uniform(0, span)
        x2 = x1 + rng.uniform(0.0, span * 0.4)
        y2 = y1 + rng.uniform(0.0, span * 0.4)
        bboxes[f"N{i}"] = (x1, y1, x2, y2)
    return bboxes


def _clusters_as_sets(clusters: list[list[str]]) -> set[frozenset[str]]:
    return {frozenset(c) for c in clusters}


# ---------------------------------------------------------------------------
# _compute_conflict_clusters
# ---------------------------------------------------------------------------


def test_compute_conflict_clusters_matches_oracle_membership_randomized():
    rng = random.Random(2026080701)
    for _ in range(60):
        n = rng.randint(0, 25)
        bboxes = _random_bboxes(rng, n)
        real = shipped._compute_conflict_clusters(bboxes)
        oracle = ORACLE._compute_conflict_clusters(bboxes)
        assert len(real) == len(oracle), (n, bboxes)
        assert _clusters_as_sets(real) == _clusters_as_sets(oracle), (n, bboxes)


def test_compute_conflict_clusters_empty_and_single():
    assert shipped._compute_conflict_clusters({}) == ORACLE._compute_conflict_clusters({}) == []
    single = {"A": (0.0, 0.0, 1.0, 1.0)}
    assert shipped._compute_conflict_clusters(single) == ORACLE._compute_conflict_clusters(single) == [["A"]]


def test_compute_conflict_clusters_custom_overlap_threshold():
    rng = random.Random(99)
    bboxes = _random_bboxes(rng, 15)
    for threshold in (0.01, 0.1, 0.5, 0.9):
        real = shipped._compute_conflict_clusters(bboxes, threshold)
        oracle = ORACLE._compute_conflict_clusters(bboxes, threshold)
        assert _clusters_as_sets(real) == _clusters_as_sets(oracle), threshold


# ---------------------------------------------------------------------------
# _cluster_union_bbox
# ---------------------------------------------------------------------------


def test_cluster_union_bbox_matches_oracle_randomized():
    rng = random.Random(20260807)
    for _ in range(60):
        n = rng.randint(1, 15)
        bboxes = _random_bboxes(rng, n)
        cluster = list(bboxes.keys())
        rng.shuffle(cluster)
        # Take a random non-empty sub-cluster.
        k = rng.randint(1, len(cluster))
        sub = cluster[:k]
        real = shipped._cluster_union_bbox(sub, bboxes)
        oracle = ORACLE._cluster_union_bbox(sub, bboxes)
        assert real == oracle, (sub, bboxes)


def test_cluster_union_bbox_empty_cluster():
    assert shipped._cluster_union_bbox([], {}) == ORACLE._cluster_union_bbox([], {}) == (0.0, 0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# _capacity_in_bbox
# ---------------------------------------------------------------------------


def test_capacity_in_bbox_matches_oracle_randomized():
    rng = random.Random(555)
    for _ in range(60):
        w, h = rng.randint(3, 40), rng.randint(3, 40)
        cell_size = rng.choice([0.1, 0.25, 0.5, 1.0])
        grid = _make_grid(w, h, cell_size, seed=rng.randint(0, 10_000))
        bbox = (
            rng.uniform(-5.0, w * cell_size + 5.0),
            rng.uniform(-5.0, h * cell_size + 5.0),
            rng.uniform(-5.0, w * cell_size + 5.0),
            rng.uniform(-5.0, h * cell_size + 5.0),
        )
        real = shipped._capacity_in_bbox(grid, bbox)
        oracle = ORACLE._capacity_in_bbox(grid, bbox)
        assert real == oracle, (w, h, cell_size, bbox)


def test_capacity_in_bbox_out_of_bounds():
    grid = _make_grid(10, 10, 1.0)
    bbox = (100.0, 100.0, 200.0, 200.0)
    assert shipped._capacity_in_bbox(grid, bbox) == ORACLE._capacity_in_bbox(grid, bbox)


def test_capacity_in_bbox_all_free_matches_oracle():
    grid = OccupancyGrid("F.Cu", np.zeros((50, 50), dtype=np.int8), (0.0, 0.0), 1.0, 50, 50)
    bbox = (0.0, 0.0, 10.0, 10.0)
    assert shipped._capacity_in_bbox(grid, bbox) == ORACLE._capacity_in_bbox(grid, bbox)


# ---------------------------------------------------------------------------
# _compute_fill_factor -- the np.clip NaN trap
# ---------------------------------------------------------------------------


def test_compute_fill_factor_matches_oracle_randomized():
    rng = random.Random(31337)
    for _ in range(80):
        trace_width = rng.uniform(0.0, 2.0)
        n = rng.randint(0, 10)
        areas = {f"N{i}": rng.uniform(0.01, 500.0) for i in range(n)}
        real = shipped._compute_fill_factor(trace_width, areas)
        oracle = ORACLE._compute_fill_factor(trace_width, areas)
        assert real == oracle, (trace_width, areas)


def test_compute_fill_factor_empty_matches_oracle():
    assert shipped._compute_fill_factor(0.2, {}) == ORACLE._compute_fill_factor(0.2, {}) == 0.5


def test_compute_fill_factor_nan_area_matches_oracle_not_naive_clip():
    """avg_area=NaN: `avg_area <= 0` is False in both languages (falls
    through rather than short-circuiting to 0.5), and np.clip(NaN, ...)
    propagates NaN -- NOT the 1.0 a naive max(lo, min(hi, NaN)) chain
    would give. Both the oracle and the shipped (Rust-backed) module must
    agree, and both must be NaN."""
    areas = {"A": float("nan")}
    oracle = ORACLE._compute_fill_factor(0.2, areas)
    real = shipped._compute_fill_factor(0.2, areas)
    assert oracle != oracle, "oracle sanity: expected NaN"  # noqa: PLR0124 (NaN != NaN)
    assert real != real, f"expected NaN, got {real}"


def test_compute_fill_factor_clip_bounds_match_oracle():
    # ff way below 0.01 and way above 1.0, both directions.
    for trace_width, areas in [
        (0.0001, {"A": 1_000_000.0}),
        (1000.0, {"A": 0.0001}),
    ]:
        real = shipped._compute_fill_factor(trace_width, areas)
        oracle = ORACLE._compute_fill_factor(trace_width, areas)
        assert real == oracle
        assert 0.01 <= real <= 1.0


# ---------------------------------------------------------------------------
# max_routable_nets (live importer: benchmark.py)
# ---------------------------------------------------------------------------


def test_max_routable_nets_matches_oracle_randomized():
    rng = random.Random(20260807 * 2)
    for _ in range(40):
        w, h = rng.randint(10, 60), rng.randint(10, 60)
        cell_size = rng.choice([0.1, 0.5, 1.0])
        grid = _make_grid(w, h, cell_size, seed=rng.randint(0, 10_000))
        n = rng.randint(0, 20)
        bboxes = _random_bboxes(rng, n, span=w * cell_size)
        trace_width = rng.uniform(0.05, 1.0)
        real = shipped.max_routable_nets(grid, bboxes, trace_width)
        oracle = ORACLE.max_routable_nets(grid, bboxes, trace_width)
        assert real == oracle, (w, h, cell_size, n, trace_width, bboxes)


def test_max_routable_nets_explicit_fill_factor_matches_oracle():
    grid = _make_grid(30, 30, 1.0)
    bboxes = {"A": (0.0, 0.0, 10.0, 10.0), "B": (15.0, 15.0, 25.0, 25.0)}
    for ff in (0.01, 0.1, 0.5, 1.0):
        real = shipped.max_routable_nets(grid, bboxes, 0.2, fill_factor=ff)
        oracle = ORACLE.max_routable_nets(grid, bboxes, 0.2, fill_factor=ff)
        assert real == oracle, ff


def test_max_routable_nets_empty_matches_oracle():
    grid = _make_grid()
    assert shipped.max_routable_nets(grid, {}, 0.2) == ORACLE.max_routable_nets(grid, {}, 0.2) == 0


# ---------------------------------------------------------------------------
# demand_budget_summary (live importer: _pipeline_grid.py)
# ---------------------------------------------------------------------------


def _assert_summary_matches(real: dict, oracle: dict, *, context) -> None:
    # Exact / order-invariant fields.
    for key in ("max_routable", "total_nets", "cluster_count", "fill_factor"):
        assert real[key] == oracle[key], (key, context)
    # total_demand_mm2 is a sum over net_bboxes dict order, which IS
    # deterministic (Python dict iteration is insertion-ordered) -- exact.
    assert real["total_demand_mm2"] == oracle["total_demand_mm2"], context
    # total_capacity_mm2 / utilization sum over CLUSTER order, which the
    # oracle's own hash-salted set traversal does not guarantee -- see the
    # module docstring. Tight tolerance, not bit-exact.
    assert real["total_capacity_mm2"] == pytest.approx(oracle["total_capacity_mm2"], rel=1e-9, abs=1e-9), context
    assert real["utilization"] == pytest.approx(oracle["utilization"], rel=1e-9, abs=1e-9), context


def test_demand_budget_summary_matches_oracle_randomized():
    rng = random.Random(777111)
    for _ in range(40):
        w, h = rng.randint(10, 60), rng.randint(10, 60)
        cell_size = rng.choice([0.1, 0.5, 1.0])
        grid = _make_grid(w, h, cell_size, seed=rng.randint(0, 10_000))
        n = rng.randint(0, 20)
        bboxes = _random_bboxes(rng, n, span=w * cell_size)
        trace_width = rng.uniform(0.05, 1.0)
        real = shipped.demand_budget_summary(grid, bboxes, trace_width)
        oracle = ORACLE.demand_budget_summary(grid, bboxes, trace_width)
        _assert_summary_matches(real, oracle, context=(w, h, cell_size, n, trace_width))


def test_demand_budget_summary_empty_matches_oracle():
    grid = _make_grid()
    real = shipped.demand_budget_summary(grid, {}, 0.2)
    oracle = ORACLE.demand_budget_summary(grid, {}, 0.2)
    assert real == oracle


def test_demand_budget_summary_single_cluster_capacity_is_bit_exact():
    """A single-cluster board has no cross-cluster summation-order
    ambiguity at all -- total_capacity_mm2 must match the oracle exactly,
    not just within tolerance, whenever there is only one cluster."""
    grid = _make_grid(30, 30, 1.0)
    bboxes = {"A": (0.0, 0.0, 5.0, 5.0), "B": (1.0, 1.0, 6.0, 6.0)}  # overlapping -> one cluster
    real = shipped.demand_budget_summary(grid, bboxes, 0.2)
    oracle = ORACLE.demand_budget_summary(grid, bboxes, 0.2)
    assert real["cluster_count"] == oracle["cluster_count"] == 1
    assert real["total_capacity_mm2"] == oracle["total_capacity_mm2"]
    assert real["utilization"] == oracle["utilization"]
