"""Type-carrying signatures for the Wave-4 Phase 2 R1a differential.

A bare ``==`` between two results cannot tell ``1`` from ``1.0``, an f32
``0.1`` from an f64 ``0.1``, ``True`` from ``1``, ``0.0`` from ``-0.0``,
or two floats a single ulp apart once numpy up-casts on comparison. This
module renders any value as a hashable signature in which

* every float carries ``float.hex()`` -- an exact, lossless token, never
  a tolerance;
* every array carries its ``dtype`` and ``shape`` alongside the hex of
  every element;
* every other leaf carries its **concrete type name**.

It extends ``tests/physics/_leafcmp.py`` (the same idea, used by the
Phase 4 differentials) with the leaf kinds this phase needs: sets and
frozensets, and the four contract objects (``Rect``, ``FabPreset``,
``PinInfo``, ``PlacementViolation``), each of which is reduced to its
public attribute tuple so a Rust pyclass and a Python dataclass produce
the same signature *iff* every attribute matches in value and type.

``test_sig_self.py`` is the anti-vacuity proof for this file: it asserts
that each of the five distinctions above actually changes the signature.
"""

from __future__ import annotations

from typing import Any

import numpy as np

#: Attribute lists for the migrated contract objects, in declaration
#: order. `type_name` is normalised so the Rust class and the pinned
#: oracle dataclass compare equal *as contracts* -- the class identity
#: itself is asserted separately, not smuggled in here.
_CONTRACT_FIELDS: dict[str, tuple[str, ...]] = {
    "Rect": ("x_min", "y_min", "x_max", "y_max"),
    "FabPreset": (
        "name",
        "trace_width_pct",
        "min_trace_mm",
        "min_clearance_mm",
        "etch_undercut_mm",
        "layer_registration_mm",
        "drill_tolerance_mm",
    ),
    "PinInfo": ("x", "y", "net_name", "component_name", "pin_name", "diameter_mm"),
    "PlacementViolation": (
        "item_a",
        "item_b",
        "distance",
        "required",
        "violation_type",
        "message",
    ),
}


def signature(value: Any) -> Any:
    """Render `value` as a hashable, type-carrying signature."""
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

    name = type(value).__name__
    if name in _CONTRACT_FIELDS:
        return (
            name,
            tuple(signature(getattr(value, f)) for f in _CONTRACT_FIELDS[name]),
        )

    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(signature(v) for v in value))
    if isinstance(value, (set, frozenset)):
        # Sets are unordered; sort the *signatures* so the comparison is
        # deterministic without imposing an order on the values.
        return (type(value).__name__, tuple(sorted(map(repr, map(signature, value)))))
    if isinstance(value, dict):
        return ("dict", tuple((signature(k), signature(v)) for k, v in value.items()))
    if isinstance(value, BaseException):
        return ("exception", type(value).__name__, str(value))
    raise AssertionError(f"signature: unhandled leaf type {type(value)!r}")


def call(fn, *args, **kwargs) -> Any:
    """Call `fn`, returning either its value or the exception it raised.

    Exception *type* and *message* are part of the contract, so the
    differential compares them exactly like a return value.
    """
    try:
        return fn(*args, **kwargs)
    except BaseException as exc:  # noqa: BLE001 -- the exception IS the result
        return exc


def assert_same(got: Any, want: Any, context: str = "") -> None:
    """Assert two values are bit-identical *and* the same concrete types."""
    got_sig = signature(got)
    want_sig = signature(want)
    assert got_sig == want_sig, f"{context}\n  rust  = {got_sig!r}\n  oracle= {want_sig!r}"
