---
date: 2026-06-22
topic: router-v6-performance-bottleneck
focus: Resolve the 338K SAT variable explosion and 5 redundant A* routing iterations
mode: repo-grounded
---

# Ideation: Router V6 Performance Bottleneck

## Grounding Context

**Problem:** Router V6 runs 5 redundant A* iterations re-routing already-successful nets, and builds a 338K-variable SAT model for 23 nets. The pipeline takes 200s+ with no benefit from iterations 2-5.

**Profile findings (from `pcb/temper_placed.kicad_pcb`):**

| Stage | Detail | Cost |
|-------|--------|------|
| Stage 2 (channel analysis) | 5 layers, ~2,600 nodes + ~3,300 edges each | ~13K nodes, ~16K edges |
| Stage 3 (SAT model) | 338,514 variables, 5,176 clauses for 23 nets | ~14,700 vars/net — variable explosion |
| Stage 3 (SAT solving) | Solution found — solver is fake (greedy, `topology_solver.py:49` "simplified solver") | Milliseconds |
| Stage 4 (A*) | 5+ iterations routing same nets | Each re-routes already-successful nets |
| Loop cap | `len(routable_nets) * 5` retry attempts at `astar_pathfinding.py:750` | Forces 5+ iterations |

**Key insight:** The SAT solver at `topology_solver.py:42-141` is a simplified greedy assignment that never actually uses the timeout — the comment on line 49 says "A production implementation would use a real SAT solver like Z3 or MiniSat." Building the 338K-variable model is wasted work when the solver just does round-robin greedy assignment.

**Root cause chain:**
1. Channel skeleton extracts 2,600-3,300 nodes per layer → 13K total channel nodes
2. SAT model creates one variable per (net, channel_node) pair → 23 × 13K = 338K variables
3. Greedy solver assigns paths, returns "SATISFIABLE" → result is no better than direct A* would find
4. A* routes ~18 nets successfully on iteration 1
5. Rip-up loop re-enters Stage 3+4 for iterations 2-5, routing the same nets again
6. `len(routable_nets) * 5` retry cap keeps the loop running even after all nets are done

## Topic Axes

1. **SAT model simplification** — reduce or skip the variable explosion in Stage 3
2. **Iteration economy** — stop redundant re-routing of already-successful nets
3. **Channel graph pruning** — reduce the skeleton graph fed into SAT/A*
4. **A* optimization** — reduce per-route cost, cache paths across iterations

## Ranked Ideas

### 1. Exit Rip-Up Loop Early
**Description:** Track per-iteration success delta. After each iteration, if zero new nets were routed (compared to previous iteration), exit the rip-up loop immediately. The current 5 redundant iterations route the same ~18 nets every time — iteration 1 already succeeds.
**Axis:** Iteration economy
**Basis:** `direct:` The profile shows 5 iterations re-routing identical nets. `astar_pathfinding.py:750` caps retries at `len(routable_nets) * 5` with no early-exit check. `reasoned:` a rip-up loop's purpose is to try again when blocking nets are removed. If no new nets succeed, further iterations can't help — the cost is pure waste.
**Why it matters:** Cuts runtime ~80% (from 200s to ~40s) with zero quality impact. The most impactful single line change in the pipeline.
**Confidence:** 95%
**Complexity:** Low

### 2. Skip SAT Stage, Route Directly with A*
**Description:** The SAT solver at `topology_solver.py:42-141` is a simplified greedy assignment — not a real SAT engine. The 338K-variable model build in Stage 3.7 is wasted work. Skip Stage 3 entirely: route all nets with direct A* on the occupancy grid built in Stage 2.5, using the channel skeleton from Stage 2.3 as guidance. The greedy solver already does this (assigns channels by round-robin) — stripping it out just removes the overhead of encoding the problem as SAT clauses.
**Axis:** SAT model simplification
**Basis:** `direct:` `topology_solver.py:49` — "A production implementation would use a real SAT solver like Z3 or MiniSat." The current solver is acknowledged as placeholder. `direct:` The SAT model has 338K variables for 23 nets (profile output). `reasoned:` a greedy round-robin assignment encoded as SAT clauses and decoded back to channel paths is isomorphic to directly assigning channels by round-robin. Eliminate the encode-decode overhead.
**Why it matters:** Eliminates the entire 338K-variable model build. Stage 3 collapses from ~seconds to zero. Makes the pipeline ~30% faster.
**Confidence:** 85%
**Complexity:** Medium — needs to feed Stage 2 channel assignments directly into Stage 4 A*

