# Board-face airflow for the 28 A ceiling on hot copper (2026-10-16)

Analysis lane for DECISIONS 66, reviewed at integration. B3 runs were made on a byte-copy snapshot of the unit at 206171acc; run files and snapshots live outside git at `runs-native21/airflow28/` (runs/, snap/, s21snap/). Scripts default to those paths.

# Board-face airflow for the 28 A tank ceiling, on hot copper (DECISIONS 66)

Analysis lane, 2026-10-16. Nothing written to any git worktree.

- **Unit:** native-21 power board, PS = `worktrees/ps-integrate/zapote/power-stage-120v`, HEAD 206171acc.
- **Board:** s47 integration board 83355da5 (copper key 387b3e2d), S18 B3 model.
- **Model:** a byte copy of PS HEAD's round5-native21 tree and the files it reads, at
  `worktrees/runs-native21/airflow28/snap/` (`SNAPSHOT.txt`).
- **Run files:** `worktrees/runs-native21/airflow28/runs/<mode>/bay<B>/`.
- **Scripts:** `scripts/` beside this file.

Every case is solved as the gate solves it: hot copper (the default), each case at its own bay, I_line 13.5 A, FET tab ties
from `fet_case`, both meshes, and the gate's estimator `Q(0.25) + 3|Q(0.25) − Q(0.5)| + (bay − 50)`.

## 0. Answer

1. **Minimum board-face h at 28 A, on hot copper.** B3's own knob, h on both faces of the whole board and on every
   part body:
   - **h ≥ 31 W/m²K with ≤ 61 °C air** (fails at 30, passes at 31; interpolated zero 30.7);
   - **h ≥ 27 with ≤ 55 °C air** (26 / 27; 26.4);
   - h ≥ 24 with ≤ 50 °C air (23 / 24).

   In every case the binding pair is:
   - the laminate 1 mm-block copper at R5.4 (x 38.5, y 15.5, F.Cu, against the 130 °C MOT);
   - **R12's 2512 terminal derating**, 0.3 K behind it.

   The laminate ratchet and the rated-part ratchet cross within 0.2 W/m²K of each other at every ceiling.
2. **The faces both count.**
   - **Top face only** (bottom face kept at h 10) needs **h_top ≥ 47 (61 °C) / 38 (55 °C)**. There the FET-row copper
     binds, on B.Cu at (44.5, 19.5).
   - **The top-face hot region alone is not enough at 61 °C.** Over the hot corner only (x 0–125, y 0–90), the top face
     passes at **41 at 55 °C**. At 61 °C the tank copper outside that region, at (140.5, 98.5) between J2/J5, T1 and the
     bank, levels off at 130.0 °C (h 54: −0.5 K; h 63: −0.0 K).
   - **Corner plus tank path** (x 0–195, y 0–120) needs **47 at 61 °C** (46 / 47; 46.8), the same as the whole top
     face.
3. **The airflow-r1 jet strip does not reach 28 A on hot copper.** That is temper-8d's design, 8 × Ø3 mm jets on
   x 0–90, y 7–23.5, at its design h_top 100.
   - At 55 °C it fails by −4.0 K; at 61 °C by −10.2 K.
   - The binding copper is at (73.5, 4.5) In2.Cu between Q2 and BR1, outside the strip. At 61 °C U26 is also over,
     at −3.0 K.
   - The superseded cold-copper "required h_top 45 / 59" cannot be re-stated as a strip-only number.
   - **What works: the R45 jet strip at h 100 plus a base face flow over both faces.** The base flow needs
     **h ≥ 16 at 61 °C** (15 fails −0.7 K, 16 passes +0.7 K) and **h ≥ 12 at 55 °C** (10 −4.0, 12 +0.4).
   - Every S21 row passes there: R75 +4.2 / +4.3 K, C127 / C129 +4.6 / +6.0 K, U3 TJ +9.9 / +12.6 K.
   - It binds on the FET-row copper at (73.5, 4.5) In2.
