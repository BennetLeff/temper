# Task 05 round 5: coil geometry against the 0.50 µF tank (R34 two-section r 26–114 vs R32 uniform r 22–116)

> **ASSUMED / PRE-MEASUREMENT.** No Temper coil or pan has been measured. The coupling ratios come
> from a linear-µ axisymmetric FEM. The pan classes are round 4's assumed basis. The yields are
> model results on that basis. Bench measurement of the real coil on real pans replaces all of it (§6).

- **Board / stage:** native-21 stage 14, `codex/power-stage-integration`; tank 5 × TDK B32654A1104K000 = 0.50 µF.
- **Date / tools:** 2026-10-10; ngspice 45.2; Miniforge Python 3.12 (numpy 2.4, scipy 1.18); Claude Opus 5.5.
- **Folder name:** the folder is called `round5-coil-od210` because the brief started as a Ø210 check. On 2026-10-10 the enclosure session ruled Ø210 out on coil cooling (`output/temper-r33-studies/09-coil-210-strayfield/REPORT.md`), so the brief was retargeted to the R34 candidate. Ø210 survives here as one comparison row.

## Verdict

1. **Coupling.** The R34 two-section winding (r 26–68 / gap / r 76–114, OD ≈ 228) couples to pans **the same as R32's uniform r 22–116 winding**, within the model's resolution.
   - Reflected R per µH of L0: R34/R32 = 0.96–0.99 at µ 100, and 0.95–1.00 over µ 30–1000 and 160–260 mm pans.
   - Inductance drop: R34/R32 = 0.96–0.98 (µ 30–100).
   - The gap costs nothing measurable, so the choice between the two windings is mechanical and thermal, not electrical.
2. **Full-power yield at 120 V is low for both, and nearly the same.** Full power here means reaching the 11.1 A input hold, 1239 W. The 22 A tank ceiling binds in 38–45 of 45 grid cases.

   | Pan base Ø | R34 Ø228 two-section | R32 Ø240 uniform |
   |---|---|---|
   | 180 mm | 0.2 % | 1.0 % |
   | 220 mm | 13.0 % | 15.7 % |
   | 260 mm | 20.0 % | 23.3 % |

   The figures are MC means over the five pan classes, FHA calibrated against ngspice to 0.3 %. Per class, cast iron reaches 41–55 % on ≥ 220 mm pans; enamelled steel and clad multiply reach 1–10 %.
3. **A smaller coil couples more R per µH but cannot be cooled.**
   - The round-4 basis coil (Ø180 on a 200 mm pan) yields 25.9 %.
   - Ø210 two-section on a 220 mm pan yields 14.6 %, only +1.6 points over R34. It is out on cooling (R33 study 09).
4. **Resonance and ZVS.**
   - With R34 at 66.34 µH installed, nominal loaded resonance is **33.8–35.6 kHz** (220 mm pan). With L0 ±10 % and C ±10 % it spans **27.2–43.7 kHz**, so the ZVS floor 1.05·f_res reaches 45.9 kHz.
   - The fixed 35 kHz floor is **not** a ZVS guarantee: nominal coupling already puts 1.05·f_res above 35 kHz. The CT_ZC guard (f ≥ 1.05·f_res, round 4 recommendation 4) is therefore **required**, not optional.
   - In the grid, f/f_res ≥ 1.21 and the FHA phase is ≥ 54°.
5. **Stress, at 22 A for every geometry:**
   - **Capacitors:** each B32654 part carries 5.15 A in the worst share, **0.86×** TDK's 85 °C curve at 35 kHz (unchanged from DECISIONS 2026-10-09). The worst-case voltage is 194 V RMS against the 500 Vac rating.
   - **Tank peak:** **47.5–47.9 A**, up to 0.6 A over the stage-13 Kelvin band's 47.32 A low corner, and over the 45 A firmware peak limit in 17–32 of 45 cases. The firmware tank-peak limit (DECISIONS 2026-10-09) stays mandatory.
