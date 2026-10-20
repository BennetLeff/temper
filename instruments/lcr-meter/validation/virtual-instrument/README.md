# Rev C virtual instrument: predicted accuracy before the PCB order

This directory builds a simulated Temper LCR Rev C (`C-local100p`). It produces bit-exact capture records for the **real host binary** and predicts whether the board can make the measurements the Temper induction-cooker project needs. Signal and noise transfers come from the validated full-chain SPICE deck (official TI models, true DC operating point, KLU). Records go through the committed host `temper-lcr` 0.4.0 (`calibrate`, `validate`, `analyze`), built from commit `ff1ffb45b` (`data/host-commit.txt`). The host sources are unchanged in `b886211a6`.

**Everything here is simulation.** The models are typical vendor macromodels at 27 °C. Requirements are **proposed**. Values marked ESTIMATE are not datasheet values. No board exists.

## 1. Verdicts (100 Ω range, proposed targets)

E = |bias| + 2σ over 7 boards × 5 calibrations × 3 repeats, run through the real host, at the worst test frequency. "Typical" uses realistic standards and fixture. "Corner" uses worst-case standards and fixture, DDS SNR at its 55 dB minimum, and amplifier noise ×1.5. A target **meets** when both E values are within the tolerance T. It is **marginal** when the typical E meets but the corner E does not. The spur column is a separate deterministic bound (§2.3) for an AD9833 spur at the −60 dBc datasheet SFDR, and at −80 dBc (ESTIMATE).

| Target | Proposed T | Why this tolerance | E typical | E corner | Spur bound −60 / −80 dBc | Verdict |
|---|---:|---|---:|---:|---:|---|
| Coil L, no pan, 35–60 kHz | ±1 % | Coil-spec §2 asks for an LCR meter with ≥ 1 % accuracy at 30–80 µH | 0.031 % | 0.16 % | 0.10 / 0.010 % | **meets** |
| Coil R_ac, no pan | ±20 mΩ | Row 5 limit curve 0.132/0.193/0.241 Ω at 20/40/60 kHz; ±10 % of the 40 kHz limit | 3.3 mΩ | 20.8 mΩ | 21 / 2.1 mΩ (50 kHz) | **marginal** |
| Coil L, reference pan (≈42 µH) | ±0.5 % | Row 3 floor is 41.5 µH; a nominal coil reads 41.95 µH, only 1.1 % above it | 0.029 % | 0.16 % | 0.14 / 0.014 % | **meets** |
| Coil R, reference pan (≈2.4 Ω) | ±5 % | Pan-reflected R sets delivered power; the r40 pan classes in coil_mc.rs are 30–50 % wide | 0.08 % | 0.53 % | 0.67 / 0.07 % | **meets** |
| Coil L / R, low-R pan class (≈1 Ω) | ±0.5 % / ±5 % | Same reasoning; lowest-R pan is the worst case | 0.030 % / 0.24 % | 0.16 % / 1.4 % | 0.06 / 0.86 % | **meets** |
| 100 nF capacitor C | ±1 % | Replaces the ±10 % (K) assumption in the f_res floor; 1 % in C is 0.5 % in f_res | 0.037 % | 0.15 % | 0.025 % | **meets** |
| 100 nF tan δ | ±1×10⁻³ | Gross-fault screen only: PP film ≲ 1e-3, X7R ≈ 2.5e-2 | 2.6e-4 | 1.22e-3 | 2.5e-4 | **marginal** |
| 0.5 µF bank C | ±1 % | As above | 0.048 % | 0.145 % | 0.024 % | **meets** |
| 0.5 µF bank tan δ (1e-3 = 6.4 mΩ ESR at 50 kHz) | ±1×10⁻³ | As above | 3.4e-4 | 1.30e-3 | 2.4e-4 | **marginal** |
| 9 µF bus capacitor C at 1 kHz | ±2 % | Capacitance check; film tolerance is 5–10 % | 0.034 % | 0.16 % | 0.08 % | **meets** |
| Tank f0 with pan (34.74 kHz), as a network | ±0.5 % | 10× inside the f ≥ 1.05·f_res ZVS guard | 0.003 % | 0.007 % | <1e-4 % | **meets** |
| Tank Q with pan (≈4) | ±5 % | Sets tank current per volt | 0.07 % | 0.35 % | <1e-3 % | **meets** |
| Tank f0 / Q, no pan (27.64 kHz, Q≈72) | ±0.5 % / ±10 % | Coil/capacitor loss screen | 0.002 % / 1.1 % | 0.005 % / 3.9 % | 0.07 % on Q | **meets** |

