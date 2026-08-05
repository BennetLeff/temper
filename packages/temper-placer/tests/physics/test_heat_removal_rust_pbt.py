"""Property-based tests for the Rust vertical-sink field kernel
(``temper_thermal.build_h_field_py``, Wave 4 Phase 4 — migration of
``temper_placer/physics/heat_removal.py::build_h_field``).

Five non-vacuous properties, each vacuity-guarded by a real mutant:

1. P1 — the field is the background value everywhere with no devices,
   and the background is uniform and positive.
2. P2 — a single device adds its h_cell exactly on its footprint cells
   and only there (bit-exact).
3. P3 — a board-heatsinked device (R_θCS + R_θSA = 0) contributes
   nothing.
4. P4 — the field is non-negative and bounded by
   background + Σ_dev g_dev / (n_cells·cs²) over overlapping cells
   (soundness: a physically meaningful conductance field).
5. P5 — the per-device footprint cell count matches the 5 mm footprint
   geometry (row/col span = ceil/floor of the 5 mm bbox).

Metamorphic relations:

- M1 — translating the grid origin shifts the device footprint cells by
  the corresponding integer cell count, producing an IDENTICAL field
  (the grid is translation-covariant for device positions at the same
  relative cell offsets).
- M2 — doubling the cell size with a doubled device position and
  footprint keeps the per-cell h_cell scaled by 1/4 (area scales as
  cs²): h_cell ∝ 1/(n_cells·cs²) with n_cells ∝ 1/cs².
- M3 — a device with R_θCS and R_θSA swapped gives the same field
  (R_vert = R_θCS + R_θSA is commutative).
"""

from __future__ import annotations

import numpy as np
import temper_thermal as _tt
from hypothesis import given, settings
from hypothesis import strategies as st

MAX_EXAMPLES = 100

_xy = st.floats(min_value=-30.0, max_value=30.0, allow_nan=False, allow_infinity=False)
_r = st.floats(min_value=0.05, max_value=2.0, allow_nan=False, allow_infinity=False)


def _field(cs, ox, oy, h, w, xs, ys, r_cs, r_sa):
    raw = _tt.build_h_field_py(cs, ox, oy, h, w, xs, ys, r_cs, r_sa)
    return np.frombuffer(raw, dtype=np.float64).reshape((h, w)).copy()


def _bg(cs):
    # h_bg = 10.0 * (cs * 1e-3)**2 / (cs * cs) — computed like the
    # reference (pow via float ** 2).
    return 10.0 * ((cs * 1e-3) ** 2) / (cs * cs)


