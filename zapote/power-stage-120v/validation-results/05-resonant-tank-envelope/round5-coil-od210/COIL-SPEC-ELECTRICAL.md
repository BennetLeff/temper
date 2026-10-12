# Tank coil specification: electrical content (native-21), copy

This is a copy of the electrical sections of `docs/hardware/TANK_COIL_SPECIFICATION.md`: rows 1–12, §2–§5.
They were rewritten on 2026-10-10 in the main checkout, where the file is **not committed**, because other
sessions have uncommitted work there. Mechanical rows 13–16 (§1b) belong to the enclosure session and
are not reproduced. Derivations and evidence are in this folder's README and `outputs/floor.json`.
All coupling, yield and floor numbers are **ASSUMED / pre-measurement**.

### Changes since 2026-10-10

Updated 2026-10-12 for the 28 A commissioned ceiling. Sources are `zapote/power-stage-120v/DECISIONS.md` (DEC) item numbers
with line numbers at this commit. Every changed number is recomputed by `coil_spec_28a_check.py` (output
`coil_spec_28a_check.json`), which also asserts that the value printed here matches.

| Row / section | Was | Now | Source |
|---|---|---|---|
| 1 (alt. B turns) | about 21 turns against 19.6 | about 23.4 against 21.9 (L ∝ N²) | R36 21.9 turns for 70 µH: DEC item 12 (l. 528–532) |
| 5 AC resistance | 0.25 Ω hot at 40 kHz; 60 kHz point 0.241 Ω at 25 °C | **≤ 0.23 Ω hot at 40 kHz (0.178 Ω at 25 °C), and ≤ 0.2551 Ω hot (0.197 Ω at 25 °C) at every frequency 20–60 kHz**; the cap binds above about 48.3 kHz. 60 kHz point 0.197 Ω at 25 °C | 28 A needs R_ac ≤ about 0.23 Ω (DEC item 10 l. 516); 200 W / 28² cap (DEC item 5 l. 471, item 12 l. 531). R36 passes with margin |
| 6 continuous current | 22 A RMS | **28 A RMS**, 35–60 kHz, plenum; commissioned in steps from 22 A | DEC item 10 l. 503–510, item 13 l. 551–554 |
| 7 peak current | 98 A (stage-13 band top 97.77 A) | **117 A** (stage-17 band top 116.44 A) | DEC item 17 l. 687 |
| 12b (new) insulation | none in this copy | winding insulation: reinforced, with test levels | DEC item 7 l. 474; `r43/COIL-PROTOTYPE-BUILD.md` l. 48–52; `ORACLE-ANSWER.md` Q3 |
| §2 window-top bound | "hold 22 A", x_reg 1.45 | ceiling-independent: 1.45 still bounds 22–28 A (round-6 grid max 1.434 at 22 A, 1.321 at 28 A); floor 41.5 µH unchanged | `round6-full-power/outputs/grid6-*-I2*-cases.csv` |
| §2 below-floor text, 47.32 A corner | shunt corner 47.32 A | dated as round 5 at 22 A; band is now 67.72–116.44 A | DEC item 17 l. 687 |
| §2 resistance note | coil loss 121 W / 151 W at 22 A | 180 W at 40 kHz and 200 W at 60 kHz at 28 A; the earlier 0.25 Ω (196 W) form and its 245 W at 60 kHz are shown for the record | `coil_spec_28a_check.json` |
| §3 thermal soak | 22 A at 40 and 60 kHz; model 140.7 °C at 22 A | 28 A (after 22 A), model heat-equivalent to the 140.7 °C case; ferrite loss on top | DEC item 8 l. 478–481, item 12 l. 531 |
| §3 saturation pulse | 98 A | 117 A | row 7 |
| §4 current / peak limit | 22 A RMS / peak limit about 45 A | 28 A RMS commissioned (ships 22 A); firmware peak trip min(2.17 c + 3, 62) A = 50.74 A at 22 A, 62.0 A at 28 A; RMS trip 29.4 A | `firmware/components/power/Kconfig` l. 35–46; `include/tank_freq.h` l. 75–80; `test/test_tank_freq.c` l. 59–64 (branch `fw/stage15-tank-ceiling`, an ancestor of this commit) |
| §4 coil loss of record | 200 W design, ≤ 151 W at 22 A | 91–107 W expected for R36, 196 W at the 0.25 Ω DECISIONS limit, 180 W at the row-5 0.23 Ω limit, 28 A; plenum basis 200 W | DEC item 12 l. 531 |
| §4 L-target row | "47.32 A shunt corner is no longer passed" | dated as round 5 against the superseded band | DEC item 17 l. 687 |
| §5 provenance | 97.8 A, stage-13 band | 116.44 A, stage-17 band; added 28 A, firmware, R36 rows | as above |

