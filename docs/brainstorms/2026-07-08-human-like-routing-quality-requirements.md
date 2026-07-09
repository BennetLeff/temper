---
date: "2026-07-08"
topic: human-like-routing-quality
status: requirements
tier: standard-feature
---

# "Human-Like" Routing Operationalized — Octilinear, Via Budget, Corridor Consolidation, Track Spread

## Summary

Operationalize "looks human-made" as four measurable gates: (1) octilinear routing — percentage of track segments at multiples of 45°, (2) via-count ceiling — total vias ≤ threshold, (3) corridor consolidation — tracks sharing the same channel are grouped rather than interleaved, (4) track-spread — no unnecessarily sparse routing in open areas. Add an "AI-slop pattern" linter that flags degenerate routing artifacts (hairpin turns, single-net detours, unnecessary layer switches, isolated vias). Gate: all four metrics within threshold; linter returns 0.

## Problem Frame

A human PCB designer follows implicit aesthetic and layout-quality rules that produce "clean" boards: tracks run at 45° angles, vias are used sparingly, parallel tracks are grouped into neat corridors, and routing doesn't wander across open board areas. AI-generated routing, by contrast, often produces "slop" — orthogonal-only tracks, vias everywhere, spaghetti corridors, and tracks that detour across empty board for no reason. These don't affect DRC or electrical performance, but they affect manufacturability, inspectability, and trust.

## Requirements

### R1 — Octilinear routing

Route tracks at multiples of 45° (0°, 45°, 90°, 135°) rather than only orthogonal (0°, 90°). The existing A* grid pathfinder supports 8-directional search — the work is enabling it and measuring the result.

Gate: ≥ 70% of track segments (by length, not count) are at 45° or 135°. The remaining 30% are orthogonal connections to pads and vias.

### R2 — Via-count ceiling

Total via count on the routed board ≤ 100. Each via adds manufacturing cost and reliability risk. A human designer on a 33-component 4-layer board would use ~50-80 vias for signal routing plus thermal/stitching vias.

Gate: total vias (excluding thermal via arrays) ≤ 100. Thermal and stitching vias are counted separately.

### R3 — Corridor consolidation

Tracks sharing the same routing channel (the same space between components) should be grouped into a single corridor rather than interleaved with tracks from other channels. This is a topological constraint: nets originating from the same component cluster should stay together.

Gate: corridor consolidation score ≥ 0.7 (ratio of co-routed track pairs to total track pairs that share a channel). A score of 1.0 means every pair of tracks in the same channel is co-routed.

### R4 — Track-spread

In open board areas with no obstacles, tracks should be evenly distributed with a target spacing rather than clustering on one side or spreading to extremes. This prevents "track spread" where a net that could take a direct path instead wanders across the board.

Gate: track-spread score ≤ 1.5 (ratio of actual max gap to target spacing across the board's routing channels). A score of 1.0 means tracks are at exactly target spacing.

### R5 — AI-slop pattern linter

Define a linter that flags specific degenerate routing artifacts:
- **Hairpin turns:** a track segment that reverses direction within one grid cell
- **Single-net detours:** a net that deviates > 50% from the straight-line path between its endpoints
- **Unnecessary layer switches:** a via that changes layers without crossing an obstacle
- **Isolated vias:** a via with only one connected segment (stub)
- **Zigzag patterns:** three or more consecutive direction changes with no obstacle between them

Gate: linter returns 0 on the routed board.

## Key Decisions

- **45° routing is enabled via 8-directional A*.** The existing A* grid pathfinder supports diagonal moves — it's disabled for speed. Re-enable and measure.
- **Corridor consolidation is a post-route optimization, not a pre-route constraint.** Route first, then consolidate parallel tracks into corridors. This avoids over-constraining the router.
- **The "slop linter" is a post-route check, not a routing constraint.** It doesn't prevent the router from producing slop — it detects it and feeds back into the loop (W5).

## Scope Boundaries

- Curved/arc routing is out of scope — octilinear is sufficient for this board.
- Differential-pair routing quality (W2 R6) is out of scope — this is about general track aesthetics.
- Via tenting, solder mask expansion, and silkscreen are out of scope.

## Dependencies

- **W0 (router build unblock).**
- **W1 (single-layer route).**
- **W2 (4-layer stackup).** Via-count ceiling needs the stackup's via strategy.

## Success Criteria

1. ≥ 70% of track length at 45° or 135°
2. Total signal vias ≤ 100
3. Corridor consolidation score ≥ 0.7
4. Track-spread score ≤ 1.5
5. AI-slop linter returns 0
