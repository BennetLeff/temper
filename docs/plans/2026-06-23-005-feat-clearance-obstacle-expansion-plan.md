---
type: feat
origin: docs/brainstorms/2026-06-23-clearance-obstacle-expansion-requirements.md
status: completed
date: 2026-06-23
---

# Pre-Route HV Clearance Obstacle Expansion — Implementation Plan

## Problem Frame

The deterministic placer achieves only 33% routing completion (8/24 nets); 10 nets are blocked by 6mm IEC 60335-1 creepage clearances around HV power components Q1, Q2, D1, D2. The placer produces HPWL-optimal positions that ignore creepage, and the router discovers HV violations late through reactive policing. C-space obstacle inflation — expanding HV pad geometry by the creepage distance in the obstacle map before routing — eliminates routing-level HV clearance checks by construction. The expanded grid is verifiably conservative: the router cannot enter creepage-violating space because that space is already blocked. This unblocks the 10 stuck nets, leaves placement HPWL unchanged, and removes the need for the router's HV-aware avoidance code.

## Implementation Units

### U1. Per-Layer Creepage Helper and HV-Pad Set Resolution

**Goal.** Compute the per-layer effective creepage distance and identify the HV-pad set once, before grid construction mutates any state. No grid mutation; pure data resolution.

**Requirements.** R1 (HV-pad identification via `hv_exclusion_zones[*].component_refdes`), R2 (layer-aware factor: `6.0mm` outer, `6.0mm * INTERNAL_LAYER_CREEPAGE_FACTOR` inner), R6 (no schema/config mutation).

**Files.**

- `packages/temper-placer/src/temper_placer/deterministic/stages/clearance_grid.py` (new module-level helpers, no behavior change yet)
- `packages/temper-placer/src/temper_placer/routing/constraints/drc_oracle.py` (read `INTERNAL_LAYER_CREEPAGE_FACTOR` constant; no edits)
- `configs/temper_deterministic_config.yaml` (read `hv_exclusion_zones[*].component_refdes` and `clearance_mm`; no edits)

**Approach.** Add two pure functions to `clearance_grid.py`:

1. `effective_creepage(layer: str, base_creepage_mm: float) -> float` — returns `base_creepage_mm` for `F.Cu`/`B.Cu`, else `base_creepage_mm * INTERNAL_LAYER_CREEPAGE_FACTOR`.
2. `hv_pad_set(pads: list[Pad], config: TemperConfig) -> set[PadRef]` — returns the set of pads whose parent component refdes appears in any `hv_exclusion_zones[*].component_refdes`. The function reads the config once, validates every HV refdes resolves to a known component, and raises a clear error otherwise. The set is exposed as a module-level singleton (rebuilt each `clearance_grid` stage run) and reused by U2 and U3.

**Test scenarios.**

- `test_effective_creepage_outer`: input layer=`F.Cu`, base=6.0 → output 6.0.
- `test_effective_creepage_inner`: input layer=`In1.Cu`, base=6.0, factor=0.3 → output 1.8.
- `test_effective_creepage_back_copper`: input layer=`B.Cu`, base=6.0 → output 6.0.
- `test_hv_pad_set_includes_all_pins_of_hv_component`: input pads containing Q1.G, Q1.D, Q1.S, D1.A, D1.K, plus non-HV nets → output contains all 5 HV pads, excludes others.
- `test_hv_pad_set_unknown_refdes_raises`: config lists refdes `Q99` not in pad list → raises `ConfigError` naming the missing refdes.

**Verification.** `pytest tests/deterministic/stages/test_clearance_grid.py -k "creepage or hv_pad" -v` passes; both helpers have 100% line coverage; no grid mutation is observable from these functions (snapshot test on a fixture grid before/after helper import).

### U2. Pre-Route Creepage Expansion Pass

**Goal.** Mutate the `ClearanceGrid` so that every HV pad blocks the Minkowski-sum of its per-layer pad shape with a disc of radius `effective_creepage(layer)`. Non-HV pads keep current blocking. Runs once, in the same stage that constructs the grid (per K4).

**Requirements.** R1 (expansion pass), R3 (geometrically correct inflation, not bbox, per K6), R6 (read-only config access).

**Files.**

