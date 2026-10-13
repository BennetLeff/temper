# Round 2: thermal margins at 28 A (r2-thermal, stage 20 board)

Everything below reruns with `python3 -I` from this folder. The B3 model is a **copy** of the committed one (`round5copy/`, paths patched to the repo; originals untouched, `chain.sh` not run). Controls reproduced before use: converged model 1 mm c28 h25 peak 120.4 C and 0.25 mm 125.2 C (committed b3-convergence tables); legacy model 135.97 C (scorecard `b3_c28_h25_peak_C` 136.0); FET Tj 129.0 / 134.5 / 140.1 C at 40 / 45 / 50 kHz (round-6 `board-side-fets.csv`).
Re-run: `export R2_CACHE=<scratch dir>; python3 -I b3_rerun.py --scenario L1_15A_dc20 --op c28 --h 25 --pitch 0.25` (about 4 min), `./run_sweeps.sh`, `python3 -I f12_l1_mot.py`, `fet_tj_levers.py`, `bank_caps_limits.py`, `fw_derate.py`, `summarize_sweeps.py` (outputs in `results/`, `runs/`).

## 0. Findings that change the margin table (desk, no hardware)

**F12 step 1: L1 at the 15 A envelope. PASS** (`f12_l1_mot.py`, `results/f12.json`; B3 0.25 mm, c28, h25).

| L1 heat | L1 winding | C5 | C6 | PS2 case | board peak |
|---|---|---|---|---|---|
| 1.229 W (11.7 A, as modelled) | 67.5 C | 77.9 | 74.5 | 96.2 | 125.2 |
| 2.025 W (15 A, 2 x 4.5 mOhm typ, 20 C) | 77.2 C | 78.5 | 74.9 | 96.5 | 125.2 |
| 2.70 W (reviewer bound = hot-copper DCR) | 85.5 C | 79.0 | 75.3 | 96.6 | 125.2 |

