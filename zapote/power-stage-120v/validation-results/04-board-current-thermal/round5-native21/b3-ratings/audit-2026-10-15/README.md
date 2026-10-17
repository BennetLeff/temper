# B3 board temperatures against the laminate and part ratings (native-21 s32, board `2fb346dc…`)

Analysis only, 2026-10-15. Nothing in the repo was edited; every number here comes from `python3 run_all.py` in this
folder (about 25 min cold, 2 min with the solves cached in `runs/`). Downloaded sources are in `dl/<doc>/` and are not
for the repo.

## 1. What B3's peak and "conditional_pad_cell_max_c" are

`b3/thermal.py` is a 2.5-D finite-volume model: seven sheets (4 copper, 3 FR-4), k_Cu 390 and k_FR4 0.3 W/mK, binary copper
raster, plated barrels as axial links. Heat sources are the A4 copper Joule maps scaled by (I_op/I_case)^2, plus each
part's `watts × board_fraction`. Both outer faces convect with one uniform `h` to **50 °C** air. There is no radiation term,
no body-to-air path and no FET-lead path.

- **`peak`** is the hottest single cell over all seven sheets (copper or FR-4) of the 1 mm grid.
- **`conditional_pad_cell_max_c`** is the hottest copper cell whose centre falls inside the part's pads. The part's whole
  board share of its loss is injected uniformly into exactly those cells. So it is the temperature of the cell the heat is
  injected into, not a junction, body or case temperature. thermal.py says so itself ("no rating verdict").
- **"Conditional"** means conditional on the partial A6 heat map, the assumed board fractions, the A4 current scalings, the
  assumed h and the 50 °C air.
- **h:** run_study.py calls h = 10 W/m²K "still air" and h = 25 "fan airflow over the board"; task 04's plan calls 25 "light
  forced air". Nothing in the enclosure records provides that airflow. D-18 ducts the blower through the sink only. The
  enclosure's R33 study 14 models the board bay as "a well-mixed wrapper with no through-flow" and puts bay air at
  **55 °C** (expected, 40 °C kitchen), **61 °C** (worst, B3 heat only) and **78 °C** (all allowances stacked).
- **Physical h for still air:** horizontal-plate correlations give 7.5–8.4 W/m²K on the top face and about 4 on the
  bottom. Radiation adds up to 9–10 only where a face sees cool walls (`results/verdict.json` → `h_estimate`). Still air is
  therefore h ≈ 10–15, and **h 10 is the normal operating case for the board, not a fan-failure case**.

**Grid sensitivity.** The committed model at 1.0 / 0.5 / 0.25 mm on s32 (control L1: the 1 mm reruns reproduce 162.087 and
135.049 °C exactly):

| case | 1.0 mm | 0.5 mm | 0.25 mm |
|---|---|---|---|
| nominal h10 | 162.1 (U42) | 213.1 (U41) | 173.2 (U42) |
| c28 h25 | 135.0 (R5.4) | 181.3 (U41) | 142.5 (U42) |
| c28 h10 | 192.3 (R5.4) | 218.9 (U41) | 187.2 (R5.4) |

The peak jumps 40–50 K between meshes and changes part. The cause is point deposition into whichever binary pad cells the
cell centres hit, as the committed `b3-convergence` study (stage 19b) found. Under that study's body-level model (exact
pad-overlap flux, datasheet θJB/θJC networks, fill-fraction copper), rerun here on s32, U42's pad max is 108.7 °C and its
junction 125.3 °C in nominal h10, against legacy pad cells of 162–181 °C. **The 162.1 and 135.0 °C scorecard numbers are
artefacts and should not be compared to anything.** The R5.4 / FET-row copper peak is real and converges slowly: 1 mm-block
peak 170.0 / 172.3 / 174.6 °C (c28 h10), plus +6 K to the 0.0625 mm windows in 19b.

## 2. Ratings (re-read on the cited page; `scripts/ratings.py` asserts every quote)

