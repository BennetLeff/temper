# Via-Aware Layer Transitions — Scoping Issue #226

**Date:** 2026-07-18
**Status:** Requirements — ready for planning
**Scope tier:** Deep — router-algorithm engineering, touches the A* pathfinding kernel and the KiCad output writer

## Problem

Issue #226 states the router "has no via insertion" and that `layer_constraints`
was "constructed in `RouterV6Pipeline.__init__` but never wired into
`_run_stage4`/A***." Both are now imprecise relative to current `main`
(verified below): the wiring is live, and a substantial amount of
via-related infrastructure already exists — but it is disconnected at five
distinct points along the pipeline, any one of which is enough to make the
whole chain a no-op. The net effect issue #226 describes is real (a net
routed on B.Cu whose SMD pads exist only on F.Cu is DRC-unconnected without
a via), but the fix is "reconnect five already-built pieces and add real
legality checking to one of them," not "build via insertion from scratch."

This matters for scoping: a plan written against issue #226's literal text
would likely re-invent machinery (`Via`, `ViaPlacement`, `place_vias`,
`CompiledRoute.vias`) that already exists, while missing the actual gaps
(an always-empty `via_positions` list, a hardcoded via layer-span, a
KiCad-writer that never reads the `vias` field it's handed, and a
completion-preserving gate that makes layer divergence permanently
impossible even after the rest is fixed).

## Existing state (verified 2026-07-18, against `origin/main` @ `746a2d32`)