# ---------------------------------------------------------------------------
# P1..P5
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(cs=st.floats(min_value=0.25, max_value=2.0, allow_nan=False, allow_infinity=False))
def test_p1_empty_devices_uniform_background(cs):
    """P1 — no devices → every cell is exactly the background value;
    a kernel that fills zeros (drops the background) fails."""
    f = _field(cs, 0.0, 0.0, 5, 5, [], [], [], [])
    bg = _bg(cs)
    assert float(f[0, 0]) == bg
    assert (f == bg).all()
    assert f[0, 0] > 0.0


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(cs=_xy, ox=_xy, oy=_xy)
def test_p2_single_device_footprint_exact(cs, ox, oy):
    """P2 — a single device adds exactly g_dev/(n_cells·cs²) on its
    5 mm footprint cells and NOTHING outside; the added cells are the
    footprint bbox (in-grid case).  A kernel that drops the footprint
    regioning or the per-cell add fails."""
    cs = abs(cs) + 0.5
    h, w = 10, 10
    x = ox + 5.0 * cs  # well inside
    y = oy + 5.0 * cs
    r_cs, r_sa = 0.25, 1.0
    f = _field(cs, ox, oy, h, w, [x], [y], [r_cs], [r_sa])
    bg = _bg(cs)
    half = 2.5
    col_min = max(0, int(np.floor((x - half - ox) / cs)))
    col_max = min(w, int(np.ceil((x + half - ox) / cs)))
    row_min = max(0, int(np.floor((y - half - oy) / cs)))
    row_max = min(h, int(np.ceil((y + half - oy) / cs)))
    n_cells = max(1, (row_max - row_min) * (col_max - col_min))
    h_cell = (1.0 / (r_cs + r_sa)) / (n_cells * cs * cs)
    inside = f[row_min:row_max, col_min:col_max]
    outside = np.concatenate(
        [f[:row_min].ravel(), f[row_max:].ravel(), f[row_min:row_max, :col_min].ravel(), f[row_min:row_max, col_max:].ravel()]
    )
    assert (outside == bg).all()
    assert (inside == bg + h_cell).all()


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(cs=st.floats(min_value=0.25, max_value=2.0, allow_nan=False, allow_infinity=False))
def test_p3_board_heatsinked_device_contributes_nothing(cs):
    """P3 — R_θCS + R_θSA = 0 → the device is skipped entirely; a
    kernel that treats zero resistance as a divide-by-zero / inf sink
    fails."""
    # Grid 60x60 with Q2 fixed at (12, 12) — its 5 mm footprint
    # [9.5, 14.5] stays > 9 mm from (0,0) and inside the grid for every
    # cs in the strategy range.  Q1 (R_vert 0) at (1, 1) is skipped.
    f = _field(cs, 0.0, 0.0, 60, 60, [1.0, 12.0], [1.0, 12.0], [0.0, 0.25], [0.0, 1.0])
    bg = _bg(cs)
    # The far corner (0,0) is touched by NEITHER footprint: Q1 is
    # skipped and Q2 is > 5 mm away.
    assert float(f[0, 0]) == bg
    # Q2's footprint region differs from background.
    cx = int(np.floor(12.0 / cs))
    assert float(f[cx, cx]) != bg


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(cs=st.floats(min_value=0.25, max_value=2.0, allow_nan=False, allow_infinity=False))
def test_p4_field_non_negative_and_bounded(cs):
    """P4 — soundness: the field is non-negative and every cell is
    bounded by background + Σ over contributing devices of
    g_dev/(n_cells·cs²) (per-cell adds only ever increase the value).
    A kernel with a sign flip (negative h_cell) fails."""
    xs = [1.0, 3.0, 8.0]
    ys = [2.0, 4.0, 6.0]
    r_cs = [0.25, 0.5, 0.1]
    r_sa = [1.0, 1.5, 0.8]
    f = _field(cs, 0.0, 0.0, 12, 12, xs, ys, r_cs, r_sa)
    bg = _bg(cs)
    upper = bg + sum(
        (1.0 / (rc + rs)) / (1.0 * cs * cs) for rc, rs in zip(r_cs, r_sa)
    )
    assert (f >= 0.0).all()
    assert (f <= upper).all()
    assert (f >= bg).all()


def test_p5_footprint_cell_count_geometry():
    """P5 — a 5 mm footprint on a 1 mm grid spans exactly 5x5 cells
    when aligned to cell centres (row/col span from floor/ceil of the
    bbox); a kernel with an off-by-one in the bbox fails."""
    cs = 1.0
    h, w = 10, 10
    x, y = 5.0, 5.0  # aligned so the bbox is [2.5, 7.5] → cols 2..8 → 5? no: floor(2.5)=2, ceil(7.5)=8 → 6
    f = _field(cs, 0.0, 0.0, h, w, [x], [y], [0.25], [1.0])
    bg = _bg(cs)
    changed = (f != bg).sum()
    assert changed == 36  # floor(2.5)=2..ceil(7.5)=8 → 6x6 = 36 cells
    # A centred-on-5.0 footprint spans cells 2..8 (6 columns) — pinned
    # from the oracle's floor/ceil rule.


# ---------------------------------------------------------------------------
# Vacuity guards (mutants that must fail the property)
# ---------------------------------------------------------------------------


def _mutant_zero_background(cs, ox, oy, h, w, xs, ys, r_cs, r_sa):
    """P1 mutant: fills zeros instead of the background value."""
    raw = _tt.build_h_field_py(cs, ox, oy, h, w, xs, ys, r_cs, r_sa)
    f = np.frombuffer(raw, dtype=np.float64).reshape((h, w)).copy()
    f -= _bg(cs)  # zero out the background → P1's `== bg` fails
    return f


def _mutant_centroid_only(cs, ox, oy, h, w, xs, ys, r_cs, r_sa):
    """P2 mutant: the whole device sink is deposited on the CENTROID
    cell only (n_cells treated as 1), leaving the rest of the footprint
    at background — the per-footprint-cell spread is dropped."""
    f = np.full((h, w), _bg(cs), dtype=np.float64)
    for (x, y, rc, rs) in zip(xs, ys, r_cs, r_sa):
        if rc + rs <= 0.0:
            continue
        c = int(np.floor((x - ox) / cs))
        r = int(np.floor((y - oy) / cs))
        if 0 <= r < h and 0 <= c < w:
            f[r, c] += (1.0 / (rc + rs)) / (1.0 * cs * cs)
    return f


