# Task 05 round 4: resonant tank on an ASSUMED coil/pan basis

> **ASSUMED / PRE-MEASUREMENT.** Nobody has measured Temper's coil or any pan. Every
> coil and pan number below is a digitized published chart value, a repo-transcribed
> value, or a labelled engineering estimate. The capacitor limit is a bound we derived
> from the catalogue, not a CDE rating. Bench measurements replace all of it (see the end).

- **Board / stage:** native-21 full bridge, `codex/power-stage-integration` @ `8496f67c6`.
- **Date / tools:** 2026-10-09; ngspice 45.2; Miniforge Python 3.12.12; Claude Opus 5.5.
  Kit smoke test: `outputs/smoke-test.txt` ends `SMOKE PASS` (vendor model SHA-256 `02ac6634…`, not committed).
- **Evidence class:** simulation over an assumed load basis, plus a catalogue-derived bound. No hardware.
- **Verdict:**
  - **Grid complete.** 135/135 main cases and 27 supplemental cases were solved under the native-21 envelope.
  - **Tank design.** The bank value, ZVS margin, capacitor voltage and CT all fit the basis.
  - **Bank parts fail the conservative bound.** At the 22 A ceiling, C21/C22 (942C12P22K-F) exceed the conservative 70 °C current bound in 90/135 cases (up to 1.64×). They also exceed the best estimate in 30/135 cases (up to 1.045×). The catalogue therefore does not support the 22 A ceiling on these parts.
  - **Shunt OCP.** Envelope tank peaks reach the lower edge of the DC-return shunt OCP band.

## 1. Assumed coil/pan basis

### Model and how the sources transfer

The coil and pan form a series R_eq–L_eq load: [PAS] p. 79275–79276; [ON] p. 4–7; [IFX] Fig. 16.
Everything is normalised to the coil's no-pan inductance L0, as `coil_mc.rs` does:

    L_eq(f) = L0 · kl40 · (f/40 kHz)^β
    R_eq(f) = L0 · [ q40 · (f/40 kHz)^γ  +  r40 · (f/40 kHz)^α ]      (L0 in µH, q/r in Ω/µH)

For one winding geometry, L0, R_coil and the reflected pan R all scale with N². The
ratios kl, q and r therefore carry over to a 70 µH winding of similar geometry: Ø170–200 mm,
ferrite-backed, 5–10 mm gap. They do not carry over exactly to a different diameter, ferrite
layout or gap.

`TANK_COIL_SPECIFICATION.md` does not give turns or Litz detail. It is still the 88 µH / 300 nF
design from before native-21. Section 5 lists what is missing.

For orientation, at the same geometry L ∝ N². A 70 µH winding is then about 0.90× the turns of
the 87 µH Infineon kit coil (an estimate). The comparable published inductors are:
- Infineon kit: 170 mm, 87 µH;
- onsemi: 110 µH;
- [PAS] p. 79279/79281: 145 mm with 24 turns, and 180 mm with 19 turns.

### Anchors

The digitized anchors are in `outputs/anchors.csv`. Values are at 40 kHz, small signal, about 25 °C.

| Anchor | L0 µH | kl40 | r40 Ω/µH | q40 Ω/µH | α (pan R exp.) | β (L exp.) | γ (coil R exp.) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [IFX] kit coil + vessel | 87.0 | 0.683 | 0.0330 | 0.0041 | 0.60 | −0.11 | 0.59 |
| [ON] cast iron | 110.4 | 0.664 | 0.0350 | 0.0024 | 0.65 | −0.15 | 0.52 |
| [ON] 5-ply (430 exterior / Al core) | 110.4 | hidden¹ | 0.0299 | 0.0024 | 0.82 | — | 0.52 |
| [ON] Midea 430 SS | 110.4 | 0.646 | hidden¹ | 0.0024 | — | −0.16 | — |
| [ON] Duxtop 18/10, magnetic base (25 kHz) | 110.5 | 0.729 | 0.031² | — | — | — | — |
| [ON] aluminium | 110.4 | 0.485 | 0.0007 | 0.0024 | — | — | — |
| [MDPI] cast iron / stainless / Silargan³ | 110 | 0.816 / 0.744 / 0.628 | 0.034–0.036 / 0.026–0.028 / 0.018–0.020 | bracketed | — | — | — |

