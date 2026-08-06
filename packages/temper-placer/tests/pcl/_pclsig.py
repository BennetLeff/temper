"""Type-carrying signature comparison for the Wave-4 Phase-2 PCL differentials.

This is the PCL sibling of ``tests/physics/_leafcmp.py``, extended with the
three leaf kinds the PCL contract layer actually produces and physics does
not: ``enum.Enum`` members (which must be compared by *identity*, because
the migration is only correct if Rust hands back the very same singleton
the Python enum module owns), ``set``/``frozenset`` (compared by content,
never by iteration order -- see ``docs/`` note on PYTHONHASHSEED), and
raised exceptions (compared by concrete class *identity* plus message).

Design rule, unchanged from physics: **no tolerance, ever**.  Every float
leaf is rendered as ``float.hex()``, every non-float leaf carries its
concrete type name.  A migration that returns ``int`` where the oracle
returned ``float``, or ``True`` where the oracle returned ``1``, or an
``f32``-rounded value, fails here even though ``==`` would pass.

``test_pclsig_selftest.py`` proves the comparator actually has that power
-- it is the anti-vacuity gate on the gate.
"""

from __future__ import annotations

import enum
import math
from typing import Any

try:  # numpy is present in this repo, but the PCL layer does not require it.
    import numpy as _np
except ImportError:  # pragma: no cover - numpy is a hard dep of temper-placer
    _np = None


def _float_token(v: float) -> str:
    """Exact, sign-complete rendering of a float.

    ``float.hex()`` is exact for every finite and infinite value, but it
    renders BOTH NaN signs as the single string ``'nan'`` -- so a migration
    that flipped a NaN's sign bit would slip through a hex-only comparator.
    (Found by this module's own self-test, not by a differential.) The sign
    is therefore appended explicitly for NaN via ``math.copysign``, which
    reads the sign bit rather than the value.
    """
    if math.isnan(v):
        return "nan+" if math.copysign(1.0, v) > 0 else "nan-"
    return v.hex()


def signature(value: Any) -> Any:
    """Recursively render ``value`` as a hashable, type-carrying signature.

    The returned token is only equal to another token when the two values
    are the same concrete type *and* bit-identical.
    """
    # --- numpy leaves ------------------------------------------------------
    if _np is not None and isinstance(value, _np.ndarray):
        return (
            "ndarray",
            str(value.dtype),
            tuple(value.shape),
            tuple(_float_token(float(v)) for v in value.ravel()),
        )
    if _np is not None and isinstance(value, _np.bool_):
        return ("numpy.bool_", bool(value))
    if _np is not None and isinstance(value, _np.floating):
        # dtype is carried explicitly: float32(0.1) and float64(0.1) have
        # different dtypes AND different hex once widened, but carrying the
        # dtype makes the failure legible instead of merely numeric.
        return ("numpy." + type(value).__name__, str(value.dtype), _float_token(float(value)))
    if _np is not None and isinstance(value, _np.integer):
        return ("numpy." + type(value).__name__, str(value.dtype), int(value))

    # --- enum members: identity, not value ---------------------------------
    # An Enum member is compared by (owning class qualname, member name).
    # Two distinct Enum classes that happen to share names/values are NOT
    # interchangeable for our callers, so the class is part of the token.
    if isinstance(value, enum.Enum):
        return ("enum", type(value).__module__, type(value).__qualname__, value.name)

    # --- scalars -----------------------------------------------------------
    # bool is a subclass of int -- check it first or True collapses into 1.
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, float):
        # _float_token separates 0.0 from -0.0, separates 1-ulp neighbours,
        # and (unlike bare .hex()) separates nan from -nan.
        return ("float", _float_token(value))
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, bytes):
        return ("bytes", value)
    if value is None:
        return ("NoneType", None)

    # --- containers --------------------------------------------------------
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(signature(v) for v in value))
    if isinstance(value, (set, frozenset)):
        # Content comparison. Set iteration order is PYTHONHASHSEED-dependent
        # for str elements and id()-dependent for Enum members, so sorting by
        # the *rendered* signature is the only stable canonical form. This is
        # sound precisely because a set has no observable order; where a
        # caller does observe an order (e.g. the first error raised while
        # iterating a set), the differential passes that order in explicitly
        # instead of relying on this function.
        return (type(value).__name__, tuple(sorted(repr(signature(v)) for v in value)))
    if isinstance(value, dict):
        # dicts ARE ordered in CPython 3.7+, and every dict the PCL layer
        # builds is insertion-ordered from an ordered input, so order is part
        # of the contract and is preserved here.
        return (
            "dict",
            tuple((signature(k), signature(v)) for k, v in value.items()),
        )

    raise AssertionError(f"signature: unhandled leaf type {type(value)!r} ({value!r})")


def assert_same(got: Any, want: Any, context: str = "") -> None:
    """Assert two values are bit-identical *and* the same concrete types."""
    got_sig = signature(got)
    want_sig = signature(want)
    assert got_sig == want_sig, f"{context}\n  rust  = {got_sig!r}\n  oracle= {want_sig!r}"


def call_signature(fn, *args, **kwargs) -> Any:
    """Run ``fn`` and render either its return value or its raised exception.

    Exceptions are part of the public API being migrated, so they are
    compared by concrete class identity (module + qualname) and by the exact
    ``str(exc)`` message -- not merely by "something was raised".
    """
    try:
        return ("return", signature(fn(*args, **kwargs)))
    except BaseException as exc:  # noqa: BLE001 - deliberately catches everything
        cls = type(exc)
        return ("raise", cls.__module__, cls.__qualname__, str(exc))


def assert_same_call(rust_fn, oracle_fn, *args, context: str = "", **kwargs) -> Any:
    """Assert Rust and oracle agree on return value *or* raised exception."""
    got = call_signature(rust_fn, *args, **kwargs)
    want = call_signature(oracle_fn, *args, **kwargs)
    assert got == want, (
        f"{context or f'args={args!r} kwargs={kwargs!r}'}\n  rust  = {got!r}\n  oracle= {want!r}"
    )
    return want
