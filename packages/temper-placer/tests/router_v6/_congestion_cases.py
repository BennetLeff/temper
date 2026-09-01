"""Shared input corpus for the Wave-4 **cluster E** gates (congestion & feedback).

**One fixture module, three consumers**: the differential suite (R1a), the
property/metamorphic suite (R1c/R1d), and the ``benchmarks/perf_ab.py`` arms
(R1b) that Phase B will add all draw their inputs from here.

That is deliberate and structural, not stylistic.  PR #714 passed its
differential at iterations ``[0, 1, 2, 8, 17, 100]`` and then failed CI on a
benchmark that ran 120 -- the benchmark exercised a parameter the behavioural
gate had never reached.  Sharing the corpus makes that class of gap
impossible to reintroduce: every tuple the benchmark times is, by
construction, a tuple the differential has already compared bit-for-bit.
``test_bench_corpus_is_covered_by_differential`` in
``test_congestion_rust_differential.py`` asserts the containment explicitly
(``BENCH_* <= the full list`` as a set), so the property survives future
edits to either side.

The corpus is a *fixed* list, not a live random draw, so the perf A/B ratio
is comparable across runs and machines.  The randomized sweeps in the
differential are additional coverage layered on top, never a replacement.

**Nothing here imports the code under test.**  It is pure data -- plain
tuples, lists and dicts -- so the oracle arm and the (future) Rust arm can
each build their own object types from it.  ``_build.py``-style helpers that
*would* need ``Netlist``/``Board`` live in the test modules, not here.

Coverage intent per named list
-------------------------------
``BOARD_GRIDS``              ``CongestionGrid.from_board`` sizing: the
                             ``math.ceil`` boundary, a zero-width board (which
                             yields a ``(1, 0)`` array), a width one ulp over
                             an exact multiple of the cell size, and the
                             ``inf`` width that raises ``OverflowError``.
``DEMAND_SUPPLY_PAIRS``      ``get_utilization`` / ``get_overflow``: the
                             ``np.maximum(supply, 1e-6)`` floor exactly, NaN
                             in each operand independently (B12), +-inf,
                             signed zeros, and the denormal band (B8).
``NET_BBOXES``               ``estimate_net_demand``: fewer than two pins,
                             both pins in one cell, a net spanning the whole
                             board, a net entirely off-board on each side
                             (the site of defect D3's negative-index slice,
                             repaired by #760 -- both sides now contribute
                             nothing), a net straddling the boundary, and a
                             NaN coordinate (which raises ``ValueError``).
``ANALYZE_DESIGNS``          ``analyze_congestion`` end to end: empty netlist,
                             single one-pin net, two overlapping nets, a net
                             whose components are missing from the netlist,
                             and the ``capacity_per_cell`` values that put the
                             overflow mask on either side of zero.
``ROUTING_RESULT_CASES``     ``identify_congested_regions``: no failed nets,
                             1 / 2 / 3 failed nets (the ``>= 3`` and ``>= 1``
                             severity cliffs), route coordinates landing on
                             each of the ``> 0.5`` / ``> 1.0`` / ``> 3.0`` /
                             ``> 5.0`` score thresholds, and off-grid coords.
``DEMAND_PCBS``              ``estimate_routing_demand``: the regex classifier
                             (``GND``/``VCC``/``VDD``/``VSS`` anchored,
                             leading ``+``/``-``, ``_P``/``_N``/``DP``/``DN``
                             diff-pair, and the fall-through), plus zero
                             routable nets so ``avg_pins_per_net`` takes its
                             ``0.0`` branch.
``SUGGESTION_REGIONS``       ``generate_placement_suggestions``: the
                             ``bottleneck_score < 0.5`` cutoff exactly, the
                             ``distance < 0.1`` "already at centre" branch,
                             the ``2 x radius`` inclusion boundary, every
                             severity string plus one unknown one (which
                             takes the ``.get(severity, 3.0)`` default), and
                             the ``{:.2f}`` half-even formatting values.

``BENCH_*`` are the subsets the perf arms will time.  They are *subsets*, not
separate data: the containment test is what makes the #714 gap unreachable.
"""

from __future__ import annotations

import math

