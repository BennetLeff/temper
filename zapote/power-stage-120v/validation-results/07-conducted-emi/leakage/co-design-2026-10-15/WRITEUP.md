# Leakage × conducted EMI co-design, native-21 120 V power board (desk study, 2026-10-15)

This is an analysis only. Nothing in the repo was edited, staged or committed. Nobody was contacted.
- Every number comes from `python3 -I run_all.py`, which writes `results/summary.json`, `results/joint.csv` and `results/run_all.log`.
- `run_all.py` reruns the controls first and exits 1 if any control fails.
- A full solve takes 30–40 min with 4 processes (2,434 s on a loaded machine). `--reuse` reloads the cached EMI candidates, but still re-solves the control candidate.
- Repo inputs are byte-identical copies in `repo_copies/`, with SHA-256 values checked in `MANIFEST.json` against the repo files at the study base 0aecdc56f (stage 38 later changed the working copies for the s38 system; amended 2026-10-15):
  - `leakage_budget.py` and its `result.json`;
  - `emi_s19b.py` and its `results.json`.
- Datasheets are in `downloads/` and are not for the repo. `run_all.py` re-reads their rows with `pdftotext`.

## 1. Controls (reproduced)

| Control | Committed | Reproduced |
|---|---|---|
| Leakage DESIGN row (datasheet-max supplies, +20 % Y, 132 V) | 0.9741 mA FAIL | 0.9741 mA (Δ < 1e-12) |
| INFORMATIONAL, typical supplies | 0.5750 mA | 0.5750 mA |
| INFORMATIONAL, board Y only + typical supplies | 0.1629 mA PASS | 0.1629 mA |
| CONTROL (+10 nF/line) and CONTROL 2 | 1.5713 / 0.7601 mA FAIL | same |
| c23 + D-22 rev B (Y 2.2, PS1 deleted); same filter with PS1 fitted (CONTROLLER-REQUEST.md) | 0.419 / 0.562 mA | 0.4191 / 0.5621 mA |
| s19b `emi_min_margin_dB` (nominal, 6 configs, 0.5 kHz step) | 10.479334 dB | 10.479334 dB |
| s19b 19 compliance sensitivities + INFO pan-earthed, each one | results.json | max \|Δ\| 4.1e-10 dB |
| s19b sensitivity minimum (X caps −20 %) | 6.5028 dB | 6.5028 dB |
| Meter networks (IEC 60990 Fig. 4; UL-style 1500 Ω ∥ 0.15 µF) against closed form | — | exact |
| temper-8d T1: E00 earthed pan, R inside the coil | 8.37 dB | 8.366 dB |

**"Every compliance scenario"** means s19b's own verdict set, 20 scenarios in all:
- `nominal`: 170/198 V × pan_22A / pan_28A / nopan_22A, with fs from 35 to 60 kHz in 0.5 kHz steps.
- The 19 sensitivities, each over 3 configs with a 1 kHz step:
  - `tabs_mismatch_AlN_range`, `tabs_mismatch_reversed`;
  - `enclosure_metal_5mm`, `no_enclosure_coupling`;
  - `coil_caps_at_sw_nodes_(D-22 convention)`;
  - `coil_PE_study16_low_28p5pF`, `coil_PE_study16_high_35p1pF`, `coil_PE_study16_plus_board_51pF`;
  - `Y_caps_minus20pct`, `Y_caps_ESL_x3`;
  - `L1_minus30pct_and_module_choke_minus30pct`, `L1_winding_C_x2`;
  - `module_DM_80uH`, `module_DM_L_parasitic_C_100pF`;
  - `X_caps_minus20pct`, `PE_bond_200nH`;
  - `edge_B_x1.2`, `edge_x0.5_slower`, `edge_x2_faster`.

For a candidate, the relative sensitivities are applied to the candidate's own part values:
- Y −20 %, X −20 %, chokes −30 %, winding C ×2 and DM L ×31/41.
- For the committed design these reduce exactly to s19b's absolute values. That is the control above.

`INFO_pan_earthed_91pF` is reported but is not in the verdict, as in s19b.

