# Resonant bank at the 28 A ceiling under airflow (bank28, 2026-10-16)

Analysis lane, reviewed at integration. Pad temperatures come from the airflow28 B3 runs (s47 board; run files outside git at `runs-native21/airflow28/runs`); datasheets at `runs-native21/bank28/dl/`. `results/bank_air_metric.json` feeds the scorecard metric `bank_air_ratio_28A_35k` (DECISIONS 68).

# bank28: the resonant bank at the 28 A ceiling, with board-face airflow

Analysis lane, 2026-10-16. Nothing was written to any git worktree. No new B3 solves were run (0 workers).

- **Unit:** PS = `worktrees/ps-integrate/zapote/power-stage-120v`, HEAD 05a3d9138, board s48.
- **B3 pad temperatures:** the airflow28 run files (`runs-native21/airflow28/runs/`, s47 board 83355da5, hot copper). Read
  with the gate's estimator.
- **Scripts:** `scripts/` beside this file.
- **Datasheets:** `runs-native21/bank28/dl/`, read with `python3 -I` and pdftotext.

## 0. Verdict

1. **TDK's "85 °C curve" is a self-heating limit, not a temperature limit.**
   - It is the current at which the part's hottest surface point rises **20 K** above the air around it (15 K for the
     c34 part). It holds for any ambient T_A ≤ 85 °C.
   - So the real check is ΔT ≤ 20 K, plus T_A + ΔT ≤ Top,max (110 °C) above 85 °C. Airflow can move ΔT. It cannot move
     the curve.
2. **Airflow alone does not close the fitted bank (5 × B32654A1104J000).**
   - The bank is a column with 0.5–0.8 mm gaps, so each interior cap loses its two large faces (symmetry).
   - At the recommended jets + base flow (2.1–3.1 m/s at the bank) an interior cap rises **22.6–34.2 K** at 28 A /
     35 kHz. The range is central to conservative correlation. That is **1.06–1.31×** TDK's limit.
   - At the no-jet design flow (6.7 m/s) it is **17.9–21.6 K, 0.94–1.04×**.
   - To reach TDK's limit the bank needs **4.6 m/s** (central) or **8.3 m/s** (conservative).
   - The c34 0.85 margin (bench ΔT ≤ 14.5 K) needs **12.7–17.7 m/s**. The bench gate "ΔT ≤ 14.5 K under airflow" is
     therefore predicted to fail.
3. **The c34 bank (5 × B32643B8104J000) closes under the recommended flow.**
   - At the design flow (3.07 m/s) it rises **9.9–14.0 K against 15 K: 0.81–0.97×**.
   - It reaches TDK's limit at ≥ 2.7 m/s at the bank and the 0.85 margin at ≥ 2.4 / 4.7 m/s (central / conservative).
   - It also adds 15 K of Top,max headroom (125 °C case) and runs at about a third of the heat.
4. **Recommendation: both.**
   - The c34 bank.
   - The airflow, plus a bank-local velocity line in S24: ≥ 3.0 m/s across the bank column.
   - A scorecard change: the bank's 28 A metric becomes a physical self-heating check under the declared airflow
     (`bank_air_ratio_28A_35k`; producer and patch in `scripts/`, `patch/`).
