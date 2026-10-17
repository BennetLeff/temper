# 03 — Loss and thermal budget (heatsink and airflow)

Part of the [master plan](00-MASTER-PLAN.md). Read the master plan's ground
rules first.

## Goal

1. Compute the dissipation of every component that gets warm, at the full-power
   operating point and at the worst corner.
2. From those losses, derive the **required heatsink thermal resistance** for
   the shared heatsink (MOSFETs Q2/Q3/Q5/Q6 and bridge BR1). Give the
   **airflow requirement** as the input for decision D2, which is still open.
3. List the board-mounted heat sources for task 04.

Evidence class: **bounded calculation**, using datasheet values at stated
temperatures. The physical test that confirms it is a thermocouple temperature
rise at full power in the enclosure.

## Inputs

- Operating envelope (POWER-SECTION.md §2):
  - tank current ~18.7 A rms (line-average), 37 A peak
  - 33–39 kHz at full power
  - input 15 A at 120 V
- Existing estimates:
  - MOSFETs ~25 W for all four and bridge ~29 W (`docs/hardware/power-section-120v/power_section.rs` and `power-section-output.txt`)
  - `LOSS-REFACTOR.md`
- Rebuild those independently here. Don't just copy them; compare your numbers
  to them at the end.
- Parts: `frozen/default.csv`.
- Heatsink arrangement (DECISIONS.md D2): one shared, PE-bonded heatsink along
  the long top edge (board x 12–165 mm), with electrically insulated MOSFETs
  and bridge. **The insulating pad and the heatsink aren't chosen yet**, so
  this task produces their requirements.

## Datasheet values needed

- **IPW65R018CFD7:**
  - RDS(on) vs Tj (the typ/max curve at 25/100/125 °C)
  - Eoss and Coss(tr)
  - switching energy or charge (Qg, QGD)
  - body-diode VSD and Qrr
  - RthJC
  - maximum Tj
- **GBJ2510-F:** VF vs IF and temperature, and RthJC per leg or package.
- **WSK2512R0010FEA:** power rating vs pad/board temperature.
- **MC78L05ACHT1G (U3):** thermal resistance in SOT-89; its input is `v15_ls`
  (≈15 V) and its output `hot5` (5 V). Get the load current from the U4–U9,
  U5 bias and comparator datasheets.
- **IRM-20-15 (PS1) and IRM-05-15 (PS2):** efficiency at the actual load, which
  gives their internal loss.
- **Insulating pad:** since none is selected, use two representative options,
  an alumina-filled silicone pad and a polyimide film. Give their RthCS per
  TO-247 from real datasheets and say which pads you used.

## Step 1: MOSFET losses

Per device, in a full bridge each device conducts half the time:

- **Conduction:** `P_cond = I_dev,rms² × RDS(on)(Tj)`, where
  `I_dev,rms = I_tank,rms / √2`. Use the RDS(on) at the assumed junction
  temperature and iterate: guess Tj, compute the losses, compute Tj from step
  4, and repeat until Tj changes by less than 2 °C.
- **Turn-off:** with ZVS, a hard turn-off of the current at the switching
  instant is partly absorbed by Coss and the 1 nF snubber. Estimate
  `E_off` ≈ from datasheet switching curves at the turn-off current, scaled.
  If task 01 exists, integrate VDS × ID over the simulated turn-off instead;
  that's better.
- **Turn-on:** 0 under ZVS. Add a **light-load / lost-ZVS case**
  (`E = ½·Coss(tr)·V² + Qrr·V` per event, at 60 kHz and 198 V) from task 01 S3.
- **Gate drive:** `Qg × Vdrive × f`, but this dissipates mostly in the driver
  and gate resistors, not the MOSFET. Report where it goes.
- **Operating points:** nominal (120 V, 1,710 W, 35 kHz) and worst (140 V rms
  line, 39 kHz, tank current +10 %). State your basis for the +10 %; taking
  the coil_mc p95 is better.

## Step 2: other heat sources

| Part | Calculation |
| --- | --- |
| BR1 bridge | Each diode conducts half-cycles: `P = 2·(VF·I_avg + r·I_rms²)` using the input current waveform. With no PFC, the input current is roughly sinusoidal at 15 A rms, so check this against the bus model |
| R5 shunt (1 mΩ) | I_rms through the leg return × 1 mΩ. Find the leg-return RMS: it's the tank current commutated to the bus. Take the rectified-tank-current RMS from task 05 or compute it |
| Gate resistors R10/R12/R18/R20 | Qg × Vdrive × f share |
| U3 LDO | (15 V − 5 V) × I_load |
| R22–R25 bleed | V² / R over the actual tank-capacitor voltage waveform (task 05) |
| C21–C23 resonant capacitors | ESR × I² (datasheet dissipation factor at frequency) |
| T1 current transformer | Burden loss (datasheet) |
| L1 common-mode choke | Winding resistance × input current² |
| PS1/PS2 | (1/η − 1) × load |

## Step 3: heatsink requirement

- **Ambient:** assume the internal enclosure air is **50 °C (nominal)** and
  **65 °C (worst)**. These are assumptions for an under-counter appliance;
  state them clearly as assumptions.
- **Junction limit:** design Tj ≤ **125 °C** for the MOSFETs, derated from the
  datasheet maximum, and the equivalent derating for BR1 from its datasheet.
- **Model:** a single isothermal heatsink at `T_s`.
  - Each MOSFET needs `T_s ≤ Tj_design − P_i·(RthJC + RthCS)`.
  - BR1 gives a similar limit.
  - `T_s,max` is the lowest of those limits.
- **Result:** `Rth,SA,required = (T_s,max − T_amb) / P_total,heatsink`.
  Report it for both ambients, both pad options, and nominal and worst losses.

Translate the result into an airflow requirement using typical extrusion
curves: natural convection vs forced air at 1, 2 and 3 m/s. Cite a
manufacturer's extrusion datasheet, for example a Fischer or Aavid profile of
a size that fits the 153 mm heatsink length.

## Acceptance criteria

- Every loss has a formula, inputs with sources, and a number at nominal and
  worst. The sum is compared with `power_section.rs`. Differences over 20 %
  are explained.
- The report states the required Rth,SA and whether natural convection is
  plausible. Most likely it isn't, so it gives the forced-air velocity needed.
  **This is the D2 input.**
- There's a per-component power table for task 04, with reference, W, and
  location from the board.
- **FAIL** if any part exceeds its rating at the worst corner even with an
  ideal heatsink, for example the shunt power rating or the LDO junction
  temperature.

## Deliverables

In `validation-results/03-loss-thermal-budget/`:

- `README.md`
- `scripts/losses.py`
- `outputs/losses.json` (per component, per corner)
- `outputs/heatsink_requirement.json`
- `outputs/board_heat_sources.json`, holding `ref`, `watts_nominal`,
  `watts_worst` and the footprint centre from the copper census. It feeds
  task 04.

## Pitfalls

- RDS(on) roughly doubles from 25 °C to 125 °C. Using the 25 °C value halves
  the conduction loss. Iterate on temperature.
- The tank RMS and the rectifier RMS vary over the 120 Hz line cycle, because
  the bus isn't filtered. Use line-cycle-averaged RMS, and state it.
- The MC78L05 in SOT-89 dissipating (15 − 5) × I can overheat with only tens
  of mA. Check it; it's easy to miss.
