"""Shared mathematical invariant assertion helpers for property-based tests.

Import from here to get all invariant checkers without knowing which submodule they live in.
"""

from .assertions import (
    assert_empty_is_zero,
    assert_idempotent,
    assert_monotonic,
    assert_positive_when_violation,
    assert_zero_when_no_violation,
)
from .jax_helpers import (
    assert_gradient_finite,
    assert_loss_context_is_pytree,
)
from .strategies import (
    board_strategy,
    netlist_strategy,
)

__all__ = [
    # Assertion helpers
    "assert_zero_when_no_violation",
    "assert_positive_when_violation",
    "assert_monotonic",
    "assert_idempotent",
    "assert_empty_is_zero",
    # JAX helpers
    "assert_gradient_finite",
    "assert_loss_context_is_pytree",
    # Strategies
    "board_strategy",
    "netlist_strategy",
]