5. **New flag (still air, below 28 A).**
   - The same physics puts the fitted bank's interior caps at **0.99×** TDK's limit at 18 A / 61 °C in still air
     (radiation credited), and at 1.26× without radiation.
   - So the shipped 17.5 A ceiling is at the limit. This is the open 2026-10-09 bench item ("middle cap hot spot
     ≤ 20 K before releasing 22 A"), and the model predicts it fails above about 18 A.

## 1. What the TDK curve limits (task 1)

Datasheets (sha256 in §8):
- B3265*A/G/J/T, June 2026 (`MKP_B32651_658.pdf`);
- B3264*B, June 2026 (`MMKP_B32641B_B32643B.pdf`);
- TDK *Film Capacitors – General technical information*, Oct 2025 (GTI).

| Item | Fitted B32654A1104J000 | c34 B32643B8104J000 |
|---|---|---|
| Curve | p.57: "Permissible current I_RMS versus frequency f (for sinusoidal waveforms, **ambient temperature T_A ≤ 85 °C, self-heating ΔT ≤ 20 °C** when ΔESR_typ ≤ ±5 %)", 1600 V DC / 500 V AC, 27.5 mm | p.24: "Permissible current I_RMS versus frequency f (for sinusoidal waveforms, **T_A ≤ 85 °C, ΔT ≤ 15 °C**)", 2000 V DC / 500 V AC, 22.5 mm |
| 100 kHz anchor | p.23: 7.3 A at 85 °C / 100 kHz, ESR_typ 19.3 mΩ, 14.0 × 24.5 × 31.5 mm; fn 2 "for a ΔT ≤ 20 °C" | p.11: 8.3 A, ESR_typ 8 mΩ, ESL 11 nH, 14.5 × 29.5 × 26.5 mm; fn 8 "ΔT ≤ 15 °C" |
| Temperatures | p.35: rated 85 °C, Top,max 110 °C, upper category 100 °C; p.2: max operating 110 °C | p.2: Top,max 125 °C (case), climatic 55/110/56; p.12: rated 85, Top,max 125, Tmax 110 |
| Above 85 °C | p.64: I_RMS(T_A) = I_RMS,≤85 · F_T(T_A); "the self-heating (ΔT) … must be reduced to avoid that … (Top = T_A + ΔT) reaches values above maximum operating temperature". F_T = 1 at ≤ 85 °C | p.25: same rule, F_T to 0 at 125 °C |
| F_T, read off the curve | fits √((110 − T_A)/25) at 90/95/100/105 °C (0.89/0.77/0.63/0.45). So ΔT_allowed = 0.8 (110 − T_A) | fits √((125 − T_A)/40) (0.87 at 95, 0.71 at 105). So ΔT_allowed = 0.375 (125 − T_A) |
| tan δ upper limits, 20 °C | p.35: 1.0e-3 at 10 kHz, 3.0e-3 at 100 kHz | p.12: 0.6e-3 at 10 kHz, 1.5e-3 at 100 kHz |

**Definitions from the GTI:**
- **ΔT** is "the self-heating or steady-state overtemperature attained **at the hottest part of the capacitor surface
  in relation to the surrounding atmosphere**" (GTI p.25).
- The heat balance is Pgen = V²·2πf·C·tan δ = Pdiss = **α·A·ΔT**, with α the heat transfer coefficient and A the
  surface area (GTI p.25; symbols on B3265x p.77).
- T_A is "temperature of the air surrounding the component" (p.78). It is measured on an **unpowered dummy
  capacitor of similar size, about 50 mm away on the same PC board** (GTI p.30, Figure 26).
- GTI p.30: "For any critical case … a temperature check on the capacitor under working conditions should be
  carried out."
- The curve's frequency shape comes from tan δ(f). Its level is set by TDK's own still-air α·A.
- TDK's scaling for a load below the curve is ΔT' = (I'/I_max(f))² · ΔT_lim (GTI p.27).

**Consequences:**
- **"85 °C curve" is not a case or hot-spot temperature.** It is the ΔT = 20 K (or 15 K) locus, valid while the
  surrounding air is ≤ 85 °C. A cooler location earns nothing (F_T = 1). An airflow that raises α·A lowers ΔT at a
  given current.
- **The repo's ratios are ΔT ratios in disguise.** Under TDK's test the fitted part rises ratio² × 20 K:
  - 1.045² × 20 = **21.8 K** at 28 A / 35 kHz;
  - 1.022² × 20 = 20.9 K at 40 kHz;
  - 1.117² × 20 = 25 K on round 6's K-share max (DECISIONS 10's "1.12×", reproduced by c34 control C3).
  The current at 35 kHz is 6.06 A per part (J worst share 0.2165) against a curve value of 5.80 A.
- **"Bench ΔT ≤ 14.5 K"** is 0.85² × 20 K = 14.45 K. It is c34's 0.85 go-margin on the current ratio (c34 README
  §4: "it leaves 0.85² = 72 % of the rated self-heating"), restated as a bench ΔT by airflow28 (README §0.5, §6).
  - It is **not** a TDK number. TDK's limit is 20 K.
  - The 28 % was kept to absorb what the isolated-part curve leaves out: the shadowed column and the hot copper
    under the leads.
  - Measured per GTI Fig. 26, it means: the hottest-surface temperature of the worst cap minus an unpowered dummy cap's
    temperature in the same airflow, at 28 A / 35 kHz.

