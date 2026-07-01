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

import jax.numpy as jnp
import numpy as np
from jax import Array

import hashlib

import jax

from temper_placer.core.board import Board
from temper_placer.core.netlist import (
    Net,
    Netlist,
    build_adjacency_matrix,
)
from temper_placer.heuristics.force_directed import compute_force_directed_layout
from temper_placer.io.config_loader import GroupSeparation, PlacementConstraints
from temper_placer.ml.learned_init import LearnedInitializerGNN


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
    ) -> Array:
        """
        Compute initial positions for all components using spectral embedding.

        For disjoint subgraphs, places largest subgraph at center and smaller
        subgraphs in corners/periphery to prevent overlap.

        Args:
            netlist: Components and connectivity.
            board: Board dimensions.
            rng_key: Random key (unused, for API compatibility).

        Returns:
            (N, 2) initial positions in board coordinates.

        Notes:
            - Deterministic for same netlist (no randomness).
            - Single components placed at center.
            - Disjoint subgraphs are partitioned and packed strategically.
        """
        n = len(netlist.components)
        if n == 0:
            return jnp.zeros((0, 2))
        if n == 1:
            center_x = board.width / 2
            center_y = board.height / 2
            return jnp.array([[center_x, center_y]])

        # Build connectivity graph
        adjacency = build_adjacency_matrix(netlist)

        # Find connected components (disjoint subgraphs)
        components = find_connected_components(adjacency)

        # If single connected graph, use unified spectral embedding
        if len(components) == 1:
            all_coords = compute_spectral_coordinates(
                adjacency,
                n_dims=2,
                normalized=self.normalized_laplacian,
            )
            positions = scale_to_board(all_coords, board, self.margin_fraction)
            positions = self._separate_coincident_components(positions, board)
            return positions

        # Multiple disjoint subgraphs: handle each independently
        return self._initialize_disjoint_subgraphs(adjacency, components, board)

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


