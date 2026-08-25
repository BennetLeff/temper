<!-- provenance: commit=959a96852826880ac872b8a8ef2276d1b6497fc5 dirty=UNKNOWN -->
---
module: pcb
tags: [routing, drc, zone-stitch, c-space, track-width, netclass, gnd, power, coil]
problem_type: bug
date: 2026-08-16
---

# Route-to-100%: zone-stitch C-space gate + Power-class coil width (2026-08-16)

**Purpose**: close the two largest DRC violation families on the
2026-08-16 capstone route (89/139 nets): (1) `shorting_items` from the
zone-stitch emitter's straight pad-to-pour lines and gnd's MST fallback
backbone that never consulted any occupancy data, and (2) `track_width`
violations from the relay-coil nets and gnd backbone emitting below the
DRC-enforced netclass minimum width.

**Status**: both fixes committed on `fix/route-to-100-percent`
(2988df485, 5759fa5ae), base `origin/main` @ `607cc7bd6`. Route
re-measured in this document.

**Branch**: `fix/route-to-100-percent` (worktree `/tmp/opencode/agent-route-100`).

---

## 1. Baseline measurement (capstone route, 2026-08-16, pre-fix)

`kicad-cli pcb drc` on `/tmp/opencode/capstone-route.kicad_pcb` (the
pre-fix route, 89/139 nets): 2129 total violations, 226 unconnected
items. KiCad caps every category at ERROR_LIMIT 199 / EXTENDED_ERROR_LIMIT
499, so `shorting_items=199` and `track_width=199` are **caps, not
counts** (handoff §2.4). The uncapped counts were established directly:

- **track_width, TRUE count 747** (width-vs-class-min audit, same rule
  the DRU encodes): 531 Power-class (coil nets at 0.2mm vs 1.0mm min) +
  216 GND-class (gnd backbone at 0.4mm vs 1.0mm min).
- **shorting_items** dominated by the zone-stitch straight lines: sample
  items include `Track [DC_BUS_RTN] on F.Cu, length 159.8-193.7mm` and
  `Track [gnd] on F.Cu, length 55.2mm` (shorting `hb-gnd` pad 1 on T2).
  Net pairs: DC_BUS_RTN 48, PWR_RTN 47, gnd 35, SW_NODE 30, +170V_BUS
  27, safety.ovp.comp-inp 26 tracks involved.

## 2. Fix 1: the zone-stitch emitter consults C-space

The zone-stitch emitter (`router_v6/_zone_pour_stitch.py`,
`_stitch_isolated_pads`) emitted straight pad-to-nearest-pour-vertex
lines for every zone-eligible net with **zero** consultation of any
occupancy data. On the pre-fix board these were 5mm-wide (the
HighVoltage netclass width) lines up to 193mm long crossing unrelated
nets' copper wholesale. The gnd MST fallback (`_ground_plane.py`) was a
second instance of the same class: its keepout-only `_blocked()` check
let straight fallback edges cross other nets' existing F.Cu copper (the
55.2mm edge shorting hb-gnd).

Two fail-closed gates, each strictly *removing* copper the DRC rejects
(never a weakening):

1. `_stitch_isolated_pads` now checks every proposed segment against the
   **same per-pair obstacle records the Rust zone carve consumes**
   (`collect_zone_obstacle_records`: other nets' copper on the stitch
   layer, each item buffered by its own `max(clearance, creepage)` pair
   separation, including the segments/vias this route emitted). A
   segment whose buffered footprint intersects a foreign obstacle is
   skipped, logged per net, never emitted.
2. `_ground_plane.py`'s fallback `_blocked()` now also rejects a
   straight edge that crosses `other_copper_fcu_backbone` (the
   per-pair-clearance union already computed for the A* obstacle grid —
   reused, not re-derived). The one-bend detour shares the check.

**Connectivity consequence, measured**: the gnd audit floor dropped
15 → 4/88, and this is a *downward correction*, not a regression — the
old floor was partly built on shorting copper the audit counted as
connected while DRC flagged it as electrical shorts between different
nets. The In1.Cu plane still covers all 88 pads electrically (the audit
is zone-blind by documented design); the honest corridor-clean backbone
connectivity is 4/88. The test floor was re-pinned with this rationale
(`test_ground_plane.py`). A labelled gap beats emitting shorts.

## 3. Fix 2: Power-class coil nets emit at 1.0mm (was 0.2mm)

