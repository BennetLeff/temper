# Rev E improvements: how far four changes close the gap to a bench LCR meter

This study asks how much four planned changes improve the accuracy of the Rev E LCR meter on the Temper induction-cooker targets, and how the result compares with commercial bench meters. The four changes are:

1. a characterized calibration kit;
2. four-terminal (Kelvin) coax leads;
3. an internal 1 kΩ reference check;
4. a 375 kHz codec rate.

The same model over all three ranges, 10 mΩ–10 MΩ and 50 Hz–85 kHz, is in [rev-e-accuracy-map](../rev-e-accuracy-map/README.md).

**Everything here is simulation.** No Rev E board exists. Values marked ESTIMATE are not from datasheets, and the verdicts depend on them. Section 4 gives each one's sensitivity so the results can be rescaled.

## 1. Results

E = |bias| + 2σ at the worst test frequency of each target, through the host's three-standard calibration, as in [the VI README](../virtual-instrument/README.md).
- **Typical** uses random draws: 20 kits × 5 calibrations × 4 repeats.
- **Corner** uses deterministic worst patterns: 8 × 5 × 4.

Monte Carlo spread between seeds is about ±15 % (seeds 7–10).

### 1.1 Each improvement on its own, and all four together (E typical / E corner)

| Target | Tolerance | Baseline Rev E | 1 Kit | 2 Kelvin | 3 Ref check | 4 375 kHz | All four |
|---|---:|---:|---:|---:|---:|---:|---:|
| Coil L, no pan | 1 % | 0.17 / 0.33 % | 0.04 / 0.19 % | 0.17 / 0.29 % | 0.17 / 0.27 % | 0.17 / 0.33 % | 0.03 / 0.10 % |
| **Coil R, no pan** | 20 mΩ | **19.0 / 40.4** | 17.3 / 30.0 | 14.1 / 48.3 | 20.9 / 48.5 | 19.0 / 40.6 | **20.3 / 26.4** |
| Coil L, pan | 0.5 % | 0.17 / 0.33 % | 0.06 / 0.20 % | 0.16 / 0.28 % | 0.16 / 0.26 % | 0.17 / 0.33 % | 0.04 / 0.12 % |
| Coil R, pan | 5 % | 0.43 / 1.48 % | 0.40 / 1.37 % | 0.39 / 1.58 % | 0.45 / 1.52 % | 0.43 / 1.49 % | 0.48 / 1.21 % |
| Coil L, low-R pan | 0.5 % | 0.17 / 0.33 % | 0.05 / 0.19 % | 0.17 / 0.29 % | 0.17 / 0.26 % | 0.17 / 0.33 % | 0.03 / 0.11 % |
| Coil R, low-R pan | 5 % | 1.31 / 3.46 % | 1.20 / 3.17 % | 0.97 / 3.80 % | 1.44 / 3.77 % | 1.31 / 3.47 % | 1.45 / 2.74 % |
| 100 nF C | 1 % | 0.17 / 0.30 % | 0.05 / 0.15 % | 0.17 / 0.30 % | 0.17 / 0.23 % | 0.17 / 0.30 % | 0.02 / 0.11 % |
| **100 nF tan δ** | 1e-3 | **9.3e-4 / 2.2e-3** | 5.7e-4 / 1.3e-3 | 9.0e-4 / 1.9e-3 | 9.3e-4 / 1.9e-3 | 9.3e-4 / 2.2e-3 | **7.0e-4 / 2.0e-3** |
| 0.5 µF bank C | 1 % | 0.21 / 0.27 % | 0.14 / 0.16 % | 0.18 / 0.31 % | 0.21 / 0.21 % | 0.21 / 0.27 % | 0.05 / 0.13 % |
| **0.5 µF bank tan δ** | 1e-3 | **1.3e-3 / 6.3e-3** | 1.4e-3 / 5.0e-3 | 1.1e-3 / 6.2e-3 | 1.2e-3 / 6.0e-3 | 1.3e-3 / 6.3e-3 | **1.3e-3 / 5.8e-3** |
| 9 µF bus C, 1 kHz | 2 % | 0.14 / 0.31 % | 0.03 / 0.16 % | 0.14 / 0.29 % | 0.15 / 0.26 % | 0.14 / 0.31 % | 0.02 / 0.12 % |
| Tank f0, pan | 0.5 % | 0.023 / 0.027 % | 0.021 / 0.027 % | 0.008 / 0.011 % | 0.023 / 0.024 % | 0.023 / 0.030 % | 0.010 / 0.016 % |
| Tank Q, pan | 5 % | 0.35 / 1.61 % | 0.28 / 1.50 % | 0.34 / 1.63 % | 0.34 / 1.56 % | 0.35 / 1.61 % | 0.26 / 1.48 % |
| Tank f0, no pan | 0.5 % | 0.013 / 0.015 % | 0.014 / 0.016 % | 0.005 / 0.008 % | 0.013 / 0.015 % | 0.013 / 0.017 % | 0.005 / 0.010 % |
| **Tank Q, no pan** | 10 % | **3.8 / 16.0 %** | 3.7 / 17.3 % | 3.6 / 16.6 % | 3.8 / 16.4 % | 3.8 / 16.0 % | **3.4 / 17.5 %** |

