# Control-assembly integration report (P3 U2-U4)

Plan: `docs/plans/2026-09-10-1322-feat-buck-mcu-composition-plan.md`
Units: U2 (compose source-derived geometry), U3 (route and verify), U4 (package).

**Verdict: `apparatus-only-assisted`. The section has complete required
supply/return connectivity with no introduced DRC finding, but it is not a
qualified cooker.** The live construction model was transport-blocked (Zen
HTTP 429), so no autonomous construction occurred. The autonomous attempt is
preserved separately at
`verification/failed-attempts/live-model-transport.json`; this report
describes the labelled scripted pass only.

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
| mcu | SW1 | `mcu.btn_reset` | SW1 | Resistor_SMD:R_0603_1608Metric |
| mcu | SW2 | `mcu.btn_boot` | SW2 | Resistor_SMD:R_0603_1608Metric |

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

## 3. Routing (apparatus-only scripted)

The scripted pass uses the same bounded native copper primitive
(`buck_native.replace_copper`, dispatched by `run_block.BlockSession`) under
the KiCad Python runtime.

- **`gnd`**: one filled F.Cu zone below the antenna keepout connects all 12
  gnd pads; KiCad-native refill applied (`--refill-zones --save-board`).
- **`buck-vcc-1` (+3V3)**: an F.Cu bus with pad stubs plus a two-via
  inner-layer run to the buck output cluster.
- `buck-vcc` (+15V), `sw`, `fb`, `boot` are carried by the imported
  prototype local copper.

`run_block.BlockSession` itself was **not** instantiated: its task contract
is MCU-profile-specific (`REQUIRED_INTERNAL_NETS = ("vcc", "gnd")`,
`power_nets = ("vcc",)`, and the MCU staging census must equal the strict-map
census). The combined netlist uses `buck-vcc`/`buck-vcc-1` and carries 19
instances, so the session contract needs a P1-owned profile/contract change.
This is a named blocker, not worked around by editing P1 code.

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
| DRC (all-track-errors + parity + all-severity) | 126 | 113 | **0** | 13 | 113 |
| ERC (all-severity, 0 errors) | 55 | 55 | **0** | 0 | 55 |
| Schematic parity (subset of DRC) | 98 | 98 | **0** | 0 | 98 |
| DRC unconnected items | 20 | 7 | **0** | 13 | 7 |

The 13 resolved findings are the +3V3/gnd inter-block and decoupling opens.
**No new finding is introduced by routing or refill.** The 98 schematic-parity
findings are persistent and unchanged: Value `?` and sheet-prefixed net names
(`/BUCK/<net>` vs `<net>`) — the same class as the MCU package's 67. The
remaining 7 unconnected items are MCU-local signals: `en`, `io0`, `scl`,
`sda` (pull-ups/buttons to module), outside the "shared supply/return"
routing scope of this pass.

Invariant checks (`summary.json` -> `checks`):

- `required_connectivity`: **pass** — `gnd`, `buck-vcc`, `buck-vcc-1`, `sw`,
  `fb`, `boot` each one native cluster.
- `inter_block`: **pass** — U2 VCC3V3 and buck +3V3 anchor share a cluster;
  U2 GND and buck GND anchor share a cluster.
- `antenna_keepout`: **pass** — no track/via endpoint inside the keepout.
- `power_width`: **fail** — imported prototype +3V3 runs are 0.3 mm, below
  the 0.6 mm assembly floor. Inherited prototype geometry; needs review, not
  a new section violation.
- `no_placeholder_leftover`: **pass** — no `U27`/`U3`/`L2` survives.
- `production_digest`: **pass** — `pcb/temper.kicad_pcb` matches the frozen
  target-context digest `00a27419…ac4d9`; the production board was never
  written.

## 5. Candidate binding and renders

`verification/apparatus-only/candidate-binding.json` binds the U2 package
board hash, the routed candidate hash, the summary hash, and the production
board hash in one manifest. A later edit invalidates the binding.

A native SVG render of the routed candidate is at
`verification/apparatus-only/renders/control-assembly-routed.svg` (F.Cu, B.Cu,
Edge.Cuts). It is available for human review; this pass did **not** rely on
visual inspection — keepout clearance, connectivity and the finding-set delta
are asserted by the native checks above, not by looking at the render.

**Cross-view comparison** (`cross-view-report.json`): the canonical
comparison method and categories are bound, but the second (scratch
full-board overlay) view is **pending** — inserting the section into the
read-only production board requires the autonomous placement/routing turn
that is transport-blocked. The comparison is a labelled gap, not a pass.

## 6. Assisted changes

Two operator/agent-assisted changes were required; both are recorded so they
are not mistaken for autonomous work:

1. **MCU placement revision** — moved nine staged parts out of the assumed
   antenna keepout (U2, placement only).
2. **Prototype footprint fallback** — `Inductor_SMD:L_Bourns_SRP1265A` is in
   neither KiCad stock nor `pcb/libs`, so P3 stages it from
   `pcb/prototypes/buck-reva/buck-reva.pretty`. This is a P1 vendor gap
   (`block_source._stock_footprint_source`); a P1 fix is requested.

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
| MCU-local | en, io0, scl, sda | signal | 7 unconnected DRC items, not routed |

## 9. Blockers (milestone cannot close)

1. Live model transport blocked (Zen 429) — no autonomous construction.
2. Schematic parity: 98 persistent findings.
3. Scratch full-board overlay insertion and cross-view comparison pending.
4. `run_block.BlockSession` contract does not fit the combined assembly
   (P1-owned profile/contract change needed).
5. P1 vendorer gap for `L_Bourns_SRP1265A`.
6. `power_width` finding on inherited prototype +3V3 copper (0.3 mm).
7. MCU-local signal completion (en/io0/scl/sda) unrouted.

## 10. Related

- P2 memory closeout: [`memory-report.md`](memory-report.md).
- P1 U4 handoff: `harness-lab/runs/mcu-20260910-a/handoff.json`.
- P3 U1 context: [`README.md`](README.md), `target-context.json`,
  `interfaces.json`.
- Reproduction: see [`README.md`](README.md).
