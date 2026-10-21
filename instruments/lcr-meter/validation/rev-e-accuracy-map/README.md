# Rev E accuracy map: |Z| × frequency on all three ranges

This study maps the Rev E meter's accuracy over 10 mΩ to 10 MΩ and 50 Hz to 85 kHz, in the same form as a bench meter's datasheet chart. It then compares the result with the GW Instek LCR-6100's published accuracy. The [improvements study](../rev-e-improvements/README.md) covered only the Temper targets on the 100 Ω range.

**Everything here is simulation.** No Rev E board exists. Values marked ESTIMATE are not from datasheets, and the high-|Z| and low-|Z| edges depend on them.

## 1. Method

- **Model.** The phasor Monte Carlo of `../rev-e-improvements` (`revE_front.py`, `study.py`): source, four-terminal coax fixture, the four codec input legs, drift between calibration and measurement, and codec noise. Everything goes through the host's three-standard calibration (`vi_model.cal_coeffs`/`correct`, a replica of the host). It is generalized to all three ranges:
  - range r: RG = R_F = r, with R104 (47 Ω) in series to DUT_HI, so the source resistance is r + 47 Ω. C104 (100 pF) is shared by all ranges. These match the board nets of R40/R41/R42 and R104.
  - standards per range: short + 20 Ω/100 Ω, 1 kΩ/4.99 kΩ, 20 kΩ/100 kΩ ([cal kit](../../calkit/README.md)), DMM-characterized.
- **Configuration.** The recommended setup from the improvements study:
  - four-terminal leads;
  - the reference check on the same range with the leads unplugged;
  - the short re-measured at the start of each session;
  - 187.5 kHz;
  - the host's default capture, the smallest whole number of periods summing to at least 0.25 s.
  
  It does not use the C0G phase check, which exists only for the 100 Ω range's reactive targets.
- **New error term: HI–LO clip stray.** C_HL is the stray capacitance across the DUT at the clips: 0.3 pF, with ±5 % random per insertion (typical) or +10 % after calibration (corner). ESTIMATE.
  - Calibration absorbs a fixed C_HL, because it is a linear fixture term. Only its variation from one insertion to the next is an error.
  - It matters only at high |Z|.
- **New error term: standard self-capacitance.** STD_C is 0.2 pF on every resistor standard, ESTIMATE. The study's `z_resistor` already had this value. The host takes only real-valued standards, so the meter reads STD_C as part of the DUT.
- **DUTs.** |Z| = 10 mΩ to 10 MΩ in half decades. Each |Z| is tried at three phases: resistive, inductive with Q = 100, and capacitive with D = 10⁻³. A cell reports the worst of the three, for |Z| error (%) and for phase error. For small D or 1/Q, the phase error is the D (tan δ) error.
- **Range.** The host has no autorange, so the operator picks a range. "Best range" is the one with the lowest typical |Z| error.
- **Frequencies.** 50, 100, 200 and 500 Hz; 1, 2, 5, 10, 20 and 50 kHz; 85 kHz.
  - The firmware's lowest tone is 45.8 Hz: the period can be at most 4096 samples at 187.5 kHz (`tone_for_hz`).
  - Its highest is 85 kHz, the limit of the codec path.
- **Error figure.** E = |bias| + 2σ.
  - Typical uses random draws: 20 kits × 5 calibrations × 4 repeats.
  - Corner uses the deterministic worst patterns of the improvements study.
  - **Above about 100 kΩ, typical can exceed corner.** The corner is a fixed shift after calibration, while typical carries random clip variation at every calibration insertion, and that variation is extrapolated. So every verdict below requires both typical and corner to pass.

## 2. Results

Full tables are in [results/tables.md](results/tables.md): |Z| error, phase error, best range, the LCR-6100 published figure, and the verdict per cell.

### 2.1 Where the meter is accurate

E is the worst of typical and corner, |Z| and phase. The phase limit is the same number in rad: 0.2 % corresponds to 2 mrad.

