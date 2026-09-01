"""A small, self-contained reader for the ``.ato`` (atopile) design sources.

Why this exists instead of calling ``ato``
------------------------------------------
``scripts/check_ato_assertion_vacuity.py`` needs to answer a question the
atopile toolchain cannot answer for us: *for each assertion, which quantities
does its truth value actually depend on, and can that truth value ever
change?*  Answering it requires (a) the assertion's expression tree, (b) the
definition of every name in that tree, and (c) the ability to re-evaluate the
assertion under a perturbed value.

The atopile CLI is not usable for that here:

* It is not installed.  ``make netlist`` shells out to
  ``uv tool run --from 'atopile>=0.2,<0.3' ato ...``, i.e. it downloads the
  tool on demand.  A CI gate that needs a network fetch of a pinned-range
  third-party solver before it can report anything is a gate that will be
  disabled the first time PyPI is slow.
* Its build output (``elec/build/default.net``) is a *netlist*.  Assertions
  are consumed by the solver and do not survive into it, so the artifact that
  a build produces cannot be inspected for this property at all.
* Perturbation would require mutating ``elec/src/**`` and re-running a full
  solve per mutation.  At 71 assertions x N perturbations that is thousands of
  solver invocations, and three other agents are concurrently editing those
  files.

So this module parses the sources directly.  It is deliberately a *partial*
reader: it understands declarations, instantiations, attribute assignment and
assertions, and it ignores connections (``~``), pins, footprints and traits,
which carry no information about whether an assertion can fail.  Everything it
does not understand it reports as unresolved rather than guessing --- see
``UNRESOLVED`` handling in the caller.  A vacuity detector that silently
skipped the expressions it could not read would itself be vacuous.

Scope of the grammar handled (verified against elec/src/*.ato):

* ``module|component|interface NAME:`` blocks, nestable, indentation-scoped.
* Triple-quoted docstrings (single- and multi-line) are skipped as content.
* ``name = new TypeName`` / ``a.b = new TypeName`` instantiation.
* ``name: unit_type = expr`` typed declaration with value.
* ``name: unit_type`` typed declaration without value (abstract slot).
* ``a.b.c = expr`` attribute assignment.
* ``assert EXPR`` where EXPR is a comparison or a ``within`` band.
* ``import X from "file.ato"`` (used only to know a name is external).
* Numeric literals with unit suffixes and optional ``+/-`` tolerance.

There is no ``from``-style inheritance anywhere in elec/src, so none is
implemented; ``parse_file`` raises on encountering it rather than silently
dropping the base class.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------
# Dimension vector order: (length, mass, time, current, temperature).
Dim = tuple[int, int, int, int, int]

DIMENSIONLESS: Dim = (0, 0, 0, 0, 0)

_BASE_UNITS: dict[str, tuple[float, Dim]] = {
    "": (1.0, DIMENSIONLESS),
    "V": (1.0, (2, 1, -3, -1, 0)),
    "A": (1.0, (0, 0, 0, 1, 0)),
    "W": (1.0, (2, 1, -3, 0, 0)),
    "ohm": (1.0, (2, 1, -3, -2, 0)),
    "Ohm": (1.0, (2, 1, -3, -2, 0)),
    "Ω": (1.0, (2, 1, -3, -2, 0)),
    "F": (1.0, (-2, -1, 4, 2, 0)),
    "H": (1.0, (2, 1, -2, -2, 0)),
    "Hz": (1.0, (0, 0, -1, 0, 0)),
    "s": (1.0, (0, 0, 1, 0, 0)),
    "K": (1.0, (0, 0, 0, 0, 1)),
    "m": (1.0, (1, 0, 0, 0, 0)),
    "C": (1.0, (0, 0, 1, 1, 0)),
    "J": (1.0, (2, 1, -2, 0, 0)),
    "VA": (1.0, (2, 1, -3, 0, 0)),
    "percent": (0.01, DIMENSIONLESS),
}

_PREFIXES: dict[str, float] = {
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "µ": 1e-6,
    "m": 1e-3,
    "k": 1e3,
    "K": 1e3,
    "M": 1e6,
    "G": 1e9,
}

# Unit-type annotations used in ``name: <type> = ...`` declarations.  These are
# atopile's physical-dimension names; they carry no magnitude.
TYPE_ANNOTATIONS: frozenset[str] = frozenset(
    {
        "voltage",
        "current",
        "power",
        "resistance",
        "capacitance",
        "inductance",
        "frequency",
        "time",
        "temperature",
        "length",
        "dimensionless",
        "int",
        "energy",
        "charge",
    }
)


class UnitError(ValueError):
    """Raised when a unit string cannot be resolved or dimensions clash."""


def parse_unit(text: str) -> tuple[float, Dim]:
    """Resolve a unit suffix such as ``kohm`` or ``nF`` to (scale, dimension).

    Exact base-unit matches win over prefix decomposition so that ``m`` is a
    metre rather than a milli-nothing, and ``K`` is a kelvin rather than a
    kilo-nothing.
    """
    if text in _BASE_UNITS:
        return _BASE_UNITS[text]
    if len(text) >= 2 and text[0] in _PREFIXES:
        rest = text[1:]
        if rest in _BASE_UNITS and rest != "":
            scale, dim = _BASE_UNITS[rest]
            return (scale * _PREFIXES[text[0]], dim)
    raise UnitError(f"unknown unit {text!r}")


def _dim_add(left: Dim, right: Dim) -> Dim:
    """Component-wise sum, preserving the fixed 5-tuple shape of ``Dim``."""
    return (
        left[0] + right[0],
        left[1] + right[1],
        left[2] + right[2],
        left[3] + right[3],
        left[4] + right[4],
    )


def _dim_sub(left: Dim, right: Dim) -> Dim:
    return _dim_add(left, (-right[0], -right[1], -right[2], -right[3], -right[4]))


def format_dim(dim: Dim) -> str:
    """Render a dimension vector using a familiar unit name where one exists."""
    for name, (scale, base) in _BASE_UNITS.items():
        if base == dim and scale == 1.0 and name:
            return name
    return "dimensionless" if dim == DIMENSIONLESS else f"dim{dim}"


# ---------------------------------------------------------------------------
# Interval quantities
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Quantity:
    """A closed interval ``[lo, hi]`` in SI base units, with a dimension.

    atopile parameters are intervals, not points: ``0.22uF +/- 20%`` is a
    range, and an assertion over it must hold across the whole range.  Modeling
    a quantity as a point would make every tolerance-bearing assertion look
    decidable when it is not, which is precisely the kind of false confidence
    this gate exists to detect.  Exact literals are the degenerate interval
    ``lo == hi``.
    """

    lo: float
    hi: float
    dim: Dim

    @staticmethod
    def exact(value: float, dim: Dim = DIMENSIONLESS) -> Quantity:
        return Quantity(value, value, dim)

    @property
    def is_exact(self) -> bool:
        return self.lo == self.hi

    def _require_same_dim(self, other: Quantity, op: str) -> None:
        if self.dim != other.dim:
            raise UnitError(
                f"dimension mismatch in {op}: "
                f"{format_dim(self.dim)} vs {format_dim(other.dim)}"
            )

    def __add__(self, other: Quantity) -> Quantity:
        self._require_same_dim(other, "+")
        return Quantity(self.lo + other.lo, self.hi + other.hi, self.dim)

    def __sub__(self, other: Quantity) -> Quantity:
        self._require_same_dim(other, "-")
        return Quantity(self.lo - other.hi, self.hi - other.lo, self.dim)

    def __mul__(self, other: Quantity) -> Quantity:
        products = [
            self.lo * other.lo,
            self.lo * other.hi,
            self.hi * other.lo,
            self.hi * other.hi,
        ]
        dim = _dim_add(self.dim, other.dim)
        return Quantity(min(products), max(products), dim)

    def __truediv__(self, other: Quantity) -> Quantity:
        if other.lo <= 0.0 <= other.hi:
            raise UnitError("division by an interval spanning zero")
        quotients = [
            self.lo / other.lo,
            self.lo / other.hi,
            self.hi / other.lo,
            self.hi / other.hi,
        ]
        dim = _dim_sub(self.dim, other.dim)
        return Quantity(min(quotients), max(quotients), dim)

    def __neg__(self) -> Quantity:
        return Quantity(-self.hi, -self.lo, self.dim)

    def scaled(self, factor: float) -> Quantity:
        lo, hi = self.lo * factor, self.hi * factor
        return Quantity(min(lo, hi), max(lo, hi), self.dim)

    def __str__(self) -> str:
        unit = format_dim(self.dim)
        suffix = "" if unit == "dimensionless" else unit
        if self.is_exact:
            return f"{self.lo:g}{suffix}"
        return f"[{self.lo:g}, {self.hi:g}]{suffix}"


# ---------------------------------------------------------------------------
# Expression AST
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Literal:
    quantity: Quantity
    text: str


@dataclass(frozen=True)
class Ref:
    """A dotted name, e.g. ``power_in.fuse.current_rating``."""

    path: tuple[str, ...]

    def __str__(self) -> str:
        return ".".join(self.path)


@dataclass(frozen=True)
class BinOp:
    op: str
    left: Expr
    right: Expr


@dataclass(frozen=True)
class UnaryOp:
    op: str
    operand: Expr


@dataclass(frozen=True)
class Tolerance:
    """``base +/- spread`` where spread may be a percentage of base."""

    base: Expr
    spread: Expr
    is_percent: bool


@dataclass(frozen=True)
class Within:
    """``value within lo to hi`` (or ``value within base +/- tol``)."""

    value: Expr
    lo: Expr
    hi: Expr


@dataclass(frozen=True)
class Compare:
    op: str
    left: Expr
    right: Expr


Expr = Literal | Ref | BinOp | UnaryOp | Tolerance | Within | Compare


def walk_refs(expr: Expr) -> list[Ref]:
    """Return every :class:`Ref` appearing in *expr*, in source order."""
    out: list[Ref] = []
    stack: list[Expr] = [expr]
    while stack:
        node = stack.pop()
        if isinstance(node, Ref):
            out.append(node)
        elif isinstance(node, BinOp):
            stack.extend([node.right, node.left])
        elif isinstance(node, UnaryOp):
            stack.append(node.operand)
        elif isinstance(node, Tolerance):
            stack.extend([node.spread, node.base])
        elif isinstance(node, Within):
            stack.extend([node.hi, node.lo, node.value])
        elif isinstance(node, Compare):
            stack.extend([node.right, node.left])
    return out


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    (?P<number>\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)
  | (?P<tolerance>\+/-|±)
  | (?P<name>[A-Za-z_][A-Za-z_0-9]*)
  | (?P<cmp><=|>=|==|!=|<|>)
  | (?P<op>[-+*/().%])
  | (?P<ws>\s+)
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    pos: int


class ParseError(SyntaxError):
    """Raised on any construct the reader does not understand."""


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if match is None:
            raise ParseError(f"unexpected character {text[pos]!r} at {pos} in {text!r}")
        kind = match.lastgroup or ""
        if kind != "ws":
            tokens.append(Token(kind, match.group(), match.start()))
        pos = match.end()
    return tokens


# ---------------------------------------------------------------------------
# Expression parser (recursive descent)
# ---------------------------------------------------------------------------

_COMPARISONS = {"<", ">", "<=", ">=", "==", "!="}


class ExpressionParser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.tokens = tokenize(text)
        self.index = 0

    # -- token helpers ---------------------------------------------------
    def peek(self, offset: int = 0) -> Token | None:
        position = self.index + offset
        return self.tokens[position] if position < len(self.tokens) else None

    def next(self) -> Token:
        token = self.peek()
        if token is None:
            raise ParseError(f"unexpected end of expression in {self.text!r}")
        self.index += 1
        return token

    def accept(self, text: str) -> bool:
        token = self.peek()
        if token is not None and token.text == text:
            self.index += 1
            return True
        return False

    def expect(self, text: str) -> Token:
        token = self.next()
        if token.text != text:
            raise ParseError(f"expected {text!r}, got {token.text!r} in {self.text!r}")
        return token

    # -- grammar ---------------------------------------------------------
    def parse_assertion(self) -> Expr:
        expr = self.parse_predicate()
        trailing = self.peek()
        if trailing is not None:
            raise ParseError(
                f"trailing tokens after assertion in {self.text!r}: {trailing.text!r}"
            )
        return expr

    def parse_predicate(self) -> Expr:
        left = self.parse_tolerance()
        token = self.peek()
        if token is not None and token.text == "within":
            self.next()
            band = self.parse_tolerance()
            if self.accept("to"):
                high = self.parse_tolerance()
                return Within(left, band, high)
            if isinstance(band, Tolerance):
                return Within(left, band, band)
            raise ParseError(f"malformed `within` in {self.text!r}")
        if token is not None and token.kind == "cmp":
            self.next()
            right = self.parse_tolerance()
            return Compare(token.text, left, right)
        return left

    def parse_tolerance(self) -> Expr:
        base = self.parse_additive()
        token = self.peek()
        if token is not None and token.kind == "tolerance":
            self.next()
            spread = self.parse_additive()
            is_percent = self.accept("%")
            return Tolerance(base, spread, is_percent)
        return base

    def parse_additive(self) -> Expr:
        node = self.parse_multiplicative()
        while True:
            token = self.peek()
            if token is None or token.text not in {"+", "-"}:
                return node
            self.next()
            node = BinOp(token.text, node, self.parse_multiplicative())

    def parse_multiplicative(self) -> Expr:
        node = self.parse_unary()
        while True:
            token = self.peek()
            if token is None or token.text not in {"*", "/"}:
                return node
            self.next()
            node = BinOp(token.text, node, self.parse_unary())

    def parse_unary(self) -> Expr:
        token = self.peek()
        if token is not None and token.text in {"-", "+"}:
            self.next()
            return UnaryOp(token.text, self.parse_unary())
        return self.parse_atom()

    def parse_atom(self) -> Expr:
        token = self.next()
        if token.text == "(":
            inner = self.parse_tolerance()
            self.expect(")")
            return inner
        if token.kind == "number":
            return self._finish_number(token)
        if token.kind == "name":
            if token.text in {"True", "False"}:
                return Literal(Quantity.exact(1.0 if token.text == "True" else 0.0), token.text)
            parts = [token.text]
            while True:
                following = self.peek()
                if following is None or following.text != ".":
                    break
                self.next()
                nxt = self.next()
                if nxt.kind != "name":
                    raise ParseError(f"bad attribute path in {self.text!r}")
                parts.append(nxt.text)
            return Ref(tuple(parts))
        raise ParseError(f"unexpected token {token.text!r} in {self.text!r}")

    def _finish_number(self, token: Token) -> Literal:
        value = float(token.text)
        unit_token = self.peek()
        # A unit suffix is lexed as a separate name token because it is not
        # separated by whitespace in the source; it only counts as a unit when
        # it is immediately adjacent (no intervening space) and resolvable.
        if (
            unit_token is not None
            and unit_token.kind == "name"
            and unit_token.pos == token.pos + len(token.text)
            and unit_token.text not in {"to", "within"}
        ):
            try:
                scale, dim = parse_unit(unit_token.text)
            except UnitError:
                raise ParseError(
                    f"unknown unit {unit_token.text!r} in {self.text!r}"
                ) from None
            self.next()
            return Literal(Quantity.exact(value * scale, dim), token.text + unit_token.text)
        # ``%`` is deliberately NOT consumed here. It only ever appears as the
        # tail of a ``+/-`` tolerance (``0.22uF +/- 20%``), and swallowing it
        # into the number made the spread read as an absolute 0.20 of the base
        # unit rather than 20 percent -- turning a +/-4400ohm tolerance into
        # +/-0.2ohm. ``ExpressionParser.parse_tolerance`` owns the ``%``.
        return Literal(Quantity.exact(value, DIMENSIONLESS), token.text)


def parse_expression(text: str) -> Expr:
    return ExpressionParser(text).parse_assertion()


# ---------------------------------------------------------------------------
# Source-file model
# ---------------------------------------------------------------------------


@dataclass
class Assertion:
    """One ``assert`` statement, located in source."""

    file: str
    line: int
    source: str
    expr: Expr
    owner: str  # definition name the assert is written inside


@dataclass
class Definition:
    """A ``module`` / ``component`` / ``interface`` block."""

    kind: str
    name: str
    file: str
    line: int
    # attribute name -> (Expr | None); None means an abstract typed slot.
    attributes: dict[str, Expr | None] = field(default_factory=dict)
    # dotted assignment target -> Expr, for ``a.b.c = expr`` inside this block.
    deep_assignments: dict[tuple[str, ...], Expr] = field(default_factory=dict)
    # instance name -> type name, for ``x = new T``.
    instances: dict[str, str] = field(default_factory=dict)
    # dotted instance target -> type name, for ``a.b = new T``.
    deep_instances: dict[tuple[str, ...], str] = field(default_factory=dict)
    assertions: list[Assertion] = field(default_factory=list)
    signals: set[str] = field(default_factory=set)


_DEF_RE = re.compile(r"^(module|component|interface)\s+([A-Za-z_]\w*)\s*:\s*$")
_INHERIT_RE = re.compile(r"^(module|component|interface)\s+([A-Za-z_]\w*)\s+from\s")
_NEW_RE = re.compile(r"^([A-Za-z_][\w.]*)\s*=\s*new\s+([A-Za-z_]\w*)\s*$")
_TYPED_RE = re.compile(r"^([A-Za-z_][\w.]*)\s*:\s*([A-Za-z_]\w*)\s*(?:=\s*(.+))?$")
_ASSIGN_RE = re.compile(r"^([A-Za-z_][\w.]*)\s*=\s*(.+)$")
_SIGNAL_RE = re.compile(r"^signal\s+([A-Za-z_]\w*)")
_ASSERT_RE = re.compile(r"^assert\s+(.+)$")


def _strip_comment(line: str) -> str:
    """Remove a trailing ``#`` comment that is not inside a string literal."""
    out: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(line):
        char = line[index]
        if quote:
            out.append(char)
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            out.append(char)
        elif char == "#":
            break
        else:
            out.append(char)
        index += 1
    return "".join(out)