4. **In enclosure terms** (§5):
   - **Air speed:** turbulent flat-plate, the jet lane's own correlation, no credit for radiation or natural
     convection. h 31 on both faces needs about **5.3 m/s** along x over the corner and tank path (195 mm run, 120 mm
     wide), and **5.9 m/s** along the whole board. With the ×1.2 margin, h 37: 6.7 / 7.4 m/s. A laminar, untripped
     face would need 11.8–17.6 m/s.
   - **Flow:** in 10 mm free gaps on both faces that is **27 CFM** for the corner and tank path and **47 CFM** for the
     whole 190 mm board (34 / 59 at ×1.2). In 25 mm gaps, 68 / 118 CFM.
   - The both-face requirement was solved on the whole board (B3's h). That the corner plus tank path is enough is
     shown for the top face (zone2 = whole top, 47); for both faces it is inferred, not solved.
   - **Against the D-18 blower:** its whole sink branch is 8.6–19.9 CFM. **A parallel face flow at this h is a second
     air mover, not a bleed.**
   - **Jets plus base flow (the recommended route):** the base h 16 (×1.2 = 19) is about **2.3 m/s** (2.7 at ×1.2)
     along x over the corner and tank path (195 mm run, 120 mm wide), tripped. That is **12 CFM** (14 at ×1.2) in 10 mm
     gaps above and below the board, plus the 0.48 CFM jet bleed. At 55 °C (h 12) it is 1.6 m/s and 8 CFM.
5. **What still fails at 28 A with that airflow:**
   - Nothing thermal in B3 or S21. At h 31 / 61 °C every S21 row is ≥ +7.3 K: R58 +7.3 K, R75 +8.4 K, C129 +11.2 K,
     J1 +20.6 K, U26 +24.2 K. U3 TJ is 98.7 °C (+26.3 K). PS2's local air is +4.2 K; it does not depend on h.
   - **The resonant bank: 1.045× TDK's 85 °C curve at 35 kHz.** The curve takes no air temperature and no h (F_T = 1.0
     below 85 °C, ΔT ≤ 20 K), so airflow does not move the rating. Two things close it:
     - the c34 bank (B32643B8104J000, 0.831);
     - a bench ΔT ≤ 14.5 K at 28 A under the airflow (0.85² × 20 K).
   - **S23, the OCP floor common-mode term:** −1.75 A at c28. It is electrical, so airflow does not touch it.
   - **J1:** its row uses Phoenix's 6 mm² own-rise curve. The 14 AWG cord case is still not modelled.
