# 07 Conducted EMI, stage 19b: predicted margin vs limits (EMC1 follow-up)

- **Design:** native-21 stage 19b (`zapote/power-stage-120v`, board SHA-256 `b19a4553…0756662`, from integration `5d53896c3`). Model-based desk study. **No measurement, no compliance claim.**
- **Verdict: INCONCLUSIVE** (criterion below). The nominal case clears 6 dB (worst **7.8 dB**, 9-150 kHz QP, at 60 kHz, common mode), but one-at-a-time sensitivities fall to **1.8 dB** (22 A: 3.1 dB), all driven by one unmeasured number: the **tank-coil-to-PE capacitance**. No result is a regulatory margin.

## 1. Pass criterion (fixed before the results were computed)

Margin = limit − predicted line level, CW-equivalent RMS at the line crest (the D-22 convention; modulation by the line cycle only lowers AV/QP, so it is conservative by up to 3.9 dB for AV). AV binds above 150 kHz (it is 10 dB tighter than QP); below 150 kHz only a QP limit exists.

| Verdict | Rule |
|---|---|
| **PASS** | min margin ≥ **6 dB** in the nominal case and in every one-at-a-time sensitivity, over 35-60 kHz sweep, 22 A and 28 A ceilings, pan and no-pan clamp, 170 V and 198 V crest |
| **FAIL** | nominal < 0 dB, or any 22 A sensitivity < 0 dB |
| **INCONCLUSIVE** | anything else (nominal ≥ 0 but a sensitivity or an unqualified source leaves 0-6 dB, or the controls fail) |

Why 6 dB: the model's own uncertainty (unmeasured CM capacitances, ±20 % X caps, CW-equivalent detectors, idealised HF) is several dB, and D-22 used the same 6 dB (+1 dB reserve). Excluded from the sensitivity set (still reported): alternative designs (D-22 18 µH module, board-only, module Y removed, thin-pad insulator), stacked/beyond-spec corners, the `nopan_28A` clamp-failure fault, and the `REC*` recommendation scenarios. After the first run the coil capacitance was moved to the physical coil-end nodes (section 3); the criterion was not changed, and the earlier placement is kept as scenario `coil_caps_at_sw_nodes_(D-22 convention)` (9.8 dB).

## 2. Limits: which, and are they right for 120 V US/CA/MX

- **Used by the repo:** 47 CFR 18.307(a), the table for **induction cooking ranges**, transcribed in `../sources/ecfr-47cfr18.307-table.json` (eCFR read 2026-09-27): 9-50 kHz 110 dBµV QP; 50-150 kHz 90→80 dBµV QP (log decrease); 150-500 kHz 66→56 QP / 56→46 AV; 0.5-5 MHz 56 / 46; 5-30 MHz 60 / 50 dBµV; tighter value at boundaries (18.307(g)); 18.301 ISM bands excluded (6.78 ± 0.015, 13.56 ± 0.007, 27.12 ± 0.163 MHz), 50 µH/50 Ω LISN, each line to ground. D-22 and round 3 stopped at 150 kHz; **this study also applies the 9-150 kHz rows**, which is where the 35-60 kHz fundamental and low harmonics sit.
- **US:** FCC Part 18 (consumer ISM, induction cooking) is the right regime; the transcription is the one the repo already uses (secondary: the eCFR HTML could not be hash-pinned).
- **Canada / Mexico / CISPR 14-1: not verified.** A web check (not downloaded; standards are paywalled) found that CISPR 14-1 ed. 5.2's terminal-voltage table starts at 148.5 kHz and that induction-cooking emission rules also sit in CISPR 11, so CISPR 14-1 alone would not cover 9-150 kHz. ICES-001 (Canada) is expected to follow CISPR 11 and Mexico was not checked. Ask the test lab to confirm the Canadian limit set and whether any Mexican conducted-EMI requirement applies before relying on FCC alone. [Search result](https://webstore.ansi.org/preview-pages/IEC/preview_cispr14-1%7Bed5.2%7Db.pdf) for the 148.5 kHz start.

