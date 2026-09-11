# Control-assembly integration candidate (P3 U2-U4)

**Status: `apparatus-only-assisted` — not a qualified cooker, not autonomously
constructed.** The live construction model was transport-blocked (Zen HTTP 429),
so this package is the labelled apparatus-only scripted result. The autonomous
outcome is preserved separately in
`pcb/blocks/control-assembly/verification/failed-attempts/live-model-transport.json`.

**Milestone status: INCOMPLETE.** The coordinator join, contract acceptance,
replay, and full remaining-interface inventory are in
[`harness-report.md`](harness-report.md). Closure is still blocked by the
missing live model delivery/construction turn and the scratch overlay's
introduced findings (below). Schematic parity is now **fixed (0 findings)**;
so is the P1 vendorer gap for the Bourns inductor. This README, the
integration report, and the memory report are the P3/P2 owner reports the
coordinator joins.

This directory is the entry point for the buck + MCU section that fits the
cooker board. It composes the source-derived buck functional nine with the P1
U4 accepted MCU ten, routes their shared supply/return, and records every
mapping and remaining interface needed by the next owner.

## What is here

| Path | What it is |
|------|------------|
| `target-context.json` | P3 U1 authoritative target: outline, six-layer stackup, domains, reserved regions, replacement ledger, provenance. |
| `interfaces.json` | Internal required connections vs future RTD/safety/programming obligations. |
| `mcu-input-contract.json` | The P1 U4 input contract U2 composed against. |
| `source/combined-bridge.json` | Real combined-wrapper build: 19 components keyed by instance path, netlist/BOM hashes. |
| `assembly-candidate/` | The U2 assembly candidate: source-path map, layer map, via recreation, prototype exclusion, replacement ledger, owned-region guard, cross-view scaffold, library provenance, generated PCB + flat schematic. |
| `verification/apparatus-only/` | The U3 scripted routing/verification pass: routed board, native DRC/ERC reports, finding-set delta, connectivity, candidate binding. |
| `verification/failed-attempts/` | The autonomous live-model attempt, preserved separately. |
| `../../docs/hardware/control-assembly/harness-report.md` | Coordinator report (U1-U3): contract acceptance, attempt/intervention ledger, replay, tests, remaining interfaces, milestone verdict. |
| `../../docs/hardware/control-assembly/integration-report.md` | Full integration report and finding-set delta. |
| `../../docs/hardware/control-assembly/memory-report.md` | P2 memory closeout (link). |

## Reproduce

```bash
# U2: build the combined source and compose the assembly candidate
.venv/bin/python harness-lab/compose_assembly.py compose

# U3: apparatus-only scripted routing + native checks
.venv/bin/python harness-lab/run_control_assembly.py

# Tests: U2 scenarios 1-4 and U3 scenarios 1-7
.venv/bin/python -m pytest harness-lab/test_block_composition.py \
    harness-lab/test_control_assembly.py -q
```

`pcb/temper.kicad_pcb` is read-only (R6): the scripts never write it. Its
digest is checked against the frozen target context on every U3 run.

## Key measured facts

- **19 functional instances** mapped by canonical source path (`buck.*`,
  `mcu.*`), never by refdes. The combined build renumbers them
  (prototype `U3`/`C9` -> combined `U1`/`C1`; standalone MCU `U1` -> combined
  `U2`), which is why the refdes is not the identity.
- **Layers**: prototype outer `F.Cu`/`B.Cu` map to the target outer pair of
  the six-layer stackup `F.Cu / In3.Cu / In1.Cu / In2.Cu / In4.Cu / B.Cu`.
  Any other prototype layer is rejected, never dropped.
- **Through vias** are recreated with the target `F.Cu-B.Cu` span, 0.8/0.4 mm.
- **Prototype fixtures** `J1/J2/TP1-TP4/H1-H4` are excluded; 5 fixture copper
  tracks were removed and 3 shared fixture/functional tracks were cut at the
  functional end with continuity rechecked.
- **U1 replacement ledger**: native `U27`->`mcu.mcu`, `U3`->`buck.buck`,
  `L2`->`buck.l_out`, retaining before/after identities.
