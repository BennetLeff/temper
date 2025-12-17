"""
Spectral initialization for PCB placement optimization.

This module implements spectral (graph-based) initialization using the connectivity
graph's eigenvectors to compute initial component positions. This approach places
connected components near each other, improving convergence on large boards.

Implements temper-1my.7: Spectral/Analytical Initialization
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import jax.numpy as jnp
import numpy as np
from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist


def build_adjacency_matrix(netlist: Netlist) -> Array:
    """
    Build weighted adjacency matrix from netlist connectivity.

    The adjacency matrix A is symmetric with A[i,j] equal to the number of nets
    connecting components i and j. Components on the same net create edges between
    all pairs of components on that net (complete subgraph).

    Args:
        netlist: Netlist with components and nets.

    Returns:
        (N, N) symmetric adjacency matrix where A[i,j] = number of nets
        connecting components i and j. Returns (0,0) array for empty netlist.

    Example:
        For a netlist with 3 components:
        - R1, R2 on NET1
        - R2, R3 on NET2

        Adjacency matrix:
        [[0, 1, 0],   # R1: connected to R2 via NET1
         [1, 0, 1],   # R2: connected to R1 via NET1, R3 via NET2
         [0, 1, 0]]   # R3: connected to R2 via NET2
    """
    n = len(netlist.components)

    if n == 0:
        return jnp.array([]).reshape(0, 0)

    # Build component ref -> index mapping
    ref_to_idx = {comp.ref: i for i, comp in enumerate(netlist.components)}

    # Initialize adjacency matrix
    adj = np.zeros((n, n), dtype=np.float32)

    # For each net, connect all component pairs
    for net in netlist.nets:
        # Get component indices for this net
        comp_indices = []
        for comp_ref, _ in net.pins:
            if comp_ref in ref_to_idx:
                comp_indices.append(ref_to_idx[comp_ref])

        # Remove duplicates (component may have multiple pins on same net)
        comp_indices = list(set(comp_indices))

        # Add edges between all pairs (complete subgraph)
        for i in range(len(comp_indices)):
            for j in range(i + 1, len(comp_indices)):
                idx_i = comp_indices[i]
                idx_j = comp_indices[j]

                adj[idx_i, idx_j] += 1
                adj[idx_j, idx_i] += 1  # Symmetric

    return jnp.array(adj)


def compute_spectral_coordinates(
    adjacency: Array,
    n_dims: int = 2,
    normalized: bool = True,
) -> Array:
    """
    Compute spectral coordinates from adjacency matrix.

    Uses the graph Laplacian's eigenvectors (spectral embedding) to compute
    coordinates that place connected components near each other. The Fiedler
    vector (eigenvector for smallest non-zero eigenvalue) gives the primary
    dimension, and subsequent eigenvectors give additional dimensions.

    Args:
        adjacency: (N, N) weighted adjacency matrix.
        n_dims: Number of dimensions (typically 2 for X/Y placement).
        normalized: If True, use normalized Laplacian L = I - D^(-1/2) A D^(-1/2).
                   If False, use unnormalized Laplacian L = D - A.
                   Normalized is generally better for graphs with varying node degrees.

    Returns:
        (N, n_dims) array of spectral coordinates.

    Notes:
        - For disconnected graphs, there will be multiple zero eigenvalues.
        - The normalized Laplacian handles varying node degrees better.
        - Edge case: graphs with < n_dims+1 nodes may not have enough eigenvectors.
    """
    n = adjacency.shape[0]

    if n == 0:
        return jnp.zeros((0, n_dims))

    if n == 1:
        # Single node: return zeros
        return jnp.zeros((1, n_dims))

    # Compute degree matrix
    degrees = jnp.sum(adjacency, axis=1)

    if normalized:
        # Normalized Laplacian: L = I - D^(-1/2) A D^(-1/2)
        # Add small epsilon to avoid division by zero for isolated nodes
        d_inv_sqrt = jnp.where(degrees > 0, 1.0 / jnp.sqrt(degrees + 1e-10), 0.0)
        D_inv_sqrt = jnp.diag(d_inv_sqrt)
        L = jnp.eye(n) - D_inv_sqrt @ adjacency @ D_inv_sqrt
    else:
        # Unnormalized Laplacian: L = D - A
        D = jnp.diag(degrees)
        L = D - adjacency

    # Eigendecomposition
    # eigh returns eigenvalues in ascending order
    eigenvalues, eigenvectors = jnp.linalg.eigh(L)

    # Skip first eigenvector (corresponds to eigenvalue ≈ 0, constant vector)
    # Take next n_dims eigenvectors for coordinates
    if n < n_dims + 1:
        # Not enough eigenvectors, pad with zeros
        coords = eigenvectors[:, 1:n]
        padding = jnp.zeros((n, n_dims - (n - 1)))
        coords = jnp.concatenate([coords, padding], axis=1)
    else:
        coords = eigenvectors[:, 1 : n_dims + 1]

    return coords


def scale_to_board(
    spectral_coords: Array,
    board: Board,
    margin_fraction: float = 0.1,
) -> Array:
    """
    Scale spectral coordinates to fit within board bounds with margin.

    Normalizes spectral coordinates to [0, 1] in each dimension, then scales
    to board dimensions while respecting margin. This ensures all components
    are placed within the board boundaries.

    Args:
        spectral_coords: (N, 2) raw spectral coordinates (can be any range).
        board: Board with width, height, and origin.
        margin_fraction: Fraction of board to leave as margin (e.g., 0.1 = 10%).
                        Components will be placed in the central (1-2*margin) region.

    Returns:
        (N, 2) positions in board coordinate system.

    Example:
        For a 100x150mm board with 10% margin:
        - Usable area: 80x130mm (90% of width/height)
        - Components placed in region [10,10] to [90,140]
    """
    n = spectral_coords.shape[0]

    if n == 0:
        return jnp.zeros((0, 2))

    # Check for degenerate case: all coordinates the same
    min_coords = jnp.min(spectral_coords, axis=0)
    max_coords = jnp.max(spectral_coords, axis=0)
    range_coords = max_coords - min_coords

    # If range is near zero, all coords are the same → place at board center
    is_degenerate = range_coords < 1e-10

    if jnp.all(is_degenerate):
        # All coordinates the same → place all components at board center
        center_x = board.origin[0] + board.width / 2
        center_y = board.origin[1] + board.height / 2
        positions = jnp.full((n, 2), jnp.array([center_x, center_y]))
    else:
        # Normal case: normalize and scale
        # Avoid division by zero by using safe range
        safe_range = jnp.where(is_degenerate, 1.0, range_coords)
        normalized = (spectral_coords - min_coords) / safe_range

        # For degenerate dimensions, set to 0.5 (will map to center of usable area)
        normalized = jnp.where(is_degenerate, 0.5, normalized)

        # Compute usable board area (excluding margins)
        usable_width = board.width * (1 - 2 * margin_fraction)
        usable_height = board.height * (1 - 2 * margin_fraction)

        # Compute offset (margin)
        offset_x = board.origin[0] + board.width * margin_fraction
        offset_y = board.origin[1] + board.height * margin_fraction

        # Scale to board
        positions = normalized * jnp.array([usable_width, usable_height])
        positions = positions + jnp.array([offset_x, offset_y])

    return positions


@dataclass
class SpectralInitializer:
    """
    Initialize component positions using spectral graph layout.

    Uses the connectivity graph's eigenvectors to compute initial positions that
    place connected components near each other. This improves convergence for
    large boards (>100 components) compared to random initialization.

    Attributes:
        normalized_laplacian: If True, use normalized Laplacian (better for
                            graphs with varying node degrees).
        margin_fraction: Fraction of board to leave as margin (default 10%).

    Example:
        >>> initializer = SpectralInitializer(normalized_laplacian=True, margin_fraction=0.1)
        >>> positions = initializer.initialize(netlist, board)
    """

    normalized_laplacian: bool = True
    margin_fraction: float = 0.1

    def initialize(
        self,
        netlist: Netlist,
        board: Board,
        rng_key: Optional[Array] = None,
    ) -> Array:
        """
        Compute initial positions for all components using spectral embedding.

        Args:
            netlist: Components and connectivity.
            board: Board dimensions.
            rng_key: Random key (unused, for API compatibility).

        Returns:
            (N, 2) initial positions in board coordinates.

        Notes:
            - Deterministic for same netlist (no randomness).
            - Handles disconnected components gracefully.
            - Single components placed at center.
        """
        if len(netlist.components) == 0:
            return jnp.zeros((0, 2))

        # Build connectivity graph
        adjacency = build_adjacency_matrix(netlist)

        # Compute spectral coordinates
        spectral_coords = compute_spectral_coordinates(
            adjacency,
            n_dims=2,
            normalized=self.normalized_laplacian,
        )

        # Scale to board bounds
        positions = scale_to_board(spectral_coords, board, self.margin_fraction)

        return positions