A realistic ESR/Q resolution is about 3×10⁻⁴ in tan δ with characterized standards. That is 8 mΩ on one 100 nF capacitor at 35 kHz and 2 mΩ on the bank at 60 kHz. It is about 1×10⁻³ with marked-only standards. Real polypropylene loss (tan δ ≈ 2×10⁻⁴, ESTIMATE) is therefore **not resolvable**. A degraded or wrong-dielectric part is. Measure the tank as a network at the calibrated frequency closest to f0. Its f0 and Q are far inside target because |Z| ≈ R at f0, and dX/df = 4πL is steep.

Host checks: the 47 Ω check standard passed `validate` at 1 % in 245 of 245 calibrations. The largest check error was 0.036 %. No `analyze` record was flagged invalid. The Python replica of the host fit and calibration agrees with the binary to 8.7×10⁻¹² relative on the same records.

## 2. Dominant error terms

1. **Errors in the resistor-standard values, as a ratio.** All three standards are real, so the bilinear correction maps value errors into the term c, which is real. For a reactive DUT, c turns into a false real part of about c·X². With ±0.1 % errors of opposite sign on the 20 Ω and 100 Ω standards (marking only), coil R at 60 kHz shows **−16.5 mΩ** and capacitor tan δ about 1×10⁻³. With standards characterized to σ = 0.02 % (ESTIMATE, DMM), the board-to-board spread from this term is 1.5 mΩ. This term sets every marginal verdict. **Requirement (proposed): know the 20 Ω/100 Ω ratio to ≤ 0.03 %, and validate phase with a low-loss reactive check standard.** Those are lab procedures, not PCB changes.
2. **Contact resistance per insertion** (ESTIMATE: U(0, 2 mΩ) typical, U(0, 6 mΩ) corner, two-terminal fixture): 0.6 mΩ repeatability typical, 1.7 mΩ corner. It enters R directly; the short subtracts only its own insertion.
3. **AD9833 spurs that alias onto f0** (`spur_alias.py`). Undersampling with fs/f0 a small rational folds low-order harmonics onto the measured tone: n = 9 and 11 at 50 kHz, n = 49 and 51 at 1 kHz. The DUT impedance at n·f0 differs from that at f0, so the error neither cancels in A/B nor calibrates out. At the −60 dBc datasheet SFDR bound this gives **21 mΩ** on coil R at 50 kHz. At −80 dBc it gives 2.1 mΩ. Using 49 kHz instead of 50 kHz cuts it below 0.01 mΩ. **Avoid test frequencies with fs/f0 a small rational.** This is a host/firmware grid choice.
4. **Electronic noise is negligible.** One capture's fitted |ΔZ/Z| is 2–10×10⁻⁶ for coils and capacitors (σ_R = σ_X ≈ 65 µΩ on the coil). The tank at resonance reaches 6×10⁻⁴, but |Z| there is only 0.16 Ω. With calibration noise included (perfect standards), E reaches at most 2.9 % of any tolerance (bank tan δ). The analytic budget matches the Monte Carlo repeatability within sampling error: median ratio 0.95, 5–95 % range 0.68–1.27, over 90 points.
   - **Per conversion, everything folds.** On the coil at 40 kHz, analog noise is σ_A 100 µV and σ_B 134 µV, with ρ ≈ 0. ADC thermal noise plus quantization adds 62 µV per channel. Total is about 0.95 LSB. For a matched 100 Ω DUT the channels correlate at ρ = +0.93 (85 µV each). The common noise is wideband AD9833 output, which cancels for resistive DUTs but not for reactive ones.
   - **Fitted-Z noise budget, coil at 40 kHz.** ADC 36 %, DDS 30 %, OPA810 gain stage 29 %, FDA A 3 %. For capacitors and the 9 µF bus capacitor, ADC 77–89 %. Full-scale use: A is 2–17 % and B 38–43 % at 35–60 kHz.
