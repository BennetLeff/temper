<!-- provenance: commit=023bc0283289895314209d6242d31f7fe89c4626 dirty=UNKNOWN -->
---
title: "Root-cause of every unrouted and broken net from the 6-layer route"
date: 2026-08-15
module: temper-placer
tags: [router, routing, pad-connectivity, nlayer, zone-pour, root-cause]
problem_type: routing-completion
---

# Root-cause of every unrouted and broken net from the 6-layer route

## 1. What was measured

Two full 6-layer batched routes of `pcb/temper.kicad_pcb`, each
`scripts/route_board.py --net-batching --batch-size 10` (the documented
production recipe), fresh process each, ~12.7 min wall, both audited with
the **fixed** `pad_connectivity_audit` (post-#1200, on main):

| run | source | nets routed | pad-connected | fake-completion | honest-gap | unrouted |
|---|---|---|---|---|---|---|
| previous (`agent-final-6layer`) | `/tmp/opencode/final-route-6layer-output.kicad_pcb` | 97/107 (90.7%) | **60/139** | 66 | 13 | 10 |
| this work (`origin/main` @ a5da999cb) | `/tmp/opencode/rootcause-route.kicad_pcb` | 95/106 (89.6%) | **62/139** | 65 | 12 | 11 |

Both runs agree on the audit partition: 60-62 connected, **9
zone-dependent, 68-70 broken**. Run-to-run churn is real (7 nets flip
status between the two runs; `+3V3`, `i2c_sda_ui`, `discharge.k_dis1-no`
etc. differ), but no net flips *between* the broken and the connected
category's causal classes.

The route runs on the 6-layer board auto-select the N-layer A* path
(`_pipeline_route.py`: `use_nlayer = enable_nlayer_astar_spike or
len(available_grids) > 2`; the board has 4 declared signal layers
F.Cu/In3.Cu/In4.Cu/B.Cu), which is why the previous 2-layer-only analysis
in `docs/evidence/2026-08-08-nlayer-via-astar-spike.md` no longer fully
applies.

## 2. The five root-cause mechanisms (exhaustive)

Every one of the 68 broken + 9 zone-dependent nets (77 total) falls into
exactly one of these five mechanisms. Counts from the fresh run.

### M1 — Wrong-layer landing, no via (32 nets) — ROUTER BUG, fix exists but is not on main

The netclass SSOT (`netclass_rules.yaml` / `TEMPER_NET_CLASSES`) assigns a
working layer per net (e.g. `FinePitch` → `B.Cu`, `GateDriveHV` →
`B.Cu`, `GateDriveSELV` → `B.Cu`). Every SMD pad on this board sits on
`F.Cu`. Tier 1 of the N-layer A* searches the SSOT-forced layer, walks
straight to the pad's exact (x, y) — an SMD pad leaves no obstacle on a
layer it has no copper on — reports "arrival", and emits copper that
ends at the pad's coordinate **on the wrong layer with zero vias**. The
pad-connectivity audit then correctly reports the net broken.

Measured on the fresh output, `GATE_HS` (GateDriveHV, SSOT layer B.Cu,
both pads F.Cu):

```
trace: (47.6025,115.35) -> (82.735,137.555), all 67 segments on B.Cu, 0 vias
pad R18.1 at (47.6025,115.35) layer=F.Cu   <- endpoint lands EXACTLY here, wrong layer
pad U6.15 at (82.735,137.555) layer=F.Cu   <- endpoint lands EXACTLY here, wrong layer
```

Same shape for 31 more nets. This is the exact defect `#1196`
(`_land_route_on_pad_layers` in `_astar_nlayer.py`,
`docs/evidence/2026-08-14-router-pad-layer-landing-fix.md`) fixes — but
**`#1196` is not on `origin/main`**. It exists only on
`origin/fix/router-nlayer-routing` (commit `a6ab2356a`), stuck inside the
blocked PR #1178 stack. Main's `_astar_nlayer.py` has **zero**
occurrences of `_land_route_on_pad_layers`; the fix branch has 2.

Since the 6-layer board auto-triggers the N-layer path, every route from
`origin/main` ships this defect.

Nets (32): `+15V`, `+3V3`, `GATE_HS`, `GATE_LS` (2-of-3, see M4),
`PWM_HS`, `PWM_LS`, `RTD_CS_N`, `RTD_DRDY`, `RTD_HW_FAULT`, `RTD_SDI`,
`V_BUS_SENSE`, `WDT_RESET_N`, `bias`, `cs_n`, `discharge.k_dis1-coil1`,
`discharge.k_dis1-coil2`, `discharge.k_dis2-coil1`, `hb-gnd`, `ina`,
`inb`, `power_in.bypass_relay-coil2`, `refin_n`, `rtd_pan.r_low_top-inn`,
`rtd_pan.rail_monitor-ina_p`, `rtd_pan.rail_monitor-outa`,
`safety.coil_thermal.comp-inp`, `safety.fault_any_or-a2`,
`safety.thermal-line`, `safety.uvlo_logic.mon-ina_p`, `sclk`, `sw`,
`vbias`, `vcc`.

Fix: merge `#1196` (and its `primary_grid` sibling `#1197`) out of the
PR #1178 stack. The fix is already written, tested (5 new tests), and
measured (+33 F.Cu↔B.Cu vias, 13 nets out of fake-completion) on the
branch.

### M2 — Zone emission uses rotation-blind pad coordinates (9 nets) — ROUTER BUG, not a fill-pass gap

`_write_routes_to_content` collects the pad positions that feed zone
emission through `temper_orchestration.run_collect_pad_positions`, a
Rust port of the pre-migration Python block. Both the oracle and the Rust
port compute `comp.initial_position + pin.position` — **plain sums with
no rotation applied**. Every other pad-position consumer in the codebase
(the A* path via `core/pad_identity.net_pad_positions`, the
pad-connectivity audit via `core.pin_geometry.pin_world_position`) applies
the component's `initial_rotation` through
`pin_world_position_kernel_py`.

The 2026-08-08 measurement (`docs/evidence/2026-08-08-*`, quoted in
`pad_identity`'s docstring) is explicit: **148 of 169 components on this
board have nonzero `initial_rotation`; a naive `initial_position +
pin.position` sum is wrong for all of them.** The U-H migration
(`feat(orchestration): U-H adapter marshalling -> Rust`, `6037e9686`,
on main) faithfully ported the buggy oracle; the differential test
(`test_adapter_convert_marshal_rust_differential.py`) pins the wrong
behavior because its fixtures never set `initial_rotation`.

Measured on the fresh output, `R6` (rot=180):

```
board file:    R6 at=(55.71,174.09) rot=180, pad 1 local (0,0)  -> world (55.71,174.09)
audit:         R6.1 -> (55.71,174.09)   [rotation-aware, matches board]
run_collect:   R6.1 -> (32.85,174.09)   [rotation-blind, 22.86 mm off]
```

Consequences, both confirmed by direct measurement on the fresh output:

1. **Zone hulls are built around the wrong coordinates.** Only 21 of 59
   real pads of the 9 zone-dependent nets (36%) sit inside a same-layer
   emitted zone hull; the router's own rotation-blind positions are
   covered 42/59 (71%). The hulls cover where the router *thinks* the
   pads are, not where they are. **A fill pass would not fix these nets**
   — the outlines are in the wrong place.
2. **The continuity-exempt MST stitch (`power_in.ntc-no`) connects the
   wrong coordinates.** Its 3 In3.Cu MST edges run between the
   rotation-blind positions `(23.21,175.44) (40.4,210.1) (92.055,227.645)
   (168,223.03)`; the real pads are at `(28.29,175.44) (32.9,210.1)
   (98.405,211.895) (162.92,223.03)` — 5-17 mm off. The audit sees the
   net with 4 pads but `pads_connected=1`.

This is why the audit's `zone_dependent_unmeasured` verdict — "a zone
exists on every unreached pad's layer, might deliver the connection" — is
**more optimistic than reality** for these nets: the zones exist, but
their geometry is wrong. The `zone_dependent_unmeasured` category is a
"cannot measure" verdict; the rotation-blind emission means the honest
verdict for 9 nets is closer to "broken, zone can't help in current form".

Nets (9): `+170V_BUS`, `DC_BUS_RTN`, `PWR_RTN`, `SW_NODE`, `ac_n`,
`power_in.ntc-no`, `tank.c_tank1-p2`, `w1_1`, `w1_2`.

Fix: make `run_collect_pad_positions` (and its oracle) apply
`pin_world_position`'s rotation/side kernel; then re-pin the differential
oracle deliberately (add rotation to the fixtures), per the
oracle-re-pin convention in PR #1198. After that, the emitted hulls will
cover real pads and the remaining gap is a genuine fill pass (M2b below).

### M2b — Zone outlines are never filled (all 9 M2 nets + all 231 zones) — MISSING ZONE-FILL PASS

`zone_emission.py` emits zone outlines (`(polygon (pts ...))` with
`(fill yes ...)`) but **no `filled_polygon` geometry**: measured 231/231
zone blocks in the previous output and 304/304 in the fresh output carry
zero `filled_polygon` sub-blocks. The audit's own docstring says this is
expected ("this codebase's zone writer never runs a fill pass"), but it
means even a *correctly-placed* zone outline is not yet copper. After M2
is fixed, a KiCad fill pass (`kicad-cli pcb fill-zones` or a correct
reimplementation) is still required for these 9 nets to become
pad-connected. Not a router A* fix; a separate, missing pipeline step.

### M3 — Multi-pad nets route only 2 of N pads (22 nets) — ROUTER CONFIG, default off

`route_pcb` defaults `enable_all_pad_tree=False`. With it off,
`expand_channel_path_terminals` only validates **2-pad** nets
(`_validated_two_pad_terminals`); for N>2-pad nets it returns the
SAT-derived channel waypoints unchanged and never appends the missing pad
centres. The A* chain then routes a path through however many waypoints
the SAT topology chose — measured on the fresh output, repeatedly **2 of
3, 2 of 4, 2 of 5, 2 of 6, 2 of 7**.

Measured, `+15V_LS` (3 pads):

```
trace: (21.24,75.465) -> (22.25,67.31), 16 segments on F.Cu, 0 vias
pad C23.1 at (21.24,75.465)  <- endpoint lands exactly
pad U7.2  at (22.25,67.31)   <- endpoint lands exactly
pad U6.11 at (87.815,137.555) <- never visited; not in the waypoint chain
```

The A* *is capable* of reaching every pad (the per-segment loop iterates
all waypoints) — the pads simply are not in the waypoint list. This is a
terminal-expansion gap, not a search-capacity gap: `enable_all_pad_tree`
exists (`_pipeline_route._run_stage4` builds a `TerminalTreePlan` when
on) but is not the production default and is not wired through
`route_board.py`.

Nets (22): `+15V_LS`, `I_SENSE` (2/7), `OCP2_VREF_2V5`, `SHUTDOWN` (2/6),
`discharge.k_dis1-nc`, `discharge.k_dis2-nc`, `discharge.q_dis_drv-g`,
`en`, `hb.gate_hs.driver-p1-1`, `hb.gate_hs.driver-p2`,
`hb.power_loop.q_high-g`, `io0`, `rtd_pan.r_high_top-inp`, `safety-line`,
`safety.ocp.comp-inn`, `safety.ocp2-line`, `safety.ovp-line`,
`safety.ovp.comp-inp`, `safety.thermal.comp-inp`,
`safety.uvlo_logic-line`, `safety.uvlo_logic.mon-outa`, `y`, plus the
3 M1/M3 hybrids (`GATE_LS`, `power_in.bypass_relay-coil1`,
`safety-line-1`) which route 2-of-3 with one wrong-layer landing.

Fix: flip the production default (`enable_all_pad_tree=True` in
`route_pcb`) or, minimally, have `expand_channel_path_terminals` append
missing pad centres for N>2 nets regardless of the flag (the flag's
terminal-tree machinery is a separate, larger feature; the append is the
part that fixes connectivity).

### M4 — A* finds no legal path at all (11 nets) — ROUTER/PHYSICS, mixed

These nets emit **zero** copper: the A* searched and failed closed
(forced segments are banned by `_allow_forced_segments`, so an honest
decline). Measured spans (max pairwise pad distance) show why the search
is hard:

| net | pads | span |
|---|---|---|
| `gnd` | 88 | 296 mm |
| `+3V3` | 50 | 238 mm |
| `power_in.q_relay_drv-g` | 3 | 236 mm |
| `sdi` | 2 | 213 mm |
| `safety.fault_or-y2` | 2 | 212 mm |
| `sdo` | 2 | 224 mm |
| `RELAY_CTRL` | 2 | 227 mm |
| `RTD_SCK` | 2 | 177 mm |
| `s1` | 4 | 159 mm |
| `discharge.r_snub2-p2` | 2 | 168 mm |
| `safety.coil_thermal-line` | 3 | 158 mm |
| `fb` | 3 | 141 mm |

Two distinct sub-causes:

- **`gnd` (88 pads) and `+3V3` (50 pads) are pour-class nets being
  trace-routed.** `TEMPER_NET_ASSIGNMENTS` maps both to the `Power`
  class (the 2026-08-11 `gnd` reclassification), and `Power` declares no
  `routing_strategy`, so `_zone_layers_for_net()` returns `[]` for them,
  `_should_route()` returns `True`, and the A* is asked to route an
  88-pad / 50-pad net as a 1.0 mm trace across a 296 mm span. That is the
  documented `_should_route`/`_zone_layers_for_net` policy gap from
  `docs/evidence/2026-07-28-pour-strategy-audit.md` — plus `gnd`'s
  dedicated In1.Cu plane generator (`router_v6/_ground_plane.py`) has
  **no production caller** (verified: only `_power_islands.py` imports
  it, and `_power_islands` is itself caller-less), so `gnd` gets nothing
  from either mechanism. `+3V3`'s Power-class pour history is documented
  in `_zone_pour_stitch.py` ("Power staying trace-only is a landed,
  evidence-corroborated decision") — but at 50 pads a pure-trace A* is
  not a viable realization; see the fix note.
- **The remaining 9 nets are long, mostly 2-pad, mostly Default-class
  signal nets** whose only viable path crosses the board; with the
  N-layer landing defect (M1) consuming B.Cu/In3.Cu/In4.Cu with
  wrong-layer copper on earlier-routed nets, the search space is both
  congested and partly phantom-occupied. These are router-fixable *in
  combination* with M1 (correct vias free the inner layers) and M3 (tree
  routing), and plausibly placement-fixable for the very longest ones.

Nets (11): `RELAY_CTRL`, `RTD_SCK`, `discharge.r_snub2-p2`, `fb`, `gnd`,
`power_in.q_relay_drv-g`, `s1`, `safety.coil_thermal-line`,
`safety.fault_or-y2`, `sdi`, `sdo`.

### M5 — Missing component / physically impossible — NOT FOUND

Checked the two candidates from the handoff:

- **Missing component (OCP-02: T2, R65, C37):** all three are present on
  this board (T2 = `temper:CST3015`, R65 = R_1206, C37 = C_0603;
  verified against `pcb/temper.kicad_pcb`). The handoff's "off-board"
  note is stale for this board version. `s1` (which they join) is M4
  (A* no-path), not M5.
- **Physically impossible:** no net's pads are on opposite sides of the
  board with no viable path in principle. The 6-layer stackup was
  specifically chosen (`#1178`) to give the board enough routing
  capacity; every M4 net has a plausible multi-layer path. The
  `power_in.ntc-no` MST-stich issue is M2 (wrong coordinates), not
  physical.

## 3. Verification of the audit itself

The handoff asked to verify the fixed audit is trustworthy. Findings:

1. **The three #1200 defects are fixed on main** (`84cc526fd`): union-find
   two-pass pad handling (no stale root), `_cluster_key` tie handling, and
   zone awareness (`zone_dependent_unmeasured`). Regression tests exist.
2. **Cross-checked against ground truth**: the audit's pad positions for
   `GATE_HS` (`47.6025,115.35` / `82.735,137.555`) exactly match the
   board file's rotation-aware world positions and the A* trace
   endpoints — the audit reads pads the same way the router's *good* path
   does, which is precisely why it catches the zone-emission mismatch.
3. **One residual audit gap found (diagnostic only):** single-pad nets
   (`pad_count <= 1`) return from `check_net_pad_connectivity` early and
   therefore carry empty `zone_layers`, even when a zone exists for the
   net (e.g. `ac_l` has 4 zone blocks, audit reports `zone_layers=()`).
   This does not affect classification (`fully_connected=True` is correct
   for a 1-pad net) — noted for completeness, not a defect in the verdict.
4. **The zone-dependent verdict is optimistic, not wrong**: the audit
   cannot see zone fill and says so; the *new* finding in this work is
   that the emitted zone *outlines themselves* are at wrong coordinates
   (M2), which a fill pass cannot rescue. The audit's category stays
   "cannot measure" — the router's emission bug is what needs fixing.

## 4. Classification summary

| mechanism | count | fixable by | status of fix |
|---|---|---|---|
| M1 wrong-layer landing | 32 | **router** (merge #1196/#1197 from PR #1178 stack) | fix written & measured, not on main |
| M2 rotation-blind zone pads | 9 | **router** (`run_collect_pad_positions` rotation + oracle re-pin) | new finding, no fix yet |
| M2b no zone fill | (9, same nets) | **zone-fill pass** (kicad-cli fill-zones or reimpl) | missing pipeline step |
| M3 2-of-N pads | 22 | **router** (`enable_all_pad_tree` default / terminal append) | one-line-ish, no PR |
| M4 A* no path | 11 | **router** (M1+M3 enable it) + **placement** for longest | depends on M1/M3 |
| M5 missing component / impossible | 0 | — | — |

Totals by *fix owner*:

- **Router-fixable: 63** (32 M1 + 9 M2 + 22 M3). Of these, **41 already
  have a written fix** (M1: #1196/#1197, unmerged) and **22 need a small
  new fix** (M3 default flip / terminal append), plus 9 M2 (new).
- **Zone-fill-fixable: 9** (M2b — after M2 lands; without M2, the fill
  has nothing correct to fill).
- **Placement-fixable: 0-4** (the longest M4 spans may need a re-place;
  not proven necessary).
- **Config-fixable: 0-2** (`gnd`/`+3V3` pour-vs-trace class assignment is
  a deliberate recorded decision, not a slip — changing it is an owner
  call, tracked as part of M4).
- **Need-missing-component: 0**.
- **Genuinely impossible: 0**.

## 5. What specifically needs to change in the router

1. **Merge `#1196` + `#1197`** (`_land_route_on_pad_layers` +
   `primary_grid` anchor from pad layer) out of PR #1178 into main. This
   alone should move most of the 32 M1 nets into genuinely-connected
   (the branch measured 69/139 vs 60/139 pre-fix).
2. **Fix `run_collect_pad_positions` rotation** (M2): route it through
   the same `pin_world_position_kernel_py` rotation/side kernel the
   audit and A* use; extend the differential oracle fixtures with
   nonzero `initial_rotation` and re-pin deliberately.
3. **Flip `enable_all_pad_tree` to True** in `route_pcb` (M3), or append
   missing pad centres in `expand_channel_path_terminals` for N>2 nets
   regardless of the flag.
4. **Wire a zone-fill pass** after zone emission (M2b) — either
   `kicad-cli pcb fill-zones` on the written board or a faithful
   reimplementation; the audit's `zone_dependent_unmeasured` then becomes
   a measurable verdict instead of a permanent open question.
5. **Re-evaluate `gnd`/`+3V3` realization** (M4 sub-case): either wire
   `_ground_plane.py`'s In1.Cu generator into production for `gnd`, or
   accept a dedicated pour for `+3V3`; an 88-pad / 50-pad A* trace route
   is not a viable strategy at 1.0 mm.

## 6. Reproducibility

- Route: `scripts/route_board.py --net-batching --batch-size 10 --output /tmp/opencode/rootcause-route.kicad_pcb`
  on `origin/main` @ `a5da999cb1a3438d01dfe472333e6d8dba2e0b01`, fresh
  process, 766.5 s, 0 batch crashes/timeouts.
- Audit: `temper_placer.router_v6.pad_connectivity_audit.audit_pcb_file`
  (fixed #1200), same as the route script's PRIMARY metric.
- All coordinates in this doc were re-read from the routed output file's
  own `(pad ...)`/`(segment ...)`/`(zone ...)` blocks; no inference.

## Appendix A — Full per-net root-cause table (fresh run)

Status: **connected** = 62, **zone_dependent** = 9, **broken** = 68.

Mechanism keys: M1 = wrong-layer landing (merge #1196); M2 = zone
emission rotation-blind pads; M3 = 2-of-N pads (`enable_all_pad_tree`);
M4 = A* no legal path; OK = connected.

| net | pads | status | class | mechanism | fix owner |
|---|---|---|---|---|---|
| +15V | 10 | broken | Power | M1 | router |
| +15V_LS | 3 | broken | HighVoltageSignal | M3 (2/3) | router |
| +170V_BUS | 11 | zone_dependent | HighVoltage | M2+M2b | router+fill |
| +3V3 | 50 | broken | Power | M1 (+M4 pour-vs-trace) | router |
| DC_BUS_RTN | 8 | zone_dependent | HighVoltage | M2+M2b | router+fill |
| DISCHARGE_CTRL | 2 | connected | Default | OK | — |
| GATE_HS | 2 | broken | GateDriveHV | M1 | router |
| GATE_LS | 3 | broken | GateDriveHV | M1+M3 (2/3) | router |
| I_SENSE | 7 | broken | Default | M3 (2/7) | router |
| OCP2_VREF_2V5 | 3 | broken | Default | M3 (2/3) | router |
| PWM_HS | 2 | broken | GateDriveSELV | M1 | router |
| PWM_LS | 2 | broken | GateDriveSELV | M1 | router |
| PWR_RTN | 15 | zone_dependent | HighVoltage | M2+M2b | router+fill |
| RELAY_CTRL | 2 | broken | Default | M4 | router/placement |
| RTD_CS_N | 2 | broken | FinePitch | M1 | router |
| RTD_DRDY | 2 | broken | FinePitch | M1 | router |
| RTD_HW_FAULT | 3 | broken | FinePitch | M1 | router |
| RTD_SCK | 2 | broken | FinePitch | M4 | router/placement |
| RTD_SDI | 2 | broken | FinePitch | M1 | router |
| RTD_SDO | 2 | connected | FinePitch | OK | — |
| SHUTDOWN | 6 | broken | Default | M3 (2/6) | router |
| SW_NODE | 7 | zone_dependent | HighVoltage | M2+M2b | router+fill |
| V_BUS_SENSE | 4 | broken | Power | M1 | router |
| WDT_KICK | 2 | connected | Default | OK | — |
| WDT_RESET_N | 3 | broken | Default | M1 | router |
| a3 | 1 | connected | Default | OK (single pad) | — |
| ac_l | 1 | connected | ACMains | OK (single pad) | — |
| ac_n | 3 | zone_dependent | ACMains | M2+M2b | router+fill |
| b3 | 1 | connected | Default | OK (single pad) | — |
| bias | 3 | broken | FinePitch | M1 | router |
| boot | 2 | connected | Default | OK | — |
| c3 | 1 | connected | Default | OK (single pad) | — |
| cs_n | 2 | broken | FinePitch | M1 | router |
| discharge.k_dis1-coil1 | 3 | broken | Signal | M1 | router |
| discharge.k_dis1-coil2 | 5 | broken | Signal | M1 | router |
| discharge.k_dis1-nc | 4 | broken | HighVoltageSignal | M3 (2/4) | router |
| discharge.k_dis1-no | 2 | connected | Default | OK | — |
| discharge.k_dis2-coil1 | 3 | broken | Signal | M1 | router |
| discharge.k_dis2-nc | 4 | broken | HighVoltageSignal | M3 (2/4) | router |
| discharge.k_dis2-no | 2 | connected | Default | OK | — |
| discharge.q_dis_drv-g | 3 | broken | Default | M3 (2/3) | router |
| discharge.r_dis1a-p2 | 2 | connected | Default | OK | — |
| discharge.r_dis2a-p2 | 2 | connected | Default | OK | — |
| discharge.r_snub1-p2 | 2 | connected | Default | OK | — |
| discharge.r_snub2-p2 | 2 | broken | Default | M4 | router/placement |
| en | 4 | broken | Default | M3 (2/4) | router |
| fb | 3 | broken | Default | M4 | router/placement |
| gnd | 88 | broken | Power | M4 (pour-vs-trace; plane gen. uncalled) | router+config |
| gpio18 | 1 | connected | Default | OK (single pad) | — |
| gpio21 | 1 | connected | Default | OK (single pad) | — |
| gpio35 | 1 | connected | Default | OK (single pad) | — |
| gpio36 | 1 | connected | Default | OK (single pad) | — |
| gpio37 | 1 | connected | Default | OK (single pad) | — |
| hb-gnd | 6 | broken | Default | M1 | router |
| hb.gate_hs.driver-p1 | 2 | connected | Default | OK | — |
| hb.gate_hs.driver-p1-1 | 4 | broken | HighVoltageIsolated | M3 (2/4) | router |
| hb.gate_hs.driver-p2 | 4 | broken | HighVoltageIsolated | M3 (2/4) | router |
| hb.power_loop.q_high-g | 3 | broken | HighVoltageSignal | M3 (2/3) | router |
| i2c_scl_ui | 2 | connected | Default | OK | — |
| i2c_sda_ui | 2 | connected | Default | OK | — |
| ina | 3 | broken | Default | M1 | router |
| inb | 3 | broken | Default | M1 | router |
| input | 2 | connected | Default | OK | — |
| io0 | 3 | broken | Default | M3 (2/3) | router |
| io13 | 1 | connected | Default | OK (single pad) | — |
| io40 | 1 | connected | Default | OK (single pad) | — |
| io41 | 1 | connected | Default | OK (single pad) | — |
| io42 | 1 | connected | Default | OK (single pad) | — |
| io45 | 1 | connected | Default | OK (single pad) | — |
| io46 | 1 | connected | Default | OK (single pad) | — |
| io48 | 1 | connected | Default | OK (single pad) | — |
| nc3 | 1 | connected | Default | OK (single pad) | — |
| nc_7 | 1 | connected | Default | OK (single pad) | — |
| power_in.bypass_relay-coil1 | 3 | broken | Signal | M3 (2/3)+M1 | router |
| power_in.bypass_relay-coil2 | 3 | broken | Signal | M1 | router |
| power_in.ntc-no | 4 | zone_dependent | HighVoltage | M2+M2b (MST at wrong coords) | router+fill |
| power_in.q_relay_drv-g | 3 | broken | Default | M4 | router/placement |
| refin_n | 5 | broken | FinePitch | M1 | router |
| rtd_force_n | 2 | connected | Default | OK | — |
| rtd_force_p | 2 | connected | Default | OK | — |
| rtd_pan.high_window-out | 2 | connected | Default | OK | — |
| rtd_pan.low_window-out | 2 | connected | Default | OK | — |
| rtd_pan.r_high_top-inp | 3 | broken | Default | M3 (2/3) | router |
| rtd_pan.r_low_top-inn | 3 | broken | Default | M1 | router |
| rtd_pan.rail_monitor-ina_p | 3 | broken | Default | M1 | router |
| rtd_pan.rail_monitor-outa | 3 | broken | Default | M1 | router |
| rtd_pan.rail_monitor-outb | 1 | connected | Default | OK (single pad) | — |
| rtd_sense_n | 2 | connected | Default | OK | — |
| rtd_sense_p | 2 | connected | Default | OK | — |
| rx | 1 | connected | Default | OK (single pad) | — |
| s1 | 4 | broken | Default | M4 | router/placement |
| safety-line | 4 | broken | Default | M3 (2/4) | router |
| safety-line-1 | 3 | broken | Default | M3 (2/3)+M1 | router |
| safety-line-2 | 2 | connected | Default | OK | — |
| safety-line-3 | 2 | connected | Default | OK | — |
| safety.coil_thermal-line | 3 | broken | Default | M4 | router/placement |
| safety.coil_thermal.comp-inp | 4 | broken | Default | M1 | router |
| safety.fault_any_or-a2 | 3 | broken | Default | M1 | router |
| safety.fault_any_or-y2 | 2 | connected | Default | OK | — |
| safety.fault_any_or-y3 | 1 | connected | Default | OK (single pad) | — |
| safety.fault_or-a2 | 2 | connected | Default | OK | — |
| safety.fault_or-b2 | 2 | connected | Default | OK | — |
| safety.fault_or-y2 | 2 | broken | Default | M4 | router/placement |
| safety.fault_or-y3 | 1 | connected | Default | OK (single pad) | — |
| safety.fault_or3-b2 | 2 | connected | Default | OK | — |
| safety.fault_or3-y2 | 2 | connected | Default | OK | — |
| safety.fault_or3-y3 | 1 | connected | Default | OK (single pad) | — |
| safety.latch-b2 | 2 | connected | Default | OK | — |
| safety.ocp-line | 2 | connected | Default | OK | — |
| safety.ocp.comp-inn | 3 | broken | Default | M3 (2/3) | router |
| safety.ocp2-line | 3 | broken | Default | M3 (2/3) | router |
| safety.ovp-line | 3 | broken | Default | M3 (2/3) | router |
| safety.ovp.comp-inp | 4 | broken | Default | M3 (2/4) | router |
| safety.ovp.r_adc_top1-p2 | 2 | connected | HighVoltage | OK | — |
| safety.ovp.r_adc_top2-p2 | 2 | connected | HighVoltage | OK | — |
| safety.ovp.r_div_top1-p2 | 2 | connected | HighVoltage | OK | — |
| safety.ovp.r_div_top2-p2 | 2 | connected | HighVoltage | OK | — |
| safety.thermal-line | 3 | broken | Default | M1 | router |
| safety.thermal.comp-inp | 4 | broken | Default | M3 (2/4) | router |
| safety.uvlo_logic-line | 4 | broken | Default | M3 (2/4) | router |
| safety.uvlo_logic.mon-ina_p | 4 | broken | Default | M1 | router |
| safety.uvlo_logic.mon-outa | 4 | broken | Default | M3 (2/4) | router |
| safety.uvlo_logic.mon-outb | 1 | connected | Default | OK (single pad) | — |
| sclk | 2 | broken | FinePitch | M1 | router |
| sdi | 2 | broken | FinePitch | M4 | router/placement |
| sdo | 2 | broken | FinePitch | M4 | router/placement |
| sw | 3 | broken | Default | M1 | router |
| tank-out | 2 | connected | HighVoltage | OK | — |
| tank.c_tank1-p2 | 4 | zone_dependent | HighVoltageTank | M2+M2b | router+fill |
| thermal.j_fan-p1 | 2 | connected | Default | OK | — |
| tx | 1 | connected | Default | OK (single pad) | — |
| usb_dn | 1 | connected | Default | OK (single pad) | — |
| usb_dp | 1 | connected | Default | OK (single pad) | — |
| vbias | 3 | broken | FinePitch | M1 | router |
| vcc | 13 | broken | Power | M1 | router |
| w1_1 | 4 | zone_dependent | HighVoltage | M2+M2b | router+fill |
| w1_2 | 3 | zone_dependent | HighVoltage | M2+M2b | router+fill |
| y | 3 | broken | Default | M3 (2/3) | router |
| y1 | 2 | connected | Default | OK | — |

