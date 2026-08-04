"""Bit-exact comparison helpers for the topological differential suite.

Floats are compared through ``float.hex()`` -- never a tolerance -- and every
non-float leaf carries its concrete ``type`` into the comparison key, so an
``int``/``float``/``bool`` substitution can never compare equal to the value
it replaced. ``bool`` is checked before ``int`` because ``bool`` is a subclass
of ``int`` in Python and would otherwise be absorbed by it.

NaN is canonicalised to the string ``"nan"`` (``float.hex()`` renders NaN as
``'nan'`` already, and NaN != NaN would make any direct comparison fail even
against itself). Signed zero survives: ``(-0.0).hex() == '-0x0.0p+0'`` while
``(0.0).hex() == '0x0.0p+0'``, so a sign flip on zero is caught.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def key(value: Any) -> Any:
    """Return a hashable, type-tagged, bit-exact comparison key."""
    # numpy scalars first: np.float64 is not a Python float subclass in all
    # paths, and its width is exactly what this suite must not lose.
    if isinstance(value, np.generic):
        return ("np", value.dtype.str, key(value.item()))
    if isinstance(value, np.ndarray):
        return ("ndarray", value.dtype.str, value.shape, tuple(key(v) for v in value.ravel().tolist()))
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, float):
        if math.isnan(value):
            return ("float", "nan")
        return ("float", value.hex())
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, str):
        return ("str", value)
    if value is None:
        return ("none",)
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(key(v) for v in value))
    if isinstance(value, (set, frozenset)):
        # sets are unordered by definition; sort the *keys* so the comparison
        # is order-insensitive exactly where Python itself is.
        return ("set", tuple(sorted((repr(key(v)) for v in value))))
    if isinstance(value, dict):
        return ("dict", tuple(sorted((repr(key(k)), key(v)) for k, v in value.items())))
    raise TypeError(f"no bit-exact comparison key for {type(value)!r}: {value!r}")


def assert_identical(actual: Any, expected: Any, what: str) -> None:
    """Assert two values are bit-identical under :func:`key`."""
    ka, ke = key(actual), key(expected)
    assert ka == ke, f"{what}: bit-parity violated\n  rust  = {ka!r}\n  oracle= {ke!r}"
