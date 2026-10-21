# Characterizing the cal kit with a borrowed 6½-digit DMM

The meter's accuracy depends on how well its resistor standards are known **as a ratio**. `../validation/virtual-instrument/README.md` §2 sets the requirement: know the 20 Ω / 100 Ω ratio to **≤ 0.03 %**. Marked ±0.1 % values with opposite-sign errors (a 0.2 % ratio error) leave −16.5 mΩ on coil R at 60 kHz and about 1×10⁻³ of false tan δ. The error scales with the ratio error, so 0.03 % gives about 2.5 mΩ.

This procedure gets the ratio to about **0.004 % (k = 2)**, about seven times inside that requirement. The absolute values come out at the DMM's own accuracy. That is enough: an error common to both standards scales every corrected impedance by the same factor. 0.01 % in L, C or R is negligible against the ±0.5–2 % targets.

## 1. What the host does with the numbers

Rev E's host reads the characterized values from a **standards file** (`--standards=KIT.json`). Name the standards on the command line; the short is always the entry `SHORT`:

```sh
temper-lcr calibrate short.json r1.json R1 r3.json R3 cal-100.json --standards=kit-SN03.json
temper-lcr validate  r2.json cal-100.json R2 0.1 --standards=kit-SN03.json
```

```json
{
  "schema": "temper-lcr-standards-1",
  "kit": "calkit-r2 SN03, DMM 34465A MY123 cal 2026-08, 2026-10-21",
  "temperature_c": 23.1,
  "standards": {
    "SHORT": {"r_ohm": 0.0, "l_h": 1.5e-9},
    "R1":  {"r_ohm": 20.00412,  "l_h": 1.5e-9, "c_f": 0.2e-12},
    "R2":  {"r_ohm": 51.00876,  "l_h": 1.5e-9, "c_f": 0.2e-12},
    "R3":  {"r_ohm": 100.01327, "l_h": 1.5e-9, "c_f": 0.2e-12},
    "R7":  {"r_ohm": 20001.6,   "l_h": 1.5e-9, "c_f": 0.2e-12},
    "R9":  {"r_ohm": 99987.2,   "l_h": 1.5e-9, "c_f": 0.2e-12},
    "R11": {"r_ohm": 1000312.0, "l_h": 1.5e-9, "c_f": 0.2e-12}
  }
}
```

- **Model.** Each standard is `r_ohm` in series with `l_h`, and the pair is shunted by `c_f`.
  - `l_h` and `c_f` default to 0. The file refuses unknown fields and values outside |l_h| ≤ 1 mH and 0 ≤ c_f ≤ 1 µF; those limits catch unit slips such as nH typed as H.
  - `calibrate_e_standards` (`host/src/rev_e.rs`) fits `measured = (a·true + b)/(c·true + 1)` at every frequency through the three complex impedances. So the short's inductance and the resistors' capacitance are not mistaken for fixture error.
  - The calibration file records the values used (`standards`) and the kit string (`standards_kit`).
- **Where the numbers come from.**
  - `r_ohm` comes from the DMM procedure below.
  - `l_h` and `c_f` need one measurement of the kit on a reference LCR meter or VNA, at the highest frequency you will use: each τ = L/R − RC, read from its phase (§5).
  - Until that is done, enter the §5 ESTIMATES (1.5 nH, 0.2 pF). They remove the nominal parasitic, but the residual is then the ESTIMATE's own uncertainty, so keep the 100 kΩ range at ≤ 10 kHz.
- **Without `--standards`.** The numeric form still works: `calibrate … LOAD1_OHM … LOAD2_OHM`. It assumes an exact 0 Ω short and purely real resistors.
- **The OPEN is not a calibration standard.** The host README calls it an overload/leakage diagnostic only.
- **Reactive check standards.** `validate` with `--standards` compares against the named standard's complex impedance, but the file holds R/L/C standards only. Check C1, C2–C6 and L1 by running `analyze` and comparing C, L and tan δ with §6 by hand.
- **Fixture string.** Use the same `FIXTURE` string for every capture in a calibration, for example `calkit-r2-SN03`. The host refuses mixed fixtures.

| Meter range | `calibrate` LOAD1 / LOAD2 | `validate` | Card rows |
|---|---|---|---|
| 100 Ω | R1 (20 Ω) / R3 (100 Ω) | R2 (51 Ω) | SHORT, R1, R2, R3 |
| 5 kΩ | R4 (1 kΩ) / R6 (4.99 kΩ) | R5 (2 kΩ) | SHORT, R4, R5, R6 |
| 100 kΩ, up to 100 kΩ DUTs | R7 (20 kΩ) / R9 (100 kΩ) | R8 (49.9 kΩ) | SHORT, R7, R8, R9 (≤ 10 kHz without characterized c_f, §5) |
| 100 kΩ, DUTs above 100 kΩ | R7 (20 kΩ) / R11 (1 MΩ) | R9 (100 kΩ) | SHORT, R7, R9, R11 (needs `--standards`) |

