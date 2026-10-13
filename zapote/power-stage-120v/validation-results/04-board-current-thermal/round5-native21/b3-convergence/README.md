# B3 thermal model convergence study, stage 19b (board b19a4553...)

Study and model improvement only. No board, copper or schematic edit. `../b3/*` is untouched and still reproduces the old numbers.

## Pass criterion (written before the new-model results were computed)

A reported quantity is **CONVERGED** when, for the two finest meshes in which it is computed (0.125 -> 0.0625 mm in a nested window, else 0.25 -> 0.125 mm window), the change is **< 2 K**, and the Richardson extrapolation uncertainty (|Q_extrapolated - Q_finest|, order p observed from the three finest levels, clipped to 0.5-3; for non-monotone sequences the sum of the last two increments) is **< 2 K**. Reported value = extrapolated value; margins below use "estimate + uncertainty". Quantities per part: (a) pad-copper area-weighted mean and maximum cell, (b) junction/element temperature from the package network. A "pad max cell" is the hottest mesh cell that is >= 50 % covered by the part's mounting-layer pads.
Controls (asserted by `report_convergence.py`, exit 1 on failure): C1 legacy mode reproduces the committed 28 A h25 ceiling-sweep peak (136.0 C) within 0.1 K; C2 energy balance closes to < 0.1 % on every run; C3 a uniformly heated disc on a fin plate matches the Bessel solution within 3 %.

## Results of the controls (all PASS)

| control | result |
|---|---|
| C1 | legacy mode 135.95932463 C vs committed 135.95932462 C (diff 3e-9 K); `thermal.py` subprocess identical; committed 0.5 mm run 182.2695 C reproduced to 1e-8 K |
| C2 | 102 solves, worst relative imbalance 1.5e-8 (limit 1e-3) |
| C3 | disc (a = 3 mm, 0.25 mm mesh): mean rise error 6.7e-5, junction error 2.9e-5 (limit 3e-2); committed strip and through-thickness oracles pass |
| C4 (extra) | a 0.25 mm window with boundary values from the global solution reproduces the global field to < 4e-7 K |

Note on inputs: the `outputs/*-heat.npz` copied from ps-integrate were stale (stage 19), so the 14 A4 cases used were regenerated with the committed `run_cases.py`/`run_board.py` on the stage-19b board. Their JSON outputs are byte-identical to the committed ones (`git status` clean); only the gitignored npz changed.

## 1. Mesh sensitivity reproduced, and what drives it

Legacy model (committed `thermal.py`), c28 h25: peak **136.0 / 182.3 / 142.8 C** at 1 / 0.5 / 0.25 mm, at three different places (R5.4; U41 pad; U42 pad). Nominal h25: 129.1 / 180.8 / 139.9 C. This is the review's 133 vs 182 C, reproduced on stage 19b.

Four-way ablation (c28 h25 single-cell peak, 1 / 0.5 / 0.25 mm; plot `board-peak-vs-mesh.png`):

| model | peak C |
|---|---|
| legacy: binary copper, point deposit | 136.0 / 182.3 / 142.8 |
| binary copper + package network | 130.9 / 144.7 / 131.9 |
| copper fill-fraction + point deposit | 123.6 / 125.5 / 130.2 |
| fill-fraction + package network (new) | 120.4 / 122.9 / 125.2 |

