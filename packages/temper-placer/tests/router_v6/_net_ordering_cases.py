"""Shared input corpus for the Wave-4 ``net_ordering`` gates (cluster G, split).

**One fixture module, three consumers**: the differential suite (R1a), the
property/metamorphic suite (R1c/R1d), and the ``benchmarks/perf_ab.py`` arms
(R1b) that Phase B will add all draw their inputs from here -- the structural
answer to PR #714, which passed its differential at iterations
``[0, 1, 2, 8, 17, 100]`` and then failed CI on a benchmark that ran 120.
``test_bench_corpus_is_covered_by_differential`` asserts the containment.

This corpus is **deliberately not shared with** ``_escape_via_cases.py``.
The survey's cluster G pairs ``net_ordering`` with ``escape_via_generator``
while calling the pairing weak; on reading, the two modules share no type, no
fixture and no divergence class, so fusing their corpora would mean a single
list whose rows are two unrelated shapes.  See the "Why this is its OWN
oracle module" section of ``_net_ordering_py_oracle.py``.

**Nothing here imports the code under test** -- pure tuples, lists and dicts.
``Netlist``/``Component``/``Pin``/``LoopCollection`` objects are built from
this data by helpers in the test modules.

Coverage intent per named list
-------------------------------
``NET_CLASS_STRINGS``    every one of the 22 keys of
                         ``get_net_class_from_string``'s mapping, plus the
                         near-misses that must fall through to ``SIGNAL``
                         (wrong case, whitespace, empty, the ``GateDrive``
                         name that the 2026-07-28 R4 split removed from
                         ``netclass_rules.yaml``).
``LOOP_CASES``           ``get_loop_criticality``: net in no loop, in one
                         loop of each ``LoopPriority``, in several loops
                         (lowest wins), and in a loop whose priority is not
                         in the mapping (the ``.get(..., 3)`` default).
``HPWL_DESIGNS``         ``compute_hpwl`` / ``compute_bbox_area``: zero pins,
                         one pin, two coincident pins (zero-area bbox), a
                         degenerate line bbox (zero width or zero height),
                         rotated components, components with no
                         ``initial_position``, NaN and inf coordinates, and
                         magnitudes where ``max - min`` is inexact.
``ORDER_DESIGNS``        ``order_nets``: empty net list, one net, a full tie
                         broken only by name, ties broken by each of the six
                         key fields in turn, duplicate net names (an exact
                         tie -- stable-sort order), a config-priority map that
                         does and does not cover every net, and the NaN
                         wirelength that breaks the total order.
``PRIORITY_KEYS``        ``NetPriority`` comparison directly: pairs that
                         differ in exactly one field, at each of the six
                         positions, plus ``-0.0``/``0.0`` wirelength (equal
                         under ``<``, distinguishable under ``float.hex``).

``BENCH_*`` are subsets, never separate data.
"""

from __future__ import annotations

import math

__all__ = [
    "BENCH_HPWL_DESIGNS",
    "BENCH_ORDER_DESIGNS",
    "HPWL_DESIGNS",
    "LOOP_CASES",
    "NET_CLASS_STRINGS",
    "ORDER_DESIGNS",
    "PRIORITY_KEYS",
    "random_order_designs",
]

NAN = float("nan")
INF = float("inf")
NEG_INF = float("-inf")
DENORM = 5e-324


def _ulp_over(x: float) -> float:
    return math.nextafter(x, math.inf)


# ---------------------------------------------------------------------------
# get_net_class_from_string -- every mapping key plus the fall-through cases
# ---------------------------------------------------------------------------
NET_CLASS_STRINGS: list[str] = [
    # the 22 keys, verbatim
    "HighVoltage",
    "highvoltage",
    "HV",
    "Differential",
    "differential",
    "DiffPair",
    "Power",
    "power",
    "GateDrive",
    "gatedrive",
    "Gate",
    "GateDriveHV",
    "gatedrivehv",
    "GateDriveSELV",
    "gatedriveselv",
    "Signal",
    "signal",
    "FinePitch",
    "finepitch",
    "Ground",
    "ground",
    "GND",
    # near-misses that MUST fall through to SIGNAL -- the mapping is an
    # exact-match dict, not a case-insensitive or prefix lookup
    "HIGHVOLTAGE",
    "highVoltage",
    "hv",
    "gnd",
    "Gnd",
    "GND2",
    " GND",
    "GND ",
    "Power ",
    "POWER",
    "gatedriveSELV",
    "",
    "0",
    "None",
    "Signal\n",
    "\tSignal",
    "Ground/Signal",
]