5. Board tolerances do not appear in the error. Six SPICE tolerance draws (RG/RF 0.1 %, CF 5 %, FDA network per BOM) plus ADC gain, offset and INL, and a 40 ps aperture mismatch, are all removed exactly by the per-frequency three-standard calibration. Any linear error in the chain is a bilinear map of Z.

## 3. What-ifs: PCB and firmware changes

Each what-if is rerun through the same chain with perfect standards and no contact resistance, so only noise remains. That isolates what each change buys. Ratios are noise-only E for the base board over E for the variant, from 16 calibrations × 3 repeats (`results/whatif.csv`; single-capture analytic values are in `whatif_analytic.csv`). Above 1 is better. **Base noise-only E is 0.05–2.9 % of the tolerance, so no what-if changes a verdict.**

| Change | Coil R / L, no pan | Coil L, pan | Bank C / tan δ | 9 µF C | Tank Q (pan / no pan) | Cost and risk |
|---|---:|---:|---:|---:|---:|---|
| (a) 33 Ω range with BUF634A, full drive (55 mA peak into a short) | 0.87 / 1.03 | 1.70 | 1.9 / 2.0 | 1.0 | 3.3 / 3.3 | New range, BUF634A on source and TIA, stability unqualified |
| (a′) 33 Ω range limited to 20 mA (drive ×0.37) | 0.28 / 0.50 | 0.83 | 0.70 / 0.68 | 0.34 | 1.4 / 1.6 | Worse for most targets |
| (b1) Both FDAs at gain 2 (R_in 499 Ω); never clips for a passive DUT | 1.6 / 1.5 | 1.5 | 1.9 / 1.9 | 1.8 | 1.5 / 1.4 | Eight resistors; FDA loop margin needs a recheck |
| (b2) Source ×2 (OPA810 gain 12) | 1.4 / 1.6 | 1.6 | 2.1 / 1.9 | 1.9 | 1.4 / 1.5 | 36 mA peak into a short, so BUF634A |
| (b3) Channel A gain 4 | 2.0 / 1.9 | 1.9 | 3.5 / 3.1 | 2.6 | 1.7 / 1.5 | Clips for \|Z\| > ~1.2·RG on any range |
| (c) On-chip boxcar at 1 MSPS (N = divider) | 0.84 / 1.8 | 2.0 | 1.2 / 1.2 | **6.2** | 1.6 / 1.9 | Firmware only; no gain at 60 kHz (divider 1). Spur alias bound ÷2.4 at 50 kHz, ÷49 at 1 kHz |
| (b1) + (c) | 1.5 / 2.5 | 2.7 | 2.2 / 2.2 | 10 | 2.3 / 2.5 | |
| (d) R_iso 22 Ω LO isolation (Rev D candidate) | 0.97 / 0.93 | 0.95 | 0.81 / 0.80 | 0.80 | 0.81 / 0.90 | See below |

Single-capture analytic values, worst frequency, coil R: base 71 µΩ; (a) 30; (b1) 60; (b3) 57; (c) 64, which is 42 µΩ at 35–50 kHz; (d) 85. Ratios of 0.8–1.0 for coil R under (c) are Monte Carlo sampling noise at 60 kHz, where boxcar changes nothing. The MC E values carry about ±20 % sampling uncertainty.