¹ At ≥30 kHz this trace runs under the cast-iron trace, within the line width (visual check). [ON] p. 9 concludes that "the type of magnetic material does not have an appreciable impact on the losses".
² Read at 25 kHz and scaled to 40 kHz with α = 0.62 (calculation).
³ Transcribed in the repo, not re-fetched. r is recomputed per the study's own 110 µH, with the coil R bracketed by q = 0.0024–0.0041.

### Coil (no pan)

| Quantity | Nominal | Min | Max | Basis |
| --- | ---: | ---: | ---: | --- |
| L0 (no pan, 20–50 kHz) | **70 µH** | 63 | 77 | Design value (power-stage README; `coil_mc.rs`). ±10 % is the tolerance TANK_COIL_SPEC row 1 imposes. ESTIMATE: no 70 µH coil is specified |
| L0 flatness 20–50 kHz | ±1 % | | | [IFX] 87.4→87.0 µH; [ON] 110.5→110.3 µH |
| R_ac, 40 kHz (q40 · L0) | **0.245 Ω** (q 0.0035) | 0.168 (0.0024) | 0.41 (0.0058) | [ON] 0.0024, [IFX] 0.0041. Max = TANK_COIL_SPEC row 5 ceiling (0.40 Ω / 88 µH) × 1.29 for a 100 °C winding (Cu 0.393 %/K, calculation) |
| R_ac at 30 / 60 kHz | 0.21 / 0.31 Ω | | | R ∝ f^0.55, with γ = 0.52 [ON] to 0.59 [IFX] |
| Unloaded Q at 40 kHz | ≈72 | | | Calculation |

### Pans

Values are the equivalent series parameters that the 70 µH coil sees (`outputs/basis-table.csv`).

| Pan class | kl40 nom (min–max) | L_eq at 40 kHz, µH | R_pan at 40 kHz, Ω | R_eq total at 30 / 40 / 60 kHz, Ω (nom; min–max) | α | f_res with 0.54 µF, kHz (nom; min–max over pan corner) | Q at f_res |
| --- | --- | --- | --- | --- | ---: | --- | --- |
| Cast iron | 0.69 (0.62–0.84) | 48.3 (43.4–58.8) | 2.38 (2.03–3.15) | 2.20 / 2.63 / 3.37; 1.84–4.56 | 0.62 | 30.6 (27.6–32.4) | 4.3 (3.8–4.7) |
| Enamelled steel | 0.66 (0.58–0.78) | 46.2 (40.6–54.6) | 1.82 (1.26–2.52) | 1.73 / 2.07 / 2.65; 1.20–3.75 | 0.62 | 31.4 (28.7–33.6) | 5.3 (4.3–6.8) |
| 18/10 stainless, ferromagnetic base | 0.71 (0.62–0.80) | 49.7 (43.4–56.0) | 2.10 (1.68–2.66) | 1.97 / 2.35 / 3.01; 1.55–3.93 | 0.62 | 30.2 (28.3–32.4) | 5.0 (4.2–5.6) |
| Thin stainless, single-ply ferritic | 0.67 (0.58–0.80) | 46.9 (40.6–56.0) | 2.10 (1.40–2.80) | 1.97 / 2.35 / 3.01; 1.32–4.11 | 0.62 | 31.1 (28.3–33.6) | 4.7 (4.0–6.2) |
| Aluminium-clad multiply (ferritic exterior) | 0.68 (0.60–0.80) | 47.6 (42.0–56.0) | 1.89 (1.26–2.38) | 1.71 / 2.14 / 2.92; 1.14–3.80 | 0.80 | 30.9 (28.3–33.0) | 5.5 (4.9–7.3) |
| Offset / small pan (SYNTHETIC, from `coil_mc.rs`) | 0.85 (0.80–0.90) | 59.5 (56.0–63.0) | 1.19 (0.84–1.54) | 1.21 / 1.44 / 1.84; 0.85–2.49 | 0.62 | 27.4 (26.6–28.3) | 9.4 (7.3–12.8) |
| No pan (fault/detection) | 1.0 | 70 | 0 | 0.21 / 0.25 / 0.31 | — | 25.1 | ≈60 |
| Aluminium / non-magnetic 18/10 (fault/detection) | 0.485 | 34 | 0.05 | 0.25 / 0.29 / 0.37 | — | **37.0** | ≈28 |