## 1. Specification — as a supplier would receive it

**Part:** resonant tank coil for an 1800 W (120 V / 15 A) domestic induction hob:
- two-section flat spiral, ferrite-backed;
- full-bridge series-resonant inverter, operating at **35–60 kHz**.

| # | Parameter | Requirement | How it is verified |
|---|---|---|---|
| 1 | **Inductance, unloaded** | **70 µH ±10 %** (63–77 µH), measured free in air. Installed in the enclosure it reads **≈ 0.95×** this: R32 gives 66.34 µH no-pan, and round 5's FEM gives 0.950 for this winding. **RFQ alternate B: 80 µH ±10 %** (≈ 76 µH installed, about 23.4 turns against 21.9 for the 70 µH coil of record, L ∝ N²), with every other row unchanged. Quote both (§4) | LCR bridge, **40 kHz**, ≤ 1 V. Coil free in air with its ferrite fitted, ≥ 100 mm from any metal |
| 2 | **Measurement frequency** | 40 kHz. Inductance **flat within ±3 % over 20–60 kHz** | Sweep 20/30/40/50/60 kHz on the same bridge |
| 3 | **Loaded inductance — the binding criterion** | **L_loaded ≥ 41.5 µH** at 40 kHz on the §2 reference pan at the production gap. Expected: about 42 µH for a nominal 70 µH coil, about 48 µH for alternate B | §2 |
| 3b | **Loaded/unloaded ratio — coupling screen** | **0.54 ≤ L_loaded / L_unloaded ≤ 0.77** (70 µH design); 0.47–0.77 for alternate B | §2 |
| 4 | **DC resistance** | **≤ 0.100 Ω** at 25 °C including leads (target ≤ 0.080 Ω) | 4-wire milliohmmeter, 25 °C; derivation §2 "Resistance" |
| 5 | **AC resistance, unloaded** | **≤ 0.23 Ω at 40 kHz with the winding at 100 °C** (the binding figure: 28 A needs it for the winding to stay ≤ 150 °C, §3). The 25 °C acceptance equivalent is **≤ 0.178 Ω at 40 kHz**. A measured **curve over 20–60 kHz** is required, and every point must satisfy both: ≤ 0.178 Ω·(f/40 kHz)^0.55 at 25 °C, and **≤ 0.197 Ω at 25 °C (0.2551 Ω hot = 200 W / (28 A)²)**, which keeps coil loss at 28 A inside the 200 W plenum basis at the top of the band (§2 "Resistance"). Limit points at 25 °C: 0.121 / 0.178 / 0.197 Ω at 20 / 40 / 60 kHz (the flat cap starts at 48.3 kHz). The R36 coil of record (estimated 116–136 mΩ at 40 kHz) passes with margin | Same LCR sweep as row 2 (series R). First articles also get two hot points: the winding soaked at 100 °C, R_ac at 40 kHz ≤ 0.23 Ω and at 60 kHz ≤ 0.2551 Ω |
| 6 | **Continuous current** | **28 A RMS at any frequency in 35–60 kHz**, in the enclosure's coil-cooling condition (jet plenum, not still air). The firmware commissions the ceiling in steps: it ships at 22 A and rises to 28 A only after bench gates; until the peak ratio is calibrated the effective cap is 27.2 A, and the RMS trip is 1.05 × ceiling = 29.4 A. Limits: mean winding ≤ 150 °C, ferrite ≤ 140 °C. Coil copper loss at 28 A must stay ≤ 200 W (the plenum basis), which row 5 enforces: 180 W at the 40 kHz limit, 200 W at the 60 kHz cap | Thermal soak, §3 (22 A first, then 28 A) |
| 7 | **Peak current, non-repetitive** | **No saturation up to 117 A peak**, which covers the top of the DC-return shunt OCP band with 0.56 A of margin (116.44 A; power-stage DECISIONS item 17, stage-17 Kelvin band 67.72–116.44 A). L at 117 A peak within **3 %** of the small-signal L. The supplier states the ferrite's peak flux density at 117 A and 100 °C, which must be ≤ 0.75× the material's published B_sat at 100 °C. Normal operation peaks at 59.17 A (28 A envelope; 117 A is 1.98× that) and the firmware peak trip is 62.0 A, so this row is the last-line fault case | Ring-down pulse test, §3; supplier calculation on the CoC |
| 8 | **Conductor** | **Litz**, bare-copper strands **0.08–0.10 mm** (AWG 40–38), enamel thermal class ≥ 200 °C, bunched or Type 2 (served). Strand count must meet rows 4–5 (estimate ≥ 200 × 0.1 mm, i.e. ≥ 1.55 mm² Cu for about 9 m at 0.10 Ω; the in-house coil of record, R36, uses 270 × 0.10 mm, 2.12 mm² Cu, 21.9 turns, about 9.9 m, estimated R_ac 116–136 mΩ at 40 kHz / 100 °C). Skin depth in Cu at 60 kHz is 0.27 mm at 20 °C and 0.31 mm at 100 °C. Strands ≤ δ/3 keep strand-level skin effect negligible, and proximity loss in a many-strand bundle grows with d², which is why 0.2 mm strands are not acceptable here | Declared on the CoC (strand Ø, count, construction, enamel grade); rows 4–5 measured |
| 9 | **Outer diameter** | **Winding r 26–114, two sections, OD ≈ 228, ceiling 240.** Round 5 shows this winding couples to pans like R32's uniform r 22–116: reflected R per µH within 1–5 %, inductance drop within 2–4 %, modelled full-power yield at 120 V within 3.3 points. A Ø210 coil gains only about 1.6 points and cannot be cooled at 22 A, still less at 28 A (enclosure R33 study 09). Exact radii and the ferrite are in row 16 | Calipers |
| 10 | **Terminations** | Two leads in the winding's own Litz, terminated per row 15. Termination resistance is included in row 4 | Visual; row 4 |
| 11 | **Temperature class** | Litz, strand enamel, serving and any impregnant rated **≥ 200 °C** continuous (thermal class 200). Former and carrier per row 13. Pan temperature is capped at 250 °C. The glass underside reaches 230–250 °C in the fry and empty-pan hold cases (R32 study 02) | Datasheet / CoC |
| 12 | **Ferrite backing** | MnZn power ferrite, **N87/N97 class** (or equal: µi ≥ 2000, Curie ≥ 210 °C), **radial bars**, ≥ 8 × 20 mm wide, leaving the **≥ 14 mm cooling-jet lanes** between bars clear. Geometry per row 16. A plate or an air core is not acceptable: cooling, plus field pickup at the OCP Kelvin loop | Drawing check; rows 3 and 7 verify it electrically |
| 12b | **Winding insulation (tank to SELV and PE)** | Working voltage of the winding against SELV and PE parts: **242 V rms / 640 V peak**, 33–60 kHz. Insulation to those parts is **reinforced**: creepage ≥ 8.0 mm (PD3, material group IIIa, >125–250 V band), clearance ≥ 3.0 mm, and the IEC 60664-4 distances above 30 kHz where larger. Test levels (proposed by the power stage; the certifier confirms): dielectric strength, winding to the ferrite, carrier screws and NTC leads, **3000 V rms for 1 min** after the humidity treatment, no breakdown; partial discharge **< 10 pC at 1.5 × U_rp = 960 V peak** (raised first to 1.875 × U_rp = 1200 V peak), at 50/60 Hz and, if a source is available, at about 40 kHz; production **3000 V for 1 s** | Hipot and PD test, CoC; creepage and clearance by drawing check |