Coil R values are in mΩ. Bold marks baseline and all-four entries that fail: E corner above the tolerance, or E typical within 7 % of it or above it.

### 1.2 Recommended configuration, and the bench meters (published accuracy)

| Target | Tolerance | All four + session procedure (`rec`) | Same, 10× capture (`rec10`) | GW LCR-6100, 0 m fixture | GW LCR-6100, 1 m leads | B&K 891 |
|---|---:|---:|---:|---:|---:|---:|
| Coil L, no pan | 1 % | 0.03 / 0.10 % | 0.03 / 0.09 % | 0.14 % | 0.88 % | 1.0 % |
| Coil R, no pan | 20 mΩ | **4.7 / 8.6 mΩ** | **3.3 / 3.8 mΩ** | 26 mΩ | 220 mΩ | 250 mΩ |
| Coil L, pan | 0.5 % | 0.04 / 0.09 % | 0.03 / 0.09 % | 0.15 % | 0.90 % | 1.03 % |
| Coil R, pan | 5 % | 0.11 / 0.21 % | 0.07 / 0.12 % | 0.73 % | 5.6 % | 5.5 % |
| Coil L, low-R pan | 0.5 % | 0.03 / 0.09 % | 0.03 / 0.09 % | 0.14 % | 0.88 % | 1.0 % |
| Coil R, low-R pan | 5 % | 0.33 / 0.59 % | 0.23 / 0.28 % | 1.9 % | 15 % | 17 % |
| 100 nF C | 1 % | 0.03 / 0.11 % | 0.02 / 0.10 % | 0.13 % | 0.88 % | 1.0 % |
| 100 nF tan δ | 1e-3 | 1.6e-4 / 2.5e-4 | 1.0e-4 / 1.0e-4 | 1.3e-3 | 8.8e-3 | 1.0e-2 |
| 0.5 µF bank C | 1 % | 0.05 / 0.14 % | 0.04 / 0.13 % | 0.14 % | 0.90 % | 1.0 % |
| 0.5 µF bank tan δ | 1e-3 | 2.8e-4 / 4.7e-4 | 1.3e-4 / 1.4e-4 | 1.4e-3 | 9.0e-3 | 1.0e-2 |
| 9 µF bus C, 1 kHz | 2 % | 0.02 / 0.10 % | 0.02 / 0.10 % | 0.06 % | 0.09 % | 0.5 % |
| Tank f0, pan | 0.5 % | 0.009 / 0.015 % | 0.007 / 0.009 % | 0.022 % | 0.079 % | 0.12 % |
| Tank Q, pan | 5 % | 0.04 / 0.12 % | 0.02 / 0.09 % | 0.18 % | 0.64 % | 1.0 % |
| Tank f0, no pan | 0.5 % | 0.006 / 0.011 % | 0.004 / 0.006 % | 0.010 % | 0.012 % | 0.014 % |
| Tank Q, no pan | 10 % | 0.53 / 1.05 % | 0.19 / 0.45 % | 1.4 % | 1.8 % | 2.0 % |

