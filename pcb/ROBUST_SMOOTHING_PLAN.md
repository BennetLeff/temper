# Phase 2: Robust Geometric Optimization via Active Contours

## Philosophy: Why Math, Not Heuristics?
Standard "trace shoving" or "force-directed" algorithms often treat traces as particles with simple 1/r² repulsion. This is a "band-aid" because it lacks a global definition of "correctness" and can get stuck in local minima or push traces into other obstacles.

We will use **Active Contour Models (Snakes)** backed by **Signed Distance Fields (SDF)**.
- **SDFs** provide a continuous, differentiable scalar field representing the board geometry. $SDF(x)$ is the exact distance to the nearest clearance boundary.
- **Snakes** treat the trace as a spline minimizing an Energy Functional.
- **Robustness**: This approach guarantees that if we minimize the energy without crossing the zero-level set of the SDF, we preserve the **homotopy class** (topology) found by the router while achieving the **optimal geometry**.

---

## Experiments

### Experiment S1: Signed Distance Field (SDF) Generation
**Hypothesis**: An SDF provides a faster and more accurate query for clearance than iterated geometry checks.
**Method**:
1. Rasterize all static obstacles (pads, keepouts) into a high-res binary grid.
2. Compute the **Euclidean Distance Transform (EDT)** to get the distance to the nearest obstacle for every pixel.
3. Subtract the required clearance to get the **Signed Distance Field**.
   - $Val > 0$: Safe region (margin).
   - $Val = 0$: Exact clearance boundary.
   - $Val < 0$: Violation.
4. Compute Gradient $\nabla \phi$ (Finite Difference) to get the "push" vector direction.

### Experiment S2: Variational Path Optimization ("Snakes")
**Hypothesis**: Minimizing a Snake Energy functional will remove jaggedness and fix minor DRC violations simultaneously.
**Formula**:
$$E_{total} = E_{internal} + E_{external}$$
$$E_{internal} = \alpha ||\mathbf{v}_i - \mathbf{v}_{i-1}||^2 + \beta ||\mathbf{v}_{i-1} - 2\mathbf{v}_i + \mathbf{v}_{i+1}||^2$$
(Encourages short lengths and low curvature/smoothness)
$$E_{external} = \gamma \sum \max(0, \epsilon - SDF(\mathbf{v}_i))^2$$
(Penalizes violating the clearance margin $\epsilon$)

**Algorithm**:
1. **Densify**: Resample the Theta* path to have nodes every ~0.1mm.
2. **Iterate**: Update node positions using Gradient Descent on $E_{total}$.
   $$\mathbf{v}_i^{t+1} = \mathbf{v}_i^t - \lambda \nabla E(\mathbf{v}_i^t)$$
3. **Homotopy Lock**: Prevent nodes from crossing $SDF=0$ boundary (tunneling) by clamping step size.

### Experiment S3: Mathematical Validation
**Hypothesis**: We can prove DRC compliance by querying the SDF.
**Method**:
- Compute $\min(SDF(p))$ for all points $p$ on the final path.
- If $\min > -tolerance$, the path is **mathematically proven** to be DRC clean relative to the grid resolution.

---

## Implementation Strategy

### 1. New Module: `geometry_fields`
- `SDFBuilder`: Converts `OccupancyGrid` or raw geometry into `scipy` EDT arrays.
- `FieldInterpolator`: Provides continuous $(x,y)$ queries from the discrete EDT grid.

### 2. New Module: `variational_router`
- `SnakeOptimizer`: Implementation of the iterative solver.
- `Densifier`: Upsamples linear segments into vertex chains.

### 3. Integration
- Insert as Stage 4.3 (Post-Processing) in `RouterV6Pipeline`.
- Input: `RoutePath` (jagged, from Theta*).
- Output: `RoutePath` (smooth, clearance-compliant).

## Success Metrics
1. **DRC Reduction**: clearance violations count $\to 0$.
2. **Path Quality**: Path length reduction (removing zig-zags).
3. **Stability**: No new shorts created (homotopy preservation).
