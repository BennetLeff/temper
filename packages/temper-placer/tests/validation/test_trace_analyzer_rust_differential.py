"""Differential test: trace-analysis kernels in Rust (temper_drc_rs) vs the
pinned Python implementations (Wave 4, Phase 4 — validation DRC-check slice).

``temper_placer/validation/trace_analyzer.py`` moves two pure kernels to
``temper_drc_rs``:
- ``calculate_actual_trace_length``  → ``temper_drc_rs.trace_length``
- ``calculate_min_hv_lv_clearance``  → ``temper_drc_rs.min_hv_lv_trace_clearance``

The pre-migration implementations are pinned VERBATIM below (the
thermal_scorer convention of pinning the migrated functions inside the
differential, commit ``aece7c372``). ``calculate_actual_loop_area`` stays in
Python: its core is ``scipy.spatial.ConvexHull`` (Qhull), which is not
bit-reproducible outside scipy — the GEOS-style "library semantics are not
reimplementable" boundary, argued in the module source.

Floats are compared bit-exactly via ``float.hex()``; ``+inf`` (empty input
semantics) is a first-class asserted output, not an accident.
"""

from __future__ import annotations

import math
import random

import numpy as np
import pytest
import temper_drc_rs as _tdrc
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.board import Board, Trace

# Rust symbols under test — must exist or this file fails to collect (RED).
TRACE_LENGTH = _tdrc.trace_length
MIN_HV_LV_CLEARANCE = _tdrc.min_hv_lv_trace_clearance

from temper_placer.validation.trace_analyzer import (  # noqa: E402
    calculate_actual_trace_length as shim_trace_length,
)
from temper_placer.validation.trace_analyzer import (  # noqa: E402
    calculate_min_hv_lv_clearance as shim_min_clearance,
)

# ---------------------------------------------------------------------------
# Oracles — the pre-migration implementations, verbatim (commit aece7c372)
# ---------------------------------------------------------------------------


def _ref_calculate_actual_trace_length(board: Board, net_name: str) -> float:
    """Pre-migration ``calculate_actual_trace_length``, verbatim."""
    length = 0.0
    for trace in board.traces:  # type: ignore[attr-defined]
        if trace.net == net_name:
            dx = trace.end[0] - trace.start[0]
            dy = trace.end[1] - trace.start[1]
            length += math.sqrt(dx**2 + dy**2)
    return length


def _ref_calculate_min_hv_lv_clearance(board: Board, net_classes: dict[str, str]) -> float:
    """Pre-migration ``calculate_min_hv_lv_clearance``, verbatim (the numpy
    norm calls and the split are kept byte-for-byte)."""
    hv_traces = [t for t in board.traces if net_classes.get(t.net) == "HighVoltage"]  # type: ignore[attr-defined]
    lv_traces = [t for t in board.traces if net_classes.get(t.net) != "HighVoltage"]  # type: ignore[attr-defined]

    if not hv_traces or not lv_traces:
        return float("inf")

    min_dist = float("inf")

    for hv in hv_traces:
        for lv in lv_traces:
            # Shortest distance between two line segments
            # Simplified: check endpoints for now
            pts_hv = [np.array(hv.start), np.array(hv.end)]
            pts_lv = [np.array(lv.start), np.array(lv.end)]

            for p1 in pts_hv:
                for p2 in pts_lv:
                    dist = float(np.linalg.norm(p1 - p2))
                    min_dist = min(min_dist, dist)

    return float(min_dist)


# ---------------------------------------------------------------------------
# Input construction
# ---------------------------------------------------------------------------

_COORD = st.floats(min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False)
_NET = st.text(min_size=1, max_size=12).map(lambda s: f"N{abs(hash(s)) % 5000}")


def _board_from_traces(traces: list[tuple[str, float, float, float, float]]) -> Board:
    board = Board(width=200.0, height=200.0)
    board.traces = [  # type: ignore[attr-defined]
        Trace(start=(x1, y1), end=(x2, y2), width=0.2, layer="F.Cu", net=net)
        for (net, x1, y1, x2, y2) in traces
    ]
    return board


def _net_classes_for(traces, hv_nets: set[str]) -> dict[str, str]:
    return {t[0]: ("HighVoltage" if t[0] in hv_nets else "Signal") for t in traces}


# ---------------------------------------------------------------------------
# Differential — bit-exact floats
# ---------------------------------------------------------------------------


