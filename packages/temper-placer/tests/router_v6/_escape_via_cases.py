"""Shared input corpus for the Wave-4 ``escape_via_generator`` gates (cluster G, split).

**One fixture module, three consumers**: the differential suite (R1a), the
property/metamorphic suite (R1c/R1d), and the ``benchmarks/perf_ab.py`` arms
(R1b) that Phase B will add all draw their inputs from here -- the structural
answer to PR #714 (differential ran ``[0, 1, 2, 8, 17, 100]``, CI benchmark
ran 120, the benchmark found a parameter the gate had never reached).
``test_bench_corpus_is_covered_by_differential`` asserts the containment.

Deliberately **separate** from ``_net_ordering_cases.py``: the survey pairs
these two modules as cluster G while calling the pairing weak, and on reading
they share no type, no fixture and no divergence class.  See the "Why this is
its own oracle module" section of ``_escape_via_py_oracle.py``.

**Nothing here imports the code under test** -- pure tuples and dicts.
``Component``/``Pin``/``DensePackage``/``DesignRules`` objects are built from
this data by helpers in the test modules.

Coverage intent per named list
-------------------------------
``PACKAGES``       ``generate_escape_vias``: an empty pin list, a component
                   whose pins have no net (skipped by ``if not pin.net``),
                   BGA grids at the pitches that straddle the dog-bone
                   feasibility boundary, non-square pad shapes, every
                   ``initial_rotation`` index 0-3 and ``None``, both
                   ``initial_side`` values (the D4 corpus -- since #760 the
                   layer follows the side), ``initial_position = None``, and the
                   ``pitch_mm`` values ``0.0`` / negative / ``inf`` / ``NaN``.
``RULE_SETS``      ``DesignRules.get_rules_for_net``: the default fall-through,
                   an assignment naming a class that exists, an assignment
                   naming a class that does *not* exist (falls back to the
                   defaults), and via/clearance sizes that put
                   ``dist < required - 0.001`` on each side of its boundary
                   including exactly on it and one ulp either way.
``STRATEGIES``     ``"dog-bone"``, ``"via-in-pad"``, and strings that match
                   neither (the silent-empty branch -- there is no ``else``).
``VALID_PROBES``   ``_is_position_valid`` directly: a via exactly at the
                   required distance, one ulp inside, one ulp outside, at the
                   ``- 0.001`` epsilon boundary, in the denormal band (B8),
                   and with NaN/inf coordinates (where ``<`` is False, so the
                   position is ACCEPTED -- see the oracle header).

``BENCH_*`` are subsets, never separate data.
"""

from __future__ import annotations

import math

__all__ = [
    "BENCH_PACKAGES",
    "BENCH_RULE_SETS",
    "PACKAGES",
    "RULE_SETS",
    "STRATEGIES",
    "VALID_PROBES",
    "random_packages",
]

NAN = float("nan")
INF = float("inf")
NEG_INF = float("-inf")
DENORM = 5e-324

# The exact constant the collision test subtracts.  Landing on it, not near
# it, is what makes the epsilon mutant killable.
_EPS = 0.001


def _ulp_over(x: float) -> float:
    return math.nextafter(x, math.inf)


def _ulp_under(x: float) -> float:
    return math.nextafter(x, -math.inf)


def _grid_pins(
    n: int, pitch: float, w: float = 0.4, h: float = 0.4, shape: str = "circle"
) -> list[tuple[str, tuple[float, float], str, float, float, str]]:
    """``n x n`` pad grid: (pin_number, (px, py), net, width, height, shape)."""
    return [
        (str(r * n + c + 1), (c * pitch, r * pitch), f"N{r * n + c}", w, h, shape)
        for r in range(n)
        for c in range(n)
    ]