How the ranges were set (the `basis` fields in `outputs/basis.json` give the full wording):

- **kl ranges.** The anchor spread, widened by about 6 % at the low end for gap and centring (ESTIMATE).
- **r minimum.** About 12 % below the lowest anchor, for cold, small-signal readings and spread (ESTIMATE).
- **r maximum.** About 30 % above nominal, for a hot pan (ESTIMATE). Iron resistivity rises with temperature and R_sheet ∝ √(ρµ).
- **Small-signal caveat.** Small-signal ferromagnetic R understates large-signal R. This is not quantified here, and it makes the low-R corners conservative for current.
- **Thin stainless.** This class is ferritic and electrically thick: skin depth at 40 kHz is 0.07–0.2 mm for µr 100–700 and ρ ≈ 0.6 µΩ·m (calculation).
- **Non-magnetic single-ply 18/10.** It has no anchor. It is treated with aluminium as a load that pan detection must reject.

**Resonance including tolerances.** The coil is assumed at ±10 % and the 942C 'K' parts at ±10 %
(`outputs/basis.json`). On ferrous pans, the loaded resonance ranges from **24.9 kHz** (L0 +10 %,
kl max, C +10 %) to **37.6 kHz** (L0 −10 %, kl min, C −10 %).

### Fit with what the repo already assumes (`outputs/basis-vs-repo.csv`)

- **coil_mc.rs / round 3–4A pan classes.** The kl ranges overlap. The repo's cast-iron r40 (0.036–0.052) and 430-steel r40 (0.029–0.041) sit **about 20–26 % above** the anchors. The transfer note derived the MDPI values as (R_total − 0.34 Ω)/**87 µH**, the kit's L0, not the study's own **110 µH** no-load L. Renormalised, MDPI cast iron is r ≈ 0.035, which agrees with [ON] 0.035 and [IFX] 0.033. Higher r understates current for a given power, so the old classes are slightly non-conservative for tank stress.
- **Tri-ply guess.** coil_mc's `triply_clad_GUESS` (0.018–0.032) agrees with the [ON] 5-ply anchor (0.030).
- **Frequency exponent.** α = 0.5 (repo) versus 0.60–0.65 measured (0.82 for 5-ply).
- **Coil R.** The kit deck holds R_coil constant with frequency; the basis uses γ ≈ 0.55.
- **TANK_COIL_SPECIFICATION.md** (88 µH, ratio 0.68, 300 nF, 42–50 kHz) is not the native-21 design. Its own anchor ([IFX], kl 0.683) agrees with the basis nominal. Its 0.40 Ω AC-R ceiling is used here.
- **pll_control.h** still carries the old design: PLL 44–50 kHz and a 37.58 kHz default resonance. For native-21 it does not apply: ferrous-pan resonance is 25–38 kHz and `fullbridge_adapter.c` allows 35–60 kHz.

## 2. Check of the native-21 tank against the basis

### Resonant frequency and ZVS margin

The bank is 0.54 µF: C21/C22 are 0.22 µF and C23 is 0.10 µF, CDE 942C 1200 Vdc.

