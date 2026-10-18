# sensor-r3 PCB decisions (C1 pan-sensor electronics)

2026-10-14. Scope: HANDOFF section B. Every number below is printed by
`checks.py` into `checks.json` (run `python3 checks.py`; it exits 1 on any
failed gate). All 11 gates pass for the proposed circuit.

The circuit under test is the controller as captured on branch
`controller-layout` (300b8a934, `zapote/controller`, read-only), called
"captured" below. "Proposed" is that circuit plus `CHANGE-REQUEST.md`.

## For the CAD agent (G11 and the cartridge leads): read this first

| Item | Requirement | Source in checks.json |
|---|---|---|
| Clearance, any tank-class part to any cartridge or cable conductor | **≥ 3.0 mm** | item 7 |
| Creepage, same | **≥ 8.0 mm** (reinforced, 250 V row, PD3, material group III) | item 7 |
| Solid insulation, if credited | ≥ 2 mm (IEC 60335-1 cl. 29.3), or three thin layers that each pass the reinforced test. The cable's own insulation is not credited. | item 7 |
| Which parts count as tank class | Winding, coil leads, **ferrite bars** (PC95 is semi-conductive, so treat it as at tank potential) and the resonant bank. Measure to any floating metal that can bridge to a SELV conductor (the spring, the wave spring) as if it were a conductor. | item 7 |
| Working voltage | 242 V rms, 640 V peak recurring, 33–60 kHz (R40, from the power stage) | item 7 |
| Low-k Pt leads, first 20 mm | **Manganin**, Ø0.08, four conductors, in place of constantan. Thermal conductivity is the same (22 vs 21 W/m·K), so the G4 cold leak stays at 0.022 mW/K. | item 9 |
| Twisting in the post | S+ with S−, and F+ with F−. Pitch ≤ 5 mm, centre spacing ≤ 0.30 mm. Untwisted leads pick up 50 mV at 40 kHz; twisted, the bound is 6.6 mV. | item 4 |
| Splices (manganin to copper) | All four splices at the same height, within 0.5 mm, inside one potted block | item 9 |
| Insulation between leads in the hot zone | **≥ 10 MΩ at 300 °C** between any two leads and across the element pads. 1.04 MΩ gives 0.1 K. Glass-fibre sleeve, separate bores in the PI post, or ceramic potting; no PTFE above 260 °C. | fault check |
| Film orientation | Pt film toward the disc. Facing away costs 0.016 K of self-heating (0.106 vs 0.090 K). | item 3 |
| Pigtail | 6 × AWG26 M22759/12 (PTFE, nickel-plated copper, 260 °C, 600 V), as three twisted pairs, from the splice block to the inline connector | item 9 |
| Inline 6-pin connector | Outside the coil and ferrite footprint, where the air is ≤ 85 °C, ≥ 8 mm from tank parts, and reachable with the cover lifted. Pinout in `CHANGE-REQUEST.md` §4. | item 9 |

## D1. The captured RTD channel cannot run C1 in the coil eye

Captured design against the bounding coil pickup (`checks.json` item 4):

- **Signal at the converter:** 779 LSB of differential signal at RTDIN±.
  The only filter is the 1 nF across RTDIN±, whose corner sits above 1 MHz
  with a source impedance near 100 Ω.
- **Runaway comparator:** it sees 44 K of threshold ripple. Its 100 kΩ
  branch has no capacitor, so it would trip on coil ripple near 260–270 °C.

The pickup bound:
- **Pan potential.** Winding-mean voltage × 2, from
  `temper-coil-driver-r1/tank_cm.json` (one-sided bank, 28 A ceiling).
- **Coupling.** 1.18 pF in total: 2 × the film capacitance through the
  disc and bond, plus 0.2 pF from winding to pigtail.
- **Magnetic.** 20 mT in the eye and 1 mT on the harness.

Controller C29 deferred this filter to bench EM2/S3, because a ≤ 1 kHz
differential RC appeared to break the RTD unit's 100 ms open-lead response.
That conclusion used 10.5 τ, which is the settling time to 15 bits. The real
detection event is a comparator crossing. With the pull-ups moved to the
connector side and set to 499 kΩ:
- an open S+ is caught by the runaway comparator in 33 ms (25 °C);
- an open S− is caught by the low window in 13 ms.

**Decision:** add the filter now (CR-1). The bench confirms it; it does not
discover the problem.

## D2. Filter topology: two poles on the sense lines, nothing in series on the force lines

**Sense lines.** J3 → 1.00 kΩ → 100 nF C0G across the pair → 1.00 kΩ →
100 nF C0G across RTDIN±, plus 1 nF C0G from each pin to ground.
Each J3 pin also gets a 220 nF X7R to ground and an ESD5Z3.3.