**`rec`** is all four improvements plus two session procedures, neither of which adds hardware:
- run the reference check with the leads **unplugged**;
- **re-measure the Kelvin short at the start of each measurement session**.

**`rec10`** adds captures 10× longer than Rev D's (0.16–3.3 s per point), which on-device averaging allows.

The bench-meter columns are published accuracy limits, not |bias| + 2σ (section 5). They are a different kind of number, but both are meant to bound the error.

## 2. What each improvement buys

**1. Characterized kit (DMM ratio σ 0.01–0.02 % plus a C0G check standard).**
- It is the only change that moves L and C: 0.17 % → 0.04 % typical, 0.33 % → 0.19 % corner.
- Coil R and tan δ improve only partly (19.0 → 17.3 mΩ), because standards are no longer the largest R term once drift is modelled (§3).
- **1a, DMM only:** 14.5 / 29.6 mΩ.
- **1b, C0G check only:** 17.3 / 30.2 mΩ. The C0G check (10 nF, tan δ entered as 5×10⁻⁵, true value U(0, 1×10⁻⁴)) recovers the real ratio error between the standards (the "c" term), even with marking-only standards. It leaves the absolute L/C scale at the marking tolerance.
- With the kit, the residual standards term is mostly the **unknown series inductance of the standards** (1.5 ± 1 nH, ESTIMATE): 1.6 mΩ on coil R. A δL on the 20 Ω standard gives a false R of about X·ωδL/20 Ω on a reactive DUT (§4, S7).

**2. Kelvin coax leads.** The modelled effects:

| Effect | 2T baseline | 4T Kelvin |
|---|---:|---:|
| Contact change of 6 mΩ after calibration (S4) | 6.0 mΩ on coil R | ≤ 0.02 mΩ on any terminal |
| Lcur contact (only path left: B gain, Rc/(R_iso + Z_f) = 5×10⁻⁵) | — | 0.005 % on L |
| Lead C moved after calibration (S7), coil R | 100 pF + 20 %: 4.2 mΩ; 200 pF: 8.4 mΩ | coax + 1 %: 0.42 mΩ; + 3 %: 1.25 mΩ |
| Calibration-insertion loop or mutual L change, coil R | 10 nH: 5.9 mΩ | 2 nH: 1.2 mΩ |
| 1 kΩ CUR→POT resistors with Kelvin leads attached (S3) | — | ≤ 1×10⁻⁷ in tan δ, below 0.01 mΩ on coil R (negligible) |

- **Shielding does not remove the R_iso mechanism.** Coax moved by 20 % gives the same 8.3 mΩ as a loose wire. The gain comes only from coax C being geometrically stable, by ±1 % against ±20 %. That ±1 % is an ESTIMATE; it should be measured on the real cables.
- **On its own, 4T barely changes the totals:** 14.1 / 48.3 mΩ. Marked standards and the drift term below still dominate. The corner rises because the deterministic corner biases of different sources partly cancel in the baseline. Section 4 lists each term alone.
- **Cable capacitance on all four ports adds stray load** (about 100 pF per lead). Stability is being checked separately.