- **Nominal resonance.** Ferrous classes resonate at 30.2–31.4 kHz. The 35–60 kHz window therefore starts **1.11–1.16× above nominal resonance**.
- **Grid margin.** In the 135-case grid, f/f_res ≥ **1.23** and the first-harmonic phase is ≥ **54°**. The current at the line-crest drive edge is always inductive and ≥ **18.6 A**.
- **Floor-limited cases.** 5/135 cases are limited by the 35 kHz floor. These are the high-L corners at 108–120 V, where the floor costs power, not safety.
- **Floor versus resonance.** The fixed 35 kHz floor is not a ZVS guarantee:
  - Resonance reaches 37.6 kHz with low-tolerance parts. In the L0 −10 %/C −10 % run, the 1.05·f_res floor set the minimum frequency in 45/108 cases.
  - An aluminium or non-magnetic load resonates at 33–41 kHz. At 35 kHz the floor probe shows it **capacitive** at the crest edge, i.e. hard switching (`outputs/floor-probe.csv`).
  - The controller's CT_ZC phase inhibit (README pin 13 note) must therefore enforce f ≥ 1.05·f_res, and pan detection must reject these loads.
  - There is still no qualified ZVS current threshold from task 01.

### The 22 A RMS tank ceiling

The ceiling binds in **41/135** main cases: the low-r corners of every class. In those cases the
delivered power for a 1710 W request at 120 V is:

| Class | Corner result |
| --- | --- |
| Enamelled steel, clad multiply | 740 W (low corner) |
| Thin stainless | 811 W |
| 18/10 with ferromagnetic base | 927 W |
| Cast iron | 1096 W |

The **11.1 A input hold** binds next, at **1239 W** at 120 V (8 cases).

Parts against the ceiling:
- **Coil.** Its spec requires a 25 A RMS continuous rating, so it covers 22 A.
- **R5.** It is good to 31.6 A (DECISIONS).
- **C21/C22.** They do **not** fit on a conservative reading (see below).

### Capacitor voltage and current

Method (`scripts/cap_rating.py`, `outputs/cap-rating-bound.csv`):

- **Inputs.** CDE p. 3 gives the 70 °C / 100 kHz table values and p. 1 the voltage derating. The p. 4 25 °C curves were digitized for 0.1 and 0.33 µF; there is no 0.22 µF curve.
- **Bound.** The thermal limit is P_max = I_100k² · ESR(100 kHz) at CDE's 70 °C rating condition. ESR·f does not decrease with f: metal R does not fall with frequency, and the PP loss term is ∝ 1/f. Therefore ESR(f) ≤ ESR(100k)·100k/f, which gives **I_allow(f, 70 °C) ≥ I_100k·√(f/100 kHz)**. This is a lower bound.
- **Cross-check.** The same 100 kHz value was also transferred with the frequency shape of the 0.1 µF and 0.33 µF 25 °C curves. The verdict uses min(bound, shapes).
- **Best estimate.** The 0.33 µF shape is reported as the best estimate.
- **Hotter ambient.** Above 70 °C, the 105 °C category is treated as the hot-spot ceiling (I² ∝ 105 − T_amb). This is an ESTIMATE and is reported at 85 °C.
- **Current sharing.** C21/C22 carry 40.7 % of the tank current nominally and 45.7 % in the worst case (that part +10 %, the others −10 %). C23 carries 18.5 % nominally and 21.7 % worst case.

| f | C21/C22 bound, 70 °C | Tank limit (worst share) | Tank limit, 85 °C est. | C21 best estimate | Tank, best est. (nom share) | C23 tank limit (worst share) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 35 kHz | 6.09 A | **13.4 A** | 10.1 A | 8.56 A | 21.0 A | 25.0 A |
| 40 kHz | 6.51 A | 14.3 A | 10.8 A | 8.76 A | 21.5 A | 26.8 A |
| 50 kHz | 7.28 A | 16.0 A | 12.1 A | 9.39 A | 23.0 A | 29.9 A |
| 60 kHz | 7.98 A | 17.5 A | 13.2 A | 9.56 A | 23.5 A | 32.8 A |

