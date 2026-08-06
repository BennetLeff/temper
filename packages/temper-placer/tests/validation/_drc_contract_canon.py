"""Type-carrying, bit-exact canonicalization for the Wave 4 Phase 2
drc_types / drc_result contract differentials
(``test_drc_contracts_rust_differential.py``).

Why this exists rather than plain ``==``
----------------------------------------
The contracts being migrated are plain ``@dataclass``es, which perform **no
coercion**: ``ComponentPlacement(ref="R1", footprint="fp", x=1, ...)`` keeps
``int`` x and ``ComponentPlacement.x`` returns ``int`` ``1``. Plain ``==``
cannot see the difference between ``1`` and ``1.0`` — exactly the drift a
Rust port is most likely to introduce. So every leaf is wrapped with its
concrete ``type(...).__name__`` and:

* ``float`` compares as ``float.hex()`` — an exact bit pattern, never a
  tolerance. ``nan`` is normalised to a single sentinel so two NaNs compare
  equal here (``float('nan') != float('nan')`` would otherwise make every
  comparison involving NaN vacuously "differ" on both sides alike).
* ``bool`` is checked **before** ``int`` (``bool`` is an ``int`` subclass, so
  the naive order would render ``True`` as ``("int", 1)`` and hide a
  ``True``-vs-``1`` drift).
* ``dict`` keeps insertion order (it *is* part of the contract for the
  detail/metrics/component dicts) and canonicalizes keys and values.
* nested contract objects canonicalize by their declared field surface, so
  a new field on either side shows up as a difference instead of being
  silently skipped.
* ``Severity`` canonicalizes as its ``(name, value)`` pair — the dataclass
  ``__eq__`` on an ``Issue`` compares ``severity`` through the enum's own
  equality, so ``name`` plus ``value`` is exactly the distinguishable
  surface.

Anything not explicitly handled falls through to ``_canon_object`` via the
``FIELDS`` surface map below.
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
    # --- drc_result.py ---
    "Location": ("x", "y", "layer"),
    "Severity": ("name", "value"),
    "Issue": (
        "severity",
        "code",
        "message",
        "category",
        "check_name",
        "affected_items",
        "location",
        "details",
        "constraint_id",
    ),
    "CheckResult": (
        "check_name",
        "passed",
        "issues",
        "elapsed_ms",
        "metrics",
    ),
    "RunResult": ("check_results", "total_elapsed_ms"),
    # --- drc_types.py ---
    "ComponentPlacement": (
        "ref",
        "footprint",
        "x",
        "y",
        "rotation",
        "layer",
        "width",
        "height",
        "net_class",
        "voltage_domain",
    ),
    "Placement": (
        "components",
        "nets",
        "zones",
        "board_width",
        "board_height",
        "net_classes",
        "voltage_domains",
        "via_placement",
        "trace_placement",
    ),
    "ClearanceRule": ("from_class", "to_class", "min_mm", "description"),
    "ZoneDefinition": ("name", "bounds", "net_classes", "components"),
    "LoopConstraint": ("name", "nets", "max_area_mm2", "weight", "description"),
    "ThermalConstraint": (
        "components",
        "prefer_edge",
        "min_spacing_mm",
        "max_distance_from_edge_mm",
        "description",
    ),
    "GroupConstraint": (
        "name",
        "components",
        "max_spread_mm",
        "zone",
        "proximity_rules",
        "description",
    ),
    "ConstraintSet": (
        "clearances",
        "zones",
        "critical_loops",
        "thermal_constraints",
        "component_groups",
        "net_classes",
        "voltage_domains",
        "hv_clearance_mm",
        "board_width",
        "board_height",
    ),
    "Via": ("position", "from_layer", "to_layer", "diameter", "drill", "net_name"),
    "ViaPlacement": ("vias",),
    "TraceSegment": ("net_name", "layer", "width", "start", "end"),
    "TracePlacement": ("segments",),
}


def _field_names(value: Any) -> tuple[str, ...] | None:
    return FIELDS.get(type(value).__name__)


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
        return ("ndarray", str(value.dtype), value.shape, value.tobytes())
    if isinstance(value, np.generic):
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

    The class *name* is deliberately part of the key, so a ``Location``
    never compares equal to a plain 3-tuple here even though ``__eq__``
    between a dataclass and a tuple returns ``False`` anyway — the
    differential asserts that separately, and must not have a type swap
    silently papered over.
    """
    return (
        type(value).__name__,
        tuple((f, canon(getattr(value, f))) for f in fields),
    )


def canon_call(fn, *args, **kwargs) -> Any:
    """Canonicalize a call's outcome -- value OR raised exception.

    Error parity is part of bit-identical parity: a Rust port that raises
    ``TypeError`` where Python raised ``ValueError``, or that changes the
    message text, is a behaviour change. Both the exception *type name* and
    its ``str()`` are compared.
    """
    try:
        return ("ok", canon(fn(*args, **kwargs)))
    except Exception as exc:  # noqa: BLE001 -- comparing failure modes IS the test
        return ("raised", type(exc).__name__, str(exc))