# ---------------------------------------------------------------------------
# generate_escape_vias
#   (label, initial_position, initial_rotation, initial_side, pitch_mm,
#    package_type, pins)
# ---------------------------------------------------------------------------
PACKAGES: list[tuple[str, tuple[float, float] | None, int | None, int | None, float, str, list]] = [
    # --- degenerate shapes -------------------------------------------------
    ("no_pins", (0.0, 0.0), 0, 0, 0.8, "BGA", []),
    (
        "all_pins_netless",
        (0.0, 0.0),
        0,
        0,
        0.8,
        "BGA",
        [("1", (0.0, 0.0), None, 0.4, 0.4, "circle"), ("2", (0.8, 0.0), "", 0.4, 0.4, "circle")],
    ),
    (
        "single_pin",
        (10.0, 20.0),
        0,
        0,
        0.8,
        "BGA",
        [("1", (0.0, 0.0), "N0", 0.4, 0.4, "circle")],
    ),
    (
        "two_coincident_pads",
        (0.0, 0.0),
        0,
        0,
        1.27,
        "BGA",
        [
            ("1", (0.0, 0.0), "N0", 0.4, 0.4, "circle"),
            ("2", (0.0, 0.0), "N1", 0.4, 0.4, "circle"),
        ],
    ),
    # --- the dog-bone feasibility boundary ---------------------------------
    # With the DEFAULT rule set (via 0.45, pad 0.4 circle, clearance 0.15) the
    # required separation is 0.225 + 0.2 + 0.15 = 0.575 and the candidate sits
    # at pitch/2 * sqrt(2) from its own pad.  Measured: infeasible at
    # 0.4/0.5/0.65/0.8 mm, feasible at 1.0/1.27 mm.  Both sides are present.
    ("bga3_pitch_0p40", (10.0, 20.0), 0, 0, 0.40, "BGA", _grid_pins(3, 0.40)),
    ("bga3_pitch_0p50", (10.0, 20.0), 0, 0, 0.50, "BGA", _grid_pins(3, 0.50)),
    ("bga3_pitch_0p65", (10.0, 20.0), 0, 0, 0.65, "BGA", _grid_pins(3, 0.65)),
    ("bga3_pitch_0p80", (10.0, 20.0), 0, 0, 0.80, "BGA", _grid_pins(3, 0.80)),
    ("bga3_pitch_1p00", (10.0, 20.0), 0, 0, 1.00, "BGA", _grid_pins(3, 1.00)),
    ("bga3_pitch_1p27", (10.0, 20.0), 0, 0, 1.27, "BGA", _grid_pins(3, 1.27)),
    ("bga5_pitch_1p27", (10.0, 20.0), 0, 0, 1.27, "BGA", _grid_pins(5, 1.27)),
    # --- rotation ----------------------------------------------------------
    ("rot_none", (10.0, 20.0), None, 0, 1.27, "BGA", _grid_pins(3, 1.27)),
    ("rot_0", (10.0, 20.0), 0, 0, 1.27, "BGA", _grid_pins(3, 1.27)),
    ("rot_1", (10.0, 20.0), 1, 0, 1.27, "BGA", _grid_pins(3, 1.27)),
    ("rot_2", (10.0, 20.0), 2, 0, 1.27, "BGA", _grid_pins(3, 1.27)),
    ("rot_3", (10.0, 20.0), 3, 0, 1.27, "BGA", _grid_pins(3, 1.27)),
    # a non-quadrant rotation index: the module multiplies by pi/2 without
    # validating the range, so this is the only case where R(+theta) vs
    # R(-theta) is observable (the 4-way candidate set is symmetric at
    # quadrants).  B1's dlsym cos/sin trap is live here.
    ("rot_5_out_of_range", (10.0, 20.0), 5, 0, 1.27, "BGA", _grid_pins(3, 1.27)),
    ("rot_negative", (10.0, 20.0), -1, 0, 1.27, "BGA", _grid_pins(3, 1.27)),
    # --- side (the D4 corpus: since #760 the layer follows initial_side) ---
    ("side_0", (10.0, 20.0), 0, 0, 1.27, "BGA", _grid_pins(3, 1.27)),
    ("side_1_back", (10.0, 20.0), 0, 1, 1.27, "BGA", _grid_pins(3, 1.27)),
    ("side_none", (10.0, 20.0), 0, None, 1.27, "BGA", _grid_pins(3, 1.27)),
    # --- position ----------------------------------------------------------
    ("position_none", None, 0, 0, 1.27, "BGA", _grid_pins(3, 1.27)),
    ("position_origin", (0.0, 0.0), 0, 0, 1.27, "BGA", _grid_pins(3, 1.27)),
    ("position_signed_zero", (-0.0, -0.0), 0, 0, 1.27, "BGA", _grid_pins(3, 1.27)),
    ("position_negative", (-40.0, -12.5), 0, 0, 1.27, "BGA", _grid_pins(3, 1.27)),
    ("position_huge", (1e12, 1e12), 0, 0, 1.27, "BGA", _grid_pins(3, 1.27)),
    # --- pad shapes (pin_world_radius dispatches on these) -----------------
    ("pads_rect", (10.0, 20.0), 0, 0, 1.27, "BGA", _grid_pins(3, 1.27, 0.5, 0.3, "rect")),
    ("pads_oval", (10.0, 20.0), 0, 0, 1.27, "BGA", _grid_pins(3, 1.27, 0.6, 0.3, "oval")),
    (
        "pads_roundrect",
        (10.0, 20.0),
        0,
        0,
        1.27,
        "BGA",
        _grid_pins(3, 1.27, 0.5, 0.5, "roundrect"),
    ),
    ("pads_zero_size", (10.0, 20.0), 0, 0, 1.27, "BGA", _grid_pins(3, 1.27, 0.0, 0.0, "rect")),
    ("pads_elongated", (10.0, 20.0), 0, 0, 2.54, "BGA", _grid_pins(3, 2.54, 2.0, 0.2, "rect")),
    # --- pitch pathologies -------------------------------------------------
    ("pitch_zero", (10.0, 20.0), 0, 0, 0.0, "BGA", _grid_pins(3, 1.27)),
    ("pitch_negative", (10.0, 20.0), 0, 0, -1.27, "BGA", _grid_pins(3, 1.27)),
    ("pitch_denormal", (10.0, 20.0), 0, 0, DENORM, "BGA", _grid_pins(3, 1.27)),
    ("pitch_inf", (10.0, 20.0), 0, 0, INF, "BGA", _grid_pins(3, 1.27)),
    # NaN pitch is ACCEPTED: `dist < required - 0.001` is False for NaN, so
    # every candidate validates and 9 vias are emitted at (nan, nan).
    ("pitch_nan", (10.0, 20.0), 0, 0, NAN, "BGA", _grid_pins(3, 1.27)),
    # --- NaN / inf pad coordinates ----------------------------------------
    (
        "pad_nan_coord",
        (10.0, 20.0),
        0,
        0,
        1.27,
        "BGA",
        [
            ("1", (NAN, 0.0), "N0", 0.4, 0.4, "circle"),
            ("2", (1.27, 0.0), "N1", 0.4, 0.4, "circle"),
        ],
    ),
    (
        "pad_inf_coord",
        (10.0, 20.0),
        0,
        0,
        1.27,
        "BGA",
        [
            ("1", (INF, 0.0), "N0", 0.4, 0.4, "circle"),
            ("2", (1.27, 0.0), "N1", 0.4, 0.4, "circle"),
        ],
    ),
    # --- ordering: two pins on the same net, and duplicate pin numbers -----
    (
        "same_net_two_pads",
        (10.0, 20.0),
        0,
        0,
        1.27,
        "BGA",
        [
            ("1", (0.0, 0.0), "SHARED", 0.4, 0.4, "circle"),
            ("2", (1.27, 0.0), "SHARED", 0.4, 0.4, "circle"),
        ],
    ),
    (
        "duplicate_pin_numbers",
        (10.0, 20.0),
        0,
        0,
        1.27,
        "BGA",
        [
            ("1", (0.0, 0.0), "N0", 0.4, 0.4, "circle"),
            ("1", (1.27, 0.0), "N1", 0.4, 0.4, "circle"),
        ],
    ),
    # --- a wider package, so the O(pins^2) collision scan does real work ---
    ("bga8_pitch_1p27", (10.0, 20.0), 0, 0, 1.27, "BGA", _grid_pins(8, 1.27)),
]

