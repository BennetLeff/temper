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

## Implications
1.  **Fanout is Crucial**: It solved the local "Pin Trap" problem. This utility `temper_placer.routing.fanout` is now a permanent tool in our arsenal.
2.  **Topology Limits**: We proved that a 2-layer dense weave has limited routability for non-orthogonal nets. This validates the need for 4-layer routing (Inner Layers) for complex nets in `Temper`.

## Artifacts
-   `temper_placer/routing/fanout.py`: The new generator.
-   `router-experiments/exp_02_c_complex_weave.py`: The updated benchmark proving the fanout integration.
