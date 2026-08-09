"""Shared input corpus for the router_v6 cluster-F (quality metrics) gates.

**One fixture module, three consumers**: the differential suite (R1a), the
property/metamorphic suite (R1c/R1d), and the future
``benchmarks/perf_ab.py`` arms (R1b) all draw their inputs from here.

That is deliberate and structural, not stylistic.  PR #714 passed its
differential at iterations ``[0, 1, 2, 8, 17, 100]`` and then failed CI on a
benchmark that ran 120 -- the benchmark exercised a parameter the behavioral
gate had never reached.  Sharing the corpus makes that class of gap
impossible to reintroduce: every input the benchmark times is, by
construction, an input the differential has already compared bit-for-bit.
``test_quality_metrics_oracle_pin.py::test_benchmark_corpus_is_covered_by_differential``
asserts the containment explicitly, so the property survives future edits to
either side.

The corpus is a *fixed* list, not a live random draw, so the perf A/B ratio is
comparable across runs and machines.  The randomized sweeps are additional
coverage layered on top, never a replacement.

**No module in here imports the code under test** -- it is pure data, so the
oracle arm and the Rust arm can each build their own object types from it.

Threshold constants the kernels branch on
-----------------------------------------
Landing *on* a threshold (not merely near it) is what makes a
branch-boundary mutant killable.  The pinned thresholds are:

===============================================  ==========================
Constant                                         Kernel / branch
===============================================  ==========================
``160.0`` deg                                    hairpin; also the zigzag
                                                 exclusion
``5.0`` deg                                      zigzag "almost straight"
``cross > 0`` / ``< 0`` / ``== 0``               zigzag left/right/straight
``0.2`` mm                                       isolated-via attachment
``1.5``                                          detour ratio (default)
``0.001`` mm                                     detour zero-length guard
``0.1`` mm                                       ``_order_traces`` eps
``1e-9``                                         ``_angle_between`` degenerate
``3.0 * (0.2 + 0.15)``                           channel min gap
``5.0`` mm                                       stitching board-edge margin
``{"Q1", "Q2"}`` / ``"DC_BUS+"``                 thermal via classification
===============================================  ==========================

``CHANNEL_MIN_GAP`` below is written as the *expression* the kernel evaluates,
not as a decimal literal: ``3.0 * (0.2 + 0.15)`` is ``1.0499999999999998``,
which is a different f64 from both ``1.05`` and ``3.0 * 0.2 + 3.0 * 0.15``
(catalog B7 -- grouping is part of the contract).
"""

from __future__ import annotations

import random

__all__ = [
    "NAN",
    "INF",
    "CHANNEL_MIN_GAP",
    "DISTANCE_PAIRS",
    "ANGLE_CASES",
    "ORDER_TRACE_SETS",
    "BBOX_CASES",
    "EDGE_MARGIN_CASES",
    "SCENARIOS",
    "CORPUS_BOARDS",
    "BENCH_DISTANCE_PAIRS",
    "BENCH_ANGLE_CASES",
    "BENCH_SCENARIOS",
    "BENCH_CORPUS_BOARDS",
    "random_distance_pairs",
    "random_angle_cases",
    "random_trace_set",
]

NAN = float("nan")
INF = float("inf")

#: The channel-width threshold, written as the kernel's own expression.
#: ``_CHANNEL_WIDTH_MULTIPLIER * (track_width_mm + min_clearance_mm)``.
CHANNEL_MIN_GAP = 3.0 * (0.2 + 0.15)

# ---------------------------------------------------------------------------
# (ax, ay, bx, by) -- ``_distance_mm``  (CPython ``math.hypot``, catalog B4)
# ---------------------------------------------------------------------------
DISTANCE_PAIRS: list[tuple[float, float, float, float]] = [
    # ordinary board-scale separations
    (0.0, 0.0, 3.0, 4.0),
    (10.0, 10.0, 10.0, 10.0),  # coincident -> exactly 0.0
    (-5.5, 2.25, 5.5, -2.25),
    (127.0, 63.5, 0.0, 0.0),
    # exactly the isolated-via 0.2 mm attachment threshold, and one ulp
    # either side of it (the branch is ``< 0.2``, so ON the threshold is out)
    (0.0, 0.0, 0.2, 0.0),
    (0.0, 0.0, 0.19999999999999998, 0.0),
    (0.0, 0.0, 0.20000000000000004, 0.0),
    # exactly the ``_order_traces`` eps of 0.1 mm and its neighbours
    (0.0, 0.0, 0.1, 0.0),
    (0.0, 0.0, 0.09999999999999999, 0.0),
    (0.0, 0.0, 0.10000000000000002, 0.0),
    # exactly the detour zero-length guard of 0.001 mm
    (0.0, 0.0, 0.001, 0.0),
    (0.0, 0.0, 0.0009999999999999998, 0.0),
    # pairs where CPython's Dekker ``hypot`` and naive ``sqrt(dx*dx+dy*dy)``
    # provably disagree in the last ulp -- these are pinned instances of the
    # ~17% of random 2-vectors that separate the two (catalog B4)
    (0.0, 0.0, 0.1, 0.2),
    (0.0, 0.0, 1.7976931348623157e308, 0.0),  # overflows the naive form
    (0.0, 0.0, 5e-324, 5e-324),  # denormal band (catalog B8)
    (0.0, 0.0, 1e-300, 1e-300),
    (0.0, 0.0, 3.0000000000000004, 3.9999999999999996),
    # signed zeros: ``-0.0 - 0.0`` is ``-0.0``; hypot must still give ``+0.0``
    (0.0, 0.0, -0.0, -0.0),
    (-0.0, -0.0, 0.0, 0.0),
    # NaN / inf -- ``math.hypot`` treats inf as dominant even beside NaN
    (NAN, 0.0, 0.0, 0.0),
    (0.0, NAN, 0.0, 0.0),
    (0.0, 0.0, NAN, NAN),
    (INF, 0.0, 0.0, 0.0),
    (INF, NAN, 0.0, 0.0),  # CPython: inf wins over NaN -> inf
    (-INF, 0.0, INF, 0.0),
    # ints: callers do pass integer coordinates
    (0, 0, 3, 4),
]