### 3. Only Re-Route Failed + Blocked Nets
**Description:** The current rip-up loop re-routes ALL nets each iteration, even those that succeeded in previous iterations. Modify the loop to only re-route: (a) nets that failed, and (b) nets that were ripped up because a newly-routed net blocked their path. Successful, unblocked nets skip A* entirely on subsequent iterations.
**Axis:** A* optimization
**Basis:** `direct:` The profile shows all 18 successful nets being re-routed in every iteration. `astar_pathfinding.py:544-755` builds `routable_nets` from the full net list each iteration. `reasoned:` a net whose path hasn't changed and hasn't been blocked by others doesn't need re-routing. This is the standard incremental routing pattern from VLSI CAD.
**Why it matters:** Eliminates ~80% of A* calls in the rip-up loop. Combined with idea #1, the loop runs 1 iteration at ~20% of the current A* cost.
**Confidence:** 90%
**Complexity:** Low-Medium — needs to track which nets were bloacked

### 4. Prune Channel Graph to Net Bounding Boxes
**Description:** Before building the SAT model, filter channel nodes to only those within each net's bounding box. A net connecting two pads 10mm apart doesn't need channel nodes 80mm away. Reduces the ~14,700 channel nodes per net to ~100-500.
**Axis:** Channel graph pruning
**Basis:** `direct:` The channel skeleton has 2,600+ nodes per layer. Most are irrelevant to any given net. `reasoned:` a signal net only needs the channel segments between its endpoints. Including every channel node on the board creates an O(nets × channels) variable explosion.
**Why it matters:** Reduces SAT model from 338K variables to ~5-10K. Making Stage 3 model build nearly instant even if the SAT stage is kept.
**Complexity:** Medium

### 5. Replace SAT Greedy with Direct Channel Assignment
**Description:** Instead of bouncing through Stages 3.1-3.9 (build constraint model → build SAT model → greedy-solve → extract topology), assign channels directly at Stage 2.4 using the capacity vs demand estimates already computed. If demand fits capacity, assign deterministically. No SAT model, no constraint encoding, no decoder. The topology is implicit in the channel skeleton.
**Axis:** SAT model simplification
**Basis:** `direct:` Stage 2 already computes channel capacity (`pipeline.py:270`) and routing demand (`pipeline.py:272`). The capacity-vs-demand check is the only real constraint the SAT model enforces. `reasoned:` if routing demand ≤ channel capacity, the assignment is trivial (any ordering works). If demand > capacity, SAT wouldn't help either (the greedy solver would also fail). Skip the formalism.
**Complexity:** Medium-High — restructures Stages 2-4 interface

### 6. Cache A* Paths Across Iterations
**Description:** When a net's path is unchanged after rip-up (no blockers on its route), reuse the cached A* result from the previous iteration instead of re-running pathfinding. Only invalidate cache for nets whose path intersects newly-routed blocking nets.
**Axis:** A* optimization
**Basis:** `direct:` The current loop re-runs A* for every net every iteration. `reasoned:` a net's route only changes if a blocker appears on its path. Detecting blockers is already done in the rip-up logic — extend it to flag nets whose paths intersect with changed routes.
**Complexity:** Medium

### 7. Reduce Channel Skeleton Density
**Description:** Only extract skeleton lines from F.Cu and B.Cu (outer layers), dropping the 3 inner layers. Inner layers add 60% of the graph nodes but contribute negligible routing value — most nets route on outer layers, and layer switching happens at pads. Reduces channel graph from 13K to ~5K nodes.
**Axis:** Channel graph pruning
**Basis:** `direct:` Stage 2.3 extracts skeleton for all 5 layers, producing 2,600-3,300 lines each. `direct:` The board has 27 THT pads for layer switching — inner-layer routing is limited to PTH transitions. `reasoned:` an outer-layer-only skeleton reduces the SAT variable space by 60% with minimal routing quality impact on a 4-layer board where inner layers are used for power/ground planes.
**Complexity:** Low — 1 line in the channel extraction loop

## Rejection Summary

| # | Idea | Reason Rejected |
|---|------|-----------------|
| 1 | Replace SAT with Z3/Python-SAT | Tools would require new dependencies. The pseudo-SAT overhead can be eliminated without a real solver. |
| 2 | Parallelize A* across nets | Python GIL limits parallelism benefit. Net dependencies (blocker detection) complicate threading. |
| 3 | Reduce SAT model variable count | A stopgap — removing the model entirely (idea #2) is better than optimizing a model build for a fake solver. |
| 4 | Profile-guided iteration budget per net | Adaptive iteration budgets add complexity. A fixed early-exit (idea #1) is sufficient. |
