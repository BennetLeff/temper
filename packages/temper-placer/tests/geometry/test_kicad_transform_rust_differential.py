"""Differential tests: the ``kicad_transform`` shim (Rust-backed via
``temper_geometry.kicad_transform``) vs VERBATIM copies of the
pre-migration pure-Python implementation.

What changed
------------
Before this migration, ``temper_placer.geometry.kicad_transform`` was a
pure-Python module carrying the single sanctioned implementation of KiCad's
footprint-child rotation convention (R(-theta)), and the ``temper_geometry``
crate carried a separately-maintained Rust copy of the same formula
(``transform.rs::transform_pin_position``), pinned to it only by
tolerance-based tests. This migration replaces the pure-Python module with
a thin shim delegating to new Rust kernels in
``packages/temper-geometry/src/kicad_transform.rs`` (exposed as
``temper_geometry.kicad_*_py``); the module's public names, docstrings and
``__all__`` are unchanged, so the 12 consolidated call sites and the
no-raw-rotation-trig lint keep working unchanged. There is now ONE
implementation of the formula (in Rust); the Python side only forwards.

Why the oracles exist
---------------------
Per the Wave-4 discipline contract (G1/G2), the differential pins the shim
against a VERBATIM copy of the module AS COMMITTED before the migration —
the ``_oracle_*`` blocks below, which must not be edited. The Rust kernels
resolve ``cos``/``sin`` through the host process's libm (B1 — the dlsym
pattern shared with ``pad_geometry.rs``), so every assertion is
**bit-exact ``float.hex()`` equality**, not tolerance: a 1-ulp drift in
either direction fails here. ``transform.rs``'s ``transform_pin_position``
still uses the plain statically-bound ``f64::cos``/``f64::sin`` (a second,
tolerance-pinned copy kept for the crate's own consumers — see
``test_transform_pin_position_consistency`` below), which is why the two
are NOT compared bit-exactly here.

``temper_geometry`` is an unconditional, non-optional dependency of
``temper_placer.geometry`` (imported at that package's module level, with
no try/except fallback) — unlike the optional Rust accelerators this repo
also has (``temper_drc_rs``, ``temper_rust_router``), there is no
skip-if-missing story for this one; if it is not importable, essentially
this entire package fails to import, so no skip guard is needed here.
"""

from __future__ import annotations

import math
import random

import pytest

import temper_geometry as _tg
from temper_placer.geometry.kicad_transform import (
    place_local_to_world,
    rotate_local_to_world,
    rotate_local_to_world_deg,
    rotate_world_to_local,
    rotate_world_to_local_deg,
    shapely_rotation_angle_deg,
)
from temper_placer.geometry.transform import transform_pin_position, transform_pin_positions

# ---------------------------------------------------------------------------
# The six kernels, exposed from temper_geometry under the kicad_ prefix
# (the module's shim re-exports them under their public names). Binding
# them here is the G1 import-time RED gate: these attributes do not exist
# until the Rust kernels land, so this module fails to collect before then.
# ---------------------------------------------------------------------------
_RL2W = _tg.kicad_rotate_local_to_world_py
_RL2WD = _tg.kicad_rotate_local_to_world_deg_py
_RW2L = _tg.kicad_rotate_world_to_local_py
_RW2LD = _tg.kicad_rotate_world_to_local_deg_py
_PL2W = _tg.kicad_place_local_to_world_py
_SRA = _tg.kicad_shapely_rotation_angle_deg_py

# ---------------------------------------------------------------------------
# Verbatim pre-migration oracles (copied from the module AS COMMITTED
# before the Wave-4 migration; do not edit — they are the reference).
# ---------------------------------------------------------------------------


def _oracle_rotate_local_to_world(x: float, y: float, theta_rad: float) -> tuple[float, float]:
    """Rotate a local (footprint-relative) offset into world orientation.

    This is R(-theta), KiCad's real footprint-child rotation convention —
    see this module's docstring for the confirming evidence. ``theta_rad``
    is the footprint/component's own board rotation, in radians.
    """
    c, s = math.cos(theta_rad), math.sin(theta_rad)
    return (x * c + y * s, -x * s + y * c)


def _oracle_rotate_local_to_world_deg(x: float, y: float, theta_deg: float) -> tuple[float, float]:
    """Degrees convenience wrapper for :func:`_oracle_rotate_local_to_world`."""
    return _oracle_rotate_local_to_world(x, y, math.radians(theta_deg))