## 2. Leakage side: the supplies set the floor

DESIGN rule (unchanged):
- touch current = Σ ωCV over the hot line, with every Y at +20 % and the coil at 31 pF (+20 %), at 132 V and 60 Hz;
- plus each mains-connected supply at its datasheet maximum, scaled ×V/V_test ×60/50.

Per-unit contributions:
- 0.0597 mA per nF/line of Y;
- 0.143 mA per IRM supply (< 0.25 mA/277 Vac);
- 0.048 mA per MPM-20 (< 80 µA/264 VAC);
- 0.060 mA per MPM-65 (< 100 µA/264 VAC).

**Largest total Y per line (board + module, nominal nF) that meets each criterion:**

| Supplies charged to PE | Supplies, mA | Portable 0.25 (50 %) | Stationary 0.375 (50 %) | Portable 0.5 | Stationary 0.75 |
|---|---|---|---|---|---|
| S0 as built: IRM-20-15, IRM-20-24, IRM-60-15ST | 0.429 | **impossible** (−3.03) | **impossible** (−0.93) | 1.16 | 5.35 |
| S1 c23 (delete PS1) | 0.286 | **impossible** (−0.63) | 1.46 | 3.55 | 7.74 |
| S2 c23 + PS3 → MPM-65-15ST | 0.203 | 0.76 | 2.85 | 4.94 | 9.13 |
| S3 c23 + PS2 → MPM-20-24 | 0.191 | 0.96 | 3.05 | 5.14 | 9.33 |
| **S4 c23 + PS2 → MPM-20-24 + PS3 → MPM-65-15ST** | **0.108** | **2.35** | 4.44 | 6.53 | 10.72 |
| S5 no c23, all three → MPM (MPM-20-15, MPM-20-24, MPM-65-15ST) | 0.156 | 1.54 | 3.64 | 5.73 | 9.92 |
| *X1 c23 + g06 P3 (PS2 not in the PE path), IRM supplies* | 0.143 | 1.76 | 3.85 | 5.95 | 10.13 |
| *X2 c23 + P3 + PS3 → MPM-65* | 0.060 | 3.15 | 5.24 | 7.34 | 11.52 |
| *X3 R38 open (SELV floating) + P3* | 0 | 4.16 | 6.25 | 8.34 | 12.53 |

Rows in italics are not on the DESIGN basis, because they change which supplies are charged. Each one needs a bench measurement and certifier acceptance.

**What this proves:**
- With two or more IRM-class supplies charged at their datasheet maximum, no Y value, filter or EMI trade meets 0.25 mA. The supplies alone take 0.286 mA.
- Candidate 23 is therefore necessary but not sufficient for the portable class.
- On the DESIGN basis, only lower-leakage supplies open the space.

Supply alternatives (MEAN WELL, same vendor):
- **MPM-20-xx** is in the same Case No. 219A as IRM-20, with the same 52.4 × 27.2 × 24 mm body and pin grid (MPM-20-SPEC 2024-10-30 p.4; IRM-20-SPEC 2025-11-21 p.3).
- **MPM-65-15ST** is in the same Case No. IRM60 as IRM-60-15ST, 109 × 52 × 33.5 mm, screw terminals (MPM-65-SPEC 2024-10-30 p.2 and p.4; IRM-60-SPEC p.4).
- So both are footprint and mounting drop-ins.
- Both are 2 × MOPP medical parts, and Notes 6/7 say the "Touch current was measured from primary input to DC output". That is the same path the model charges.
- No module with a lower stated touch current was found in the searches.

## 3. EMI side: how low Y can go (full s19b compliance set)

