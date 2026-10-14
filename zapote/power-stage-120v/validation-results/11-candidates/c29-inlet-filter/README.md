# C29: move the D-22 inlet filter onto the power board with a leakage-sized Y (desk study, 2026-10-13)

Nothing was built, committed, sent or ordered, and no existing file was edited. Every number comes from the scripts in
this folder (`python3 -I <script>`). Each script writes its own `.json`, and the console output is in the matching `.log`.
The EMI numbers come from the committed s19b model, which is called read-only through g01's wrapper. "est" marks an
allowance that has no price or data source.

| Script | Computes | Output |
|---|---|---|
| `c29_leakage.py` | Y budget per line for each supply set and limit; touch current of each candidate. Its controls reproduce 0.974 / 0.693 / 0.551 / 0.408 / 0.364 mA and 1.16 / 5.95 nF | `c29_leakage.json/.log` |
| `c29_emi.py scan` | 960-point nominal screen of total Y, Y position, L1, stage-1 CM choke, DM inductor and coil shield (fs step 2 kHz) | `c29_emi_scan.json/.log`, `c29_scan_summary.txt` |
| `c29_emi.py final` | Named candidates at a 1 kHz step with a 0.5 kHz re-check, g01's 8 one-at-a-time sensitivities and the pan-earthed INFO case. Its control reproduces the scorecard's 10.479 dB | `c29_emi_final.json`, `c29_emi_final*.log` |
| `board_area.py` | Courtyard occupancy and free rectangles on the s27 board (`runs-native21/s27/s27b/section.kicad_pcb`, sha 44644390…, text parse only) | `board_area.json/.log` |
| `c29_cost_area.py` | System cost at 500 boards (module removed vs on-board parts added), placements, lines and the area needed | `c29_cost_area.json/.log` |

## Recommendation: CONDITIONAL GO, with candidate 23's PS1 deletion. On its own it does not fix leakage.

**Design of record (C29-B):**
- Delete the D-22 module, including all of its Y capacitors.
- Keep C3/C4 at 2.2 nF Y1 as the only line-to-PE Y: **2.2 nF per line in total**.
- On the inlet side of L1, add a stage-1 CM choke of 3.6–5.7 mH, 20 A, nanocrystalline (KEMET SCF39XV / SCF31X class).
- Also add D-22's 2.2 µF input X2, its 4.7 µF X2, the 3.9 Ω + 4.7 µF damping branch, the 2 × 15 kΩ bleed pair and the 2 × 41 µH DM inductors.
- L1 is unchanged.

| | Benchmark (s27) | C29-B (3.6 mH) | C29-B (5.68 mH) |
|---|---|---|---|
| Y per line, nominal | 9.1 nF | 2.2 nF | 2.2 nF |
| Touch current, Test A (datasheet max), 3 supplies | 0.974 mA | **0.562 (fails 0.5)** | 0.562 |
| Test A, PS1 deleted (candidate 23) | 0.831 | **0.419 (84 %, passes)** | 0.419 |
| Test B (5 × typical), PS1 deleted | 0.644 | **0.232 (meets the 0.25 / 50 % target)** | 0.232 |
| EMI nominal / sensitivity minimum | 10.5 / 6.5 dB | **10.8 / 6.6 dB (PASS)** | 12.4 / 8.2 dB |
| Pan earthed (INFO) | 2.6 dB | 1.7 dB | 3.3 dB |
| System cost at 500 boards | — | **−$6.74 material; about −$14.6 with labour (est)** | price not found |

Cheaper variant, adopted only after a bench measurement (C29-C): Y 2.7 nF per line, with SC-20-201 for both L1 and stage 1.
- EMI is 10.9 / 6.7 dB, and Test A with PS1 deleted is 0.449 mA (90 %). The system saves −$28.71 at 500.
- If SC-20-201's unpublished leakage inductance is 10 µH instead of the assumed 20 µH, the margin falls to **4.7 / 0.3 dB**.
- So the saving depends on a sample measurement (the same gate g01 P1 carries).

## 1. What D-22 is and where it is specified

The specification is `01-switching-parasitics/round17/delegation/out-D22/PARTS.md`. The topology is at lines 5–12, the parts at 22–28 and the cost at 56. The numbers are in `budget.py:58-79`. The DM requirement is in DECISIONS.md:477 and in item 20 (DECISIONS.md:800-816).