| \|Z\| | ≤ 0.2 % | ≤ 1 % |
|---|---|---|
| 10 mΩ | — | — |
| 31.6 mΩ | — | — |
| 100 mΩ | — | 50–10k Hz (8/11) |
| 316 mΩ | — | 50–50k Hz (10/11) |
| 1 Ω | 50–20k Hz (9/11) | 50–85k Hz (11/11) |
| 3.16 Ω | 50–85k Hz (11/11) | 50–85k Hz (11/11) |
| 10 Ω | 50–85k Hz (11/11) | 50–85k Hz (11/11) |
| 31.6 Ω | 50–85k Hz (11/11) | 50–85k Hz (11/11) |
| 100 Ω | 50–85k Hz (11/11) | 50–85k Hz (11/11) |
| 316 Ω | 50–85k Hz (11/11) | 50–85k Hz (11/11) |
| 1 kΩ | 50–85k Hz (11/11) | 50–85k Hz (11/11) |
| 3.16 kΩ | 50–85k Hz (11/11) | 50–85k Hz (11/11) |
| 10 kΩ | 50–85k Hz (11/11) | 50–85k Hz (11/11) |
| 31.6 kΩ | 50–20k Hz (9/11) | 50–85k Hz (11/11) |
| 100 kΩ | 50–5k Hz (7/11) | 50–50k Hz (10/11) |
| 316 kΩ | — | 50–20k Hz (9/11) |
| 1 MΩ | — | 50–5k Hz (7/11) |
| 3.16 MΩ | — | — |
| 10 MΩ | — | — |

- **Within 0.2 % at every frequency, 50 Hz–85 kHz:** 3.16 Ω to 10 kΩ, about 3.5 decades.
- **Within 1 % at every frequency:** 1 Ω to 31.6 kΩ.
- **Mid-band level:** about 0.02–0.03 % typical and 0.1 % corner. The corner is set by the DMM ratio error of the standards (0.04 %, opposite signs) and by drift.

### 2.2 Against the GW Instek LCR-6100 (published accuracy)

The LCR-6100 formula comes from `../rev-e-improvements/commercial.py` (its manual, ch. 13, at 1 Vrms and slow speed). Rev E runs at 1.7 V peak.
- ✓ means typical and corner, |Z| and phase, are all within the LCR-6100 spec.
- ~ means typical is within the spec and corner is not.
- ✗ means typical is outside the spec.

| Comparison | ✓ | ~ | ✗ |
|---|---:|---:|---:|
| LCR-6100 with 1 m leads (like for like: Rev E also uses 1 m coax) | 144 | 22 | 43 |
| LCR-6100 on its 0 m direct fixture | 80 | 75 | 54 |

Each comparison covers 209 cells (19 |Z| values × 11 frequencies).
- **1 m leads.** Rev E is within the spec (✓, or ~ at the 1 kHz trim point) from 10 mΩ to 100 kΩ up to 20 kHz, and from 316 mΩ to 31.6 kΩ up to 85 kHz.
  - It loses at ≤ 31.6 mΩ above 20 kHz.
  - It loses at 316 kΩ above 2 kHz, and from 1 MΩ up at every frequency.
- **0 m fixture.** In mid-band, Rev E's typical is better and its corner, about 0.1 %, is worse than the 0.05–0.09 % spec.
- **1 kHz column.** The 1 kHz cells show more ~ because 1 kHz is ASSUMED to be an LCR-6100 open/short trim frequency, which tightens its spec.

### 2.3 What sets the edges

Each column enables one error source at a time (`study.SOURCES`). Cells are E typical / corner in %, worst of the three phases.

