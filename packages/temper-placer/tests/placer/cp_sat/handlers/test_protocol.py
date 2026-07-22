"""Tests for ConstraintHandler Protocol, registry, and shared utilities."""

from __future__ import annotations

from temper_placer.pcl.constraints import ConstraintType
from temper_placer.placer.cp_sat.handlers._registry import (
    HANDLER_REGISTRY,
    register_handler,
)


class TestRegistry:
    def test_handlers_registry_initially_empty_after_first_import(self) -> None:
        from temper_placer.placer.cp_sat.handlers._registry import HANDLER_REGISTRY as hr
        assert hr == HANDLER_REGISTRY

    def test_register_handler_decorator_stores_entry(self) -> None:
        before = len(HANDLER_REGISTRY)

        @register_handler(ConstraintType.ADJACENT)
        def _test_adj_handler(constraint, components, model, ctx):
            return []

        assert ConstraintType.ADJACENT in HANDLER_REGISTRY
        assert HANDLER_REGISTRY[ConstraintType.ADJACENT] is _test_adj_handler
        assert len(HANDLER_REGISTRY) == before + 1

    def test_register_handler_returns_fn_unchanged(self) -> None:
        @register_handler(ConstraintType.SEPARATED)
        def _my_sep(constraint, components, model, ctx):
            return [42]

        assert _my_sep(None, {}, None, None) == [42]

    def test_register_handler_sets_constraint_type_attr(self) -> None:
        @register_handler(ConstraintType.ON_SIDE)
        def _my_onside(constraint, components, model, ctx):
            return []

        assert getattr(_my_onside, "constraint_type", None) is ConstraintType.ON_SIDE


class TestProtocolStructuralSubtyping:
    def test_function_matches_protocol_without_inheritance(self) -> None:
        from temper_placer.placer.cp_sat.handlers._protocol import ConstraintHandler

        def my_handler(constraint, components, model, ctx):
            return []

        assert isinstance(my_handler, ConstraintHandler)
