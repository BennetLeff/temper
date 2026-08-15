<!-- provenance: commit=1d6aa40200df96978ef44e352cab201e0885f5f9 (fix/router-nlayer-routing, worktree
/home/bennet/Desktop/temper-worktrees/router-nlayer-routing, branched from fix/layer-architecture-ssot
commit eaef53cbf). pcb/temper.kicad_pcb sha256=1b15b2747ff55977bd45154e23200c7feaf137e927c4fb9f59d27b2e4c4ade0d
-- UNCHANGED by this task throughout (verified before and after every measurement below; routing output
went to scratch_out/temper_routed_nlayer.kicad_pcb sha256=ad537ab044be14fb5f170adcc7d50c03e60a1e33cd5da4ca85bca9ef8da1c172,
never committed, never overwriting the tracked board). elec/build/default.net sha256=
5887b2377a1371b3bb082eaefa1132c5dc5cb9b9bcb9732d781343bfe99853f8, confirmed identical to the main
checkout's after `diff -r` on elec/src came back empty -- not regenerated. kicad-cli 10.0.5. Single agent,
no subagents dispatched. -->

# Router N-layer routing: the plumbing works, genuine pad connectivity does not improve, and a real copper-weight width gap is now live

**Verdict up front.**

1. **The 6-layer stackup decision (PR #1178) is no longer inert.** `scripts/route_board.py --net-batching --batch-size 10` against the unmodified committed board now emits real copper on all four declared signal layers: **segments** F.Cu 2076 / In3.Cu 1551 / In4.Cu 1138 / B.Cu 1349 (6114 total); **vias** 74 total, only 10 of them plain F.Cu↔B.Cu through-vias -- the other 64 are blind vias touching In3.Cu or In4.Cu; **zones** exactly 40 per layer × 4 layers = 160. PR #1193's measurement (100% of 3331 segments/26 vias/80 zones on F.Cu/B.Cu, zero on the new layers) does not reproduce on this branch.
2. **Root cause, confirmed by code inspection, not assumption:** `core/board_layer_roles.ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED` stayed frozen at `("F.Cu", "B.Cu")` after PR #1178 declared `In3.Cu`/`In4.Cu` signal, so it never propagated to any call site reading through it -- including `_zone_pour_stitch.py`, which already did. Underneath that, the actual production hot path (`_pipeline_route._run_stage4`) never even reached the accessor: it unconditionally called `select_routing_grids()` + `run_astar_pathfinding()`, whose signature caps pathfinding at exactly `(grid, alternate_grid)` -- two grids, full stop -- regardless of how many occupancy grids Stage 2 built. Stage 2 (`routing_space.py`/`occupancy_grid.py`) was already genuinely N-layer (one grid per declared signal/mixed stackup layer, no hardcoded name). A tested, N-layer-generic A* driver already existed (`_astar_nlayer.py`, `spike/nlayer-via-astar`) but was gated behind `enable_nlayer_astar_spike`, default `False`, never flipped for production. Full inventory in §1.
3. **Pad-to-pad connectivity is flat, not improved: 52/139 vs the 2-layer baseline's 53/139** (`pad_connectivity_audit.audit_pcb_file`, the same tool PR #1193 used). The honest/fake split moved sharply the wrong way: honest-gap (net gets zero copper, an honest fail) dropped 40→16, but fake-completion (copper exists, does not join every pad) rose 46→71. More channel capacity let more nets get *partial* A* success across layers, not more nets get *complete* success. §3.
4. **A real, live copper-weight gap:** `trace_width_assignment.py` derives trace width purely from net-name keyword classification (power/HV/default) with zero reference to which physical layer a segment lands on -- so it cannot apply PR #1153's 1oz-inner/2oz-outer distinction. This is not theoretical: `power_in.bypass_relay-coil1`, `-coil2`, and `power_in.q_relay_drv-g` are routed at 0.508mm (the "power" width constant, calibrated for 2oz copper) on **In3.Cu, which is 1oz**, in this actual run. §4.
5. **`courtyards_overlap` unaffected (8 before, 8 after)** -- expected, since courtyard collisions are a placement property, not a routing one; this is a sanity check, not a routing-quality claim. **`clearance` is inconclusive from this pass alone**: kicad-cli reports 500 (committed board) vs 501 (this run), both sitting on/near the ~499-513 reporting ceiling documented in `docs/evidence/2026-08-12-uncapped-drc-measurement.md` -- a real delta requires that session's full partition-and-sum, not attempted here for time. §5.
6. **No DRU/clearance/creepage threshold was changed. No ceiling in `power_pcb_dataset/drc_ceiling.json` was touched.** `pcb/temper.kicad_pcb`'s sha256 is unchanged throughout (verified before and after every measurement in this document).

---

## 1. Inventory: every site that decides which layers are routable

Searched `router_v6/*.py` for hardcoded `"F.Cu"`/`"B.Cu"` literals (29 files matched at least one occurrence) and classified each by whether it is a genuine routability decision or an incidental default/doc-comment/via-geometry-syntax reference.

**Genuine routability decision points (fixed this session):**

| site | what it decided | fix |
|---|---|---|
| `core/board_layer_roles.py: ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED` | the SSOT itself | widened `("F.Cu","B.Cu")` → `("F.Cu","In3.Cu","In4.Cu","B.Cu")` |
| `router_v6/grid_prep_stage.py:43,72,100` | per-layer occupancy-grid construction (Stage 4's `GridPrepStage`, confirmed dead in the live call graph today -- see below -- but named explicitly in this task and real infrastructure other refactors could revive) | reads `board_layer_roles.routable_signal_layers_from_path(pcb.source_path)`, falls back to the SSOT constant only when no real file is on disk |
| `router_v6/_astar_nlayer.py:156` (`select_routing_grids_nlayer`'s `preferred_order`) | tie-break/preference ordering only (the function already returned every grid handed to it -- this line never restricted *which* layers, only which came first) | reads `ENGINE_SUPPORTED_SIGNAL_LAYERS_ORDERED` |
| `router_v6/_pipeline_route.py: _run_stage4` | **the actual production hot path** -- see §2 | filters Stage 2's occupancy grids to `routable_signal_layers_from_path(pcb.source_path)`, then routes through the N-layer A* whenever more than 2 routable layers are available (no longer gated behind `enable_nlayer_astar_spike`, though that flag still forces the N-layer path on a 2-layer board if set) |
| `router_v6/_zone_pour_stitch.py: _zone_layers_for_net` | which layers a `plane_required`/`plane_preferred` net's zone gets poured on | already read the SSOT (PR #1178); now also filters the returned list against the routed board's *own* declared stackup layer names (via the `pcb` `_emit_zone_pours` already receives), so a board whose inner layers are named differently than the production board's (`In1.Cu`/`In2.Cu` instead of `In3.Cu`/`In4.Cu`, e.g. `pcb/benchmarks/temper_fixture_33.kicad_pcb`) never gets a phantom zone on a layer name it doesn't declare |

**Confirmed genuinely N-layer already, no hardcoded name found (verified by reading the implementation, not inferred):**

- `routing_space.py: compute_routing_space` -- iterates `pcb.stackup.layers`, includes every `layer_type in {"signal","mixed"}`. No per-name literal.
- `occupancy_grid.py: build_occupancy_grid` / `OccupancyGridStage` -- one grid per `RoutingSpace`, keyed by whatever `layer_name` that routing space carries.
- `obstacle_map.py: build_obstacle_map` -- THT/all-layer pads and escape vias are added to every `layer_info.name` in `pcb.stackup.layers` whose type is signal/mixed; net-aware zone obstacle handling is likewise layer-name-agnostic.
- `astar_core._route_segment_3d` / `_astar_search_3d` -- accepts an arbitrary-size `grids: dict[str, OccupancyGrid]`, costs a layer transition (via) generically. This is the "N-layer" in `_astar_nlayer.py`'s name; the search core needed no changes, only its 2-grid-capped callers did.
- `via_placement._place_vias_for_path` -- already derives each via's `from_layer`/`to_layer` from the path's own actual routed segment layers (`temper_geometry.via_layer_pair_py`), not a hardcoded pair (a prior "U3" fix, predates this session).
- `creepage_check.py` -- same-layer aggregation groups by whatever `layer` string the segment carries; no hardcoded name.
- `pad_connectivity_audit.py` -- union-find's `layer_universe` is built from the layer strings actually present in segments/pads/vias, not a fixed set. This is the audit tool itself; its honesty does not depend on this session's fix.

**Genuinely 2-layer/4-layer-only, named as the task asked (not fixed this session -- see §6 for why each is deferred, not just skipped):**

- **`router_v6/layer_assignment.py`'s `Layer` enum** (`L1_TOP=1, L2_GND=2, L3_PWR=3, L4_BOT=4`), rigidly 1:1 mapped to `F.Cu/In1.Cu/In2.Cu/B.Cu`, and the Rust mirror in `temper-orchestration/src/channel_mapping.rs`'s `_LAYER_ENUM_TO_KICAD`/`ssot_layer_for_net_impl` (only recognizes enum values 1 and 4). This drives `channel_mapping._assign_layer`'s **soft preferred-layer heuristic** for a net -- it can only ever resolve to `F.Cu` or `B.Cu`. Verified this is a soft hint, not a hard cap: `_astar_route_nlayer`'s tiers 2/3 try every other available grid regardless of what tier 1's preferred layer was (confirmed empirically -- §1's copper distribution above has substantial In3.Cu/In4.Cu occupancy despite this). Also verified inert today: no entry in `packages/temper-placer/configs/netclass_rules.yaml`'s `layer:` field names anything but `F.Cu`/`B.Cu`/`In1.Cu`.
- **`kicad_connectivity.py: _layer_id`** -- `return 0 if layer_name == "F.Cu" else 1  # coarse; full stackup deferred`, collapsing every non-F.Cu layer into one bucket for the post-write connectivity preflight. This is a real correctness gap for a 4-signal-layer board (two same-"bucket" segments on different real layers would misreport as touching), but its caller (`connectivity_preflight`) is gated behind `enable_connectivity_verifier`, default `False`, not exercised by `route_board.py`'s production call and confirmed not the tool this document's own connectivity numbers came from (`pad_connectivity_audit.py`, verified layer-agnostic above).
- **`copper_balance.py: _LAYER_ORDER_NAMES`** -- derives from `core.board.STANDARD_LAYER_ORDER`, a canonical 4-layer enumeration used only for copper-balance/manufacturing-report tooling. Gated behind `enable_manufacturing_drc`, default `False`, not part of the routing decision path.

**Confirmed NOT a routability decision (via-geometry syntax, correctly 2-element by KiCad's own format, not a bug):** `_ground_plane.py`/`_power_islands.py`'s `(layers "F.Cu" "B.Cu")` via emission literals are the KiCad through-via span syntax (a mechanically-drilled through-hole via always spans outermost-to-outermost and electrically contacts every copper layer between, including inner ones, without needing to name them) -- unrelated to which layers the router may route traces on. `annular_ring_check.py`'s `_EXTERNAL_LAYERS = {"F.Cu", "B.Cu"}` correctly means "the two *external* layers" (a real, board-size-independent DRC distinction: external-layer annular ring rules differ from internal), not "the two routable layers" -- not a bug.

---

## 2. Why the production path was still 2-layer-capped despite Stage 2 already being N-layer

`RouterV6Pipeline._run_stage4` (`_pipeline_route.py`) constructs a fresh `Stage4Orchestrator` and calls only its **static** `assemble_pathfinding_result(state)` method -- which does nothing but `return getattr(state, "pathfinding_result", None)` on a `state` that was never run through `Stage4Orchestrator.run()` (that would execute `GridPrepStage`/`RouteStage`, the ones hardcoding `("F.Cu","B.Cu")` per §1's table). So `pathfinding_result` is `None` unconditionally at that call site, and every real route always fell through to:

```python
if pathfinding_result is None and self.enable_nlayer_astar_spike:   # default False
    ...  # the N-layer path -- never reached in production
elif pathfinding_result is None:
    fcu_grid, bcu_grid = select_routing_grids(stage2.occupancy_grids)
    pathfinding_result = run_astar_pathfinding(channel_mapping, fcu_grid, ..., alternate_grid=bcu_grid, ...)
```

`select_routing_grids`/`run_astar_pathfinding`'s signature is `(grid, alternate_grid)` -- exactly two, always, regardless of how many grids `stage2.occupancy_grids` actually held. Confirmed empirically before making any change: `stage2.occupancy_grids` on the current board (parsed with `use_declared_layer_roles=True`, what `net_batching.py`'s production worker path uses) already contained a grid for **all six** physical copper layers, because the structural-position stackup heuristic (`_extract_stackup`) classifies every non-outer layer `"mixed"` when nothing is poured on it yet -- which includes `In1.Cu`/`In2.Cu`, the two layers declared `power`. `routing_space.py`'s filter (`layer_type in {"signal","mixed"}`) does not distinguish "mixed because nothing's poured yet" from "genuinely meant for point-to-point signal routing," so simply widening the grid *count* passed to A* without also filtering by the board's *declared* signal-layer set would have let ordinary signal traces land on the GND/PWR plane layers.

This is exactly the two-accessor split `board_layer_roles.py`'s own docstring argues for (declared-architecture `signal_layer_names` vs. routable-today `routable_signal_layers`) -- `_run_stage4` now filters `stage2.occupancy_grids` through `routable_signal_layers_from_path(pcb.source_path)` (reading the board's own `(layers ...)` role tokens directly, not the zone-content heuristic) before ever calling the grid selector, so `In1.Cu`/`In2.Cu` are excluded regardless of what Stage 2 happened to classify them as, and route through the N-layer A* (`_astar_nlayer.py`, already tested, already existed) whenever more than 2 routable layers survive that filter.

---

## 3. Connectivity measurement: same tool, before/after

`scripts/route_board.py --pcb pcb/temper.kicad_pcb --output scratch_out/temper_routed_nlayer.kicad_pcb --net-batching --batch-size 10` (matching PR #1193's invocation exactly), 483.2s wall.

**Topology/Stage-4 level** (route_board.py's own trace): 97/106 attempted nets solved (91.5%), segments=6114 vias=74 zones=160. 12/12 net-batching batches solved at batch level, 0 crashed. Only 9 nets fully unrouted: `+3V3, RELAY_CTRL, RTD_SCK, WDT_RESET_N, discharge.r_snub2-p2, s1, safety.fault_or-y2, safety.ovp.r_adc_top1-p2, sdi`.

**Pad connectivity** (`pad_connectivity_audit.audit_pcb_file` -- the same tool, same audit path PR #1193 used, `fully_connected`/`is_fake_completion`):

| | 2-layer baseline (PR #1193, cited) | this run |
|---|---:|---:|
| fully pad-connected | 53/139 | **52/139** |
| fake-completion | 46 | **71** |
| honest-gap | 40 | **16** |

Fully-connected count did not improve -- it is flat within one net, arguably one worse. What moved is the *composition* of the non-connected 87/86 nets: far fewer report an honest zero-copper failure, far more report copper that exists but does not join every one of the net's own pads. Concretely, `power_in.bypass_relay-coil1/-coil2/-q_relay_drv-g`, `hb.gate_hs.driver-p1`, and most of the `discharge.*` family appear in the fake-completion list at 2-4 fully-formed segments per net, on `In3.Cu`/`In4.Cu` -- real copper genuinely present on the new layers, genuinely not completing the net.

**Reading this honestly, not spun:** raw channel capacity was not the (sole) binding constraint. Four times the signal-layer area let Stage 3's SAT solver commit to far more nets (91.5% vs the topology-level rate implied by the 2-layer baseline's far larger unrouted/orphaned set) and let Stage 4's A* place real copper for most of them -- but a large fraction of those multi-layer paths do not complete to every pad. The 3-tier cascade in `_astar_route_nlayer` (same-layer 2D → whole-segment-detour-on-another-layer 2D → full via-aware 3D) tries hard per *segment*, but a channel-path's *waypoint chain* is still assembled per Stage 3's SAT topology output; a topology that routes through channels on a layer whose actual A* occupancy differs from what the SAT solver's channel-capacity model assumed can produce a chain where individual segments each succeed locally (hence real copper, hence not an honest gap) while the chain as a whole never reaches every one of the net's pads (hence fake-completion, not full connectivity). This is consistent with §5's hard-constraint framing: "more layers may not help every net" -- it did not help *this* board's net-completion figure at all, on this run.

---

## 4. Copper-weight width gap: real, live, not fixed this session

PR #1153 declared inner layers 1oz vs. outer 2oz; PR #1188 established `hb-gnd` needs 4.77mm at 2oz for its current rating. `trace_width_assignment.py`'s `assign_trace_widths`/`_determine_trace_width` (delegating to `temper_geometry.determine_trace_width_py`) computes a net's width from **net-name keyword classification only** (`default_width`/`power_width`/`hv_width`) -- no parameter, anywhere in the call chain, carries which physical layer the segment will land on. This means the width derivation cannot apply PR #1153's copper-weight distinction even in principle.

Checked whether this is theoretical or live in this actual run: it is live. `power_in.bypass_relay-coil1`, `power_in.bypass_relay-coil2`, and `power_in.q_relay_drv-g` are emitted at 0.508mm (the `power_width` constant, sized for 2oz copper) with segments on **In3.Cu (1oz)** in `scratch_out/temper_routed_nlayer.kicad_pcb`. A 1oz trace at a 2oz-calibrated width carries meaningfully less current for the same temperature rise (roughly proportional to copper cross-section, so roughly half, before IPC-2152's non-linear width/current relationship). This is a genuine, safety-relevant sizing gap on a mains-adjacent relay-drive circuit, not a style nit -- and it is now reachable in production precisely because this session's fix lets the router place copper on 1oz layers at all. `hb-gnd` itself stayed on B.Cu (2oz, outer) in this run and does not currently exercise the gap, but nothing in the width-assignment code prevents it from landing on an inner layer on a future run (net ordering/net-batching are not guaranteed stable across runs).

Not fixed here: correctly threading per-segment layer (and therefore per-layer copper weight) into `assign_trace_widths` -- and deriving the actual IPC-2152 width-vs-current relationship per copper weight, not just picking a bigger constant -- is separate, safety-relevant engineering, not a quick patch, and out of scope for a routing-plumbing task. Flagged per this task's own hard-constraint #6 instruction.

---

## 5. DRC deltas

**`courtyards_overlap`:** 8 (currently-committed `pcb/temper.kicad_pcb`) vs. 8 (`scratch_out/temper_routed_nlayer.kicad_pcb`), via `kicad-cli pcb drc --format json`. Identical, as expected -- courtyard overlap is a component-placement property; this run did not move any component. Reported as a sanity check (routing did not somehow perturb placement-derived violations), not a routing-quality signal.

**`clearance`:** kicad-cli reports 500 (committed board) vs. 501 (this run) -- both sitting at/near the ~499-513 reporting ceiling `docs/evidence/2026-08-12-uncapped-drc-measurement.md` already proved is a cap, not a true count (that session's own partition-and-sum found the *true* whole-board clearance count is 1,664 against a 2-layer board). Both readings here are saturated, so this raw comparison cannot say whether clearance genuinely improved, worsened, or stayed flat -- an honest limitation, not a result. A real delta requires re-running that session's DRU-rule partition-and-sum against both boards, not attempted in this pass for time. No DRU/clearance/creepage threshold was changed to produce either number.

Full raw kicad-cli category counts (both severity-error and severity-warning, `--format json`), for completeness -- read with the clearance/silk/shorting caveats above in mind, since several categories here also sit on kicad-cli's own reporting limits and are not claimed as true whole-board counts:

| category | committed board | this run |
|---|---:|---:|
| clearance | 500 | 501 |
| courtyards_overlap | 8 | 8 |
| silk_overlap | 199 | 199 |
| shorting_items | 95 | 66 |
| lib_footprint_issues | 13 | 168 |
| copper_edge_clearance | 7 | 40 |
| hole_clearance | 8 | 29 |
| solder_mask_bridge | 145 | 19 |
| track_dangling | 44 | 36 |
| unconnected_items | 426 | 319 |

`lib_footprint_issues` (13→168) and `lib_footprint_mismatch` (26→0) moved by a large margin unrelated to layer count -- most plausibly a footprint-library/KiCad-version artifact of `route_board.py`'s `strip_existing_copper` + `_write_routes_to_content` regeneration path rather than a routing-decision consequence (this category is about footprint definitions, not copper). Not investigated further; flagged rather than silently dropped.

---

## 6. What was deliberately not changed, and why

- `layer_assignment.py`'s 4-element `Layer` enum / Rust `_LAYER_ENUM_TO_KICAD` (§1): extending the enum to 6 layers touches a hand-authored `DEFAULT_LAYER_CONSTRAINTS` table, the netclass YAML `layer:` field contract, and a Rust rebuild -- real, separately-scoped work, and verified low-urgency (soft hint only, tiers 2/3 route around it, no netclass currently names `In3.Cu`/`In4.Cu`).
- `trace_width_assignment.py`'s copper-weight blindness (§4): safety-relevant sizing engineering, not a plumbing fix.
- `kicad_connectivity.py`'s `_layer_id` coarseness: dead in production today (`enable_connectivity_verifier` defaults `False`); fixing a disabled code path was deprioritized in favor of the live production fix.
- A full uncapped clearance/creepage/track_width partition-and-sum for both boards (§5): a multi-hour undertaking on its own precedent (`docs/evidence/2026-08-12-uncapped-drc-measurement.md`); the raw capped numbers are reported honestly as inconclusive rather than a partial number being dressed up as the real answer.
- Whether the 64/74 blind vias this run emits (F.Cu↔In3.Cu, F.Cu↔In4.Cu, B.Cu↔In3.Cu, B.Cu↔In4.Cu -- only 10/74 are plain F.Cu↔B.Cu through-vias) are within `docs/hardware/FAB_CAPABILITY.md`'s fabrication envelope: that document does not mention blind/buried vias at all, and `pcb/temper.kicad_pro`'s design rules carry no blind/buried-via-specific constraint. Flagged as an open manufacturing question this session did not resolve, not asserted either way.
- No ratchet ceiling in `power_pcb_dataset/drc_ceiling.json` was moved.
