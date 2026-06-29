"""Safe predicate expression parser and evaluator for skip_if conditions.

Grammar:
    expr     = or_expr
    or_expr  = and_expr ("or" and_expr)*
    and_expr = not_expr ("and" not_expr)*
    not_expr = "not" not_expr | comparison
    comparison = atom (("==" | "!=" | "<" | ">" | "<=" | ">=") atom)?
    atom     = "true" | "false" | "null" | NUMBER | STRING | accessor
    accessor = ("config" | "state" | "context") "." IDENTIFIER
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.state import State
    from temper_placer.core.netlist import Netlist
    from temper_placer.core.board import Board
    from temper_placer.pcl.parser import ConstraintCollection
    from temper_placer.router_v6.stage0_data import ParsedPCB

import ast
import re
from typing import Any

from temper_placer.pipeline.dag_types import DAGExprError, DAGExprSyntaxError

_KEYWORD_START = re.compile(r"[a-zA-Z_]")
_IDENTIFIER = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
_NUMBER = re.compile(r"(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")
_STRING_SINGLE = re.compile(r"'([^'\\]*(?:\\.[^'\\]*)*)'")
_STRING_DOUBLE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')

_TOKEN_SPEC = [
    ("STRING", re.compile(r"'([^'\\]*(?:\\.[^'\\]*)*)'|"
                          r'"([^"\\]*(?:\\.[^"\\]*)*)"')),
    ("NUMBER", re.compile(r"(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")),
    ("NULL", re.compile(r"null\b")),
    ("TRUE", re.compile(r"true\b")),
    ("FALSE", re.compile(r"false\b")),
    ("AND", re.compile(r"and\b")),
    ("OR", re.compile(r"or\b")),
    ("NOT", re.compile(r"not\b")),
    ("EQ", re.compile(r"==")),
    ("NEQ", re.compile(r"!=")),
    ("LTE", re.compile(r"<=")),
    ("GTE", re.compile(r">=")),
    ("LT", re.compile(r"<")),
    ("GT", re.compile(r">")),
    ("LPAREN", re.compile(r"\(")),
    ("RPAREN", re.compile(r"\)")),
    ("DOT", re.compile(r"\.")),
    ("IDENT", re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")),
    ("SKIP", re.compile(r"[ \t]+")),
    ("MISMATCH", re.compile(r".")),
]


def _tokenize(source: str) -> list[tuple[str, str, int]]:
    tokens: list[tuple[str, str, int]] = []
    pos = 0
    while pos < len(source):
        match = None
        for kind, pattern in _TOKEN_SPEC:
            m = pattern.match(source, pos)
            if m:
                if kind == "SKIP":
                    pass
                elif kind == "MISMATCH":
                    raise DAGExprSyntaxError(f"Unexpected character '{source[pos]}' at position {pos}")
                elif kind == "STRING":
                    tokens.append((kind, m.group(1) or m.group(2), pos))
                else:
                    tokens.append((kind, m.group(0), pos))
                pos = m.end()
                match = True
                break
        if not match:
            raise DAGExprSyntaxError(f"Unexpected character '{source[pos]}' at position {pos}")
    tokens.append(("EOF", "", pos))
    return tokens


class _Parser:
    def __init__(self, source: str):
        self.source = source
        self.tokens = _tokenize(source)
        self.pos = 0
        self._loop_limit = 200

    def _peek(self) -> tuple[str, str, int]:
        return self.tokens[self.pos]

    def _advance(self) -> tuple[str, str, int]:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _expect(self, kind: str) -> tuple[str, str, int]:
        tok = self._advance()
        if tok[0] != kind:
            raise DAGExprSyntaxError(
                f"Expected {kind}, got {tok[0]} ('{tok[1]}') at position {tok[2]}"
            )
        return tok

    def parse(self) -> ast.Expression:
        node = self._expr()
        self._expect("EOF")
        return ast.Expression(body=node)

    def _expr(self) -> ast.expr:
        left = self._and_expr()
        while self._peek()[0] == "OR":
            self._advance()
            right = self._and_expr()
            left = ast.BoolOp(op=ast.Or(), values=[left, right])
        return left

    def _and_expr(self) -> ast.expr:
        left = self._not_expr()
        while self._peek()[0] == "AND":
            self._advance()
            right = self._not_expr()
            left = ast.BoolOp(op=ast.And(), values=[left, right])
        return left

    def _not_expr(self) -> ast.expr:
        if self._peek()[0] == "NOT":
            self._advance()
            operand = self._not_expr()
            return ast.UnaryOp(op=ast.Not(), operand=operand)
        return self._comparison()

    def _comparison(self) -> ast.expr:
        left = self._atom()
        tok = self._peek()
        if tok[0] in ("EQ", "NEQ", "LT", "GT", "LTE", "GTE"):
            op_map = {
                "EQ": ast.Eq(),
                "NEQ": ast.NotEq(),
                "LT": ast.Lt(),
                "GT": ast.Gt(),
                "LTE": ast.LtE(),
                "GTE": ast.GtE(),
            }
            self._advance()
            right = self._atom()
            return ast.Compare(left=left, ops=[op_map[tok[0]]], comparators=[right])
        return left

    def _atom(self) -> ast.expr:
        tok = self._advance()
        if tok[0] == "LPAREN":
            node = self._expr()
            self._expect("RPAREN")
            return node
        elif tok[0] == "TRUE":
            return ast.Constant(value=True)
        elif tok[0] == "FALSE":
            return ast.Constant(value=False)
        elif tok[0] == "NULL":
            return ast.Constant(value=None)
        elif tok[0] == "NUMBER":
            text = tok[1]
            if "." in text or "e" in text.lower():
                return ast.Constant(value=float(text))
            return ast.Constant(value=int(text))
        elif tok[0] == "STRING":
            return ast.Constant(value=tok[1])
        elif tok[0] == "IDENT":
            ident = tok[1]
            if self._peek()[0] == "DOT":
                self._advance()
                field_tok = self._expect("IDENT")
                return _AccessorExpr(ns=ident, field=field_tok[1],
                                     lineno=1, col_offset=0)
            raise DAGExprSyntaxError(
                f"Bare identifier '{ident}' not allowed; "
                f"use config.{ident}, state.{ident}, or context.{ident}"
            )
        else:
            raise DAGExprSyntaxError(
                f"Unexpected token {tok[0]} ('{tok[1]}') at position {tok[2]}"
            )


class _AccessorExpr(ast.expr):
    _fields = ("ns", "field")

    def __init__(self, ns: str, field: str, lineno: int = 1, col_offset: int = 0, **kwargs):
        self.ns = ns
        self.field = field
        super().__init__(lineno=lineno, col_offset=col_offset, **kwargs)


def parse_skip_expr(source: str) -> ast.Expression:
    """Parse a skip expression string into an AST.

    Raises DAGExprSyntaxError on syntax errors.
    """
    source = source.strip()
    if not source:
        raise DAGExprSyntaxError("Empty skip expression")
    parser = _Parser(source)
    return parser.parse()


def evaluate_skip_expr(
    expr: ast.Expression,
    config: Any,
    state: Any,
    context: DataContext,
) -> bool:
    """Evaluate a parsed skip expression against live objects.

    Raises DAGExprError on missing keys or evaluation errors.
    """

    def _eval(node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not _eval(node.operand)
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for v in node.values:
                    if not _eval(v):
                        return False
                return True
            elif isinstance(node.op, ast.Or):
                for v in node.values:
                    if _eval(v):
                        return True
                return False
            raise DAGExprError(f"Unsupported boolean operator: {type(node.op).__name__}")
        elif isinstance(node, ast.Compare):
            left_val = _eval(node.left)
            for op, comp in zip(node.ops, node.comparators):
                right_val = _eval(comp)
                if isinstance(op, ast.Eq):
                    result = left_val == right_val
                elif isinstance(op, ast.NotEq):
                    result = left_val != right_val
                elif isinstance(op, ast.Lt):
                    result = left_val < right_val
                elif isinstance(op, ast.Gt):
                    result = left_val > right_val
                elif isinstance(op, ast.LtE):
                    result = left_val <= right_val
                elif isinstance(op, ast.GtE):
                    result = left_val >= right_val
                else:
                    raise DAGExprError(f"Unsupported comparison: {type(op).__name__}")
                if not result:
                    return False
                left_val = right_val
            return True
        elif isinstance(node, _AccessorExpr):
            if node.ns == "config":
                if not hasattr(config, node.field):
                    raise DAGExprError(
                        f"Unknown config field '{node.field}' in skip expression"
                    )
                return getattr(config, node.field)
            elif node.ns == "state":
                if not hasattr(state, node.field):
                    raise DAGExprError(
                        f"Unknown state field '{node.field}' in skip expression"
                    )
                return getattr(state, node.field)
            elif node.ns == "context":
                if node.field not in context:
                    raise DAGExprError(
                        f"Unknown context key '{node.field}' in skip expression"
                    )
                return context[node.field]
            else:
                raise DAGExprError(f"Unknown namespace '{node.ns}' in skip expression")
        else:
            raise DAGExprError(f"Unsupported AST node: {type(node).__name__}")

    return bool(_eval(expr.body))
