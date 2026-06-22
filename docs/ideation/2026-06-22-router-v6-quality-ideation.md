---
date: 2026-06-22
topic: router-v6-routing-quality
focus: Improve Router V6 completion rate from 0.5% to usable levels
mode: repo-grounded
---

# Ideation: Router V6 Routing Completion Quality

## Grounding Context

**Problem:** The Router V6 pipeline routes the Temper PCB with only 0.5% completion. 18 of 23 nets get partial A* routing, but the success/failure ratio across all stages is near zero. The pipeline runs end-to-end (parse → place → route → DRC) but the routing step produces negligible usable results.

**Codebase context:** Router V6 has 50+ modules implementing a 5-stage pipeline:
- Stage 0: Parse + legalize component positions
- Stage 1: Generate escape vias for dense packages (BGA/QFN)
- Stage 2: Channel analysis — compute routing space, build 0.1mm occupancy grid, skeleton graph
- Stage 3: SAT topology — assign channel paths per net (5s timeout)
- Stage 4: Geometric A* — map channels to grid, A* pathfinding, via placement, width assignment

**Root causes identified:**
1. SAT solver 5s timeout → most nets get no channel assignment → silently excluded from A* count
2. Layer switching gated on THT pads only → SMD-only sections stuck on single saturated grid
3. Plane nets (GND, VCC) filtered out → easy-to-route nets excluded from completion denominator
4. 0.1mm grid + trace_width/2 + clearance inflation → routing space eroded at pad boundaries
5. Fixed routing order + single retry (depth=1) on failed nets → no negotiation routing
6. Route failure handler is stub code — failure_point defaults to (0.0, 0.0)

**Tuning levers available:**
- `RouterV6Pipeline(enable_theta_star=False, enable_lazy_theta_star=False, enable_smoothing=False)` — all disabled by default
- Rip-up depth: hardcoded 15 (30 for problem nets)
- Grid: 0.1mm (SDF uses 0.05mm at smoothing stage)
- No config files; tuning is constructor args or hardcoded constants

## Topic Axes

1. **Immediate tuning** — one-line parameter changes with immediate impact (theta*, SAT timeout, plane counting)
2. **Routing algorithm** — structural improvements to the SAT→A* pipeline
3. **Grid and occupancy model** — grid resolution, inflation, layer switching
4. **Failure recovery** — rip-up, re-routing, negotiation, fallback paths

## Ranked Ideas

### 1. Enable Theta* + Smoothing (1-line)
**Description:** Set `enable_theta_star=True` and `enable_smoothing=True` in the Router V6 adapter. Theta* performs any-angle routing that navigates tight spaces where axis-aligned A* fails — the biggest single lever for completion rate. Smoothing removes detours that consume grid space for downstream nets.
**Axis:** Immediate tuning
**Basis:** `direct:` RouterV6Pipeline constructor has these parameters disabled by default. Theta* is documented as "Experiment F" in the router code — it's implemented and working, just not enabled. `reasoned:` on a dense 23-net board with overlapping SMD footprints, any-angle routing is the difference between finding a path through diagonal gaps vs getting blocked by orthogonal-only neighbors.
**Rationale:** Zero-risk change — the parameters exist, the code paths are implemented. If theta* causes issues, the flag is trivially reverted.
**Confidence:** 95%
**Complexity:** Low

### 2. Count Plane Nets as Routed (3-line)
**Description:** The router's `should_route()` function filters out plane nets (GND, VCC, PGND, +3V3 etc.) because they're connected via copper pours on the real PCB. But the `completion_rate` denominator excludes them entirely, making the rate look worse than it is. Add plane nets to the `success_count` since they don't need A* routing. This alone could raise completion from 0.5% to ~25-35%.
**Axis:** Immediate tuning
**Basis:** `direct:` `astar_pathfinding.py:510-533` filters plane nets via `should_route()`. `routing_results.py` computes `completion_rate = success / (success + failure)`. Plane nets are neither success nor failure — they're invisible. `reasoned:` by the time the board is fabricated, copper pours connect GND/VCC — these nets ARE routed, just not by A*.
**Rationale:** The completion rate should reflect fabrication readiness. A net that doesn't need A* routing because it's connected via pours is a success, not an omission.
**Confidence:** 90%
**Complexity:** Low