- `packages/temper-placer/src/temper_placer/deterministic/stages/clearance_grid.py` (extend `build_clearance_grid` to invoke the pass after the existing per-pad blocking)
- `packages/temper-placer/src/temper_placer/deterministic/stages/clearance_grid.py:165-205` (reuse existing `block_circle` and `block_rect` entry points)

**Approach.** After the existing blocking loop, iterate the HV-pad set from U1. For each (pad, layer) where the pad has a layer-specific shape:

- Circular pad (TO-247, SOT-23): compute `r' = pad.radius + effective_creepage(layer)`, call `block_circle(layer, pad.x, pad.y, r')`.
- Rectangular pad (SOIC, QFN): compute `(x', y', w', h') = (pad.x - eff, pad.y - eff, pad.w + 2*eff, pad.h + 2*eff)`, call `block_rect(layer, x', y', w', h')`.
- Pads with no shape on a given layer are skipped on that layer.

The pass records the set of (pad_ref, layer, blocked_cell_count) tuples it touched, in a module-level `_EXPANSION_LOG` consumed by U3 (the fence) and U4 (the closure test). The log is regenerated on every stage run; it is not persistent state.

**Test scenarios.**

- `test_expansion_circular_pad_grows_radius`: input single circular Q1 pad, layer=F.Cu, base=6.0 → grid blocked at distance `r + 6.0 - 0.5*cell` from pad center, NOT blocked at `r + 6.0 + 0.5*cell` (the boundary is exact, not over-conservative by more than one cell, per R8).
- `test_expansion_rect_pad_grows_each_side`: input single SOIC-8 rect pad → grid blocked at corners offset by `(eff, eff)` from rect bbox, NOT blocked at `(eff - 0.5*cell, eff - 0.5*cell)`.
- `test_expansion_inner_layer_uses_reduced_factor`: input same circular pad on `In1.Cu` → blocked radius is `r + 1.8`, not `r + 6.0`.
- `test_expansion_skips_non_hv_pads`: input mixed HV/LV pad set → only HV-pad cells change relative to pre-pass snapshot.
- `test_expansion_runs_once_per_stage`: call `build_clearance_grid` twice on same input → `_EXPANSION_LOG` length matches pad count (not double).

**Verification.** `pytest tests/deterministic/stages/test_clearance_grid.py -k expansion -v` passes; on the determinism fixture, snapshot diff of `ClearanceGrid.cells` shows expansion only in HV-pad annuli; `_EXPANSION_LOG` length equals HV-pad count.

### U3. Grid Validity Fence — `clearance_grid_conservatism`

**Goal.** Add a per-stage DRC fence check that asserts the expanded grid is conservative: for every (pad, layer), the cells at radius `pad_radius + effective_creepage` from the pad boundary are blocked. Follows the existing per-stage fence pattern (K3).

**Requirements.** R4 (fence check, performance budget <20% of grid-build wall time; emits warning (not violation) on overrun to avoid CI flakes).

**Files.**

- `packages/temper-placer/src/temper_placer/deterministic/stages/clearance_grid.py` (new `check_clearance_grid_conservatism(grid, expansion_log, config) -> FenceResult` function)
- `tests/deterministic/stages/test_clearance_grid.py` (fence test)
- `docs/solutions/architecture-patterns/per-stage-drc-fence-verification-2026-06-22.md` (reference only; no edits)

**Approach.** Reuse the existing `FenceResult` and per-stage fence pattern (per `docs/solutions/architecture-patterns/`). The new check:

1. Iterate `_EXPANSION_LOG` from U2.
2. For each (pad_ref, layer) sample 16 points on a circle of radius `pad_radius + effective_creepage` (circular) or 4 corners plus 4 edge midpoints offset by `effective_creepage` (rect).
3. Convert each sample to grid cell coordinates; assert the cell is blocked.
4. On any miss, return a `FenceResult(violations=[(pad_ref, layer, xy, expected_radius)])` and emit a stage-attributed diagnostic.
5. Wrap in a wall-time timer; assert elapsed < 20% of the grid-build stage's elapsed time. Emit a warning (not a violation) if the budget is exceeded, to keep fence from flaking on slow CI.

**Test scenarios.**