6. **Bank value.** **0.50 µF stays.** Changing C moves resonance but not the reflected R, and reflected R is what limits power under the 22 A ceiling.
7. **L target: more turns would help. 70 µH has no margin on the loaded-L floor.**
   - Reflected R scales as N², so at the 22 A ceiling the power does too. Yield on 220 mm pans rises from 12–13 % at 66 µH installed to **22–25 %** at 75–80 µH installed (`l-sweep-mc.csv`), and the 47.32 A shunt corner is no longer exceeded (+0.07 A at 75 µH).
   - The cost is floor-limited operation on weakly coupled corners: 2 cases at 75 µH, 11 at 82 µH. That costs power, not safety.
   - The new loaded-L floor (§4) passes a nominal 70 µH coil but **fails a −10 % one**. A nominal 80 µH coil passes at −10 %.
   - **Recommendation:** RFQ the coil at 70 µH (the accepted value) **and** quote an alternate at **80 µH free-air** (≈ 76 µH installed, about 21 turns against 19.6). Both carry the same R_ac ≤ 0.25 Ω. Adopting 80 µH is a power-stage decision; it changes `coil_mc.rs`, the firmware resonance tables and the R32 installed value.
   - **R_ac at 80 µH.** 80 µH needs about 7 % more turns (L ∝ N²), and in the same winding window R_ac rises about as N² (+14 %). So 80 µH meets 0.25 Ω only with better copper fill. That is why it is an alternate, not a change.
8. **Control Freak inductance range (53–70 µH est.) in this tank.**
   - 70 µH is fine.
   - At 53 µH installed, the controller cannot hold 22 A in continuous mode: 10/45 cases need burst at 60 kHz, the tank peak reaches 61 A, and the capacitor reaches 1.13× its curve. Its estimated low end does not suit the 0.50 µF / 35–60 kHz envelope.

## 1. Sources and what they can and cannot give

- **[ON] onsemi AND9201/D, *The Effect of Pan Material in an Induction Cooker*, Rev. 0, Jan 2015.** p. 4 Table 1 lists the pans; p. 7 Figs. 9–10 give L and R from 1 kHz to 1 MHz. The fetched copy's SHA-256 `eca2fff5…` matches round 4. **It states no coil or pan dimensions**: a full-text search finds only the "1/4" (6 mm)" base thickness on p. 4. It cannot scale coupling with OD.
- **[IFX] Infineon UG-2023-15, EVAL-IHW25N140R5L user guide, Rev. 1.0.** p. 21 Fig. 16 gives the kit coil's L and R with and without a vessel. The text below the figure says cookware should sit "at a distance of 5 to 10 mm above the coil". No coil diameter is given; SHA-256 `db2816dd…`.
- **[PAS] Pascual, Acero, Carretero, Llorente, Burdío, *IEEE Access* 11 (2023) pp. 79275–79284.** It models the inductor–load system as series R_eq–L_eq from an axisymmetric electromagnetic model (pp. 79275–79276). Its inductors are 145 mm / 24 turns (p. 79279) and 180 mm / 19 turns (p. 79281).
- **Not retrieved.** The Acero/Lucía/Burdío papers on pan size could not be retrieved: zaguan.unizar.es refused connections (ECONNREFUSED) on 2026-10-10. No value in this round comes from them.
- **Consequence.** No published chart gives k or R_eq against coil OD and pan diameter for a Temper-like coil. This round therefore computes the **ratios** with an axisymmetric FEM (the [PAS] method class) and applies them to round 4's published-anchor classes. That transfer is the main assumption.
- **Repo sources:**
  - `output/temper-r32-studies/06-emi-strayfield/fem_axi.py` (solver, copied byte for byte, SHA-256 `f2d21553…`) and its R32 geometry;
  - `output/temper-r33-studies/09-coil-210-strayfield/REPORT.md` (R34 winding, Ø210 cooling verdict);
  - `output/temper-reference/control-freak-teardown/coil-estimate.json`;
  - round 4 (`../round4-assumed-basis/`: classes, deck, solver);
  - DECISIONS 2026-10-09: bank, R32 66.34 µH, the 47.32–97.77 A Kelvin band, the 45 A firmware peak limit.
  - The bank review gives B32654 at 5.97 A per part at 35 kHz / 85 °C (TDK p. 57, read by eye ±10 %).