The accuracy map ([../validation/rev-e-accuracy-map](../validation/rev-e-accuracy-map/README.md) §3) gives what each row buys. Calibrating with R11 instead of R9 takes 1 MΩ at 1 kHz from 0.40/0.56 % to 0.064/0.12 %, and leaves 100 kΩ at 0.031/0.097 %. Characterized `c_f` takes 100 kΩ at 85 kHz from 1.2/1.0 % to 0.42/0.22 %.

Enter every digit the DMM gives. Do not round to the marking.

## 2. Equipment

- A 6½-digit DMM with 4-wire ohms and **offset compensation** (OCOMP). Examples are Keysight 34461A/34465A, Keithley DMM6500 and R&S HMC8012 (6½-digit mode). Note its calibration date.
- A 4-wire Kelvin clip lead set with banana plugs. Alternatively, use the meter's own 4-terminal BNC Kelvin leads with BNC-to-banana adapters: Hcur → INPUT HI, Hpot → SENSE HI, Lpot → SENSE LO, Lcur → INPUT LO. Either jaw of a clip may be force or sense, because the card's two faces are separate paths (README).
- A thermometer resolving 0.1 °C, with its probe taped to the card spine on the back, next to the row being measured. A thermocouple on the DMM is fine. Also record room temperature.
- A non-metallic surface. Keep L1 away from steel.

## 3. Setup

1. Let the card and the DMM sit in the room for **≥ 60 min**, the DMM powered on. Handle the card by its header and footer only. A finger near a standard warms it by more than 1 °C.
2. Set the DMM to 4-wire Ω, **OCOMP on**, autozero on, **NPLC 10** (or 100), and **fixed range** (see the table below). Turn on the digital filter only if it is a plain moving average.
3. Clip H on the left tab and L on the right tab, fully onto the gold, and wait **30 s** before reading. Clipping makes a thermal EMF transient; OCOMP removes its steady part.

| Rows | DMM range | Test current (typical) | Why |
|---|---|---|---|
| SHORT, R1, R2, R3 | 100 Ω | 1 mA | One range: gain error cancels in the ratio |
| SHORT, R4, R5, R6 | 10 kΩ | 100 µA | Same; 1 kΩ is 10 % of range, so null the offset with the SHORT |
| SHORT, R7, R8, R9 | 100 kΩ (or 1 MΩ if 100 kΩ over-ranges) | 10 µA | Same; average 4× more (noise) |
| R11 | 1 MΩ (2-wire is fine: 0.1 Ω of lead is 10⁻⁷) | 5 µA (typical) | A different range from R7: the ratio carries the DMM's range-to-range transfer error (ESTIMATE 20–50 ppm). Clean flux off the row first; surface leakage is in parallel |
| L1 (DC resistance only) | 100 Ω | 1 mA | Null with the SHORT; expect ≈ 63 mΩ |

Self-heating is negligible: 1 mA in 100 Ω is 0.1 mW.

## 4. Sequence and number of readings

For each range group, run an **ABBA sequence**. Each letter is one clip-on with **10 readings** averaged:

```
SHORT  STD1  STD2  CHECK  CHECK  STD2  STD1  SHORT      (one cycle; repeat 3 cycles)
```

Each standard gets 6 clip-ons × 10 readings = 60 readings, plus 6 SHORT clip-ons. A cycle takes about 5 minutes at NPLC 10. Record card temperature at the start and end of each cycle.

Reduction:

1. Subtract the mean SHORT reading of that cycle from every reading in the cycle. The card's SHORT has coincident sense points, so its true value is 0 Ω. Its reading is the DMM offset plus the leads' thermal EMF residual.
2. Take the mean of each standard's 6 clip-on means. Use the standard deviation of those 6 means ÷ √6 as the repeatability term. Clip-on to clip-on scatter includes contact effects, which the Kelvin tabs should hold below 1 ppm.
3. Ratio: r = R3/R1 (and R6/R4, R9/R7). The ABBA order cancels linear drift.
4. **Accept** the set when the ABBA halves agree to ≤ 5 ppm and card temperature moved ≤ 0.3 °C. Otherwise repeat.
5. Write each value and the card temperature on the back of the card (write-in fields: `R3 = ____ @ __ °C`). Keep the full record (DMM model, serial, calibration date, NPLC, readings) next to the calibration files. Put the values into the standards file (§1); keep the CSV (`row,ref,value_ohm,u_ohm_k2,card_c,date,dmm`) as the record behind it.

## 5. Uncertainty

Ratio budget for R1/R3, 100 Ω range, standard uncertainties (k = 1). Datasheet-dependent lines are marked ESTIMATE. Replace them with your DMM's numbers.

