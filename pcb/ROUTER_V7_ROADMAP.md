# Router V7 Roadmap: Zero-Touch Production Automation

**Goal**: Transform Router V6 (a robust geometric solver) into a holistic PCB Designer that handles congestion, power integrity, and signal integrity without manual intervention.

---

## Phase 8: Negotiated Congestion (The 100% Completion Engine)
**Problem**: V6 oscillates endlessly on the last 5% of nets (Rip-up loops).
**Solution**: Implement the **PathFinder Algorithm** (McMurchie & Ebeling).
1.  **Iteration 1**: Route all nets independently. Allow shorts/overlaps.
2.  **Update Costs**: Calculate congestion map. Overused nodes get a `history_cost`.
3.  **Reroute**: Reroute nets using `cost = base + congestion + history`.
4.  **Converge**: As `history_cost` grows exponentially, nets are forced to find alternative paths, however long.
**Outcome**: Guaranteed convergence to a valid solution if one exists.

## Phase 9: Power Planes & Polygons (Power Integrity)
**Problem**: V6 routes power as thin traces (0.5mm). Production requires planes.
**Solution**: **Region-Based Synthesis**.
1.  **Seed**: Identify Power/GND pads.
2.  **Grow**: Use Voronoi or Wavefront expansion to claim free space for power planes *before* signals are routed.
3.  **Pour**: Convert regions to `Zone` polygons.
4.  **Route**: Signal router treats these zones as obstacles (or tunnels for vias).

## Phase 10: Differential Pair Engine (Signal Integrity)
**Problem**: USB/Ethernet signals must be routed as a coupled pair.
**Solution**: **State-Space Expansion**.
1.  Route pair `(P, N)` as a single entity.
2.  State: `(x, y, orientation, spacing_mode)`.
3.  Cost function penalizes spacing deviation and length mismatch.

## Phase 11: Global Placement Optimization
**Problem**: "Legal" placement can still be "Unroutable" (knots).
**Solution**: **Hierarchical Force-Directed Placement**.
1.  **Cluster**: Group components by net density.
2.  **Global Place**: Optimize cluster locations.
3.  **Detailed Legalize**: Use existing Phase 6 legalizer.

## Phase 8.5: Provable Capacity & Corridors (The Math Fix)
**Problem**: The "Oscillation" in Phase 8 occurs when the Global Router (Stage 3) assigns more nets to a channel than geometrically possible. PathFinder tries to solve an impossible packing problem.
**Solution**: **Algebraic Capacity & Topological Confinement**.

### 1. Algebraic Capacity Calibration
Instead of guessing channel capacity, we derive it from **Grid Efficiency constraints**.
- **Theory**: The max flow in a grid with via blockage is limited by the **Vertex Cut** density.
- **Action**: Update `layer_capacity.py` to use a conservative formula:
  $$ C_{effective} = \lfloor \frac{W_{channel} - 2\cdot \text{margin}}{W_{trace} + S_{spacing}} \rfloor \times (1 - \text{ViaDensityFactor}) $$
- **Guarantee**: If Stage 3 finds a SAT solution under these constraints, a geometric solution **exists** with high probability ($P > 99\%$).

### 2. Strict Topological Corridors
**Concept**: Do not allow PathFinder to wander across the whole board.
- **Method**: Convert the Stage 3 `TopologyGraph` into hard **Polygon Constraints** (Corridors).
- **Algorithm**:
  1. Construct Corridor Polygons for each edge in the Skeleton.
  2. In `_astar_search`, treat pixels outside the assigned Corridor as **Infinite Cost**.
- **Benefit**: Decomposes one global $O((N \cdot G)^2)$ problem into $K$ local $O(G_{channel}^2)$ problems. Oscillation is confined to local channels and resolved quickly or flagged as "Capacity Error" immediately.

### 3. Critique & Refinement (Phase 8.5)
**Weakness**: Hard Corridors are brittle (geometry bugs at junctions).
**Pivot**: **"Calibrate, Don't Constrain"**.
- Instead of forcing the router to stay in a box, we make the Global Solver (Stage 3) smarter.
- If Stage 3 knows the **Real Capacity** (calibrated via $\eta$), it won't over-subscribe channels.
- The oscillation in Stage 4 vanishes because the problem is feasible.

---

# Experiments