## 3. Model

`emi_s19b.py` is a complex nodal (MNA) solver (numpy only). It replaces ngspice: its transfer functions match D-22's saved ngspice arrays to 2.3×10⁻⁶ relative. Each source's response is solved exactly at every harmonic of the switching frequency, for 35-60 kHz (0.5 kHz steps nominal, 1 kHz sensitivities), so **the fundamental and low harmonics in 9-150 kHz and the frequency-sweeping loop are covered** (max-hold over the loop's range; the firmware steps 250 Hz per half line cycle from 60 down to 35 kHz, so each line is a swept narrowband line whose dwell only reduces AV; held-frequency operation is the bound used).

**Sources at the line crest** (unfiltered bus: bus voltage and tank current follow |sin| at 2× line; crest is the worst case):

| Source | Model | Basis |
|---|---|---|
| Switch nodes SW_A, SW_B | 0-Vc trapezoids, 50 % duty, legs 180° apart (D-27 C1, the only approved point), Vc = 170 or 198 V | edge times from D-19 edge census (`out-D19/edge-table.md`, 37 A ZVS rows: 10-90 % 26.8/19.5 ns at 170 V, 24.0/18.6 ns at 198 V), scaled ∝ commutating current Ipk·sin φ / 37 A |
| Bus ripple DM current | bridge input current i·sgn(v): Ipk sin(ωt−φ) rectified, lines at **2k·fs**, exact Fourier series, edge-smoothed | tank Ipk = 2.17 × ceiling (firmware `TANK_PEAK_PER_RMS`): 47.7 A (22 A), 60.8 A (28 A); φ = 50° pan (ZVS lag ≥ 45°), 88° no-pan clamp |
| Reachable current vs fs | Ipk(fs) = min(ceiling, V1 sin φ / (ωL_min − 1/ωC)), L_min = 0.58 × 70 µH (pan class `low_R_silargan_like`, `coil_mc.rs`) or 66.5 µH (empty coil), C = 0.54 µF | high fs cannot carry full current; tank R/L solved per case so the circuit is self-consistent |

Source model check against the device-level D-22 FFT (170 V, 35 kHz): bus-current harmonics 4-20 within 0.25 dB (2nd within 1.4 dB), switch-node harmonics 1-35 within 0.05 dB (`controls.analytic_source_vs_D22_fft`).

**Receiver and filter** (round-3/D-22 network unchanged where not re-specified): LISN 50 µH (+5 Ω below 150 kHz, as CISPR 16-1-2) and 50 Ω to PE, PE bond 100 nH/10 mΩ; board filter per `elec/src/power_stage_120v.ato`: C1/C2 1 µF X2 (12.2 nH, 35 mΩ), TMOV 1.4 nF, L1 B82726S2203A020 (1.6 mH/winding, 18 µH leakage, 11.1 pF + 12.7 kΩ per winding from the TDK curve fit), C3/C4 2.2 nF Y with 15 nH ESL; BR1 85 pF junctions; 5.4 + 0.4 µF DC link (20/5 nH). **Inlet module** (DECISIONS D-22/D-36 and "EMI below 150 kHz" item 4): CM choke B82726S2203A020 + 2.2 µF X in, 4.7 µF X + 3.9 Ω/4.7 µF damping + 30 kΩ bleed, Y 4.7 nF + 2.2 nF per line (D-22 `PARTS.md`), **DM raised to 100 µH**: 18 µH leakage + 2 × 41 µH discrete (8 mΩ, 30 pF each).

**CM paths from stage-19b geometry** (`inputs/copper-dump-s19b-summary.json` is the reduced copper dump; the script reads `…/runs-native21/s19/s19b/copper-dump.json` when present):

| Path | Value | Source |
|---|---|---|
| Q3/Q6 tab (SW_A/SW_B) → PE sink via 2.0 mm AlN (εr 8.6) + two 0.03 mm compound films (εr 4, assumed) | **5.4-8.6 pF, nominal 7.0 pF** (tab area 151-240 mm²) | DECISIONS M11, `m11/stack_calc.py` (its 5.8-9.1 pF omitted the compound); thin-pad fallback 42 pF kept as a scenario |
| Q2/Q5 tabs (BUS_P) → PE | 2 × 7.0 pF | same |
| SW_A / SW_B pour edge → set-back PE pedestal (2-D Laplace of the y-z cross-section; edge lengths from the dump) | 0.28 pF / 0.12 pF | `fringe_cap_per_mm` |
| SW_A (1.93 e-3 m²) / SW_B (3.31 e-3 m²) pour area → chassis, plate model at 15 mm | 1.1 / 1.95 pF (**ASSUMED**: no enclosure-metal data; 5 mm and none run as sensitivities) | zone areas in the dump |
| BR1 case → PE | 10 pF per rail | round 3 (**ASSUMED**) |
| **Coil / pan → PE** | **25 pF at each coil end (50 pF total), at the coil-end nodes, so the drive is the tank voltage, not just the switch node. No data in the repo; 10-100 pF is round 3's assumed range.** | **ASSUMED** |
| IRM-20 / IRM-60 isolation, F6 bias transformers, ISO7710 | not in the CM model; `native21/cm_screen.json` shows ≤ 0.05 dB for the 0.4 pF ISO7710 paths. HOT↔SELV isolation capacitance of PS1-PS3 is **not in any repo datasheet** | open |

**PS1/PS2/PS3** (IRM-20, IRM-20, IRM-60): no EMI data exist in the repo, so they are a *bound*, not a source. Assume each exactly meets the AV limit in a bare LISN and inject that current at L_FILT/N_FILT (DM, or CM to PE). Through the filter, the margin is ≥ 135 dB (DM) and ≥ 38 dB (CM, three modules incoherent, worst at 150 kHz); the filter transfer, not the modules, decides. This bound uses the filtered-side node and ignores any module-internal Y path to PE that bypasses L1.

## 4. Controls (asserted in the script; all pass)

| Control | Result |
|---|---|
| Reproduce D-22's native-15 headline: worst proposed-filter terminal AV margin **9.28 dB** (198 V, 60 kHz, `old_low_leakage`, 180 kHz) | **9.2801 dB**, Δ = 9×10⁻¹⁰ dB (limit 1 dB) |
| Reproduce D-22's nominal terminal margins from its stored source FFTs: original filter −24.15 / −16.08 dB (35/60 kHz), proposed +28.88 / +39.54 dB | Δ ≤ 6×10⁻⁸ dB |
| Reproduce round 3's committed assumed-source peak CM lines (both-mismatches 59.97 dBµV @175 kHz and 64.19 @180 kHz; choke −30 %, coil 100 pF) | Δ ≤ 3.4×10⁻⁵ dB (the balanced case is a −150 dBµV cancellation floor and is excluded) |
| Closed-form checks: series-L/shunt-C into 50 Ω at 20 and 200 kHz; 100 pF CM injection into the LISN pair at 150 kHz and 2 MHz | Δ ≤ 3×10⁻¹⁰ dB (limit 0.5 dB) |
| MNA transfers vs D-22's saved ngspice AC arrays (15 cases) | max relative error 2.3×10⁻⁶ |

The control reproduces D-22's numbers, so it validates the solver and receiver, not D-22's physical assumptions.

## 5. Results (nominal stage-19b model)

Worst predicted terminal line per band, from `results.json` (`scenarios.nominal`); 22 A and 28 A rows coincide in 9-150 kHz because the tank cannot reach more than ~19 A peak at 60 kHz.

| Case | Band | Margin (dB) | Worst freq | Detector | Level (dBµV) | CM vs DM |
|---|---|---:|---|---|---:|---|
| 22 A, pan, 170 V | 9-150 kHz | 9.1 | 60 kHz (fs fundamental) | QP 9.1 | 79.2 | CM (79.2 vs −12) |
| 22 A, pan, 170 V | 150 kHz-30 MHz | 24.4 | 150 kHz (4th harmonic of 37.5 kHz) | AV 24.4 / QP 34.4 | 31.6 | DM (30.3 vs 15.7) |
| 28 A, pan, 198 V | 9-150 kHz | **7.8** | 60 kHz | QP 7.8 | 80.5 | CM |
| 28 A, pan, 198 V | 150 kHz-30 MHz | 22.3 | 150 kHz (37.5 kHz ×4) | AV 22.3 / QP 32.3 | 33.7 | DM (32.4 vs 17.8) |
| 22 A, no pan, 198 V | 9-150 kHz | 11.7 | 70 kHz (2 × 35 kHz) | QP 11.7 | 75.2 | DM (73.6 vs 64.8) |
| 22 A, no pan, 198 V | 150 kHz-30 MHz | 25.6 | 150 kHz | AV 25.6 | 30.4 | DM |
| any | 0.5-5 MHz / 5-30 MHz | 62 / 60 | 504 kHz / 26.4 MHz | AV | −16 / −10 | CM / DM |

(`nopan_28A` is the clamp-failure fault; margins 11.7 / 25.6 dB.) The 0.5-30 MHz numbers come from an ideal trapezoid through a lumped filter with no board/harness parasitics, a choke fit unqualified above ~850 kHz, and no ring; **treat them as unassessed, not as 60 dB of margin**.  For scale, the board filter alone (no module) is at 1.0 dB at 26 MHz in this model.

Findings:
1. **The inlet module is mandatory.** Without it the board filter misses every band (−39 dB at 70 kHz, −38 dB at 150 kHz).
2. **D-22's module as specified (18 µH DM) fails 9-150 kHz by 5.1 dB** (2×fs bus ripple, 70 kHz; DECISIONS says −4 to −25 dB) and has 8.7 dB at 150 kHz with the 28 A source. The ≥ 100 µH DM requirement fixes both (≈ +15 dB). Even at 80 µH (≥ 80 % at 15 A bias) the margins hold (21.1 dB above 150 kHz).
3. **Above 150 kHz the bus-current DM at the 4th harmonic of 37.5 kHz (150 kHz) is the worst line, 22 dB.** Switch-node CM is not limiting: the 2 mm AlN tab capacitance (7 pF) is 6× below the 42 pF thin-pad design.
4. **Below 150 kHz the limiting line is the fs fundamental in CM at 50-60 kHz.** The limit steps from 110 to 90 dBµV at 50 kHz, the CM transfer peaks at 28 and 70 kHz (`margin_vs_fs_and_transfer.png`), and the drive is the tank capacitor/coil voltage acting through coil-to-PE capacitance. Margin vs fs: 9.8 dB at 35 kHz (2×fs DM at 70 kHz), rising to ≈ 29 dB at 49.5 kHz, then 11 dB at 50 kHz falling to 7.8 dB at 60 kHz.

## 6. Sensitivity (min over 170/198 V × 22 A/28 A pan and 22 A no-pan, 35-60 kHz)

| Scenario (one change from nominal) | 9-150 kHz QP | 150-500 kHz AV | 0.5-5 MHz AV | 5-30 MHz AV | worst |
|---|---:|---:|---:|---:|---|
| nominal | 7.8 @ 60 k | 22.3 @ 150 k | 62.2 | 59.9 | CM |
| tab capacitances 8.6/5.4 pF (or reversed) | 8.5 / 7.1 | 22.8 / 21.2 | 60.9 / 57.8 | 59.9 | CM |
| thin-pad insulator instead of AlN (42 pF, ±20 % mismatch) | 9.5 | 18.8 | 48.2 | 59.6 | DM |
| chassis metal at 5 mm / no chassis coupling | 7.5 / 8.0 | 22.1 / 22.8 | 60.1 / 62.7 | 59.6 / 60.1 | CM |
| **coil→PE total 10 pF** | 11.1 | 23.7 | 72.5 | 62.3 | DM |
| **coil→PE total 100 pF (symmetric)** | **1.8 @ 60 k** | 17.3 | 56.6 | 57.6 | CM |
| coil→PE 100 pF, 70/30 split | 2.9 | 10.0 | 40.2 | 57.6 | CM |
| coil→PE 100 pF, all on one end (beyond-spec, informational) | −0.8 | 1.9 | 32.2 | 57.6 | CM |
| coil caps at the switch nodes (D-22 convention) | 9.8 @ 70 k | 22.8 | 70.2 | 59.9 | DM |
| Y caps −20 % | 8.6 | 18.5 | 58.4 | 52.8 | CM |
| Y-cap ESL ×3 | 7.8 | 22.8 | 62.2 | 59.7 | CM |
| module Y caps removed (board 2.2 nF only) | 3.6 | 3.0 | 18.6 | 26.9 | CM |
| L1 and module choke −30 % | 8.4 | 15.7 | 57.5 | 59.9 | CM |
| choke winding capacitance ×2 | 7.8 | 22.8 | 55.8 | 47.0 | CM |
| module DM 80 µH / 18 µH only (D-22 as specified) | 7.8 / **−5.1** | 21.1 / 8.7 | 62.2 / 62.1 | 59.9 / 57.7 | CM / DM |
| module DM inductor self-capacitance 100 pF | 7.8 | 22.8 | 62.2 | 58.4 | CM |
| X caps −20 % (all) | 6.1 | 18.9 | 62.2 | 59.9 | DM |
| PE bond 200 nH | 7.8 | 22.8 | 62.2 | 59.9 | CM |
| edge rate ×0.5 / ×2 / leg B ×1.2 | 7.8 | 22.8 | 61.5-62.2 | 59.9-60.1 | CM |
| board filter only (no module) | −39.3 | −38.4 | 2.8 | 1.0 | DM |
| stacked worst corners (informational) | 3.2 | **−4.6** | 28.9 | 37.3 | CM |

Edge rate is irrelevant where the margin is decided (≤ 150 kHz) and only moves content above ~3 MHz, where the model is not credible. CM capacitance is **the** sensitivity.

## 7. Verdict

**INCONCLUSIVE** (`results.json: verdict`): nominal min margin 7.8 dB ≥ 6 dB; sensitivity minimum 1.8 dB (coil→PE 100 pF symmetric), 22 A sensitivity minimum 3.1 dB; no 22 A sensitivity inside the declared set is below 0 dB (the < 0 dB cases are excluded stacked/beyond-spec corners). The result flips to FAIL if coil→PE exceeds roughly 100 pF with any asymmetry. Above 150 kHz the predicted margin is ≥ 10 dB in every declared sensitivity (10.0 dB with a 100 pF 70/30 coil split); the open items are the 50-60 kHz fundamental CM and the unassessed HF band.

## 8. Limitations

- Coil→PE capacitance, chassis distance and PS1-PS3 isolation capacitance are not in any repo data. The prior studies' 10-100 pF is an assumption.
- CW-equivalent line levels, not a CISPR receiver (no 9 kHz/200 Hz IF, no mains modulation, no sweep dwell, no QP weighting); the swept line is treated as held.
- Fixed rectifier conducting pair, one-way source (filter does not load the switching circuit), no 120 Hz cyclostationary simulation, no startup/inrush/burst (the 20 s burst mode and the damper-open peaks D-27 R42 flagged are untested).
- Choke/capacitor models: TDK curve fit (older plot, ±2 px sensitivity 799-897 kHz resonance) and a K-SIM ESL for a related KEMET part; the module DM inductors are an assumed ideal 41 µH + 30 pF (the real 20 A DM inductor is not specified). Module saturation (≥ 80 % at 15 A) is only represented by the 80 µH case.
- Legs share one tank-current waveform; leg B's own switching matrix was not used (D-22 same limitation). dv/dt scaling with current is a first-order ZVS rule.
- Above ~1-3 MHz the lumped model is not predictive (no wiring/board parasitics, no ring, no harness).
- Model margin at the sweep's 150 kHz boundary depends on whether harmonics fall exactly at 150 kHz (fs = 37.5/50 kHz): the 4th and 3rd harmonics land there and the limit steps by 10 dB at 150 kHz (AV defined only above); the 148.5 kHz CISPR start would differ by about 1 dB.

## 9. Recommendations

1. **Measure the coil→PE capacitance first** (LCR meter at 100 kHz, coil studs J2/J5 shorted to PE-bonded enclosure, with and without a pan, in the assembled enclosure; also each end separately for asymmetry). This one number moves the margin from 11 dB (10 pF) to 2 dB (100 pF). Reserve a bench tap: see `BENCH-PRECOMPLIANCE.md` step 1. If the measured sum is ≤ 50 pF and balanced, the nominal 7.8 dB stands.
2. **Do not add Y capacitors from the DC bus to PE as a fix.** Scenario REC1 (2.2 nF on each rail) *worsens* the 60 kHz CM line to 1.4 dB (−3.2 dB with a 70/30 coil split) because it lowers the CM resonance into the switching band. Keep Y at the current 9.1 nF per line (leakage: 0.48 mA per line at 140 V/60 Hz from Y alone; the touch-current budget is the real cap).
3. **Preferred CM fixes, in order of effect** (`results.json` REC scenarios; all pass 6 dB at nominal coil capacitance):
   - a coil-side electrostatic shield returned to bus_n (REC3, 75 % of the coil capacitance: 11.0 dB) and, with a 100 pF 70/30 coil, REC4 (shield + bus Y) gives 8.6 dB;
   - a stronger inlet-module CM choke, 3.2 mH (REC2: 10.5 dB; 8.7 dB at 100 pF 70/30 but only 15.7 dB above 150 kHz). The module is off-board, so this is an enclosure/BOM change, not a re-layout.
4. **Controller (information, no change recommended):** margin is lowest at fs = 35 kHz (2×fs DM, 9.8 dB) and at 50-60 kHz (CM fundamental, 11 → 7.8 dB) and highest at 45-49.9 kHz (≥ 23 dB). The loop chooses fs by pan and power, so this cannot be steered; confirm at BENCH step 5.
5. **Keep the inlet module** (specified ≥ 100 µH DM, 20 A, ≥ 80 % at 15 A bias, Y 4.7 + 2.2 nF per line, 3.9 Ω damping). Without ≥ 100 µH DM the 9-150 kHz band fails (−5 dB). Its heat allowance (8 W) is tight for two 8 mΩ 15 A DM inductors (3.6 W) plus the choke (2.7 W): re-check at bench.
6. **Board: no change required by this study (none made).** If the board is re-spun, reserve: a PE-bonded test point (and a spare 4.7 nF Y2 footprint pair from L_FILT/N_FILT to PE on the board side of L1) so Y can be tuned at the bench within the leakage budget; keep R38 (the SELV-to-PE functional bond) a hand-removable part so the bench can separate the SELV/CM path; and keep a current-probe window around each of the J2/J5 coil studs. For the module, reserve mounting space for the CM choke upgrade (REC2) in the 110 × 80 × 50 mm allocation (the 3.2 mH choke is larger than the 45 × 25.5 × 41 mm B82726S2203A020).

## 10. Reproduce

```sh
cd zapote/power-stage-120v/validation-results/07-conducted-emi/s19b
python3 emi_s19b.py          # ~5 min, 3 threads; asserts the controls; writes results.json and four PNGs
python3 emi_s19b.py --no-plots
```

numpy/scipy compute everything; matplotlib is used only for the PNGs. Inputs outside the directory: D-22 evidence under `../../01-switching-parasitics/round17/delegation/out-D22/` (including 891 MB of FFTs for one control case) and round 3's `../round3/outputs/`; the copper dump falls back to `inputs/copper-dump-s19b-summary.json`.
