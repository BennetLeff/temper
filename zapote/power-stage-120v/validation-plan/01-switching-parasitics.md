# 01 — Layout parasitics and switching transient

Part of the [master plan](00-MASTER-PLAN.md). Read the master plan's ground
rules first.


> **Update 2026-09-27:** the board is now **native-13**, with the tank-CT
> detector, BAS116H clamps and a 100 Ω / 1 kΩ permit/DIS network. Use
> [SIMULATION-RUNBOOK.md](SIMULATION-RUNBOOK.md) and `sim-kit/` for the
> procedure; this document keeps the goals and pass criteria.

## Goal

Predict, from the routed copper and vendor device models:

1. The **peak drain–source voltage** on each MOSFET at turn-off, in normal
   operation and when turning off a fault current.
2. **Gate ringing** and **false turn-on**: the gate voltage of the *off*
   MOSFET while its partner switches.
3. Whether the **dead time** (≈ 348 ns nominal) lets the switch node swing
   fully, which is zero-voltage switching (ZVS).

These are the failures that destroy MOSFETs on first power-up. D4 conditions 2
and 3 in `DECISIONS.md` require bench measurements; this task predicts them
first.

Evidence class: **simulation/model-based**. The physical test that confirms it
is scope measurement at bring-up (VDS, VGS, switch node) at low bus voltage
first.

## Inputs

| Input | Where |
| --- | --- |
| Board | `native-09/section.kicad_pcb` (record SHA-256) |
| Copper census | `tools/copper_dump.py` (see master plan §3) |
| Gate trace lengths already measured | `native-06/verification/gate-lengths.json` (same routing as native-09 for gate nets; re-measure if unsure) |
| Stackup | `stackup.json`: F.Cu–In1 0.4355 mm, In1–In2 **0.5 mm**, In2–B.Cu 0.4355 mm, εr ≈ 4.3–4.5 |
| Parts | `frozen/default.csv` |
| Dead time | R9/R17 = 39 kΩ → DT ≈ 8.6 × 39 + 13 ≈ 348 ns nominal (POWER-SECTION.md §4 table) |
| Operating points | POWER-SECTION.md §2; `docs/hardware/power-section-120v/coil_mc.rs` output `coil-mc-output.txt` |

### Circuit elements in the switching loops

**Commutation loop, leg A:**
local bus capacitor (C38 and C39: B32652A0104K000, 0.1 µF film)
→ BUS_P (In2 plane)
→ Q2 drain (pad Q2.2)
→ Q2 source (Q2.3, net `sw_a`)
→ Q3 drain (Q3.2)
→ Q3 source (Q3.3, net `leg_ret`)
→ In1 LEG_RET region
→ R5 pad 1 (WSK2512R0010FEA, 1 mΩ)
→ R5 pad 4 (`hv_ret`)
→ HV_RET (In1 plane)
→ capacitor return pad.

**Commutation loop, leg B:** the same path with C40/C41, Q5 (high side) and
Q6 (low side). The net is `sw_b`.

Both legs share R5 and the planes. The bulk capacitors C5/C6
(B32656G0275J000, 2.7 µF each) sit farther away, on the western bus.

**Snubbers:** C12 (Q2 D–S), C13 (Q3), C19 (Q5) and C20 (Q6) are 1 nF, 1 kV
C0G (GRM31A5C3A102JW01D). Find each capacitor's two nets in the netlist to
confirm which switch it sits across.

**Gate loops:**

| Gate | Driver pin | Series resistor | Hold-off | Return |
| --- | --- | --- | --- | --- |
| Q2 high side | U1 OUTA (U1.15) | R10 | R11 | U1.14 → `sw_a` |
| Q3 low side | U1 OUTB (U1.10) | R12 | R13 | U1.9 → `leg_ret` |
| Q5 high side | U2 OUTA (U2.15) | R18 | R19 | U2.14 → `sw_b` |
| Q6 low side | U2 OUTB (U2.10) | R20 | R21 | U2.9 → `leg_ret` |