| Filter (module Y removed unless stated; L1 = TDK 1.6 mH unless stated) | Y/line | Nominal | **Minimum over the 20 scenarios** [binding] | Earthed pan (INFO) |
|---|---|---|---|---|
| E00 committed (board 2.2 + module 4.7 + 2.2, module TDK 1.6 mH) | 9.1 | 10.48 | 6.50 [X −20 %] | 2.62 |
| E01 module Y 2.2 nF HF only (g01 P1 Y) | 4.4 | 8.68 | 3.31 [chokes −30 %] | −0.32 |
| E02 module Y removed, nothing else | 2.2 | 7.12 | −9.50 [chokes −30 %] | −1.93 |
| E03 board Y removed, module Y kept | 6.9 | 9.67 | 5.05 [coil+board 51 pF] | −0.72 |
| Board 3.3 nF, module TDK 1.6 | 3.3 | 10.74 | 6.54 [coil 51 pF] | 1.65 |
| Board 2.2, module SC-20-201 2 mH | 2.2 | 8.13 | −1.79 | −0.92 |
| Board 2.2, module 3.6 mH (SCF39XV class) | 2.2 | 10.79 | 6.60 [coil 51 pF] | 1.73 |
| **Board 2.2, module KEMET SCF31X-220-2R1A011JH 5.68 mH** | 2.2 | 12.37 | **8.19** [coil 51 pF] | 3.32 |
| Same, with 0.3 % DM leakage | 2.2 | 11.13 | 6.87 [X −20 %] | 3.32 |
| **Board 2.2, L1 and module both SCF31X 5.68 mH** | 2.2 | 16.02 | **11.51** [winding C ×2] | 6.96 |
| Board 1.5, module SCF31X 5.68 mH | 1.5 | 9.03 | 4.86 [coil 51 pF] | 0.03 |
| Board 1.5, L1 and module SCF31X | 1.5 | 12.72 | 8.25 [winding C ×2] | 3.71 |
| Board 1.0, L1 and module SCF31X | 1.0 | 9.23 | 4.77 | 0.31 |
| Board 1.0, L1 and module SCF31X + 75 % coil shield | 1.0 | 17.52 | 10.37 | 11.70 |
| Board 0 (no Y at all), L1 and module SCF31X | 0 | −19.56 | −23.66 | −25.26 |
| Board 2.2, module 3.6 mH, X up (C1/C2 2.2 µF, module 10 µF) | 2.2 | 10.79 | 6.60 (no change) | 1.73 |

Readings:
1. **Y must sit at C3/C4 (L1 output).** The same 2.2 nF at the module output (E04, with a 3.6 mH choke) gives 0.07 dB.
2. **Deleting the module Y without a bigger CM choke fails badly** (−9.5 dB). The 2.2 nF Y and the 1.6 mH chokes put a CM resonance in the band, and the chokes −30 % corner lands it on 180 kHz. A stage-1 choke of ≥ 3.6 mH is needed, and 5.68 mH gives slack.
3. **X caps do nothing for the binding lines** at low Y, which are CM at 180 kHz and 60 kHz. The X-up row is unchanged. The model supports the X-cap lever, but it buys no margin here.
4. **Y must stay ≥ 1.5 nF/line.** With both chokes at 5.68 mH that is the floor. 1.0 nF needs the coil-side shield as well. At 0 nF the margin is −24 dB in every combination tried.

## 4. Pareto frontier (DESIGN basis; touch current vs EMI minimum vs cost)

These are the non-dominated priced points from `results/summary.json → pareto_design_basis`. Rows with EMI below 0 are left out here but kept in the JSON. Cost is USD per system at 500 units against the committed design, and includes the supplies, the module parts and L1. The 2 × 41 µH DM inductors are needed in every plan, have no MPN, and are not priced.