**Results:**
- **Physical bound:** ≤ 0.11 LSB at the pins from 20 to 100 kHz.
- **Handoff test:** 1 V common mode at 40 kHz, applied through 150 Ω total
  (600 Ω per line, the IEC 61000-4-6 CDN convention), with tolerance corners.
  The result is 0.51 LSB.
  - That injection drives 6.8 mA, about 50 times the physical bound.
  - It stays below 1 LSB from 33 to 100 kHz.
  - It reaches 2.45 LSB at 20 kHz, below the coil's 33 kHz minimum.

**Criterion.** The residual amplitude must be below 1 LSB, with no credit
for the sinc3 filter. The modulator clock is unpublished, so an alias onto
DC can't be ruled out, and an amplitude below 1 LSB bounds both aliasing
and rectification.

**Why no series resistor on FORCE±.** The runaway comparator reads the
force-loop voltage. A series resistor there moves the trip point, and it
cuts the reference current.

**Moved to the connector side of the filter, so their DC currents never cross
the 2 kΩ:**
- the 499 kΩ pull-ups;
- the 100 kΩ window/runaway branch, which now has 10 nF to ground
  (τ = 1 ms);
- the low-window divider return.

Firmware removes the fixed loading: R_true = R_meas − (7.86e-4·R_meas −
0.0331 Ω).

## D3. Accuracy: what ±0.3 K can and cannot mean for a MAX31865

These are the worst cases over 40–250 °C after a single gain calibration.
The calibration uses a 50 ppm reference resistor at R(200 °C) on J3, with
the board at 25 °C; the board then runs from 0 to 85 °C (±60 K).

| Term at 250 °C | Captured (RT 25 ppm) | Proposed (RG2012V 5 ppm) |
|---|---|---|
| Rref tempco | 0.80 K | 0.16 K |
| Calibration reference | 0.03 K | 0.03 K |
| Loading/leakage residual (TVS, pin leakage, pull-ups, divider currents) | 0.02 K | 0.06 K |
| Thermo-EMF, manganin, 2 K between splices | 0.004 K | 0.004 K |
| **Board-controlled terms, linear** | 0.86 K | **0.26 K** |
| MAX31865 offset, ±3 LSB at cal and at use (strict) | 0.23 K | 0.23 K |
| MAX31865 FS + INL (datasheet typical only) | 0.09 K | 0.09 K |
| **RSS, all terms** | 0.84 K | **0.30 K** (0.298) |
| Strict linear, all terms | 1.18 K | 0.58 K |

**Decision.** The gate is:
- the board-controlled terms, stacked linearly, ≤ 0.30 K; **and**
- the RSS of every term ≤ 0.30 K.

The strict linear stack is reported, not gated. The MAX31865 bounds its
offset at ±3 LSB with no drift specification. That alone is 0.23 K at 250 °C,
so no MAX31865 design can be proven to ±0.3 K linear from its datasheet.
The typical curve (TOC06) shows about ±0.1 °C over die temperatures from
−40 to 100 °C.

**The captured Rref fails by itself.** C35 swapped it to a 25 ppm part for
prototype stock, which costs 0.8 K at 250 °C on a hot board.

**CR-2 restores the RTD library's original Susumu RG2012V-431-W-T1**
(0.05 %, 5 ppm/K). The RSS margin is nil (0.298 K). If the bench shows the
need, the next step is a Vishay VSMP0805 foil resistor (0.2 ppm/K, about
$10). It removes 0.16 K from both stacks.

**Ageing is outside the gate.** 0.01 % of Rref drift costs 0.05 K at 250 °C.
Record Susumu's load-life figure when ordering.

## D4. Runaway comparator: reference it to S−, not ground (CR-3)

**The captured trip shifts with the force return.** The captured comparator
compares V(RTDIN+) to BIAS/3 referred to ground. Every ohm in the FORCE−
return moves the trip: the C1 manganin leads (1.80 Ω per conductor) and the
MAX31865's internal FORCE− switch, whose resistance is not specified (swept
0.5–20 Ω). The C6 band of 297–319 °C assumed leads of 0–1 Ω and no switch.
On C1 the band becomes **237.5–316.3 °C**, which reaches below the 250 °C
setpoint.

**The fix.** Return the 20 k/10 k divider to the connector-side S− instead of
ground. The comparison is then
R > k·(Rref + R_F+)/(1 − k), and the FORCE− path drops out.
- **Proposed band:** **299.2–321.9 °C**.
- **Margin:** ≥ 44 K above the 250 °C maximum setpoint plus the 5 K B2
  overshoot.
