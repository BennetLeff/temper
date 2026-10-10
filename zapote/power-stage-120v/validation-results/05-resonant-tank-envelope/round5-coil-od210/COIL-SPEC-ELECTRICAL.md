# Tank coil specification: electrical content (native-21), copy

This is a copy of the electrical sections of `docs/hardware/TANK_COIL_SPECIFICATION.md`: rows 1–12, §2–§5.
They were rewritten on 2026-10-10 in the main checkout, where the file is **not committed**, because other
sessions have uncommitted work there. Mechanical rows 13–16 (§1b) belong to the enclosure session and
are not reproduced. Derivations and evidence are in this folder's README and `outputs/floor.json`.
All coupling, yield and floor numbers are **ASSUMED / pre-measurement**.

## 1. Specification — as a supplier would receive it

**Part:** resonant tank coil for an 1800 W (120 V / 15 A) domestic induction hob:
- two-section flat spiral, ferrite-backed;
- full-bridge series-resonant inverter, operating at **35–60 kHz**.

| # | Parameter | Requirement | How it is verified |
|---|---|---|---|
| 1 | **Inductance, unloaded** | **70 µH ±10 %** (63–77 µH), measured free in air. Installed in the enclosure it reads **≈ 0.95×** this: R32 gives 66.34 µH no-pan, and round 5's FEM gives 0.950 for this winding. **RFQ alternate B: 80 µH ±10 %** (≈ 76 µH installed, about 21 turns against 19.6), with every other row unchanged. Quote both (§4) | LCR bridge, **40 kHz**, ≤ 1 V. Coil free in air with its ferrite fitted, ≥ 100 mm from any metal |
| 2 | **Measurement frequency** | 40 kHz. Inductance **flat within ±3 % over 20–60 kHz** | Sweep 20/30/40/50/60 kHz on the same bridge |
| 3 | **Loaded inductance — the binding criterion** | **L_loaded ≥ 41.5 µH** at 40 kHz on the §2 reference pan at the production gap. Expected: about 42 µH for a nominal 70 µH coil, about 48 µH for alternate B | §2 |
| 3b | **Loaded/unloaded ratio — coupling screen** | **0.54 ≤ L_loaded / L_unloaded ≤ 0.77** (70 µH design); 0.47–0.77 for alternate B | §2 |
| 4 | **DC resistance** | **≤ 0.100 Ω** at 25 °C including leads (target ≤ 0.080 Ω) | 4-wire milliohmmeter, 25 °C; derivation §2 "Resistance" |
| 5 | **AC resistance, unloaded** | **≤ 0.25 Ω at 40 kHz with the winding at 100 °C.** The 25 °C acceptance equivalent is **≤ 0.193 Ω at 40 kHz**. A measured **curve over 20–60 kHz** is required, every point ≤ 0.193 Ω·(f/40 kHz)^0.55 at 25 °C: 0.132 / 0.193 / 0.241 Ω at 20 / 40 / 60 kHz | Same LCR sweep as row 2 (series R). First articles also get one hot point: the winding soaked at 100 °C, R_ac at 40 kHz ≤ 0.25 Ω |
| 6 | **Continuous current** | **22 A RMS at any frequency in 35–60 kHz**, in the enclosure's coil-cooling condition (jet plenum, not still air). Limits: mean winding ≤ 150 °C, ferrite ≤ 140 °C | Thermal soak, §3 |
| 7 | **Peak current, non-repetitive** | **No saturation up to 98 A peak**, the maximum of the DC-return shunt OCP band (97.8 A; power-stage DECISIONS, stage-13 Kelvin band 47.32–97.77 A). L at 98 A peak within **3 %** of the small-signal L. The supplier states the ferrite's peak flux density at 98 A and 100 °C, which must be ≤ 0.75× the material's published B_sat at 100 °C | Ring-down pulse test, §3; supplier calculation on the CoC |
| 8 | **Conductor** | **Litz**, bare-copper strands **0.08–0.10 mm** (AWG 40–38), enamel thermal class ≥ 200 °C, bunched or Type 2 (served). Strand count must meet rows 4–5 (estimate ≥ 200 × 0.1 mm, i.e. ≥ 1.55 mm² Cu for about 9 m at 0.10 Ω). Skin depth in Cu at 60 kHz is 0.27 mm at 20 °C and 0.31 mm at 100 °C. Strands ≤ δ/3 keep strand-level skin effect negligible, and proximity loss in a many-strand bundle grows with d², which is why 0.2 mm strands are not acceptable here | Declared on the CoC (strand Ø, count, construction, enamel grade); rows 4–5 measured |
| 9 | **Outer diameter** | **Winding r 26–114, two sections, OD ≈ 228, ceiling 240.** Round 5 shows this winding couples to pans like R32's uniform r 22–116: reflected R per µH within 1–5 %, inductance drop within 2–4 %, modelled full-power yield at 120 V within 3.3 points. A Ø210 coil gains only about 1.6 points and cannot be cooled at 22 A (enclosure R33 study 09). Exact radii and the ferrite are in row 16 | Calipers |
| 10 | **Terminations** | Two leads in the winding's own Litz, terminated per row 15. Termination resistance is included in row 4 | Visual; row 4 |
| 11 | **Temperature class** | Litz, strand enamel, serving and any impregnant rated **≥ 200 °C** continuous (thermal class 200). Former and carrier per row 13. Pan temperature is capped at 250 °C. The glass underside reaches 230–250 °C in the fry and empty-pan hold cases (R32 study 02) | Datasheet / CoC |
| 12 | **Ferrite backing** | MnZn power ferrite, **N87/N97 class** (or equal: µi ≥ 2000, Curie ≥ 210 °C), **radial bars**, ≥ 8 × 20 mm wide, leaving the **≥ 14 mm cooling-jet lanes** between bars clear. Geometry per row 16. A plate or an air core is not acceptable: cooling, plus field pickup at the OCP Kelvin loop | Drawing check; rows 3 and 7 verify it electrically |

