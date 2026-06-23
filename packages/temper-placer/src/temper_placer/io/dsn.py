from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence, Union


@dataclass(frozen=True)
class DSNExpression:
    """A SPECCTRA DSN S-expression primitive."""

    name: str
    args: Sequence[Union[str, float, int, DSNExpression]] = field(default_factory=list)
    comment: str | None = None

    def with_comment(self, line: str) -> DSNExpression:
        """Return a copy with a comment line prepended before the S-expression."""
        return DSNExpression(name=self.name, args=self.args, comment=line)

    def __str__(self) -> str:
        def fmt(v) -> str:
            if isinstance(v, DSNExpression):
                return str(v)
            if isinstance(v, float):
                # Format float to remove trailing zeros and ensure decimal point if needed
                s = f"{v:.6f}".rstrip("0").rstrip(".")
                if "." not in s and "e" not in s:
                    # Specctra sometimes needs a decimal point for some fields? 
                    # Actually standard says it can be integer.
                    pass
                return s
            if isinstance(v, str):
                if not v:
                    return '""'
                # Check for special characters that require quoting
                # SPECCTRA is very permissive with identifiers.
                # Only quote if it has spaces, parens or quotes.
                special_chars = set(" ()\"")
                if any(c in special_chars for c in v):
                    # Escape quotes in string
                    escaped = v.replace('"', '\\"')
                    return f'"{escaped}"'
                return v
            return str(v)

        body = f"({self.name})" if not self.args else f"({self.name} {' '.join(fmt(arg) for arg in self.args)})"
        if self.comment:
            return f"{self.comment}\n{body}"
        return body


def dsn_list(name: str, *args) -> DSNExpression:
    """Helper to create a DSN S-expression."""
    return DSNExpression(name, args)


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
class DSNRect(DSNShape):
    """A rectangular shape in DSN: (rect layer x1 y1 x2 y2)."""
    layer: str
    x1: float
    y1: float
    x2: float
    y2: float

    def to_dsn(self) -> DSNExpression:
        return dsn_list("rect", self.layer, self.x1, self.y1, self.x2, self.y2)


@dataclass(frozen=True)
class DSNCircle(DSNShape):
    """A circular shape in DSN: (circle layer diameter [x y])."""
    layer: str
    diameter: float
    x: float = 0.0
    y: float = 0.0

    def to_dsn(self) -> DSNExpression:
        return dsn_list("circle", self.layer, self.diameter, self.x, self.y)


@dataclass(frozen=True)
class DSNPolygon(DSNShape):
    """A polygon/path shape in DSN: (polygon layer width x1 y1 x2 y2 ...)."""
    layer: str
    width: float
    points: Sequence[tuple[float, float]]

    def to_dsn(self) -> DSNExpression:
        args = [self.layer, self.width]
        for x, y in self.points:
            args.extend([x, y])
        return dsn_list("polygon", *args)


@dataclass(frozen=True)
class DSNPath(DSNShape):
    """A path shape in DSN: (path layer width x1 y1 x2 y2 ...)."""
    layer: str
    width: float
    points: Sequence[tuple[float, float]]

    def to_dsn(self) -> DSNExpression:
        args = [self.layer, self.width]
        for x, y in self.points:
            args.extend([x, y])
        return dsn_list("path", *args)
