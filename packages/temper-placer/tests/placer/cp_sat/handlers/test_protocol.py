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
        ct = ConstraintType.ADJACENT
        # Use a key not already taken by a real handler module import.
        if ct in HANDLER_REGISTRY:
            original = HANDLER_REGISTRY.get(ct)
            del HANDLER_REGISTRY[ct]
        else:
            original = None
        try:

            @register_handler(ct)
            def _test_adj_handler(constraint, components, model, ctx):
                return []

            assert ct in HANDLER_REGISTRY
            assert HANDLER_REGISTRY[ct] is _test_adj_handler
        finally:
            del HANDLER_REGISTRY[ct]
            if original is not None:
                HANDLER_REGISTRY[ct] = original

    def test_register_handler_returns_fn_unchanged(self) -> None:
        @register_handler(ConstraintType.ALIGNED)
        def _my_aligned(constraint, components, model, ctx):
            return [42]

        try:
            assert _my_aligned(None, {}, None, None) == [42]
        finally:
            del HANDLER_REGISTRY[ConstraintType.ALIGNED]

    def test_register_handler_sets_constraint_type_attr(self) -> None:
        @register_handler(ConstraintType.ON_SIDE)
        def _my_onside(constraint, components, model, ctx):
            return []

        try:
            assert getattr(_my_onside, "constraint_type", None) is ConstraintType.ON_SIDE
        finally:
            del HANDLER_REGISTRY[ConstraintType.ON_SIDE]


class TestProtocolStructuralSubtyping:
    def test_function_matches_protocol_without_inheritance(self) -> None:
        from temper_placer.placer.cp_sat.handlers._protocol import ConstraintHandler

        def my_handler(constraint, components, model, ctx):
            return []

        assert isinstance(my_handler, ConstraintHandler)