**Certificate of conformance shall report, per unit:**
- L_unloaded at 40 kHz, and the 20–60 kHz sweep;
- R_dc, and the R_ac 20–60 kHz curve at a stated winding temperature;
- L_loaded at 40 kHz with the supplier's own ferromagnetic reference pan (pan Ø and gap stated), and the ratio;
- Litz construction (strand Ø, count, enamel grade);
- ferrite material and bar count.

> §1b mechanical rows 13–16: see the main document (enclosure session).

### Why 70 µH, in one line

With the 0.50 µF bank, a 70 µH coil (66.3 µH installed) puts the nominal loaded resonance on
ferrous pans at **33.8–35.6 kHz**, at the bottom of the 35–60 kHz window. Full power is then reached
at 37–56 kHz with f/f_res ≥ 1.21 (round 5, Ø228 coil on a 220 mm pan). More turns raise the reflected pan R as N², and with it the power
available under the 22 A ceiling. Hence alternate B (§4).

---

## 2. THE ACCEPTANCE TEST — measure `L_loaded`

**This is the deliverable.** Rows 3 and 3b decide whether the coil works in this tank, and **no
vendor in this class states either**, so they are measured on receipt.

### Why a loaded measurement and not an inductance check

Only the **loaded** inductance resonates with the tank capacitor, and the pan's reflected
resistance is what turns the 22 A ceiling into power. A coil with a perfect unloaded reading and
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

(b) Window-top bound (binding): the controller must be able to hold 22 A / 11.1 A in continuous
    mode below F_MAX. Round 5's grid needs up to x_reg = f/f_res = 1.45 (Ø228 and Ø240, 108–140 V,
    1710 W request).
    f_res,max = F_MAX / x_reg = 60 000 / 1.45 = 41 379 Hz
    L_loaded,min (most strongly coupled pan in the population)
                 = 1 / ((2π × 41 379 Hz)² × 0.45 µF) = 32.87 µH

(c) Transfer to the one reference pan used at incoming inspection:
    kl(population minimum) / kl(reference class, cast iron nominal) = 0.4998 / 0.6308 = 0.792
    L_loaded,min on the reference pan = 32.87 / 0.792 = 41.5 µH      ← row 3