| Touch current (mA) | EMI min (dB) | Δ$ | Δ parts | Passes | Change set |
|---|---|---|---|---|---|
| 0.1696 | 4.77 | +4.74 | −5 | P S (EMI fail) | S4, Y 1.0, L1 + module SCF31X |
| 0.1994 | **8.25** | +4.74 | −5 | **P** S | S4, Y 1.5, L1 + module SCF31X |
| 0.1994 | 5.46 | −0.63 | −5 | P S (EMI fail) | S4, Y 1.5, L1 SC-20-201, module SCF31X |
| **0.2412** | **11.51** | +4.74 | −5 | **P** S | S4, Y 2.2, L1 + module SCF31X (robust) |
| **0.2412** | **8.19** | **+2.95** | −5 | **P** S | **S4, Y 2.2, module SCF31X (recommended)** |
| 0.2525 | 4.77 | −1.96 | −5 | S | S3, Y 1.0, L1 + module SCF31X |
| 0.2824 | 8.25 | −1.96 | −5 | S | S3, Y 1.5, L1 + module SCF31X |
| 0.3069 | 9.93 | +2.95 | −5 | S | S4, Y 3.3, module SCF31X |
| 0.3242 | 8.19 | −3.75 | −5 | S | S3, Y 2.2, module SCF31X |
| 0.3773 | 8.25 | −6.01 | −5 | — | S1, Y 1.5, L1 + module SCF31X |
| 0.4191 | 8.19 | −7.80 | −5 | 100 % only | S1 (c23 only), Y 2.2, module SCF31X |
| 0.4848 | 7.11 | −13.17 | −5 | 100 % only | S1, Y 3.3, module SC-20-201 |

P = meets 0.25 mA (portable, 50 %). S = meets 0.375 mA (stationary, 50 %).

Points with the 75 % coil shield have no price because the shield is a coil/enclosure change. Their extra margin comes on top: 9.9–10.4 dB.

## 5. Recommended smallest change set (portable 0.5 mA, 50 % rule, EMI ≥ 6 dB everywhere)

Only 12 of the 228 DESIGN-basis combinations meet both rules, and every one of them needs S4 or S5. The smallest set has five changes:

| # | Change | Where | Δ$ at 500 | Δ parts |
|---|---|---|---|---|
| 1 | Delete PS1 (candidate 23, J13 rail merge) | power board + controller | −8.40 | −1 |
| 2 | PS2 IRM-20-24 → **MEAN WELL MPM-20-24**, same footprint | power board | +4.05 (est) | 0 |
| 3 | PS3 IRM-60-15ST → **MEAN WELL MPM-65-15ST**, same case and mounting | chassis | +6.70 (est) | 0 |
| 4 | D-22 module: remove all four Y caps (4.7 + 2.2 nF per conductor); C3/C4 stay 2.2 nF | inlet module | −1.19 | −4 |
| 5 | D-22 module CM choke TDK B82726S2203A020 1.6 mH → **KEMET SCF31X-220-2R1A011JH** 5.68 mH, 22 A, 500 VAC, 4.39 mΩ | inlet module | +1.79 (est, price unverified) | 0 |
| | **Total** | | **+$2.95** (est) | **−5** |

**Touch current, DESIGN basis:** 0.2412 mA.
- Portable 50 % (0.25): PASS, by 8.8 µA (3.5 % of the budget).
- Stationary 50 % (0.375): PASS.
- That is 48 % of 0.5 mA and 32 % of 0.75 mA.
- PE-conductor current with PE intact is 0.48 mA (2× per line).

**EMI per compliance scenario (dB; committed design in brackets):**

| Scenario | Margin (dB) | Committed design (dB) |
|---|---|---|
| nominal | 12.37 | 10.48 |
| tabs_mismatch_AlN_range | 13.08 | 10.48 |
| tabs_mismatch_reversed | 10.16 | 10.48 |
| enclosure_metal_5mm | 11.33 | 10.28 |
| no_enclosure_coupling | 12.77 | 10.58 |
| coil_caps_at_sw_nodes | 14.07 | 10.48 |
| coil_PE_study16_low | 13.04 | 10.56 |
| coil_PE_study16_high | 11.36 | 10.35 |
| **coil_PE_study16_plus_board_51pF** | **8.19** (minimum) | 7.69 |
| Y_caps_minus20pct | 10.43 | 10.78 |
| Y_caps_ESL_x3 | 12.38 | 10.48 |
| L1/module chokes −30 % | 10.28 | 10.74 |
| L1_winding_C_x2 | 11.62 | 10.40 |
| module_DM_80uH | 12.37 | 8.68 |
| module_DM_L_parasitic_C_100pF | 12.37 | 10.48 |
| X_caps_minus20pct | 9.86 | 6.50 |
| PE_bond_200nH | 12.36 | 10.47 |
| edge_B_x1.2 | 12.38 | 10.48 |
| edge_x0.5_slower | 12.38 | 10.48 |
| edge_x2_faster | 12.37 | 10.48 |
| INFO earthed pan | 3.32 | 2.62 |