## 2. Coupling vs geometry and pan diameter (`scripts/coupling.py` → `outputs/coupling*.{json,csv}`)

**FEM setup.**
- R32 stack: winding Z 98.5–102.5; 8 homogenised ferrite bars 20 mm wide, µ 2000, Z 93.5–97.5; glass Z 106–110; 2 mm steel pan at Z 110–112; base plate and roof ring present (the installed condition).
- Solved at 40 kHz, at 1 turn, with the pan as linear µ 30/100/300/1000 and ρ 0.6 µΩ·m.
- Two-section windings carry equal current in series, with uniform turn density.

**Validation against R32 study 06.** The installed/free ratio of the Ø240 winding is 0.9496 (R32: 0.948 → 66.34/70). kl and r at µ 100 on a 220 mm pan are 0.501 / 0.0496 Ω/µH (R32 `calibrate_pan.json`: 0.501 / 0.0501).

**How the ratios are used.** The linear-µ pan cannot reproduce round 4's anchors in absolute terms (R32 study 06 says so too). Only ratios to the round-4 basis coil (Ø180 continuous, r 22–90, on a 200 mm pan) are used:
- f_k = (1−kl)/(1−kl_ref) and f_r = r/r_ref;
- per class, kl′ = 1 − (1−kl)·f_k and r′ = r·f_r, at µ 100;
- at µ ≥ 300 the linear pan's magnetisation cancels the inductance drop (kl → 1), so f_k is meaningless there. f_r is robust across µ.

| Geometry | Pan Ø | kl (µ100) | f_k µ100 (µ30) | f_r µ100 (µ30–1000) |
|---|---|---|---|---|
| Basis Ø180 cont. (ref) | 200 | 0.594 | 1.00 | 1.00 |
| **R34 Ø228 two-section** | 180 | 0.574 | 1.05 (0.97) | **0.73** (0.71–0.76) |
| | 220 | 0.516 | 1.19 (1.11) | **0.88** (0.87–0.97) |
| | 260 | 0.510 | 1.20 (1.13) | **0.92** (0.89–1.07) |
| **R32 Ø240 uniform** | 180 | 0.558 | 1.09 (1.01) | **0.76** (0.74–0.78) |
| | 220 | 0.501 | 1.23 (1.14) | **0.89** (0.88–0.99) |
| | 260 | 0.495 | 1.24 (1.15) | **0.93** (0.89–1.11) |
| Ø210 two-section (out) | 220 | 0.547 | 1.11 (1.06) | 0.91 (0.90–0.97) |

**Turns** (FEM homogenised bars):
- R34: 19.6 for 70 µH free-air, installed/free 0.950;
- R32: 19.9 turns, 0.950;
- Ø210: 20.1 turns, 0.958.

**Reading the table.**
- Pan diameter dominates.
- Pans smaller than the winding lose 20–27 % of reflected R per µH against pans that cover it.
- Coupling saturates once the pan base reaches about the winding OD: from 220 to 260 mm, kl moves ≤ 1.1 % and r ≤ 4 %.

## 3. Grid (`scripts/run_grid5.py` → `outputs/grid5-*-cases.csv`) and yield (`scripts/analyze5.py`)

**Grid setup.**
- Round 4's solver, deck and envelope, unchanged: 35–60 kHz; f ≥ 1.05·f_res; 22 A RMS; 11.1 A × 0.93 × V; bisection to 10 Hz.
- Five classes × low/nom/high corners × 108/120/140 V, at a 1710 W request: 45 cases per configuration and 12 configurations, at 4 workers.
- L0 is the installed value. Coil R_ac at 40 kHz is 0.168 / 0.21 / 0.25 Ω for the low / nom / high corner, with R ∝ f^0.55.

