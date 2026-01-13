# Phase 3: Robust Geometric Refinement (Homotopic & Computational Geometry)

## Philosophy: Constructive Geometry over Simulation
Iterative solvers ("Snakes") are sensitive to hyperparameters (step size, weights) and can fail (tunneling, oscillation). 
We will replace them with **Constructive Computational Geometry** algorithms that provide **guarantees** on validity and optimality.

The core concept is **Homotopy Preservation**:
1. The Grid Router (Theta*) finds a valid *topological* path (a sequence of free cells).
2. We convert this sequence into a **Safe Corridor** (Simple Polygon).
3. We compute the optimal **Geometric Path** strictly *inside* this corridor.

Since the corridor is constructed from free space, any path inside it is **guaranteed** to be DRC-clean regarding static obstacles.

---

## Experiments

### Experiment H1: Safe Corridor Construction
**Goal**: Convert a grid path into a continuous geometric "Tube" that guarantees safety.
**Method**:
1. Iterate through the grid cells $(x,y)$ traversed by the Theta* path.
2. Construct a polygon $P = \bigcup \text{Cell}_i$.
3. **Refinement**: Since the grid is conservative, $P$ is a rough approximation of free space. We can "inflate" $P$ locally until it hits real obstacles (using the SDF computed in Phase 2) to maximize the maneuvering room.
**Guarantee**: $P \cap \text{Obstacles} = \emptyset$.

### Experiment H2: The Funnel Algorithm (Euclidean Shortest Path)
**Goal**: Remove jaggedness ("stair-casing") optimally.
**Method**:
- The **Funnel Algorithm** finds the shortest path inside a simple polygon between two points.
- It operates on the triangulation of the polygon.
- **Math**: It maintains a "funnel" (deque of vertices) and collapses it as we traverse the channel.
- **Result**: A "taut string" path that hugs the inner corners of the corridor.
- **Pros**: $O(N)$ efficiency, guaranteed shortest length.
- **Cons**: Hugs corners (min clearance). Good for "tight" routing, but maybe too tight.

### Experiment H3: Medial Axis Retraction (Maximum Clearance)
**Goal**: Maximize manufacturing yield by centering traces.
**Method**:
- Instead of shortest path (hugging walls), we want the path furthest from walls.
- Construct the **Medial Axis Transform (MAT)** (or Voronoi Skeleton) of the Safe Corridor $P$.
- Project the original path onto this skeleton.
- **Result**: A path that flows down the "center river" of the free space.
- **Why**: This maximizes $d(\text{trace}, \text{obstacle})$, absorbing manufacturing tolerances.

---

## Implementation Plan

### Module: `temper_placer.routing.exact_geometry`

#### 1. `CorridorBuilder`
- Input: `RoutePath` (grid nodes).
- Output: `shapely.Polygon` (The Safe Corridor).
- Logic: Union of grid cell rectangles + optional expansion into SDF.

#### 2. `FunnelOptimizer`
- Input: Corridor Polygon, Start, End.
- Output: Optimized Polyline.
- Algorithm: `shapely.ops.triangulate` -> graph search -> string pulling.
- *Simplified Alternative*: `shapely.simplify` but constrained to stay within the polygon (buffer(0) check).

#### 3. `MedialAxisOptimizer`
- Input: Corridor Polygon.
- Output: Optimized Polyline.
- Algorithm: `skimage.morphology.medial_axis` on the rasterized corridor, or `scipy.spatial.Voronoi` of the polygon boundary samples.

## Comparison: Why this is better than Snakes?
| Feature | Snakes (Force-Directed) | Homotopic Corridor (Geometry) |
|---------|-------------------------|-------------------------------|
| **Validity** | Probabilistic (can tunnel) | **Guaranteed** (bounded by corridor) |
| **Stability** | Oscillates / Diverges | **Deterministic** |
| **Optimality**| Local Minimum | **Global Optimum** (for defined metric) |
| **Tuning** | Many parameters ($\alpha, \beta, \gamma$) | **Zero parameters** |

## Success Metrics
1. **Static DRC Violations**: Must be exactly **0** for all smoothed paths.
2. **Path Length**: Should be $\le$ Theta* path length.
3. **Runtime**: Should be faster than 200 iterations of snake optimization.