At the 22 A ceiling, each 0.22 µF part carries **8.96 A** nominally and **10.05 A** in the worst case.
- **Conservative bound.** It is exceeded in **90/135** main cases, up to 1.64×.
- **Best estimate.** It is exceeded in **30/135** cases, up to 1.045×, all at 35–43 kHz.
- **85 °C estimate.** It is exceeded in 95/135 cases.
- **C23.** It passes everywhere.

The interim DECISIONS figure, that C21/C22 "would allow ~25 A tank", divided the 100 kHz rating
directly by the share. The 942C catalogue does not support that at 35–45 kHz.

Voltage stays inside the ratings:
- **Line-cycle RMS.** At most 184 V (main grid) and 198 V (tolerance runs), against 430 Vac (p. 3). The rating is full to 85 °C (p. 1).
- **Against the 25 °C bracket.** The line-cycle RMS is at most **0.76×** the lower 0.33 µF trace at the operating frequency. The 0.22 µF part should sit between the 0.33 µF trace and the 0.1 µF trace (flat at 430 V to about 40 kHz).
- **Peak.** At most 367 V (393 V in the tolerance runs), against 1200 Vdc.
- **Crest window.** The ±10 % line-crest window RMS reaches 259 V, still below the 0.33 µF trace in every main case.

### CT burden, OCP trip band (~55 A) and the 47.5–98 A bus OCP band

- **CT T1** (1:100 into R39 = 1.5 Ω):
  - Peak secondary is 0.709 V. CT_MON swings 1.65 ± 0.71 V, and the rail would allow about ±110 A.
  - Half-cycle volt-time is about 6.5 V·µs at 35 kHz, against 638 V·µs ([CST3015] p. 1).
  - RMS is 22 A, against the 88 A thermal reference.
  - **No change needed.**
- **CT trip band.** The maximum envelope tank peak is **47.25 A** (main), 47.67 A (offset pan) and 47.73 A (tolerance runs). That is **≥ 2.8 A below** the 50.56 A static minimum of the CT band, and about 7 A below its 55 A nominal. Unregulated operation at the 35 kHz floor puts ferrous low/nominal corners at 55–168 A peak, which the CT trips. No-pan stays at **38.5 A peak**, so OCP does not catch no-pan; pan detection must.
- **DC-return shunt band (47.52–97.98 A).** In frequency-control mode the shunt sees the tank current magnitude. Envelope peaks reach the **band's lower edge**: margin is +0.27 A on the main grid, −0.15 A on the offset pan and −0.21 A in the tolerance runs. At the stacked-corner low edge, a nuisance trip is possible in TANK_LIMITED operation. The nominal trip is about 61 A.

### Recommendations (for the owner to implement; no board or elec/ files were changed)

1. **Change the tank-bank parts. The value can stay at about 0.5 µF.**
   - **Replace C21/C22/C23 with 5 × CDE 942C16P1K-F** in parallel: 0.10 µF, 1600 Vdc / 460 Vac, 11.4 A at 70 °C/100 kHz, D22.5 × L34 mm, CDE p. 3. The bank becomes **0.50 µF**.
   - **Simulated result.** On the same 135-case grid with 0.50 µF (`outputs/alt-bank-0p50uF-cases.csv`), the conservative bound peaks at **0.74×** at 70 °C, with **0** cases over at the 85 °C estimate.
   - **Fallback.** 5 × 942C12P1K-F reaches 0.92× at 70 °C but has 62 cases over at 85 °C.
   - **Ruled out.** 3 × 942C12P15K-F + 942C12P1K-F (0.55 µF) still exceeds the bound in 47 cases.
   - **Side effects of 0.50 µF.** Resonance rises 3.9 %, and the minimum f/f_res is 1.21. Floor-limited main cases go from 5 to 0. Tank-limited power is slightly higher, because operation moves to higher frequency and R_pan ∝ f^0.62; cast iron at 120 V averages 1198 W against 1164 W.
   - **Why the bank value itself is fine.** The 0.54 µF value is not the problem. The current share per part is.