BENCH_PACKAGES = [
    p
    for p in PACKAGES
    if p[0] in {"bga8_pitch_1p27", "bga5_pitch_1p27", "bga3_pitch_0p80", "rot_5_out_of_range"}
]

# ---------------------------------------------------------------------------
# DesignRules -- (label, net_classes, net_class_assignments, defaults)
#   net_classes:   {class_name: (clearance, trace_w, via_dia, via_drill)}
#   defaults:      (clearance, trace_w, via_dia, via_drill)
# ---------------------------------------------------------------------------
RULE_SETS: list[tuple[str, dict, dict, tuple[float, float, float, float]]] = [
    ("defaults_only", {}, {}, (0.15, 0.2, 0.45, 0.25)),
    # an assignment that resolves, and one whose class name is absent (the
    # `class_name and class_name in self.net_classes` guard falls through)
    (
        "assignment_resolves",
        {"HV": (0.5, 0.3, 0.8, 0.4)},
        {"N0": "HV"},
        (0.15, 0.2, 0.45, 0.25),
    ),
    (
        "assignment_names_missing_class",
        {"HV": (0.5, 0.3, 0.8, 0.4)},
        {"N0": "GHOST"},
        (0.15, 0.2, 0.45, 0.25),
    ),
    (
        "assignment_empty_string_class",
        {"HV": (0.5, 0.3, 0.8, 0.4)},
        {"N0": ""},
        (0.15, 0.2, 0.45, 0.25),
    ),
    # per-net rules that make ONE pin feasible and its neighbours not
    (
        "mixed_feasibility",
        {"TIGHT": (0.6, 0.3, 0.9, 0.5), "LOOSE": (0.02, 0.1, 0.2, 0.1)},
        {"N0": "TIGHT", "N1": "LOOSE", "N4": "LOOSE"},
        (0.15, 0.2, 0.45, 0.25),
    ),
    # clearances that put `dist < required - 0.001` exactly on its boundary
    # for a 1.27 mm BGA with 0.4 mm circular pads: dist = 1.27/2 * sqrt(2)
    # = 0.8980...; required = via_dia/2 + 0.2 + clearance.
    ("boundary_exact", {}, {}, (0.4980256811733193, 0.2, 0.4, 0.25)),
    ("boundary_ulp_under", {}, {}, (_ulp_under(0.4980256811733193), 0.2, 0.4, 0.25)),
    ("boundary_ulp_over", {}, {}, (_ulp_over(0.4980256811733193), 0.2, 0.4, 0.25)),
    # zero and negative clearance / via size
    ("zero_clearance", {}, {}, (0.0, 0.2, 0.45, 0.25)),
    ("zero_via", {}, {}, (0.15, 0.2, 0.0, 0.0)),
    ("negative_clearance", {}, {}, (-1.0, 0.2, 0.45, 0.25)),
    # denormal-band clearance (B8): a fast-math build flushes it to 0.0
    ("denormal_clearance", {}, {}, (DENORM, 0.2, 0.45, 0.25)),
    # exactly the epsilon: required - dist == 0.001
    ("epsilon_exact", {}, {}, (0.8980256811733193 - 0.2 - 0.2 + _EPS, 0.2, 0.4, 0.25)),
    # NaN / inf rule values
    ("nan_clearance", {}, {}, (NAN, 0.2, 0.45, 0.25)),
    ("inf_clearance", {}, {}, (INF, 0.2, 0.45, 0.25)),
    ("nan_via_diameter", {}, {}, (0.15, 0.2, NAN, 0.25)),
    ("huge_clearance", {}, {}, (1e6, 0.2, 0.45, 0.25)),
]