def _oracle_rotate_world_to_local(x: float, y: float, theta_rad: float) -> tuple[float, float]:
    """Inverse of :func:`_oracle_rotate_local_to_world`: rotate a world-oriented
    offset back into the footprint's local frame.

    This is R(+theta) -- the transpose of R(-theta), which for a rotation
    matrix is also its inverse.
    """
    c, s = math.cos(theta_rad), math.sin(theta_rad)
    return (x * c - y * s, x * s + y * c)


def _oracle_rotate_world_to_local_deg(x: float, y: float, theta_deg: float) -> tuple[float, float]:
    """Degrees convenience wrapper for :func:`_oracle_rotate_world_to_local`."""
    return _oracle_rotate_world_to_local(x, y, math.radians(theta_deg))


def _oracle_place_local_to_world(
    local_x: float,
    local_y: float,
    origin_x: float,
    origin_y: float,
    theta_rad: float,
) -> tuple[float, float]:
    """Rotate a local offset by ``theta_rad`` (KiCad convention) and
    translate by ``(origin_x, origin_y)``.
    """
    rx, ry = _oracle_rotate_local_to_world(local_x, local_y, theta_rad)
    return (origin_x + rx, origin_y + ry)


def _oracle_shapely_rotation_angle_deg(theta_deg: float) -> float:
    """The angle (degrees) to pass to ``shapely.affinity.rotate`` to apply
    this module's KiCad rotation convention to a polygon."""
    return -theta_deg


# ---------------------------------------------------------------------------
# Bit-exact comparison helper (G2: `==` via float.hex(), never tolerance)
# ---------------------------------------------------------------------------


def _assert_bit_exact(got, expected, ctx: str) -> None:
    assert len(got) == len(expected), (ctx, got, expected)
    for g, e in zip(got, expected):
        assert float(g).hex() == float(e).hex(), f"{ctx}: {g!r}.hex()={float(g).hex()} != {e!r}.hex()={float(e).hex()}"


# ---------------------------------------------------------------------------
# Exhaustive finite angle set {0, 90, 180, 270} x offset set (plan 011 U2):
# every (angle, offset) pair must agree bit-for-bit with the oracle.
# ---------------------------------------------------------------------------

_FINITE_ANGLE_SET_DEG = (0.0, 90.0, 180.0, 270.0)
_EXHAUSTIVE_OFFSETS = ((0.5, 0.3), (2.0, -1.0), (5.0, 0.0), (3.7, -2.1), (-5.0, 5.0))
_COMP_POSITIONS = ((12.5, -7.25), (0.0, 0.0), (-200.0, 300.0))


@pytest.mark.parametrize("angle_deg", _FINITE_ANGLE_SET_DEG)
@pytest.mark.parametrize("offset", _EXHAUSTIVE_OFFSETS)
def test_rotate_local_to_world_bit_exact_finite_angle_set(angle_deg, offset):
    x, y = offset
    theta = math.radians(angle_deg)
    got = rotate_local_to_world(x, y, theta)
    expected = _oracle_rotate_local_to_world(x, y, theta)
    _assert_bit_exact(got, expected, f"rotate_local_to_world({x}, {y}, {angle_deg}deg)")
    # the degrees wrapper agrees with the radians path bit-for-bit too
    got_deg = rotate_local_to_world_deg(x, y, angle_deg)
    _assert_bit_exact(got_deg, expected, f"rotate_local_to_world_deg({x}, {y}, {angle_deg})")


@pytest.mark.parametrize("angle_deg", _FINITE_ANGLE_SET_DEG)
@pytest.mark.parametrize("offset", _EXHAUSTIVE_OFFSETS)
def test_rotate_world_to_local_bit_exact_finite_angle_set(angle_deg, offset):
    x, y = offset
    theta = math.radians(angle_deg)
    got = rotate_world_to_local(x, y, theta)
    expected = _oracle_rotate_world_to_local(x, y, theta)
    _assert_bit_exact(got, expected, f"rotate_world_to_local({x}, {y}, {angle_deg}deg)")
    got_deg = rotate_world_to_local_deg(x, y, angle_deg)
    _assert_bit_exact(got_deg, expected, f"rotate_world_to_local_deg({x}, {y}, {angle_deg})")


@pytest.mark.parametrize("angle_deg", _FINITE_ANGLE_SET_DEG)
@pytest.mark.parametrize("offset", _EXHAUSTIVE_OFFSETS)
@pytest.mark.parametrize("comp", _COMP_POSITIONS)
def test_place_local_to_world_bit_exact_finite_angle_set(angle_deg, offset, comp):
    lx, ly = offset
    ox, oy = comp
    theta = math.radians(angle_deg)
    got = place_local_to_world(lx, ly, ox, oy, theta)
    expected = _oracle_place_local_to_world(lx, ly, ox, oy, theta)
    _assert_bit_exact(
        got, expected, f"place_local_to_world({lx}, {ly}, {ox}, {oy}, {angle_deg}deg)"
    )