| Range | f | \|Z\| | standards | contact | leads | drift_ratio | drift_leg | noise | all |
|---|---|---|---|---|---|---|---|---|---|
| 100 | 1k | 10 mΩ | 0.52 / 3 | 0.002 / 0.0068 | 0.22 / 0.001 | 0.0099 / 0.078 | 0.00066 / 0.0047 | 3.3 / 5 | 3.7 / 7.9 |
| 100 | 85k | 10 mΩ | 11 / 27 | 0.015 / 0.048 | 18 / 0.0071 | 0.0086 / 0.083 | 0.00057 / 0.0044 | 3.4 / 4.9 | 29 / 31 |
| 100 | 85k | 1 Ω | 0.13 / 0.3 | 0.0016 / 0.0055 | 0.18 / 0.0071 | 0.0086 / 0.083 | 0.00057 / 0.0044 | 0.034 / 0.049 | 0.29 / 0.38 |
| 100k | 85k | 100 kΩ | 1.1 / 1.1 | 0.00019 / 0.001 | 0.15 / 0.16 | 0.0089 / 0.079 | 0.00067 / 0.0045 | 0.026 / 0.035 | 1.2 / 1 |
| 100k | 1k | 1 MΩ | 0.39 / 0.5 | 0.00014 / 0.001 | 0.019 / 0.02 | 0.0076 / 0.082 | 0.00059 / 0.0046 | 0.029 / 0.039 | 0.4 / 0.56 |
| 100k | 85k | 1 MΩ | 12 / 12 | 0.00021 / 0.0014 | 1.5 / 1.6 | 0.01 / 0.09 | 0.00076 / 0.0052 | 0.13 / 0.2 | 14 / 10 |
| 100k | 1k | 10 MΩ | 4 / 5.1 | 0.00025 / 0.0014 | 0.19 / 0.19 | 0.0077 / 0.084 | 0.0006 / 0.0046 | 0.15 / 0.21 | 4 / 5.2 |

**Low |Z|, ≤ 0.3 Ω**
- **Noise.** At 1 kHz noise is 3.3 % of the 3.7 % error at 10 mΩ. The 100 Ω range's 147 Ω source limits the current to 11.6 mA, which puts 116 µV across 10 mΩ, and the codec has no analog gain.
- **The short's residual.** Its R (0.05/0.3 mΩ) and L (2/5 nH) are ESTIMATEs that the host assumes are zero.
- **Lead movement above 20 kHz.** The movement of the current-to-sense mutual inductance (±2/5 nH, ESTIMATE) dominates.

**High |Z|, ≥ 316 kΩ**
- **Calibration, not hardware.** Noise contributes only 0.03–0.2 %.
- **Extrapolation.** The standards stop at 100 kΩ, so their ratio errors and the calibration noise extrapolate as |Z|/100 kΩ. At 10 MΩ and 1 kHz that gives 4 %.
- **Self-capacitance above about 5 kHz.** The 0.2 pF the host cannot enter is 1.1 % of phase on the 100 kΩ standard at 85 kHz, and more on anything extrapolated from it.

**Low frequency.** The map shows no low-frequency degradation down to 50 Hz, because the reference check removes the drift of the coupling capacitors (§3, Vn). The 45.8 Hz firmware floor is the only limit at that end.

## 3. What would widen it

These variants are tested at the edges (`variants.py`). Cells are E typical / corner in %, worst of the three phases.

- **V0:** as §2.
- **Vn:** V0 without the per-session reference check.
- **V1:** the host takes characterized complex standards. Each standard's capacitance and the short's inductance are known to STD_C_RESID = 0.05 pF and SHORT_L_RESID = 0.5 nH (corner 1 nH). Both are ESTIMATEs: they need a measurement on a reference LCR meter or VNA.
- **V2:** V1 plus a characterized 1 MΩ standard, so the 100 kΩ range is calibrated with 20 kΩ and 1 MΩ.
- **V3:** V2 with 10× longer captures (2.5 s per point).