```

Below the floor, the grid shows what goes wrong (round 5, R34 winding at 58 and 53 µH installed):
- 60 kHz can no longer hold the envelope, and burst is needed in 2 and 10 of 45 cases respectively;
- the tank peak passes the 47.32 A shunt corner, reaching 52 and 61 A;
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
3. Measure R_dc (row 4) and the R_ac curve (row 5) at a recorded winding temperature, corrected to 25 °C with Cu +0.393 %/K.
4. Put the coil on the spacer stack. Centre the reference pan, empty and at room temperature.
5. Measure **L_loaded** at 40 kHz, same drive. Record it.
6. **ACCEPT if L_loaded ≥ 41.5 µH. Reject otherwise.**
7. Compute **L_loaded / L_unloaded**. It must lie in 0.54–0.77 (0.47–0.77 for alternate B); otherwise escalate.

No waiver on step 6 without re-deriving the floor with `floor.py`, and the firmware resonance and
peak-current limits with it.

### Resistance: rows 4 and 5

```
Requirement (R32): R_ac(40 kHz, winding 100 °C) ≤ 0.25 Ω
At 25 °C, conservatively assuming all of R_ac scales with copper resistivity:
  R_ac(40 kHz, 25 °C) ≤ 0.25 / (1 + 0.00393 × 75) = 0.193 Ω                       ← row 5
  (Proximity/eddy loss in strands much thinner than δ scales as 1/ρ, so it FALLS with
   temperature. The resistivity assumption is therefore the safe direction.)
Frequency shape: R_ac ∝ f^0.55 (round 4: onsemi 0.52, Infineon 0.59 over 30–50 kHz)
  → ≤ 0.132 / 0.193 / 0.241 Ω at 20 / 40 / 60 kHz, 25 °C
R_dc: a well-stranded Litz coil keeps F_R = R_ac/R_dc ≤ about 1.9 at 40 kHz. ESTIMATE: the supplier
  must show the curve; the Infineon kit coil, at 0.10 → 0.34 Ω (UG-2023-15 p. 21 Fig. 16), shows F_R 3.4,
  and such a coil would FAIL row 5.
  R_dc ≤ 0.193 / 1.93 = 0.100 Ω                                                      ← row 4
  Target 0.080 Ω, which leaves F_R up to 2.4.