Row 12b sources: DECISIONS item 7 (l. 474, working voltage); `ORACLE-ANSWER.md` Q3 (reinforced 8.0 mm in the >125–250 V band; clearance about 3 mm from Table 16, marked "verify"); `D5-BASIS.md` l. 33–37 (IEC 60664-4 above 30 kHz);
`r43/COIL-PROTOTYPE-BUILD.md` l. 48–52 (test levels). The DECISIONS 2026-10-08 M11 entry's hipot figures (l. 256–268) (type 3000 Vac 60 s, routine 2000 Vac 1 s, clearance 2.0 mm) belong to the mains-HOT-to-sink stack, not to this winding.

**Certificate of conformance shall report, per unit:**
- L_unloaded at 40 kHz, and the 20–60 kHz sweep;
- R_dc, and the R_ac 20–60 kHz curve at a stated winding temperature;
- L_loaded at 40 kHz with the supplier's own ferromagnetic reference pan (pan Ø and gap stated), and the ratio;
- Litz construction (strand Ø, count, enamel grade);
- ferrite material and bar count;
- the row 12b hipot and PD results.

> §1b mechanical rows 13–16: see the main document (enclosure session).

### Why 70 µH, in one line

With the 0.50 µF bank, a 70 µH coil (66.3 µH installed) puts the nominal loaded resonance on
ferrous pans at **33.8–35.6 kHz**, at the bottom of the 35–60 kHz window. Full power is then reached
at 37–56 kHz with f/f_res ≥ 1.21 (round 5, Ø228 coil on a 220 mm pan). More turns raise the reflected pan R as N², and with it the power
available under the tank-current ceiling (22 A at first power, 28 A commissioned). Hence alternate B (§4).

