# Geometric Layer Assignment & Router Stability

## Problem: RRR Symmetry Breaking
In the "Auto Mode" of the Unified Router, we observed a phenomenon termed **"RRR Symmetry Breaking"**.
-   **Symptom**: The router would "thrash" between layers for simple nets, failing to converge even on trivial topologies.
-   **Cause**: Without explicit layer hints, the router treats all layers as equally valid for any net. When two crossing nets (one Horizontal, one Vertical) both pick the *same* layer (e.g., Top) due to lack of bias, they collide. The Rip-up and Reroute (RRR) mechanism then rips one up, but it might just pick the *same* bad layer again in the next iteration, or the other net might switch, leading to an infinite switching loop.

## Solution: Geometric-Aware Layer Assignment
We implemented a **Geometric-Aware Layer Assignment** strategy to break this symmetry before the router even starts.

### 1. Directional Detection
The `LayerAssignment` module now accepts `component_positions`. It calculates the bounding box of a net's pins to determine its dominant physical direction:
-   **Horizontal**: Width > Height * 1.2
-   **Vertical**: Height > Width * 1.2
-   **Mixed**: Aspect ratio roughly 1:1

### 2. Layer Bias
Based on the detected direction, we enforce a preferred layer that matches the `MazeRouter`'s internal `wrong_way_penalty`:
-   **Horizontal Nets** $\rightarrow$ **Layer 1 (Top)** (Router prefers horizontal motion here)
-   **Vertical Nets** $\rightarrow$ **Layer 4 (Bottom)** (Router prefers vertical motion here)

### 3. Configurable Router Bias
We also exposed `wrong_way_penalty` as a configurable parameter in `MazeRouter` (defaulted to 2.0), allowing us to tune how strongly the A* search adheres to these preferences.

## Verification: EXP-02-C (The Dense Weave)
To validate this, we created **EXP-02-C**, a high-density "Weave" benchmark:
-   **Setup**: An 8x8 grid of pins (2.54mm pitch) with alternating Horizontal and Vertical nets.
-   **Constraint**: 2 "Disturber" diagonal nets slicing through the collection.

### Results
-   **Orthogonal Nets (H/V)**: **100% Routed with 0 Vias**.
    -   This is the critical result. "0 Vias" means the Horizontal nets stayed entirely on L1 and Vertical nets stayed entirely on L4.
    -   Effectively, the system decomposed a complex 2D routing problem with $N^2$ potential conflicts into two non-interacting 1D routing problems.
-   **Diagonal Nets**: Failed (as expected for this stage).
    -   Diagonals are "Mixed" direction and don't fit the Manhattan strategy cleanly. They failed due to start/end pin blockages in the dense grid, serving as a good test case for future "Escape Routing" improvements.

## Key Takeaway
**Geometry is the best heuristic.** By checking the physical pin layout *before* routing, we can provide the router with a global strategy that it cannot easily discover on its own through local A* search.
