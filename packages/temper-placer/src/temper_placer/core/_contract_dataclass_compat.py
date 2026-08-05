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
pyclass.

Why the *full* field surface, not just ``(name, init)``
-------------------------------------------------------
``_replace`` reads only ``name``/``init``/``_field_type``, but
``dataclasses.fields()`` is public API and the pyclasses sit in front of code
that uses it. The pinned pre-migration oracle's ``Field`` metadata is part of
the contract:

* ``f.default`` must be ``dataclasses.MISSING`` where the oracle had a
  ``default_factory``, and the oracle's literal default where it had one.
  ``f.default_factory`` must be the oracle's zero-arg callable (``list`` /
  ``dict`` / ``frozenset`` / the ``lambda`` defaults) — a caller that
  materializes ``field.default_factory()`` must get a fresh, equal default.
* ``f.type`` must be the oracle's annotation, and ``__annotations__`` must be
  installed so ``typing.get_type_hints`` resolves the contract the same way it
  resolves the oracle.

So each ``install_dataclass_fields`` call carries an explicit ``field(...)``
spec that mirrors the oracle field-for-field, and the module writes the
prototype's ``__dataclass_fields__`` *and* ``__annotations__`` onto the
pyclass.

``__module__`` repointing. ``typing.get_type_hints(cls)`` (3.11+) resolves
string annotations against ``sys.modules[cls.__module__]``. The pyclasses'
native module (``temper_design_bundle_python.board_contracts``) does not carry
the contract names (``Rect``, ``Zone``, ``Pin``, ...), so the annotations
would raise ``NameError`` at resolution time. Repointing ``__module__`` at the
public module the class is re-exported from makes the names resolve — the same
names, in the same relative position, that the oracle resolves in
``tests.core._board_py_oracle`` / ``tests.core._netlist_py_oracle``. Instance
``repr`` and ``dataclasses.replace`` do not read ``__module__``; the
differential tests pin both, and they are unaffected.

Parity for all of this is asserted in
``tests/core/test_board_rust_differential.py`` and
``tests/core/test_netlist_rust_differential.py``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any, cast

__all__ = ["FieldSpec", "field", "install_dataclass_fields"]


class FieldSpec:
    """One oracle field: name, annotation string, default / factory, flags.

    ``default`` is the literal default, or ``dataclasses.MISSING`` when the
    oracle field has no literal default. ``default_factory`` is the oracle's
    zero-arg factory, or ``None``. ``init`` / ``repr`` mirror the oracle's
    ``field(...)`` flags.
    """

    __slots__ = ("name", "annotation", "default", "default_factory", "init", "repr")

    def __init__(
        self,
        name: str,
        annotation: str,
        default: Any,
        default_factory: Callable[[], Any] | None,
        init: bool,
        repr: bool,
    ) -> None:
        self.name = name
        self.annotation = annotation
        self.default = default
        self.default_factory = default_factory
        self.init = init
        self.repr = repr


def field(
    name: str,
    annotation: str,
    default: Any = dataclasses.MISSING,
    *,
    default_factory: Callable[[], Any] | None = None,
    init: bool = True,
    repr: bool = True,
) -> FieldSpec:
    """Declare one oracle field for :func:`install_dataclass_fields`.

    Args:
        name: field name, in oracle declaration order.
        annotation: the oracle's annotation, as written (string form). The
            pyclasses coerce nothing, so this is the oracle's own annotation —
            not ``Any`` — and ``f.type`` / ``get_type_hints`` consumers see
            exactly what they saw before the migration.
        default: the oracle's literal default. Omit (or pass
            ``dataclasses.MISSING``) for a field with no literal default —
            either a required field or one backed by ``default_factory``.
        default_factory: the oracle's zero-arg factory (``list``, ``dict``,
            ``frozenset`` or the oracle's ``lambda``), or ``None``.
        init: the oracle's ``init`` flag (``False`` for ``Board._zone_map``).
        repr: the oracle's ``repr`` flag (``False`` for the ``Netlist``
            computed indices).
    """
    if default is not dataclasses.MISSING and default_factory is not None:
        raise ValueError(
            f"field {name!r}: default and default_factory are mutually exclusive"
        )
    return FieldSpec(name, annotation, default, default_factory, init, repr)


def install_dataclass_fields(
    cls: type,
    fields: tuple[FieldSpec, ...],
    *,
    module: str,
) -> None:
    """Give `cls` a genuine ``__dataclass_fields__`` matching the oracle.

    Args:
        cls: the pyo3 pyclass to annotate.
        fields: every oracle field, in declaration order (the oracle's own
            ordering, so non-defaulted fields precede defaulted ones and the
            throwaway prototype's generated ``__init__`` stays valid).
        module: the public module the class is re-exported from; its globals
            are where ``typing.get_type_hints`` resolves the annotation
            strings (see the module docstring).
    """
    spec: list[tuple[str, Any, Any]] = []
    for f in fields:
        if f.default_factory is not None:
            spec.append(
                (
                    f.name,
                    f.annotation,
                    dataclasses.field(
                        default_factory=f.default_factory,
                        init=f.init,
                        repr=f.repr,
                    ),
                )
            )
        elif f.default is not dataclasses.MISSING:
            spec.append(
                (
                    f.name,
                    f.annotation,
                    dataclasses.field(default=f.default, init=f.init, repr=f.repr),
                )
            )
        else:
            spec.append(
                (f.name, f.annotation, dataclasses.field(init=f.init, repr=f.repr))
            )

    # `make_dataclass` is annotated as returning bare `type`, which does not
    # carry `__dataclass_fields__`; neither does the `cls` we write it to.
    # Both ends are narrowed through `Any` at exactly this one expression
    # rather than weakening the `cls: type` parameter. The *consumer* side is
    # fully typed: the pyclass stubs declare
    # `__dataclass_fields__: ClassVar[dict[str, Field[Any]]]`, which is what
    # lets `dataclasses.replace()` type-check at call sites like
    # `deterministic/stages/apply_placements.py`.
    prototype: Any = dataclasses.make_dataclass(f"_{cls.__name__}Fields", spec)
    cast(Any, cls).__dataclass_fields__ = prototype.__dataclass_fields__
    cast(Any, cls).__annotations__ = dict(prototype.__annotations__)
    cast(Any, cls).__module__ = module
