"""Restore the dataclass protocol on the Rust contract pyclasses.

Wave 4 Phase 3 candidate 1 replaced the ``core/board.py`` and
``core/netlist.py`` dataclasses with pyo3 pyclasses. The pyclasses reproduce
construction, ``repr``, ``==``, ``hash``, frozen-ness and undeclared-attribute
injection — but a pyclass is not a dataclass, so ``dataclasses.replace()``
raised ``TypeError: replace() should be called on dataclass instances``.

That is not hypothetical. ``deterministic/stages/apply_placements.py`` is
built on it::

    new_comp = replace(component, initial_position=placements_dict[component.ref])
    new_netlist = replace(state.netlist, components=list(updated_components))

``dataclasses.replace(obj, **changes)`` needs exactly two things:

1. ``hasattr(type(obj), "__dataclass_fields__")`` — the ``_is_dataclass_instance``
   check; and
2. that mapping to hold real :class:`dataclasses.Field` objects, because
   ``_replace`` reads ``f.name``, ``f.init`` and ``f._field_type`` off each one
   before calling ``obj.__class__(**changes)``.

Rather than fake ``Field`` (``_field_type`` is a private sentinel), this
module builds a throwaway dataclass with the *same field list and the same
``init`` flags* and installs its genuine ``__dataclass_fields__`` on the
pyclass. Every field is annotated ``Any``: the pyclasses coerce nothing, so
claiming a narrower type here would be a lie that ``dataclasses.fields()``
consumers could act on.

The pyclass constructors already accept every field name as a keyword in
declaration order, which is what ``obj.__class__(**changes)`` needs. Fields
declared ``init=False`` (``Board._zone_map``) are skipped by ``_replace``
exactly as they were before the migration.

Parity for all of this is asserted in
``tests/core/test_board_rust_differential.py`` and
``tests/core/test_netlist_rust_differential.py``.
"""

from __future__ import annotations

import dataclasses
from typing import Any

__all__ = ["install_dataclass_fields"]

# Sentinel default so `make_dataclass` accepts a non-init field.
_UNSET = object()


def install_dataclass_fields(
    cls: type,
    field_names: tuple[str, ...],
    *,
    non_init: tuple[str, ...] = (),
) -> None:
    """Give `cls` a genuine ``__dataclass_fields__`` matching `field_names`.

    Args:
        cls: the pyo3 pyclass to annotate.
        field_names: every field, in declaration order.
        non_init: the subset declared ``init=False`` on the original
            dataclass. ``dataclasses.replace`` skips these and rejects any
            attempt to pass them, which is the pre-migration behaviour.
    """
    spec: list[tuple[str, Any, Any]] = []
    for name in field_names:
        if name in non_init:
            spec.append((name, Any, dataclasses.field(init=False, default=None)))
        else:
            spec.append((name, Any, dataclasses.field(default=_UNSET)))

    prototype = dataclasses.make_dataclass(f"_{cls.__name__}Fields", spec)
    cls.__dataclass_fields__ = prototype.__dataclass_fields__