- **Schematic parity**: the strict-candidate schematic is emitted **flat**
  (one root sheet, unscoped global labels) and the board footprint `Value`
  is set from the BOM (`default.csv`), so the board and schematic agree on
  both net names and values: **0 parity findings** (was 98: 19
  `footprint_symbol_mismatch` + 79 `net_conflict`).
- **Switch identity**: `SW1`/`SW2` are the real
  `Button_Switch_SMD:SW_SPST_EVQP7A` (`EVQ-P7A01P`), not the stale 0603
  placeholder.
- **Vendoring**: `Inductor_SMD:L_Bourns_SRP1265A` resolves through the P1
  vendorer's prototype-library fallback and is recorded as
  `prototype-lib:` in `assembly-candidate/library-provenance.json`
  (previously a P3-local workaround).

## Verification result (apparatus-only)

Full details in `integration-report.md` and
`verification/apparatus-only/summary.json`. In short:

- Required connectivity: **pass** — `gnd`, `buck-vcc` (+15V), `buck-vcc-1`
  (+3V3), `sw`, `fb`, `boot` each form one native cluster; U2 VCC3V3/GND share
  the buck supply/return cluster.
- DRC (all-track-errors + schematic-parity + all-severity): baseline 39 ->
  routed 26, **0 introduced**, 13 resolved, 26 persistent; unconnected
  23 -> 9.
- ERC (all-severity): 89 warnings, **0 errors**, 0 introduced.
- Schematic parity: **0 -> 0** (fixed by the flat schematic + BOM-sourced
  board `Value`).
- Antenna keepout: **pass**. Production digest: **exact**. No placeholder
  leftover: **pass**.
- Required power path: **pass** — the +3V3 (`buck-vcc-1`) net was widened to
  the 0.6 mm floor with 0 introduced findings; 8 inherited `fb`/`boot` 0.3 mm
  prototype segments are attributed signal-net copper and kept visible.
- BlockSession: **admitted** — the combined 19-instance assembly routes
  through `run_block.BlockSession` (2 bounded actions; no native bypass).
- Cross-view comparison: **produced, 0 mismatches** (assembly vs scratch
  overlay); ground continuity across the boundary measured (gnd islands
  40 -> 7). Scratch overlay: **produced but not clean** — it introduces 323
  findings, dominated by section-placement conflicts with production copper
  still inside the owned regions; an open integration blocker, reported not
  suppressed. The section's `gnd` pour was exonerated (clipping it was
  measured to *raise* the count and break the cross-view endpoints), and the
  10 production track nets re-propagated by KiCad's refill are re-asserted by
  name (`net_reassigned` 0).

## Remaining interfaces (not closed by this milestone)

Power: `BUCK_VIN_15V` (PS1 counterpart is not in this candidate) and
`BUCK_EN` (source-side tie only). Signal, named obligations:
`PWM_HS`, `PWM_LS`, `RTD_SPI`, `SAFETY`, `RELAY_DISCHARGE`, `SENSE_ADC`,
`COMMS`, `SPARES`. MCU-local signal completion still open: `en`, `io0`,
`scl`, `sda` (pull-up/button to module; 9 unconnected DRC items). See
`interfaces.json` and the integration report.

## Blockers keeping the milestone open

1. Live model transport blocked (Zen 429) — no autonomous construction turn.
2. Scratch full-board overlay introduces 323 findings. Root cause is
   section-placement conflicts with production copper that remains inside the
   owned regions (the transplant removes only placeholder-touching copper);
   the section's `gnd` pour is **not** the cause (clipping it was measured to
   raise the count and break the cross-view endpoints). A complete fix needs
   the production copper inside the owned envelopes cleared or the section
   placed at the native positions — a follow-up, not silently excused.
   Cross-view comparison passes; outside-region geometry is exact; production
   track nets are re-asserted after refill.
3. Re-bind required after the parallel `pcb/blocks/mcu/` regeneration: the
   committed assembly package (and therefore the overlay binding) predates it.
4. Live-delivery memory receipt: P2 records delivery of the frozen buck-memory
   selection to the retained model-input payload, but no live model turn ran,
   so the plan's live-delivery requirement is unsatisfied (see
   [`harness-report.md`](harness-report.md) §4).
5. Uncommitted milestone artifacts: the working tree carries P1/P2/P3 source
   and evidence that are not yet committed (see `harness-report.md` §7). The
   branch is not reproducible until the owner lands them.