- The binding line is CM at 180 kHz (198 V / 28 A, 3 × 60 kHz).
- The minimum is **8.19 dB** against the committed design's 6.50 dB, so EMI improves as well.
- The NC5.68 DM leakage is unpublished (1 % assumed). At 0.3 % the minimum is 6.87 dB, which still passes.

**Robust variant (recommended if the board is re-laid out anyway):** also change L1 to SCF31X-220-2R1A011JH.
- Cost is +$1.79 (est), +$4.74 in total, and the board needs re-layout: the choke is 45 × 42 × 33 mm with S ≥ 17 mm and S1 ≥ 30 mm, against the TDK part's footprint.
- EMI minimum is 11.51 dB (binding: winding C ×2).
- The earthed pan improves to 6.96 dB.
- The estimated HF touch current drops from 0.045 to 0.018 mA (section 7).

**Other limit classes (smallest change set, EMI ≥ 6 dB):**
- Stationary 0.375 mA (50 %), four changes: c23 + PS2 → MPM-20-24 + module Y removed + SCF31X. Touch current 0.324 mA, −$3.75. PS3 can stay IRM-60.
- Portable 0.5 mA (100 %), three changes: c23 + module Y removed + SCF31X. Touch current 0.419 mA, EMI 8.19 dB, −$7.80. With the module choke unchanged and C3/C4 → 3.3 nF: 0.485 mA and 6.54 dB, −$9.59 (thin on both).
- Stationary 0.75 mA (100 %), two changes: module Y removed + C3/C4 → 3.3 nF. Touch current 0.628 mA, EMI 6.54 dB, no supply change.

**Without the controller change (no c23):**
- S5 (all three → MPM) with Y 1.5 nF and L1 + module SCF31X: 0.2474 mA (2.6 µA margin, 1 %), EMI 8.25 dB, +$17.19, and a board re-layout for L1.
- It passes, but it is too thin to recommend.

## 6. Sanity: assumptions and what would flip the result

- **Margin.** The recommended set fails if the Y grows by 0.15 nF/line, or if the supply datasheet maxima are 8 % higher.
- **Worst corner.** Across the sweep (120/127/132/134.6 V, 60/50 factor 1.0 or 1.2, Y +10/+20 %, coil 31/51 pF) the worst case is 0.2472 mA, at 134.6 V (1.06 × 127), ×1.2, +20 % and 51 pF. It still passes.
- **Voltage.** 132 V (+10 %) is the committed basis. At an IEC-style 1.06 × 127 V = 134.6 V the result is 0.2459 mA at 31 pF.
- **Frequency factor ×1.2.** Neither datasheet states a test frequency. Linear capacitive scaling is conservative if the test was at 60 Hz (×1.0 gives 0.223 mA). It is exact if the test was at 50 Hz.
- **Y tolerance.** +20 % is the real tolerance: Murata RA series ±20 %, EGD08G p.8 (DE1E3RA102/152/222/332MA4BP01F, A4 leads, 10 mm pitch); TDK B32021 'M' suffix.
- **Supply basis.** MPM touch current is "max", measured input-to-output at 264 VAC. Linear scaling to 132 V assumes a capacitive path, which is the same rule the committed IRM terms use.
- **What flips it.**
  - The certifier rejecting datasheet-max summation in either direction. If measured values are allowed, the IRM supplies alone are about 14 × below their maximum (one unit, Simpex report), and the whole space opens up.
  - A choke DM leakage below about 0.3 %.
  - The HF term (next section).
