"""Tests for dag_expr: skip expression parser and evaluator."""

import ast

import pytest

from temper_placer.pipeline.dag_expr import (
    evaluate_skip_expr,
    parse_skip_expr,
)
from temper_placer.pipeline.dag_types import DAGExprError, DAGExprSyntaxError


class MockConfig:
    skip_topological = True
    skip_routing = False
    dry_run = False
    input_pcb = "/path/to/pcb.kicad_pcb"
    fab_preset = "jlcpcb_standard"


class MockState:
    success = True
    iteration = 0


class TestParseSkipExpr:
    def test_true_literal(self):
        expr = parse_skip_expr("true")
        assert isinstance(expr, ast.Expression)

    def test_false_literal(self):
        expr = parse_skip_expr("false")
        assert isinstance(expr, ast.Expression)

    def test_null_literal(self):
        expr = parse_skip_expr("null")
        assert isinstance(expr, ast.Expression)

    def test_config_accessor(self):
        expr = parse_skip_expr("config.skip_topological == true")
        assert isinstance(expr, ast.Expression)

    def test_state_accessor(self):
        expr = parse_skip_expr("state.success == true")
        assert isinstance(expr, ast.Expression)

    def test_context_accessor(self):
        expr = parse_skip_expr("context.routing_completion < 0.5")
        assert isinstance(expr, ast.Expression)

    def test_and_expression(self):
        expr = parse_skip_expr("true and false")
        assert isinstance(expr, ast.Expression)

    def test_or_expression(self):
        expr = parse_skip_expr("true or false")
        assert isinstance(expr, ast.Expression)

    def test_not_expression(self):
        expr = parse_skip_expr("not true")
        assert isinstance(expr, ast.Expression)

    def test_numeric_comparison(self):
        expr = parse_skip_expr("context.value > 10")
        assert isinstance(expr, ast.Expression)

    def test_string_comparison(self):
        expr = parse_skip_expr("config.fab_preset == 'jlcpcb_standard'")
        assert isinstance(expr, ast.Expression)

    def test_parenthesized(self):
        expr = parse_skip_expr("(true and false) or true")
        assert isinstance(expr, ast.Expression)

    def test_complex_expression(self):
        expr = parse_skip_expr(
            "config.dry_run == true and config.skip_routing == false"
        )
        assert isinstance(expr, ast.Expression)

    def test_empty_expression_raises(self):
        with pytest.raises(DAGExprSyntaxError, match="Empty skip expression"):
            parse_skip_expr("")

    def test_bare_identifier_raises(self):
        with pytest.raises(DAGExprSyntaxError, match="Bare identifier"):
            parse_skip_expr("skip_topological")

    def test_invalid_operator_raises(self):
        with pytest.raises(DAGExprSyntaxError):
            parse_skip_expr("config.x + 1")

    def test_unknown_namespace_parses(self):
        expr = parse_skip_expr("unknown.field == true")
        assert isinstance(expr, ast.Expression)


