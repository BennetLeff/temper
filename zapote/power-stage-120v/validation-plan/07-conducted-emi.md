# 07 — Conducted EMI pre-check

Part of the [master plan](00-MASTER-PLAN.md). Read the master plan's ground
rules first. This task uses task 01's switch-node edge rate. Without it, sweep
1–20 V/ns and mark the result provisional.

## Goal

Estimate the conducted emissions at the mains terminals J1 (line and neutral)
from 150 kHz to 30 MHz. Check whether the input filter leaves margin to the
applicable limit before a lab pre-scan. Separate differential-mode (DM) and
common-mode (CM) noise, so that a shortfall points to the right filter part.

Evidence class: **simulation/model-based**, and deliberately coarse. It
predicts roughly where the emissions sit and which filter part matters; it
doesn't predict pass or fail within a few dB. The physical test that confirms
it is the conducted-EMI pre-scan with a LISN (POWER-SECTION.md §7 item 6).

## Limits

The design basis names **FCC Part 18** (consumer ISM equipment: induction
cooking) and **Part 15B** (POWER-SECTION.md §7).

- Get the current conducted limits from the official eCFR text of 47 CFR
  18.307 (the conducted limits table). Record the retrieval date and the table
  in `sources/`.
- For international context, also plot CISPR 14-1 / CISPR 11 (group 2, class
  B) if you can cite the table from a published source.
- **Don't type limits from memory.**

## Circuit to model (ngspice)

**Mains and measurement:**
- **LISN:** the standard 50 µH / 50 Ω network per CISPR 16-1-2, one per line.
  Emission is the voltage across each 50 Ω.
- **Mains:** 120 V rms, 60 Hz, on the LISN's supply side.

**Input filter, in circuit order (read the netlist to confirm):**
- **Fuse and surge:** F1, RV1 (MOV; model as its capacitance, from the datasheet).
- **X capacitors:** C1, C2 (R463R410000M1M, 1 µF X2), with ESR and ESL.
- **Common-mode choke:** L1 (B82726S2203A020). From its datasheet take the CM
  inductance, the leakage (DM) inductance, the winding resistance, and the
  impedance-vs-frequency curve. Model the self-resonance with a parallel C.
- **Y capacitors:** C3, C4 (DE1E3RA222MA4BP01F, 2.2 nF) to PE (J6).

**Downstream of the filter:**
- **Rectifier:** BR1, using diode models with junction capacitance.
- **Bus capacitors:** C5/C6 (5.4 µF) and C38–C41 (0.4 µF), with ESL.

**Noise source:**
- **Bridge:** two switch nodes (`sw_a`, `sw_b`) as trapezoid voltage sources
  from 0 to V_bus, with the task 01 rise/fall times, at 35 kHz (and 60 kHz),
  in anti-phase (full bridge).
- **Tank load:** the coil and resonant capacitor between the nodes.

**Common-mode paths to PE:**
- **MOSFETs:** each TO-247 tab (drain) couples to the PE-bonded heatsink
  through its insulating pad: `C = ε0·εr·A/d`, where A ≈ tab area and d = pad
  thickness. The tab is the drain. The high-side tabs (Q2, Q5) sit on BUS_P,
  which is quiet. The low-side tabs (Q3 on `sw_a`, Q6 on `sw_b`) sit on the
  **switch nodes**, which are noisy; they are the main CM source. Confirm the
  nets from the netlist. Use the pad options from
  task 03, or 2 representative pads.
- **Coil and pan:** capacitance from the coil to the pan and to earth. It's
  unknown, so sweep 10–100 pF and say so.
- **Bridge:** BR1 to the heatsink, the same pad method.

## Steps

1. Write `scripts/emi.cir` and a `.control` block that runs a transient long
   enough for several 60 Hz half-cycles at the switching resolution. Or, more
   practically, run at a fixed bus voltage (170 V crest) for ~2 ms, then FFT
   the LISN voltages.
2. Convert to dBµV. Apply a quasi-peak / average detector approximation: for
   a desk check, report the peak spectrum and label it "peak, not QP". An
   FFT with ~9 kHz resolution bandwidth equivalent is acceptable if you
   explain it.
3. Split DM and CM: DM = (V_L − V_N)/2 and CM = (V_L + V_N)/2 at the LISNs.
4. Run the sensitivities:
   - coil-to-earth capacitance
   - insulating-pad capacitance
   - L1 CM inductance −30 % (tolerance and saturation)
   - edge rate ×2

## Acceptance criteria

| Check | Pass |
| --- | --- |
| Predicted peak vs limit, 150 kHz–30 MHz | ≥ 6 dB margin at nominal; report the minimum margin and its frequency |
| Dominant mode | Identified (DM or CM) at the worst frequency |
| Sensitivity | States which parameter moves the worst margin most |

A shortfall isn't a failed task. It's a finding: report which filter part to
change and by how much, but **don't change the board**.

## Deliverables

In `validation-results/07-conducted-emi/`:

- `README.md`
- `scripts/emi.cir` and the post-processing script
- `outputs/spectrum_dm_cm.png` (with the limit line)
- `outputs/margins.csv`
- `sources/` (the limit table and datasheet curves)

## Pitfalls

- The CM choke's impedance falls above its self-resonance. A pure-inductor
  model overstates attenuation at MHz. Use the datasheet impedance curve.
- Without the heatsink capacitance the CM noise is near zero, which is wrong.
  Include it.
- Keep the sim step ≤ 1/10 of the edge time, or the MHz content is lost.
