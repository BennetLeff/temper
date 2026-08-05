"""Differential test: deterministic BottleneckMap score/coercion compute,
Rust vs oracle.

Wave 4, **Phase 5** (deterministic hubs slice). The ``score_at`` hot-path
lookup (CPython float floor-division + O(1) row-major index) and the
``_coerce_score`` numeric clamp of ``temper_placer/deterministic/bottleneck_map.py``
move to ``temper_design_bundle_python.deterministic_hubs``. The Python module
keeps its public API (``BottleneckMap`` stays a Python frozen dataclass —
``dataclasses.replace`` and the pinned ``FrozenInstanceError`` behaviour in
``tests/deterministic/test_bottleneck_map.py`` are load-bearing) and delegates
``score_at``/``_coerce_score`` to Rust. The loader orchestration
(``load_bottleneck_map`` — ``board_state`` attribute check + file read + JSON
parse) stays Python.

Numerical pins:
- ``score_at`` uses CPython float **floor-division** ``int(rel_x // cell_size)``
  — the fmod-based algorithm in CPython's ``float_divmod``, NOT a naive
  ``(a / b).floor()``. The Rust kernel replicates the algorithm and the
  differential probes the discriminating classes (exact multiples, near-multiples
  that round to an integer, subnormal cell sizes).
- Empty/degenerate maps (width/height/cell_size <= 0) return ``0.0`` on both
  sides (empty-input semantics pinned).
"""

from __future__ import annotations

import random

import pytest
import temper_design_bundle_python as _tdb
import tests.deterministic._bottleneck_map_py_oracle as _oracle
from tests.core._contract_canon import canon, canon_call

# Rust symbols under test — must exist or this file fails to collect (RED).
_DH = _tdb.deterministic_hubs
RS_SCORE_AT = _DH.bottleneck_score_at
RS_COERCE = _DH.bottleneck_coerce_score


# ---------------------------------------------------------------------------
# score_at parity — direct kernel vs oracle dataclass method
# ---------------------------------------------------------------------------


def _map_fields(seed=0):
    rng = random.Random(seed)
    w = rng.choice([1, 2, 3, 4, 8])
    h = rng.choice([1, 2, 3, 4, 8])
    cell = rng.choice([0.25, 0.5, 1.0, 2.5, 5.0, 0.1])
    ox = rng.choice([-2.0, 0.0, 1.0])
    oy = rng.choice([-1.0, 0.0, 2.0])
    scores = [round(rng.uniform(0, 1), 4) for _ in range(w * h)]
    return w, h, cell, ox, oy, scores


def _probe_points(w, h, cell, ox, oy, seed):
    rng = random.Random(seed + 1000)
    pts = []
    for _ in range(60):
        pts.append((rng.uniform(-20, 20), rng.uniform(-20, 20)))
    # cell boundaries (floor-division discriminating cases)
    for col in range(w + 1):
        x = ox + col * cell
        pts.append((x, oy))
        pts.append((x - 1e-9, oy))
        pts.append((x + 1e-9, oy))
    for row in range(h + 1):
        y = oy + row * cell
        pts.append((ox, y))
        pts.append((ox, y - 1e-9))
        pts.append((ox, y + 1e-9))
    # exact multiples and near-multiples of cell size
    pts.append((ox + 0.3, oy + 0.1))  # 0.3 / 0.1 style near-multiple
    pts.append((ox + 1e308, oy))  # overflow-probe: int(inf) would raise in Python
    pts.append((ox - 1e308, oy))
    return pts


@pytest.mark.parametrize("seed", [0, 1, 2, 3])
def test_score_at_parity(seed):
    w, h, cell, ox, oy, scores = _map_fields(seed)
    oracle_map = _oracle.BottleneckMap(
        cell_size_mm=cell, width=w, height=h, origin_xy=(ox, oy), scores=tuple(scores)
    )
    for (x, y) in _probe_points(w, h, cell, ox, oy, seed):
        o = canon_call(oracle_map.score_at, x, y)
        s = canon_call(RS_SCORE_AT, cell, w, h, ox, oy, list(scores), x, y)
        assert s == o, f"score_at divergence at ({x}, {y}): {s} vs {o}"


