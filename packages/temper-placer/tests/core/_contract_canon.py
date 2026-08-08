"""Type-carrying, bit-exact canonicalization for the Wave 4 Phase 3
contract differentials (``test_board_rust_differential.py`` /
``test_netlist_rust_differential.py`` and their PBT siblings).

Why this exists rather than plain ``==``
----------------------------------------
The contracts being migrated are plain ``@dataclass``es, which perform **no
coercion**: ``Component("R1", "fp", (1, 2))`` keeps ``int`` bounds and
``Component.width`` returns ``int`` ``1``. Plain ``==`` cannot see the
difference between ``1`` and ``1.0``, nor between a ``float32`` and a
``float64`` numpy array holding the same nominal values -- exactly the two
drifts a Rust port is most likely to introduce.

So every leaf is wrapped with its concrete ``type(...).__name__`` and:

* ``float`` compares as ``float.hex()`` -- an exact bit pattern, never a
  tolerance. ``nan`` is normalised to a single sentinel so two NaNs compare
  equal here (``float('nan') != float('nan')`` would otherwise make every
  comparison involving NaN vacuously "differ" on both sides alike).
* ``bool`` is checked **before** ``int`` (``bool`` is an ``int`` subclass, so
  the naive order would render ``True`` as ``("int", 1)`` and hide a
  ``True``-vs-``1`` drift).
* numpy arrays carry ``dtype``, ``shape`` and raw ``tobytes()`` -- so a
  ``float32`` surface silently widened to ``float64`` fails loudly, which is
  the single sharpest edge in this migration.
* ``set``/``frozenset`` canonicalize to a *sorted* tuple of canonical
  members, because CPython set iteration order is not part of the contract.
* ``dict`` keeps insertion order (it *is* part of the contract for the index
  dicts) and canonicalizes keys and values.

Anything not explicitly handled falls through to ``_canon_object``, which
walks the object's declared field surface -- so a new field on either side
shows up as a difference instead of being silently skipped.
"""

from __future__ import annotations

from typing import Any

import numpy as np

_NAN = ("float", "nan")

# Field surfaces, keyed by class name. Both the pinned Python oracle and the
# Rust pyclass expose exactly these attributes; listing them explicitly (as
# opposed to `vars()`, which a pyclass does not have) is what makes the
# comparison total rather than best-effort.
FIELDS: dict[str, tuple[str, ...]] = {
    # --- netlist.py ---
    "Pin": (
        "name",
        "number",
        "position",
        "net",
        "width",
        "height",
        "shape",
        "layer",
        "drill",
        "is_pth",
        "roundrect_ratio",
        "pad_rotation_deg",
    ),
    "NetlistComponent": (
        "ref",
        "footprint",
        "bounds",
        "pins",
        "net_class",
        "zone",
        "fixed",
        "initial_position",
        "initial_rotation",
        "initial_side",
        "attributes",
        "tags",
        "sheetpath",
    ),
    "Net": ("name", "pins", "net_class", "weight", "max_current", "voltage_class"),
    "Netlist": (
        "components",
        "nets",
        "_component_index",
        "_net_index",
        "_component_nets",
    ),
    # --- board.py ---
    "MountingHole": ("position", "diameter", "keepout_radius"),
    "Pad": ("position", "size", "shape", "layer", "number", "net_name"),
    "BoardComponent": (
        "ref",
        "position",
        "rotation",
        "width",
        "height",
        "footprint",
        "pads",
        "layer",
        "fixed",
    ),
    "Trace": ("start", "end", "width", "layer", "net"),
    "Via": ("position", "drill", "width", "layers", "net", "is_diff_pair"),
    "Layer": ("name", "layer_type", "copper_weight", "is_routable"),
    "LayerStackup": ("layers", "thickness"),
    "Rect": ("x_min", "y_min", "x_max", "y_max"),
    "Zone": (
        "name",
        "bounds",
        "net_classes",
        "components",
        "weight",
        "polygon",
        "layers",
        "max_size",
        "can_expand",
        "zone_type",
    ),
    "GroundDomain": ("name", "bounds", "star_point"),
    "Board": (
        "width",
        "height",
        "origin",
        "zones",
        "mounting_holes",
        "keepouts",
        "ground_domains",
        "layer_stackup",
        "outline_polygon",
        "_zone_map",
    ),
    # --- deterministic leaf data contracts (Phase 5, batch 2) ---
    "DiffPairConfig": (
        "net_pos",
        "net_neg",
        "spacing_mm",
        "coupling_tolerance_mm",
        "max_skew_mm",
    ),
    "LayerAssignment": ("net_name", "layer", "allow_layer_change", "is_plane"),
}