- Margin to 125 C at the bound: **39.5 K** (criterion 15 K). Neighbours move at most +1.1 K (C5), +0.4 K (PS2).
- **The 125 C limit is now sourced** (it was "unverified"): TDK B82726S22*3A020 datasheet 5/26 (https://www.tdk-electronics.tdk.com/inf/30/db/ind_2008/b82726s22x3.pdf) p.4 climatic category 40/125/56, rated 20 A at TR 60 C; p.5 derating curve. Read from the plot (+-0.03): Iop/IR 0.80 at 80 C, 0.52 at 100 C, so **15 A (0.75) is allowed up to about 83.6 C air; 11.1 A up to about 97.5 C.** A lumped model calibrated on that curve gives winding 82 / 93 / 105 C at 15 A in 50 / 60 / 70 C air. So the test is **local air at L1 <= about 80 C**, which B3 does not compute. AC copper and core loss are not quantifiable from the datasheet (DM leakage flux only; line-frequency skin effect nil); the 2.7 W bound covers them unless core loss exceeds about 0.7 W (a bench IR on the winding settles it).
- No hardware change needed. Rescoring: MAG-09 can cite this.

**F12 step 2: R5.4 against laminate MOT 130 C: FAIL the 5 K rule.** MOT 130 C is the NP-155F datasheet value (`08-manufacturing-package/native-21/sourcing/inquiries/CTI-JLC.md:37`).
- Scorecard legacy peak 136.0 C is **-6.0 K** (but see Section 3: the legacy peak sits on R5.4 only until it is lowered; below 133 C a U42 point-deposit artifact at (14.5, 56.5) takes over).
- Converged model: R5 pad max cell **129.4-129.5 C = +0.5 K margin** (1 mm block mean 129.1). Under 5 K, so 28 A needs the bench IR point at R5.4 (RESOLUTION-PLAN F12.2).
- Sensitivity (`results/f12.json`, 0.5 mm tank-current sweep plus the 6.7 K mesh offset): the converged pad peak is 99 / 107 / 115 / 119 / 123 / 129.5 C at tank RMS 22 / 24 / 26 / 27 / 28 / 29.4 A, about 4.6 K per A. **5 K of margin needs tank RMS <= 28.4 A, i.e. a 27.0 A ceiling** (the 28 A ceiling trips at 29.4 A).

**Film-cap limits re-read from the TDK catalogue** (`bank_caps_limits.py`; MKP_B32651_658.pdf 6/26, https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/MKP_B32651_658.pdf p.35, p.64; this PDF is TDK's, not committed): B3265*A/G/J/T is rated TR 85 C, **upper category temperature 100 C (40/100/56), maximum operating temperature Top,max 110 C** (Top = TA + self-heating), voltage derating 1.25 %/K above 85 C, and IRMS x F_T(TA) above 85 C (F_T 0.89 / 0.77 / 0.63 at 90 / 95 / 100 C, 0 at 110 C). B3 assumed 105 C.
- HF films C38-41 (B32652A0104K000): margin (estimate + convergence uncertainty, c28 h25) to 105 C as modelled 5.0 K (C40), **to Top,max 110 C: 10.0 K (C40), 12.4 (C38)**, **to the 100 C category limit: 0.0 K (C40), 2.4 (C38)**. Which limit governs is a lifetime vs absolute question for TDK; I would take 110 C as the hard limit and require the bench IR on C40 to read <= 100 C at 28 A. At 99 C the DC rating derates to about 825 V against a 460 V clamp: fine.
- Bank (B32654A1104J000, same catalogue): TDK gives **no credit below 85 C air**, so cooler air does not move `bank_ratio_tdk_28A_40k` (1.022). Above 85 C local air it worsens fast (1.14 at 90 C, 1.32 at 95 C). The question is the bank body air temperature, not the board.

## 1. Proposals, ranked by margin per dollar and risk

| # | Proposal | Cost @500 | Margin gained | Risk / effort |
|---|---|---|---|---|
| R2-1 | Specify and verify the FET interface bond line (HTCP20S, 2 x <= 50 um) | $0 | FET Tj -9.4 K (BLT 50 um) to -13.7 K (25 um) | med (needs per-FET bench dT), process |
| R2-2 | R5.4: 4 more vias in the pad | $0 | R5.4 pad -3.6 K; legacy metric 136.0 -> 133.2 | low-med, local re-layout |
| R2-3 | Firmware: frequency floor that rises with current, plus ceiling 27 A until bench IR | $0 | bank 1.022 -> 0.99; R5.4 +0.5 -> +5.3 K | low (but see trade-off) |
| R2-4 | Airflow ask to temper-f7: local h >= 30 W/m2K on the FET-row band | enclosure | peak -7.5 K, C40 -6.5 K, bank -2.8 K, PS2 -2.9 K | med (owner) |
| R2-5 | K1 skived sink (already DECISIONS 15's contingency) | not in my data | FET Tj -11.9 K | med (owner) |

### R2-1. FET interface: replace the conservative bond-line with a specified one (SAFETY-adjacent, process)

- **Change:** none to the BOM. The stack stays 2.0 mm AlN (IEC 60335-1 29.3.1(a), unchanged) with Electrolube HTCP20S (2.5 W/mK; DECISIONS 2026-10-08 M11) on both faces. Add to the assembly spec: compound applied by stencil/screen, target bond line <= 50 um per face (controlled by clamp force 38-60 N per TO-247 at 25 N/cm2 per `stack_calc.py` and the lapped tile), and a per-FET dT acceptance in the M11 bench plan.
- **Mechanism:** the model's Rcs 0.634 K/W is built from a TIC1000A-class proxy (0.172-0.273 K/W per face, `m11/stack_calc.py`). With HTCP20S, R = BLT/k/A on the 151.2 mm2 minimum tab area, that proxy equals a **~105 um** bond line per face. 50 um gives Rcs 0.353 (AlN 0.088 + 2 x 0.132); 25 um gives 0.220.
- **Effect** (`fet_tj_levers.py`, controls pass; worst FET, 28 A, 120 V, S8 sink, 13 CFM, 50 C inlet):

| Rcs | 40 kHz | 45 kHz | 50 kHz |
|---|---|---|---|
| 0.634 (as modelled) | 129.0 | 134.5 | 140.1 |
| 0.485 (BLT 75 um) | 123.9 | 129.1 | 134.3 |
| 0.353 (BLT 50 um) | **119.6** | **124.4** | 129.2 |
| 0.220 (BLT 25 um) | 115.3 | 119.8 | 124.3 |

 Sustained ceiling that holds 125 C at 40 kHz: 26.6 A now, 30.0 A at 50 um.
- **Scorecard:** none of `b3_*` or the bank metric moves (FET Tj is not on the card). B3 copper: lead conduction sign (-5.6 / +0.5 K) shifts slightly; not computed.
- **Interfaces / SAFETY:** this is the HOT-to-PE insulation stack. The solid-insulation route (2 mm AlN) and the 8 mm creepage geometry are untouched; a thinner compound layer does not shorten any creepage path, but the filler must stay non-conductive (HTCP20S is). Pump-out and thickness drift over thermal cycling are unknown; bench dT at start and after cycling. Owner: enclosure (clamp force), sourcing (stencil). Needs certifier only if the compound or tile changes.
- **Risk:** med: it moves a number from "conservative" to "specified"; it is only real once measured. **Effort:** process + bench.

### R2-2. R5.4 pad: four more vias to In1 (hv_ret)

- **Change:** R5.4 (hv_ret pad, F.Cu, x 36.8-40.2, y 14.3-16.1). Add 4 x 0.5 mm drill / 0.8 mm pad vias to In1 hv_ret at (37.3, 14.7), (38.1, 15.6), (39.0, 14.7), (39.8, 15.6), subject to the existing ones and DRC (positions are the model's, not a DRC-clean layout). This is the same field as g02-g03 Proposal C (>= 7 vias, for the fusing neck); one edit serves both.
- **Mechanism:** the pad sits at 125 C on a 113 C In1 plateau; heat leaves through the via barrels (18 um wall in the model, a conservative figure).
- **Effect** (`edits.json`, `b3_rerun.py --edit r54_vias4`, 0.25 mm): R5 pad max 125.2 -> **121.6 C (-3.6 K)**, element 136.2 -> 134.3 (-1.9 K). Applied to the converged value 129.5 -> about 125.9 C, **margin to MOT 0.5 -> 4.1 K** (still under 5 K, so the bench IR point stays). Legacy 1 mm `b3_c28_h25_peak_C`: 136.0 -> **133.2** (-2.8 K), and then it is pinned by a U42 point-deposit artifact at (14.5, 56.5): it will not fall further whatever is done at R5.
- **Interfaces:** R5 Kelvin (ocp_kelvin_p/n pads 2/3, G08: do not touch them; rerun the Kelvin band), hv_ret In1 pour, fusing neck (improves). Not touched: barriers, J4.
- **SAFETY:** none new (current path R5.4 -> hv_ret is unchanged; fusing ratio improves).
- **Risk:** low-med. **Effort:** local re-layout (R5/U6 corridor, already reopened by candidate 21). Cost $0.

### R2-3. Firmware: current-dependent frequency floor and the 27 A step

`fw_derate.py` (`results/fw_derate.json`, S8 sink, Rcs 0.634): the margins pull the frequency in opposite directions. FET Tj rises 5.5 K per 5 kHz at 28 A; the bank ratio falls (1.022 / 0.992 / 0.950 at 40 / 45 / 50 kHz). At 28 A:

| f | FET Tj | margin to 125 | bank ratio |
|---|---|---|---|
| 40 kHz | 129.0 | -4.0 | 1.022 |
| 45 kHz | 134.5 | -9.5 | 0.992 |
| 50 kHz | 140.1 | -15.1 | 0.950 |

So at 28 A no frequency satisfies both on the conservative interface; **only with R2-1 (BLT 50 um) does 44-46 kHz do (Tj 124.4 C, bank 0.992 at 45 kHz).** Bank ratio <= 1.00 needs f >= 43.7 kHz at 28 A; <= 0.95 needs 50.1 kHz.
- **Change:** (a) hold the commissioned ceiling at **27 A** until bench IR clears R5.4: R5.4 +5.3 K margin, bank 0.986 at 40 kHz, Tj 126.0 at 40 kHz (-1.0 K, vs -4.0 at 28 A); (b) after R2-1 is measured, use f >= 44 kHz above 27.4 A (the allowed tank current at 40 kHz is 27.4 A, 28.2 A at 45 kHz).
- **Yield cost not computed:** a 27 A ceiling affects the 85 % full-power yield at 28 A (DECISIONS 10); needs the round-6 grid.
- **Scorecard:** `bank_ratio_tdk_28A_40k` is defined at a fixed 40 kHz and does not move.
- **Interfaces:** firmware / controller (frequency window, G04 tank, F10 EMI floor: higher f helps the EMI floor issue). Risk low, effort firmware only.

### R2-4. Airflow ask (temper-f7; list only, nobody contacted)

Uniform-h sweep on B3 (0.5 mm, c28; `run_sweeps.sh`, `results/sweeps.json`): h 25 / 30 / 35 / 45 W/m2K gives board peak 122.9 / 115.4 / 109.7 / 101.7 C, R5 pad 122.8 / 115.3 / 109.6 / 101.6, C40 96.3 / 89.8 / 85.0 / 78.5, bank C21 88.7 / 85.9 / 83.9 / 81.1, PS2 case 95.3 / 92.4 / 90.2 / 87.0. Legacy peak 136.0 / 128.1 / 123.1 / 116.9.
- **Ask:** deliver h >= 30 over the FET row band (board x 20-80, y 0-35: the copper plateau and C38-41), and hold it over C21-C23/151/152 and PS2. A flat-plate estimate h = 5.7 + 3.8 v puts h 30 at about 6.4 m/s (**ESTIMATE**, not a CFD result); this uniform-h run overstates a local gain because the rest of the board stays at 25 and the model has no air heating, so treat -7.5 K as an upper bound. Also needed: local air temperature at PS1, PS2 (g06 gives allowed 70.5-76.7 C for PS2), L1 (<= 80 C at 15 A, Section 0), C5/C6 and the bank (<= 85 C, TDK has no credit below).
- **Scorecard:** `b3_c28_h25_peak_C` moves only through h; recorded as h25 so it would not change unless the case definition does.
- **Risk:** med (enclosure noise/pressure; h 30 is +20 % on the blower). Cost not in my data.

### R2-5. K1 sink (DECISIONS 15 contingency)

`fet_tj_levers.py`: K1 (R_SA 0.214 + pedestal) with the conservative interface gives 117.1 / 121.8 / 126.6 C at 40 / 45 / 50 kHz (-11.9 / -12.7 / -13.5 K); with R2-1 at 50 um, 108.2 / 112.2 / 116.3. (DECISIONS 15 states 118.9 / 123.8 / 128.7 for K1 at its own flow; my solve is 1.8-2.1 K lower, so use DECISIONS' numbers for the claim.) Trigger stays as recorded: bench switching loss > 125 W at 28 A. Cost and lead time: enclosure owner.

## 2. Considered and rejected

- **hv_ret F.Cu pour beside R5.4** (5.5 x 2 mm at x 41-46.5, y 15.2-17.2): -0.1 K (`r54_pour`). The heat leaves through the vias, not in-plane on 70 um copper.
- **Heavier copper:** the stack is already 2 oz on all four layers (`native-17/stackup.json`); I have no JLC heavy-copper price or rule data. Not evaluated.
- **L1 change:** none needed (Section 0; 39.5 K margin at 2.7 W). L1's zero stock is g01's problem.
- **Lower-ESR HF caps:** C38-41 heat is board copper (0.05 W self-heat), not ESR. A higher-temperature part would be the lever, but I found no stocked >= 125 C film or C0G at 100 nF / 1 kV, did not search further, and the MLCC route is the g02-g03 Proposal E commutation-loop question. Not recommended.
- **Capacitance binning to +-2 %** (select-on-test): bank ratio 1.022 -> 0.975 (+-3 %: 0.991); TDK sells J (+-5 %) as its tightest, so it is labour and part loss; and the same gain comes free from f >= 44 kHz (R2-3).
- **1 mm AlN:** saves about 0.05 K/W (about 1.5 K) but loses the 29.3.1(a) route to a lab assessment. No.
- **SiC / other FET (650 V, lower hot Rds(on)):** CFD7 is 18 mOhm typ, about 35 mOhm at 125 C in this model; a SiC part needs 18 V drive and a different Qg/Coss behaviour, breaks the F6 decks and gate network, costs several times more and I could not verify TO-247-3 stock or Rds at Tj from datasheets in this session. Rejected as high risk and unverified.
- **R5 to a lower resistance:** halving it halves the sense signal into the Kelvin band and the 64.17 A trip floor already sits at the bound (DECISIONS 14). No.
- **PS1/PS2:** g06-g08-g10 already shows the right test is local air (PS2 allows 70.5-76.7 C); I add only that B3 shows PS2 case -2.9 K at h30 and +0.4 K from L1 at 15 A.
- **C5/C6:** unaffected (27 K margin; +0.6-1.1 K from L1). B32676G datasheet not retrieved (path 404), so their own Top,max is unconfirmed.

## 3. Notes for the lead

- The scorecard `b3_c28_h25_peak_C` (legacy point-deposit model) is not a physical measure: after R5.4 is relieved it floors at about 129-133 C at U42 (14.5, 56.5). The converged number (129.4 C at R5.4) is the one to track against MOT.
- Mesh offsets: 0.5 mm values in Section 1 are deltas; converged absolute values are +6.7 K (R5 pad) from the committed 0.0625 mm result.

## 4. What I could not verify

- L1 core/AC loss and local air; L1 derating curve is read by eye from a plot (+-0.03 in Iop/IR).
- Local airflow numbers (h to velocity is a textbook estimate; no CFD); K1 cost; yield cost of a 27 A ceiling; HTCP20S real bond line on the lapped tile.
- Prices, stock, and LCSC codes for any new part: none proposed, so none checked (R2-1..R2-5 are all existing parts or process).
- TDK B32676 (C5/C6) limits; Mean Well IRM-20 curve (taken from g06).