@settings(max_examples=60, deadline=None)
@given(
    st.lists(
        st.tuples(_NET, _COORD, _COORD, _COORD, _COORD),
        min_size=0,
        max_size=10,
    ),
    _NET,
)
def test_trace_length_differential(traces, net_name):
    board = _board_from_traces(traces)
    ref = _ref_calculate_actual_trace_length(board, net_name)
    got = shim_trace_length(board, net_name)
    assert got.hex() == ref.hex(), (got.hex(), ref.hex())


@settings(max_examples=60, deadline=None)
@given(
    st.lists(
        st.tuples(_NET, _COORD, _COORD, _COORD, _COORD),
        min_size=0,
        max_size=10,
    ),
    st.sets(_NET, max_size=5),
)
def test_min_clearance_differential(traces, hv_nets):
    board = _board_from_traces(traces)
    nc = _net_classes_for(traces, set(hv_nets))
    ref = _ref_calculate_min_hv_lv_clearance(board, nc)
    got = shim_min_clearance(board, nc)
    assert got.hex() == ref.hex(), (got.hex(), ref.hex())


def test_differential_edge_cases():
    board = _board_from_traces([])
    # empty board: length 0.0; clearance +inf
    assert shim_trace_length(board, "N1") == 0.0
    assert shim_min_clearance(board, {}) == float("inf")
    # net with no traces: length 0.0
    b2 = _board_from_traces([("N1", 0.0, 0.0, 10.0, 0.0)])
    assert shim_trace_length(b2, "N2") == 0.0
    assert shim_min_clearance(b2, {"N1": "HighVoltage"}) == float("inf")  # no LV
    assert shim_min_clearance(b2, {"N1": "Signal"}) == float("inf")  # no HV
    # identical endpoints → zero-length segment, dist 0.0
    b3 = _board_from_traces([("HV", 5.0, 5.0, 5.0, 5.0), ("LV", 5.0, 5.0, 5.0, 5.0)])
    assert shim_trace_length(b3, "HV") == 0.0
    assert shim_min_clearance(b3, {"HV": "HighVoltage", "LV": "Signal"}) == 0.0
    # a 3-4-5 triangle
    b4 = _board_from_traces([("N1", 0.0, 0.0, 3.0, 4.0)])
    assert shim_trace_length(b4, "N1") == pytest.approx(5.0)


def test_trace_length_none_net_trace_skipped():
    """Trace.net is ``str | None`` (core/board.py) — a None-net trace must be
    skipped exactly like the oracle's ``if trace.net == net_name`` (None never
    equals a str net_name). The shim marshals None into the kernel's
    Option<String>; regression: the kernel's ``Vec<(String, ...)>`` extraction
    raised TypeError on None."""
    board = Board(width=200.0, height=200.0)
    board.traces = [  # type: ignore[attr-defined]
        Trace(start=(0.0, 0.0), end=(10.0, 0.0), width=0.2, layer="F.Cu", net=None),
        Trace(start=(0.0, 0.0), end=(3.0, 4.0), width=0.2, layer="F.Cu", net="N1"),
    ]
    ref = _ref_calculate_actual_trace_length(board, "N1")
    got = shim_trace_length(board, "N1")
    assert got.hex() == ref.hex() == (5.0).hex()
    # the None-net trace contributes to no net, and None != "" (distinct keys)
    board.traces.append(  # type: ignore[attr-defined]
        Trace(start=(0.0, 0.0), end=(1.0, 0.0), width=0.2, layer="F.Cu", net="")
    )
    for net_name in ("N1", "OTHER", ""):
        ref2 = _ref_calculate_actual_trace_length(board, net_name)
        got2 = shim_trace_length(board, net_name)
        assert got2.hex() == ref2.hex()
    assert got == 5.0  # None-net segment (length 10) never counted


def test_trace_length_pow2_libm_parity():
    """CPython `dx**2` is libm `pow`, NOT `x*x` — for this dx the two differ
    by 1 ulp (measured; `assert dx * dx != dx**2` below documents the trap),
    so a kernel squaring with `dx * dx` returns a length 1 ulp too large.
    Pins the host-libm `pow` squaring (dlsym'd, exactly what CPython calls)
    against the oracle bit-exactly (this exact segment was the one-ulp
    mismatch the random stress exposed)."""
    dx = 608.5928659723188
    assert dx * dx != dx**2  # the trap this test exists for
    board = Board(width=200.0, height=200.0)
    board.traces = [  # type: ignore[attr-defined]
        Trace(
            start=(-865.4678626166876, -742.1170049716059),
            end=(-256.8749966443688, -881.6442646909118),
            width=0.2, layer="F.Cu", net="HV",
        )
    ]
    ref = _ref_calculate_actual_trace_length(board, "HV")
    got = shim_trace_length(board, "HV")
    assert got.hex() == ref.hex()