- All series resistors are 3.9 Ω and all hold-offs are 10 kΩ.
- Driver-to-resistor copper lengths are 38.2/43.3 mm on leg A and 30.8/35.4 mm
  on leg B (PLACEMENT-REVIEW.md).
- The gate driver is supplied from `v15_ls`, a 15 V unipolar supply.

## Datasheets and models to obtain

Record the URL, revision and SHA-256 of each file in `sources/`.

- **Infineon IPW65R018CFD7:**
  - Datasheet: the VDS rating (650 V), VGS limits (static and transient),
    VGS(th) minimum, Rg,int, Coss(V), Qoss, body-diode Qrr and trr, ID,pulse,
    and the package inductance if stated.
  - The CoolMOS CFD7 650 V SPICE library from the Infineon product page
    ("Simulation models"). Infineon ships PSpice syntax.
- **TI UCC21550:** datasheet output resistance (pull-up/pull-down), peak
  current, propagation delay, dead-time programming accuracy, and the VCCI
  input thresholds. TI provides a PSpice/TINA model; use the datasheet
  behaviour if the model won't run in ngspice.
- **TDK B32652A0104K000 and B32656G0275J000:** ESR and self-inductance (ESL),
  or the self-resonant frequency, from which ESL = 1/((2πf)²C).
- **Vishay WSK2512:** its inductance, if published.
- **Murata GRM31A5C3A102JW01D:** its C0G capacitance vs voltage (flat) and
  ESL if available.

## Step 1: estimate loop inductances (required)

The verdict must not depend on one uncertain inductance number. Do this in
two parts.

**1a. Analytic estimate.** Write `scripts/loop_inductance.py`, which:

- Reads the copper census JSON and locates the pads above by reference
  (items with `kind == "pad"` and `ref == "Q2.2"`, and so on).
- Computes, for each leg's commutation loop, the sum of:
  - **Plane-pair section:** for current flowing along In2 over In1 (or F.Cu
    over In1), use `L = μ0 · d · ℓ / w`. Here `d` is the dielectric thickness
    between the two conductors carrying opposite current, `ℓ` is the path
    length and `w` is the overlap width. Take `ℓ` from pad-centre distances
    and `w` from the filled-zone polygons: measure the narrowest overlap along
    the path with shapely.
  - **Vias:** use `L ≈ (μ0·h/2π)·(ln(4h/d) + 1)` per via, with the via
    length `h` and drill `d`. Place vias in parallel where banks exist.
  - **Packages and components:** TO-247 source/drain lead inductance from the
    datasheet. If it isn't given, **sweep 5–15 nH per device** and record it
    as an assumption. Capacitor ESL comes from the datasheet.
- Writes `outputs/loop_inductance.json` with each term, its source, and a low,
  nominal and high total.

**1b. Field-solver cross-check (optional but preferred).**
- Build FastHenry2 from https://github.com/ediloren/FastHenry2 with `make` in
  `src/`. Model each leg loop as segments and uniform planes from the census.
- Report agreement with 1a. If the build fails twice, skip this step and say
  so in the report.

Do the same for the **gate loops**. For a trace over a plane, use
`L ≈ μ0·h·ℓ/w_eff` with `w_eff` ≈ trace width + 2h. That gives roughly
0.4–1 nH/mm for these widths; compute it rather than using this number.

## Step 2: build the ngspice deck

Create `scripts/leg.cir`, one half-bridge leg:

- DC bus source at the corners **170 V** (120 V rms crest), **198 V** (140 V
  rms crest) and **280 V** (the OVP trip level: the bridge can still switch
  up to it).
- The bulk capacitance through an ESR/ESL branch, and the local 0.1 µF film
  capacitors through their ESL. Put the loop inductance from step 1 as lumped
  inductors split between the drain side and the source side of each device.
  Use the low, nominal and high values, and a `.step`-style sweep via
  `foreach` in a `.control` block.
- Both MOSFETs from the Infineon library. ngspice needs PSpice compatibility:
  create `.spiceinit` in the run directory containing
  `set ngbehavior=psa`. If the library still fails, stop and report the error
  text. Don't substitute a generic MOSFET model without saying so.