@pytest.mark.parametrize("angle_deg", _FINITE_ANGLE_SET_DEG)
def test_shapely_rotation_angle_bit_exact_finite_angle_set(angle_deg):
    assert shapely_rotation_angle_deg(angle_deg).hex() == (
        _oracle_shapely_rotation_angle_deg(angle_deg).hex()
    )


# ---------------------------------------------------------------------------
# Randomized bit-exact parity (G2): seeded PRNG sweep over board-scale and
# extreme magnitudes. cos/sin are resolved through the host process's libm
# on the Rust side, so even transcendental angles must match bit-for-bit.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(40))
def test_random_bit_exact_parity(seed):
    rng = random.Random(seed * 104729 + 7)
    for _ in range(30):
        theta_rad = rng.uniform(-4 * math.pi, 4 * math.pi)
        x = rng.uniform(-50.0, 50.0)
        y = rng.uniform(-50.0, 50.0)
        ox = rng.uniform(-200.0, 200.0)
        oy = rng.uniform(-200.0, 200.0)
        _assert_bit_exact(
            rotate_local_to_world(x, y, theta_rad),
            _oracle_rotate_local_to_world(x, y, theta_rad),
            f"rl2w(seed {seed}, θ={theta_rad})",
        )
        _assert_bit_exact(
            rotate_world_to_local(x, y, theta_rad),
            _oracle_rotate_world_to_local(x, y, theta_rad),
            f"rw2l(seed {seed}, θ={theta_rad})",
        )
        _assert_bit_exact(
            place_local_to_world(x, y, ox, oy, theta_rad),
            _oracle_place_local_to_world(x, y, ox, oy, theta_rad),
            f"pl2w(seed {seed}, θ={theta_rad})",
        )
        theta_deg = rng.uniform(-720.0, 720.0)
        assert shapely_rotation_angle_deg(theta_deg).hex() == (
            _oracle_shapely_rotation_angle_deg(theta_deg).hex()
        ), f"sra(seed {seed}, θ={theta_deg})"


@pytest.mark.parametrize("seed", range(20))
def test_random_degree_wrappers_bit_exact(seed):
    rng = random.Random(seed * 7919 + 3)
    for _ in range(20):
        theta_deg = rng.uniform(-720.0, 720.0)
        x = rng.uniform(-100.0, 100.0)
        y = rng.uniform(-100.0, 100.0)
        _assert_bit_exact(
            rotate_local_to_world_deg(x, y, theta_deg),
            _oracle_rotate_local_to_world_deg(x, y, theta_deg),
            f"rl2wd(seed {seed}, θ={theta_deg})",
        )
        _assert_bit_exact(
            rotate_world_to_local_deg(x, y, theta_deg),
            _oracle_rotate_world_to_local_deg(x, y, theta_deg),
            f"rw2ld(seed {seed}, θ={theta_deg})",
        )


# ---------------------------------------------------------------------------
# Crafted edge cases (G2): NaN / ±inf / signed zero / denormals / extremes.
# The oracle and the kernel must agree bit-for-bit including the NaN and
# signed-zero conventions.
# ---------------------------------------------------------------------------

_NUMERIC_EDGES = (
    -0.0,
    0.0,
    1.0,
    -1.0,
    5e-324,          # smallest subnormal
    2.2250738585072014e-308,  # largest subnormal
    2.2250738585072014e-308 * 2.0,  # smallest normal
    1e-300,
    1e-18,
    1e-10,
    123456789.123,
    -123456789.123,
    1e200,
    1e308,
    -1e308,
    float("inf"),
    float("-inf"),
    float("nan"),
)

_THETA_EDGES = (
    -0.0,
    0.0,
    math.pi / 2,
    math.pi,
    3 * math.pi / 2,
    -math.pi / 2,
    2 * math.pi,
    -2 * math.pi,
    1e-300,
    1e-12,
    0.1,
    -0.1,
    1e6,
    -1e6,
    float("inf"),
    float("-inf"),
    float("nan"),
)


