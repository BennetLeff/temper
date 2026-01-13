# Phase 4: Provable Robustness via Closed-Loop Geometry

## Philosophy: "Measure, Don't Guess"
The persistent DRC violations indicate a disconnect between the Router's internal model ($M$) and the Design Rules Engine's reality ($R$). Instead of endlessly refining the parser to approximate $R$, we will use the DRC engine itself as a **Measurement Oracle** to correct $M$ iteratively.

We also adopt **Constructive Solid Geometry (CSG)** principles to transform "Clearance" problems into "Connectivity" problems, making violations mathematically impossible if a path exists.

---

## Experiments

### Experiment V1: The "Echo" Loop (Iterative Learning)
**Goal**: guaranteed resolution of "Missing Obstacle" shorts.
**Method**:
1. **Route**: Run the router with current Obstacle Map $O_i$.
2. **Measure**: Run KiCad DRC (CLI). Parse the JSON report.
3. **Learn**: For every violation $v$ (coordinate $x,y$):
   - Create a local exclusion zone $Z_v$ (e.g., Circle($x,y$, $r=0.5mm$)).
   - Add $Z_v$ to the Obstacle Map: $O_{i+1} = O_i \cup Z_v$.
4. **Retry**: Reroute the specific failed nets.
**Convergence**: The free space decreases monotonically. The router effectively "feels" the invisible obstacles by bumping into them and remembering the location.

### Experiment V2: Minkowski Configuration Space (C-Space)
**Goal**: Eliminate clearance math errors by geometry transformation.
**Method**:
- Instead of checking `Dist(Trace, Obs) > Clearance + Width/2` at runtime:
- **Pre-process**:
  - For each net class (Width $W$, Clearance $C$):
  - Compute $O_{expanded} = \bigcup (O_j \oplus \text{Disk}(W/2 + C))$.
  - Use `shapely.buffer` and `unary_union`.
- **Route**: Find a path for a *point* robot in $\mathbb{R}^2 \setminus O_{expanded}$.
**Guarantee**: Any valid path in this space corresponds to a physical trace with **zero** clearance violations. The geometry engine enforces the constraints *a priori*.

### Experiment V3: Homotopic Locking
**Goal**: Prevent "Tunneling" during simplification.
**Method**:
- When simplifying path $P_{rough} \to P_{smooth}$:
- Verify that the polygon formed by $(P_{rough} \cup P_{smooth})$ does not contain any obstacle centroids.
- If it does, the paths wind differently around an obstacle -> **Reject**.
- This ensures the Smoother respects the topology found by the Router (Theta*).

---

## Implementation Roadmap

### 1. `FeedbackLooper` (Module: `temper_placer.deterministic.feedback`)
- Wraps `RouterV6Pipeline`.
- Parses `drc_report.json`.
- Inject "Virtual Obstacles" into `Stage2Output`.

### 2. `CSpaceBuilder` (Module: `temper_placer.router_v6.c_space`)
- Replaces raw `SDFGrid` generation.
- Generates exact Buffered Polygons for the Pathfinding graph.

### Success Criteria
1. **Convergence**: < 3 iterations of V1 to reach 0 Shorts.
2. **Yield**: 100% DRC Clean board.
3. **Automation**: No human intervention required to identify "invisible" obstacles.