def _logical_lines(text: str) -> list[tuple[int, int, str]]:
    """Yield ``(line_number, indent, code)`` with docstrings and comments gone.

    Docstrings are skipped by tracking triple-quote state.  This matters: the
    ``.ato`` sources in this repo carry very long prose docstrings that contain
    text such as ``assert c_bus1.voltage_rating >= v_bus_half * 1.25`` inside
    them.  A line-oriented reader that did not track docstring state would
    parse those quotations as real assertions and report findings against
    statements that do not exist.
    """
    result: list[tuple[int, int, str]] = []
    in_doc = False
    doc_delim = ""
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if in_doc:
            if doc_delim in stripped:
                in_doc = False
            continue
        for delim in ('"""', "'''"):
            if stripped.startswith(delim):
                # Single-line docstring closes on the same line.
                if not (len(stripped) > len(delim) and stripped.endswith(delim)):
                    in_doc = True
                    doc_delim = delim
                break
        else:
            code = _strip_comment(raw).rstrip()
            if code.strip():
                indent = len(code) - len(code.lstrip())
                result.append((number, indent, code.strip()))
            continue
        continue
    return result


def parse_file(path: Path, repo_root: Path) -> dict[str, Definition]:
    """Parse one ``.ato`` file into ``{definition_name: Definition}``.

    Nested definitions (``module Constraints:`` containing ``module ACMains:``)
    are registered under their dotted path *and* their bare name, because
    ``constraints.ato`` uses both forms.
    """
    rel = str(path.relative_to(repo_root))
    text = path.read_text(encoding="utf-8")
    definitions: dict[str, Definition] = {}
    # Stack of (indent, Definition) for the enclosing blocks.
    stack: list[tuple[int, Definition]] = []

    for number, indent, code in _logical_lines(text):
        if _INHERIT_RE.match(code):
            raise ParseError(
                f"{rel}:{number}: `from`-style inheritance is not supported by "
                f"this reader; the vacuity gate must not silently drop a base "
                f"class. Extend scripts/_lib/ato_model.py before using it."
            )
        while stack and indent <= stack[-1][0]:
            stack.pop()

        def_match = _DEF_RE.match(code)
        if def_match:
            kind, name = def_match.group(1), def_match.group(2)
            qualified = f"{stack[-1][1].name}.{name}" if stack else name
            definition = Definition(kind=kind, name=qualified, file=rel, line=number)
            definitions[qualified] = definition
            definitions.setdefault(name, definition)
            stack.append((indent, definition))
            continue

        if not stack:
            continue  # imports, pragmas, top-level noise
        current = stack[-1][1]

        assert_match = _ASSERT_RE.match(code)
        if assert_match:
            body = assert_match.group(1).strip()
            current.assertions.append(
                Assertion(
                    file=rel,
                    line=number,
                    source=body,
                    expr=parse_expression(body),
                    owner=current.name,
                )
            )
            continue

        signal_match = _SIGNAL_RE.match(code)
        if signal_match:
            current.signals.add(signal_match.group(1))
            continue

        if "~" in code or code.startswith(("import ", "from ", "#pragma", "pin ")):
            continue

        new_match = _NEW_RE.match(code)
        if new_match:
            target, type_name = new_match.group(1), new_match.group(2)
            parts = tuple(target.split("."))
            if len(parts) == 1:
                current.instances[parts[0]] = type_name
            else:
                current.deep_instances[parts] = type_name
            continue

        typed_match = _TYPED_RE.match(code)
        if typed_match and typed_match.group(2) in TYPE_ANNOTATIONS:
            target, _annotation, value = typed_match.groups()
            parts = tuple(target.split("."))
            expr = parse_expression(value.strip()) if value else None
            if len(parts) == 1:
                current.attributes[parts[0]] = expr
            elif expr is not None:
                current.deep_assignments[parts] = expr
            continue

        assign_match = _ASSIGN_RE.match(code)
        if assign_match:
            target, value = assign_match.group(1), assign_match.group(2).strip()
            if value.startswith(("\"", "'")) or value in {"True", "False"}:
                # Strings (mpn, footprint) and booleans carry no quantity.
                continue
            try:
                expr = parse_expression(value)
            except ParseError:
                continue  # non-numeric RHS; not a quantity we can reason about
            parts = tuple(target.split("."))
            if len(parts) == 1:
                current.attributes[parts[0]] = expr
            else:
                current.deep_assignments[parts] = expr
            continue

    return definitions


def parse_tree(src_root: Path, repo_root: Path) -> dict[str, Definition]:
    """Parse every ``.ato`` under *src_root* into one definition table."""
    definitions: dict[str, Definition] = {}
    for path in sorted(src_root.rglob("*.ato")):
        for name, definition in parse_file(path, repo_root).items():
            # First definition wins; a duplicate bare name from a nested block
            # must not shadow a real top-level module.
            definitions.setdefault(name, definition)
    return definitions