| item | limit | applies to | source |
|---|---|---|---|
| KB-6164 / KB-6064 laminate (UL "KB-616(X)", X = 0, 4) | **MOT 130 °C** for multilayer PWBs; RTI elec 130, mech 130 (0.38 mm) / 140 (≥ 0.63 mm) | continuous board temperature | UL Product iQ QMTS2 reprint, file E123995, "Last Updated on 2026-02-20", p.3 (RTI rows), p.6 (column headers), p.7 (multilayer row: MOT 130, **Max Int 35 µm**), footnote "X - may be 0, 4"; kblaminates.com/upload/portal/20260224/202602241024184756.pdf (via kblaminates.com/list/28.html); Canadian reprint identical |
| KB-6164 Tg | 140 °C (DSC) | process / CTE marker, not a use limit | Kingboard TDS KB-6164/KB-6064, PDF 2025-03-13 |
| KB-6165 ("TG155"), KB-6167F (Tg 170) | MOT **130 °C** as well | — | same UL reprint p.6 (only KB-6169GT, FR-15.1, reaches 150 °C, p.7) |
| RECOM R24C2T25/R (U41/U42) | Tj **150 °C** abs max; OTP 160 ± 10 °C latch-off; θJB 25.9, θJC 16.6 K/W | junction | Rev. 1-2024, p.2, p.8. The 2 W / 82 °C knee is ambient on RECOM's 50 × 50 mm EVM (p.3, note 7) |
| TI TPS7A4700 (U26) | TJ **125 °C** | junction | SBVS204G (rev. May 2026), p.4, p.6; RθJC(bot) 1.7 K/W p.5 |
| Bourns CSS2H-2512R-1L00F (R5) | **170 °C** operating max; 5 W @ 70 °C terminal → 0 W @ 170 °C | element; terminal derating | REV. 06/17/20, p.1, p.3 |
| TDK B82726S2203A020 (L1) | climatic **40/125/56** (125 °C component temperature); IR 20 A at TR 60 °C | winding/body | TDK datasheet (PDF 2026-05-21), p.4, p.6 |
| Mean Well IRM-20 (PS1/PS2) | **85 °C ambient**, derating 100 % → 50 °C, 50 % @ 70 °C; no case or pin rating | local air | IRM-20-SPEC 2025-11-21, p.2, p.3 |
| TDK B3265* MKP (C38–C41, bank C21–23/151/152) | **Top,max 110 °C** (TA + self-heating); Tmax 100 °C ambient; VDC derates 1.25 %/K above 85 °C | body | TDK June 2026, p.2, p.35 (the repo used 105 °C) |
| 1206 thick film (gate R10/12/18/20, R53/54/57/58) | 155 °C | element | vendor-typical; **unverified** (LCSC returned HTML) |

Solder mask has no rating of its own at JLC. It is covered by the finished board's UL recognition (JLC E479892, type JLC-4),
whose MOT is not published and cannot exceed the laminate's 130 °C.

Two record errors to fix:
- DECISIONS 21 compares the FET-row copper with "laminate Tg 150". Tg is not a use limit, and KB-6164's Tg is 140; the
  relevant limit is the 130 °C MOT.
- run_study.py's c28 comment states a gate "≤ 105 °C (25 K under a 130 °C FR-4 class)" that nothing enforces.

## 3. Verdict per hot spot

Estimates come from the body-level model at 0.25 mm on s32 plus the stage-19b fine-window increment, at 50 °C. The other
bay air values shift 1:1 (the model is linear). Each estimate carries a spread. VIOLATION means over the limit even at the
optimistic end of the spread. Full tables: `results/VERDICT-TABLES.md`.

| hot spot | c22 h10 (22 A default, still air) | c28 h10 (28 A Kconfig, still air) | c28 h25 (needs unproven board airflow) |
|---|---|---|---|
| Board copper at R5.4 (39.5, 15.5) vs laminate MOT 130 | 137.1 °C → **−7 K @50, −12 @55: VIOLATION** | 180.6 → **−51 / −56** | 127.2 → +2.8 @50 (thin), −2.2 @55 |
| FET-row copper vs 130 | 127.9 → +2.1 / −2.9 | 170.9 → **−41** | 117.8 → +12 / +7 |
| R5 element vs 170 / terminal vs derating | 148.3 (+22) / 140.8 vs 156.7 | **196.6 (−27) / 184.4 vs 148.4 (−36)** | 137.5 (+33) / 126.6 vs 148.4 |
| HF film C40 (C38) vs 110 | **116.3 (−6)** (110.6, −0.6) | **146.2 (−36)** | 96.8 (+13) |
| Gate resistors R12/R58 vs 155 (unverified) | 124 / 119, OK | **161 / 156, over** | 107 / 105 |
| U42 / U41 Tj vs 150 | 130.6 / 126.8, OK (+19 / +23) | 139.3 / 130.8, OK (+11 / +19), +6 @55 | 105 / 104 |
| U26 Tj vs 125 | 111.0 ± 9.5, thin | 116.4 ± 9.5, thin (+3.6 @55) | 88.7 |
| Bank C21 vs 110 (board share only) | 90.2 | 111.9 (−2) | 89.1 |
| L1 vs 125 (assumed path) | 81.5 | 84.1 | 68.5 |
| PS2 / PS1: bay air vs IRM-20 derating limit 70.2 / 78.1 °C (at 9.59 W / 4.83 W, 90 % rule) | +15 / +23 K at 55 °C bay; **−8 / 0 at 78 °C** | same | same |

