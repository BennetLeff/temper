"""
Spectral Placement Engine.

Uses Laplacian Eigenmaps to find the analytically optimal relative placement
that minimizes total squared wirelength.
"""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

from temper_placer.router_v6.stage0_data import ParsedPCB


class SpectralPlacer:
    def __init__(self, pcb: ParsedPCB):
        self.pcb = pcb
        self.comp_to_idx = {c.ref: i for i, c in enumerate(pcb.components)}
        self.idx_to_comp = {i: c.ref for i, c in enumerate(pcb.components)}
        self.num_components = len(pcb.components)

    def compute_placement(
        self,
        constraint_weights: dict[tuple[int, int], float] | None = None,
    ) -> dict[str, tuple[float, float]]:
        """
        Compute spectral placement coordinates.

        Args:
            constraint_weights: Optional per-edge constraint weight contributions.

        Returns:
            dict mapping component ref -> (x, y) [normalized/unscaled]
        """
        if self.num_components < 3:
            # Trivial case
            return {c.ref: (0.0, 0.0) for c in self.pcb.components}

        # Re-scan components to build connectivity
        net_to_comps: dict[str, set[int]] = {}

        for comp_idx, comp in enumerate(self.pcb.components):
            if hasattr(comp, "pins"):
                for pin in comp.pins:
                    if pin.net:
                        if pin.net not in net_to_comps:
                            net_to_comps[pin.net] = set()
                        net_to_comps[pin.net].add(comp_idx)

        # Build adjacency matrix
        adj = np.zeros((self.num_components, self.num_components), dtype=np.float64)
        for _net_name, comp_indices in net_to_comps.items():
            k = len(comp_indices)
            if k < 2:
                continue
            weight = 1.0 / (k - 1)
            indices = list(comp_indices)
            for i in range(k):
                for j in range(i + 1, k):
                    u = indices[i]
                    v = indices[j]
                    adj[u, v] += weight
                    adj[v, u] += weight

        # Layer on constraint weights
        needs_stabilize = False
        if constraint_weights:
            for (i, j), w in constraint_weights.items():
                if 0 <= i < self.num_components and 0 <= j < self.num_components:
                    adj[i, j] += w
                    adj[j, i] += w
                    if w < 0:
                        needs_stabilize = True

        # Build normalized Laplacian
        degrees = np.sum(adj, axis=1)
        d_inv_sqrt = np.where(degrees > 0, 1.0 / np.sqrt(degrees + 1e-10), 0.0)
        D_inv_sqrt = np.diag(d_inv_sqrt)
        laplacian = np.eye(self.num_components) - D_inv_sqrt @ adj @ D_inv_sqrt

        # PSD stabilization if negative weights are present
        if needs_stabilize:
            from temper_placer.placement.constraint_weights import apply_psd_shift

            laplacian_stable, shift, was_overdamped = apply_psd_shift(laplacian, adj)
            if shift > 0:
                import logging
                logger = logging.getLogger(__name__)
                logger.info(
                    "SpectralPlacer PSD shift: %.4f (over-damped: %s)",
                    shift, was_overdamped,
                )
            laplacian = laplacian_stable

        # Convert to sparse for eigsh
        laplacian_sparse = sp.csr_matrix(laplacian)

        # Eigen decomposition
        k = min(self.num_components - 1, 3)
        if k < 2:
            return {c.ref: (0.0, 0.0) for c in self.pcb.components}

        try:
            evals, evecs = spla.eigsh(laplacian_sparse, k=k, which="SA")

            x_vec = evecs[:, 1]
            y_vec = evecs[:, 2] if k > 2 else np.zeros_like(x_vec)

            result = {}
            for i in range(self.num_components):
                ref = self.idx_to_comp[i]
                result[ref] = (float(x_vec[i]), float(y_vec[i]))

            return result

        except Exception as e:
            print(f"Spectral solver failed: {e}")
            # Fallback to current positions
            return {c.ref: c.initial_position or (0.0, 0.0) for c in self.pcb.components}
