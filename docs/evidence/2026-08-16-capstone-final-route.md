<!-- provenance: commit=6ac839e28646fe3b6e984326cc4efc0d56e58daa dirty=false -->
---
title: "Capstone final route with ALL session fixes on main — 89/139 pad-connected, 0 fake completions, 0 unconnected DRC items"
date: 2026-08-16
module: temper-placer
tags: [router, routing, capstone, pad-connectivity, nlayer, final-route, net-routing-result, zone-generator, width-aware]
problem_type: routing-completion
---

# Capstone final route: every session fix on `main` (2026-08-16)

**One-line result:** a fresh batched 6-layer route of
`pcb/temper.kicad_pcb` at `6ac839e28` — the first board carrying **all**
session fixes (width-aware C-space #1249, NetRouteResult type system #1256,
auto-batch #1250, Rust creepage-aware zone generator #1257, pad-layer
landing #1246, via-type emission, zone rotation, `enable_all_pad_tree`, gnd
In1.Cu plane, FinePitch 0.2 mm #1255, K1/RT1/U1/U2 cluster placement #1248,
firmware interlocks #1254, thermal SSOT in Rust #1251) — measures
**89/139 fully pad-connected**, with the router's own Rust-verified
`NetRouteResult` line reporting **89 connected, 6 zone-dependent, 7
partial, 37 failed of 139 pad-bearing nets** and **0 unconnected DRC
items**. The fake-completion class is **gone from the type system**: a net
is `Connected` only when `verify_continuity` proves real copper joins its
pads; the 13 audit-level "fake" nets are honestly re-classified as 7
`partial` (copper exists, pads not all joined) + 6 `zone_dependent`
(outline-only pours, fill-blind to the graph). DRC errors fell to **1,732**
(from 1,927 last capstone; committed board 1,483). Board still **not
fabricable** (see §8).

The headline connectivity is **−3 vs the 2026-08-16 09:43 capstone
(92/139)** — but that run's board (fdbe0a6ad) predates the K1-cluster
placement (#1248), so the comparison is confounded: **12 nets lost, 9
gained**, a ±21-net flip far beyond the documented ~7-net run-to-run churn.
The lost set is dominated by exactly the nets the two new fixes changed:
OVP-divider nets whose old 30-zone pours were non-creepage-aware islands
(the Rust generator now honestly refuses them at PD3 carve), and
K1-cluster-adjacent signal nets on the moved board. See §3/§6.

## 1. Recipe

```
.venv/bin/python scripts/route_board.py --net-batching --batch-size 10 \
  --output /tmp/opencode/capstone-route.kicad_pcb
```

- Worktree: `/tmp/opencode/agent-final-route-v2` @ `6ac839e28`
  (`origin/main`, `scripts/assert-base.sh origin/main` OK), **isolated**
  venv (`make venv-isolate` + `make extensions`, 10/10 fresh via
  `make extensions-check`; `make venv-integrity-check` PASSED — the shared
  repo venv was never touched).
- Board: `pcb/temper.kicad_pcb` at `6ac839e28` (sha256
  `ddb96f9e03abdcbb0aa40523b45c07413bc694309417628907780e3d19527ef2`),
  **not modified** by this work (`git status` clean for it).
- DRU: `scripts/generate_kicad_dru.py` regenerated into the worktree
  (untracked `pcb/temper.kicad_dru`, diff vs the 09:43 run's DRU is
  exactly one line: FinePitch `track_width` 0.127 → 0.2 mm, #1255).
- Full log: `/tmp/opencode/capstone-route.log`; routed output:
  `/tmp/opencode/capstone-route.kicad_pcb` (1.64 MB).
- Wall time: **963.7 s** (~16 min), **14 batches, 14 solved at batch
  level, 0 crashed / 0 timeouts**; auto-batch (2.5 M-var threshold, #1250)
  did **not** trigger (models stayed under). Parent RSS peaked ~721 MB;
  largest SAT worker 4.0 GB (documented 1–5 GB/batch range). **No OOM.**
- Audit: `temper_placer.router_v6.pad_connectivity_audit.audit_pcb_file`
  (fixed #1200) + `net_route_result_preflight` (Rust `NetRouteResult`
  pyclass, #1256) — the type-enforced verdict is PRIMARY.

## 2. Headline route stats

| metric | value |
|---|---|
| nets routed (Stage-3 topology) | 67/106 (63.2%) |
| fully pad-connected (audit) | **89/139** |
| **NetRouteResult (type-enforced)** | **89 connected, 6 zone-dependent, 7 partial, 37 failed** |
| audit fake-completion (legacy label) | 13 (all 13 = 7 partial + 6 zone-dependent per the type system) |
| honest-gap (neither connected nor fake) | 37 |
| segments | 6,119 |
| vias | **177** (97 through F.Cu↔B.Cu, **80 blind** In3.Cu/In4.Cu↔F.Cu) |
| zones | 55 tokens / 50 parsed outlines (11 nets) |
| wall time | 963.7 s |
| batches / crashes | 14 / 0 |

Segment layer spread: In3.Cu 1,976 · F.Cu 1,781 · B.Cu 1,248 · In4.Cu
1,114 — all four declared signal layers carry copper. Via layer pairs:
F.Cu↔B.Cu 97, In3.Cu↔F.Cu 56, In4.Cu↔F.Cu 24.

**Zone collapse, intended**: 387 zone tokens (16 nets) in the 09:43 run →
50 outlines (11 nets) now. This is the Rust zone generator (#1257) being
honest: the old Python carve emitted padless islands and clearance-only
(not creepage) carve — measured 167 isolated-copper islands and +222
creepage violations. The new generator carves at `max(clearance,
creepage)` (HV↔LV = 12.6 mm), applies `PadsOnly` island policy to every
non-GND pour, and drops pieces that cover 0 pads. Zone nets this run:
`gnd` 10 (In1.Cu plane), `SW_NODE` 8, `PWR_RTN` 8, `+170V_BUS` 7,
`DC_BUS_RTN` 6, `tank.c_tank1-p2` 4, `w1_1` 2, `power_in.ntc-no` 2
(sparse inner-layer), `ac_n` 1, `ac_l` 1, `w1_2` 1.

## 3. Connectivity comparison — every prior run, same fixed audit

| run | fully connected | fake | honest-gap | source |
|---|---|---|---|---|
| committed board (essentially unrouted) | 27/139 | — | — | handoff 2026-08-15 |
| pre-PD3 4-layer | 53/139 | — | — | handoff |
| 6-layer pre-#1245 (honest / audit) | 62/139 / 63/139 | 64–65 | 13 | handoff; re-audit |
| 6-layer + M1 only (agent 66) | **69/139** | 54 | 16 | re-audit |
| 2026-08-16 09:43 capstone (pre-width-C-space, pre-zone-gen) | **92/139** | 14 | 33 | `2026-08-16-definitive-final-route.md` |
| **THIS RUN (ALL fixes, K1-cluster board)** | **89/139** | **13 → 7 partial + 6 zone-dep (type-enforced)** | 37 | this document |

**Net-level delta vs the 09:43 capstone: 12 lost / 9 gained** (the two
runs are on different boards — K1/RT1/U1/U2 cluster landed in #1248
between them):

- **Lost (12)**: `SHUTDOWN`, `discharge.k_dis2-nc`,
  `hb.gate_hs.driver-p2`, `hb.power_loop.q_high-g`, `i2c_sda_ui`,
  `power_in.ntc-no`, `safety.ovp.r_adc_top1-p2`,
  `safety.ovp.r_div_top1-p2`, `safety.ovp.r_div_top2-p2`,
  `safety.uvlo_logic.mon-outa`, `sclk`, `sdo`.
- **Gained (9)**: `OCP2_VREF_2V5`, `WDT_RESET_N`, `cs_n`, `io0`,
  `safety.coil_thermal-line`, `safety.ocp.comp-inn`, `safety.ovp.comp-inp`,
  `safety.thermal.comp-inp`, `sdi`.

Attribution: the three `safety.ovp.r_*`/`r_div_*` losses are the intended
zone honesty — they previously "connected" via 13–30 non-creepage-aware
zones each; the Rust carve now refuses those pours at 12.6 mm and the nets
fall back to traces that don't complete. `power_in.ntc-no` lost its 44
island-zones + its single bridging via (see §4). The remaining losses sit
around the re-placed K1/OVP area and the MCU SPI/I2C rails — board-change
confound, not a single-mechanism regression. Width-aware C-space (#1249)
also changed obstacle halos for every net (track↔track shorts 35→0), so
some previously-passable paths are now honestly blocked.

## 4. Specific nets

| net | pads | status | detail |
|---|---|---|---|
| `power_in.ntc-no` | 4 | **partial (3/4)** | 3 segments @ **5.0 mm** (2 F.Cu, 1 In3.Cu) + 2 honest inner-layer zones (In3.Cu/In4.Cu). NetRouteResult: groups `[[1,2,3]]`, pad 0 unreached. The 09:43 run was fully connected via 1 bridging via (98.405,211.895); **this run emitted no via** — pad 0 is stranded on a different layer. F.Cu pour honestly absent (PD3 12.6 mm carve covers 0/4 pads; #1257 design-doc §1.3). Ampacity width achieved where copper exists; connectivity regressed one via. |
| `gnd` | 88 | **partial** | In1.Cu plane present: 10 zones (up from 9). Trace/via graph reaches 53 pads in 9 groups; plane fill delivery is fill-blind to the graph (as before). 22 "no clear via drop point" skips (vs 21). |
| `GATE_HS` | 2 | **connected** | 2 vias at **exact** pad coords (47.6025,115.35) and (82.735,137.555) — M1 coordinate-level check holds, byte-identical coords to the 09:43 run. |
| `PWM_HS` / `PWM_LS` | 2 / 2 | **connected** | 2 vias each at exact pad coords. |
| `GATE_LS` | 3 | **partial** | groups `[[1,2]]`, pad 0 unreached — the known 2-of-3 hybrid, unchanged. |
| `+3V3` | 50 | **failed** | no copper at all (UNEXPLAINED, as in the 09:43 run). Still the largest broken net. |
| `SHUTDOWN` | 6 | **failed** | was 6/6 connected in the 09:43 run; unrouted now. Near the moved K1 cluster — board-change confound, not type-system noise. |
| `+170V_BUS`, `PWR_RTN`, `SW_NODE`, `ac_n`, `tank.c_tank1-p2` | 11/15/7/3/4 | **zone-dependent** | outline-only pours (7/8/8/1/4 outlines); fill-blind. |
| `WDT_RESET_N`, `OCP2_VREF_2V5`, `safety.coil_thermal-line`, `safety.thermal.comp-inp`, `sdi`, `cs_n`, `io0`, `safety.ocp.comp-inn`, `safety.ovp.comp-inp` | — | **connected** | all 9 were fake/partial in the 09:43 run; genuinely joined now. |
| `w1_1`, `w1_2`, `discharge.k_dis1-no`, `discharge.k_dis2-no`, `rtd_force_p/n`, `rtd_sense_p/n`, `safety.fault_any_or-*`, `safety.fault_or-*` | 4-3 | **connected** | multi-pad nets fully joined (M3). |

## 5. DRC (kicad-cli 10.0.5, `--all-track-errors`, sidecar-copied project, freshly generated DRU with FinePitch 0.2 mm)

| metric | committed board | 09:43 routed 6-layer | **this run** |
|---|---|---|---|
| errors | 1,483 | 1,927 | **1,732** |
| warnings | 353 | 378 | **395** |
| unconnected items | 0 (no copper) | **0** | **0** |
| total (err+warn) | 1,836 | 2,305 | **2,127** |

Error categories this run: clearance 499 (cap), creepage 400 (was 485),
track_width 199 (cap), shorting_items 199 (cap), hole_clearance 128,
solder_mask_bridge 123, annular_width 70, copper_edge_clearance 50,
tracks_crossing 47 (was 10), drill_out_of_range 16, courtyards_overlap 1.
Warnings: silk_overlap 199 (cap), holes_co_located 69, silk_over_copper 42,
via_dangling 35, lib_footprint_mismatch 26, lib_footprint_issues 13,
missing_courtyard 5, track_dangling 5, silk_edge_clearance 1.

**Headline: 0 unconnected items for the second consecutive full route, and
errors down 195 vs the 09:43 capstone (1,927 → 1,732)** — creepage fell
485 → 400 (the creepage-aware zone carve removes pour-created violations)
while clearance/shorting/track_width sit at KiCad's 199/499 caps as before.
`tracks_crossing` rose 10 → 47 — new this run, needs attribution (likely
the denser K1-cluster board + width-aware halos pushing traces into
crossing patterns; the 199-cap categories mask the true totals either way).
Note the DRU differs by exactly the FinePitch line, so DRC inputs are not
byte-identical to the 09:43 run.

## 6. Per-mechanism verification (all 13 fixes)

| mechanism | fix | verdict | evidence |
|---|---|---|---|
| width-aware C-space | per-net obstacle halos (#1249) | **works** | track↔track shorts 35→0 in the fix's own measurement; no new short class observed here (shorting_items at cap, unchanged) |
| fake-completions type system | `NetRouteResult`, Connected only from `verify_continuity` (#1256) | **works — headline** | route log prints "89 connected, 6 zone-dependent, 7 partial, 37 failed of 139"; cross-tab vs audit: 0 downgrades, 0 upgrades; 13 audit-fakes = exactly 6 zone-dep + 7 partial |
| auto-batch safety net | 2.5 M-var threshold (#1250) | **armed, not needed** | 14/14 batches solved; no threshold message; no OOM (Stage-3 workers peaked 4.0 GB) |
| Rust zone generator | creepage-aware carve (#1257) | **works as designed** | zones 387→50, honest (0 isolated-copper islands by design); creepage DRC 485→400; `power_in.ntc-no` honestly partial (0-pad F.Cu pour refused) |
| pad-layer landing (M1) | `_land_route_on_pad_layers` (#1246) | **works** | GATE_HS/PWM_HS/PWM_LS vias at exact pad coords; through vias 97 |
| via-type emission | blind/buried tokens (#1245) | **works** | 80 blind vias (In3/In4.Cu↔F.Cu) in output |
| zone rotation (M2) | rotation-correct pad positions (#1245) | **works** | zone pads attach correctly; courtyards_overlap 1 |
| `enable_all_pad_tree` (M3) | all-pad terminal trees (#1245) | **works** | `w1_1` 4/4, `w1_2` 4/4, 9 previously-fake nets genuinely connected |
| gnd In1.Cu plane (M4) | `_ground_plane.py` (#1245) | **partial (unchanged)** | 10 In1.Cu gnd zones; trace graph 53/88 pads; fill-blind remainder |
| FinePitch 0.2 mm | netclass width (#1255) | **works** | DRU diff exactly the one line; track_width still at cap (masked) |
| K1 cluster placement | #1248 board | **board-changed** | the confound: 12 lost nets sit in/around the moved cluster; placement-level gain (per #1248) not re-measured here |
| firmware interlocks | data-driven thermal/OCP (#1254) | n/a to routing | firmware-domain, no routing effect |
| thermal SSOT in Rust | temper-thermal (#1251) | n/a to routing | crate fresh in this venv (10/10); no routing effect |

## 7. Fake completions — dead as a class

The 09:43 run reported 14 fake-completions and a separate
honest-gap bucket. The type system (#1256) removes the class: every net's
verdict is `Connected` (proven copper continuity), `zone_dependent`
(outline-only, fill-unmeasured), `partial` (copper exists, pads not all
joined), or `failed` (no joining copper). The audit's legacy
fake-completion=13 this run decomposes exactly: **6 zone-dependent**
(+170V_BUS, DC_BUS_RTN, PWR_RTN, SW_NODE, ac_n, tank.c_tank1-p2 — all
pour-covered, fill-blind) + **7 partial** (GATE_LS 2/3, RTD_HW_FAULT 2/3,
bias 2/3, discharge.k_dis2-nc 2/4, gnd 53/88, power_in.ntc-no 3/4,
safety.uvlo_logic.mon-ina_p 3/4). No net can be reported "routed" on A*
finding a grid path alone.

## 8. Fabricability assessment

**Not fabricable as-is** — unchanged conclusion, mildly improved numbers:
1,732 DRC errors (clearance 499-capped, creepage 400, shorting 199-capped,
track_width 199-capped) still include real clearance breaks and shorts a
fab would reject; PD3 creepage remains unmet at placement level (T1/T2/U6
>half per handoff §7C). The **0 unconnected items** and **89/139
pad-connectivity with zero fake completions** are routing-quality
milestones, not fab sign-off. The route is no longer the binding
constraint — placement (K1/OVP cluster, PD3) and pour fragmentation are.

## 9. Remaining gaps (what remains)

1. **`power_in.ntc-no` pad-0 gap** — one missing via (was present 09:43).
   The net needs its layer bridge re-emitted or a re-place so 3 F.Cu/In3.Cu
   segments can reach the 4th pad. This is now the highest-value single
   routing fix; the Stage-3 memory bug is no longer the blocker.
2. **`+3V3` (50 pads) and `vcc` (13) still carry no copper** — UNEXPLAINED
   for two consecutive runs; the two largest broken nets.
3. **`SHUTDOWN`, `sclk`, `sdo`, `i2c_sda_ui`, `safety.uvlo_logic.mon-outa`,
   `hb.gate_hs.driver-p2`** regressed with the K1-cluster board — needs
   the 09:43-vs-now net-level diff walked per net against the moved
   components (board-change confound, not router regression).
4. **`tracks_crossing` 10 → 47** — new, unattributed; de-cap
   clearance/shorting/track_width first (199/499 caps hide the totals).
5. **PD3 creepage (12.6 mm) unmet at placement** — 400 creepage errors;
   owner decision PD2-vs-PD3 or re-placement (handoff §7C).
6. **Run-to-run churn** — this is one sample of a churn-prone router on a
   board that changed between runs; a `--runs N` distribution is the
   honest next measurement before claiming any ±3 net movement.
7. **gnd plane fill delivery unmeasured** — real KiCad zone-fill + DRC pass
   on this output is the documented next step (audit is fill-blind).

## 10. Artifacts

- Routed output: `/tmp/opencode/capstone-route.kicad_pcb` (1.64 MB)
- Route log: `/tmp/opencode/capstone-route.log` (963.7 s, 14/14 batches)
- Measurement scripts (adapted from the 09:43 run's):
  `/tmp/opencode/measure_capstone.py` (audit + stats + DRC),
  `/tmp/opencode/measure_net_route_result.py` (type-system cross-tab)
- Regenerated DRU (FinePitch 0.2 mm): worktree `pcb/temper.kicad_dru`
  (untracked; not committed — board's committed rules unchanged)
- Committed board untouched (sha256 `ddb96f9e...7ef2`); no DRU/clearance/
  creepage threshold changed; no `drc_ceiling.json` touched; no stash used;
  worktree venv isolated; shared repo venv untouched.