---

## 2. THE ACCEPTANCE TEST — measure `L_loaded`

**This is the deliverable.** Rows 3 and 3b decide whether the coil works in this tank, and **no
vendor in this class states either**, so they are measured on receipt.

### Why a loaded measurement and not an inductance check

Only the **loaded** inductance resonates with the tank capacitor, and the pan's reflected
resistance is what turns the tank-current ceiling (22 A at first power, 28 A commissioned) into power. A coil with a perfect unloaded reading and
unusual coupling is a failed coil; a coil 10 % low with strong coupling can be fine. Full argument:
`docs/solutions/design-patterns/resonant-tank-only-loaded-inductance-resonates-2026-07-28.md`.

### Deriving the floor (native-21)

All inputs are committed constants or round-5 results (`round5-coil-od210/scripts/floor.py`).
The worst-case capacitance for the *highest* resonance is the bank at −10 % (`K000` parts, ±10 %,
TDK B3265*A data sheet):

```
C_worst = 0.50 µF × (1 − 0.10) = 0.45 µF

(a) Fixed-floor ZVS guarantee (the method of the 2026-07-29 issue), for reference only:
    f_res,max = F_MIN / ZVS = 35 000 / 1.05 = 33 333 Hz
    L_loaded,min = 1 / ((2π × 33 333 Hz)² × 0.45 µF) = 50.66 µH
    → a 66.3 µH-installed coil would need kl ≥ 0.76 on EVERY pan. The assumed basis has
      0.63–0.69 nominal, so this cannot be an acceptance criterion. On native-21, ZVS rests on the
      controller's CT_ZC guard (f ≥ 1.05·f_res, measured), and the fixed 35 kHz floor does not
      guarantee it.

(b) Window-top bound (binding): the controller must be able to hold the commissioned tank ceiling
    and the 11.1 A inlet limit in continuous mode below F_MAX. Round 5's grid (22 A) needs up to
    x_reg = f/f_res = 1.45 (Ø228 and Ø240, 108–140 V, 1710 W request). A higher ceiling only lowers
    the operating frequency: round 6's grid (R34 as modelled, 70 µH / 0.50 µF) peaks at x_reg 1.434
    at 22 A and 1.321 at 28 A, so 1.45 bounds every ceiling from 22 to 28 A and the floor is unchanged.
    f_res,max = F_MAX / x_reg = 60 000 / 1.45 = 41 379 Hz
    L_loaded,min (most strongly coupled pan in the population)
                 = 1 / ((2π × 41 379 Hz)² × 0.45 µF) = 32.87 µH

(c) Transfer to the one reference pan used at incoming inspection:
    kl(population minimum) / kl(reference class, cast iron nominal) = 0.4998 / 0.6308 = 0.792
    L_loaded,min on the reference pan = 32.87 / 0.792 = 41.5 µH      ← row 3
```

Below the floor, the grid shows what goes wrong (round 5, R34 winding at 58 and 53 µH installed):
- 60 kHz can no longer hold the envelope, and burst is needed in 2 and 10 of 45 cases respectively;
- the tank peak (round 5, 22 A ceiling) reaches 52 and 61 A, above the 50.74 A firmware peak trip at 22 A (§4);
- at 53 µH the bank reaches 1.13× TDK's 85 °C curve.

| Coil | L_loaded on reference pan (nom. coupling) | Row 3 |
|---|---|---|
| 70 µH nominal (66.5 installed) | 41.95 µH | passes, by 1 % |
| 70 µH at −10 % | 37.75 µH | **fails** |
| 80 µH (alt. B) nominal | 47.94 µH | passes |
| 80 µH at −10 % | 43.15 µH | passes |

