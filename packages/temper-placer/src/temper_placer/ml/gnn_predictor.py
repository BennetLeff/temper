"""
GNN-based placement quality predictor.

Uses Graph Neural Networks to predict the quality of a given placement
based on netlist topology and component positions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import jax
import jax.numpy as jnp
from flax import linen as nn
from jax import Array

if TYPE_CHECKING:
    pass


class GNNBlock(nn.Module):
    """Simple graph convolution block."""
    out_features: int

    @nn.compact
    def __call__(self, nodes: Array, edges: Array) -> Array:
        # Simple graph aggregation: average of neighbor features
        # nodes: (N, F)
        # edges: (E, 2)

        # Message passing (simplified)
        source_idx = edges[:, 0]
        target_idx = edges[:, 1]

        messages = nodes[source_idx]

        # Aggregate messages at targets
        # Using segment_sum or scatter for JAX
        num_nodes = nodes.shape[0]
        agg_messages = jnp.zeros((num_nodes, nodes.shape[1]))
        agg_messages = agg_messages.at[target_idx].add(messages)

        # Combine with self
        combined = jnp.concatenate([nodes, agg_messages], axis=-1)

        return nn.Dense(self.out_features)(combined)


class PlacementQualityGNN(nn.Module):
    """
    Predicts quality scores for a proposed placement.

    Inputs:
        - Node features: [Area, PinCount, Fixed, PosX, PosY]
        - Edge indices: (E, 2)

    Output:
        - Quality score (0-1)
    """
    hidden_dim: int = 64

    @nn.compact
    def __call__(self, graph_nodes: Array, positions: Array, edges: Array) -> Array:
        # 1. Combine graph features with proposed positions
        # graph_nodes: (N, 3) -> [Area, PinCount, Fixed]
        # positions: (N, 2)
        x = jnp.concatenate([graph_nodes, positions], axis=-1) # (N, 5)

        # 2. Graph Convolution Layers
        x = GNNBlock(self.hidden_dim)(x, edges)
        x = nn.relu(x)
        x = GNNBlock(self.hidden_dim)(x, edges)
        x = nn.relu(x)

        # 3. Global Pooling (Mean)
        x_global = jnp.mean(x, axis=0)

        # 4. Final Output Head
        x_global = nn.Dense(self.hidden_dim)(x_global)
        x_global = nn.relu(x_global)
        score = nn.Dense(1)(x_global)

        return nn.sigmoid(score)


def train_step(state, nodes, positions, edges, target_score):
    """Performs a single training step."""
    def loss_fn(params):
        logits = state.apply_fn({'params': params}, nodes, positions, edges)
        return jnp.mean((logits - target_score) ** 2)

    grad_fn = jax.value_and_grad(loss_fn)
    loss, grads = grad_fn(state.params)
    state = state.apply_gradients(grads=grads)
    return state, loss
