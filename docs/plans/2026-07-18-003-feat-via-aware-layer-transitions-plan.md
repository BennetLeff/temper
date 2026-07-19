---
title: "feat: Via-Aware Layer Transitions (Issue #226)"
type: feat
status: active
date: 2026-07-18
origin: docs/brainstorms/2026-07-18-via-aware-layer-transitions-requirements.md
---

# Via-Aware Layer Transitions (Issue #226)

## Summary

Reconnect and complete the five-point disconnected via-insertion chain the
origin brainstorm identified: populate real via positions from actual layer
transitions, fix a hardcoded via layer-span bug, add per-net-class via
legality/sizing, emit real `(via ...)` KiCad output, then — only once all of
that is proven not to regress connectivity — re-land the segment-layer write
and relax the completion-preserving SSOT gate. Fresh git archaeology
(below) found the disconnected `_astar_search_3d` 3D via-aware search is not
abandoned/broken work, but it is also not a low-risk drop-in swap: the
production 2D-stitched router has accumulated substantial route-quality
machinery (Theta*/Lazy Theta*, Numba-JIT line-of-sight, coarse-to-fine,
congestion-tensor and thermal-weighted cost) that the older 3D search
entirely lacks. This plan recommends using the 3D search as an additional
**fallback tier** on hard-to-route segments — not a primary-router
replacement — validated by an empirical spike (U1) before the recommendation
is locked in.

---

## Requirements

Traces to the origin (`docs/brainstorms/2026-07-18-via-aware-layer-transitions-requirements.md`).

- R1 — Populate real via positions from actual layer transitions (not a
  hardcoded `[]`).
- R2 — Fix the hardcoded via layer-span (`from_layer="F.Cu"` /
  `to_layer="B.Cu"` regardless of actual transition layers).
- R3 — Via placement legality against the occupancy grid, with per-netclass
  `via_diameter`/clearance from `netclass_rules.yaml` (not hardcoded
  defaults).
- R4 — Emit real `(via ...)` KiCad output, reading `compiled_route.vias`.
- R5 — Re-land the segment-layer write (previously reverted in `903dfaef`),
  sequenced strictly after R1-R4 are proven.
- R6 — Relax the `ssot == heuristic` completion-preserving no-op gate,
  sequenced after R5 is proven, gated on an explicit before/after
  `kicad-cli pcb drc` comparison.
- R7 — Anti-false-zero discipline throughout: every connectivity/routing
  claim is checked against real `kicad-cli pcb drc` `unconnected_items` and
  violation-class deltas, on both the corpus board and
  `pcb/temper.kicad_pcb`, never inferred from "A* found a path."

---

## Scope Boundaries

- 4-layer (In1.Cu/In2.Cu) via transitions — the production board is
  currently 2-layer; this plan's fixes are layer-span-correct for whatever
  layers are actually in play, but testing against inner layers is deferred
  until the board itself uses them.
- `shorting_items` and `diff_pair_gap_out_of_range` violation classes — per
  the routing-completion plan, these likely need individual diagnosis
  separate from via/layer-crowding work.
- The board-capacity/BOM decision, power-plane pours (W2 U4), and
  `EscapeVia`/pin-escape via generation (Stage 1.3) — independent, untouched
  threads, per the origin brainstorm's Scope Boundaries.
- Porting Theta*/coarse-to-fine/congestion-tensor/thermal-weighted cost
  *into* `_astar_search_3d` itself — this plan's recommended approach avoids
  needing that port by using the 3D search only as a fallback tier, not a
  primary-router replacement. If U1's spike shows the fallback tier is
  inadequate, porting these features into the 3D search would be a much
  larger follow-up, explicitly out of this plan's scope.

---

## Context & Research

### Fresh git archaeology on `_astar_search_3d` (resolves brainstorm Open Question 2)

The brainstorm asked planning to determine why the 3D via-aware search was
built but never wired to production. Traced via `git log --all -S` across
renames:

- **Original commit: `c2027834` (2026-01-12), "implement production-grade 3D
  A* routing with explicit via insertion."** The commit message is
  unambiguous about intent and claimed results: *"Piantor benchmark: 24/24
  (100%) routing, 19 vias placed... Production ready for Temper board
  (4-layer, SMD-heavy)."* This was not a prototype or experiment — it was
  built and claimed working on a real board (Piantor) at the time. This
  claim was **not** re-verified in this investigation (no current-code
  benchmark was run) and predates months of subsequent router changes; it is
  evidence the design is sound, not evidence it works today.