| Item | Part | Value |
|---|---|---|
| CM choke | TDK B82726S2203A020 | 1.6 mH per winding, 18 µH DM leakage (typical), 4.5 mΩ, 20 A; 45 × 25.5 × 41 mm |
| Input X | TDK B32923C3225K000 | 2.2 µF X2 305 VAC |
| Output X + damping X | 2 × TDK B32924D3475K000 | 4.7 µF X2; damping branch 3.9 Ω (Vishay AC05000003908JAC00) in series |
| Main Y | 2 × TDK B32021A3472M000 | 4.7 nF Y2 per conductor |
| HF Y | 2 × TDK B32021A3222M000 | 2.2 nF Y2 per conductor (**6.9 nF per line, 0.437 mA at 140 V on its own**, PARTS.md:48) |
| Bleed | 2 × Vishay PR02 15 kΩ | 30 kΩ across L–N |
| DM inductors | **none in PARTS.md.** The choke's 18 µH leakage was the only DM | DECISIONS item 20 / s19b require **≥ 100 µH DM (18 + 2 × 41 µH)**: as specified, D-22 gives **−5.1 dB** (rerun here: −5.1 / −9.8 dB). The 41 µH parts have **no MPN** (g01 P3) |
| Envelope | 110 × 80 × 50 mm (0.44 L), 8 W allowance | PARTS.md:50-54; mounted in R43 on a folded 5052 stand with 8 PEM CLA-M4-1 and 9 screws (`output/temper-manufacturing-r43/src/electronics_r20.py:22-100`, `r32_world.py:298-314`) |