**Correction to this session's own prior audit:** the routing plan's U7
finding (`docs/plans/2026-07-18-002-feat-board-routing-completion-plan.md`)
and issue #226 itself both describe `layer_constraints` as unwired. That was
accurate when written (against PR #220's `112df593` state) but `main` has
since absorbed `17447274` (the loc-cap `fallback_channel_path` extraction),
which moved code but not behavior. Re-verified directly against
`origin/main` for this document — the wiring described below is current,
not stale.

### The five-point gap chain (each verified against real `origin/main` source)

1. **`channel_mapping.py::_assign_layer()` — SSOT is wired but permanently
   inert.** `_assign_layer(net_name, layer_constraints)` resolves a
   `heuristic` layer (power/ground/HV → B.Cu, else F.Cu) and an `ssot` layer
   from the netclass YAML via `_ssot_layer_for_net()`. But: `if ssot is not
   None and ssot == heuristic: return ssot` — SSOT is **only ever applied
   when it already agrees with the heuristic.** This is deliberate
   (commit `112df593`, "completion-preserving SSOT layer semantics," written
   to stop the PR #220 regression) but means no net's routing layer can
   currently diverge from pure name-pattern heuristics, regardless of what
   the netclass YAML says. This gate is *correct as a stopgap* and *wrong as
   a permanent state* — it exists specifically because nothing downstream
   could yet handle a real divergence safely.

2. **Two independent multilayer mechanisms exist. The one actually wired to
   production (`_astar_route_multilayer`) never records a via. The one that
   does (`_astar_search_3d`) is fully built, algorithm-tested — and called
   by nobody.**

   - **`astar_pathfinding.py::_astar_route_multilayer()`** (the function
     `_route_net_with_ripup()` — the real production dispatch — actually
     calls): per waypoint-to-waypoint segment, tries the primary grid, and
     on failure retries `alternate_grid` — but only `if ... alternate_grid
     and tht_locations` (a non-empty *set*, checked for existence, not
     per-point proximity — looser than the function's own docstring claims:
     "layer switching at SMD pads is enabled when an alternate grid exists"
     is not what the code does). When the retry succeeds,
     `detailed_segments` DOES correctly carry the true per-point layer
     (`node.layer_name`) — a `RoutePath3D.segments` list can legitimately
     span two layers today. But the function's return statement hardcodes
     `via_positions=[]` and `via_count=0` unconditionally — no code detects
     "the layer changed between consecutive segments, record a via position
     here." This function stitches together separate single-layer 2D A*
     searches per waypoint pair; it does not reason about layers as part of
     one search.

   - **`astar_core.py::_astar_search_3d()` / `_route_segment_3d()`**: a
     genuine, complete 3D A* implementation. `RouteNode3D` (`x, y, layer`)
     is the actual search state; the frontier expands across layers with a
     tunable `via_cost`; on reaching the goal it reconstructs the path and
     **correctly detects every layer transition to populate
     `via_positions`** (`if prev_layer is not None and prev_layer != cl:
     vias.append((cx, cy))` — exactly the logic point 2's other mechanism
     is missing); it then calls `grid.mark_via_blocked(...)` on every layer
     the via spans, with real `via_diameter`/`clearance` parameters, so
     later searches don't collide with it. It has direct property-based
     test coverage (`test_astar_metamorphic_pbt.py::test_3d_path_cells_free`,
     `test_3d_no_redundant_same_layer_nodes`, Hypothesis-driven, 50 examples
     each) confirming basic path-legality invariants hold. **`grep` for
     `_route_segment_3d` and `_astar_search_3d` across
     `src/temper_placer/` turns up zero callers outside `astar_core.py`
     itself and its own tests.** It was introduced (or relocated) in commit
     `4b037d11` ("decompose astar_pathfinding.py into astar_core.py +
     astar_grid.py") — consistent with this being multilayer
     infrastructure built ahead of the project's deliberate
     single-layer-first sequencing (`docs/brainstorms/2026-07-08-single-layer-route-requirements.md`)
     and never reconnected once that phase completed. This materially
     changes the shape of the options below: a full via-aware 3D search is
     not a from-scratch design question, it is an existing, tested
     component whose integration was never finished.

3. **`via_placement.py::place_vias()` — real via-computation logic exists,
   consumes the (always-empty) `via_positions`, and has one concrete bug.**
   `_place_vias_for_path()` correctly derives `Via` objects from
   `route_path.via_positions` when present (currently always `[]`, per #2,
   so it currently produces zero vias for any A*-routed net). It receives
   real per-net sizing from the caller (`pcb.design_rules.default_via_diameter_mm`
   / `default_via_drill_mm` in `pipeline.py::_run_stage5`) — sizing is not
   hardcoded at the call site. But inside the function itself: `from_layer=
   "F.Cu"` / `to_layer="B.Cu"` is hardcoded regardless of which layers the
   path segments actually transition between ("Assume THT via spans full
   stack" — wrong for any transition that isn't exactly F.Cu↔B.Cu, which
   matters once a 4-layer stackup is in play, not for the current 2-layer
   production board).

4. **The data reaches `CompiledRoute.vias` — and stops there.**
   `pipeline.py::_run_stage5()` calls `place_vias()`, then
   `compile_routing_results()` stores `net_vias =
   via_placement.get_vias_for_net(net_name)` onto `CompiledRoute.vias` (a
   real, populated field on the exact object `route_pcb()` and
   `_write_routes_to_content()` receive as `result.stage4.routing_results`).
   **`adapter.py::_write_routes_to_content()` never reads
   `compiled_route.vias`.** No `(via ...)` KiCad s-expression is emitted
   anywhere in the codebase's actual output path. This is the most directly
   actionable single gap — the data already exists at the point the writer
   runs; nothing downstream consumes it.

5. **The segment layer write is hardcoded to F.Cu, reverted deliberately in
   PR #220.** `_write_routes_to_content()` computes `path_layer` correctly
   per segment (`path_layer = s[2]` from `RoutePath3D.segments`) but writes
   `(layer "F.Cu")` literally regardless (commit `903dfaef`: "revert
   routed-segment layer output to F.Cu pending via-aware transitions" — this
   revert is the direct reason issue #226 exists, and un-reverting it without
   fixing 1-4 first would reproduce the exact 8-unconnected-items regression
   PR #220 hit).

### Three distinct "via" concepts in the codebase — do not conflate

- **`EscapeVia`** (`escape_via_generator.py`, Stage 1.3): dog-bone/via-in-pad
  escape vias for dense packages, computed at pin-escape time. Unrelated to
  mid-route layer transitions — out of scope here.
- **`Via`/`ViaPlacement`** (`via_placement.py`, Stage 4.3): the mid-route
  layer-transition vias this document is about.
- **THT-pad implicit transitions** (`astar_pathfinding.py`, Stage 4.2): the
  "free" layer switch at an existing plated hole — a legality *mechanism*,
  not a via *object*. No `Via` is ever created for these today; the THT pad
  itself carries the connection.

### Relevant existing SSOT data

`netclass_rules.yaml` already carries real per-class `via_diameter`/
`via_drill` values (e.g. `via_diameter: 1.2, via_drill: 0.6` for HV classes;
`0.4/0.2` for FinePitch) — this is exactly the sizing data a fixed
`_place_vias_for_path()` should resolve per net's class, rather than a
single board-wide `pcb.design_rules.default_via_diameter_mm` for every net
regardless of class.

### Existing DRC coverage that activates for free once vias are real

`IECCreepageGate` (6mm HV↔LV creepage) and the general DRC clearance gate
both run `kicad-cli pcb drc` against whatever is actually in the routed PCB
file. Neither needs new code to check via clearance/creepage — they will
start checking it automatically the moment real `(via ...)` entries appear
in the output, the same way they already check track clearance. This is a
reason to prioritize #4 (writer emission) — it's the one change that makes
existing gates start doing real work.

### What the W2 plan (`docs/plans/2026-07-08-004-feat-4-layer-functional-stackup-plan.md`) does and does not cover

W2's U2 ("Net-to-layer assignment from the SSOT") specified exactly the
`layer_constraints`/`layer_assignments_from_netclass()` machinery that is
now built and confirmed live (point 1 above). **U2's spec never mentions via
insertion at all** — it assumes layer *assignment* is the whole problem.
This document is not a resumption of an existing via-insertion design; none
exists yet.

### PR #220 evidence trail (what NOT to repeat)

- `d88e61d2` — wired `layer_constraints` through and fixed the segment
  write to use `path_layer` instead of hardcoded F.Cu.
- `112df593` — hit the regression (8 unconnected items: heuristic-B.Cu nets'
  SMD pads exist only on F.Cu, and without via insertion, routing them on
  B.Cu disconnects them) and added the completion-preserving gate (point 1)
  as a stopgap.
- `903dfaef` — reverted the segment-write change entirely (point 5) after
  confirming the gate alone wasn't sufficient; router output is
  byte-identical to `main` as of this document. Two guard tests
  (`test_no_net_force_moved_from_heuristic_layer`,
  `test_completion_rate_100pct_routing_signal`) were added and remain live —
  any future work here must keep them passing or explicitly supersede them.

The pattern across all three commits: **a route that "found a path" was
trusted before its DRC connectivity was verified.** This document's
Success criteria (below) make that check explicit up front rather than
discovering it via a second regression.

## Requirements

### R1 — Populate real via positions from actual layer transitions

Whichever option (below) is chosen, `via_positions` (or equivalent) must
stop being a hardcoded `[]` and must reflect genuine layer changes between
consecutive routed points for a net.

### R2 — Fix the hardcoded via layer-span

`_place_vias_for_path()`'s `from_layer="F.Cu"` / `to_layer="B.Cu"` must be
derived from the actual segment layers on either side of the transition, not
assumed. Low-risk on the current 2-layer production board; a real
correctness requirement the moment a 3rd/4th copper layer is in play.

### R3 — Via placement legality against the occupancy grid

A candidate via position must be checked for physical legality — no
collision with existing copper/other vias/keepouts on either layer it
spans, and clearance vs. the netclass SSOT's `via_diameter` for its class —
before being accepted. Currently zero legality checking exists; vias are
placed wherever a layer change happens to occur.

### R4 — Emit real `(via ...)` KiCad output

`_write_routes_to_content()` must read `compiled_route.vias` and emit a
`(via (at x y) (size d) (drill dr) (layers "F.Cu" "B.Cu") (net n) ...)`
s-expression for each one, using per-net-class sizing from `netclass_rules.yaml`
(R2's corrected layer-span feeds directly into which layer pair a via's
`(layers ...)` field names).

### R5 — Re-land the segment-layer write, this time completion-verified

Re-apply `903dfaef`'s reverted change (write the real `path_layer`, not a
hardcoded F.Cu) — but only after R1-R4 land and are proven, on the actual
corpus and production boards, not to reintroduce unconnected items. This is
sequenced last deliberately: it's the change that actually lets output
diverge from `main`, and everything before it is what makes that safe.

### R6 — Make the SSOT completion-preserving gate real once safe

Once R1-R5 are proven not to regress completion, the `ssot == heuristic`
no-op condition in `_assign_layer()` should be relaxed so SSOT-driven layer
assignments can actually diverge from the heuristic (the entire point of the
W2 U2 work). This is explicitly sequenced after, not alongside, R1-R5 — the
guard exists because a prior attempt made this change first and broke
completion.

### R7 — Anti-false-zero discipline, explicit up front

Per this session's own repeated lesson (PR #220's two false subagent
fixes): any claim that vias/layer transitions "work" must be checked against
real `kicad-cli pcb drc` `unconnected_items` and violation-class deltas —
before and after, per board (corpus and production) — not inferred from "A*
found a path" or "the via object was created." Every claimed improvement
must be traceable to a specific measured delta, matching the `u9_final`
baseline provenance pattern already established.

## Success criteria

1. `via_positions` is populated from genuine layer transitions, not a
   static empty list (R1).
2. `kicad-cli pcb drc` on both the corpus board and `pcb/temper.kicad_pcb`
   shows `unconnected_items` unchanged or improved (never worse) relative to
   the current `main` baseline, for every intermediate state — not just the
   final one.
3. At least one net with an explicit netclass (e.g. `GateDrive`,
   `FinePitch`) actually routes on a layer that diverges from the pure
   heuristic, with a real `(via ...)` entry connecting it back to its
   F.Cu-only pads, verified via `kicad-cli pcb drc` (not just code
   inspection).
4. `IECCreepageGate` and the general clearance gate both report a real
   measurement (not `UNMEASURED`) against the via-containing output.
5. The two guard tests from `903dfaef`
   (`test_no_net_force_moved_from_heuristic_layer`,
   `test_completion_rate_100pct_routing_signal`) still pass, or are
   explicitly and visibly superseded with a documented reason.
6. The corpus board's `clearance`/`tracks_crossing`/`solder_mask_bridge`
   violation counts (144/108/99 as of this document) show a measured,
   attributed improvement — or, if they don't, the reason is diagnosed and
   documented rather than assumed to be "fixed by adding a layer."

## Scope boundaries

**In scope:** the five-point gap chain (R1-R5), via placement legality
(R3), per-netclass via sizing (R2), and the sequenced SSOT-gate relaxation
(R6) once proven safe.

**Deferred:**
- The specific via-insertion algorithm's implementation details (exact
  cost-function integration if Option B below is chosen, exact legality
  search order if Option A is chosen) — this document scopes the decision,
  a planning pass designs the mechanism.
- 4-layer (In1.Cu/In2.Cu) via transitions — the production board is
  currently 2-layer; R2's fix is layer-span-correct for whatever layers are
  actually in play, but testing against inner layers is out of scope until
  the board itself uses them.
- `shorting_items` and `diff_pair_gap_out_of_range` violation classes — per
  the routing-completion plan (`docs/plans/2026-07-18-002`), these likely
  need individual diagnosis separate from layer-crowding/via work.

**Outside scope:**
- The board-capacity/BOM decision (`docs/brainstorms/2026-07-18-board-capacity-bom-decision-requirements.md`)
  — independent, parallel thread.
- Power-plane pours (W2 U4) — explicitly named in issue #226 as depending on
  this work, not part of it.
- `EscapeVia`/pin-escape via generation (Stage 1.3) — a different, already-
  functional mechanism, not touched here.

## Open questions for planning

1. **Option A vs. B vs. C for R1's via-detection/insertion mechanism** — no
   option is pre-selected:

   | Option | Approach | Tradeoff |
   |---|---|---|
   | **A. Post-hoc detection on the existing 2D-stitched router** | Keep `_astar_route_multilayer()`'s current per-waypoint-segment 2D search; add a pass that scans `detailed_segments` for consecutive layer changes and records/legality-checks a via at each one (retrying the segment if the via position is illegal). | Lowest short-term implementation complexity; touches only `astar_pathfinding.py`, not the core kernel. Risk: vias are chosen after pathfinding, not during it — the "found a path, then couldn't legally realize it" failure mode PR #220 already hit once (at connectivity) could recur in a new form (at via legality). Also duplicates legality logic `_astar_search_3d` already has. |
   | **B. Wire in the existing `_astar_search_3d`/`_route_segment_3d`** | Replace (or add as an alternative branch to) `_astar_route_multilayer()`'s per-segment 2D-retry loop with calls to the already-built, already-tested 3D search. `via_positions` detection, via-cost weighting, and post-placement blocking via `mark_via_blocked()` all already exist and need no new algorithm work. | Structurally correct, and the highest-risk algorithmic component (the search itself) is already done and property-tested. Real remaining work: confirm it performs adequately at production scale (95 nets / 149 components — its tests use small synthetic grids), confirm its `via_cost`/`clearance` defaults match `netclass_rules.yaml`'s real per-class values (R2/R3), and confirm end-to-end wiring (does it need `alternate_grid`'s multi-grid dict reshaped as `grids: dict[str, OccupancyGrid]`? — `_route_segment_3d`'s signature suggests yes, that reshaping is likely mechanical). Lower algorithmic risk than a fresh Option A build; the open question is integration cost, not correctness. |
   | **C. Extend THT-gated switching only, make it precise** | Keep transitions limited to real THT pad proximity (no arbitrary mid-trace vias at all), but fix the board-level `tht_locations` existence check to be a genuine per-point proximity check, and populate `via_positions` only for these THT-anchored transitions. | Smallest scope, no new via-legality engineering needed (the THT pad itself is already a legal, DRC-clean transition point). Likely insufficient alone: not every net has a THT pad nearby, so this wouldn't unlock general multi-layer routing for the corpus/production board's actual violation classes — probably a floor to build on, not a complete answer. |

   Given the finding above, **B now looks like the lower-risk path to a
   general solution** rather than the higher-complexity option a naive
   reading of the issue would suggest — but planning should still verify
   this at production scale before committing, since none of `_astar_search_3d`'s
   existing tests exercise anything close to a 95-net board. A blend (C as
   an immediate low-risk floor, B as the general mechanism once verified)
   is also a legitimate answer.

2. **Resolved by this document:** `RouteNode3D`/`_astar_search_3d` is not
   abandoned or broken work — it is complete, property-tested, and simply
   never connected to the production call site (see point 2 above). The
   remaining question for planning is narrower: why was it never wired in
   — was single-layer-first sequencing the only reason (in which case
   wiring it in now is low-risk), or was there a performance/correctness
   concern at the time that isn't recorded in the commit history (in which
   case Option B needs a scale/perf validation pass before being trusted)?
   No commit message or code comment found during this investigation
   explains the disconnection explicitly — planning should treat this as
   genuinely unknown rather than assume either explanation.

