"""Shared numpy→tuple marshaling for the temper-quality-oracle kernels.

Shim-debt cleanup (2026-08-19): the numpy→flat-tuples marshaling that used
to live inline in each metrics module is centralized here.  The
``temper-quality-oracle`` crate has no pyo3-numpy feature, so its kernels
take flat Python tuples; these helpers convert numpy arrays and carry the
source dtype flag WITH the data, because the kernels need it to reproduce
the numpy NEP 50 float32 chains bit-for-bit (see ``aesthetic_score_py``'s
``*_are_f32`` parameters and the wave-4 bit-exactness catalog).

When a crate in this repo gains pyo3-numpy support, this helper is the
single site to delete -- the per-module marshaling copies are gone.
"""

from __future__ import annotations

import numpy as np


def to_float_tuples(arr: np.ndarray) -> tuple[list[tuple[float, ...]], bool]:
    """Convert a 2-D float array to flat Python float tuples plus the f32 flag.

    The ``float(v)`` widening is exact (f32 → f64 never loses precision), so
    the tuples carry the same f64 values pyo3 extracts from the numpy
    scalars of a bare ``tuple(row)`` conversion; the flag preserves the
    source dtype for the kernels' NEP 50 dtype-narrowing reproduction.

    Args:
        arr: A (N, D) float numpy array (``state.positions`` /
            ``state.rotation_logits`` and similar).

    Returns:
        ``(tuples, is_f32)`` where ``tuples`` is a list of D-length float
        tuples and ``is_f32`` is ``arr.dtype == numpy.float32``.
    """
    return [tuple(float(v) for v in row) for row in arr.tolist()], arr.dtype == np.float32