**MC yield.** 4000 draws per class and line. Each draw is uniform over the class's kl and r range, L0 ±10 %, C ±10 % and R_ac 0.168–0.25 Ω. The FHA solve is calibrated against ngspice: P ratio 1.0014–1.0034, I ratio 1.0007–1.0018 over all 540 cases.

| Config (installed L0) | 120 V grid full-power | MC yield 108 / 120 / 140 V | f_res nom (tol.) kHz | Max tank pk A | Cap part / TDK curve | Coil loss max W |
|---|---|---|---|---|---|---|
| Basis Ø180, 200 mm pan | 4/15 | 44 / 26 / 7 % | 32.4–33.6 (26.7–40.3) | 47.24 | 0.86 | 121 |
| R34 Ø228, 180 mm | 0/15 | 3 / 0.2 / 0 % | 32.7–34.1 (26.8–41.1) | 47.91 | 0.86 | 123 |
| **R34 Ø228, 220 mm** | 2/15 | 29 / 13 / 2 % | 33.8–35.6 (27.2–43.7) | 47.61 | 0.86 | 124 |
| R34 Ø228, 260 mm | 2/15 | 37 / 20 / 4 % | 33.9–35.7 (27.3–44.0) | 47.52 | 0.86 | 124 |
| R32 Ø240, 180 mm | 0/15 | 6 / 1 / 0 % | 33.0–34.5 (26.9–41.8) | 47.87 | 0.86 | 123 |
| **R32 Ø240, 220 mm** | 2/15 | 32 / 16 / 3 % | 34.1–36.0 (27.3–44.4) | 47.61 | 0.86 | 124 |
| R32 Ø240, 260 mm | 3/15 | 41 / 23 / 6 % | 34.2–36.1 (27.4–44.7) | 47.51 | 0.86 | 125 |
| Ø210, 220 mm (out) | 2/15 | 31 / 15 / 3 % | 33.2–34.8 (27.0–42.3) | 47.52 | 0.86 | 123 |
| R34, 53 µH (CF low) | 0/15 | 11 / 4 / 4 % | 38.1–40.1 (30.7–49.3) | **61.46** | **1.13** | 176 |
| R34, 58 µH | 1/15 | 17 / 6 / 1 % | 36.3–38.2 (29.3–46.9) | 51.95 | 0.94 | 131 |
| R34, 75 µH | 2/15 | 38 / 22 / 6 % | 31.6–33.3 (25.5–40.9) | 47.25 | 0.86 | 118 |
| R34, 82 µH | 1/15 | 39 / 27 / 9 % | 30.2–31.7 (24.3–39.0) | 46.98 | 0.86 | 114 |

**Per-class MC yield at 120 V** (`outputs/yield-mc.csv`):

| Class | R34 220 mm | R32 220 mm | R34 260 mm | R32 260 mm | R34 75 µH, 220 mm |
|---|---|---|---|---|---|
| Cast iron | 41 % | 45 % | 52 % | 55 % | 51 % |
| Enamelled steel | 3 % | 5 % | 7 % | 11 % | 10 % |
| 18/10, ferromagnetic base | 6 % | 10 % | 15 % | 19 % | 20 % |
| Thin stainless | 14 % | 18 % | 22 % | 27 % | 26 % |
| Clad multiply | 1 % | 2 % | 4 % | 6 % | 4 % |

Median delivered power at 120 V for R34 on 220 mm pans is 904–1187 W, against the 1239 W hold.

**Other results.**
- **ZVS:** f/f_res ≥ 1.21 and FHA phase ≥ 54° in every configuration. The crest-edge current is ≥ 28.7 A, always inductive.
- **Capacitor voltage:** ≤ 199 V RMS and ≤ 398 V peak, against 500 Vac / 1600 Vdc.
- **Window floor:** floor-limited cases appear only at L0 ≥ 75 µH.
- **Coil loss:** the coil-loss column is I²·R_ac(f) at the grid's 0.25 Ω corner, so it is ≤ 125 W at 66 µH. It sits inside R32's 200 W design figure.

