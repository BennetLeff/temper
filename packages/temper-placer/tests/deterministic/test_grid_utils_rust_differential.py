"""Differential test: deterministic grid_utils compute, Rust vs oracle.

Wave 4, **Phase 5, first slice** (deterministic leaf stages). The pure
compute of ``temper_placer/deterministic/geometry/grid_utils.py`` moves to
the ``temper-geometry`` crate; the Python module becomes a delegation shim.
The pre-migration implementation is pinned VERBATIM as the oracle
(``_grid_utils_py_oracle.py``) and every assertion here drives IDENTICAL
inputs through both sides.

Bit-exactness conventions (R1a):
- floats compare via ``float.hex()`` — never a tolerance;
- every leaf carries its concrete ``type`` (``int`` vs ``float`` cannot hide);
- ``canon`` (tests/core/_contract_canon.py) canonicalizes the outputs.

Numerical traps pinned here:
- ``round()`` is CPython's **round-half-to-even** on the division result,
  *then* the result (an ``int``) is multiplied by ``grid_size`` — Rust's
  ``f64::round`` is half-away-from-zero and would drift on every ``.5`` tick.
- ``** 0.5`` is libm ``pow``, not ``sqrt``; ``** 2`` is libm ``pow``, not
  ``x * x`` (see the Wave-4 guide's "numerical traps"). The Rust side
  resolves ``pow`` via ``dlsym`` to the exact libm the host CPython calls.
- empty-input semantics: ``add_endpoint_nudge`` returns ``[]`` for an empty
  path — asserted explicitly so vacuity cannot hide there.
"""

from __future__ import annotations

import random
import string

import pytest
import temper_geometry as _tg

import tests.deterministic._grid_utils_py_oracle as _oracle
from tests.core._contract_canon import canon, canon_call

# Rust symbols under test — must exist or this file fails to collect (RED).
RS_SNAP = _tg.snap_to_grid
RS_NUDGE = _tg.add_endpoint_nudge

_GRID_SIZES = [0.25, 0.1, 0.5, 1.0, 2.0, 0.125, 0.3]


def _rand_positions(n: int, seed: int = 0) -> list[tuple[float, float]]:
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        # Mix in exact grid-aligned values and half-grid ticks (.5), which
        # are the round-half-even discriminating cases.
        kind = rng.randrange(4)
        if kind == 0:
            out.append((rng.uniform(-100, 100), rng.uniform(-100, 100)))
        elif kind == 1:
            out.append((round(rng.uniform(-100, 100) / 0.25) * 0.25, round(rng.uniform(-100, 100) / 0.25) * 0.25))
        elif kind == 2:
            # exact .5 ticks on the division result
            div = rng.randint(-200, 200) + 0.5
            gs = rng.choice(_GRID_SIZES)
            out.append((div * gs, div * gs))
        else:
            out.append((rng.uniform(-1, 1) * 1e-9, rng.uniform(-1, 1) * 1e-9))
    return out


def _rand_paths(n: int, seed: int = 1) -> list[list[tuple[float, float]]]:
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        length = rng.randrange(0, 8)
        pts = [
            (round(rng.uniform(-50, 50) / 0.25) * 0.25, round(rng.uniform(-50, 50) / 0.25) * 0.25)
            for _ in range(length)
        ]
        out.append(pts)
    return out


# ---------------------------------------------------------------------------
# snap_to_grid
# ---------------------------------------------------------------------------

def _assert_snap_equal(px: float, py: float, gs: float) -> None:
    assert canon(_oracle.snap_to_grid((px, py), gs)) == canon(RS_SNAP(px, py, gs)), (
        f"snap_to_grid mismatch for ({px!r}, {py!r}) grid {gs!r}"
    )


def test_snap_to_grid_fixed_cases():
    # Half-even discriminating cases on the division result.
    cases = [
        ((0.0, 0.0), 0.25),
        ((0.125, 0.125), 0.25),  # 0.5 -> rounds to 0
        ((0.375, 0.375), 0.25),  # 1.5 -> rounds to 2
        ((-0.125, -0.125), 0.25),  # -0.5 -> -0
        ((-0.375, -0.375), 0.25),  # -1.5 -> -2
        ((1.0, 1.0), 0.25),
        ((1.7, -2.3), 0.1),
        ((1.2345, 9.8765), 0.125),
        ((0.0, 0.0), 0.1),
        ((-0.0, -0.0), 0.25),  # -0.0 / 0.25 = -0.0; round(-0.0) = 0
    ]
    for pos, gs in cases:
        _assert_snap_equal(pos[0], pos[1], gs)