**This is the case for alternate B.** On the assumed coupling, a 70 µH coil passes row 3 only at
or above nominal L.

**Ratio screen (row 3b)**, as L_loaded on the reference pan over L_unloaded free in air:
- **lower 0.54**, the floor at L +10 %: 41.5 / 77. Below it the coupling is stronger than the basis allows.
- **upper 0.77**, the basis's cast-iron kl maximum × 0.95 installed. Above it the coupling is weak, and the pan heats less per amp; that was the R19 Ø240 lesson.
- For alternate B the lower bound is 41.5 / 88 = 0.47.
- A coil that passes row 3 but fails row 3b is **escalated, not accepted**.

**Re-derivation.** The 0.792 transfer and x_reg = 1.45 are assumed-basis numbers. When the first
coil has been measured on the reference pan **and** on the five class pans (cast iron, enamelled
steel, 18/10 with magnetic base, thin ferritic, clad multiply) at 180/220/260 mm, replace them and
re-run `floor.py`.

**Legacy record (kept for the CI gate, not a native-21 requirement):** in the 2026-07-29
half-bridge issue, `L_loaded ≥ 53.43 µH` is requirement #3. `scripts/check_pll_range_consistency.py`
check 8 still checks that sentence against the legacy `elec/src/main.ato` (300 nF, 88 µH) and
`pll_control.h` (`PLL_MIN_FREQ_HZ` 44 kHz). Retarget the gate (§8) before deleting it.

### Procedure

**Equipment:**
- an LCR meter capable of 20–60 kHz with ≥ 1 % accuracy at 30–80 µH;
- the reference pan below;
- a non-ferrous spacer stack reproducing the production gap: **winding top to pan base 7.5 mm**, i.e. 3.5 mm air plus 4 mm glass (R32 stack; use a glass offcut if possible).

**Reference pan.** Fix it once and keep the same physical pan for all incoming inspection:
- flat-bottomed **ferromagnetic** pan, cast iron or ferritic single-ply (verify with a magnet);
- **base Ø 230–260 mm**, i.e. ≥ the 228 mm winding; round 5's FEM shows coupling flat within about 1 % from 220 to 260 mm;
- base ≥ 3 mm thick, flat within 0.5 mm.

Record its make and model. A different pan gives a different L_loaded.

**Steps**
1. Coil free in air with its ferrite fitted, ≥ 100 mm from any metal. Measure **L_unloaded** at 40 kHz, ≤ 1 V. Record it, then sweep 20–60 kHz for row 2.
2. Confirm row 1 (63–77 µH; 72–88 µH for alternate B). If it fails, stop and reject.
3. Measure R_dc (row 4) and the R_ac curve (row 5) at a recorded winding temperature, corrected to 25 °C with Cu +0.393 %/K. Check the curve against both row-5 limits, the f^0.55 shape from 0.178 Ω and the flat 0.197 Ω cap.
4. Put the coil on the spacer stack. Centre the reference pan, empty and at room temperature.
5. Measure **L_loaded** at 40 kHz, same drive. Record it.
6. **ACCEPT if L_loaded ≥ 41.5 µH. Reject otherwise.**
7. Compute **L_loaded / L_unloaded**. It must lie in 0.54–0.77 (0.47–0.77 for alternate B); otherwise escalate.

No waiver on step 6 without re-deriving the floor with `floor.py`, and the firmware resonance and
peak-current limits with it.

### Resistance: rows 4 and 5

```
Requirement (round 6, DECISIONS item 10): R_ac(40 kHz, winding 100 °C) ≤ 0.23 Ω
  (R32's earlier figure was 0.25 Ω; 0.25 Ω holds only 27.2 A in the round-6 coil model)
At 25 °C, conservatively assuming all of R_ac scales with copper resistivity:
  R_ac(40 kHz, 25 °C) ≤ 0.23 / (1 + 0.00393 × 75) = 0.178 Ω                       ← row 5
  (Proximity/eddy loss in strands much thinner than δ scales as 1/ρ, so it FALLS with
   temperature. The resistivity assumption is therefore the safe direction.)
Frequency shape: R_ac ∝ f^0.55 (round 4: onsemi 0.52, Infineon 0.59 over 30–50 kHz)
  → 0.121 / 0.178 / 0.222 Ω at 20 / 40 / 60 kHz, 25 °C, before the cap
Cap (200 W plenum basis at 28 A): R_ac ≤ 200 / 28² = 0.2551 Ω hot = 0.197 Ω at 25 °C at every frequency
  → limit points 0.121 / 0.178 / 0.197 Ω at 20 / 40 / 60 kHz; the cap binds above 48.3 kHz
R_dc: a well-stranded Litz coil keeps F_R = R_ac/R_dc ≤ about 1.8 at 40 kHz. ESTIMATE: the supplier
  must show the curve; the Infineon kit coil, at 0.10 → 0.34 Ω (UG-2023-15 p. 21 Fig. 16), shows F_R 3.4,
  and such a coil would FAIL row 5.
  R_dc ≤ 0.178 / 1.78 = 0.100 Ω                                                      ← row 4
  Target 0.080 Ω, which leaves F_R up to 2.2.
```