def test_score_at_nonfinite_error_parity():
    """NaN/±inf coordinates raise the EXACT Python errors on both sides —
    the floordiv path turns infinite operands into NaN quotients (ValueError),
    while a quotient that overflows to ±inf raises OverflowError. The Rust
    kernel must not silently saturate `as i64` (which would land NaN in cell
    (0, 0))."""
    for (x, y) in [
        (float("nan"), 0.5),
        (0.5, float("nan")),
        (float("inf"), 0.5),
        (float("-inf"), 0.5),
        (1e308, 1e-320),  # quotient overflows to +inf -> OverflowError
        (-1e308, 1e-320),
    ]:
        o = canon_call(
            _oracle.BottleneckMap(
                cell_size_mm=1.0, width=2, height=2, origin_xy=(0.0, 0.0),
                scores=(0.1, 0.1, 0.1, 0.1),
            ).score_at,
            x,
            y,
        )
        s = canon_call(RS_SCORE_AT, 1.0, 2, 2, 0.0, 0.0, [0.1, 0.1, 0.1, 0.1], x, y)
        assert s == o, f"non-finite divergence at ({x}, {y}): {s} vs {o}"


def test_score_at_floor_div_snap_cases():
    """CPython's float floor-division snaps the quotient when fp error lands
    just below an integer: ``8.2 // 0.1 == 81.0`` (div computes to
    80.99999999999999, floor 80, snap -> 81). A naive floor — or a port that
    drops the fmod-subtraction or the snap — yields 80. These are the
    anti-vacuity discriminating probes (M1/M2 in the mutation campaign)."""
    cell = 0.1
    w, h = 200, 2
    # Distinct per-column values so a col-80-vs-81 floor-division slip is
    # observable (a uniform map would mask it).
    scores = [round(0.001 * i, 6) for i in range(w * h)]
    oracle_map = _oracle.BottleneckMap(
        cell_size_mm=cell, width=w, height=h, origin_xy=(0.0, 0.0), scores=tuple(scores)
    )
    for rel in [8.2, 8.7, 16.3, 16.8, 0.3, 9.2]:
        x = rel
        o = canon_call(oracle_map.score_at, x, 0.05)
        s = canon_call(RS_SCORE_AT, cell, w, h, 0.0, 0.0, scores, x, 0.05)
        assert s == o, f"floor-div snap divergence at x={x}: {s} vs {o}"
        assert o[0] == "ok" and o[1][1] != 0.0  # in-grid: real cell, not OOB zero
    # Discriminating pin: CPython computes 8.2 // 0.1 as 81.0 via the snap
    # (div = 80.99999999999999); a naive floor gives col 80.
    assert canon_call(oracle_map.score_at, 8.2, 0.05)[1][1] == scores[81].hex()


def test_score_at_degenerate_maps_parity():
    """width/height/cell_size <= 0 return 0.0 on both sides."""
    degenerate = [
        (0.0, 0, 2, (0.0, 0.0), [0.1, 0.1]),
        (1.0, -1, 2, (0.0, 0.0), [0.1, 0.1]),
        (1.0, 2, 0, (0.0, 0.0), [0.1, 0.1]),
        (-1.0, 2, 2, (0.0, 0.0), [0.1, 0.1, 0.1, 0.1]),
    ]
    for cell, w, h, origin, scores in degenerate:
        oracle_map = _oracle.BottleneckMap(
            cell_size_mm=cell, width=w, height=h, origin_xy=origin, scores=tuple(scores)
        )
        for (x, y) in [(0.0, 0.0), (1.0, 1.0), (-5.0, 5.0)]:
            assert canon(RS_SCORE_AT(cell, w, h, origin[0], origin[1], scores, x, y)) == canon(
                oracle_map.score_at(x, y)
            )


