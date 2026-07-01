"""
Spectral initialization for PCB placement optimization.

This module implements spectral (graph-based) initialization using the connectivity
graph's eigenvectors to compute initial component positions. This approach places
connected components near each other, improving convergence on large boards.

Implements temper-1my.7: Spectral/Analytical Initialization
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import jax.numpy as jnp
import numpy as np
from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.netlist import (
    Netlist,
    build_adjacency_matrix,
)
from temper_placer.ml.learned_init import LearnedInitializerGNN

if TYPE_CHECKING:
    from temper_placer.io.config_loader import PlacementConstraints
    from temper_placer.pcl.parser import ConstraintCollection


def compute_spectral_coordinates(
    adjacency: Array,
    n_dims: int = 2,
    normalized: bool = True,
    stabilize: bool = False,
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
        normalized: If True, use normalized Laplacian.
        stabilize: If True, apply PSD stabilization via Gershgorin before eigh.

    Returns:
        (N, n_dims) array of spectral coordinates.
    """
    n = adjacency.shape[0]

    if n == 0:
        return jnp.zeros((0, n_dims))

    if n == 1:
        return jnp.zeros((1, n_dims))

    adj_np = np.array(adjacency, dtype=np.float64)
    degrees = np.sum(adj_np, axis=1)

    if normalized:
        d_inv_sqrt = np.where(degrees > 0, 1.0 / np.sqrt(degrees + 1e-10), 0.0)
        D_inv_sqrt = np.diag(d_inv_sqrt)
        L = np.eye(n) - D_inv_sqrt @ adj_np @ D_inv_sqrt
    else:
        D = np.diag(degrees)
        L = D - adj_np

    # U3: PSD stabilization
    if stabilize:
        from temper_placer.placement.constraint_weights import apply_psd_shift

        L_stable, shift, was_overdamped = apply_psd_shift(L, adj_np)
        if shift > 0:
            import logging
            logger = logging.getLogger(__name__)
            logger.info("PSD shift applied: %.4f (over-damped: %s)", shift, was_overdamped)
        L = L_stable

    L_jax = jnp.array(L)

    eigenvalues, eigenvectors = jnp.linalg.eigh(L_jax)

    if n < n_dims + 1:
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
        # All coordinates the same → place all components at board center (relative)
        center_x = board.width / 2
        center_y = board.height / 2
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

        # Compute offset (margin) - relative to board (0,0)
        offset_x = board.width * margin_fraction
        offset_y = board.height * margin_fraction

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
        _rng_key: Array | None = None,
        constraint_weights: dict[tuple[int, int], float] | None = None,
        placement_constraints: "PlacementConstraints | None" = None,
        pcl_collection: "ConstraintCollection | None" = None,
    ) -> Array:
        """
        Compute initial positions for all components using spectral embedding.

        If constraint_weights is provided, builds a constraint-weighted
        Laplacian instead of the uniform-weight baseline.

        Args:
            netlist: Components and connectivity.
            board: Board dimensions.
            rng_key: Random key (unused, for API compatibility).
            constraint_weights: Optional per-edge constraint weight contributions.
            placement_constraints: PlacementConstraints for building weights.
            pcl_collection: PCL constraint collection for building weights.

        Returns:
            (N, 2) initial positions in board coordinates.
        """
        n = len(netlist.components)
        if n == 0:
            return jnp.zeros((0, 2))
        if n == 1:
            center_x = board.width / 2
            center_y = board.height / 2
            return jnp.array([[center_x, center_y]])

        # Build connectivity graph — use constraint-weighted if available
        use_weighted = constraint_weights is not None and len(constraint_weights) > 0
        if use_weighted:
            from temper_placer.placement.constraint_weights import (
                compute_laplacian_from_weights,
            )

            adj, _L = compute_laplacian_from_weights(
                netlist,
                constraint_weights=constraint_weights,
                normalized=self.normalized_laplacian,
            )
            adjacency = jnp.array(adj)
        else:
            adjacency = build_adjacency_matrix(netlist)

        # Find connected components (disjoint subgraphs)
        components = find_connected_components(adjacency)

        # Determine if PSD stabilization is needed (negative weights present)
        needs_stabilize = use_weighted and any(w < 0 for w in constraint_weights.values())  # type: ignore[union-attr]

        if len(components) == 1:
            all_coords = compute_spectral_coordinates(
                adjacency,
                n_dims=2,
                normalized=self.normalized_laplacian,
                stabilize=needs_stabilize,
            )
            positions = scale_to_board(all_coords, board, self.margin_fraction)
            positions = self._separate_coincident_components(positions, board)
            return positions

        # Multiple disjoint subgraphs: handle each independently
        return self._initialize_disjoint_subgraphs(
            adjacency, components, board, stabilize=needs_stabilize
        )

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

    def _initialize_disjoint_subgraphs(
        self,
        adjacency: Array,
        components: list[list[int]],
        board: Board,
        stabilize: bool = False,
    ) -> Array:
        """
        Initialize disjoint subgraphs independently and pack them strategically.

        Strategy:
        - Sort subgraphs by size (largest first)
        - Largest subgraph at board center
        - Smaller subgraphs placed in corners/spiral pattern
        - Each subgraph gets its own spectral embedding

        Args:
            adjacency: (N, N) adjacency matrix.
            components: List of component indices for each subgraph.
            board: Board dimensions.
            stabilize: If True, apply PSD stabilization before eigendecomposition.

        Returns:
            (N, 2) positions for all components.
        """
        n = adjacency.shape[0]

        # Sort subgraphs by size (largest first)
        sorted_subgraphs = sorted(components, key=len, reverse=True)

        # Compute spectral coordinates for each subgraph
        subgraph_coords = []
        for subgraph in sorted_subgraphs:
            if len(subgraph) == 1:
                # Single isolated component - just use zero coords
                subgraph_coords.append(np.array([[0.0, 0.0]]))
            else:
                # Extract subgraph adjacency matrix
                sub_adj = adjacency[np.ix_(subgraph, subgraph)]
                # Compute spectral coordinates
                coords = compute_spectral_coordinates(
                    sub_adj,
                    n_dims=2,
                    normalized=self.normalized_laplacian,
                    stabilize=stabilize,
                )
                subgraph_coords.append(np.array(coords))

        # Pack subgraphs onto board
        packed_positions = self._pack_subgraphs(sorted_subgraphs, subgraph_coords, board)

        # Reconstruct positions in original component order
        positions = np.zeros((n, 2))
        for subgraph, coords in zip(sorted_subgraphs, packed_positions):  # type: ignore[assignment]
            for idx, comp_idx in enumerate(subgraph):
                positions[comp_idx] = np.asarray(coords[idx])  # type: ignore[assignment]

        # Apply separation for coincident components within each subgraph
        positions_jax = jnp.array(positions)
        positions_jax = self._separate_coincident_components(positions_jax, board)

        return positions_jax

    def _pack_subgraphs(
        self,
        subgraphs: list[list[int]],
        subgraph_coords: list[np.ndarray],
        board: Board,
    ) -> list[np.ndarray]:
        """
        Pack subgraphs strategically: largest at center, others in corners/spiral.

        Packing strategy:
        - Subgraph 0 (largest): Board center, full region
        - Subgraph 1: Top-right corner (quadrant)
        - Subgraph 2: Top-left corner (quadrant)
        - Subgraph 3: Bottom-left corner (quadrant)
        - Subgraph 4: Bottom-right corner (quadrant)
        - Subgraph 5+: Spiral outward from corners

        Args:
            subgraphs: List of component indices (sorted by size).
            subgraph_coords: List of spectral coordinates (normalized [-0.5, 0.5]).
            board: Board dimensions.

        Returns:
            List of scaled positions for each subgraph.
        """
        packed = []

        for i, (_subgraph, coords) in enumerate(zip(subgraphs, subgraph_coords)):
            if i == 0:
                # Largest subgraph: center region with margin
                region = self._get_board_region(board, "center", self.margin_fraction)
            elif i == 1:
                # Top-right corner
                region = self._get_board_region(board, "top-right", self.margin_fraction)
            elif i == 2:
                # Top-left corner
                region = self._get_board_region(board, "top-left", self.margin_fraction)
            elif i == 3:
                # Bottom-left corner
                region = self._get_board_region(board, "bottom-left", self.margin_fraction)
            elif i == 4:
                # Bottom-right corner
                region = self._get_board_region(board, "bottom-right", self.margin_fraction)
            else:
                # Fall back to center with offset (spiral pattern)
                # This handles the rare case of 6+ disjoint subgraphs
                angle = (i - 4) * 2.618  # Golden angle
                radius = 0.3 * min(board.width, board.height)
                offset_x = np.cos(angle) * radius
                offset_y = np.sin(angle) * radius
                region = self._get_board_region(
                    board, "center", self.margin_fraction, offset=(offset_x, offset_y)
                )

            # Scale coordinates to region
            scaled = self._scale_to_region(coords, region)
            packed.append(scaled)

        return packed

    def _get_board_region(
        self,
        board: Board,
        location: str,
        margin: float,
        offset: tuple[float, float] = (0.0, 0.0),
    ) -> dict:
        """
        Get a rectangular region of the board.

        Args:
            board: Board dimensions.
            location: "center", "top-left", "top-right", "bottom-left", "bottom-right".
            margin: Margin fraction.
            offset: Optional (x, y) offset from region center.

        Returns:
            Dict with 'x_min', 'x_max', 'y_min', 'y_max', 'center_x', 'center_y'.
        """
        margin_x = board.width * margin
        margin_y = board.height * margin

        if location == "center":
            x_min = margin_x
            x_max = board.width - margin_x
            y_min = margin_y
            y_max = board.height - margin_y
        elif location == "top-right":
            # Push further into corner (use 2/3 point, not midpoint)
            x_min = board.width * 0.67
            x_max = board.width - margin_x
            y_min = board.height * 0.67
            y_max = board.height - margin_y
        elif location == "top-left":
            x_min = margin_x
            x_max = board.width * 0.33
            y_min = board.height * 0.67
            y_max = board.height - margin_y
        elif location == "bottom-left":
            x_min = margin_x
            x_max = board.width * 0.33
            y_min = margin_y
            y_max = board.height * 0.33
        elif location == "bottom-right":
            x_min = board.width * 0.67
            x_max = board.width - margin_x
            y_min = margin_y
            y_max = board.height * 0.33
        else:
            raise ValueError(f"Unknown location: {location}")

        center_x = (x_min + x_max) / 2 + offset[0]
        center_y = (y_min + y_max) / 2 + offset[1]

        return {
            "x_min": x_min,
            "x_max": x_max,
            "y_min": y_min,
            "y_max": y_max,
            "center_x": center_x,
            "center_y": center_y,
            "width": x_max - x_min,
            "height": y_max - y_min,
        }

    def _scale_to_region(self, coords: np.ndarray, region: dict) -> np.ndarray:
        """
        Scale normalized coordinates to fit within a region.

        Args:
            coords: (N, 2) coordinates in normalized space (roughly [-0.5, 0.5]).
            region: Dict with region bounds from _get_board_region.

        Returns:
            (N, 2) scaled coordinates.
        """
        if len(coords) == 0:
            return coords

        # Normalize to [0, 1]
        min_c = np.min(coords, axis=0)
        max_c = np.max(coords, axis=0)
        range_c = max_c - min_c

        # Avoid division by zero for degenerate cases
        range_c = np.where(range_c < 1e-10, 1.0, range_c)

        normalized = (coords - min_c) / range_c

        # Scale to region with some internal margin (10% of region size)
        internal_margin = 0.1
        usable_width = region["width"] * (1 - 2 * internal_margin)
        usable_height = region["height"] * (1 - 2 * internal_margin)

        scaled = np.zeros_like(coords)
        scaled[:, 0] = (
            region["x_min"] + region["width"] * internal_margin + normalized[:, 0] * usable_width
        )
        scaled[:, 1] = (
            region["y_min"] + region["height"] * internal_margin + normalized[:, 1] * usable_height
        )

        return scaled


