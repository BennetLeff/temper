"""
Routing difficulty predictor for PCB placement.

Predicts the expected routing congestion and topological difficulty
of a placement using Graph Neural Networks.
"""

from __future__ import annotations

import jax.numpy as jnp
from flax import linen as nn
from jax import Array


class RoutingDifficultyGNN(nn.Module):
    """
    Predicts a routing difficulty score (0-1).
    
    Inputs:
        - Node features: [Area, PinCount, Density, CenterDist]
        - Edge indices: (E, 2)
        - Edge features: [Wirelength, CrossingsApprox]
    
    Output:
        - Difficulty score (0-1): Higher means more congested/difficult.
    """
    hidden_dim: int = 64

    @nn.compact
    def __call__(self, nodes: Array, edges: Array, edge_features: Array) -> Array:
        # nodes: (N, FN)
        # edges: (E, 2)
        # edge_features: (E, FE)

        # 1. Edge processing
        e = nn.Dense(self.hidden_dim)(edge_features)
        e = nn.relu(e)

        # 2. Node processing with edge context
        x = nn.Dense(self.hidden_dim)(nodes)
        x = nn.relu(x)

        # 3. Message passing layers
        for _ in range(2):
            # Simplified message passing with edge weights
            source_idx = edges[:, 0]
            target_idx = edges[:, 1]

            # Message = neighbor_node * edge_weight
            messages = x[source_idx] * e

            # Aggregate
            num_nodes = nodes.shape[0]
            agg = jnp.zeros((num_nodes, self.hidden_dim))
            agg = agg.at[target_idx].add(messages)

            x = nn.Dense(self.hidden_dim)(jnp.concatenate([x, agg], axis=-1))
            x = nn.relu(x)
            x = nn.LayerNorm()(x)

        # 4. Global pooling
        x_global = jnp.mean(x, axis=0)

        # 5. Output head
        x_global = nn.Dense(self.hidden_dim)(x_global)
        x_global = nn.relu(x_global)
        score = nn.Dense(1)(x_global)

        return nn.sigmoid(score)


def estimate_routing_difficulty(params, nodes, edges, edge_features):
    """Predict routing difficulty for a given placement."""
    model = RoutingDifficultyGNN()
    return model.apply({'params': params}, nodes, edges, edge_features)
