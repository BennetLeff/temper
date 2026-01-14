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

    def compute_placement(self) -> dict[str, tuple[float, float]]:
        """
        Compute spectral placement coordinates.
        Returns:
            dict mapping component ref -> (x, y) [normalized/unscaled]
        """
        if self.num_components < 3:
            # Trivial case
            return {c.ref: (0.0, 0.0) for c in self.pcb.components}

        # 1. Build Adjacency Matrix
        # Using Clique Model for hyperedges (nets)
        # Weight for clique of size k: w = 2/k (standard) or 1/(k-1)

        rows = []
        cols = []
        data = []

        for net in self.pcb.nets:
            # Find connected components
            connected_indices = []
            seen_refs = set()

            for pin in net.pins:
                # Resolve component ref from pin
                # In router_v6, net.pins are Pin objects.
                # We need to link back to component.
                # Usually we iterate components and check their pins?
                # Or parsing links pin->comp?
                # Let's assume pin.component_ref or finding via component list is needed.
                pass

            # Efficient way: Inverse map already built?
            # No. Let's build a map NetName -> List[CompIndex] first.
            pass

        # Re-scan components to build connectivity
        net_to_comps: dict[str, set[int]] = {}

        for comp_idx, comp in enumerate(self.pcb.components):
            if hasattr(comp, "pins"):
                for pin in comp.pins:
                    if pin.net:
                        if pin.net not in net_to_comps:
                            net_to_comps[pin.net] = set()
                        net_to_comps[pin.net].add(comp_idx)

        # Build edges
        for net_name, comp_indices in net_to_comps.items():
            k = len(comp_indices)
            if k < 2:
                continue

            # Clique weight
            weight = 1.0 / (k - 1)

            indices = list(comp_indices)
            for i in range(k):
                for j in range(i + 1, k):
                    u = indices[i]
                    v = indices[j]

                    # Add edge (u, v) and (v, u)
                    rows.append(u)
                    cols.append(v)
                    data.append(weight)

                    rows.append(v)
                    cols.append(u)
                    data.append(weight)

        # Construct sparse matrix
        adj = sp.coo_matrix((data, (rows, cols)), shape=(self.num_components, self.num_components))
        adj = adj.tocsr()

        # 2. Compute Laplacian: L = D - A
        # D is diagonal matrix of degrees (row sums of A)
        degrees = np.array(adj.sum(axis=1)).flatten()
        laplacian = sp.diags(degrees) - adj

        # 3. Eigen Decomposition
        # We need smallest eigenvalues.
        # k=3 because 1st is 0 (constant vector). We want 2nd and 3rd.
        # which='SM' (Smallest Magnitude)

        # Determine number of eigenvectors to compute
        # Must be < num_components
        k = min(self.num_components - 1, 3)
        if k < 2:
            return {c.ref: (0.0, 0.0) for c in self.pcb.components}

        try:
            # Use 'SA' (Smallest Algebraic) for symmetric matrix
            evals, evecs = spla.eigsh(laplacian, k=k, which="SA")

            # evecs is (N, k). Columns are eigenvectors.
            # Sorted by eigenvalue? usually.
            # 1st vector (index 0) should be near-zero eigenvalue (constant)
            # We want index 1 and 2.

            x_vec = evecs[:, 1]
            y_vec = evecs[:, 2] if k > 2 else np.zeros_like(x_vec)

            # Normalize to 0-1 range for easier downstream handling?
            # Or keep centered. Let's keep centered.

            result = {}
            for i in range(self.num_components):
                ref = self.idx_to_comp[i]
                result[ref] = (float(x_vec[i]), float(y_vec[i]))

            return result

        except Exception as e:
            print(f"Spectral solver failed: {e}")
            # Fallback to current positions
            return {c.ref: c.initial_position or (0.0, 0.0) for c in self.pcb.components}
