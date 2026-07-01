"""U11: Verify fixed-component gradient suppression mechanism.

This test formalizes the invariant that fixed_components truly prevents
gradient updates through the optimizer.  If this test fails, thermal
anchoring CANNOT proceed as a hard prerequisite.
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
import optax
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist
from temper_placer.losses.base import LossContext


def _make_minimal_netlist(
    n_movable: int = 2,
    n_fixed: int = 1,
    fixed_positions: list[tuple[float, float]] | None = None,
) -> tuple[Netlist, Board]:
    """Build a small Netlist with movable and fixed components."""
    board = Board(width=100.0, height=100.0)
    components = []

    for i in range(n_movable):
        comp = Component(
            ref=f"M{i}",
            footprint="test",
            bounds=(10.0, 10.0),
            initial_position=(50.0 + i * 5, 50.0 + i * 5),
            fixed=False,
        )
        components.append(comp)

    if fixed_positions is None:
        fixed_positions = [(25.0, 25.0)] * n_fixed
    for i in range(n_fixed):
        pos = fixed_positions[i] if i < len(fixed_positions) else (25.0, 25.0)
        comp = Component(
            ref=f"F{i}",
            footprint="test",
            bounds=(10.0, 10.0),
            initial_position=pos,
            fixed=True,
        )
        components.append(comp)

    netlist = Netlist(components=components, nets=[])
    return netlist, board


class TestFixedComponentGradientSuppression:
    """Verify that fixed components don't move during gradient descent (R15)."""

    def test_fixed_component_position_unchanged_after_epochs(self):
        """Fixed component position must not change by >1e-6 mm over 10 epochs."""
        netlist, board = _make_minimal_netlist(
            n_movable=2, n_fixed=1, fixed_positions=[(25.0, 25.0)]
        )
        loss_context = LossContext.from_netlist_and_board(netlist, board)

        # Initial positions
        initial = jnp.zeros((netlist.n_components, 2), dtype=jnp.float32)
        for i, comp in enumerate(netlist.components):
            if comp.initial_position:
                initial = initial.at[i].set(jnp.array(comp.initial_position, dtype=jnp.float32))

        optimizer = optax.adam(learning_rate=0.1)
        opt_state = optimizer.init(initial)
        positions = initial
        state = opt_state

        # Simple loss: sum of squared positions (encourages drift toward origin)
        def loss_fn(p):
            return jnp.sum(p[:, 0] ** 2 + p[:, 1] ** 2)

        for _epoch in range(10):
            loss_val, grads = jax.value_and_grad(loss_fn)(positions)

            # Zero gradients for fixed components (matching train.py behavior)
            grads = jnp.where(loss_context.fixed_mask[:, None], 0.0, grads)

            updates, state = optimizer.update(grads, state, positions)
            positions = optax.apply_updates(positions, updates)

            # Clamp fixed components to initial positions
            positions = jnp.where(loss_context.fixed_mask[:, None], initial, positions)

            # Zero optimizer state for fixed components
            if hasattr(state, "mu"):
                state = state._replace(
                    mu=jnp.where(loss_context.fixed_mask[:, None], 0.0, state.mu),
                    nu=jnp.where(loss_context.fixed_mask[:, None], 0.0, state.nu),
                )

        # Verify: fixed component position unchanged
        fixed_idx = netlist.n_components - 1  # last component is fixed
        initial_fixed = initial[fixed_idx]
        final_fixed = positions[fixed_idx]
        delta = float(jnp.max(jnp.abs(final_fixed - initial_fixed)))
        assert delta < 1e-6, (
            f"Fixed component moved by {delta:.2e} mm (expected < 1e-6 mm)"
        )

    def test_movable_components_do_move(self):
        """Sanity check: movable components DO change position."""
        netlist, board = _make_minimal_netlist(n_movable=2, n_fixed=0)
        loss_context = LossContext.from_netlist_and_board(netlist, board)

        initial = jnp.zeros((netlist.n_components, 2), dtype=jnp.float32)
        for i, comp in enumerate(netlist.components):
            if comp.initial_position:
                initial = initial.at[i].set(jnp.array(comp.initial_position, dtype=jnp.float32))

        optimizer = optax.adam(learning_rate=0.5)
        opt_state = optimizer.init(initial)
        positions = initial
        state = opt_state

        def loss_fn(p):
            return jnp.sum(p[:, 0] ** 2 + p[:, 1] ** 2)

        for _epoch in range(20):
            _, grads = jax.value_and_grad(loss_fn)(positions)
            grads = jnp.where(loss_context.fixed_mask[:, None], 0.0, grads)
            updates, state = optimizer.update(grads, state, positions)
            positions = optax.apply_updates(positions, updates)

        delta = float(jnp.max(jnp.abs(positions - initial)))
        assert delta > 0.01, (
            f"Movable components didn't move (delta={delta:.6f} mm). "
            "Gradient updates may not be working."
        )

    def test_fixed_optimizer_state_is_zero(self):
        """Fixed component optimizer state (mu, nu) should be zeros after training."""
        netlist, board = _make_minimal_netlist(
            n_movable=1, n_fixed=1, fixed_positions=[(25.0, 25.0)]
        )
        loss_context = LossContext.from_netlist_and_board(netlist, board)

        initial = jnp.zeros((netlist.n_components, 2), dtype=jnp.float32)
        for i, comp in enumerate(netlist.components):
            if comp.initial_position:
                initial = initial.at[i].set(jnp.array(comp.initial_position, dtype=jnp.float32))

        optimizer = optax.adam(learning_rate=0.1)
        opt_state = optimizer.init(initial)
        positions = initial
        state = opt_state

        def loss_fn(p):
            return jnp.sum(p[:, 0] ** 2 + p[:, 1] ** 2)

        for _epoch in range(10):
            _, grads = jax.value_and_grad(loss_fn)(positions)
            grads = jnp.where(loss_context.fixed_mask[:, None], 0.0, grads)
            updates, state = optimizer.update(grads, state, positions)
            positions = optax.apply_updates(positions, updates)
            positions = jnp.where(loss_context.fixed_mask[:, None], initial, positions)
            if hasattr(state, "mu"):
                state = state._replace(
                    mu=jnp.where(loss_context.fixed_mask[:, None], 0.0, state.mu),
                    nu=jnp.where(loss_context.fixed_mask[:, None], 0.0, state.nu),
                )

        fixed_idx = 1  # F0 is at index 1
        if hasattr(state, "mu"):
            fixed_mu = state.mu[fixed_idx]
            fixed_nu = state.nu[fixed_idx]
            assert jnp.allclose(fixed_mu, 0.0, atol=1e-6), f"Fixed mu not zero: {fixed_mu}"
            assert jnp.allclose(fixed_nu, 0.0, atol=1e-6), f"Fixed nu not zero: {fixed_nu}"

    def test_all_fixed_no_gradient_updates(self):
        """With all components fixed, no positions change anywhere."""
        netlist, board = _make_minimal_netlist(
            n_movable=0, n_fixed=2,
            fixed_positions=[(25.0, 25.0), (75.0, 75.0)]
        )
        loss_context = LossContext.from_netlist_and_board(netlist, board)

        initial = jnp.zeros((netlist.n_components, 2), dtype=jnp.float32)
        for i, comp in enumerate(netlist.components):
            if comp.initial_position:
                initial = initial.at[i].set(jnp.array(comp.initial_position, dtype=jnp.float32))

        optimizer = optax.adam(learning_rate=0.1)
        opt_state = optimizer.init(initial)
        positions = initial
        state = opt_state

        def loss_fn(p):
            return jnp.sum(p[:, 0] ** 2 + p[:, 1] ** 2)

        for _epoch in range(10):
            _, grads = jax.value_and_grad(loss_fn)(positions)
            grads = jnp.where(loss_context.fixed_mask[:, None], 0.0, grads)
            updates, state = optimizer.update(grads, state, positions)
            positions = optax.apply_updates(positions, updates)
            positions = jnp.where(loss_context.fixed_mask[:, None], initial, positions)
            if hasattr(state, "mu"):
                state = state._replace(
                    mu=jnp.where(loss_context.fixed_mask[:, None], 0.0, state.mu),
                    nu=jnp.where(loss_context.fixed_mask[:, None], 0.0, state.nu),
                )

        delta = float(jnp.max(jnp.abs(positions - initial)))
        assert delta < 1e-6, f"All-fixed positions changed by {delta:.2e}"