## 2. The physical check (task 2)

**Model** (`scripts/bank_thermal.py`; equations in its docstring):
- Per cap: ΔT_ours = ratio² · ΔT_lim · G_tdk / G_ours.
- The dummy-cap temperature is T_A = (G_air·T_air + G_board·T_pad)/(G_air + G_board).
- Pass if ΔT_ours ≤ ΔT_lim·F_T(T_A)² and T_A + ΔT_ours ≤ Top,max.
- Effective ratio = √(ΔT_ours / ΔT_allowed). It is ≤ 1 at TDK's limit and ≤ 0.85 at the c34 margin.

**Conductances** (G_tdk and G_ours come from one first-principles model, so correlation error cancels in the ratio):
- **TDK's test:** the part alone in still air at 85 °C. Churchill-Chu vertical faces, 0.54 Ra^¼ top face, radiation
  ε 0.9.
  - **Calibration:** the model gives G = 0.0536 W/K against 0.0514 W/K implied by p.23 (7.3² × 19.3 mΩ / 20 K).
    That is **1.04×**, so the free-air model reproduces TDK's rating.
  - For B32643B the model is 1.44× the implied value (8.3² × 8 mΩ / 15 K = 0.0367). Its rating is more conservative
    than free air, which makes this lane's c34 numbers conservative.
- **Ours:** the bank column, bodies 0.5 / 0.8 / 0.5 / 0.5 mm apart (`validation-plan/enclosure-fit/native21-boxes.json`).
  - Interior caps (C22, C23, C151) keep the top face and the two end faces: 1127 mm² of 2670.
  - The end caps (C21, C152) also keep one large face.
- **Still air:** natural convection, with and without radiation. Air is at bay + 15 K (B3's film-cap rule,
  `FILM_HF_AIR_RISE_K`).
- **Forced convection:** flow along x hits the end faces. No radiation and no natural convection are credited (as in
  airflow28).
  - **A (central):** laminar flat plate on top and sides; Sparrow–Geiger flat face normal to the flow on the front
    face; 0.5 × top on the rear face.
  - **B (conservative):** square prism in cross-flow (Incropera Table 7.3, Jakob), Nu = 0.102 Re^0.675 Pr^⅓,
    D = l, on every exposed face. Re 3–12 × 10³; below 5 × 10³ this is an extrapolation.
- **Velocity and air:** from airflow28 `enclosure.json`, "corner + tank path along x": the tripped velocity (the lower
  estimate) and the full 10 mm-gap bulk rise.
- **Board coupling:** G_board = 0.005 W/K (the TDK-implied weak tie) or 0.046 W/K (B3's 50 K/W lead path plus 0.5 mm
  seat-gap conduction). Each criterion takes the worse of the two. T_pad is the B3 bank-pad maximum of that case
  (`bank_pads.json`).

### 2.1 Results at 28 A, worst share, 35 kHz (40 kHz in brackets)

**Fitted bank (ΔT_lim 20 K, Top,max 110 °C).** The worst cap is interior in every case.