## Experiment T1: The Packing Limit (Calibration)
**Objective**: Measure the "Phase Transition" density where `Lazy Theta*` fails due to congestion/via blockage.
**Setup**:
- Channel: 5mm x 10mm.
- Trace Width: 0.2mm + 0.2mm spacing (Pitch 0.4mm).
- Theoretical Max: $N_{theo} = 5.0 / 0.4 = 12$ nets.
- **Variable**: Via Density (nets switching layers randomly).
**Method**:
- Run with $N=1..12$.
- Record $N_{max}$ (Success).
- Calculate $\eta = N_{max} / N_{theo}$.
**Outcome**: Update `layer_capacity.py` with specific $\eta_{via}$ factors.

## Experiment T2: Corridor Confinement
**Objective**: Verify A* stays inside a polygon.
**Setup**:
- Define a "U" shaped polygon corridor.
- Route start to end.
- **Pass**: Path follows the U shape.
- **Fail**: Path shortcuts through the void (violating topology).

---

# Critical Analysis & Refinement

## 1. The Pre-Mortem (Future: July 2026)
**Disaster Report**: Router V7 failed.
*   **Why?**: We implemented **Phase 8 (PathFinder)** on a grid that was too coarse. The congestion map allowed traces to exist, but the **Geometry Smoother (Phase 4)** couldn't legalize them because the topology was physically impossible (10 wires in a 1mm gap).
*   **Result**: The router said "Success" (valid topological path), but the output was a mess of DRC errors because the physics engine couldn't "shove" the wires into reality.
*   **Lesson**: Topological feasibility != Geometric feasibility. We decoupled them too much.

## 2. The Red Team / Devil's Advocate
**Blocking Concerns**:
1.  **Memory Explosion**: Phase 8 requires storing a congestion history for *every grid node*. On a 0.05mm grid for a 100x100mm board, that's $4 \times 10^6$ nodes. Python overhead will kill performance.
2.  **Power Plane Complexity**: Phase 9 (Planes First) is dangerous. If you fill the board with power, you block all signals. You need "Power *After* Signals" or "Co-Design". Routing signals through a Swiss-cheese plane is basically impossible.
3.  **Diff Pair Over-engineering**: Extending A* state-space explodes complexity ($N^2$ states). Just route them as two single nets with a "Magnet Force" (Phase 6 style) is 90% effective and 10% cost.

## 3. Steel-Man the Alternative
**Solution B: "Push and Shove" (Interactive Router Automation)**
Instead of global negotiation (Phase 8), use local deformation.
1.  **Method**: Route Net A. If Net B blocks, *push* Net B aside geometrically (using springs/physics) rather than ripping it up topologically.
2.  **Advantage**: Preserves topology. Very robust for "last mile" routing. Matches human workflow.
3.  **Verdict**: Hard to implement robustly in batch mode without a geometry engine like CGAL. PathFinder is simpler to implement on a Grid.

## 4. The Confidence Score
**Score**: 6/10.
**Gap**:
*   The disconnect between "Grid Congestion" and "Physical Widths" (Pre-Mortem #1) is fatal. PathFinder works on FPGAs (fixed tracks) but PCBs have variable widths.
*   "Planes First" (Phase 9) is risky.

---

# Refined Plan (Target Score: 9/10)

## Revised Phase 8: Capacity-Aware PathFinder
**Adjustment**: The grid must handle **Capacity**, not just binary occupancy.
*   Each edge has capacity $C$ (width in mm).
*   Each net consumes width $W$.
*   Cost function penalizes $\sum W > C$.
*   **Verification**: Run "Legalizer" (Smoother) periodically during negotiation to ensure geometric feasibility.

## Revised Phase 9: Skeleton-Based Power
**Adjustment**: Do not pour planes first.
1.  Route Power as **Thick Traces** (Spines) during Global Routing.
2.  Route Signals.
3.  **Flood** remaining space connected to Spines.
*   This guarantees connectivity for signals.

---

# Experiments

## Experiment C1: The Congestion Benchmark
**Objective**: Validate PathFinder convergence.
**Setup**:
- 20 nets in a bottleneck channel (capacity 10 tracks).
- Run standard Rip-up vs PathFinder.
**Metric**: Iterations to convergence. PathFinder should stabilize; Rip-up should oscillate.

## Experiment C2: The "Variable Width" Stress Test
**Objective**: Ensure capacity logic handles power traces (1.0mm) vs signals (0.2mm).
**Setup**:
- Force a 1.0mm trace and five 0.2mm traces through a 1.5mm gap.
- **Fail**: If router treats them as "6 nets" and tries to fit them.
- **Pass**: If router sees capacity $1.5mm < 1.0 + 5*0.2 = 2.0mm$ and detours the signals.

## Experiment P1: The Flood Fill
**Objective**: Test "Route then Flood" strategy.
**Setup**:
- Route full board.
- Seed "GND" at pad.
- Run Wavefront fill.
- **Metric**: Coverage area %. Continuity check.