**Cost:**
- Parts are **$15.90 at 500** (`sourcing/STOCK-2026-10-13.csv:204-210`; $29.54 in PARTS.md's 2026-10-03 single-unit snapshot).
- Add $15 for the carrier, terminals and cover (budget.py:66), $3 for the module-to-board harness (est, r3) and about $4 for the enclosure stand and hardware (est).
- **$37.90 per system in total**, with the DM inductors unpriced.

## 2. Y budget (132 V, 60 Hz, +20 % on Y, coil 31 pF; `c29_leakage.log`)

The touch current is 0.0597 mA per nF/line of nominal Y. Each supply adds 0.143 mA at datasheet maximum, or 0.0495 mA at 5 × typical.

| Supplies in the PE path | Test A, 0.5 mA (datasheet max) | 0.25 mA target (datasheet max) | Test B, 0.40 mA (5 × typical) | 0.25 mA (5 × typical) |
|---|---|---|---|---|
| 3 (as built) | **1.16 nF** | impossible (supplies alone 0.429 mA) | 4.18 nF | 1.67 nF |
| 2 (PS1 deleted, candidate 23) | **3.55 nF** | impossible (0.286 mA) | 5.01 nF | 2.50 nF |
| 1 (and g06 P3: PS2 off PE, a bench claim) | 5.95 nF | 1.76 nF | 5.84 nF | 3.33 nF |

The as-built board Y alone (C3/C4 at 2.2 nF) already fails Test A with three supplies (0.562 mA). The module is the dominant term, but it is not the only one.

## 3. EMI with that Y

**Model:** the s19b MNA model (`07-conducted-emi/s19b/emi_s19b.py`).
- Limit: 47 CFR 18.307(a), induction cooking (`emi_s19b.py:41-56`). Below 150 kHz it is QP only: 110 dBµV below 50 kHz, then a logarithmic fall from 90 to 80 dBµV over 50–150 kHz. Over 0.15–30 MHz the limits are 66→56 / 56 / 60 dBµV QP, and 10 dB lower for AV.
- Range: 9 kHz–30 MHz. Sweep: fs 35–60 kHz. Cases: 170 V / 22 A pan, 198 V / 28 A pan, 198 V / 22 A no-pan.
- PASS means ≥ 6 dB nominal and in every sensitivity.
- An on-board stage on the inlet side of L1 is the model's "module" network. The model has no harness, so the network is identical.

Findings (`c29_scan_summary.txt`, `c29_emi_final*.log`):
- **Y must sit at the C3/C4 node (L1 output), not on the inlet side.** At 2.2 nF with the 3.6 mH choke, moving the Y to the stage-1 output gives 5.9 / 0.1 dB, against 10.8 / 6.6 dB at C3/C4.
- **The discrete DM inductors stay.** With LNEW 0 the margin is 6.2 / 1.8 dB, and with 20 µH it is 8.7 / 4.5 dB, both against 10.8 / 6.6 at 41 µH. The binding line is the 70 kHz DM (2 × 35 kHz). F10's fs-floor route (g01 P3) is still the only way to drop them.
- **The input 2.2 µF X is needed** (−14.2 dB without it). The damping branch adds 0 dB of EMI margin (14.0 vs 14.2 dB). It stays only for D-22's input-filter stability argument (`damping-results.json`), so it could be removed if that argument is re-made.

| Y per line | Best real-part set (L1 / stage 1 / DM) | Nominal / sensitivity minimum (binding sensitivity) |
|---|---|---|
| 3.3 nF (A) | TDK / SC-20-201 / 41 µH | 11.4 / 7.1 (X −20 %) PASS; with 5.68 mH 14.2 / 9.9 |
| 2.7 nF (C) | SC-20-201 / SC-20-201 / 41 µH | 10.9 / 6.7 PASS. **4.7 / 0.3 if the SC-20-201 leakage is 10 µH** |
| 2.2 nF (B) | TDK / 3.6 mH NC / 41 µH | 10.8 / 6.6 PASS (coil + board 51 pF). With 0.3 % NC leakage: 10.5 / 6.2. With SC-20-201 instead: 8.1 / −1.8 |
| 1.0 nF (3-supply Test A) | 5.68 mH NC for both / 41 µH | 9.2 / 4.8, **INCONCLUSIVE**. Ideal 6.4 + 10 mH reaches 13.0 nominal only; a 75 % coil shield is also needed |

**Added inductance:** 3.6–5.7 mH CM at 20 A in place of D-22's 1.6 mH, plus 2 × 41 µH DM (≥ 80 % at 15 A, ≤ 8 mΩ).
- **X:** D-22's 2.2 µF + 4.7 µF + 4.7 µF damping carry over; the board's C1/C2 (1 µF) stay.
- **No added Y.**
- **Board heat:** about 1.9 W (NC choke, 4.14 mΩ × 2 × 15²) plus about 3.6 W (DM inductors, s19b README §9.5), about 5.5 W in total. That moves onto the board near the mains corner, so B3 must be rerun.

## 4. Fit, cost, placements, enclosure

**Area** (`board_area.log`, `c29_cost_area.log`):
- The s27 outline is an L of 45,150 mm². Courtyards cover 49.4 % of it.
- The added parts need about 3,960 mm² of courtyard, or 6,470 mm² with the DM inductors (33 mm toroids, est). At the board's occupancy that is **8,000–13,100 mm² of board (18–29 %)**.
- The mains corner has no free rectangle ≥ 45 × 31 mm. The largest free rectangle in the top-right quadrant is 59 × 11 mm.
- **Where it could go:** a strip added on the mains edge. The outline grows about 50–95 mm to the right (x 290 → 340–385, y 0–140), and J1, F1 and RV1 move to the new edge so the series path stays J1 → F1 → stage 1 → L1.
- Candidate 23's PS1 slot (x 206–259, y 112–140) would take the choke alone, but it is 100 mm from J1. The L/N path would then run down and back past L1, which is not recommended.
- PCB area cost is +$1.42 at 500 (r3 rate). The enclosure must accept the larger board: that is the fit gate.

**Cost per system at 500** (DM inductors excluded on both sides: they are needed either way and have no MPN):

| Variant | Parts added to the board | System net (material) | With labour (est) | Board-only scorecard `parts_usd_at_500` |
|---|---|---|---|---|
| B, 3.6 mH NC (KEMET SCF39XV-200-Z2R1A012JH, CNY 176.39 at 108+, 37 wk) | $29.74 | **−$6.74** | −$14.61 | 221.82 → 251.56 |
| A, SC-20-201 stage 1, Y 3.3 | $11.18 | −$25.30 | −$33.18 | 221.82 → 233.00 |
| C, SC-20-201 × 2, Y 2.7 | $7.77 | −$28.71 | −$36.58 | 221.82 → 229.59 |

- **Placements and lines:** 349 → 358 (C: 360) and 91 → 97 (C: 98). All the additions are THT hand/consign lines.
- **Scoring trap** (the mirror of r3's S1 note): the single-board scorecard shows a cost *increase*, because the module's parts move onto the board BOM. This candidate must be scored on system cost: board + module + harness + enclosure hardware.
- **r3 S1, for comparison:** S1 moves the board's mains parts into a module board and saves about $8.5 per system. That rests on the same $15 carrier allowance.

**Enclosure:** removing the module takes out:
- the 110 × 80 × 50 mm (0.44 L) envelope and its folded 5052 stand;
- 8 PEM nuts, 8 M4 and 1 M3 screws;
- the module-to-J1 harness, the module's PE stud and its separate 8 W heat allowance in the enclosure.

The cord lands directly on J1. The R43 handoff's open item "D-22 module terminals and 96 × 62 fixing pattern" (HANDOFF.md:216) closes. In exchange, the board outline grows (above).

## 5. Scorecard movement (C29-B, together with candidate 23's PS1 deletion)

| Metric | Benchmark | C29-B | Note |
|---|---|---|---|
| `leakage_touch_mA` (DESIGN row: 3 supplies, datasheet max) | 0.974 | 0.562; **0.419 with PS1 deleted** | The 0.25 target is unreachable on the datasheet-max basis with ≥ 2 supplies. With PS1 deleted it is met on Test B at 0.232 |
| `emi_min_margin_dB` | 10.5 | 10.8 (12.4 with 5.68 mH) | Within the 0.5 dB tolerance, so equal or better |
| `parts_usd_at_500` (board only) | 221.82 | 251.56 (+29.74, DM unpriced) | System −$6.74 |
| `placements` | 349 | 358 | |
| `bom_lines` | 91 | 97 | +6 hand/consign lines; `zero_stock_lines` and `single_source_lines` likely +1 (NC choke, 37 wk) |

## 6. Blocking inputs

1. **Certifier: leakage class and basis.**
   - 0.5 mA portable vs 0.75 mA stationary, and whether Test B (measured supplies) is accepted.
   - At 0.75 mA, C29-A/C pass even with three supplies (0.628 / 0.592 mA).
   - Also a second certifier question: are the on-board stage's choke ratings and agency files acceptable? The NC choke's VAC rating and recognition were not read.
2. **Candidate 23 (delete PS1)** or a measured supply leakage. Without one of them, no EMI-passing filter here meets Test A: the ceiling is 1.16 nF/line, and the best case is 9.2 / 4.8 dB.
3. **Enclosure:** whether an outline grown by 50–95 mm on the mains edge fits R43 (fit gate), and the cord route to J1.
4. **Measured parasitics:**
   - the stage-1 choke's DM leakage inductance (0.3–1 % assumed; NC parts publish none);
   - the SC-20-201 leakage, if C is wanted;
   - the coil-to-PE split (study 16 gives 31 pF; +20 pF board bound);
   - the built Y and X tolerances.
5. **DM inductor MPN (F10):** a 41 µH, 20 A part, or the fs floor raised to ≥ 40–45 kHz. This is open in either plan.
6. **Prices and lead:** the NC choke figure is one distributor listing (CNY, 37 wk lead). The KEMET SCF31X-220-2R1A011JH (5.68 mH, 22 A) was not priced: the Farnell page timed out.

## Sources (fetched 2026-10-13)

- KEMET SCF39XV-200-Z2R1A012JH, 3.6 mH, 20 A, 4.14 mΩ, element14.cn: https://www.element14.cn/en-CN/kemet/scf39xv-200-z2r1a012jh/common-mode-3-6mh-20a/dp/4199926
- KEMET SCF31X-220-2R1A011JH (5.68 mH, 22 A, 500 V) and SCF31X 45 × 31 × 42 mm class, search listings: https://es.farnell.com/en-ES/kemet/scf31x-220-2r1a011jh/common-mode-choke-22a-5680uh-500v/dp/4728656 (timed out) and https://novapart.co/datasheet/farnell:4728643/ (third party; its own inductance figure conflicts with its part number)
- KEMET SC-20-201: g01 PROPOSALS.md:24 (DigiKey FR, KEMET spec sheet)
- The D-22 part datasheets are as cited in PARTS.md:22-28.