| Case | v at bank (m/s) | T_air (°C) | B3 pad max (°C) | ΔT, A / B (K) | eff ratio, A / B | (40 kHz) | T_A dummy, B (°C) | T_op, B (margin) |
|---|---|---|---|---|---|---|---|---|
| Still air @61 | — | 76.0 | 123.3 | 29.8 (hi) / 41.6 (lo) | **3.16** (T_A 106 → F_T² 0.15) | 3.12 | 106.3 | 136 (−26) |
| Still air @55 | — | 70.0 | 116.6 | 30.1 / 42.3 | **1.95** | 1.91 | 100.1 | 130 (−20) |
| Jets + base h16 @61 (min) | 2.32 | 65.9 | 103.4 | 25.6 / 40.2 | **1.13 / 1.42** | 1.11 / 1.39 | 72.3 | 120 (−9.7) |
| **Jets + base h20 @61 (design)** | 3.07 | 64.7 | 97.2 | 22.6 / 34.2 | **1.06 / 1.31** | 1.04 / 1.28 | 69.4 | 112 (−1.7) |
| Jets + base h12 @55 (min) | 1.62 | 62.0 | 106.8 | 30.0 / 48.7 | **1.23 / 1.56** | 1.20 / 1.53 | 71.3 | 125 (−15) |
| **Jets + base h15 @55 (design)** | 2.14 | 60.3 | 99.0 | 26.6 / 41.8 | **1.15 / 1.45** | 1.13 / 1.41 | 67.2 | 116 (−5.8) |
| No jets h31 @61 (min) | 5.31 | 63.1 | 88.0 | 19.1 / 24.7 | 0.98 / 1.11 | 0.96 / 1.09 | 65.7 | 99 (+11) |
| **No jets h37 @61 (design)** | 6.67 | 62.7 | 85.1 | 17.9 / 21.6 | **0.94 / 1.04** | 0.92 / 1.02 | 73.1 | 95 (+15) |
| No jets h27 @55 (min) | 4.47 | 57.5 | 84.3 | 20.1 / 27.3 | 1.00 / 1.17 | 0.98 / 1.14 | 60.6 | 97 (+14) |
| **No jets h33 @55 (design)** | 5.61 | 57.0 | 80.7 | 18.8 / 23.8 | **0.97 / 1.09** | 0.95 / 1.07 | 59.4 | 92 (+18) |

**c34 bank (ΔT_lim 15 K, Top,max 125 °C case):**

| Case | v (m/s) | ΔT, A / B (K) | eff ratio, A / B | (40 kHz) | T_A, B (°C) | T_op, B (margin) |
|---|---|---|---|---|---|---|
| Still air @61 / @55 | — | 14.2 / 14.3 (hi) | 1.39 / 1.22 (T_A 105 / 99 from the hot pads) | 1.36 / 1.20 | 105 / 99 | 120 / 114 (+5 / +12) |
| Jets + base h16 @61 (min) | 2.32 | 11.0 / 16.5 | 0.86 / 1.05 | 0.84 / 1.03 | 71.6 | 101 (+24) |
| **Jets + base h20 @61 (design)** | 3.07 | 9.9 / 14.0 | **0.81 / 0.97** | 0.80 / 0.95 | 68.9 | 95 (+31) |
| Jets + base h12 @55 (min) | 1.62 | 12.9 / 20.2 | 0.93 / 1.16 | 0.91 / 1.14 | 70.3 | 106 (+20) |
| Jets + base h15 @55 (design h, 2.14 m/s) | 2.14 | 11.4 / 17.2 | 0.87 / 1.07 | 0.86 / 1.05 | 66.4 | 97 (+28) |
| No jets h31 / h37 @61 | 5.31 / 6.67 | 8.4 / 10.2; 7.8 / 9.3 | 0.75 / 0.82; **0.72 / 0.79** | 0.74 / 0.81; 0.71 / 0.77 | 74 / 72 | +41 / +44 |
| No jets h27 / h33 @55 | 4.47 / 5.61 | 8.9 / 11.1; 8.3 / 9.9 | 0.77 / 0.86; 0.74 / 0.81 | 0.76 / 0.85; 0.73 / 0.80 | 60 / 67 | +44 / +48 |

**Bank velocity needed** (interior cap, 28 A / 35 kHz; T_A < 85 °C, so the result does not depend on the air
temperature):

