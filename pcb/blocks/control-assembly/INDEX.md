# Control-assembly candidate index

Machine entry point for the P3 U2-U4 buck + MCU integration candidate.
Status: **`apparatus-only-assisted`** — not autonomously constructed, not a
qualified cooker. Human-readable entry point:
`docs/hardware/control-assembly/README.md`; full report:
`docs/hardware/control-assembly/integration-report.md`.

## Candidate

| Artifact | Path | Schema |
|----------|------|--------|
| Combined source bridge | `source/combined-bridge.json` | `control-assembly.combined-bridge.v1` |
| Assembly candidate index | `assembly-candidate/candidate-index.json` | `control-assembly.candidate-index.v1` |
| Source-path identity map | `assembly-candidate/source-map.json` | `control-assembly.source-map.v1` |
| Layer map | `assembly-candidate/layer-map.json` | `control-assembly.layer-map.v1` |
| Via recreation | `assembly-candidate/via-recreation.json` | `control-assembly.via-recreation.v1` |
| Prototype exclusion | `assembly-candidate/prototype-exclusion.json` | `control-assembly.prototype-exclusion.v1` |
| Replacement ledger | `assembly-candidate/replacement-ledger.json` | (U1 ledger + after identities) |
| Owned-region guard | `assembly-candidate/owned-region-guard.json` | (U1 envelopes) |
| MCU placement revision | `assembly-candidate/mcu-placement-revision.json` | `control-assembly.mcu-placement-revision.v1` |
| Cross-view scaffold | `assembly-candidate/cross-view-scaffold.json` | (comparison categories) |
| Assembly board | `assembly-candidate/control-assembly.kicad_pcb` | KiCad 10 |
| Assembly schematic | `assembly-candidate/control-assembly.kicad_sch` (+ `buck`/`mcu` sheets) | KiCad 10 |

## Verification

| Artifact | Path |
|----------|------|
| U3 summary | `verification/apparatus-only/summary.json` |
| Candidate binding (board + summary + production hashes) | `verification/apparatus-only/candidate-binding.json` |
| Native connectivity | `verification/apparatus-only/routed-connectivity.json` |
| Native DRC (baseline / routed) | `verification/apparatus-only/baseline/drc.json`, `.../routed/drc.json` |
| Native ERC (baseline / routed) | `verification/apparatus-only/baseline/erc.json`, `.../routed/erc.json` |
| Refill record | `verification/apparatus-only/refill/refill-command.json` |
| Cross-view report | `verification/apparatus-only/cross-view-report.json` |
| Rendered candidate | `verification/apparatus-only/renders/control-assembly-routed.svg` |
| Failed autonomous attempt | `verification/failed-attempts/live-model-transport.json` |

## Identity, layer, net

- Identity: canonical instance path (`buck.*`, `mcu.*`); combined refdes in
  `source-map.json`. Prototype `U3`/`C9` -> `U1`/`C1`; P1 package MCU `U1`
  -> `U2`.
- Layers: prototype `F.Cu`/`B.Cu` -> target outer pair of
  `F.Cu / In3.Cu / In1.Cu / In2.Cu / In4.Cu / B.Cu`; unsupported layers
  rejected.
- Nets: source `buck-vcc` = +15V feed, `buck-vcc-1` = +3V3 output/MCU VCC3V3,
  `gnd` = shared return. Target aliases `+15V`/`+3V3` resolved by source
  identity, never string match.

## Finding-set delta

DRC (all-track-errors + schematic-parity + all-severity): baseline 126 ->
routed 113, **introduced 0**, resolved 13, persistent 113. ERC 55 ->
55, introduced 0 (0 errors). Schematic parity 98 -> 98 (persistent).
Unconnected 20 -> 7. Sets are compared, never counts.

## Pending external interfaces

See `interfaces.json`: `BUCK_VIN_15V`, `BUCK_EN`, `PWM_HS`, `PWM_LS`,
`RTD_SPI`, `SAFETY`, `RELAY_DISCHARGE`, `SENSE_ADC`, `COMMS`, `SPARES`, plus
MCU-local `en`/`io0`/`scl`/`sda` completion.

## Related

- P2 memory closeout: `docs/hardware/control-assembly/memory-report.md`.
- P1 U4 handoff: `harness-lab/runs/mcu-20260910-a/handoff.json`.
