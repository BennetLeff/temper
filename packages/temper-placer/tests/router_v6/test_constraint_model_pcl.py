"""Fail-closed tests for the router PCL lowering boundary."""

from __future__ import annotations

import pytest

from temper_placer.router_v6.constraint_model import ModelBuilder


class _Model:
    """Small model double for exercising only ``_apply_pcl_constraints``."""

    def __init__(self) -> None:
        self.constraints: list[object] = []

    def add_constraint(self, constraint: object) -> None:
        self.constraints.append(constraint)


def _builder(*, pcl_constraints=None) -> ModelBuilder:
    """Construct a builder without invoking the Rust model builder."""
    builder = object.__new__(ModelBuilder)
    builder.pcl_constraints = pcl_constraints
    builder.model = _Model()
    builder.pcb = None
    builder.nets = []
    builder.skeletons = {}
    builder.channel_widths = {}
    builder.design_rules = None
    return builder


def test_no_pcl_constraints_is_a_noop() -> None:
    builder = _builder()

    builder._apply_pcl_constraints()

    assert builder.model.constraints == []


def test_router_pcl_compilation_rejection_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unsupported/unregistered supplied PCL must fail the routing stage."""
    from temper_placer.pcl import router_compiler

    rejection = KeyError("unsupported router constraint: future_constraint")

    def reject(_collection, _context):
        raise rejection

    monkeypatch.setattr(router_compiler, "compile_pcl_for_router", reject, raising=False)
    builder = _builder(pcl_constraints=[object()])

    with pytest.raises(KeyError, match="unsupported router constraint"):
        builder._apply_pcl_constraints()

    assert builder.model.constraints == []
