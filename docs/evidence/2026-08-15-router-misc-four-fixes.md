# 2026-08-15 — Four router fixes: rotation, all-pad-tree, gnd plane, via audit

Branch: `fix/router-misc-fixes` (4 commits off `origin/main` @ `6285d6889`).
Companion task: handoff `2026-08-15` §"Four router fixes" (agents 57/58/64
findings). Expected connectivity improvement: 9 + 22 + 11 = 42 nets could
improve; measured below.

## Summary

| # | Commit | Fix | Verdict |
|---|--------|-----|---------|
| 1 | `8bdd71272` | Zone pad-position rotation (M2 — 9 nets) | 148/169 components had nonzero rotation; pad positions were `comp_pos + pin_pos` with no rotation, so zone hulls and the connectivity preflight sat at wrong coordinates. Now resolved through the sanctioned temper-geometry kernel. |
| 2 | `287f221e7` | `enable_all_pad_tree` default True (M3 — 22 nets) | N>2 nets never had missing pad centres appended to the A* waypoint chain. Now the default at every production site; `+15V_LS`'s U6.11 is visited. |
| 3 | `5af006d2e` | gnd In1.Cu ground plane wired into production (M4 — 11 nets partially) | gnd (88 pads) had zero copper. `_ground_plane.py` was a spike with no production caller; now rides every `route_pcb()`. |
| 4 | `65cc37e07` | Audit via model: untyped = through (7 — trust the 139 number) | The audit modelled a via's reach from its declared `(layers ...)` endpoint pair; all router vias are untyped through vias spanning every layer. 32→35 on the nlayer routed board (cs_n, RTD_DRDY, sdo), zero regressions. |

## Fix 1 — component rotation in zone pad position collection

**Finding (agent 57):** `temper_orchestration.pipeline_route::run_collect_pad_positions`
(the board→`pad_positions` conversion feeding zone-pour emission and the
connectivity preflight) did `comp_pos + pin_pos` with no component rotation.
148/169 components have nonzero rotation; only 21/59 real pads (36%) sat
inside their same-layer zone hulls.

**Fix:** the pad-resolved branch now calls back into the sanctioned
temper-geometry kernel (`pin_world_position_at_py`: mirror X on side==1,
R(−θ) rotation, then comp position) — the D4/D5 mixin-call-back pattern
already used for the chamfer, so the geometry stays single-source in
temper-geometry and cannot drift. Missing `initial_rotation_quadrant`/
`initial_side` read as 0/0 (getattr defaults, same as the kernel).

**Oracle re-pin:** the differential oracle
(`test_adapter_convert_marshal_rust_differential.py::_oracle_collect_pad_positions`)
encoded the same naive-sum bug; re-pinned (digest
`0353f298…` → `ab4c4b81…`) to resolve pins through the canonical kernel so
the A/B asserts the port matches canonical pad-position geometry. New test
`test_collect_pad_positions_applies_component_rotation` pins the corrected
absolute values (180° rotation: (9.0, 20.0) not (11.0, 20.0); side mirror:
(3.0, 5.0) not (7.0, 5.0)) — non-vacuous.

Tests: `test_adapter_convert_marshal_rust_differential.py` 29 passed (was
28, +1 new).

## Fix 2 — `enable_all_pad_tree` defaults True

**Finding (agent 57):** `enable_all_pad_tree` defaulted False at every
production-facing site (`route_pcb`, `RouterV6Pipeline.__init__`,
`BoardState`, `route_stage` getattr). N>2 nets never had missing pad centres
appended to the Stage 4 A* waypoint chain: A* is capable but pads weren't in
the list (`+15V_LS`: C23.1 + U7.2 visited, U6.11 never).

**Fix:** default True at all four sites; callers wanting the old
SAT-waypoints-only behaviour can still pass False. The flag gates only Stage
4 waypoint expansion (`expand_channel_path_terminals` + terminal-tree
planning); Stage 3's SAT topology solve already handles multi-pad nets and
is untouched.

**Verified:** on the real board, `+15V_LS`'s expanded chain carries all 3
pads (old default: 2 waypoints, U6.11 missing).

## Fix 3 — gnd In1.Cu ground plane wired into production

