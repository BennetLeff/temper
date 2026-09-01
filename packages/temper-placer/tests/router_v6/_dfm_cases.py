"""Shared input corpus for the router_v6 post-route DFM cluster (Wave 4, cluster D).

**One fixture module, three consumers**: the differential suite (R1a,
``test_dfm_rust_differential.py``), the property/metamorphic suite (R1c/R1d,
``test_dfm_pbt.py``), and -- once Phase B lands -- the ``dfm-*`` arms of
``benchmarks/perf_ab.py`` (R1b) all draw their inputs from here.

That is deliberate and structural, not stylistic.  PR #714 passed its
differential at iterations ``[0, 1, 2, 8, 17, 100]`` and then failed CI on a
benchmark that ran 120 -- the benchmark exercised a parameter the behavioral
gate had never reached.  Sharing the corpus makes that class of gap
impossible to reintroduce: every tuple the benchmark times is, by
construction, a tuple the differential has already compared bit-for-bit.
``test_dfm_rust_differential.py::test_benchmark_corpus_is_covered_by_differential``
asserts the containment explicitly, so the property survives future edits to
either side.

The corpus is a *fixed* list, not a live random draw, so the perf A/B ratio is
comparable across runs and machines.  The randomized sweeps in the differential
are additional coverage layered on top, never a replacement.

No module in here imports the code under test -- it is pure data, so the
oracle arm and the Rust arm can each build their own object types from it.

Why the corpus is tuples and not ``RoutingResults``
---------------------------------------------------
Every kernel pinned in ``_dfm_py_oracle.py`` is reachable from plain scalars,
coordinate lists and layer-name strings.  Keeping the corpus at that level is
what lets the *same* rows feed a pyo3 boundary that will take ``f64`` slices,
without a ``RoutingResults`` (which is not a pyclass yet -- survey slice 1).
The differential builds the duck-typed via/path objects the oracle expects;
the Rust arm will take the scalars directly.
"""

from __future__ import annotations

import math
import random

__all__ = [
    "ANGLE_TRIPLES",
    "ANNULAR_AREAS",
    "ANNULAR_RING_VIAS",
    "BENCH_ANGLE_TRIPLES",
    "BENCH_ANNULAR_AREAS",
    "BENCH_ANNULAR_RING_VIAS",
    "BENCH_SEGMENT_RUNS",
    "BENCH_SPOKE_CASES",
    "BENCH_TEARDROP_CASES",
    "LAYER_NAMES",
    "LAYER_TRIPLES",
    "NET_NAMES",
    "PLANE_CONNECTIONS",
    "POUR_CASES",
    "RECT_CLAMPS",
    "SEGMENT_RUNS",
    "SEVERITY_CASES",
    "SPOKE_CASES",
    "TEARDROP_CASES",
    "random_angle_triples",
    "random_annular_vias",
    "random_segment_runs",
    "random_spoke_cases",
]

NAN = float("nan")
INF = float("inf")

# The exact threshold constants the reference branches on.  Landing *on* them
# (not merely near them) is what makes the branch-boundary mutants killable:
#   ring_width <= threshold + 1e-12   -- annular_ring_check._check_via
#   abs(sx - vx) < 1e-4               -- via_placement segment match
#   dist < 1e-9                       -- teardrop_generation direction guard
#   trace_width_mm < 0.2              -- acid_trap severity demotion
_FP_EPSILON = 1e-12
_VIA_MATCH_EPS = 1e-4
_TEARDROP_DIST_EPS = 1e-9

# The four canonical copper layers, in stackup order.  `_layer_is_between`
# and `_check_via`'s external/internal split are both indexed by these.
LAYER_NAMES: tuple[str, ...] = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")


# ---------------------------------------------------------------------------
# thermal_relief._is_power_net -- net-name strings
#
# The regex has three families of alternation: explicit ground variants, the
# `[A-Z]*GND` catch-all, and the rail names.  `\b` word boundaries mean the
# `+` in `+3V3` and the `_` in `VDD_CORE` behave very differently, and
# re.IGNORECASE means the catch-all matches lowercase too.
# ---------------------------------------------------------------------------
NET_NAMES: list[str] = [
    # explicit ground variants
    "GND",
    "PGND",
    "AGND",
    "DGND",
    "CGND",
    # `[A-Z]*GND` catch-all, and its lowercase form under IGNORECASE
    "XGND",
    "QUIETGND",
    "agnd",
    "Gnd",
    # rails
    "VCC",
    "VDD",
    "VEE",
    "VPP",
    "VBB",
    "VREF",
    "VBAT",
    "VDDIO",
    "AVDD",
    "DVDD",
    "VCCINT",
    "VCCO",
    "VDD_CORE",
    "POWER",
    "PVCC",
    "PVDD",
    # word-boundary edges: `_` is a word char, `+`/`-`/`/`/`.` are not
    "VDD_CORE_A",
    "A_VDD",
    "VDD-1",
    "1-VDD",
    "+3V3",
    "+5V",
    "+15V",
    "DC_BUS+",
    "DC_BUS-",
    "SW_NODE",
    "AC_L",
    "AC_N",
    "PE",
    "NET_VCC_FILT",
    "VCC1",  # `VCC1` has no boundary after VCC -> no match
    "1VCC",
    "MYVCC",
    "VCC.A",
    "VCC/2",
    # plain signal nets that must NOT match
    "SDA",
    "SCL",
    "USB_DP",
    "USB_DM",
    "CLK",
    "N$1",
    "",
    " ",
    "gnd_but_not_a_word_boundaryGND",
]

