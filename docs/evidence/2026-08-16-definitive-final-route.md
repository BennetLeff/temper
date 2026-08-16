<!-- provenance: commit=fdbe0a6ad2bed62f9bbe13dcd894db92ffbfe6a9 dirty=false -->
---
title: "Definitive final route on main with ALL router fixes — 92/139 pad-connected, 0 unconnected DRC items"
date: 2026-08-16
module: temper-placer
tags: [router, routing, capstone, pad-connectivity, nlayer, final-route, M1, M2, M3, M4]
problem_type: routing-completion
---

# Definitive final route: all router fixes on `main`

**One-line result:** with M1 (pad-layer landing) merged onto `main` alongside
the M2/M3/M4 + via-type + pad-avoidance + Rust-raster fixes (#1245), a fresh
batched 6-layer route of `pcb/temper.kicad_pcb` measures **92/139 fully
pad-connected** (up from 69 with M1 alone, 62/63 on the pre-#1245 6-layer
stack), **216 vias (93 through + 123 blind/buried)**, **0 unconnected DRC
items** (down from 329), and `power_in.ntc-no` — the net previously blocked
by the Stage-3 SAT memory bug — **fully connected at its required 5.0 mm
width**. The board is still **not fabricable**: 1,927 DRC errors remain,
dominated by the 499/199-capped clearance/shorting/track-width categories and
PD3 creepage.

## 1. Recipe

```
scripts/route_board.py --net-batching --batch-size 10 --output /tmp/opencode/definitive-route.kicad_pcb
```

- Worktree: `/tmp/opencode/agent-final-push` @ `fdbe0a6ad` (`main`, after
  #1246 = M1 squash-merge), isolated venv (`make venv-isolate` + `make
  extensions`, 10/10 fresh, shared repo venv untouched).
- Board: `pcb/temper.kicad_pcb` at `fdbe0a6ad` (sha256
  `077d4b6993c2708ea8d32572300f2964d2e0fb1634f903f5736b3a6eb38f2fda`),
  **not modified** by this work.
- Full log: `/tmp/opencode/definitive-route.log`; routed output:
  `/tmp/opencode/definitive-route.kicad_pcb` (2.2 MB).
- Wall time: **810.6 s** (~13.5 min), 14 batches, 14 solved at batch level,
  **0 crashed / 0 timeouts**. RSS stayed ~545 MB throughout — no Stage-3
  memory blowup this run (that bug is net-count-dependent; see handoff §6).
- Audit: `temper_placer.router_v6.pad_connectivity_audit.audit_pcb_file`
  (fixed #1200, on main) — the same fixed audit every recent number in this
  document was measured with.

## 2. Headline route stats

| metric | value |
|---|---|
| nets routed (Stage-3 topology) | 76/106 (71.7%) |
| fully pad-connected | **92/139** |
| fake-completion | 14 |
| honest-gap (neither) | 33 (6 zone-dependent-unmeasured) |
| segments | 7,972 |
| vias | **216** (93 through F.Cu↔B.Cu, **123 blind/buried**) |
| zones | 391 |
| wall time | 810.6 s |
| batches / crashes | 14 / 0 |

Segment layer spread: In3.Cu 2,529 · F.Cu 2,267 · In4.Cu 1,848 · B.Cu 1,328
— all four declared signal layers carry copper (not the pre-#1195
F.Cu/B.Cu-only shape).

## 3. Connectivity comparison — every prior run, same fixed audit

| run | fully connected | fake | honest-gap | source |
|---|---|---|---|---|
| committed board (essentially unrouted) | 27/139 | — | — | handoff 2026-08-15 |
| pre-PD3 4-layer | 53/139 | — | — | handoff |
| 6-layer pre-#1245 (honest / audit) | 62/139 / 63/139 | 64–65 | 13 | handoff; re-audited `final-route-6layer-output.kicad_pcb` → 62 |
| 6-layer + M1 only (agent 66) | **69/139** | 54 | 16 | re-audited `pad-layer-after.kicad_pcb` → 69 |
| **this run (ALL fixes: M1+M2+M3+M4)** | **92/139** | **14** | **33** | this document |

Movement: +23 nets over M1-only, +29–30 over pre-#1245 6-layer. The
fake-completion count collapsed 54 → 14: the fail-closed path converting
fake copper into either genuine completions or honest gaps, in the direction
this project has always wanted (fakes → real or honest, not honest → fake).

## 4. Specific nets

| net | pads | status | detail |
|---|---|---|---|
| `power_in.ntc-no` | 4 | **fully connected** | 3 segments @ **5.0 mm** on In3.Cu + 1 via (98.405,211.895) + 44 zone blocks across F.Cu/In3.Cu/In4.Cu/B.Cu. The net handoff §8 item 6 said needed the Stage-3 memory fix; its required width is 5.0 mm (`HighVoltage` class) — delivered. |
| `gnd` | 88 | fake (15/88 in trace graph) | In1.Cu plane exists (9 zone blocks) but the segment/via graph reaches only 15 pads; plane delivery is the unmeasured remainder. |
| `GATE_HS` | 2 | **connected** | 2 vias at **exact** pad coords (47.6025,115.35) and (82.735,137.555) — the M1 coordinate-level check. |
| `PWM_HS` / `PWM_LS` | 2 / 2 | **connected** | 2 vias each at exact pad coords. |
| `GATE_LS` | 3 | fake (2/3) | 1 landing via at R23.1; U5.1 (THT) still unreached — the known 2-of-3 hybrid, unchanged. |
| `+3V3` | 50 | broken | no copper at all (router dropped its zones; UNEXPLAINED in copper-audit). |
| `+170V_BUS` / `PWR_RTN` / `SW_NODE` / `ac_n` / `tank.c_tank1-p2` | 11/15/7/3/4 | zone-dependent | pour-covered nets; audit cannot see fill. |
| `SHUTDOWN` | 6 | **connected** | 6/6 — multi-pad net fully joined (M3). |
| `w1_1`, `discharge.k_dis1-nc`, `discharge.k_dis2-nc`, `safety.uvlo_logic.mon-outa`, `hb.gate_hs.driver-p2` | 4 | **connected** | 4/4 each. |

## 5. DRC (kicad-cli 10.0.5, `--all-track-errors`, sidecar-copied project)

| metric | committed board | prior routed 6-layer | **this run** |
|---|---|---|---|
| errors | 1,483 | 2,248 (unfilled) | **1,927** |
| warnings | 353 | 519 | 378 |
| unconnected items | 0 (no copper) | **329** | **0** |
| total (err+warn) | 1,836 | 2,767 | **2,305** |

Error categories this run: clearance 499 (cap), creepage 485, track_width 199
(cap), shorting_items 199 (cap), hole_clearance 199 (cap),
solder_mask_bridge 180, annular_width 86, copper_edge_clearance 47,
drill_out_of_range 20, tracks_crossing 10, hole_to_hole 1,
courtyards_overlap 1.

**The headline is the unconnected-items collapse: 329 → 0.** The router now
emits no pad that its own copper fails to touch — every remaining pad-level
gap is either a whole-net honest gap (zone-covered or unrouted) or a
fake-completion on nets whose copper partially joins. The remaining 1,927
errors are the known structural stack: clearance/shorting/track-width at the
499/199 KiCad caps, and PD3 (12.6 mm) creepage that the placed board cannot
meet without re-placement (handoff §7C: T1/T2/U6 alone account for >half;
net-new exposure excluding them ~64).

## 6. Per-mechanism verification (M1–M4 + the #1245 extras)

| mechanism | fix | verdict | evidence |
|---|---|---|---|
| M1 pad-layer landing | `_land_route_on_pad_layers` (#1246) | **works** | GATE_HS/PWM_HS/PWM_LS vias at exact pad coords; through vias 6 → 31 → 93 across the three runs; 9 M1-class nets connected |
| M2 zone rotation | rotation-correct pad positions in zone collection (#1245) | **works** | ntc-no pours span all 4 signal layers with correct pad attachment; 391 zones vs 314 pre-#1245 |
| M3 `enable_all_pad_tree=True` | all-pad terminal trees (#1245) | **works** | SHUTDOWN 6/6, ntc-no 4/4, five 4-pad nets fully joined |
| M4 gnd In1.Cu plane | `_ground_plane.py` In1.Cu pour (#1245) | **partial** | 9 In1.Cu gnd zones emitted, but trace graph reaches 15/88 pads — plane fill delivery is the unmeasured remainder |
| via-type emission | blind/buried tokens (#1245) | **works** | 123 blind vias (In3.Cu/In4.Cu ↔ F.Cu/B.Cu) in output |
| pad-avoidance | rotation-correct pad positions (#1245) | **works** | courtyards_overlap 1; landing vias sit on pads, not in them |
| Rust occupancy raster | 125× faster containment (#1245) | **works** | 810.6 s wall with 0 crashes; no Stage-3 blowup observed |

## 7. Fake completions — how many "routed" nets are real?

92/139 are real (graph-verified). 14 are fake (copper exists but does not
join all pads): `+15V`, `+15V_LS`, `DC_BUS_RTN`, `GATE_LS`,
`OCP2_VREF_2V5`, `RTD_HW_FAULT`, `WDT_RESET_N`, `bias`, `gnd`,
`hb.gate_hs.driver-p1-1`, `safety.coil_thermal-line`,
`safety.thermal.comp-inp`, `safety.uvlo_logic.mon-ina_p`, `vbias`. The 33
honest-gap nets carry no (or non-joining) copper and are reported as
unrouted — the fail-closed direction, per the audit's design.

## 8. Remaining gaps (not fixed)

1. **`gnd` (88 pads) not graph-connected.** Plane emitted on In1.Cu but the
   trace/via graph reaches 15 pads. Whether the plane actually delivers the
   rest is unmeasured (audit is fill-blind by design). **Highest-value next
   step**: a real zone-fill DRC pass (KiCad `fill zones` + DRC) on this
   output, which the router's `--enable-zone-pours` output is not.
2. **`+3V3` (50 pads) and `vcc` (13) have no copper.** Router dropped their
   zones; UNEXPLAINED in the copper-audit. These are the two largest
   remaining broken nets.
3. **PD3 creepage (12.6 mm) unmet at placement level** — 485 creepage
   errors, mostly placement/T1/T2/U6; needs re-placement or the
   PD2-vs-PD3 owner decision (handoff §7C).
4. **DRC clearance/shorting/track-width at 499/199 caps** — the routed board
   is denser; de-saturation and attribution is the same work the committed
   board's ceilings already track.
5. **Run-to-run churn remains** (~7 nets flip between identical-code runs,
   documented in agent 57's root-cause doc). This is one sample, not a
   distribution.

## 9. Fabricability assessment

**Not fabricable as-is.** 1,927 DRC errors (worst: clearance 499-capped,
creepage 485, shorting 199-capped, track_width 199-capped, hole_clearance
199-capped, solder_mask_bridge 180) exceed the committed board's ceiling
(1,298 err / 489 warn) and include real shorts/clearance breaks a fab would
reject. The **0 unconnected items** and **92/139 pad-connectivity** are
routing-quality milestones, not fab sign-off: the remaining errors are
structural (placement + PD3 creepage + pour fragmentation), which is
consistent with the handoff's assessment that placement, not the router, is
now the binding constraint.

## 10. Artifacts

- Routed output: `/tmp/opencode/definitive-route.kicad_pcb`
- Route log: `/tmp/opencode/definitive-route.log`
- Measurement script: `/tmp/opencode/measure_definitive.py`
- Prior artifacts re-audited with the same fixed audit:
  `/tmp/opencode/final-route-6layer-output.kicad_pcb` (62/139),
  `/tmp/opencode/pad-layer-after.kicad_pcb` (69/139)
- Committed board untouched (sha256 `077d4b...fda`); no DRU/clearance/
  creepage threshold changed; no `drc_ceiling.json` touched.
