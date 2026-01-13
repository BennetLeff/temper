# Phase 7 Experiments: Topological Legalization (Analytical Placement)

## Objective
Replace the heuristic "Force-Directed" legalizer with a deterministic **Constraint Graph** approach.
We decompose the 2D packing problem into two 1D Linear Programming (LP) problems.

---

## Series 1: The Core Solver (1D)

### Experiment TP1: 1D Chain Compaction ("The Bookshelf")
**Goal**: Verify the "Longest Path" algorithm correctly removes overlaps in a single dimension while minimizing displacement.
**Setup**:
- 3 Components (A, B, C) of width 10mm.
- Initial positions: A=0, B=5, C=8 (Heavy overlap).
- Constraints: $A \to B \to C$ (A left of B left of C).
**Test**: Construct HCG (Horizontal Constraint Graph) and solve.
**Expected Result**:
- A stays at 0.
- B moves to 10 (0 + width_A).
- C moves to 20 (10 + width_B).
- Total displacement minimized.

### Experiment TP2: Slack Management ("The Centering")
**Goal**: Ensure components don't just "stack left" but preserve relative spacing if possible.
**Setup**:
- A=0, B=20. Width=10. (Gap of 10 exists).
- Constraint: $A \to B$.
**Test**: Solve.
**Expected Result**:
- Positions remain A=0, B=20. (Solver shouldn't collapse necessary gaps, only enforce minimums).
- *Math*: $x_j \ge x_i + w_i$. If current $x_j$ satisfies this, keep it.

---

## Series 2: 2D Constraint Generation

### Experiment TP3: The "Compass" Decision (Heuristic Ordering)
**Goal**: Correctly choose between Horizontal (HCG) or Vertical (VCG) separation for diagonal overlaps.
**Setup**:
- A at (0,0), B at (5, 5). Size 10x10. (Overlap in both X and Y).
- Aspect Ratio test:
    - Case 1: Overlap X > Overlap Y. Strategy: Separate Vertically (easier).
    - Case 2: Overlap Y > Overlap X. Strategy: Separate Horizontally.
**Expected Result**:
- Generates ONE constraint edge (either in HCG or VCG, not both).
- Resulting placement has 0 area overlap.

### Experiment TP4: Cycle Detection & Breaking ("The Deadlock")
**Goal**: Handle geometric cycles that make LP infeasible.
**Setup**:
- A (0,0), B (10,0), C (5, -5). Triangle.
- Bad Heuristic might say: A left of B, B left of C, C left of A.
**Test**:
- Detect Cycle in the graph.
- **Cycle Breaker**: Identify the "weakest" edge (smallest overlap or least logical) and reverse/delete it.
- Solve.
**Expected Result**: Solver succeeds (does not hang/crash) and resolves overlap.

---

## Series 3: Integration & Real Data

### Experiment TP5: The "D1 vs U_GATE" Benchmark
**Goal**: Solve the specific collision from Phase 6 using Analytical methods.
**Setup**: Load `temper.kicad_pcb`. Extract D1, U_GATE, C_VCC.
**Test**: Run Analytical Legalizer.
**Metrics**:
- **Displacement Norm**: $\sum |d_{new} - d_{old}|$. Compare vs Physics Legalizer.
- **Runtime**: Time to solution (Expect < 100ms vs Physics 1-2s).
- **Stability**: Run 10 times. Output should be identical (Deterministic).

---

## Implementation Sequence

1. **`ConstraintGraph` Class**: Data structure for DAGs.
2. **`LongestPathSolver`**: The O(V+E) solver.
3. **`AnalyticalLegalizer`**: The logic to build graphs from geometry.
4. **`test_analytical.py`**: Unit tests covering TP1-TP4.