- `test_fence_passes_on_correct_expansion`: build grid with U2 enabled → fence returns 0 violations.
- `test_fence_detects_missing_block_on_circle`: hand-craft a grid where one of the 16 samples is unblocked → fence returns 1 violation naming the pad and coordinate.
- `test_fence_detects_missing_block_on_rect_corner`: hand-craft a grid where one rect corner sample is unblocked → fence returns 1 violation.
- `test_fence_detects_missing_block_on_rect_edge`: hand-craft a grid where one edge midpoint is unblocked while corners are blocked → fence returns 1 violation naming the pad and edge midpoint coordinate.
- `test_fence_warns_on_budget_overrun`: instrument a slow fence (sleep) → emits a Warning, not a FenceViolation.
- `test_fence_pipeline_halts_on_violation`: integration test — fence wired into the stage DAG halts subsequent stages with a `FenceViolation` exception that names the offending pad_ref.

**Verification.** `pytest tests/deterministic/stages/test_clearance_grid.py -k fence -v` passes; on the determinism fixture, average fence wall time over 10 runs is <20% of average grid-build wall time over 10 runs (recorded in the test, not asserted as a hard gate — assert budget only in CI gate if a budget sentinel is added per the existing fence pattern).

### U4a. Closure Validation with Router HV Code Present

**Goal.** Confirm the previously-stuck 10 HV nets now route to 100% completion, zero new DRC violations, and placement HPWL is unchanged, with the router's HV-aware avoidance code **still present**. This validates the expansion is the system under test; the router code is unchanged so any closure regression points unambiguously at U1–U3.

**Requirements.** R7 (closure test 24/24 with router HV code present), R8 (regression test asserts completion, no new violations, HPWL unchanged).

**Files.**

- `tests/test_closure.py` (verify exact path; assert completion == 24, zero new DRC violations measured against pre-expansion baseline)
- `packages/temper-placer/tests/` (new regression test `test_clearance_expansion_regression.py` asserting the 10 stuck nets route)

**Approach.** Run the full closure test on a build with U1–U3 merged and the router's HV-aware code **still present**. Record per-net routing outcomes; assert exactly the 10 previously-stuck HV nets now route. If this fails, halt and debug — the expansion is the system under test, not the router.

**Test scenarios.**

- `test_closure_completes_24_of_24`: full closure test pipeline → completion metric == 24, failed_nets == [].
- `test_closure_hv_nets_route`: explicitly assert the 10 nets previously failing now succeed (named list of net IDs from a fixture file).
- `test_closure_no_new_drc_violations`: DRC violation count delta vs. pre-expansion baseline == 0.
- `test_placement_hpwl_unchanged`: placement HPWL output within 0.1% of pre-expansion run on the determinism case (acceptance criterion).

**Verification.** Closure test passes (24/24); regression test passes; HPWL delta < 0.1%; DRC violation delta == 0. Router HV code is **not** touched in U4a.

### U4b. Router HV-Code Removal (R5) — Deferred

**Goal.** Remove the router's HV-aware avoidance code as the load-bearing payoff of the expansion. Ships as a separate PR gated on U4a passing 100% (R7).

**Requirements.** R5 (router drops HV-specific logic), R8 (post-removal DRC-delta assertion).

**Files.**

- `packages/temper-placer/src/temper_placer/deterministic/stages/sequential_routing.py` (remove HV-aware avoidance)
- `packages/temper-placer/tests/` (post-removal DRC-delta regression test)

**Approach.** Edit `sequential_routing.py` to remove HV-specific avoidance. Re-run closure test; assert 24/24 completion. The acceptance criterion `grep -E "(creepage|hv_aware|hv_clearance)" sequential_routing.py` returns zero matches.

**Test scenarios.**

- `test_router_no_creepage_references`: assertion that `sequential_routing.py` contains no `creepage`/`hv_aware`/`hv_clearance` token post-removal.
- `test_closure_no_new_drc_violations_post_removal`: DRC violation count delta vs. pre-expansion baseline == 0 after removal (the same assertion as U4a, re-asserted to catch removal-introduced regressions).

**Verification.** Closure test passes (24/24) post-removal; DRC violation delta == 0 post-removal; `grep` returns zero matches. See "Deferred to Follow-Up Work" below.

## Pre-Implementation Checklist

The following must be verified **before** U2 and U3 implementation begins. The results are recorded inline in this plan's Files section as they are discovered.

