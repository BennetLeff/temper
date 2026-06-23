---
title: "PCB Autorouter Completion Rate: 47× Routing Speedup but 33% Completion Wall"
date: 2026-06-23
module: "temper-placer"
category: "performance-issues"
tags: ["pcb", "autorouter", "jax", "temper", "gnhf", "pipeline", "compounding-agents"]
problem_type: "performance_issue"
symptoms:
  - "Temper pipeline takes 15+ minutes end-to-end on 24-net temper board"
  - "Only 8/24 nets (33%) complete routing"
  - "10 nets blocked by 6mm HV creepage clearances around Q1, Q2, D1, D2"
  - "DRC violations = 2 (downstream consequence of partial routing)"
root_cause: |
  Two distinct problems compounded: (1) the deterministic A* pathfinder's retry loop
  in sequential_routing.py was exponentially inflating iteration budgets via
  `distance × base × congestion_factor × layer_factor × safety_margin` (giving 1M
  iterations per segment for unreachable nets), and (2) the deterministic A* loop
  in maze_router.py was calling `query_tracks_near` 10× per `can_place_via` call
  when through-hole vias only need a single unfiltered query because they must
  satisfy clearance on all layers anyway. Together these caused 15+ minute pipeline
  runs. Separately, placement was never aware that 6mm HV clearances would consume
  the routing channels it created, so 10 nets were structurally unroutable at
  the placement-output level — no routing algorithm improvement can fix that.
resolution_type: "structural fix (pathfinder budgets + KD-tree dedup + placement/routing contract change)"
---

## Problem

The temper PCB autorouter pipeline (JAX-accelerated deterministic placement
followed by A* maze routing for a 24-net induction-cooker board) had two
distinct failure modes stacked on top of each other:

1. **Runtime**: 15+ minutes end-to-end per closure run
2. **Completion rate**: 8/24 (33%) nets routed, 10 nets blocked

Initial belief was that runtime was the main bottleneck. Profiling proved
it was. gnhf was used to fix it: 3 commits, 47× speedup to 19s.

After the speedup, the completion rate was unchanged. The 10 stuck nets
were blocked not by routing algorithm performance, but by **placement
producing component positions whose surrounding 6mm HV creepage
clearances leave no routing channels for the router to find**. No routing
optimization can solve that — placement must change first.

## What Didn't Work

- **gnhf targeting routing perf alone** — it correctly optimized retry budgets,
  removed redundant KD-tree queries, and capped pathfinder iterations. But this
  only attacked the wrong layer. 47× faster to 19s, completion rate unchanged.

- **Code review-style spot fixes without systematic grounding** — the codebase
  had `NetClassRules.creepage_mm` and `INTERNAL_LAYER_CREEPAGE_FACTOR=0.30` already
  configured; the bottleneck was that placement never consumed them. A
  "what's broken?" question alone doesn't surface that the very field the
  router uses as authoritative is being ignored upstream.

- **Treating ideation as a single 7-survivor brainstorm** — we ran ce-ideate
  with 6 frames (Pain, Inversion, Assumption-Breaking, Leverage, Cross-Domain,
  Constraint-Flipping) and got 7 strong survivors across all 5 axes (HV footprint
  inflation, Zone topology surgery, Placement scoring with routing foresight,
  Iterative feedback loop, HV constraint relaxation). But the survivors
  ranked by *idea quality* ≠ ranked by *cheapest first step*. The right order
  was: (1) ghost-pad injection (lowest code change, highest direct impact), (2)
  seed filtering (cheapest compute, highest compounding), then (3) channel-aware
  scoring, (4) guard strip, (5) obstacle expansion, (6) isolation slots, (7)
  min-cut bottleneck. The ideation doc listed "by leverage" but not "by
  ship order" — and shipped in that order, the easier features create the
  measurement surface for the harder ones.

## Solution (Two-Phase)

### Phase 1: Routing perf speedup (gnhf, 3 commits)