- Snubber capacitor 1 nF across each device, using the netlist's actual
  connection.
- **Gate drive:** a 0/15 V pulse source with the driver's datasheet
  pull-up/pull-down resistance, then the gate-loop inductance, then 3.9 Ω,
  then the device gate. The source return runs through its own loop
  inductance, so include the common-source inductance: the part of the power
  loop shared with the gate return. Include the 10 kΩ hold-off.
- **Dead time:** 348 ns nominal. Sweep 250, 348 and 450 ns (resistor tolerance
  plus driver accuracy; replace this with the datasheet accuracy).
- **Load:**
  - Model A: an inductive current source equal to the tank current at the
    switching instant.
  - Model B, for one case: the full series tank (70 µH, 0.54 µF, pan
    resistance from `coil-mc-output.txt`) at 35 kHz, to confirm A.

## Step 3: cases

Run every case at every bus voltage and every loop-inductance corner.

| Case | Switched current | Purpose |
| --- | --- | --- |
| S1 nominal ZVS | +37 A (tank peak), soft turn-on | Normal overshoot and ringing |
| S2 fault turn-off | 61 A (nominal OCP trip) and 71 A (trip + 10 A spread) | Worst turn-off overshoot |
| S3 light load | 2, 5 and 10 A at 60 kHz | Is ZVS lost? Hard turn-on, body-diode recovery |
| S4 hard turn-on | Partner body diode conducting 20 A, then hard turn-on | Reverse-recovery spike and false turn-on of the off device |

For each run, record:
- peak VDS of each device
- peak and minimum VGS of each device, especially the off device
- dv/dt and di/dt at the switch node
- ringing frequency and decay time
- whether VDS reaches ~0 before turn-on (ZVS yes/no)

## Acceptance criteria

| Quantity | Pass | Notes |
| --- | --- | --- |
| VDS peak, S1 and S3, all corners | ≤ 520 V | 80 % of 650 V; this is the project clamp/derating target in DC-LINK-CLAMP.md |
| VDS peak, S2 at 280 V bus | ≤ 585 V (90 % of 650 V) | Report the margin. Anything above 585 V is FAIL, and anything above 650 V is a destroyed device |
| Off-device VGS during partner switching | stays below VGS(th),min − 0.5 V (datasheet) | Otherwise false turn-on risk: FAIL, and name the fix (e.g. negative drive or Miller clamp) but don't implement it |
| VGS peak (overshoot) | within the datasheet transient VGS limit | Undershoot is limited the same way |
| ZVS at S1 | achieved at nominal dead time | Report the minimum current for ZVS at 170 V and 198 V |
| Sensitivity | The verdict holds across the low–high loop inductance range, or the report states the inductance at which it flips | |

## Deliverables

In `validation-results/01-switching-parasitics/`:

- `README.md` in the master template, including a one-line answer for each
  criterion.
- `outputs/loop_inductance.json` and the waveform CSVs.
- For S1, S2 and S4: plots of VDS, VGS (both devices) and ID over the
  switching edge. Use PNG via Python matplotlib from the CSVs.
- The minimum-ZVS-current table (it feeds task 05) and the S2 turn-off
  waveform (it feeds task 02).
- The switch-node dv/dt and edge time (they feed task 07).

## Pitfalls

- The Infineon model files can contain several devices; select
  `IPW65R018CFD7` by exact subcircuit name, and record the level (L1/L3).
- Keep ngspice time steps small enough (`.tran 0.1n ...`, or set
  `.options method=gear reltol=1e-4`). An unresolved edge under-reports
  overshoot. Halve the step once and confirm the peak changes by less than 2 %.
- Don't forget the snubber capacitor or the 1 mΩ shunt. The shunt is part of
  the loop, and task 02 needs the shunt voltage waveform.
- The common-source inductance (source lead plus shared copper) changes the
  gate voltage during di/dt. Leaving it out hides false turn-on.
- Report the model limits: no temperature dependence unless you use the
  model's temperature parameter, and a lumped rather than distributed layout.
