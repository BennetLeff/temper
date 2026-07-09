---
date: "2026-07-08"
topic: human-like-routing-quality
status: requirements
tier: standard-feature
---

# "Human-Like" Routing Operationalized — Octilinear, Via Budget, Corridor Consolidation, Track Spread

## Summary

Operationalize "looks human-made" as four measurable gates: (1) octilinear routing — percentage of track segments at 45° or 135° (diagonal), (2) via-count ceiling — signal vias (excluding thermal and stitching vias) ≤ threshold, (3) corridor consolidation — tracks sharing the same channel are grouped rather than interleaved, (4) track-spread — no unnecessarily sparse routing in open areas. Add an "AI-slop pattern" linter that flags degenerate routing artifacts (hairpin turns, single-net detours, isolated vias). Gate: all four metrics within threshold; linter returns 0.

## Problem Frame

A human PCB designer follows implicit aesthetic and layout-quality rules that produce "clean" boards: tracks run at 45° angles, vias are used sparingly, parallel tracks are grouped into neat corridors, and routing doesn't wander across open board areas. AI-generated routing, by contrast, often produces "slop" — orthogonal-only tracks, vias everywhere, spaghetti corridors, and tracks that detour across empty board for no reason. These don't affect DRC or electrical performance, but they affect manufacturability, inspectability, and trust.

## Requirements

### R1 — Octilinear routing

Route tracks at multiples of 45° (0°, 45°, 90°, 135°) rather than only orthogonal (0°, 90°). The existing A* pathfinder (`astar_core.py:189`) already iterates all 8 directions unconditionally. The work is (a) adding an octilinear-% metric (no such metric exists today) and (b) a post-route rectification pass or diagonal cost incentive to raise diagonal share above the current baseline.

Gate: ≥ 70% (provisional — to be calibrated against the human golden board in W1 implementation) of track length is diagonal (45° or 135°). The remaining 30% are orthogonal connections to pads and vias (0°/90°).

### R2 — Via-count ceiling

Signal vias (excluding thermal and stitching vias) on the routed board ≤ 100. Each via adds manufacturing cost and reliability risk. A human designer on a 33-component 4-layer board would use ~50-80 vias for signal routing plus thermal/stitching vias.

Gate: signal vias (excluding thermal and stitching vias) ≤ 100 (provisional — to be calibrated against the human golden board in W1 implementation). 100 provides ~20-via headroom over the 50-80 vias observed on the human reference board for the additional layer + routability margin.

### R3 — Corridor consolidation

Tracks sharing the same routing channel (the same space between components) should be grouped into a single corridor rather than interleaved with tracks from other channels. This is a topological constraint: nets originating from the same component cluster should stay together.

A **channel** is the rectangular gap region between two component courtyards wider than 3 track widths. **Co-routed** means two tracks adjacent with no foreign track interleaved between them. **Corridor consolidation score** = (# co-routed pairs) / (# pairs sharing a channel).

Gate: corridor consolidation score ≥ 0.7 (provisional — to be calibrated against the human golden board in W1 implementation). A score of 1.0 means every pair of tracks in the same channel is co-routed.

### R4 — Track-spread

In open board areas with no obstacles, tracks should be evenly distributed with a target spacing rather than clustering on one side or spreading to extremes. R4 measures spacing uniformity only; single-net wandering is covered by R5's single-net detour check.

**Target spacing** = min_clearance + track_width from the netclass SSOT. **Track-spread score** = (max gap between adjacent tracks in a channel) / (target spacing).

Gate: track-spread score ≤ 1.5 (provisional — to be calibrated against the human golden board in W1 implementation). A score of 1.0 means tracks are at exactly target spacing.

### R5 — AI-slop pattern linter

Define a linter that flags specific degenerate routing artifacts:
- **Hairpin turns:** a track segment that reverses direction within one grid cell (≥160° turn)
- **Single-net detours:** a net that deviates > 50% from the straight-line path between its endpoints (uses existing `diagnostics.detour_ratio = route_length / direct_distance`)
- **Isolated vias:** a via with only one connected segment (stub)
- **Zigzag patterns:** three or more consecutive alternating direction changes with no obstacle between them, excluding hairpin reversals

Gate: linter returns 0 OR the offending region is constrained by a KeepoutConstraint that the loop could not satisfy (UNSAT-surfaced). The W5 compound loop treats slop deltas as soft — skips on UNSAT rather than blocking convergence.

## Key Decisions

- **45° routing already runs — the A\* pathfinder iterates all 8 directions unconditionally (`astar_core.py:189`).** The work is measuring the diagonal share (a new octilinear-% metric) and raising it via a post-route rectification pass or diagonal cost incentive.
- **Corridor consolidation is a post-route optimization, not a pre-route constraint.** Route first, then consolidate parallel tracks into corridors. This avoids over-constraining the router.
- **The "slop linter" is a post-route check, not a routing constraint.** It doesn't prevent the router from producing slop — it detects it and feeds back into the compound place→route loop (W5).
- **Metric extraction is a W1 prerequisite.** `human_reference_extractor` currently measures via_count only; extending it to compute octilinear %, corridor score, and track-spread is a W1 prerequisite.

## Scope Boundaries

- Curved/arc routing is out of scope — octilinear is sufficient for this board.
- Differential-pair routing quality (W2 R6) is out of scope — this is about general track aesthetics.
- Via tenting, solder mask expansion, and silkscreen are out of scope.
- Feedback into the compound loop (W5) is deferred — this document defines the detection gates; W5 defines the constraint-delta feedback.

## Dependencies

- **W0 (router build unblock).**
- **W1 (single-layer route).**
- **W2 (4-layer stackup).** Via-count ceiling needs the stackup's via strategy.

## Success Criteria

All numeric thresholds below are provisional — to be calibrated against the human golden board in W1 implementation.

1. ≥ 70% of track length at 45° or 135° (diagonal)
2. Signal vias (excluding thermal and stitching vias) ≤ 100
3. Corridor consolidation score ≥ 0.7
4. Track-spread score ≤ 1.5
5. AI-slop linter returns 0
