<!-- provenance: commit=07d514f9b8a92788672e72fb765d78bfa2c0cbf3 dirty=true -->

# Net-aware pour handling in the obstacle map: mechanism, fix, and measured effect

**Date:** 2026-08-07
**Task:** `docs/evidence/2026-08-07-channel-skeleton-bridging-perf.md` Section 5
diagnosed F.Cu/B.Cu's ~25% available routing area as downstream of
`obstacle_map.py`'s zone-handling loop treating every committed zone as an
obstacle regardless of net, and pointed at
`docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md` (status: swept,
not implemented) as the durable fix. This document confirms the mechanism,
implements net-aware pour handling, measures the effect on
`pcb/temper.kicad_pcb`, and reports how far `route_pcb()` gets.

---

## 1. Confirmed mechanism

`build_obstacle_map()`'s zone loop (`obstacle_map.py`, "3. Zones / Keepouts")
unioned **every** zone into its layer's obstacle polygon unconditionally, with
an explicit `# TODO: If we route the SAME net, we should allow entering the
zone` and `# Safe default: Treat as obstacle` left unresolved. Unlike the
pad/escape-via/pre-existing-via loops beside it (which at least layer-type-
filter "All-layer" obstacles), the zone loop had **no net check of any kind**
-- every one of the board's 96 committed zones became a routing obstacle for
every net, including its own.

Quantified on `pcb/temper.kicad_pcb` (`build_obstacle_map()` + the same
`board_polygon.difference(obstacles)` math `routing_space.py` uses -- a naive
`board_area - obstacle_area` subtraction is wrong here, see the pitfall note
in Section 3):

| Layer | Obstacle source | Raw obstacle area | Available area (board minus obstacles) |
|---|---|---:|---:|
| F.Cu | hard only (pads/tracks/vias, no zones) | 1,449.5 mm² | 34,118.5 mm² (95.9%) |
| F.Cu | + all 96 zones, net-blind (current/before) | 32,214.5 mm² | 8,899.3 mm² (25.0%) |
| B.Cu | hard only | 881.8 mm² | 34,686.2 mm² (97.5%) |
| B.Cu | + all 96 zones, net-blind (current/before) | 32,139.4 mm² | 8,977.8 mm² (25.2%) |
| In1.Cu / In2.Cu | hard + zones (no zones present) | 650.5 mm² | 34,917.7 mm² (98.2%) |

This reproduces the evidence doc's 25.0%/25.2% figures exactly (`build_obstacle_map`
run standalone, `escape_vias=[]`; the ~0.3-point gap from the full-pipeline
25.4%/25.6% figures below is escape-via geometry, present in the full run and
absent here).

