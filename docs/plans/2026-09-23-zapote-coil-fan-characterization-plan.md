---
title: Zapote coil, pan, and cooling characterization
date: 2026-09-23
status: capture-ready; no physical data
---

# Coil, pan, and cooling characterization

## Decision and review

The existing inverter U3 checker already has a closed 20-scenario registry and the cooling U3 checker retains three separate fan concepts. A second operating-point calculator would duplicate those gates. The useful next step is a traceable bench intake: identify an actual article and fixture, record raw calibrated observations, and only then populate the existing manifests. This plan supplies that intake and keeps every run unmeasured (`NOT_RUN` or an explicit hold) until evidence exists.

Three approaches were considered: reuse the old 47 kHz/coil and free-air fan figures as design inputs; build a new numerical model; or capture actual small-signal coil/pan impedance and installed fan behavior first. The third approach is selected. The old 47 kHz and catalog flow points are hypotheses, while another model cannot resolve unknown article, assembly, and source behavior.

Review boundary: de-energized impedance measurements and isolated low-voltage fan measurements can be prepared independently of a native inverter PCB. Any energized inverter, live pan removal, fault injection, full-bank discharge, or assembled thermal test remains on hold pending a separately reviewed article, bounded energy/current source, protection, test procedure, and stop criteria. No arbitrary voltage, current, or thermal ceiling is inferred here.

The product target is a precise home-kitchen cooker with set/hold temperature, through-glass sensing, probe control, heat-intensity control and presets comparable in behavior to Control Freak Home. These are **later behavioral test scenarios**, not specifications for the unselected coil, pan, fan, bus or discharge circuit. The user's temperature range and recovery criteria still need adoption for Temper. The physical campaign must eventually include temperature step/hold/recovery, different pans and placement, probe-versus-glass disagreement, removal and fault stop, with synchronized power/temperature/flow data; no present capture claims that performance.

## Work packages

1. Freeze a coil winding/ferrite/bracket revision, production gap definition, pan set, fixture, instrument and calibration identity. Record raw complex-impedance points with uncertainty across frequency, excitation current, temperature and geometry in `zapote/inverter/characterization/coil-points.tsv`. Keep the seven inverter U3 coil scenarios in `coil-run-register.tsv` and all other U3 scenarios under their existing owner. Early coil-only fixture measurements inform selection but do not populate the U3 manifest: its current gate requires every measured row to name one physical article. Repeat the coil campaign on the eventual protected inverter article, or separately review and revise that cohort contract before transferring component-only records.
2. Acquire one exact fan and physical duct/fin/enclosure assembly per retained cooling alternative. Record terminal electrical/tach data, installed pressure/flow/temperature maps and timed fault response separately under `zapote/thermal/cooker-envelope/characterization/`. Do not combine the GBU and GBJ thermal boundaries or treat a Sanyo or Sunon free-air endpoint as the installed operating point. A selected fan rail, sensor placement, J1/J2 implementation and joined stop chain are later prerequisites to fill the 17 unknown fields in `candidate-inputs.tsv`.
3. Hand measured coil impedance and real bus/gate waveforms to inverter part/frequency selection. Hand selected VB-local capacitance and any detached energy-storage elements to discharge. Hand each physical loss destination, fan electrical load and installed fin-path behavior to cooling. All three handoffs need source revision and uncertainty; no absent term becomes zero.

## Acceptance and negative controls

- Every capture identifies article/build/serial, pan or fan, fixture, instrument/serial, calibration, probe or correction settings, raw byte path and SHA-256, operator, reviewer, timestamp, conditions, units and uncertainty. An uncalibrated or unidentified record stays `NOT_REVIEWED` even if its numeric columns are full.
- The coil matrix includes no pan, reference cold/hot, a distinct weak pan, offset and lift. Frequency and current span multiple points. A single LCR reading or unloaded inductance cannot define the loaded operating window. Live removal is a separate protected transient and remains `HOLD_ENERGIZED`.
- Installed fin flow/pressure and heat-source inlet temperature are measured on the same physical duct/grille/enclosure revision. Tach alone cannot pass blocked-flow behavior; fan self-recovery cannot release the fault latch.
- Re-run the inverter U3 test suite's negative controls for missing current-zero, nominal-only bus, `PWR_RTN` substitution, F2 as direct-bank clearer, free-air L as loaded L, synthetic evidence, and absent raw SHA. Re-run cooling U3 tests for stuck J1, automatic recovery, invalid sensor and source drift. These are checker tests, not physical qualification.
- A capture packet can advance to independent engineering review. Neither a complete template nor matching hashes by themselves prove a safe operating envelope. The inverter U3 gate caps its verdict at `REVIEW_PENDING`; cooling candidate selection remains blocked pending independent assembly qualification.

## Source anchors and dependencies

- `zapote/inverter/U3-MEASUREMENT-READINESS.md` and `zapote/inverter/evidence/measurement-scenarios.tsv`
- `zapote/inverter/coil-evidence.md` and `zapote/inverter/interface-contract.md`
- `zapote/thermal/cooker-envelope/readiness-receipt.md`, `candidate-inputs.tsv`, `loss-ledger.md`, `space-ledger.md`
- `zapote/discharge/interface-contract.md` and `zapote/discharge/bench-qualification.md`

No coupon PCB is specified. The actual coil termination, sensor, fan harness, duct geometry and instrument connection have not been selected; a generic coupon could falsely imply an acceptable current, isolation or mechanical path. Draw a fixture schematic and, if useful, a board only after those connections and limits are reviewed.