# ---------------------------------------------------------------------------
# get_loop_criticality -- (label, [(loop_name, priority_name, [net, ...])],
#                          net_to_query)
# priority_name is one of CRITICAL / HIGH / MEDIUM / LOW.
# ---------------------------------------------------------------------------
LOOP_CASES: list[tuple[str, list[tuple[str, str, list[str]]], str]] = [
    ("no_loops", [], "N1"),
    ("net_not_in_any_loop", [("L1", "CRITICAL", ["OTHER"])], "N1"),
    ("critical", [("L1", "CRITICAL", ["N1"])], "N1"),
    ("high", [("L1", "HIGH", ["N1"])], "N1"),
    ("medium", [("L1", "MEDIUM", ["N1"])], "N1"),
    ("low", [("L1", "LOW", ["N1"])], "N1"),
    # in several loops -- the LOWEST criticality number wins, and it must not
    # depend on the order the loops were added
    ("multi_low_then_critical", [("A", "LOW", ["N1"]), ("B", "CRITICAL", ["N1"])], "N1"),
    ("multi_critical_then_low", [("A", "CRITICAL", ["N1"]), ("B", "LOW", ["N1"])], "N1"),
    (
        "multi_all_four",
        [
            ("A", "LOW", ["N1"]),
            ("B", "MEDIUM", ["N1"]),
            ("C", "HIGH", ["N1"]),
            ("D", "CRITICAL", ["N1"]),
        ],
        "N1",
    ),
    # the same loop listed twice, and a loop with many nets
    ("dup_loop", [("A", "HIGH", ["N1"]), ("A", "HIGH", ["N1"])], "N1"),
    ("wide_loop", [("A", "MEDIUM", [f"N{i}" for i in range(50)])], "N7"),
    # name matching is exact -- a substring must not match
    ("substring_not_matched", [("A", "CRITICAL", ["N10"])], "N1"),
    ("empty_net_name", [("A", "CRITICAL", [""])], ""),
]