3. **What's the actual legality check for R3?** Via-to-via clearance,
   via-to-track clearance, and via-to-pad clearance from `netclass_rules.yaml`
   are known; is there an existing spatial-index/occupancy-grid primitive
   this can reuse (`constraints_spatial_index.py`?), or does it need new
   geometry?

4. **Sequencing R6 (relax the completion-preserving gate) — how is "proven
   safe" operationalized?** A specific before/after `kicad-cli pcb drc`
   comparison gate (matching R7), run in CI, before the gate relaxation
   merges? Planning should specify the exact measurement, not leave it to
   implementer judgment given this exact failure mode already happened
   twice.

## Evidence

- Issue #226: https://github.com/BennetLeff/temper/issues/226
- `packages/temper-placer/src/temper_placer/router_v6/channel_mapping.py` —
  `_assign_layer()`/`_ssot_layer_for_net()`, the completion-preserving gate
  (point 1).
- `packages/temper-placer/src/temper_placer/router_v6/astar_pathfinding.py` —
  `_astar_route_multilayer()` (THT-gated switching, always-empty
  `via_positions`, point 2, the production-wired mechanism);
  `_route_net_with_ripup()` (multilayer dispatch, confirmed to call
  `_astar_route_multilayer`, not `_route_segment_3d`).
