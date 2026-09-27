# 05 — Resonant tank operating envelope

Part of the [master plan](00-MASTER-PLAN.md). Read the master plan's ground
rules first.


> **Update 2026-09-27:** the board is now **native-13**, with the tank-CT
> detector, BAS116H clamps and a 100 Ω / 1 kΩ permit/DIS network. Use
> [SIMULATION-RUNBOOK.md](SIMULATION-RUNBOOK.md) and `sim-kit/` for the
> procedure; this document keeps the goals and pass criteria.

## Goal

Over the full range of pans, power levels and line voltage, find the tank's
current and voltage stresses and check each against its part rating:

- **Resonant capacitors:** C21/C22 are 942C12P22K-F and C23 is 942C12P1K-F,
  together 0.54 µF. Check the voltage vs frequency derating and the current.
- **Current transformer:** T1 is a CST3015-100ED, 1:100, rated 88 A. Check the
  burden and the peak current.
- **Bleed resistors:** R22–R25, 4 × 470 kΩ 1206 across the resonant bank. Check
  each resistor's voltage and power.
- **Soft switching:** check the ZVS margin at every operating point, using
  task 01's minimum-ZVS-current table.

Evidence class: **simulation/model-based**, with an established design model.
The physical test that confirms it is coil and pan measurement (COIL-MC.md)
plus the tank current waveform at bring-up.

## Inputs

- `docs/hardware/power-section-120v/COIL-MC.md`, `coil_mc.rs`,
  `coil-mc-output.txt`: the coil (≈70 µH nominal) and pan-resistance
  distribution, and the operating frequencies (33–39 kHz at full power,
  up to 60 kHz at light load).
- `power_section.rs` and `power-section-output.txt`: tank current
  18.7 A rms line-average, 37 A peak.
- POWER-SECTION.md §4 table notes: the C21–C23 current share is "10.3 + 10.3 +
  9.2 A vs ~18.7 A", and it says R22–R25 "can be left with ~250 V on C_res
  after an OCP trip".
- The bus is **unfiltered**: it follows the rectified line, 0 to 170 V at
  120 V rms, or up to 198 V at 140 V rms. The tank sees a 120 Hz-modulated
  drive.
- The control modes in use are frequency control, phase shift and
  line-synchronous bursts (POWER-SECTION.md §2).

## Datasheets needed

- **CDE 942C:** the permissible AC voltage vs frequency curve, and the
  current rating vs frequency, for 942C12P22K-F and 942C12P1K-F.
- **Coilcraft CST3015-100ED:** the burden resistance range, the maximum
  current, and the volt-second limit.
- **Yageo RC1206:** working voltage, overload voltage, and power at 70 °C.

## Steps

1. **Write the model.** Write `scripts/tank.cir` (ngspice) or reuse the Rust
   model `coil_mc.rs`. Prefer reusing it for consistency, and cross-check one
   point in ngspice. The model is a full-bridge square wave into
   L_coil–R_pan–C_res in series:
   - the drive amplitude follows `|V_line(t)|` over a full 8.33 ms half-cycle
   - include the MOSFET RDS(on) and the dead time
2. **Build the case grid:**
   - pans: p05, median and p95 from `coil-mc-output.txt` (L, R)
   - power: 100 %, 50 % and the lowest continuous level, plus a burst example
   - line: 108, 120 and 140 V rms
   - frequency set by the control law in `coil_mc.rs`
3. **Record per case, over the line cycle:**
   - tank current rms and peak
   - capacitor voltage peak and rms, and frequency
   - T1 primary current
   - switching-instant current (for ZVS)
   - energy stored in C_res at turn-off
4. **Check each result** against:
   - the capacitor voltage-vs-frequency curve, at the actual frequency
   - the capacitor current rating, splitting the current between C21/C22/C23
     by capacitance
   - T1 at 88 A peak, and its burden/volt-seconds
   - the bleed resistor voltage: V_Cres,peak / 4 per resistor against the
     1206 working voltage, and power ≈ V_rms² / R
5. **Check ZVS.** At each operating point, is the current at the switching
   instant ≥ task 01's minimum ZVS current? If task 01 isn't done, use the
   energy criterion ½·L_coil·I² ≥ 2 × Eoss(V_bus), from the datasheet Eoss,
   and mark it provisional.
6. **Check trip ring-down.** Starting from the worst-case capacitor voltage at
   an OCP trip, find the voltage left on C_res and the bleed time to below
   60 V (the SELV-like touch threshold; state the basis you use).

## Acceptance criteria

| Check | Pass |
| --- | --- |
| Resonant capacitor voltage | ≤ the datasheet permissible voltage at the operating frequency, every case |
| Resonant capacitor current | ≤ the rating per capacitor, every case |
| T1 | Peak ≤ 88 A, and the burden within the datasheet |
| R22–R25 | Voltage per resistor ≤ the 1206 working voltage; power ≤ 50 % of rating at the local temperature |
| ZVS | Report the region where ZVS is lost. It's expected at light load; the finding is the boundary, not a fail |
| Bleed-down | Time to < 60 V reported. Flag it if > 10 s |

## Deliverables

In `validation-results/05-resonant-tank-envelope/`:

- `README.md`
- `outputs/cases.csv`, one row per case with every recorded quantity
- the plots
- `outputs/zvs_map.png` (power vs pan, ZVS yes/no)
- the rectified leg-return current RMS, which task 03 needs for the R5 shunt
  loss

## Pitfalls

- The capacitor datasheet voltage rating falls steeply with frequency. Use the
  curve at 33–60 kHz, not the DC rating.
- Line-average RMS and crest RMS differ a lot on an unfiltered bus. Report
  both.