# ---------------------------------------------------------------------------
# thermal_relief._connects_to_power_plane
#   (net_name, from_layer, to_layer, plane_layers, plane_nets)
# ---------------------------------------------------------------------------
_PL = ("In1.Cu", "In2.Cu")
_PN = ("GND", "VCC", "+3V3", "DC_BUS+")
PLANE_CONNECTIONS: list[tuple[str, str, str, tuple[str, ...], tuple[str, ...]]] = [
    ("GND", "F.Cu", "In1.Cu", _PL, _PN),  # to_layer hits
    ("GND", "In1.Cu", "B.Cu", _PL, _PN),  # from_layer hits
    ("GND", "F.Cu", "B.Cu", _PL, _PN),  # neither hits
    ("GND", "In1.Cu", "In2.Cu", _PL, _PN),  # both hit
    ("SDA", "F.Cu", "In1.Cu", _PL, _PN),  # net not registered -> early False
    ("VCC", "In2.Cu", "In2.Cu", _PL, _PN),  # same layer both sides
    ("+3V3", "F.Cu", "In1.Cu", _PL, _PN),
    ("DC_BUS+", "In2.Cu", "B.Cu", _PL, _PN),
    ("GND", "F.Cu", "In1.Cu", (), _PN),  # empty plane_layers
    ("GND", "F.Cu", "In1.Cu", _PL, ()),  # empty plane_nets -> early False
    ("GND", "", "", _PL, _PN),  # empty layer names
    ("GND", "in1.cu", "b.cu", _PL, _PN),  # case-sensitive: no match
]

# ---------------------------------------------------------------------------
# thermal_relief._generate_spoke_segments
#   (cx, cy, pad_w, pad_h, spoke_count, spoke_width, clearance_gap)
#
# `angle = 2.0 * math.pi * i / spoke_count` is a THREE-op left-to-right chain
# (B7): reassociating it changes 27.27% of (i, count) pairs (measured).
# `pad_radius = math.hypot(pw/2, ph/2)` is CPython's Dekker hypot (B4).
# `spoke_length = max(gap*2, width*2)` is CPython `max` (B5).
# ---------------------------------------------------------------------------
SPOKE_CASES: list[tuple[float, float, float, float, int, float, float]] = [
    # the production default: 4 spokes, 0.6mm via pad, 10mil width/gap
    (0.0, 0.0, 0.6, 0.6, 4, 0.254, 0.254),
    (12.5, -7.25, 0.6, 0.6, 4, 0.254, 0.254),
    (100.0, 100.0, 0.6, 0.6, 4, 0.254, 0.254),
    # spoke counts: 2 (the minimum the caller enforces), odd, large
    (0.0, 0.0, 0.6, 0.6, 2, 0.254, 0.254),
    (0.0, 0.0, 0.6, 0.6, 3, 0.254, 0.254),
    (0.0, 0.0, 0.6, 0.6, 5, 0.254, 0.254),
    (0.0, 0.0, 0.6, 0.6, 8, 0.254, 0.254),
    (0.0, 0.0, 0.6, 0.6, 12, 0.254, 0.254),
    (0.0, 0.0, 0.6, 0.6, 64, 0.254, 0.254),
    # spoke_count == 1 and 0: below the caller's guard, but the KERNEL
    # accepts them (0 -> empty list, 1 -> a single spoke at angle 0.0).
    (0.0, 0.0, 0.6, 0.6, 1, 0.254, 0.254),
    (0.0, 0.0, 0.6, 0.6, 0, 0.254, 0.254),
    # which arm of `max(gap*2, width*2)` wins
    (0.0, 0.0, 0.6, 0.6, 4, 1.0, 0.1),  # width arm
    (0.0, 0.0, 0.6, 0.6, 4, 0.1, 1.0),  # gap arm
    (0.0, 0.0, 0.6, 0.6, 4, 0.5, 0.5),  # exact tie -> `max` keeps the FIRST
    # rectangular (non-square) pads -- hypot with unequal legs
    (0.0, 0.0, 2.0, 0.5, 4, 0.254, 0.254),
    (0.0, 0.0, 0.5, 2.0, 4, 0.254, 0.254),
    # degenerate / zero-area pads
    (0.0, 0.0, 0.0, 0.0, 4, 0.254, 0.254),
    (0.0, 0.0, 0.0, 1.0, 4, 0.254, 0.254),
    (0.0, 0.0, 1.0, 0.0, 4, 0.254, 0.254),
    # negative pad extents: hypot takes |x|, so the radius stays positive
    (0.0, 0.0, -1.0, -1.0, 4, 0.254, 0.254),
    # signed zeros in the centre
    (-0.0, -0.0, 0.6, 0.6, 4, 0.254, 0.254),
    (0.0, -0.0, 0.6, 0.6, 4, 0.254, 0.254),
    # magnitudes where hypot's compensation actually matters
    (0.0, 0.0, 1e-300, 1e-300, 4, 0.254, 0.254),
    (0.0, 0.0, 1e300, 1e300, 4, 0.254, 0.254),
    (0.0, 0.0, 5e-324, 5e-324, 4, 1e-300, 1e-300),  # denormal band (B8)
    (1e15, 1e15, 0.6, 0.6, 4, 0.254, 0.254),  # cx dominates start_r*dx
    # NaN / inf in every slot
    (NAN, 0.0, 0.6, 0.6, 4, 0.254, 0.254),
    (0.0, NAN, 0.6, 0.6, 4, 0.254, 0.254),
    (0.0, 0.0, NAN, 0.6, 4, 0.254, 0.254),
    (0.0, 0.0, 0.6, NAN, 4, 0.254, 0.254),
    (0.0, 0.0, 0.6, 0.6, 4, NAN, 0.254),  # NaN in max()'s SECOND arg
    (0.0, 0.0, 0.6, 0.6, 4, 0.254, NAN),  # NaN in max()'s FIRST arg
    (INF, 0.0, 0.6, 0.6, 4, 0.254, 0.254),
    (0.0, 0.0, INF, 0.6, 4, 0.254, 0.254),
    (0.0, 0.0, 0.6, 0.6, 4, INF, 0.254),
    (0.0, 0.0, 0.6, 0.6, 4, 0.254, -INF),
    # integer inputs (int/float divergence in the signature comparator)
    (0, 0, 1, 1, 4, 1, 1),
]

