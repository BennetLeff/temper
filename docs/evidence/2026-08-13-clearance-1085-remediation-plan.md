<!-- provenance: analysis-only task, branch analysis/clearance-1085-remediation-plan,
worktree /home/bennet/Desktop/temper-clearance-1085-plan, base origin/fix/board-schematic-resync
@ a3fbaff37afd739b72f2b109847813b30ceb8e88 (PR #1134). pcb/temper.kicad_pcb NOT modified by this
task (git status --porcelain pcb/ empty throughout); sha256 b7d865b7946f55dcc0d907cccbbee12f730fd1878b30d417bd56004d1091c1d6,
matching power_pcb_dataset/drc_ceiling.json's own recorded provenance hash on this branch exactly.
pcb/temper.kicad_pro sha256 f2d90755af04fea40357be3ba2ef94368a01b1afc34c450b42fad0b9e15a51ac. kicad-cli
10.0.5. Worktree built with `make venv-isolate` (isolated .venv, immune to any other checkout's
uv sync); `scripts/check_stale_extensions.py` reported 10/10 fresh AND all 10 extensions were
independently verified to `import` cleanly (both checked before AND after every measurement below,
per this task's own environment-hazard instructions). All measurements use
`scripts/measure_uncapped_drc.py`'s provably-exhaustive DRU-rule partition-and-sum method
(docs/evidence/2026-08-12-uncapped-drc-measurement.md), or a purpose-built variant of it (this
task's own `clr1085_analyze.py`, described inline below) that captures full kicad-cli violation
JSON per band instead of only a count, so kind_a/kind_b/net/component data is real measured
output, not inferred. No `pcb/**` file, DRC ceiling, ratchet, clearance/creepage/safety value was
changed by this document. -->

# The 1085 true clearance violations: two-thirds trace to three nets whose existing copper is disconnected from its own pads, not to genuine HV/LV proximity, placement crowding, or a mis-scoped rule

**Verdict up front.**

1. **1085 reproduced exactly**, byte-identical band tree to the one already recorded in `power_pcb_dataset/drc_ceiling.json`'s `2026-08-13-clearance-saturation-correction` `_march` entry: `AC Mains to LV`=22, `AC Mains to HV`=1, `HighVoltageIsolated same side`=4, `HighVoltageIsolated to LV`=113, `HV internal same footprint`=1, `HV to LV`=655 (largest leaf 464), `HighVoltageTank to LV`=5, `Default routing`=258, `netclass-implicit fallback`=26.
2. **Board-wide, exhaustive kind_a/kind_b breakdown, all 1085 accounted for**: **805 track-track (74.2%), 197 pad-track (18.2%), 35 pad-pad (3.2%), 32 track-via (2.9%), 16 pad-via (1.5%), 0 zone-involved (0%)**. This is not a placement (pad-pad) problem and not a pour/zone-fill problem — it is almost entirely a **copper-routing** problem.
3. **The single decisive mechanism: three nets' existing copper does not connect to its own pads.** Using this repo's own tested tool, `temper_placer.router_v6.pad_connectivity_audit.audit_pcb_file` (built specifically to catch this exact "fake completion" shape, per its own module docstring), of 139 nets with pads: only **27 (19.4%) are fully pad-connected**, **48 (34.5%) are "fake completion"** (copper exists, tagged with the right net, but does not actually join the net's own pads), and 91 have no copper at all. **7 of the 48 fake-completion nets sit in a mains/HV-adjacent netclass**, and those 7 alone account for **at least 721 of the 1085 (66%)** true clearance violations, measured exhaustively per net, not estimated. The single largest leaf the task asked about — 464 of 655 in `HV to LV` — is **not** one net; it splits `SW_NODE`=5 + `discharge.k_dis1-nc`=459, and `discharge.k_dis1-nc`'s 104-segment, 2-via trace is independently confirmed (both by this tool and by direct pad-to-copper distance geometry) to be topologically disconnected from all three of its own real pads (K2, R14, R7) — a 104-segment "trace" that touches none of them, wandering across roughly half the board.
4. **The 464-net leaf is not a mis-scoped rule.** `discharge.k_dis1-nc` (and the other 6 dominant nets) are correctly classified `HighVoltage`/`HighVoltageIsolated`/`GateDriveHV` per `elec/domain_manifest.yaml`'s own domain model — they are real 400V-bus-referenced nodes. The violations are real DRC findings against real (if non-functional) copper, not an artifact of grading a net against the wrong rule. A **different, smaller, genuine rule-scoping gap was found and is reported separately** (finding 6 below): 3 of the 22 `AC Mains to LV` violations charge `(ACMains, HighVoltageIsolated)` pairs the full 6.0mm/8.0mm reinforced-barrier figure when the file's own `HighVoltageIsolated same side`/RULE 4a machinery, and its own 2026-08-11 precedent fixing the identical shape for `GateDriveHV`, say this pair should get the reduced 2.0mm same-side figure instead.
5. **A second, independently-confirmed mechanism accounts for a third of `Default routing`'s 258**: 87 of 258 (34%) read `actual 0.1500mm` or `actual 0.1972mm` to four decimal places — the exact signature `docs/evidence/2026-08-12-clearance-congestion-band.md` already diagnosed and fixed on a different board (a 0.15mm router reservation graded against RULE 10's 0.2mm bar). That fix has evidently not been carried into whatever produced this board's committed copper.
6. **Intrinsic, unfixable-by-placement-or-routing findings exist and are small**: the `netclass-implicit fallback` band (26; 23 pad-pad + 3 pad-via) is dominated by same-footprint, adjacent-pin pairs on ordinary logic ICs (`U8`, `U3`, `U27`, `U21`, `U13`, `U9`, `U20`) at real gaps of 0.015–0.36mm against the netclass base bar (0.5mm `Power` / 0.2mm `Default`) — below any real IC package's pin pitch tolerance, and structurally excluded from the file's own `"Same footprint pads"` reduction rule because that rule requires `A.NetClass == B.NetClass` (a deliberate cross-domain safety guard, not an oversight) while these are legitimate same-domain, cross-netclass pairs (`Power` vs `Default`, `Power` vs `GND`).
7. **No band in this measurement shows the classic "placement-blocked" signature** (a netclass-specific-rule-governed cluster of gross pad-pad violations that no rerouting could close). The `HighVoltage`/`HighVoltageIsolated`/`ACMains` bands are 96%+ track-involved, not pad-involved. This does not prove placement is never a factor elsewhere on the board — it means this measurement found no evidence for it as a driver of the 1085.

---

## 1. Reproduction

```
$ export PATH="/home/bennet/.local/bin:$PATH"; unset CONDA_PREFIX VIRTUAL_ENV
$ uv run --no-sync python3 scripts/measure_uncapped_drc.py dru-category clearance \
    --dru-generator scripts/generate_kicad_dru.py \
    --scratch-dir /tmp/clr1085_repro --json /tmp/clr1085_repro_bandtree.json
TRUE clearance: 1085
AC Mains to LV = 22
AC Mains to HV = 1
HighVoltageIsolated same side = 4
HighVoltageIsolated to LV = 113
HV internal same footprint = 1
HV to LV = 655  [split on real net names of class 'HighVoltage' (12 nets); n_before_split=511]
  ... [6/12] = 515 -> [3/6]=30, [3/6]=485 -> [1/3]=21 (PWR_RTN), [2/3]=464 (SW_NODE + discharge.k_dis1-nc)
  ... [6/12] = 140 (discharge.k_dis2-nc, hb.power_loop.q_high-g, power_in.ntc-no, tank-out, w1_1, w1_2)
HighVoltageTank to LV = 5
Default routing = 258
netclass-implicit fallback (no explicit DRU rule matches) = 26
```

Sum: 22+1+4+113+1+655+5+258+26 = **1085**, byte-identical to `power_pcb_dataset/drc_ceiling.json`'s `2026-08-13-clearance-saturation-correction` entry and to this task's own brief. `GateDriveHV near HV` / `GateDriveSELV near HV` / `GateDriveHV to ACMains` / `GateDriveHV to HighVoltageIsolated` / `Power internal same footprint` / `Ground clearance` / `Same footprint pads` / `Fine pitch IC pads` / `USB differential` all measured **0**.

## 2. Method for getting kind_a/kind_b, not just counts

`scripts/measure_uncapped_drc.py`'s partition machinery (rule-ranked isolation DRUs, `severity ignore` on everything else, recursive net-name bisection when a band saturates) only returns *counts*. This task built a thin variant, `clr1085_analyze.py` (kept in the session scratchpad, not committed — it imports `measure_uncapped_drc` and reuses every one of its exhaustiveness-proof primitives unchanged, only replacing `category_count()` calls with `run_kicad_drc()` calls whose full violation JSON is then classified), so every band below is backed by the **real kicad-cli violation JSON** (`items[].description`, parsed for kind/net/ref), not inference. Every band in the tree above was measured under its own report cap (the largest single isolation run was 464, comfortably under `EXTENDED_ERROR_LIMIT`=499) — this document did not need to trust any capped read-out.

Board-wide kind_a/kind_b, summed over **every** band's full captured JSON (all 1085 accounted for — nothing estimated or extrapolated):

| kind pair | count | % |
|---|---:|---:|
| track–track | 805 | 74.2% |
| pad–track | 197 | 18.2% |
| pad–pad | 35 | 3.2% |
| track–via | 32 | 2.9% |
| pad–via | 16 | 1.5% |
| zone-involved | 0 | 0.0% |
| **total** | **1085** | **100%** |

**Answer to task question 1**: this is overwhelmingly track/copper vs. track/copper (92.4% of all violations involve at least one track), not a placement (pad-pad, 3.2%) problem and not a zone-pour problem (0%). A pad-pad violation would point at a footprint/placement fix; a zone violation would point at a filler/pour-parameter fix. Neither is the story here. It is a **routing** problem — but, per finding 3 below, not in the usual "the router chose a bad path" sense.

## 3. The dominant mechanism: fake completion, confirmed by the repo's own tested tool

### 3.1 `discharge.k_dis1-nc`: 459 of `HV to LV`'s 655 (70%), 42% of the board's entire true clearance count

`HV to LV`'s recursive net-name split bottoms out at a 2-net leaf, `{SW_NODE, discharge.k_dis1-nc}` = 464. Disaggregated (single-net isolation DRUs against the real rule condition):

```
SW_NODE               ->   5
discharge.k_dis1-nc   -> 459
```

`discharge.k_dis1-nc` is `HighVoltage`-classed (per `pcb/temper.kicad_pro`'s `netclass_assignments`, matching `elec/domain_manifest.yaml`'s domain model — it is the DC-bus discharge-bleed net, a real 400V-referenced node) and connects, per the netlist, exactly three real pads: `K2` pin 4 (a relay contact, `discharge.k_dis1` sheet), `R14` pin 1 (`discharge.r_snub1`), `R7` pin 2 (`discharge.r_dis1b`). Its routed copper: **104 track segments + 2 vias, all on B.Cu**, forming (verified via union-find over shared segment endpoints) a **single connected polyline with exactly 2 endpoints**: `(49.188, 91.11)` and `(153.96, 117.06)`. Neither endpoint is within tens of millimetres of any of the net's 3 real pad positions (`K2` pin4 ≈ (143.7, 81–89), `R14` pin1 ≈ (115.7, 249.4), `R7` pin2 ≈ (178.1, 206.9) — computed via `pin_world_position`-equivalent absolute-position math, cross-checked directly against the raw `.kicad_pcb` text). kicad-cli's own `via_dangling` check independently confirms both of this net's vias: `"Via is not connected or connected on only one layer"`.

This is **not inference from geometry alone** — `packages/temper-placer/src/temper_placer/router_v6/pad_connectivity_audit.py` is a repo-native, tested module purpose-built for exactly this shape of defect (its own docstring: *"a net can have segments, and a rising completion counter, while those segments never touch the net's own pads at all"* — the exact `b39b382d15b` incident it cites). Running it against the committed board:

```python
from temper_placer.router_v6.pad_connectivity_audit import audit_pcb_file
res = audit_pcb_file(Path("pcb/temper.kicad_pcb"))
```

`discharge.k_dis1-nc.is_fake_completion == True` (`pads_connected`=1 of 4 pad instances, `has_any_copper`=True). 104 segments of drawn copper, tagged with the right net number, contribute **zero** real electrical connectivity and **459** clearance violations.

Kind breakdown for this net alone: **444 track-track, 13 track-via, 2 pad-track** — a wandering, heavily-fragmented trace crossing through unrelated board territory (its segment bounding box, `x:20.75–167.35, y:21.45–148.35`, spans roughly half the board's width and a large fraction of its height), racking up proximity violations against whatever real copper happens to lie in its path — dominated by `hb.gate_hs.driver-p1` (325 of 459; the LV/logic-side input pin of the U6 isolated gate-driver IC, correctly `Default`-classed since it is on the primary/non-isolated side of that part) plus `ina` (47), `safety-line-2` (32), `gnd` (20), `safety.coil_thermal.comp-inp` (16).

### 3.2 `power_in.ntc-no`: 125 of `HV to LV`'s remaining 140-net-pool, plus the board's only `AC Mains to HV` violation

Same pattern, same tool confirmation (`is_fake_completion == True`, `HighVoltage`-classed, 4 real pads). Isolated count: **125** (of the pool's 140). Kind: 86 track-track, 39 pad-track. Dominant pairs: `discharge.k_dis1-coil2` (48), `WDT_RESET_N` (31). Also the board's single `AC Mains to HV` violation (`ac_n <-> power_in.ntc-no`).

### 3.3 `hb.gate_hs.driver-p1-1`: 111 of `HighVoltageIsolated to LV`'s 113 (98%)

`hb.gate_hs.driver-p1-1` is the U6 isolated gate-driver's floating (secondary/HV-referenced) output pin — correctly `HighVoltageIsolated`-classed, distinct from (and easily confused with) `hb.gate_hs.driver-p1` (no `-1` suffix, correctly `Default`-classed — the *primary/logic-side* pin of the same package; verified these are two genuinely different, correctly-classified nets, not a naming collision). Isolated count: **111**. Also fake-completion per the audit tool (`pads_connected`=1 of 4). Kind: 87 track-track, 14 pad-track, 5 track-via, 4 pad-via, 1 pad-pad. Also drives 3 of the 4 `HighVoltageIsolated same side` violations and part of `HV internal same footprint`'s 1.

### 3.4 Aggregate: at least 721 of 1085 (66%), measured exhaustively per net across every band it appears in

| net | class | HV to LV | HVI to LV | HVI same side | HV internal same fp | AC Mains to HV | Default routing (partial, known floor) |
|---|---|---:|---:|---:|---:|---:|---:|
| `discharge.k_dis1-nc` | HighVoltage | 459 | — | — | — | — | ≥10 |
| `power_in.ntc-no` | HighVoltage | 125 | — | — | — | 1 | — |
| `hb.gate_hs.driver-p1-1` | HighVoltageIsolated | — | 111 | 3 | — | — | — |
| `hb.power_loop.q_high-g` | HighVoltage | 7 | — | (shared w/ above) | 1 | — | — |
| `hb.gate_hs.driver-p2` | HighVoltageIsolated | — | 2 | (shared w/ above) | — | — | — |
| `w1_2` | HighVoltage | 1 | — | — | — | — | — |
| `GATE_LS` | GateDriveHV | — | — | — | — | — | (not yet isolated) |
| **subtotal (conservative, exhaustively measured)** | | **592** | **113** | **4** | **1** | **1** | **≥10** |

**≥ 721 of 1085 (66.4%)** — a lower bound (the `Default routing` column is only partially swept for these 7 nets; the true total is very likely higher). All 7 of these nets are confirmed `is_fake_completion` or, in `GATE_LS`'s case, one of the 48 fake-completion nets by the same audit (not individually isolated here for time). None of the other 41 fake-completion nets sit in a mains/HV-adjacent class (34 are `Default`, 4 `FinePitch`, 3 `Power` — they still generate real violations, just not against the strict safety-domain rules this document's `HV to LV`/`HighVoltageIsolated to LV`/etc. bands measure; they are folded into `Default routing`'s 258 instead, which is consistent with `Default routing`'s own dominant pairs `WDT_RESET_N<->cs_n` (42), `RTD_SDI<->power_in.bypass_relay-coil2` (19) — both plausible fake-completion nets by name).

### 3.5 Board-wide pad connectivity, for context

```python
audit_pcb_file(Path("pcb/temper.kicad_pcb"))  # 139 nets with >=1 pad
# fully_connected: 27  (19.4%)
# is_fake_completion: 48  (34.5%)
# no copper at all: 91
```

This number was not previously reported for this exact (post-resync) committed board in any evidence document found in this repo — the "51/139"/"55/139" pad-connectivity figures cited elsewhere in the repo's history are all for `route_board.py`-produced candidate/heatsink boards, a different board lineage. **19.4% full pad connectivity on the committed, ship-target board** is itself a finding independent of the clearance count, and is the root of most of it.

## 4. `Default routing` (258): a known, previously-fixed-elsewhere router defect, still present here

Isolating RULE 10 (`A.Type=='Track' || B.Type=='Track'`, 0.2mm) directly and reading every violation's `actual` field:

```
0.1500mm x48
0.1972mm x37   <-- 87/258 (34%) match the exact signature
0.1226mm x33
0.1160mm x19
0.0210mm x17
...
```

`docs/evidence/2026-08-12-clearance-congestion-band.md` already diagnosed this exact pair of values on a different board build: the router's `default_clearance_mm=0.15` (later corrected to a per-class-derived rasteriser input) stamped a 0.40mm channel pitch against RULE 10's 0.2mm requirement, landing exactly at `0.400-0.25=0.1500mm` (parallel) or `0.447214-0.25=0.1972mm` (diagonal lattice step). That fix (`router_v6/clearance_floor.py`, `_pipeline_core.py`) is real and landed, but **this board's committed copper still shows the pre-fix signature on 87 of 258 `Default routing` violations** — either this board predates that fix's application, or the fix touches a code path this board's copper was not produced through. Kind breakdown for the whole band: 188 track-track, 56 pad-track, 14 track-via — consistent with a routing (not placement) fix. The remaining 171 (258−87) were not individually re-diagnosed against a specific mechanism in this session; kind data (`track-track`-dominant) is captured for all of them, but their `actual`-value distribution (33 at 0.1226mm, 19 at 0.1160mm, 17 at 0.0210mm, ...) does not match a single second signature as cleanly — likely a mix of genuine congestion and further fake-completion nets not in the mains/HV-adjacent set (§3.4).

## 5. `netclass-implicit fallback` (26): intrinsic, same-footprint, not fixable by placement or routing

Full JSON (all 26 captured): **23 pad-pad, 3 pad-via**. `ref_pairs`: `U8<->U8` (8), `U3<->U3` (3), `U27<->U27` (3), `U22<->U22` (2), `U21<->U21` (2), `U13<->U13` (2), plus 6 singletons. Every pair with two identical refs is, by construction, a same-footprint (adjacent pin) pair. Example real gaps against the governing netclass base value:

```
Clearance violation (netclass 'Power' clearance 0.5000 mm; actual 0.0150 mm)
    Pad 1 [vcc] of R40 on F.Cu
    Via [safety.fault_or-a2] on F.Cu - B.Cu
Clearance violation (netclass 'Power' clearance 0.5000 mm; actual 0.2350 mm)
    Pad 1 [RTD_DRDY] of U8 on F.Cu
    Pad 2 [vcc] of U8 on F.Cu
Clearance violation (netclass 'Power' clearance 0.5000 mm; actual 0.3500 mm)
    Pad 2 [gnd] of U9 on F.Cu
    Pad 3 [+3V3] of U9 on F.Cu
```

`scripts/generate_kicad_dru.py`'s own `"Same footprint pads"` rule (0.1mm) requires `A.NetClass == B.NetClass` — a **deliberate** cross-domain guard (its own comment: without it, an HV-side/SELV-side same-footprint pair on an isolator would silently receive a manufacturability allowance meant for ordinary tight pin pitch). But `vcc`/`RTD_DRDY`, `gnd`/`+3V3`, etc. are **not** cross-domain — they are ordinary LV logic-IC pins that simply carry *different* LV net classes (`Power` vs `Default`, `Power` vs `GND`) on the same package. The guard's blast radius catches these too, and no reduction rule applies, so they are graded at the full base netclass bar against real IC pin pitches of 0.5–1.27mm with pad copper filling most of that pitch. **No placement move and no reroute can satisfy a 0.5mm bar between two pads soldered 0.015–0.36mm apart on a purchased IC package.** This is the "intrinsic" case the task asked about, confirmed with real measured gaps, not asserted from a prior finding.

## 6. A genuine, small, well-precedented rule-scoping gap: `(ACMains, HighVoltageIsolated)`

`scripts/generate_kicad_dru.py` RULE 2 (`"AC Mains to LV"`, 6.0mm clearance / 8.0mm creepage) condition:

```
A.NetClass == 'ACMains' && B.NetClass != 'ACMains' && B.NetClass != 'HighVoltage'
  && B.NetClass != 'HighVoltageTank' && B.NetClass != 'GateDriveHV'
```

`HighVoltageIsolated` is **not** excluded. But the file's own `RULE 4a`/`"HighVoltageIsolated same side"` block (and its extensive comment) establishes `HighVoltageIsolated` — U6/U7's floating gate-drive bootstrap output — as being on the **same side** of the mains-isolation barrier as `ACMains`/`HighVoltage` ("RULE 3 already models for ACMains vs. HighVoltage... 4a relaxes the pair to the same 2.0mm figure"), and RULE 2 already excludes the analogous case `GateDriveHV` for the identical reason, fixed 2026-08-11 (the file's own comment on that exclusion: *"GATE_HS/GATE_LS ... SAME HV domain as ac_l/+170V_BUS/SW_NODE ... Before this fix, GateDriveHV was not excluded ... a false positive, not a real cross-barrier hazard"*). `HighVoltageIsolated` never received the mirror-image fix on RULE 2's side, even though `RULE 4`'s own B-side exclusion of `HighVoltageIsolated` (also 2026-08-11) explicitly fixed the *reverse* direction of the identical asymmetry.

Measured: `(ac_n, hb.gate_hs.driver-p1-1)` = **3** of the 22 `AC Mains to LV` violations (`ac_n<->hb.gate_hs.driver-p1-1`). This is a real DRU defect — a same-side pair charged the cross-barrier figure — argued from the file's own stated domain model and its own prior fix precedent for the structurally identical `GateDriveHV` case, not "relax a genuine violation for convenience." **Not fixed in this document** (analysis only; `pcb/**` and `scripts/generate_kicad_dru.py` untouched).

## 7. Answers to the task's five questions

1. **What is actually violating?** 74.2% track-track, 18.2% pad-track, 3.2% pad-pad, 2.9% track-via, 1.5% pad-via, 0% zone-involved (§2, exhaustive over all 1085). Not a filler/pour problem anywhere in this count.
2. **Fixable by rerouting alone, no placement change?** At least **721 of 1085 (66%)** — the fake-completion-driven violations (§3), because the fix is to strip disconnected copper and re-route 7 already-placed nets, not move any component. Plus at least 87 more (8%) from the known router-clearance-floor signature in `Default routing` (§4), whose landed fix (`router_v6/clearance_floor.py`) just needs to reach whatever produced this board's copper. **≥808 of 1085 (74%) is reroute-only**, conservatively.
3. **Require placement changes?** No band in this measurement shows the signature (a netclass-specific-rule-governed pad-pad cluster at gross gap ratios) that would indicate genuine "too close for any routing to fix." This is a negative result, reported as such, not a claim that placement is never a factor on this board generally.
4. **Intrinsic (no placement/routing can fix)?** The 26 `netclass-implicit fallback` violations (§5) — same-footprint, cross-LV-netclass IC pin pairs below any real package's pin pitch, structurally excluded from the one reduction rule that could otherwise cover them. ~2.4% of the total.
5. **Rule-scoping artifacts inflating a band?** Two found, of very different sizes: (a) **the 464-leaf itself is NOT a scoping artifact** — `discharge.k_dis1-nc`/`SW_NODE` are correctly `HighVoltage`-classed; the 459/1085 is real DRC output against real (non-functional) copper, not a misclassification (§3.1, §3.4). (b) A genuine but small scoping gap exists: `(ACMains, HighVoltageIsolated)` pairs (3 of 1085) are charged the full barrier-crossing figure when the file's own domain model and prior fix precedent say they should get the same-side figure (§6).

## 8. Ranking: (violations closed) / (effort + risk)

| # | Item | Violations closed (measured) | Effort | Risk | Notes |
|---|---|---:|---|---|---|
| 1 | Fix `(ACMains, HighVoltageIsolated)` DRU scoping gap — add `HighVoltageIsolated` to RULE 2's B-side exclusion list | 3 (+ likely a few more once `GATE_LS`/other `GateDriveHV`/`GateDriveSELV` pairs are checked the same way) | Trivial (few-line generator change, mirrors an already-landed 2026-08-11 fix for the identical shape) | **Zero** — corrects an over-conservative misclassification using the file's own established domain model, does not touch any genuine violation | Do this **first**: smallest, safest, fastest, and removes noise before the bigger items are tackled |
| 2 | Strip disconnected ("fake completion") copper on the 7 mains/HV-adjacent nets (`discharge.k_dis1-nc`, `power_in.ntc-no`, `hb.gate_hs.driver-p1-1`, `hb.gate_hs.driver-p2`, `hb.power_loop.q_high-g`, `w1_2`, `GATE_LS`) and re-route them from their existing, unmoved placement | ≥721 (66%) | Medium — `pad_connectivity_audit` already identifies exactly which nets and pads; ripping up non-functional copper is mechanical (same operation the resync PR already did for the ZCD circuit's 145 orphaned items); re-routing 7 already-placed nets is a bounded router task, not a placement re-solve | Low-medium — must re-verify true pad connectivity (not just a lower violation count) after re-routing, per the `pad_connectivity_audit` module's own stated purpose, so a "fixed" net doesn't silently stay fake-complete at a lower copper volume | **Highest-leverage item by far** — closes two-thirds of the entire board's true clearance debt without moving a single component |
| 3 | Extend `pad_connectivity_audit`-style fake-completion detection to the other 41 fake-completion nets (34 `Default`, 4 `FinePitch`, 3 `Power`) and clean/re-route those too | Unquantified here (folds mostly into `Default routing`'s 258, of which 87 already have a distinct, separately-fixable signature — §4) | Medium | Low-medium, same as #2 | Natural follow-on to #2, same mechanism, lower safety priority since these are LV/SELV-only |
| 4 | Land/propagate the router `clearance_floor.py` fix (0.15mm-vs-0.2mm signature) to whatever produced this board's copper | ≥87 (confirmed exact-signature subset of `Default routing`) | Low — the fix already exists and is landed elsewhere; this is a "make sure this board's route path uses it" task, not new engineering | Low | Can run in parallel with #2/#3 |
| 5 | Same-footprint, cross-LV-netclass pad reduction rule (fixes the 26 intrinsic `netclass-implicit fallback` violations) | 26 (2.4%) | Medium — needs a new, carefully-scoped condition (same `A.Reference == B.Reference`, but "both sides non-HV" instead of "both sides same netclass", to avoid reopening the cross-domain guard's own protection) | Low if scoped correctly; **must not** weaken the existing HV/SELV same-footprint guard | Smallest count of the actionable items; do after 1–4 |

**What this task would do first, concretely:** land #1 (trivial, zero-risk, immediate), then #2 (the dominant lever) — in that order, because #1 costs nothing and slightly cleans the `AC Mains to LV` band before the larger cleanup, and #2 is the item that actually moves the board from "1085 true violations" to something in the 300s, which is the prerequisite for the netclass-width increase (PR #1129) to even be re-evaluated (see §9).

## 9. Relationship to PR #1129 / the `HighVoltage` 3.0→5.0mm width increase

PR #1129 (merged; `docs/evidence/2026-08-13-netclass-current-scoping.md`) measured that raising `HighVoltage`/`HighVoltageTank` minimum trace width from 3.0mm to 5.0mm, graded against this board's **unchanged, uncleaned** copper, surfaces **1648 violations against a 1425 threshold** (`test_production_board_drc_regression`) and correctly refused to bump that ratchet. This document's finding sharpens why: a large share of this board's existing `HighVoltage`-classed copper (`discharge.k_dis1-nc`, `power_in.ntc-no`, `w1_2`, `hb.power_loop.q_high-g`) is not real, functioning routing at all — it is disconnected copper that happens to occupy space and generate DRC findings. Grading a **wider minimum width** against copper that is already known-disconnected garbage is measuring the wrong thing twice over. **This remediation (particularly item #2) should land, and this board should be re-routed clean, before PR #1129's width increase is re-attempted** — re-running PR #1129's own measurement after item #2 lands is the natural way to find out whether the 1425-threshold breach was itself partly an artifact of the same disconnected copper.

## 10. What could not be determined in this session

- **The exact mechanism for `Default routing`'s remaining 171 (258−87) violations** was not individually diagnosed beyond kind (track-track-dominant) and a rough `actual`-value histogram; some are very likely more instances of §3's fake-completion pattern on the 34 `Default`-classed fake-completion nets, but this was not exhaustively attributed net-by-net (time-bounded).
- **Whether any of the other 41 non-mains-adjacent fake-completion nets contribute to `netclass-implicit fallback` or `AC Mains to LV`/`HighVoltageIsolated to LV`** was not checked (those bands are dominated by the 7 nets in §3.4, but a residual contribution from the other 41 to the smaller bands was not ruled out).
- **Why this board's copper is 80%+ disconnected in the first place** — whether it is inherited from a pre-resync placement/route iteration whose copper was never fully regenerated, a partial/interrupted `route_board.py` run, or something else — was not traced to a specific commit or tool invocation. `docs/evidence/2026-08-13-netclass-current-scoping.md` (§4.2) independently documents `w1_1`/`tank.c_tank1-p2` as "unrouted in both runs" of a *different* net-batching experiment, which is consistent with (but does not by itself explain) this board's low connectivity.
- **Whether stripping the disconnected copper and re-routing would itself introduce new fake-completion or clearance findings** was not measured — item #2 in §8 needs its own before/after `pad_connectivity_audit` + `measure_uncapped_drc.py` pass to confirm, not assumed.

## 11. Reproduction

```bash
# Setup (per AGENTS.md; run once per worktree)
git worktree add -b <branch> <path> origin/fix/board-schematic-resync
cd <path> && unset CONDA_PREFIX VIRTUAL_ENV && make venv-isolate
uv run --no-sync python3 scripts/check_stale_extensions.py   # expect 10/10 fresh
export PATH="/home/bennet/.local/bin:$PATH"   # kicad-cli 10.0.5

# 1. Reproduce 1085 and the band tree
uv run --no-sync python3 scripts/measure_uncapped_drc.py dru-category clearance \
  --dru-generator scripts/generate_kicad_dru.py \
  --scratch-dir /tmp/clr1085_repro --json /tmp/clr1085_repro_bandtree.json

# 2. Disaggregate the 464-leaf by single net name (example)
uv run --no-sync python3 -c "
import sys; sys.path.insert(0,'scripts')
import measure_uncapped_drc as M
board_dir = M.Path('/tmp/clr1085_repro'); M.make_scratch_board(board_dir)
rule_cond = \"A.NetClass == 'HighVoltage' && B.NetClass != 'HighVoltage' && B.NetClass != 'HighVoltageTank' && B.NetClass != 'ACMains' && B.NetClass != 'GateDriveHV' && B.NetClass != 'HighVoltageIsolated'\"
for net in ['SW_NODE', 'discharge.k_dis1-nc']:
    restricted = rule_cond.replace(\"A.NetClass == 'HighVoltage'\", f\"A.NetName == '{net}'\")
    dru = M.isolation_dru(restricted, 2.0, 'clearance', f'probe-{net}')
    n, nondet = M._verified_count(board_dir, dru, 'clearance', M.default_safe_ceiling('clearance'))
    print(net, n, nondet)
"

# 3. Pad connectivity audit (the tool that names the mechanism)
uv run --no-sync python3 -c "
from pathlib import Path
from temper_placer.router_v6.pad_connectivity_audit import audit_pcb_file
res = audit_pcb_file(Path('pcb/temper.kicad_pcb'))
fake = [r for r in res.values() if r.is_fake_completion]
print(len(res), 'nets;', sum(r.fully_connected for r in res.values()), 'fully connected;', len(fake), 'fake completion')
"

# 4. Default-routing actual-value histogram (the router-floor signature check)
uv run --no-sync python3 -c "
import sys, re; sys.path.insert(0,'scripts')
import measure_uncapped_drc as M
board_dir = M.Path('/tmp/clr1085_repro')
dru = M.isolation_dru(\"A.Type == 'Track' || B.Type == 'Track'\", 0.2, 'clearance', 'default-routing-probe')
data = M.run_kicad_drc(board_dir, dru)
viol = [v for v in data['violations'] if v['type']=='clearance']
from collections import Counter
c = Counter(round(float(re.search(r'actual ([0-9.]+) ?mm', v['description']).group(1)),4) for v in viol)
print(c.most_common(10))
"
```

## Sources

- `docs/evidence/2026-08-12-uncapped-drc-measurement.md` — the partition-and-sum method, exhaustiveness proof, and `scripts/measure_uncapped_drc.py` itself.
- `docs/evidence/2026-08-13-netclass-current-scoping.md` (PR #1129, merged) — the netclass-width-increase measurement this remediation unblocks; its own `discharge.k_dis1-nc` "0 segments in baseline, 135 in corrected, fake-completion" note on a *different* board build independently corroborates the same net's routing pathology found here on the *committed* board.
- `docs/evidence/2026-08-12-clearance-congestion-band.md` — the router `default_clearance_mm=0.15` vs. RULE 10 0.2mm signature, reused in §4 to attribute 87/258 of `Default routing`.
- `docs/evidence/2026-08-12-clearance-regression-route-vs-placement.md` — prior kind_a/kind_b methodology (pad-pad/track-track/etc.) this document's own §2 mirrors, on a different board lineage.
- `packages/temper-placer/src/temper_placer/router_v6/pad_connectivity_audit.py` — the tested, repo-native fake-completion detector this document's central finding is built on.
- `scripts/generate_kicad_dru.py` — RULE 2/3/4/4a/4b text and comments (§6's scoping-gap argument is built entirely from this file's own stated domain model and its own 2026-08-11 fix precedent, not from an external standard).
- `power_pcb_dataset/drc_ceiling.json` `_march` — `2026-08-13-board-schematic-resync` and `2026-08-13-clearance-saturation-correction` entries, which this document's §1 reproduces independently.
- PR #1134 (`fix/board-schematic-resync`) — the baseline board this document analyzes.
- Not modified by this document: `pcb/temper.kicad_pcb`, `pcb/temper.kicad_pro`, `power_pcb_dataset/**`, `scripts/generate_kicad_dru.py`, any clearance/creepage/safety value or ratchet ceiling.
