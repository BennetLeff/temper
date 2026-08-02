"""Differential tests: the U3 conservatism-fence sample geometry, Rust vs oracle.

Wave 3 candidate #1: the sample-generation geometry of
``temper_placer/deterministic/stages/_grid_fence.py``
(``check_clearance_grid_conservatism``) moved to the ``temper-geometry``
crate (``packages/temper-geometry/src/grid_raster.rs``) as
``fence_samples_py``.  The pre-migration sample computation is pinned
here VERBATIM as the oracle.  The orchestration (iterating the expansion
log, calling ``grid.is_available`` per sample, assembling violation
dicts) stays Python.

Bit-exactness notes:
- ``theta = 2.0 * math.pi * i / sample_count_circle`` is a three-op
  left-to-right chain; ``math.pi`` == ``std::f64::consts::PI`` bit-for-bit.
- ``math.cos`` / ``math.sin`` are resolved via ``dlsym`` in the crate so
  they call the exact libm the Python runtime uses (the uv standalone
  build's libm differs from the crate's statically-bound f64::cos/sin in
  the last ulp — measured on a real input; see pad_geometry.rs).
"""

from __future__ import annotations

import math
import random

import temper_geometry as _tg

# ---------------------------------------------------------------------------
# Oracle: the pre-migration sample computation, verbatim
# ---------------------------------------------------------------------------


def _oracle_fence_samples(shape, pos, pad_radius, pad_size, eff_creep, inset, sample_count_circle):
    """The sample-generation block of check_clearance_grid_conservatism, verbatim."""
    samples: list[tuple[float, float]] = []
    if shape in ("rect", "roundrect", "oval") and pad_size[0] > 0 and pad_size[1] > 0:
        cx, cy = pos
        w, h = pad_size
        eff = eff_creep - inset
        # 4 corners expanded by eff on each side
        samples.append((cx - w / 2 - eff, cy - h / 2 - eff))
        samples.append((cx + w / 2 + eff, cy - h / 2 - eff))
        samples.append((cx - w / 2 - eff, cy + h / 2 + eff))
        samples.append((cx + w / 2 + eff, cy + h / 2 + eff))
        # 4 edge midpoints
        samples.append((cx, cy - h / 2 - eff))
        samples.append((cx, cy + h / 2 + eff))
        samples.append((cx - w / 2 - eff, cy))
        samples.append((cx + w / 2 + eff, cy))
    else:
        cx, cy = pos
        r = pad_radius + eff_creep - inset
        for i in range(sample_count_circle):
            theta = 2.0 * math.pi * i / sample_count_circle
            samples.append((cx + r * math.cos(theta), cy + r * math.sin(theta)))
    return samples


def _rust_fence_samples(shape, pos, pad_radius, pad_size, eff_creep, inset, sample_count_circle):
    raw = _tg.fence_samples_py(
        _SHAPE_CODES.get(shape, 99), pos[0], pos[1], pad_radius, pad_size[0], pad_size[1], eff_creep, inset, sample_count_circle
    )
    return [(raw[2 * i], raw[2 * i + 1]) for i in range(len(raw) // 2)]


_SHAPES = ["circle", "rect", "roundrect", "oval", "custom", ""]

# FFI pad-shape code (pad_geometry.rs `SHAPE_*`): 0=circle, 1=oval,
# 2=rect, 3=roundrect, 4=thru_hole; unknown -> 99 (circle branch in
# fence_samples, matching the old unrecognized-string match).
_SHAPE_CODES = {"circle": 0, "oval": 1, "rect": 2, "roundrect": 3, "thru_hole": 4}


def test_circle_samples_match_oracle_on_random_inputs():
    rng = random.Random(20260731)
    for _ in range(500):
        cx, cy = rng.uniform(-100, 100), rng.uniform(-100, 100)
        pad_radius = rng.uniform(0.0, 20.0)
        eff_creep = rng.uniform(0.0, 20.0)
        inset = rng.uniform(0.0, 1.0)
        count = rng.randrange(1, 65)
        shape = rng.choice(_SHAPES)
        pad_size = (rng.uniform(0.0, 10.0), rng.uniform(0.0, 10.0))
        if shape in ("rect", "roundrect", "oval") and pad_size[0] > 0 and pad_size[1] > 0:
            pad_radius = 0.0  # irrelevant for the rect branch
        pos = (cx, cy)
        rust = _rust_fence_samples(shape, pos, pad_radius, pad_size, eff_creep, inset, count)
        oracle = _oracle_fence_samples(shape, pos, pad_radius, pad_size, eff_creep, inset, count)
        assert len(rust) == len(oracle)
        for (rx, ry), (ox, oy) in zip(rust, oracle):
            assert rx == ox, f"x mismatch: {rx!r} vs {ox!r}"
            assert ry == oy, f"y mismatch: {ry!r} vs {oy!r}"


def test_rect_samples_match_oracle_on_random_inputs():
    rng = random.Random(551)
    for _ in range(500):
        cx, cy = rng.uniform(-100, 100), rng.uniform(-100, 100)
        w = rng.uniform(0.05, 30.0)
        h = rng.uniform(0.05, 30.0)
        eff_creep = rng.uniform(0.0, 20.0)
        inset = rng.uniform(0.0, 1.0)
        shape = rng.choice(["rect", "roundrect", "oval"])
        pos = (cx, cy)
        rust = _rust_fence_samples(shape, pos, 0.0, (w, h), eff_creep, inset, 16)
        oracle = _oracle_fence_samples(shape, pos, 0.0, (w, h), eff_creep, inset, 16)
        assert len(rust) == 8 and len(oracle) == 8
        for (rx, ry), (ox, oy) in zip(rust, oracle):
            assert rx == ox, f"x mismatch: {rx!r} vs {ox!r}"
            assert ry == oy, f"y mismatch: {ry!r} vs {oy!r}"


def test_edge_cases():
    # pad_size (0,0) with a rect shape falls through to the circle branch
    for shape, pad_size in [("rect", (0.0, 0.0)), ("roundrect", (0.0, 3.0)), ("circle", (4.0, 4.0))]:
        rust = _rust_fence_samples(shape, (1.0, 2.0), 1.5, pad_size, 0.5, 0.25, 8)
        oracle = _oracle_fence_samples(shape, (1.0, 2.0), 1.5, pad_size, 0.5, 0.25, 8)
        assert len(rust) == len(oracle)
        for (rx, ry), (ox, oy) in zip(rust, oracle):
            assert rx == ox and ry == oy

    # sample_count_circle == 0 and == 1
    for count in (0, 1):
        rust = _rust_fence_samples("circle", (3.0, 4.0), 1.0, (0.0, 0.0), 0.5, 0.25, count)
        oracle = _oracle_fence_samples("circle", (3.0, 4.0), 1.0, (0.0, 0.0), 0.5, 0.25, count)
        assert len(rust) == len(oracle)
        for (rx, ry), (ox, oy) in zip(rust, oracle):
            assert rx == ox and ry == oy


def test_default_fence_scenario_matches():
    """The U3 fence's own default (16 samples, 0.5 mm cell) on a circle pad."""
    samples = _rust_fence_samples("circle", (10.0, 10.0), 1.0, (0.0, 0.0), 2.0, 0.25, 16)
    oracle = _oracle_fence_samples("circle", (10.0, 10.0), 1.0, (0.0, 0.0), 2.0, 0.25, 16)
    assert len(samples) == 16
    for (rx, ry), (ox, oy) in zip(samples, oracle):
        assert rx == ox and ry == oy