| Range | \|Z\| | f | V0 | Vn | V1 | V2 | V3 |
|---|---|---|---|---|---|---|---|
| 100 | 10 mΩ | 50 | 4.2 / 7.6 | 3.9 / 9 | 4.2 / 7.6 | 4.2 / 7.6 | 1.7 / 4.5 |
| 100 | 10 mΩ | 1k | 3.7 / 7.9 | 4 / 7.8 | 3.7 / 8 | 3.7 / 8 | 1.5 / 4.6 |
| 100 | 10 mΩ | 20k | 7.8 / 10 | 7.5 / 11 | 5.9 / 7.4 | 5.9 / 7.4 | 5 / 4.4 |
| 100 | 10 mΩ | 85k | 29 / 31 | 30 / 31 | 21 / 10 | 21 / 10 | 20 / 7 |
| 100 | 100 mΩ | 50 | 0.42 / 0.76 | 0.45 / 1.8 | 0.42 / 0.76 | 0.42 / 0.76 | 0.17 / 0.45 |
| 100 | 100 mΩ | 1k | 0.37 / 0.79 | 0.4 / 0.83 | 0.37 / 0.79 | 0.37 / 0.79 | 0.15 / 0.46 |
| 100 | 100 mΩ | 20k | 0.78 / 1 | 0.75 / 1.2 | 0.59 / 0.72 | 0.59 / 0.72 | 0.5 / 0.43 |
| 100 | 100 mΩ | 85k | 2.9 / 3.2 | 3 / 3.1 | 2.1 / 1 | 2.1 / 1 | 2 / 0.72 |
| 100 | 10 Ω | 50 | 0.022 / 0.098 | 0.21 / 1 | 0.022 / 0.098 | 0.022 / 0.098 | 0.022 / 0.098 |
| 100 | 10 Ω | 1k | 0.026 / 0.11 | 0.037 / 0.18 | 0.026 / 0.11 | 0.026 / 0.11 | 0.026 / 0.11 |
| 100 | 10 Ω | 20k | 0.026 / 0.1 | 0.036 / 0.18 | 0.024 / 0.1 | 0.024 / 0.1 | 0.023 / 0.1 |
| 100 | 10 Ω | 85k | 0.038 / 0.12 | 0.049 / 0.18 | 0.03 / 0.1 | 0.03 / 0.1 | 0.031 / 0.099 |
| 5k | 1 kΩ | 50 | 0.024 / 0.099 | 0.23 / 1.2 | 0.024 / 0.099 | 0.024 / 0.099 | 0.023 / 0.098 |
| 5k | 1 kΩ | 1k | 0.023 / 0.099 | 0.032 / 0.13 | 0.023 / 0.099 | 0.023 / 0.099 | 0.023 / 0.099 |
| 5k | 1 kΩ | 20k | 0.028 / 0.11 | 0.04 / 0.12 | 0.026 / 0.11 | 0.026 / 0.11 | 0.026 / 0.11 |
| 5k | 1 kΩ | 85k | 0.037 / 0.11 | 0.044 / 0.16 | 0.029 / 0.1 | 0.029 / 0.1 | 0.029 / 0.1 |
| 100k | 100 kΩ | 50 | 0.032 / 0.11 | 0.2 / 1.3 | 0.032 / 0.11 | 0.023 / 0.1 | 0.016 / 0.096 |
| 100k | 100 kΩ | 1k | 0.046 / 0.12 | 0.054 / 0.14 | 0.044 / 0.12 | 0.031 / 0.097 | 0.025 / 0.088 |
| 100k | 100 kΩ | 20k | 0.3 / 0.33 | 0.3 / 0.35 | 0.11 / 0.14 | 0.1 / 0.13 | 0.1 / 0.12 |
| 100k | 100 kΩ | 85k | 1.2 / 1 | 1.2 / 1.1 | 0.42 / 0.22 | 0.41 / 0.2 | 0.4 / 0.2 |
| 100k | 1 MΩ | 50 | 0.19 / 0.55 | 0.31 / 1.7 | 0.19 / 0.55 | 0.03 / 0.11 | 0.019 / 0.099 |
| 100k | 1 MΩ | 1k | 0.4 / 0.56 | 0.4 / 0.57 | 0.4 / 0.56 | 0.064 / 0.12 | 0.059 / 0.11 |
| 100k | 1 MΩ | 20k | 2.9 / 2.3 | 2.9 / 2.3 | 0.98 / 0.55 | 0.94 / 0.36 | 0.93 / 0.35 |
| 100k | 1 MΩ | 85k | 14 / 10 | 14 / 10 | 4.3 / 1.3 | 4.2 / 1.3 | 4.2 / 1.2 |
| 100k | 10 MΩ | 50 | 1.8 / 5.2 | 1.9 / 6.4 | 1.8 / 5.2 | 0.16 / 0.47 | 0.15 / 0.46 |
| 100k | 10 MΩ | 1k | 4 / 5.2 | 4 / 5.1 | 4 / 5.2 | 0.48 / 0.48 | 0.47 / 0.47 |
| 100k | 10 MΩ | 20k | 39 / 27 | 40 / 27 | 10 / 5.4 | 10 / 2.7 | 10 / 2.7 |
| 100k | 10 MΩ | 85k | 40499 / 1022 | 13994 / 1012 | 67 / 14 | 63 / 14 | 63 / 13 |

