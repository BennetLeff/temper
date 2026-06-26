# Phase 3: Robust Geometric Refinement (Hybrid Approach)

## Critique & Refinement
*Original Plan Risk*: Constructing complex "Safe Corridor" polygons from grid cells is computationally expensive ($O(N^2)$ union) and prone to numerical instability (`shapely` errors).
*Refined Strategy*: Use **Path Decimation** verified by **Signed Distance Fields (SDF)**. This achieves the "taut string" effect of the Funnel Algorithm without the heavy geometric construction overhead.

---

## Experiments

### Experiment H1: SDF-Verified Path Decimation (The "Rubber Band")
**Goal**: Remove jaggedness and minimize path length efficiently.
**Method**:
1. Start with the dense Theta* path.
2. **Iterative Shortcut**: For every triplet of nodes $(A, B, C)$:
   - Check if segment $AC$ is valid.
   - **Validity Check**: Instead of geometric ray-casting, sample the **SDF** along line $AC$.
   - Condition: $\min_{p \in AC} SDF(p) \ge 0$ (Safe).
   - If valid, remove $B$.
3. **Repeat** until no more nodes can be removed.
**Benefit**: Reduces node count by ~90% and removes "stair-casing" naturally. $O(N)$ runtime.

### Experiment H2: Vertex Relaxation (SDF Gradient Descent)
**Goal**: Maximize clearance for the remaining vertices.
**Method**:
- After H1, we have a minimal polyline (Corner $\to$ Corner).
- The vertices effectively "touch" obstacles (clearance = 0).
- **Relaxation**: Move each vertex $v$ along the SDF gradient $\nabla \phi$ until local clearance is maximized or it becomes collinear with neighbors.
- **Math**: $v_{new} = v + \alpha \nabla SDF(v)$.
- **Result**: Pushes the "tight string" slightly away from corners to improve yield.

### Experiment H3: Acute Angle Mitigation
**Goal**: Prevent "Acid Traps" (angles < 90°) at pads.
**Method**:
- Post-process the path endpoints.
- Ensure the entry vector into a Pad is aligned with the Pad's preferred axis (or normal to the edge).
- Insert a "dog-bone" or small intermediate segment if the angle is too sharp.

---

## Implementation Plan

### Module: `temper_placer.routing.exact_geometry`

#### 1. `PathSimplifier`
- Input: `RoutePath`, `SDFGrid`.
- Output: Optimized `RoutePath`.
- Logic: Greedy decimation using `sdf.get_distance(line_sample)`.

#### 2. `CornerRelaxer`
- Input: Simplified `RoutePath`.
- Logic: Nudge vertices away from obstacles using SDF gradient (local optimization only, no global energy minimization).

#### 3. `ViaLocker`
- Logic: Split 3D paths at Via locations. Optimize 2D segments independently. Treat Vias as fixed anchors initially.

## Success Metrics
1. **DRC Violations**: 0.
2. **Path Node Count**: Reduced by >80% vs Theta*.
3. **Runtime**: < 5s for full board (vs 25s for Snake Optimizer).