Decomposition (`results.json` -> `decomposition_c28_h25`): with part heat removed the copper-Joule field alone peaks at the FET row (In1/In2/B.Cu near x 50, y 4-6) at 124.6 / 119.8 / 120.6 C (legacy raster) and 111.9 / 114.1 / 114.9 C (fill-fraction): a genuine copper bottleneck, moderate mesh sensitivity. With copper heat removed the part heat alone peaks at **125.5 / 179.4 / 137.4 C in the legacy model** (U41/U42/U26/U3 pad cells) and 81.2 / 82.4 / 83.3 C in the new one. So the non-convergence is (i) the point deposit into whichever binary-raster pad cells the cell centres hit (U41 pad max 102 / 182 / 134 C, U42 92 / 152 / 143, U26 86 / 129 / 117, U3 67 / 96 / 87; deposit areas change by 1-4x and isolated binary copper cells strand the heat) plus (ii) the binary copper mask. It is not a genuine bottleneck at U41/U42: their area-mean pad temperature is about 76-78 C on every mesh once the source is a flux over the true pad area. The R5.4 / FET-row copper is the genuine bottleneck, and it is slowly convergent: single-cell peak at R5.4 120.4 / 122.9 / 125.2 C (p about 0.2, global meshes) and **129.4 C at 0.0625 mm** (1 mm-block mean 129.1 C).

## 2. New model (`thermal_body.py`)

Same 7-sheet board; per heat-generating part a junction node joined to its pads through the datasheet junction-to-board (or junction-to-exposed-pad) resistance, flux distributed over exact pad/cell overlap areas, junction-to-case(top) + convection h on the body top to ambient (the same h as the board faces), copper fill-fraction cells from a 0.0625 mm supersampled mask. Package values and sources (`SPECS` in the module; datasheets downloaded to scratch, not committed):

| part | network | source |
|---|---|---|
| U41/U42 RECOM R24C2T25/R | 25.9 K/W to PGND and VOUT- pads, 16.6 K/W to case, body 12.83 x 7.5, Tj max 150 | RECOM Rev.1-2024 p.8, p.13, p.12, p.1 |
| U26 TPS7A4700 RGW | 1.7 K/W to the exposed pad (21), 27 K/W to case; Tj <= 125 | TI SBVS204G p.5, p.21 |
| U1/U2 UCC21550 DWK | 32.8 K/W to pads, 34.1 K/W case; Tj 150 | TI UCC21550 p.5, p.1 |
| U3/U37-39 TPS70950 DBV | 39.5 / 78.5 K/W; Tj 125 | TI TPS709 p.4 |
| R5 CSS2H | 20 K/W element-to-terminal derived from the vendor derating curve (5 W at 70 C terminal to 0 W at 170 C); G6 rule | `../stage17-r5/screen.py` (Bourns site returned 403; not re-fetched) |
| 1206 chip resistors | 33 K/W derived (alumina, k = 24 W/mK); 155 C limit is vendor-typical, **not verified** | derived |
| film caps, IRM-20, L1 | class values **assumed** (leads / pins); TDK pages returned 403; limits from the repo's round6 README (105 C category, TDK 85 C ripple curve) and the Mean Well IRM-20 spec (85 C **ambient**) | assumed |
| CFD7 TO-247 (Q2/3/5/6) | as the old model: no heat deposited (path to sink); only lead-copper temperatures reported | unchanged |

Sensitivity (0.5 mm, `results.json`): junction minus pad scales with the assumed resistance (x2 gives U41/U42 +22 K, R5 element +16 K, U26 +1.4 K); body convection h x0.5 changes < 4 K; heating all pins instead of the RECOM thermal pins < 1.5 K; including an underside air-gap conduction path lowers PS1/PS2 by 12-18 K (baseline excludes it, so conservative). Parts with a sink fraction (bank caps, PS1, PS2) model only their board share of the loss.

## 3. Convergence of the new model

Levels 1 / 0.5 / 0.25 mm global, 0.125 mm refined windows for every part, 0.0625 mm nested windows (boundary values from the 0.125 window) for R5, U41, U42, U26/U37, R39, PS1, PS2, R58. The drift seen on the global meshes (e.g. U26 pad mean 75.5 / 76.5 / 78.4 C) is copper-feature resolution (0.15-0.25 mm traces and antipads) and **saturates**: 0.125 -> 0.0625 mm changes are 0.0-0.8 K for every part that has both. All converged-per-criterion parts are marked in `RESULTS-TABLES.md` (full tables, levels per part). Not meeting the criterion: R58 (non-monotone: 108.9 at 0.25, 105.8 at 0.0625; 4 K uncertainty), R53, R68, R69 and the 0.125-only parts that did not stabilise (all with > 40 K margin); the FET-lead copper (Q3: 112.3 / 113.0 / 113.4 / 115.6 C) and board peak remain only to about 2-3 K.

