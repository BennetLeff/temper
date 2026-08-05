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
  ``15110feccc6ec9389f0777d3cff1ce9f81b11068`` (``origin/main``).
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

Defects pinned, not fixed
-------------------------
D1 ``positions=`` is ignored, D2 ``layer_assignments=`` raises
``ModuleNotFoundError``, D3 an off-board net writes a 7x7 block at the
origin.  Each has a named test.  See the oracle header for the full write-up.
"""

from __future__ import annotations

import ast
import math
import random
import subprocess

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

_ORACLE_PIN_SHA = "15110feccc6ec9389f0777d3cff1ce9f81b11068"
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
        lambda fn: fn(overflows, n),
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
        _assert_same(
            f"random bbox seed={seed} pins={pins}",
            lambda p=pins: ORACLE.estimate_net_demand(
                ORACLE.CongestionGrid.from_board(build_board(10.0, 10.0), cell_size_mm=1.0), p
            ).demand,
            "congestion_estimate_net_demand_py",
            lambda fn, p=pins: fn(10.0, 10.0, 1.0, (0.0, 0.0), p, 0, 1.0, 1),
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
# congestion.py -- the three pinned defects
# ---------------------------------------------------------------------------


def test_d1_positions_argument_is_ignored():
    """DEFECT D1, pinned: ``positions=`` has no effect on the result.

    ``_get_pin_positions`` reads ``positions`` into ``comp_x, comp_y`` and
    then never uses them -- the appended coordinate comes from
    ``pin_world_position(pin, comp)``.  The placement feedback loop is
    therefore blind to the positions it is meant to be evaluating.

    REPORTED, NOT FIXED: a fix would break the verbatim pin.  The Rust arm
    must reproduce this, and this test is where the decision to change it
    will surface.
    """
    design = next(d for d in ANALYZE_DESIGNS if d["label"] == "two_pin_net")
    netlist = build_netlist(design["components"], design["nets"])
    moved = np.array([[999.0, 999.0], [-999.0, -999.0]], dtype=np.float64)

    without = ORACLE._get_pin_positions(netlist, "N1", None)
    with_positions = ORACLE._get_pin_positions(netlist, "N1", moved)

    assert sig(without) == sig(with_positions), (
        "D1 appears to have been fixed in the oracle -- the oracle must stay "
        "verbatim; fix the production module and re-pin instead"
    )

    board = build_board(*design["board"])
    a = ORACLE.analyze_congestion(netlist, board)
    b = ORACLE.analyze_congestion(netlist, board, positions=moved)
    assert sig(a.grid.demand) == sig(b.grid.demand)
    assert sig(a.max_utilization) == sig(b.max_utilization)


def test_d2_layer_assignments_raises_module_not_found():
    """DEFECT D2, pinned as error parity.

    ``analyze_congestion`` imports ``temper_placer.routing.layer_assignment``,
    a package that does not exist (the tree is ``temper_placer.router_v6``),
    so every call with ``layer_assignments is not None`` raises before doing
    any work.  The multi-layer branch is unreachable in production.

    The Rust arm must raise the same type with the same message until someone
    fixes the import -- which is what this assertion says out loud.
    """
    design = next(d for d in ANALYZE_DESIGNS if d["label"] == "two_pin_net")
    netlist = build_netlist(design["components"], design["nets"])
    board = build_board(*design["board"])

    with pytest.raises(ModuleNotFoundError) as excinfo:
        ORACLE.analyze_congestion(netlist, board, layer_assignments={})
    assert excinfo.value.name == "temper_placer.routing"

    # ... and with a non-empty mapping, i.e. the branch is not reached at all
    with pytest.raises(ModuleNotFoundError):
        ORACLE.analyze_congestion(netlist, board, layer_assignments={"N1": object()})

    # `None` is the only value that works
    ORACLE.analyze_congestion(netlist, board, layer_assignments=None)


def test_d3_offboard_net_writes_negative_slice():
    """DEFECT D3, pinned: an off-board net adds demand at the ORIGIN.

    ``col_max = min(width_cells - 1, int(...))`` clamps only from above, so a
    net entirely left of / below the board leaves ``col_max`` negative and
    ``demand[row_min:row_max + 1, col_min:col_max + 1]`` becomes a
    negative-index slice.  Measured on a 10x10 grid with a net at
    x, y in [-5, -4]: **49** cells written, at the board origin, where the
    correct answer is zero.

    The asymmetry is the tell.  A net off the FAR edge produces
    ``col_min = 50``, ``col_max = 9`` -- an empty ``[50:10]`` slice, i.e. the
    right answer by accident.  Only the near edge goes negative, and only the
    near edge is wrong.
    """
    grid = ORACLE.CongestionGrid.from_board(build_board(10.0, 10.0), cell_size_mm=1.0)
    out = ORACLE.estimate_net_demand(grid, [(-5.0, -5.0), (-4.0, -4.0)], demand_per_cell=1.0)

    written = out.demand > 0.0
    assert int(written.sum()) == 49, "D3 appears to have changed -- re-pin the oracle"
    # ... and it is the ORIGIN block, not the far corner
    assert written[0, 0]
    assert written[6, 6]
    assert not written[7, 7]

    # the far-side equivalent produces an empty slice and writes nothing
    far = ORACLE.estimate_net_demand(grid, [(50.0, 50.0), (60.0, 60.0)], demand_per_cell=1.0)
    assert int((far.demand > 0.0).sum()) == 0


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
        lambda: [
            (s.component_id, s.suggested_position, s.reason, s.priority)
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
    _assert_same(
        "apply_suggestions_with_damping(partial positions)",
        lambda: [
            a.component_id
            for a in ORACLE.apply_suggestions_with_damping(
                suggestions, partial, 0.5, 0.5
            ).adjustments
        ],
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