- **Legacy hot list:** U42 162, PS2 151, PS1 136, L1 133 and U41 132 °C are modelling artefacts. Each part is inside its own
  limit on the body model: U41/U42 junctions 121–139 °C against 150; PS1/PS2 have no board-temperature rating, and their
  real question is the bay air; L1 sits at 81–97 °C against 125.
- **R5 at 131 °C is a symptom of a genuine problem:** the R5.4 / FET-row tank copper.
- **Genuine violations in still air (h 10, the only airflow the records support):**
  - laminate MOT at R5.4, even at the 22 A default ceiling: −7 K at 50 °C, −12 K at 55 °C;
  - the HF film caps C38/C40 at 22 A;
  - at 28 A, additionally R5 (element and terminal), the gate resistors and the bank cap C21. R5's element reaches
    197 °C against 170.
- **The forced-air case barely holds MOT** even if a board airflow existed: +2.8 K at 50 °C, −2.2 K at 55 °C.
- **The stall derate (der14, 14.7 A) passes everything** at 55 °C (laminate +22 K).
- **"Nominal" and "extreme" are not reachable operating points.** Their line currents (14.25 / 15.8 A) exceed the 11.1 A
  inlet hold and the 15 A cap.
- **Still-air ceiling sweep (central estimates):**

  | ceiling | 1 mm-block board copper | R5 element |
  |---|---|---|
  | 18 A | 114 °C | 123 °C |
  | 20 A | 125 °C | 135 °C |
  | 22 A | 137 °C | 148 °C |

  The highest ceiling meeting laminate, R5 and U42 limits is **20 A at 50 °C bay air and 18 A at 55–61 °C**.
- **Bias, unmodelled in this audit:** the FET drain-lead path to the sink, which stage15b `lead_bias.py` bounds at about
  −26 K at h10 on the FET row for a ZVS case temperature. It acts mainly on the FET row and less at R5.4.

## 4. Proposed gate (`gate/`)

- **`b3_ratings_gate.py`** reads body-level solves at 0.25 and 0.5 mm. It estimates each quantity as
  Q(0.25) + 3·|Q(0.25) − Q(0.5)| + (bay − 50).
  - **Gated:** the laminate MOT 130 °C on the 1 mm-block copper peak and on the FET-row copper; the RECOM Tj 150 °C; the
    TPS7A47 TJ 125 °C; the CSS2H element 170 °C and its terminal derating.
  - **Advisory:** the MKP 110 °C, L1 125 °C and 1206 155 °C rows.
  - **Basis:** c22_h10 and c28_h10, bay 55 °C.
  - It writes `margins.json` with `b3_laminate_margin_K`, `b3_rated_part_margin_K` and `pass`.
- **`run_basis.py`** is the in-repo runner: four solves, about 6 min, using the committed b3-convergence modules.
- **`scorecard-b3-ratings.patch`** (`git apply --check` clean on 2a649f73): adds gate `b3_ratings` and the PERF ratchets
  `b3_laminate_margin_K` / `b3_rated_part_margin_K` (higher is better, 1 K tolerance). It drops the two artefact peaks from
  the comparison but keeps them on the card.
- **Result on s32:** the gate **FAILS**: laminate −56.4 K, rated parts −38.9 K, worst item the R5.4 copper (c28_h10).
- **Controls** (`gate_control.py`, all pass):
  - G2: the real c22 files +40 K FAIL;
  - G3: rises × 0.3 PASS;
  - G4: c28_h25 at 50 °C passes (+2.4 K), and raising only U42 Tj to 151 °C fails on U42;
  - G5: the mesh allowance reacts exactly (+30 K for a 10 K mesh step);
  - G6: the gate's estimates agree with the 19b-corrected estimates within 2 K. The exception is R5's element at
    c22/c28 h10, which is 4–6 K low; R5 converges at p ≈ 0.2.