**3. Internal 1 kΩ reference check** (`S5`, `S1`).
- **Noise resolution.** One check resolves 1.4–2.5×10⁻⁵ (1σ, gain and phase) at 27–60 kHz, and 5.5×10⁻⁶ at 1 kHz, at Rev D capture times. That is 0.0014°, or 0.6 mΩ of coil R at 60 kHz.
- **What it corrects.** It removes pure ratio drift exactly. A 0.01° codec inter-channel phase drift costs 4.4 mΩ of coil R and 1.7×10⁻⁴ of tan δ uncorrected, and about 0 after the check.
- **Limit 1, gain.** The check's gain is limited by the reference's own TCR: 25 ppm/°C (ESTIMATE) × 5–15 °C = 1.3–3.8×10⁻⁴. That is about the same as the RF and R_iso drift it replaces. So correct phase, or use a ≤ 5 ppm/°C reference; correcting gain with a 25 ppm part buys nothing.
- **Limit 2, phase with leads attached.** With 2T leads attached, the loose LO lead's capacitance still diverts current through R_iso; a ±20 % change is 1.7×10⁻⁴ at 60 kHz. With the Kelvin leads plugged in but open, each pot coax hangs on its follower through the 1 kΩ CUR→POT resistor. A 1 % coax change then moves the check's phase by 2.9×10⁻⁴ at 60 kHz, 12× its noise. Run through the check, this becomes 15.8 mΩ of typical coil R error in the combined configuration. **With leads attached, improvement 3 makes coil R worse** (20.9 mΩ against 19.0).
  - Shorting Hcur→Hpot with the relay's second pole cuts this to 9×10⁻⁵ (`all_bp`: 9.4 mΩ typical, but 37 mΩ corner). The rest comes from Lpot through its own 1 kΩ.
  - Unplugging the leads for the check removes it.
- **What it cannot see.** Drift that is not a ratio: an offset or a parallel term. The largest modelled drift (§3) is an offset.

**4. 375 kHz codec rate. It buys nothing for Temper, and it does not raise the ceiling to 172 kHz.**
- **No accuracy change.** In wideband mode the noise density at the tone sets the fitted-phasor noise for a given capture time; it does not depend on the output rate. E is unchanged at typical. The corner assumes an extra 3 dB of unpublished noise.
- **Spur and image aliasing stays negligible at both rates.** The DAC image at fs − f0, aliased by the ADC decimation, is ≤ 2×10⁻⁹ in tan δ at 187.5 kHz and ≤ 1×10⁻⁸ at 375 kHz (`S6`). The 375 kHz linear-phase filters have less stop-band rejection (77.7/80 dB against 86.9/90.5 dB), but the image moves past the 295 kHz source pole.
- **The ceiling stays near 85–90 kHz** (datasheet):
  - TAC5112 "Input Signal Bandwidth: up to 192 kSPS 0.46·fS; > 192 kSPS 90 kHz" (`sources/rev-e/TAC5112.txt`, SLASF24A p10);
  - BW_MODE = 1 is "wide band-width (96 kHz mode)" (p134);
  - the ADC linear-phase passband at 384 k is 0.227·fs = 85 kHz (survey, T7-32).
- **Above 90 kHz** a per-frequency calibration could still remove the extra roll-off, at a noise cost the datasheet does not give. That is a bench item.
- **Firmware cost.** The PIO loop has 320 rather than 640 cycles per frame (209 used) and BCLK is 24 MHz, i.e. 5 system clocks per BCLK against the current 10.

## 3. What dominates

**Baseline (typical).** Coil R 19 mΩ, which is 95 % of the tolerance:

| Term | Coil R |
|---|---:|
| Standards | 11.0 mΩ |
| Lead C and loop movement | 13.4 mΩ |
| CH1 leg-mismatch drift | 6.5 mΩ |
| Noise | 2.1 mΩ |
| Contact | 1.6 mΩ |

At the corner, leg-mismatch drift alone reaches 38.6 mΩ.

