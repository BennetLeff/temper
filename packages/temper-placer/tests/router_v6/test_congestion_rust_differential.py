"""R1a differential: Wave-4 cluster E (congestion & placement feedback) vs its pinned oracle.

**THIS SUITE IS DELIBERATELY RED.**  Gate G1 requires the differential that
pins the pre-migration implementation verbatim to exist and fail *before* the
Rust exists, so every comparison below resolves its Rust arm through
``tests/router_v6/_pending_rust.rust`` and fails with a named
``PendingRustError`` until Phase B supplies the pyfunction.  See that
module's docstring for why a skip, an ``xfail`` and a module-scope import
were all rejected.

Arms
----
* **oracle** -- ``tests/router_v6/_congestion_py_oracle.py``, a verbatim
  ``git show`` copy of the six cluster-E modules at
  ``143752893c177dc976da614566c64e4e53e4951f`` (``origin/main``).
* **rust** -- the pyfunctions Phase B will add.  All of them are listed in
  :data:`REQUIRED_RUST_SYMBOLS` and bound in the adapter block below; nothing
  outside that block knows the Rust arm exists.

Comparison is by **type-carrying signature** (``tests/router_v6/_signature``):
``float.hex()`` per float, ``dtype`` + ``shape`` per array, concrete type name
per leaf.  **No tolerance anywhere** -- gate G2.  Exceptions are captured and
compared as values, so error parity (type and message) is part of the
differential rather than an unasserted side channel.

Traps this file pins explicitly
-------------------------------
``np.maximum`` propagates NaN from **either** operand; CPython's ``max``
keeps the **first**; ``f64::max`` **discards** it.  This cluster uses the
first two, sometimes within five files of each other, and
``test_trap_three_way_max_semantics`` measures all three side by side (B12,
B5).

``np.sum`` is a **pairwise** reduction, not a left fold.  Measured here on
the corpus's own grids (:func:`test_trap_np_sum_is_not_a_left_fold`).

``(dx**2 + dy**2) ** 0.5`` is two libm ``pow`` calls, and disagrees with
``math.hypot`` on ~17% of random pairs and with ``sqrt(dx*dx + dy*dy)`` on
~0.3% (:func:`test_trap_pow_form_is_not_hypot_or_sqrt`) (B7).

``format(x, '.2f')`` rounds the exact binary value **half to even**:
``0.125`` renders ``'0.12'``.  That string is a compared dataclass field
(:func:`test_trap_format_2f_is_round_half_even`) (B3).

``CongestionHeatmap.get_hotspots`` returns tuples mixing Python ``float``
with ``numpy.float32``.  ``==`` cannot see that; ``sig()`` can
(:func:`test_trap_hotspot_tuples_leak_float32`).

Defects repaired since the first pin
------------------------------------
D1 (``positions=`` ignored), D2 (``layer_assignments=`` raising
``ModuleNotFoundError``) and D3 (an off-board net writing a 7x7 block at the
board origin) were all pinned *unfixed* by the first version of this file.
**#760 (``aebaecd99``) repaired all three**, and the oracle was re-pinned onto
the repaired source at ``143752893``.

The three pins were **inverted, not deleted**: each now asserts the repaired
behaviour, so a re-introduction of the original defect fails here rather than
being silently blessed, and each also rejects the plausible-but-wrong fix a
reimplementation would most likely reach for instead.  Each pairs an ``ast``
read of the *shipped* module -- which is how a production regression is
caught even though the oracle itself is a frozen copy pinned at a SHA -- with
a real call to the oracle.  See the oracle header for the measurements on
both sides of each repair.
"""

from __future__ import annotations

import ast
import math
import random
import subprocess
from pathlib import Path

import numpy as np
import pytest

import tests.router_v6._congestion_py_oracle as ORACLE
from tests.router_v6._congestion_builders import (
    build_board,
    build_grid,
    build_netlist,
    build_parsed_pcb,
    build_router_stub,
    build_routing_results,
)
from tests.router_v6._congestion_cases import (
    ANALYZE_DESIGNS,
    BENCH_ANALYZE_DESIGNS,
    BENCH_BOARD_GRIDS,
    BENCH_DEMAND_SUPPLY_PAIRS,
    BENCH_HEATMAP_ROUTERS,
    BENCH_NET_BBOXES,
    BENCH_ROUTING_RESULT_CASES,
    BOARD_GRIDS,
    DAMPING_CASES,
    DEMAND_PCBS,
    DEMAND_SUPPLY_PAIRS,
    HEATMAP_QUERIES,
    HEATMAP_ROUTERS,
    HOTSPOT_THRESHOLDS,
    NET_BBOXES,
    ROUTING_RESULT_CASES,
    SUGGESTION_POSITIONS,
    SUGGESTION_REGIONS,
    random_demand_supply,
    random_net_bboxes,
)
from tests.router_v6._pending_rust import missing_symbols, rust
from tests.router_v6._signature import sig

# ===========================================================================
# ADAPTER BLOCK -- the ONLY part of this file that knows the Rust arm exists.
#
# Phase B binds these; nothing below this block changes.  A diff of the Rust
# PR that touches anything past the closing banner is a weakened assertion.
# ===========================================================================

#: Migration target.  ``congestion_tensor.rs`` already lives in
#: ``temper-geometry`` and this cluster's grid kernels are its neighbours, so
#: that is the crate named here.  If Phase B picks a different home, this one
#: constant moves and the suite is otherwise unchanged.
_RUST_MODULE = "temper_geometry"

REQUIRED_RUST_SYMBOLS: tuple[str, ...] = (
    # congestion.py
    "congestion_grid_from_board_py",
    "congestion_grid_utilization_py",
    "congestion_grid_overflow_py",
    "congestion_bottleneck_to_coordinates_py",
    "congestion_result_overflow_ratio_py",
    "congestion_result_top_bottlenecks_py",
    "congestion_estimate_net_demand_py",
    "congestion_analyze_py",
    # congestion_analysis.py
    "congestion_identify_regions_py",
    "congestion_classify_severity_py",
    # routing_demand.py
    "routing_demand_estimate_py",
    "routing_demand_complexity_py",
    # placement_suggestions.py
    "placement_suggestions_generate_py",
    "placement_find_affected_py",
    "placement_suggested_position_py",
    # congestion_heatmap.py
    "congestion_heatmap_from_router_py",
    "congestion_heatmap_at_py",
    "congestion_heatmap_total_py",
    "congestion_heatmap_hotspots_py",
    # apply_suggestions.py
    "apply_suggestions_damped_py",
    "apply_damped_position_py",
    "apply_total_movement_py",
    "apply_update_positions_py",
)


def _rust(symbol: str):
    return rust(_RUST_MODULE, symbol)


# ===========================================================================
# END ADAPTER BLOCK
# ===========================================================================