def test_differential_random_stress():
    """Random float stress with awkward magnitudes — bit-exact via hex().
    ``None`` appears in the net choice: a None-net trace exercises the
    Option<String> marshalling path and must be skipped in both arms."""
    random.seed(2026)
    for _ in range(500):
        traces = [
            (
                random.choice(["HV", "LV", "SIG", None]),
                random.uniform(-1e3, 1e3),
                random.uniform(-1e3, 1e3),
                random.uniform(-1e3, 1e3),
                random.uniform(-1e3, 1e3),
            )
            for _ in range(random.randint(0, 8))
        ]
        board = _board_from_traces(traces)
        nc = {"HV": "HighVoltage", "LV": "Signal", "SIG": "Signal"}
        for net in ("HV", "LV", "SIG", "MISSING"):
            ref_l = _ref_calculate_actual_trace_length(board, net)
            got_l = shim_trace_length(board, net)
            assert got_l.hex() == ref_l.hex()
        ref_c = _ref_calculate_min_hv_lv_clearance(board, nc)
        got_c = shim_min_clearance(board, nc)
        assert got_c.hex() == ref_c.hex()


# ---------------------------------------------------------------------------
# PBT — five non-vacuous properties of the migrated kernels
# ---------------------------------------------------------------------------


@settings(max_examples=30, deadline=None)
@given(
    st.lists(
        st.tuples(st.just("N1"), _COORD, _COORD, _COORD, _COORD),
        min_size=1,
        max_size=8,
    ),
)
def test_prop1_length_is_nonnegative(traces):
    assert shim_trace_length(_board_from_traces(traces), "N1") >= 0.0


@settings(max_examples=30, deadline=None)
@given(
    st.lists(st.tuples(_NET, _COORD, _COORD, _COORD, _COORD), min_size=1, max_size=6),
    st.just("N1"),
)
def test_prop2_length_monotone_in_trace_addition(traces, _):
    """P2: appending a trace never decreases the net's total length."""
    base = shim_trace_length(_board_from_traces(traces), "N1")
    extra = _board_from_traces(traces + [("N1", 0.0, 0.0, 7.0, 0.0)])
    assert shim_trace_length(extra, "N1") >= base


def test_prop3_empty_semantics():
    """P3: empty trace set → length 0.0; missing HV or LV arm → +inf."""
    b = _board_from_traces([])
    assert shim_trace_length(b, "X") == 0.0
    assert math.isinf(shim_min_clearance(b, {}))
    b2 = _board_from_traces([("A", 0.0, 0.0, 1.0, 0.0)])
    assert math.isinf(shim_min_clearance(b2, {"A": "HighVoltage"}))
    assert math.isinf(shim_min_clearance(b2, {"A": "Signal"}))


def test_prop4_single_segment_exact():
    """P4: a single segment's length is exactly sqrt(dx² + dy²) — the
    correctly-rounded IEEE result, checked against math.sqrt."""
    for (x1, y1, x2, y2) in [(0, 0, 3, 4), (1.5, -2.5, 9.25, 0.125), (-1e-7, 2e-7, 5e-7, -3e-7)]:
        b = _board_from_traces([("N1", x1, y1, x2, y2)])
        got = shim_trace_length(b, "N1")
        ref = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        assert got.hex() == ref.hex()


def test_prop5_min_clearance_is_exact_min_of_endpoint_pairs():
    """P5: the kernel result equals the exact minimum over all four
    endpoint-pair Euclidean distances (bit-exact — recomputed with math.sqrt
    on the same operands, and the kernel uses the same operation order)."""
    random.seed(5)
    for _ in range(200):
        hv = [("HV", random.uniform(-100, 100), random.uniform(-100, 100),
               random.uniform(-100, 100), random.uniform(-100, 100)) for _ in range(2)]
        lv = [("LV", random.uniform(-100, 100), random.uniform(-100, 100),
               random.uniform(-100, 100), random.uniform(-100, 100)) for _ in range(2)]
        b = _board_from_traces(hv + lv)
        nc = {"HV": "HighVoltage", "LV": "Signal"}
        got = shim_min_clearance(b, nc)
        best = float("inf")
        for (_, hx1, hy1, hx2, hy2) in hv:
            for (_, lx1, ly1, lx2, ly2) in lv:
                for (px, py) in ((hx1, hy1), (hx2, hy2)):
                    for (qx, qy) in ((lx1, ly1), (lx2, ly2)):
                        d = math.sqrt((px - qx) ** 2 + (py - qy) ** 2)
                        best = min(best, d)
        assert got.hex() == best.hex()