- **Upper limit:** below the bond's 325 °C intermittent limit.

The lower edge sits 0.8 K below the firmware's 300 °C limit, which C6
already accepted.

## D5. Rim NTC: keep the captured GPIO9 channel; reject the ADS1115

ADC1 is no longer full. C27 freed GPIO9 (ADC1_CH8), and the captured design
already reads the rim there: 1.00 k pull-up, 10 k/100 nF, TLV9061.

**Resolution:**
- worst case 0.057 K over 100–280 °C, with firmware choosing the attenuation
  by node voltage;
- below 93 °C the channel saturates (ATTEN3 full scale). That is by design:
  the 1 k pull-up serves the hot end.

**Accuracy** is 10.2 K linear at 250 °C, and the sensor's own B tolerance
(±2 %) is 7.5 K of it. An ADS1115 would not move that, so it is rejected.

**Firmware rules:**
- correct for the rail with the existing MCP3202 CH1 (LM4040) reading of
  v3v3;
- use ATTEN0 when the node is below 0.80 V.

**Consequences for the firmware agent:**
- **Cross-check threshold.** "Pt100 below rim" must use **25 K**, not 15 K,
  or a correct pan will trigger D1 probes.
- **Sink error.** A rim error reaches the KF estimate at 0.0198 K per K,
  which is 0.2 K at the worst rim error.

**TVS.** The captured ESD5Z3.3 on RIM_SENSE has a 3.3 V stand-off, but the
node reaches 3.367 V (v3v3 maximum). CR-6 swaps it to ESD5Z5.0T1G.

## D6. Second hardware trip on the rim NTC: fitted (CR-5)

**Why.** Leakage across the element (lead insulation breaking down in the hot
zone) reads low and is electrically invisible. 1 kΩ in parallel reads 164 °C
when the true temperature is 250 °C.
- Today only firmware D1 and the rim cross-check catch it.
- A hardware rim trip is the independent backstop. It also protects the
  cartridge polymers.

**The circuit:**
- **Comparator:** a TLV3201 on rim_filt, against v3v3 × 10k/(86.6k + 10k).
  The threshold is ratiometric, so the rail cancels.
- **Trip:** nominal 275.6 °C. The band is **262.3–288.1 °C** over the NTC's
  R25 and B tolerances, the resistors and V_IO, including 1.7 K of
  self-heating, which trips it early.
- **Output:** ORed with the RTD runaway into RUNAWAY_FAULT through an
  SN74LVC1G32. The interlock has no free input.

**Patent position (US10278238B2).** The rim NTC is outside the cap, so the
Pt100 remains the only under-cap sensor feeding hardware. Its two
comparators, window and runaway, share one sensor.

**Bench condition.** Bench T3 logs the rim under a 250 °C hold; it must stay
≤ 252 °C (band low − 10 K). Study 08 measured the glass underside 12–46 K
below the pan. If the log comes out higher, raise the 86.6 k, rather than
removing the trip.

## D7. Self-heating is incidental and under budget

- **Bias current:** 3.16–3.92 mA, the MAX31865's own continuous measuring
  current; VBIAS stays on in auto mode.
- **Element power:** ≤ 2.19 mW.
- **Offset at h_c 888:** worst 0.090 K at 320 °C (film toward the disc). That
  is under 0.1 K.
- **Correction:** firmware may subtract a 0.061 K constant, leaving ±0.025 K
  over the whole contact spread.
- **P1:** nothing is pulsed, modulated or used as a contact signal. With no
  pan the offset is 1.6 K; firmware must not read it as contact evidence,
  because that is Impulse dependent claim 3 and its spec.
- **Fault cycle:** the MAX31865 fault-detection cycle opens FORCE− and stops
  conversions. It runs only at power-up and when the coil is off.

## D8. Cable and connector

**Cable.** R31's "SAB TD 801 F 4 × AWG28" is replaced. Distributor listings
for TD 801 F disagree on its rating (150, 180 and 200 °C), and it has four
cores. The harness is now **Alpha Wire 55493** (Xtra-Guard 5):
- 3 pairs × 24 AWG, FEP insulation and FEP jacket, foil shield;
- 300 V, −80 to +200 °C;
- UL AWM 20229 (rating source: Alpha Wire listing, read through a
  distributor);
- **the outer diameter is open:** confirm it against the 2.3 mm R31 route
  allowance;
- **drain:** at the controller only, on new J12.3.

**Inside the cartridge:** the M22759/12 pigtail and the manganin leads
(table at the top of this file).