| Bank | eff ≤ 1.00 (TDK), A / B | eff ≤ 0.85, A / B |
|---|---|---|
| Fitted | 4.6 / 8.3 m/s | 12.7 / 17.7 m/s |
| c34 | **1.2 / 2.7 m/s** | 2.4 / 4.7 m/s |

### 2.2 Sensitivities at the design points (correlation B unless stated; `bank_thermal.json` → `sensitivities`)

| Sensitivity | Fitted, jets + base h20 @61 | Fitted, no jets h37 @61 | c34, h20 @61 | c34, h37 @61 |
|---|---|---|---|---|
| 29.4 A (the 1.05× trip) | 1.37 | 1.09 | 1.02 | 0.83 |
| Bank velocity × 0.5 (a 26–30 mm column in a 10 mm face gap) | 1.59 | 1.28 | 1.18 | 0.94 |
| Radiation credit ε 0.9 to air-temperature surroundings, A / B | 1.00 / 1.15 | 0.91 / 0.99 | 0.77 / 0.86 | 0.69 / 0.75 |
| Gap through-flow (0.5 mm slots, pressure-driven) | 1.26 (+0.0025 W/K) | 0.98 | 0.93 | 0.73 |
| A part at the tan δ upper limit (heat × 2.3 fitted, × 3.7 c34) | 1.99 | 1.58 | 1.87 | 1.52 |
| Core penalty of the column (heat leaves through the end contacts, k_in-plane 0.5–1.0) | +2.6 to +18 K | same | −1.0 to +2.4 K | same |

**Reading:**
- **The fitted bank fails TDK's own limit under every jets + base point, on both correlations.** It passes only at
  the no-jet design flows, and only on the central correlation (0.94–0.97). It never reaches 0.85.
- On B it also exceeds Top,max (110 °C) by 1.7–15 K under jets + base. That is the strong-tie bound: the 97–107 °C
  bank pads pull the dummy toward 84 °C.
- **c34 passes TDK's limit at the design flow (3.07 m/s) on both correlations.** It fails on B at the minimum base
  flows (1.6–2.3 m/s).
- c34 has ≥ 24 K of Top,max margin under any airflow, because its heat is a third of the fitted part's (0.38 W against
  1.12 W per part, curve-implied).
- The tan δ upper-limit row is a part-spread bound, not TDK's rating basis (the curves are at ESR_typ). The bench
  covers it.

### 2.3 Still air below 28 A (`still_air_ladder`; pads from the B3 still-air ladder runs; radiation credited, no-radiation in brackets)

| Ceiling | Fitted @61 | Fitted @55 | c34 @61 | c34 @55 |
|---|---|---|---|---|
| 18 A | **0.99** (1.26) | 1.00 (1.26) | 0.78 (1.02) | 0.79 (1.02) |
| 20 A | 1.08 (1.38) | 1.09 (1.38) | 0.86 (1.12) | 0.87 (1.12) |
| 22 A | 1.17 (1.50) | 1.18 (1.50) | 0.93 (1.21) | 0.94 (1.21) |
| 24 A | 1.41 | 1.28 | 1.01 | 1.02 |

- **Fitted bank:** in still air, about 18 A by TDK's limit with radiation credit, about 14 A without.
- **c34:** about 23 A with radiation credit, about 17.6 A without.
- DECISIONS 37's "the shipped 22 A ceiling stays inside the bank's 0.85 margin" is an isolated-part reading. The column
  geometry does not support it.

## 3. The c34 bank (task 3)