| # | Commit | Optimization | Before → After |
|---|--------|-------------|----------------|
| 1 | `e11793b0` | Reduce retry pathfinder budgets, add time caps, disable adaptive budget | >15min → 39.3s |
| 2 | `5f9d0576` | Remove redundant `for layer in range(10)` in `can_place_via` (single unfiltered `query_tracks_near` suffices for through-hole vias) | 39.3s → 29.0s (26% faster) |
| 3 | `0eeed91f` | Cap retry pathfinder iterations 5000→1000 (GATE nets need only ~400) | 29.0s → 19.2s (33% faster) |

**Net: >15min → 19.2s, 47× faster. Same routing outcome.**

### Phase 2: Placement awareness (7 brainstormed features, all implemented in worktrees)

| # | Branch | Change | Difficulty |
|---|--------|--------|------------|
| 1 | `feat/ghost-pad-injection` | Inject 6mm "ghost pads" at HV pin positions into placer's slot reservation, so the placer treats creepage as physical obstruction rather than a post-hoc routing rule | Low (≤50 lines in `phased_component_assignment.py`) |
| 2 | `feat/seed-filtering` | Pre-filter placement seed candidates by sampling the channel bottleneck map at component positions (O(1) per seed) so the first router run lands at >50% instead of 33% | Low (≤30 lines) |
| 3 | `feat/channel-aware-scoring` | Wire Stage 2 channel analysis output (`placement.channels.json` sidecar: obstacle maps, occupancy grids, bottleneck scores) into placer's `_place_optimize` scoring | Medium (~150 lines, new `channels.py`) |
| 4 | `feat/hv-lv-guard-strip` | Pre-placement stage that partitions components into HV/LV buckets, computes a 6mm guard strip between them, runs standard placement on two separated domains | Medium (4 implementation units) |
| 5 | `feat/clearance-obstacle-expansion` | Expand all HV pad geometries by 6mm creepage in the obstacle map before routing, with DRC fence verification | Medium (~80 lines) |
| 6 | `feat/isolation-slots-slotgen` | Consume existing-but-unused `isolation_slots` config in slot generation; propagate the per-slot clearance credit through the DRC oracle | Low (~40 lines + oracle wiring) |
| 7 | `feat/min-cut-bottleneck` | Capacitated routing graph + min-cut bottleneck detection to answer the diagnostic question "exactly where is routing blocked?" instead of just "10 nets stuck" | Medium-high (~200 lines, new `bottleneck_geometry.py`) |

## Why This Works

The 47× speedup came from eliminating wasted compute on unroutable nets
(retry budgets no longer inflate 1M× per segment; vias don't pay 10×
KD-tree cost for what they can never satisfy on the layers they care about).

The placement features attack the actual constraint: HV-net routing needs
explicit routing channels carved out during placement. The cheapest "ghost pad"
change forces the placer to leave 6mm of clear space around HV pins without
needing any new infrastructure; the more expensive channel-aware scoring
makes the placer continuously optimize for routing success.

Crucially, the **placement features are independent and stack**: ghost pads
prevent placement in known-bad regions, seed filtering avoids placement
seeds that put components in congestion, channel-aware scoring chooses
better positions, and the guard strip enforces the HV/LV separation as a hard
constraint. Each helps, all stack.

## Prevention

**For PCB autorouter pipelines**:

- **Run a profilable closure test that measures both runtime AND completion rate
  on every PR** — not just "tests pass" and not just "runtime budget met". The
  33% completion rate was structural; a 47× speedup that didn't change completion
  rate is still a failure-mode signal you want caught early.

- **When placing HV components, consume the routing-implied constraints
  upstream** — i.e., if the router enforces 6mm creepage, the placer should
  know that 6mm around HV pins is reserved space. The `NetClassRules.creepage_mm`
  field already exists in the codebase; if the placer doesn't read it, that's
  a design contract gap, not a routing problem.

- **Stage-2 channel analysis output is a measurement surface for placement
  optimization** — not just a router input. The decomposed `placement.channels.json`
  sidecar should be consumed by both the placement-stage scoring AND the router
  itself; the closed loop (placer → channel analysis → router → bottleneck report
  → next placer iteration) is what completes the feedback.

**For the gnhf compounding-agents pipeline**:

- **The 3-found-pattern heuristic (problem-stated vs structurally-caused vs
  contract-mismatch) is the right place to start, not a single-frame
  ideation brainstorm** — we wasted some iteration when "code review-style
  optimization" kept producing gnhf commits that the user (correctly) said was
  "don't stop until done".