**The leg-mismatch term is new in this study and specific to R_iso.** The LOW follower sits at V_LO ≈ I·R_iso, the common mode of codec CH1. A drift δ in the gain mismatch between CH1's two input legs puts δ·R_iso in series with the DUT.
- **Size:** 2.2 mΩ of coil R, 4×10⁻⁴ of bank tan δ and 1.4 % of unloaded-tank Q per 1×10⁻⁴ of mismatch (`S2`).
- **Sources:** the 0.1 % 1 kΩ divider resistors (25 ppm/°C each, ESTIMATE) and leg-to-leg differences in the drift of the codec's input impedance.
- **What removes it:** neither the kit, the Kelvin leads nor the reference check, because it is an offset. A **re-measured short at the start of each session** removes it: 6.3 → 0.01 mΩ typical, 36.6 → 0.07 mΩ corner.
  - Rev C, with no R_iso, does not have this term.
  - Ratio-tracking resistor networks for the four 1k/1k dividers would also reduce it.

**After all four improvements plus the two procedures (`rec`), at Rev D capture times:**
- **Coil R** (typical 4.7 mΩ): codec noise 3.3 mΩ, coax movement and fixture 2.3 mΩ, standard inductance 1.6 mΩ.
- **Bank tan δ** (2.8×10⁻⁴): noise.
- **Unloaded-tank Q** (0.53 %): noise.
- **L and C** (0.03 % typical, 0.09–0.14 % corner): DMM ratio uncertainty and the reference resistor's TCR (0.08 % corner).
- **With 10× captures (`rec10`):** coil R 3.3 / 3.8 mΩ, now set by standard inductance and coax movement. Tan δ is 1–1.4×10⁻⁴. Every target sits at ≤ 19 % of its tolerance at the corner. The baseline fails four targets at the corner (coil R, both tan δ, unloaded-tank Q) and bank tan δ at typical.

## 4. Sensitivities (`results/sensitivity.json`)

| Case | Coil R | Low-R pan R | 100 nF tan δ | Bank tan δ | Tank Q, no pan |
|---|---:|---:|---:|---:|---:|
| S1 codec phase drift 0.01°, baseline | 4.39 mΩ | 0.31 % | 1.7e-4 | 1.7e-4 | 0.008 % |
| S1 same, with reference check | < 0.01 mΩ | 0 | 4e-10 | 1e-10 | 0 |
| S2 CH1 leg-gain mismatch 1×10⁻⁴ (2T or 4T) | 2.19 mΩ | 0.24 % | 8.2e-5 | 4.1e-4 | 1.39 % |
| S4 2T contact +6 mΩ after calibration | 6.00 mΩ | 0.65 % | 2.3e-4 | 1.1e-3 | 3.6 % |
| S4 4T Lcur contact +6 mΩ (worst terminal) | 0.02 mΩ | 0.005 % | 1e-7 | 2e-8 | 0.005 % |
| S7 2T lead C 200 → 240 pF | 8.37 mΩ | 0.59 % | 3.3e-4 | 3.2e-4 | 0.007 % |
| S7 4T coax +1 % / +3 % / +20 % | 0.42 / 1.25 / 8.31 mΩ | 0.03 / 0.09 / 0.58 % | 1.7e-5 / 5.0e-5 / 3.3e-4 | 1.6e-5 / 5.0e-5 / 3.3e-4 | ≤ 0.001 % |
| S7 4T standard-insertion L +2 nH | 1.17 mΩ | 0.08 % | 4.7e-5 | 4.7e-5 | 0.001 % |
| S6 DAC-image alias, 187.5 / 375 kHz | < 0.01 mΩ | 0 | 2e-9 / 9e-9 | 2e-9 / 8e-9 | 0 |

**Reference check: what it can detect.** Values are 1σ per check at Rev D capture times (gain and phase are equal), with the systematic floors alongside.

| f | Noise | Open-lead movement, 2T ±20 % | 4T coax ±1 % | 4T ±1 %, Hcur–Hpot bypass | Rref TCR (gain only), 5 / 15 °C |
|---:|---:|---:|---:|---:|---:|
| 1 kHz | 5.5e-6 | 2.8e-6 | 4.9e-6 | 1.6e-6 | 1.3e-4 / 3.8e-4 |
| 35 kHz | 1.75e-5 | 9.7e-5 | 1.7e-4 | 5.4e-5 | same |
| 60 kHz | 2.5e-5 | 1.7e-4 | 2.9e-4 | 9.3e-5 | same |

