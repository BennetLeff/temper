"""Differential tests: temper-thermal Rust copper-coverage kernels vs
the pure-Python reference (temper_placer/physics/copper_coverage.py,
Wave 4 Phase 4).

The pre-migration implementations are pinned here as oracles (verbatim
semantics, including: cell centres `ox + ((col + 0.5) * cs)`; the rect
inside-board compare `cx >= ox && cx <= ox + w && cy >= oy && cy <= oy
+ h`; keepout rects `kx0 <= cx <= kx1 && ky0 <= cy <= ky1`; mounting-
hole circles `(cx - mx)**2 + (cy - my)**2 < kr**2` — where the ARRAY
`** 2` with an int exponent is numpy's per-element x*x MULTIPLY path
(NOT libm pow; measured 2026-08-04 on numpy 2.4.6, they differ by
1 ulp at the discriminators below) while the FLOAT-scalar `kr**2` IS
CPython `float.__pow__` → libm pow — and the `np.minimum(1.0, grid +
cell_cov)` per-trace accumulation with NaN propagation; and the full
`copper_coverage_grid` end to end with traces).  Any change to the Rust
kernels (packages/temper-thermal/src/copper_coverage.rs) or the Python
delegation that disagrees with the oracle fails here, bit-exactly.

Bit-exactness notes (Wave 4 catalog):

- **B1 (host libm via dlsym):** the circle test mixes two `** 2`
  semantics: `(cx - mx) ** 2` on a numpy ARRAY with an int exponent is
  the x*x multiply path (bit-identical to `a * a`, NOT libm pow), while
  `kr ** 2` on a Python FLOAT is libm pow.  The kernel mirrors both
  (mul for the offsets, hostmath pow for the radius); a future reader
  must NOT "normalise" one toward the other — the constructed
  adjacent-float discriminators below pin the divergence.
- **`np.minimum` NaN semantics:** NaN propagates from either operand.
- **Mask accumulation** is bool OR (order-independent); the trace
  accumulation is per-trace in caller list order.
"""

from __future__ import annotations

import random

import numpy as np
import pytest
import temper_thermal as _tt

from temper_placer.core.board import Board, Layer, LayerStackup, MountingHole
from temper_placer.physics.copper_coverage import (
    SANITY_CEILING_C,
    check_thermal_plausibility,
    copper_coverage_grid,
)
from temper_placer.physics.thermal_fdm import ThermalFDMConfig

# ---------------------------------------------------------------------------
# Oracles (pre-migration implementation, verbatim)
# ---------------------------------------------------------------------------