Coil loss at the row-5 limits (I²·R_ac at 100 °C), against the 200 W plenum basis (DECISIONS items 5 and 12):

| | 22 A (first power) | 28 A (commissioned) |
|---|---|---|
| 40 kHz at the 0.23 Ω limit | | 180 W |
| 35 kHz, 0.23·(35/40)^0.55 | | 168 W at 35 kHz |
| 60 kHz, 0.23 Ω·1.5^0.55 = 0.2875 Ω with no cap | | 225 W, **over the basis** |
| 60 kHz at the row-5 cap, 0.2551 Ω | | 200 W |
| For the record: the superseded 0.25 Ω / 40 kHz limit | 121 W at 40 kHz, 151 W at 60 kHz | 196 W at 40 kHz, 245 W at 60 kHz |

**Why row 5 has two limits.** The 0.23 Ω / 40 kHz figure is the thermal one (round 6: 0.25 Ω holds only 27.2 A,
28 A needs about 0.23 Ω; DECISIONS item 10, l. 516). On its own it still allows 0.2875 Ω at 60 kHz under
R_ac ∝ f^0.55, which is 225 W at 28 A. The plenum basis is 200 W, so the hot R_ac must also stay
≤ 200 W / (28 A)² = 0.2551 Ω at every frequency, i.e. 0.2551 / 1.29475 = 0.197 Ω at 25 °C
(1.29475 = 1 + 0.00393 × 75). The shape curve meets that cap at 48.3 kHz and the cap binds above it.
The R36 estimate (116–136 mΩ at 40 kHz, DECISIONS item 12) gives 91–107 W at 40 kHz, and 0.170 Ω, 133 W at 60 kHz
for its upper figure: it passes both limits with margin. Ferrite loss is added on top by the enclosure.

**Thermal margin.** The 0.23 Ω limit comes from the round-6 coil model at 45 kHz, full blower, 50 °C inlet; it is
not modelled across 35–60 kHz, so a coil at the limit is not guaranteed to pass the 28 A soak at 60 kHz or on a worse
pan. The soak (§3) decides.

---

## 3. Thermal soak (row 6) and saturation pulse (row 7)

**Not a go/no-go for first articles.** Both tests must pass before the coil is released for
production. Temper runs them on first articles in the enclosure, or in a fixture that reproduces
its coil cooling.

**Cooling condition** (R32 study 02, `output/temper-r32-studies/02-cooling-acoustics-venting/coil_thermal.py`;
R33 study 09 for this winding):
- **Jets:** a sealed jet plenum under the carrier, 135 × Ø3 mm jets on a 14 mm grid, 5.5 mm below the winding, blowing between the ferrite bars.
- **Supply:** fed by the push blower's ~27 % bleed, inlet air at **50 °C**.
- **Drive:** blower at the drive the coil loop commands. Study 09 needs 0.9 drive for 22 A at maximum R on this winding; at the 196 W loss of the superseded 0.25 Ω limit the coil needs about 0.9 drive at 28 A (DECISIONS item 15).
- **Glass gap:** stagnant, 3.5 mm to the glass.

**Cases.**
1. **22 A RMS, then 28 A RMS, each at 40 kHz and 60 kHz**, on the reference pan holding boiling water (glass underside about 110 °C), until stable (≥ 30 min). The 22 A step is the first-power gate; 28 A is the commissioned ceiling the firmware reaches only after bench gates (DECISIONS items 10 and 13). Record the coil loss (I²·R_ac at the measured hot R_ac) beside the temperatures: it must be ≤ 200 W.
2. **12.7 A RMS fry hold**, with the glass underside at 230 °C.