| Item | Result (source) |
|---|---|
| What changes | C21–C23, C151, C152: B32654A1104J000 (MKP 1600 V, P27.5) → **B32643B8104J000** (MMKP "High frequency", 2000 V DC / 500 V AC, P22.5, ±5 %). One BOM line replaces one: **BOM-line delta 0** (94 → 94). Both are JLC Extended THT |
| Ratio at 28 A, vendor curve | **0.831 / 0.816 / 0.796** at 35 / 40 / 50 kHz, against 1.045 / 1.022 / 0.950 (c34 `bank_margin.json`). Tank current at the curve: 33.7 A at 35 kHz; at 0.85: 28.6 A |
| Ratio at 28 A, physical (this lane) | Design flow 3.07 m/s: **0.81 / 0.97** (A / B). No-jet design: 0.72–0.81. Still air: 1.22–1.39 (from hot pads plus shadowing) |
| Cost per board (5 parts) | JLC same channel: **$2.61 → $1.24 at 500** (−$1.37; C3794777 $0.5221 vs C3781430 $0.248, 1040+ tier) and $3.94 → $3.37 at 5. DigiKey: $7.44 → $6.55 at 500 (B32654 J $1.48848, SNAPSHOT-2026-10-15; B32643B $1.30931 at MOQ 2080, DECISIONS 37). Cheaper on every channel read |
| Stock (the blocker) | JLC 0 (C3781430, MOQ 14), DigiKey not stocked, 28-week manufacturer lead time, MOQ 2080 untaped (DECISIONS 37, p.11 MOQ 2080). OPEN-ITEMS S9 "waits on stock". Fitted part: JLC 104, DigiKey 881 (2026-10-15) |
| Footprint | New `temper:TDK_B32643B_P22.5_W14.5_L26.5_Radial`, 0.8 mm leads (p.2), plus STEP. The body is 5 mm shorter in x and 5 mm taller (29.5 mm) |
| Layout | Rows at y 53.2 / 68.2 / 83.2 / 98.2 / 113.2 (15.0 mm pitch for 14.5 mm bodies, 0.5 mm gaps). RES_A stays at x 163.0; SW_B moves to x 185.5. Re-cut the res_a / sw_b strips. Move the line_zc_raw B.Cu segment (x 184.0–203.3) from y 121.27 to ≥ 122.55 so the SW_B pin of row 5 at y 113.2 keeps 8 mm |
| Fits the slot on s48? | **Yes, with the same changes as on s32.** I re-ran c34's `slot_geometry.py` from a scratch copy on s48 HEAD copper (592a0d38…): the column limits are identical (`slot48/results/slot_geometry_s48.json`; summary equal; SW_B pin ≤ y 111.5, RES_A ≤ 113.5, both bounded by line_zc_raw; top y 48.0; R43 headroom 52.51 mm vs 29.5 mm). On s48 the SELV copper below y 122 has moved (line_zc_raw now binds where v15_selv did), so the 1.3 mm line_zc_raw move must be re-checked against s48's SELV lane by DRC |
| 35 kHz floor | Unchanged. C_nom 0.50 µF and J tolerance are the same, so f_res, the rule f ≥ max(35 kHz, 1.05 f_res) and C_min 0.475 µF are unchanged (V_rms bound 268 V at 28 A) |
| Yield (DECISIONS 10) | Unchanged. Round 6 `fstrat-b-bank-sweep.csv`: 0.50 µF → 88.6 % at 28 A (70 µH, 220 mm pans); the 85 % pooled figure stands. The 70 µH / 0.50 µF basis is kept |
| Other effects | **Closes F3** (triple fault 1683 V pk at 0.84 × 2000 V; 1.05 × 1600 V today). dV/dt 3800 V/µs (B3264*B p.13, 2000 V / 22.5 mm) against 1000 (B3265x p.36, 1600 V / 27.5 mm). Bank loss at 28 A about 1.9 W against 5.6 W (curve-implied), so less heat into the res_a / sw_b copper. The body is 5 mm taller in the airflow path |
| Gates to rerun | DRC, barrier21 (RES_A 12.6 mm outer), D5, enclosure fit (height), task 04 strips, B3 bank rows, the CPL rotation audit, the datasheet ledger (2000 V, p.24 curve, ΔT ≤ 15 K, Top,max 125 °C case), audit.rs identity strings, JLC class; `scorecard.py` must learn the MPN (the patch below does) |

## 4. Recommendation (task 4): both

