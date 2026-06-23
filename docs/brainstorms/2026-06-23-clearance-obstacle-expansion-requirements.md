---
date: 2026-06-23
topic: clearance-obstacle-expansion
focus: Pre-route expansion of HV pad geometries by creepage distance in the obstacle map, eliminating routing-level HV clearance checks by construction
origin: docs/ideation/2026-06-23-hv-clearance-placement-completion-ideation.md (Idea #5)
status: active
actors: clearance grid builder, sequential router, DRC fence, temper-drc
---

# Requirements: Pre-Route HV Clearance Obstacle Expansion

## Problem Frame

The deterministic placer achieves only 33% routing completion (8 of 24 nets). Ten nets are blocked by 6mm IEC 60335-1 creepage clearances around HV power components Q1, Q2, D1, D2. The placer produces HPWL-optimal positions that ignore creepage; the router discovers HV violations late and either fails or routes around them by trial. The result is wasted router compute and a hard completion ceiling.

HV clearance is currently enforced twice: once at routing time (router refuses to enter creepage-violating cells) and once at endpoint DRC. Both modes are reactive — the model handed to the router is not creepage-safe, so the router has to police itself.

The fix is to push the clearance into the obstacle model itself before routing begins. C-space obstacle inflation is a proven motion-planning technique: expand every obstacle by the agent radius to obtain a configuration space where the agent (a trace) is treated as a point. Here, the obstacles are HV pads, and the agent radius is the 6mm creepage distance. The resulting expanded obstacle map is verifiably conservative: the router cannot route into space that would violate creepage, because that space is already marked blocked.

This is a load-bearing prerequisite for "Zero routing-level HV clearance checks needed" (see K1). It is not a placement change and does not alter the placer's HPWL objective.

## Actors

- **A1. Clearance grid builder** — the code that constructs `ClearanceGrid` for the router. Today it calls `block_circle` and `block_rect` per pad with the pad's physical radius but no creepage margin.
- **A2. Sequential router** — consumes the grid and runs maze routing. Today it carries its own HV-aware logic to avoid creepage cells.
- **A3. DRC fence** — runs after each pipeline stage, attests output invariants, must verify the expanded grid is conservative within <20% wall-time overhead.
- **A4. Pipeline operator** — runs the closure test, expects 100% completion on the previously-stuck 10 nets without introducing new DRC violations.

## Key Decisions

- **K1. C-space inflation, not runtime policing.** Expand pad geometry in the obstacle map by the full creepage distance. The router then operates on a verifiably conservative model and can drop all HV-specific routing logic. Failure becomes impossible-by-construction rather than detected-after-the-fact.
- **K2. Single source of truth for creepage distance.** Reuse `INTERNAL_LAYER_CREEPAGE_FACTOR` semantics by computing effective creepage per layer: `effective = base_creepage * INTERNAL_LAYER_CREEPAGE_FACTOR` on inner layers (In1.Cu, In2.Cu), `base_creepage` on outer layers. `base_creepage` reads from `hv_exclusion_zones[*].clearance_mm` in the config (currently 6.0mm) — no new constants.
- **K3. DRC fence verifies the expansion.** A new check (`clearance_grid_conservatism`) samples N points around each HV pad and asserts that the grid blocks them to the declared creepage radius. The fence is the verifier; the expansion is the system under test. Pattern follows `docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md`.
- **K4. Expansion runs once, before the router's first stage.** Not incrementally per net. The cost is bounded by pad count, not net count, and amortized across all routed nets.
- **K5. No change to placement objective.** The placer is not told about creepage. This is a routing-input fix, not a placement fix. (Placement-side fixes are Ideas #1–#4 in the ideation doc and out of scope here.)
- **K6. Pad radius, not bounding box.** Round pads inflate by the Minkowski sum with a disc of radius `effective_creepage`; rect pads inflate by a uniform offset of `effective_creepage` on each side. Do not approximate by bbox-inflation, which over-blocks channels and reclaims the wrong channel capacity.
- **K7. Per-layer expansion.** Internal layers get the reduced factor; outer layers get the full distance. The grid builder must apply the right factor per layer when calling `block_circle` / `block_rect`.

## Requirements

### R1. Pre-Route Creepage Expansion Pass
Status: required

Before the sequential router consumes the `ClearanceGrid`, a new pass walks every HV pad in the placement and re-blocks its cells with the pad radius inflated by the layer-appropriate effective creepage. Non-HV pads are left at their current blocking radius. The pass runs in the same stage that constructs the grid (currently `clearance_grid.py`), no new pipeline stage.

**HV-pad identification.** A pad is considered HV iff its parent component refdes appears in `hv_exclusion_zones[*].component_refdes` (e.g., Q1, Q2, D1, D2). All pads of an HV component receive the expansion, including signal/control pins (e.g., Q1 gate). The HV-pad set is computed once at pass entry and reused for the fence and the router handoff.

### R2. Layer-Aware Creepage Factor
Status: required

The expansion factor is `6.0mm` on outer layers (F.Cu, B.Cu) and `6.0mm * INTERNAL_LAYER_CREEPAGE_FACTOR` (= 1.8mm) on inner layers (In1.Cu, In2.Cu), read from `configs/temper_deterministic_config.yaml:451-468` `hv_exclusion_zones[*].clearance_mm` and `packages/temper-placer/src/temper_placer/routing/constraints/drc_oracle.py:71` respectively. A single helper computes the per-layer effective distance; both config and constant are read once at pass entry.

### R3. Geometrically Correct Inflation
Status: required

- For each layer the pad exists on, expand the layer-specific pad geometry (as exported by the KiCad parser for that layer, not a single per-pad shape) by that layer's `effective_creepage`. Pads present on only one layer (SMD) are expanded on that layer only.
- Circular pads (TO-247, SOT-23): expand radius by `effective_creepage`, recurse to `block_circle` with the summed radius.
- Rectangular pads (SOIC, QFN): expand each side of the rect by `effective_creepage`, recurse to `block_rect` with the grown rect.
- The pass must not approximate by axis-aligned bounding box. The inflation must be the exact Minkowski sum.

### R4. Grid Validity Fence
Status: required

Add a `clearance_grid_conservatism` check that runs after the grid is built and before the router begins. For each (pad, layer) pair, sample the layer-specific `pad_radius + effective_creepage` boundary and assert blocked on that layer's grid. For circular pads, sample at least 16 points on a circle of that radius; for rect pads, sample 4 corners offset by `effective_creepage`. Any miss is a fence violation, the pipeline halts with a stage-attributed diagnostic naming the pad and missed coordinate. Performance budget: <20% of grid-build wall time, following the fence pattern.

### R5. Router Drops HV-Specific Logic
Status: required

Once R1–R4 land and the closure test passes with 100% completion on the stuck 10 nets, remove the router's HV-aware avoidance code. The expanded grid is sufficient. This is the load-bearing payoff: routing becomes creepage-agnostic. Removal is a follow-up PR gated on the closure test.

### R6. Config and Config Schema Untouched
Status: required

The expansion reads existing config. No new fields in `hv_exclusion_zones`. No new top-level keys. Operators do not need to reconfigure.

### R7. Closure Test Passes 100%
Status: required

The existing closure test (`tests/test_closure.py` or equivalent — verify exact path) must show 100% routing completion (24/24 nets) and zero new DRC violations attributable to the expansion. The previously-stuck 10 nets must route without manual intervention.

### R8. Test Coverage
Status: required

- Unit test: for each pad shape (circle, rect) and each layer (outer, inner), assert grid blocking at radius `pad_radius + effective_creepage ± 0.5 cell`.
- Unit test: assert grid NOT over-blocked at radius `pad_radius + effective_creepage - 0.5 cell` (the boundary is exact, not conservative by more than one cell).
- Fence test: assert `clearance_grid_conservatism` reports the offending pad and coordinate on a synthetic grid missing one sample.
- Regression test: closure test rerun, assert completion = 24/24 (100%); the previously-stuck 10 HV nets must all route.

## Acceptance Criteria

- Closure test routes all 24 nets (vs 8 today (33% baseline)).
- Zero DRC violations introduced.
- `clearance_grid_conservatism` fence check passes on every build.
- Router's HV-aware code paths are removed — `grep -E "(creepage|hv_aware|hv_clearance)" packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py` returns zero matches after R5.
- Placement HPWL output equals the pre-change run within 0.1% (|new - old| / old), measured on the determinism case.
- Fence wall time, averaged over 10 runs on the determinism case, is <20% of the average of 10 runs of the grid-build pass that includes the expansion; both measured with the same timer under the same process conditions.

## Out of Scope

- Placement-side creepage awareness (covered by Ideas #1–#4 in the ideation doc).
- Creepage-aware scoring during placement optimization.
- Per-net creepage negotiation or backtracking.
- DRC oracle changes (the oracle stays as the final authority; the fence is a stronger upstream check).
- Bbox-based inflation shortcuts.
- Redesign of the `ClearanceGrid` data structure.
- New pipeline stages or new fence framework work — this reuses the existing per-stage fence.

## Open Questions

- **OQ1 resolved: expansion is ≤80 lines and stays in clearance_grid.py per R1; no new module.**
- **OQ2. Should internal-layer reduction apply to ALL HV pads, or only those covered by a ground plane?** Today the factor is unconditional in `drc_oracle.py:71`; the expansion pass should match that behavior. If we want plane-conditional reduction, that is a separate change.
- **OQ3. How does this interact with isolation slots (Idea #7)?** Slots reclaim creepage by physical cutout. The expansion may over-block in slot regions. Likely follow-up: subtract slot geometry from the expanded blocking region. Not in this PR.
- **OQ4. Does the expansion make any currently-routable net unroutable?** Hypothesis: no, because the expansion only adds blocking to cells the router is forbidden from entering anyway. Closure test will confirm. If a regression appears, the fence will name the offending pad.

## See Also

- Ideation: `docs/ideation/2026-06-23-hv-clearance-placement-completion-ideation.md` (Idea #5, axis: HV footprint inflation)
- Fence pattern: `docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md`
- Grid construction: `packages/temper-placer/src/temper_placer/deterministic/stages/clearance_grid.py` (block_circle, block_rect at lines 165–205)
- Router grid consumer: `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py`
- Internal-layer factor: `packages/temper-placer/src/temper_placer/routing/constraints/drc_oracle.py:71`
- HV exclusion zones: `configs/temper_deterministic_config.yaml:451–468`
- Sibling ideas in ideation: #2 Ghost-Pad Injection (placement-side inflation), #7 Consume Isolation Slots (slot geometry interaction)
