# Phase 7: Smart Topological Legalization (Linear Programming)

## Philosophy: "Constraint Solving over Simulation"
The physics-based legalizer ("Shove") is heuristic and can get stuck in local minima or oscillate.
We will implement an **Analytical Legalizer** based on **Constraint Graphs** and **Linear Programming (LP)**.
This guarantees the mathematically optimal position (minimum displacement) that satisfies all non-overlap constraints.

---

## Methodology

### 1. Separation Logic
For every pair of overlapping components $A$ and $B$, we must choose a spatial relationship:
- $A$ is Left of $B$ ($L$)
- $A$ is Right of $B$ ($R$)
- $A$ is Above $B$ ($U$)
- $A$ is Below $B$ ($D$)

**Heuristic**: Preserve the relative order from the initial (invalid) placement.
If $|x_A - x_B| > |y_A - y_B|$, we separate in X.
If $x_A < x_B$, we enforce $x_B \ge x_A + \frac{w_A + w_B}{2} + margin$.

### 2. The Constraint Graphs (HCG & VCG)
We construct two Directed Acyclic Graphs (DAGs):
- **HCG (Horizontal)**: Edges $A \to B$ impose minimum X separation.
- **VCG (Vertical)**: Edges $A \to B$ impose minimum Y separation.

### 3. The Solver (1D Compaction)
For each axis (X and Y), we solve a constrained optimization problem:
$$ \text{Minimize } \sum |x_i - x_{initial, i}| $$
$$ \text{Subject to } x_j - x_i \ge w_{ij} \quad \forall (i, j) \in E_{HCG} $$

**Algorithm**:
Since the constraints form a DAG, we can solve this using the **Longest Path Algorithm** (Critical Path Method).
1. Add a source node $S$ connected to all nodes with 0 in-degree.
2. Topological Sort the graph.
3. Relax edges: $x_j = \max(x_j, x_i + w_{ij})$.
4. This finds the *left-most* legal compaction.
5. To minimize displacement, we can refine this using a simple QP or iterative relaxation.

### 4. Topology Integration (The "Smart" Part)
We can inject constraints from the Stage 3 Topology Solver:
- If Net $N$ connects $A \to B$, we can add a soft constraint (or weight) to keep them close in the sorting order.
- This ensures that legalization doesn't "break" the routing channels optimized by the SAT solver.

---

## Implementation Plan

### Module: `temper_placer.placement.analytical`

#### 1. `ConstraintGraphBuilder`
- Input: List of Components.
- Logic: Sweep-line algorithm or pairwise check to generate HCG/VCG edges based on current overlap.

#### 2. `CompactionSolver`
- Input: DAG + node weights (widths).
- Output: New coordinates.
- Algorithm: Critical Path (Longest Path).

### 3. Integration
- Replace `Legalizer` loop with `AnalyticalLegalizer.legalize()`.

## Advantages vs Physics
1. **Deterministic**: Same input -> Same output.
2. **Optimal**: Finds minimum area/displacement.
3. **Valid**: Guaranteed zero overlap if the graph is acyclic.
4. **Fast**: $O(N \log N)$ or $O(N^2)$ vs iterative convergence.