1. **Bank → c34 (5 × B32643B8104J000)** as soon as stock allows (S9). Place the long-lead order early, as DECISIONS 37
   already says. It is the only option that meets TDK's own self-heating limit under the recommended jets + base
   airflow (0.81–0.97 at 3.07 m/s). It costs nothing in yield or BOM lines and is $1.37 per board cheaper on JLC.
2. **Airflow (DECISIONS 66, S24) with a bank line added to the requirement:**
   - **≥ 3.0 m/s across the bank column (x 161–193, y 46–119, 0–30 mm above the board), entering its end faces
     (flow along x).**
   - The design flow (base h 20, 3.07 m/s) meets it. The 55 °C design point's h 15 flow (2.14 m/s) does not:
     c34 1.07 on B. So the base flow is sized by the bank, not by h at 55 °C. The enclosure delivers one flow, and the
     h 20 flow is the requirement at both air temperatures.
   - The bank is 26–30 mm tall, so the face gap over it must not throttle it. At half velocity the c34 bank is 1.18
     on B.
3. **Fitted bank, if c34 cannot be bought:** airflow does not close 28 A.
   - Hold the commissioned ceiling at what the fitted column supports: **21.4 A (B) – 26.3 A (A)** under the design
     flow, from 28 A / eff (I² scaling, pads at 28 A, conservative).
   - In still air, about 18 A.
   - The "bench ΔT ≤ 14.5 K" route is predicted to fail (22.6–34.2 K at 3 m/s).
4. **Scorecard metric change** (proposed; producer `scripts/bank_air_metric.py`, patch `patch/scorecard-bank-air.patch`,
   dry-run `git apply --check` clean, not applied):
   - **`bank_air_ratio_28A_35k`** (lower is better, tolerance 0) is the maximum over the declared airflow points
     (the h 20 design flow at 61 °C and at 55 °C air) and over the column positions of
     √(ΔT_col / (ΔT_lim · F_T(T_A)²)). It uses correlation B and the worse G_board bound, at 28 A, J worst share and
     the 35 kHz floor.
   - **Go ≤ 1.00.** The 0.85 margin was a stand-in for the column shadowing and the hot copper, and the metric now
     models both. Correlation spread is covered by using B.
   - Values: **fitted 1.308, c34 0.967.** Control: it reproduces `bank_thermal.py` at the min design points
     (1.446 / 1.072).
   - `bank_ratio_tdk_28A_35k` / `_40k` stay on the card as informational vendor-curve values. The patch also gives them
     the c34 MPN (0.831 / 0.816), since today's code reads only B32654A1104.
   - **For scoring a new board:** the producer takes pads from B3 jetmix runs (now the s47 airflow28 runs; the card
     records their board sha). Add `c28_h20_jet100@61` and `c28_h15_jet100@55` to the chain's B3 case list so the pads
     follow the board. Under forced flow T_A stays below 85 °C (worst 84.0 °C), so the metric is weakly sensitive to
     them.
5. **Bench release under the declared flow** (replaces "ΔT ≤ 14.5 K"):
   - **Setup:** GTI Fig. 26 fixture. Thermocouple the hottest surface point (top, centre) of an interior cap (C151,
     between two 0.5 mm gaps) and an unpowered dummy cap of the same type in the same flow beside the column.
   - **Condition:** 29.4 A (the trip, not 28 A) at 35 kHz, minimum fan setting.
   - **Pass:** ΔT ≤ ΔT_lim (c34 15 K; fitted 20 K) and T_A + ΔT ≤ Top,max.
   - Measuring at the trip current replaces the 0.85² model margin with the real worst current.
   - Predicted c34: 10.9 (A) – 15.5 (B) K. Do the still-air case at 17.5–18 A first (§2.3).

## 5. Where the bank sits in B3 today (for the record)

- **The bank is class `film_radial`:** a body node with 0.3 of its self-heat (0.27 W per cap at the c28 case, ESR_typ
  flat at 19.3 mΩ, K share 0.234, 29.4 A), a 50 K/W lead path to the pads, and **no body-to-air path** (`body_air`
  False). Its row is advisory at 110 °C (`b3_ratings_gate.ADVISORY`).