**Pass:**
- **mean winding ≤ 150 °C**, by the resistance method (R_dc rise, Cu 0.393 %/K);
- **ferrite ≤ 140 °C** (thermocouple on the bar under the hottest turn);
- no discoloration of the serving or the carrier.

Model expectation (R32 study 02, DECISIONS item 8): 102.5 °C at a typical 17 A; 140.7 °C at 22 A with the
old maximum R (0.41 Ω, 198 W) and 50 °C inlet. 28 A at the row-5 limit (0.23 Ω) is 180 W, below that 198 W case; at the
60 kHz cap it is 200 W, equal to it. A coil at R36's estimated 116–136 mΩ (91–107 W) dissipates about half. Ferrite loss is added on top
(enclosure). Round 6's R34-as-modelled variant holds 27.2 A at 0.25 Ω and needs about 0.23 Ω for 28 A (DECISIONS item 10), which is why row 5 is set there. The bench decides.

**Saturation pulse (row 7).** Charge a known film capacitor and discharge it into the coil, free in
air with its ferrite fitted, so the first current peak is 117 A. Then compare:
- the ring frequency of the first cycle with that of a ≤ 5 A ring of the same circuit. **L may differ by at most 3 %;**
- L at small signal before and after the pulse, **unchanged within 1 %.**

---

## 4. What this specification does to the rest of the design

| Quantity | Value | Moved by this spec? |
|---|---|---|
| Resonant bank | 5 × B32654A1104K000 = 0.50 µF ±10 % | No. Round 5: C moves resonance, not reflected R, so it is not the power lever |
| Control window | 35–60 kHz | No |
| ZVS guard | f ≥ 1.05·f_res from CT_ZC | **Required.** The fixed 35 kHz floor sits below 1.05·f_res at nominal coupling (§2 (a)) |
| Tank current ceiling / peak limit | **28 A RMS commissioned** (hardware sized for it; firmware ships at 22 A and steps up after bench gates, effective cap 27.2 A until the peak ratio is calibrated). Firmware limits derive from the ceiling: peak trip min(2.17·c + 3, 62) A = 50.74 A at 22 A and 62.0 A at 28 A (the formula alone gives 63.76 A); half-cycle RMS trip 1.05·c = 29.4 A at 28 A | **Moved from 22 A / about 45 A.** The 45 A limit capped the line RMS near 21 A, so it was lifted. Envelope peak at 28 A is 59.17 A, the CT band is 64.55–76.09 A and the shunt OCP band is 67.72–116.44 A, so the 62.0 A trip sits under the CT band. The 27.2 A cap is (62 − 3) / 2.17. Sources: DECISIONS items 10, 13, 17; `firmware/components/power/Kconfig` l. 35–46, `include/tank_freq.h` l. 75–80, `test/test_tank_freq.c` l. 59–64 |
| Coil loss of record | 200 W plenum basis (R32); R36 expected 91–107 W at 28 A | Basis unchanged. The row-5 limits give ≤ 200 W at 28 A: 180 W at 40 kHz, 200 W at the 60 kHz cap (§2) |
| **L target** | 70 µH (66.3 installed), alternate B 80 µH (≈ 76 installed) | **Open, power-stage decision.** Round 5 on 220 mm pans: MC full-power yield at 120 V rises from 13 % to 22–25 %, and the 47.32 A shunt corner of the time is no longer passed (round 5, superseded: the band is now 67.72–116.44 A, DECISIONS item 17). At the 28 A ceiling round 6 keeps 70 µH: 80 and 90 µH lose yield to the 35 kHz floor (pooled 81 % and 59 % against 85 %; DECISIONS item 10), so alternate B is a quoted option, not a recommendation. Alternate B also passes row 3 at −10 % L. Cost: floor-limited corners, 2/45 at 75 µH and 11/45 at 82 µH installed (power, not safety); about 7 % more turns, so R_ac rises about 14 % in the same winding window, and holding R_ac ≤ 0.23 Ω (and the 0.197 Ω cap) needs better copper fill; for alternate B the tighter 0.23 Ω is harder still; the firmware resonance tables and `coil_mc.rs` change |
| Legacy `elec/src` 88 µH / 300 nF and gate check 8 | Unchanged | **Stale.** They still check the half-bridge (§8) |

Round-5 modelled full-power yield at 120 V at the 22 A ceiling (MC over the five classes, 1239 W hold reached):