_ORACLE_PIN_SHA = "143752893c177dc976da614566c64e4e53e4951f"
_ORACLE_SOURCES: dict[str, tuple[str, ...]] = {
    "congestion.py": (
        "CongestionGrid",
        "Bottleneck",
        "CongestionResult",
        "estimate_net_demand",
        "_get_pin_positions",
        "analyze_congestion",
    ),
    "congestion_analysis.py": (
        "CongestionSeverity",
        "CongestedRegion",
        "CongestionMap",
        "identify_congested_regions",
        "_classify_congestion",
    ),
    "routing_demand.py": ("RoutingDemand", "estimate_routing_demand"),
    "placement_suggestions.py": (
        "PlacementSuggestion",
        "PlacementSuggestions",
        "generate_placement_suggestions",
        "_find_affected_components",
        "_calculate_suggested_position",
    ),
    "congestion_heatmap.py": ("CongestionHeatmap",),
    "apply_suggestions.py": (
        "AppliedAdjustment",
        "AdjustmentResult",
        "apply_suggestions_with_damping",
        "_calculate_damped_position",
        "update_component_positions",
    ),
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _capture(fn):
    """Run ``fn()``, returning its value or the exception it raised.

    Error parity is part of the contract, so an exception is a *value* here,
    not a test failure.
    """
    try:
        return fn()
    except BaseException as exc:  # noqa: BLE001 - error parity is the point
        return exc


def _assert_same(label: str, oracle_fn, symbol: str, rust_fn):
    """Compare the two arms bit-for-bit.

    The oracle arm runs **first and unconditionally**, so a broken oracle
    fails with its own error rather than being masked by the pending-Rust
    failure.
    """
    a = _capture(oracle_fn)
    fn = _rust(symbol)  # RED until Phase B lands
    b = _capture(lambda: rust_fn(fn))
    assert sig(a) == sig(b), f"{label}: oracle={a!r} rust={b!r}"


def _region(case: tuple):
    cx, cy, radius, severity, failed, score = case
    return ORACLE.CongestedRegion(
        center=(cx, cy),
        radius=radius,
        severity=ORACLE.CongestionSeverity(severity)
        if severity in {s.value for s in ORACLE.CongestionSeverity}
        else _FakeSeverity(severity),
        failed_net_count=failed,
        bottleneck_score=score,
    )


class _FakeSeverity:
    """A severity whose ``.value`` is not one of the five enum members.

    ``_calculate_suggested_position`` looks the value up in a dict with a
    ``.get(severity, 3.0)`` default, so an unknown severity is a reachable
    input, and the corpus carries one.
    """

    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value


# ---------------------------------------------------------------------------
# G1 evidence: the oracle really is a verbatim copy, and the suite really is
# red.
# ---------------------------------------------------------------------------


def _segments_at_pin(path: str, names: tuple[str, ...]) -> dict[str, str]:
    rel = f"packages/temper-placer/src/temper_placer/router_v6/{path}"
    src = subprocess.run(
        ["git", "show", f"{_ORACLE_PIN_SHA}:{rel}"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return _segments_from_source(src, names)


def _segments_from_source(src: str, names: tuple[str, ...]) -> dict[str, str]:
    tree = ast.parse(src)
    lines = src.splitlines()
    out: dict[str, str] = {}
    for node in tree.body:
        nm = getattr(node, "name", None)
        if nm in names:
            decos = getattr(node, "decorator_list", [])
            start = (min(d.lineno for d in decos) if decos else node.lineno) - 1
            out[nm] = "\n".join(lines[start : node.end_lineno])
    return out


def test_oracle_is_verbatim_copy():
    """Every definition in the oracle is character-identical to the pin.

    This is the gate-G1 artefact: if anyone "improves" the oracle -- including
    fixing D1, D2 or D3 -- the differential stops proving anything, so drift
    fails here instead of passing quietly.
    """
    try:
        subprocess.run(
            ["git", "cat-file", "-e", f"{_ORACLE_PIN_SHA}^{{commit}}"],
            capture_output=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):  # pragma: no cover
        pytest.skip(f"pinned commit {_ORACLE_PIN_SHA} not present in this clone")

    with open(ORACLE.__file__, encoding="utf-8") as fh:
        copied = _segments_from_source(
            fh.read(), tuple(n for v in _ORACLE_SOURCES.values() for n in v)
        )

    for path, names in _ORACLE_SOURCES.items():
        original = _segments_at_pin(path, names)
        for name in names:
            assert name in copied, f"{name} missing from the oracle module"
            assert name in original, f"{name} missing from {path} at {_ORACLE_PIN_SHA}"
            assert copied[name] == original[name], (
                f"{path}::{name} in the oracle is NOT verbatim -- "
                f"the pin is broken and the differential proves nothing"
            )


def test_oracle_excludes_the_stage_wrapper():
    """``RoutingDemandStage`` / ``validate_routing_demand`` are NOT copied.

    ``@register_validator("RoutingDemand")`` mutates a process-global
    registry at import time; copying it would double-register a validator for
    the shipped module.  The exclusion is behavioural, so it is asserted.
    """
    assert not hasattr(ORACLE, "RoutingDemandStage")
    assert not hasattr(ORACLE, "validate_routing_demand")


def test_rust_symbols_exist():
    """The Phase-B checklist.  RED until every kernel is ported."""
    missing = missing_symbols(_RUST_MODULE, REQUIRED_RUST_SYMBOLS)
    assert not missing, (
        f"{_RUST_MODULE} is missing {len(missing)} of {len(REQUIRED_RUST_SYMBOLS)} "
        f"cluster-E kernels: {missing}"
    )


def test_bench_corpus_is_covered_by_differential():
    """Every benchmark row is a row the differential already compares.

    PR #714 passed its differential at iterations ``[0, 1, 2, 8, 17, 100]``
    and then failed CI on a benchmark that ran 120.  This assertion is what
    makes that class of gap unreachable.
    """
    for bench, full, name in (
        (BENCH_BOARD_GRIDS, BOARD_GRIDS, "BOARD_GRIDS"),
        (BENCH_DEMAND_SUPPLY_PAIRS, DEMAND_SUPPLY_PAIRS, "DEMAND_SUPPLY_PAIRS"),
        (BENCH_NET_BBOXES, NET_BBOXES, "NET_BBOXES"),
        (BENCH_ROUTING_RESULT_CASES, ROUTING_RESULT_CASES, "ROUTING_RESULT_CASES"),
    ):
        missing = [b for b in bench if b not in full]
        assert not missing, f"BENCH_{name} rows absent from {name}: {missing}"
    assert all(d in ANALYZE_DESIGNS for d in BENCH_ANALYZE_DESIGNS)
    assert all(h in HEATMAP_ROUTERS for h in BENCH_HEATMAP_ROUTERS)
    for bench, name in (
        (BENCH_BOARD_GRIDS, "BOARD_GRIDS"),
        (BENCH_DEMAND_SUPPLY_PAIRS, "DEMAND_SUPPLY_PAIRS"),
        (BENCH_NET_BBOXES, "NET_BBOXES"),
        (BENCH_ROUTING_RESULT_CASES, "ROUTING_RESULT_CASES"),
        (BENCH_ANALYZE_DESIGNS, "ANALYZE_DESIGNS"),
        (BENCH_HEATMAP_ROUTERS, "HEATMAP_ROUTERS"),
    ):
        assert bench, f"BENCH_{name} is empty -- a vacuous containment assertion"


# ---------------------------------------------------------------------------
# congestion.py -- CongestionGrid
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", BOARD_GRIDS)
def test_grid_from_board_bit_exact(case):
    w, h, cell, layers, supply, origin = case

    def _oracle():
        g = ORACLE.CongestionGrid.from_board(
            build_board(w, h, origin),
            cell_size_mm=cell,
            num_layers=layers,
            default_supply=supply,
        )
        return (
            g.demand,
            g.supply,
            g.cell_size_mm,
            g.width_cells,
            g.height_cells,
            g.num_layers,
            g.origin,
        )

    _assert_same(
        f"from_board{case}",
        _oracle,
        "congestion_grid_from_board_py",
        lambda fn: fn(w, h, origin, cell, layers, supply),
    )


@pytest.mark.parametrize("case", DEMAND_SUPPLY_PAIRS)
def test_grid_utilization_bit_exact(case):
    demand, supply = case
    _assert_same(
        f"get_utilization({demand}, {supply})",
        lambda: build_grid(ORACLE, demand, supply).get_utilization(),
        "congestion_grid_utilization_py",
        lambda fn: fn(demand, supply),
    )


@pytest.mark.parametrize("case", DEMAND_SUPPLY_PAIRS)
def test_grid_overflow_bit_exact(case):
    demand, supply = case
    _assert_same(
        f"get_overflow({demand}, {supply})",
        lambda: build_grid(ORACLE, demand, supply).get_overflow(),
        "congestion_grid_overflow_py",
        lambda fn: fn(demand, supply),
    )


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_grid_utilization_random_sweep(seed):
    for demand, supply in random_demand_supply(seed, 40):
        _assert_same(
            f"random utilization seed={seed}",
            lambda d=demand, s=supply: build_grid(ORACLE, d, s).get_utilization(),
            "congestion_grid_utilization_py",
            lambda fn, d=demand, s=supply: fn(d, s),
        )


@pytest.mark.parametrize(
    "cell,origin,x,y",
    [
        (1.0, (0.0, 0.0), 0, 0),
        (1.0, (0.0, 0.0), 3, 7),
        (1.0, (-0.0, -0.0), 0, 0),
        (0.25, (-5.0, 12.5), 11, 2),
        (0.1, (0.0, 0.0), 9, 9),  # 0.1 is not representable; (x + 0.5) * 0.1 is inexact
        (1e-9, (1e9, 1e9), 1, 1),  # catastrophic cancellation
        (float("inf"), (0.0, 0.0), 1, 1),
        (float("nan"), (0.0, 0.0), 1, 1),
        (1.0, (float("inf"), 0.0), 1, 1),
    ],
)
def test_bottleneck_to_coordinates_bit_exact(cell, origin, x, y):
    _assert_same(
        f"to_coordinates(cell={cell}, origin={origin}, x={x}, y={y})",
        lambda: ORACLE.Bottleneck(x=x, y=y, utilization=0.0, overflow=0.0).to_coordinates(
            cell_size_mm=cell, origin=origin
        ),
        "congestion_bottleneck_to_coordinates_py",
        lambda fn: fn(x, y, cell, origin),
    )


@pytest.mark.parametrize(
    "demand,total_overflow",
    [
        ([0.0, 0.0], 0.0),  # total_demand == 0 -> the early 0.0 return
        ([1.0, 1.0], 0.0),
        ([1.0, 1.0], 1.0),
        ([1.0, 1.0], 2.0),  # ratio 1.0 exactly
        ([1.0, 1.0], 5.0),  # min() clamps
        ([1.0, 1.0], -1.0),  # negative ratio is NOT clamped from below
        ([1.0, 1.0], float("nan")),  # NaN is the FIRST min() argument -> NaN (B5)
        ([1.0, 1.0], float("inf")),
        ([float("nan"), 1.0], 1.0),  # NaN total_demand: != 0, so no early return
        ([-1.0, 1.0], 1.0),  # total_demand == 0.0 via cancellation
        ([1e308, 1e308], 1.0),  # total_demand overflows to inf
        ([5e-324], 5e-324),  # denormal band (B8)
    ],
)
def test_overflow_ratio_bit_exact(demand, total_overflow):
    grid = build_grid(ORACLE, demand, [1.0] * len(demand))
    _assert_same(
        f"overflow_ratio(demand={demand}, overflow={total_overflow})",
        lambda: ORACLE.CongestionResult(grid=grid, total_overflow=total_overflow).overflow_ratio(),
        "congestion_result_overflow_ratio_py",
        lambda fn: fn(demand, total_overflow),
    )


@pytest.mark.parametrize(
    "overflows,n",
    [
        ([], 10),
        ([1.0], 10),
        ([3.0, 1.0, 2.0], 10),
        ([1.0, 1.0, 1.0, 1.0, 1.0], 3),  # a full tie -- stable-sort order
        ([1.0, 1.0, 1.0], 0),
        ([1.0, 1.0, 1.0], -1),  # negative n -> `[:-1]`, NOT an empty list
        ([float("nan"), 5.0, 1.0], 3),  # NaN in a sort key
        ([float("inf"), 1.0], 2),
        ([0.0, -0.0], 2),  # signed zeros compare equal -> stable order
        ([1.0, 2.0, 3.0], 100),
    ],
)
def test_top_bottlenecks_bit_exact(overflows, n):
    def _oracle():
        bs = [
            ORACLE.Bottleneck(x=i, y=0, utilization=float(i), overflow=o)
            for i, o in enumerate(overflows)
        ]
        result = ORACLE.CongestionResult(grid=build_grid(ORACLE, [0.0], [1.0]), bottlenecks=bs)
        return [
            (b.x, b.y, b.utilization, b.overflow, b.layer) for b in result.get_top_bottlenecks(n)
        ]

    _assert_same(
        f"get_top_bottlenecks({overflows}, n={n})",
        _oracle,
        "congestion_result_top_bottlenecks_py",
        # The kernel's contract is REAL bottleneck records -- the oracle's own
        # fixtures flattened -- not a bare list of `overflow` floats.  The
        # synthetic `(x=i, y=0, utilization=i, layer=0)` reconstruction the
        # kernel used to build from a flat list matched this fixture exactly,
        # which is precisely why it could not see the gap (arbitrary records).
        lambda fn: fn([(i, 0, float(i), o, 0) for i, o in enumerate(overflows)], n),
    )


# Real bottleneck records with arbitrary x/y/utilization/layer -- the shape
# the shipped `CongestionResult.get_top_bottlenecks` actually sorts.  The
# synthetic-form fixture above pins x=i/y=0/utilization=i/layer=0 only, so it
# cannot see a kernel that drops any of those fields.
_BOTTLENECK_RECORDS: list[tuple[list[tuple[int, int, float, float, int]], int]] = [
    # arbitrary coordinates / utilization / layers
    ([(2, 3, 0.5, 1.5, 1), (0, 0, 0.25, 0.5, 0)], 10),
    ([(5, 1, 1.0, 2.0, 0), (1, 2, 0.9, 2.0, 0), (3, 4, 0.8, 1.0, 1)], 2),
    ([(4, 4, 0.1, 1.0, 2), (0, 0, 0.2, 3.0, 1), (1, 1, 0.3, 2.0, 0)], -1),  # negative n -> `[:-1]`
    ([], 5),
    ([(2, 2, 0.5, 1.0, 0)], 0),
    ([(2, 2, 0.5, 1.0, 0)], 100),
    # an overflow TIE with unequal secondary fields: only timsort stability
    # decides, so the secondary fields must survive into the output verbatim
    ([(3, 3, 0.1, 2.0, 0), (1, 1, 0.9, 2.0, 1), (2, 2, 0.5, 2.0, 0)], 3),
    # NaN in the sort key
    ([(1, 1, 0.5, float("nan"), 0), (2, 2, 0.5, 5.0, 0), (3, 3, 0.5, 1.0, 0)], 3),
    # infinities sort to the edges
    ([(1, 1, 0.5, float("inf"), 0), (2, 2, 0.5, -float("inf"), 0), (3, 3, 0.5, 0.0, 0)], 3),
    # signed zeros compare equal -> stability decides
    ([(0, 0, 0.0, 1.0, 0), (0, 0, 0.0, -0.0, 0)], 2),
    # a full tie across every record
    ([(0, 0, 0.0, 1.0, 0), (1, 1, 0.0, 1.0, 1), (2, 2, 0.0, 1.0, 2)], 2),
]


@pytest.mark.parametrize("records,n", _BOTTLENECK_RECORDS)
def test_top_bottlenecks_real_records_bit_exact(records, n):
    def _oracle():
        bs = [ORACLE.Bottleneck(x=x, y=y, utilization=u, overflow=o, layer=l) for (x, y, u, o, l) in records]
        result = ORACLE.CongestionResult(grid=build_grid(ORACLE, [0.0], [1.0]), bottlenecks=bs)
        return [(b.x, b.y, b.utilization, b.overflow, b.layer) for b in result.get_top_bottlenecks(n)]

    _assert_same(
        f"get_top_bottlenecks(records={records}, n={n})",
        _oracle,
        "congestion_result_top_bottlenecks_py",
        lambda fn: fn(list(records), n),
    )


@pytest.mark.parametrize("case", NET_BBOXES)
def test_estimate_net_demand_bit_exact(case):
    w, h, cell, origin, pins, layer, per_cell = case
    layers = 2 if layer > 0 else 1

    def _oracle():
        grid = ORACLE.CongestionGrid.from_board(
            build_board(w, h, origin), cell_size_mm=cell, num_layers=layers
        )
        out = ORACLE.estimate_net_demand(grid, pins, layer=layer, demand_per_cell=per_cell)
        # `out is grid` for the < 2 pins early return; the identity itself is
        # part of the contract, so it is signed alongside the values.
        return (out.demand, out is grid)

    _assert_same(
        f"estimate_net_demand{case}",
        _oracle,
        "congestion_estimate_net_demand_py",
        lambda fn: fn(w, h, cell, origin, pins, layer, per_cell, layers),
    )


@pytest.mark.parametrize("seed", [11, 12])
def test_estimate_net_demand_random_sweep(seed):
    for pins in random_net_bboxes(seed, 40):

        def _oracle(p=pins):
            # Signs the SAME pair as test_estimate_net_demand_bit_exact.
            # Projecting a bare `.demand` here signed strictly less than its
            # sibling and, because `sig()` is arity-carrying, no single Rust
            # function could satisfy both call sites at once.  The identity is
            # the D3 contract: both early returns hand back the INPUT grid, and
            # a mirror returning a fresh copy carrying an empty write is
            # indistinguishable from the repair unless `out is grid` is signed.
            grid = ORACLE.CongestionGrid.from_board(
                build_board(10.0, 10.0), cell_size_mm=1.0
            )
            out = ORACLE.estimate_net_demand(grid, p)
            return (out.demand, out is grid)

        _assert_same(
            f"random bbox seed={seed} pins={pins}",
            _oracle,
            "congestion_estimate_net_demand_py",
            lambda fn, p=pins: fn(10.0, 10.0, 1.0, (0.0, 0.0), p, 0, 1.0, 1),
        )


# The ACCUMULATION shape -- the reason `estimate_net_demand` could not
# delegate (see the module docstring's first gap).  `analyze_congestion`'s
# per-net loop accumulates onto the SAME grid across many nets; a kernel that
# always rebuilds a fresh zero grid silently drops every net's demand but the
# first.  Each case here accumulates several nets onto ONE grid, so the
# pre-existing demand must survive.
#   (w, h, cell, origin, layers, [(pins, layer, demand_per_cell), ...])
_ACCUMULATION_CASES: list[tuple] = [
    # two disjoint nets -- the second must NOT erase the first
    (10.0, 10.0, 1.0, (0.0, 0.0), 1,
     [([(1.0, 1.0), (3.0, 3.0)], 0, 1.0), ([(5.0, 5.0), (7.0, 7.0)], 0, 1.0)]),
    # overlapping bboxes: the shared cells read 2.0, not 1.0 -- the crux case
    (10.0, 10.0, 1.0, (0.0, 0.0), 1,
     [([(1.0, 1.0), (6.0, 6.0)], 0, 1.0), ([(3.0, 3.0), (8.0, 8.0)], 0, 1.0)]),
    # a < 2-pin net mid-accumulation contributes nothing but leaves the rest
    (10.0, 10.0, 1.0, (0.0, 0.0), 1,
     [([(1.0, 1.0), (3.0, 3.0)], 0, 1.0), ([(2.0, 2.0)], 0, 1.0), ([(5.0, 5.0), (6.0, 6.0)], 0, 1.0)]),
    # an off-board net mid-accumulation (D3's guard) likewise adds nothing
    (10.0, 10.0, 1.0, (0.0, 0.0), 1,
     [([(1.0, 1.0), (3.0, 3.0)], 0, 1.0), ([(50.0, 50.0), (60.0, 60.0)], 0, 1.0), ([(5.0, 5.0), (6.0, 6.0)], 0, 1.0)]),
    # fractional demand_per_cell: the overlap accumulates 0.5 + 0.5
    (10.0, 10.0, 1.0, (0.0, 0.0), 1,
     [([(1.0, 1.0), (6.0, 6.0)], 0, 0.5), ([(3.0, 3.0), (8.0, 8.0)], 0, 0.5)]),
    # NaN demand_per_cell: `0.0 + NaN` is NaN and NaN stays NaN under `NaN + 1.0`
    (10.0, 10.0, 1.0, (0.0, 0.0), 1,
     [([(1.0, 1.0), (3.0, 3.0)], 0, float("nan")), ([(2.0, 2.0), (4.0, 4.0)], 0, 1.0)]),
    # 3D: two nets on different layers accumulate independently
    (10.0, 10.0, 1.0, (0.0, 0.0), 2,
     [([(1.0, 1.0), (3.0, 3.0)], 0, 1.0), ([(1.0, 1.0), (3.0, 3.0)], 1, 1.0)]),
    # non-zero grid origin participates in the bbox math
    (10.0, 10.0, 1.0, (-5.0, -5.0), 1,
     [([(-4.0, -4.0), (0.0, 0.0)], 0, 1.0), ([(1.0, 1.0), (2.0, 2.0)], 0, 1.0)]),
    # three overlapping nets accumulate 1.0 + 1.0 + 1.0 in the centre
    (10.0, 10.0, 1.0, (0.0, 0.0), 1,
     [([(2.0, 2.0), (4.0, 4.0)], 0, 1.0), ([(3.0, 3.0), (5.0, 5.0)], 0, 1.0), ([(2.0, 2.0), (5.0, 5.0)], 0, 1.0)]),
]


@pytest.mark.parametrize(
    "case",
    _ACCUMULATION_CASES,
    ids=["disjoint", "overlap", "one_pin_middle", "offboard_middle", "fractional", "nan", "layers", "origin", "triple"],
)
def test_estimate_net_demand_accumulates_bit_exact(case):
    w, h, cell, origin, layers, nets = case

    def _oracle():
        grid = ORACLE.CongestionGrid.from_board(
            build_board(w, h, origin), cell_size_mm=cell, num_layers=layers
        )
        for pins, layer, per_cell in nets:
            grid = ORACLE.estimate_net_demand(grid, pins, layer=layer, demand_per_cell=per_cell)
        return grid.demand

    def _rust(fn):
        # The initial accumulator is the fresh grid's own zero array.  `ceil`
        # here is the kernel's own `ceil_to_int` formula (`math.ceil(w/cell)`),
        # so the shape matches `CongestionGrid.from_board`'s exactly; the
        # accumulator form of the kernel derives its cells from the ARRAY
        # shape, so w/h/cell below are pass-throughs for that form.
        height_cells = math.ceil(h / cell)
        width_cells = math.ceil(w / cell)
        shape = (height_cells, width_cells) if layers == 1 else (layers, height_cells, width_cells)
        demand = np.zeros(shape)
        for pins, layer, per_cell in nets:
            demand, _is_identity = fn(w, h, cell, origin, pins, layer, per_cell, layers, demand)
        return demand

    _assert_same(
        f"estimate_net_demand_accumulates[{w},{h},{cell},{origin},{layers}]",
        _oracle,
        "congestion_estimate_net_demand_py",
        _rust,
    )


@pytest.mark.parametrize("design", ANALYZE_DESIGNS, ids=lambda d: d["label"])
def test_analyze_congestion_bit_exact(design):
    def _oracle():
        result = ORACLE.analyze_congestion(
            build_netlist(design["components"], design["nets"]),
            build_board(*design["board"]),
            cell_size_mm=design["cell"],
            capacity_per_cell=design["capacity"],
            num_layers=design["layers"],
        )
        return (
            result.grid.demand,
            result.grid.supply,
            result.total_overflow,
            result.max_utilization,
            [(b.x, b.y, b.utilization, b.overflow, b.layer) for b in result.bottlenecks],
        )

    _assert_same(
        f"analyze_congestion[{design['label']}]",
        _oracle,
        "congestion_analyze_py",
        lambda fn: fn(
            design["components"],
            design["nets"],
            design["board"],
            design["cell"],
            design["capacity"],
            design["layers"],
        ),
    )


# ---------------------------------------------------------------------------
# congestion.py -- the three defects, REPAIRED by #760 and pinned INVERTED
#
# Each of D1/D2/D3 was originally pinned unfixed, because the oracle's job is
# to be the shipped behaviour.  #760 (``aebaecd99``) repaired all three and
# this oracle was re-pinned onto the repaired source at ``143752893``.  The
# pins below were **inverted rather than deleted**: each fails if the original
# defect returns, and each also rejects the plausible-but-wrong "fix" that a
# reimplementation is most likely to reach for instead.
#
# Every one has two halves:
#   * a STRUCTURAL half that reads the *shipped* module with ``ast`` -- not a
#     source-string match, so it survives reformatting, and not an import, so
#     it holds without the Rust extensions being buildable.  This is the half
#     that catches a regression in production even though the oracle is a
#     frozen copy pinned at a SHA.
#   * a BEHAVIOURAL half that actually calls the oracle.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SRC = _REPO_ROOT / "packages" / "temper-placer" / "src" / "temper_placer" / "router_v6"


def _shipped_function(module: str, name: str) -> ast.FunctionDef:
    """The shipped module's ``ast`` node for ``name``.

    Parsed rather than imported, for the same reason
    :func:`test_oracle_is_verbatim_copy` shells out to ``git show``: these
    structural checks must stay verifiable without the Rust extensions being
    importable.
    """
    path = _SRC / f"{module}.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{module}.py no longer defines {name}()")


def test_repaired_d1_positions_argument_is_honoured():
    """D1, REPAIRED by #760 (``aebaecd99``): ``positions=`` now moves the pins.

    **Was:** ``_get_pin_positions`` unpacked ``positions`` into
    ``comp_x, comp_y`` (and the ``else`` branch into ``_comp_x, _comp_y``,
    underscore-prefixed so linters read the whole triple as intentionally
    unused), then appended ``pin_world_position(pin, comp)`` -- which reads
    the component's own ``initial_position``.  Measured then: a ``positions``
    array moving every component 999 mm produced a byte-identical result to
    ``positions=None``, so the placement feedback loop was blind to the
    candidate placements it was scoring.

    **Now:** ``pos_override`` is threaded into ``pin_world_position_at``.

    This is the *inversion* of the old defect pin.  It fails if the dead
    ``comp_x``/``comp_y`` form returns, and -- via the structural half -- if
    someone "fixes" it by keeping ``pin_world_position`` and mutating the
    component instead, which would work here but leak a mutation into the
    caller's netlist.
    """
    fn = _shipped_function("congestion", "_get_pin_positions")
    body = ast.unparse(fn)

    assert "pin_world_position_at" in body, (
        "_get_pin_positions no longer calls pin_world_position_at -- the D1 "
        "repair has been reverted or restructured; re-derive D1 before "
        "trusting this test"
    )
    assert "pos_override" in body, "the positions array is no longer threaded through an override"
    # the wrong fix: mutating the component to make the stale read come out
    # right.  `positions` is the caller's candidate, not a commit.
    assert not any(
        isinstance(node, ast.Attribute)
        and node.attr == "initial_position"
        and isinstance(node.ctx, ast.Store)
        for node in ast.walk(fn)
    ), "_get_pin_positions assigns to comp.initial_position -- that mutates the caller's netlist"

    # --- behavioural half -------------------------------------------------
    design = next(d for d in ANALYZE_DESIGNS if d["label"] == "two_pin_net")
    netlist = build_netlist(design["components"], design["nets"])
    moved = np.array([[999.0, 999.0], [-999.0, -999.0]], dtype=np.float64)

    without = ORACLE._get_pin_positions(netlist, "N1", None)
    with_positions = ORACLE._get_pin_positions(netlist, "N1", moved)

    assert without == [(1.0, 1.0), (6.0, 5.0)], (
        f"the positions=None baseline moved: {without!r} -- the corpus row "
        "changed and the D1 measurement below no longer means what it says"
    )
    assert with_positions == [(999.0, 999.0), (-999.0, -999.0)], (
        f"positions= is not being honoured: {with_positions!r}"
    )
    assert sig(without) != sig(with_positions)

    board = build_board(*design["board"])
    a = ORACLE.analyze_congestion(netlist, board)
    b = ORACLE.analyze_congestion(netlist, board, positions=moved)
    assert sig(a.grid.demand) != sig(b.grid.demand), (
        "analyze_congestion still produces identical demand with and without a "
        "positions array that moves every component 999 mm -- D1 is back"
    )
    assert float(a.grid.demand.sum()) == 30.0
    assert float(b.grid.demand.sum()) == 100.0

    # ... and passing the components' own positions back in is a no-op, which
    # is what says the override is a genuine substitution rather than a
    # scale/offset applied on top of initial_position.
    same = np.array([c.initial_position for c in netlist.components], dtype=np.float64)
    assert sig(ORACLE._get_pin_positions(netlist, "N1", same)) == sig(without)


def test_repaired_d2_layer_assignments_path_is_reachable():
    """D2, REPAIRED by #760 (``aebaecd99``): the multi-layer branch now runs.

    **Was:** ``from temper_placer.routing.layer_assignment import Layer`` in
    two places inside ``analyze_congestion``.  There is no
    ``temper_placer.routing`` package -- the tree is ``temper_placer.router_v6``
    -- so every call with ``layer_assignments is not None`` raised
    ``ModuleNotFoundError`` before computing anything.  The entire multi-layer
    branch was unreachable in production, and the old pin asserted that as
    *error parity*.

    **Now:** both imports read ``temper_placer.router_v6.layer_assignment``.

    Inverted, not deleted: this fails if the dead ``temper_placer.routing``
    path comes back in either location, and also if someone "fixes" it by
    wrapping the import in ``try/except ImportError`` -- which would stop the
    raise while leaving the branch just as unreachable, and is exactly the
    shape a reviewer would wave through.
    """
    fn = _shipped_function("congestion", "analyze_congestion")
    imports = [
        ".".join(filter(None, (node.module, alias.name)))
        for node in ast.walk(fn)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    ]
    assert imports, "analyze_congestion no longer has function-local imports at all"
    assert all(i == "temper_placer.router_v6.layer_assignment.Layer" for i in imports), (
        f"analyze_congestion imports something other than the repaired path: {imports}"
    )
    # the wrong fix: silence the raise, keep the branch dead.
    assert not any(
        isinstance(node, ast.Try)
        and any(isinstance(h.type, ast.Name) and "Error" in h.type.id for h in node.handlers)
        for node in ast.walk(fn)
    ), (
        "analyze_congestion swallows an import error -- that suppresses D2's "
        "symptom without making the multi-layer branch reachable"
    )

    # --- behavioural half -------------------------------------------------
    from temper_placer.router_v6.layer_assignment import Layer, LayerAssignment

    design = next(d for d in ANALYZE_DESIGNS if d["label"] == "two_pin_net")
    netlist = build_netlist(design["components"], design["nets"])
    board = build_board(*design["board"])

    # an empty mapping used to raise; it now returns a result
    empty = ORACLE.analyze_congestion(netlist, board, layer_assignments={})
    assert isinstance(empty, ORACLE.CongestionResult)
    assert empty.grid.num_layers == 1

    def _assign(net: str, layer: Layer) -> LayerAssignment:
        return LayerAssignment(
            net=net, primary_layer=layer, allowed_layers=[layer], vias_required=0, reason="test"
        )

    # ... and a mapping that genuinely spans two layers promotes num_layers,
    # i.e. the code the ModuleNotFoundError used to hide actually executes.
    mixed = ORACLE.analyze_congestion(
        netlist,
        board,
        layer_assignments={"N1": _assign("N1", Layer.L1_TOP), "N2": _assign("N2", Layer.L4_BOT)},
    )
    assert mixed.grid.num_layers == 2, "the L1_TOP/L4_BOT promotion did not fire"
    assert mixed.grid.demand.shape == (2, 10, 10)

    # a single-layer mapping must NOT promote -- otherwise "num_layers == 2"
    # above would be true for any non-empty mapping and prove nothing.
    single = ORACLE.analyze_congestion(
        netlist, board, layer_assignments={"N1": _assign("N1", Layer.L1_TOP)}
    )
    assert single.grid.num_layers == 1
    assert single.grid.demand.shape == (10, 10)


def test_repaired_d3_offboard_net_contributes_nothing():
    """D3, REPAIRED by #760 (``aebaecd99``): off-board nets add no demand.

    **Was:** ``estimate_net_demand`` clamped ``col_min`` from below and
    ``col_max`` from above -- each bound from one side only.  A net entirely
    left of the board left ``col_max`` negative, so
    ``demand[row_min:row_max + 1, col_min:col_max + 1]`` became a
    *negative-index* slice.  Measured on a 10x10 grid with a net at
    x, y in [-5, -4]: **49** cells written at the board ORIGIN where the
    answer is zero.  The far edge was right by accident (``col_min = 50``,
    ``col_max = 9`` is an empty ``[50:10]`` slice), and that asymmetry is what
    made the near edge visible at all.

    **Now:** ``if col_max < col_min or row_max < row_min: return grid``.

    Inverted, not deleted.  The interesting failure this still catches is not
    the original defect but the over-broad fix: a guard written as
    ``if col_max < 0 or row_max < 0`` (or one that rejects any net with a
    negative coordinate) also makes the 49 cells go away, and additionally
    drops the *straddling* net that legitimately contributes 9 cells.  So the
    straddling case is asserted alongside.
    """
    fn = _shipped_function("congestion", "estimate_net_demand")
    guards = [
        ast.unparse(node.test)
        for node in ast.walk(fn)
        if isinstance(node, ast.If)
        and any(isinstance(s, ast.Return) for s in node.body)
        and "col_max" in ast.unparse(node.test)
    ]
    assert guards, (
        "estimate_net_demand has no early-return guard mentioning col_max -- "
        "the D3 repair has been reverted; re-derive D3 before trusting this test"
    )
    assert any("col_min" in g and "row_min" in g for g in guards), (
        f"the D3 guard compares col_max against a constant rather than against "
        f"col_min/row_min: {guards} -- that also rejects legitimate nets whose "
        "bounding box straddles the low edge"
    )

    # --- behavioural half -------------------------------------------------
    grid = ORACLE.CongestionGrid.from_board(build_board(10.0, 10.0), cell_size_mm=1.0)

    near = ORACLE.estimate_net_demand(grid, [(-5.0, -5.0), (-4.0, -4.0)], demand_per_cell=1.0)
    assert int((near.demand > 0.0).sum()) == 0, (
        "an off-board net still writes demand at the origin -- D3's negative-index slice is back"
    )
    assert near is grid, "the guard should return the input grid, not a copy"

    # the far edge used to be right by accident, via an empty slice on a fresh
    # copy; it is now right on purpose, by the same identity return.
    far = ORACLE.estimate_net_demand(grid, [(50.0, 50.0), (60.0, 60.0)], demand_per_cell=1.0)
    assert int((far.demand > 0.0).sum()) == 0
    assert far is grid

    # ... and the guard is not over-broad: a net straddling the low boundary
    # still contributes its on-board part.  This is the assertion that fails
    # for a `col_max < 0`-style fix.
    straddling = ORACLE.estimate_net_demand(grid, [(-3.0, -3.0), (2.0, 2.0)], demand_per_cell=1.0)
    written = straddling.demand > 0.0
    assert int(written.sum()) == 9, f"straddling net wrote {int(written.sum())} cells, expected 9"
    assert written[0, 0]
    assert written[2, 2]
    assert not written[3, 3]


# ---------------------------------------------------------------------------
# congestion_analysis.py
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", ROUTING_RESULT_CASES, ids=lambda c: c[0])
@pytest.mark.parametrize("use_segments", [False, True])
def test_identify_congested_regions_bit_exact(case, use_segments):
    label, bw, bh, gs, failed, routes = case

    def _oracle():
        cm = ORACLE.identify_congested_regions(
            build_routing_results(failed, routes, use_segments), bw, bh, gs
        )
        return [
            (r.center, r.radius, r.severity.value, r.failed_net_count, r.bottleneck_score)
            for r in cm.regions
        ]

    _assert_same(
        f"identify_congested_regions[{label}, segments={use_segments}]",
        _oracle,
        "congestion_identify_regions_py",
        lambda fn: fn(failed, routes, bw, bh, gs, use_segments),
    )


@pytest.mark.parametrize(
    "score,failed",
    [
        (0.0, 0),
        (1.0, 0),  # exactly 1.0 -> NONE (the test is strict >)
        (math.nextafter(1.0, 2.0), 0),  # -> LOW
        (3.0, 0),
        (math.nextafter(3.0, 4.0), 0),  # -> MEDIUM
        (5.0, 0),
        (math.nextafter(5.0, 6.0), 0),  # -> HIGH
        (1e9, 0),
        (-1.0, 0),
        (float("nan"), 0),  # every `>` is False -> NONE
        (float("inf"), 0),
        (0.0, 1),  # failed >= 1 -> HIGH, whatever the score
        (0.0, 2),
        (0.0, 3),  # failed >= 3 -> CRITICAL
        (1e9, 3),
        (0.0, -1),  # negative counts fall through to the score branch
    ],
)
def test_classify_congestion_bit_exact(score, failed):
    _assert_same(
        f"_classify_congestion({score}, {failed})",
        lambda: ORACLE._classify_congestion(score, failed).value,
        "congestion_classify_severity_py",
        lambda fn: fn(score, failed),
    )


# ---------------------------------------------------------------------------
# routing_demand.py
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", DEMAND_PCBS, ids=lambda c: c[0])
@pytest.mark.parametrize("as_dict", [False, True])
def test_estimate_routing_demand_bit_exact(case, as_dict):
    label, components, net_names = case

    def _oracle():
        d = ORACLE.estimate_routing_demand(build_parsed_pcb(components, net_names, as_dict))
        return (
            d.total_nets,
            d.routable_nets,
            d.total_pins,
            d.signal_nets,
            d.power_nets,
            d.diff_pair_nets,
            d.avg_pins_per_net,
            d.max_pins_per_net,
            d.routing_complexity,
        )

    _assert_same(
        f"estimate_routing_demand[{label}, dict={as_dict}]",
        _oracle,
        "routing_demand_estimate_py",
        lambda fn: fn(components, net_names, as_dict),
    )


@pytest.mark.parametrize(
    "avg,routable",
    [
        (0.0, 0),  # the early 0.0 return
        (2.0, 1),
        (10.0, 100),  # exactly 1.0 before the min()
        (10.0, 101),  # min() clamps
        (1e9, 1),
        (float("nan"), 1),  # min(1.0, NaN) -> 1.0 (NaN is the SECOND argument)
        (float("inf"), 1),
        (-5.0, 3),  # negative complexity is NOT clamped from below
        (5e-324, 1),  # denormal band
    ],
)
def test_routing_complexity_bit_exact(avg, routable):
    _assert_same(
        f"routing_complexity(avg={avg}, routable={routable})",
        lambda: ORACLE.RoutingDemand(
            total_nets=routable,
            routable_nets=routable,
            total_pins=0,
            signal_nets=0,
            power_nets=0,
            diff_pair_nets=0,
            avg_pins_per_net=avg,
            max_pins_per_net=0,
        ).routing_complexity,
        "routing_demand_complexity_py",
        lambda fn: fn(avg, routable),
    )


# ---------------------------------------------------------------------------
# placement_suggestions.py
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", SUGGESTION_REGIONS)
def test_generate_placement_suggestions_bit_exact(case):
    def _oracle():
        cm = ORACLE.CongestionMap(regions=[_region(case)])
        out = ORACLE.generate_placement_suggestions(cm, dict(SUGGESTION_POSITIONS))
        return [
            (s.component_id, s.current_position, s.suggested_position, s.reason, s.priority)
            for s in out.suggestions
        ]

    _assert_same(
        f"generate_placement_suggestions{case}",
        _oracle,
        "placement_suggestions_generate_py",
        lambda fn: fn(case, dict(SUGGESTION_POSITIONS)),
    )


def test_generate_placement_suggestions_with_no_positions():
    """``component_positions=None`` -> the ``{}`` default -> no suggestions."""
    cm = ORACLE.CongestionMap(regions=[_region(SUGGESTION_REGIONS[4])])
    _assert_same(
        "generate_placement_suggestions(no positions)",
        lambda: ORACLE.generate_placement_suggestions(cm, None).suggestions,
        "placement_suggestions_generate_py",
        lambda fn: fn(SUGGESTION_REGIONS[4], None),
    )


def test_generate_placement_suggestions_over_many_regions():
    """Several regions at once: the suggestion list's ORDER is the contract."""
    cm = ORACLE.CongestionMap(regions=[_region(c) for c in SUGGESTION_REGIONS])
    _assert_same(
        "generate_placement_suggestions(all regions)",
        # Signs the SAME 5-tuple as test_generate_placement_suggestions_bit_exact.
        # `current_position` was missing here and nowhere else; because `sig()`
        # is arity-carrying, that made the two call sites demand different
        # return shapes from one Rust function.  It is also the only check that
        # a suggestion carries the position it was computed FROM once more than
        # one region contributes, which is exactly what this test is for.
        lambda: [
            (
                s.component_id,
                s.current_position,
                s.suggested_position,
                s.reason,
                s.priority,
            )
            for s in ORACLE.generate_placement_suggestions(
                cm, dict(SUGGESTION_POSITIONS)
            ).suggestions
        ],
        "placement_suggestions_generate_py",
        lambda fn: fn(list(SUGGESTION_REGIONS), dict(SUGGESTION_POSITIONS)),
    )


@pytest.mark.parametrize("case", SUGGESTION_REGIONS)
def test_find_affected_components_bit_exact(case):
    region = _region(case)
    _assert_same(
        f"_find_affected_components{case}",
        lambda: ORACLE._find_affected_components(region, dict(SUGGESTION_POSITIONS)),
        "placement_find_affected_py",
        lambda fn: fn(case, dict(SUGGESTION_POSITIONS)),
    )


@pytest.mark.parametrize("pos_name,pos", sorted(SUGGESTION_POSITIONS.items()))
@pytest.mark.parametrize("severity", ["critical", "high", "medium", "low", "none", "UNKNOWN"])
def test_calculate_suggested_position_bit_exact(pos_name, pos, severity):
    _assert_same(
        f"_calculate_suggested_position({pos_name}, {severity})",
        lambda: ORACLE._calculate_suggested_position(pos, (50.0, 50.0), severity),
        "placement_suggested_position_py",
        lambda fn: fn(pos, (50.0, 50.0), severity),
    )


# ---------------------------------------------------------------------------
# congestion_heatmap.py
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", HEATMAP_ROUTERS, ids=lambda c: c[0])
def test_heatmap_from_router_bit_exact(case):
    def _oracle():
        hm = ORACLE.CongestionHeatmap.from_router(build_router_stub(case))
        return (hm.grid, hm.cell_size, hm.origin)

    _assert_same(
        f"from_router[{case[0]}]",
        _oracle,
        "congestion_heatmap_from_router_py",
        lambda fn: fn(*case[1:]),
    )


@pytest.mark.parametrize("case", HEATMAP_ROUTERS, ids=lambda c: c[0])
def test_heatmap_total_congestion_bit_exact(case):
    _assert_same(
        f"get_total_congestion[{case[0]}]",
        lambda: ORACLE.CongestionHeatmap.from_router(
            build_router_stub(case)
        ).get_total_congestion(),
        "congestion_heatmap_total_py",
        lambda fn: fn(*case[1:]),
    )


@pytest.mark.parametrize("case", HEATMAP_ROUTERS, ids=lambda c: c[0])
@pytest.mark.parametrize("query", HEATMAP_QUERIES)
def test_heatmap_congestion_at_bit_exact(case, query):
    x, y = query
    _assert_same(
        f"get_congestion_at[{case[0]}]{query}",
        lambda: ORACLE.CongestionHeatmap.from_router(build_router_stub(case)).get_congestion_at(
            x, y
        ),
        "congestion_heatmap_at_py",
        lambda fn: fn(case[1:], x, y),
    )


@pytest.mark.parametrize("case", HEATMAP_ROUTERS, ids=lambda c: c[0])
@pytest.mark.parametrize("threshold,max_count", HOTSPOT_THRESHOLDS)
def test_heatmap_hotspots_bit_exact(case, threshold, max_count):
    _assert_same(
        f"get_hotspots[{case[0]}](t={threshold}, n={max_count})",
        lambda: ORACLE.CongestionHeatmap.from_router(build_router_stub(case)).get_hotspots(
            threshold, max_count
        ),
        "congestion_heatmap_hotspots_py",
        lambda fn: fn(case[1:], threshold, max_count),
    )


# ---------------------------------------------------------------------------
# apply_suggestions.py
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("damping,threshold", DAMPING_CASES)
def test_apply_suggestions_with_damping_bit_exact(damping, threshold):
    def _oracle():
        cm = ORACLE.CongestionMap(regions=[_region(c) for c in SUGGESTION_REGIONS])
        suggestions = ORACLE.generate_placement_suggestions(cm, dict(SUGGESTION_POSITIONS))
        out = ORACLE.apply_suggestions_with_damping(
            suggestions, dict(SUGGESTION_POSITIONS), damping, threshold
        )
        return (
            [
                (
                    a.component_id,
                    a.original_position,
                    a.suggested_position,
                    a.applied_position,
                    a.damping_factor,
                )
                for a in out.adjustments
            ],
            out.adjustment_count,
            out.total_movement,
        )

    _assert_same(
        f"apply_suggestions_with_damping(damping={damping}, threshold={threshold})",
        _oracle,
        "apply_suggestions_damped_py",
        lambda fn: fn(list(SUGGESTION_REGIONS), dict(SUGGESTION_POSITIONS), damping, threshold),
    )


def test_apply_suggestions_with_missing_component():
    """A suggestion whose component is absent from ``current_positions``
    is skipped by the ``if current_pos is None: continue`` guard."""
    cm = ORACLE.CongestionMap(regions=[_region(c) for c in SUGGESTION_REGIONS])
    suggestions = ORACLE.generate_placement_suggestions(cm, dict(SUGGESTION_POSITIONS))
    partial = {"NEAR": SUGGESTION_POSITIONS["NEAR"]}
    def _oracle():
        # Signs the SAME 3-tuple as test_apply_suggestions_with_damping_bit_exact.
        # The id-only projection signed strictly less than its sibling, and
        # `sig()` is arity-carrying, so the two call sites demanded different
        # return shapes from one Rust function -- undispatchable here, because
        # they differ ONLY in the size of the positions dict (12 vs 1).
        # It also could not see `total_movement`, which is where the
        # `(dx ** 2 + dy ** 2) ** 0.5` libm-`pow` trap actually bites.  The
        # `if current_pos is None: continue` guard this test exists for stays
        # fully visible in the adjustment list.
        out = ORACLE.apply_suggestions_with_damping(suggestions, partial, 0.5, 0.5)
        return (
            [
                (
                    a.component_id,
                    a.original_position,
                    a.suggested_position,
                    a.applied_position,
                    a.damping_factor,
                )
                for a in out.adjustments
            ],
            out.adjustment_count,
            out.total_movement,
        )

    _assert_same(
        "apply_suggestions_with_damping(partial positions)",
        _oracle,
        "apply_suggestions_damped_py",
        lambda fn: fn(list(SUGGESTION_REGIONS), partial, 0.5, 0.5),
    )


@pytest.mark.parametrize(
    "current,suggested,damping",
    [
        ((0.0, 0.0), (10.0, 10.0), 0.0),
        ((0.0, 0.0), (10.0, 10.0), 0.5),
        ((0.0, 0.0), (10.0, 10.0), 1.0),
        ((0.0, 0.0), (10.0, 10.0), 2.0),
        ((0.0, 0.0), (10.0, 10.0), -1.0),
        ((1e16, 0.0), (1e16 + 2.0, 0.0), 0.5),  # catastrophic cancellation
        ((0.0, 0.0), (float("inf"), 0.0), 0.0),  # inf * 0.0 -> NaN
        ((float("nan"), 0.0), (1.0, 1.0), 0.5),
        ((-0.0, -0.0), (0.0, 0.0), 0.5),
        ((0.0, 0.0), (5e-324, 5e-324), 0.5),  # denormal band
    ],
)
def test_calculate_damped_position_bit_exact(current, suggested, damping):
    _assert_same(
        f"_calculate_damped_position({current}, {suggested}, {damping})",
        lambda: ORACLE._calculate_damped_position(current, suggested, damping),
        "apply_damped_position_py",
        lambda fn: fn(current, suggested, damping),
    )


@pytest.mark.parametrize(
    "moves",
    [
        [],
        [((0.0, 0.0), (3.0, 4.0))],
        [((0.0, 0.0), (3.0, 4.0)), ((0.0, 0.0), (5.0, 12.0))],
        [((0.0, 0.0), (0.1, 0.2))] * 100,  # accumulation ORDER matters (B7)
        [((0.0, 0.0), (float("nan"), 0.0))],
        [((0.0, 0.0), (float("inf"), 0.0)), ((0.0, 0.0), (1.0, 1.0))],
        [((0.0, 0.0), (1e200, 1e200))],  # (dx**2 + dy**2) overflows
        [((0.0, 0.0), (5e-324, 5e-324))],
    ],
)
def test_total_movement_bit_exact(moves):
    def _oracle():
        adjustments = [
            ORACLE.AppliedAdjustment(
                component_id=f"C{i}",
                original_position=o,
                suggested_position=a,
                applied_position=a,
                damping_factor=1.0,
            )
            for i, (o, a) in enumerate(moves)
        ]
        return ORACLE.AdjustmentResult(adjustments=adjustments).total_movement

    _assert_same(
        f"total_movement({len(moves)} moves)",
        _oracle,
        "apply_total_movement_py",
        lambda fn: fn(moves),
    )


@pytest.mark.parametrize(
    "positions,applied",
    [
        ({}, []),
        ({"A": (1.0, 1.0)}, []),
        ({"A": (1.0, 1.0)}, [("A", (2.0, 2.0))]),
        ({"A": (1.0, 1.0)}, [("B", (2.0, 2.0))]),  # a key not in the input
        ({"A": (1.0, 1.0)}, [("A", (2.0, 2.0)), ("A", (3.0, 3.0))]),  # last write wins
        ({"A": (1.0, 1.0), "B": (0.0, 0.0)}, [("B", (9.0, 9.0))]),
    ],
)
def test_update_component_positions_bit_exact(positions, applied):
    def _oracle():
        result = ORACLE.AdjustmentResult(
            adjustments=[
                ORACLE.AppliedAdjustment(
                    component_id=cid,
                    original_position=(0.0, 0.0),
                    suggested_position=pos,
                    applied_position=pos,
                    damping_factor=1.0,
                )
                for cid, pos in applied
            ]
        )
        updated = ORACLE.update_component_positions(dict(positions), result)
        # dict ITERATION ORDER is part of the value -- sig() does not sort it
        return updated

    _assert_same(
        f"update_component_positions({positions}, {applied})",
        _oracle,
        "apply_update_positions_py",
        lambda fn: fn(dict(positions), applied),
    )


# ---------------------------------------------------------------------------
# Traps: measured, in this file, so the numbers in the oracle header are
# reproducible rather than asserted from memory.
# ---------------------------------------------------------------------------


def test_trap_three_way_max_semantics():
    """numpy, CPython and Rust disagree three ways on ``max`` with NaN.

    B12 in the catalog.  The cluster uses the first two -- ``np.maximum`` in
    ``get_utilization``/``get_overflow``, the builtin in ``overflow_ratio``
    and ``identify_congested_regions`` -- so a Rust mirror that reaches for
    ``f64::max`` is wrong at *both* sites, in two different directions.
    """
    nan = float("nan")

    # numpy: propagates from either operand
    assert math.isnan(float(np.maximum(nan, 1.0)))
    assert math.isnan(float(np.maximum(1.0, nan)))

    # CPython builtin: keeps the FIRST argument
    assert math.isnan(max(nan, 1.0))
    assert max(1.0, nan) == 1.0
    assert min(nan, 1.0) != min(1.0, nan) or math.isnan(min(nan, 1.0))

    # ... and the same asymmetry decides two of this cluster's results in
    # opposite directions:
    #   overflow_ratio   -> min(NaN, 1.0) -> NaN
    #   bottleneck_score -> min(1.0, NaN) -> 1.0
    assert math.isnan(min(nan, 1.0))
    assert min(1.0, nan * 1.2) == 1.0

    # signed zeros: max returns the FIRST argument when they compare equal
    assert math.copysign(1.0, max(0.0, -0.0)) == 1.0
    assert math.copysign(1.0, max(-0.0, 0.0)) == -1.0


def test_trap_np_sum_is_not_a_left_fold():
    """``np.sum`` is a pairwise reduction; ``iter().sum()`` is not (B7).

    ``get_total_congestion`` is ``float(np.sum(self.grid))``.  A Rust mirror
    spelled ``grid.iter().sum::<f32>()`` accumulates left to right and
    diverges in the last bits.

    **Honestly bounded.**  numpy's pairwise reduction only splits above its
    128-element blocking threshold, and *below* it numpy still unrolls by 8,
    which is itself not a left fold -- but on a small, smooth grid the two
    can coincide.  So the divergence is asserted on a grid large enough for
    the mechanism to be forced (``512`` f32 cells, built here), and the
    corpus's own grids are *measured and reported* rather than asserted:
    they are 3x3 to 5x5, which is why they are not the right witness.
    """
    rng = random.Random(19)
    values = np.array([rng.uniform(0.0, 1.0) for _ in range(512)], dtype=np.float32)
    left_fold = np.float32(0.0)
    for v in values:
        left_fold = np.float32(left_fold + v)
    assert float(np.sum(values)) != float(left_fold), (
        "np.sum agreed with a left fold over 512 random f32 cells -- either "
        "numpy changed its reduction or this witness stopped discriminating"
    )

    # ... and the same construction over the corpus, reported not asserted.
    corpus_checked = 0
    for case in HEATMAP_ROUTERS:
        hm = ORACLE.CongestionHeatmap.from_router(build_router_stub(case))
        if np.isfinite(hm.grid).all():
            corpus_checked += 1
    assert corpus_checked >= 3, "the corpus no longer has finite heatmap grids"


def test_trap_pow_form_is_not_hypot_or_sqrt():
    """``(dx**2 + dy**2) ** 0.5`` is three distinct spellings of a distance.

    B7.  Used by ``_find_affected_components``,
    ``_calculate_suggested_position`` and ``AdjustmentResult.total_movement``.
    """
    rng = random.Random(7)
    n = 20000
    vs_hypot = 0
    vs_sqrt = 0
    for _ in range(n):
        dx = rng.uniform(-1e3, 1e3)
        dy = rng.uniform(-1e3, 1e3)
        pow_form = (dx**2 + dy**2) ** 0.5
        if pow_form != math.hypot(dx, dy):
            vs_hypot += 1
        if pow_form != math.sqrt(dx * dx + dy * dy):
            vs_sqrt += 1
    assert vs_hypot / n > 0.10, f"pow-form vs hypot disagreed on only {vs_hypot}/{n}"
    assert vs_sqrt > 0, "pow-form vs sqrt(x*x + y*y) agreed everywhere"


def test_trap_format_2f_is_round_half_even():
    """``f"{x:.2f}"`` rounds the exact binary value half-to-EVEN (B3).

    ``generate_placement_suggestions`` embeds this in ``reason``, a compared
    field.  A Rust mirror spelled ``(x * 100.0).round() / 100.0`` produces
    ``0.13`` where CPython produces ``0.12``, because ``f64::round`` is
    half-away-from-zero while both ``format`` and CPython's ``round`` are
    half-to-even.
    """
    assert f"{0.125:.2f}" == "0.12"
    assert f"{0.135:.2f}" == "0.14"
    assert f"{2.675:.2f}" == "2.67"
    assert f"{0.005:.2f}" == "0.01"
    assert f"{0.015:.2f}" == "0.01"

    def _rust_round(x: float) -> float:
        """``f64::round`` -- half away from zero, per the Rust reference."""
        return math.floor(x + 0.5) if x >= 0.0 else math.ceil(x - 0.5)

    # The naive Rust construction disagrees with the format spec on exactly
    # those exactly-representable .xx5 values whose lower neighbour is EVEN
    # (12.5 -> 12 half-even vs 13 half-away; 37.5 -> 38 either way).
    disagreements = [
        v
        for v in (0.125, 0.375, 0.625, 0.875)
        if _rust_round(v * 100.0) / 100.0 != float(f"{v:.2f}")
    ]
    assert disagreements == [0.125, 0.625], (
        f"expected 0.125 and 0.625 to diverge and 0.375/0.875 not to, got {disagreements}"
    )
    # CPython's own `round` agrees with `format` (both half-to-even), which is
    # why grepping for `round(` does NOT find this class -- the divergence is
    # entirely on the Rust side.
    assert round(0.125 * 100.0) / 100.0 == float(f"{0.125:.2f}")


def test_trap_hotspot_tuples_leak_float32():
    """``get_hotspots`` mixes ``float`` with ``numpy.float32`` in one tuple.

    ``==`` cannot see the difference; ``sig()`` records the concrete type
    name at every leaf, which is why the differential compares signatures
    rather than values.
    """
    case = next(c for c in HEATMAP_ROUTERS if c[0] == "ramp")
    hm = ORACLE.CongestionHeatmap.from_router(build_router_stub(case))
    spots = hm.get_hotspots(threshold=0.0, max_count=3)
    assert spots, "the corpus's 'ramp' case no longer produces hotspots"
    x, y, val = spots[0]
    assert type(x) is float
    assert type(y) is float
    assert type(val) is np.float32
    # the discrimination the differential relies on
    assert sig(val) != sig(float(val))
    assert val == float(val)  # ... while `==` says they are the same