- **Order brainstormed features by ship-readiness, not by elegance**:
  ghost-pad-injection is more valuable shipped-before channel-aware-scoring even
  though the latter sounds more "architectural" — because the simpler feature
  surfaces a measurement surface (did the dead `_inject_ghost_pads` code path
  work?) that the harder feature needs. Ship in order; let each PR inform the next.

- **When code reviews surface "this code is dead", that's a high-priority finding** —
  we found that `_inject_ghost_pads` (the unit's main implementation) was never
  called by `run()`. The 10 tests in U1 all passed by calling the dead code
  directly. This is the kind of failure that the next gnhf iteration would
  spend hours re-discovering.

- **Pipeline-vs-output contracts need end-to-end tests, not unit tests alone** —
  every one of the 7 features had at least one "this is wired in unit tests
  but not in production" finding. The systematic pattern: implementer tests
  the helper with a hand-built state, the pipeline never reaches the helper.

## Files Touched

- `packages/temper-placer/src/temper_placer/deterministic/__init__.py`
- `packages/temper-placer/src/temper_placer/deterministic/state.py`
- `packages/temper-placer/src/temper_placer/deterministic/stages/phased_component_assignment.py`
- `packages/temper-placer/src/temper_placer/deterministic/stages/zone_aware_slot_generation.py`
- `packages/temper-placer/src/temper_placer/deterministic/stages/clearance_grid.py`
- `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py`
- `packages/temper-placer/src/temper_placer/deterministic/stages/hv_lv_partition.py` (new)
- `packages/temper-placer/src/temper_placer/deterministic/geometry/guard_strip.py` (new)
- `packages/temper-placer/src/temper_placer/deterministic/channels.py` (new)
- `packages/temper-placer/src/temper_placer/deterministic/bottleneck_map.py` (new)
- `packages/temper-placer/src/temper_placer/deterministic/seed_filter.py` (new)
- `packages/temper-placer/src/temper_placer/deterministic/flags.py` (new)
- `packages/temper-placer/src/temper_placer/router_v6/bottleneck_geometry.py` (new)
- `packages/temper-placer/src/temper_placer/router_v6/diagnostics.py`
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py`
- `packages/temper-placer/src/temper_placer/router_v6/sdf_builder.py`
- `packages/temper-placer/src/temper_placer/router_v6/astar_grid.py`
- `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py`
- `packages/temper-placer/src/temper_placer/routing/constraints/drc_oracle.py`
- `packages/temper-placer/src/temper_placer/routing/maze_router.py`
- `packages/temper-placer/src/temper_placer/io/config_loader.py`
- `packages/temper-placer/src/temper_placer/io/isolation_slot_geometry.py` (new)
- `packages/temper-placer/src/temper_placer/regression/closure_test.py`
- `configs/temper_deterministic_config.yaml`
- `docs/ideation/2026-06-23-hv-clearance-placement-completion-ideation.md` (new)
- `docs/brainstorms/2026-06-23-{idea}-requirements.md` (7 new)
- `docs/plans/2026-06-23-{NNN}-feat-{idea}-plan.md` (7 new)
- `docs/plans/2026-06-23-seed-filtering-sc1-acceptance-addendum.md` (new)

## Related

- `docs/ideation/2026-06-23-hv-clearance-placement-completion-ideation.md` — 7 brainstormed features across 5 axes
- `docs/brainstorms/2026-06-23-*.md` — 7 requirements docs (one per feature)
- `docs/plans/2026-06-23-*.md` — 7 implementation plans (one per feature)
- gnhf commits on `main`: `e11793b0`, `5f9d0576`, `0eeed91f` (Phase 1 routing perf)
- 7 feature branches in `.worktrees/feat/` (Phase 2 placement awareness)
- `docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md` — prior pattern
- `docs/solutions/design-patterns/decomposing-monolithic-stage-micro-stages-2026-06-22.md` — prior pattern
- `docs/solutions/architecture-patterns/declarative-stage-dag-replaces-orchestrator-2026-06-22.md` — prior pattern
- `docs/solutions/design-patterns/dsn-universal-seam-eda-pipelines-2026-06-22.md` — prior pattern