**Root cause — NOT a width pass-through bug.** The emitted width always
reached the copper; the *two homes of the netclass disagreed*:

| home | coil-net class | role |
|---|---|---|
| `core/design_rules.py` TEMPER_NET_ASSIGNMENTS (2026-08-13) | Signal (0.2mm) | router width SSOT |
| `pcb/temper.kicad_pro` netclass_assignments (2026-08-12, #1087) | Power (1.0mm min) | what kicad-cli's DRC reads |
| `configs/temper_production_config.yaml` | Power | original intent ("relay coil drivers into Power") |

The 2026-08-13 Signal declaration's PRIMARY purpose — blocking the
hyphen-boundary-widened "COIL" keyword from reclassifying these nets
HighCurrent (safety_category "HV") — survives unchanged under an
explicit Tier-2 Power entry (explicit wins over the cascade; Power !=
HighCurrent; safety_category stays LV). Aligning the router's emitted
width with the DRC-enforced class emits strictly WIDER copper (the
conservative direction) and matches the router's own C-space halos
(already Power 0.5mm clearance, read from kicad_pro).

The design_rules oracle was re-pinned (deliberate, exactly 1 hash moved,
keep-in-sync convention).

**gnd backbone width, same commit**: `STITCH_TRACE_WIDTH_MM` 0.4 → 1.0.
The DRU's "Ground trace width" rule (min 1.0mm, from kicad_pro's
declared GND class, which mirrors `TEMPER_NET_CLASSES["GND"]`
trace_width=1.0) flagged all 216 gnd backbone/stub segments — the other
216 of the 747 uncapped track_width violations.

## 4. Result (post-fix routes)

Two post-fix routes, each ~16.5 min wall (`--net-batching --batch-size 10`,
worktree venv):

| metric | pre-fix capstone | v1 | v2 | **v3 (final)** |
|---|---|---|---|---|
| pad connectivity (PRIMARY) | 89/139 | 88/139 | 88/139 | **88/139** |
| fake completions | 13 | 8 | 7 | **7** |
| total kicad-cli violations | 2129 | 1639 | 1379 | **1364** |
| track_width (TRUE count) | 747 | **0** | **0** | **0** |
| shorting_items | 199 (capped) | 195 | 18 | **11** |
| tracks_crossing | 48 | 24 | 2 | **0** |
| solder_mask_bridge | 123 | 13 | 7 | **1** |
| hole_clearance | 128 | 85 | 26 | **24** |
| creepage | 400 | 312 | 310 | **311** |
| clearance | 500 (cap) | 499 (cap) | 499 (cap) | **501 (cap)** |
| silk_overlap | 199 (cap) | 199 (cap) | 199 (cap) | **199 (cap)** |