def _oracle_masks(
    h: int,
    w: int,
    ox: float,
    oy: float,
    cs: float,
    board_w: float,
    board_h: float,
    polygon_mask: np.ndarray | None,
    keepouts: list[tuple[float, float, float, float]],
    holes: list[tuple[float, float, float]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Verbatim pre-migration mask arithmetic (the numpy expressions of
    copper_coverage_grid, without the trace path)."""
    row_idx = np.arange(h, dtype=np.float64).reshape(-1, 1)
    col_idx = np.arange(w, dtype=np.float64).reshape(1, -1)
    cx_grid = ox + (col_idx + 0.5) * cs  # (1, w)
    cy_grid = oy + (row_idx + 0.5) * cs  # (h, 1)

    if polygon_mask is not None:
        inside_board = polygon_mask.astype(bool)
    else:
        inside_board = (
            (cx_grid >= ox)
            & (cx_grid <= ox + board_w)
            & (cy_grid >= oy)
            & (cy_grid <= oy + board_h)
        )  # broadcast: (h, w) bool

    in_keepout = np.zeros((h, w), dtype=bool)
    for kx0, ky0, kx1, ky1 in keepouts:
        in_keepout |= (cx_grid >= kx0) & (cx_grid <= kx1) & (cy_grid >= ky0) & (cy_grid <= ky1)
    for mx, my, kr in holes:
        in_keepout |= ((cx_grid - mx) ** 2 + (cy_grid - my) ** 2) < kr**2

    active_area = inside_board & (~in_keepout)
    return inside_board, in_keepout, active_area


def _oracle_trace_accumulate(trace_grid: np.ndarray, cell_cov: np.ndarray) -> np.ndarray:
    """Verbatim pre-migration per-trace accumulation."""
    return np.minimum(1.0, trace_grid + cell_cov)


def _oracle_copper_coverage_grid(
    board: Board,
    fdm_config: ThermalFDMConfig,
    traces: list | None = None,
) -> np.ndarray:
    """Verbatim pre-migration copper coverage grid (with the polygon
    rasteriser kept as the current pure-numpy reference — the shim's
    `_rasterise_polygon_mask` boundary is already Rust and pinned by
    the existing differential)."""
    from temper_placer.physics.thermal_fdm import _trace_to_cell_coverage

    h = fdm_config.height_cells
    w = fdm_config.width_cells
    ox, oy = fdm_config.origin_mm
    cs = fdm_config.cell_size_mm

    stackup = board.layer_stackup
    if stackup is None or len(stackup.layers) == 0:
        return np.zeros((h, w), dtype=np.float64)

    row_idx = np.arange(h, dtype=np.float64).reshape(-1, 1)
    col_idx = np.arange(w, dtype=np.float64).reshape(1, -1)
    cx_grid = ox + (col_idx + 0.5) * cs
    cy_grid = oy + (row_idx + 0.5) * cs

    if board.has_polygon_outline and board.outline_polygon:
        inside_board = _numpy_rasterise_oracle(
            board.outline_polygon, h, w, ox, oy, cs
        )
    else:
        inside_board = (
            (cx_grid >= ox)
            & (cx_grid <= ox + board.width)
            & (cy_grid >= oy)
            & (cy_grid <= oy + board.height)
        )

    in_keepout = np.zeros((h, w), dtype=bool)
    for kx0, ky0, kx1, ky1 in board.keepouts:
        in_keepout |= (cx_grid >= kx0) & (cx_grid <= kx1) & (cy_grid >= ky0) & (cy_grid <= ky1)
    for mh in board.mounting_holes:
        kr = mh.keepout_radius
        mx, my = mh.position
        in_keepout |= ((cx_grid - mx) ** 2 + (cy_grid - my) ** 2) < kr**2

    active_area = inside_board & (~in_keepout)

    total_copper_weight = sum(ly.copper_weight for ly in stackup.layers)
    if total_copper_weight <= 0.0:
        return np.zeros((h, w), dtype=np.float64)

    weighted_sum = np.zeros((h, w), dtype=np.float64)

    for layer in stackup.layers:
        cw = layer.copper_weight
        if cw <= 0.0:
            continue
        if layer.layer_type == "plane":
            weighted_sum += active_area.astype(np.float64) * cw
        elif layer.layer_type in ("signal", "mixed") and traces is not None and layer.is_routable:
            # Rasterise only traces assigned to this layer.
            layer_traces = [t for t in traces if _trace_layer_match_oracle(t, layer.name)]
            if layer_traces:
                trace_grid = np.zeros((h, w), dtype=np.float64)
                for t in layer_traces:
                    if hasattr(t, "start") and hasattr(t, "end"):
                        sx, sy = float(t.start[0]), float(t.start[1])
                        ex, ey = float(t.end[0]), float(t.end[1])
                        tw = getattr(t, "width", 0.5)
                    elif isinstance(t, (list, tuple)) and len(t) >= 4:
                        sx, sy, ex, ey = (float(t[0]), float(t[1]), float(t[2]), float(t[3]))
                        tw = float(t[4]) if len(t) >= 5 else 0.5
                    else:
                        continue
                    cell_cov = _trace_to_cell_coverage(
                        (sx, sy), (ex, ey), tw, (ox, oy), cs, h, w
                    )
                    trace_grid = np.minimum(1.0, trace_grid + cell_cov)
                trace_grid *= active_area.astype(np.float64)
                weighted_sum += trace_grid * cw

    fraction = weighted_sum / total_copper_weight
    return np.clip(fraction, 0.0, 1.0)


def _trace_layer_match_oracle(trace, layer_name: str) -> bool:
    """Verbatim pre-migration trace-layer matcher."""
    if hasattr(trace, "layer"):
        return str(trace.layer) == layer_name
    if isinstance(trace, (list, tuple)) and len(trace) >= 6:
        return str(trace[5]) == layer_name
    return False


def _numpy_rasterise_oracle(polygon, height_cells, width_cells, ox, oy, cs):
    """The pure-numpy ray-casting oracle (from the Wave 3 rasterise
    differential) — used by _oracle_copper_coverage_grid so the whole
    grid can be compared against a fully independent numpy build."""
    mask = np.zeros((height_cells, width_cells), dtype=bool)
    n = len(polygon)
    if n < 3:
        return mask
    px = np.array([p[0] for p in polygon], dtype=np.float64)
    py = np.array([p[1] for p in polygon], dtype=np.float64)
    for row in range(height_cells):
        cy = oy + (row + 0.5) * cs
        for col in range(width_cells):
            cx = ox + (col + 0.5) * cs
            inside = False
            j = n - 1
            for i in range(n):
                yi = py[i]
                yj = py[j]
                if ((yi > cy) != (yj > cy)) and (
                    cx < (px[j] - px[i]) * (cy - yi) / (yj - yi) + px[i]
                ):
                    inside = not inside
                j = i
            mask[row, col] = inside
    return mask


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(h: int, w: int, cs: float, ox: float = 0.0, oy: float = 0.0) -> ThermalFDMConfig:
    return ThermalFDMConfig(cell_size_mm=cs, origin_mm=(ox, oy), height_cells=h, width_cells=w)


def _assert_mask_eq(got, want, label):
    assert got.shape == want.shape and got.dtype == want.dtype
    if not np.array_equal(got, want):
        idx = np.argwhere(got != want)[0]
        raise AssertionError(f"{label}: first mismatch at {tuple(idx)}")


def _assert_grid_eq(got: np.ndarray, want: np.ndarray, label: str) -> None:
    assert got.dtype == want.dtype and got.shape == want.shape, f"{label}: {got.shape} vs {want.shape}"
    eq = (got == want) | (np.isnan(got) & np.isnan(want))
    if not eq.all():
        idx = np.argwhere(~eq)[0]
        raise AssertionError(f"{label}: first mismatch at {tuple(idx)}: {got[tuple(idx)]!r} vs {want[tuple(idx)]!r}")


def _rect_board(stackup, keepouts=None, holes=None) -> Board:
    return Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
        layer_stackup=stackup,
        keepouts=keepouts or [],
        mounting_holes=holes or [],
    )


# ---------------------------------------------------------------------------
# Direct mask kernel pins
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(6))
def test_masks_randomized(seed):
    rng = random.Random(seed)
    h, w = rng.randint(3, 12), rng.randint(3, 12)
    cs = rng.choice([0.5, 1.0, 2.0, 0.25])
    ox, oy = rng.choice([0.0, -2.0, 1.5]), rng.choice([0.0, -1.0])
    board_w, board_h = rng.uniform(5.0, 40.0), rng.uniform(5.0, 40.0)
    keepouts = []
    for _ in range(rng.randint(0, 3)):
        kx0 = rng.uniform(ox - 2.0, ox + board_w)
        ky0 = rng.uniform(oy - 2.0, oy + board_h)
        keepouts.append((kx0, ky0, kx0 + rng.uniform(1.0, 8.0), ky0 + rng.uniform(1.0, 8.0)))
    holes = []
    for _ in range(rng.randint(0, 3)):
        holes.append((rng.uniform(ox, ox + board_w), rng.uniform(oy, oy + board_h), rng.uniform(1.0, 5.0)))
    keep_flat = [v for k in keepouts for v in k]
    hole_flat = [v for hh in holes for v in hh]

    # Rect-board case (no polygon).
    ib, ko, act = _tt.copper_masks_py(h, w, ox, oy, cs, board_w, board_h, False, None, keep_flat, hole_flat)
    got_i = np.frombuffer(ib, dtype=np.bool_).reshape((h, w))
    got_k = np.frombuffer(ko, dtype=np.bool_).reshape((h, w))
    got_a = np.frombuffer(act, dtype=np.bool_).reshape((h, w))
    want_i, want_k, want_a = _oracle_masks(h, w, ox, oy, cs, board_w, board_h, None, keepouts, holes)
    _assert_mask_eq(got_i, want_i, f"masks-inside seed {seed}")
    _assert_mask_eq(got_k, want_k, f"masks-keepout seed {seed}")
    _assert_mask_eq(got_a, want_a, f"masks-active seed {seed}")

    # Polygon case: an L-shaped polygon mask, passed through verbatim.
    pm = np.zeros((h, w), dtype=bool)
    pm[: h // 2, :] = True
    pm[:, : w // 2] = True
    ib2, _, act2 = _tt.copper_masks_py(h, w, ox, oy, cs, board_w, board_h, True, pm.tobytes(), [], [])
    got_i2 = np.frombuffer(ib2, dtype=np.bool_).reshape((h, w))
    got_a2 = np.frombuffer(act2, dtype=np.bool_).reshape((h, w))
    assert np.array_equal(got_i2, pm)
    assert np.array_equal(got_a2, pm)


def test_masks_hole_mul_vs_pow_discriminator():
    # The circle test's `(cx - mx) ** 2` is a numpy ARRAY `** 2` with an
    # integer exponent → numpy's x*x multiply path (measured 2026-08-04;
    # bit-identical to a*a, NOT libm pow — a kernel using libm pow for
    # the offsets is bit-WRONG).  At this cell offset the pow-sum and
    # mul-sum are ADJACENT floats with the radius at the larger one, so
    # a pow-kernel flips the mask bit.  The kernel must match the
    # mul-based oracle.
    import struct

    rng = random.Random(99)
    found = None
    for _ in range(500000):
        aa = rng.uniform(0.1, 3.0)
        bb = rng.uniform(0.1, 3.0)
        pw = (aa**2) + (bb**2)  # libm pow sums (python float ** 2)
        ml = (aa * aa) + (bb * bb)  # numpy mul path
        if struct.pack(">d", pw) != struct.pack(">d", ml) and min(pw, ml) < max(pw, ml):
            # adjacent-float discriminator: the two sums straddle a threshold.
            found = (aa, bb, pw, ml)
            break
    assert found is not None
    aa, bb, pw, ml = found
    t2 = max(pw, ml)
    # pow-sum < t2 <= mul-sum OR mul-sum < t2 <= pow-sum — the two
    # variants genuinely disagree on the comparison.
    assert (pw < t2) != (ml < t2)
    mx = 0.5 - aa
    my = 0.5 - bb
    h, w, cs = 1, 1, 1.0
    ib, ko, _ = _tt.copper_masks_py(h, w, 0.0, 0.0, cs, 1.0, 1.0, False, None, [], [mx, my, t2**0.5])
    got_k = np.frombuffer(ko, dtype=np.bool_).reshape((h, w))
    want_k = _oracle_masks(h, w, 0.0, 0.0, cs, 1.0, 1.0, None, [], [(mx, my, t2**0.5)])[1]
    assert np.array_equal(got_k, want_k)
    # The oracle uses numpy's mul path for the offsets; a libm-pow
    # kernel would give the OPPOSITE bit here.
    oracle_bit = bool(want_k[0, 0])
    mul_sum = (0.5 - mx) * (0.5 - mx) + (0.5 - my) * (0.5 - my)
    pow_sum = (0.5 - mx) ** 2 + (0.5 - my) ** 2
    assert oracle_bit == (mul_sum < t2)
    assert oracle_bit != (pow_sum < t2)  # a pow kernel flips — pin is discriminating


def test_masks_hole_radius_pow_vs_mul_discriminator():
    # The circle test's radius term `kr**2` is a PYTHON float `** 2` →
    # host libm pow (NOT kr*kr — the two differ by 1 ulp at this kr,
    # and the cell offset is constructed so the distance squared equals
    # exactly the SMALLER of the two).  A kr*kr kernel flips the keepout
    # bit; the reference (and this kernel) use pow.  Measured
    # 2026-08-04.
    import math
    import struct

    kr = 2.882033520478047
    p = (kr**2)  # libm pow
    m = kr * kr
    assert struct.pack(">d", p) != struct.pack(">d", m)
    mn = min(p, m)
    dx = math.sqrt(mn)
    assert struct.pack(">d", dx * dx) == struct.pack(">d", mn)  # d2 == min exactly
    d2 = dx * dx
    assert (d2 < p) and not (d2 < m)  # pow: inside; mul: outside
    h, w, cs = 1, 1, 1.0
    mx = 0.5 - dx
    my = 0.5
    ib, ko, _ = _tt.copper_masks_py(h, w, 0.0, 0.0, cs, 1.0, 1.0, False, None, [], [mx, my, kr])
    got_k = np.frombuffer(ko, dtype=np.bool_).reshape((h, w))
    want_k = _oracle_masks(h, w, 0.0, 0.0, cs, 1.0, 1.0, None, [], [(mx, my, kr)])[1]
    assert np.array_equal(got_k, want_k)
    assert bool(got_k[0, 0]) is True  # pow radius: inside the keepout


# ---------------------------------------------------------------------------
# Direct trace-accumulation pins
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(6))
def test_trace_accumulate_randomized(seed):
    rng = random.Random(seed)
    n = rng.randint(1, 200)
    grid = np.array([rng.uniform(0.0, 1.5) for _ in range(n)])
    cov = np.array([rng.uniform(0.0, 1.5) for _ in range(n)])
    got_raw = _tt.copper_trace_accumulate_py(grid.tobytes(), cov.tobytes())
    got = np.frombuffer(got_raw, dtype=np.float64).copy()
    want = _oracle_trace_accumulate(grid, cov)
    _assert_grid_eq(got, want, f"trace-accumulate seed {seed}")


def test_trace_accumulate_nan_propagates():
    grid = np.array([np.nan, 0.5, 1.0])
    cov = np.array([0.5, np.nan, 0.0])
    got_raw = _tt.copper_trace_accumulate_py(grid.tobytes(), cov.tobytes())
    got = np.frombuffer(got_raw, dtype=np.float64).copy()
    want = _oracle_trace_accumulate(grid, cov)
    _assert_grid_eq(got, want, "trace-accumulate nan")
    assert np.isnan(got[0]) and np.isnan(got[1])


# ---------------------------------------------------------------------------
# Module-level end-to-end pins (full grid with keepouts/holes/traces)
# ---------------------------------------------------------------------------


class _Trace:
    def __init__(self, sx, sy, ex, ey, width, layer):
        self.start = (sx, sy)
        self.end = (ex, ey)
        self.width = width
        self.layer = layer


def test_module_grid_keepouts_holes():
    stackup = LayerStackup(
        layers=[
            Layer("F.Cu", "signal", copper_weight=2.0, is_routable=True),
            Layer("In1.Cu", "plane", copper_weight=1.0, is_routable=False),
            Layer("In2.Cu", "plane", copper_weight=1.0, is_routable=False),
            Layer("B.Cu", "signal", copper_weight=1.0, is_routable=True),
        ]
    )
    keepouts = [(10.0, 10.0, 20.0, 20.0), (50.0, 0.0, 60.0, 30.0)]
    holes = [MountingHole(position=(80.0, 80.0), diameter=3.0, keepout_radius=5.0)]
    board = _rect_board(stackup, keepouts, holes)
    cfg = _cfg(20, 20, 5.0)
    got = copper_coverage_grid(board, cfg)
    want = _oracle_copper_coverage_grid(board, cfg)
    _assert_grid_eq(got, want, "grid-keepouts-holes")


def test_module_grid_with_traces():
    stackup = LayerStackup(
        layers=[
            Layer("F.Cu", "signal", copper_weight=2.0, is_routable=True),
            Layer("In1.Cu", "plane", copper_weight=1.0, is_routable=False),
            Layer("In2.Cu", "plane", copper_weight=1.0, is_routable=False),
            Layer("B.Cu", "signal", copper_weight=1.0, is_routable=True),
        ]
    )
    board = _rect_board(stackup)
    cfg = _cfg(20, 20, 5.0)
    traces = [
        _Trace(0.0, 0.0, 40.0, 40.0, 1.0, "F.Cu"),
        _Trace(10.0, 50.0, 60.0, 60.0, 0.8, "F.Cu"),
        _Trace(0.0, 20.0, 20.0, 20.0, 0.5, "B.Cu"),
        (5.0, 5.0, 15.0, 15.0, 1.0, "B.Cu"),  # tuple form
    ]
    got = copper_coverage_grid(board, cfg, traces=traces)
    want = _oracle_copper_coverage_grid(board, cfg, traces=traces)
    _assert_grid_eq(got, want, "grid-traces")


def test_module_grid_no_stackup():
    board = _rect_board(None)
    cfg = _cfg(10, 10, 5.0)
    got = copper_coverage_grid(board, cfg)
    want = _oracle_copper_coverage_grid(board, cfg)
    _assert_grid_eq(got, want, "grid-no-stackup")


def test_module_plausibility_unchanged():
    field = np.zeros((4, 4), dtype=np.float64)
    field[2, 2] = 300.0
    ok, reason = check_thermal_plausibility(field)
    assert ok and "peak 300.0 C" in reason
    field[2, 2] = 500.0
    ok, reason = check_thermal_plausibility(field)
    assert not ok and "sanity ceiling" in reason
    ok, reason = check_thermal_plausibility(None)
    assert not ok and "field is None" in reason
    assert SANITY_CEILING_C == 400.0
