"""
Learned initialization model for PCB placement.

Uses Graph Neural Networks to predict optimal initial component positions
based on netlist topology and component features.
"""

from __future__ import annotations

import jax.numpy as jnp
from jax import Array
from flax import linen as nn
from .gnn_predictor import GNNBlock


class LearnedInitializerGNN(nn.Module):
    """
    Predicts initial component positions [X, Y].
    
    Inputs:
        - Node features: [Area, PinCount, Fixed, Centrality]
        - Edge indices: (E, 2)
    
    Output:
        - Positions: (N, 2) in normalized [0, 1] range.
    """
    hidden_dim: int = 128
    n_layers: int = 3

    @nn.compact
    def __call__(self, nodes: Array, edges: Array) -> Array:
        # nodes: (N, F)
        # edges: (E, 2)
        
        x = nodes
        
        # 1. Graph Convolution Layers
        for _ in range(self.n_layers):
            x = GNNBlock(self.hidden_dim)(x, edges)
            x = nn.relu(x)
            x = nn.LayerNorm()(x)
        
        # 2. Per-node output head (Position Prediction)
        # Output is (N, 2)
        x = nn.Dense(self.hidden_dim)(x)
        x = nn.relu(x)
        positions = nn.Dense(2)(x)
        
        # Normalize to [0, 1] range using sigmoid
        return nn.sigmoid(positions)


def predict_initial_positions(params, nodes, edges):
    """Run inference using pre-trained parameters."""
    model = LearnedInitializerGNN()
    return model.apply({'params': params}, nodes, edges)