6. **Margin.**
   - **Face flow alone:** at h_req × 1.2 (h 37 at 61 °C, h 33 at 55 °C, solved), every gated row is ≥ +4.2 K at 61 °C
     (PS2's fixed row; the laminate +6.6 K) and ≥ +8.5 K at 55 °C.
   - **Jets plus base:** at base ×1.25 (h 20 at 61 °C, h 15 at 55 °C), every gated row is ≥ +4.2 / +5.5 K and every
     S21 line ≥ +8.6 K.
   - Near h_req the margin rises 1.1–1.3 K per W/m²K (face flow) and 1.4 K per W/m²K (base under the jets).
   - h_req × 1.2 is defensible as the design number, and the measured h, not the correlation, is the release
     evidence.
   - The ×1.2 margin covers:
     - the correlation spread (laminar / turbulent: 1.6× in velocity);
     - air at the hot corner 2–4 K above the inlet (§5.3);
     - the R_on 0.217 W bound (bench reading open).

## 1. The knobs B3 has for airflow

| Knob | Where | Physical meaning | Air it convects to |
|---|---|---|---|
| `c<ceil>_h<h>` (h, integer W/m²K) | `thermal_body.assemble`: `conv = h·area` on the top and bottom sheets of every board cell; `build_network_parts`: `h_loc = h` for every part body's air path | One film coefficient (convection plus radiation, lumped) on **both faces of the whole board** and on **every part body**: generic bodies r_top + 1/(h·A_top); C38–C41 fin `film_body_g_air(h)`; PS2 `h·5246 mm²` | Board cells and generic bodies: the bay. **C38–C41 and PS2: bay + 15 K** (`FILM_HF_AIR_RISE_K` = `MODULE_AIR_RISE_K`), at any h |
| `_jet<h_top>[a<air>]` | `thermal_body.TopRegion` on `run_basis.JET_REGION` (x 0–90, y 7.0–23.5 mm, inclusive, on cell and heat-row centres) | Top-face cells in the region at h_top. Bodies whose heat-row centre is in the region (R5, R10/R12/R18/R20, R53/R54/R57/R58) at h_top. Everything else stays at h, including the whole bottom face | The region's air: `a<air>`, or the bay. A credited film cap or module takes the region air instead of bay + 15 K ("the jet sweeps the board's warm layer away") |
| `@<bay>` | `run_basis.one`, `copper_tcr air_c` | The air temperature of the convection boundary condition. Hot copper is solved at that absolute T (not shift-invariant). FET tab tie = `fet_case.t_case() − bay`, with the sink at the firmware fan law's 88.6 °C | It sets every air above |
| `--film-air-rise K`, `--module-air-rise K` | sens keys | C38–C41 / PS2 body air over the bay (default 15 K: the board's natural-convection layer, 12 K plus 3 K headroom) | — |
| `--jet-credit-refs` | `TopRegion.credit_refs` | Credits named bodies at h_top although centred outside the region | region air |
| `--module-gap-mm`, `--module-r-pad` | PS2 sensitivities | Bottom-face gap path; pin path (default 15 K/W) | — |

**How the film caps and PS2 pick up air temperature.**
- C38–C41 convect from their 9.0 × 17.5 × 18.0 mm box. The model is a fin from the end contacts, k 0.2 W/mK, at the
  local h, to air at bay + 15 K. The gated row is `top_bound_c`: the body tied to its hotter pad through copper leads.
- PS2's case node carries the whole 1.348 W. Its pins go to the pads at 15 K/W, and its case loses h·5246 mm² to air at
  bay + 15 K.
- The PS2 gated row rates PS2's local air, est = bay + max(15 K, layer_factor(24 mm) × the 10 mm ring excess). With
  forced h the ring cools, so the 15 K floor sets it at every h: **+4.2 K at 61 °C and +10.2 K at 55 °C, whatever the
  airflow** (uniform mode).
- In a region that credits PS2 (top mode only), its air becomes the bay, and the row reads +17.5 / +23.3 K. There its
  pins carry 0.04 W *into* the module, which the gate refuses ("the board heats it"). This study waives that one guard
  and flags the row (`airflow_search.gate()`).

**What h10 and h25 mean.**
- **h 10 is still air, the release basis.** The audit (`audit-2026-10-15/README.md`) puts natural convection at
  7.5–8.4 W/m²K on the top face and about 4 on the bottom. Radiation adds up to 9–10 only where a face sees cool walls.
  There is no forced velocity. B3 has no radiation term; h 10 is the lumped still-air value.
- **h 25 is `run_study.py`'s legacy "fan airflow over the board".** No enclosure record ever supplied it (DECISIONS 46).
  On the jet lane's correlation it is 4.5 m/s tripped (11.5 m/s laminar) along the 290 mm board, or 3.4–3.6 m/s over a
  90–125 mm hot-corner run.
- The jet lane converts jets to h with Martin (1977) × 0.6. In `delivery.py`, 0.48 CFM through 8 × Ø3 mm gives
  h 100 design / 167 estimate.

**Velocity correlation used here.** The same correlation as `delivery.py`'s `parallel_flow_alternative`: a flat plate
from the leading edge over run L, with R43 `coil_thermal` air (k 0.0285, ν 1.8e-5, Pr 0.71, ρ 1.09, cp 1005).
- Laminar: Nu_L = 0.664 Re^0.5 Pr^1/3.
- Fully turbulent: Nu_L = 0.037 Re^0.8 Pr^1/3. This is the tripped boundary layer of a populated board, and the jet
  lane's headline figure.
- h_forced = h: no natural-convection or radiation credit on top.
- Control: h 73.2, L 90 mm gives 30.5 / 12.8 m/s, as in `delivery.json`.

## 2. Method

**Search** (`scripts/airflow_search.py`).
- Each series (ceiling, bay, mode) is bracketed on integer h:
  - each round solves ceil(h*) − 1 and ceil(h*);
  - h* is the zero of the worst h-dependent gated margin, linear in 1/h between the bracket ends;
  - once c28 @ 61 had ≥ 3 points, h* came from a shape transfer of that curve (fit m = A + B f(h); `predict_next.py`).
    Checked on c28 @ 55, it predicted 25.8 / 26.9 against 26.4.
- A series stops at hi − lo ≤ 1. Bisection was used, not a grid: 6–8 solves per ceiling.
- **Rules** (`scripts/analyze.py`):
  - **all gated** = every gated row ≥ 0: the release rule, applied here at the case's own bay;
  - **laminate** = the `b3_laminate_margin_K` rows;
  - **rated parts** = every other gated row, the `b3_rated_part_margin_K` rows.
- "fail / pass" are solved h values. The zero is interpolated in 1/h between them.
- **Workers:** at most 6 B3 workers on the machine at a time, counting the s48 chain. The machine was shared at load
  25–90.

**Controls** (all pass):

| Control | Result |
|---|---|
| Snapshot solver vs the chain: re-solve c28_h10 @ 55 at 0.5 mm, compare with PS `b3-ratings/runs/c28_h10_p0p5.json` | 1 mm block, FET row and all 40 part tj: **0.0 K** |
| Snapshot gate on the chain's run files vs the committed `b3-ratings/margins.json` | 291 rows, **0.0 K**; release +1.2 K (R10), laminate −51.0, rated −51.2 (DECISIONS 66's "about −51 K") |
| S21 wrapper (`s21_airflow.py`) on the BASIS runs vs the committed `temp-ratings-2026-10-15/results.json` | 73 lines, **0.000 K** |
| U3 pad vs the S20 README (106.7 / 124.3 °C) | 106.2 / 123.6 °C: **−0.5 / −0.7 K**. The README is on pre-S18 run files, and S18 moved PS2's neighbours toward margin. Reported, not asserted |

## 3. Minimum h per ceiling: the ladder (both faces, whole board; release rule and ratchets)

`h fail / pass (zero)`, W/m²K. Every series is bracketed to 1 W/m²K.

| Tank ceiling (trip) | Air ≤ 61 °C: all gated | laminate | rated parts | binding at the pass | Air ≤ 55 °C: all gated | laminate | rated parts | binding at the pass |
|---|---|---|---|---|---|---|---|---|
| 18 A (18.9) | 10 / **11** (10.2) | passes at 10 | 10 / 11 (10.2) | R10 terminal derating +2.3 | **10** (still air) | 10 | 10 | R10 +4.8 |
| 20 A (21.0) | 12 / **13** (12.6) | 12 / 13 (12.4) | 12 / 13 (12.6) | R10 +1.0, laminate block +1.4 | 10 / **11** (10.7) | 10 / 11 (10.7) | 10 / 11 (10.7) | R10 +1.0, laminate block +1.1 |
| 22 A (23.1) | 16 / **17** (16.1) | 16 / 17 (16.1) | 10 / 16 (15.4) | laminate block +1.6 | 13 / **14** (13.8) | 13 / 14 (13.8) | 13 / 14 (13.2) | laminate block +0.5 |
| 24 A (25.2) | 19 / **20** (19.7) | 19 / 20 (19.1) | 19 / 20 (19.7) | R12 terminal +0.6 | 16 / **17** (16.9) | 16 / 17 (16.5) | 16 / 17 (16.9) | R12 +0.3 |
| 26 A (27.3) | 24 / **25** (24.7) | 23 / 24 (23.9) | 24 / 25 (24.7) | R12 +0.4 | 21 / **22** (21.2) | 10 / 21 (20.5) | 21 / 22 (21.2) | R12 +1.4 |
| 28 A (29.4) | 30 / **31** (30.7) | 30 / 31 (30.7) | 30 / 31 (30.5) | laminate block +0.3, R12 +0.6 | 26 / **27** (26.4) | 26 / 27 (26.4) | 26 / 27 (26.3) | laminate block +0.9, R12 +1.1 |
| 28 A at **50 °C** air | — | — | — | — | 23 / **24** (≈ 23.5) | | | laminate block +0.9 |

**Still air (h 10) margins** (worst gated, K):

| Air | 18 A | 20 A | 22 A | 24 A | 26 A | 28 A |
|---|---|---|---|---|---|---|
| 61 °C | −0.5 | −7.7 | −17.8 | −28.0 | −41.5 | −56.8 |
| 55 °C | +4.8 | −2.3 | −12.6 | −22.6 | −36.0 | −51.2 |
| 50 °C (28 A) | | | | | | −46.4 |

- The still-air release ceiling stays 17.5 A at 61 °C: c18 @ 61 is −0.5 K, against −0.7 K on s45 (DECISIONS 61) before
  S18's +0.2 K.
- **Binding rows change down the ladder:**
  - 18–20 A: R10 2512 terminal derating;
  - 22 A and 28 A: the laminate 1 mm block at R5.4;
  - 24–26 A: R12 2512 terminal derating.
  All three sit in the FET row / R5 strip (x 0–90, y 0–25), within 2 K of each other at every pass, so no single part
  change buys more than about 1 W/m²K.
- **Air temperature against h:** at 28 A, 6 K of air costs 4.3 W/m²K (0.72 per K, 55 → 61 °C) and 0.56 per K
  (50 → 55 °C). At 22 A it is 0.38 per K.
- **For firmware commissioning,** each ladder step needs a measured h at the hot corner ≥ the pass value above, at the
  air temperature measured there. Interpolate between the 55 and 61 °C columns; do not extrapolate above 61 °C.

## 4. Which face, which region (28 A)

### 4.1 Top face only (whole board top at h, bottom face at h 10; credited bodies to bay air)

| Air | fail / pass (zero) | binding at the pass |
|---|---|---|
| 61 °C | 46 / **47** (46.7) | laminate FET-row copper +0.2, block +0.5 (both on B.Cu at x 44.5, y 19.5, under R12 / Q3); R12 terminal +3.5 |
| 55 °C | 37 / **38** (37.9) | FET-row copper +0.1, block +0.5; R12 +2.3 |

The rated parts alone pass at 46 / 36 (zeros 42.2 / 35.6). With only the top cooled, the binding copper moves to the bottom face under the
FET row.

- Going from both faces at 31 to top 47 / bottom 10, 16 W/m²K more on the top replaces 21 W/m²K on the bottom.
- **So a W/m²K on the bottom face is worth about 0.75 of one on the top.** The faces are close to interchangeable,
  because the 1.6 mm board conducts well through its thickness. The top keeps the edge because the part bodies and the
  F.Cu hot spots are there.

### 4.2 Regions on the top face (bottom at h 10)

| Region | Air 55 °C | Air 61 °C |
|---|---|---|
| Hot corner, x 0–125, y 0–90 (FET row, R5, gate networks, C38–C41, C126–C129, R71–R75, drivers, RECOMs, U3, U26, U29) | 40 / **41** (40.9) | **not reached:** 54 −0.5 K, 63 −0.0 K (130.0 °C at x 140.5, y 98.5 F.Cu, outside the region) |
| Corner plus tank path, x 0–195, y 0–120 (adds J2 / J5, T1, bank C21–C152) | — | 46 / **47** (46.8): FET-row copper +0.1 K |
| Whole top face | 38 | 47 |

### 4.3 Where the heat binds (ranked), and the regions that matter

1. **FET row / R5 / gate-network strip, x 0–90, y 0–25 (both faces).**
   - Laminate block at R5.4 (38.5, 15.5) F.Cu; R12 (44.6, 12.4), R10 (62.6, 12.4) and R20 / R18 terminals; FET-row
     copper.
   - On the bottom face under it: (44.5, 19.5) B.Cu.
   - This region sets every ladder step.
2. **The bus / BR1 edge, x 60–85, y 0–7 (In2 at 73.5, 4.5).**
   - It becomes the hot spot when only the jet strip (y 7–23.5) is cooled.
   - It lies under the TO-247 bodies and BR1, where a jet box cannot reach. Both-face or bottom-face flow covers it.
3. **Tank path to the coil terminals, x 125–195, y 80–120: J2 / J5 (132, 70–86), T1 (135, 110), bank column (163–190).**
   - This binds at 61 °C once the corner is cooled (the 130.0 °C asymptote above).
4. **The HF film caps C38–C41 (y 28, x 2–83), C126–C129 (y 37) and R71–R75 (y 35).**
   - They bind only with still air or with jets alone (C40 −10.3 K at jet 60 / 61 °C).
   - Any face flow over the corner clears them: C40 +10.2 K at h 31.
5. **U26 (115, 81), U3 (114, 53), the drivers (y 51), the RECOMs U41 / U42 (y 61–66).**
   - U26 is −5.7 K in still air at 28 A / 61 °C and −3.0 K under the jet strip.
   - It passes by +24 K under whole-face flow.
6. **J1 (274.6, 9.2) and L1 (232, 31), far right.** Line current only. J1 is +0.5 K at release in still air; the c28
   ceiling does not change it. Flow reaching it adds margin (+20.6 K at h 31).

### 4.4 Jets (airflow-r1's strip), on hot copper

| Case | 55 °C | 61 °C | Binding |
|---|---|---|---|
| Jet strip h_top 60, rest h 10 | −16.8 K | −23.0 K | FET-row copper at (73.5, 4.5) In2; C40 −4.4 / −10.3; R12 −2.8 / −8.7 |
| Jet strip h_top 100 (the R45 design h), rest h 10 | **−4.0 K** | **−10.2 K** | FET-row copper (73.5, 4.5); U26 +3.2 / **−3.0** K; C40 +5.8 / −0.1 |
| Jet 100 + both-face base h 12 | **+0.4 K** (pass) | — | FET-row copper (73.5, 4.5) In2; block +1.2; C40 +9.3; U26 +9.6 |
| Jet 100 + both-face base h 15 | +5.5 K | −0.7 K | FET-row copper; block +0.1 at 61 °C |
| Jet 100 + both-face base h 16 | — | **+0.7 K** (pass) | FET-row copper; block +1.5; PS2 +4.2; C40 +8.6 |
| Jet 100 + both-face base h 17 | — | +2.1 K | FET-row copper |
| Jet 100 + both-face base h 20 (×1.25 of 16) | — | +4.2 K (PS2; laminate +5.5) | |

- **On hot copper, the strip alone does not carry 28 A at any h tested,** and the copper that binds is outside it.
- **S21 under the strip alone** (h 100):
  - at 61 °C: C127 −8.3 K, R72 −6.1 K, U26 −3.0 K, J1 −0.2 K, U3 TJ −3.4 K;
  - at 55 °C: C127 −1.7 K, R75 +0.2 K.
- The jet lane's 45.1 / 59.2 (cold copper, bay + 15 K cap air) is superseded, as DECISIONS 61 says. There is no hot
  strip-only number to replace it with.
- **Replace it with a pair:** strip at h_top 100, plus both faces at h ≥ 16 (61 °C) / 12 (55 °C).
  - S21 at that minimum: R75 +4.3 / +4.2 K; C129 / C127 +6.0 / +4.6 K; U26 ≥ +9.6 K; U3 TJ 112.4 / 115.1 °C
    (+12.6 / +9.9 K).
  - S21 at base h 20 / 61 °C and h 15 / 55 °C: every line ≥ +8.6 K.

## 5. Enclosure terms

### 5.1 Velocity and flow for the 28 A requirement

Turbulent (tripped) flat-plate velocity, with the laminar bound in brackets. Flow is that velocity × the width across
the flow × the free height over each face, summed over the faces that need it (`results/enclosure.json`).

**Both faces at h 31 (≤ 61 °C air); ×1.2 = h 37:**

| Flow path | v at h 31 | v at h 37 | CFM, 10 mm gaps, 2 faces | CFM, 25 mm gaps |
|---|---|---|---|---|
| Hot corner along x (enter at the x 0 edge, 125 mm run, 90 mm wide) | **4.75** (7.6) m/s | 5.97 (10.9) | 18.1 (22.8 at ×1.2) | 45.3 |
| Hot corner along y (90 mm run, 125 mm wide) | 4.38 (5.5) | 5.50 (7.9) | 23.2 | 58.0 |
| **Corner + tank path along x (195 mm run, 120 mm wide)**, the region that suffices on the top face (§4.2) | **5.31** (11.8) | 6.67 (17.0) | **27.0** (33.9 at ×1.2) | 67.5 |
| Whole board along x (290 mm run, 190 mm wide) | 5.86 (17.6) | 7.37 (25.3) | 47.2 (59.3) | 118 |
| Whole board along y (190 mm run, 290 mm wide) | 5.28 (11.5) | 6.63 (16.6) | 64.8 | 162 |

**Both faces at h 27 (≤ 55 °C air):** 4.0 m/s over the corner along x (5.0 at ×1.2), 15–19 CFM in 10 mm gaps.
Whole board along x: 4.9 m/s, 40 CFM.

**Top face only at h 47 (61 °C) / 38 (55 °C):**
- 8.0 / 6.1 m/s over the corner along x (laminar 17 / 11);
- 15 / 12 CFM in one 10 mm gap over the 90 mm corner.
- The corner alone is not enough at 61 °C (§4.2). Over the corner and tank path at h 47 it is 8.9 m/s and 22.7 CFM in
  one 10 mm gap (11.2 m/s at ×1.2).

For comparison, from `delivery.json`:
- the D-18 blower's sink branch carries 8.6 / 10.5 / 19.9 CFM at drive 0.46 / 0.55 / 1.0;
- the jet bleed carries 0.41–0.83 CFM.

**A face flow at h ≈ 30 is 15–60 CFM. That is a second fan** (a 60–80 mm axial fan moves 15–40 CFM free air), **not a
bleed from the push hood.** The jet lane's D2 reached the same conclusion for its 16.5 × 15 mm channel.

**Jets plus base flow** (R45 strip at h_top 100, plus both faces at the base h; `results/enclosure.json` →
`jetmix_base`). The run is along x over the corner and tank path (195 mm run, 120 mm wide), in 10 mm gaps above and
below:

| Base h (both faces) | Where it is the minimum | v tripped (laminar) | CFM |
|---|---|---|---|
| 12 | 55 °C | 1.6 (1.8) m/s | 8.2 |
| 15 | ×1.25 at 55 °C | 2.1 (2.8) | 10.9 |
| 16 | 61 °C | 2.3 (3.2) | 11.8 |
| 20 | ×1.25 at 61 °C | 3.1 (4.9) | 15.6 |

- The same base over the whole board along x is 2.6–3.4 m/s and 21–27 CFM.
- Over the 90 mm hot corner only, it is 2.1–2.8 m/s and 8–11 CFM. That is not enough at 61 °C: the tank path must be
  covered (§4.2).
- Base h 12–16 sits barely above still air's 10. B3's 10 already lumps natural convection and radiation, and
  h_forced = h credits neither.
- **So the base is a gentle bay through-flow, not a jet:** about 2 m/s across both faces. It can come from:
  - a small fan (40–60 mm class);
  - a second, open bleed from the push hood of about 12 CFM. At drive 0.55 that is more than the whole sink branch
    (10.5 CFM), so the blower would run harder. That cost is not evaluated here.

### 5.2 Inlet air temperature

- B3's "bay" here is the air that reaches the board face. The requirement is a pair, **(h, air temperature at the hot
  corner):**

  | Air | 50 °C | 55 °C | 61 °C |
  |---|---|---|---|
  | h at 28 A | 24 | 27 | 31 |

