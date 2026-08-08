<!-- provenance: commit=8abcec2418fa1f9858485f06aba9072881091235 dirty=true -->

# Channel-skeleton island bridging: characterisation and fix

**Date:** 2026-08-07
**Task:** `_ensure_skeleton_connectivity` in
`packages/temper-placer/src/temper_placer/router_v6/channel_skeleton.py` was
identified (commit `8abcec24`, the plane-fix + `ChannelSkeletonStage`
hardcode removal) as the router's blocking defect once F.Cu/B.Cu reach the
pipeline with real zone-pour geometry: an O(components² · nodes²)
brute-force island-bridging loop that did not complete in practical time.
This doc characterises the fragmentation, measures the old algorithm, and
records the fix.

**Measured on:** `pcb/temper.kicad_pcb`, worktree at commit `8abcec24`
(dirty — this fix's own uncommitted changes), single machine, no other
concurrent CPU-bound load in the measured windows.

---

## 1. Characterisation (before touching the algorithm)

Ran `ObstacleMapStage` + `RoutingSpaceStage`, then the medial-axis extraction
only (not the bridging loop), on all four routable layers:

| Layer | Nodes | Edges | Available area ratio | Islands | Top-5 island sizes |
|---|---:|---:|---:|---:|---|
| F.Cu | 41,271 | 52,341 | 25.0% | 153 | 19999, 18780, 538, 521, 459 |
| B.Cu | 18,805 | 22,576 | 25.2% | 225 | 7948, 5067, 1829, 476, 426 |
| In1.Cu | 21,713 | 28,991 | 98.2% | 3 | 21709, 2, 2 |
| In2.Cu | 21,713 | 28,991 | 98.2% | 3 | 21709, 2, 2 |

Two findings up front:

1. **The quadratic term is real.** For F.Cu, `sum over component pairs of
   |A|·|B|` (the number of node-pair distance comparisons the old
   algorithm's *single* outer-loop pass performs) is **~475 million**,
   dominated by the two ~20,000-node islands alone (19999 × 18780 ≈ 375M).
   B.Cu's equivalent figure is ~130 million.
2. **The island count itself correlates almost perfectly with obstacle
   density, not layer topology.** F.Cu/B.Cu (outer layers, real zone pours
   present) sit at ~25% available area and fragment into 153/225 islands.
   In1/In2 (inner layers, ~98% available area) produce only 3 islands each
   — one real region plus two 2-node degenerate slivers. See §5.

## 2. Algorithm chosen

**Exact minimum spanning tree over the skeleton's connected components**,
computed as:

1. `scipy.spatial.cKDTree.query_pairs(r=max_bridge_distance)` over all N
   skeleton nodes finds every node pair within the bridging radius in one
   call — O(N log N + P), P = pairs within radius (output-sensitive: bounded
   by local point density, not N²). Measured: 44.1M pairs for N=41,271 on
   F.Cu in 1.2s.
2. Filter to cross-component pairs (numpy boolean mask), compute distances
   vectorized, sort ascending — O(P log P).
3. Validate **every** candidate's geometry in one vectorized batch:
   `shapely.linestrings()` constructs all P candidate segments at once,
   `shapely.prepare()` + `shapely.contains()` tests all of them against the
   routable region (`available_area`) in a single C-level loop.
4. Kruskal via union-find consumes the sorted, pre-validated candidates,
   merging components until fully connected or the threshold is exhausted.

This is provably the same answer the old "always bridge the globally
closest cross-island node pair, recompute, repeat" loop computes: that
greedy rule is exactly Kruskal's MST algorithm over the complete node graph,
restricted to cross-component edges and thresholded at
`max_bridge_distance`. Replacing the brute-force distance computation with a
spatial index does not change which components end up merged — it only
avoids evaluating pairs that were never going to be the answer.

**Bound bought:** O(N log N + P log P), P output-sensitive in local point
density — not O(components² · nodes_per_component²).

**Rejected alternatives** (see the function's docstring in
`channel_skeleton.py` for the full writeup):

- *K-nearest-neighbour candidates (fixed K, e.g. 16)* — asymptotically
  cheaper per query, but an **approximation**: a component's true nearest
  cross-component point can be crowded out of any fixed K by same-component
  neighbours in a dense island (exactly the two ~20,000-node F.Cu islands).
  Implemented and measured; silently under-connected relative to the exact
  algorithm. A second fallback phase (exact search only over the few
  components K-NN missed) was also implemented and measured — and was
  *slower* than the exact radius query (≈57s for B.Cu alone), because a
  large fraction of real-geometry candidates are invalid and get rejected,
  pushing many components into the fallback path, whose own cost is
  quadratic in how many components still need it.
- *Per-candidate (non-vectorized) geometry validation*, checked lazily
  inside the Kruskal loop with a per-pair attempt cap to bound cost — also
  implemented and measured (F.Cu ≈54s, B.Cu ≈48s). Worked, but was still
  dominated by ~13µs/call Python-level `shapely` overhead at the P ~ 10⁶
  scale this board exhibits, and traded away exactness (a capped pair could
  in principle have had a valid bridge past the cap). Batching the *entire*
  candidate set through one vectorized `shapely.contains` call (~1µs/call —
  ~13x faster, because the per-call Python/GIL overhead is paid once for the
  batch instead of once per candidate) removed both problems at once, so the
  cap was deleted rather than kept as a secondary safeguard.
- *Euclidean MST over island centroids* — rejected: a centroid is not
  guaranteed to be a real skeleton node, and a centroid-to-centroid line is
  far more likely to cross an obstacle than a line between the islands'
  actual nearest boundary nodes.
- *R-tree (shapely STRtree) over per-node bounding boxes* — rejected in
  favor of a KD-tree: candidates here are point-to-point nearest-neighbour
  queries, which is what a KD-tree is built for; an R-tree earns its keep
  over 2D regions with extent, which skeleton nodes do not have.

## 3. Geometric validity

The **old algorithm had no geometry check at all** — it would happily bridge
the two nearest cross-island nodes regardless of what lay between them,
which on real zone-pour geometry could mean routing straight through
copper. The new algorithm validates every candidate against
`routing_space.available_area` (obstacles already subtracted) before
accepting it as a bridge; `extract_channel_skeleton` now threads
`available_area` through to `_ensure_skeleton_connectivity` for exactly this
purpose.

Verified on the real board (both F.Cu and B.Cu): **every bridge edge added
lies entirely inside `available_area`** (checked independently, post hoc,
via `prepared_area.contains(LineString(u, v))` for every new edge in the
result graph — 0 invalid out of 24 bridges on F.Cu, 0 invalid out of 55 on
B.Cu). Original skeleton edges are also verified untouched (bridging only
adds edges, never removes or mutates existing ones).

Three targeted synthetic tests
(`tests/router_v6/test_channel_skeleton_bridging.py`) prove this
structurally, not just on this one board:

- `test_bridge_rejected_when_no_valid_path_exists` — two islands 1mm apart
  (well under `max_bridge_distance`) with **no** connecting geometry in
  `available_area`: the function must leave them disconnected rather than
  fabricate a bridge through the gap.
- `test_bridge_uses_valid_path_around_obstacle` — a dumbbell-shaped
  `available_area` where the geometrically *invalid* direct line is shorter
  than the geometrically *valid* corridor line: the function must find and
  use the valid one and the result must be connected.
- `test_bridges_multiple_islands_into_connected_graph` — N islands, no
  obstacles: sanity-checks the MST behavior itself (spanning-tree edge
  count, all bridges within threshold, original edges preserved).

## 4. Measured wall time / RSS on `pcb/temper.kicad_pcb`

**Before** (old O(components² · nodes²) algorithm, reconfirmed independently
in this task rather than only cited from the plane-fix commit message): ran
the original `_ensure_skeleton_connectivity` against F.Cu's real 153-island
graph with a 120s wall-clock budget. **One outer-loop pass took 91.3s**
(close to the plane-fix commit's own 79s figure; the gap is machine-load
variance) — and F.Cu alone needs up to 152 such passes to finish, since each
successful bridge only reduces the island count by one and the loop
recomputes the full nearest-pair search from scratch every time. The run was
killed by the budget after pass 1; it does not complete in any practical
time.

**After** (new algorithm, `_ensure_skeleton_connectivity` standalone, wrapped
in `tracemalloc` for the Python-allocation component and measured
end-to-end with `/usr/bin/time -v` for whole-process peak RSS):

| Layer | Islands before | Bridging wall time | `tracemalloc` peak | Islands after | Bridges added |
|---|---:|---:|---:|---:|---:|
| F.Cu | 153 | 14.5s | 1183.8 MB | 129 | 24 |
| B.Cu | 225 | 14.6s | 551.8 MB | 170 | 55 |

Whole-script run (parse + `ObstacleMapStage` + `RoutingSpaceStage` +
medial-axis extraction + bridging, both layers): **33.55s wall, 2.84 GB peak
RSS** (`/usr/bin/time -v`, `Maximum resident set size`).

129/170 islands remaining after bridging is not a bridging-algorithm defect:
it is Kruskal correctly refusing to fabricate a bridge where no
geometrically valid straight line exists within `max_bridge_distance`
(10mm) — see §5.

## 5. Is 153 islands itself the defect? Yes — reported, not fixed here

F.Cu/B.Cu measure **~25% available area** versus **~98%** on the inner
layers on this board. This matches the ~24.7% figure already recorded in
`docs/solutions/best-practices/correct-diagnosis-unsafe-change-2026-07-28.md`'s
2026-07-29 addendum: `obstacle_map.py`'s zone-handling loop
(`build_obstacle_map`, section 3, "Zones / Keepouts") unions **every** zone
on a layer into that layer's obstacle polygon unconditionally, regardless of
which net the pour belongs to —

```python
# packages/temper-placer/src/temper_placer/router_v6/obstacle_map.py:123
# Safe default: Treat as obstacle. The router connects to PADS, not zones directly yet.
layer_obstacles[layer].append(poly)
```

— so pours the router will never actually route through (a net's own
copper) still carve the medial axis into many small, often genuinely
wall-separated pockets. The inner layers, with real pour-free area, produce
only 3 islands (one real region plus two 2-node slivers) on the same board.

This is corroborated directly by the bridging measurement itself: with
geometric validation in place, only 24/152 (F.Cu) and 55/224 (B.Cu) possible
merges have *any* valid straight-line bridge within 10mm — most of the
remaining islands are not merely far apart, they are genuinely separated by
obstacle geometry on every candidate examined. A fast, correct bridging
algorithm over 153/225 spurious islands is still solving the wrong problem:
the durable fix is the already-scoped, not-yet-implemented "pours become
derived output" project
(`docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md`, R7/U3, status:
swept — not implemented), which this task does not implement, per its scope.

## 6. How far `route_pcb()` gets afterwards

Ran `route_pcb()` end-to-end on `pcb/temper.kicad_pcb` (110 nets, 169
components) via the same `router_v6.adapter.route_pcb` entry point
`test_route_pcb_production_board` uses, with a self-imposed 10 GB RSS safety
cap (this is a shared multi-agent machine; per task scope, "reaching the OOM
is a successful outcome," not "let it actually OOM the box"). Observed:

- Stage 0/0.5/1 (parse, legalize, escape vias) complete normally.
- Stage 2 channel analysis reaches `ChannelSkeletonStage` for all four
  routable layers and **completes bridging on all of them** — F.Cu (171
  islands in this run's slightly different obstacle set — pad-anchor nodes
  are added after bridging, changing exact counts run to run, not a
  correctness issue), B.Cu (225 islands, matching §4), and the inner layers
  (3 islands each, matching §1) — where before the plane fix this stage
  never ran on F.Cu/B.Cu at all, and before this task's fix it did not
  finish in any observed run.
- Process RSS grew to ~1.6 GB within the first ~60s of wall time, past
  channel-skeleton bridging and into the later Stage 2 sub-stages
  (occupancy grid, layer capacity, routing demand) — the last stdout line
  observed was `Added 376 pad anchor nodes to skeleton` (the final
  `extract_channel_skeleton` step, inner layers). Everything after that is
  silent by design (no per-stage prints past Stage 2's micro-stages until
  Stage 3 logging), and RSS climbed steadily and without a plateau: 1.6 GB
  → 4.1 GB → 6.9 GB → 8.9 GB → 10.4 GB over roughly the next 4 minutes,
  polled every 8s. This is the same silent, monotonic growth signature
  `docs/evidence/2026-08-07-router-oom-diagnosis.md` documents for
  `ModelBuilder.build()`'s 42M-variable / 78M-clause CNF construction (its
  own baseline: ~7 GB at completion, OOMing past ~13 GB under shared-machine
  memory pressure) — consistent with having reached that stage, not a new
  memory regression introduced by this fix.
- The run was killed intentionally at 10.4 GB RSS (self-imposed cap, not a
  crash) rather than let it continue toward an actual OOM on a machine
  shared with other concurrent agent worktrees, per this task's
  instruction not to fix `#871` and this repo's general guidance against
  imposing avoidable load on shared infrastructure. It had not printed any
  Stage 3 completion or failure output by that point, i.e. it was still
  climbing, not stabilized.

This confirms connectivity is no longer the blocker: the pipeline now
reaches, and was still inside, the stages that lead to the already-
documented, already-diagnosed `#871` OOM
(`docs/evidence/2026-08-07-router-oom-diagnosis.md`), which this task does
not attempt to fix, per its scope. Before this fix, `route_pcb()` could not
reach this point at all on F.Cu/B.Cu (bridging did not complete); before
the plane fix it landed one commit earlier, `route_pcb()` never had
F.Cu/B.Cu skeletons to bridge in the first place.

## 7. Tests added

`packages/temper-placer/tests/router_v6/test_channel_skeleton_bridging.py`:

- Correctness: no-op when already connected, empty graph, multi-island
  spanning-tree bridging (no obstacles), bridge-rejected-when-no-valid-path,
  bridge-uses-valid-path-around-obstacle (see §3).
- Scale guard (`TestScaleGuard`): bridging time for an 8x increase in
  synthetic island count stays well under the ~64x a quadratic algorithm
  would cost (empirically: 200→1600 islands ≈6.2x time, 1600→20,000 islands
  (12.5x) ≈19.2x time — comfortably sub-quadratic); an absolute wall-clock
  ceiling test bridging 2,000 islands (4,000 nodes, past the old
  algorithm's own "N is small (<2000 nodes)" comment) in well under a
  second.

All pre-existing `channel_skeleton` tests pass unchanged.
`test_r3_channel_skeleton_filters_to_outer_layers`
(`test_wave1_easy_wins.py`) remains failing, as instructed — it asserts the
`ChannelSkeletonStage` hardcode removed by the plane-fix commit is still
present, and encoded the bug it was meant to catch as intended behavior.

## 8. Sources

- `docs/evidence/2026-08-07-router-oom-diagnosis.md` — the downstream OOM
  this fix's success is measured against reaching, not fixing.
- `docs/solutions/best-practices/correct-diagnosis-unsafe-change-2026-07-28.md`
  (2026-07-29 addendum) — the net-blind pour obstacle-map mechanism cited
  in §5.
- `docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md` — the scoped,
  not-yet-implemented fix for §5's upstream defect.
- `packages/temper-placer/src/temper_placer/router_v6/channel_skeleton.py`
  — `_ensure_skeleton_connectivity`'s full docstring records the same
  algorithm choice and rejected-alternatives reasoning as this doc, in the
  code itself.
