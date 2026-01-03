# Plan: Systematic Improvement of Maze Router

**Target:** Increase routing completion from 26% to >98%.
**Baseline:** `temper_ready_for_route.kicad_pcb` using `internal_route.py`.

## 1. Baseline Analysis
The current `MazeRouter` uses a greedy A* approach. Nets routed early block paths for later nets. With complex constraints (split planes, HV zones), this leads to a high failure rate (~74% failure).

**Root Causes:**
1.  **Ordering Dependency:** Greedy routing is highly sensitive to net order.
2.  **Lack of Rip-up:** Once a net is placed, it is immutable unless using the experimental `PushShoveRouter`.
3.  **Coarse Grid:** Grid-based A* may miss fine-grained paths available to shape-based routers.

## 2. Execution Roadmap

### Phase 1: Infrastructure & Benchmarking
*   Create `scripts/benchmark_router.py` to run routing on a set of test boards and output JSON metrics (completion, length, time).
*   Establish "Golden Baselines" (FreeRouter output) for comparison.

### Phase 2: Rip-up and Reroute (RRR)
*   Implement the standard conflict-resolution algorithm:
    *   Route net $N$.
    *   If blocked by nets $B_1, B_2...$:
        *   "Rip up" $B_1, B_2$ (remove from occupancy).
        *   Route $N$.
        *   Add $B_1, B_2$ back to the queue with a "history cost" penalty to discourage using the same resources again.
*   **Hypothesis:** This single change should boost completion from 26% to >80%.

### Phase 3: Cost Function Tuning
*   **Wrong-Way Penalty:** Prefer Horizontal routing on one layer, Vertical on another to reduce blocking.
*   **Via Penalty:** Tune via cost to prevent excessive layer hopping while allowing necessary transitions.
*   **Margin Cost:** Add soft penalties near obstacles to leave room for other traces (avoid "hugging" too tight).

### Phase 4: Push-Shove Integration
*   Use `PushShoveRouter` (`push_shove.py`) as a local solver for dense areas where grid A* fails.
*   Implement `UnifiedRouter.route_net` to seamlessly switch strategies.

## 3. Validation Strategy
*   **Unit Tests:** Verify RRR logic on small 10x10 grids.
*   **Integration:** Run `benchmark_router.py` after each phase.
*   **Visualization:** Use `visualization/layer_view.py` to inspect failures visually.