```

Coil loss at the row-5 limit and 22 A: 121 W at 40 kHz and 151 W at 60 kHz (I²·R_ac at 100 °C).
That is inside R32's 200 W design figure.

---

## 3. Thermal soak (row 6) and saturation pulse (row 7)

**Not a go/no-go for first articles.** Both tests must pass before the coil is released for
production. Temper runs them on first articles in the enclosure, or in a fixture that reproduces
its coil cooling.

**Cooling condition** (R32 study 02, `output/temper-r32-studies/02-cooling-acoustics-venting/coil_thermal.py`;
R33 study 09 for this winding):
- **Jets:** a sealed jet plenum under the carrier, 135 × Ø3 mm jets on a 14 mm grid, 5.5 mm below the winding, blowing between the ferrite bars.
- **Supply:** fed by the push blower's ~27 % bleed, inlet air at **50 °C**.
- **Drive:** blower at the drive the coil loop commands. Study 09 needs 0.9 drive for 22 A at maximum R on this winding.
- **Glass gap:** stagnant, 3.5 mm to the glass.

**Cases.**
1. **22 A RMS, 40 kHz and 60 kHz**, on the reference pan holding boiling water (glass underside about 110 °C), until stable (≥ 30 min).
2. **12.7 A RMS fry hold**, with the glass underside at 230 °C.

**Pass:**
- **mean winding ≤ 150 °C**, by the resistance method (R_dc rise, Cu 0.393 %/K);
- **ferrite ≤ 140 °C** (thermocouple on the bar under the hottest turn);
- no discoloration of the serving or the carrier.

Model expectation (R32 study 02): 102.5 °C at a typical 17 A; 140.7 °C at 22 A with the old maximum R
and 50 °C inlet. With the row-5 limit (0.25 Ω hot instead of 0.41 Ω) the margin is larger. The
bench decides.

**Saturation pulse (row 7).** Charge a known film capacitor and discharge it into the coil, free in
air with its ferrite fitted, so the first current peak is 98 A. Then compare:
- the ring frequency of the first cycle with that of a ≤ 5 A ring of the same circuit. **L may differ by at most 3 %;**
- L at small signal before and after the pulse, **unchanged within 1 %.**

---

## 4. What this specification does to the rest of the design

| Quantity | Value | Moved by this spec? |
|---|---|---|
| Resonant bank | 5 × B32654A1104K000 = 0.50 µF ±10 % | No. Round 5: C moves resonance, not reflected R, so it is not the power lever |
| Control window | 35–60 kHz | No |
| ZVS guard | f ≥ 1.05·f_res from CT_ZC | **Required.** The fixed 35 kHz floor sits below 1.05·f_res at nominal coupling (§2 (a)) |
| Tank current ceiling / peak limit | 22 A RMS / firmware tank-peak limit about 45 A | No. Round-5 envelope peaks are 47.5–47.9 A at 66 µH, so the 45 A limit stays mandatory (DECISIONS 2026-10-09) |
| Coil loss of record | 200 W design figure (R32) | No. The row-5 limit gives ≤ 151 W at 22 A |
| **L target** | 70 µH (66.3 installed), alternate B 80 µH (≈ 76 installed) | **Open, power-stage decision.** Round 5 on 220 mm pans: MC full-power yield at 120 V rises from 13 % to 22–25 %, and the 47.32 A shunt corner is no longer passed. Alternate B also passes row 3 at −10 % L. Cost: floor-limited corners, 2/45 at 75 µH and 11/45 at 82 µH installed (power, not safety); about 7 % more turns, so R_ac rises about 14 % in the same winding window, and holding R_ac ≤ 0.25 Ω needs better copper fill; the firmware resonance tables and `coil_mc.rs` change |
| Legacy `elec/src` 88 µH / 300 nF and gate check 8 | Unchanged | **Stale.** They still check the half-bridge (§8) |

Round-5 modelled full-power yield at 120 V (MC over the five classes, 1239 W hold reached):

| Pan base | 180 mm | 220 mm | 260 mm |
|---|---|---|---|
| R34 two-section r 26–114 | 0.2 % | 13 % | 20 % |
| R32 uniform r 22–116 | 1 % | 16 % | 23 % |

Cast iron reaches 41–55 %. These are ASSUMED-basis numbers; the 22 A ceiling binds.

---

## 5. Provenance of the numbers

| Number | Source |
|---|---|
| 70 µH design, 66.34 µH installed | Power-stage selected design (`coil_mc.rs`, power-stage README); R32 study 06 FEM, accepted in power-stage DECISIONS 2026-10-09 item 5 |
| R_ac ≤ 0.25 Ω at 40 kHz / 100 °C, Litz ≥ 200 °C, N87/N97 radial bars on ≥ 14 mm lanes, 250 °C pan cap | Power-stage DECISIONS 2026-10-09 item 8 (R32 coil cooling) |
| Pan coupling classes (kl, r, α) | Round 4 assumed basis. Anchors: Infineon UG-2023-15 p. 21 Fig. 16; onsemi AND9201/D p. 7 Figs. 9–10; repo-transcribed MDPI 180 mm study |
| Coupling against OD and pan Ø | Round 5 FEM (R32 study-06 solver), used as ratios only |
| 0.50 µF, ±10 % | Power-stage DECISIONS 2026-10-09; TDK B3265*A data sheet |
| 97.8 A | Power-stage DECISIONS, stage-13 Kelvin band 47.32–97.77 A |

**What is UNVERIFIED, stated plainly:**
- No Temper coil or pan has been measured.
- The coupling ratios come from a linear-µ pan model.
- The floor's 0.792 transfer and x_reg 1.45 are assumed-basis numbers.
- Part-to-part spread of a wound coil is unknown; ±10 % is imposed, not measured.

> **Superseded:** the 2026-07-29 provenance (88 µH and ratio 0.68 read off Infineon Fig. 16 as the design value). That chart is now one of round 4's anchors, not the design.
