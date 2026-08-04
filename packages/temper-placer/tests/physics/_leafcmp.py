"""Type-carrying leaf comparison for the Wave-4 R1a differentials.

A bare `==` between two numbers cannot tell `1` from `1.0`, nor an f32
`0.1` from an f64 `0.1` once numpy up-casts on comparison.  Every
differential in this package therefore compares *signatures*: each leaf
carries its concrete Python/numpy type name alongside an exact value
token (`float.hex()` for floats — never a tolerance), and arrays
additionally carry their `dtype` and `shape`.  A migration that silently
widens f32 to f64, or returns `int` where the oracle returned `float`,
fails here even though the numbers would compare equal.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def leaf_signature(value: Any) -> Any:
    """Recursively render `value` as a hashable, type-carrying signature."""
    if isinstance(value, np.ndarray):
        return (
            "ndarray",
            str(value.dtype),
            tuple(value.shape),
            tuple(float(v).hex() for v in value.ravel()),
        )
    # bool is a subclass of int -- check it first or True becomes 1.
    if isinstance(value, (bool, np.bool_)):
        return (type(value).__name__, bool(value))
    if isinstance(value, (float, np.floating)):
        return (type(value).__name__, float(value).hex())
    if isinstance(value, (int, np.integer)):
        return (type(value).__name__, int(value))
    if isinstance(value, (str, bytes)):
        return (type(value).__name__, value)
    if value is None:
        return ("NoneType", None)
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(leaf_signature(v) for v in value))
    if isinstance(value, dict):
        return (
            "dict",
            tuple((leaf_signature(k), leaf_signature(v)) for k, v in value.items()),
        )
    raise AssertionError(f"leaf_signature: unhandled leaf type {type(value)!r}")


def assert_same(got: Any, want: Any, context: str = "") -> None:
    """Assert two values are bit-identical *and* the same concrete types."""
    got_sig = leaf_signature(got)
    want_sig = leaf_signature(want)
    assert got_sig == want_sig, (
        f"{context}\n  rust  = {got_sig!r}\n  oracle= {want_sig!r}"
    )
