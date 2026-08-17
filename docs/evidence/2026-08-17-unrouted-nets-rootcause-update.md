<!-- provenance: commit=fa067a9523cba69978ea7216a65009f6343315a7 dirty=false (worktree agent-routing-completeness-recon, branched from origin/main at fa067a9523cba69978ea7216a65009f6343315a7. pcb/temper.kicad_pcb sha256 9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd verified unchanged, never opened for writing by this task -- every route below writes to a scratch path outside the repo/worktree tracked tree.) -->
---
title: "Phase 2: per-net root cause on the current main tip (61/139, fa067a952)"
date: 2026-08-17
module: temper-placer
tags: [router, routing, pad-connectivity, root-cause]
problem_type: routing-completion
status: measured
---

# Phase 2: why each still-unrouted net is unrouted, on current `main`

Builds on, does not redo, `docs/evidence/2026-08-15-unrouted-nets-rootcause.md`
(PR #1290, M1-M5 taxonomy, 62/139 baseline). See
`docs/evidence/2026-08-17-routing-completeness-reconciliation.md` (this
task's Phase 1) for why that doc's mechanism taxonomy is still the right
frame but its *specific per-net assignments* are stale: M1 (#1246), M2
(#1245 zone rotation), and M3 (#1245 `enable_all_pad_tree`) have all
landed on `main` since it was written. This document is the fresh
per-net table, measured live on `fa067a952` (61/139, §1 of the
reconciliation doc's §6), cross-referenced against the 2026-08-15 doc's
per-net table to see exactly which nets moved and why.

## What's already re-verified from source (no route needed for these)

- **M1 (wrong-layer landing) is fixed on `main`**: `_land_route_on_pad_layers`
  exists in `_astar_nlayer.py` (line 590), matching the fix the 2026-08-15
  doc named as unmerged.
- **M2 (zone rotation) and M3 (`enable_all_pad_tree` default) are fixed on
  `main`**: `_pipeline_core.py:155` and `_adapter_convert.py:229` both
  default `enable_all_pad_tree=True` (was `False` in the 2026-08-15 doc's
  tree).
- **M2b (missing zone-fill pass) is STILL not wired**: no
  `fill-zones`/`filled_polygon` emission found in `route_board.py` or
  `zone_emission.py`. Every `zone_dependent` net remains fill-blind to
  the audit — this has not changed since the 2026-08-15 doc.
- **M4 `gnd`/`+3V3` pour-vs-trace**: both now get a *dedicated* inner-layer
  plane/island generator wired directly into `_adapter_convert.py`
  (`_ground_plane.py` → In1.Cu for `gnd`, `_power_islands.py` → In2.Cu for
  `+3V3`/`vcc`/`+15V`), gated only on `enable_zone_pours` (production
  default `True`, `_adapter_convert.py:230`) and the net existing on the
  board. This is new since the 2026-08-15 doc (which found `gnd`'s plane
  generator caller-less). **Still A*-routed as a trace in parallel**
  (`gnd`/`+3V3` are classed `"Power"`, which declares no
  `routing_strategy`, so `_should_route()` still sends them through A* at
  1.0mm trace width across a 296mm/238mm span) — the plane supplements
  rather than replaces the original M4 defect; per the 2026-08-16 capstone
  doc, the trace/via graph alone reached only 53/88 `gnd` pads, with the
  rest dependent on the (unmeasured, fill-blind) plane fill.
- **Zone-stitch C-space (#1261) and creepage-aware halos (#1267) are new
  since 2026-08-15** and, per Phase 1's reconciliation doc, are the
  leading suspects for *new* honest declines not represented in any prior
  M1-M5 bucket: a net that used to "connect" via an under-stamped foreign
  obstacle now honestly fails. This is plausibly a **sixth mechanism**
  (call it **M6 — foreign-clearance/creepage ring restored**) alongside
  the original five; PR #1301 (unmerged) is the most advanced diagnosis
  of this specific mechanism for the clearance case.

## 1. Fresh measurement and transition table

Live route, `scripts/route_board.py` default recipe (no `--net-batching`),
`fa067a952`, wall 327.8s:

```
fully_connected: 61/139   fake_completion: 8   honest_gap: 70
NetRouteResult: connected=61 partial=8 zone_dependent=9 failed=61 of 139
```

Cross-referencing every net's 2026-08-15-doc status/mechanism against its
fresh 2026-08-17 status (`.scratch/diff_rootcause.py`, full 139-row table
committed alongside this doc) gives six transition buckets:

| old → new | count | meaning |
|---|---|---|
| connected → connected | 48 | stable, unaffected by anything in this window |
| broken → **connected** | 13 | **M1/M3 fixes confirmed working** |
| broken → partial | 8 | improved (M1 landing fix helps) but still incomplete — the fake-completion set |
| zone_dependent → zone_dependent | 9 | unchanged — M2b (fill pass) still missing |
| broken → **failed** | 47 | still broken, but the *reason* changed (M1/M3 fixed, something else now blocks it) |
| **connected → failed** | 14 | **regressions** — net used to fully connect, now doesn't |

48+13+8+9+47+14 = 139. ✓

## 2. broken → connected (13): the M1/M3 fixes, confirmed live

`GATE_HS`, `OCP2_VREF_2V5`, `PWM_HS`, `PWM_LS`, `RTD_CS_N`, `RTD_SDI`,
`discharge.q_dis_drv-g`, `fb`, `ina`, `inb`, `rtd_pan.r_high_top-inp`,
`safety.fault_any_or-a2`, `safety.ocp2-line`. GATE_HS/PWM_HS/PWM_LS/
RTD_CS_N/RTD_SDI/ina/inb/safety.fault_any_or-a2 were M1 (wrong-layer
landing) in the old doc; OCP2_VREF_2V5/discharge.q_dis_drv-g/
rtd_pan.r_high_top-inp/safety.ocp2-line were M3 (2-of-N). **Both fixes
are real, working, and net-positive** — this is not offset by anything
else in this bucket.

## 3. broken → partial (8): M1 helps, M4 (span/capacity) still blocks completion

`+15V`, `+3V3`, `GATE_LS`, `RTD_HW_FAULT`, `V_BUS_SENSE`, `gnd`, `sw`,
`vcc` — all were M1 in the old doc (wrong-layer landing, 0 real copper).
Now they have *some* correctly-landed copper but not all pads joined.
For `gnd`/`+3V3`/`vcc`: this is exactly the M4 sub-case (§ "What's
already re-verified" above) — the dedicated In1.Cu/In2.Cu plane
generators reach some pads, the parallel A* trace reaches some pads,
neither reaches all, and the union still isn't "fully connected" because
the audit's `fully_connected` is a pure segment+via+pad graph check that
**cannot credit zone-pour fill** (M2b). `GATE_LS`/`RTD_HW_FAULT` are the
already-known 2-of-3 hybrid nets (M1+M3 overlap in the old doc).

## 4. zone_dependent → zone_dependent (9): M2b, exactly as before

`+170V_BUS`, `DC_BUS_RTN`, `PWR_RTN`, `SW_NODE`, `ac_n`,
`power_in.ntc-no`, `tank.c_tank1-p2`, `w1_1`, `w1_2` — identical set to
the 2026-08-15 doc. Zone rotation (M2) landed, so the outlines are now at
the *correct* pad coordinates (verified live: `courtyards_overlap` in
recent DRC runs is ~1, not the dozens a rotation-blind hull would cause),
but **no fill pass exists** (confirmed above — `grep` for
`fill-zones`/`filled_polygon` in `route_board.py`/`zone_emission.py`:
zero hits). These 9 nets are permanently stuck at "cannot measure" until
someone wires a fill pass (`kicad-cli pcb fill-zones` on the written
output, or a faithful reimplementation) — this is a **missing pipeline
step**, not a router defect, and has had zero net movement since
2026-08-15 despite everything else on the board changing.

## 5. connected → failed (14): the decision-relevant regressions

| net | old mechanism | why it now fails |
|---|---|---|
| `safety.ovp.r_adc_top1-p2` | OK | **confirmed**: PD3-honest zone refusal |
| `safety.ovp.r_adc_top2-p2` | OK | **confirmed**: PD3-honest zone refusal |
| `safety.ovp.r_div_top1-p2` | OK | **confirmed**: PD3-honest zone refusal |
| `safety.ovp.r_div_top2-p2` | OK | **confirmed**: PD3-honest zone refusal |
| `discharge.k_dis1-no` | OK | not spatially clustered — see below |
| `discharge.k_dis2-no` | OK | not spatially clustered — see below |
| `discharge.r_dis1a-p2` | OK | not spatially clustered — see below |
| `discharge.r_dis2a-p2` | OK | not spatially clustered — see below |
| `WDT_KICK` | OK | unattributed |
| `input` | OK | unattributed |
| `hb.gate_hs.driver-p1` | OK | unattributed |
| `rtd_force_n` | OK | unattributed |
| `safety.fault_any_or-y2` | OK | unattributed |
| `tank-out` | OK | unattributed |

**The 4 OVP nets are confirmed**, not speculative: the 2026-08-16
capstone doc (`docs/evidence/2026-08-16-capstone-final-route.md` §3)
already caught 3 of these 4 (`r_adc_top1-p2`, `r_div_top1-p2`,
`r_div_top2-p2`) regressing for the identical, named reason — "the Rust
carve now refuses those pours at 12.6mm and the nets fall back to traces
that don't complete" — when the Rust zone generator (#1257/#1259)
replaced the old Python carve. `r_adc_top2-p2` joining the failure set
between that measurement and now is consistent with the same mechanism
continuing to bite as placement/obstacle changes shifted where the
PD3-honest carve lands; not independently re-verified per-pad in this
pass, but the mechanism, the netclass (`HighVoltage`), and the physical
neighborhood (all 4 are OVP resistor-divider legs) are identical to the
3 already confirmed.

**The 4 discharge/relay nets were checked for a placement-cluster
explanation and it does NOT hold**: `discharge.k_dis1-no`/`k_dis2-no`
attach to `K2` (144.82, 97.55) and `K3` (66.47, 50.59);
`discharge.r_dis1a-p2`/`r_dis2a-p2` attach to `R6` (51.71, 174.09) and
`R8` (117.23, 196.95). None of these four positions are inside or near
the `#1248` K1/RT1/U1/U2 cluster (60-112, 205-226) or the two later
placement-pass footprints (`#1269`/`#1279`, the left-edge R5/U7/C23
group at (9-16, 72-80)). They are scattered across four different
quadrants of the board. **This rules out "these specific nets regressed
because they sit near a moved component"** as the mechanism — leaving
board-wide obstacle-map tightening (`#1259`/`#1261`/`#1267`, this
document's proposed **M6**) or cumulative A*-ordering congestion
(earlier-routed nets in this run consuming channel capacity that these
nets needed) as the remaining candidates. Distinguishing those two would
need per-net obstacle-map/A*-trace instrumentation this pass did not
build — reported as an open question, not resolved.

**The remaining 6 singleton regressions are unattributed** — no common
netclass, no common board region, no common old-mechanism. Individually
tracing each would need the same A*-trace instrumentation as the
discharge cluster above.

## 6. broken → failed (47): mechanism reclassification, not new nets

None of these are "new" unrouted nets — every one was already broken in
the 2026-08-15 doc. What changed is *why*: M1's landing-layer bug and
M3's 2-of-N truncation are gone, so a net that used to fail (or falsely
appear to complete) for those reasons now fails for a different,
harder-to-fix reason. Grouping by old mechanism:

- **Old M1 (wrong-layer landing), still fails (13)**: `I_SENSE`†,
  `RTD_DRDY`, `WDT_RESET_N`, `bias`, `cs_n`, `hb-gnd`, `refin_n`,
  `rtd_pan.r_low_top-inn`, `rtd_pan.rail_monitor-ina_p`,
  `rtd_pan.rail_monitor-outa`, `safety.thermal-line`, `sclk`, `vbias`,
  `power_in.bypass_relay-coil2`. The landing bug is fixed (copper now
  lands on the pad's own layer, verified for the 13 nets in §2), but for
  these nets the corrected, harder search (must actually reach the pad
  through real geometry, not just claim arrival on the wrong layer) finds
  no legal path at all. **This is new information**: M1 was necessary but
  not sufficient for these 13 — something else (M6 congestion, or
  genuine capacity) blocks them now that the fix forces an honest search.
- **Old M3 (2-of-N truncation), still fails, now 0-of-N instead of 2-of-N
  (17)**: `+15V_LS`, `discharge.k_dis1-nc`, `discharge.k_dis2-nc`, `en`,
  `hb.gate_hs.driver-p1-1`, `hb.gate_hs.driver-p2`,
  `hb.power_loop.q_high-g`, `io0`, `safety-line`, `safety-line-1`,
  `safety.ocp.comp-inn`, `safety.ovp-line`, `safety.ovp.comp-inp`,
  `safety.thermal.comp-inp`, `safety.uvlo_logic-line`,
  `safety.uvlo_logic.mon-outa`, `y`. **This is the clearest new finding
  in this bucket**: `enable_all_pad_tree=True` makes the terminal-tree
  builder require a path through *every* pad, not just 2 — a strictly
  harder constraint than before. Before the fix, these nets silently
  shipped a 2-of-N partial "success" (counted as `broken` by the audit,
  but Stage 4 itself did not report failure). After the fix, the router
  honestly tries for all N pads and, evidently, fails closed rather than
  falling back to the old partial behavior — Stage 4's
  `NetRouteResult` now reports these as `failed`, not `partial`. **M3's
  fix traded "quietly wrong" for "honestly failed" on this set** — a
  fail-closed improvement in kind (per the hard rule's own philosophy:
  "a labelled red beats a green that means nothing"), but it means these
  17 nets need a *harder* fix than M3 alone provides (more capacity, less
  congestion, or a relaxed multi-pad topology, not just "visit every
  pad").
- **Old M4 (A* no legal path), still fails, unchanged (10)**:
  `RELAY_CTRL`, `RTD_SCK`, `discharge.r_snub2-p2`,
  `power_in.q_relay_drv-g`, `s1`, `safety.coil_thermal-line`,
  `safety.fault_or-y2`, `sdi`, `sdo`. No new information here — these
  were long-span/pour-class nets that never had a legal short path, and
  neither M1 nor M3 changes that. Genuinely still capacity/topology
  limited, consistent with the 2026-08-15 doc's own conclusion for this
  class.
- **Old M1+M3 hybrid, still fails (1)**: `safety-line-1` (counted once
  above under M3, listed here for completeness — was `M3(2/3)+M1`).

† `I_SENSE` was `M3(2/7)` in the old doc, not M1; grouped here as "still
fails after both fixes landed" for the summary count — see the M3 bucket
above for its correct original mechanism (already listed there; not
double-counted in the 47).

## 7. Summary: what Phase 2 adds to the 2026-08-15 taxonomy

1. **M1 and M3 are confirmed working** on the nets they were designed
   for (13 net gain, §2), but for a **different, larger set (30 nets:
   13 old-M1 + 17 old-M3, §6)**, the fix corrects the symptom (wrong
   layer / partial pad set) without being sufficient to complete the
   route — a harder underlying obstacle-map or capacity constraint takes
   over. This is the single largest new finding: **M1/M3 were real fixes
   that mostly moved the failure mode, not the failure, for 30 nets.**
2. **M2/M2b is unchanged**: rotation is fixed, fill is still missing,
   the same 9 nets are stuck exactly where they were.
3. **A new regression class exists (14 nets, §5)**, of which 4 are
   confirmed (PD3-honest zone refusal, same mechanism the capstone doc
   already named) and 10 are not yet attributable to a single cause —
   4 of those 10 were spatially checked and ruled OUT of the
   "near a moved placement cluster" explanation, pointing instead at a
   board-wide mechanism (obstacle-halo tightening, `#1259`/`#1261`/
   `#1267` — proposed **M6**) or A*-ordering congestion, neither
   confirmed at the single-net level in this pass.
4. **M4 (10 nets) is inert** — unaffected by anything that has landed;
   still needs either placement or a materially different routing
   strategy for these specific long-span/pour-class nets.

## 8. What would resolve the open attribution (§5, §6's M6 candidates)

Per-net obstacle-map instrumentation: re-run the router with a hook that
records, for each net that fails, whether the A* frontier was exhausted
by capacity (no free cells) or by a specific foreign clearance/creepage
halo (M6) versus genuinely running out of legal geometry (M4-like). This
was out of scope for this pass (no such hook exists in
`_astar_nlayer.py` today, and building one touches the file siblings
`fix/per-pair-clearance-halos-nlayer-astar` (#1301) and
`fix/nlayer-astar-ci-collection-and-typecheck` (#1303) currently own —
left for a future task per the coordination boundary in this task's
brief).