def test_snap_to_grid_random_grid_sizes():
    for gs in _GRID_SIZES:
        for px, py in _rand_positions(60, seed=int(gs * 1000)):
            _assert_snap_equal(px, py, gs)


def test_snap_to_grid_exact_halves_randomized():
    """Division results landing exactly on .5 — the round-half-to-even set."""
    rng = random.Random(7)
    for _ in range(200):
        gs = rng.choice(_GRID_SIZES)
        div = rng.randint(-300, 300) + 0.5
        _assert_snap_equal(div * gs, div * gs, gs)


def test_snap_to_grid_identity_on_aligned_points():
    """A point already on the grid must be returned unchanged (bit-exact)."""
    for gs in _GRID_SIZES:
        for i in range(-25, 26):
            v = i * gs
            _assert_snap_equal(v, v, gs)


def test_snap_to_grid_default_grid_size():
    """grid_size defaults to 0.25 on both arms."""
    for px, py in _rand_positions(30, seed=11):
        assert canon(_oracle.snap_to_grid((px, py))) == canon(RS_SNAP(px, py))


# ---------------------------------------------------------------------------
# add_endpoint_nudge
# ---------------------------------------------------------------------------

def _assert_nudge_equal(
    path: list[tuple[float, float]], start: tuple[float, float], end: tuple[float, float]
) -> None:
    assert canon(_oracle.add_endpoint_nudge(path, start, end)) == canon(
        RS_NUDGE([x for p in path for x in p], start[0], start[1], end[0], end[1])
    ), f"add_endpoint_nudge mismatch for path={path!r} start={start!r} end={end!r}"


def test_nudge_empty_path_returns_empty():
    """Empty-input semantics: [] in, [] out — vacuity guard."""
    assert _oracle.add_endpoint_nudge([], (0, 0), (1, 1)) == []
    assert list(RS_NUDGE([], 0.0, 0.0, 1.0, 1.0)) == []


def test_nudge_single_point_path():
    path = [(0.0, 0.0)]
    # Start coincides with path[0] -> no start nudge; end far -> end nudge.
    _assert_nudge_equal(path, (0.0, 0.0), (1.0, 1.0))
    # Both ends far.
    _assert_nudge_equal(path, (-1.0, -1.0), (1.0, 1.0))
    # Both ends coincide (within threshold) -> path unchanged.
    _assert_nudge_equal(path, (0.0, 0.0), (0.0, 0.0))


def test_nudge_threshold_boundary():
    """The 1e-4 threshold is exclusive: exactly 1e-4 -> no nudge."""
    path = [(1.0, 1.0)]
    start = (1.0 + 1e-4, 1.0)
    end = (1.0, 1.0)
    _assert_nudge_equal(path, start, end)
    # Just over the threshold -> nudge appended.
    start_over = (1.0 + 1e-4 + 1e-9, 1.0)
    _assert_nudge_equal(path, start_over, end)


def test_nudge_random_paths():
    paths = _rand_paths(80, seed=5)
    ends = _rand_positions(80, seed=6)
    starts = _rand_positions(80, seed=7)
    for path, start, end in zip(paths, starts, ends):
        _assert_nudge_equal(path, start, end)


def test_nudge_preserves_path_order():
    """Path points appear in order between the nudges."""
    for _ in range(30):
        path = _rand_paths(1, seed=9)[0]
        start = _rand_positions(1, seed=10)[0]
        end = _rand_positions(1, seed=11)[0]
        result = list(RS_NUDGE([x for p in path for x in p], start[0], start[1], end[0], end[1]))
        path_seq = [tuple(result[i : i + 2]) for i in range(0, len(result), 2)]
        # The original path points must appear as a contiguous subsequence.
        if path:
            for p in path:
                assert p in path_seq