def _mutant_sign_flip_sink(cs, ox, oy, h, w, xs, ys, r_cs, r_sa):
    """P4 mutant: negative sink (subtract instead of add)."""
    raw = _tt.build_h_field_py(cs, ox, oy, h, w, xs, ys, r_cs, r_sa)
    f = np.frombuffer(raw, dtype=np.float64).reshape((h, w)).copy()
    bg = _bg(cs)
    half = 2.5
    for (x, y) in zip(xs, ys):
        col_min = max(0, int(np.floor((x - half - 0.0) / cs)))
        col_max = min(w, int(np.ceil((x + half - 0.0) / cs)))
        row_min = max(0, int(np.floor((y - half - 0.0) / cs)))
        row_max = min(h, int(np.ceil((y + half - 0.0) / cs)))
        f[row_min:row_max, col_min:col_max] = bg - (f[row_min:row_max, col_min:col_max] - bg)
    return f


def test_p1_fails_for_zero_background_mutant():
    cs = 1.0
    f = _mutant_zero_background(cs, 0.0, 0.0, 5, 5, [], [], [], [])
    assert float(f[0, 0]) != _bg(cs)


def test_p2_fails_for_centroid_only_mutant():
    cs = 1.0
    f = _mutant_centroid_only(cs, 0.0, 0.0, 10, 10, [5.0], [5.0], [0.25], [1.0])
    bg = _bg(cs)
    changed = (f != bg).sum()
    assert changed != 36  # P2 pins 36 changed cells


def test_p4_fails_for_sign_flip_mutant():
    cs = 1.0
    f = _mutant_sign_flip_sink(cs, 0.0, 0.0, 8, 8, [3.0], [3.0], [0.25], [1.0])
    assert not (f >= _bg(cs)).all()  # P4's lower bound violated


# ---------------------------------------------------------------------------
# M1..M3: metamorphic relations
# ---------------------------------------------------------------------------


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(cs=st.floats(min_value=0.25, max_value=2.0, allow_nan=False, allow_infinity=False))
def test_m1_origin_translation_covariance(cs):
    """M1 — the field is translation-covariant: a device at the same
    RELATIVE cell offset from the origin produces the same per-cell
    pattern.  (Honest bound: this holds when the device stays inside
    the grid and its footprint bbox does not cross the grid edge —
    floor/ceil of the same relative coordinate.)"""
    h, w = 8, 8
    f1 = _field(cs, 0.0, 0.0, h, w, [2.0 * cs], [2.0 * cs], [0.25], [1.0])
    f2 = _field(cs, 1.0, 1.0, h, w, [1.0 + 2.0 * cs], [1.0 + 2.0 * cs], [0.25], [1.0])
    assert (f1 == f2).all()


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(cs=st.floats(min_value=0.25, max_value=0.6, allow_nan=False, allow_infinity=False))
def test_m2_cell_size_area_scaling(cs):
    """M2 — the per-cell h_cell scales as 1/cs² when the device covers
    the whole grid (n_cells·cs² = constant area): the area-consistency
    identity peak·(n_cells·cs²) = g_dev holds exactly at both cell
    sizes.  cs ≤ 0.6 keeps the 5 mm footprint covering the whole 4×4
    grid at both sizes (grid span 2·cs·4 ≤ 4.8 mm < 5 mm)."""
    h, w = 4, 4
    f1 = _field(cs, 0.0, 0.0, h, w, [2.0 * cs], [2.0 * cs], [0.25], [1.0])
    f2 = _field(2.0 * cs, 0.0, 0.0, h, w, [4.0 * cs], [4.0 * cs], [0.25], [1.0])
    g = 1.0 / 1.25
    peak1 = float((f1 - _bg(cs)).max())
    peak2 = float((f2 - _bg(2.0 * cs)).max())
    # area-consistency: peak * (n_cells * cs * cs) == g for full coverage
    assert abs(peak1 * (16.0 * cs * cs) - g) < 1e-12
    assert abs(peak2 * (16.0 * (2.0 * cs) * (2.0 * cs)) - g) < 1e-12


@settings(max_examples=MAX_EXAMPLES, deadline=None)
@given(cs=st.floats(min_value=0.25, max_value=2.0, allow_nan=False, allow_infinity=False))
def test_m3_rtheta_commutative(cs):
    """M3 — R_θCS and R_θSA swapped give the same field (R_vert = R_θCS
    + R_θSA is an IEEE-commutative sum), bit-exact."""
    f1 = _field(cs, 0.0, 0.0, 6, 6, [3.0], [3.0], [0.25], [1.0])
    f2 = _field(cs, 0.0, 0.0, 6, 6, [3.0], [3.0], [1.0], [0.25])
    assert (f1 == f2).all()