@pytest.mark.parametrize("x", _NUMERIC_EDGES)
@pytest.mark.parametrize("y", _NUMERIC_EDGES)
@pytest.mark.parametrize("theta_rad", _THETA_EDGES)
def test_rotate_local_to_world_edge_cases_bit_exact(x, y, theta_rad):
    _assert_bit_exact(
        rotate_local_to_world(x, y, theta_rad),
        _oracle_rotate_local_to_world(x, y, theta_rad),
        f"rl2w edges ({x!r}, {y!r}, {theta_rad!r})",
    )


@pytest.mark.parametrize("x", _NUMERIC_EDGES)
@pytest.mark.parametrize("y", _NUMERIC_EDGES)
@pytest.mark.parametrize("theta_rad", _THETA_EDGES)
def test_rotate_world_to_local_edge_cases_bit_exact(x, y, theta_rad):
    _assert_bit_exact(
        rotate_world_to_local(x, y, theta_rad),
        _oracle_rotate_world_to_local(x, y, theta_rad),
        f"rw2l edges ({x!r}, {y!r}, {theta_rad!r})",
    )


@pytest.mark.parametrize("lx", _NUMERIC_EDGES[:12])  # finite only: inf/nan origins
@pytest.mark.parametrize("ly", _NUMERIC_EDGES[:12])
@pytest.mark.parametrize("ox", _NUMERIC_EDGES[:12])
@pytest.mark.parametrize("oy", _NUMERIC_EDGES[:12])
@pytest.mark.parametrize("theta_rad", _THETA_EDGES[:10])  # finite + zero thetas
def test_place_local_to_world_edge_cases_bit_exact(lx, ly, ox, oy, theta_rad):
    _assert_bit_exact(
        place_local_to_world(lx, ly, ox, oy, theta_rad),
        _oracle_place_local_to_world(lx, ly, ox, oy, theta_rad),
        f"pl2w edges ({lx!r}, {ly!r}, {ox!r}, {oy!r}, {theta_rad!r})",
    )


@pytest.mark.parametrize("theta_deg", (-0.0, 0.0, -1e-300, 1e-300, 90.0, 360.0, -720.0, float("nan")))
def test_shapely_rotation_angle_edge_cases_bit_exact(theta_deg):
    assert shapely_rotation_angle_deg(theta_deg).hex() == (
        _oracle_shapely_rotation_angle_deg(theta_deg).hex()
    ), f"sra edge ({theta_deg!r})"


# ---------------------------------------------------------------------------
# The pre-existing separate copy in transform.rs (`transform_pin_position`).
# It is intentionally NOT bit-exact with the shim: it uses the plain
# statically-bound `f64::cos`/`f64::sin` (B1: can differ from the host
# runtime's libm by 1 ulp), and it is kept for the crate's own consumers,
# not the KiCad I/O paths. The historical tolerance pin stays: the two must
# never drift by more than float noise, so a sign flip in either is still
# caught.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("angle_deg", _FINITE_ANGLE_SET_DEG)
@pytest.mark.parametrize("offset", _EXHAUSTIVE_OFFSETS)
@pytest.mark.parametrize("comp", _COMP_POSITIONS)
def test_transform_pin_position_consistency(angle_deg, offset, comp):
    """``transform.rs::transform_pin_position`` stays within float noise of
    the shim's ``place_local_to_world`` (same R(-theta) convention). A sign
    flip in either copy fails here (the anchors at 90/270 with asymmetric
    offsets differ by O(1) between the two conventions)."""
    lx, ly = offset
    ox, oy = comp
    theta = math.radians(angle_deg)
    rust = transform_pin_position(lx, ly, ox, oy, theta)
    python = place_local_to_world(lx, ly, ox, oy, theta)
    assert rust[0] == pytest.approx(python[0], abs=1e-9), (angle_deg, offset, comp)
    assert rust[1] == pytest.approx(python[1], abs=1e-9), (angle_deg, offset, comp)


@pytest.mark.parametrize("angle_deg", _FINITE_ANGLE_SET_DEG)
def test_transform_pin_positions_batch_consistency(angle_deg):
    theta = math.radians(angle_deg)
    comp = _COMP_POSITIONS[0]
    flat = [c for p in _EXHAUSTIVE_OFFSETS for c in p]
    rust_flat = transform_pin_positions(flat, comp[0], comp[1], theta)
    for i, (lx, ly) in enumerate(_EXHAUSTIVE_OFFSETS):
        python = place_local_to_world(lx, ly, comp[0], comp[1], theta)
        assert rust_flat[2 * i] == pytest.approx(python[0], abs=1e-9), (angle_deg, (lx, ly))
        assert rust_flat[2 * i + 1] == pytest.approx(python[1], abs=1e-9), (angle_deg, (lx, ly))