# ---------------------------------------------------------------------------
# Metamorphic relations — three, honestly bounded
# ---------------------------------------------------------------------------


def test_mr1_reverse_trace_direction():
    """MR1: reversing every trace's start/end leaves the length bit-identical
    (dx → -dx exactly; dx² is unchanged) and the HV-LV clearance bit-identical."""
    random.seed(11)
    for _ in range(100):
        traces = [
            (random.choice(["HV", "LV"]), random.uniform(-100, 100), random.uniform(-100, 100),
             random.uniform(-100, 100), random.uniform(-100, 100))
            for _ in range(4)
        ]
        b = _board_from_traces(traces)
        rev = _board_from_traces([(n, x2, y2, x1, y1) for (n, x1, y1, x2, y2) in traces])
        nc = {"HV": "HighVoltage", "LV": "Signal"}
        for net in ("HV", "LV"):
            assert shim_trace_length(b, net).hex() == shim_trace_length(rev, net).hex()
        assert shim_min_clearance(b, nc).hex() == shim_min_clearance(rev, nc).hex()


def test_mr2_permute_traces():
    """MR2: permuting the trace list preserves (a) the length of any net when
    the lengths are exactly representable (axis-aligned integer-coordinate
    segments — each length is an exact integer and the accumulation is
    exact, so ANY accumulation order is bit-identical), and (b) the HV-LV
    clearance unconditionally (a min over a fixed set is order-independent
    — unlike a sum, min is associative)."""
    random.seed(23)
    # axis-aligned, integer coordinates → exact lengths
    traces = [
        (random.choice(["HV", "LV", "SIG"]), float(random.randint(-50, 50)),
         float(random.randint(-50, 50)), 0.0, 0.0)
        for _ in range(6)
    ]
    traces = [(n, x1, y1, x1 + float(random.randint(1, 30)), y1) for (n, x1, y1, _, _) in traces]
    nc = {"HV": "HighVoltage", "LV": "Signal", "SIG": "Signal"}
    base_len = {n: shim_trace_length(_board_from_traces(traces), n) for n in ("HV", "LV", "SIG")}
    base_clr = shim_min_clearance(_board_from_traces(traces), nc)
    for _ in range(5):
        perm = traces[:]
        random.shuffle(perm)
        for n in ("HV", "LV", "SIG"):
            assert shim_trace_length(_board_from_traces(perm), n).hex() == base_len[n].hex()
        assert shim_min_clearance(_board_from_traces(perm), nc).hex() == base_clr.hex()
    # non-exact arm: min-clearance invariance under permutation still holds
    random.seed(24)
    traces2 = [
        (random.choice(["HV", "LV"]), random.uniform(-100, 100), random.uniform(-100, 100),
         random.uniform(-100, 100), random.uniform(-100, 100))
        for _ in range(6)
    ]
    base2 = shim_min_clearance(_board_from_traces(traces2), {"HV": "HighVoltage", "LV": "Signal"})
    for _ in range(5):
        perm = traces2[:]
        random.shuffle(perm)
        assert shim_min_clearance(_board_from_traces(perm), {"HV": "HighVoltage", "LV": "Signal"}).hex() == base2.hex()


def test_mr3_scale_by_two():
    """MR3: scaling all coordinates by exactly 2.0 doubles lengths and
    distances bit-exactly (multiplication by 2 is exact in IEEE-754)."""
    random.seed(31)
    traces = [
        (random.choice(["HV", "LV"]), random.uniform(-50, 50), random.uniform(-50, 50),
         random.uniform(-50, 50), random.uniform(-50, 50))
        for _ in range(4)
    ]
    scaled = [(n, 2.0 * x1, 2.0 * y1, 2.0 * x2, 2.0 * y2) for (n, x1, y1, x2, y2) in traces]
    nc = {"HV": "HighVoltage", "LV": "Signal"}
    for n in ("HV", "LV"):
        a = shim_trace_length(_board_from_traces(traces), n)
        b = shim_trace_length(_board_from_traces(scaled), n)
        assert (2.0 * a).hex() == b.hex()
    a = shim_min_clearance(_board_from_traces(traces), nc)
    b = shim_min_clearance(_board_from_traces(scaled), nc)
    assert (2.0 * a).hex() == b.hex()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