@dataclass
class HierarchicalGroupInitializer:
    """
    Initialize positions using hierarchical group pre-clustering.

    Reduces dimensionality from N components to G super-nodes (G << N)
    by exploiting component_groups from the config, then explodes back
    to full positions.

    Attributes:
        normalized_laplacian: Passed to Phase 3 spectral embedding.
        margin_fraction: Board margin for Phase 3 scaling.
        force_iterations: Iterations for Phase 1 micro-solve.
        diagnostics: List of diagnostic messages set during initialize().
    """

    normalized_laplacian: bool = True
    margin_fraction: float = 0.1
    force_iterations: int = 200
    diagnostics: list[str] = field(default_factory=list)

    def initialize(
        self,
        netlist: Netlist,
        board: Board,
        constraints: PlacementConstraints | None = None,
    ) -> Array:
        """
        Compute initial positions using hierarchical group pre-clustering.

        Returns (N, 2) positions. Falls back to SpectralInitializer if
        no component_groups are defined.
        """
        self.diagnostics = []

        if constraints is None or not constraints.component_groups:
            fallback = SpectralInitializer(
                normalized_laplacian=self.normalized_laplacian,
                margin_fraction=self.margin_fraction,
            )
            return fallback.initialize(netlist, board)

        n = len(netlist.components)
        if n == 0:
            return jnp.zeros((0, 2))

        adjacency = build_adjacency_matrix(netlist)

        # Phase 1: Intra-group micro-placement
        micro_offsets = self._solve_group_micro_layout(
            netlist, adjacency, constraints.component_groups, board
        )

        # Phase 2: Coarsen to super-nodes
        (
            super_adj,
            super_node_map,
            component_to_super,
            group_to_super,
            group_name_to_super,
        ) = self._coarsen_to_super_nodes(
            netlist, adjacency, constraints.component_groups, board
        )

        # Phase 3: Global spectral embedding of super-nodes
        super_centroids = self._embed_super_nodes(
            super_adj, super_node_map, board, constraints.group_separations,
            group_name_to_super,
        )

        # Phase 4: Explode to component positions
        positions = self._explode_positions(
            super_centroids, micro_offsets, component_to_super,
            group_to_super, board,
        )

        self.diagnostics.append(
            f"Pre-clustered {n} components into {len(super_node_map)} super-nodes"
        )

        return positions

    def _solve_group_micro_layout(
        self,
        netlist: Netlist,
        adjacency: Array,
        component_groups: list,
        board: Board,
    ) -> dict[int, tuple[Array, list[int]]]:
        """Phase 1: Solve intra-group micro-layout per group using force-directed solver.
        
        Returns:
            dict mapping group_id → (M_i, 2) offsets, list of member indices.
            The member indices list specifies which component each offset row belongs to.
        """
        offsets: dict[int, tuple[Array, list[int]]] = {}
        self.diagnostics.append("Phase 1: Solving intra-group micro-layouts")

        for gid, group in enumerate(component_groups):
            member_indices = self._resolve_member_indices(netlist, group)
            if len(member_indices) <= 1:
                offsets[gid] = (jnp.zeros((len(member_indices), 2)), list(member_indices))
                continue

            max_spread = group.max_spread_mm
            if max_spread <= 0:
                max_spread = 30.0

            # Extract sub-adjacency
            idx_arr = jnp.array(member_indices, dtype=jnp.int32)
            sub_adj = adjacency[jnp.ix_(idx_arr, idx_arr)]

            # Initialize micro-positions around local origin
            seed = int(hashlib.md5(group.name.encode()).hexdigest()[:8], 16) & 0x7FFFFFFF
            rng_key = jax.random.PRNGKey(seed)

            local_positions = self._init_local_positions(
                netlist, member_indices, max_spread, rng_key
            )

            # Build subnetlist for force-directed solver
            sub_netlist = self._build_subnetlist(netlist, member_indices)

            # Run force-directed solve
            local_bbox = max_spread * 2.0
            area = local_bbox * local_bbox
            repulsion_k = float(jnp.sqrt(area / len(member_indices)))

            solved = compute_force_directed_layout(
                sub_netlist,
                local_positions,
                board_width=local_bbox,
                board_height=local_bbox,
                iterations=self.force_iterations,
                learning_rate=0.5,
                repulsion_k=repulsion_k,
                repulsion_power=1.0,
                weighted_adj=sub_adj,
                attraction_k=0.1,
                initial_temp=max_spread / 10.0,
                cooling_factor=0.95,
                min_temp=0.1,
            )

            # Validate: if diameter > max_spread_mm * 1.2, fall back to radial
            diameter = self._compute_pairwise_diameter(solved)
            if diameter > max_spread * 1.2:
                self.diagnostics.append(
                    f"  Group '{group.name}': force-directed diameter {diameter:.1f}mm "
                    f"exceeds {max_spread * 1.2:.1f}mm — radial fallback"
                )
                solved = self._radial_placement(member_indices, max_spread)

            offsets[gid] = (solved, list(member_indices))

            self.diagnostics.append(
                f"  Group '{group.name}': {len(member_indices)} components, "
                f"diameter {max(diameter, 0.0):.1f}mm / max_spread {max_spread:.1f}mm"
            )

        return offsets

    def _coarsen_to_super_nodes(
        self,
        netlist: Netlist,
        adjacency: Array,
        component_groups: list,
        board: Board,
    ) -> tuple[Array, list[list[int]], Array, dict[int, int], dict[str, int]]:
        """Phase 2: Coarsen components into super-nodes with aggregated adjacency.

        Returns:
            super_adj: (G, G) aggregated adjacency.
            super_node_map: list of lists of component indices per super-node.
            component_to_super: (N,) array mapping component index → super-node id.
            group_to_super: dict mapping group_id → super_node_id (for coarsened groups).
            group_name_to_super: dict mapping group_name → super_node_id.
        """
        n = adjacency.shape[0]
        board_diagonal = float(jnp.sqrt(board.width**2 + board.height**2))
        spanning_threshold = 0.3 * board_diagonal

        # Build component-to-group assignment with overlap resolution
        group_assignments: dict[int, int] = {}

        for gid, group in enumerate(component_groups):
            member_indices = self._resolve_member_indices(netlist, group)

            # Spanning-group detection
            if group.max_spread_mm > spanning_threshold:
                self.diagnostics.append(
                    f"  Group '{group.name}' spans >30% of board diagonal "
                    f"({board_diagonal:.1f}mm) — coarsening disabled, members placed individually"
                )
                continue

            for idx in member_indices:
                if idx in group_assignments:
                    existing_gid = group_assignments[idx]
                    existing_spread = component_groups[existing_gid].max_spread_mm
                    if group.max_spread_mm < existing_spread:
                        group_assignments[idx] = gid
                        self.diagnostics.append(
                            f"  Component '{netlist.components[idx].ref}' reassigned "
                            f"from '{component_groups[existing_gid].name}' to '{group.name}' "
                            f"(tighter spread: {group.max_spread_mm} < {existing_spread})"
                        )
                    else:
                        self.diagnostics.append(
                            f"  Component '{netlist.components[idx].ref}' appears in multiple "
                            f"groups ('{group.name}' + '{component_groups[existing_gid].name}') "
                            f"— kept in '{component_groups[existing_gid].name}' "
                            f"(tighter spread: {existing_spread} < {group.max_spread_mm})"
                        )
                else:
                    group_assignments[idx] = gid

        # Build super-node mapping
        super_node_map: list[list[int]] = []
        component_to_super = np.full(n, -1, dtype=np.int32)
        group_to_super: dict[int, int] = {}
        group_name_to_super: dict[str, int] = {}

        # First, add coarsened groups as super-nodes
        for gid in range(len(component_groups)):
            group = component_groups[gid]
            members = [i for i, g in group_assignments.items() if g == gid]
            if not members:
                continue
            # Skip spanning groups
            if group.max_spread_mm > spanning_threshold:
                continue
            sn_id = len(super_node_map)
            super_node_map.append(sorted(members))
            group_to_super[gid] = sn_id
            group_name_to_super[group.name] = sn_id
            for idx in members:
                component_to_super[idx] = sn_id

        # Then, add ungrouped components as individual super-nodes
        for idx in range(n):
            if component_to_super[idx] < 0:
                sn_id = len(super_node_map)
                super_node_map.append([idx])
                component_to_super[idx] = sn_id

        G = len(super_node_map)

        # Build aggregated super-adjacency
        super_adj = np.zeros((G, G), dtype=np.float32)
        for gi in range(G):
            for gj in range(gi + 1, G):
                members_i = super_node_map[gi]
                members_j = super_node_map[gj]
                weight = 0.0
                for mi in members_i:
                    for mj in members_j:
                        weight += float(adjacency[mi, mj])
                if weight > 0:
                    super_adj[gi, gj] = weight
                    super_adj[gj, gi] = weight

        return (
            jnp.array(super_adj),
            super_node_map,
            jnp.array(component_to_super),
            group_to_super,
            group_name_to_super,
        )

    def _embed_super_nodes(
        self,
        super_adj: Array,
        super_node_map: list[list[int]],
        board: Board,
        group_separations: list[GroupSeparation],
        group_name_to_super: dict[str, int] | None = None,
    ) -> Array:
        """Phase 3: Compute global spectral embedding of super-nodes."""
        G = super_adj.shape[0]
        if G == 0:
            return jnp.zeros((0, 2))
        if G == 1:
            center = jnp.array([[board.width / 2, board.height / 2]])
            return center

        spectral_coords = compute_spectral_coordinates(
            super_adj, n_dims=2, normalized=self.normalized_laplacian
        )
        centroids = scale_to_board(spectral_coords, board, self.margin_fraction)

        # Apply GroupSeparation nudges
        if group_separations and group_name_to_super:
            centroids = self._apply_group_separations(
                centroids, group_name_to_super, group_separations
            )

        return centroids

    def _explode_positions(
        self,
        super_centroids: Array,
        micro_offsets: dict[int, tuple[Array, list[int]]],
        component_to_super: Array,
        group_to_super: dict[int, int],
        board: Board,
    ) -> Array:
        """Phase 4: Explode super-node positions back to component positions.

        For each component: position = centroid[super_node] + offset[group][local_idx].
        Uses member_indices from micro_offsets to correctly pair offsets with components.
        """
        n = len(component_to_super)
        positions = jnp.zeros((n, 2))

        # First, assign centroids to all components
        for sn_id in range(len(super_centroids)):
            centroid = super_centroids[sn_id]
            mask = component_to_super == sn_id
            indices = jnp.where(mask)[0]
            for comp_idx in indices:
                positions = positions.at[int(comp_idx)].set(centroid)

        # Apply micro-offsets using the stored member_indices for correct pairing
        for gid, sn_id in group_to_super.items():
            if gid not in micro_offsets:
                continue
            g_offsets, g_member_indices = micro_offsets[gid]
            if len(g_member_indices) != g_offsets.shape[0]:
                continue
            for local_i, comp_idx in enumerate(g_member_indices):
                positions = positions.at[comp_idx].add(g_offsets[local_i])

        # Board-boundary correction: shift groups inward if members exceed bounds
        positions = self._shift_groups_in_bounds(positions, component_to_super, board)

        # Coincident separation
        positions = self._separate_coincident_components_fn(positions, board)

        return positions

    def _resolve_member_indices(self, netlist: Netlist, group) -> list[int]:
        """Map group component refs to integer indices."""
        indices = []
        for ref in group.components:
            try:
                indices.append(netlist.get_component_index(ref))
            except KeyError:
                self.diagnostics.append(
                    f"  Warning: Component '{ref}' in group '{group.name}' not found in netlist"
                )
        return indices

    def _init_local_positions(
        self,
        netlist: Netlist,
        member_indices: list[int],
        max_spread: float,
        rng_key: Array,
    ) -> Array:
        """Initialize local positions within a group's bounding box."""
        m = len(member_indices)
        positions = jnp.zeros((m, 2))

        # Fixed components use their anchor position
        for local_i, comp_idx in enumerate(member_indices):
            comp = netlist.components[comp_idx]
            if comp.fixed and comp.initial_position is not None:
                positions = positions.at[local_i].set(
                    jnp.array(comp.initial_position)
                )

        # Unfixed components: small circle at max_spread_mm / 2 from origin
        unfixed_mask = jnp.ones(m, dtype=bool)
        for local_i, comp_idx in enumerate(member_indices):
            comp = netlist.components[comp_idx]
            if comp.fixed and comp.initial_position is not None:
                unfixed_mask = unfixed_mask.at[local_i].set(False)

        unfixed_indices = jnp.where(unfixed_mask)[0]
        n_unfixed = len(unfixed_indices)
        if n_unfixed > 0:
            radius = max_spread / 2.0
            for k, local_i in enumerate(unfixed_indices.tolist()):
                angle = 2.0 * jnp.pi * k / n_unfixed
                positions = positions.at[local_i].set(
                    jnp.array([jnp.cos(angle) * radius, jnp.sin(angle) * radius])
                )

        return positions

    def _compute_pairwise_diameter(self, positions: Array) -> float:
        """Compute the maximum pairwise distance between positions."""
        if positions.shape[0] <= 1:
            return 0.0
        diff = positions[:, None, :] - positions[None, :, :]
        dist = jnp.sqrt(jnp.sum(diff**2, axis=-1) + 1e-10)
        return float(jnp.max(dist))

    def _build_subnetlist(
        self, netlist: Netlist, member_indices: list[int]
    ) -> Netlist:
        """Build a Netlist containing only the specified subset of components."""
        subset_comps = [netlist.components[i] for i in member_indices]
        # Build nets connecting only subset members
        subset_nets = []
        comp_set = {c.ref for c in subset_comps}
        for net in netlist.nets:
            pins_in_subset = [
                (ref, pin) for ref, pin in net.pins if ref in comp_set
            ]
            if len(pins_in_subset) >= 2:
                subset_nets.append(Net(net.name, pins_in_subset))
        return Netlist(components=subset_comps, nets=subset_nets)

    def _radial_placement(self, member_indices: list[int], max_spread: float) -> Array:
        """Fallback: arrange components in a circle at max_spread_mm / 2 radius."""
        m = len(member_indices)
        if m <= 1:
            return jnp.zeros((m, 2))
        radius = max_spread / 2.0
        angles = 2.0 * jnp.pi * jnp.arange(m) / m
        return jnp.stack([jnp.cos(angles) * radius, jnp.sin(angles) * radius], axis=-1)

    def _apply_group_separations(
        self,
        centroids: Array,
        group_name_to_super: dict[str, int],
        group_separations: list[GroupSeparation],
    ) -> Array:
        """Nudge super-node centroids apart based on GroupSeparation constraints."""
        for _ in range(3):
            for sep in group_separations:
                idx_a = group_name_to_super.get(sep.group_a)
                idx_b = group_name_to_super.get(sep.group_b)
                if idx_a is None or idx_b is None or idx_a == idx_b:
                    continue

                delta = centroids[idx_a] - centroids[idx_b]
                dist = jnp.linalg.norm(delta) + 1e-10
                if dist < sep.min_distance_mm:
                    push = (sep.min_distance_mm - dist) / 2.0
                    direction = delta / dist
                    centroids = centroids.at[idx_a].add(push * direction)
                    centroids = centroids.at[idx_b].add(-push * direction)

        return centroids

    def _shift_groups_in_bounds(
        self,
        positions: Array,
        component_to_super: Array,
        board: Board,
        margin: float = 3.0,
    ) -> Array:
        """Shift groups whose members exceed board bounds fully inward."""
        n = positions.shape[0]
        super_ids = sorted(set(c.item() for c in component_to_super if c >= 0))

        x_min = margin
        y_min = margin
        x_max = board.width - margin
        y_max = board.height - margin

        for sn_id in super_ids:
            mask = component_to_super == sn_id
            indices = jnp.where(mask)[0]
            if len(indices) == 0:
                continue

            group_positions = positions[indices]
            gx_min = float(jnp.min(group_positions[:, 0]))
            gx_max = float(jnp.max(group_positions[:, 0]))
            gy_min = float(jnp.min(group_positions[:, 1]))
            gy_max = float(jnp.max(group_positions[:, 1]))

            shift_x = 0.0
            shift_y = 0.0

            if gx_min < x_min:
                shift_x = x_min - gx_min
            elif gx_max > x_max:
                shift_x = x_max - gx_max

            if gy_min < y_min:
                shift_y = y_min - gy_min
            elif gy_max > y_max:
                shift_y = y_max - gy_max

            if shift_x != 0.0 or shift_y != 0.0:
                shift = jnp.array([shift_x, shift_y])
                for idx in indices.tolist():
                    positions = positions.at[idx].add(shift)

        return positions

    def _separate_coincident_components_fn(
        self, positions: Array, board: Board
    ) -> Array:
        """Delegate to SpectralInitializer's coincident separation."""
        init = SpectralInitializer()
        return init._separate_coincident_components(positions, board)