2. **If the board cannot change, do not release 22 A on catalogue evidence.** Either:
   - measure C21/C22 hot-spot temperature at 22 A and 35–45 kHz in the enclosure ambient (best-estimate exceedance is ≤ 4.5 %), or get CDE to confirm 942C12P22K-F at 35–60 kHz and 70–85 °C; or
   - make the firmware tank ceiling frequency-dependent: 13.4 A at 35 kHz rising to 17.5 A at 60 kHz (conservative). That roughly halves power on low-R pans.
3. **Shunt OCP band.** Record that the 22 A RMS envelope reaches 47.7 A peak, the shunt band's minimum corner. Either:
   - measure the real trip threshold at bring-up and confirm it is well above 48 A; or
   - add a tank-**peak** limit of about 45 A to the controller, which costs about 5 % of the RMS ceiling on low-R pans.
   - Do not lower OCP margins to fit.
4. **Controller.** Enforce f ≥ 1.05·f_res from CT_ZC phase, not from the fixed 35 kHz floor. Reject the aluminium / non-magnetic / no-pan signatures (kl ≈ 0.49 or 1.0, R_eq < 0.5 Ω) in `pan_detect`. Retire or retune `pll_control.h` (44–50 kHz) for native-21.
5. **Bank value.** No change from 0.54 µF is needed for ZVS or the frequency window. 0.50 µF is acceptable and slightly better under the current ceiling.

## 3. Task-05 grid (completed on this basis)

- **Cases.** 5 pan classes × 3 paired corners (low / nominal / high: kl, r and q together) × 108 / 120 / 140 V × 1710 / 855 / 300 W requests = **135 cases**. The synthetic offset/small pan adds 27 more.
- **Pan classes.** The five requested classes replace round 3's `coil_mc.rs` classes. The offset pan is kept only as a supplement.
- **Envelope** (`scripts/run_grid.py`):
  - 35–60 kHz (`fullbridge_adapter.c`);
  - f ≥ 1.05·f_res;
  - tank ≤ 22.0 A RMS over the line half-cycle;
  - P ≤ 11.1 A · 0.93 · V_line (`input_limits.c` η_min);
  - nominal 0.54 µF.
- **Solver.** Each case bisects to 10 Hz for the lowest feasible frequency on the kit's ideal-bridge deck, with frequency-dependent L and R (`scripts/tank_basis.cir`).
- **Runs.** 1820 ngspice runs at 8 workers.
- **Timestep check.** 50 → 25 ns on the peak-current, peak-voltage and peak-RMS extremes changed the result by at most **0.033 %**, against the 2 % threshold (`outputs/timestep-check.json`).

| Result over the 135 main cases (maxima over the grid, not bounds beyond it) | Value | Case |
| --- | ---: | --- |
| Status | MET 74, TANK_LIMITED 41, INPUT_LIMITED 8, FLOOR_LIMITED 5, BURST_REQUIRED 7 | the 7 burst cases are 300 W at 140 V on low/nominal corners: 60 kHz still gives 301–374 W |
| Frequency | 35.0–60.0 kHz; f/f_res ≥ 1.231; FHA phase ≥ 54.3° | |
| Tank RMS, line half-cycle / ±10 % crest window | 22.00 / 31.06 A | at the ceiling |
| Tank peak | **47.25 A** | enamelled steel, low corner, 140 V |
| Capacitor-bank peak / line RMS | **367.2 / 183.9 V** | clad multiply, high corner, 120 V |
| Total tank power / I_ps,est | 1445.9 W / 11.10 A | |
| C21/C22 current over the 70 °C bound (worst share) | max 1.64×; 90 cases > 1 | see §2 |
| C21/C22 current over the best estimate (nominal share) | max 1.045×; 30 cases > 1 | |
| CT secondary peak | 0.709 V | |
| Tank peak against the CT 50.56 A / shunt 47.52 A minimum trip | margin 3.31 A / 0.27 A | |