# ---------------------------------------------------------------------------
# compute_hpwl / compute_bbox_area
#   (label, [(comp_ref, initial_position, rotation, [(pin_number, (px, py),
#             net)])], net_to_query)
# ---------------------------------------------------------------------------
HPWL_DESIGNS: list[tuple[str, list, str]] = [
    ("no_components", [], "N1"),
    ("net_absent", [("U1", (0.0, 0.0), 0, [("1", (0.0, 0.0), "OTHER")])], "N1"),
    ("single_pin", [("U1", (0.0, 0.0), 0, [("1", (0.0, 0.0), "N1")])], "N1"),
    # initial_side is READ by pin_world_position -- a bottom-side pad mirrors
    # X BEFORE rotation -- and the Rust kernel did not model it until
    # 2026-08-06, when its own comment asserted side was "0 for every
    # component this kernel can see". True of this corpus at the time; false
    # of any real board. Matching pin offsets on opposite sides collapse to
    # hpwl 0.0 if the mirror is skipped, and 2.0 if it is honoured.
    (
        "mixed_side_mirror",
        [
            ("U1", (0.0, 0.0), 0, [("1", (1.0, 0.0), "N1")], 0),
            ("U2", (0.0, 0.0), 0, [("1", (1.0, 0.0), "N1")], 1),
        ],
        "N1",
    ),
    # two coincident pins -> zero-area bbox, hpwl 0.0, area 0.0
    (
        "coincident_pins",
        [
            ("U1", (5.0, 5.0), 0, [("1", (0.0, 0.0), "N1")]),
            ("U2", (5.0, 5.0), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        "N1",
    ),
    # degenerate line bboxes: zero width, zero height
    (
        "zero_width",
        [
            ("U1", (5.0, 1.0), 0, [("1", (0.0, 0.0), "N1")]),
            ("U2", (5.0, 9.0), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        "N1",
    ),
    (
        "zero_height",
        [
            ("U1", (1.0, 5.0), 0, [("1", (0.0, 0.0), "N1")]),
            ("U2", (9.0, 5.0), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        "N1",
    ),
    # ordinary
    (
        "ordinary",
        [
            ("U1", (1.0, 2.0), 0, [("1", (0.0, 0.0), "N1")]),
            ("U2", (11.0, 7.0), 0, [("1", (0.0, 0.0), "N1")]),
            ("U3", (4.0, 4.0), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        "N1",
    ),
    # several pins on ONE component -- the inner loop appends more than once
    (
        "multi_pin_one_component",
        [
            (
                "U1",
                (0.0, 0.0),
                0,
                [
                    ("1", (0.0, 0.0), "N1"),
                    ("2", (3.0, 0.0), "N1"),
                    ("3", (0.0, 4.0), "N1"),
                    ("4", (3.0, 4.0), "OTHER"),
                ],
            )
        ],
        "N1",
    ),
    # rotations 0..3 -- pin_world_position applies them
    (
        "rotated",
        [
            ("U1", (0.0, 0.0), 1, [("1", (2.0, 1.0), "N1")]),
            ("U2", (10.0, 10.0), 3, [("1", (2.0, 1.0), "N1")]),
        ],
        "N1",
    ),
    # components with no initial_position (the `and component.initial_position`
    # guard) -- including the falsy (0.0, 0.0) tuple, which is NOT None but IS
    # truthy, and the falsy `None`
    (
        "no_initial_position",
        [
            ("U1", None, 0, [("1", (1.0, 1.0), "N1")]),
            ("U2", (5.0, 5.0), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        "N1",
    ),
    # NaN / inf coordinates -- max()/min() over an iterable containing NaN
    (
        "nan_first",
        [
            ("U1", (NAN, 0.0), 0, [("1", (0.0, 0.0), "N1")]),
            ("U2", (5.0, 5.0), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        "N1",
    ),
    (
        "nan_last",
        [
            ("U1", (5.0, 5.0), 0, [("1", (0.0, 0.0), "N1")]),
            ("U2", (NAN, 0.0), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        "N1",
    ),
    (
        "nan_middle",
        [
            ("U1", (0.0, 0.0), 0, [("1", (0.0, 0.0), "N1")]),
            ("U2", (NAN, 0.0), 0, [("1", (0.0, 0.0), "N1")]),
            ("U3", (9.0, 9.0), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        "N1",
    ),
    (
        "inf_span",
        [
            ("U1", (NEG_INF, 0.0), 0, [("1", (0.0, 0.0), "N1")]),
            ("U2", (INF, 0.0), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        "N1",
    ),
    # magnitudes where max - min is inexact, and where width * height
    # overflows to inf while width + height does not
    (
        "catastrophic_cancellation",
        [
            ("U1", (1e16, 0.0), 0, [("1", (0.0, 0.0), "N1")]),
            ("U2", (1e16 + 2.0, 1.0), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        "N1",
    ),
    (
        "area_overflows_hpwl_does_not",
        [
            ("U1", (0.0, 0.0), 0, [("1", (0.0, 0.0), "N1")]),
            ("U2", (1e200, 1e200), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        "N1",
    ),
    # signed zeros and denormals
    (
        "signed_zero_span",
        [
            ("U1", (-0.0, -0.0), 0, [("1", (0.0, 0.0), "N1")]),
            ("U2", (0.0, 0.0), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        "N1",
    ),
    (
        "denormal_span",
        [
            ("U1", (0.0, 0.0), 0, [("1", (0.0, 0.0), "N1")]),
            ("U2", (DENORM, DENORM), 0, [("1", (0.0, 0.0), "N1")]),
        ],
        "N1",
    ),
]

BENCH_HPWL_DESIGNS = [
    d for d in HPWL_DESIGNS if d[0] in {"ordinary", "multi_pin_one_component", "rotated"}
]

# ---------------------------------------------------------------------------
# order_nets
#   (label, components, nets, loops, net_priority_config)
#   components: [(ref, initial_position, rotation, [(pin_number, (px, py), net)])]
#   nets:       [(name, [(comp_ref, pin_name), ...], net_class_or_None)]
#   loops:      [(loop_name, priority_name, [net, ...])]
# ---------------------------------------------------------------------------


def _chain(names: list[str], spread: float = 1.0) -> tuple[list, list]:
    """One two-pin net per name, on its own component pair, at distinct HPWLs."""
    comps = []
    nets = []
    for i, n in enumerate(names):
        comps.append(
            (
                f"U{i}",
                (0.0, 0.0),
                0,
                [("1", (0.0, 0.0), n), ("2", (spread * (i + 1), 0.0), n)],
            )
        )
        nets.append((n, [(f"U{i}", "1"), (f"U{i}", "2")], None))
    return comps, nets


def _tied(names: list[str]) -> tuple[list, list]:
    """One two-pin net per name, all with IDENTICAL keys except ``name``."""
    comps = []
    nets = []
    for i, n in enumerate(names):
        comps.append((f"U{i}", (0.0, 0.0), 0, [("1", (0.0, 0.0), n), ("2", (1.0, 1.0), n)]))
        nets.append((n, [(f"U{i}", "1"), (f"U{i}", "2")], None))
    return comps, nets


_TIE_C, _TIE_N = _tied(["C", "A", "B"])
_CHAIN_C, _CHAIN_N = _chain(["Z", "Y", "X", "W"])

ORDER_DESIGNS: list[tuple[str, list, list, list, dict | None]] = [
    ("empty", [], [], [], None),
    ("single_net", *_chain(["ONLY"]), [], None),
    # broken ONLY by the alphabetical tiebreaker
    ("full_tie_name_only", _TIE_C, _TIE_N, [], None),
    # broken by each key field in turn
    ("tie_broken_by_wirelength", _CHAIN_C, _CHAIN_N, [], None),
    (
        "tie_broken_by_pin_count",
        [
            ("U0", (0.0, 0.0), 0, [("1", (0.0, 0.0), "A"), ("2", (1.0, 1.0), "A")]),
            (
                "U1",
                (0.0, 0.0),
                0,
                [("1", (0.0, 0.0), "B"), ("2", (1.0, 1.0), "B"), ("3", (0.5, 0.5), "B")],
            ),
        ],
        [
            ("A", [("U0", "1"), ("U0", "2")], None),
            ("B", [("U1", "1"), ("U1", "2"), ("U1", "3")], None),
        ],
        [],
        None,
    ),
    (
        "tie_broken_by_net_class",
        _TIE_C,
        [
            ("C", [("U0", "1"), ("U0", "2")], "Ground"),
            ("A", [("U1", "1"), ("U1", "2")], "HighVoltage"),
            ("B", [("U2", "1"), ("U2", "2")], "Power"),
        ],
        [],
        None,
    ),
    (
        "tie_broken_by_loop_criticality",
        _TIE_C,
        _TIE_N,
        [("L1", "CRITICAL", ["B"]), ("L2", "MEDIUM", ["A"])],
        None,
    ),
    ("tie_broken_by_config_priority", _TIE_C, _TIE_N, [], {"C": 1, "B": 2}),
    # a config map covering nets that do not exist, and covering none
    ("config_covers_absent_nets", _TIE_C, _TIE_N, [], {"GHOST": 1}),
    ("config_empty_dict", _TIE_C, _TIE_N, [], {}),
    ("config_out_of_range", _TIE_C, _TIE_N, [], {"A": -5, "B": 0, "C": 99}),
    # duplicate net names -> an exact six-field tie -> stable-sort order
    (
        "duplicate_names",
        [
            ("W0", (0.0, 0.0), 0, [("1", (0.0, 0.0), "D"), ("2", (1.0, 0.0), "D")]),
            ("W1", (0.0, 0.0), 0, [("1", (0.0, 0.0), "D"), ("2", (1.0, 0.0), "D")]),
        ],
        [
            ("D", [("W0", "1"), ("W0", "2")], None),
            ("D", [("W1", "1"), ("W1", "2")], None),
        ],
        [],
        None,
    ),
    # a net with zero pins and a net with one pin (pin_count 0 and 1)
    (
        "zero_and_one_pin_nets",
        [("U0", (0.0, 0.0), 0, [("1", (0.0, 0.0), "P1")])],
        [("P0", [], None), ("P1", [("U0", "1")], None)],
        [],
        None,
    ),
    # NaN wirelength: the 6-tuple stops being a total order.  Pinned, not
    # papered over -- see the oracle header.
    (
        "nan_wirelength",
        [
            ("N0", (0.0, 0.0), 0, [("1", (0.0, 0.0), "P"), ("2", (1.0, 1.0), "P")]),
            ("N1", (NAN, 0.0), 0, [("1", (0.0, 0.0), "Q"), ("2", (1.0, 1.0), "Q")]),
            ("N2", (0.0, 0.0), 0, [("1", (0.0, 0.0), "R"), ("2", (2.0, 2.0), "R")]),
        ],
        [
            ("P", [("N0", "1"), ("N0", "2")], None),
            ("Q", [("N1", "1"), ("N1", "2")], None),
            ("R", [("N2", "1"), ("N2", "2")], None),
        ],
        [],
        None,
    ),
    # names whose ordering is byte-wise, not locale- or case-aware
    (
        "byte_wise_name_order",
        *_tied(["a", "B", "_", "0", "AA", "A"]),
        [],
        None,
    ),
    # unicode names -- ordering is by code point
    ("unicode_names", *_tied(["é", "e", "É", "E"]), [], None),
    # a wider design, so the sort does real work
    ("wide", *_chain([f"NET{i:03d}" for i in range(64)], spread=0.125), [], None),
]

BENCH_ORDER_DESIGNS = [
    d
    for d in ORDER_DESIGNS
    if d[0] in {"wide", "tie_broken_by_wirelength", "tie_broken_by_loop_criticality"}
]

# ---------------------------------------------------------------------------
# NetPriority comparison: (config_priority, loop_criticality, net_class_value,
#                          pin_count, estimated_wirelength, name)
# Pairs differing in exactly one position, at each of the six positions.
# ---------------------------------------------------------------------------
_BASE_KEY = (5, 3, 4, 2, 1.0, "N")

PRIORITY_KEYS: list[tuple[tuple, tuple]] = [
    (_BASE_KEY, _BASE_KEY),  # equal
    (_BASE_KEY, (1, 3, 4, 2, 1.0, "N")),
    (_BASE_KEY, (5, 0, 4, 2, 1.0, "N")),
    (_BASE_KEY, (5, 3, 0, 2, 1.0, "N")),
    (_BASE_KEY, (5, 3, 4, 1, 1.0, "N")),
    (_BASE_KEY, (5, 3, 4, 2, 0.5, "N")),
    (_BASE_KEY, (5, 3, 4, 2, 1.0, "M")),
    # -0.0 vs 0.0: equal under `<` and `==`, distinguishable under float.hex
    ((5, 3, 4, 2, 0.0, "N"), (5, 3, 4, 2, -0.0, "N")),
    # NaN wirelength: neither `<` nor `==` -- the tuple comparison is unordered
    ((5, 3, 4, 2, NAN, "N"), (5, 3, 4, 2, 1.0, "N")),
    ((5, 3, 4, 2, NAN, "N"), (5, 3, 4, 2, NAN, "N")),
    # inf wirelength
    ((5, 3, 4, 2, INF, "N"), (5, 3, 4, 2, 1e308, "N")),
    ((5, 3, 4, 2, NEG_INF, "N"), (5, 3, 4, 2, -1e308, "N")),
    # a 1-ulp wirelength difference must NOT be swallowed
    ((5, 3, 4, 2, 1.0, "N"), (5, 3, 4, 2, _ulp_over(1.0), "N")),
    # int-vs-bool in config_priority: True == 1, and the key must not
    # silently accept it as an int (the signature comparator separates them)
    ((5, 3, 4, 2, 1.0, "N"), (True, 3, 4, 2, 1.0, "N")),
]


def random_order_designs(seed: int, n: int) -> list[tuple[list, list]]:
    """``n`` seeded (components, nets) pairs for ``order_nets``.

    Names, pin counts, coordinates and net classes are all drawn, so the
    sweep exercises every key field rather than only the wirelength one.
    """
    import random

    rng = random.Random(seed)
    classes = [None, "HighVoltage", "Power", "GateDrive", "Signal", "Ground", "Nonsense"]
    out = []
    for _ in range(n):
        k = rng.choice([0, 1, 2, 5, 9])
        names = [f"N{rng.randrange(1000):04d}" for _ in range(k)]
        comps = []
        nets = []
        for i, name in enumerate(names):
            npins = rng.choice([1, 2, 2, 3, 6])
            pins = [
                (str(p), (rng.uniform(-30.0, 30.0), rng.uniform(-30.0, 30.0)), name)
                for p in range(npins)
            ]
            comps.append((f"U{i}", (rng.uniform(-5.0, 5.0), rng.uniform(-5.0, 5.0)), 0, pins))
            nets.append((name, [(f"U{i}", str(p)) for p in range(npins)], rng.choice(classes)))
        out.append((comps, nets))
    return out