- `packages/temper-placer/src/temper_placer/router_v6/astar_core.py` —
  `RouteNode3D`, `RoutePath3D`, `_astar_search_3d()`, `_route_segment_3d()`
  (complete, property-tested 3D via-aware search with zero production
  callers, point 2 — the central finding of this document).
- `packages/temper-placer/tests/router_v6/test_astar_metamorphic_pbt.py` —
  `test_3d_path_cells_free`, `test_3d_no_redundant_same_layer_nodes`
  (existing Hypothesis property tests for `_astar_search_3d`, none at
  production board scale).
- `packages/temper-placer/src/temper_placer/router_v6/via_placement.py` —
  `place_vias()`/`_place_vias_for_path()` (hardcoded via layer-span, point 3).
- `packages/temper-placer/src/temper_placer/router_v6/routing_results.py` —
  `CompiledRoute.vias`, `compile_routing_results()` (data reaches here,
  point 4).
- `packages/temper-placer/src/temper_placer/router_v6/adapter.py` —
  `_write_routes_to_content()` (never reads `.vias`, hardcodes `(layer
  "F.Cu")`, points 4-5).
- `packages/temper-placer/src/temper_placer/router_v6/pipeline.py` —
  `_run_stage4()`/`_run_stage5()` (real `layer_constraints` and via-sizing
  wiring, confirmed live).
- `packages/temper-placer/configs/netclass_rules.yaml` — per-class
  `via_diameter`/`via_drill` SSOT data.
- `packages/temper-placer/src/temper_placer/placer/cp_sat/gates.py` —
  `IECCreepageGate`, `StackupGate` (existing gates that activate for real
  vias for free).
- `docs/plans/2026-07-08-004-feat-4-layer-functional-stackup-plan.md` — W2
  U2 (layer assignment only, no via-insertion design).
- `docs/plans/2026-07-18-002-feat-board-routing-completion-plan.md` — U7
  audit that first surfaced the two-layer-mechanism question (partially
  superseded by this document's more precise five-point chain).
- Commits `d88e61d2`, `112df593`, `903dfaef` — the PR #220 wire → regress →
  revert sequence.
- `packages/temper-placer/tests/router_v6/test_via_placement.py` — existing
  test coverage for `place_vias()` (tests the legacy `RoutePath` fallback
  path, not the `RoutePath3D`/`via_positions` path this document's R1
  targets — a coverage gap worth noting for planning).
