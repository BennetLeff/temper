# PFC switching-loss measurement — physical test plan (proposal)

Date: 2026-09-17 (revised after audit)
Status: **PROPOSAL — NOT AUTHORIZED.** The campaign plan explicitly authorizes
no purchase, fabrication or powered bench operation. Nothing here may be
executed until a qualified engineer, working under the site's electrical safety
process, separately approves it.

Campaign context: [CLOSEOUT.md](CLOSEOUT.md),
[LOSS-ACCOUNTING-AUDIT.md](LOSS-ACCOUNTING-AUDIT.md).

Method reference: Tektronix, *Double Pulse Testing for Power Semiconductor
Devices with an Oscilloscope and Arbitrary Function Generator*
(75W-61623-4). Standards: JEDEC JEP182, JESD24-10; IEC 60747-8, 60747-9.

## 1. Why this measurement

The two switching models disagree by ~1.45x at the retained baseline operating
point (analytic 37.37 W overlap vs independent vendor model 26.76 W
Eoss-inclusive), and the retained board device STW65N65DM2AG has no independent
result at all — no reachable vendor model, no datasheet Eon/Eoff. Until one
switching energy is measured, neither model can be used to rank switching-
adjacent candidates.

## 2. What this measurement can and cannot decide

This section exists because the first draft of this plan overreached.

**Can decide, at the tested conditions only:**
- Whether the analytic or the vendor switching model is closer to reality for
  the tested device at the tested bus, current, gate network and temperature.
- The measured Eon/Eoff/Eoss of the tested devices at those conditions.

**Cannot decide:**
- "Everything derived" from either model. Agreement at one operating point
  validates that point; it does not license applying a factor elsewhere.
- That a part swap is worthwhile overall. A switching-energy ratio says nothing
  about package thermal path, gate-drive compatibility, EMI, sourcing, cost, or
  the rest of the assembly ledger. Swap economics require an assembly-level
  comparison, not this test.
- Anything about conduction, gate, bridge, inductor or auxiliary losses.
- The board's thermal behaviour.

A switching ratio is a **necessary input** to a swap decision, not the decision.

## 3. Devices under test

| Priority | Device | Role |
| --- | --- | --- |
| P0 | `STW65N65DM2AG` | retained board part; the unverified lever |
| P0 | `IPW65R045C7` | C1 baseline; control tying this test to the frozen models |
| P1 | `IPZ60R040C7` | K-SILICON candidate; best independent switching device found |

## 4. Conditions (frozen, so results compare to the models)

- **Bus:** 400 V DC, measured at the device terminals.
- **Gate drive:** 0 -> 12 V; **9.7 ohm turn-on / 5.3 ohm turn-off** external
  (the retained `no-assist` buffered drive). Record the measured edge and any
  driver current limit.
- **Target currents:** turn-off 15.01 A, turn-on 11.95 A; sweep at least
  8 / 12 / 15 A to expose the energy-vs-current slope. Report the **achieved**
  current for every event; never scale an energy to a requested current.
- **Temperature:** 25 C and a hot point. DPT pulses deliberately limit
  self-heating; a two-pulse test does **not** establish a settled junction
  temperature. Establish and report the case/tab temperature, state the method,
  and state explicitly that junction temperature is inferred, not measured.
- **Freewheel diode:** use the retained boost diode if available
  (`C3D20065D`); otherwise state the substitute. The substitution changes both
  Eon and Eoff (the vendor simulation: Eon +10%, Eoff -7%, sum +1.0%), so it
  must be reported with the result.
- **Clamp inductor:** sized for the target currents without saturating; a test
  element, not the PFC boost choke. State value and saturation current.

## 5. Apparatus

- Isolated DC supply, 400 V, current-limited, with low-inductance film bus caps.
- Clamped-inductive double-pulse fixture with DUT, freewheel diode, clamp
  inductor, and a **coaxial shunt or current-viewing resistor (CVR)** in the
  device source/drain path.
- Isolated gate driver reproducing 9.7/5.3 ohm at 0 -> 12 V, driven by pulse
  widths that are independently adjustable.
- Oscilloscope >= 500 MHz, >= 2 GS/s, >= 4 channels, with area/integration math.
- Probes rated for the maximum voltage and current:
  - `V_DS`: high-voltage differential probe, >= 1 kV.
  - `I_D`: **isolated current probe across a coaxial shunt/CVR**. Clamp-on
    Hall probes and Rogowski coils are explicitly not suitable here — their
    bandwidth (<= 120 MHz / ~15 MHz) and insertion inductance distort the fast
    edge. (Tektronix Table 1.)
  - `V_GS`: passive probe with an MMCX test point where possible.
- Safety enclosure with interlocks (Section 9).

## 6. Standards and measurement definitions

Use the industry-standard threshold definitions, not ad-hoc ones:

- `td(on)`: V_GS at 10% to V_DS at 90%.
- `tr`: V_DS 90% to 10% (falling edge, turn-on).
- `td(off)`: V_GS at 90% to V_DS at 10%.
- `tf`: V_DS 10% to 90% (rising edge, turn-off).