## 4. The 28 A conclusion, restated

Converged estimates at the 28 A ceiling case (tank 29.4 A RMS), 50 C ambient (limit quantity in the column header; margin = limit - (estimate + uncertainty); full numbers in `RESULTS-TABLES.md` and `results.json`).

| part | pad mean / pad max C (h25) | junction / element C (h25) | limit | margin h25 | stall-derated 14 A, h10: junction C (margin) | status |
|---|---|---|---|---|---|---|
| R5 CSS2H shunt | 123.7 / 129.5 | 140.1 | terminal 148.4 (derating, 20 % power margin; 160 C pad gate) | 18.8 K | 95.0 (67.7 K) | margin, converged to 0.0625 mm |
| U41/U42 RECOM | 78 / 92.6 | 105.1 | Tj 150 | 44.9 K | 123.2 (26.8 K) | margin; x2 on theta-JB would give 127 / 145 C (thin in stall) |
| U26 TPS7A4700 | 83.8 / 88.7 | 88.9 | Tj 125 | 36.0 K | 102.4 (22.5 K) | margin |
| U1/U2 UCC21550 | 73 / 80.5 | 79.0 | Tj 150 | 69.8 K | 85.2 (62.8 K) | margin |
| U3, U37-39 TPS70950 | 75 / 76 | 78.5 | Tj 125 | 45.6 K | 85.9 (39.1 K) | margin |
| gate resistors (1206) | 106 / 107 (R58) | 107 | 155 (unverified) | 43.5 K | 87.4 (64 K) | margin; hot only because of the FET-row copper |
| other 1206 resistors | 70 / 70 | 72 | 155 (unverified) | 81 K | 76.6 | margin |
| bank film caps C21-23, 151, 152 | 77 / 78 | 89.5 (board share only) | 105 category | 15.3 K | 69.2 (35.8 K) | **bench IR** (70 % of loss and winding hot spot not modelled; 1.12x TDK 85 C curve per round6) |
| HF film caps C38-41 | 96 / 99 | 98.7 | 105 | 5.0 K | 86.8 (17.6 K) | **bench IR**; heated by the FET-row copper |
| C5/C6 | 64 / 67 | 78 | 105 | 26.7 K | 65.6 | bench IR (assumed lead resistance) |
| L1 mains choke | 64 / 66 | 68.6 | 125 (unverified) | 55.8 K | 79.8 | bench IR |
| PS1 IRM-20-15 | 74.9 / 76.9 | 86.2 | 85 **ambient** rating | -1.3 K | 94.9 | **bench IR** (rating is ambient, not pin/case) |
| PS2 IRM-20-24 | 86.0 / 90.2 | 98.2 | 85 **ambient** rating | -13.4 K | 105.1 | **bench IR** |
| FET-lead copper (Q2/3/5/6) | 118 / 126 (Q3) | n/a | laminate Tg 150 | 20.8 K | 89 / 91 (58 K) | not converged better than ~3 K; FET Tj is the sink study |
| board copper peak | 1 mm-block 129.1 C at R5.4 (0.0625 mm) | | Tg 150 | about 21 K | 92 C at R5.4; module region 107 C | R5.4 region sets the peak |