__all__ = [
    "ANALYZE_DESIGNS",
    "BENCH_ANALYZE_DESIGNS",
    "BENCH_DEMAND_SUPPLY_PAIRS",
    "BENCH_NET_BBOXES",
    "BENCH_ROUTING_RESULT_CASES",
    "BOARD_GRIDS",
    "DEMAND_PCBS",
    "DEMAND_SUPPLY_PAIRS",
    "NET_BBOXES",
    "ROUTING_RESULT_CASES",
    "SUGGESTION_REGIONS",
    "random_demand_supply",
    "random_net_bboxes",
]

NAN = float("nan")
INF = float("inf")
NEG_INF = float("-inf")

# Smallest positive f64 (denormal) and the smallest normal, for B8.
DENORM = 5e-324
TINY = 2.2250738585072014e-308

# The exact constants the reference branches on.  Landing *on* them, not
# merely near them, is what makes the branch-boundary mutants killable.
_SUPPLY_FLOOR = 1e-6  # np.maximum(self.supply, 1e-6)
_SCORE_CUTOFF = 0.5  # region.bottleneck_score < 0.5 -> skip
_CENTRE_EPS = 0.1  # distance < 0.1 -> "already at centre"
_CONGESTION_CUTOFF = 0.5  # congestion > 0.5 -> emit a region


def _ulp_over(x: float) -> float:
    return math.nextafter(x, math.inf)


def _ulp_under(x: float) -> float:
    return math.nextafter(x, -math.inf)


# ---------------------------------------------------------------------------
# CongestionGrid.from_board -- (width, height, cell_size_mm, num_layers,
#                               default_supply, origin)
# ---------------------------------------------------------------------------
BOARD_GRIDS: list[tuple[float, float, float, int, float, tuple[float, float]]] = [
    # ordinary square boards, 2D and 3D
    (100.0, 100.0, 1.0, 1, 10.0, (0.0, 0.0)),
    (10.0, 10.0, 1.0, 1, 10.0, (0.0, 0.0)),
    (10.0, 10.0, 1.0, 2, 10.0, (0.0, 0.0)),
    (10.0, 10.0, 1.0, 4, 3.5, (0.0, 0.0)),
    # non-square, non-unit cell
    (33.0, 17.0, 2.5, 1, 10.0, (0.0, 0.0)),
    (33.0, 17.0, 0.25, 1, 10.0, (-5.0, -5.0)),
    # ceil boundary: exact multiple, one ulp over, one ulp under
    (10.0, 10.0, 1.0, 1, 10.0, (0.0, 0.0)),
    (_ulp_over(10.0), 10.0, 1.0, 1, 10.0, (0.0, 0.0)),
    (_ulp_under(10.0), 10.0, 1.0, 1, 10.0, (0.0, 0.0)),
    (99.9, 99.9, 1.0, 1, 10.0, (0.0, 0.0)),
    # degenerate: zero-area board -> a (1, 0) demand array, not an error
    (0.0, 10.0, 1.0, 1, 10.0, (0.0, 0.0)),
    (10.0, 0.0, 1.0, 1, 10.0, (0.0, 0.0)),
    (0.0, 0.0, 1.0, 1, 10.0, (0.0, 0.0)),
    # sub-cell board
    (0.5, 0.5, 1.0, 1, 10.0, (0.0, 0.0)),
    # signed-zero origin -- (x + 0.5) * cell against -0.0 in to_coordinates
    (4.0, 4.0, 1.0, 1, 10.0, (-0.0, -0.0)),
    # supply extremes
    (4.0, 4.0, 1.0, 1, 0.0, (0.0, 0.0)),
    (4.0, 4.0, 1.0, 1, _SUPPLY_FLOOR, (0.0, 0.0)),
    (4.0, 4.0, 1.0, 1, DENORM, (0.0, 0.0)),
    (4.0, 4.0, 1.0, 1, NAN, (0.0, 0.0)),
    (4.0, 4.0, 1.0, 1, INF, (0.0, 0.0)),
    # int(math.ceil(inf / 1.0)) raises OverflowError -- error parity
    (INF, 10.0, 1.0, 1, 10.0, (0.0, 0.0)),
    (NAN, 10.0, 1.0, 1, 10.0, (0.0, 0.0)),
]