- The airflow28 "bank bodies 99.8 °C at h 31" is pad + 0.27 W × 50 K/W, not a hot spot.
- **Only C38–C41 (`film_hf`) have the body-to-air fin at bay + 15 K.** The bank does not.
- The pads, the one input this lane takes from B3, run 97–107 °C under jets + base flow and 116–123 °C in still air at
  28 A. They matter here only through T_A, under the strong-tie bound.

## 6. Did not match / caveats

- **Velocities are the airflow28 tripped flat-plate estimates for the board faces**, applied to a 26–30 mm-tall body.
  A real enclosure with a 10 mm face gap would be blocked by the column. Measure the velocity at the bank, not h.
- **Correlation spread A / B is 1.5–1.6× in G for interior caps.** Neither is a wall-mounted-block correlation in a
  channel; B is used for the metric.
- **The shadowed faces are adiabatic by symmetry.** Measured slot flow is negligible at 0.5 mm (+0.0025 W/K at 3 m/s).
  Wider gaps would help, but the slot has no spare length (c34 §2; s48 identical).
- **The G_board 'hi' bound is inconsistent with TDK's own rating** (model 1.78× the implied G). It is kept only as the
  strong-tie bound for T_A. The heat the caps send into the pads under 'hi' (about 60 %) exceeds B3's 30 % share, so
  the pads would be a little hotter than B3 shows.
- **B32643B:** the free-air model gives 1.44× TDK's implied G. TDK's 15 K rating is stricter than free air, which
  makes the c34 numbers conservative by up to that factor.
- **The F_T curves are digitized by eye at 4–5 points.** They matter only in still air, where T_A exceeds 85 °C.
- **The c34 slot study's layout changes** (strip re-cut, line_zc_raw move) are geometry only. KiCad DRC on s48 is the
  authority.

## 7. Files

| What | Path |
|---|---|
| Bank pad temperatures per case (B3 airflow28 runs, gate estimator) | `scripts/bank_pads.py` → `bank_pads.json` |
| Physical model, all cases, sensitivities, still-air ladder | `scripts/bank_thermal.py` → `bank_thermal.json`, `bank_thermal.out` |
| Proposed metric producer (design flow; `--declared min` for the min design points) | `scripts/bank_air_metric.py` → `bank_air_metric.json`, `bank_air_metric_min.json` |
| Scorecard patch (dry-run applies to PS HEAD) | `patch/scorecard-bank-air.patch` (`patch/scorecard.py` patched copy) |
| c34 slot geometry on s48 | `slot48/slot_geometry_s48.py` → `slot48/results/slot_geometry_s48.json` |

Run order: `bank_pads.py` → `bank_thermal.py` → `bank_air_metric.py` (the metric's control reads
`bank_thermal.json`). All use `python3 -I`, stdlib only (the slot script needs numpy), and are read-only on PS.

## 8. Datasheets (`runs-native21/bank28/dl/`)

| File | sha256 | Pages used |
|---|---|---|
| `tdk/MKP_B32651_658.pdf`, TDK B3265*A/G/J/T, June 2026 (= c34's) | `c32e3754787fa19b2e256e007c98a24755ae18eb52830cce430ffd6b177afdd3` | p.2, p.23, p.35, p.36, p.57, p.64, p.77, p.78 |
| `b3264/MMKP_B32641B_B32643B.pdf`, TDK B3264*B, June 2026 (= c34's) | `ab9fdca0b9676c8528b8bb5469d8ec4a60f0983520a65fa8f0517e4b4a58ab77` | p.2, p.11, p.12, p.24, p.25 |
| `gti/gti.pdf`, TDK Film Capacitors – General technical information, Oct 2025 | `c2bbe57524093c73f9ad66b9967136d3190d85bba62c58aba3b74ef4077d13a9` | p.25, p.26, p.27, p.29, p.30 |
