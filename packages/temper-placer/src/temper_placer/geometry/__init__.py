"""
Geometry engine for temper-placer — Rust-backed via pyo3.

Shim-debt cleanup (2026-08-19): the pure re-export surface (``x = _tg.x``
for ~125 symbols) was collapsed; consumers import those symbols from
``temper_geometry`` directly. This package keeps only:

- the ``ROTATION_*`` constants (static data),
- ``compute_pairwise_distances`` — the re-export the pinned validation
  oracles (``tests/validation/_geometric_py_oracle.py`` and
  ``_validation_metrics_py_oracle.py``) import from this package, and
- ``sdf_gradient`` — takes a Python callable and cannot be ported to Rust.

The ``drc_inflate`` / ``kicad_transform`` submodule re-exports were removed
in Phase 1.4 (2026-08-19): zero importers referenced those names through
this package (consumers use the submodule paths directly).

``smooth_leaky_relu`` remains a small Python boundary because its historical
API supplies defaults that the scalar Rust kernel intentionally leaves
explicit.  The wrapper keeps callers on the placer package surface while
delegating all computation to Rust.
"""

from __future__ import annotations

import math

import temper_geometry as _tg

# ---------------------------------------------------------------------------
# Constants from transform.py (ported to Python since they're static data)
# ---------------------------------------------------------------------------

ROTATION_ANGLES = (0.0, math.pi / 2, math.pi, 3 * math.pi / 2)
ROTATION_ANGLES_DEG = (0.0, 90.0, 180.0, 270.0)

# Applied as rx = M[0][0]*x + M[0][1]*y, ry = M[1][0]*x + M[1][1]*y for a
# local (footprint-relative) point (x, y) at rotation index 0..3 (0/90/180/
# 270 degrees). This is KiCad's real footprint-child rotation, R(-theta) --
# see temper_placer.geometry.kicad_transform's module docstring for the
# confirming evidence. NOT the standard-math R(+theta) matrix a rotation
# index might otherwise suggest -- unused anywhere in this repo as of this
# comment (verified: `grep -rn ROTATION_MATRICES` outside this file), so
# fixing its sign changes no behaviour, but it previously encoded the same
# bug that was independently found and fixed in 12 other places (see
# docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md);
# left un-consolidated (a plain tuple, not a call into kicad_transform) to
# avoid float rounding at exact 90-degree multiples.
ROTATION_MATRICES = (
    ((1.0, 0.0), (0.0, 1.0)),
    ((0.0, 1.0), (-1.0, 0.0)),
    ((-1.0, 0.0), (0.0, -1.0)),
    ((0.0, -1.0), (1.0, 0.0)),
)

# ---------------------------------------------------------------------------
# Pinned-oracle re-export (required by tests/validation/_*_py_oracle.py)
# ---------------------------------------------------------------------------

compute_pairwise_distances = _tg.compute_pairwise_distances


def smooth_leaky_relu(
    x: float, alpha: float = 10.0, negative_slope: float = 0.01
) -> float:
    """Evaluate Rust's smooth leaky-ReLU kernel with stable API defaults."""
    return _tg.smooth_leaky_relu(x, alpha, negative_slope)

# ---------------------------------------------------------------------------
# sdf_gradient — kept as Python wrapper since Rust can't take a callable
# ---------------------------------------------------------------------------


def sdf_gradient(p: tuple[float, float], sdf_fn, eps: float = 1e-4) -> tuple[float, float]:
    """Compute the gradient of an SDF at point p using central finite differences."""
    px, py = p
    dx = (sdf_fn((px + eps, py)) - sdf_fn((px - eps, py))) / (2 * eps)
    dy = (sdf_fn((px, py + eps)) - sdf_fn((px, py - eps))) / (2 * eps)
    length = math.sqrt(dx * dx + dy * dy)
    if length > 1e-12:
        dx /= length
        dy /= length
    return (dx, dy)


__all__ = [n for n in dir() if not n.startswith("_") and n not in ("math", "n")]