**Pairs.** (S+, S−), (F+, F−), (NTC, NTC return). This departs from the
handoff's F+/S+ pairing. The sense loop is what reads magnetic EMF one to
one, so its two conductors are paired. The force loop is attenuated by
R_rtd/R_loop.

**Inline connector.** Molex Micro-Fit 3.0, 6 ways:
- 43025-0600 receptacle (female, recessed) on the harness side, the side a
  user can touch;
- 43020-0600 plug on the cartridge pigtail;
- −40 to +105 °C;
- gold 43030/43031-series crimps for the chosen AWG; the harness maker
  picks the terminal part number.

The controller keeps J3 (4-pin XH) and J12 (now 3-pin XH).

## D9. Deviations from the handoff text

| Handoff | Done | Why |
|---|---|---|
| Item 5: choose an ADS1115 | Kept the captured GPIO9 ADC1 channel | ADC1 is not full since C27; the sensor's B tolerance dominates (D5) |
| Item 6: low-capacitance TVS + series R on all 6 lines | TVS on all 6 lines; series R on the sense lines only; 220 nF X7R per RTD pin | A series R in the force loop moves the runaway trip; capacitance doesn't matter on DC lines |
| Item 9: twisted pairs F+/S+, F−/S− | S+/S−, F+/F− | Magnetic EMF in the sense loop reads directly |
| Constantan leads | Manganin leads | Thermo-EMF vs Cu ~25× lower: 0.004 K vs 0.092 K at a 2 K splice difference |
| Item 2: DRDY to the MCU | DRDY stays on the TCA9555 (C23 took the GPIO); firmware reads every 20 ms with stale-data detection | No free GPIO; the rate is ≥ 56.8 Hz either way |

## D10. Not done here

- **No edits to the controller sources:** the change request goes to their
  owner.
- **Not run against the controller board:** the RTD block validator
  (`zapote-rtd`) must be re-run on the new block, and its 36-part census
  changes.
- **No heater or pulse driver** was laid out (P1).

## CAD interface check

`cad/DECISIONS.md` did not exist when this file was written, so there was no
"Interface changes for PCB/firmware" note to reconcile. I read the CAD
working files and found two items.

**Agreements.** `cad/cartridge_r3.py` already uses:
- four manganin Ø0.08 leads;
- a Kelvin splice, each IST Ni lead to two manganin wires, at one height
  (agrees with item 9);
- a Ø2.6 cable through the body.

**Conflict 1: lead insulation.** CAD specifies polyimide enamel of the
MW 16-C class, rated 240 °C, on the manganin. That is below the 260 °C pan
and below the ≥ 300 °C / ≥ 10 MΩ requirement above (fault check).
- The chip-end leads sit at disc temperature.
- **Request to CAD:** glass-fibre sleeving, or separate bores, over the hot
  length. Otherwise show from `thermal_axisym.py` that the enamel stays
  ≤ 240 °C, and that leakage stays ≥ 10 MΩ at the worst case.

**Conflict 2: eye air temperature.** CAD's `thermal-axisym.json` puts the eye
air at 130–140 °C (winding 148–160 °C).
- The pigtail (260 °C) and the harness (200 °C) are fine there.
- **The inline Micro-Fit (105 °C) must sit outside the eye,** where the local
  air is ≤ 85 °C.
- If no such location is within reach from above, the fallback is a
  ≥ 150 °C connector class (Harwin Gecko / Datamate). That is open.

## Orchestrator rulings on CAD interface changes (2026-10-15)

- **Accept CAD I2 (straight lead pairs in the capillary).** S+/S− and F+/F− run
  untwisted for 10.3 mm in adjacent bores of the 4-bore capillary.
  - Modelled pickup is about 0.31 mV at 20 mT / 100 kHz
    (`cad/field-screen.json` `capillary_pair_pickup`), against this folder's
    6.6 mV twisted bound: about 21× margin.
  - Below the capillary, the twist at ≤ 5 mm pitch is unchanged.
- **Conflict 1 (lead insulation) resolved by CAD.** CAD fitted a fused-silica
  4-bore capillary, one bare manganin wire per bore: about 100 MΩ at 350 °C.
  The enamel is used only where it stays ≤ 211 °C. This meets the
  ≥ 10 MΩ at 300 °C requirement, pending supplier confirmation of the
  capillary (alternate: alumina).
- **Conflict 2 (connector temperature) answered by CAD.** CAD placed the
  Micro-Fit outside the coil eye, 35.4 mm from the nearest tank part. The
  ≤ 50 °C air there is carried over from R43 airflow evidence and needs a
  bench check, so the ≥ 150 °C connector fallback stays open until then.