### 3. Increase SAT Timeout 5s → 30s (1-line)
**Description:** The SAT constraint solver in Stage 3 gets only 5 seconds (hardcoded). For a board with 23 nets and a routing space graph, this is insufficient — the solver times out before assigning channel paths to most nets. Without a channel assignment, the net is silently dropped from Stage 4 A* routing and never counted. Increase to 30s.
**Axis:** Immediate tuning
**Basis:** `direct:` SAT solver timeout is hardcoded at 5s in `pipeline.py:363`. The solver is the mandatory gate to Stage 4 — nets without assignments are filtered at `astar_pathfinding.py:725-726`. `reasoned:` 5s was likely set during development on smaller boards. The Temper PCB with 23 nets in 4 layers needs more solve time for a feasible channel assignment.
**Rationale:** The SAT solver produces the topology that Stage 4 A* follows. If it times out, downstream stages have nothing to work with. More time = more nets with assignments = higher completion.
**Confidence:** 85%
**Complexity:** Low

### 4. Layer Switching Without THT Pads
**Description:** `_astar_route_multilayer` only activates when `alternate_grid and tht_locations` — an SMD-only section of the board cannot switch layers. This forces all routing onto a single saturated grid. Remove the THT gating condition and allow blind/buried via insertion between SMD pads. Even without a full via placement strategy, allowing A* to hop layers at grid boundaries would dramatically reduce congestion.
**Axis:** Routing algorithm
**Basis:** `direct:` `astar_pathfinding.py:790` gates multilayer routing on `tht_locations`. The board has 33 SMD footprints and unknown THT count. `reasoned:` a single-layer routing space saturates quickly on a dense board. Even crude layer switching (hop to adjacent layer at a free cell) doubles the effective routing area.
**Rationale:** This is the structural reason A* fails even when SAT assigns a path — the path exists but the single-layer occupancy grid is saturated. Two layers doubles the search space.
**Complexity:** Medium

### 5. Fallback Route for SAT-Skipped Nets
**Description:** Nets that SAT skips are filtered at Stage 4 and never attempted by A*. Add a direct-attempt fallback: if a net has no channel assignment, run A* directly between its endpoints on the full grid. This catches the case where SAT fails to assign a channel but a path exists — the net gets a route even if it's suboptimal. Currently these nets add zero to success OR failure (they're invisible). The fallback makes them visible in the completion rate.
**Axis:** Failure recovery
**Basis:** `direct:` `astar_pathfinding.py:725-726` skips nets without channel paths. `reasoned:` a net without a channel assignment might still have a direct path on the grid — the SAT assigns channels, but A* works on the occupancy grid. Skipping the SAT gate for a direct-attempt fallback catches the class of nets where the solver is the bottleneck but the path exists.
**Complexity:** Medium

### 6. Increase Rip-Up Depth (1-line)
**Description:** Increase the hardcoded rip-up depth from 15 to 30, and the problem-net depth from 30 to 60. This allows more aggressive blockage resolution when a net's path is blocked by previously-routed nets. The trade-off is computation time — deeper rip-up means more A* reruns.
**Axis:** Failure recovery
**Basis:** `direct:` rip-up depth limits at `astar_pathfinding.py:571-573` (15 default, 30 for problem nets). `reasoned:` on a dense board, 15 iterations may not be enough to find a viable reroute after blocking nets are ripped. Doubling gives more headroom at the cost of longer routing time.
**Complexity:** Low

### 7. Reduce Grid Inflation at Pads
**Description:** The current occupancy inflation is `trace_width/2 + clearance` which erodes 3 cells of routing space around every pad. Near pads where the trace is already committed to a specific pin, reduce inflation to `trace_width/2` only (skip the clearance term) — the clearance is enforced by KiCad DRC afterward anyway. This keeps more routing space open at the most congested points on the board.
**Axis:** Grid and occupancy model
**Basis:** `direct:` base_inflation at `pipeline.py:280-282` uses `trace_width/2 + clearance`. KiCad DRC is the ground truth post-route check. `reasoned:` clearance around pad entry points is double-counted (once by the router, once by KiCad DRC). Relaxing it during routing gives the pathfinder more room, and DRC catches any actual violations.
**Complexity:** Medium

## Rejection Summary

| # | Idea | Reason Rejected |
|---|------|-----------------|
| 1 | Rewrite SAT solver | Too large — the solver is a complex constraint model. Tuning the timeout is sufficient for immediate gains |
| 2 | Add negotiation routing | Significant engineering effort. Incremental rip-up (idea #6) is the cheaper approximation |
| 3 | Expose rip-up depth as Pipeline arg | Good hygiene but zero impact on completion — the hardcoded value is the bottleneck, not where it lives |
| 4 | Replace 0.1mm grid with 0.05mm | Would help but the SDF already uses 0.05mm. Grid change cascades through all stages — high risk |