BENCH_BOARD_GRIDS = [
    (100.0, 100.0, 1.0, 1, 10.0, (0.0, 0.0)),
    (33.0, 17.0, 0.25, 1, 10.0, (-5.0, -5.0)),
    (10.0, 10.0, 1.0, 4, 3.5, (0.0, 0.0)),
]

# ---------------------------------------------------------------------------
# get_utilization / get_overflow -- (demand_row, supply_row)
# Two equal-length rows; the tests reshape them into (1, N) grids.
# ---------------------------------------------------------------------------
DEMAND_SUPPLY_PAIRS: list[tuple[list[float], list[float]]] = [
    # ordinary
    ([0.0, 1.0, 5.0, 12.0], [10.0, 10.0, 10.0, 10.0]),
    ([3.0, 3.0], [3.0, 6.0]),
    # supply at, just under, and just over the 1e-6 np.maximum floor
    ([1.0, 1.0, 1.0], [_SUPPLY_FLOOR, _ulp_under(_SUPPLY_FLOOR), _ulp_over(_SUPPLY_FLOOR)]),
    ([1.0, 1.0], [0.0, -0.0]),
    ([1.0, 1.0], [-1.0, -1e30]),
    # B12: np.maximum propagates NaN from EITHER operand; CPython max keeps
    # the first; f64::max discards.  One NaN per position, independently.
    ([NAN, 1.0], [10.0, 10.0]),
    ([1.0, 1.0], [NAN, 10.0]),
    ([NAN, NAN], [NAN, NAN]),
    # infinities, including inf - inf -> NaN in get_overflow
    ([INF, 1.0], [10.0, INF]),
    ([INF, NEG_INF], [INF, NEG_INF]),
    ([NEG_INF, 1.0], [10.0, 10.0]),
    # denormal band (B8): a fast-math/FTZ build flushes these to 0.0
    ([DENORM, TINY], [DENORM, TINY]),
    ([DENORM], [1e300]),
    # signed zeros: 0.0 / 1e-6 vs -0.0 / 1e-6 differ in sign bit only
    ([0.0, -0.0], [1.0, 1.0]),
    # large magnitudes where demand/supply is inexact
    ([1e308, 1e-308], [1e-308, 1e308]),
]

BENCH_DEMAND_SUPPLY_PAIRS = [
    ([0.0, 1.0, 5.0, 12.0], [10.0, 10.0, 10.0, 10.0]),
    ([1.0, 1.0, 1.0], [_SUPPLY_FLOOR, _ulp_under(_SUPPLY_FLOOR), _ulp_over(_SUPPLY_FLOOR)]),
    ([1e308, 1e-308], [1e-308, 1e308]),
]