class TestEvaluateSkipExpr:
    def make_context(self, **kwargs):
        return kwargs

    def test_true_literal(self):
        expr = parse_skip_expr("true")
        assert evaluate_skip_expr(expr, None, None, {}) is True

    def test_false_literal(self):
        expr = parse_skip_expr("false")
        assert evaluate_skip_expr(expr, None, None, {}) is False

    def test_config_accessor_true(self):
        config = MockConfig()
        expr = parse_skip_expr("config.skip_topological == true")
        assert evaluate_skip_expr(expr, config, None, {}) is True

    def test_config_accessor_false(self):
        config = MockConfig()
        expr = parse_skip_expr("config.skip_routing == true")
        assert evaluate_skip_expr(expr, config, None, {}) is False

    def test_state_accessor(self):
        state = MockState()
        expr = parse_skip_expr("state.success == true")
        assert evaluate_skip_expr(expr, None, state, {}) is True

    def test_context_accessor(self):
        context = {"routing_completion": 0.3}
        expr = parse_skip_expr("context.routing_completion < 0.5")
        assert evaluate_skip_expr(expr, None, None, context) is True

    def test_context_accessor_false(self):
        context = {"routing_completion": 0.9}
        expr = parse_skip_expr("context.routing_completion < 0.5")
        assert evaluate_skip_expr(expr, None, None, context) is False

    def test_and_true(self):
        expr = parse_skip_expr("true and true")
        assert evaluate_skip_expr(expr, None, None, {}) is True

    def test_and_false(self):
        expr = parse_skip_expr("true and false")
        assert evaluate_skip_expr(expr, None, None, {}) is False

    def test_or_true(self):
        expr = parse_skip_expr("false or true")
        assert evaluate_skip_expr(expr, None, None, {}) is True

    def test_or_false(self):
        expr = parse_skip_expr("false or false")
        assert evaluate_skip_expr(expr, None, None, {}) is False

    def test_not_true(self):
        expr = parse_skip_expr("not true")
        assert evaluate_skip_expr(expr, None, None, {}) is False

    def test_not_false(self):
        expr = parse_skip_expr("not false")
        assert evaluate_skip_expr(expr, None, None, {}) is True

    def test_greater_than(self):
        context = {"value": 10}
        expr = parse_skip_expr("context.value > 5")
        assert evaluate_skip_expr(expr, None, None, context) is True

    def test_less_than(self):
        context = {"value": 2}
        expr = parse_skip_expr("context.value < 5")
        assert evaluate_skip_expr(expr, None, None, context) is True

    def test_gte(self):
        context = {"value": 5}
        expr = parse_skip_expr("context.value >= 5")
        assert evaluate_skip_expr(expr, None, None, context) is True

    def test_lte(self):
        context = {"value": 5}
        expr = parse_skip_expr("context.value <= 5")
        assert evaluate_skip_expr(expr, None, None, context) is True

    def test_eq(self):
        expr = parse_skip_expr("42 == 42")
        assert evaluate_skip_expr(expr, None, None, {}) is True

    def test_neq(self):
        expr = parse_skip_expr("42 != 7")
        assert evaluate_skip_expr(expr, None, None, {}) is True

    def test_null_comparison(self):
        config = MockConfig()
        expr = parse_skip_expr("config.input_pcb == null")
        result = evaluate_skip_expr(expr, config, None, {})
        assert result is False

    def test_string_equality(self):
        config = MockConfig()
        expr = parse_skip_expr("config.fab_preset == 'jlcpcb_standard'")
        assert evaluate_skip_expr(expr, config, None, {}) is True

    def test_string_inequality(self):
        config = MockConfig()
        expr = parse_skip_expr("config.fab_preset != 'other'")
        assert evaluate_skip_expr(expr, config, None, {}) is True

    def test_complex_predicate(self):
        config = MockConfig()
        expr = parse_skip_expr(
            "config.dry_run == true and config.skip_routing == false"
        )
        assert evaluate_skip_expr(expr, config, None, {}) is False

    def test_unknown_config_field_raises(self):
        config = MockConfig()
        expr = parse_skip_expr("config.nonexistent == true")
        with pytest.raises(DAGExprError, match="nonexistent"):
            evaluate_skip_expr(expr, config, None, {})

    def test_unknown_state_field_raises(self):
        state = MockState()
        expr = parse_skip_expr("state.nonexistent == true")
        with pytest.raises(DAGExprError, match="nonexistent"):
            evaluate_skip_expr(expr, None, state, {})

    def test_unknown_context_key_raises(self):
        expr = parse_skip_expr("context.missing == true")
        with pytest.raises(DAGExprError, match="missing"):
            evaluate_skip_expr(expr, None, None, {})

    def test_float_literal(self):
        expr = parse_skip_expr("0.5 > 0.1")
        assert evaluate_skip_expr(expr, None, None, {}) is True

    def test_int_literal(self):
        expr = parse_skip_expr("42 == 42")
        assert evaluate_skip_expr(expr, None, None, {}) is True

    def test_or_short_circuit(self):
        config = MockConfig()
        expr = parse_skip_expr("true or config.nonexistent == true")
        assert evaluate_skip_expr(expr, config, None, {}) is True

    def test_and_short_circuit(self):
        config = MockConfig()
        expr = parse_skip_expr("false and config.nonexistent == true")
        assert evaluate_skip_expr(expr, config, None, {}) is False
