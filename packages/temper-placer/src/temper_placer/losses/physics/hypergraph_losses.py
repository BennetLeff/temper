"""
Hypergraph-based Loss Functions.

This module implements loss functions that operate directly on the 
PhysicsHypergraph BCOO incidence matrix, enabling vectorized physics-aware
optimization.
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.core.hypergraph import PhysicsHypergraph


def hypergraph_wirelength_loss(
    positions: Array, 
    hg: PhysicsHypergraph
) -> float:
    """
    Compute total HPWL (Half-Perimeter Wire Length) approximation using 
    sparse matrix operations.
    
    This replaces the iterative 'Star Model' loop.
    
    L = sum_{nets} weight * (sum_{pins} || pos_pin - center_net ||^2)
    
    Args:
        positions: (N_nodes, 2) array of component centers.
        hg: PhysicsHypergraph instance.
        
    Returns:
        Scalar loss value.
    """
    H = hg.incidence.matrix
    W = hg.incidence.hyperedge_weights
    
    # 1. Compute Net Centroids
    # D_e (degree of edges)
    # Note: If we precompute D_e in the hypergraph, we save this step.
    ones_v = jnp.ones(hg.n_nodes)
    degrees = H.T @ ones_v
    
    # Avoid div/0 for empty nets (though factory should filter them)
    inv_degrees = 1.0 / (degrees + 1e-10)
    
    # Sum positions per net: (N_edges, 2)
    sum_pos = H.T @ positions 
    
    centroids = sum_pos * inv_degrees[:, None]
    
    # 2. Compute Variance (Distance from Centroid)
    # We want: sum_{e} W_e * [ sum_{v in e} || p_v - c_e ||^2 ]
    
    # Expand: sum ||p||^2 - |e| * ||c||^2
    
    # Term 1: Sum of squared positions for every pin
    # We need to weight this by the net weight W_e.
    # Since a pin can be in multiple nets, we can't just do sum(pos^2).
    # We need H.T @ (pos^2) -> this gives sum of squares per net.
    
    term1_per_net = H.T @ (positions ** 2) # (N_edges, 2)
    term1 = jnp.sum(term1_per_net * W[:, None])
    
    # Term 2: |e| * ||c||^2
    term2_per_net = degrees[:, None] * (centroids ** 2)
    term2 = jnp.sum(term2_per_net * W[:, None])
    
    return term1 - term2


def high_voltage_repulsion_loss(
    positions: Array,
    hg: PhysicsHypergraph,
    min_clearance: float = 10.0
) -> float:
    """
    Repulsion force to maintain HV clearance.
    
    Strategy:
    1. Identify 'HV Nodes' (connected to any HV net).
    2. Identify 'LV Nodes' (not connected to any HV net).
    3. Compute repulsion between these two sets.
    
    This is an N^2 operation if naive.
    Optimization: Use the coarse graph? Or just random sampling?
    For now, exact calculation on subsets.
    """
    H = hg.incidence.matrix
    
    # 1. Identify HV Nodes
    # hv_nets is binary mask (1 if HV)
    hv_nets = hg.edge_voltages 
    
    # Propagate to nodes: If node touches HV net, it is HV
    # node_hv_score = H @ hv_nets
    node_hv_score = H @ hv_nets
    
    is_hv = node_hv_score > 0.5
    
    # Get indices (using boolean masking)
    # Note: dynamic shapes are bad for JIT.
    # We ideally compute a soft mask.
    
    # Soft mask strategy
    # mask_hv = sigmoid(node_hv_score * 100)
    # mask_lv = 1.0 - mask_hv
    
    # Calculating pairwise distance matrix is heavy (N=1000 -> 1M entries)
    # But JAX handles 1M float32s easily (4MB).
    
    # Dist matrix: || p_i - p_j ||
    # d_sq = ||p_i||^2 + ||p_j||^2 - 2 <p_i, p_j>
    
    r = jnp.sum(positions**2, axis=1)
    d_sq = r[:, None] + r[None, :] - 2 * jnp.dot(positions, positions.T)
    d_sq = jnp.clip(d_sq, 0.0, None) # Numerical stability
    dist = jnp.sqrt(d_sq + 1e-6)
    
    # Violation: ReLU(min_clearance - dist)
    violation = jax.nn.relu(min_clearance - dist)
    
    # Apply Mask: Only penalize HV-LV pairs
    # mask[i, j] = 1 if (i is HV and j is LV) or (i is LV and j is HV)
    
    mask_hv = (node_hv_score > 0.0).astype(jnp.float32)
    mask_lv = 1.0 - mask_hv
    
    # Outer product for mask
    # M_hv_lv = hv[:, None] * lv[None, :]
    pair_mask = mask_hv[:, None] * mask_lv[None, :]
    
    # Sum weighted violations
    return jnp.sum(violation**2 * pair_mask)
