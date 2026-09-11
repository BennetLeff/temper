# Control-assembly integration report (P3 U2-U4)

Plan: `docs/plans/2026-09-10-1322-feat-buck-mcu-composition-plan.md`
Units: U2 (compose source-derived geometry), U3 (route and verify), U4 (package).

**Verdict: `apparatus-only-assisted`. The local section has complete required
supply/return connectivity, zero schematic-parity findings and no introduced
DRC finding, and the full-board cross-view comparison passes, but the section
is NOT overlay-clean and is not a qualified cooker.** The live construction model
was transport-blocked (Zen HTTP 429), so no autonomous construction occurred.
The autonomous attempt is preserved separately at
`verification/failed-attempts/live-model-transport.json`; this report
describes the labelled scripted pass only.

Route through the shared bounded session and create the scratch overlay are
now done (previously named blockers): every PCB mutation went through
`run_block.BlockSession`, and the production board was copied (never written)
to build the overlay that exposes the integration debt in §4b.

## 1. Source-to-board lineage

The combined wrapper
`harness-lab/blocks/control-assembly/control-assembly.ato:ControlAssemblyCandidate`
was built with pinned Atopile 0.2.69 in a fresh workspace (offline) and
bridged by canonical instance path. The build renumbers refdes relative to
both inputs, so identity is the path, never the refdes.

| Block | Combined ref | Canonical source path | P1 package ref | Footprint |
|-------|--------------|-----------------------|----------------|-----------|
| buck | U1 | `buck.buck` | — | Package_TO_SOT_SMD:SOT-23-6 |
| buck | L1 | `buck.l_out` | — | Inductor_SMD:L_Bourns_SRP1265A |
| buck | C1 | `buck.c_in` | — | Capacitor_SMD:C_1210_3225Metric |
| buck | C2 | `buck.c_boot` | — | Capacitor_SMD:C_0603_1608Metric |
| buck | C3 | `buck.c_out1` | — | Capacitor_SMD:C_1210_3225Metric |
| buck | C4 | `buck.c_out2` | — | Capacitor_SMD:C_1210_3225Metric |
| buck | C5 | `buck.c_out_hf` | — | Capacitor_SMD:C_0603_1608Metric |
| buck | R1 | `buck.r_fb_top` | — | Resistor_SMD:R_0603_1608Metric |
| buck | R2 | `buck.r_fb_bot` | — | Resistor_SMD:R_0603_1608Metric |
| mcu | U2 | `mcu.mcu` | U1 | lib:ESP32-S3-WROOM-1 |
| mcu | C6 | `mcu.c_vcc1` | C1 | Capacitor_SMD:C_0603_1608Metric |
| mcu | C7 | `mcu.c_vcc2` | C2 | Capacitor_SMD:C_0805_2012Metric |
| mcu | C8 | `mcu.c_en` | C3 | Capacitor_SMD:C_0603_1608Metric |
| mcu | R3 | `mcu.r_en` | R1 | Resistor_SMD:R_0603_1608Metric |
| mcu | R4 | `mcu.r_boot` | R2 | Resistor_SMD:R_0603_1608Metric |
| mcu | R5 | `mcu.r_sda_pullup` | R3 | Resistor_SMD:R_0603_1608Metric |
| mcu | R6 | `mcu.r_scl_pullup` | R4 | Resistor_SMD:R_0603_1608Metric |
| mcu | SW1 | `mcu.btn_reset` | SW1 | Button_Switch_SMD:SW_SPST_EVQP7A |
| mcu | SW2 | `mcu.btn_boot` | SW2 | Button_Switch_SMD:SW_SPST_EVQP7A |

Full machine-readable map: `assembly-candidate/source-map.json`.
Combined build provenance (netlist/BOM hashes, wrapper hashes):
`source/combined-bridge.json`.

**Planted geometry.**

- Buck: the prototype functional nine is translated as one rigid cluster
  (offset centres the functional bounding box in the reserved `buck_block`
  100-146 x 132-162 mm); its local copper is imported by the canonical path
  rules below.
- MCU: the P1 U4 accepted package's staged geometry is imported, with a
  **placement-only revision**: nine parts staged at `y = 31` inside the
  assumed antenna keepout (18-52 x 20-32) were moved to `y = 35` with source
  identity, footprint and orientation preserved
  (`assembly-candidate/mcu-placement-revision.json`).