**Finding (agent 57/64):** `gnd` (88 pads — the board's largest net) and
`+3V3` (50 pads) get zero copper. `gnd` is mapped to the `Power` netclass
(kicad_pro does not declare a `GND` class; see `design_rules.py`'s gnd entry
and the PR #1087 rationale), `Power` declares no `routing_strategy`, so
`_zone_layers_for_net("gnd") == []` and the F.Cu/B.Cu pour path never fires.
`router_v6/_ground_plane.py` (In1.Cu plane + HV/SELV keepout + drop vias +
MST backbone) existed only as a standalone spike
(`scripts/generate_ground_plane.py`).

**Fix:** `_write_routes_to_content` now appends the gnd-plane blocks after
the R7 strip + `_emit_zone_pours` pass, so the In1.Cu zones survive the
F.Cu/B.Cu regeneration. `generate_ground_plane_content` was refactored
(computation byte-identical, verified by diff against origin/main) into
`generate_ground_plane_blocks` (returns s-expression blocks + report; the
production seam) + a thin content-splicing wrapper (standalone
script/tests). `tstamp_counter` is threaded so the plane's tstamps continue
the run's deterministic sequence. The default domain-manifest path resolves
against the repo root when CWD-relative and missing (production `route_pcb`
runs from arbitrary CWDs — pytest from `packages/temper-placer`, `make
route` from the repo root). Boards without a `gnd` net are skipped.

**`+3V3` note (agent 64's R1/R7 policy):** `Power` staying trace-only is an
already-landed, evidence-corroborated, actively-tested decision
(`TestZonePoursForNet.test_power_class_is_not_zone_eligible` and a dozen
fixtures were deliberately rewritten 2026-07-28/30 to stop assuming `vcc`/
`+3V3` are zone-eligible — see `_zone_pour_stitch.py::_zone_layers_for_net`'s
NOT-CHANGED-2026-08-11 block). The N-layer board does now have In1.Cu
available, but gnd is the safety-relevant, largest, and least-excusable net
(ground return of a mains board); the In1.Cu plane for gnd is this commit's
scope. Promoting `Power` to a plane class (e.g. `+3V3` on In2.Cu) is the
`_power_islands.py` design and is deliberately a separate decision.

**Verified:**
- Wiring unit check through the production `_write_routes_to_content` with a
  real `source_path`: output carries 9 gnd In1.Cu pours + 4 keepout zones +
  52 drop vias + MST backbone (the R7 strip removes the input's 96 zones
  first; the plane's own 13 survive because they are appended after).
- Full route (`route_pcb`, SAT capped to 1 net — see below): 13 In1.Cu
  zones in the routed output; gnd goes from 0 copper / 1 pad connected to
  real copper / 15 pads connected on the current committed board.
- The generator itself is unchanged from origin/main; the test floor was
  re-pinned 45/88 → 15/88 with attribution to board drift (the pre-refactor
  generator also measures 15/88 on main `6285d6889`; 46 of 87 MST edges now
  cross the HV keepout and are dropped fail-closed).

## Fix 4 — audit models untyped vias as through

**Finding (agent 58):** the pad-connectivity audit (`pad_connectivity_audit.py`)
modelled a via's reach from its declared `(layers "F.Cu" "B.Cu")` endpoint
pair. KiCad's format omits the `(type ...)` token for THROUGH vias (it is
written only for blind/buried), and every via this project's router and
ground-plane generator emit is untyped — a through via physically spans
every copper layer, not just its endpoints. The audit under-reported (a 4th
metric defect in the under-reporting direction; the 139-number needed the
+2).

**Fix:** the parser now reads `(type ...)`; absent or `through` → `layers=()`
(the checker's existing "spans every layer" encoding, previously unreachable
because every parsed via carried its endpoint pair); explicit blind/buried
keeps the declared pair. Note this also supersedes `_ground_plane.py`'s
`BACKBONE_LAYER = "F.Cu"` rationale comment (the audit now sees a through
via's real inner-layer contact), but the backbone layer itself is unchanged
— F.Cu is one of the via's declared layers and still unions correctly.

**Verified:** on the routed nlayer scratch board (the artifact the audit
tests pin): 32/112 → 35/112 fully-connected multi-pad nets; newly connected
`cs_n`, `RTD_DRDY` (agent 58's prediction), plus `sdo`; zero regressions.
New parser-level test pins absent-token → all-layers vs `(type blind)` →
declared-pair.

## Route verification

A full `route_pcb` run on the production board OOM-killed (exit 137) at the
documented Stage 3 SAT memory blowup (handoff §6: t≈260–270s, another
agent's `route_board.py` was live at 12 GB — this machine has had routing
runs OOM-killed at 54–59 GB with several agents active; per handoff §"Never
relaunch a run that died", not relaunched).

Route verification instead ran with `max_sat_nets=1` (SAT model collapsed
~100×, still exercising full Stage 4 A* with the new defaults and the
complete write path):

- wall 268s, completion_rate 57.55% (SAT-cap-limited; power nets +15V/+3V3
  remain trace-only by R1/R7 policy)
- **13 In1.Cu zones in the routed output** (9 gnd pours + 4 keepout) — Fix 3
  rode a production route
- **`+15V_LS` routed and audited fully connected (3/3 pads)** — Fix 2's
  U6.11 finding closed
- audit of the routed output (Fix 4 via model): 61/112 multi-pad nets fully
  connected, 43 confirmed broken, 8 zone-dependent-unmeasured

## Test results

- `test_adapter_convert_marshal_rust_differential.py`: 29 passed (+1 new rotation test, oracle re-pinned)
- `test_pad_connectivity_audit.py`: 26 passed (+1 new through-via parser test)
- `test_ground_plane.py`: 7 passed (floor re-pinned 45→15 with attribution)
- `test_adapter.py`: 103 passed (2 pre-existing geographic-pruning failures resolved by the gnd-net guard; 1 pre-existing `test_bundled_full_pipeline` SkeletonGraph fixture failure unchanged)
- Combined sweep (all four fixes' surfaces): **262 passed, 1 skipped**
- Oracle content-hash gate: 167/167 OK; import-linter gate: 0 violations
- Pre-existing, unrelated failures confirmed not caused by this branch:
  `test_kicad7_footprint_dir_resolves` (env), `test_pad_identity.py`
  `initial_rotation` vs `initial_rotation_quadrant` staleness (origin/main
  rename), `regen-check` manifest/layer_identity items (files outside this
  diff), coverage-gate `ThermalScorer` allowlist gap (outside this diff)

## Outstanding

- Full-board (uncapped SAT) route verification remains blocked by the
  documented Stage 3 memory bug (handoff §6) while other agents route; the
  `max_sat_nets=1` run above is the strongest verification possible on this
  machine right now.
- The gnd plane's connectivity on the CURRENT committed board is 15/88 (was
  45/88 on the 2026-08-13 board) — board drift, generator unchanged,
  fail-closed drops of 46 MST edges across the HV keepout. A future
  generator revision with real pathfinding (`_corridor_backbone.py`'s own
  note) is the lever, not a wider keepout.
- `kicad_connectivity.py`'s preflight has the same declared-pair via model
  behind `enable_connectivity_verifier=False` (default-off) — flagged, not
  changed.
