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
from temper_placer.core.netlist import (
    Netlist,
    build_adjacency_matrix,
    compute_eigenvector_centrality,
)


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
        # Not enough eigenvectors, take what we have and pad with zeros
        coords = eigenvectors[:, 1:n]
        padding = jnp.zeros((n, n_dims - (n - 1)))
        coords = jnp.concatenate([coords, padding], axis=1)
    else:
        coords = eigenvectors[:, 1 : n_dims + 1]

    return coords


def find_connected_components(adjacency: Array) -> list[list[int]]:
    """
    Find connected components in the graph using BFS.

    Args:
        adjacency: (N, N) weighted adjacency matrix.

    Returns:
        List of lists, where each inner list contains indices of components
        belonging to the same connected component.
    """
    n = adjacency.shape[0]
    visited = np.zeros(n, dtype=bool)
    components = []

    # Use numpy for graph traversal
    adj_np = np.array(adjacency)

    for i in range(n):
        if not visited[i]:
            component = []
            queue = [i]
            visited[i] = True
            while queue:
                u = queue.pop(0)
                component.append(u)
                # Find neighbors (where weight > 0)
                neighbors = np.where(adj_np[u] > 0)[0]
                for v in neighbors:
                    if not visited[v]:
                        visited[v] = True
                        queue.append(v)
            components.append(component)

    return components


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
        separation_factor: Factor used to separate components that end up at
                          the same position (default 0.05 = 5% of board size).

    Example:
        >>> initializer = SpectralInitializer(normalized_laplacian=True, margin_fraction=0.1)
        >>> positions = initializer.initialize(netlist, board)
    """

    normalized_laplacian: bool = True
    margin_fraction: float = 0.1
    separation_factor: float = 0.05

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
            - Single components placed at center.
            - Components with identical spectral coordinates are separated
              using their index as a deterministic offset.
        """
        n = len(netlist.components)
        if n == 0:
            return jnp.zeros((0, 2))
        if n == 1:
            center_x = board.origin[0] + board.width / 2
            center_y = board.origin[1] + board.height / 2
            return jnp.array([[center_x, center_y]])

        # Build connectivity graph
        adjacency = build_adjacency_matrix(netlist)

        # Compute spectral coordinates for the entire graph at once
        # This naturally handles disjoint subgraphs via multiple zero eigenvalues
        all_coords = compute_spectral_coordinates(
            adjacency,
            n_dims=2,
            normalized=self.normalized_laplacian,
        )

        # Scale all coordinates to board bounds
        positions = scale_to_board(all_coords, board, self.margin_fraction)

        # Separate components that ended up at identical positions
        # (common for directly connected components in small subgraphs)
        positions = self._separate_coincident_components(positions, board)

        return positions

    def _separate_coincident_components(
        self,
        positions: Array,
        board: Board,
    ) -> Array:
        """
        Separate components that are at exactly the same position.

        Uses deterministic spiral pattern based on component index to separate
        coincident components while keeping them close together.

        Args:
            positions: (N, 2) initial positions (may have duplicates).
            board: Board dimensions.

        Returns:
            (N, 2) positions with coincident components separated.
        """
        n = positions.shape[0]
        if n <= 1:
            return positions

        # Separation distance (fraction of smaller board dimension)
        sep = min(board.width, board.height) * self.separation_factor

        # Convert to numpy for mutation
        pos_np = np.array(positions)

        # Find groups of coincident components
        # Using a simple O(n^2) approach since n is typically small (<1000)
        processed = np.zeros(n, dtype=bool)

        for i in range(n):
            if processed[i]:
                continue

            # Find all components at same position as i
            dists = np.linalg.norm(pos_np - pos_np[i], axis=1)
            coincident = np.where(dists < 1e-6)[0]

            if len(coincident) <= 1:
                processed[i] = True
                continue

            # Separate coincident components using spiral pattern
            # This keeps them close together but not overlapping
            center = pos_np[i].copy()
            for k, idx in enumerate(coincident):
                if k == 0:
                    # First component stays at center
                    pass
                else:
                    # Spiral outward: angle increases, radius increases
                    angle = k * 2.618  # Golden angle in radians
                    radius = sep * np.sqrt(k)  # Increasing radius
                    offset = np.array(
                        [
                            np.cos(angle) * radius,
                            np.sin(angle) * radius,
                        ]
                    )
                    pos_np[idx] = center + offset

                processed[idx] = True

        return jnp.array(pos_np)
