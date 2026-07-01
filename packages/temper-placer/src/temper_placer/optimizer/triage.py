"""
Triage evaluation: fixed-budget cheap optimization for seed ranking.

Runs a lightweight (30-iteration) SGD optimization on a minimal loss stack
to estimate seed quality before committing to full multi-phase training.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import jax.numpy as jnp
from jax import Array

from temper_placer.losses.base import (
    CompositeLoss,
    LossContext,
    WeightedLoss,
    create_value_and_grad_fn_with_breakdown,
)
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.clearance import ClearanceLoss
from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.wirelength import WirelengthLoss

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist

logger = logging.getLogger(__name__)

_TRIAGE_LOSS_NAMES = ["wirelength", "overlap", "boundary", "clearance"]
_DEFAULT_N_ITERS = 30
_DEFAULT_LR = 0.05


def _triage_evaluate(
    positions: Array,
    netlist: Netlist,
    board: Board,
    context: LossContext | None = None,
    n_iters: int = _DEFAULT_N_ITERS,
    lr: float = _DEFAULT_LR,
) -> float:
    """
    Run a fixed-budget cheap evaluation of a seed.

    Loss stack: wirelength (w=1.0) + overlap (w=1.0) +
                boundary (w=1.0) + clearance (w=1.0)

    Uses simple SGD (no optax, no Gumbel-Softmax) for `n_iters` iterations.
    Returns the final loss value. Returns NaN on numerical failure.

    Args:
        positions: (N, 2) initial component positions.
        netlist: Component netlist.
        board: Board definition.
        context: Optional pre-built LossContext (created if None).
        n_iters: Number of SGD iterations (default 30).
        lr: Learning rate for SGD (default 0.05).

    Returns:
        Final loss value (lower is better). NaN on failure.
    """
    # Build LossContext if not provided
    if context is None:
        context = LossContext.from_netlist_and_board(netlist, board)

    # Early exit: NaN positions cannot be evaluated
    if jnp.any(jnp.isnan(positions)) or jnp.any(jnp.isinf(positions)):
        return float("nan")

    # Build lightweight composite loss with all weights = 1.0
    composite_loss = _build_triage_loss()
    # ... rest unchanged ...

    # Create JIT-compiled value-and-grad function
    value_and_grad_fn = create_value_and_grad_fn_with_breakdown(
        composite_loss, context
    )

    # Fixed rotation logits (uniform = no orientation preference)
    n_components = netlist.n_components
    rotations = jnp.zeros((n_components, 4), dtype=jnp.float32)

    # Net virtual nodes — initialized to mid-board or zeros
    # (the loss functions need them; we don't optimize them)
    n_nets = netlist.n_nets
    if n_nets > 0:
        net_virtual_nodes = jnp.full(
            (n_nets, 2), board.width / 2.0, dtype=jnp.float32
        )
        net_virtual_nodes = net_virtual_nodes.at[:, 1].set(board.height / 2.0)
    else:
        net_virtual_nodes = jnp.zeros((0, 2), dtype=jnp.float32)

    pos = positions.copy()
    total_epochs = max(n_iters, 1)

    for iteration in range(n_iters):
        try:
            (loss_val, _breakdown), (grad_pos, _grad_rot, _grad_vn) = value_and_grad_fn(
                pos,
                rotations,
                net_virtual_nodes,
                iteration,
                total_epochs,
            )
        except Exception:
            logger.debug("Triage gradient step %d failed.", iteration)
            return float("nan")

        loss_float = float(loss_val)
        if not _is_finite(loss_float):
            return float("nan")

        # Simple SGD update (no optax)
        pos = pos - lr * grad_pos

    # One final evaluation to get the final loss
    try:
        (final_loss, _breakdown), _grads = value_and_grad_fn(
            pos, rotations, net_virtual_nodes, n_iters - 1, total_epochs
        )
        final_val = float(final_loss)
        if not _is_finite(final_val):
            return float("nan")
        return final_val
    except Exception:
        return float("nan")


def _build_triage_loss() -> CompositeLoss:
    """Build the triage CompositeLoss with all weights = 1.0."""
    loss_terms: list[WeightedLoss] = [
        WeightedLoss(WirelengthLoss(), weight=1.0),
        WeightedLoss(OverlapLoss(), weight=1.0),
        WeightedLoss(BoundaryLoss(), weight=1.0),
        WeightedLoss(ClearanceLoss(), weight=1.0),
    ]
    return CompositeLoss(loss_terms)


def _is_finite(val: float) -> bool:
    """Check if value is finite (not NaN, not Inf)."""
    import math
    return math.isfinite(val)