v1 fixes (commits 2988df485 + 5759fa5ae) removed the gnd/DC_BUS/PWR_RTN
stitch straight lines (all 31 stitch segments across 9 nets skipped by
the new gate, logged) and fixed every track_width violation, but exposed
two residual straight-line/via families: ntc-no's In3.Cu MST edges
shorting w1_2's In3.Cu tracks (76 of the 195), and gnd drop vias landing
on this route's own In3.Cu/In4.Cu tracks (61). Commit 438b18e4b extends
the gates: per-pair obstacle check on the In3.Cu MST edges, emitted-
copper awareness in via placement + backbone corridor/fallback, and a
buffered (real-footprint) fallback `_blocked` test. v2 (1379) shows the
effect: shorting 195 -> 18, tracks_crossing 24 -> 2, hole_clearance
85 -> 26. The 18 residual shorts break down as ~6 gnd via-STUB segments
(pad->offset-via lines not footprint-checked; fixed by d0a97cf6e) and
~12 N-layer A* machinery-internal via-vs-track shorts on In3.Cu/In4.Cu
(a different bug class -- the A* router's own via placement, not the
stitch emitters; out of this task's scope, see §6).

## 5. What still blocks 100% connectivity / DRC-zero

**Connectivity (88/139, target was >92/139 -- not reached).** The 51
un-connected nets break down as 37 failed (no copper), 7 partial, 7
fake-completion. Pre-fix was 89 with 13 fakes; the -1 net is
`power_in.ntc-no`, which moved from fake-completed to HONESTLY failed:
its last In3.Cu straight MST edge was skipped by the C-space gate
because it shorted w1_2's 5mm In3.Cu tracks -- the previous "connected"
was fabricated by shorting copper. The blocking factors are unchanged
from the handoff: the 7 zone-only HV nets (PWR_RTN, DC_BUS_RTN, SW_NODE,
+170V_BUS, ac_l, ac_n, power_in.ntc-no) are excluded from A* and their
zones are outline-only at PD3 creepage (no fill credit in the audit);
+15V/+3V3/V_BUS_SENSE/Power-class rails are A*-excluded but not zone-
eligible either (SSOT says trace, not pour -- and the coil nets
discharge.k_dis1-coil2/k_dis2-coil1/power_in.bypass_relay-coil1/-coil2
now at their required 1.0mm width fail to find corridor-clean paths in
the dense relay area); the remaining ~20 are A* corridor failures in
dense regions.

**DRC-zero blockers, ranked:**
1. clearance 501 (capped -- true count >=501; the DRU's HV-vs-SELV
   12.6mm creepage-style clearance rules and dense placement) --
   pre-existing family, not routing-created; the route only added 1-2.
2. silk_overlap 199 (capped) -- pre-existing footprint silk collisions,
   unrelated to routing (same 199 pre-fix).
3. creepage 311 -- the PD3 enforcement families (T1/T2/U6 + K1,
   handoff §7C).
4. annular_width 68 / holes_co_located 60 / via_dangling 44 /
   copper_edge_clearance 35 / drill_out_of_range 20 -- fab-rule
   families, pre-existing.
5. shorting_items 11 -- ALL are the N-layer A* machinery's own
   via-vs-track shorts on In3.Cu/In4.Cu (safety.uvlo_logic.mon-ina_p
   vias vs thermal.j_fan-p1/comp-inp tracks, r_adc_top2-p2 In4.Cu
   track vs WDT_KICK/mon-ina_p vias, sw via vs safety-line-3, tank
   vs vbias blind via, boot vs r_adc_top2-p2 blind via). This is a
   DIFFERENT bug class from this task's (the A* router's own via
   placement does not consult the width-aware C-space for the via's
   inner-layer barrel clearance against tracks routed on other layers
   -- #1249 fixed track halos, not via-vs-inner-track). The straight-
   line emitters this task gated are all clean: zero stitch, stub, or
   fallback shorts remain.

## 6. Notes for the record

- **`w1_1`/`w1_2` route on In3.Cu despite being HighVoltage zone-covered**:
  `_should_route`'s HV keyword classifier (`net_classification.is_hv_net`)
  does not recognize the `w1_1`/`w1_2` names, so they fall through to
  A* (5.0mm tracks on In3.Cu/In4.Cu) instead of being zone-only. That is
  not itself a defect (real, clearance-respecting copper is fine; the
  zone carve now carves around those tracks) -- but it is why ntc-no's
  In3.Cu MST edges shorted, and it is a latent classification drift worth
  an owner look: either declare `w1_1`/`w1_2` explicitly in the HV
  keyword set, or accept them as A*-routed-by-design and keep the gates.
- `Differential` (USB) class still declares `track_width: 0.127` in
  kicad_pro (below the board's 0.2mm min) — latent, not live: the
  router has no Differential SSOT entry and emits usb nets at the
  Default catch-all width; no usb tracks exist on the routed board. If
  usb routing is ever enabled, #1255-style width fix applies.
- `pcb/temper.kicad_pro`'s netclass_assignments is missing four HV
  divider nets the SSOT declares HighVoltage (`safety.ovp.r_adc_top1-p2`,
  `r_adc_top2-p2`, `r_div_top1-p2`, `r_div_top2-p2`) — they fall to
  Default (0.2mm) in DRC while the router treats them as HighVoltage
  (2.0mm). This is the *opposite* drift direction (under-classified, no
  DRC violation cost); adding them would STRENGTHEN DRC enforcement and
  is flagged for owner decision, not done here.
- `scripts/sync_kicad_netclass_assignments.py --check` fails on the
  pre-existing CGND protection ('CGND' now resolves to a declared GND
  class) before reporting any diff — the coil-net drift it would have
  caught was invisible behind that refusal.
- Pre-existing, unrelated to this fix: `test_pad_identity.py` two
  failures (`Component(initial_rotation=...)` API drift) and the two
  `zone_pour_*` stale-table tests fail on any fresh checkout
  (`pcb/temper.kicad_dru` is not a tracked file).