- Interpolate between the points; above 61 °C it is not solved.
- Air drawn from the kitchen intake (40 °C worst kitchen, D-18's 50 °C hood-air basis) lowers the requirement by about
  0.6 W/m²K per K against bay air.
- **The bay's own 78 °C stacked-allowance case is not covered at any h here.** At that bay PS2's local air is 93 °C, over
  its 85 °C maximum (S18).

### 5.3 Air heating along the board

- The board puts 29.5 W into the air at 28 A at h_req (run-file balance: convection 26.3 W plus bodies 3.3 W; 0.9–1.3 W
  more leaves through the FET drain leads to the sink).
- Bulk rise = 29.5 W / (ρ cp V̇) = 1.0–4.9 K over the paths in §5.1.
  - 27 CFM over the corner and tank path: 2.1 K.
  - The 12–16 CFM base flow under the jets: 3.6–4.8 K.
- The hot corner is the first thing the air should meet: enter at the x 0 end (C41 / Q5 side), or blow across y from the
  film-cap side. Otherwise the inlet limit is the corner air minus the upstream pickup. An x 290 → 0 run puts L1 / J1 /
  C5 / C6's heat upstream, about 2–3 K at 20–40 CFM.

### 5.4 Margin

- At h_req × 1.2 (h 37 / 61 °C, h 33 / 55 °C, solved), every gated row is ≥ +4.2 K at 61 °C and ≥ +8.5 K at 55 °C.
  - At 61 °C that is PS2's h-independent row. The laminate is +6.6 K and R12 is above it.
  - At 55 °C the laminate block is +8.5 K and R12 +8.8 K.
- The S21 rows at h 40 / 61 °C are ≥ +15 K (§6).
- Recommend **h_req × 1.2 as the design point** (37 / 33 W/m²K on both faces, or 56 / 46 on the top face alone). The
  release needs a **measured** h of at least h_req at the hot corner, from a heated-plate or IR bench, plus the
  board thermocouples DECISIONS 66 lists.
- The 1.2 factor is about the laminar / turbulent spread at a 90–125 mm run (1.2–1.6× in velocity). It is not a
  thermal-model allowance: K_MESH = 3 already bounds the mesh, and copper is already hot.
- **Jets plus base:** at base ×1.25 (h 20 at 61 °C, h 15 at 55 °C), every gated row is ≥ +4.2 K (PS2; the laminate
  +5.5 K) and every S21 line ≥ +8.6 K.
  - The jet h itself (100) is the jet lane's Martin × 0.6 design value; the estimate is 167.
  - The base is the number to margin and to measure.

## 6. Parts outside the B3 gate at the 28 A minimum h

`results/s21-c28-uniform.json` and `results/s21-c28-top-zone.json`. Worst ref per line, margin in K.

| Line | still air c28 @ 55 (committed S21) | **h 31 @ 61** | h 27 @ 55 | h 40 @ 61 (×1.29) | top 47 @ 61 | zone 41 @ 55 |
|---|---|---|---|---|---|---|
| R58 1206W4F100KT5E (terminal derating) | −42.2 | **+7.3** | +8.0 | +15.8 | +8.9 | ≥ +10 |
| R75 0603WAF4991T5E split bleed | −36.7 | **+8.4** | +10.0 | +15.4 | ≥ +10 | ≥ +10 |
| C129 6SVPC220MV | −33.8 | +11.2 | +12.8 | +18.0 | ≥ +10 | ≥ +10 |
| R13 0603WAF1002T5E | −32.9 | +20.6 | +20.5 | +29.9 | | |
| C59 / C122 / C97 / C148 MLCC | −11.2 / −10.7 / −8.9 / −0.6 | +32.6 / +33.7 / +34.7 / +37.5 | | | | |
| D7 PMEG6030EP | −9.4 | +34.8 | +35.6 | | | |
| U2 2EDR8259X | −3.4 | +33.0 | +35.5 | | | |
| U26 TPS7A4700 | +0.5 | +24.2 | +28.1 | +27.6 | | |
| J1 MKDS 5/2-9,5 (6 mm² own-rise basis) | +6.4 | **+20.6** | +25.4 | +23.2 | ≥ +10 | **+6.6** (outside the zone) |
| **U3 TPS70950 TJ** = pad + 38.7 K/W × 0.160 W (S19) | 129.8 °C, −4.8 | **98.7 °C, +26.3** | 95.2, +29.8 | 94.7, +30.3 | 99.0, +26.0 | 100.3, +24.7 |
| PS2 local air (B3 gated row) | +10.2 | +4.2 | +10.2 | +4.2 | +17.5 (guard waived) | +10.2 |

- **Every one of the 10 c28 S21 gaps closes** at the uniform h_req, at both air temperatures. The minimum over all 73
  lines is R58 +7.3 K.
- **J1:** it needs the flow to reach it, or stays at its still-air +0.5 K (release) / +6.6 K (c28 @ 55). The 14 AWG
  cord case (S21) is still open either way.
- **The bank (`bank_ratio_tdk_28A_35k` 1.045, c34):** the TDK curve has no air or h input, so it stays 1.045.
  - In B3's advisory rows the bank bodies are 99.8 °C at h 31 / 61 °C: C21 +10.2 K against 110 °C. That is board heat
    plus the board share only, not the self-heating.
  - What closes it: a bench ΔT ≤ 14.5 K at 28 A / 35 kHz under the airflow, or the c34 bank.
- **U3** passes at any face flow that reaches it (+26 K). Still air at c28 is −4.8 K; S19's Q1 grade and EN divider fix
  are separate.
- **S23** (OCP floor, −1.75 A at c28) is electrical and unaffected.
- **Jets plus base** (`results/s21-c28-jetmix.json`):
  - At the minimum (h 16 at 61 °C / h 12 at 55 °C): R75 +4.3 / +4.2 K, C129 / C127 +6.0 / +4.6 K, U26 ≥ +9.6 K,
    U3 TJ +12.6 / +9.9 K. Every other line is ≥ +10 K.
  - At ×1.25: every line ≥ +8.6 K.
  - **The jet strip alone at 61 °C fails S21 too:** C127 −8.3, R72 −6.1, U26 −3.0, J1 −0.2 and U3 TJ −3.4 K.

## 7. Requirement statement for temper-8d

> **Power-board airflow for the 28 A tank ceiling (native-21 s47, B3 on hot copper, 2026-10-16).**
>
> The R45 jet strip alone does not carry 28 A on hot copper. That is 8 × Ø3 mm jets at a design h 100 over board x 0–90,
> y 7–23.5 mm: it misses by 4 K at 55 °C air and 10 K at 61 °C. The copper that binds lies under the TO-247 / bridge edge
> and on the bottom face, where the jets do not reach.
>
> **Keep the jets and add a gentle through-flow over both faces of the board's hot end** (x 0–195, y 0–120 mm: the FET
> row, film caps, coil terminals, CT and resonant bank). Required film coefficient, measured on the bench:
> - **h ≥ 16 W/m²K** when the air reaching the board is at 61 °C;
> - **h ≥ 12 W/m²K** at 55 °C.
>
> Design to **1.25×: 20 / 15 W/m²K**, solved, with every rating ≥ +4 K. That is about **3 m/s along the board from the
> FET-row end** (x 0), tripped flat-plate, about **16 CFM through 10 mm gaps above and below**. The jet bleed's
> 0.5 CFM is on top.
>
> **Without the jets,** the same both-face flow must reach h ≥ 31 at 61 °C / 27 at 55 °C / 24 at 50 °C (design 37 / 33
> / 29): about 6–7 m/s, 30–60 CFM. Cooling only the top face needs h ≥ 47 / 38.
>
> **Air:** the air must meet the FET-row end first; it warms 2–5 K across the board. Air drawn from the kitchen
> intake instead of the bay lowers every figure (about 0.6–0.7 W/m²K per K). The 78 °C stacked bay is outside
> every case.
>
> **For a partial-airflow enclosure:** firmware raises the ceiling one step at a time against the measured h. Without
> jets, in W/m²K on both faces at 61 / 55 °C air:
>
> | Tank ceiling | 18 A | 20 A | 22 A | 24 A | 26 A | 28 A |
> |---|---|---|---|---|---|---|
> | h at 61 / 55 °C air | 11 / 10 | 13 / 11 | 17 / 14 | 20 / 17 | 25 / 22 | 31 / 27 |
>
> These are the minimum passing values; design to 1.2×. **The face flow is a second air mover (40–80 mm fan class), not
> a bleed of the D-18 sink flow.**