## 4. Loaded-L acceptance floor (`scripts/floor.py` → `outputs/floor.json`)

```
Fixed-floor ZVS guarantee (old §2 method):
  f_res,max = 35 000 / 1.05 = 33 333 Hz;  C_worst = 0.50 µF × 0.90 = 0.45 µF
  L_loaded,min = 1/((2π·33 333)²·0.45 µF) = 50.66 µH
  → a 66.3 µH-installed coil needs kl ≥ 0.76 on EVERY pan. The basis nominal is 0.63–0.69, so this cannot
    be an acceptance criterion. ZVS rests on the CT_ZC guard.
Window-top bound (binding for native-21):
  x_reg = max f/f_res the grid needs to hold 22 A / 11.1 A without burst = 1.45 (Ø228/Ø240, 108–140 V)
  f_res,max = 60 000 / 1.45 = 41 379 Hz
  L_loaded,min (most strongly coupled pan in the population) = 1/((2π·41 379)²·0.45 µF) = 32.87 µH
Transfer to the reference pan (cast iron or ferritic, base ≥ winding OD):
  kl population minimum / kl reference-class nominal = 0.4998 / 0.6308 = 0.792  (Ø228, 220 mm, round-4 classes)
  L_loaded,min on the reference pan = 32.87 / 0.792 = 41.5 µH
Ratio screen (L_loaded on the reference pan / L_free), 70 µH design: 0.54 (floor at L +10 %) to 0.77 (cast-iron kl max)
Nominal 70 µH coil: 66.5 × 0.631 = 41.95 µH, passes. At −10 %: 37.75 µH, FAILS.
Nominal 80 µH coil: 47.94 µH; at −10 %: 43.15 µH, passes.
```

**Caveats.**
- x_reg and the 0.792 transfer both come from the assumed basis.
- The floor must be re-derived once the first coil is measured on the reference pan **and** on the population pans (§6 item 1).

## 5. Answers

- **Ø228 two-section against Ø240 uniform:**
  - **Electrically equivalent:** within 1–5 % on reflected R and 2–4 % on the inductance drop. Full-power yield differs by ≤ 3.3 points (R32 slightly ahead), which is inside the model's resolution.
  - **Resonance:** essentially identical (R34 is 0.3 kHz lower).
  - **Choice:** R34 is the better *package* (cooling, field, combed former, eye clearance; R33 study 09), and costs nothing in the tank.
- **Ø210:** a +1.6-point yield gain on 220 mm pans does not justify a coil that cannot be cooled at 22 A.
- **0.50 µF:** keep it.
- **L target:**
  - **Keep 70 µH** as the RFQ base, as accepted in R32.
  - Quote an **80 µH alternate**; it is the better tank target if R_ac ≤ 0.25 Ω is still met.
  - Do not go below about 62 µH installed: peaks pass the shunt corner, burst is needed at 60 kHz, and the bank is overstressed.

## 6. What the bench must measure first

1. **The first R34 sample's L and R, 20–60 kHz:**
   - free air;
   - installed;
   - on the reference pan and on the five class pans at 180 / 220 / 260 mm.
   - This replaces f_k/f_r, x_reg and the 0.792 transfer, and the floor is then re-derived.
2. **R_ac(f) hot (100 °C),** checked against the 0.25 Ω requirement.
3. **Tank peak against the real shunt trip** at 22 A on the lowest-R pan (unchanged from round 4).

## Reproduce

```sh
python3 scripts/coupling.py          # FEM, ~15-25 min single-threaded
python3 scripts/run_grid5.py         # 12 configs x 45 cases, 4 ngspice workers, ~15 min
python3 scripts/analyze5.py          # summary5.json, yield-mc.csv, l-sweep-mc.csv (seeded MC)
python3 scripts/floor.py             # floor.json
```

The grid needs the sim-kit vendor model in place (round 4 "Reproduce"). It imports round 4's
`run_grid.py`, `basis.py` and `tank_basis.cir` unchanged.
