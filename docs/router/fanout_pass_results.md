# Fanout Generator & Dense Mesh Routing

## The "Dense Weave" Challenge (EXP-02-C)
We implemented a **Fanout Generator** to solve the "Start blocked" failures in the dense 8x8 weave experiment.
-   **Strategy**: "Dog-bone" fanout.
-   **Execution**:
    1.  Identify pins (e.g. Diagonals).
    2.  Place a Via at `(r+0.5, c+0.5) * pitch` (Geometric center of the 4-pin dual grid).
    3.  Create a trace from Pin to Via.
    4.  Tell the Router to start/end at the Via.

## Results
-   **Fanout Generation**: Success. The generator created connectivity-valid escapes.
-   **Routing**: **Failure (16/18)**.
    -   Although the router could now "escape" the pin, it remained trapped by the global topology.
    -   In a 2-layer board with a perfect Manhattan Weave (L1 Rows, L4 Cols), a diagonal net is topologically blocked on *both* layers simultaneously by the orthogonal traces.
    -   Solving this requires **Via Stitching** (jumping L1/L4 repeatedly to cross traces) or **4 Layers**.
    -   Even with reduced costs, the current A* implementation struggled to find a valid "zig-zag" path through the mesh.

## Update: 4-Layer Verification Findings (2025-12-30)

### 1. The "Through-Hole Barrier"
Initial attempts to route diagonal nets *through* a dense 8x8 THT grid failed even with 4 layers.
-   **Problem**: THT pins exist on *all* layers. They form a "forest of pillars" that blocks L2/L3 just as effectively as L1/L4.
-   **Result**: At standard 2.54mm pitch (0.1"), the gap between pins is ~0.74mm. While theoretically routable, the Rip-up and Reroute (RRR) algorithm diverged, creating **27,000+ clearance conflicts** as it tried to force diagonal traces through the orthogonal weave.

### 2. The "Via Forest" (SMD Components)
We hypothesized that replacing THT pins with SMD pads (Top Layer only) would open up L2/L3 for routing.
-   **Experiment**: 8x8 SMD grid. Rows on L1, Cols on L4. Diagonals on L2/L3.
-   **Result**: **Failure (28,000+ conflicts)**.
-   **Why?**: To connect the SMD pads on Top to the Column traces on Bottom (L4), the router had to place a **via at every column pin**. This grid of 64 vias recreated the exact same blockage as the THT pins.
-   **Lesson**: High-density routing on opposite layers *always* creates a vertical barrier, whether from physical pins or necessary vias.

### 3. Proven Solutions: Channel Reservation vs. Perimeter Routing
We tested specific professional strategies for escaping the dense grid:

*   **Strategy A: Center Escape (Tunneling)**: Attempting to route from the center pin *out* through the saturated grid.
    *   **Result**: **FAILED**. The center pin is topologically trapped by the surrounding "Via Forest" and Row traces.
*   **Strategy B: Channel Reservation**: Leaving one row of pads empty (depopulated) to create a "highway".
    *   **Result**: **SUCCESS (0 conflicts, 1.0s)**. The router easily utilized the empty channel to route the escape net on Layer 1.
*   **Strategy C: Perimeter Routing**: Routing signals that originate *outside* the grid *around* it.
    *   **Result**: **SUCCESS (0 conflicts, 1.6s)**.

### Conclusion
For `Temper`'s high-density regions:
1.  **Do not force internal routing** through dense pin fields.
2.  **Design for Manufacturing**: If a signal must escape the center of a dense array, you **must reserve a routing channel** (delete or move adjacent pins) to create a path. The router cannot "magic" a path through a solid wall of vias.
3.  **Strict Layer Partitioning** is mandatory for the dense core (L1=Row, L4=Col).

## Implications
1.  **Fanout is Crucial**: It solved the local "Pin Trap" problem. This utility `temper_placer.routing.fanout` is now a permanent tool in our arsenal.
2.  **Topology Limits**: We proved that a 2-layer dense weave has limited routability for non-orthogonal nets. This validates the need for 4-layer routing (Inner Layers) for complex nets in `Temper`.
3.  **Grid Resolution**: Router cell size must be <= Clearance/2 for reliable results in dense areas.
4.  **Layer Discipline**: High-density routing requires strict layer constraints to preserve channel capacity. "Flexible" routing often leads to divergence in congested areas.

## Artifacts
-   `temper_placer/routing/fanout.py`: The new generator.
-   `router-experiments/exp_02_c_complex_weave.py`: The updated benchmark proving the fanout integration.