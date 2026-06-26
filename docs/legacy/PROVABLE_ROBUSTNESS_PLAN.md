# Phase 4: Verification via Visualization & Dynamic Safety

## Critique & Pivot
*Original Plan Risk*: The "Feedback Loop" (V1) relying on DRC text reports is slow, unstable, and treats the symptom (shorts) rather than the root cause (incomplete world model).
*Refined Strategy*: **Visual Debugging** to confirm the "Missing Obstacle" theory, and **Dynamic Safety** to ensure routed nets see *each other*.

---

## Hypothesis Refinement
The `AC_L` vs `CGND` short persists despite accurate static parsing.
**New Theory**: **The "Ghost Trace" Problem**.
- The `SDFGrid` represents **Static Obstacles** (Pads, Keepouts, Pre-routed Tracks).
- The `OccupancyGrid` represents **Dynamic Obstacles** (New traces routed in this session).
- `PathSimplifier` currently checks **ONLY** the `SDFGrid`.
- **Failure Mode**: `PathSimplifier` optimizes a path to be "smooth" according to static geometry, but effectively "ignores" the `OccupancyGrid` reservation made by other nets. It might pull a string tight *through* a neighboring net that was just routed!

## Experiments

### Experiment V1: The "Dual-Layer" Safety Check
**Goal**: Ensure `PathSimplifier` respects both static geometry and dynamic reservations.
**Method**:
- Modify `PathSimplifier.check_segment_safety`:
  1. **Static Check**: `SDF.get_distance(p) > margin` (Existing).
  2. **Dynamic Check**: Query `OccupancyGrid` at `p`. If cell is occupied by *another net*, REJECT.
- **Why**: The grid router (Theta*) respects OccupancyGrid. The Smoother (Simplifier) broke that contract by looking only at SDF.

### Experiment V2: The "Truth Map" (Visualization)
**Goal**: visually confirm what the router sees.
**Method**:
- Generate an image `debug_layer_F_Cu.png`.
- Plot:
  - **Black**: Static Obstacles (from `RoutingSpace`).
  - **Red**: Low SDF regions (< margin).
  - **Blue**: Dynamic Occupancy (other nets).
  - **Green**: The failing path.
- **Analysis**: If the path crosses Black/Red, it's a Static bug. If it crosses Blue, it's a Dynamic bug.

---

## Implementation Plan

### 1. `PathSimplifier` Upgrade
- Inject `OccupancyGrid` into the simplifier.
- Add `check_occupancy(p)` method.

### 2. `DebugVisualizer`
- Simple script using `matplotlib` or `PIL` to render the router's internal state.

## Success Metrics
1. **Shorts**: 0.
2. **Visual Confirmation**: The debug image shows the path staying in "White" (Safe) space.
