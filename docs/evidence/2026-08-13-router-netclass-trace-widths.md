<!-- provenance: commit=8fb30497f248b5659e0b929f199020d720b8edf7 dirty=true -->

<!-- Worktree .claude/worktrees/rt-netclass, branch fix/router-netclass-trace-widths, based on origin/main 344ebf765 (which contains #1110 DRU precedence, #1111 uncapped DRC, #1113 router clearance floor). dirty=true because this document is committed together with itself. Isolated venv (`make venv-isolate` + `make extensions`), so no build was written into the shared .venv. kicad-cli 10.0.5. pumpkin_engine identity gate VERIFIED (sha256=7ff153f4..., source_commit=5bbf650d), exit 0, before any solve -- though this session runs no placement solve at all (see sec 6). `pcb/temper.kicad_pcb` and `power_pcb_dataset/drc_ceiling.json` are NOT modified by this work; every board measured below is a scratch route written outside the repo. `.kicad_dru` regenerated from scripts/generate_kicad_dru.py into every scratch DRC directory alongside `fp-lib-table` and `libs/`. -->

# 3.0mm is not enough copper for this board's 15A mains, and the router was emitting 0.2mm

**Date:** 2026-08-13
**Branch:** `fix/router-netclass-trace-widths`
**Board:** unchanged. Two full scratch routes, byte-identical except for `(width ...)`.

---

## 0. Lead finding: the netclass figure is itself short

The task asked me to verify 3.0mm against the repo's own IPC-2221B method
rather than assume the netclass is right. It is not right.

`docs/hardware/TRACE_WIDTH_CALCULATIONS.md` §1 declares, as this board's
design parameters:

| parameter | declared value |
|---|---|
| Ambient temperature | 60 °C |
| **Max temp rise (traces)** | **20 °C** |
| Max temp rise (pours) | 40 °C |
| Outer copper weight | 2 oz (70 µm) |

and §2 gives `I = k · ΔT^0.44 · A^0.725`, k = 0.048 external, t = oz × 1.37 mils.
Re-derived with those exact numbers (`ipc.py`, this session):

| current | why this current | ΔT | required width |
|---|---|---|---|
| **15 A** | design load, `elec/src/constraints.ato` `i_max` (1800 W / 120 V) | **20 °C (trace)** | **4.16 mm** |
| 15 A | same | 40 °C (pour) | 2.73 mm |
| 16 A | F1 fuse rating (Schurter 0034.3129) | 20 °C | 4.54 mm |
| 16 A | same | 40 °C | 2.98 mm |
| 20 A | K_BYPASS contact rating (Omron G4A-1A-E) | 20 °C | 6.18 mm |

Read in the other direction, at the widths actually in play:

| width | what it is | ampacity @20 °C rise | @40 °C rise |
|---|---|---|---|
| 0.200 mm | what the router emitted for `w1_2` | **1.66 A** | 2.26 A |
| 0.508 mm | what the router emitted for `power_in.ntc-no` | **3.27 A** | 4.43 A |
| 0.635 mm | the keyword classifier's `hv_width` | 3.84 A | 5.21 A |
| **3.000 mm** | **`HighVoltage`/`ACMains` netclass `trace_width`** | **11.84 A** | 16.07 A |
| 4.000 mm | `TRACE_WIDTH_CALCULATIONS.md` §4, **AC Mains row** | 14.59 A | 19.79 A |
| 5.000 mm | same table, DC Bus row | 17.15 A | 23.27 A |

**Verdict: 3.0mm does not suffice for 15A.** Three independent reasons, all
from the repo's own documents:

1. **Against the declared trace limit it is 28% short.** These nets are
   emitted as *tracks*, not pours. The doc's trace budget is a 20 °C rise;
   at that budget 15 A needs 4.16 mm and 3.0 mm carries 11.84 A — a 21%
   current shortfall on the appliance's continuous full-load current, in a
   60 °C ambient.
2. **The hardware spec's own summary table already says 4.0mm.**
   §4's AC Mains row reads `15A | 2 oz ext | 40°C | 4.0mm pour | ACMains`.
   The netclass table says 3.0mm for both `ACMains` and `HighVoltage`. Two
   in-repo sources disagree by 25% on the single most safety-critical
   conductor on the board, and the router follows the narrower one.
3. **Even the generous reading has no margin.** Granting the 40 °C *pour*
   allowance to a *trace* (copper at 100 °C, ambient 60 °C), 3.0 mm gives
   16.07 A against a 15 A load — 7% headroom — and against the **16 A fuse**
   that is supposed to be the protective limit, 3.0 mm needs to be 2.98 mm,
   i.e. **0.7% margin**. A fuse rated above the trace's own ampacity does
   not protect the trace.

The same arithmetic condemns `HighVoltage`'s 3.0mm for its other declared
role: §3.1 puts the DC bus at 22 A peak and recommends 5.0 mm; correctly
evaluated, 22 A at 40 °C needs 4.63 mm. (§3.1's worked arithmetic is itself
wrong in the safe direction twice — it uses 4.57 for `40^0.44`, which is
5.069, and `100.2^1.38 = 478` where it is 578 — so the doc's prose
under-reports required width while its summary table happens to land higher.)

At the routed lengths this session measured, 3.0 mm mains copper also
dissipates real power:

| net | routed length | layer | R @3.0mm/2oz | P @15A | V drop @15A |
|---|---|---|---|---|---|
| `w1_2` | 52.41 mm | F.Cu | 4.19 mΩ | 0.94 W | 62.9 mV |
| `power_in.ntc-no` | 85.27 mm | B.Cu | 6.82 mΩ | 1.53 W | 102.3 mV |

**This is a bigger finding than the router bug and it is the owner's call.**
Raising `HighVoltage`/`ACMains` `trace_width` to the 4.0mm its own hardware
spec prescribes is a safety-number change with board-feasibility
consequences (§5 shows 3.0mm already collides with a Y-capacitor pad), and I
did not make it unilaterally. **The router fix below is necessary and not
sufficient**: it makes the router obey the table; it cannot make the table
right.

---

## 1. The router defect

`packages/temper-placer/src/temper_placer/router_v6/trace_width_assignment.py`
Stage 4.4 chose every emitted width from three hardcoded buckets keyed on the
net **name** (`default 0.127 / power 0.508 / hv 0.635` mm), with **zero**
references to `TEMPER_NET_CLASSES` or `get_rules_for_net`.

That is the fourth confirmed instance of one defect class in this repo — a
net-name keyword classifier drifting from the authoritative net-class table
(`creepage_check.py`, `clearance_check.py`, `clearance_engine.py` are the
first three, all cited in this file's own bug-history comments). Three things
made it survive:

- Nets whose real spelling contains none of the keywords (`zcd`, `a`, `w1_2`,
  `power_in.ntc-no`, `discharge.k_dis1-nc`, `hb.power_loop.q_high-g`,
  `hb.gate_hs.driver-p1-1`, `hb.gate_hs.driver-p2`) fell to `default_width`.
- A *correct* keyword hit was still wrong: `hv_width` is 0.635mm against a
  `HighVoltage` requirement of 3.0mm — 21%. `GATE_LS` matched `"GATE"` and
  got `power_width × 0.6` = 0.3048mm against `GateDriveHV`'s 0.4mm.
- The fallback was **silent**. Nothing logged, nothing failed.

It is also inconsistent with the code immediately around it. `place_vias`,
the Stage 4.3 call one line above, already takes `design_rules`. Stage 4's own
A* (`_astar_reconstruct.py`) already reserves corridor at
`net_rule.trace_width_mm`. Only the emitted *label* used keywords.

### 1.1 A second site, found by measuring rather than assuming

Fixing Stage 4.4 alone left a residual. `_zone_pour_stitch._stitch_isolated_pads`
— the emitter that joins a zone-eligible net's outlying pads back to its own
pour — wrote `(width 0.2000)` as a literal. Zone eligibility is granted only
to classes declaring `routing_strategy plane_required`/`plane_preferred`,
which on this board are exactly `ACMains` and `HighVoltage`, so that literal
was **by construction only ever applied to mains and DC-bus copper**. Both
sites are fixed; §3 shows the residual it accounted for.

---

## 2. Method

Two full production routes through `scripts/route_board.py --net-batching`,
identical in every respect except the two source files:

- **baseline** — `_pipeline_route.py` / `trace_width_assignment.py` reverted
  to their pre-fix content (`git checkout HEAD~1 --`), everything else
  including the Rust extensions identical. 417.2 s wall.
- **fixed** — both fixes applied. 429.8 s wall.
- **mains-only** (§5) — not a route: the baseline board with *only* `w1_2`
  and `power_in.ntc-no`'s 97 segments taking the fixed board's width, every
  other byte held identical. Isolates the mains widening from everything else.

**The two routed boards are byte-identical apart from `(width ...)` values**
(verified: normalising every `(width X)` to `(width W)` makes the files
compare equal; 0 non-width differing lines). Segments 2916, vias 30, zones 94,
completion 63/103, pad connectivity 49/139, `unconnected_items` 349 — all
identical. **Every DRC delta below is therefore attributable to trace width
alone**, with no confounding from routing nondeterminism.

Counts use `scripts/measure_uncapped_drc.py` (#1111), not a kicad-cli
headline: `track_width` saturates at 199 and `clearance` at 499/500 on this
board, and both categories are at their cap in the baseline.

---

## 3. `track_width`: 841 → 117

**True (uncapped) counts.** kicad-cli's headline reads 199 for the baseline —
saturated, and wrong by 4.2×.

| | baseline | fixed |
|---|---|---|
| kicad-cli headline | 199 (**capped**) | 117 |
| **true count** (`measure_uncapped_drc.py dru-category track_width`) | **841** | **117** |

Per DRU rule band:

| band | baseline | fixed |
|---|---|---|
| `HighVoltage trace width` | 510 | **0** |
| `HighVoltageTank trace width` | 1 | **0** |
| `GateDriveSELV trace width` | 92 | **0** |
| `GateDriveHV trace width` | 83 | **0** |
| `Power trace width` | 155 | 117 |
| `ACMains` / `Ground` / `HighCurrent` / `Signal` / `HighSpeed` / `FinePitch` | 0 | 0 |
| **total** | **841** | **117** |

(The baseline's `HighVoltage` band contains one sub-band the tool flags as a
**lower bound** — 190 violations on the single net `discharge.k_dis1-nc`,
unsplittable further. 841 is therefore a floor, not a ceiling. The fixed
board's 117 is below every cap and is exact.)

Measured independently of kicad-cli, straight off the emitted segments
against each net's netclass `trace_width`: **826 undersized segments across
17 nets → 0 across 0 nets.**

| net | class | required | baseline emitted | fixed emitted |
|---|---|---|---|---|
| `w1_2` | HighVoltage | 3.0 | **0.2** (6.7%) | **3.0** |
| `power_in.ntc-no` | HighVoltage | 3.0 | **0.508** (16.9%) | **3.0** |
| `zcd` | HighVoltage | 3.0 | 0.2 | 3.0 |
| `discharge.k_dis1-nc` | HighVoltage | 3.0 | 0.2 | 3.0 |
| `discharge.k_dis2-nc` | HighVoltage | 3.0 | 0.2 | 3.0 |
| `tank-out` | HighVoltage | 3.0 | 0.2 | 3.0 |
| `DC_BUS_RTN`, `hb.power_loop.q_high-g` | HighVoltage | 3.0 | 0.2 | 3.0 |
| `tank.c_tank1-p2` | HighVoltageTank | 3.0 | 0.2 | 3.0 |
| `hb.gate_hs.driver-p1-1`, `-p2` | HighVoltageIsolated | 2.0 | 0.2 | 2.0 |
| `GATE_HS`, `GATE_LS` | GateDriveHV | 0.4 | 0.3048 | 0.4 |
| `PWM_HS`, `PWM_LS` | GateDriveSELV | 0.4 | 0.2 | 0.4 |
| `+15V` | Power | 1.0 | 0.508 | 1.0 |
| `V_BUS_SENSE` | Power | 1.0 | 0.2 | 1.0 |

The keyword classifier was also wrong in the *other* direction: `power_in.r_zcd_top1-p2`
is a `Default` (0.2mm) net that matched the `POWER` keyword and was emitted
at 0.508mm.

`DC_BUS_RTN`, `hb.power_loop.q_high-g`, `tank.c_tank1-p2` and one segment of
`discharge.k_dis1-nc` were the entire residual after the Stage 4.4 fix — 4
segments, all from `_stitch_isolated_pads`'s hardcoded literal (§1.1).

### 3.1 The remaining 117 are a different defect, and are not a hazard

All 117 are `Track width (rule 'Power trace width' min width 1.0000 mm;
actual 0.2000 mm)` on relay-coil nets (`discharge.k_dis1-coil2` and
siblings). The router is not ignoring its table — the two tables disagree
about *membership*:

| SSOT | authority over | says |
|---|---|---|
| `pcb/temper.kicad_pro` `netclass_assignments` | what KiCad resolves, hence what the DRU **enforces** | `discharge.k_dis1-coil2` → `Power` (1.0mm) |
| `TEMPER_NET_ASSIGNMENTS` (`design_rules.py` / `netclass_rules.yaml`) | what the **router** emits | → `Default` (0.2mm) |

**13 of 162 nets disagree** between the two:

| kicad_pro says | placer says | nets |
|---|---|---|
| `Power` | `Default` | `discharge.k_dis1-coil1/-coil2`, `discharge.k_dis2-coil1`, `power_in.bypass_relay-coil1/-coil2` |
| `FinePitch` | `Default` | `I_SENSE`, `rtd_force_n/p`, `rtd_sense_n/p` |
| `Differential` | `Default` | `usb_dn`, `usb_dp` |
| `GND` | `Power` | `gnd` |

`track_width` cannot reach 0 without reconciling that membership, which
touches `pcb/temper.kicad_pro` and is out of this PR's remit. Electrically it
is benign — these are ~30–75 mA relay coils, and 0.2mm carries 1.66 A. It is a
classification defect, not a thermal one. **Flagged, not fixed here.**

---

## 4. What widening cost: clearance, and the rest

`clearance` is saturated on both boards (headline 500 / 506), so these are
uncapped counts. Both totals carry unsplittable saturated sub-bands (2 and 3
respectively) and are therefore lower bounds.

| DRU clearance band | baseline | **mains-only** | fixed (all nets) |
|---|---|---|---|
| HV to LV | 1231 | 1230 | 1324 |
| Default routing | 420 | 412 | 508 |
| AC Mains to LV | 65 | 65 | 63 |
| HighVoltageIsolated same side | 34 | 34 | 23 |
| netclass-implicit fallback | 29 | 29 | 29 |
| AC Mains to HV | 10 | 12 | 12 |
| HighVoltageTank to LV | 10 | 10 | 12 |
| HV internal same footprint | 9 | 9 | 9 |
| HighVoltageIsolated to LV | 5 | 5 | 5 |
| GateDriveHV to HighVoltageIsolated | 1 | 1 | 0 |
| GateDriveSELV near HV | 0 | 0 | 1 |
| **TRUE total** | **1814** | **1807** | **1986** |

**Yes, pair clearance regresses when all 17 nets go to full width: +172
(+9.5%).** It is concentrated in `HV to LV` (+93) and `Default routing`
(+88), and it is driven by the *other* HV nets — chiefly `zcd` (142 segments
0.2 → 3.0mm) and the two `discharge.*-nc` nets (244 segments) — not by the
mains pair.

Other categories, all three boards (kicad-cli headline; `creepage` re-measured
uncapped and confirmed exact at 164 / 167 / 185):

| category | baseline | mains-only | fixed | note |
|---|---|---|---|---|
| `track_width` (true) | 841 | — | **117** | −86% |
| `clearance` (true) | 1814 | **1807** | 1986 | +9.5% overall, −0.4% for mains alone |
| `creepage` (true) | 164 | 167 | 185 | +12.8% |
| `shorting_items` | 35 | 48 | **≥202** | 202 exceeds the 199 cap → saturated |
| `solder_mask_bridge` | 25 | 38 | **≥199** | saturated |
| `hole_clearance` | 22 | 38 | 72 | |
| `copper_edge_clearance` | 18 | 18 | 21 | |
| `tracks_crossing` | 7 | 7 | 0 | |
| `unconnected_items` | 349 | 349 | 349 | unchanged |

The `shorting_items` blow-up is dominated by two nets: of 202, `zcd` appears
183 times and `discharge.k_dis1-coil2` 177. Widening `zcd` from 0.2 to 3.0mm
over 142 segments is what drives it. That is a **real** result — 3.0mm is what
`zcd`'s netclass demands — and it says the current placement cannot absorb
full-width HV copper everywhere. It is not an argument for narrowing the
trace; it is the measurement the owner needs.

---

## 5. Can the board carry 15A mains at compliant width? Yes — except at one part

The mains-only variant isolates the question the hazard actually poses.
Widening **only** `w1_2` and `power_in.ntc-no` to the compliant 3.0mm, with
every other byte held identical:

| category | baseline | mains-only | delta |
|---|---|---|---|
| **`clearance` (true, uncapped)** | 1814 | **1807** | **−7** |
| `creepage` (true) | 164 | 167 | +3 |
| `shorting_items` | 35 | 48 | +13 |
| `hole_clearance` | 22 | 38 | +16 |
| `solder_mask_bridge` | 25 | 38 | +13 |
| `copper_edge_clearance` | 18 | 18 | 0 |

**Clearance does not regress at all** — it improves by 7. The board outline
and the current requirement are *not* incompatible: there is room for 3.0mm
mains copper on this placement.

The entire cost is one component. Every one of the 12 new `shorting_items`
and all 16 new `hole_clearance` violations name **C6** — `power_in.y_cap_pe`,
the Y1 mains-to-PE safety capacitor — and nothing else:

```
PTH pad 1 [PWR_RTN] of C6  |  Track [power_in.ntc-no] on B.Cu, length 11.9000 mm
PTH pad 2 [gnd]     of C6  |  Track [w1_2]            on F.Cu, length 12.4000 mm
```

Both mains conductors are routed straight across the Y-capacitor's
through-hole pads. **This is pre-existing, not caused by the width fix**: the
baseline board already carries 3 `shorting_items` between `power_in.ntc-no`
and C6 pad 1 at 0.508mm. The fix widens an already-shorting trace from 0.508
to 3.0mm, taking C6's involvement from 3 to 15.

That is a router routing defect at a *safety-critical* crossing — a mains
conductor over the PE-side pad of the Y capacitor — and it is independent of
trace width. Two mains-carrying nets shorting to `gnd`/`PWR_RTN` through the
Y-cap's pads is the more serious of the two failure modes described in this
document, and it exists on `main` today at 8.3%-width copper. **Flagged;
fixing it is router collision-avoidance work (the same-run pad-blocking gap
`docs/evidence/2026-08-11-track-width-shorting-root-cause.md` §4 scoped out),
not a width question.**

---

## 6. Constraints that had to hold

Both hold, and hold *provably* rather than by re-measurement, because this
work changes no geometry other than segment width:

- **The 169 `(footprint ...)` blocks in both routed boards are byte-identical
  to `pcb/temper.kicad_pcb`'s.** `route_board.py` passes an empty placements
  dict; no placement solve ran in this session at all. Every
  placement-derived property — the PD2/8.0mm isolation-barrier geometry with
  all 8 isolators, and #1082's IGBT heatsink co-location
  (`check_heatsink_colocation`, a pure function of positions/rotations/sizes)
  — is therefore bit-for-bit what it is on `main`.
- **`scripts/measure_cross_domain_creepage.py` output is byte-identical**
  between the baseline and fixed boards (JSON diff empty; same worst gaps,
  same violating parts: R35 0.318mm, U5/C16 2.441mm, Q1 3.270mm, U15 5.249mm,
  L1 5.396mm). The isolation barrier is unmoved.
- `scripts/check_isolation_keepout.py` reports the *same single violation* on
  the committed board, the baseline route and the fixed route: no
  `MAINS_SELV_ISOLATION_BARRIER` keepout zone exists on this board at all.
  Pre-existing on `main`, unchanged here, not this PR's to close.

`board_origin` is not applicable: it guards `_apply_placements_to_pcb`, which
this session never calls.

---

## 7. Verification

- `packages/temper-placer/tests/router_v6/` run twice under the identical
  isolated venv: **25 failed / 6637 passed / 18 skipped / 23 xfailed** with
  the fix, **32 failed / 6620 passed / 18 skipped / 23 xfailed** with
  `router_v6/` reverted to `origin/main`.
  The failure *sets* differ by exactly the 7 new tests in this PR — **zero
  regressions**, and the 25 pre-existing failures (channel-skeleton, adapter
  marshal PBT, feedback classifier, production-board routing) are identical
  in both arms.
- The 7 new tests are non-vacuous by construction: each one fails against the
  pre-fix source and passes against the fixed source, measured above.
- New: `tests/router_v6/test_zone_stitch_netclass_width.py` (registered in
  `.github/workflows/python-tests.yml`'s router_v6 job).
- The Rust/oracle geometry differential
  (`test_zone_pour_geometry_rust_differential.py`) deliberately keeps the
  pinned `0.2` literal in its own mirror — its oracle is verbatim-at-pin and
  must stay so, and changing the literal there would break the *geometry*
  proof rather than test the width. Documented in place.

## 8. What was and was not measured

**Measured live this session:** both full routes; per-segment widths against
the netclass table, independently of kicad-cli; uncapped `track_width` and
`clearance` on the baseline, mains-only and fixed boards; uncapped `creepage`
on all three; kicad-cli headline categories on all three; the byte-identity of
the two routes modulo width; the 13-net kicad_pro-vs-placer assignment
divergence; cross-domain creepage on both routes; the IPC-2221B re-derivation
from `TRACE_WIDTH_CALCULATIONS.md`'s own declared parameters; routed lengths
and I²R for both mains nets.

**Not measured / out of scope:** an uncapped `shorting_items` total for the
fixed board (`measure_uncapped_drc.py`'s physical-partition path is documented
as not yet producing a validated total; `≥202` is what the cap supports); a
re-placed board that could absorb full-width `zcd`/`discharge.*-nc` copper
without the +172 clearance cost; whether 4.0mm mains copper is routable on
this outline (not attempted — the netclass value is unchanged pending the
owner's decision in §0); the C6 routing defect's fix.