Verdict. With the body-level model every part that has a datasheet junction or terminal limit **has margin at 28 A, h25** (smallest: R5 terminal, 18.8 K to the 20 %-margin derating rule, 40 K to the raw 170 C curve), and the old 136.0 C "peak" was a point-deposit / binary-raster artefact: the converged R5.4 copper peak is about 129 C and the module/LDO pad temperatures the 1 mm model reported (104 / 133 C) were 77 / 92 C converged. The 28 A h25 claim therefore **survives for the semiconductor, driver and resistor parts**. It does **not** become a validated claim for the bank capacitors, HF caps, PS1/PS2, L1 and C5/C6: their limits are ambient or hot-spot ratings, their package paths are assumed, and the bank and PS1/PS2 are modelled only through their board share. Those depend on bench IR. In the stall case (derated to 14 A, h10) the same parts stay inside limits with 22-27 K on the modules and U26 (thin if theta-JB is 2x the datasheet). The h10 28 A **without** derate is not supported (R5 203 C element/191 C pad, gate resistors 168 C, FET-lead copper 187 C; modules 141 C): that case relies on the stall derate, as DECISIONS 14 already says. Model limits: 2.5-D, isotropic fill-fraction mixing, conduction-only inner layers, convection h assumed, A4 Joule heat at its own 0.0625-0.125 mm resolution, package resistances from board-level theta-JB/theta-JC (conservative double counting of board spreading), no radiation, no component-to-component air coupling.

## 5. Bench IR measurement points (predicted values: c28 h25 / derated h10)

Use matte tape or paint (emissivity about 0.95) on bare copper/solder; thermocouples on the sink and two board points for air reference; steady state at 28 A tank RMS, 50 C inlet.
1. R5 pads 1 and 4 and the body: pad max 129 C / 92 C, element about 140 C / 95 C.
2. U41 and U42 body tops: 103 C / 122 C (model body-top), PGND/VOUT- pad rows 78 C / 95 C. A reading above about 125 C at h25 means theta-JB is more than 2x the datasheet.
3. U26 body top and exposed pad edge: 88 C / 102 C.
4. PS1 and PS2 case at the pins and mid-body, plus local air 10 mm above: pad 75 / 86 C, case estimate 86 / 98 C. Decide against the 85 C ambient rating using the air temperature, not the case.
5. Bank capacitor winding surface (mid-body, hottest of the five, C21 end) and lead exits: board share gives 89 C; real hot spot needs the measured value against the TDK 85 C curve.
6. C40 and C38 (HF caps nearest the FETs): 99 / 98 C.
7. FET-row copper at x 50, y 4 (In2/B.Cu under the FET row; measure Q3 and Q2 leads and the nearby F.Cu): 123-126 C / 90 C.
8. Gate resistors R58/R12: 107-110 C / 89 C.
9. L1 winding surface: 69 C / 80 C (assumed limit).

## Files and rerun

| file | content |
|---|---|
| `thermal_body.py` | body-level model, package specs with citations, analytic disc control |
| `body_runs.py` | one global or windowed solve + per-part metrics |
| `run_convergence.py` | compute stage: `--stage global|windows|fine|all`, <= 4 workers |
| `report_convergence.py` | controls, Richardson, tables, plots, `results.json`, `RESULTS-TABLES.md` |
| `extract_bodies.py`, `inputs/part-bodies.json`, `inputs/heat_der14.json` | derived inputs (board file sha256 recorded) |
| `runs/*.json` | every solve (102) |
| `board-peak-vs-mesh.png`, `parts-vs-mesh.png`, `verdict-vs-limits.png` | plots |

```
cd zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21
# once, if outputs/*-heat.npz are stale or missing: WORKERS=4 python3 run_cases.py   (about 1 min for the 14 cases used)
cd b3-convergence
python3 run_convergence.py --stage all --workers 3 --fresh   # about 65 min on a 12-core Mac (global 30, windows 17, fine 17)
python3 report_convergence.py                                  # about 2 min; exit 1 if a control fails
```
Limitations: converged status is shown only where finer meshes exist (0.0625 mm for R5, U41, U42, U26, U37, R39, PS1, PS2, R58; 0.125 mm for the rest); fine windows depend on boundary values from the 0.125 mm parent; nested windows near R58/FET row/PS2 are edge-limited (peaks within 5 mm of a window edge are flagged unusable in `results.json`); no experimental validation. The old h10 stall study (`../h10-stall/`) was computed on an earlier board and with the legacy model; this study re-derives its operating points on stage 19b.