- **Adoption note:** with the patch, the hard gate makes s32 and every current candidate "not a candidate". That is the
  correct reading of the data. If the parent prefers a ratchet-only step first, drop the `gates()` hunk and keep the two
  PERF metrics.

## 5. Fixes ranked by leverage (0.5 mm deltas against the same-mesh h10 baseline, `results/verdict.json` → `sensitivities`)

| rank | fix | effect on R5.4 board copper (c28 / c22) | notes |
|---|---|---|---|
| 1 | Forced air across the board faces (enclosure: a bleed from the blower over the FET-row / R5 region) | h15: −27 / −18 K; h20: −42 / −28 K | Largest lever and no board change. It needs an enclosure flow path and a measured h. At c22, h15 brings the copper to ~119 °C central. |
| 2 | Less tank copper Joule heat at R5.4 / FET row (wider or thicker paths, more parallel layers, a 3 oz outer) | ×0.7: −25 / −16 K; ×0.5: −42 / −26 K | Layout candidate. Re-runs F6 / Kelvin / fusing. ×0.7 at 22 A gives ~122 °C. |
| 3 | Lower the commissioned ceiling in still air | 22 → 20 A: −12 K; → 18 A: −23 K | Firmware Kconfig only. Supports 18 A at 55–61 °C bay air until 1 or 2 lands. |
| 4 | Halve R5's loss (0.5 mΩ shunt) | −7 / −5 K board; R5 element −21 / −13 K | Changes the OCP / Kelvin budget. Second-order for the laminate, first-order for R5's own rating at 28 A. |
| 5 | Module loss / thermal vias under U41/U42 | modules ×0.5: Tj −30 K, board −2 K | Not needed: U41/U42 are inside 150 °C at every realistic case. The 162 °C was an artefact. |
| 6 | PS1/PS2 | ×0.5 loss: PS2 pad −16 K, nothing else | Their limit is bay air (PS2 ≤ ~70 °C at 9.59 W). Bench-measure the air; IRM-30 class if the stacked 78 °C case is real. |
| 7 | Higher-Tg laminate (JLC TG155 / TG170) | **0 K of margin** | Kingboard KB-6165 and KB-6167F have the same 130 °C MOT (UL p.6). Tg is not the limit. Only an FR-15.1 class (KB-6169GT, 150 °C) would move it, and JLC does not offer it. |

## Side findings (outside the thermal question, flagged for the owner)

- **Inner copper outside KB-616(X)'s UL multilayer recognition:** that recognition lists **Max Int 35 µm** (p.7), while the
  s32 stack has 2 oz inner copper (61 µm finished). KB-6164F (102 µm) and KB-6165F (102/204 µm) are recognised for it.
  Whether JLC's own E479892 JLC-4 recognition covers 2 oz inner layers with KB-6164 needs checking before a UL-marked build.
- **c28 heat file assumptions behind the current BOM and operating window:** it carries U41/U42 at their 40 kHz loss
  (1.09 W) while the window runs to 60 kHz (~1.4 W). It also still carries the stage-19b UCC21550 / 3.9 Ω gate-network
  losses; s29 fitted the 2EDR8259X with 8.2 Ω.
- **Film-cap record:** the repo's film-cap limit of 105 °C should be 110 °C Top,max and 100 °C ambient category, with VDC
  derating above 85 °C.

## Files

- `run_all.py`: the single entry point.
- `scripts/`:
  - `paths.py`
  - `ratings.py`: ratings, sources and the quote verifier, run with `-I`
  - `legacy_grid.py`
  - `prepare_model.py`: copies b3-convergence into `model/` with two asserted patches (repo path; 2EDR8259X → DWK class,
    assumed) and checks the 19b part bodies against the s32 pick-and-place
  - `body_cases.py`
  - `verdict.py`
- `gate/`: `b3_ratings_gate.py`, `gate_control.py`, `run_basis.py` (proposed for
  `validation-results/04-board-current-thermal/round5-native21/b3-ratings/`).
- `scorecard-b3-ratings.patch`
- `results/`: `ratings.json`, `legacy_grid.json`, `verdict.json`, `VERDICT-TABLES.md`, `margins.json`, `gate_control.json`.
- `runs/`: solves (gitignore-class), plus `model/` (generated copy).
- `dl/`: downloaded sources (do not commit).