# ---------------------------------------------------------------------------
# thermal_relief._clamp_to_board_outline, RECTANGULAR arm only
#   (x, y, origin_x, origin_y, board_w, board_h)
#
# The polygonal arm is GEOS (B6) and is EXCLUDED from the migration scope
# (survey spike S1).  See the oracle header.
#
# `max(x_min, min(x, x_max))` is CPython min-then-max (B5): measured, a NaN
# `x` clamps to `x_min`, NOT to NaN and NOT to `x_max`.
# ---------------------------------------------------------------------------
RECT_CLAMPS: list[tuple[float, float, float, float, float, float]] = [
    (5.0, 5.0, 0.0, 0.0, 10.0, 10.0),  # inside
    (-5.0, 5.0, 0.0, 0.0, 10.0, 10.0),  # left of x_min
    (15.0, 5.0, 0.0, 0.0, 10.0, 10.0),  # right of x_max
    (5.0, -5.0, 0.0, 0.0, 10.0, 10.0),  # below y_min
    (5.0, 15.0, 0.0, 0.0, 10.0, 10.0),  # above y_max
    (-5.0, 15.0, 0.0, 0.0, 10.0, 10.0),  # both axes clamp
    (0.0, 0.0, 0.0, 0.0, 10.0, 10.0),  # exactly on the min corner
    (10.0, 10.0, 0.0, 0.0, 10.0, 10.0),  # exactly on the max corner
    (5.0, 5.0, 12.0, -3.5, 40.0, 25.0),  # non-zero origin
    (-0.0, -0.0, 0.0, 0.0, 10.0, 10.0),  # signed zero: max(0.0, -0.0) is 0.0
    (0.0, 0.0, -0.0, -0.0, 10.0, 10.0),  # signed zero in the ORIGIN
    (5.0, 5.0, 0.0, 0.0, 0.0, 0.0),  # zero-area board: x_min == x_max
    (5.0, 5.0, 0.0, 0.0, -10.0, -10.0),  # inverted board: x_max < x_min
    # NaN point -- position-dependent min/max is the whole point
    (NAN, 5.0, 0.0, 0.0, 10.0, 10.0),
    (5.0, NAN, 0.0, 0.0, 10.0, 10.0),
    (NAN, NAN, 0.0, 0.0, 10.0, 10.0),
    (INF, 5.0, 0.0, 0.0, 10.0, 10.0),
    (-INF, 5.0, 0.0, 0.0, 10.0, 10.0),
    # NaN / inf board dims and origin -> the isfinite guards return the point
    (5.0, 5.0, 0.0, 0.0, NAN, 10.0),
    (5.0, 5.0, 0.0, 0.0, 10.0, NAN),
    (5.0, 5.0, 0.0, 0.0, INF, 10.0),
    (5.0, 5.0, NAN, 0.0, 10.0, 10.0),
    (5.0, 5.0, 0.0, INF, 10.0, 10.0),
    # magnitude where ox + width rounds
    (1.0, 1.0, 1e16, 0.0, 1.0, 1.0),
    (0, 0, 0, 0, 10, 10),  # integers
]