BENCH_RULE_SETS = [
    r for r in RULE_SETS if r[0] in {"defaults_only", "mixed_feasibility", "assignment_resolves"}
]

STRATEGIES: list[str] = [
    "dog-bone",
    "via-in-pad",
    # neither branch matches -> the loop body does nothing and the result is
    # []; there is no `else`, so an unknown strategy fails silently.
    "",
    "dogbone",
    "Dog-Bone",
    "via_in_pad",
    "nonsense",
]

# ---------------------------------------------------------------------------
# _is_position_valid probes -- (label, via_x, via_y, via_radius, clearance,
#                               [(pad_x, pad_y, pad_w, pad_h, shape)])
# Pad radius is `pin_world_radius`, so a 0.4x0.4 circle contributes 0.2.
# ---------------------------------------------------------------------------
_R = 0.225  # via radius for a 0.45 mm via
_PAD = [(0.0, 0.0, 0.4, 0.4, "circle")]

VALID_PROBES: list[tuple[str, float, float, float, float, list]] = [
    ("far_away", 100.0, 100.0, _R, 0.15, _PAD),
    ("coincident", 0.0, 0.0, _R, 0.15, _PAD),
    # required = 0.225 + 0.2 + 0.15 = 0.575; the test is
    # `dist < required - 0.001`, so the cliff is at 0.574.
    ("dist_exactly_at_cliff", 0.574, 0.0, _R, 0.15, _PAD),
    ("dist_one_ulp_under_cliff", _ulp_under(0.574), 0.0, _R, 0.15, _PAD),
    ("dist_one_ulp_over_cliff", _ulp_over(0.574), 0.0, _R, 0.15, _PAD),
    ("dist_exactly_required", 0.575, 0.0, _R, 0.15, _PAD),
    # the `- 0.001` epsilon itself: without it, 0.5745 would be invalid
    ("inside_epsilon_band", 0.5745, 0.0, _R, 0.15, _PAD),
    # zero-size via and zero-size pad (pin_world_radius returns 0.5 for a
    # 0x0 pad -- a documented special case, not a bug)
    ("zero_via_radius", 0.3, 0.0, 0.0, 0.15, _PAD),
    ("zero_size_pad", 1.0, 0.0, _R, 0.15, [(0.0, 0.0, 0.0, 0.0, "rect")]),
    # denormal band (B8)
    ("denormal_offset", DENORM, 0.0, _R, 0.15, _PAD),
    ("denormal_clearance", 1.0, 0.0, _R, DENORM, _PAD),
    # NaN / inf: `dist < required` is False for NaN, so the position is
    # ACCEPTED.  A Rust mirror that early-returns on NaN diverges here.
    ("nan_via_x", NAN, 0.0, _R, 0.15, _PAD),
    ("nan_pad", 1.0, 0.0, _R, 0.15, [(NAN, 0.0, 0.4, 0.4, "circle")]),
    ("nan_clearance", 1.0, 0.0, _R, NAN, _PAD),
    ("inf_via_x", INF, 0.0, _R, 0.15, _PAD),
    ("neg_inf_via_x", NEG_INF, 0.0, _R, 0.15, _PAD),
    ("inf_minus_inf", INF, 0.0, _R, 0.15, [(INF, 0.0, 0.4, 0.4, "circle")]),
    # signed zeros
    ("signed_zero_via", -0.0, -0.0, _R, 0.15, _PAD),
    # many pads, the first of which already fails -> short-circuit order
    (
        "first_pad_fails",
        0.1,
        0.0,
        _R,
        0.15,
        [(0.0, 0.0, 0.4, 0.4, "circle"), (50.0, 50.0, 0.4, 0.4, "circle")],
    ),
    (
        "last_pad_fails",
        0.1,
        0.0,
        _R,
        0.15,
        [(50.0, 50.0, 0.4, 0.4, "circle"), (0.0, 0.0, 0.4, 0.4, "circle")],
    ),
    ("no_pads_at_all", 0.0, 0.0, _R, 0.15, []),
    # magnitudes where (x - px) ** 2 overflows
    ("overflow_square", 1e200, 0.0, _R, 0.15, [(-1e200, 0.0, 0.4, 0.4, "circle")]),
    # roundrect_ratio is READ by pin_world_radius and was hardcoded to the
    # 0.25 default in the Rust kernel until 2026-08-06. `.kicad_pcb` files
    # carry real `roundrect_rratio` values, so this is reachable on real
    # boards, not a synthetic edge. The probe sits between the radius the
    # default ratio implies and the one 0.5 implies, so the two disagree on
    # the accept/reject verdict rather than merely on a returned float.
    ("roundrect_ratio_non_default", 0.8893943276465976, 0.0, _R, 0.15,
     [(0.0, 0.0, 1.0, 0.6, "roundrect", 0.5)]),
    ("roundrect_ratio_zero_is_falsy", 0.8893943276465976, 0.0, _R, 0.15,
     [(0.0, 0.0, 1.0, 0.6, "roundrect", 0.0)]),
]


def random_packages(seed: int, n: int) -> list[tuple[tuple[float, float], int, float, list]]:
    """``n`` seeded (position, rotation, pitch, pins) tuples.

    Pitches straddle the dog-bone feasibility cliff and pad shapes are drawn
    from all four ``pin_world_radius`` branches, so the sweep exercises both
    the accept and the reject path rather than only one.
    """
    import random

    rng = random.Random(seed)
    shapes = ["circle", "rect", "oval", "roundrect"]
    out = []
    for _ in range(n):
        side = rng.choice([1, 2, 3, 4])
        pitch = rng.choice([0.4, 0.5, 0.65, 0.8, 1.0, 1.27, 2.54, rng.uniform(0.3, 3.0)])
        w = rng.uniform(0.05, 1.2)
        h = rng.uniform(0.05, 1.2)
        shape = rng.choice(shapes)
        out.append(
            (
                (rng.uniform(-50.0, 50.0), rng.uniform(-50.0, 50.0)),
                rng.choice([0, 1, 2, 3]),
                pitch,
                _grid_pins(side, pitch, w, h, shape),
            )
        )
    return out
