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
    ones_v = jnp.ones(hg.n_nodes)
    degrees = H.T @ ones_v

    # Avoid div/0 for empty nets
    inv_degrees = 1.0 / (degrees + 1e-10)

    # Sum positions per net: (N_edges, 2)
    sum_pos = H.T @ positions

    centroids = sum_pos * inv_degrees[:, None]

    # 2. Compute Variance (Distance from Centroid)
    # Term 1: Sum of squared positions for every pin
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
    """
    H = hg.incidence.matrix

    # 1. Identify HV Nodes
    hv_nets = hg.edge_voltages
    node_hv_score = H @ hv_nets

    # Soft mask strategy
    mask_hv = (node_hv_score > 0.0).astype(jnp.float32)
    mask_lv = 1.0 - mask_hv

    # 2. Compute Pairwise Distance Matrix
    r = jnp.sum(positions**2, axis=1)
    d_sq = r[:, None] + r[None, :] - 2 * jnp.dot(positions, positions.T)
    d_sq = jnp.clip(d_sq, 0.0, None)
    dist = jnp.sqrt(d_sq + 1e-6)

    # 3. Compute Violation
    violation = jax.nn.relu(min_clearance - dist)

    # 4. Apply Mask: Only penalize HV-LV pairs
    pair_mask = mask_hv[:, None] * mask_lv[None, :]

    # Sum weighted violations
    return jnp.sum(violation**2 * pair_mask)


def current_weighted_spacing_loss(
    positions: Array,
    hg: PhysicsHypergraph,
    base_spacing: float = 0.5,
    current_factor: float = 0.5  # mm per Amp
) -> float:
    """
    Enforce spacing proportional to current.

    High current nodes need more spacing for:
    1. Thermal dissipation
    2. Trace width accommodation
    3. Magnetic field isolation

    Spacing_req = base_spacing + current * current_factor
    """
    H = hg.incidence.matrix

    # 1. Compute Node Max Current
    node_currents = H @ hg.edge_currents

    # 2. Pairwise Required Spacing
    req_spacing = base_spacing + current_factor * (node_currents[:, None] + node_currents[None, :])

    # 3. Compute Distances
    r = jnp.sum(positions**2, axis=1)
    d_sq = r[:, None] + r[None, :] - 2 * jnp.dot(positions, positions.T)
    d_sq = jnp.clip(d_sq, 0.0, None)
    dist = jnp.sqrt(d_sq + 1e-6)

    # 4. Violation
    violation = jax.nn.relu(req_spacing - dist)

    # Exclude self-interaction
    n = positions.shape[0]
    mask = 1.0 - jnp.eye(n)

    return jnp.sum(violation**2 * mask)


def electrostatic_congestion_loss(
    positions: Array,
    hg: PhysicsHypergraph,
    board_width: float,
    board_height: float,
    grid_size: int = 32
) -> float:
    """
    Penalize areas with high routing density (electrostatic analogy).

    Acts as a global spreading force to prevent routing bottlenecks.
    """
    # 1. Compute Centroids and Spread
    H = hg.incidence.matrix
    ones_v = jnp.ones(hg.n_nodes)
    degrees = H.T @ ones_v
    inv_degrees = 1.0 / (degrees + 1e-10)

    centroids = (H.T @ positions) * inv_degrees[:, None]

    # Spread (variance) per net
    sq_diff = (H.T @ (positions**2)) * inv_degrees[:, None] - centroids**2
    spread = jnp.sqrt(jnp.clip(jnp.sum(sq_diff, axis=1), 0.1, None))

    # Net 'Charge' = Width * Current proxy
    charge = hg.edge_widths * (1.0 + 0.1 * hg.edge_currents) * jnp.log(degrees + 1)

    # 2. Grid-based Density
    x = jnp.linspace(0, board_width, grid_size)
    y = jnp.linspace(0, board_height, grid_size)
    X, Y = jnp.meshgrid(x, y)
    grid_pos = jnp.stack([X, Y], axis=-1) # (G, G, 2)

    def net_density(c, s, q):
        dist_sq = jnp.sum((grid_pos - c)**2, axis=-1)
        return q * jnp.exp(-dist_sq / (2 * s**2 + 1e-6))

    rho = jnp.sum(jax.vmap(net_density)(centroids, spread, charge), axis=0)

    # 3. Potential (Blurred Density)
    kernel = jnp.array([[1, 2, 1], [2, 4, 2], [1, 2, 1]]) / 16.0
    phi = jax.scipy.signal.convolve2d(rho, kernel, mode='same')

    return jnp.sum(rho * phi)