**What each change buys**

1. **Complex standards in the host (V1).** This is software only, plus one characterization of the kit on a reference meter. It is [calkit open item 5](../../calkit/README.md#open-questions).
   - At 100 kΩ, 85 kHz: from 1.2 / 1.0 % to 0.42 / 0.22 %.
   - At 1 MΩ, 85 kHz: from 14 / 10 % to 4.3 / 1.3 %.
   - At 10 mΩ, 85 kHz: the corner falls from 31 % to 10 %.
2. **A 1 MΩ standard (V2).** One more row on the cal kit.
   - At 1 MΩ, 1 kHz: from 0.40 / 0.56 % to 0.064 / 0.12 %.
   - At 10 MΩ, 1 kHz: from 4.0 / 5.2 % to 0.48 / 0.48 %.
   - At 100 kΩ it doesn't hurt: 0.031 / 0.097 % at 1 kHz.
3. **Longer captures (V3).** Firmware or host only. At 10 mΩ, 1 kHz: from 3.7 / 7.9 % to 1.5 / 4.6 %.
   - Going further at low |Z| needs more test current or analog gain on the voltage channel. That is a hardware change and was not simulated.
4. **What stays.** High |Z| at high frequency stays limited by the per-insertion HI–LO stray. At 10 MΩ and 20 kHz the error is still 10 % typical, because 0.015 pF of variation is an admittance ratio of about 2 × 10⁻² there. Going further needs a guarded fixture. The ESTIMATE ±5 % movement sets this number.
5. **The reference check is what makes 50 Hz work (Vn).** Without it, 10 Ω at 50 Hz is 0.21 / 1.0 %, against 0.022 / 0.098 % with it, because of the drift of the 1 µF X7R coupling capacitors. Below 45.8 Hz, the firmware would need periods longer than 4096 samples.
6. **Above 85 kHz.** This was not simulated. It needs a converter with more than the TAC5112's 90 kHz analog bandwidth ([front end](../../docs/rev-e-front-end.md)).

## 4. Assumptions and limits

| Quantity | Value | Basis |
|---|---|---|
| HI–LO clip stray C_HL | 0.3 pF | ESTIMATE |
| Its movement per insertion | ±5 % typ random / +10 % corner after calibration | ESTIMATE |
| Standard self-capacitance STD_C | 0.2 pF, uncorrected by the host | ESTIMATE (same as `study.z_resistor`) |
| Characterized residuals (V1) | 0.05 pF; short L 0.5 nH typ / 1 nH corner | ESTIMATE |
| Everything else | as `../rev-e-improvements` §4 | its README |

- **Noise.** Only codec noise is modelled. The 100 kΩ feedback resistor's Johnson noise is 41 nV/√Hz at the TIA, against about 550 nV/√Hz of codec noise referred to the same point, and the op-amp noise is lower still.
- **Relay contacts.** The range relay's contact resistance (28–75 mΩ, in series with R_F) is a calibrated gain term. Its drift is not modelled: at most 164 ppm of the 100 Ω range ([range switching §5](../../docs/rev-e-range-switching.md)).
- **Reference check level.** The reference check is at 1.7 V on every range. Host commit 758a51d50 fixed the default, which had been 863 mV on 5 kΩ and 43 mV on 100 kΩ.
- **Unsimulated cells.** Cells at 10 MΩ above 20 kHz reach 100–150 % on the best range. The model is still linear there, but the reading carries no information.
- **Commercial comparison.** The LCR-6100 figures are guaranteed specifications; Rev E's are simulated E values.

## 5. Files

| Path | What |
|---|---|
| `accuracy_map.py` | Map → `results/map.json`, `results/tables.md` |
| `attribution.py` | One error source at a time at the edges → `results/attribution.json` |
| `variants.py` | Host, kit and capture changes at the edges → `results/variants.json` |
| `rerun.sh` | All of the above plus `results/provenance.json` (about 15 s) |