## 8. Did not match, and caveats

- **The airflow-r1 jet design misses 28 A on hot copper** by 4 K at 55 °C and 10 K at 61 °C (§4.4).
  - Its cold-copper basis gave a required strip h_top of 45 / 59 (bay + 15 K) or 73 / 97 (lead-only caps).
  - On hot copper the strip is no longer the right region. The hot spot moves under the TO-247 / BR1 edge (y < 7) and to
    the bottom face.
- **OPEN-ITEMS S2(d)** says U26 keeps 0.6–2.4 K at 28 A / 61 °C. That was cold copper and the jet case. On hot copper
  in still air, U26 at c28 @ 61 is **−5.7 K** (+0.5 K at 55 °C). Under the jet strip it is −3.0 K.
- **ENCLOSURE-REQUEST.md**'s "h 15 / 20 gives −27 / −42 K at R5.4, 28 A" is the cold-copper, pre-refine model. On hot
  copper at 55 °C, h 10 → 25 (both faces) moves the worst row 49 K, from −51.2 to −2.2.
- **The zone search at 61 °C** read −0.0 K at h 63 (est 130.0 = limit). The gate's rounded margin is −0.0, which Python
  counts as ≥ 0. It is treated here as not reached; it is an asymptote set by copper outside the region.
- **The PS2 pin-direction guard was waived in top mode.** There the board heats PS2 by 0.04 W through its pins. The
  gate refuses that case by design; the row is flagged, not used for the requirement.