**(d) 22 Ω R_iso between J3 LO and the TIA summing node** (`fixture-envelope.md`; deck: X7A −IN, RF and CF on `sum`, `Risolo low sum 22`, LOW follower on `low`):
- **Less drive.** Voltage across the coil falls 18 % (A goes from 6.8 % to 5.6 % of full scale at 40 kHz). Fitted-Z noise rises 19 %, which is still negligible. B rises 0.5–10 % because B = I·(R_iso + RF‖CF). The short case still gives B equal to the source, so B clipping does not change.
- **Lead capacitance present during calibration.** With 100 or 200 pF on each DUT terminal, the three-standard calibration absorbs it. Noise-only E is unchanged within sampling (coil R 0.40 mΩ against 0.29 mΩ without leads).
- **Leads moved after calibration, C changed by ±20 %.** This bias is not removable. Rev C (LO at virtual ground) shows ≤ 0.1 mΩ.

  | Error | 100 pF ± 20 % | 200 pF ± 20 % | Share of target |
  |---|---:|---:|---|
  | Coil R, no pan, at 60 kHz | 4.2 mΩ | **8.3 mΩ** | 21–42 % of the 20 mΩ target |
  | Low-R pan coil R | 0.29 % | 0.58 % | |
  | Capacitor tan δ | 1.7e-4 | 3.3e-4 | |
  | L and C | < 7×10⁻⁵ | < 7×10⁻⁵ | |

  This matches R_iso·ω·ΔC·|Z|. Added to the typical 3.3 mΩ, coil R still meets. Added to corner standards, it fails. With R_iso, lock the LO lead geometry or recalibrate after any lead change.
- **Host.** Uncalibrated Z is 22 % low on the 100 Ω range until `feedback()` includes R_iso, which also needs a new identity and calibration model. Calibrated results do not depend on it.

**Recommendation from the model.** No PCB change is needed for noise; the chain is 30–2000× better than the proposed targets need. Accuracy depends on calibration standards, fixture contact and test-frequency choice, so spend there. Choose test frequencies that avoid harmonic aliasing (49 kHz rather than 50 kHz). Boxcar decimation (c) is free and does help the 1 kHz case and spur rejection. If (d) is adopted for stability, budget up to 8 mΩ of coil-R error from lead movement, or recalibrate after moving leads.

## 4. Method

- **Transfers** (`chain_spice.py`): the deck is `solver-resolution-fixed-local/ac-matched100.cir` with 38 zero-valued AC injection sources added (37 on Rev C, plus one for R_iso):
  - op-amp e_n in series with each + input
  - TIA and FDA input current noise
  - a thermal current source across every chain resistor
  - the AD9833 output
  - DUT thermal noise
- **Operating point.** KLU with `optran 1 0 0 0 0 0` and a declaration-order search, followed by a true-OP check. Both reuse `../solver-resolution-rev-c-final/strict_order.rs` through `op_guard.rs`. Every run accepted order 0 and passed the MID/acin checks.
- **Analyses.** One AC sweep (1 Hz–200 MHz, 50 points per decade) per source.
- **Bilinear model.** Each response is bilinear in Z_DUT with a shared denominator. Three DUT resistances therefore give the response to any impedance. A fourth resistance reproduces it to ≤ 8.2×10⁻⁸.
- **Validation against SPICE and transients** (`validate_transfer.py`):
  - Direct SPICE with real C, L+R, coil and tank elements at off-grid frequencies matches the model's uncalibrated Z to ≤ 6.3 µΩ.
  - The committed stage53 transient results match: uncalibrated Z within 0.27 mΩ (9 µF) and ≤ 0.10 mΩ (others), and ADC peaks within 1.8×10⁻⁵.
- **Noise densities.** Datasheet sources are in `sources/`:
  - OPA810 6.3 nV/√Hz, 1/f corner 1.5 kHz. OPA2810 6 nV/√Hz with the same corner (ESTIMATE).
  - FET current noise 5 fA/√Hz.
  - THS4551 3.3 nV/√Hz (1/f < 150 Hz) and 0.5 pA/√Hz (1/f < 10 kHz).
  - Resistor 4kT/R.
  - AD9833 SNR 60 dB typical (55 dB minimum), treated as white noise to 12 MHz.
  - ADS9224R transition noise 0.4 LSB plus explicit quantization; 52 MHz input pole; aperture jitter 2 ps; 40 ps tA mismatch.
  - REFby2 noise is common-mode.
  - ESTIMATES: reference gain noise 5 ppm common and 2 ppm per channel, CONVST jitter 50 ps.
  - Channel-common terms cancel in A/B and are synthesized anyway.
