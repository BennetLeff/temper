"""Safe predicate expression parser and evaluator for skip_if conditions.

Grammar:
    expr     = or_expr
    or_expr  = and_expr ("or" and_expr)*
    and_expr = not_expr ("and" not_expr)*
    not_expr = "not" not_expr | comparison
    comparison = atom (("==" | "!=" | "<" | ">" | "<=" | ">=") atom)?
    atom     = "true" | "false" | "null" | NUMBER | STRING | accessor
    accessor = ("config" | "state" | "context") "." IDENTIFIER

Tokenizing, parsing and evaluation live in Rust
(``packages/temper-io-types/src/dag_expr.rs``). This module is the Python
boundary: it keeps the public API byte-identical to the pre-port version and
translates the Rust error types back to ``DAGExprError`` / ``DAGExprSyntaxError``.

The pinned behavioural oracle for the port is
``packages/temper-placer/tests/pipeline/_dag_expr_py_oracle.py``.
"""

from __future__ import annotations

import ast
from typing import Any

import temper_io_types as _rs

from temper_placer.pipeline.dag_types import DAGExprError, DAGExprSyntaxError, DataContext

__all__ = ["evaluate_skip_expr", "parse_skip_expr"]


class _AccessorExpr(ast.expr):
    _fields = ("ns", "field")

    def __init__(self, ns: str, field: str, lineno: int = 1, col_offset: int = 0, **kwargs):
        self.ns = ns
        self.field = field
        super().__init__(lineno=lineno, col_offset=col_offset, **kwargs)


_CMP_OPS: dict[str, type[ast.cmpop]] = {
    "Eq": ast.Eq,
    "NotEq": ast.NotEq,
    "Lt": ast.Lt,
    "Gt": ast.Gt,
    "LtE": ast.LtE,
    "GtE": ast.GtE,
}

# Attribute used to carry the Rust handle on the returned ast.Expression.
#
# parse_skip_expr's public contract is "returns an ast.Expression", and
# dag_schema.py relies on that only to mean "did not raise". Rather than change
# the return type, the real parsed form rides along on the object; a dunder-ish
# private name keeps it out of the way of anything walking _fields.
_HANDLE_ATTR = "_temper_rs_skip_expr"


def _materialize(spec: tuple) -> ast.expr:
    """Rebuild the ast tree the pure-Python parser used to return.

    Kept so that the object handed back from ``parse_skip_expr`` is still a
    real ``ast.Expression`` with the same node types, ``_AccessorExpr``
    included -- callers that introspect it (none in-tree today, but it is
    public surface) see exactly what they saw before the port.
    """
    kind = spec[0]
    if kind == "const":
        return ast.Constant(value=spec[1])
    if kind == "not":
        return ast.UnaryOp(op=ast.Not(), operand=_materialize(spec[1]))
    if kind == "and":
        return ast.BoolOp(op=ast.And(), values=[_materialize(spec[1]), _materialize(spec[2])])
    if kind == "or":
        return ast.BoolOp(op=ast.Or(), values=[_materialize(spec[1]), _materialize(spec[2])])
    if kind == "cmp":
        return ast.Compare(
            left=_materialize(spec[1]),
            ops=[_CMP_OPS[spec[2]]()],
            comparators=[_materialize(spec[3])],
        )
    if kind == "accessor":
        return _AccessorExpr(ns=spec[1], field=spec[2], lineno=1, col_offset=0)
    raise DAGExprError(f"Unsupported node spec: {kind!r}")


def parse_skip_expr(source: str) -> ast.Expression:
    """Parse a skip expression string into an AST.

    Raises DAGExprSyntaxError on syntax errors.
    """
    try:
        handle = _rs.parse_skip_expr_rs(source)
    except _rs.DagExprSyntaxError as e:
        raise DAGExprSyntaxError(str(e)) from None
    except _rs.DagExprError as e:
        raise DAGExprError(str(e)) from None
    expr = ast.Expression(body=_materialize(handle.to_spec()))
    setattr(expr, _HANDLE_ATTR, handle)
    return expr


def evaluate_skip_expr(
    expr: ast.Expression,
    config: Any,
    state: Any,
    context: DataContext,
) -> bool:
    """Evaluate a parsed skip expression against live objects.

    Raises DAGExprError on missing keys or evaluation errors.
    """
    handle = getattr(expr, _HANDLE_ATTR, None)
    if handle is None:
        # An ast.Expression built by something other than parse_skip_expr.
        # Nothing in-tree does this, but the signature has always accepted a
        # bare ast.Expression, so the pure-Python walker stays reachable
        # rather than turning a previously-working call into an error.
        return _evaluate_ast(expr, config, state, context)
    try:
        return handle.evaluate(config, state, context)
    except _rs.DagExprError as e:
        raise DAGExprError(str(e)) from None


def _evaluate_ast(
    expr: ast.Expression,
    config: Any,
    state: Any,
    context: DataContext,
) -> bool:
    """Compatibility walker for externally-constructed ASTs.

    Semantics are the pinned oracle's; it is differential-tested against the
    Rust path by ``test_fallback_walker_matches_rust`` so the two cannot drift.
    """

    def _eval(node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return not _eval(node.operand)
            raise DAGExprError(f"Unsupported unary operator: {type(node.op).__name__}")
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                # `_evaluate_ast` is the compatibility walker for
                # *externally-constructed* ASTs (see its docstring) -- unlike
                # `_materialize`'s own output, which always builds exactly
                # 2-element `values` lists, a caller-built `ast.BoolOp` is
                # not guaranteed to be well-formed. `all(())` is vacuously
                # True, which would silently evaluate a malformed empty
                # `and` node as "passes" instead of raising -- fail loudly
                # instead (`any(())` for `or` already fails closed to False,
                # so it needs no guard; see check_vacuous_gates.py).
                if not node.values:
                    raise DAGExprError("BoolOp 'and' with no operands")
                return all(_eval(v) for v in node.values)
            if isinstance(node.op, ast.Or):
                return any(_eval(v) for v in node.values)
            raise DAGExprError(f"Unsupported boolean operator: {type(node.op).__name__}")
        if isinstance(node, ast.Compare):
            left_val = _eval(node.left)
            for op, comp in zip(node.ops, node.comparators, strict=False):
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
        if isinstance(node, _AccessorExpr):
            if node.ns == "config":
                if not hasattr(config, node.field):
                    raise DAGExprError(f"Unknown config field '{node.field}' in skip expression")
                return getattr(config, node.field)
            if node.ns == "state":
                if not hasattr(state, node.field):
                    raise DAGExprError(f"Unknown state field '{node.field}' in skip expression")
                return getattr(state, node.field)
            if node.ns == "context":
                if node.field not in context:
                    raise DAGExprError(f"Unknown context key '{node.field}' in skip expression")
                return context[node.field]
            raise DAGExprError(f"Unknown namespace '{node.ns}' in skip expression")
        raise DAGExprError(f"Unsupported AST node: {type(node).__name__}")

    return bool(_eval(expr.body))