@dataclass
class LearnedInitializer:
    """
    Initialize positions using a pre-trained GNN model.

    The model predicts [X, Y] coordinates in [0, 1] range based on
    netlist graph features.

    Attributes:
        model_path: Path to the pre-trained model parameter file (.pkl).
        fallback: Initializer to use if model loading fails.
    """

    model_path: str | Path | None = "models/learned_init.pkl"
    fallback: SpectralInitializer = field(default_factory=SpectralInitializer)

    def initialize(
        self,
        netlist: Netlist,
        board: Board,
        rng_key: Array | None = None,
    ) -> Array:
        """
        Predict initial positions using GNN inference.

        Args:
            netlist: Component netlist.
            board: Board dimensions.
            rng_key: Random key (unused).

        Returns:
            (N, 2) positions in board coordinates.
        """
        # 1. Attempt to load model parameters
        params = self._load_params()
        if params is None:
            return self.fallback.initialize(netlist, board, rng_key)

        # 2. Build graph features
        adjacency = build_adjacency_matrix(netlist)
        edges = jnp.array(np.where(np.array(adjacency) > 0)).T

        # Node features: [Area, PinCount, Fixed, Centrality]
        areas = jnp.array([c.width * c.height for c in netlist.components])
        pin_counts = jnp.array([len(c.pins) for c in netlist.components])
        fixed = jnp.array([c.fixed for c in netlist.components], dtype=jnp.float32)

        # Compute centrality for features
        degrees = jnp.sum(adjacency, axis=1)

        # Normalize features
        areas = areas / jnp.maximum(jnp.max(areas), 1e-6)
        pin_counts = pin_counts / jnp.maximum(jnp.max(pin_counts), 1e-6)

        nodes = jnp.stack([areas, pin_counts, fixed, degrees], axis=-1)

        # 3. Run Inference
        model = LearnedInitializerGNN()
        norm_positions: Array = model.apply({"params": params}, nodes, edges)  # type: ignore[assignment]

        # 4. Scale to board
        positions = scale_to_board(norm_positions, board, margin_fraction=0.1)

        return positions

    def _load_params(self) -> dict | None:
        """Load model parameters from disk."""
        if self.model_path is None:
            return None

        path = Path(self.model_path)
        if not path.exists():
            return None

        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:
            return None