# ---------------------------------------------------------------------------
# (i0x, i0y, i1x, i1y, o0x, o0y, o1x, o1y) -- ``_angle_between``
#
# The kernel is called as ``_angle_between((prev.end, prev.start),
# (curr.start, curr.end))``, i.e. the incoming arm is already reversed.
# ---------------------------------------------------------------------------
ANGLE_CASES: list[tuple[float, ...]] = [
    # straight-through junction: incoming reversed is antiparallel to
    # outgoing -> 180 deg (a hairpin by the >= 160 rule)
    (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 2.0, 0.0),
    # exact right angle -> 90.0
    (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 1.0, 1.0),
    # exact reversal -> 0.0 deg
    (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0),
    # 45 / 135 deg, exactly representable directions
    (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 2.0, 1.0),
    (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 1.0),
    # The 160 deg hairpin threshold.  With the incoming arm reversed to
    # ``(-1, 0)`` and the outgoing arm the unit vector at ``t`` degrees, the
    # kernel returns ``180 - t``.  ulp-level neighbours of t = 20 deg first...
    (0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.9396926207859084, 0.34202014332566871),
    (0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.9396926207859083, 0.34202014332566871),
    (0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.9396926207859085, 0.34202014332566871),
    # ...then unambiguously either side: t = 19 deg -> 161 deg (a hairpin)
    # and t = 21 deg -> 159 deg (not a hairpin).
    (0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.9455185755993168, 0.32556815445715670),
    (0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 0.9335804264972017, 0.35836794954530027),
    # The 5 deg zigzag "almost straight" threshold.  Incoming reversed is
    # ``(1, 0)``, so the kernel returns ``t`` directly.  ulp neighbours of 5...
    (0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.9961946980917455, 0.08715574274765817),
    (0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.9961946980917456, 0.08715574274765816),
    # ...then t = 4 deg (excluded) and t = 6 deg (kept).
    (0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.9975640502598242, 0.06975647374412530),
    (0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.9945218953682733, 0.10452846326765347),
    # degenerate arms: m1 < 1e-9 and/or m2 < 1e-9 -> early ``return 0.0``
    (0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 2.0, 0.0),
    (1.0, 0.0, 0.0, 0.0, 5.0, 5.0, 5.0, 5.0),
    (0.0, 0.0, 0.0, 0.0, 5.0, 5.0, 5.0, 5.0),
    # exactly AT the 1e-9 magnitude guard and one ulp either side
    (0.0, 0.0, 1e-9, 0.0, 0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 9.999999999999998e-10, 0.0, 0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0000000000000002e-9, 0.0, 0.0, 0.0, 1.0, 0.0),
    # dot/(m1*m2) lands just outside [-1, 1] from rounding -> the
    # ``max(-1.0, min(1.0, ...))`` clamp is what keeps ``acos`` in domain.
    # Nearly-parallel long collinear arms are the reliable way to produce it.
    (0.0, 0.0, 1e8, 1e8, 0.0, 0.0, 1e8, 1e8),
    (0.0, 0.0, -1e8, -1e8, 0.0, 0.0, 1e8, 1e8),
    (0.0, 0.0, 0.1, 0.3, 0.0, 0.0, 0.2, 0.6),
    # NaN: exercises CPython's min-then-max first-argument rule (catalog B5).
    # ``min(1.0, NaN)`` -> 1.0, ``max(-1.0, 1.0)`` -> 1.0, ``acos(1.0)`` -> 0.0.
    # A Rust ``clamp``/``f64::max``-``min`` chain does NOT reproduce this.
    (0.0, 0.0, NAN, 0.0, 0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0, NAN, 0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0, 0.0, 0.0, 0.0, NAN, 1.0),
    (NAN, NAN, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
    # inf arms: magnitudes are inf, dot is inf or NaN
    (0.0, 0.0, INF, 0.0, 0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, INF, 0.0, 0.0, 0.0, 0.0, INF),
    (0.0, 0.0, -INF, 0.0, 0.0, 0.0, INF, 0.0),
    # signed zeros
    (-0.0, -0.0, 0.0, 0.0, -0.0, 0.0, 0.0, -0.0),
    # very large / very small magnitudes (denormal band, catalog B8)
    (0.0, 0.0, 5e-324, 0.0, 0.0, 0.0, 0.0, 5e-324),
    (0.0, 0.0, 1e300, 1e300, 0.0, 0.0, 1e300, -1e300),
    # ints
    (1, 0, 0, 0, 1, 0, 1, 1),
]

# ---------------------------------------------------------------------------
# Trace-segment sets for ``_order_traces`` -- the greedy chain builder whose
# output depends on INSERTION ORDER, on the 0.1 mm eps, and on strict ``<``
# tie-breaking (earliest index wins).
#
# Each entry: (name, [(sx, sy, ex, ey), ...]).
# ---------------------------------------------------------------------------
ORDER_TRACE_SETS: list[tuple[str, list[tuple[float, float, float, float]]]] = [
    ("empty", []),
    ("single", [(0.0, 0.0, 1.0, 0.0)]),
    # already in order, head-to-tail
    ("chain_in_order", [(0.0, 0.0, 1.0, 0.0), (1.0, 0.0, 2.0, 0.0), (2.0, 0.0, 3.0, 0.0)]),
    # same chain, shuffled: the greedy builder must rebuild it
    ("chain_shuffled", [(2.0, 0.0, 3.0, 0.0), (0.0, 0.0, 1.0, 0.0), (1.0, 0.0, 2.0, 0.0)]),
    # same chain, reversed input order
    ("chain_reversed_input", [(2.0, 0.0, 3.0, 0.0), (1.0, 0.0, 2.0, 0.0), (0.0, 0.0, 1.0, 0.0)]),
    # a segment that must be FLIPPED to attach (d_end < d_start)
    ("needs_reversal", [(0.0, 0.0, 1.0, 0.0), (2.0, 0.0, 1.0, 0.0)]),
    # both endpoints equidistant from the tail -> ``best_reversed`` ends True
    # because the ``d_end`` test runs second and uses ``<`` against the
    # already-updated ``best_dist``... which it does NOT satisfy.  Pinned to
    # lock in whichever arm actually wins.
    ("symmetric_attachment", [(0.0, 0.0, 1.0, 0.0), (1.0, 0.0, 1.0, 0.0)]),
    # gap exactly AT the 0.1 mm eps (``< eps`` is false -> disconnected arm)
    ("gap_at_eps", [(0.0, 0.0, 1.0, 0.0), (1.1, 0.0, 2.0, 0.0)]),
    ("gap_just_under_eps", [(0.0, 0.0, 1.0, 0.0), (1.0999999999999999, 0.0, 2.0, 0.0)]),
    # fully disconnected -> the nearest-remaining fallback branch
    ("disconnected", [(0.0, 0.0, 1.0, 0.0), (50.0, 50.0, 51.0, 50.0), (10.0, 0.0, 11.0, 0.0)]),
    # exact ties between two candidates: earliest index must win
    (
        "tie_earliest_index_wins",
        [(0.0, 0.0, 1.0, 0.0), (1.0, 0.0, 2.0, 0.0), (1.0, 0.0, 1.0, 1.0)],
    ),
    # zero-length segments mixed in
    ("zero_length_only", [(1.0, 1.0, 1.0, 1.0)]),
    ("zero_length_mixed", [(0.0, 0.0, 1.0, 0.0), (1.0, 0.0, 1.0, 0.0), (1.0, 0.0, 2.0, 0.0)]),
    # collinear run -- every junction angle is exactly 0 or 180
    (
        "collinear_run",
        [(0.0, 0.0, 1.0, 0.0), (1.0, 0.0, 2.0, 0.0), (2.0, 0.0, 3.0, 0.0), (3.0, 0.0, 4.0, 0.0)],
    ),
    # a true hairpin: doubles back on itself
    ("hairpin", [(0.0, 0.0, 5.0, 0.0), (5.0, 0.0, 0.05, 0.0)]),
    # an alternating zigzag long enough to trip the 3-window scan
    (
        "zigzag",
        [
            (0.0, 0.0, 1.0, 0.0),
            (1.0, 0.0, 2.0, 1.0),
            (2.0, 1.0, 3.0, 0.0),
            (3.0, 0.0, 4.0, 1.0),
            (4.0, 1.0, 5.0, 0.0),
        ],
    ),
    # NaN and inf coordinates: every distance comparison is False, so the
    # greedy loop falls into its nearest-remaining branch every time
    ("nan_coords", [(0.0, 0.0, 1.0, 0.0), (NAN, 0.0, 2.0, 0.0), (1.0, 0.0, NAN, 0.0)]),
    ("inf_coords", [(0.0, 0.0, 1.0, 0.0), (INF, 0.0, 2.0, 0.0)]),
    ("all_nan", [(NAN, NAN, NAN, NAN), (NAN, NAN, NAN, NAN)]),
    # signed zeros
    ("signed_zeros", [(-0.0, -0.0, 0.0, 0.0), (0.0, -0.0, 1.0, 0.0)]),
]

# ---------------------------------------------------------------------------
# (via_x, via_y, [(x_min, y_min, x_max, y_max), ...]) -- ``_is_via_in_bbox``
# ---------------------------------------------------------------------------
BBOX_CASES: list[tuple[float, float, list[tuple[float, float, float, float]]]] = [
    (5.0, 5.0, []),  # empty bbox list -> any() over nothing -> False
    (5.0, 5.0, [(0.0, 0.0, 10.0, 10.0)]),
    (5.0, 5.0, [(0.0, 0.0, 1.0, 1.0), (4.0, 4.0, 6.0, 6.0)]),  # second matches
    (5.0, 5.0, [(0.0, 0.0, 1.0, 1.0)]),  # none match
    (0.0, 0.0, [(0.0, 0.0, 0.0, 0.0)]),  # degenerate bbox, exact hit
    (NAN, 0.0, [(0.0, 0.0, 10.0, 10.0)]),
    (INF, 0.0, [(-INF, -INF, INF, INF)]),
]

# ---------------------------------------------------------------------------
# (via_x, via_y, x_min, y_min, x_max, y_max, margin_mm)
#   -- ``_is_via_near_board_edge``
#
# The kernel uses the **variadic** builtin ``min`` over four distances and
# then ``min_edge_dist <= margin_mm`` (catalog B5: variadic ``min`` returns
# the FIRST argument when NaN is present anywhere, because every ``<``
# comparison against NaN is False).
# ---------------------------------------------------------------------------
EDGE_MARGIN_CASES: list[tuple[float, ...]] = [
    (1.0, 1.0, 0.0, 0.0, 100.0, 100.0, 5.0),  # near the min corner
    (50.0, 50.0, 0.0, 0.0, 100.0, 100.0, 5.0),  # dead centre, far
    (99.0, 50.0, 0.0, 0.0, 100.0, 100.0, 5.0),  # near +x edge
    (50.0, 99.0, 0.0, 0.0, 100.0, 100.0, 5.0),  # near +y edge
    # exactly AT the 5.0 mm margin (``<=`` -> True) and one ulp either side
    (5.0, 50.0, 0.0, 0.0, 100.0, 100.0, 5.0),
    (5.000000000000001, 50.0, 0.0, 0.0, 100.0, 100.0, 5.0),
    (4.999999999999999, 50.0, 0.0, 0.0, 100.0, 100.0, 5.0),
    (0.0, 0.0, 0.0, 0.0, 100.0, 100.0, 5.0),  # exactly on the corner -> 0.0
    (-10.0, 50.0, 0.0, 0.0, 100.0, 100.0, 5.0),  # outside the board -> negative
    (50.0, 50.0, 0.0, 0.0, 0.0, 0.0, 5.0),  # zero-size board
    (50.0, 50.0, 0.0, 0.0, 100.0, 100.0, 0.0),  # zero margin
    (50.0, 50.0, 0.0, 0.0, 100.0, 100.0, -1.0),  # negative margin
    # NaN in the FIRST computed distance (left_dist) vs a later one.  This
    # PAIR is the discriminating witness for catalog B5's variadic-``min``
    # rule, and the two entries must disagree:
    #   (NaN, 1.0): left_dist is NaN -> CPython ``min`` returns its FIRST
    #               argument, NaN -> ``NaN <= 5.0`` is False.
    #   (1.0, NaN): left_dist is 1.0, the NaNs arrive later and lose every
    #               ``<`` comparison -> ``min`` returns 1.0 -> True.
    # A Rust fold over ``f64::min`` (which discards NaN) returns 1.0 in BOTH
    # cases and so reports True for both -- the divergence this pins.
    (NAN, 1.0, 0.0, 0.0, 100.0, 100.0, 5.0),
    (1.0, NAN, 0.0, 0.0, 100.0, 100.0, 5.0),
    (NAN, 50.0, 0.0, 0.0, 100.0, 100.0, 5.0),
    (50.0, NAN, 0.0, 0.0, 100.0, 100.0, 5.0),
    (50.0, 50.0, NAN, 0.0, 100.0, 100.0, 5.0),
    (50.0, 50.0, 0.0, 0.0, NAN, 100.0, 5.0),
    (50.0, 50.0, 0.0, 0.0, 100.0, 100.0, NAN),
    (INF, 50.0, 0.0, 0.0, 100.0, 100.0, 5.0),
    (-INF, 50.0, 0.0, 0.0, 100.0, 100.0, 5.0),
    (50.0, 50.0, -INF, -INF, INF, INF, 5.0),
    (1, 1, 0, 0, 100, 100, 5),  # ints
]

# ---------------------------------------------------------------------------
# Whole-board scenarios.
#
# Pure data.  The consuming suite builds its own duck-typed ``ParseResult``
# stand-in (oracle arm) or its own Rust input struct (Rust arm) from these.
#
# Each entry is a dict with:
#   traces:     [(sx, sy, ex, ey, width, layer, net), ...]
#   vias:       [((x, y), net, (layer_a, layer_b)), ...]
#   components: [(ref, (cx, cy) | None, width, height), ...]
#   board:      (width, height) | None
# ---------------------------------------------------------------------------
_F = "F.Cu"
_B = "B.Cu"

SCENARIOS: list[tuple[str, dict]] = [
    (
        "empty_board",
        {"traces": [], "vias": [], "components": [], "board": (100.0, 100.0)},
    ),
    (
        "no_board_outline",
        {
            "traces": [],
            "vias": [((1.0, 1.0), "GND", (_F, _B))],
            "components": [],
            "board": None,  # ``_get_board_bbox`` returns None -> no stitching
        },
    ),
    (
        "single_trace",
        {
            "traces": [(0.0, 0.0, 10.0, 0.0, 0.25, _F, "NET1")],
            "vias": [],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
    (
        "zero_length_segments",
        {
            "traces": [
                (5.0, 5.0, 5.0, 5.0, 0.25, _F, "NET1"),
                (5.0, 5.0, 5.0, 5.0, 0.25, _F, "NET1"),
                (5.0, 5.0, 15.0, 5.0, 0.25, _F, "NET1"),
            ],
            "vias": [],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
    (
        "collinear_run",
        {
            "traces": [
                (0.0, 0.0, 10.0, 0.0, 0.25, _F, "NET1"),
                (10.0, 0.0, 20.0, 0.0, 0.25, _F, "NET1"),
                (20.0, 0.0, 30.0, 0.0, 0.25, _F, "NET1"),
                (30.0, 0.0, 40.0, 0.0, 0.25, _F, "NET1"),
            ],
            "vias": [],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
    (
        "hairpin_pair",
        {
            "traces": [
                (0.0, 0.0, 10.0, 0.0, 0.25, _F, "NET1"),
                (10.0, 0.0, 0.05, 0.0, 0.25, _F, "NET1"),
            ],
            "vias": [],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
    (
        "zigzag_run",
        {
            "traces": [
                (0.0, 0.0, 1.0, 0.0, 0.25, _F, "NET1"),
                (1.0, 0.0, 2.0, 1.0, 0.25, _F, "NET1"),
                (2.0, 1.0, 3.0, 0.0, 0.25, _F, "NET1"),
                (3.0, 0.0, 4.0, 1.0, 0.25, _F, "NET1"),
                (4.0, 1.0, 5.0, 0.0, 0.25, _F, "NET1"),
                (5.0, 0.0, 6.0, 1.0, 0.25, _F, "NET1"),
            ],
            "vias": [],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
    (
        "all_same_direction_turns",
        {
            # A regular convex polygon walk: every turn is the same handedness,
            # so ``len(set(dirs)) == 1`` short-circuits the zigzag scan.
            "traces": [
                (0.0, 0.0, 1.0, 0.0, 0.25, _F, "NET1"),
                (1.0, 0.0, 2.0, 1.0, 0.25, _F, "NET1"),
                (2.0, 1.0, 2.0, 2.0, 0.25, _F, "NET1"),
                (2.0, 2.0, 1.0, 3.0, 0.25, _F, "NET1"),
                (1.0, 3.0, 0.0, 3.0, 0.25, _F, "NET1"),
            ],
            "vias": [],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
    (
        "detour_over_ratio",
        {
            # Path length 30, direct distance 10 -> ratio 3.0 > 1.5
            "traces": [
                (0.0, 0.0, 0.0, 10.0, 0.25, _F, "NET1"),
                (0.0, 10.0, 10.0, 10.0, 0.25, _F, "NET1"),
                (10.0, 10.0, 10.0, 0.0, 0.25, _F, "NET1"),
            ],
            "vias": [],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
    (
        "detour_exactly_at_ratio",
        {
            # Path 15, direct 10 -> ratio exactly 1.5, and ``> max_ratio`` is
            # False, so this must NOT be reported.
            "traces": [
                (0.0, 0.0, 0.0, 2.5, 0.25, _F, "NET1"),
                (0.0, 2.5, 10.0, 2.5, 0.25, _F, "NET1"),
                (10.0, 2.5, 10.0, 0.0, 0.25, _F, "NET1"),
            ],
            "vias": [],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
    (
        "detour_closed_loop",
        {
            # start == end -> direct_dist 0.0 < 0.001 -> skipped entirely
            "traces": [
                (0.0, 0.0, 10.0, 0.0, 0.25, _F, "NET1"),
                (10.0, 0.0, 10.0, 10.0, 0.25, _F, "NET1"),
                (10.0, 10.0, 0.0, 10.0, 0.25, _F, "NET1"),
                (0.0, 10.0, 0.0, 0.0, 0.25, _F, "NET1"),
            ],
            "vias": [],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
    (
        "isolated_via_stub",
        {
            # Exactly one trace endpoint within 0.2 mm of the via -> reported.
            "traces": [(1.0, 1.0, 10.0, 1.0, 0.25, _F, "NET1")],
            "vias": [((1.0, 1.0), "NET1", (_F, _B))],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
    (
        "via_with_two_segments",
        {
            "traces": [
                (1.0, 1.0, 10.0, 1.0, 0.25, _F, "NET1"),
                (1.0, 1.0, 1.0, 10.0, 0.25, _B, "NET1"),
            ],
            "vias": [((1.0, 1.0), "NET1", (_F, _B))],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
    (
        "via_attachment_at_threshold",
        {
            # Trace endpoint exactly 0.2 mm away: ``< 0.2`` is False, so the
            # via has ZERO attached segments and is NOT reported (the kernel
            # reports only ``segment_count == 1``).
            "traces": [(1.2, 1.0, 10.0, 1.0, 0.25, _F, "NET1")],
            "vias": [((1.0, 1.0), "NET1", (_F, _B))],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
    (
        "via_unnamed_net",
        {
            # ``via.net`` empty -> the ``or "?"`` arms in net_name/description
            "traces": [(1.0, 1.0, 10.0, 1.0, 0.25, _F, "")],
            "vias": [((1.0, 1.0), "", (_F, _B))],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
    (
        "thermal_vias_under_q1",
        {
            "traces": [],
            "vias": [
                ((10.0, 10.0), "DC_BUS+", (_F, _B)),  # inside Q1 -> thermal
                ((10.0, 10.0), "dc_bus+", (_F, _B)),  # case-insensitive match
                ((90.0, 90.0), "DC_BUS+", (_F, _B)),  # outside Q1 -> not thermal
            ],
            "components": [("Q1", (10.0, 10.0), 5.0, 5.0), ("R1", (50.0, 50.0), 2.0, 1.0)],
            "board": (100.0, 100.0),
        },
    ),
    (
        "thermal_component_without_position",
        {
            # ``initial_position is None`` -> the component contributes no
            # bbox, so ``thermal_bboxes`` is empty and the ``if thermal_bboxes``
            # guard short-circuits to False.
            "traces": [],
            "vias": [((10.0, 10.0), "DC_BUS+", (_F, _B))],
            "components": [("Q1", None, 5.0, 5.0)],
            "board": (100.0, 100.0),
        },
    ),
    (
        "stitching_vias_at_edges",
        {
            "traces": [],
            "vias": [
                ((1.0, 50.0), "GND", (_F, _B)),  # within 5 mm of x_min
                ((99.0, 50.0), "GND", (_F, _B)),  # within 5 mm of x_max
                ((50.0, 50.0), "GND", (_F, _B)),  # centre -> not stitching
                ((5.0, 50.0), "GND", (_F, _B)),  # exactly AT the 5 mm margin
            ],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
    (
        "mixed_via_classes",
        {
            "traces": [],
            "vias": [
                ((10.0, 10.0), "DC_BUS+", (_F, _B)),  # thermal
                ((1.0, 50.0), "GND", (_F, _B)),  # stitching
                ((50.0, 50.0), "SIG1", (_F, _B)),  # signal
                ((50.0, 50.0), "GND", (_F, _B)),  # ground, not near edge
                ((50.0, 50.0), "+3V3", (_F, _B)),  # power, not near edge
            ],
            "components": [("Q1", (10.0, 10.0), 5.0, 5.0)],
            "board": (100.0, 100.0),
        },
    ),
    (
        "corridor_two_components_one_channel",
        {
            # Two courtyards separated in y by more than CHANNEL_MIN_GAP, with
            # overlapping x-projections -> exactly one VERTICAL channel
            # spanning x [7.25, 13.75], y [7.25, 13.75].
            #
            # A vertical channel sorts its tracks by ``t.x`` and measures
            # left/right edges, so the tracks must be spread in **x** for the
            # spread kernel to see anything.  (Spreading them in y instead
            # yields coincident x and a negative gap, which the ``gap >
            # overall_max_gap_mm`` guard drops -- a live trap.)
            #
            # Tracks are placed in the SAME (board-relative) frame as the
            # courtyards, which is the only way the assignment step fires at
            # all -- see defect (2) in the oracle header.
            "traces": [
                (8.0, 10.0, 8.0, 11.0, 0.25, _F, "N1"),
                (10.0, 10.0, 10.0, 11.0, 0.25, _F, "N2"),
                (12.0, 10.0, 12.0, 11.0, 0.25, _F, "N3"),
            ],
            "vias": [],
            "components": [("U1", (10.5, 5.0), 6.0, 4.0), ("U2", (10.5, 16.0), 6.0, 4.0)],
            "board": (100.0, 100.0),
        },
    ),
    (
        "corridor_same_net_intervening",
        {
            # Exercises the ``intervening_nets`` arm that counts a
            # non-adjacent pair as co-routed when the only intervening net
            # equals the LEFT track's net -- and, via the N2 in the middle,
            # the arm where it does not.
            "traces": [
                (8.0, 10.0, 8.0, 11.0, 0.25, _F, "N1"),
                (9.0, 10.0, 9.0, 11.0, 0.25, _F, "N1"),
                (10.0, 10.0, 10.0, 11.0, 0.25, _F, "N2"),
                (11.0, 10.0, 11.0, 11.0, 0.25, _F, "N1"),
            ],
            "vias": [],
            "components": [("U1", (10.5, 5.0), 6.0, 4.0), ("U2", (10.5, 16.0), 6.0, 4.0)],
            "board": (100.0, 100.0),
        },
    ),
    (
        "corridor_horizontal_channel",
        {
            # y-projections overlap, x-gap wide -> a HORIZONTAL channel, which
            # sorts by ``t.y`` and measures bottom/top edges instead.  Tracks
            # are therefore spread in **y** here.
            "traces": [
                (10.0, 8.0, 11.0, 8.0, 0.25, _F, "N1"),
                (10.0, 10.0, 11.0, 10.0, 0.25, _F, "N2"),
                (10.0, 12.0, 11.0, 12.0, 0.25, _F, "N3"),
            ],
            "vias": [],
            "components": [("U1", (5.0, 10.5), 4.0, 6.0), ("U2", (16.0, 10.5), 4.0, 6.0)],
            "board": (100.0, 100.0),
        },
    ),
    (
        "corridor_gap_just_over_threshold",
        {
            # Courtyard gap 1.0500000000000007 mm against a threshold of
            # ``3.0 * (0.2 + 0.15)`` == 1.0499999999999998 -- just OVER, so a
            # channel IS formed (with no tracks in it).
            "traces": [],
            "vias": [],
            "components": [
                ("U1", (10.0, 5.0), 6.0, 4.0),
                ("U2", (10.0, 5.0 + 4.0 + 2 * 0.25 + 3.0 * (0.2 + 0.15)), 6.0, 4.0),
            ],
            "board": (100.0, 100.0),
        },
    ),
    (
        "corridor_single_component",
        {
            # ``len(courtyards) < 2`` -> ``_identify_channels`` returns []
            "traces": [(10.0, 10.0, 11.0, 10.0, 0.25, _F, "N1")],
            "vias": [],
            "components": [("U1", (10.0, 5.0), 6.0, 4.0)],
            "board": (100.0, 100.0),
        },
    ),
    (
        "corridor_reversed_component_order",
        {
            # IDENTICAL geometry to ``corridor_two_components_one_channel``
            # with only the component LIST ORDER reversed.
            #
            # This is NOT a permutation-invariance case -- it is the witness
            # that permutation invariance FAILS.  ``_identify_channels`` only
            # considers pairs with ``j > i`` and computes
            # ``gap = cb.y_min - ca.y_max``; the guard ``gap > min_gap`` (with
            # min_gap > 0) already implies ``ca.y_max < cb.y_min``, so the
            # ``else`` arm of the ``if ca.y_max < cb.y_min`` test is
            # UNREACHABLE (defect 3 in the oracle header) and a channel is
            # found only when the earlier-listed component is the lower/left
            # one.  Reversing the list therefore yields ZERO channels and the
            # degenerate scores, not the same scores.
            "traces": [
                (8.0, 10.0, 8.0, 11.0, 0.25, _F, "N1"),
                (10.0, 10.0, 10.0, 11.0, 0.25, _F, "N2"),
                (12.0, 10.0, 12.0, 11.0, 0.25, _F, "N3"),
            ],
            "vias": [],
            "components": [("U2", (10.5, 16.0), 6.0, 4.0), ("U1", (10.5, 5.0), 6.0, 4.0)],
            "board": (100.0, 100.0),
        },
    ),
    (
        "corridor_identical_channels",
        {
            # Two component PAIRS producing value-identical channels.  The
            # kernel keys ``_assign_tracks_to_channels`` by ``id(ch)``, so the
            # duplicates must remain DISTINCT keys (see the oracle header) --
            # a Rust port keying by channel VALUE would collapse them and
            # change both scores.
            "traces": [
                (8.0, 10.0, 8.0, 11.0, 0.25, _F, "N1"),
                (10.0, 10.0, 10.0, 11.0, 0.25, _F, "N2"),
            ],
            "vias": [],
            "components": [
                ("U1", (10.5, 5.0), 6.0, 4.0),
                ("U2", (10.5, 16.0), 6.0, 4.0),
                ("U3", (10.5, 5.0), 6.0, 4.0),
                ("U4", (10.5, 16.0), 6.0, 4.0),
            ],
            "board": (100.0, 100.0),
        },
    ),
    (
        "corridor_track_order_permutation",
        {
            # Same three tracks as ``corridor_two_components_one_channel`` in a
            # different INPUT order.  Here invariance genuinely DOES hold (the
            # kernel sorts by ``t.x`` before pairing), so this is the positive
            # permutation case that pairs with the negative one above.
            "traces": [
                (12.0, 10.0, 12.0, 11.0, 0.25, _F, "N3"),
                (8.0, 10.0, 8.0, 11.0, 0.25, _F, "N1"),
                (10.0, 10.0, 10.0, 11.0, 0.25, _F, "N2"),
            ],
            "vias": [],
            "components": [("U1", (10.5, 5.0), 6.0, 4.0), ("U2", (10.5, 16.0), 6.0, 4.0)],
            "board": (100.0, 100.0),
        },
    ),
    (
        "nan_trace_coordinates",
        {
            "traces": [
                (0.0, 0.0, 10.0, 0.0, 0.25, _F, "NET1"),
                (NAN, 0.0, 20.0, 0.0, 0.25, _F, "NET1"),
                (20.0, 0.0, NAN, NAN, 0.25, _F, "NET1"),
            ],
            "vias": [((0.0, 0.0), "NET1", (_F, _B))],
            "components": [("U1", (NAN, 5.0), 6.0, 4.0), ("U2", (10.5, 16.0), 6.0, 4.0)],
            "board": (100.0, 100.0),
        },
    ),
    (
        "inf_trace_coordinates",
        {
            "traces": [
                (0.0, 0.0, 10.0, 0.0, 0.25, _F, "NET1"),
                (INF, 0.0, -INF, 0.0, 0.25, _F, "NET1"),
            ],
            "vias": [((INF, 0.0), "NET1", (_F, _B))],
            "components": [],
            "board": (INF, INF),
        },
    ),
    (
        "nan_board_dimensions",
        {
            "traces": [],
            "vias": [((1.0, 1.0), "GND", (_F, _B))],
            "components": [],
            "board": (NAN, NAN),
        },
    ),
    (
        "signed_zero_coordinates",
        {
            "traces": [
                (-0.0, -0.0, 0.0, 0.0, 0.25, _F, "NET1"),
                (0.0, -0.0, 1.0, 0.0, 0.25, _F, "NET1"),
            ],
            "vias": [((-0.0, -0.0), "GND", (_F, _B))],
            "components": [],
            "board": (0.0, 0.0),
        },
    ),
    (
        "unnamed_net_bucket",
        {
            # ``trace.net or "_unnamed"`` -- empty and None both fall into the
            # same bucket, and it must be the SAME bucket.
            "traces": [
                (0.0, 0.0, 10.0, 0.0, 0.25, _F, ""),
                (10.0, 0.0, 20.0, 0.0, 0.25, _F, None),
            ],
            "vias": [],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
    (
        "many_nets_insertion_order",
        {
            # Net iteration order is the parser's trace order and is part of
            # the contract (findings come out in that order).
            "traces": [
                (0.0, 0.0, 5.0, 0.0, 0.25, _F, "Z_LAST"),
                (0.0, 1.0, 5.0, 1.0, 0.25, _F, "A_FIRST"),
                (5.0, 0.0, 0.1, 0.0, 0.25, _F, "Z_LAST"),
                (5.0, 1.0, 0.1, 1.0, 0.25, _F, "A_FIRST"),
            ],
            "vias": [],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
    (
        "many_nets_insertion_order_swapped",
        {
            # The SAME four traces, first two swapped.  ``lint_all``'s output
            # ORDER must change even though the finding set does not -- this is
            # the case that catches a Rust port that sorts its net map.
            "traces": [
                (0.0, 1.0, 5.0, 1.0, 0.25, _F, "A_FIRST"),
                (0.0, 0.0, 5.0, 0.0, 0.25, _F, "Z_LAST"),
                (5.0, 0.0, 0.1, 0.0, 0.25, _F, "Z_LAST"),
                (5.0, 1.0, 0.1, 1.0, 0.25, _F, "A_FIRST"),
            ],
            "vias": [],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
    (
        "description_rounding_ties",
        {
            # Coordinates chosen so the ``:.2f`` formatting in ``description``
            # lands on an exact decimal tie: CPython rounds half-to-EVEN
            # (catalog B3), Rust's ``format!("{:.2}")`` rounds half-away.
            # 0.125 -> "0.12" in Python, "0.13" in Rust.
            "traces": [
                (0.125, 0.375, 10.125, 0.375, 0.25, _F, "NET1"),
                (10.125, 0.375, 0.175, 0.375, 0.25, _F, "NET1"),
            ],
            "vias": [((0.125, 0.375), "NET1", (_F, _B))],
            "components": [],
            "board": (100.0, 100.0),
        },
    ),
]

# ---------------------------------------------------------------------------
# The five real ``power_pcb_dataset`` corpus boards, with every cluster-F
# metric pinned as it was measured against the oracle at base commit
# ``15110feccc6ec9389f0777d3cff1ce9f81b11068``.
#
# Floats are pinned as ``float.hex()`` strings so the pin is exact and
# decimal-free.
#
# NOTE on ``via_total`` -- this is the ONE cluster-F number that the recorded
# ``human_reference.yaml`` baselines can corroborate for free: their
# ``via_count`` metric equals ``ViaCounts.total`` on all five boards.  None of
# the other cluster-F metrics appear in those baselines; see
# ``test_quality_metrics_oracle_pin.py`` and the PR body.
# ---------------------------------------------------------------------------
CORPUS_BOARDS: list[dict] = [
    {
        "board_id": "bitaxe_ultra",
        "pcb": "power_pcb_dataset/corpus/bitaxe_ultra/bitaxeUltra.kicad_pcb",
        "n_vias": 201,
        "n_traces": 933,
        "n_components": 137,
        "n_nets": 61,
        "via_signal": 118,
        "via_thermal": 0,
        "via_stitching": 83,
        "via_total": 201,
        "human_reference_via_count": 201.0,
        "consolidation_hex": "0x1.0000000000000p+0",
        "spread_hex": "0x0.0p+0",
        "lint_total": 302,
        "lint_by_type": {
            "hairpin": 67,
            "zigzag": 164,
            "isolated_via": 26,
            "single_net_detour": 45,
        },
    },
    {
        "board_id": "minimal",
        "pcb": "power_pcb_dataset/corpus/minimal/minimal_board.kicad_pcb",
        "n_vias": 0,
        "n_traces": 0,
        "n_components": 4,
        "n_nets": 0,
        "via_signal": 0,
        "via_thermal": 0,
        "via_stitching": 0,
        "via_total": 0,
        "human_reference_via_count": 0.0,
        "consolidation_hex": "0x1.0000000000000p+0",
        "spread_hex": "0x0.0p+0",
        "lint_total": 0,
        "lint_by_type": {},
    },
    {
        "board_id": "piantor_right",
        "pcb": "power_pcb_dataset/corpus/piantor_right/keyboard_pcb.kicad_pcb",
        "n_vias": 11,
        "n_traces": 237,
        "n_components": 36,
        "n_nets": 27,
        "via_signal": 7,
        "via_thermal": 0,
        "via_stitching": 4,
        "via_total": 11,
        "human_reference_via_count": 11.0,
        # The ONLY corpus board on which the corridor kernels return a
        # non-degenerate value, and only because its courtyard and trace
        # coordinate ranges overlap by accident (oracle header, defect 2).
        "consolidation_hex": "0x1.125f8a6956f77p-2",
        "spread_hex": "0x1.5da750d4e5fdcp+2",
        "lint_total": 61,
        "lint_by_type": {"hairpin": 5, "zigzag": 38, "single_net_detour": 18},
    },
    {
        "board_id": "rp2040_designguide",
        "pcb": "power_pcb_dataset/corpus/rp2040_designguide/RP2040-Guide.kicad_pcb",
        "n_vias": 32,
        "n_traces": 433,
        "n_components": 36,
        "n_nets": 56,
        "via_signal": 7,
        "via_thermal": 0,
        "via_stitching": 25,
        "via_total": 32,
        "human_reference_via_count": 32.0,
        "consolidation_hex": "0x1.0000000000000p+0",
        "spread_hex": "0x0.0p+0",
        "lint_total": 128,
        "lint_by_type": {
            "hairpin": 23,
            "zigzag": 68,
            "isolated_via": 12,
            "single_net_detour": 25,
        },
    },
    {
        "board_id": "temper",
        "pcb": "power_pcb_dataset/corpus/temper/temper.kicad_pcb",
        "n_vias": 0,
        "n_traces": 0,
        "n_components": 33,
        "n_nets": 0,
        "via_signal": 0,
        "via_thermal": 0,
        "via_stitching": 0,
        "via_total": 0,
        "human_reference_via_count": 0.0,
        "consolidation_hex": "0x1.0000000000000p+0",
        "spread_hex": "0x0.0p+0",
        "lint_total": 0,
        "lint_by_type": {},
    },
]

# ---------------------------------------------------------------------------
# Benchmark corpora (R1b).  These are STRICT SUBSETS of the corpora above --
# ``test_quality_metrics_oracle_pin.py::test_benchmark_corpus_is_covered_by_differential``
# proves it -- so every
# input ``benchmarks/perf_ab.py`` will time has been compared bit-for-bit by
# the differential first.
# ---------------------------------------------------------------------------
BENCH_DISTANCE_PAIRS = DISTANCE_PAIRS
BENCH_ANGLE_CASES = ANGLE_CASES
BENCH_SCENARIOS = SCENARIOS
BENCH_CORPUS_BOARDS = CORPUS_BOARDS


def random_distance_pairs(n: int, seed: int = 20260804) -> list[tuple[float, ...]]:
    """``n`` reproducible random point pairs over board-scale coordinates."""
    rng = random.Random(seed)
    return [tuple(rng.uniform(-150.0, 150.0) for _ in range(4)) for _ in range(n)]


def random_angle_cases(n: int, seed: int = 20260805) -> list[tuple[float, ...]]:
    """``n`` reproducible random ``_angle_between`` inputs."""
    rng = random.Random(seed)
    return [tuple(rng.uniform(-50.0, 50.0) for _ in range(8)) for _ in range(n)]


def random_trace_set(n: int, seed: int = 20260806) -> list[tuple[float, float, float, float]]:
    """``n`` reproducible random ``(sx, sy, ex, ey)`` segments.

    Roughly one segment in four is emitted head-to-tail from the previous
    one, so ``_order_traces`` sees a mix of connectable and disconnected
    input rather than an all-disconnected degenerate case.
    """
    rng = random.Random(seed)
    out: list[tuple[float, float, float, float]] = []
    cx, cy = 0.0, 0.0
    for _ in range(n):
        if out and rng.random() < 0.25:
            sx, sy = cx, cy
        else:
            sx, sy = rng.uniform(-50.0, 50.0), rng.uniform(-50.0, 50.0)
        ex, ey = sx + rng.uniform(-10.0, 10.0), sy + rng.uniform(-10.0, 10.0)
        out.append((sx, sy, ex, ey))
        cx, cy = ex, ey
    return out