Supplemental and sensitivity runs (all in `outputs/summary.json`):

- **Offset pan.** Peak 47.67 A, 10/27 floor-limited, and 1710 W requests deliver 452–806 W.
- **L0 −10 % / C −10 %** (108 cases):
  - f_res reaches 37.6 kHz, and the 1.05·f_res floor binds 45 times;
  - tank peak 47.73 A and cap peak 393 V;
  - 16 cases need burst.
- **L0 +10 % / C +10 %.** Peak 47.14 A; 39/108 cases are floor-limited.
- **Alternative 0.50 µF bank.** 0 floor-limited, peak 47.08 A, cap peak 381.5 V.

**Task-05 verdict, assumed basis.** The tank operates inside the 22 A / 11.1 A envelope across
the pan grid:
- ZVS margin, capacitor voltage and the CT are adequate.
- The 942C12P22K-F parts are **not qualified** for 22 A by the catalogue-derived bound. Recommendation 1 or 2 closes this.
- The shunt OCP band's low edge is reached; recommendation 3.

These are model results on assumed loads. They are not a release of the operating envelope.

## 4. What the bench must measure first

1. **Loaded L and R of the real coil with the real pans**, over 25–60 kHz, at the production gap. Use an LCR meter at small signal, and also at operating current if possible.
   - Pans: cast iron, an enamelled steel, an 18/10 with a magnetic base, a thin single-ply ferritic, and a clad multiply.
   - Also measure no pan, aluminium, and an offset pan.
   - The **lowest kl and lowest r** decide the 22 A-limited power, the resonance maximum, and whether f ≥ 1.05·f_res clears 35 kHz.
   - Then rerun `scripts/run_grid.py` with the measured values entered in `basis.py`.
2. **Coil no-pan L0 and R_ac(f)**, at cold and at hot winding temperature.
3. **C21/C22 hot-spot or can temperature** at 22 A tank RMS, 35–45 kHz, in the enclosure's worst ambient. Compare it with the 105 °C category, or get CDE's written rating for 942C12P22K-F at 30–60 kHz and 70–85 °C. Do this before keeping the present parts.
4. **Tank peak against the actual shunt and CT trip thresholds** at the 22 A ceiling on the lowest-R pan, plus the bridge-edge current at line crest, for ZVS.

## Reproduce

From `zapote/power-stage-120v/validation-plan/sim-kit`, restore `models/vendor/IFX_CFD7_650V.lib`
(SHA above) and run `python3 smoke_test.py` (expect `SMOKE PASS`). Then, from this directory:

```sh
python3 -I scripts/digitize_sources.py --onsemi <AND9201.pdf> --infineon <UG-2023-15.pdf> --cde ../sources/942C.pdf
python3 -I scripts/basis.py
python3 -I scripts/cap_rating.py
python3 scripts/run_grid.py --tag grid                      # 162 cases, <= 8 workers, ~2 min
python3 scripts/run_grid.py --tag tol-L0m10-Cm10 --l0-scale 0.9 --c-scale 0.9 --corners low,high
python3 scripts/run_grid.py --tag tol-L0p10-Cp10 --l0-scale 1.1 --c-scale 1.1 --corners low,high
python3 scripts/run_grid.py --tag alt-bank-0p50uF --cres 0.50u
python3 scripts/stress_checks.py
python3 -I scripts/analyze.py
```

Python needs numpy and Pillow, and the digitizer needs `pdftoppm` from poppler. Run directories
are temporary and deleted, so no vendor model copies are kept.