- **Thermal.** Maximum ambient read from the p.3 derating curves, MPM against IRM at the g06 loads:
  - PS3 after c23 (44.5 W): MPM-65 68.5 % → 60.7 °C, against IRM-60 74.2 % → 60.3 °C;
  - PS2 at the 80 kHz corner: MPM-20 → 74.2 °C, against IRM-20 → 70.5 °C.
  - These are equivalent, so candidate 23's "PS3 bay ≤ 58 °C" item is unchanged.
  - MPM-65 input is 80–264 VAC, against IRM's 85–305 Vac; 132 V is inside both.

## 7. Outside the committed model: switching-frequency touch current (`hf_touch.py`, estimate)

The committed budget is 60 Hz only, and its README claims no number for the 35–60 kHz coil and switch-node current.

**Method:**
- Same s19b network, with the LISN sense and PE bond replaced by a body or meter network from PE to earth.
- Sources at the line crest, all harmonics up to 3 MHz.
- The HF result adds in quadrature to the 60 Hz value.

**Recommended set:**

| Meter | HF current (mA) | RSS total (mA) |
|---|---|---|
| IEC 60990 Fig. 4, weighted | 0.028 | 0.2429 |
| UL-style meter (network from memory, NOT verified against UL 101) | 0.045 | 0.2454 |
| Unweighted body current | ≈ 1.4 | (would exceed the limit on its own) |

**Tolerance corners:** with chokes −30 % the UL-style reading rises to 0.177 mA, giving an RSS of **0.299 mA (0.272 at line-cycle RMS) → FAIL**. The cause is a CM resonance near 35 kHz, from the mains-side choke and the Y caps.

The robust variant (L1 also 5.68 mH) stays at 0.0128–0.0364 mA HF across all corners, an RSS of ≤ 0.244 mA.

So the meter network and choke tolerance can flip the recommended set, but not the robust one. Measuring this is a bench item. Ask the lab which meter network applies.

## 8. temper-8d claim: pan-reflected R inside the winding

**The physics is right.**
- In s19b, `n.R(sw_a, tank_a, RPAN)` places the whole reflected and coil resistance outside the coil, and hangs the "coil-end" capacitance on `tank_a`. That node does not exist physically: its voltage is V_SW_A − I·R, about 140 V at 47 A peak and 2.9 Ω.
- The winding's terminals are SW_A and the coil/bank junction. The reflected pan loss and the copper loss are distributed in the winding, and the potential along a lumped coil runs linearly from terminal to terminal.
- The physically correct lumping is therefore the capacitance at the two terminals. The R/2 + L + R/2 split matters only for internal nodes, which carry no capacitance in their variant.
- Caveat: this is a lumped low-frequency picture, well below the coil's self-resonance.

**Effect, re-run on the key filters** (patched `build()`, controls unchanged; `results/emi_rin.json`):

| Filter | s19b minimum → RIN minimum | Earthed pan (INFO) |
|---|---|---|
| E00 committed | 6.50 → 6.50 (binding X −20 %, DM 70 kHz; nominal 10.48 unchanged) | 2.62 → 8.37 (reproduces temper-8d T1) |
| Recommended (2.2 nF + module SCF31X) | 8.19 → 9.86 | 3.32 → 13.59 |
| Robust | 11.51 → 11.51 | 6.96 → 14.28 |
| 1.5 nF + module SCF31X only | 4.86 → 8.29 | — |

- The scorecard's `emi_min_margin_dB` (10.48) and the committed design's compliance minimum (6.50) **do not change**.
- The coil-limited scenarios gain 1.7–3.4 dB.
- **The recommended change set does not change**, because it passes in both models.
- RIN would let the no-c23 route (S5, Y 1.5 nF) work with the module choke alone, without L1, but the leakage margin there is still 2.6 µA. I did not adopt it.
- HF touch current under RIN: recommended 0.027 / 0.043 mA (0.168 mA with chokes −30 %); robust 0.015 / 0.017 mA. The section 7 conclusion is unchanged.
- I did not re-check temper-8d's dither and bank-split claims (out of scope).

## 9. Coordination items