# ---------------------------------------------------------------------------
# acid_trap_detection._calculate_angle -- (p1x, p1y, p2x, p2y, p3x, p3y)
#
# `mag = math.sqrt(v[0]**2 + v[1]**2)` is sqrt-of-pow, NOT hypot and NOT x*x
# (B4 + B7).  `max(-1.0, min(1.0, cos))` is CPython min-then-max (B5) --
# measured, NaN clamps to +1.0, so the kernel returns acos(1.0) == 0.0 and
# NOT the 180.0 degenerate fallback.  `round(deg, 9)` is round-half-EVEN (B3)
# and is load-bearing at the 60-degree severity boundary.
# ---------------------------------------------------------------------------
_S3 = math.sqrt(3.0) / 2.0
ANGLE_TRIPLES: list[tuple[float, float, float, float, float, float]] = [
    # exact right angle
    (1.0, 0.0, 0.0, 0.0, 0.0, 1.0),
    (0.0, 1.0, 0.0, 0.0, 1.0, 0.0),  # reversed -- must be bit-identical
    # straight through (180) and doubled back (0)
    (-1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
    (1.0, 0.0, 0.0, 0.0, 1.0, 0.0),
    # 45 degrees
    (1.0, 0.0, 0.0, 0.0, 1.0, 1.0),
    (1.0, 1.0, 0.0, 0.0, 1.0, 0.0),
    # THE B3 CASE: an exact 60-degree vertex.  acos/degrees gives
    # 59.99999999999999; round(.., 9) gives 60.0.  That flips
    # `_classify_severity` from "medium" to "low".
    (1.0, 0.0, 0.0, 0.0, 0.5, _S3),
    (0.5, _S3, 0.0, 0.0, 1.0, 0.0),
    # just either side of the 45-degree severity boundary
    (1.0, 0.0, 0.0, 0.0, 1.0, 1.0000001),
    (1.0, 0.0, 0.0, 0.0, 1.0, 0.9999999),
    # 30 and 120 degrees
    (1.0, 0.0, 0.0, 0.0, _S3, 0.5),
    (1.0, 0.0, 0.0, 0.0, -0.5, _S3),
    # near-collinear: cos_angle overshoots 1.0 and the clamp fires
    (1.0, 0.0, 0.0, 0.0, 1e16, 1e-16),
    (-1e16, 0.0, 0.0, 0.0, 1e16, 1e-300),
    # degenerate: v1 or v2 is the zero vector -> early 180.0
    (0.0, 0.0, 0.0, 0.0, 1.0, 0.0),
    (1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    (5.0, 5.0, 5.0, 5.0, 9.0, 2.0),  # p1 == p2 exactly
    # signed zeros: -0.0 - 0.0 is -0.0, and (-0.0)**2 is 0.0
    (-0.0, -0.0, 0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, -0.0, -0.0, 1.0, 0.0),
    # magnitudes where sqrt(x**2+y**2) provably differs from hypot
    (1e-200, 1e-200, 0.0, 0.0, 1.0, 0.0),
    (1e200, 1e200, 0.0, 0.0, 1.0, 1.0),
    (5e-324, 5e-324, 0.0, 0.0, 1.0, 1.0),  # denormal band (B8)
    # OVERFLOW: x**2 overflows to +inf where hypot would not.  mag becomes
    # inf, `mag1 == 0` is False, cos becomes 0.0/inf or nan -> pinned.
    (1e200, 1e200, 0.0, 0.0, 1e200, -1e200),
    (1.7976931348623157e308, 0.0, 0.0, 0.0, 0.0, 1.0),
    # board-scale realistic vertices
    (10.0, 10.0, 12.0, 10.0, 12.0, 14.0),
    (25.4, 12.7, 25.4, 15.24, 27.94, 15.24),
    (0.1, 0.2, 0.3, 0.4, 0.5, 0.6),
    # NaN in each slot
    (NAN, 0.0, 0.0, 0.0, 1.0, 0.0),
    (0.0, NAN, 0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, NAN, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, NAN, 1.0, 0.0),
    (0.0, 0.0, 0.0, 0.0, NAN, 0.0),
    (0.0, 0.0, 0.0, 0.0, 0.0, NAN),
    # inf in each vector -- inf - 0.0 is inf, inf**2 is inf, cos is nan
    (INF, 0.0, 0.0, 0.0, 1.0, 0.0),
    (-INF, 0.0, 0.0, 0.0, 1.0, 0.0),
    (INF, INF, 0.0, 0.0, 1.0, 0.0),
    (INF, 0.0, 0.0, 0.0, INF, 0.0),
    (INF, 0.0, INF, 0.0, 1.0, 0.0),  # inf - inf -> nan
    # integers
    (1, 0, 0, 0, 0, 1),
]

# ---------------------------------------------------------------------------
# acid_trap_detection._classify_severity -- (angle, trace_width_mm)
# ---------------------------------------------------------------------------
SEVERITY_CASES: list[tuple[float, float]] = [
    # each band, at the default 0.2mm width (no demotion: `< 0.2` is False)
    (10.0, 0.2),
    (44.999999999, 0.2),
    (45.0, 0.2),  # exactly ON the boundary -> "medium"
    (50.0, 0.2),
    (59.999999999, 0.2),
    (60.0, 0.2),  # exactly ON the boundary -> "low"
    (89.0, 0.2),
    (180.0, 0.2),
    # narrow traces -> one-level demotion
    (10.0, 0.1),
    (50.0, 0.1),
    (70.0, 0.1),
    (10.0, math.nextafter(0.2, 0.0)),  # one ulp under the demotion boundary
    (10.0, math.nextafter(0.2, 1.0)),  # one ulp over
    (10.0, 0.0),  # zero width -> demotes
    (10.0, -0.0),  # signed zero: `-0.0 < 0` is False -> demotes
    # non-finite / negative widths -> `return base` with NO demotion
    (10.0, -1.0),
    (10.0, NAN),
    (10.0, INF),
    (10.0, -INF),
    # non-finite angle: `NAN < 45` and `NAN < 60` are both False -> "low"
    (NAN, 0.2),
    (NAN, 0.1),
    (INF, 0.2),
    (-INF, 0.2),
    (-1.0, 0.2),  # negative angle -> "high"
    (10, 1),  # integers
]

# ---------------------------------------------------------------------------
# power_plane.generate_power_pours strip partition
#   (origin_x, origin_y, board_w, board_h, n_domains, isolation_gap_mm)
#
# `strip_x_min = x_min + i * (strip_width + gap)` -- the addition is INSIDE
# the multiply (B7).  Measured on this base: the last strip's x_max differs
# from the board's x_max in 34.15% of random configurations, so "the pours
# tile the board" is NOT a bit-exact invariant and is not asserted as one.
# ---------------------------------------------------------------------------
POUR_CASES: list[tuple[float, float, float, float, int, float]] = [
    (0.0, 0.0, 100.0, 80.0, 3, 0.3),  # the production default
    (0.0, 0.0, 100.0, 80.0, 1, 0.3),  # n == 1 -> total_gap is 0.0
    (0.0, 0.0, 100.0, 80.0, 2, 0.3),
    (0.0, 0.0, 100.0, 80.0, 8, 0.3),
    (0.0, 0.0, 100.0, 80.0, 3, 0.0),  # zero gap -> strips abut exactly
    (0.0, 0.0, 100.0, 80.0, 3, 0.25),  # dyadic gap
    (0.0, 0.0, 128.0, 64.0, 4, 0.5),  # everything a power of two
    (12.5, -7.25, 43.75, 21.5, 3, 0.3),  # off-origin
    (-50.0, -50.0, 100.0, 100.0, 3, 0.3),  # negative origin
    (0.0, 0.0, 1.0, 1.0, 3, 0.3),  # gaps eat 90% of the board
    (0.0, 0.0, 0.9, 1.0, 3, 0.3),  # strip_width == 0.0 -> raises
    (0.0, 0.0, 0.5, 1.0, 3, 0.3),  # strip_width < 0 -> raises
    (0.0, 0.0, 100.0, 80.0, 3, -0.1),  # negative gap -> raises
    (0.0, 0.0, 0.0, 0.0, 3, 0.0),  # zero-area board -> raises
    (0.0, 0.0, 1e-300, 1.0, 2, 0.0),  # denormal-band strip
    (0.0, 0.0, 1e300, 1.0, 3, 0.3),
    (1e16, 0.0, 1.0, 1.0, 2, 0.0),  # x_min + i*(..) loses the strip entirely
    (0.0, 0.0, NAN, 80.0, 3, 0.3),  # NaN width: `strip_width <= 0` is False
    (0.0, 0.0, INF, 80.0, 3, 0.3),
    (0.0, 0.0, 100.0, 80.0, 3, NAN),  # NaN gap: `gap < 0` is False
    (NAN, 0.0, 100.0, 80.0, 3, 0.3),
    (-0.0, -0.0, 100.0, 80.0, 3, 0.3),
    (0, 0, 100, 80, 3, 0),  # integers
]

# ---------------------------------------------------------------------------
# copper_balance._via_annular_area -- (diameter, drill)
#
# `math.pi * (r_pad * r_pad - r_hole * r_hole)` -- here it IS `r * r`, not
# `pow` (B7).  Do not unify with `_calculate_angle`'s `** 2`.
# ---------------------------------------------------------------------------
ANNULAR_AREAS: list[tuple[float, float]] = [
    (0.6, 0.3),  # the production default
    (0.8, 0.4),
    (0.45, 0.2),
    (1.0, 0.0),  # zero drill -> the `if drill > 0.0` arm is skipped
    (1.0, -0.0),  # signed-zero drill: `-0.0 or 0.0` is 0.0 (falsy!)
    (1.0, 1.0),  # drill == diameter -> 0.0
    (1.0, 1.5),  # drill > diameter -> 0.0
    (math.nextafter(1.0, 2.0), 1.0),  # one ulp above the drill
    (1.0, math.nextafter(1.0, 0.0)),  # one ulp below the diameter
    (0.0, 0.0),  # zero pad -> 0.0
    (-1.0, 0.5),  # negative diameter -> 0.0
    (1.0, -0.5),  # negative drill -> `r_hole` stays 0.0
    (1e-300, 1e-301),  # denormal band (B8)
    (5e-324, 0.0),
    (1e300, 1e299),  # r_pad*r_pad overflows -> inf
    (1e200, 1e199),
    (NAN, 0.3),
    (0.6, NAN),
    (NAN, NAN),
    (INF, 0.3),
    (0.6, INF),
    (-INF, 0.3),
    (1, 0),  # integers
]

# ---------------------------------------------------------------------------
# copper_balance._layer_is_between -- (from_layer, to_layer, candidate)
# ---------------------------------------------------------------------------
LAYER_TRIPLES: list[tuple[str, str, str]] = [
    ("F.Cu", "B.Cu", "In1.Cu"),  # strictly between
    ("F.Cu", "B.Cu", "In2.Cu"),
    ("B.Cu", "F.Cu", "In1.Cu"),  # reversed -> same answer
    ("F.Cu", "B.Cu", "F.Cu"),  # candidate == an endpoint -> False
    ("F.Cu", "B.Cu", "B.Cu"),
    ("F.Cu", "In1.Cu", "In2.Cu"),  # outside the span
    ("F.Cu", "In2.Cu", "In1.Cu"),
    ("In1.Cu", "In2.Cu", "F.Cu"),
    ("F.Cu", "F.Cu", "F.Cu"),  # degenerate span
    ("In1.Cu", "In1.Cu", "In2.Cu"),
    ("F.Cu", "B.Cu", "F.SilkS"),  # unknown candidate -> ValueError -> False
    ("F.Cu", "Edge.Cuts", "In1.Cu"),  # unknown endpoint -> False
    ("", "", ""),
    ("f.cu", "b.cu", "in1.cu"),  # case-sensitive: unknown -> False
]

# ---------------------------------------------------------------------------
# copper_balance._segment_run_copper_area
#   (segments, layer_name, width_mm) with segments as (x, y, layer) triples
#
# `seg_length = math.hypot(x2 - x1, y2 - y1)` is CPython Dekker hypot (B4).
# The `copper_area += seg_length * width_mm` accumulation order is part of
# the contract (B7) -- summing in any other order changes the last bits.
# ---------------------------------------------------------------------------
SEGMENT_RUNS: list[tuple[tuple[tuple[float, float, str], ...], str, float]] = [
    # a plain 3-segment run entirely on F.Cu
    (
        (
            (0.0, 0.0, "F.Cu"),
            (10.0, 0.0, "F.Cu"),
            (10.0, 10.0, "F.Cu"),
            (20.0, 10.0, "F.Cu"),
        ),
        "F.Cu",
        0.25,
    ),
    # same run, asking about a layer it never touches -> 0.0
    (
        (
            (0.0, 0.0, "F.Cu"),
            (10.0, 0.0, "F.Cu"),
            (10.0, 10.0, "F.Cu"),
        ),
        "B.Cu",
        0.25,
    ),
    # a layer-changing run: only the F.Cu-labelled segments count.  Note the
    # label comes from segments[i], so the LAST vertex's layer never counts.
    (
        (
            (0.0, 0.0, "F.Cu"),
            (5.0, 0.0, "In1.Cu"),
            (5.0, 5.0, "In1.Cu"),
            (10.0, 5.0, "B.Cu"),
        ),
        "F.Cu",
        0.2,
    ),
    (
        (
            (0.0, 0.0, "F.Cu"),
            (5.0, 0.0, "In1.Cu"),
            (5.0, 5.0, "In1.Cu"),
            (10.0, 5.0, "B.Cu"),
        ),
        "In1.Cu",
        0.2,
    ),
    (
        (
            (0.0, 0.0, "F.Cu"),
            (5.0, 0.0, "In1.Cu"),
            (5.0, 5.0, "In1.Cu"),
            (10.0, 5.0, "B.Cu"),
        ),
        "B.Cu",
        0.2,
    ),  # the trailing B.Cu vertex contributes NOTHING
    # empty and single-vertex runs -> `range(-1)` / `range(0)` -> 0.0
    ((), "F.Cu", 0.25),
    (((0.0, 0.0, "F.Cu"),), "F.Cu", 0.25),
    # a zero-length segment (duplicate vertex) contributes 0.0 * width
    (((0.0, 0.0, "F.Cu"), (0.0, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu")), "F.Cu", 0.25),
    # zero and negative widths
    (((0.0, 0.0, "F.Cu"), (3.0, 4.0, "F.Cu")), "F.Cu", 0.0),
    (((0.0, 0.0, "F.Cu"), (3.0, 4.0, "F.Cu")), "F.Cu", -0.25),
    # accumulation order: many short segments summed left to right
    (tuple((float(i), 0.0, "F.Cu") for i in range(33)), "F.Cu", 0.1),
    (tuple((float(i) * 0.1, float(i) * 0.1, "F.Cu") for i in range(65)), "F.Cu", 0.0254),
    # magnitudes where hypot's compensation matters
    (((0.0, 0.0, "F.Cu"), (1e-300, 1e-300, "F.Cu")), "F.Cu", 1.0),
    (((0.0, 0.0, "F.Cu"), (1e300, 1e300, "F.Cu")), "F.Cu", 1.0),
    (((0.0, 0.0, "F.Cu"), (5e-324, 5e-324, "F.Cu")), "F.Cu", 1.0),  # denormal
    # NaN / inf coordinates poison the running sum irreversibly
    (((0.0, 0.0, "F.Cu"), (NAN, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu")), "F.Cu", 0.25),
    (((0.0, 0.0, "F.Cu"), (INF, 0.0, "F.Cu"), (1.0, 0.0, "F.Cu")), "F.Cu", 0.25),
    (((INF, 0.0, "F.Cu"), (INF, 0.0, "F.Cu")), "F.Cu", 0.25),  # inf-inf -> nan
    (((0.0, 0.0, "F.Cu"), (3.0, 4.0, "F.Cu")), "F.Cu", NAN),
    (((0.0, 0.0, "F.Cu"), (3.0, 4.0, "F.Cu")), "F.Cu", INF),
    # signed zeros
    (((-0.0, -0.0, "F.Cu"), (0.0, 0.0, "F.Cu")), "F.Cu", 1.0),
    # integers
    (((0, 0, "F.Cu"), (3, 4, "F.Cu")), "F.Cu", 1),
]

# ---------------------------------------------------------------------------
# annular_ring_check._check_via
#   (diameter, drill, from_layer, to_layer, via_type, min_ring, microvia_ring)
#
# `ring_width <= threshold + 1e-12` -- the epsilon is part of the contract.
# `via_type == "microvia"` overrides the layer-derived threshold entirely.
# ---------------------------------------------------------------------------
_MV = 0.025
ANNULAR_RING_VIAS: list[tuple[float, float, str, str, str | None, float, float]] = [
    # external via, comfortably passing / failing
    (0.6, 0.3, "F.Cu", "B.Cu", None, 0.05, _MV),
    (0.35, 0.3, "F.Cu", "B.Cu", None, 0.05, _MV),
    # exactly ON the threshold, and one ulp either side of `threshold + eps`
    (0.4, 0.3, "F.Cu", "B.Cu", None, 0.05, _MV),  # ring == 0.05 exactly
    (0.4 + 2e-12, 0.3, "F.Cu", "B.Cu", None, 0.05, _MV),
    (0.4 + 4e-12, 0.3, "F.Cu", "B.Cu", None, 0.05, _MV),
    # internal-only via -> threshold is min_ring * 0.5
    (0.6, 0.3, "In1.Cu", "In2.Cu", None, 0.05, _MV),
    (0.35, 0.3, "In1.Cu", "In2.Cu", None, 0.05, _MV),
    (0.35, 0.3, "In1.Cu", "In2.Cu", None, 0.1, _MV),
    # one external endpoint is enough
    (0.35, 0.3, "F.Cu", "In2.Cu", None, 0.05, _MV),
    (0.35, 0.3, "In1.Cu", "B.Cu", None, 0.05, _MV),
    # microvia override beats BOTH layer arms
    (0.15, 0.1, "F.Cu", "In1.Cu", "microvia", 0.05, _MV),
    (0.15, 0.1, "In1.Cu", "In2.Cu", "microvia", 0.05, _MV),
    (0.14, 0.1, "F.Cu", "In1.Cu", "microvia", 0.05, _MV),
    (0.15, 0.1, "F.Cu", "In1.Cu", "buried", 0.05, _MV),  # not "microvia"
    (0.15, 0.1, "F.Cu", "In1.Cu", "MICROVIA", 0.05, _MV),  # case-sensitive
    # drill guards: <= 0, NaN
    (0.6, 0.0, "F.Cu", "B.Cu", None, 0.05, _MV),
    (0.6, -0.1, "F.Cu", "B.Cu", None, 0.05, _MV),
    (0.6, -0.0, "F.Cu", "B.Cu", None, 0.05, _MV),  # -0.0 <= 0.0 -> skipped
    (0.6, NAN, "F.Cu", "B.Cu", None, 0.05, _MV),
    (NAN, 0.3, "F.Cu", "B.Cu", None, 0.05, _MV),
    # NaN threshold guard (NaN min_ring on an external via)
    (0.6, 0.3, "F.Cu", "B.Cu", None, NAN, _MV),
    (0.6, 0.3, "In1.Cu", "In2.Cu", None, NAN, _MV),  # NaN * 0.5 is NaN
    (0.6, 0.3, "F.Cu", "B.Cu", "microvia", 0.05, NAN),  # NaN microvia ring
    # inf is NOT guarded -- these are the pinned surprises
    (INF, 0.3, "F.Cu", "B.Cu", None, 0.05, _MV),  # ring == inf -> no violation
    (0.6, INF, "F.Cu", "B.Cu", None, 0.05, _MV),  # ring == -inf -> violation
    (0.6, 0.3, "F.Cu", "B.Cu", None, INF, _MV),  # threshold inf -> violation
    (0.6, 0.3, "F.Cu", "B.Cu", None, -INF, _MV),
    # unknown / empty layer names -> internal (half) threshold
    (0.35, 0.3, "", "", None, 0.05, _MV),
    (0.35, 0.3, "F.SilkS", "Edge.Cuts", None, 0.05, _MV),
    (0.35, 0.3, "f.cu", "b.cu", None, 0.05, _MV),  # case-sensitive
    # denormal band (B8)
    (1e-300, 1e-310, "F.Cu", "B.Cu", None, 1e-320, _MV),
    (1, 0, "F.Cu", "B.Cu", None, 0, _MV),  # integers
]

# ---------------------------------------------------------------------------
# teardrop_generation._generate_via_teardrop
#   (via_x, via_y, diameter, from_layer, to_layer,
#    path_layer, coords, width_mm, length_ratio)
#
# The `nearest_idx` argmin uses CPython `min(..., key=...)`, which keeps the
# FIRST minimum on a tie (measured).  `math.hypot` is the Dekker hypot (B4).
# ---------------------------------------------------------------------------
_STRAIGHT = ((0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0))
_BEND = ((0.0, 0.0), (2.0, 0.0), (2.0, 2.0))
TEARDROP_CASES: list[tuple] = [
    # ordinary: via on the F.Cu path, trace heads +x
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, 0.25, 0.5),
    (2.0, 0.0, 0.6, "F.Cu", "In1.Cu", "F.Cu", _STRAIGHT, 0.25, 0.5),
    # via nearest the LAST coordinate -> the `nearest_idx - 1` fallback
    (3.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, 0.25, 0.5),
    (10.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, 0.25, 0.5),
    # EXACT argmin tie: equidistant from coords[0] and coords[1].
    # CPython keeps the FIRST -> nearest_idx == 0.
    (0.5, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, 0.25, 0.5),
    (1.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", ((0.0, 0.0), (2.0, 0.0)), 0.25, 0.5),
    # bends
    (2.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _BEND, 0.25, 0.5),
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _BEND, 0.25, 0.5),
    # layer gate: path_layer must be one of the via's two layers
    (0.0, 0.0, 0.6, "In1.Cu", "In2.Cu", "F.Cu", _STRAIGHT, 0.25, 0.5),
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", None, _STRAIGHT, 0.25, 0.5),  # RoutePath3D
    # `via.diameter >= trace_width * 1.2` gate, at and around the boundary
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, 0.5, 0.5),  # exactly ==
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, 0.51, 0.5),  # just over
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, 0.49, 0.5),
    # which arm of `min(diameter*0.6, trace_width*2.0)` wins
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, 0.1, 0.5),  # width arm
    (0.0, 0.0, 2.0, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, 1.0, 0.5),  # dia arm
    (0.0, 0.0, 1.0, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, 0.3, 0.5),  # exact tie
    # length_ratio at both clamp ends
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, 0.25, 0.1),
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, 0.25, 1.0),
    # coincident points -> `dist < 1e-9` -> None
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", ((0.0, 0.0), (0.0, 0.0)), 0.25, 0.5),
    # AT the 1e-9 direction boundary and one ulp either side
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", ((0.0, 0.0), (1e-9, 0.0)), 0.25, 0.5),
    (
        0.0,
        0.0,
        0.6,
        "F.Cu",
        "B.Cu",
        "F.Cu",
        ((0.0, 0.0), (math.nextafter(1e-9, 0.0), 0.0)),
        0.25,
        0.5,
    ),
    (
        0.0,
        0.0,
        0.6,
        "F.Cu",
        "B.Cu",
        "F.Cu",
        ((0.0, 0.0), (math.nextafter(1e-9, 1.0), 0.0)),
        0.25,
        0.5,
    ),
    # too-short coordinate list -> None
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", ((0.0, 0.0),), 0.25, 0.5),
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", (), 0.25, 0.5),
    # diameter guards
    (0.0, 0.0, 0.0, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, 0.25, 0.5),
    (0.0, 0.0, -0.6, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, 0.25, 0.5),
    (0.0, 0.0, NAN, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, 0.25, 0.5),
    (0.0, 0.0, INF, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, 0.25, 0.5),
    # trace-width guards: NaN and +inf return None; -inf clamps to 0.0
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, NAN, 0.5),
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, INF, 0.5),
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, -INF, 0.5),
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, -1.0, 0.5),
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, -0.0, 0.5),
    # NaN in a path coordinate -- the argmin key becomes NaN
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", ((NAN, 0.0), (1.0, 0.0)), 0.25, 0.5),
    (0.0, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", ((1.0, 0.0), (NAN, 0.0)), 0.25, 0.5),
    # NaN via position
    (NAN, 0.0, 0.6, "F.Cu", "B.Cu", "F.Cu", _STRAIGHT, 0.25, 0.5),
    # denormal band (B8)
    (0.0, 0.0, 1e-300, "F.Cu", "B.Cu", "F.Cu", ((0.0, 0.0), (1e-300, 0.0)), 1e-301, 0.5),
    # board-scale
    (
        25.4,
        12.7,
        0.6,
        "F.Cu",
        "B.Cu",
        "F.Cu",
        ((20.0, 12.7), (25.4, 12.7), (30.0, 12.7)),
        0.254,
        0.5,
    ),
]

