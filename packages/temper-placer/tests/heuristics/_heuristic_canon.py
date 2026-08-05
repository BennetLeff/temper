"""Type-carrying, bit-exact canonicalization for the Wave 4 **Phase 5**
heuristics differentials.

This is the Phase-3 ``tests/core/_contract_canon.py`` convention specialised
for the heuristics surface, with **one deliberate difference that matters**:

``_contract_canon.canon`` canonicalizes a ``set`` to a *sorted* tuple,
because for the Phase-3 index contracts set order genuinely was not part of
the contract. **Here it is.** ``organizational._find_highly_connected_groups``
turns a CPython ``set`` into a ``list`` and that list's order selects each
component's polar angle, so sorting the two arms into agreement would hide
exactly the drift this differential exists to catch (see
``test_hash_order_is_live_and_threaded`` for the measured proof that the
order really does move under ``PYTHONHASHSEED``). ``canon`` below therefore
preserves ``set`` *identity of contents* only where the value is genuinely a
``set`` in the public API, and every ``list`` keeps its live order.

Leaf rules (identical to Phase 3, restated so this file is self-contained):

* ``float`` compares as ``float.hex()`` — an exact bit pattern, never a
  tolerance. ``nan`` normalises to a sentinel so two NaNs compare equal.
* ``bool`` is checked **before** ``int`` (``bool`` is an ``int`` subclass).
* numpy arrays carry ``dtype``, ``shape`` and raw ``tobytes()``.
* numpy scalars keep their own dtype identity, so a ``np.float64`` that
  should have been a Python ``float`` fails loudly.
* every other leaf carries its concrete ``type(...).__name__``.
"""

from __future__ import annotations

from typing import Any

import numpy as np

_NAN = ("float", "nan")

# Field surfaces for the heuristics-owned dataclasses. Listed explicitly (not
# via `vars()`) so that a field added on one arm and not the other shows up as
# a difference instead of being silently skipped.
FIELDS: dict[str, tuple[str, ...]] = {
    "ComponentPlacement": ("ref", "position", "rotation", "confidence", "placed_by"),
    "HeuristicResult": ("placements", "conflicts", "success", "message"),
    "FunctionalModule": ("name", "components", "centroid"),
    "PowerFlowNode": ("ref", "role", "stage"),
    "EdgeAssignment": ("edge", "position", "rotation"),
}


def canon(value: Any) -> Any:
    """Canonicalize `value` into a hashable, type-carrying, bit-exact form."""
    if value is None:
        return ("NoneType",)
    # numpy scalars BEFORE the Python scalar branches. `np.float64` is a
    # genuine *subclass* of Python `float` (`np.int64` and `np.bool_` are not
    # subclasses of `int`/`bool`), so the intuitive ordering silently folds a
    # leaked `np.float64` into `("float", ...)` and the differential can no
    # longer see a numpy scalar escaping where the oracle returned a Python
    # float. The comparator self-test caught exactly this.
    if isinstance(value, np.generic):
        return ("npscalar", str(value.dtype), value.tobytes())
    # bool BEFORE int -- bool is an int subclass, and `True` vs `1` is exactly
    # the drift a Rust `bool`-vs-`i64` return would introduce.
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, float):
        return _NAN if value != value else ("float", value.hex())
    if isinstance(value, int):
        return ("int", value)
    if isinstance(value, str):
        return ("str", value)
    if isinstance(value, bytes):
        return ("bytes", value)
    if isinstance(value, np.ndarray):
        # dtype AND raw bytes: a bool->uint8 or float32->float64 change fails.
        return ("ndarray", str(value.dtype), value.shape, value.tobytes())
    if isinstance(value, (frozenset, set)):
        # Sorted ONLY here, where the public value really is a set and CPython
        # gives no order guarantee to begin with. Lists keep live order below.
        return (type(value).__name__, tuple(sorted(canon(v) for v in value)))
    if isinstance(value, dict):
        # Insertion order IS part of the contract for every dict these
        # heuristics return (placements dicts are iterated downstream).
        return ("dict", tuple((canon(k), canon(v)) for k, v in value.items()))

    name = type(value).__name__
    if name in FIELDS:
        return (name, tuple((f, canon(getattr(value, f))) for f in FIELDS[name]))

    # Netlist `Component` — compared by the identity-bearing subset the
    # heuristics actually read back out.
    if name == "Component" and hasattr(value, "ref") and hasattr(value, "footprint"):
        return (
            "Component",
            tuple(
                (f, canon(getattr(value, f)))
                for f in ("ref", "footprint", "bounds", "net_class", "zone", "fixed")
            ),
        )

    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(canon(v) for v in value))

    raise TypeError(f"canon(): unhandled type {type(value)!r} for value {value!r}")


def canon_call(fn, *args, **kwargs) -> Any:
    """Canonicalize a call's outcome -- value OR raised exception.

    Error parity is part of bit-identical parity: a port that raises
    `TypeError` where the oracle raised `ValueError`, or that changes the
    message text, is a behaviour change.
    """
    try:
        return ("ok", canon(fn(*args, **kwargs)))
    except Exception as exc:  # noqa: BLE001 -- comparing failure modes IS the test
        return ("raised", type(exc).__name__, str(exc))
