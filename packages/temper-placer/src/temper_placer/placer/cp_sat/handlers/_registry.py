"""Decorator-based auto-registration for constraint type handlers."""

from __future__ import annotations

from collections.abc import Callable

from ortools.sat.python import cp_model

from temper_placer.pcl.constraints import ConstraintType

HANDLER_REGISTRY: dict[ConstraintType, Callable[..., list[cp_model.IntVar]]] = {}


def register_handler(ct: ConstraintType) -> Callable[[Callable[..., list[cp_model.IntVar]]], Callable[..., list[cp_model.IntVar]]]:
    """Decorator that registers a handler function for *ct*.

    Usage::

        @register_handler(ConstraintType.SEPARATED)
        def encode_separated(constraint, components, model, ctx):
            ...

    The decorated function is returned unchanged; the side effect is
    appending an entry to ``HANDLER_REGISTRY``.
    """
    def decorator(fn: Callable[..., list[cp_model.IntVar]]) -> Callable[..., list[cp_model.IntVar]]:
        fn.constraint_type = ct  # type: ignore[attr-defined]
        HANDLER_REGISTRY[ct] = fn
        return fn
    return decorator