- **OQ1: Rotated-pad support in `block_rect`.** Read `clearance_grid.py:165-205` (the existing `block_rect` and `block_circle` entry points) and the surrounding pad-shape data model. Record the answer to: does the codebase carry any non-axis-aligned rect pads (e.g., QFN thermal pads at angles) in the current fixture set? If yes, U2 must route those pads through a `block_polygon` helper (deferred — see "Deferred to Follow-Up Work") and cannot ship relying on axis-aligned `block_rect` alone. If no, U2's axis-aligned approach is sufficient and the deferred rotated-pad test is the only outstanding gap.
- **U3 prerequisite: locate the per-stage fence framework.** Grep for `FenceResult` and `drc_fence` across `packages/temper-placer/src/temper_placer/deterministic/stages/` to identify the host file and the call site where the existing per-stage fence is registered. Record the host file path in U3's "Files" section (replacing the hedged entry) and the call-site line number here before U3 implementation begins. If the wiring is non-trivial (e.g., the fence framework requires a specific stage-context argument shape, or registration differs per stage), split U3 into "U3a. Fence helper (pure, in `clearance_grid.py`)" and "U3b. Fence wiring into the stage DAG (in `<host_file>`)" before implementation; record the split explicitly in this plan.

## Risks & Dependencies

- **OQ2 unresolved in this PR.** Internal-layer reduction is unconditional, matching `drc_oracle.py:71`. If a future ticket requires plane-conditional reduction, U1 and U2 both expose the per-layer factor and can be retargeted without structural change.
- **OQ3 unresolved.** Isolation slots (Idea #7) are not consumed by the expansion. Slots in the expanded annulus may be over-blocked. Out of scope here; tracked as a follow-up. The fence will surface any over-blocking that breaks closure.
- **OQ4 falsifiable.** If expansion makes a currently-routable net unroutable, the closure test will fail and the fence will name the pad. Recovery: tighten the expansion to use `effective_creepage - 0.5 * cell` as a one-cell shrink to reclaim a boundary band — but this is a fallback only if the primary test surfaces the issue.
- **Fence performance budget on large boards.** The 16-points-per-pad sampling is constant work per pad. Total cost is `O(num_hv_pads * num_layers)`, not grid-size. The 20% budget is a soft warning, not a hard gate, to avoid CI flakes.
- **Removal is a separate PR (U4a → U4b).** R5 is gated on R7 because removing router HV code while the expansion is wrong would mask the bug. U4a validates closure with the router HV code still present; U4b performs the removal. Do not combine U4a and U4b.

## Scope Boundaries

### Deferred to Follow-Up Work

- **U2 rotated-pad regression test: assert rotated-pad inflation via `block_polygon` (`test_expansion_no_bbox_approximation`).** Ships with the follow-up `block_polygon` helper. U2 in this PR covers only axis-aligned rect pads; verifying the rotated-pad path requires the deferred helper.
- **U4b. Router HV-code removal (R5).** Ships as a separate PR gated on U4a passing 100% in the build where U1–U3 are merged but the router code is still present. U4b's `test_router_no_creepage_references` and `test_closure_no_new_drc_violations_post_removal` live in that follow-up PR.
- **Isolation slot interaction (OQ3).** Idea #7 from the ideation doc. Subtract slot geometry from the expanded blocking region. Tracked separately.
- **Plane-conditional creepage factor (OQ2).** Today the factor is unconditional. Future change to make it plane-conditional would retarget U1's `effective_creepage` helper.
- **Rotated-pad polygon inflation.** If `block_rect` cannot represent rotated pads, add a `block_polygon` helper and route rotated pads through it. Verification: read `clearance_grid.py:165-205` first (OQ1 in the Pre-Implementation Checklist).

### Out of Scope

- Placement-side creepage awareness (Ideas #1–#4 in the ideation doc). K5 forbids it here.
- DRC oracle changes. Oracle stays the final authority; the fence is the stronger upstream check (per brainstorm).
- Bbox-based inflation shortcuts (K6).
- Redesign of `ClearanceGrid` data structure.
- New pipeline stages or new fence framework work — reuses the existing per-stage fence.
- New fields in `hv_exclusion_zones` or new top-level config keys (R6).