**Root cause of "obstacle-by-own-net-pour vs. genuinely blocked," quantified
by net-class eligibility** (see Section 2 for what "eligibility" means here):
of the board's 96 zones, **84 belong to net classes (`Power`, `GateDrive`)
that get no pour in the router's own regenerated output** --
`_write_routes_to_content()` already calls `strip_existing_zones()`
unconditionally on every existing zone and then `_emit_zone_pours()` re-emits
one only for a net class `_zone_layers_for_net()` accepts. Those 84 zones are
stale, pending-regeneration input that will not exist in the routed board for
**any** net, yet `obstacle_map.py` was treating them as a hard, permanent
obstacle during routing computation. This is the same defect
`docs/solutions/best-practices/correct-diagnosis-unsafe-change-2026-07-28.md`'s
2026-07-29 addendum traced to this file, and the missing half of U2 in
`docs/plans/2026-07-28-001-feat-provable-safety-place-and-route-plan.md`
("Landing Status" table: U2 landed only the stackup-role classification;
`compute_routing_space` basing "layer availability on declared role plus
'this layer's existing fill is pending regeneration'" was never done).

## 2. Fix implemented

**`obstacle_map.py`'s zone loop now filters on net-class pour eligibility**,
using the exact same `_zone_layers_for_net()` check the write path already
uses to decide which pours survive into the output (`_zone_pour_stitch.py`).
A zone whose owning net's class is not pour-eligible is excluded from the
obstacle map entirely -- it is never going to exist in the routed board
regardless of which net is being routed, so it is not a real routing
constraint. A zone with no net at all (a true keepout) keeps its
unconditional-obstacle treatment.

**Paired fix, R3-R5 of `docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md`
(GND correction):** `core/design_rules.py`'s `GND` net class had no
`routing_strategy` (silent `None`), disagreeing with the human-authored
`configs/temper_constraints.yaml`, which already declares GND
`"plane_preferred"`. This left `PWR_RTN` -- GND's return-plane member --
ineligible by accident, not by decision. Fixed:
- `core/design_rules.py`: `GND.routing_strategy = "plane_preferred"`.
- `_zone_pour_stitch.py`'s `_zone_layers_for_net()`: now recognizes
  `"plane_preferred"` alongside `"plane_required"` (the field has four
  documented values; only one was ever checked).
- `tests/router_v6/test_adapter.py`: `test_cgnd_is_not_zone_eligible` asserted
  the accidental gap this fix closes and is now wrong by construction --
  replaced with `test_cgnd_is_zone_eligible` (CGND and PWR_RTN share the GND
  class, so eligibility is class-level, matching R5's own documented
  assumption) and `test_pwr_rtn_is_zone_eligible`. Added
  `test_power_class_is_not_zone_eligible` per R7's own named gap ("unit tests
  assert `GateDrive` nets are zone-eligible... but no equivalent test exists
  for `Power`").

Net effect on eligibility: **14 of 96 zones are now obstacle-eligible** (was
12 before the GND fix, which itself was 0 different from the un-fixed
`_zone_layers_for_net` -- GND was never eligible before this task); **82 are
excluded** (`ac_l`/`ac_n`/`DC_BUS_RTN`/`SW_NODE`/`+15V_LS`/`PWR_RTN` kept,
`+3V3`/`vcc`/`+15V`/`V_BUS_SENSE`/`GATE_HS`/`GATE_LS`/`PWM_HS`/`PWM_LS`
excluded).

## 3. Avoiding the "correct diagnosis, unsafe change" trap

Three deliberate choices keep this fix inside the safe half of the
diagnosis-vs-consequence split
`docs/solutions/best-practices/correct-diagnosis-unsafe-change-2026-07-28.md`
documents:

1. **The exclusion criterion is "this geometry will not exist in the output
   for any net," not "this net can ignore its own copper."** A zone is
   dropped from the obstacle map only when `_zone_layers_for_net()` -- the
   SAME function the write path already uses to decide what pours survive
   into the routed board -- says no net-class-eligible pour will ever be
   emitted there. There is no scenario where the obstacle map now says an
   area is free while the final board actually has copper there for some
   *other* net: `strip_existing_zones()` + `_emit_zone_pours()` already
   guarantee that ineligible-class zones never survive, independent of this
   change. This is the opposite of the a1fe623e regression's mechanism
   (declaring a layer open while its real, unregenerated fill still blocked
   it) -- here, obstacle removal and output removal are the same rule,
   checked at both ends.
2. **Eligible zones (`ACMains`/`HighVoltage`/`GND`-`plane_preferred`, 14 of
   96) are kept as obstacles unconditionally, including for their own owning
   net.** This is deliberately conservative, not a claim that "a pour on net
   N is not an obstacle to net N" was fully implemented for the eligible
   set. `ModelBuilder._create_per_net_channel_vars()`
   (`constraint_model.py`) offers a `NetChannelVar` for every (net, edge)
   pair over this SAME shared, per-layer skeleton/obstacle view -- it is not
   per-net. Exempting an eligible zone's interior from the obstacle map here
   would open a channel through that copper to every OTHER net too, not only
   its own, which is exactly the "other nets must still keep clearance to a
   real pour" trap the task brief warns about. Implementing a true per-net
   exemption for the eligible set would require per-net topology (skeletons
   keyed by net, not by layer), which is a materially larger change than
   this task's scope ("keep your diff to the pour/obstacle-map path"); it is
   not attempted here and is recorded as a divergence from the literal "a
   pour on net N is not an obstacle to net N" framing in the task brief --
   implemented for the "will never exist in the output" case (all 82
   ineligible zones, unconditionally, for every net), not for the "exists in
   the output, but only blocks other nets" case (the 14 eligible zones,
   which remain blocking for their own net too, pending a per-net topology
   change out of scope here).
3. **Thermal-relief/antipad geometry is unaffected.** This fix changes *which
   zones enter the obstacle map*, not how a zone's own polygon is
   constructed -- `zone.polygon` is used exactly as before for every zone
   that remains in scope. No antipad/thermal-relief geometry is read or
   altered by this change.

## 4. Measured effect