| Term | Size | Note |
|---|---|---|
| DMM gain (% of reading) | cancels | Same range, same current, minutes apart |
| DMM offset (% of range, ~3 mΩ on 100 Ω) | ≈ 1 ppm of R1 after the SHORT null | Without the null it is ~150 ppm of 20 Ω (0.015 %), half the requirement |
| DMM linearity, 100 Ω range | ≤ 10 ppm of R1 (ESTIMATE, ~2 ppm of range) | Spec-sheet "linearity" or "transfer accuracy" line |
| Noise, 60 readings at NPLC 10 | ≤ 2 ppm | Measured: std of the clip-on means ÷ √6 |
| Thermal EMF | ≤ 2 ppm | OCOMP plus the 30 s wait; 1 µV over 20 mV |
| Temperature: 1 °C between characterization and use, TCR ≤ 10 ppm/°C each, opposite signs worst case | 12 ppm (rectangular, 20/√3) | Recharacterize, or keep the card within ±1 °C of the recorded temperature |
| Drift between characterization and use (thin film at µW) | ≤ 10 ppm per 6 months (ESTIMATE) | Recharacterize every 6 months and before a measurement campaign |
| **Combined (k = 1)** | **≈ 19 ppm** | |
| **Expanded (k = 2)** | **≈ 0.004 %** | Requirement ≤ 0.03 % |

This ratio error leaves about 0.3 mΩ on coil R (16.5 mΩ × 0.004/0.2), against the ±20 mΩ target. The same budget holds for the 5 kΩ and 100 kΩ groups, with more averaging on 100 kΩ.

**Absolute value** = DMM accuracy: the 24-hour or 1-year % of reading spec, typically 0.003–0.01 % on a calibrated 6½-digit DMM. It only scales all results.

**Reactive parasitics** (ESTIMATE: 0805 thin film ~1 nH series, ~0.2 pF shunt including lands and card). Enter them as `l_h` and `c_f` in the standards file (§1). Without the file the host takes the standards as real. The phase of each standard is ωτ, with τ = L/R − RC:

| Standard | 1.5 kHz | 60 kHz | 100 kHz |
|---|---|---|---|
| R1 20 Ω | 5×10⁻⁷ | 2×10⁻⁵ | 3×10⁻⁵ |
| R3 100 Ω | ≪10⁻⁶ | 4×10⁻⁶ | 6×10⁻⁶ |
| R6 4.99 kΩ | 9×10⁻⁶ | 4×10⁻⁴ | 6×10⁻⁴ |
| R9 100 kΩ | 2×10⁻⁴ | 8×10⁻³ | 1.3×10⁻² |
| R11 1 MΩ | 1.9×10⁻³ | 7.5×10⁻² | 0.13 |

The 100 Ω range's standards are effectively real across 1.5–100 kHz. Their phase sits 1–2 orders below the 3×10⁻⁴ tan δ resolution.

- **With ESTIMATE or no `c_f`, calibrate the 100 kΩ range at ≤ 10 kHz** (phase ≤ 1.3×10⁻³ on R9). The host README already recommends ≤ 10 kHz for that range.
- **R11's phase is not small at any useful frequency.** Use it only with `c_f` in the file. Its value from a reference-meter measurement sets the high-|Z| phase accuracy: 0.05 pF of residual is 3×10⁻⁴ rad at 1 kHz and 1.9×10⁻² rad at 60 kHz.

## 6. Reactive check standards: what to expect

The DMM cannot characterize these to better than their markings. They check the meter, not the reverse.

- **C1 (100 nF) and C2–C6 (0.5 µF bank), C0G ±1 %.** C must read within ±1 % of nominal (C0G's ±30 ppm/°C and the < 1 pF card stray are negligible against 1 %). C0G is rated at tan δ ≤ 1×10⁻³ (Q ≥ 1000 at 1 kHz; confirm in the Murata datasheet); real parts are far lower. The meter should read tan δ between about −3×10⁻⁴ and +1×10⁻³ at 35–60 kHz. A negative tan δ beyond −3×10⁻⁴, or one above 1×10⁻³, means the phase calibration is wrong. This is the low-loss phase check §2 of the virtual-instrument README asks for. For a sharper expected value, look up the part's ESR at the test frequency in Murata SimSurfing (open item). The bank's anti-parallel rails subtract about 0.3 mΩ at the sense points (README), about −5×10⁻⁵ in tan δ at 50 kHz.
- **L1 (47 µH ±20 %, TDK SLF12575T-470M2R7-PF).** This is a transfer standard, not a reference. Its DC resistance (≈ 63 mΩ) is measurable on the DMM's 100 Ω range after the SHORT null. The meter's R at 35–60 kHz must be **≥ DCR**: it adds winding proximity loss and core loss, and is never below DC. L must sit within the ±20 % tolerance. Its real value is only known if L1 is measured once on a reference LCR meter, then tracked for drift. Ferrite L moves by roughly 0.1–0.5 %/10 °C (ESTIMATE), so log temperature.
- **9 µF bus capacitor at 1–1.5 kHz: not on the card.** The largest C0G MLCC found in JLC stock on 2026-10-21 was 100 nF, so about 90 in parallel would be needed. Check 9 µF with a characterized film capacitor (for example a 10 µF polypropylene box capacitor) clipped directly. The host README validates it at 1.5 kHz (−j11.8 Ω).
