"""Simple standalone tests for dag_expr parse and evaluate functions.

The comprehensive differential / property / benchmark test suite lives in
test_dag_expr_rust_differential.py, test_dag_expr_properties.py, and
test_dag_expr_perf.py.  This file covers the basic smoke-test surface so
that a reader can see the public API usage without going through the
full parity machinery.
"""

import ast

import pytest

from temper_placer.pipeline.dag_expr import evaluate_skip_expr, parse_skip_expr
from temper_placer.pipeline.dag_types import DAGExprError, DAGExprSyntaxError


class _Config:
    def __init__(self):
        self.foo = 42
        self.flag = True
        self.name = "test"


class _State:
    def __init__(self):
        self.iter = 3
        self.done = False


def _make_env():
    return _Config(), _State(), {"ratio": 0.75, "ready": True}


class TestParseSkipExpr:
    """Smoke tests for parse_skip_expr."""

    def test_parse_true(self):
        expr = parse_skip_expr("true")
        assert isinstance(expr, ast.Expression)

    def test_parse_false(self):
        expr = parse_skip_expr("false")
        assert isinstance(expr, ast.Expression)

    def test_parse_null(self):
        expr = parse_skip_expr("null")
        assert isinstance(expr, ast.Expression)

    def test_parse_number(self):
        expr = parse_skip_expr("42")
        assert isinstance(expr, ast.Expression)

    def test_parse_accessor(self):
        expr = parse_skip_expr("config.foo")
        assert isinstance(expr, ast.Expression)

    def test_parse_comparison(self):
        expr = parse_skip_expr("config.foo == 42")
        assert isinstance(expr, ast.Expression)

    def test_parse_boolean_logic(self):
        expr = parse_skip_expr("true and false or config.flag")
        assert isinstance(expr, ast.Expression)

    def test_parse_empty_raises(self):
        with pytest.raises((DAGExprSyntaxError, DAGExprError)):
            parse_skip_expr("")

    def test_parse_garbage_raises(self):
        with pytest.raises((DAGExprSyntaxError, DAGExprError)):
            parse_skip_expr("@@@")


class TestEvaluateSkipExpr:
    """Smoke tests for evaluate_skip_expr."""

    def test_eval_true(self):
        config, state, ctx = _make_env()
        expr = parse_skip_expr("true")
        assert evaluate_skip_expr(expr, config, state, ctx) is True

    def test_eval_false(self):
        config, state, ctx = _make_env()
        expr = parse_skip_expr("false")
        assert evaluate_skip_expr(expr, config, state, ctx) is False

    def test_eval_null_is_falsy(self):
        config, state, ctx = _make_env()
        expr = parse_skip_expr("null")
        # null evaluates as None, which is falsy
        assert evaluate_skip_expr(expr, config, state, ctx) is False

    def test_eval_config_field(self):
        config, state, ctx = _make_env()
        expr = parse_skip_expr("config.foo == 42")
        assert evaluate_skip_expr(expr, config, state, ctx) is True

        expr = parse_skip_expr("config.foo == 99")
        assert evaluate_skip_expr(expr, config, state, ctx) is False

    def test_eval_state_field(self):
        config, state, ctx = _make_env()
        expr = parse_skip_expr("state.iter > 0")
        assert evaluate_skip_expr(expr, config, state, ctx) is True

        expr = parse_skip_expr("state.done == true")
        assert evaluate_skip_expr(expr, config, state, ctx) is False

    def test_eval_context_field(self):
        config, state, ctx = _make_env()
        expr = parse_skip_expr("context.ratio < 0.8")
        assert evaluate_skip_expr(expr, config, state, ctx) is True

    def test_eval_not(self):
        config, state, ctx = _make_env()
        expr = parse_skip_expr("not true")
        assert evaluate_skip_expr(expr, config, state, ctx) is False

        expr = parse_skip_expr("not config.flag")
        assert evaluate_skip_expr(expr, config, state, ctx) is False

    def test_eval_and_or(self):
        config, state, ctx = _make_env()
        expr = parse_skip_expr("true and false")
        assert evaluate_skip_expr(expr, config, state, ctx) is False

        expr = parse_skip_expr("true or false")
        assert evaluate_skip_expr(expr, config, state, ctx) is True

    def test_eval_unknown_field_raises(self):
        config, state, ctx = _make_env()
        expr = parse_skip_expr("config.does_not_exist")
        with pytest.raises(DAGExprError):
            evaluate_skip_expr(expr, config, state, ctx)