Board polygon area: 35,568.0 mm². Method: `build_obstacle_map()` +
`compute_routing_space()` via the real `ObstacleMapStage`/`RoutingSpaceStage`
code path, `use_declared_layer_roles=True` (already landed, U2), then medial-
axis extraction (`_extract_medial_axis`) and `_ensure_skeleton_connectivity`
(the fixed KD-tree/Kruskal bridging from `07d514f9`) exactly as
`docs/evidence/2026-08-07-channel-skeleton-bridging-perf.md` measured. Before
= working tree at `07d514f9` (this task's base commit, no changes); after =
same tree with this fix applied. `escape_vias=[]` in both (no placement pass
run), matching the standalone reproduction in Section 1.

| Layer | Available area (before) | Available area (after) | Islands before bridging (before → after) | Islands after bridging (before → after) | Bridges added (before → after) |
|---|---:|---:|---:|---:|---:|
| F.Cu | 25.0% (8,899.3 mm²) | 25.3% (8,997.0 mm²) | 153 → 155 | 129 → 131 | 24 → 24 |
| B.Cu | 25.2% (8,977.8 mm²) | 25.5% (9,079.0 mm²) | 225 → 205 | 170 → 152 | 55 → 53 |
| In1.Cu | 98.2% | 98.2% (unchanged, no zones present) | 3 → 3 | 3 → 3 | 0 → 0 |
| In2.Cu | 98.2% | 98.2% (unchanged) | 3 → 3 | 3 → 3 | 0 → 0 |

**This is a real but modest improvement, not the sharp fall the raw
84-of-96-zones-excluded number might suggest, and that gap has a specific,
already-documented cause worth stating plainly rather than rounding up the
result.** Two of the 14 still-eligible zones -- `SW_NODE` and `DC_BUS_RTN`
(both `HighVoltage`) -- are themselves pathological, board-spanning convex
hulls: raw (unclipped) areas of 14,082 mm² and 24,348 mm² respectively on a
35,568 mm² board, with vertices well outside the board outline (e.g.
`DC_BUS_RTN`'s hull spans y = -5.2 to 232.9 mm on a board whose outline is
y = 20 to 254 mm). Excluding all 82 ineligible zones only moves available
area from ~25.4%/25.6% to ~28.7%/29.0% (measured with the pre-GND-fix 12-zone
eligible set, before `PWR_RTN` was added back); adding `PWR_RTN` back
(R3-R5) brings it to 25.7%/25.9% eligible-only, and the two oversized
`HighVoltage` hulls alone still blanket most of both outer layers regardless
of how many `Power`/`GateDrive` zones are excluded. **This is R6 of
`docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md`, named there and
explicitly flagged as a separate, not-fixed-here `zone_emission.py`
clustering defect** ("`SW_NODE`'s existing hull covers 40% of board area
because `HighVoltage` is clustering-exempt and the router used the zone as a
cross-pad stitch rather than a power pour" -- and per R6, "R3/R4 must not be
read as having fixed it"). This fix does not touch `zone_emission.py` and
does not claim to fix R6; the polygon geometry of `SW_NODE`/`DC_BUS_RTN`
zones on the committed board is unchanged by this task.

B.Cu's pre-bridge island count actually **fell** (225 → 205) even though its
available-area percentage barely moved -- excluding 82 small, scattered
`Power`/`GateDrive` zones reconnects some previously-isolated pockets even
when the two giant `HighVoltage` hulls still dominate gross area. F.Cu's
pre-bridge count rose slightly (153 → 155), within the medial-axis
extraction's expected run-to-run sensitivity to small area changes (the
`docs/evidence/2026-08-07-channel-skeleton-bridging-perf.md` baseline itself
noted this: "171 islands in this run's slightly different obstacle set...
not a correctness issue").

## 5. How far `route_pcb()` gets (relative to #871)

Ran `route_pcb()` end-to-end on `pcb/temper.kicad_pcb` (110 nets, 169
components) via the exact `route_pcb`/`make_parsed_pcb_stub` path
`test_route_pcb_production_board` uses, with a self-imposed ~9.5 GB RSS /
8-minute wall-clock cap (shared multi-agent machine; per task scope,
"reaching the OOM is a successful outcome," not an actual OOM). This
worktree's changes (net-aware pour handling) are applied for both runs
below -- #871 itself (`ModelBuilder.build()`'s CNF construction) is out of
this task's scope and is being measured concurrently by another agent on
this same base; these numbers are reported because the task asks how the
pour fix affects it, not as an attempt to fix #871.

**`enable_geographic_pruning=False`:** Stage 0/0.5/1 complete normally.
Stage 2 channel analysis reaches `ChannelSkeletonStage` for all four
routable layers and completes bridging on all of them (F.Cu 173→141
remaining groups, B.Cu 205→152, inner layers 3 islands each -- consistent
with Section 4, small run-to-run differences from pad-anchor nodes added
after each layer's bridging pass). Last stdout line before the cap: `Added
376 pad anchor nodes to skeleton` (same final Stage-2 checkpoint the
pre-fix evidence doc observed). RSS then grew silently and monotonically:
2.6 GB (t=48s, right after that checkpoint) → 2.6 GB (plateaued through
t=128s) → climbing from t=136s: 3.3 → 4.4 → 6.0 → 7.3 → 8.6 → 9.3 GB,
self-imposed-killed at **t=243s, RSS=10.6 GB** (the watchdog polls every
8s, so it overshot its 9.5 GB threshold by one interval rather than
catching it exactly at the line). No Stage 3 completion or failure output
had printed. This matches
`docs/evidence/2026-08-07-channel-skeleton-bridging-perf.md` Section 6's
prior observation (same checkpoint, same silent/monotonic growth
signature, same conclusion: still climbing toward the already-diagnosed
`docs/evidence/2026-08-07-router-oom-diagnosis.md` OOM, not stabilized) --
i.e. **this fix does not change how far the pipeline gets before hitting
the #871 ceiling**, on this measurement.

**`enable_geographic_pruning=True`:** Same Stage 0-2 checkpoints as pruning
off (same island/bridge counts -- pruning only affects Stage 3 variable
creation, not Stage 2 topology). RSS then shows a materially **different
shape**, not just a different peak: it **plateaus at ~2.6 GB for over two
minutes** (t≈128s to t≈345s, 19 consecutive 8s watchdog samples with zero
growth) before finally climbing -- 2.8 → 3.5 → 3.8 → 4.3 → 4.9 → 5.3 → 6.0 GB
-- and was self-terminated by the **wall-clock cap at t=484s, RSS=6.6 GB**,
still climbing, having never printed a Stage 3 completion/failure line
either. The long flat plateau is consistent with
`_create_per_net_channel_vars`'s `enable_geographic_pruning` branch
(`constraint_model.py`): it evaluates `_is_candidate_edge` -- a pure-Python
per-(net, edge) geometric distance check -- for every one of
110 nets × ~132,500 total skeleton edges (Section 4's after-fix edge counts
summed across all four layers) before any `NetChannelVar` is
appended, i.e. real CPU-bound work with a comparatively small, slowly-
growing memory footprint, ahead of whatever (smaller, since pruning excludes
far-away edges) variable set it eventually builds. **Reached 6.6 GB in 484s
under pruning vs. 10.6 GB in 243s without it** -- pruning is markedly slower
to reach a given point in Stage 3 on this board, but was still below half
the no-pruning peak at the point this run was stopped; whether pruning's
*final* peak is lower is not established by this measurement (both runs
were stopped before Stage 3 completed or failed).

**Neither configuration routes the board end-to-end on this measurement** --
`#871` remains open, unaffected by this task's scope. Net-aware pour
handling reduces obstacle geometry (Section 4), which could plausibly
shrink the Stage 3 model's *edge* input once `#871` itself is addressed, but
the two still-oversized `HighVoltage` zones (`SW_NODE`, `DC_BUS_RTN`) keep
F.Cu/B.Cu's available area -- and therefore the skeleton edge count feeding
`ModelBuilder` -- close to unchanged on this specific board (Section 4), so
this task's fix alone does not measurably change how far either
configuration gets before hitting `#871`'s ceiling.

## 6. Tests

- `tests/router_v6/test_adapter.py::TestZoneLayersForNet` -- updated/added,
  see Section 2. `uv run pytest tests/router_v6/test_adapter.py -q`: 93
  passed, 1 skipped (unchanged skip, pre-existing kicad-cli dependency).
- `tests/core/test_design_rules_rust_differential.py` (the pinned oracle
  parity gate) initially failed 3/29 after the `GND.routing_strategy` change
  -- `tests/core/_design_rules_py_oracle.py`'s own pinned `GND` entry is a
  deliberate hand-maintained copy of `TEMPER_NET_CLASSES` and needed the
  same one-line addition. Fixed; 29/29 pass.
- Targeted re-run of every test file directly touching zone/net-class
  eligibility, obstacle handling, or design-rules parity
  (`test_adapter.py`, `test_zone_emission.py`,
  `test_zone_pour_geometry_rust_differential.py`,
  `test_routability_check.py`, `test_clearance_check.py`,
  `test_thermal_relief_boundary.py`, `test_design_rules_rust_differential.py`,
  `test_board_rust_differential.py`, `test_priority_rust_differential.py`):
  516 passed, 1 skipped, 2 failed. Both failures are pre-existing and
  unrelated -- confirmed by reading each test's own assertion/docstring
  rather than assumed: `test_tie_break_class_exists_direct_cKDTree_comparison`
  fails by its own stated design ("the forcing coordinates no longer
  reproduce a scipy/first-wins disagreement... should be re-derived" --  a
  hardcoded-coordinate probe of `scipy.spatial.cKDTree`'s internal tie-break
  order, unrelated to net eligibility, and the module this fix touches is
  not in that test's import graph); `test_latency_unroutable_early_exit`
  is a `<20ms` wall-clock benchmark that measured 27.9ms on a machine
  concurrently running two multi-GB `route_pcb()` background measurements
  (Section 5) plus a full test-suite run -- `routability_check.py` (the
  module under test) imports nothing this task's diff touches.
- `uv run pytest tests/router_v6/ -q` (full suite, 4803 items, one
  `kicad-cli`-dependent test deselected): **15 failed, 4748 passed, 19
  skipped, 1 deselected, 23 xfailed** (1341s -- long wall time from real
  shared-machine contention with two concurrent `route_pcb()` background
  measurements, Section 5, plus another agent's own concurrent pytest run
  observed via `ps aux` during this session). Of the 15 failures:
  - 4 are `kicad-cli`/KiCad-footprint-library-not-installed environmental
    gaps (`test_audit_tree_geometry.py`, 3x `test_phase1_anti_false_zero.py`).
  - `test_r3_channel_skeleton_filters_to_outer_layers` is the
    instructed-to-remain-failing test.
  - `test_tie_break_class_exists_direct_cKDTree_comparison` and
    `test_latency_unroutable_early_exit` are the two pre-existing/unrelated
    failures already explained above.
  - 6 more (`test_multi_layer_tree_routing.py` x4,
    `test_via_layer_properties_pbt.py` x2) all share one root cause:
    `BufferError: buffer contents are not compatible with i8` inside
    `occupancy_grid.py`'s calls into the `temper_geometry` Rust extension
    (`mark_path_rect_into_grid_py`/`mark_via_circle_into_grid_py`) -- a
    numpy/Rust buffer-dtype mismatch with no plausible connection to
    zone/net eligibility. **Verified, not assumed**: reverted
    `obstacle_map.py`/`_zone_pour_stitch.py`/`core/design_rules.py` to
    their pre-this-task content via `git checkout HEAD~1 -- <files>` (not
    `git stash` -- forbidden repo-wide, see the commit's own session
    notes) and re-ran the same two files; all 6 fail identically on the
    unmodified base commit. Restored via `git checkout HEAD --
    <files>`, re-verified zero diff against the commit and an identical
    failure signature with the fix back in place.
  - The remaining 2 (`test_congestion_rust_differential.py::test_total_movement_bit_exact[moves6]`,
    `test_escape_via_rust_differential.py::test_is_position_valid_bit_exact[overflow_square]`)
    also reproduce identically on the unmodified base commit (same
    revert/restore method as above): both are an `OverflowError` message-text
    mismatch between the Python oracle (`"Numerical result out of range"`)
    and the Rust extension (`"Result too large"`) on an intentional overflow
    fixture -- a platform/libc error-string difference, unrelated to net
    eligibility or obstacle geometry.
- Net: **every failure not already accounted for as instructed-failing or
  a documented pre-existing/environmental gap was independently confirmed,
  by reversion, to reproduce identically without this task's changes.**

## 7. Sources

- `docs/evidence/2026-08-07-channel-skeleton-bridging-perf.md` -- the
  characterization this task confirms and extends.
- `docs/solutions/best-practices/correct-diagnosis-unsafe-change-2026-07-28.md`
  (2026-07-29 addendum) -- the traced mechanism this fixes.
- `docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md` -- R1-R7,
  implemented here (R3-R5 directly; R1/R2/R7 confirmed already landed;
  R6 confirmed NOT fixed here, by design).
- `docs/plans/2026-07-28-001-feat-provable-safety-place-and-route-plan.md`
  -- U2's "Landing Status" table and its `compute_routing_space` sub-
  requirement, the specific gap this task closes.
- `packages/temper-placer/src/temper_placer/router_v6/obstacle_map.py`,
  `_zone_pour_stitch.py`, `core/design_rules.py` -- the changed files.