## 2. Layer / identity / via mapping

- **Layers**: prototype outer `F.Cu`/`B.Cu` -> target outer pair; target
  physical order `F.Cu / In3.Cu / In1.Cu / In2.Cu / In4.Cu / B.Cu`. Any
  other prototype layer raises rather than being dropped
  (`assembly-candidate/layer-map.json`).
- **Through vias**: recreated with the target `F.Cu-B.Cu` span, 0.8/0.4 mm
  (`assembly-candidate/via-recreation.json`).
- **Prototype-only exclusion**: `J1/J2/TP1-TP4/H1-H4` never become product
  components; 5 fixture copper tracks removed, 3 shared fixture/functional
  tracks cut at the functional end with continuity rechecked
  (`assembly-candidate/prototype-exclusion.json`).
- **U1 replacement ledger** (before/after identities,
  `assembly-candidate/replacement-ledger.json`):

  | Removed | Baseline tstamp | Replaced by |
  |---------|-----------------|-------------|
  | `U27` | `92a720b8-6473-ffc4-7fa8-ef701c075add` | `mcu.mcu` -> `U2` |
  | `U3` | `64548453-6ce6-b0e8-a81b-d46b964b66d2` | `buck.buck` -> `U1` |
  | `L2` | `b00b9a7d-6d7a-14d1-b6ad-9ece56e8a9d7` | `buck.l_out` -> `L1` |

- **Owned-region guard**: every placed instance sits inside `buck_block` or
  `mcu_block` (`assembly-candidate/owned-region-guard.json`).

## 3. Routing (apparatus-only scripted, through `BlockSession`)

The scripted pass now runs **through `run_block.BlockSession`**, not a
parallel native call. `run_block.build_assembly_task_contract` /
`run_block.prepare_assembly` build and seal a combined-assembly task contract
(19 functional instances, all measured pads mapped to their combined nets,
`gnd`/`buck-vcc`/`buck-vcc-1` as the power partition, `sw`/`fb`/`boot` as
signals) and `BlockSession.call("replace_copper", ...)` commits every copper
mutation under the shared action budget, atomic staging, protected-context
hash and Rust check. No material property of the MCU-only profile changed.

- **`gnd`**: one filled F.Cu zone below the antenna keepout connects all 12
  gnd pads, committed as one bounded `replace_copper`; KiCad-native refill
  applied (`--refill-zones --save-board`).
- **`buck-vcc-1` (+3V3)**: an F.Cu bus with pad stubs plus a two-via
  inner-layer run to the buck output cluster. Every segment -- newly routed
  and inherited prototype copper alike -- is raised to the 0.6 mm power floor
  (see §4a).
- `buck-vcc` (+15V), `sw`, `fb`, `boot` are carried by the imported
  prototype local copper.

Session record (`summary.json` -> `session`): contract kind `assembly`,
**2 committed actions**, revision after `9aa3439b…` (per-run; the committed
`summary.json` is authoritative), operations log retained at
`verification/apparatus-only/session/operations.jsonl`.

## 4. Finding-set delta (sets, never counts)

Native reports (`baseline/` and `routed/` directories; command lines in
`*-command.json`):

```text
kicad-cli pcb drc --format json --all-track-errors --schematic-parity \
    --severity-all --output <report> <board>
kicad-cli sch erc --severity-all --format json --output <report> <schematic>
```

| Set | Baseline | Routed | Introduced | Resolved | Persistent |
|-----|----------|--------|------------|----------|------------|
| DRC (all-track-errors + parity + all-severity) | 39 | 26 | **0** | 13 | 26 |
| ERC (all-severity, 0 errors) | 89 | 89 | **0** | 0 | 89 |
| Schematic parity (subset of DRC) | 0 | 0 | **0** | 0 | 0 |
| DRC unconnected items | 23 | 9 | **0** | 14 | 9 |