The double-pulse sequence has three stages: (1) first pulse establishes the
target current in the load inductor; (2) turn-off is measured at the end of the
first pulse; (3) turn-on is measured at the start of the second pulse, whose
width is kept short to limit heating.

## 7. Method

1. **Deskew V_DS against I_D before any energy measurement.** Probe delay
   mismatch is the dominant systematic error in an Eon/Eoff integration. A
   post-acquisition software deskew against measured waveforms is acceptable;
   report the residual skew in ns, and report the energy sensitivity to it.
2. Capture the turn-off event and the turn-on event in one acquisition per
   condition. Record pulse widths, trigger, and probe settings.
3. Integrate `E = INT v_ds(t) * i_d(t) dt` over each transition, using an
   explicit window rule (e.g. V_DS 10%-90% thresholds) and reporting the
   sensitivity to a +/-10 ns window shift, as the simulation did (+0.087%).
4. **Reverse recovery is part of turn-on.** The freewheel diode's recovery
   current adds to `I_D` during turn-on, so a measured `Eon` includes the diode's
   recovery energy. Record the freewheel device, and state explicitly whether
   `Eon` is reported with or without recovery. Note that the clamp inductor and
   the PFC boost inductor are different elements.
5. **State the `Eoss` convention in both directions.** A hard-switched clamp
   turn-on dissipates the DUT's stored output-capacitance energy, so a measured
   `Eon` normally includes it. Report `Eon_including_Coss` and
   `Eon_excluding_Coss`, and measure `Eoss(400 V)` separately. The analytic
   model books `Eoss` separately (1.5106 W at this point); the vendor simulation
   measured 9.76 uJ. Do not double-count in either direction.
6. Repeat >= 10 events per condition; report mean, spread and the number of
   rejected events with reasons. Never average across a fault or a probe
   artefact.
7. Retain raw waveform files, not screenshots alone.

## 8. Comparison targets and acceptance criteria

At 25 C, `f = 129107.39198576905 Hz`:

| Quantity | Analytic | Independent vendor model |
| --- | ---: | ---: |
| IPW65R045C7 `Eon` | — | 102.50 uJ @ 12.07 A |
| IPW65R045C7 `Eoff` | — | 104.79 uJ @ 14.99 A |
| IPW65R045C7 `Eoss(400 V)` | 11.7 uJ (datasheet) | 9.76 uJ |
| IPW65R045C7 overlap term | 37.368 W | — |
| IPW65R045C7 `(Eon+Eoff)*f` | — | 26.76 W (Eoss-inclusive) |
| IPW65R045C7 overlap-only* | 37.368 W | 25.50 W |
| STW65N65DM2AG analytic switch+gate | 93.183 W | not obtained |

\* overlap-only = `(Eon - Eoss + Eoff)*f`, the treatment that matches the
analytic model's separate `Eoss` booking.

Acceptance criteria, scoped deliberately:

- **Model discrimination (the primary result).** Report the measured
  `(Eon+Eoff)*f` and its overlap-only counterpart against both model values. A
  result within +/-25% of one model and far from the other discriminates between
  them **at these conditions only**. State that scope in the receipt.
- **Device ratio (secondary input).** Report the STW65N65DM2AG to IPW65R045C7
  switching ratio as an input to a swap analysis, not as a swap decision.
- **Uncertainty.** Report an explicit band from probe skew, window sensitivity,
  event spread, diode substitution and temperature. A bare point value is not an
  acceptable receipt.

Do not widen the criteria after seeing results. If the measurement lands between
the models or outside the band, that is the finding.

## 9. Safety

400 V DC is lethal and DC arcs do not self-extinguish at zero crossing.
Tektronix states plainly that power semiconductor testing involves lethal
voltages and currents and requires appropriate enclosures with safety interlocks
and PPE.

- Qualified personnel only, under the site's electrical safety process; no lone
  work.
- Sealed enclosure with interlocks; de-energize and verify dead before
  connecting or changing anything.
- Discharge and verify the bus capacitor bank before every intervention.
- Rated probes and PPE; correct grounding/isolation practice for the chosen
  probe type.
- This document is not a safety assessment. The authorizing engineer owns the
  hazard analysis.

## 10. Optional companion measurement (recommended)

The input bridge is the largest term not challenged by any independent
comparison (28.30 W) and its datasheet carries one forward-drop test point
(1.05 V at 12.5 A, 25 C). A simple `V_F(I)` sweep on `GBJ2510-F` — DC or
low-frequency, no fast probes, no deskew — would replace an 0.85/1.30 V
assumption band with measured data at the real currents and temperatures. It is
materially lower risk than the switching test and firms up the term that the
audit shows now matters relatively more. Consider running it in the same
session.

## 11. What to retain

Raw captures, probe calibration and deskew records, fixture schematic, measured
and inferred temperatures, per-event energies and spread, achieved currents,
window rule and sensitivity, Eoss and reverse-recovery conventions, and SHA-256
of every file. The receipt must separate measured from modelled quantities and
leave hardware qualification explicit.

## 12. Authorization

```text
authorizing engineer:
approval reference:
approved apparatus / facility:
hazard analysis reference:
approved conditions (any deviation from Section 4):
date:
```
