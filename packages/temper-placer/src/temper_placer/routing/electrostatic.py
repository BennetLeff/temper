"""
Electrostatic Congestion Model for PCB Routing.

This module implements a grid-based congestion map by treating routing demand
as a 'charge' distribution and computing the resulting potential field.
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
from jax import Array

from temper_placer.core.hypergraph import PhysicsHypergraph


def compute_demand_density(
    positions: Array,
    hg: PhysicsHypergraph,
    board_width: float,
    board_height: float,
    grid_size: int = 64
) -> Array:
    """
    Compute routing demand density on a fixed grid.
    
    Each net contributes to the density in the bounding box of its pins.
    The 'charge' of the net is its estimated width * current factor.
    """
    # 1. Map pins to grid coordinates
    H = hg.incidence.matrix
    # H is (N_nodes, N_edges). H.T @ positions gives sum of positions per net.
    # But we want the bounding box. 
    # This is tricky in JAX because bboxes have dynamic number of pins.
    
    # Approximation: Use net centroids and net 'radius' (spread)
    ones_v = jnp.ones(hg.n_nodes)
    degrees = H.T @ ones_v
    inv_degrees = 1.0 / (degrees + 1e-10)
    
    centroids = (H.T @ positions) * inv_degrees[:, None]
    
    # Spread (variance)
    sq_diff = (H.T @ (positions**2)) * inv_degrees[:, None] - centroids**2
    spread = jnp.sqrt(jnp.clip(jnp.sum(sq_diff, axis=1), 0.01, None))
    
    # Net 'Charge' = Width * Current * Log(pins)
    charge = hg.edge_widths * (1.0 + 0.1 * hg.edge_currents) * jnp.log(degrees + 1)
    
    # Create grid
    x = jnp.linspace(0, board_width, grid_size)
    y = jnp.linspace(0, board_height, grid_size)
    X, Y = jnp.meshgrid(x, y)
    grid_pos = jnp.stack([X, Y], axis=-1) # (G, G, 2)
    
    # 2. Accumulate Density
    # For each net, add a Gaussian blob at centroid with 'spread'
    def net_contribution(c, s, q):
        dist_sq = jnp.sum((grid_pos - c)**2, axis=-1)
        return q * jnp.exp(-dist_sq / (2 * s**2 + 1e-6))
    
    # Vmap over nets
    # Note: For many nets, this might be memory intensive if we do full grid per net.
    # Better: Use a small kernel and add_at if possible, but JAX vmap is often faster.
    densities = jax.vmap(net_contribution)(centroids, spread, charge)
    return jnp.sum(densities, axis=0)


def electrostatic_congestion_loss(
    positions: Array,
    hg: PhysicsHypergraph,
    board_width: float,
    board_height: float,
    grid_size: int = 32
) -> float:
    """
    Penalize areas with high potential (congested regions).
    
    This acts as a global 'spreading' force for routing resources.
    """
    rho = compute_demand_density(positions, hg, board_width, board_height, grid_size)
    
    # Potential Phi is blurred density (approximates Poisson solution)
    # Using a 5x5 box blur as a cheap proxy
    phi = jax.scipy.signal.convolve2d(rho, jnp.ones((5, 5)) / 25.0, mode='same')
    
    # Energy = sum(rho * phi)
    return jnp.sum(rho * phi)