- **Leads unplugged:** the check detects about 3σ = 7.5×10⁻⁵ rad (0.004°) of phase drift at 60 kHz. That is 1.9 mΩ of coil R.
- **Gain:** detection is TCR-limited at 1–4×10⁻⁴.
- **Relay:** contact repeatability of 1–10 mΩ (ESTIMATE) on 1 kΩ is 1×10⁻⁶ to 1×10⁻⁵, negligible. The TQ2SA datasheet gives 75 mΩ maximum initial and 28–38 mΩ measured, with a 30–48 mΩ band over 10⁵ operations.

## 5. Bench meters

Accuracy formulas, from the manuals, evaluated in `commercial.py`:
- **GW Instek LCR-6100.** LCR-6000 Series User Manual v1.07, §13.1–13.2, printed pp.136–142 ([gwinstek.com](https://www.gwinstek.com/en-US/products/downloadSeriesDownNew/10211/757)):
  - Ae = [A·Ar + (Ka + Kb + Kf)·100 + KL]·Kc %, with De = Ae/100 and Rs error = X·De.
  - A comes from the Fig. 13-1 region map, **read from a graph**. It is 0.05 only for 100 Hz–30 kHz and 15 Ω–312 kΩ, and 0.1 for 1.5 Ω and up to 100 kHz.
  - Ka = (1e-3/|Z|)(1 + 200/Vs).
  - Kf = 0.03 % off the open/short trim frequencies. 35 kHz and the tank resonances are not trim points.
  - KL = 2.5e-2·(1 + 0.5·f[kHz]) % for a 1 m cable.
- **B&K Precision 891.** User Manual §8, printed pp.75–81 ([bkprecision](https://bkpmedia.s3.amazonaws.com/downloads/manuals/en-us/891_manual.pdf)):
  - a |Z| × frequency table: 1 % for 1–100 Ω at 10–100 kHz; the 0.05 % applies only to 1–10 kΩ below 1 kHz;
  - D accuracy is ±Zae absolute;
  - R accuracy is X·Zae.

Both assume 1 Vrms, slow speed, 23 ± 5 °C and open/short correction. The 891's +1 displayed digit is ignored.

**How the numbers compare:**
- At Temper's points, "0.05 % basic" becomes 0.10–0.15 % for L and C on the LCR-6100 with a direct fixture.
- Its D accuracy is 1.0–1.4×10⁻³. That is 26 mΩ on the coil at 60 kHz, 130 % of the coil-R tolerance.
- The 891 is 7–10× worse on L and C (1 %), and its D spec (±0.01) is as large as the coil's whole D.
- With the LCR-6100's 1 m cable term, the bench spec fails coil R and both tan δ targets by 9–11×.

**Simulated Rev E against the bench specs:**
- **Baseline Rev E against the LCR-6100 (0 m):**
  - worse on L and C (0.17 % typical, 0.33 % corner, against 0.13–0.15 %), bus C (0.14 / 0.31 % against 0.06 %) and unloaded-tank Q (3.8 / 16 % against 1.4 %);
  - comparable on coil R (19 / 40 mΩ against 26 mΩ) and 100 nF tan δ (9.3×10⁻⁴ / 2.2×10⁻³ against 1.3×10⁻³).
- **Baseline against the 891:** better everywhere except unloaded-tank Q.
- **`rec` against the LCR-6100 (0 m):** better or equal on every target except 9 µF bus C at 1 kHz (0.02 / 0.10 % against 0.06 %). The margin is about 5× on coil R and tan δ, but only about 1.0–1.5× on L and C at the corner. `rec10` is the same picture, with bus C at 0.10 % corner.

**Caveats on this comparison:**
- **A spec is not a typical error.** Published accuracy is a guaranteed limit over the operating range and over units. A real LCR-6100 is usually several times better than its spec.
- **Different footing.** These E values are ESTIMATE-driven simulation of a board that does not exist.
- **What the comparison does show.** The spec structure is clear: generic bench meters do not specify the 1×10⁻³ ESR/D resolution that Temper's coil-R and tan δ targets need at 35–60 kHz, at 5–25 Ω. A tailored, per-frequency-calibrated instrument can plausibly reach it.
- **Test level.** The LCR-6100's Ka and Ar terms assume Vs = the 1 Vrms setting. If Vs means the voltage across a 5–10 Ω part, its error at the low-impedance points roughly doubles (0.2–0.3 %).

## 6. Method

**Network** (`revE_front.py`). Batched nodal analysis of the Rev E front end per docs/rev-e-front-end.md:
- 1.7 V peak behind R_src = 147 Ω (100 Ω RG + 47 Ω R104);
- the 2T J3 fixture, or the 4T fixture with four π-modelled coax leads and the 1 kΩ CUR→POT resistors;
- the 100 pF DUT_LO C0G, R_iso 22 Ω, and an ideal TIA virtual ground with Z_f = 100 Ω ∥ 100 pF;
- ideal followers;
- four codec input legs (1k/1k, 560 pF, 1 µF, 470 Ω, R_in 44 kΩ), CH1 = HIGH − LOW and CH2 = LOW − TIA.

Fixed core non-idealities are linear and calibrate out (VI README §2.5), so the model carries only what changes between calibration and measurement.

**Noise.** Codec ADC noise is taken exactly as `../rev-e-codec/noise_codec.py` does it: 91 dB to 85 kHz re 2 Vrms, −3 dB for CM_TOL. Each fitted phasor gets E|dP|² = 2S/T at Rev D capture times. The codec ADC is 100 % of the noise in that model.

**Calibration.** Each draw goes through the VI's verified host replica (`vi_model.cal_coeffs`, `correct`; agrees with the host binary to ~1e-11). The DUT library, targets and error metrics are `../virtual-instrument/summarize.py`, unchanged.

**Improvement models:**
- **Kit:** C0G correction by a real ratio ε on the 100 Ω standard, solved per frequency so that the check reads its entered tan δ.
- **Reference check:** Rref measured right after calibration and again at the start of each session. Raw DUT ratios are multiplied by the quotient.
- **Re-zero:** the session short replaces the offset term b.

**Cross-checks** (`validate.py`, `results/validation.json`):
- **Noise against `noise_codec.json`** (same topology, 23 points): median ratio 0.95, range 0.72–1.01.
  - At 60 kHz this model is 8 % lower, because its drive is 8 % higher.
  - At the unloaded-tank resonance it is 28 % lower, so the tank-Q noise share is somewhat optimistic.
- **Lead movement against the SPICE-based VI** (`lm_riso22_c200_to240`): coil R 8.32 against 8.32 mΩ, pan R 1.78 against 1.78 %, tan δ 3.33 against 3.35×10⁻⁴ and 3.32 against 3.50×10⁻⁴.
  - Terms below 1×10⁻⁵ do not match, because the VI's lead-move runs include noise at that level.

## 7. Assumptions (all constants at the top of `study.py`)

| Item | Typical | Corner | Basis |
|---|---|---|---|
| Marked standards (20 Ω, 100 Ω) | U(±0.1 %) each | +0.1 % / −0.1 % | Tolerance |
| DMM-characterized ratio | σ 0.01 % | ±0.02 % each (ratio 0.04 %) | Given |
| Standard series L | 1.5 ± 1 nH | 5 nH / 0 | ESTIMATE (VI) |
| Short residual, 2T / Kelvin | 0.3 mΩ + 2 nH / 0.05 mΩ + 2 nH | 2 mΩ + 5 nH / 0.3 mΩ + 5 nH | ESTIMATE |
| C0G check | 10 nF, tan δ U(0, 1e-4), entered 5e-5 | true 1e-4 | ESTIMATE |
| Contact per insertion | U(0, 2 mΩ) | U(0, 6 mΩ) | ESTIMATE (VI); 2T total, 4T per terminal |
| 2T lead C per terminal, movement | 100 pF, U(±20 %) every insertion | 200 pF, +20 % after calibration | ESTIMATE (VI) |
| 2T loop L | 400 nH ± 10 nH | +20 nH after calibration | ESTIMATE |
| Coax | 100 pF/m × 1 m, U(±1 %) every insertion | +3 % after calibration | ESTIMATE; ±20 % bracketed in S7 |
| 4T current → pot mutual L | 20 ± 2 nH | +5 nH | ESTIMATE |
| Lead R | 2T 30 mΩ; coax 35 mΩ | | ESTIMATE (fixed, calibrated) |
| ΔT between calibration and measurement | U(±5 °C) | 15 °C | ESTIMATE |
| TCs (/°C) | RF 25 ppm, R_iso 100 ppm, divider 1k 25 ppm each, C0G 30 ppm | Full value, random sign | ESTIMATE |
| Codec R_in drift, common / leg mismatch | U(±20 %) / σ 0.4 % (2 % of it) | +20 % / ±2 % pattern (10 %) | Common value given; mismatch ESTIMATE |
| X7R 1 µF drift, common / leg | U(±5 %) / σ 1 % | −15 % / −15 % on one leg | ESTIMATE (front-end doc case) |
| Codec inter-channel phase drift | 0 in E; S1 gives the cost per 0.01° | | Unpublished |
| Rref | 1 kΩ, 25 ppm/°C; relay 75 mΩ ± 1 mΩ | ±10 mΩ | ESTIMATE (repeatability) |
| Noise | Codec model ×1 | ×1.41 (CM_TOL 6 dB); 375 kHz ×1.41 more | ESTIMATE |
| Capture | Rev D times: 16–49 ms at 27–60 kHz, 328 ms at 1 kHz | | As ../rev-e-codec |

## 8. Limits

- **Not modelled:**
  - power-supply and mains spurs (`../power-spurs`);
  - codec gain compression;
  - TIA and follower loop dynamics, and their drift;
  - DUT nonlinearity;
  - the reference resistor's AC parasitics drifting;
  - capacitance between the HI and LO leads (estimated below 1×10⁻⁵ of tan δ for the coil);
  - humidity.
- **Inside every claim:** ESTIMATE values set the leg-mismatch drift, the coax movement and the standard inductance, and those now decide the coil-R and tan δ results. S2, S7 and the attribution in `results/summary.json` let them be rescaled when bench values exist. Measure them in this order:
  1. leg-to-leg drift (short re-measured over a warm-up);
  2. coax C repeatability;
  3. the standards' L.
- **Corner bias cancellation.** Corner patterns are deterministic biases with signs, and biases from different sources can partly cancel. A linear sum of the per-source corner E values is the conservative bound: baseline coil R 70.9 mΩ, all four 67.0 mΩ, `rec` 8.8 mΩ.
- **The 375 kHz conclusion rests on datasheet text.** The analog bandwidth above 90 kHz needs the EVM loopback already listed in the front-end doc.

## Reproduce

```sh
./rerun.sh     # ~10 s: validate.py, sensitivity.py, study.py, commercial.py -> results/
```

**Files:**
- `revE_front.py` — network and noise.
- `study.py` — Monte Carlo, configurations, assumptions and tables.
- `sensitivity.py` — S1–S7.
- `commercial.py` — bench-meter formulas.
- `validate.py` — cross-checks.
- `results/`:
  - `targets_E.csv` and `summary.json` (every configuration, plus per-source attribution for `base`, `all` and `rec`);
  - `sensitivity.json`, `commercial.json`, `validation.json`, `provenance.json`.

`../virtual-instrument` and `../rev-e-codec` are imported read-only.