| Pan base | 180 mm | 220 mm | 260 mm |
|---|---|---|---|
| R34 two-section r 26–114 | 0.2 % | 13 % | 20 % |
| R32 uniform r 22–116 | 1 % | 16 % | 23 % |

Cast iron reaches 41–55 %. These are ASSUMED-basis numbers; the 22 A ceiling binds. At the 28 A ceiling round 6 (70 µH, R34 as modelled) gives 85 % pooled and 89 % on 220 mm pans (DECISIONS item 10).

---

## 5. Provenance of the numbers

| Number | Source |
|---|---|
| 70 µH design, 66.34 µH installed | Power-stage selected design (`coil_mc.rs`, power-stage README); R32 study 06 FEM, accepted in power-stage DECISIONS 2026-10-09 item 5 |
| R_ac ≤ 0.23 Ω at 40 kHz / 100 °C (was 0.25 Ω; DECISIONS item 10), Litz ≥ 200 °C, N87/N97 radial bars on ≥ 14 mm lanes, 250 °C pan cap | Power-stage DECISIONS 2026-10-09 item 8 (R32 coil cooling) |
| Pan coupling classes (kl, r, α) | Round 4 assumed basis. Anchors: Infineon UG-2023-15 p. 21 Fig. 16; onsemi AND9201/D p. 7 Figs. 9–10; repo-transcribed MDPI 180 mm study |
| Coupling against OD and pan Ø | Round 5 FEM (R32 study-06 solver), used as ratios only |
| 0.50 µF, ±10 % | Power-stage DECISIONS 2026-10-09; TDK B3265*A data sheet |
| 117 A (row 7) | Power-stage DECISIONS item 17 (l. 687): shunt OCP band 67.72–116.44 A after the Kelvin shift, 67.66 A at the bound. Supersedes 97.8 A from the stage-13 band 47.32–97.77 A |
| 28 A RMS (row 6), 29.4 A RMS trip, 27.2 A effective cap | DECISIONS item 10 (l. 503–510) and item 13 (l. 551–554); `firmware/components/power/Kconfig` l. 35–46 |
| Firmware peak trip 50.74 A at 22 A, 62.0 A at 28 A | `firmware/components/power/include/tank_freq.h` l. 75–80; `test/test_tank_freq.c` l. 59–64 (stage 15, branch `fw/stage15-tank-ceiling`) |
| Envelope peak 59.17 A at 28 A; CT band 64.55–76.09 A | DECISIONS item 13 (l. 535–536) |
| R36: 270 × 0.10 mm, 21.9 turns, R_ac 116–136 mΩ, 91–107 W (196 W at 0.25 Ω) at 28 A | DECISIONS item 12 (l. 528–532); enclosure `r36/DECISIONS.md` l. 17–18 |
| 200 W plenum basis; R_ac ≤ 0.23 Ω needed for 28 A | DECISIONS item 5 (l. 471), item 10 (l. 516) |
| 242 V rms / 640 V pk; reinforced 8.0 mm / 3 mm; 3000 V rms 1 min, PD < 10 pC, 3000 V 1 s | DECISIONS item 7 (l. 474); `ORACLE-ANSWER.md` Q3; enclosure `r43/COIL-PROTOTYPE-BUILD.md` l. 48–52 (certifier to confirm) |
| Window-top x_reg 1.434 / 1.321 at 22 / 28 A | `round6-full-power/outputs/grid6-d228_gap84-L70-C050-I*-pan*-cases.csv`, recomputed in `coil_spec_28a_check.py` |

**What is UNVERIFIED, stated plainly:**
- No Temper coil or pan has been measured.
- The coupling ratios come from a linear-µ pan model.
- The floor's 0.792 transfer and x_reg 1.45 are assumed-basis numbers.
- Part-to-part spread of a wound coil is unknown; ±10 % is imposed, not measured.
- R36's R_ac (116–136 mΩ) is an estimate, the 28 A thermal model is the enclosure's scaled model, and the f^0.55 R_ac shape is a round-4 fit over 30–50 kHz extended to 60 kHz.
- The insulation test levels are the power stage's proposals; the certifier has not confirmed them, nor the clearance (Table 16, marked "verify" in ORACLE-ANSWER).

> **Superseded:** the 2026-07-29 provenance (88 µH and ratio 0.68 read off Infineon Fig. 16 as the design value). That chart is now one of round 4's anchors, not the design.