- **Apparent removal 5 days later (`3314d94a`, 2026-01-17, "Major Cleanup:
  JAX Removal, Legacy Purge, and Structural Flattening")** — `git log -S`
  shows the function definition disappearing from `astar_pathfinding.py`'s
  history at this commit. This is very likely **path-tracking noise**, not
  deliberate deletion: this commit did a monorepo-wide `src/` directory
  flattening and file reorganization, and `git log -S <path>` restricted to
  one file path will show a function as "removed" if the file moved. No
  commit message anywhere in the trace claims the 3D search was found
  broken, too slow, or wrong. **This is genuinely inconclusive** — treat it
  as such, not as confirmed evidence either way.
- The function reappears June 22 (`b7245f65`, a profiling-toolkit branch
  merge) and is then mechanically relocated into `astar_core.py` by the
  `4b037d11` U2 decomposition (same day) and de-duplicated by `ec104b32`
  (2026-06-23) — all mechanical file-organization commits, none touching the
  algorithm.
- **No commit anywhere in the traced history explains a deliberate decision
  to not wire `_astar_search_3d` into production dispatch.** The most
  plausible reading, consistent with the single-layer-first brainstorm
  (`docs/brainstorms/2026-07-08-single-layer-route-requirements.md`, six
  months after the 3D search was built) explicitly deferring "via
  optimization" to a named future workstream ("W4") while routing on F.Cu
  only for the first proof-of-concept: **the 3D search was simply never on
  the critical path during single-layer-first sequencing**, not rejected on
  technical grounds. This is the most likely explanation but is not proven
  by direct evidence.

### The finding that changes the risk picture (not covered by the brainstorm)

The brainstorm's Option B framing ("wire in the existing, tested 3D search")
under-weighted one thing: **the production 2D-stitched router
(`_astar_route_multilayer`) has grown substantial route-quality machinery
that `_astar_search_3d`/`_route_segment_3d` entirely lacks.**
`_astar_route_multilayer`'s current signature carries: `use_theta_star`,
`use_lazy_theta_star`, `congestion_tensor`, `enable_numba_los`,
`enable_coarse_to_fine`, `coarse_factor`, `corridor_buffer_cells`,
`enable_congestion_derivative`, `thermal_flat`, `thermal_weight` — none of
which exist on `_astar_search_3d`'s much simpler signature (`start, goal,
grids, via_cost, via_diameter, clearance, net_id`, plain A* with no
line-of-sight shortcutting, no coarse-to-fine, no congestion/thermal
awareness). These features were built up over many sessions (see
`docs/plans/2026-06-28-*-plan.md` series: Theta*/Lazy Theta*, Numba JIT LOS,
coarse-to-fine corridor routing, congestion tensor, thermal anchoring) and
represent real, hard-won route-quality investment.

**Consequence:** naively replacing `_astar_route_multilayer`'s primary
dispatch with `_route_segment_3d` (a literal reading of "Option B") would
regress route quality/performance for every net, not just the ones needing
layer transitions — trading a solved problem (production route quality) for
an unsolved one. This plan does not recommend that.

**Recommended shape instead — a genuine fourth option, blending the
brainstorm's A and B:** extend the *existing* fallback pattern
`_astar_route_multilayer` already uses (`if not segment_path and
alternate_grid and tht_locations: try alternate_grid`) with one more tier —
when both the primary and THT-gated alternate-grid attempts fail for a
segment, try `_route_segment_3d` as a last resort, on the (typically much
smaller) set of genuinely hard-to-route segments only. This:

- Keeps all of production's route-quality machinery intact for the common
  case (most segments never reach the fallback tier).
- Uses `_astar_search_3d`'s already-correct via detection
  (`prev_layer != cl` transition detection) and legality mechanism
  (`mark_via_blocked()`, already blocking real via positions on all spanned
  layers) exactly as built — no new via-detection algorithm needed.
- Bounds the "found a path, quality unverified" risk to a smaller,
  identifiable segment population, rather than the whole board.
- Is not free: still needs empirical validation (U1) that the fallback tier
  performs acceptably (wall time, via legality, DRC connectivity) at
  production scale, since `_astar_search_3d`'s only existing tests
  (`test_astar_metamorphic_pbt.py::test_3d_path_cells_free`,
  `test_3d_no_redundant_same_layer_nodes`) run on small synthetic grids, not
  a 95-net/149-component board.

### Rough complexity argument for U1's spike

`_astar_search_3d`'s per-node branching factor is `8 same-layer neighbors +
(len(available_layers) - 1) via-transition moves` — for the current 2-layer
production board, that's 9 vs. the 2D search's 8; for a future 4-layer
board, 11 vs. 8. This is a modest, linear-in-layer-count increase, not
combinatorial blowup — the state space grows by a small constant factor
(`len(layers)`), not exponentially. This is a reason for cautious optimism
about wall time at the fallback tier's expected (small) invocation count,
but it is an argument, not a measurement — U1 exists to replace this
argument with a real number.

### Relevant Code and Patterns

- `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py` —
  `_astar_route_multilayer()` (line 818, production dispatch, hardcodes
  `via_positions=[]`/`via_count=0`), `_route_net_with_ripup` (confirmed
  caller of `_astar_route_multilayer`, not `_route_segment_3d`).
- `packages/temper-placer/src/temper_placer/router_v6/astar_core.py` —
  `RouteNode3D`, `RoutePath3D`, `_astar_search_3d()` (line 629),
  `_route_segment_3d()` (line 771) — the existing, tested 3D search; via
  detection at `if prev_layer is not None and prev_layer != cl:
  vias.append((cx, cy))`; legality via `grid.mark_via_blocked(...)` on every
  spanned layer.
- `packages/temper-placer/src/temper_placer/router_v6/via_placement.py` —
  `_place_vias_for_path()`: the `RoutePath3D`/`via_positions` branch (lines
  104-116) hardcodes `from_layer="F.Cu"`/`to_layer="B.Cu"` (R2's bug); the
  separate legacy-`RoutePath` fallback branch (lines 118-139) already
  computes real layers via `_get_adjacent_layer()` and is unaffected — do
  not conflate the two branches when fixing R2.
- `packages/temper-placer/src/temper_placer/router_v6/routing_results.py` —
  `CompiledRoute.vias`, `compile_routing_results()` — data already reaches
  here; nothing downstream reads it (R4's gap).
- `packages/temper-placer/src/temper_placer/router_v6/adapter.py` —
  `_write_routes_to_content()`: computes `path_layer` per segment but writes
  literal `(layer "F.Cu")` (lines ~630, ~652, the `903dfaef` revert); never
  reads `compiled_route.vias`.
- `packages/temper-placer/src/temper_placer/router_v6/channel_mapping.py` —
  `_assign_layer()` (line 79), the `if ssot is not None and ssot ==
  heuristic: return ssot` no-op gate (line 115, R6's target).
- `packages/temper-placer/src/temper_placer/router_v6/occupancy_grid.py` —
  `OccupancyGrid`, `mark_via_blocked()`, `world_to_grid()`/`grid_to_world()`
  — the primitive both the existing 3D search and any new legality checking
  should reuse; no separate spatial-index module exists or is needed (R3
  can build directly on this).
- `packages/temper-placer/configs/netclass_rules.yaml` — per-class
  `via_diameter`/`via_drill` SSOT data (e.g. HV: 1.2/0.6mm; FinePitch:
  0.4/0.2mm) — must feed both the via-legality check (R3) and the writer's
  emitted `(size ...)`/`(drill ...)` (R4), replacing
  `_astar_search_3d`'s hardcoded `via_diameter=0.6, clearance=0.2` defaults
  and `via_placement.py`'s single board-wide
  `pcb.design_rules.default_via_diameter_mm`.

### Institutional Learnings

- `docs/solutions/workflow-issues/2026-07-18-plan-execution-and-ci-rot-excavation.md` —
  the PR #220 completion-regression saga this plan exists to fix properly:
  two false subagent claims, the accidentally-load-bearing F.Cu hardcode,
  the byte-identical revert. The core lesson (a route that "found a path"
  was trusted before its DRC connectivity was verified) is this plan's R7.
- `docs/plans/2026-07-18-002-feat-board-routing-completion-plan.md` — U7's
  audit first surfaced the two-mechanism question this plan's git
  archaeology resolves more precisely.
- `docs/brainstorms/2026-07-08-single-layer-route-requirements.md` — the
  deliberate single-layer-first sequencing that plausibly explains why the
  3D search was never wired (named "via optimization... out of scope (W4)").

---

## Key Technical Decisions

- **The 3D search is a fallback tier, not a primary-router replacement.**
  The route-quality feature gap (Theta*, coarse-to-fine, congestion/thermal
  awareness) makes a full swap a regression, not an upgrade. This
  supersedes the brainstorm's literal Option B framing with a more precise
  Option D-style blend, justified by evidence the brainstorm didn't have
  (the signature/feature comparison above).
- **U1 is an empirical spike, not a rubber-stamp.** The complexity argument
  above is reassuring but not a substitute for measurement — `via_cost`
  tuning, real production-board grid dimensions, and actual obstacle
  density all affect real wall time in ways a branching-factor argument
  can't fully predict. If U1's measurement contradicts the recommendation
  (unacceptable wall time, poor via legality, or DRC regressions even at
  fallback-tier scale), the plan's later units adapt — U2 onward assume U1
  passes, but are not committed to blindly if it doesn't.
  U1's own Verification section states the contingency explicitly.
- **R5 (real segment-layer write) is sequenced strictly after R1-R4, never
  alongside.** This is the exact ordering mistake that caused PR #220's
  8-unconnected-items regression — output must not diverge from `main`
  until via insertion can back it up.
- **R6 (relax the completion-preserving gate) requires an explicit,
  CI-runnable before/after DRC comparison**, not implementer judgment — see
  U8's Verification for the precise gate (resolves brainstorm Open
  Question 4).
- **Per-netclass via sizing (`netclass_rules.yaml`) replaces every hardcoded
  via dimension** encountered in this plan — `_astar_search_3d`'s
  `via_diameter=0.6, clearance=0.2` defaults and
  `via_placement.py`'s board-wide `default_via_diameter_mm` are both legacy
  shortcuts this plan corrects via R3/R4.

---

## Open Questions (Deferred to Implementation)

- **Exact `via_cost` tuning for the fallback tier.** `_astar_search_3d`
  defaults to `via_cost=10.0` (from the original 2026-01-12 commit,
  unchanged since). Whether this is well-tuned for the production board's
  actual grid resolution and net mix is unverified — U1's spike should
  record whether route quality (via count, total via + track cost) looks
  reasonable, not just "did it complete."
- **Grid dict reshaping mechanics.** `_route_segment_3d` expects `grids:
  dict[str, OccupancyGrid]` (all available layers); `_astar_route_multilayer`
  currently carries `primary_grid`/`alternate_grid` as two named
  parameters. U1/U2's implementer should confirm whether the two-grid
  shape can be trivially wrapped into a dict at the fallback call site
  (`{primary_layer_name: primary_grid, alternate_layer_name: alternate_grid}`)
  without needing to thread a full multi-layer grid dict further up the
  call chain — this looks mechanical from the signatures but wasn't traced
  end-to-end in this planning pass.
- **Whether `_astar_search_3d`'s Piantor claim (24/24, 19 vias) still holds
  today.** Not re-run in this planning pass; if U1's spike is convenient to
  extend to a Piantor re-run, that would independently corroborate (or
  correct) a 6-month-old, unverified commit-message claim — worthwhile but
  not required for this plan's own success criteria (which target the
  corpus and production boards, not Piantor).

---

## Implementation Units

### U1. Empirical validation spike — production-scale wall time and via legality for `_astar_search_3d`/`_route_segment_3d`

**Goal:** Replace the brainstorm's and this plan's complexity arguments with
real measurement: run the existing, unmodified `_route_segment_3d` against
production-scale grids (corpus board first, then `pcb/temper.kicad_pcb`) and
record wall time, via count/positions, and via-legality correctness. Confirm
or correct this plan's "fallback tier" recommendation before U2 commits to
it.

**Requirements:** R1 (informs the mechanism), supports R7 (anti-false-zero
discipline applied to the spike itself — no "seems fine" without numbers)

**Dependencies:** None

**Files:**
- Test/script: `packages/temper-placer/tests/router_v6/test_astar_3d_production_scale_spike.py`
  (new — a measurement harness, not a permanent regression test; may be
  marked `@pytest.mark.slow` and kept, or converted to a one-off script and
  its results recorded in this plan's Evidence via a follow-up doc update,
  implementer's call)

**Approach:**
- Build (or reuse, if `OccupancyGridStage` output is accessible in test
  fixtures) real production-scale occupancy grids for both the corpus board
  and `pcb/temper.kicad_pcb`.
- Call `_route_segment_3d` directly (bypassing `_astar_route_multilayer`
  entirely — this unit tests the search in isolation, not yet integrated)
  for a representative sample of segments, including some deliberately
  chosen to require a layer transition (e.g. force `start_layer != goal_layer`).
- Record: wall time per call, whether a path was found, via count and
  positions, and whether `mark_via_blocked()` correctly prevents a
  subsequent call from routing through the same via position.
- Compare recorded via positions against real `kicad-cli pcb drc` clearance
  rules manually (spot-check, not full DRC integration yet — that's R3/U4).

**Test scenarios:**
- Happy: `_route_segment_3d` finds a path for a same-layer segment (sanity
  check — should match 2D A* behavior modulo the extra via-move branching).
- Happy: `_route_segment_3d` finds a path for a forced-layer-transition
  segment and returns a non-empty `via_positions`.
- Scale: wall time recorded for N segments at production board grid
  dimensions — no pass/fail threshold yet (this unit establishes the
  baseline number; U2's Verification sets the actual bar once a target
  fallback-tier invocation rate is known).
- Edge: a deliberately congested/obstacle-dense region — confirm the search
  degrades gracefully (returns `None`, doesn't hang) rather than pathological
  blowup.

**Verification:** A committed, dated measurement record (in the test's
output or a short results note) stating: real wall time at production
scale, via-legality spot-check result, and an explicit go/adjust decision
for U2 — "the fallback-tier approach is validated as spec'd" or "the
approach needs adjustment: [specific finding]," not silence.

---

### U2. Wire `_route_segment_3d` as a fallback tier in `_astar_route_multilayer`

**Goal:** When both the primary-grid and THT-gated alternate-grid attempts
fail for a segment, try `_route_segment_3d` as a last resort; populate real
`via_positions` in the returned `RoutePath3D` from its result (R1).

**Requirements:** R1

**Dependencies:** U1 (validates the approach before committing to it)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py`
  (`_astar_route_multilayer`, add the third fallback tier after the existing
  `alternate_grid`/`tht_locations` branch)
- Test: `packages/temper-placer/tests/router_v6/test_astar_route_multilayer_via_fallback.py` (new)

**Approach:**
- After the existing THT-gated alternate-grid fallback fails (or is
  unavailable), build a `grids: dict[str, OccupancyGrid]` from the
  available primary/alternate grids (see Open Questions — confirm this
  reshaping is mechanical) and call `_route_segment_3d`.
- If it succeeds, append its `via_positions` to the net's accumulated via
  list (currently always empty — this is R1's actual fix) and use its
  `world_path` for this segment's `detailed_segments`.
- If it fails too, preserve existing failure behavior (forced/failed
  segment counting) unchanged.
- Do not change `via_cost`/`via_diameter`/`clearance` defaults yet — R2/R3
  handle sizing correctness; this unit only wires the mechanism and starts
  populating real via positions.

**Test scenarios:**
- Happy: a segment routable only via the 3D-search fallback tier produces a
  non-empty `via_positions` in the final `RoutePath3D`.
- Regression: segments that already succeed on primary/alternate grids are
  unaffected (fallback tier never invoked, existing behavior/performance
  unchanged) — proves this is additive, not a replacement.
- Integration: full-net routing (`_route_net_with_ripup`) on the corpus
  board produces a `RoutePath3D` with real via positions for at least one
  net that previously had none.

**Verification:** `via_positions` is no longer a static `[]` for nets that
needed the fallback tier; existing golden-board routing tests' non-via
behavior is unchanged (diff the routed output for nets that never reach the
fallback tier — should be byte-identical to pre-U2).

---

### U3. Fix hardcoded via layer-span in `via_placement.py`

**Goal:** `_place_vias_for_path()`'s `RoutePath3D`/`via_positions` branch
must derive `from_layer`/`to_layer` from the actual segment layers on
either side of each transition, not the hardcoded `"F.Cu"`/`"B.Cu"`.

**Requirements:** R2

**Dependencies:** None (independent of U1/U2 — this is a pure bug fix once
`via_positions` carries real data, but the fix itself doesn't depend on U2
landing first; sequence for convenience, not correctness)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/via_placement.py`
  (`_place_vias_for_path`, lines 104-116)
- Test: `packages/temper-placer/tests/router_v6/test_via_placement.py`
  (extend — existing coverage only exercises the legacy `RoutePath`
  fallback branch, not the `RoutePath3D` branch this fix targets; this is a
  real coverage gap noted in the origin brainstorm's Evidence)

**Approach:**
- `RoutePath3D.segments` already carries per-point `(x, y, layer)` — for
  each `via_positions` entry `(vx, vy)`, find the segment layer immediately
  before and after that coordinate in `route_path.segments` and use those
  as `from_layer`/`to_layer` instead of the hardcoded pair.
- Do not touch the legacy-`RoutePath` branch (lines 118-139) — it already
  computes real layers correctly via `_get_adjacent_layer()` and is
  unaffected by this bug.

**Test scenarios:**
- Happy: a `RoutePath3D` with a transition from `F.Cu` to `B.Cu` produces a
  `Via` with `from_layer="F.Cu", to_layer="B.Cu"` (matches old hardcoded
  behavior for the 2-layer case — proves no regression on the current
  production board).
- Regression (the actual bug fix, only observable once a non-F.Cu/B.Cu
  transition exists — may need a synthetic 4-layer test fixture): a
  transition involving `In1.Cu`/`In2.Cu` produces a `Via` with the correct
  non-F.Cu/B.Cu layer pair, not the old hardcoded default.
- Edge: multiple transitions in one path produce correctly-paired vias for
  each, not all defaulting to the same pair.

**Verification:** `_place_vias_for_path()`'s `RoutePath3D` branch output
matches the real segment layers for every via position, verified against a
synthetic multi-layer fixture (since the current 2-layer production board
can't distinguish the fix from the old hardcode by itself).

---

### U4. Via placement legality + per-netclass sizing

**Goal:** Thread real per-netclass `via_diameter`/`via_drill` (from
`netclass_rules.yaml`) into both the search's legality check
(`_astar_search_3d`'s `via_diameter`/`clearance` params, currently
hardcoded `0.6`/`0.2`) and `via_placement.py`'s `Via` construction
(currently a single board-wide default).

**Requirements:** R3

**Dependencies:** U2 (needs the fallback tier wired so per-net calls exist
to parameterize), U3 (layer-span must be correct before sizing is
meaningfully attached to the right layer pair)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py`
  (thread the calling net's resolved netclass through to the U2 fallback
  call site's `via_cost`/`via_diameter`/`clearance` arguments)
- Modify: `packages/temper-placer/src/temper_placer/router_v6/via_placement.py`
  (`place_vias`/`_place_vias_for_path` — resolve per-net class sizing
  instead of the single board-wide default, mirroring how
  `pipeline.py::_run_stage5` already resolves `layer_constraints` per net)
- Test: `packages/temper-placer/tests/router_v6/test_via_placement.py`
  (extend)

**Approach:**
- Resolve each net's netclass the same way `channel_mapping.py`/
  `layer_assignment.py` already do (via `netclass_rules.yaml`'s net-name
  pattern matching) — reuse that resolution, do not duplicate it.
- Pass the resolved class's `via_diameter`/`via_drill` into both the 3D
  search call (U2's fallback tier — replaces the `0.6`/`0.2` defaults) and
  `_place_vias_for_path`'s `Via` construction (replaces the board-wide
  default).
- Legality itself (no collision with existing copper/vias) is already
  handled by `mark_via_blocked()` inside `_astar_search_3d` — this unit's
  job is correct *sizing* input to that existing mechanism, not building a
  new legality check from scratch.

**Test scenarios:**
- Happy: a net in the `HV` netclass gets a via sized `1.2mm`/`0.6mm` drill
  (per `netclass_rules.yaml`), not the generic default.
- Happy: a net in `FinePitch` gets `0.4mm`/`0.2mm`.
- Regression: a net with no explicit netclass assignment falls back to a
  documented default (same as current behavior), not a crash.

**Verification:** Via sizing in both the search's legality check and the
final `Via` objects matches `netclass_rules.yaml` per net, for at least one
net per netclass present on the corpus board.

---

### U5. Emit real `(via ...)` KiCad output

**Goal:** `_write_routes_to_content()` reads `compiled_route.vias` and
emits a real `(via (at x y) (size d) (drill dr) (layers "X" "Y") (net n)
...)` s-expression for each one.

**Requirements:** R4

**Dependencies:** U3 (correct layer-span), U4 (correct sizing)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/adapter.py`
  (`_write_routes_to_content`)
- Test: `packages/temper-placer/tests/router_v6/test_via_output_writer.py`
  (new)

**Approach:**
- Add a loop over `compiled_route.vias` alongside the existing track-segment
  write loop; emit one `(via ...)` s-expression per `Via` object using its
  `from_layer`/`to_layer` (as `(layers ...)`), `diameter`/`drill`
  (as `(size ...)`/`(drill ...)`), `position` (as `(at ...)`), and resolved
  net number.
- Match the existing KiCad s-expression formatting conventions already used
  for track segments in the same function (indentation, float precision).
- This unit does **not** change the segment `(layer ...)` write — that
  remains hardcoded `F.Cu` until U6/R5. Emitting vias without yet emitting
  divergent segment layers is intentionally safe: it adds new content
  (vias) without changing existing content's meaning.

**Test scenarios:**
- Happy: a `CompiledRoute` with 2 vias produces exactly 2 `(via ...)`
  s-expressions in the output, with correct position/size/drill/layers/net.
- Happy: a `CompiledRoute` with zero vias produces no `(via ...)` entries
  (no regression for the common case).
- Integration: the written PCB file round-trips through `kicad-cli pcb drc`
  without a parse error (proves the s-expression syntax is valid KiCad
  format, not just python-side correct).

**Verification:** Real `(via ...)` entries appear in written output for
every populated `compiled_route.vias` entry; `kicad-cli pcb drc` parses the
file without error.

---

### U6. Re-land the segment-layer write (previously reverted in `903dfaef`)

**Goal:** `_write_routes_to_content()` writes the real `path_layer` per
segment (already computed, currently discarded) instead of the hardcoded
`(layer "F.Cu")` — this is the change that actually lets router output
diverge from `main`, and is safe now that U1-U5 back it with real via
insertion.

**Requirements:** R5

**Dependencies:** U1, U2, U3, U4, U5 (explicitly: do not start this unit
until all of them are merged and verified — this sequencing is the direct
lesson from PR #220's regression)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/adapter.py`
  (`_write_routes_to_content`, replace the hardcoded `"F.Cu"` literals with
  `path_layer`)
- Test: `packages/temper-placer/tests/router_v6/test_regression_drc.py`
  (extend or add a case) and the two `903dfaef` guard tests must be
  re-examined here (see below)

**Approach:**
- Replace the hardcoded `(layer "F.Cu")` writes with the already-computed
  `path_layer` variable (per the brainstorm's point 5 — the data exists,
  it's just discarded).
- Run `kicad-cli pcb drc` on both the corpus board and
  `pcb/temper.kicad_pcb` before and after this change; compare
  `unconnected_items` and per-category violation counts explicitly (R7).
- Check the two existing guard tests from `903dfaef`
  (`test_no_net_force_moved_from_heuristic_layer`,
  `test_completion_rate_100pct_routing_signal`): if they still pass
  unmodified, that's expected (R6's gate is still in place, so layer
  assignment itself hasn't changed yet — only *routing output* for nets
  already legitimately using non-heuristic layers via the fallback tier
  should differ). If either fails, stop and diagnose before proceeding —
  do not modify or delete a guard test to make it pass without
  understanding why it failed.

**Test scenarios:**
- Happy: a net routed via U2's fallback tier (genuinely on a
  divergent layer) now has correct `(layer ...)` output matching its
  actual routed layer, not `F.Cu`.
- Regression: `unconnected_items` on both the corpus and production boards
  is unchanged or improved relative to the pre-U6 baseline — never worse
  (R7, the exact PR #220 regression check, applied preemptively this time).
- Regression: the two `903dfaef` guard tests still pass.

**Verification:** `kicad-cli pcb drc` before/after comparison committed as
a dated record (matching the `u9_final` baseline provenance pattern);
`unconnected_items` never regresses; both guard tests pass.

---

### U6.1. Diagnose the residual routing-quality baseline before widening layer assignment

**Goal:** Turn the post-U6 DRC result into an evidence-backed input to U7,
rather than treating all remaining violation types as an undifferentiated
reason to change routing policy.

**Requirements:** R5, R7

**Dependencies:** U6

**Status (2026-07-18):** Complete diagnosis; its implementation consequence is
U7. The current corpus measurement has 0 routed `unconnected_items`, but 331
total routed violations versus 94 placement-only violations: 99 `clearance`,
81 `shorting_items`, 79 `solder_mask_bridge`, 54 `tracks_crossing`, and 8
`hole_clearance`. The existing U8 diagnosis established that the representative
shorts are genuine different-net copper crossings, not intra-component false
positives. The clearance, mask, and crossing classes are the expected companion
symptoms of the same same-layer congestion; hole clearance is not attributed to
layer assignment and remains out of scope for U7.

**Fresh code-path finding:** `RouterV6Pipeline._run_stage4()` already threads
`layer_constraints` into `map_topology_to_channels()` and
`fallback_channel_path()`. The blocker is deliberately in
`channel_mapping._assign_layer()`: it returns an explicit SSOT layer only when
it equals the heuristic. Thus `GateDrive` and other F.Cu-heuristic / B.Cu-SSOT
nets cannot yet use the newly proven transition path. Earlier reports that the
pipeline did not wire the constraints are stale.

**Acceptance bar for U7:** Preserve 100% internal completion and never worsen
`unconnected_items` on either board. Measure every DRC class before and after;
the first U7 increment must attribute any reduction in genuine crossings to
specific nets whose SSOT layer now diverges. It must not relax DRC thresholds
or claim that the non-layer `hole_clearance` category is solved. USB D+/D-
differential-pair spacing remains a separate W2 U5 follow-up.

---

### U7. Relax the SSOT completion-preserving gate

**Goal:** Once R5 (U6) is proven safe, relax `_assign_layer()`'s `if ssot is
not None and ssot == heuristic: return ssot` no-op condition so SSOT-driven
layer assignments can actually diverge from the pure name-pattern
heuristic — the entire original point of the W2 U2 work.

**Requirements:** R6

**Dependencies:** U6 (strictly — R6 must not start until R5 is proven; this
is the brainstorm's own explicit sequencing requirement)

**Files:**
- Modify: `packages/temper-placer/src/temper_placer/router_v6/channel_mapping.py`
  (`_assign_layer`)
- Test: `packages/temper-placer/tests/router_v6/test_channel_mapping.py`
  (extend), plus a CI-runnable before/after DRC comparison (see
  Verification — this is the brainstorm's Open Question 4, resolved here)

**Approach:**
- Remove or relax the `ssot == heuristic` condition so `_assign_layer`
  returns the SSOT layer whenever one is defined, regardless of heuristic
  agreement.
- Start with a TDD/PBT-protected policy seam: explicit, routable SSOT classes
  win; Default/unassigned nets retain the heuristic. Generate assignments over
  the supported outer layers and net-class states to prove the resolution is
  deterministic and cannot manufacture an unsupported layer.
- Before merging: run the full `kicad-cli pcb drc` comparison (corpus +
  production boards) with the gate relaxed, and require the same
  never-regress-`unconnected_items` bar as U6.
- This is the unit most likely to surface new failure modes (real layer
  divergence at scale, not just the fallback tier's small residual
  segment population) — budget for iteration here specifically.

**Test scenarios:**
- Happy: a net with an explicit SSOT netclass layer assignment that
  disagrees with the heuristic now actually routes on the SSOT layer.
- Regression: `unconnected_items` unchanged or improved on both boards,
  same bar as U6.
- Regression: the two `903dfaef` guard tests are either still passing, or
  explicitly and visibly updated/superseded with a stated reason (this is
  the one unit where they might legitimately need to change, since this is
  the unit that finally makes layer divergence real).

**Verification:** A specific, CI-runnable job or test comparing
`kicad-cli pcb drc` output before and after this unit's change, on both
boards, gating the merge — not implementer judgment. This resolves the
brainstorm's Open Question 4 by making the "proven safe" bar concrete
rather than left to discretion.

**Implementation measurement (2026-07-18):** The U7 corpus run preserves
100% completion and 0 routed `unconnected_items`. It records 329 total routed
violations (102 `clearance`, 73 `shorting_items`, 79 `solder_mask_bridge`, 57
`tracks_crossing`, 8 `hole_clearance`) versus U6.1's 331. The attributed
improvement is eight fewer genuine shorts after explicit GateDrive/power layer
divergence; clearance and crossing move by +3 each, so U7 is connectivity-safe
and directionally useful, not routing closure. The production DRC threshold
regression passes. U8 remains required to diagnose the residual categories.

---

### U8. Cross-cutting anti-false-zero verification (R7)

**Goal:** A final, explicit check that every connectivity/routing claim
made across U1-U7 is backed by real `kicad-cli pcb drc` measurement, not
inferred from "A* found a path" or "a `Via` object was created" — the
lesson from PR #220's two false subagent claims, applied here from the
start rather than discovered via a second regression.

**Requirements:** R7

**Dependencies:** U1-U7 (this unit audits the completed chain)

**Files:**
- Test: `packages/temper-placer/tests/router_v6/test_via_insertion_anti_false_zero.py`
  (new)

**Approach:**
- Assert every unit's committed measurement record (U1's spike results,
  U6's and U7's before/after DRC comparisons) exists and is traceable —
  not asserted from memory.
- Re-run `kicad-cli pcb drc` on both boards at the final state and confirm
  the cumulative `unconnected_items` delta across all of U1-U7 is
  non-negative (never worse than the pre-U1 baseline).
- Confirm `IECCreepageGate` and the general clearance gate report real
  measurements (not `UNMEASURED`) against the final via-containing output —
  per the brainstorm's Success criterion 4, these gates activate for real
  the moment real `(via ...)` entries exist; verify they actually do.

**Test scenarios:**
- Happy: all anti-false-zero conditions pass on the final state.
- Error: a missing or stale measurement record (e.g. U6's DRC comparison
  wasn't actually committed) fails this check loudly, rather than being
  silently assumed present.

**Verification:** Final, cumulative `kicad-cli pcb drc` measurement on both
boards, committed with provenance (matching the `u9_final` baseline
pattern); `IECCreepageGate`/clearance gate both report real measurements.

---

## System-Wide Impact

- **Interaction graph:** U1 (spike, no code change) → U2 (fallback tier,
  populates real via positions) → {U3, U4} (parallelizable bug fixes on the
  now-real via data) → U5 (writer emission, depends on U3+U4 for correct
  data) → U6 (segment-layer re-land, depends on U1-U5 all proven) → U7
  (SSOT gate relaxation, depends on U6 proven) → U8 (final cross-cutting
  audit).
- **Behavior changes:** Router output only diverges from current `main`
  starting at U6; U1-U5 are additive (new via data/output) without changing
  existing segment-layer behavior. U7 is the unit that finally lets net
  layer assignment itself diverge from the pure heuristic.
- **Error propagation:** No new failure modes introduced for segments that
  never reach the fallback tier (U2) — existing primary/alternate-grid
  behavior is unchanged. The fallback tier's own failure (no path found)
  degrades to existing "forced/failed segment" handling, not a crash.
- **Unchanged invariants:** The two `903dfaef` guard tests remain the
  primary regression signal for "did this break completion" until U7
  explicitly and visibly supersedes them (not before).
- **Integration coverage:** U8 is the single point that verifies the whole
  chain end-to-end against real DRC measurement, not per-unit isolated
  claims.

---

## Risks & Dependencies

| Risk | Mitigation |
|------|------------|
| U1's spike reveals `_route_segment_3d` is too slow at production scale (95 nets) | U1 explicitly gates U2 on this; if wall time is unacceptable even at fallback-tier invocation rates, U2's approach needs adjustment (e.g. a hard per-segment timeout with graceful fallback to "forced/failed," or bounding the search's grid extent) — not silently shipped anyway |
| The 3D search's lack of Theta*/coarse-to-fine/congestion-awareness produces poor-quality routes even as a fallback tier | Bounded blast radius by design (only invoked when primary+alternate already failed) — a lower-quality route on an already-hard segment is a smaller regression risk than replacing the primary router entirely |
| U6/U7 reproduce PR #220's exact regression (output diverges before via insertion can back it up) | Explicit, non-optional sequencing (U6 strictly after U1-U5; U7 strictly after U6) plus the same before/after DRC comparison discipline that caught the original regression |
| Git archaeology on why `_astar_search_3d` was shelved remains inconclusive | Does not block this plan — the plan proceeds on the evidence available (the search is correct and complete, just never wired) and treats the historical "why" as informational, not load-bearing for the implementation decision |
| Per-netclass via sizing (U4) requires net→class resolution logic that may not perfectly cover all 95 production nets | Same resolution mechanism `channel_mapping.py`/`layer_assignment.py` already use and have been production-verified against the real net list — not new, unproven logic |

---

## Success Metrics

(Mirrors the origin brainstorm's Success criteria, made unit-traceable.)

1. `via_positions` is populated from genuine layer transitions on at least
   one real net (U2).
2. `kicad-cli pcb drc` `unconnected_items` on both boards is never worse
   than the pre-U1 baseline, at every intermediate unit, not just the final
   state (U6, U7, audited by U8).
3. At least one net with an explicit netclass actually routes on a
   layer diverging from the pure heuristic, connected via a real
   `(via ...)` entry, verified by `kicad-cli pcb drc` (U7).
4. `IECCreepageGate` and the general clearance gate report real
   measurements against via-containing output (U8).
5. The two `903dfaef` guard tests pass throughout, or are explicitly
   superseded with a stated reason no later than U7.
6. The corpus board's `clearance`/`tracks_crossing`/`solder_mask_bridge`
   counts show a measured, attributed improvement — or the reason they
   don't is diagnosed, not assumed (U8, carried from the origin
   brainstorm's Success criterion 6).

---

## Sources & References

- **Origin document:** [docs/brainstorms/2026-07-18-via-aware-layer-transitions-requirements.md](../brainstorms/2026-07-18-via-aware-layer-transitions-requirements.md)
- **Issue:** https://github.com/BennetLeff/temper/issues/226
- **PR #220 evidence trail:** commits `d88e61d2`, `112df593`, `903dfaef`
- **3D search origin:** commit `c2027834` (2026-01-12), "implement
  production-grade 3D A* routing with explicit via insertion"
- **Excavation doc:** [docs/solutions/workflow-issues/2026-07-18-plan-execution-and-ci-rot-excavation.md](../solutions/workflow-issues/2026-07-18-plan-execution-and-ci-rot-excavation.md)
- **Routing-completion plan (U7 audit, partially superseded by this
  document's more precise chain):** [docs/plans/2026-07-18-002-feat-board-routing-completion-plan.md](2026-07-18-002-feat-board-routing-completion-plan.md)
- **Single-layer-first sequencing:** [docs/brainstorms/2026-07-08-single-layer-route-requirements.md](../brainstorms/2026-07-08-single-layer-route-requirements.md)
- Key code: `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py`,
  `astar_core.py`, `via_placement.py`, `routing_results.py`, `adapter.py`,
  `channel_mapping.py`, `occupancy_grid.py`
- `packages/temper-placer/configs/netclass_rules.yaml` — per-class via
  sizing SSOT
