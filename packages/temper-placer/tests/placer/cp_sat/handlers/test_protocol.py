"""Tests for the handler protocol and explicit dispatch table."""

from __future__ import annotations

from temper_placer.pcl.constraints import ConstraintType
from temper_placer.placer.cp_sat.handlers import (
    CP_SAT_HANDLER_CATALOG,
    EXPLICITLY_UNSUPPORTED_TYPES,
    _build_handler_catalog,
)


class TestRegistry:
    def test_explicit_table_covers_every_supported_constraint(self) -> None:
        assert frozenset(CP_SAT_HANDLER_CATALOG) == (
            frozenset(ConstraintType) - EXPLICITLY_UNSUPPORTED_TYPES
        )

    def test_duplicate_entries_fail(self) -> None:
        handler = next(iter(CP_SAT_HANDLER_CATALOG.values()))
        ct = next(iter(CP_SAT_HANDLER_CATALOG))
        try:
            _build_handler_catalog(((ct, handler), (ct, handler)))
        except RuntimeError as exc:
            assert "duplicate" in str(exc)
        else:
            raise AssertionError("duplicate handler entries must fail")

    def test_missing_entries_fail(self) -> None:
        entries = tuple(CP_SAT_HANDLER_CATALOG.items())
        missing_type = entries[0][0]
        try:
            _build_handler_catalog(entries[1:])
        except RuntimeError as exc:
            assert missing_type.name in str(exc)
        else:
            raise AssertionError("missing handler entries must fail")

    def test_catalog_is_immutable(self) -> None:
        try:
            CP_SAT_HANDLER_CATALOG[ConstraintType.ADJACENT] = next(
                iter(CP_SAT_HANDLER_CATALOG.values())
            )  # type: ignore[index]
        except TypeError:
            pass
        else:
            raise AssertionError("CP-SAT handler catalog must be immutable")


class TestProtocolStructuralSubtyping:
    def test_function_matches_protocol_without_inheritance(self) -> None:
        from temper_placer.placer.cp_sat.handlers._protocol import ConstraintHandler

        def my_handler(constraint, components, model, ctx):
            return []

        assert isinstance(my_handler, ConstraintHandler)