# ---------------------------------------------------------------------------
# estimate_net_demand -- (grid_w, grid_h, cell, origin, pin_positions, layer,
#                         demand_per_cell)
# ---------------------------------------------------------------------------
NET_BBOXES: list[
    tuple[float, float, float, tuple[float, float], list[tuple[float, float]], int, float]
] = [
    # < 2 pins -> the grid is returned unchanged (identity, same object)
    (10.0, 10.0, 1.0, (0.0, 0.0), [], 0, 1.0),
    (10.0, 10.0, 1.0, (0.0, 0.0), [(1.0, 1.0)], 0, 1.0),
    # both pins in one cell
    (10.0, 10.0, 1.0, (0.0, 0.0), [(1.2, 1.3), (1.4, 1.1)], 0, 1.0),
    # ordinary interior bbox
    (10.0, 10.0, 1.0, (0.0, 0.0), [(1.0, 1.0), (5.0, 4.0)], 0, 1.0),
    (10.0, 10.0, 1.0, (0.0, 0.0), [(5.0, 4.0), (1.0, 1.0)], 0, 1.0),  # insertion order
    # spans the whole board
    (10.0, 10.0, 1.0, (0.0, 0.0), [(0.0, 0.0), (10.0, 10.0)], 0, 1.0),
    # The site of defect D3: entirely off-board used to leave col_max negative
    # -> negative-index slice -> demand written at the ORIGIN.  Repaired by
    # #760; these rows are kept because they are now the regression corpus for
    # the guard, and are pinned inverted by
    # test_repaired_d3_offboard_net_contributes_nothing.
    (10.0, 10.0, 1.0, (0.0, 0.0), [(-5.0, -5.0), (-4.0, -4.0)], 0, 1.0),
    (10.0, 10.0, 1.0, (0.0, 0.0), [(-1.0, 2.0), (-0.5, 3.0)], 0, 1.0),
    # entirely off-board on the FAR side -> also returns the grid unchanged
    (10.0, 10.0, 1.0, (0.0, 0.0), [(50.0, 50.0), (60.0, 60.0)], 0, 1.0),
    # straddling the low boundary
    (10.0, 10.0, 1.0, (0.0, 0.0), [(-3.0, -3.0), (2.0, 2.0)], 0, 1.0),
    # non-zero origin
    (10.0, 10.0, 1.0, (-5.0, -5.0), [(-4.0, -4.0), (0.0, 0.0)], 0, 1.0),
    # exactly on a cell boundary -- int() truncation, not rounding
    (10.0, 10.0, 1.0, (0.0, 0.0), [(2.0, 2.0), (3.0, 3.0)], 0, 1.0),
    (10.0, 10.0, 1.0, (0.0, 0.0), [(_ulp_under(2.0), 2.0), (3.0, 3.0)], 0, 1.0),
    # negative demand, zero demand, denormal demand
    (10.0, 10.0, 1.0, (0.0, 0.0), [(1.0, 1.0), (3.0, 3.0)], 0, -1.0),
    (10.0, 10.0, 1.0, (0.0, 0.0), [(1.0, 1.0), (3.0, 3.0)], 0, 0.0),
    (10.0, 10.0, 1.0, (0.0, 0.0), [(1.0, 1.0), (3.0, 3.0)], 0, DENORM),
    # 3D grids: layer 0 and layer 1
    (10.0, 10.0, 1.0, (0.0, 0.0), [(1.0, 1.0), (3.0, 3.0)], 0, 1.0),
    (10.0, 10.0, 1.0, (0.0, 0.0), [(1.0, 1.0), (3.0, 3.0)], 1, 1.0),
    # NaN / inf coordinate -> int(NaN) raises ValueError, int(inf) OverflowError
    (10.0, 10.0, 1.0, (0.0, 0.0), [(NAN, 0.0), (1.0, 1.0)], 0, 1.0),
    (10.0, 10.0, 1.0, (0.0, 0.0), [(0.0, NAN), (1.0, 1.0)], 0, 1.0),
    (10.0, 10.0, 1.0, (0.0, 0.0), [(INF, 0.0), (1.0, 1.0)], 0, 1.0),
    (10.0, 10.0, 1.0, (0.0, 0.0), [(NEG_INF, 0.0), (1.0, 1.0)], 0, 1.0),
]

BENCH_NET_BBOXES = [
    (10.0, 10.0, 1.0, (0.0, 0.0), [(1.0, 1.0), (5.0, 4.0)], 0, 1.0),
    (10.0, 10.0, 1.0, (0.0, 0.0), [(0.0, 0.0), (10.0, 10.0)], 0, 1.0),
    (10.0, 10.0, 1.0, (-5.0, -5.0), [(-4.0, -4.0), (0.0, 0.0)], 0, 1.0),
]

# ---------------------------------------------------------------------------
# analyze_congestion -- a whole design as plain data.
#   (label, board_wh, cell, capacity, num_layers, components, nets)
# component: (ref, initial_position, initial_rotation_quadrant, [(pin_name, (px, py), net)])
# net:       (name, [(comp_ref, pin_name), ...])
# ---------------------------------------------------------------------------
_C = "components"
_N = "nets"