1. **D-22 inlet module (another board/owner):**
   - remove the 4 Y caps;
   - change the CM choke to SCF31X-220-2R1A011JH and confirm it fits the 110 × 80 × 50 mm envelope;
   - keep the 2 × 41 µH DM inductors (still no MPN);
   - the choke's DM leakage is unpublished: measure a sample, because below about 0.3 % the margin drops toward 6 dB;
   - its price is from a search snippet (Farnell ES order code 4728656, EUR 14.41 at 1 / 8.47 at 1000) and was not verified.
2. **Controller:** candidate 23 (J13 rail merge), already requested in `c23-supply-topology/CONTROLLER-REQUEST.md`.
3. **Enclosure:**
   - PS3 bay air ≤ 58 °C is unchanged with MPM-65;
   - the coil shield is the only lever that also fixes the earthed pan under s19b's tank model.
4. **Certifier** (adds to CERTIFIER-PACKET / QUEUE "Leakage basis"):
   - limit class (portable 0.5 against stationary 0.75);
   - whether datasheet-max summation is required;
   - whether the 50 % budget is the project's rule or the lab's;
   - MPM approvals are IEC/ES/CSA 60601-1 and "Design refer to BS EN/EN60335-1 (by request)", not UL 62368-1 like IRM-60, so acceptance in a UL 1026 / UL 858 appliance must be confirmed;
   - **which leakage meter network applies at 35–60 kHz** (section 7);
   - P3 and R38-open, if those routes are wanted.
5. **Parts flagged:**
   - SCF39XV-200-Z2R1A012JH (c29's 3.6 mH choice) is a 6-pin part with an N1 winding of 4.14 mΩ against P1–P3 windings of 11.96 mΩ (spec sheet 2026-10-15), which looks like a multi-line choke. Its fit for a 2-wire L/N filter is not confirmed, and its lead time is 37–68 weeks.
   - SC-20-201 is too weak once the module Y is removed.

## 10. Sources (fetched 2026-10-15; files in `downloads/`, SHA-256 prefixes in `results/datasheet_check.json`)

- MEAN WELL IRM-20-SPEC 2025-11-21, p.2 (LEAKAGE CURRENT < 0.25mA/277Vac), p.3 Case 219A: https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF
- MEAN WELL IRM-60-SPEC 2025-11-21, p.2 (< 0.25mA/277Vac), p.3 derating, p.4 Case IRM60: https://www.meanwell.com/Upload/PDF/IRM-60/IRM-60-SPEC.PDF
- MEAN WELL MPM-20-SPEC 2024-10-30, p.2 (Touch current < 80µA/264VAC, Note 7), p.3 derating, p.4 Case 219A: https://www.meanwell.com/Upload/PDF/MPM-20/MPM-20-SPEC.PDF
- MEAN WELL MPM-65-SPEC 2024-10-30, p.2 (Touch current < 100µA/264VAC, Note 6; 80–264 VAC; 65 W; ST 109 × 52 × 33.5 mm), p.3 derating, p.4 Case IRM60: https://www.meanwell.com/Upload/PDF/MPM-65/MPM-65-SPEC.PDF
- Murata Reference Specification, Type RA, EGD08G (Jun 2023), p.8: https://datasheet.lcsc.com/datasheet/pdf/f890fd62e2f832e0bca1deac34b68fec.pdf?productCode=C907949 (the copy the repo ledger uses)
- KEMET/YAGEO spec sheets generated 2026-10-15, p.1: https://search.kemet.com/download/specsheet/SCF31X-220-2R1A011JH, .../SC-20-201, .../SCF39XV-200-Z2R1A012JH
- TDK B82726S2203A020, from the repo datasheet ledger (May 2026 sheet, p.4).
- Prices:
  - repo `STOCK-2026-10-13.csv` (IRM-20, module Y, TDK choke, C3/C4) and `PLAN-16.md:44` (IRM-60-15ST $17.30);
  - search snapshots, est: MPM-20-24 Jameco $12.60 and Master Electronics $12.30 at 20+; MPM-65-15ST Jameco $24.00 at 20+; SCF31X Farnell ES snippet;
  - SCF39XV from c29 (element14.cn CNY 176.39).
