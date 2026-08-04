"""SPECCTRA DSN primitives — delegation shim over the Rust types.

Wave-4 Phase-3 candidate 6, decision D6: ``DSNExpression``, ``dsn_list``,
``DSNRect``, ``DSNCircle`` and ``DSNPath`` were already shipped as pyclasses by
``temper-io-types`` (``src/dsn_types.rs``) but nothing imported them — this
module kept a parallel pure-Python copy, and the exporter used *that*. The two
copies are now one: the Rust types are re-exported here under their existing
names, so every ``from temper_placer.io.dsn import ...`` keeps working.

``DSNPoint``, ``DSNShape`` and ``DSNPolygon`` have no Rust twin and no consumer
anywhere in the repo (measured: zero imports outside this module). They stay as
Python so the module's public surface is unchanged rather than silently
narrowed; retiring them is an R8 residual-candidate decision, not this one's.

Recorded deviations from the retired pure-Python types, all on surfaces no
caller uses:

* ``DSNRect``/``DSNCircle``/``DSNPath`` are pyclasses, not frozen dataclasses:
  they are mutable, unhashable, compare by identity rather than by field, and
  no longer subclass ``DSNShape``. Their ``__repr__`` quotes the layer with
  ``"`` instead of ``'`` and prints floats in Rust's form.
* ``DSNExpression.args`` returns a freshly built ``list`` on each access rather
  than the stored sequence, so mutating the returned list does not mutate the
  expression. ``__str__`` — the only thing the DSN contract depends on — is
  byte-identical, which is what the differential pins.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from temper_io_types import (
    DSNCircle,
    DSNExpression,
    DSNPath,
    DSNRect,
    dsn_list,
)

__all__ = [
    "DSNCircle",
    "DSNExpression",
    "DSNPath",
    "DSNPoint",
    "DSNPolygon",
    "DSNRect",
    "DSNShape",
    "dsn_list",
]


@dataclass(frozen=True)
class DSNPoint:
    """A 2D point in DSN coordinates."""

    x: float
    y: float

    def to_dsn(self) -> DSNExpression:
        # Note: Specctra often uses (at x y) or just x y in different contexts.
        # This point class is for explicit (point x y) if needed.
        return dsn_list("point", self.x, self.y)


@dataclass(frozen=True)
class DSNShape:
    """Base class for DSN shapes."""

    def to_dsn(self) -> DSNExpression:
        raise NotImplementedError


@dataclass(frozen=True)
class DSNPolygon(DSNShape):
    """A polygon/path shape in DSN: (polygon layer width x1 y1 x2 y2 ...)."""

    layer: str
    width: float
    points: Sequence[tuple[float, float]]

    def to_dsn(self) -> DSNExpression:
        args: list[str | float] = [self.layer, self.width]
        for x, y in self.points:
            args.extend([x, y])
        return dsn_list("polygon", *args)