The 13 resolved findings are the +3V3/gnd inter-block and decoupling opens.
**No new finding is introduced by routing or refill.** The sets are the
intersection of 3 DRC runs per view (kicad-cli is nondeterministic run-to-run).
**Schematic parity is fixed: 98 -> 0.** Two changes removed it: the combined
strict-candidate schematic is now generated **flat** (one root sheet with
unscoped global labels, so a compiled net `buck-vcc` is exported as
`buck-vcc`, not `/BUCK/buck-vcc`) and the board footprint `Value` is set from
`default.csv` (so it is the real part identity, not `?`). The 19
`footprint_symbol_mismatch` + 79 `net_conflict` findings are gone. The
remaining 9 unconnected items are MCU-local signals: `en`, `io0`, `scl`,
`sda` (pull-ups/buttons to module), outside the "shared supply/return" routing
scope of this pass. The residual 26 persistent local findings are attributed
in `summary.json` (9 unconnected, 3 `lib_footprint_mismatch`, 3
`shorting_items`, 3 `solder_mask_bridge`, 3 `track_dangling`, 1 `clearance`,
2 `courtyards_overlap`, 1 `silk_over_copper`, 1 `silk_overlap`).

Invariant checks (`summary.json` -> `checks`):

- `required_connectivity`: **pass** — `gnd`, `buck-vcc`, `buck-vcc-1`, `sw`,
  `fb`, `boot` each one native cluster.
- `inter_block`: **pass** — U2 VCC3V3 and buck +3V3 anchor share a cluster;
  U2 GND and buck GND anchor share a cluster.
- `antenna_keepout`: **pass** — no track/via endpoint inside the keepout.
- `power_width`: **pass** for the power nets after widening the whole
  `buck-vcc-1` (+3V3) net to the 0.6 mm floor; the floor is unchanged. 8
  inherited `fb`/`boot` prototype segments remain at 0.3 mm and are recorded,
  not suppressed (see §4a).
- `no_placeholder_leftover`: **pass** — no `U27`/`U3`/`L2` survives.
- `production_digest`: **pass** — `pcb/temper.kicad_pcb` matches the frozen
  target-context digest `00a27419…ac4d9`; the production board was never
  written (re-verified after the overlay, §4b).

### 4a. `power_width`: what was fixed and what is attributed debt

The previous pass reported 19 segments at 0.3 mm against a 0.6 mm floor on
three nets. Splitting them by function:

- **11 `buck-vcc-1` (+3V3) segments** — the required +3V3 supply. These are a
  power path and **were widened to 0.6 mm** by the same bounded
  `replace_copper` action (all retained prototype +3V3 copper plus all routed
  bus/stub segments). Re-verification: **0 introduced DRC findings**, 13
  resolved, unchanged persistent set — widening is tractable and clean.
- **6 `fb` and 2 `boot` segments at 0.3 mm** — the feedback-divider and
  bootstrap-capacitor nodes. They are **signal nets by function** (µA-scale
  gate/feedback currents, not supply paths) and meet the 0.3 mm signal floor
  the target context defines. They are inherited prototype copper and are
  retained as an explicit `inherited_below_power_floor` residual in
  `summary.json` (net, uuid, width, both floors, reason) rather than silently
  absorbed.

The floor was **not** changed. The one classification change (which nets the
0.6 mm power floor applies to) is explicitly recorded, and every sub-0.6 mm
required-net segment is still visible in the apparatus evidence.

### 4b. Scratch full-board overlay (production board COPY + section)

`pcb/blocks/control-assembly/verification/apparatus-only/overlay/` holds the
scratch overlay. `pcb/temper.kicad_pcb` was **copied, never modified**
(digest re-verified exact after the overlay). The overlay applies the U1
replacement ledger (19 native placeholder instances and 67 local tracks
removed) and inserts the routed section by canonical source identity, joining
only the shared `+15V`/`+3V3`/`gnd` rails; every other section net stays
isolated. Both the base copy and the overlay are refilled with the identical
native command before DRC, and each is sampled 3× with the intersection used
for the delta.

| Overlay DRC set | Base copy | Overlay | Introduced | Resolved | Persistent |
|-----------------|-----------|---------|------------|----------|------------|
| DRC (all-track-errors + all-severity, 3-run intersection) | 599 | 808 | **323** | 114 | 485 |

**The current section is NOT overlay-clean, and the report says so rather
than hiding it.** The introduced set is dominated by physical conflicts
between the placed section and production copper that remains *inside* the
owned regions (the transplant removes only copper touching the 19 replaced
placeholder pads, not every production object inside the envelopes):
`shorting_items` 103, `solder_mask_bridge` 50, `clearance` 44,
`hole_clearance` 24, `track_dangling` 21, `tracks_crossing` 19,
`courtyards_overlap` 19, `unconnected_items` 24, `silk_over_copper` 11,
`silk_overlap` 4, plus `isolated_copper`, `pth_inside_courtyard` and
`via_dangling`. Outside-region **geometry** is exact
(`outside_region_invariance`: pass, 0 problems).