ANALYZE_DESIGNS: list[dict] = [
    # initial_side is READ by pin_world_position_at -- a bottom-side pad
    # mirrors X BEFORE rotation -- and this kernel omitted the mirror until
    # 2026-08-06, justified by "the corpus carries no initial_side". That was
    # true of the fixtures and false of any real board. Same defect class as
    # escape_via.rs (roundrect_ratio) and net_ordering.rs (initial_side).
    {
        "label": "mixed_side_mirror",
        "components": [
            ("U1", (2.0, 2.0), 0, [("1", (1.0, 0.0), "N1")], 0),
            ("U2", (6.0, 2.0), 0, [("1", (1.0, 0.0), "N1")], 1),
        ],
        "nets": [("N1", [("U1", "1"), ("U2", "1")])],
        "board": (10.0, 10.0),
        "cell": 1.0,
        "capacity": 10.0,
        "layers": 1,
    },
    {
        "label": "empty",
        "board": (10.0, 10.0),
        "cell": 1.0,
        "capacity": 10.0,
        "layers": 1,
        _C: [],
        _N: [],
    },
    {
        "label": "single_one_pin_net",
        "board": (10.0, 10.0),
        "cell": 1.0,
        "capacity": 10.0,
        "layers": 1,
        _C: [("U1", (2.0, 2.0), 0, [("1", (0.0, 0.0), "N1")])],
        _N: [("N1", [("U1", "1")])],
    },
    {
        "label": "two_pin_net",
        "board": (10.0, 10.0),
        "cell": 1.0,
        "capacity": 10.0,
        "layers": 1,
        _C: [
            ("U1", (1.0, 1.0), 0, [("1", (0.0, 0.0), "N1")]),
            ("U2", (6.0, 5.0), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        _N: [("N1", [("U1", "1"), ("U2", "1")])],
    },
    {
        "label": "all_nets_in_one_cell",
        "board": (10.0, 10.0),
        "cell": 1.0,
        "capacity": 2.0,
        "layers": 1,
        _C: [(f"U{i}", (3.1, 3.1), 0, [("1", (0.0, 0.0), f"N{i}")]) for i in range(6)]
        + [(f"V{i}", (3.2, 3.2), 0, [("1", (0.0, 0.0), f"N{i}")]) for i in range(6)],
        _N: [(f"N{i}", [(f"U{i}", "1"), (f"V{i}", "1")]) for i in range(6)],
    },
    {
        "label": "overflow_everywhere_capacity_zero",
        "board": (4.0, 4.0),
        "cell": 1.0,
        "capacity": 0.0,
        "layers": 1,
        _C: [
            ("U1", (0.0, 0.0), 0, [("1", (0.0, 0.0), "N1")]),
            ("U2", (4.0, 4.0), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        _N: [("N1", [("U1", "1"), ("U2", "1")])],
    },
    {
        "label": "missing_component_ref",
        "board": (10.0, 10.0),
        "cell": 1.0,
        "capacity": 10.0,
        "layers": 1,
        _C: [("U1", (1.0, 1.0), 0, [("1", (0.0, 0.0), "N1")])],
        _N: [("N1", [("U1", "1"), ("GHOST", "1")])],
    },
    {
        "label": "missing_pin_name",
        "board": (10.0, 10.0),
        "cell": 1.0,
        "capacity": 10.0,
        "layers": 1,
        _C: [
            ("U1", (1.0, 1.0), 0, [("1", (0.0, 0.0), "N1")]),
            ("U2", (5.0, 5.0), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        _N: [("N1", [("U1", "NOPE"), ("U2", "1")])],
    },
    {
        "label": "component_without_initial_position",
        "board": (10.0, 10.0),
        "cell": 1.0,
        "capacity": 10.0,
        "layers": 1,
        _C: [
            ("U1", None, 0, [("1", (0.0, 0.0), "N1")]),
            ("U2", (5.0, 5.0), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        _N: [("N1", [("U1", "1"), ("U2", "1")])],
    },
    {
        "label": "rotated_components",
        "board": (20.0, 20.0),
        "cell": 1.0,
        "capacity": 10.0,
        "layers": 1,
        _C: [
            ("U1", (5.0, 5.0), 1, [("1", (1.5, 0.5), "N1")]),
            ("U2", (12.0, 9.0), 3, [("1", (1.5, 0.5), "N1")]),
        ],
        _N: [("N1", [("U1", "1"), ("U2", "1")])],
    },
    {
        "label": "three_layers_but_no_assignments",
        "board": (6.0, 6.0),
        "cell": 1.0,
        "capacity": 1.0,
        "layers": 3,
        _C: [
            ("U1", (0.5, 0.5), 0, [("1", (0.0, 0.0), "N1")]),
            ("U2", (5.5, 5.5), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        _N: [("N1", [("U1", "1"), ("U2", "1")])],
    },
]

BENCH_ANALYZE_DESIGNS = [
    d
    for d in ANALYZE_DESIGNS
    if d["label"] in {"two_pin_net", "all_nets_in_one_cell", "overflow_everywhere_capacity_zero"}
]

# ---------------------------------------------------------------------------
# identify_congested_regions -- (label, board_w, board_h, grid_size,
#                                failed_net_names, {net: [(x, y), ...]})
# ---------------------------------------------------------------------------
ROUTING_RESULT_CASES: list[tuple[str, float, float, float, list[str], dict]] = [
    ("empty", 100.0, 100.0, 10.0, [], {}),
    # failed-net severity cliffs: 1 -> HIGH, 2 -> HIGH, 3 -> CRITICAL
    ("one_failed", 100.0, 100.0, 10.0, ["A"], {}),
    ("two_failed", 100.0, 100.0, 10.0, ["A", "B"], {}),
    ("three_failed", 100.0, 100.0, 10.0, ["A", "B", "C"], {}),
    ("ten_failed", 100.0, 100.0, 10.0, [f"N{i}" for i in range(10)], {}),
    # route density only.  Each coordinate adds 0.1; the region cutoff is
    # `congestion > 0.5`, so 5 coords in one cell is exactly 0.5 (excluded --
    # strict >) and 6 is the first included count.  Both are present.
    ("five_coords_exactly_at_cutoff", 100.0, 100.0, 10.0, [], {"R": [(5.0, 5.0)] * 5}),
    ("six_coords_just_over_cutoff", 100.0, 100.0, 10.0, [], {"R": [(5.0, 5.0)] * 6}),
    # the LOW/MEDIUM/HIGH score cliffs at 1.0 / 3.0 / 5.0
    ("score_at_1_0", 100.0, 100.0, 10.0, [], {"R": [(5.0, 5.0)] * 10}),
    ("score_over_1_0", 100.0, 100.0, 10.0, [], {"R": [(5.0, 5.0)] * 11}),
    ("score_at_3_0", 100.0, 100.0, 10.0, [], {"R": [(5.0, 5.0)] * 30}),
    ("score_over_3_0", 100.0, 100.0, 10.0, [], {"R": [(5.0, 5.0)] * 31}),
    ("score_at_5_0", 100.0, 100.0, 10.0, [], {"R": [(5.0, 5.0)] * 50}),
    ("score_over_5_0", 100.0, 100.0, 10.0, [], {"R": [(5.0, 5.0)] * 51}),
    # bottleneck_score = min(1.0, congestion / 10.0) saturates at 100 coords
    ("score_saturates", 100.0, 100.0, 10.0, [], {"R": [(5.0, 5.0)] * 120}),
    # coordinates off the grid on each side -> skipped by the bounds test
    ("offgrid_negative", 100.0, 100.0, 10.0, [], {"R": [(-1.0, -1.0)] * 20}),
    ("offgrid_far", 100.0, 100.0, 10.0, [], {"R": [(1e6, 1e6)] * 20}),
    # coordinate exactly on a cell boundary -- int() truncation
    ("on_cell_boundary", 100.0, 100.0, 10.0, [], {"R": [(10.0, 10.0)] * 20}),
    ("just_under_boundary", 100.0, 100.0, 10.0, [], {"R": [(_ulp_under(10.0), 10.0)] * 20}),
    # several nets, so the accumulation order over compiled_routes matters
    (
        "multi_net_same_cell",
        100.0,
        100.0,
        10.0,
        [],
        {"A": [(5.0, 5.0)] * 4, "B": [(5.0, 5.0)] * 4, "C": [(5.0, 5.0)] * 4},
    ),
    # a board smaller than one grid cell, and a non-integer cell count
    ("sub_cell_board", 5.0, 5.0, 10.0, ["A"], {}),
    ("fractional_cells", 97.0, 43.0, 10.0, ["A"], {"R": [(93.0, 41.0)] * 8}),
    # failed nets AND density in the same cell -- failed-net severity wins
    ("failed_and_dense", 100.0, 100.0, 10.0, ["A"], {"R": [(50.0, 50.0)] * 60}),
]

BENCH_ROUTING_RESULT_CASES = [
    c
    for c in ROUTING_RESULT_CASES
    if c[0] in {"score_saturates", "multi_net_same_cell", "failed_and_dense"}
]

# ---------------------------------------------------------------------------
# estimate_routing_demand -- (label, [(comp_ref, [(pin_number, net), ...])],
#                             [net_name, ...])
# ---------------------------------------------------------------------------
DEMAND_PCBS: list[tuple[str, list, list[str]]] = [
    ("empty", [], []),
    ("no_routable_nets", [("U1", [("1", "SOLO")])], ["SOLO"]),
    (
        "one_signal_net",
        [("U1", [("1", "DATA")]), ("U2", [("1", "DATA")])],
        ["DATA"],
    ),
    # the anchored power regex: (^|_)(GND|VCC|VDD|VSS)($|[\d_])
    (
        "power_names",
        [
            ("U1", [(str(i), n) for i, n in enumerate(["GND", "VCC1", "A_VDD_B", "VSS_"])]),
            ("U2", [(str(i), n) for i, n in enumerate(["GND", "VCC1", "A_VDD_B", "VSS_"])]),
        ],
        ["GND", "VCC1", "A_VDD_B", "VSS_"],
    ),
    # near-misses the anchored regex must REJECT (they were the 2026-07-28 bug)
    (
        "power_near_misses",
        [
            ("U1", [(str(i), n) for i, n in enumerate(["AGND", "VCCX", "MYVDD", "GNDX"])]),
            ("U2", [(str(i), n) for i, n in enumerate(["AGND", "VCCX", "MYVDD", "GNDX"])]),
        ],
        ["AGND", "VCCX", "MYVDD", "GNDX"],
    ),
    # leading +/- -> power; a hyphen elsewhere must NOT match
    (
        "leading_sign",
        [
            ("U1", [(str(i), n) for i, n in enumerate(["+5V", "-12V", "SPI-P2", "D+"])]),
            ("U2", [(str(i), n) for i, n in enumerate(["+5V", "-12V", "SPI-P2", "D+"])]),
        ],
        ["+5V", "-12V", "SPI-P2", "D+"],
    ),
    # diff-pair substrings
    (
        "diff_pairs",
        [
            ("U1", [(str(i), n) for i, n in enumerate(["USB_P", "USB_N", "HDMI_DP", "HDMI_DN"])]),
            ("U2", [(str(i), n) for i, n in enumerate(["USB_P", "USB_N", "HDMI_DP", "HDMI_DN"])]),
        ],
        ["USB_P", "USB_N", "HDMI_DP", "HDMI_DN"],
    ),
    # case folding: the classifier upper-cases first
    (
        "lowercase_names",
        [
            ("U1", [(str(i), n) for i, n in enumerate(["gnd", "usb_p", "data"])]),
            ("U2", [(str(i), n) for i, n in enumerate(["gnd", "usb_p", "data"])]),
        ],
        ["gnd", "usb_p", "data"],
    ),
    # a net declared but with no pins anywhere -> not routable
    ("declared_but_unpinned", [("U1", [("1", "OTHER")])], ["GHOST", "OTHER"]),
    # a pin whose net is not in the net list -> counted in total_pins only
    ("orphan_pin_net", [("U1", [("1", "X"), ("2", "Y")])], ["X"]),
    # fanout: avg_pins_per_net and max_pins_per_net
    (
        "high_fanout",
        [(f"U{i}", [("1", "BUS")]) for i in range(12)],
        ["BUS"],
    ),
    (
        "mixed_fanout",
        [("U1", [("1", "A"), ("2", "B")]), ("U2", [("1", "A"), ("2", "B")]), ("U3", [("1", "A")])],
        ["A", "B"],
    ),
    # nets supplied as a dict (the module explicitly handles both shapes)
    ("dict_nets", [("U1", [("1", "A")]), ("U2", [("1", "A")])], ["A"]),
]

# ---------------------------------------------------------------------------
# generate_placement_suggestions / apply_suggestions_with_damping
#   region:  (center_x, center_y, radius, severity, failed_net_count,
#             bottleneck_score)
# ---------------------------------------------------------------------------
SUGGESTION_REGIONS: list[tuple[float, float, float, str, int, float]] = [
    # below / exactly at / above the 0.5 bottleneck_score cutoff
    (50.0, 50.0, 5.0, "high", 1, 0.49),
    (50.0, 50.0, 5.0, "high", 1, _SCORE_CUTOFF),
    (50.0, 50.0, 5.0, "high", 1, _ulp_under(_SCORE_CUTOFF)),
    (50.0, 50.0, 5.0, "high", 1, _ulp_over(_SCORE_CUTOFF)),
    # every severity string the move-distance table knows, plus an unknown
    # one that must take the `.get(severity, 3.0)` default
    (50.0, 50.0, 5.0, "critical", 3, 0.9),
    (50.0, 50.0, 5.0, "high", 1, 0.9),
    (50.0, 50.0, 5.0, "medium", 0, 0.9),
    (50.0, 50.0, 5.0, "low", 0, 0.9),
    (50.0, 50.0, 5.0, "none", 0, 0.9),
    (50.0, 50.0, 5.0, "UNKNOWN_SEVERITY", 0, 0.9),
    # priority = min(1.0, score * 1.2) saturates above 0.8333...
    (50.0, 50.0, 5.0, "high", 1, 0.8333333333333334),
    (50.0, 50.0, 5.0, "high", 1, 1.0),
    (50.0, 50.0, 5.0, "high", 1, INF),
    (50.0, 50.0, 5.0, "high", 1, NAN),  # min(1.0, NaN*1.2) -> 1.0 (B5)
    # the `:.2f` half-even formatting values -- these render '0.12' and
    # '2.67', not '0.13'/'2.68'
    (50.0, 50.0, 5.0, "high", 1, 0.125),
    (50.0, 50.0, 5.0, "high", 1, 0.135),
    (50.0, 50.0, 5.0, "high", 1, 2.675),
    # zero and negative radius: the `distance < radius * 2` inclusion test
    (50.0, 50.0, 0.0, "high", 1, 0.9),
    (50.0, 50.0, -1.0, "high", 1, 0.9),
    (50.0, 50.0, INF, "high", 1, 0.9),
]

# component positions the suggestion cases are evaluated against
SUGGESTION_POSITIONS: dict[str, tuple[float, float]] = {
    "AT_CENTRE": (50.0, 50.0),  # distance 0.0 -> the "already at centre" branch
    "JUST_INSIDE_EPS": (50.0 + 0.09, 50.0),  # distance < 0.1
    "AT_EPS": (50.0 + _CENTRE_EPS, 50.0),  # distance == 0.1 exactly
    "NEAR": (52.0, 53.0),
    "AT_2R": (60.0, 50.0),  # distance == radius * 2 exactly -> EXCLUDED
    "JUST_INSIDE_2R": (_ulp_under(60.0), 50.0),
    "JUST_OUTSIDE_2R": (_ulp_over(60.0), 50.0),
    "FAR": (900.0, 900.0),
    "NEGATIVE": (-10.0, -10.0),
    "NAN_X": (NAN, 50.0),
    "INF_X": (INF, 50.0),
    "SIGNED_ZERO": (-0.0, -0.0),
}

# Deterministic random sweeps.  Seeded, so the "randomized" coverage the
# differential adds on top of the fixed corpus is itself reproducible.
# ---------------------------------------------------------------------------
def random_demand_supply(seed: int, n: int) -> list[tuple[list[float], list[float]]]:
    """``n`` (demand_row, supply_row) pairs of width 8, seeded by ``seed``."""
    import random

    rng = random.Random(seed)
    out = []
    for _ in range(n):
        demand = [rng.uniform(-5.0, 50.0) for _ in range(8)]
        supply = [rng.choice([0.0, 1e-6, rng.uniform(0.0, 20.0)]) for _ in range(8)]
        out.append((demand, supply))
    return out


def random_net_bboxes(seed: int, n: int) -> list[list[tuple[float, float]]]:
    """``n`` pin-position lists, seeded by ``seed``.

    Coordinates deliberately range outside the board so the off-board branch
    -- the site of defect D3's negative-index slice, repaired by #760 and now
    an early return -- is hit by the random sweep too, not only by the
    hand-written rows.
    """
    import random

    rng = random.Random(seed)
    out = []
    for _ in range(n):
        k = rng.choice([0, 1, 2, 2, 3, 5])
        out.append([(rng.uniform(-20.0, 30.0), rng.uniform(-20.0, 30.0)) for _ in range(k)])
    return out