- **The uniform mode keeps C38–C41 and PS2 at bay + 15 K air under forced flow.** That is conservative: forced flow
  thins the natural-convection layer the 15 K was set for. PS2's +4.2 K at 61 °C comes from this rule alone and does not
  move with h.
- **h_forced = h:** no radiation credit (8–10 W/m²K at ε 0.9 where a face sees cooler walls), and no mixed-convection
  credit.
- **Correlation spread:** turbulent vs laminar flat plate is 1.2–3× in velocity, depending on the run length. The bench
  must measure h, not velocity.
- **The flow values assume clear 10 / 25 mm gaps over the faces.** The board's tall parts would block or channel a real
  flow: TO-247s about 21 mm, film caps 17.5 mm, the bank 26.5 mm, PS2 24 mm.

## 9. Reproduce

```
# from any directory; read-only on PS (imports the snapshot)
python3 -I scripts/airflow_search.py search --series c28@61,c28@55 --mode uniform      # and the ladder series, top, zone, zone2
python3 -I scripts/airflow_search.py point  --mode jet --cases c28_h10_jet100@55,...
python3 -I scripts/airflow_search.py point  --mode jetmix --cases c28_h16_jet100@61,c28_h12_jet100@55,...
python3 -I scripts/analyze.py      # -> results/analysis.json
python3 -I scripts/enclosure.py    # -> results/enclosure.json
python3 -I scripts/s21_airflow.py --case uniform:c28_h31@61 --case uniform:c28_h27@55 --out results/s21-c28-uniform.json
python3 -I scripts/control_resolve.py   # the 0.5 mm re-solve control
```

- Run files: `worktrees/runs-native21/airflow28/runs/{uniform,top,zone,zone2,jet,jetmix}/bay{50,55,61}/` (outside
  git, 0.25 + 0.5 mm per case).
- S21 inputs: `airflow28/s21snap/`, which holds `git show HEAD:` of the ledger, BOM and margins, plus the chain's BASIS
  runs.
