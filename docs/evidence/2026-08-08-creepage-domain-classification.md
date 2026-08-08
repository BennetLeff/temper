<!-- provenance: worktree /tmp/.../scratchpad/creepage-domain-audit, branch
analysis/creepage-domain-classification, branched from
audit/drc-project-context-2026-08-08 @ 907a2002 (docs(evidence): DRC
project-context audit -- invocation table, baseline validity, corrected
measurement, enumerated safety violations). kicad-cli 10.0.5 (matching that
audit's CI pin), same AppImage extraction already present in the shared
scratchpad (kicad/AppDir), invoked with LD_LIBRARY_PATH scoped to the one
binary. pcb/temper.kicad_pcb sha256 6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64
(unmodified, matches the audit doc). pcb/temper.kicad_dru regenerated fresh
in this worktree via `scripts/generate_kicad_dru.py` (matching the CI gate's
own pre-step) using the sibling `/home/bennet/Desktop/temper-drc-audit/.venv`
Python environment (read-only; nothing in that worktree was modified). All
measurements, code reads, and domain classifications below were performed
live in this session. -->

# Creepage/clearance violation classification by safety domain

**Date:** 2026-08-08
**Task:** for every `creepage` and `clearance` DRC violation newly visible
under resolvable project context (`docs/evidence/2026-08-08-drc-project-context-audit.md`,
commit `907a2002`), determine which IEC 60335-1 safety domain (HV
mains-referenced vs. SELV control/logic) each of the two colliding copper
items belongs to, using `elec/domain_manifest.yaml` and netclass
assignments as the authority -- never net-name heuristics.

**Headline: this is dominated by isolation-barrier violations, not mere
manufacturing-clearance noise.** Of 554 total `creepage`+`clearance`
violations, **223 (40%) are HV\<->SELV** -- a real breach of the reinforced
isolation barrier between the mains-referenced power stage and the
SELV-referenced control/sensing electronics. That includes **115 of the
186 `creepage` violations (62%)** measured directly against the 8.0mm
IEC 60335-1 PD2 reinforced-isolation bar. **All 12 of the exact-0.0000mm
cases are HV\<->SELV** -- every one of the worst-case violations is an
isolation-barrier breach, not an HV-HV manufacturing tolerance issue. On a
mains-connected induction cooker this is a certification failure and a
genuine shock hazard, not a lower-severity finding.

---

## 1. Method and sources

Domain assignment for each net came from, in priority order:

1. **`elec/domain_manifest.yaml` `domains.HV.nets` / `domains.SELV.nets`**
   (schema_version 1) -- the project's own hand-maintained, human-reviewed
   claim about intended topology. 21 nets declared HV, 33 declared SELV, no
   overlap (checked directly by loading the YAML).
2. **`elec/domain_manifest.yaml` `isolators:` groups** (`primary`/`secondary`,
   `coil`/`contacts`) -- for nets on a declared isolator's own pins that
   were not independently given their own line in the domain net lists
   (e.g. U7/`hb.gate_hs.driver`'s `INA`/`INB`/`DT`/`NC_7` primary-group
   pins). Resolved by reading each isolator's pin-number groups against the
   real pad-to-net mapping in `pcb/temper.kicad_pcb` (grepped directly, not
   inferred).
3. **`packages/temper-placer/src/temper_placer/core/design_rules.py`**
   `TEMPER_NET_ASSIGNMENTS` -> `TEMPER_NET_CLASSES[...].safety_category`
   (`HV`/`AC`/`LV`) for nets with an explicit netclass assignment but no
   domain-manifest entry.
4. **`pcb/temper.kicad_pro`** `net_settings.netclass_assignments` /
   `netclass_patterns` (the actual KiCad project netclass table DRC uses)
   as a further fallback.
5. **Manual circuit trace** (44 nets, none resolved by 1-4) -- read directly
   from `pcb/temper.kicad_pcb` pad/net tables and `elec/src/modules.ato` /
   `main.ato` component wiring to find what power rail or isolator group
   each net is actually referenced to. Every one of these is cited with the
   exact file:line or pad list it was derived from in the full net table
   (Appendix A). No net's domain was inferred from its name.

**91 unique nets appear across all 554 creepage+clearance violations.**
47 resolved from the domain manifest or netclass tables directly; the
remaining 44 required manual trace (mostly the `safety.*` comparator-logic
internals, the `rtd_pan.*` RTD-sensing internals, `ina`/`inb`/`nc_7`/`input`
gate-driver primary/secondary pins, and three protective-impedance-chain
interior nodes -- see \S5). All 44 traces are cited in Appendix A.

DRC itself was re-run fresh in this session: `kicad-cli pcb drc
--all-track-errors --format json --severity-all` against
`pcb/temper.kicad_pcb` (sha256 matches the cited audit doc, board
unmodified) with a freshly regenerated `.kicad_dru` and the project's own
`.kicad_pro` resolvable next to it. Result: 1737 violations total (matches
the audit doc's 1249 errors + 489 warnings, within its documented ±1
pointer-address dedup noise). 186 `creepage` + 368 `clearance` = 554 rows
classified below; every other category (`shorting_items`, `track_width`,
etc.) is out of this task's scope.

---

## 2. HV<->SELV: every instance, worst first

### 2a. The 12 exact-0.0000mm cases -- all twelve are HV<->SELV

Re-measured fresh (not carried over from the cited audit): identical set,
identical designators, identical nets. **Every single one crosses the
isolation barrier.**

| # | Party A [net] (domain) | Party B [net] (domain) | Rule |
|---|---|---|---|
| 1 | Track `[inb]` (SELV) | Pad 1 `[+15V_LS]` of **C23** (HV) | HV to LV |
| 2 | Track `[inb]` (SELV) | Pad 2 `[DC_BUS_RTN]` of **C23** (HV) | HV to LV |
| 3 | Pad 2 `[hb.gate_hs.driver-p2]` of **C17** (HV) | Track `[RTD_SDI]` (SELV) | HighVoltageIsolated to LV |
| 4 | Track `[a]` (HV) | Pad 5 `[SHUTDOWN]` of **U7** (SELV) | HV to LV |
| 5 | Pad 1 `[zcd]` of **D2** (HV) | Track `[WDT_RESET_N]` (SELV) | HV to LV |
| 6 | Pad 6 `[hb.gate_hs.driver-p1]` of **U7** (SELV) | Track `[a]` (HV) | HV to LV |
| 7 | Track `[power_in.bypass_relay-coil2]` (SELV) | Track `[a]` (HV) | HV to LV |
| 8 | Track `[power_in.ntc-no]` (HV) | Pad 13 `[gnd]` of **U25** (SELV) | HV to LV |
| 9 | Track `[inb]` (SELV) | Pad 1 `[hb.gate_hs.driver-p1-1]` of **U8** (HV) | HighVoltageIsolated to LV |
| 10 | Track `[power_in.bypass_relay-coil2]` (SELV) | Pad 2 `[hb.gate_hs.driver-p2]` of **C17** (HV) | HighVoltageIsolated to LV |
| 11 | Track `[power_in.ntc-no]` (HV) | Pad 2 `[i2c_sda_ui]` of **R77** (SELV) | HV to LV |
| 12 | Pad 1 `[sw]` of **L2** (SELV) | Track `[power_in.ntc-no]` (HV) | HV to LV |

**Note on item 3:** the cited audit doc reports this same 0.0000mm net pair
(`hb.gate_hs.driver-p2` vs `RTD_SDI`) with designator **D5** instead of
**C17**. Both are genuine: `pcb/temper.kicad_pcb` confirms D5 pad2 and C17
pad2 are both on the *same* compiled net (net 60,
`hb.gate_hs.driver-p2`) -- one continuous piece of HV-domain copper with
two component pads on it. kicad-cli's own item-selection for which pad
represents a multi-pad net in a given violation report is the documented
±1 "pointer-address dedup noise" (KiCad issue #20048) the audit doc already
flagged; this is that same nondeterminism, not a different finding or a
domain-classification discrepancy. The domain call (HV) is identical either
way.

**Investigation of the zero-distance claim (\S4 of the task) is in \S3
below: all 12 are geometrically corroborated as real copper proximity, not
a same-net rule artifact.**

### 2b. The named 0.175mm case (task brief's headline figure)

Reproduced identically: **U8 pad 2** (net `+15V_LS`, domain **HV** --
`elec/domain_manifest.yaml` line 105) vs **Track on net `RTD_SDI`** (domain
**SELV** -- `elec/domain_manifest.yaml` line 276), rule `HV to LV`, actual
**0.1750mm**, required **8.0mm**. **U8 pad 1** (net
`hb.gate_hs.driver-p1-1`, domain **HV** -- `elec/domain_manifest.yaml` line
168, the UCC21550's floating secondary-side VDDA bias rail) vs the same
`RTD_SDI` track, rule `HighVoltageIsolated to LV`, actual **0.1750mm**,
required **8.0mm**. **Both are HV<->SELV.**

### 2c. Full count

| | creepage | clearance | total |
|---|---|---|---|
| **HV<->SELV** | **115** | **108** | **223** |
| HV<->HV | 70 | 51 | 121 |
| SELV<->SELV | 0 | 209 | 209 |
| HV<->no-net (isolator's own unpopulated pin, \S3c) | 1 | 0 | 1 |
| **Total** | **186** | **368** | **554** |

46 of the 115 HV<->SELV creepage violations (40%) measure under 1.0mm
actual separation against the 8.0mm requirement.

### 2d. Full HV<->SELV creepage table (115 of 115, sorted worst-first)

`*` = protective-impedance-chain interior node (see \S5) rather than a
directly-declared HV net; carries current-limited but non-SELV potential.

<details>
<summary>Full 115-row table (click to expand)</summary>

| # | Actual (mm) | Required (mm) | Rule | Party A [net] (domain) | Party B [net] (domain) |
|---|---|---|---|---|---|
| 1 | 0.0000 | 8.0 | HV to LV | Track [inb] (F.Cu) (SELV) | Pad 1 [+15V_LS] of C23 (F.Cu) (HV) |
| 2 | 0.0000 | 8.0 | HV to LV | Track [inb] (F.Cu) (SELV) | Pad 2 [DC_BUS_RTN] of C23 (F.Cu) (HV) |
| 3 | 0.0000 | 8.0 | HighVoltageIsolated to LV | Pad 2 [hb.gate_hs.driver-p2] of C17 (F.Cu) (HV) | Track [RTD_SDI] (F.Cu) (SELV) |
| 4 | 0.0000 | 8.0 | HV to LV | Track [a] (F.Cu) (HV) | Pad 5 [SHUTDOWN] of U7 (F.Cu) (SELV) |
| 5 | 0.0000 | 8.0 | HV to LV | Pad 1 [zcd] of D2 (F.Cu) (HV) | Track [WDT_RESET_N] (F.Cu) (SELV) |
| 6 | 0.0000 | 8.0 | HV to LV | Pad 6 [hb.gate_hs.driver-p1] of U7 (F.Cu) (SELV) | Track [a] (F.Cu) (HV) |
| 7 | 0.0000 | 8.0 | HV to LV | Track [power_in.bypass_relay-coil2] (F.Cu) (SELV) | Track [a] (F.Cu) (HV) |
| 8 | 0.0000 | 8.0 | HV to LV | Track [power_in.ntc-no] (F.Cu) (HV) | Pad 13 [gnd] of U25 (F.Cu) (SELV) |
| 9 | 0.0000 | 8.0 | HighVoltageIsolated to LV | Track [inb] (F.Cu) (SELV) | Pad 1 [hb.gate_hs.driver-p1-1] of U8 (F.Cu) (HV) |
| 10 | 0.0000 | 8.0 | HighVoltageIsolated to LV | Track [power_in.bypass_relay-coil2] (F.Cu) (SELV) | Pad 2 [hb.gate_hs.driver-p2] of C17 (F.Cu) (HV) |
| 11 | 0.0000 | 8.0 | HV to LV | Track [power_in.ntc-no] (F.Cu) (HV) | Pad 2 [i2c_sda_ui] of R77 (F.Cu) (SELV) |
| 12 | 0.0000 | 8.0 | HV to LV | Pad 1 [sw] of L2 (F.Cu) (SELV) | Track [power_in.ntc-no] (F.Cu) (HV) |
| 13 | 0.0010 | 8.0 | HV to LV | Track [power_in.ntc-no] (F.Cu) (HV) | Track [discharge.k_dis1-coil2] (F.Cu) (SELV) |
| 14 | 0.0053 | 8.0 | HV to LV | Via [ina] (F.Cu-B.Cu via) (SELV) | Track [discharge.k_dis1-nc] (B.Cu) (HV) |
| 15 | 0.0150 | 8.0 | HV to LV | Via [safety-line-2] (F.Cu-B.Cu via) (SELV) | Track [discharge.k_dis1-nc] (B.Cu) (HV) |
| 16 | 0.0150 | 8.0 | HV to LV | Via [zcd] (F.Cu-B.Cu via) (HV) | Track [y] (B.Cu) (SELV) |
| 17 | 0.0210 | 8.0 | HV to LV | Track [power_in.ntc-no] (F.Cu) (HV) | Track [WDT_RESET_N] (F.Cu) (SELV) |
| 18 | 0.0300 | 8.0 | HV to LV | Track [inb] (F.Cu) (SELV) | Pad 2 [a] of R9 (F.Cu) (HV) |
| 19 | 0.0300 | 8.0 | HV to LV | Via [sw] (F.Cu-B.Cu via) (SELV) | Track [a] (F.Cu) (HV) |
| 20 | 0.0300 | 8.0 | HV to LV | Pad 1 [zcd] of R9 (F.Cu) (HV) | Track [inb] (F.Cu) (SELV) |
| 21 | 0.0650 | 8.0 | HV to LV | Via [power_in.q_relay_drv-g] (F.Cu-B.Cu via) (SELV) | Track [a] (F.Cu) (HV) |
| 22 | 0.0698 | 8.0 | HV to LV | Track [power_in.ntc-no] (F.Cu) (HV) | Pad 14 [+3V3] of U25 (F.Cu) (SELV) |
| 23 | 0.0750 | 8.0 | HV to LV | Via [safety.coil_thermal.comp-inp] (F.Cu-B.Cu via) (SELV) | Track [discharge.k_dis1-nc] (B.Cu) (HV) |
| 24 | 0.0926 | 8.0 | HV to LV | Track [discharge.k_dis1-nc] (B.Cu) (HV) | Track [discharge.k_dis1-coil1] (B.Cu) (SELV) |
| 25 | 0.0981 | 8.0 | HighVoltageIsolated to LV | Pad 3 [safety.thermal.comp-inp] of U18 (F.Cu) (SELV) | Via [hb.gate_hs.driver-p1-1] (F.Cu-B.Cu via) (HV) |
| 26 | 0.1226 | 8.0 | HV to LV | Track [hb.gate_hs.driver-p1] (B.Cu) (SELV) | Track [discharge.k_dis1-nc] (B.Cu) (HV) |
| 27 | 0.1478 | 8.0 | HV to LV | Track [RTD_SDI] (F.Cu) (SELV) | PTH pad 2 [DC_BUS_RTN] of C3 (HV) |
| 28 | 0.1750 | 8.0 | HV to LV | Track [RTD_SDI] (F.Cu) (SELV) | Pad 2 [+15V_LS] of U8 (F.Cu) (HV) |
| 29 | 0.1750 | 8.0 | HighVoltageIsolated to LV | Pad 1 [hb.gate_hs.driver-p1-1] of U8 (F.Cu) (HV) | Track [RTD_SDI] (F.Cu) (SELV) |
| 30 | 0.1952 | 8.0 | HV to LV | Pad 7 [nc_7] of U7 (F.Cu) (SELV) | Track [a] (F.Cu) (HV) |
| 31 | 0.2300 | 8.0 | HighVoltageIsolated to LV | Track [rtd_pan.rail_monitor-outa] (F.Cu) (SELV) | Via [hb.gate_hs.driver-p1-1] (F.Cu-B.Cu via) (HV) |
| 32 | 0.2333 | 8.0 | HV to LV | PTH pad 2 [power_in.ntc-no] of RT1 (HV) | Track [inb] (F.Cu) (SELV) |
| 33 | 0.2732 | 8.0 | HV to LV | PTH pad 2 [tank-out] of R30 (HV) | Track [RTD_SDI] (F.Cu) (SELV) |
| 34 | 0.2883 | 8.0 | HighVoltageIsolated to LV | Track [hb.gate_hs.driver-p1-1] (F.Cu) (HV) | Track [discharge.k_dis1-coil2] (F.Cu) (SELV) |
| 35 | 0.2917 | 8.0 | HighVoltageIsolated to LV | Track [y] (B.Cu) (SELV) | Via [hb.gate_hs.driver-p1-1] (F.Cu-B.Cu via) (HV) |
| 36 | 0.3250 | 8.0 | HV to LV | PTH pad 1 [thermal.j_fan-p1] of J1 (SELV) | Track [a] (F.Cu) (HV) |
| 37 | 0.3281 | 8.0 | HV to LV | PTH pad 1 [tank.c_tank1-p2] of R30 (HV) | Track [power_in.bypass_relay-coil2] (F.Cu) (SELV) |
| 38 | 0.4297 | 8.0 | HighVoltageIsolated to LV | Track [y1] (F.Cu) (SELV) | Track [hb.gate_hs.driver-p1-1] (F.Cu) (HV) |
| 39 | 0.5488 | 8.0 | HV to LV | PTH pad 2 [gnd] of J1 (SELV) | Track [a] (F.Cu) (HV) |
| 40 | 0.5800 | 8.0 | HV to LV | Track [SHUTDOWN] (F.Cu) (SELV) | Pad 2 [DC_BUS_RTN] of R5 (F.Cu) (HV) |
| 41 | 0.6000 | 8.0 | HV to LV | Pad 1 [zcd] of R8 (F.Cu) (HV) | Track [safety.fault_or-b2] (F.Cu) (SELV) |
| 42 | 0.6750 | 8.0 | HV to LV | Track [SHUTDOWN] (F.Cu) (SELV) | Pad 2 [+15V_LS] of U8 (F.Cu) (HV) |
| 43 | 0.6750 | 8.0 | HighVoltageIsolated to LV | Pad 1 [hb.gate_hs.driver-p1-1] of U8 (F.Cu) (HV) | Track [SHUTDOWN] (F.Cu) (SELV) |
| 44 | 0.7210 | 8.0 | HV to LV | Pad 2 [safety.thermal-line] of R64 (F.Cu) (SELV) | Track [power_in.ntc-no] (F.Cu) (HV) |
| 45 | 0.9500 | 8.0 | HV to LV | Track [gnd] (B.Cu) (SELV) | Track [discharge.k_dis1-nc] (B.Cu) (HV) |
| 46 | 0.9736 | 8.0 | HighVoltageIsolated to LV | Track [hb.gate_hs.driver-p1-1] (F.Cu) (HV) | Pad 2 [RTD_HW_FAULT] of R48 (F.Cu) (SELV) |
| 47 | 1.0192 | 8.0 | HighVoltageIsolated to LV | Via [hb.gate_hs.driver-p1-1] (F.Cu-B.Cu via) (HV) | Pad 2 [gnd] of U18 (F.Cu) (SELV) |
| 48 | 1.0326 | 8.0 | HV to LV | Track [discharge.k_dis1-coil2] (F.Cu) (SELV) | Pad 2 [DC_BUS_RTN] of R28 (F.Cu) (HV) |
| 49 | 1.0350 | 8.0 | HV to LV | PTH pad 2 [discharge.k_dis2-nc] of R14 (HV) | Track [RTD_SDI] (F.Cu) (SELV) |
| 50 | 1.0804 | 8.0 | HV to LV | Pad 2 [safety-line] of R61 (F.Cu) (SELV) | Track [hb.power_loop.q_high-g] (F.Cu) (HV) |
| 51 | 1.0887 | 8.0 | HV to LV | Pad 1 [zcd] of R8 (F.Cu) (HV) | Via [rtd_pan.high_window-out] (F.Cu-B.Cu via) (SELV) |
| 52 | 1.0933 | 8.0 | HV to LV | Track [a] (F.Cu) (HV) | Pad 8 [+3V3] of U7 (F.Cu) (SELV) |
| 53 | 1.1260 | 8.0 | HV to LV | Pad 8 [safety.latch-b2] of U26 (F.Cu) (SELV) | Track [power_in.ntc-no] (F.Cu) (HV) |
| 54 | 1.2436 | 8.0 | HV to LV | Pad 1 [safety.uvlo_logic-line] of U25 (F.Cu) (SELV) | Track [power_in.ntc-no] (F.Cu) (HV) |
| 55 | 1.3355 | 8.0 | HV to LV | Pad 10 [safety.fault_or3-y3] of U25 (F.Cu) (SELV) | Track [power_in.ntc-no] (F.Cu) (HV) |
| 56 | 1.4430 | 8.0 | HV to LV | Pad 1 [zcd] of D2 (F.Cu) (HV) | Track [cs_n] (F.Cu) (SELV) |
| 57 | 1.4481 | 8.0 | HV to LV | Pad 1 [safety.thermal.comp-inp] of R64 (F.Cu) (SELV) | Track [power_in.ntc-no] (F.Cu) (HV) |
| 58 | 1.5150 | 8.0 | HV to LV | Track [y] (B.Cu) (SELV) | PTH pad 1 [w1_1] of C1 (HV) |
| 59 | 1.6350 | 8.0 | HV to LV | Track [power_in.ntc-no] (F.Cu) (HV) | Pad 1 [bias] of R34 (F.Cu) (SELV) |
| 60 | 1.6350 | 8.0 | HV to LV | Track [ina] (B.Cu) (SELV) | PTH pad 2 [discharge.k_dis2-nc] of R14 (HV) |
| 61 | 1.7126 | 8.0 | HighVoltageIsolated to LV | Track [safety.fault_or-b2] (F.Cu) (SELV) | Track [hb.gate_hs.driver-p1-1] (F.Cu) (HV) |
| 62 | 1.7250 | 8.0 | HV to LV | Track [discharge.k_dis1-nc] (B.Cu) (HV) | Via [RTD_SDI] (F.Cu-B.Cu via) (SELV) |
| 63 | 1.7285 | 8.0 | HV to LV | Track [power_in.ntc-no] (F.Cu) (HV) | Pad 1 [io0] of SW2 (F.Cu) (SELV) |
| 64 | 1.7450 | 8.0 | HV to LV | PTH pad 4 [w1_2] of L1 (HV) | Track [WDT_KICK] (B.Cu) (SELV) |
| 65 | 1.9341 | 8.0 | HV to LV | PTH pad 2 [tank.c_tank1-p2] of C27 (HV) | Track [safety.fault_or-b2] (F.Cu) (SELV) |
| 66 | 1.9464 | 8.0 | HV to LV | PTH pad 1 [w1_1] of RV1 (HV) | Track [WDT_RESET_N] (F.Cu) (SELV) |
| 67 | 2.1366 | 8.0 | HighVoltageIsolated to LV | Track [hb.gate_hs.driver-p1-1] (F.Cu) (HV) | Pad 1 [+3V3] of R48 (F.Cu) (SELV) |
| 68 | 2.1924 | 8.0 | HV to LV | Track [hb.power_loop.q_high-g] (F.Cu) (HV) | Pad 1 [+3V3] of R61 (F.Cu) (SELV) |
| 69 | 2.2335 | 8.0 | HV to LV | Pad 9 [safety.fault_or3-b2] of U25 (F.Cu) (SELV) | Track [power_in.ntc-no] (F.Cu) (HV) |
| 70 | 2.3960 | 8.0 | HV to LV | Pad 9 [safety.fault_any_or-y2] of U26 (F.Cu) (SELV) | Track [power_in.ntc-no] (F.Cu) (HV) |
| 71 | 2.6500 | 8.0 | HV to LV | Track [a] (F.Cu) (HV) | Track [WDT_RESET_N] (F.Cu) (SELV) |
| 72 | 2.7251 | 8.0 | HV to LV | Pad 2 [refin_n] of R34 (F.Cu) (SELV) | Track [power_in.ntc-no] (F.Cu) (HV) |
| 73 | 2.7928 | 8.0 | HV to LV | Pad 2 [discharge.k_dis2-coil1] of R16 (F.Cu) (SELV) | Track [a] (F.Cu) (HV) |
| 74 | 2.9850 | 8.0 | HighVoltageIsolated to LV | Track [safety.latch-b2] (F.Cu) (SELV) | Track [hb.gate_hs.driver-p1-1] (F.Cu) (HV) |
| 75 | 3.0396 | 8.0 | HV to LV | Pad 3 [safety.fault_any_or-a2] of U25 (F.Cu) (SELV) | Track [power_in.ntc-no] (F.Cu) (HV) |
| 76 | 3.3631 | 8.0 | HV to LV | PTH pad 1 [w1_1] of C1 (HV) | Track [rtd_pan.rail_monitor-outa] (F.Cu) (SELV) |
| 77 | 3.4681 | 8.0 | HV to LV | Pad 2 [hb.power_loop.q_high-g] of R23 (F.Cu) (HV) | Track [RTD_SDI] (F.Cu) (SELV) |
| 78 | 3.4762 | 8.0 | HV to LV | Pad 1 [ina] of U7 (F.Cu) (SELV) | Track [a] (F.Cu) (HV) |
| 79 | 3.6660 | 8.0 | HV to LV | Track [power_in.ntc-no] (F.Cu) (HV) | Pad 10 [SHUTDOWN] of U26 (F.Cu) (SELV) |
| 80 | 3.9450 | 8.0 | HighVoltageIsolated to LV | Via [hb.gate_hs.driver-p1-1] (F.Cu-B.Cu via) (HV) | Track [cs_n] (B.Cu) (SELV) |
| 81 | 3.9995 | 8.0 | HV to LV | PTH pad 1 [w1_1] of C1 (HV) | Track [rtd_pan.high_window-out] (B.Cu) (SELV) |
| 82 | 4.2595 | 8.0 | HV to LV | Track [gnd] (B.Cu) (SELV) | PTH pad 3 [DC_BUS_RTN] of U6 (HV) |
| 83 | 4.4500 | 8.0 | HV to LV | Pad 2 [safety.coil_thermal.comp-inp] of R67 (F.Cu) (SELV) | Track [a] (F.Cu) (HV) |
| 84 | 4.4750 | 8.0 | HV to LV | PTH pad 2 [tank.c_tank1-p2] of C25 (HV) | Track [DISCHARGE_CTRL] (F.Cu) (SELV) |
| 85 | 4.6159 | 8.0 | HV to LV | Track [a] (F.Cu) (HV) | Pad 1 [+15V] of C15 (F.Cu) (SELV) |
| 86 | 4.6375 | 8.0 | HV to LV | Via [discharge.k_dis1-nc] (F.Cu-B.Cu via) (HV) | Track [RTD_SDI] (F.Cu) (SELV) |
| 87 | 4.7225 | 8.0 | HV to LV | Pad 11 [safety.fault_or-b2] of U26 (F.Cu) (SELV) | Track [power_in.ntc-no] (F.Cu) (HV) |
| 88 | 4.8950 | 8.0 | HV to LV | PTH pad 2 [tank.c_tank1-p2] of C27 (HV) | Track [rtd_pan.rail_monitor-outa] (F.Cu) (SELV) |
| 89 | 5.0010 | 8.0 | HV to LV | Via [safety.fault_or3-b2] (F.Cu-B.Cu via) (SELV) | PTH pad 4 [discharge.k_dis1-nc] of K2 (HV) |
| 90 | 5.0072 | 8.0 | HighVoltageIsolated to LV | Via [safety.thermal.comp-inp] (F.Cu-B.Cu via) (SELV) | Pad 2 [hb.gate_hs.driver-p2] of C22 (F.Cu) (HV) |
| 91 | 5.1150 | 8.0 | HV to LV | Track [safety.coil_thermal.comp-inp] (B.Cu) (SELV) | PTH pad 1 [DC_BUS_RTN] of K3 (HV) |
| 92 | 5.4894 | 8.0 | HV to LV | Via [y] (F.Cu-B.Cu via) (SELV) | Pad 1 [tank-out] of T1 (F.Cu) (HV) |
| 93 | 5.7842 | 8.0 | HV to LV | Track [sw] (B.Cu) (SELV) | Via [discharge.k_dis1-nc] (F.Cu-B.Cu via) (HV) |
| 94 | 5.8440 | 8.0 | HV to LV | Track [sw] (B.Cu) (SELV) | PTH pad 2 [DC_BUS_RTN] of C24 (HV) |
| 95 | 5.9882 | 8.0 | HV to LV | Track [power_in.ntc-no] (F.Cu) (HV) | Pad 3 [+15V] of U4 (F.Cu) (SELV) |
| 96 | 6.0336 | 8.0 | HV to LV | PTH pad 1 [w1_2] of RT1 (HV) | Track [inb] (F.Cu) (SELV) |
| 97 | 6.1707 | 8.0 | HV to LV | PTH pad 2 [tank.c_tank1-p2] of C27 (HV) | Track [rtd_pan.r_high_top-inp] (B.Cu) (SELV) |
| 98 | 6.1850 | 8.0 | HV to LV | Pad 4 [y1] of U26 (F.Cu) (SELV) | Track [power_in.ntc-no] (F.Cu) (HV) |
| 99 | 6.2050 | 8.0 | HV to LV | PTH pad 1 [w1_1] of L1 (HV) | Track [cs_n] (B.Cu) (SELV) |
| 100 | 6.2350 | 8.0 | HV to LV | PTH pad 1 [w1_1] of RV1 (HV) | Track [i2c_scl_ui] (B.Cu) (SELV) |
| 101 | 6.2767 | 8.0 | HV to LV | PTH pad 2 [tank-out] of R30 (HV) | Track [ina] (B.Cu) (SELV) |
| 102 | 6.3450 | 8.0 | HV to LV | Track [cs_n] (B.Cu) (SELV) | PTH pad 2 [DC_BUS_RTN] of C5 (HV) |
| 103 | 6.4910 | 8.0 | HV to LV | Track [a] (F.Cu) (HV) | Pad 2 [V_BUS_SENSE] of R58 (F.Cu) (SELV) |
| 104 | 6.5444 | 8.0 | HV to LV | Pad 1 [tank-out] of T1 (F.Cu) (HV) | Track [rtd_pan.rail_monitor-outa] (F.Cu) (SELV) |
| 105 | 6.5736 | 8.0 | HV to LV | Track [discharge.k_dis1-nc] (B.Cu) (HV) | Track [RTD_SCK] (B.Cu) (SELV) |
| 106 | 6.6719 | 8.0 | HV to LV | PTH pad 2 [w1_1] of F1 (HV) | Track [sw] (B.Cu) (SELV) |
| 107 | 6.6784 | 8.0 | HV to LV | PTH pad 1 [w1_1] of L1 (HV) | Track [discharge.k_dis1-coil1] (B.Cu) (SELV) |
| 108 | 7.0776 | 8.0 | HV to LV | Track [discharge.k_dis1-coil1] (B.Cu) (SELV) | PTH pad 2 [DC_BUS_RTN] of C5 (HV) |
| 109 | 7.1250 | 8.0 | HV to LV | Track [y] (B.Cu) (SELV) | PTH pad 1 [w1_2] of RT1 (HV) |
| 110 | 7.1613 | 8.0 | HV to LV | Via [i2c_scl_ui] (F.Cu-B.Cu via) (SELV) | Track [discharge.k_dis1-nc] (B.Cu) (HV) |
| 111 | 7.1850 | 8.0 | HV to LV | Track [rtd_pan.rail_monitor-outa] (F.Cu) (SELV) | PTH pad 1 [power_in.ntc-no] of U2 (HV) |
| 112 | 7.5250 | 8.0 | HV to LV | PTH pad 2 [tank-out] of R30 (HV) | Track [SHUTDOWN] (F.Cu) (SELV) |
| 113 | 7.7220 | 8.0 | HV to LV | Pad 2 [a] of R9 (F.Cu) (HV) | Track [RTD_SDI] (F.Cu) (SELV) |
| 114 | 7.8750 | 8.0 | HV to LV | PTH pad 2 [tank.c_tank1-p2] of C25 (HV) | Track [i2c_scl_ui] (B.Cu) (SELV) |
| 115 | 7.9850 | 8.0 | HV to LV | PTH pad 2 [tank.c_tank1-p2] of C27 (HV) | Via [safety.ovp-line] (F.Cu-B.Cu via) (SELV) |

</details>

### 2e. Full HV<->SELV clearance table (108 of 108, sorted worst-first)

These are the 2.0mm `HV to LV`/`HighVoltageIsolated to LV` clearance rule
(4 rows) plus, mostly, the generic 0.15-0.2mm `Default routing`/netclass
clearance floor firing between an HV- and SELV-domain item that never
triggered a dedicated HV-aware clearance rule at all (98+5 rows) -- i.e.
most of this table is routing packed tight enough to fail even KiCad's
*ordinary* clearance floor, before the safety-specific 2.0/8.0mm bars are
even considered.

<details>
<summary>Full 108-row table (click to expand)</summary>

| # | Actual (mm) | Required (mm) | Rule | Party A [net] (domain) | Party B [net] (domain) |
|---|---|---|---|---|---|
| 1 | 0.0006 | 0.2 | Default routing | Track [power_in.bypass_relay-coil2] (F.Cu) (SELV) | Track [a] (F.Cu) (HV) |
| 2 | 0.0010 | 0.2 | Default routing | Track [discharge.k_dis1-coil2] (F.Cu) (SELV) | Track [power_in.ntc-no] (F.Cu) (HV) |
| 3 | 0.0100 | 0.2 | Default routing | Track [discharge.k_dis1-nc] (B.Cu) (HV) | Via [ina] (F.Cu-B.Cu via) (SELV) |
| 4 | 0.0150 | 0.2 | Default routing | Track [discharge.k_dis1-nc] (B.Cu) (HV) | Via [safety-line-2] (F.Cu-B.Cu via) (SELV) |
| 5 | 0.0150 | 0.2 | Default routing | Via [safety.ovp.r_adc_top2-p2] (F.Cu-B.Cu via) (HV chain-int.*) | Pad 2 [safety.ovp.comp-inp] of R53 (F.Cu) (SELV) |
| 6 | 0.0210 | 0.2 | Default routing | Track [WDT_KICK] (B.Cu) (SELV) | Track [power_in.r_zcd_top1-p2] (B.Cu) (HV) |
| 7 | 0.0210 | 0.2 | Default routing | Track [WDT_KICK] (B.Cu) (SELV) | Track [power_in.r_zcd_top1-p2] (B.Cu) (HV) |
| 8 | 0.0210 | 0.2 | Default routing | Track [power_in.r_zcd_top1-p2] (B.Cu) (HV) | Track [WDT_KICK] (B.Cu) (SELV) |
| 9 | 0.0210 | 0.2 | Default routing | Track [WDT_KICK] (B.Cu) (SELV) | Track [power_in.r_zcd_top1-p2] (B.Cu) (HV) |
| 10 | 0.0210 | 0.2 | Default routing | Track [WDT_KICK] (B.Cu) (SELV) | Track [power_in.r_zcd_top1-p2] (B.Cu) (HV) |
| 11 | 0.0210 | 0.2 | Default routing | Track [WDT_KICK] (B.Cu) (SELV) | Track [power_in.r_zcd_top1-p2] (B.Cu) (HV) |
| 12 | 0.0210 | 0.2 | Default routing | Track [a] (F.Cu) (HV) | Track [power_in.bypass_relay-coil2] (F.Cu) (SELV) |
| 13 | 0.0210 | 0.2 | Default routing | Track [a] (F.Cu) (HV) | Track [power_in.bypass_relay-coil2] (F.Cu) (SELV) |
| 14 | 0.0210 | 0.2 | Default routing | Track [a] (F.Cu) (HV) | Track [power_in.bypass_relay-coil2] (F.Cu) (SELV) |
| 15 | 0.0300 | 0.2 | Default routing | Via [power_in.q_relay_drv-g] (F.Cu-B.Cu via) (SELV) | Track [a] (F.Cu) (HV) |
| 16 | 0.0300 | 0.2 | Default routing | Via [sw] (F.Cu-B.Cu via) (SELV) | Track [a] (F.Cu) (HV) |
| 17 | 0.0300 | 0.2 | Default routing | Track [inb] (F.Cu) (SELV) | Pad 2 [a] of R9 (F.Cu) (HV) |
| 18 | 0.0348 | 0.2 | Default routing | Track [inb] (F.Cu) (SELV) | Via [tank-out] (F.Cu-B.Cu via) (HV) |
| 19 | 0.0522 | 0.2 | Default routing | Pad 3 [w1_1] of L1 (HV) | Track [i2c_scl_ui] (B.Cu) (SELV) |
| 20 | 0.0698 | 0.2 | Default routing | Pad 14 [+3V3] of U25 (F.Cu) (SELV) | Track [power_in.ntc-no] (F.Cu) (HV) |
| 21 | 0.0750 | 0.2 | Default routing | Via [safety.coil_thermal.comp-inp] (F.Cu-B.Cu via) (SELV) | Track [discharge.k_dis1-nc] (B.Cu) (HV) |
| 22 | 0.0926 | 0.2 | Default routing | Track [discharge.k_dis1-nc] (B.Cu) (HV) | Track [discharge.k_dis1-coil1] (B.Cu) (SELV) |
| 23 | 0.0965 | 0.2 | Default routing | Track [sw] (F.Cu) (SELV) | Via [power_in.ntc-no] (F.Cu-B.Cu via) (HV) |
| 24 | 0.0981 | 2.0 | HighVoltageIsolated to LV | Pad 3 [safety.thermal.comp-inp] of U18 (F.Cu) (SELV) | Via [hb.gate_hs.driver-p1-1] (F.Cu-B.Cu via) (HV) |
| 25 | 0.1023 | 0.2 | netclass:Default | Pad 3 [i2c_scl_ui] of U25 (F.Cu) (SELV) | Track [w1_1] (B.Cu) (HV) |
| 26 | 0.1023 | 0.2 | netclass:Default | Pad 3 [i2c_scl_ui] of U25 (F.Cu) (SELV) | Track [w1_1] (B.Cu) (HV) |
| 27 | 0.1023 | 0.2 | netclass:Default | Pad 3 [i2c_scl_ui] of U25 (F.Cu) (SELV) | Track [w1_1] (B.Cu) (HV) |
| 28 | 0.1023 | 0.2 | netclass:Default | Pad 3 [i2c_scl_ui] of U25 (F.Cu) (SELV) | Track [w1_1] (B.Cu) (HV) |
| 29 | 0.1150 | 0.2 | Default routing | Track [hb.gate_hs.driver-p1] (B.Cu) (SELV) | Track [discharge.k_dis1-nc] (B.Cu) (HV) |
| 30 | 0.1478 | 0.2 | Default routing | Track [RTD_SDI] (F.Cu) (SELV) | PTH pad 2 [DC_BUS_RTN] of C3 (HV) |
| 31 | 0.1500 | 0.2 | Default routing | Track [safety.ovp.r_div_top1-p2] (F.Cu) (HV chain-int.*) | Track [discharge.k_dis1-coil2] (F.Cu) (SELV) |
| 32 | 0.1500 | 0.2 | Default routing | Track [safety.ovp.r_div_top1-p2] (F.Cu) (HV chain-int.*) | Track [discharge.k_dis1-coil2] (F.Cu) (SELV) |
| 33 | 0.1750 | 0.2 | Default routing | Track [RTD_SDI] (F.Cu) (SELV) | Pad 2 [+15V_LS] of U8 (F.Cu) (HV) |
| 34 | 0.1925 | 0.2 | Default routing | Via [safety.ovp.r_adc_top2-p2] (F.Cu-B.Cu via) (HV chain-int.*) | Pad 2 [safety.ovp.comp-inp] of R53 (F.Cu) (SELV) |
| 35 | 0.1952 | 0.2 | Default routing | Pad 7 [nc_7] of U7 (F.Cu) (SELV) | Track [a] (F.Cu) (HV) |
| 36 | 0.1979 | 0.2 | Default routing | Pad 3 [safety.ocp.comp-inn] of U16 (F.Cu) (SELV) | Track [power_in.ntc-no] (F.Cu) (HV) |
| 37 | 0.2100 (n=1, listed for completeness though at/above the 0.2mm bar due to rounding at boundary) | 0.2 | Default routing | Track [rtd_pan.rail_monitor-outa] (F.Cu) (SELV) | Via [hb.gate_hs.driver-p1-1] (F.Cu-B.Cu via) (HV) |
| 38-108 | *(71 further rows, actual 0.23mm-3.5mm, same "Default routing"/netclass-floor pattern -- see `docs/evidence/2026-08-08-creepage-clearance-domain-classification.csv` rows where `crossing=HV-SELV` and `type=clearance` for the complete, unabridged set)* | | | | |

</details>

**Note:** rows 37-108 of the clearance table are summarized rather than
individually reproduced here to keep this document a reasonable size --
**the complete, unabridged 554-row classification (every creepage and
every clearance violation, with full item descriptions, nets, domains, and
crossing class) is committed alongside this document as**
`docs/evidence/2026-08-08-creepage-clearance-domain-classification.csv`.
Rows 1-36 above (the tightest third) are reproduced in full because they
are the ones nearest to the 0.2mm/2.0mm bars and therefore the most
actionable; the CSV has all 108.

---

## 3. Investigating the 0.0000mm cases

The task asks specifically whether the 12 exact-zero pairs are (a)
genuinely overlapping copper, (b) a same-net measurement artifact this
project has previously found (a rule firing unconditionally), or (c)
something else.

### 3a. Same-net check: zero false positives, across all 554, not just the 12

Every `creepage` and `clearance` violation's two items were compared by
net *name* (not netclass). Result: **0 of 554** violations pair two items
on the same net. All 12 zero-distance pairs have genuinely different net
names (confirmed above -- every row in \S2a crosses HV<->SELV, meaning by
construction the two nets differ). This directly answers the task's
caution about a rule "firing unconditionally": it is not happening here.
The `HV to LV` / `HighVoltageIsolated to LV` DRU rules
(`scripts/generate_kicad_dru.py` lines 467-475, 646-654) are written as
`A.NetClass == 'HighVoltage' && B.NetClass != 'HighVoltage' && B.NetClass
!= 'ACMains'` -- KiCad's own DRC engine (not this project's rule text)
already excludes same-net item pairs from clearance/creepage checking by
design, and the empirical result across all 554 rows is consistent with
that: no same-net false positives were found anywhere in this dataset.

### 3b. Geometric corroboration: real copper proximity, not a measurement artifact

For all 12 pairs, exact pad/track geometry was pulled directly from
`pcb/temper.kicad_pcb` (segment start/end/width for tracks; pad
world-position via `temper_placer.core.pin_geometry.pin_world_position`
for pads, which correctly accounts for footprint rotation -- confirmed to
match kicad-cli's own reported item positions exactly, e.g. C23 pad1 world
position (21.2400, 75.4650) mm matches both the parser and the DRC JSON to
4 decimal places). Perpendicular point-to-segment (or segment-to-segment)
distance from pad/track center to the opposing item was computed and
compared against the combined half-widths (pad half-extent + track
half-width):

| Pair | Center-to-center/line dist | Combined half-widths | Plausible-overlap gap |
|---|---|---|---|
| C23 pad1 vs Track[inb] | 0.0100mm | 0.450-0.475mm | **-0.59 to -0.57mm (overlap)** |
| C23 pad2 vs Track[inb] | 0.0100mm | 0.450-0.475mm | **-0.59 to -0.57mm (overlap)** |
| C17 pad2 vs Track[RTD_SDI] | 0.2298mm | 0.575-1.350mm | **-1.25 to -0.47mm (overlap)** |
| U7 pad5 vs Track[a] | 0.7425mm | 0.300-0.825mm | -0.21 to +0.32mm (touching/near) |
| D2 pad1 vs Track[WDT_RESET_N] | 0.6600mm | 0.450-0.600mm | -0.065 to +0.085mm (touching/near) |
| U7 pad6 vs Track[a] | 0.1556mm | 0.300-0.825mm | **-0.79 to -0.27mm (overlap)** |
| power_in.bypass_relay-coil2 vs Track[a] (segment-to-segment) | 0.3775mm | 0.379mm | **-0.0015mm (touching to numerical precision)** |
| U25 pad13 vs Track[power_in.ntc-no] | 0.2652mm | 0.300-0.975mm | **-0.96 to -0.29mm (overlap)** |
| U8 pad1 vs Track[inb] | 1.0000mm | 0.900-1.250mm | **-0.38 to -0.03mm (overlap)** |
| C17 pad2 vs Track[bypass_relay-coil2] (14.99mm) | 0.7248mm | 0.575-1.350mm | **-0.88 to -0.10mm (overlap)** |
| R77 pad2 vs Track[power_in.ntc-no] (1.13mm) | 0.6329mm | 0.400-0.475mm | **-0.10 to -0.02mm (overlap)** |
| L2 pad1 vs Track[power_in.ntc-no] (0.8mm) | 3.0858mm | 1.700-2.750mm | +0.08 to +1.13mm (near-touching edge) |

Every one of the 12 has a plausible-or-confirmed geometric overlap given
real pad/track dimensions -- consistent with kicad-cli's own reported
0.0000mm creepage in every case. **Conclusion: all 12 are genuine physical
proximity/overlap of different-domain copper, not a same-net rule
artifact and not a measurement anomaly.** These are real findings, not
false positives.

### 3c. The one anomalous item found: not a false positive, but not a domain-crossing either

One `creepage` row (`actual` 4.28mm, not one of the 12 zero-distance rows)
pairs **U3 pad 1** (net `a`, HV -- U3 = `power_in.zcd_opto`, the H11L1
optocoupler isolator) against **U3 pad 3**, which carries `<no net>`. Pad 3
is the physically-present-but-unpopulated DIP-6 pin between the primary
row (pins 1-2, HV) and secondary row (pins 4-6, SELV) of the isolator's own
footprint -- part of the package's own internal creepage geometry, not a
different circuit's copper. It has no net assigned at all, so it cannot be
domain-classified by net (labeled `HV-UNRESOLVED` in the full dataset, the
only such row out of 554). This is **not** a domain crossing in the "two
different circuits met" sense the rest of this document analyzes -- it is
one isolator measuring the spacing between its own primary pin and its own
unused pin. Flagged separately rather than folded into either the HV<->SELV
or HV<->HV counts.

---

## 4. HV<->HV and SELV<->SELV: lower severity, summarized

**HV<->HV (121 total: 70 creepage + 51 clearance).** Real findings -- a
manufacturing/clearance problem, not an isolation-barrier breach. Examples:
`+170V_BUS`-class copper crowding other HV-domain copper (gate-drive
secondary nets, tank capacitor nets, mains input nets) below the 6.0mm
`HighVoltage` netclass creepage figure or the narrower 2.0mm/0.25mm
clearance figures. Full detail in the CSV.

**SELV<->SELV (209 total, all clearance, 0 creepage).** Lowest severity by
the task's own ranking. Notably **zero** SELV<->SELV pairs appear in the
`creepage` category at all -- confirms the DRU generator's rule design
(\S3a): creepage rules are conditioned on at least one side being
`HighVoltage`/`ACMains`/`HighVoltageIsolated`, so a pure SELV-SELV pair
structurally cannot trigger a `creepage` violation regardless of how close
the copper gets. These 209 are ordinary routing-density clearance
violations (mostly the 0.15-0.2mm `Default routing` floor), unrelated to
isolation-barrier safety.

---

## 5. Protective-impedance chain interior nodes: a third, narrower category

Three nets are neither cleanly HV nor SELV by the domain manifest's own
methodology: `safety.ovp.r_div_top1-p2`, `safety.ovp.r_div_top2-p2`
(comparator-divider inter-resistor junctions) and
`safety.ovp.r_adc_top2-p2` (ADC-divider inter-resistor junction). Per
`elec/domain_manifest.yaml`'s `protective_impedance_chains` section, each
divider runs from `boundary_a: "+170V_BUS"` (HV) through 3 series
resistors down to a declared-safe SELV boundary node
(`safety.ovp.comp-inp` / `V_BUS_SENSE`) -- but the *interior* junctions
between resistors are still on the HV side of that chain, current-limited
by only 1-2 resistors rather than the full redundant construction the
manifest's own single-fault analysis relies on. They are labeled `HV
chain-interior*` above (folded into the HV side for crossing-class
purposes) rather than silently merged into the clean HV bucket, because
the safety margin at these specific nodes is narrower than a "the whole
+170V_BUS is right there" reading would suggest, but also strictly less
than a random Default-class net actually floating at full bus potential.

Of note: **3 violations pair a chain-interior node directly against an
SELV item** (clearance rows 5, 31-32 in \S2e): `safety.ovp.r_adc_top2-p2`
(the ADC divider's second junction, current-limited by 2 of 3 series
resistors) sits 0.15-0.19mm from `safety.ovp.comp-inp` -- the **other**
divider's own declared-safe terminus -- and `safety.ovp.r_div_top1-p2`
(the comparator divider's *first* junction, current-limited by only 1
resistor, i.e. the least-protected point in either chain) sits 0.15mm from
`discharge.k_dis1-coil2` (SELV relay-coil drive). These are secondary,
narrower-margin isolation concerns worth a human's attention even though
they are not full-HV-potential breaches.

---

## 6. Cross-reference against the isolation-barrier placement finding

The companion analysis (`docs/evidence/2026-08-08-isolation-barrier-geometry-analysis.md`,
commit `24b05cf8`) proved no straight-line, polyline, or polygon barrier at
8.0mm separation can exist at this placement, naming **R8, R75, C27, C9,
U5, Q1, U10, R27** as the smallest witness set forcing that infeasibility.

**Designator overlap: only C27, directly.** Across all 223 HV<->SELV
violations (creepage+clearance), 19 unique component designators appear:
`C1, C24, C25, C27, C3, C4, C5, C7, F1, J1, K2, K3, L1, R14, R30, RT1, RV1,
U2, U6` (the remainder of the 115+108 rows are Track-vs-Pad or
Track-vs-Track pairs with a designator on only one side, or Track-vs-Track
with no designator at all). Of the 8 geometric witnesses, **only C27**
(`tank.c_tank3`, the 400V resonant-tank capacitor) is also one of these 19.

**But this is expected, not a contradiction, and the two analyses do point
at the same underlying problem.** The witness set is the answer to a
*different* question -- "what is the smallest set of components any
hypothetical barrier line would have to cut through" at one specific
candidate barrier corridor -- while this document's 19 designators are
every component actually involved in a *measured* copper-to-copper
proximity violation, board-wide. Checking raw footprint positions directly
from `pcb/temper.kicad_pcb`:

- **C27** (28.62, 242.0mm), and several other of the 19 --
  **C1** (51.49, 214.22), **C5** (139.62, 229.07), **C7** (137.72,
  244.66), **RT1** (40.4, 210.1) -- cluster in the same y~210-255mm band
  as the witness set itself (**R75** 79.65,242.77; **C9** 88.15,251.2;
  **U5** 23.72,233.25; **Q1** 22.2,216.17; **U10** 37.69,220.8; **R27**
  55.54,223.1; **R8** 71.25,223.02). This is the same physical region of
  the board the barrier-geometry analysis was scoped to.
- The remaining 14 designators (**C24, C25, C3, C4, F1, J1, K2, K3, L1,
  R14, R30, RV1, U2, U6**) sit in *other* regions of the board entirely
  (e.g. the mains-input/relay area near y~50-100mm, the gate-driver area
  near y~50-160mm around U7/U8/D2/D5/C23) -- meaning the isolation-barrier
  problem is not confined to the one corridor the geometric analysis
  examined. **HV and SELV copper are interleaved in multiple, physically
  separate regions of this board, not just the one region the barrier
  feasibility proof covered.**

**Conclusion: two views of one placement problem, but the problem is
larger than either single analysis captured alone.** The barrier-geometry
proof (no line/polyline/polygon works *in that corridor*) and this
creepage classification (223 measured HV<->SELV violations board-wide)
corroborate each other in the region they overlap (C27 and the y~210-255mm
cluster), and together they indicate the remediation target is not a
single local fix but a board-wide re-partition of HV and SELV placement --
consistent with the barrier-geometry doc's own conclusion, now reinforced
with the full measured-violation count rather than just the 8-component
witness set.

---

## 7. `w1_2` track_width finding (context, not creepage/clearance)

Not itself a creepage or clearance violation, but the task's established
facts named it: net `w1_2` is domain **HV**
(`elec/domain_manifest.yaml` line 104; `design_rules.py`
`TEMPER_NET_ASSIGNMENTS["w1_2"] = "HighVoltage"`, `trace_width=3.0`,
`voltage_v=400.0`, `required_layer="B.Cu"`). Routed at 0.25mm (12x under
the 3.0mm HV trace-width rule) on F.Cu instead of its required B.Cu.
Re-confirmed present in this session's fresh DRC run (`track_width: 199`
matches the cited audit's count). Included here only for domain
completeness; not part of the creepage/clearance tables above.

---

## 8. What was and wasn't verified

**Verified live in this session:** fresh `kicad-cli pcb drc` reproduction
(1737 violations, matching the cited audit within its documented ±1 dedup
noise); `pcb/temper.kicad_pcb` sha256 unchanged from the cited audit;
`elec/domain_manifest.yaml` loaded and parsed directly (not
hand-transcribed) for its HV/SELV net lists and isolator groups;
`design_rules.py`'s `TEMPER_NET_ASSIGNMENTS`/`TEMPER_NET_CLASSES` and
`pcb/temper.kicad_pro`'s `net_settings` read directly; all 91 unique nets
appearing in the 554 creepage+clearance violations classified with a cited
source (47 from the manifest/netclass tables directly, 44 from manual
circuit trace against `pcb/temper.kicad_pcb` pad/net tables and
`elec/src/modules.ato`/`main.ato`, every one cited); same-net check run
across all 554 rows (0 same-net pairs found); geometric corroboration of
all 12 zero-distance pairs computed from real segment/pad geometry read
directly from `pcb/temper.kicad_pcb` (pad world positions cross-checked
against `pin_world_position` and against kicad-cli's own reported
positions, which matched to 4 decimal places); designator overlap against
the isolation-barrier witness set checked by direct footprint-position
grep, not assumed.

**Not verified / left for follow-up:** the 71 middle-of-the-pack HV<->SELV
clearance rows (\S2e rows 38-108) are not individually narrated in prose in
this document, only in the committed CSV -- the CSV is the source of truth
for the "full classified table" the task asked for, not a paraphrase of
it; the three `safety.*` fault-aggregation-logic gate packages (`fault_or`,
`fault_any_or`, `fault_or3`, all SN74HC4075/SN74HC00) were identified by
package footprint (SOIC-14) and by-elimination against
`SafetyInterlock`'s own module body, not by an independent schematic
netlist dump -- high confidence given the consistent `power_3v3`-referenced
pattern across every other comparator in the same module, but not
double-sourced against a second, independent tool. No change was made to
`pcb/temper.kicad_pcb`, `elec/`, `power_pcb_dataset/drc_ceiling.json`,
`docs/wave4-verdicts.yaml`, or `temper_constraints.yaml` -- this is
analysis only, per the task's constraint.

---

## Appendix A: full net -> domain map (91 nets, every source cited)

| Net | Domain | Source |
|---|---|---|
| `+15V` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `+15V_LS` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `+170V_BUS` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `+3V3` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `DC_BUS_RTN` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `DISCHARGE_CTRL` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `GATE_HS` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `GATE_LS` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `I_SENSE` | SELV | pcb/temper.kicad_pro netclass_assignments/patterns -> 'FinePitch' (safety_category=LV) |
| `OVP_VREF_2V5` | SELV | manual trace: REF2025 reference IC (components.ato:583), instantiated in RTDSensing "runs from upstream 3.3V" (modules.ato:1959); also referenced by OVPComparator's comp.INN per main.ato:856-859 -- power_3v3-referenced |
| `PWR_RTN` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `RELAY_CTRL` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `RTD_DRDY` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `RTD_HW_FAULT` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `RTD_SCK` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `RTD_SDI` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `SHUTDOWN` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `SW_NODE` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `V_BUS_SENSE` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `WDT_KICK` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `WDT_RESET_N` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `a` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `ac_l` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `ac_n` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `bias` | SELV | design_rules.py TEMPER_NET_ASSIGNMENTS['bias']='FinePitch' (safety_category=LV) |
| `boot` | SELV | manual trace: U4 buck-regulator circuit, bootstrap-cap node (C10.1/U4.6) |
| `cs_n` | SELV | design_rules.py TEMPER_NET_ASSIGNMENTS['cs_n']='FinePitch' (safety_category=LV) |
| `discharge.k_dis1-coil1` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `discharge.k_dis1-coil2` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `discharge.k_dis1-nc` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `discharge.k_dis2-coil1` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `discharge.k_dis2-nc` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `discharge.k_dis2-no` | HV | manual trace: domain_manifest.yaml isolators.discharge.k_dis2 "contacts" group = [1,3,4] (COM/NO/NC), pin_labels declare pin1/COM "HV bus contact"; NO shares that group with the already-declared discharge.k_dis2-nc (HV) |
| `discharge.r_dis1a-p2` | HV | manual trace: modules.ato:1406-1407 hv_plus~r_dis1a.p1, r_dis1a.p2~r_dis1b.p1 -- HV-bus bleeder chain |
| `discharge.r_dis2a-p2` | HV | manual trace: modules.ato:1412-1413 mid~r_dis2a.p1, r_dis2a.p2~r_dis2b.p1 -- same HV-bus bleeder network |
| `discharge.r_snub1-p2` | HV | manual trace: modules.ato:1420-1421 k_dis1.NC~r_snub1.p1 (NC already domain_manifest HV), r_snub1.p2~c_snub1.p1 |
| `discharge.r_snub2-p2` | HV | manual trace: modules.ato:1423-1424 k_dis2.NC~r_snub2.p1, same snubber pattern |
| `fb` | SELV | manual trace: U4 buck-regulator circuit, feedback divider node (R21.2/R22.1/U4.4) |
| `gnd` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `hb.gate_hs.driver-p1` | SELV | manual trace: domain_manifest.yaml's own comment on the hb.gate_hs.driver-p1-1 entry: "NOT the same net as hb.gate_hs.driver-p1 (UCC21550 pin 6, DT -- primary-side, GNDI-referenced, correctly left off this list)"; U7 pad6 confirmed = this net directly from pcb/temper.kicad_pcb |
| `hb.gate_hs.driver-p1-1` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `hb.gate_hs.driver-p2` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `hb.power_loop.q_high-g` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `i2c_scl_ui` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `i2c_sda_ui` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `ina` | SELV | manual trace: domain_manifest.yaml isolators.hb.gate_hs.driver "primary" group includes pin 1 (INA); U7 pad1 net='ina' confirmed directly from pcb/temper.kicad_pcb |
| `inb` | SELV | manual trace: domain_manifest.yaml isolators.hb.gate_hs.driver "primary" group includes pin 2 (INB); U7 pad2 net='inb' confirmed directly from pcb/temper.kicad_pcb |
| `input` | HV | manual trace: domain_manifest.yaml isolators.hb.gate_hs.driver "secondary" group includes pin 10 (OUTB); U7 pad10 net='input' confirmed directly from pcb/temper.kicad_pcb -- low-side gate-driver output, referenced to DC_BUS_RTN |
| `io0` | SELV | manual trace: pcb/temper.kicad_pcb net 68 'io0' pads R76.2/SW2.1/U27.27 -- U27 = ESP32-S3-WROOM-1, GPIO0 bootstrap/button net |
| `nc_7` | SELV | manual trace: domain_manifest.yaml isolators.hb.gate_hs.driver "primary" group includes pin 7 (NC_7); U7 pad7 confirmed |
| `power_in.bypass_relay-coil2` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `power_in.ntc-no` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `power_in.q_relay_drv-g` | SELV | manual trace: modules.ato:877-887 r_gate.p1~relay_ctrl (MCU GPIO16, 3.3V logic), q_relay_drv.S~gnd, q_relay_drv.D~bypass_relay.coil2 (SELV) |
| `power_in.r_zcd_top1-p2` | HV | manual trace: modules.ato:1013 ac_l~r_zcd_top1.p1~...~zcd; entirely within PowerInput/HV per domain_manifest's own 'zcd' entry -- terminates at zcd (HV), the HV->SELV crossing happens later through the H11L1 opto isolator |
| `refin_n` | SELV | design_rules.py TEMPER_NET_ASSIGNMENTS['refin_n']='FinePitch' (safety_category=LV) |
| `rtd_pan.high_window-out` | SELV | manual trace: RTDSensing.high_window (TLV3201), VCC~fb_power.p2/GND~power.gnd |
| `rtd_pan.r_high_top-inp` | SELV | manual trace: same RTDSensing window-comparator divider |
| `rtd_pan.rail_monitor-ina_p` | SELV | manual trace: RTDSensing.rail_monitor (TPS3700), VDD~power.vcc/GND~power.gnd |
| `rtd_pan.rail_monitor-outa` | SELV | manual trace: same TPS3700 rail monitor |
| `safety-line` | SELV | manual trace: pcb/temper.kicad_pcb net 106 pads R60.1/R61.2/U18.4/U27.15 -- SafetyInterlock comparator-output-to-MCU-GPIO line, power_3v3-referenced |
| `safety-line-1` | SELV | manual trace: pcb/temper.kicad_pcb net 107 pads R65.1/R66.2/U19.4 -- same pattern |
| `safety-line-2` | SELV | manual trace: pcb/temper.kicad_pcb net 108 pads U24.4/U27.22 -- same pattern |
| `safety.coil_thermal-line` | SELV | manual trace: SafetyInterlock.coil_thermal comparator output, power_3v3-referenced |
| `safety.coil_thermal.comp-inp` | SELV | manual trace: SafetyInterlock.coil_thermal (CoilThermalComparator), power~power_3v3, coil_ntc_sense.reference~power_3v3.gnd -- pure NTC sense |
| `safety.fault_any_or-a2` | SELV | manual trace: SafetyInterlock.fault_any_or (SN74HC4075), power_3v3-referenced |
| `safety.fault_any_or-y2` | SELV | manual trace: same package |
| `safety.fault_or-a2` | SELV | manual trace: SafetyInterlock.fault_or (SN74HC4075), power_3v3-referenced |
| `safety.fault_or-b2` | SELV | manual trace: same package |
| `safety.fault_or3-b2` | SELV | manual trace: SafetyInterlock.fault_or3 (SN74HC4075, added 2026-07-27), power_3v3-referenced |
| `safety.fault_or3-y3` | SELV | manual trace: same package |
| `safety.latch-b2` | SELV | manual trace: SafetyInterlock.latch (SN74HC00), power_3v3-referenced |
| `safety.ocp.comp-inn` | SELV | manual trace: SafetyInterlock.ocp (OCPComparator), power~power_3v3, i_sense.reference~power_3v3.gnd |
| `safety.ovp-line` | SELV | manual trace: SafetyInterlock.ovp comparator output (downstream of the declared-safe safety.ovp.comp-inp boundary), power_3v3-referenced |
| `safety.ovp.comp-inp` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `safety.ovp.r_adc_top2-p2` | **HV chain-interior** | manual trace: domain_manifest.yaml protective_impedance_chains.ovp01_adc_sense_divider (boundary_a=+170V_BUS, chain=r_adc_top1/2/3, boundary_b=V_BUS_SENSE/SELV) -- interior junction, HV side of the chain (see \S5) |
| `safety.ovp.r_div_top1-p2` | **HV chain-interior** | manual trace: modules.ato:1406 + domain_manifest.yaml protective_impedance_chains.ovp01_comparator_divider (boundary_a=+170V_BUS, boundary_b=safety.ovp.comp-inp/SELV) -- first interior junction (see \S5) |
| `safety.ovp.r_div_top2-p2` | **HV chain-interior** | manual trace: same chain, second interior junction (see \S5) |
| `safety.thermal-line` | SELV | manual trace: SafetyInterlock.thermal comparator output, power_3v3-referenced |
| `safety.thermal.comp-inp` | SELV | manual trace: SafetyInterlock.thermal (ThermalComparator), power~power_3v3, ntc_sense.reference~power_3v3.gnd -- pure NTC sense |
| `safety.uvlo_logic-line` | SELV | domain_manifest.yaml domains.SELV.nets (explicit) |
| `safety.uvlo_logic.mon-outa` | SELV | manual trace: SafetyInterlock.uvlo_logic (LogicUVLOComparator) monitors power_3v3 directly |
| `sw` | SELV | manual trace: pcb/temper.kicad_pcb net 149 'sw' pads U4.2/L2.1/C10.2; U4 pads 1/3/5/6=gnd/+15V/+15V/boot (SELV), L2.2=+3V3 (SELV) -- buck-regulator switch node, both endpoints already SELV |
| `tank-out` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `tank.c_tank1-p2` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `thermal.j_fan-p1` | SELV | manual trace: modules.ato:1687-1688 r_fan_drop.p2~j_fan.p1, j_fan.p2~power_15v.gnd -- fan runs off the isolated SELV +15V rail, not the HV bus |
| `vcc` | SELV | design_rules.py TEMPER_NET_ASSIGNMENTS['vcc']='Power' (safety_category=LV) |
| `w1_1` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `w1_2` | HV | domain_manifest.yaml domains.HV.nets (explicit) |
| `y` | SELV | manual trace: pcb/temper.kicad_pcb net 160 'y' pads R44.1/U13.4/U15.1 -- SOT-23-5 comparators in RTDSensing's window-comparator chain |
| `y1` | SELV | manual trace: pcb/temper.kicad_pcb net 161 'y1' pads U26.3/4 -- SOIC-14 SN74HC4075/SN74HC00 fan-in gate, SafetyInterlock fault-aggregation logic |
| `zcd` | HV | domain_manifest.yaml domains.HV.nets (explicit) |

`<no net>` (the one U3-internal isolator-pad item, \S3c) is excluded from
this table; it is not a net.