- **Synthesis** (`vi_model.py`, `synth.py`):
  - The folded 2×2 cross-spectrum at each FFT bin is an exact alias sum up to 2 MHz plus an integral to 200 MHz. It matches the direct per-conversion integral to 0.02 %.
  - Correlated Gaussian noise is drawn per record.
  - The signal uses the DDS tuning word, `divider_for`, 16,384 pairs, per-sample jitter and aperture offset.
  - ADC gain, offset and INL are drawn per board. Codes are 16-bit with clipping.
  - The record packs B15,A15,…,A0 with zlib CRC32, exactly the host `Record` JSON.
  - Boxcar mode averages N 1 MSPS conversions without re-rounding, matching the int32 sums of the decimating firmware. The protocol-1 host cannot read those, so what-if (c) uses the replica.
- **DUTs.** Coil 66.3 µH installed, R_ac at the row-5 limit following f^0.55, and 50 pF winding capacitance (ESTIMATE). Pan cases use kl 0.633 with r40 0.0334 Ω/µH, and kl 0.85 with r40 0.012 Ω/µH. Capacitors are 100 nF, 0.5 µF and 9 µF with tan δ 2e-4 and 10–20 nH ESL (ESTIMATE). Tank cases are the series coil+bank.
- **Standards.**
  - Typical: value σ 0.02 %; 1.5±1 nH; short 0.3 mΩ + 2 nH.
  - Corner: ±0.1 % opposite signs; 5 nH on the 20 Ω standard and none on the 100 Ω; short 2 mΩ + 5 nH.
- **Monte Carlo** (`mc.py`) and **reduction** (`summarize.py`). Frequency grid: 1000, 27638, 34736, 35000, 40000, 50000 and 60000 Hz.

## 5. Limits

Not modelled:
- switching-supply and mains pickup, which another study covers in `validation/power-spurs`
- thermal drift between calibration and measurement
- the real structure of DDS spurs, beyond the bound in §2.3
- changes in lead capacitance between HI and LO
- DUT nonlinearity
- process corners of the macromodels

AC injection is small-signal; it cannot see current limiting. (a), (b2) and (d) need large-signal and stability qualification. The 33 Ω range and FDA gain changes have no loop-margin evidence. The contact-resistance and standard-parasitic values are estimates and set the marginal verdicts; measure them on the first fixture.

## Reproduce and reuse

```sh
./rerun.sh            # host from the committed snapshot, op_guard, then budgets, MC and summary (~25 min)
./rerun.sh --spice    # also re-extract data/transfer_*.npz with ngspice 45.2/KLU (needs ../../sources/ti/models)
python3 synth.py --dut coil_pan --freqs 35000,40000 --seed 3 --out coil.json          # one host-format sweep
python3 synth.py --dut R:47,1.5e-9 --freqs 40000 --instance 2 --seed 1 --out chk.json # custom R+L, board draw 2
```

`vi_model.synth_channels(dut, hz, instance, opts, acq, rng)` is the backend entry point for a later serial emulator.

**Files.**
- Scripts: `chain_spice.py`, `op_guard.rs`, `spiceinit`, `validate_transfer.py`, `vi_model.py`, `synth.py`, `noise_budget.py`, `spur_alias.py`, `mc.py`, `summarize.py`, `rerun.sh`.
- `data/`: transfer models for each configuration and board draw, `host-commit.txt`, and `provenance.json` (ngspice 45.2, Python 3.12.12, numpy 2.4.6, model SHA-256 values, host binary hash).
- `results/`: `targets.csv`, `summary.json`, `whatif*.csv`, `leadmove.csv`, `noise_budget.*`, `spur_alias.json`, `transfer_validation.json`, `analytic_vs_mc.csv`, and the raw `mc_*.csv`.