**Mechanism (a) — the section ground pour — was measured and exonerated.**
A controlled A/B on the same section and base (3-run intersections) gave:
legacy board-wide pour **328** introduced; clip-the-pour-to-owned-envelopes
**344**; re-assert-nets-only **337**; both **340**. Clipping does not reduce
the dominant categories at all, raises `unconnected_items` by ~16, and adds a
`zones_intersect`. It also leaves the section's gnd pads in more than one
overlay cluster (the production plane does not bridge every clipped island),
which fails the cross-view endpoint comparison. The decision to retain the
pour is therefore recorded (`summary.json` -> `overlay.section_pour_clip`,
`enabled: false`), not merely an omission. Ground continuity across the
boundary *is* measured on every run: `gnd` islands fall from 40 (base copy)
to 7 (overlay) with no pad lost.

**Mechanism (b) — production tracks re-netted by the refill — is fixed.**
`kicad-cli pcb drc --refill-zones --save-board` rebuilds connectivity and
re-propagates a track's net from whatever copper it now touches, silently
renaming 10 production tracks (e.g. `+3V3 -> gnd`, `V_BUS_SENSE ->
gpio21`). A post-refill pass now re-asserts each untouched production track's
original net **by name** (never by a shifted numeric code); the invariance
record reports `net_reassigned: 0` (was 10) while the underlying geometric
conflicts remain visible as DRC findings against the correctly-named track.

**Root cause of the residual (attributed, not excused):** the section's
staged geometry lands where production copper still exists. Driving the
introduced set to zero needs the production copper inside the owned envelopes
cleared (or the section placed at the native positions) — a follow-up to the
replacement ledger, out of scope for this apparatus pass. The finding remains
an open blocker, not a suppressed number.

## 5. Candidate binding and renders

`verification/apparatus-only/candidate-binding.json` binds the U2 package
board hash, the routed candidate hash, the summary hash, the production
board hash, the overlay board hash, and the cross-view report hash in one
manifest. A later edit invalidates the binding.

A native SVG render of the routed candidate is at
`verification/apparatus-only/renders/control-assembly-routed.svg` (F.Cu, B.Cu,
Edge.Cuts). It is available for human review; this pass did **not** rely on
visual inspection — keepout clearance, connectivity and the finding-set delta
are asserted by the native checks above, not by looking at the render.

**Cross-view comparison** (`cross-view-report.json`): **produced and
passing**. The owned section is extracted independently from both native
boards (assembly view and scratch overlay view), keyed by canonical source
identity, nets canonicalized back to combined names, and compared on pads,
tracks, vias, zones and interface endpoints. `mismatch_count` is 0. Zone
*fill* is context-dependent by construction; the comparison binds zone
identity (net/layer/filled) and verifies native connectivity in each view
rather than comparing filled polygons. Zone subdivision is likewise not an
identity difference: if one view implements a pour as more polygons than the
other, the distinct zone identities are compared (a genuinely different
net/layer/fill still fails). Ground continuity across the section/production
boundary is measured natively on every run (`gnd` islands 40 -> 7, 91 pads
unchanged).

The overlay binding must be **re-bound** after the parallel
`pcb/blocks/mcu/` regeneration lands (the MCU passives `C40`/`C41`/`R72` are
provisional in `target-context.json`); the report records this in
`rebind_required_after`.

## 6. Assisted changes

Two operator/agent-assisted changes were required; both are recorded so they
are not mistaken for autonomous work:

1. **MCU placement revision** — moved nine staged parts out of the assumed
   antenna keepout (U2, placement only).
2. **Prototype footprint fallback (now P1-owned and recorded)** —
   `Inductor_SMD:L_Bourns_SRP1265A` is in neither KiCad stock nor
   `pcb/libs`. `block_source._stock_footprint_source` now falls back to
   `pcb/prototypes/buck-reva/buck-reva.pretty` by footprint stem and records
   the real provenance (`prototype-lib:`), rather than P3 staging a
   temporary override root. The resolution for every used footprint is in
   `assembly-candidate/library-provenance.json`; `lib`/`temper` and KiCad
   stock resolution are unchanged.