# ---------------------------------------------------------------------------
# Benchmark corpora (R1b).  These are STRICT SUBSETS of the corpora above --
# `test_benchmark_corpus_is_covered_by_differential` proves it -- so every
# tuple `benchmarks/perf_ab.py` will time has been compared bit-for-bit
# first.  They are the whole corpus today; keeping the names separate is what
# makes a future "just time these five rows" edit provably safe.
# ---------------------------------------------------------------------------
BENCH_ANGLE_TRIPLES = ANGLE_TRIPLES
BENCH_SPOKE_CASES = SPOKE_CASES
BENCH_ANNULAR_AREAS = ANNULAR_AREAS
BENCH_ANNULAR_RING_VIAS = ANNULAR_RING_VIAS
BENCH_SEGMENT_RUNS = SEGMENT_RUNS
BENCH_TEARDROP_CASES = TEARDROP_CASES


def random_angle_triples(n: int, seed: int = 20260804) -> list[tuple[float, ...]]:
    """``n`` reproducible random ``_calculate_angle`` inputs, board-scale."""
    rng = random.Random(seed)
    return [tuple(rng.uniform(-100.0, 100.0) for _ in range(6)) for _ in range(n)]


def random_spoke_cases(n: int, seed: int = 20260805) -> list[tuple]:
    """``n`` reproducible random ``_generate_spoke_segments`` inputs."""
    rng = random.Random(seed)
    return [
        (
            rng.uniform(-100.0, 100.0),
            rng.uniform(-100.0, 100.0),
            rng.uniform(0.0, 5.0),
            rng.uniform(0.0, 5.0),
            rng.randint(2, 16),
            rng.uniform(0.05, 2.0),
            rng.uniform(0.05, 2.0),
        )
        for _ in range(n)
    ]


def random_annular_vias(n: int, seed: int = 20260806) -> list[tuple[float, float]]:
    """``n`` reproducible random ``(diameter, drill)`` pairs, both arms mixed."""
    rng = random.Random(seed)
    out: list[tuple[float, float]] = []
    for _ in range(n):
        d = rng.uniform(0.0, 3.0)
        # half the draws put the drill above the diameter, so the
        # `drill >= diameter -> 0.0` arm is exercised too
        drill = rng.uniform(0.0, d) if rng.random() < 0.5 else rng.uniform(0.0, 3.0)
        out.append((d, drill))
    return out


def random_segment_runs(n: int, seed: int = 20260807) -> list[tuple]:
    """``n`` reproducible random ``(segments, layer_name, width_mm)`` rows."""
    rng = random.Random(seed)
    out: list[tuple] = []
    for _ in range(n):
        count = rng.randint(0, 12)
        segs = tuple(
            (
                rng.uniform(-100.0, 100.0),
                rng.uniform(-100.0, 100.0),
                rng.choice(LAYER_NAMES),
            )
            for _ in range(count)
        )
        out.append((segs, rng.choice(LAYER_NAMES), rng.uniform(0.0, 1.0)))
    return out
