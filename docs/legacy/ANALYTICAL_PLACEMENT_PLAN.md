# Phase 7: Analytical Global Placement (Spectral & Linear Programming)

## Philosophy: "Math over Heuristics"
The current placement causes routing congestion because it relies on manual or heuristic positioning that may create "knots" in the connectivity graph. The Router oscillates because it tries to untangle these knots geometrically, which is impossible if the topology is twisted.

We will implement **Spectral Placement** to find the global optimum for the "Squared Wirelength" objective, providing a knot-free topological starting point.

---

## Part 1: Spectral Global Placement (The "Relaxed" Solution)
**Objective**: Find component coordinates $(x_i, y_i)$ that minimize total squared wirelength $\Phi = \sum_{i,j} w_{ij} [(x_i - x_j)^2 + (y_i - y_j)^2]$.

**Method**:
1.  **Graph Construction**: Nodes = Components. Edges = Weighted by Net Connectivity (1/pin_count).
2.  **Laplacian Matrix**: Construct $L = D - A$ (Degree - Adjacency).
3.  **Eigen-Decomposition**: Solve $L \mathbf{x} = \lambda \mathbf{x}$.
    *   The optimal X coordinates are the eigenvector associated with the 2nd smallest eigenvalue ($\lambda_2$).
    *   The optimal Y coordinates are the eigenvector associated with the 3rd smallest eigenvalue ($\lambda_3$).
4.  **Result**: A "cloud" of components where connected items are close. They will overlap heavily and likely be centered at (0,0).

## Part 2: Legalization (The "Real" Solution)
**Objective**: Snap the spectral result to valid coordinates without breaking the relative ordering (topology).

**Method**:
1.  **Spreading**: Scale/Stretch the spectral result to fill the board area.
2.  **Constraint Solving (LP)**:
    *   Preserve relative order: If $x^{spectral}_i < x^{spectral}_j$, enforce $x_j \ge x_i + w_i$ in the final solution.
    *   Minimize displacement: $\min \sum |x_i - x^{spectral}_i|$.
    *   Use Linear Programming (OR-Tools or Scipy) or 1D Compaction (Longest Path).

---

## Experiments

### Experiment A1: Spectral Energy Check
**Goal**: Prove the mathematical model works.
**Method**:
- Compute Total Squared Wirelength of the current layout.
- Run Spectral Placement.
- Compute Total Squared Wirelength of the new layout.
**Metric**: Energy reduction (Expect > 50% drop).

### Experiment A2: Visual Topology Check
**Goal**: Confirm "untangling".
**Method**: Render the connectivity graph lines. The Spectral placement should show fewer long crossing lines than the initial random/manual placement.

### Experiment A3: Legalization Success
**Goal**: Verify we can turn the "cloud" into a board.
**Method**: Run `AnalyticalLegalizer` (based on LP/Compaction) on the spectral output.
**Metric**: 0 Overlaps, Routing Congestion Map improvement.

---

## Implementation Plan

### Module: `temper_placer.placement.spectral`
- `build_connectivity_graph(pcb)` -> NetworkX graph / Adjacency Matrix.
- `compute_spectral_layout(graph)` -> Dict[ref, (x, y)].

### Script: `scripts/run_spectral_placement.py`
- Loads PCB.
- Runs Spectral.
- Runs Legalizer (reuse Phase 6 physics or new LP).
- Exports for visualization.