## 7. Failed attempts (retained separately)

- **Autonomous live-model construction**: `transport_blocked`
  (`Zen FreeUsageLimitError`, HTTP 429, retry-after ~7726 s;
  `opencode/muse-spark-1.3-contributor-free`, 0 tool calls). Preserved at
  `verification/failed-attempts/live-model-transport.json`, source
  `harness-lab/runs/mcu-20260910-a/handoff.json` -> `live_transport`.
- The P1 U4 autonomous MCU attempt (34 intrinsic silk findings) is retained
  in `harness-lab/runs/mcu-20260910-a/handoff.json` -> `autonomous_attempt`.

## 8. Remaining external interfaces

These are obligations, not fictional connectors, and are not coppered here
(`interfaces.json`):

| Interface | Signals | Domain | Counterpart in this milestone |
|-----------|---------|--------|-------------------------------|
| `BUCK_VIN_15V` | +15V | SELV_LV | No — PS1 is outside this candidate; obligation |
| `BUCK_EN` | en (tie) | SELV_LV | Source-side only; target U1 SOT-23-6 has no EN pad |
| `PWM_HS`, `PWM_LS` | PWM_HS, PWM_LS | signal | No (gate drive) |
| `RTD_SPI` | RTD_CS_N, RTD_SCK, RTD_SDI, RTD_SDO, RTD_DRDY | signal | No (MAX31865) |
| `SAFETY` | SHUTDOWN, RTD_HW_FAULT, WDT_RESET_N, WDT_KICK | signal | No (interlock, TPS3823) |
| `RELAY_DISCHARGE` | RELAY_CTRL, DISCHARGE_CTRL | signal | No |
| `SENSE_ADC` | I_SENSE, V_BUS_SENSE | signal | No |
| `COMMS` | usb_dn, usb_dp, tx, rx, i2c_scl_ui, i2c_sda_ui | signal | No (programming/UI) |
| `SPARES` | gpio18, gpio21, gpio35/36/37, io0, io13, io40/41/42/45/46/48, safety-line, en | signal | Named only |
| MCU-local | en, io0, scl, sda | signal | 9 unconnected DRC items, not routed |

## 9. Blockers (milestone cannot close)

1. Live model transport blocked (Zen 429) — no autonomous construction.
2. **Scratch overlay introduces 323 mandatory findings.** Root cause is
   physical conflict between the placed section and production copper that
   remains inside the owned regions (the transplant removes only
   placeholder-touching copper). The section `gnd` pour is **not** the cause
   (clipping it was measured to raise the count and fail the cross-view
   endpoints). Reported per category, not suppressed; a complete fix needs the
   in-envelope production copper cleared or the section placed natively.
3. **Resolved this pass:** schematic parity 98 -> 0 (flat strict-candidate
   schematic + BOM-sourced board `Value`); production track nets re-propagated
   by the KiCad refill are re-asserted by name (`net_reassigned` 0); the
   `L_Bourns_SRP1265A` vendoring gap is closed in `block_source`.
4. **Fixed since the previous pass:** `run_block.BlockSession` now admits the
   combined assembly (19 instances, combined census/nets) and the pass routes
   through it; the scratch overlay is produced and the cross-view comparison
   passes.
5. **Resolved for power:** the +3V3 (`buck-vcc-1`) net was widened to 0.6 mm
   with 0 introduced findings. `fb`/`boot` remain 0.3 mm as attributed
   signal-net prototype copper (not a supply path), kept visible in
   `summary.json`.
6. MCU-local signal completion (en/io0/scl/sda) unrouted.
7. **Re-bind required:** the overlay consumes the committed assembly package
   built from the pre-regeneration MCU package; re-run U2 composition and
   re-bind `candidate-binding.json` / `cross-view-report.json` after the
   parallel `pcb/blocks/mcu/` re-admission lands.

## 10. Related

- P2 memory closeout: [`memory-report.md`](memory-report.md).
- P1 U4 handoff: `harness-lab/runs/mcu-20260910-a/handoff.json`.
- P3 U1 context: [`README.md`](README.md), `target-context.json`,
  `interfaces.json`.
- Reproduction: see [`README.md`](README.md).