# ---------------------------------------------------------------------------
# _coerce_score parity
# ---------------------------------------------------------------------------


def test_coerce_score_parity():
    cases = [
        0.5,
        0,
        1,
        0.0,
        1.0,
        -0.5,
        1.5,
        -1e-9,
        1 + 1e-9,
        "0.5",
        "1",
        "0",
        0.3,
        0.1,
        True,
        False,
        None,
    ]
    for value in cases:
        o = canon_call(_oracle._coerce_score, value)
        s = canon_call(RS_COERCE, value)
        assert s == o, f"coerce divergence for {value!r}: {s} vs {o}"


def test_coerce_score_rejects_bool_and_none():
    """Booleans and None raise ValueError on both sides (message parity)."""
    for value in [True, False, None]:
        with pytest.raises(ValueError):
            _oracle._coerce_score(value)
        with pytest.raises(ValueError):
            RS_COERCE(value)


# ---------------------------------------------------------------------------
# _from_sidecar_payload parity (payload building drives the Rust coerce)
# ---------------------------------------------------------------------------


def test_from_sidecar_payload_parity():
    payloads = [
        {"cell_size_mm": 1.0, "width": 2, "height": 2, "origin_xy": [0.0, 0.0], "scores": [0.1] * 4},
        {"cell_size_mm": 5.0, "width": 1, "height": 1, "scores": [1.5, -0.5]},  # clamps + truncate
        {"cell_size_mm": 1.0, "width": 2, "height": 2, "scores": [0.2, 0.3]},  # truncated
        {"cell_size_mm": 1.0, "width": 0, "height": 2, "scores": []},  # non-positive dims
        {"cell_size_mm": 1.0, "width": 2, "height": 2, "scores": [0.1, "0.2", 0.3, 0.4]},
        {"cell_size_mm": 1.0, "width": 2, "height": 2, "scores": ["bad", 0.2, 0.3, 0.4]},
        {"cell_size_mm": 1.0, "width": 2, "height": 2, "origin_xy": [0.0], "scores": [0.1] * 4},
        {"cell_size_mm": "x", "width": 2, "height": 2, "scores": [0.1] * 4},
        {},  # missing keys
    ]
    for payload in payloads:
        o = _oracle._from_sidecar_payload(payload)
        s = shim_from_sidecar_payload(payload)
        if o is None or s is None:
            assert (s is None) == (o is None), f"None-parity divergence for {payload!r}"
            continue
        assert (s.cell_size_mm, s.width, s.height, s.origin_xy) == (
            o.cell_size_mm,
            o.width,
            o.height,
            o.origin_xy,
        )
        assert canon(tuple(s.scores)) == canon(tuple(o.scores)), f"scores diverge for {payload!r}"


def shim_from_sidecar_payload(payload):
    from temper_placer.deterministic.bottleneck_map import _from_sidecar_payload

    return _from_sidecar_payload(payload)


def test_load_bottleneck_map_orchestration_unchanged(tmp_path):
    """The loader's preference order (state attr > sidecar > None) is pinned
    by the existing tests; assert the sidecar arm still works end-to-end."""
    import json
    from unittest.mock import Mock

    from temper_placer.deterministic.bottleneck_map import BottleneckMap, load_bottleneck_map

    sidecar = tmp_path / "placement.channels.json"
    sidecar.write_text(
        json.dumps({"cell_size_mm": 1.0, "width": 2, "height": 2, "scores": [0.1, 0.2, 0.3, 0.4]})
    )
    state = Mock()
    state.bottleneck_analysis = None
    result = load_bottleneck_map(state, sidecar_path=sidecar)
    assert isinstance(result, BottleneckMap)
    assert result.score_at(0.5, 0.5) == 0.1