# `Component` is defined by BOTH board.py and netlist.py with different
# fields. Disambiguate by the field surface actually present on the instance.
_COMPONENT_VARIANTS = ("NetlistComponent", "BoardComponent")


def _field_names(value: Any) -> tuple[str, ...] | None:
    name = type(value).__name__
    if name in FIELDS:
        return FIELDS[name]
    if name == "Component":
        for variant in _COMPONENT_VARIANTS:
            variant_fields = FIELDS[variant]
            # `all(())` is vacuously True: an empty `variant_fields` tuple
            # (a future edit to FIELDS, not reachable today -- both current
            # entries are non-empty literals above) would make every
            # `Component` instance match the FIRST variant in
            # `_COMPONENT_VARIANTS` regardless of its actual field surface,
            # silently defeating the disambiguation this function exists to
            # do. Guarded explicitly rather than relying on FIELDS staying
            # non-empty by convention.
            if not variant_fields:
                continue
            if all(hasattr(value, f) for f in variant_fields):
                return variant_fields
    return None


def canon(value: Any) -> Any:
    """Canonicalize `value` into a hashable, type-carrying, bit-exact form."""
    if value is None:
        return ("NoneType",)
    # bool BEFORE int -- bool is an int subclass.
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
        # dtype and raw bytes: a float32->float64 widening fails here.
        return ("ndarray", str(value.dtype), value.shape, value.tobytes())
    if isinstance(value, np.generic):
        # numpy scalars keep their own dtype identity.
        return ("npscalar", str(value.dtype), value.tobytes())
    if isinstance(value, (frozenset, set)):
        return (type(value).__name__, tuple(sorted(canon(v) for v in value)))
    if isinstance(value, dict):
        return ("dict", tuple((canon(k), canon(v)) for k, v in value.items()))

    fields = _field_names(value)
    if fields is not None:
        return _canon_object(value, fields)

    if isinstance(value, (list, tuple)):
        return (type(value).__name__, tuple(canon(v) for v in value))

    raise TypeError(f"canon(): unhandled type {type(value)!r} for value {value!r}")


def _canon_object(value: Any, fields: tuple[str, ...]) -> Any:
    """Canonicalize a contract object by its declared field surface.

    The class *name* is deliberately part of the key, so a `Rect` never
    compares equal to a plain 4-tuple here even though `Rect.__eq__` says it
    does -- the differential asserts that documented tuple-equality
    separately, and must not have it silently paper over a type swap.
    """
    return (
        type(value).__name__,
        tuple((f, canon(getattr(value, f))) for f in fields),
    )


def canon_call(fn, *args, **kwargs) -> Any:
    """Canonicalize a call's outcome -- value OR raised exception.

    Error parity is part of bit-identical parity: a Rust port that raises
    `TypeError` where Python raised `ValueError`, or that changes the message
    text, is a behaviour change. Both the exception *type name* and its
    `str()` are compared.
    """
    try:
        return ("ok", canon(fn(*args, **kwargs)))
    except Exception as exc:  # noqa: BLE001 -- comparing failure modes IS the test
        return ("raised", type(exc).__name__, str(exc))
