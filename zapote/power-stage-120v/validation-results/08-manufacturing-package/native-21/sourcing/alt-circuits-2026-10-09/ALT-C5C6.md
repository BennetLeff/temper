# C5/C6 DC-link film: alternative implementations from stocked parts

**Scope.** Native-21 power stage at stage 13b (`zapote/power-stage-120v`, board `scratchpad/s13b/section.kicad_pcb`). Written 2026-10-09.

**Method and limits.**
- The repo was only read. Nothing was committed, carted, quoted or logged into.
- Datasheets went to `alt-c5c6/dl/`, or were reused from `scratchpad/dl-c5c6/`.
- The licensed vendor models (Infineon CFD7, Nexperia PMEG) were used in place from `validation-plan/sim-kit/models/vendor/`. The copy that `run_ngspice` drops into each run directory is deleted after the run.
- No more than 4 ngspice workers ran at once.

**Contents of `alt-c5c6/`:**
- `scripts/`: `dump_board.py`, `dump_fills.py`, `probe_copper.py` and `tracks_in_box.py` (KiCad 10 python); `plane_L.py`, `ripple.py`, `bus_screen.py`, `f6_bulk.py`, `f6_summary.py` and `sketch.py` (system python).
- `results/`: the outputs of those scripts.

## 0. Answer first

**Recommendation for the 5-board lot: fit 2 × TDK B32676G1905K000 (9 µF ±10 %, 750 VDC at 85 °C, MKP DC-link) on the existing C5/C6 pads.**
- Digi-Key has 547 in stock (495-3024-ND, $10.53 each, $8.015 at 10; read 2026-10-09 ≈ 20:15Z). The lot needs 20.
- There is no copper change and no FEM re-extraction. It is a recorded basis change (deviation), and audit.rs needs a 2-line edit.

**Is it better than the 2.7 µF original? Better for the power stage's electrical margins; worse on the capacitors' own ratings. Not unambiguously better.**

**Better:**
- **Switching margins.** In the F6 decks with the bulk modelled explicitly, every one of 168 decision and startup cases passes.
  - The worst die VDS falls from 466 to 455 V on leg A and from 482 to 461 V on leg B.
  - The worst off-gate falls from 0.53 to 0.13 V (A) and from 0.78 to 0.51 V (B) (§5).
  - The mechanism is the lower ESL (12 nH against 19.2 nH), not the extra C. The sweep shows C has no effect on these edges; die VDS rises about 5 V per nH of bulk-path inductance.
- **HF bus ripple voltage** falls 2.7× (5.5 → 2.0 V rms at the 22 A ceiling).
- **Returned-energy overshoot** is lower: 312 V against 369 V for a 71 A OCP trip from 280 V, unclamped.

**Worse:**
- **Ripple self-heating** reaches about 80 % of TDK's permitted ΔT at an 85 °C cap ambient, against about 35 % for the original.
- **Rated voltage** is 750 V against 1000 V. Both are far above the 410 V TVS clamp.
- **Pulse rating** is 85 V/µs against 400 V/µs. That is still enough: 765 A per part against a 630 A lossless worst inrush shared by two parts.
- **System side effects:**
  - bleed time ×3.3, to 11 s from 280 V to 60 V;
  - plug-in inrush I²t ×6, still ≤ 1.8 % of F1's melting I²t;
  - burst-power bus valley 106 V against 33 V;
  - line C·dV/dt peak 1.5 A against 0.46 A.

**New finding (applies to every option, the original included).**
- The S4 hard-turn-on margin depends on the *bulk-path inductance*: the copper from the legs to the bulk plus the bulk ESL.
- With the bulk modelled as real capacitors, rather than the repo deck's ideal source, die VDS rises about 5 V/nH. S4 fails (> 520 V, or off-gate) at about 28–32 nH.
- The basis bulk path is about 20 nH: plane estimate 8 nH trunk, C6 +12.7 nH, ESL 19.2 nH. That estimate is ±50 %, so the basis sits within the uncertainty of the failure threshold.
- **A native-21 extraction of the bulk path** (a P5-style port, as in legA5) is therefore worth doing whichever part is fitted.
- Option A moves the bulk path 4 nH further from the threshold.

**If the build can wait,** TDK samples of B32656G0275J000 or M000 are the zero-deviation route. M at −20 % is identical in the decks.

**The only equal-capacitance stocked layout that is better on every electrical axis does not fit without moving copper.** It is 4 × KEMET R75PR415050H3J (1.5 µF, 27.5 mm pitch, 583 in stock, two per site):
- 6.4 µF total;
- 64 % ripple use;
- 451/452 V worst die VDS.
- It needs a footprint ECO, plus a mains-track re-route at C5 (§4 E).

## 1. What the DC-link bulk actually does on native-21 (the requirements)

| Requirement | Accepted band | Why |
| --- | --- | --- |
| Bulk C | **4.7–7 µF nominal is "equivalent"** (min ≥ 4.3 µF at tolerance). 7–20 µF is a basis change and needs the re-validation list in §6. | BUS-CAP-SCREEN and DC-LINK-CLAMP treat 5.0 → 5.8 µF as a minor input-current effect. The 2026-10-09 alternates note treated the M-code worst case (4.72 µF total) as acceptable with an audit edit. The D-32 / LINE_ZC valley lag, the bleed and the inrush notes are all written for about 5.8 µF. Above about 7 µF those screens move by more than 20 % and must be re-run. Below about 4.3 µF the returned-energy overshoot (71 A trip) exceeds 380 V (`bus_screen.md`). |
| Voltage | VR ≥ 520 V at the cap's hot-spot temperature | Bus ≤ 280 V (static OVP corner 286 V). The TVS clamps ≤ 410 V at 282 A. The 520 V transient target sits above that. |
| Ripple | Two-site bank: ≥ 13 A per part at 85 °C / ~100 kHz. Single-part bank: ≥ 24 A. | `ripple.py`, worst over the task-05 envelope with I_tank ≤ 22 A: total HF bus current up to 21.4 A rms. In the basis split, C5 carries 12.75 A and C6 11.2 A. |
| ESL / path | **Total bulk-path L (shared trunk + per-site copper + ESL, sites in parallel) ≤ the basis ≈ 20 nH. Lower is better.** | C5/C6 sit 150–230 mm from the FETs, and the edge current closes through C38–C41. During the S4 diode-recovery edge, though, the bulk path re-supplies the local row. `lbulk_sweep.md` gives about +5 V die VDS per nH, independent of C (5.4 and 18 µF are identical), and failures at 28–32 nH. |
| Pulse | C × dV/dt ≥ worst bulk peak current (inrush ≤ 630 A lossless bound; edges ≤ 71 A) | §2 and `bus_screen.md` |
| Envelope | Within the C5/C6 courtyards (42.6 × 33.6 mm each). Height ≤ 48.4 mm. | Footprint and RELAYOUT L12. The C5 courtyard is boxed in: L1 is 0.3 mm above it and U36 0.3 mm below; an F.Cu L_FILT track runs at x 230 and a B.Cu N_FILT track at x 237.5 under the body; the LINE_ZC SELV spur sits at its lower left. C6 has 8.7 mm free above it (towards L1/C2) and D3 1.0 mm below. |

**Bus ripple current is new evidence.**
- No repo file had a qualified bus-ripple figure: BUS-CAP-SCREEN and task 07 both say so.
- `ripple.py` drives the task-05 round-4 pan basis (5 classes plus offset pan, at nominal and R/L corners), line 108/120/140 V, f 35–60 kHz, and I_tank ≤ 22 A, through an ideal full bridge. It splits i_bus = i_tank·sgn(v) among the local row, C5 and C6 by impedance.
- Results are stable to ±5 % over a 0–200 ns commutation time (`ripple-tr*.md`).
- Above about 600 kHz, the bulk/local anti-resonance (about 1.3 MHz) carries part of each branch's current. That part depends on the assumed HF damping, so the local-row figures are only indicative.
- Harmonics ≤ 600 kHz alone give 9.6–10.4 A per basis cap (`ripple-lf600k.md`).

## 2. Candidate survey: what is stocked (Digi-Key, read 2026-10-09 ≈ 20:05–20:25Z)

| MPN | C / VR | Pitch, pins, body w×h×l | Irms (datasheet basis) | ESL | dV/dt | DK stock, price | Fits C5/C6 pads? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **TDK B32676G1905K000** | 9 µF ±10 %, 750 V (85 °C), 900 V (70 °C) | 37.5, 4-pin, P1 20.3, d1 1.2; 30×45×42 | 19.5 A at 70 °C/10 kHz; ×0.7 at 85 °C → 13.7 A. ESR 5.1 mΩ. G 100 mW/K | 12 nH typ | 85 V/µs → 765 A | **547**, $10.53 / $8.015 at 10 | **Yes, drop-in** |
| TDK B32676G1106K Z 1 | 10 µF, 750 V | same | 20.5 A (70 °C) | 13 nH | 85 | 18,789, $11.39 | Yes. Non-catalogue suffix: confirm with TDK first |
| TDK B32676G8106K000 | 10 µF, 875 V | 33×48×42 | 22.5 A | 14 nH | 100 | 7 (lot needs 20) | Yes, but stock is short |
| TDK B32676G8755K000 | 7.5 µF, 875 V | 30×45×42 | 19.0 A | 13 nH | 100 | not stocked (27 wk) | – |
| KEMET R75PW456050H3J | 5.6 µF ±5 %, 630 V | 37.5, 2-pin; 24×44×41.5 | 16.5 A (85 °C/100 kHz, ΔT 20 K) | 20 nH | 90 → 504 A | 186, $14.24 | One part on C6 pads 1/3 only. **Fails ripple** as a single part (27 A needed) |
| KEMET R75PW4470JE30K | 4.7 µF ±10 %, 630 V | 37.5, 2-pin; 20×40×41.5 | 14.5 A | 20 nH | 90 | 313, $6.60 / $4.837 | C6 row 1 only (C5: hits L1). **Fails ripple** as a single part |
| WIMA MKP4J043307F00MSSD | 3.3 µF ±20 %, 630 V | 37.5, 2-pin; 19×32×41.5 | not read (WIMA PDF fetch blocked) | – | – | 700 (Marketplace), $6.75 | C6 only; ±20 % |
| KEMET R76PW410050H3J | 1 µF, 630 V | 37.5, 2-pin; 16×28.6×41.5 | 11.1 A | 20 nH | 450 | 333, $7.83 | Two per site would give only 4 µF total, and at C5 a 16 mm body collides with L1/U36 |
| R75PW4150 / R76PW4150 (1.5 µF, 13–16 w, 37.5) | | | | | | **0** (20 wk) | Would fit two per site at 13 mm. Not stocked |
| **KEMET R75PR415050H3J** | 1.5 µF ±5 %, 630 V | **27.5**, 2-pin; 14×28.1×32 | 8.5 A (85 °C/100 kHz) | 18 nH | 210 → 315 A | **583**, $4.46. R75PR4150AA30K (±10 %): 1,494, $3.65 | **No: new pads (ECO)** |
| KEMET R75PR427050H3J | 2.7 µF ±5 %, 630 V | 27.5; 22×37.1×32 | 10.4 A | 18 nH | 210 | 160, $8.34 | ECO; 10.4 A < 11.8 A needed. **Fails ripple** |
| Vishay MKP1848C… 37.5 4-pin; WIMA DC-LINK 37.5 4-pin | 10–50 µF | P2 10.2 / b 12.5–20 | – | – | – | stocked | No: their 4-pin row spacing ≠ 20.3, and C is too high |
| CDE 944U / 947D | 33–500 µF stud | – | – | – | – | – | No |
| Panasonic ECW-FE/FD, KEMET C4AE/C4AQ, Vishay MKP385, TDK B32674/B32654/B32652 | | ≤ 27.5 mm pitch (FD/FE, B3265[2-4]) or S1 = 10.2 (C4AQ) | | | | | Not on the 37.5 × 20.3 grid. The 27.5 mm candidates are represented by R75PR above |

Product URLs: `https://www.digikey.com/en/products/result?keywords=<MPN>` and the film-capacitor filter `…/filter/film-capacitors/62?keywords=R75PR4`, `…=R75PW4`, `…=R76PW41`, `…=MKP4J04`, `…=MKP1848C`, `…=DCP4`.
- Stock figures are single reads. For several WIMA rows the stock is Digi-Key Marketplace stock.

Datasheets:
- TDK B3267* (6/26): pp. 10, 14 (dV/dt), 27–29 (IRMS derating, G, ΔT_max(85 °C) = 0.7² × 20 K).
- TDK B3265* (6/26): p. 29.
- KEMET R75 F3106: table rows 1568–1569 for 37.5 mm, 1540–1560 for 27.5 mm; footnote that Irms gives ΔT ≈ 20 K at 85 °C; voltage derating 2 %/K above 85 °C.
- KEMET R76H F3118: 37.5 mm row.

**No stocked 2-pin, 37.5 mm part at ≥ 630 V and ≥ 1.35 µF is ≤ 13.2 mm wide.** That width would let two parts share one existing footprint with no courtyard change. R75PW4150 at 13 mm is the one that fits, and it has 0 stock.

## 3. Board facts (stage-13b, `results/board_dump.json`, `results/fit_sketches.png`)

- **Positions.** C5 is at pads (205.25, 65.45)/(205.25, 85.75) bus_p and (242.75, …) hv_ret. C6 is at (248.25, 73.85)/(248.25, 94.15) bus_p and (285.75, …) hv_ret. Both connect through the In2 bus_p / In1 hv_ret trunk, a 0.5 mm core.
- **The hv_ret trunk is cut on In1 near C5** and bridged on F.Cu/B.Cu ("hv_ret trunk bridge", x 203.5–226, y 52.5–75).
- **Plane-pair estimate** (`plane_L.py`: μ0·h × 2-D resistance of the overlapping sheets, 0.2 mm raster; F/B bridge counted at its own h):
  - leg A → C5 pads: 7.9 nH;
  - leg A → C6 pads: 20.6 nH, through a narrow neck where the trunk meets the C6 block;
  - a hypothetical site on the trunk at x 110–125: 2.1 nH.
  - Leg B's return does not connect through the overlap in this model (its hv_ret leaves the In1 sheet near R5), so it is not estimated.
  - These are estimates, ±50 %. The FEM P5 port of round 17 was on native-17 copper.
- **C6 is the worse-connected site.** Any option that puts all the bulk at C6 adds about 13 nH of path.
- **Clearances** (`section.kicad_dru`): HOT potential groups 3.2 mm; HOT–SELV 8.0 mm.
  - New 27.5 mm pads at C5 land either 1–3 mm from L_FILT (F.Cu x 230) or N_FILT (B.Cu x 237.5), inside the hv_ret bridge pour, or < 8 mm from the SELV `selv_gnd`/LINE_ZC spur at (215, 94) (`probe_eco_pads.txt`, `tracks_c5c6_area.txt`).
  - At C6, new pads at (248.25, 74.25/89.25) bus_p and (275.75, 74.25/89.25) hv_ret are clear: inside the bus_p/hv_ret planes, ≥ 3.6 mm from busbleed_mid, with no other-net copper within 4 mm.

## 4. Options

### A. 2 × B32676G1905K000 on the existing pads (recommended now)

- **Fit.** It is the same drawing as the basis (B1, e 37.5, P1 20.3, d1 1.2 mm in the existing Ø1.8 mm drills). The 30 × 45 × 42 mm body is inside the 33 × 48 × 42 courtyard and height basis. No other part moves (`fit_sketches.png`, panel A).
- **C.** 18 µF ±10 % bulk, 18.4 µF total: 3.4× the basis, outside the "equivalent" band.
- **Voltage.** 750 VDC at 85 °C, 900 V at 70 °C, overvoltage 1.3·VR for 1 min. It is ≥ 1.8× the 410 V clamp.
- **Ripple** (`ripple-tr100.md`). Worst cases are 12.4 A in C5 and 11.3 A in C6 (aluminium-clad pan, low-R corner, 140 V, 45.5 kHz, I_tank 22 A).
  - TDK self-heating method: P = 5.1 mΩ × 12.4² = 0.78 W, so ΔT = 0.78 / 0.100 = 7.8 K.
  - Allowed at 85 °C ambient: 0.7² × 20 = 9.8 K, which is 80 % used. At a 70 °C ambient the allowance is 20 K, 39 % used.
  - ESR at about 100 kHz is not tabulated. A +25 % ESR at 85 °C takes it to the limit, so **cap ambient ≤ 75 °C or a case-temperature measurement is a condition.**
  - The basis caps run 12.75 A against a 22.8 A rating (56 %, about 35 % of their ΔT budget).
- **ESL.** 12 nH, against 19.2 nH. The bulk-path equivalent is 16.1 nH, against 20.0 nH.
- **Pulse.** 85 V/µs × 9 µF = 765 A per part. The worst plug-in inrush, lossless at 2 µH, is 630 A over two parts.
- **F6 decks** (§5): 168/168 pass. Worst die VDS is 455/461 V (basis 466/482 V) and worst off-gate 0.13/0.51 V (basis 0.53/0.78 V). Per case the change is −22 … +18 V VDS. The higher points are non-worst cases.
- **Functional changes** (`bus_screen.md`, 140 V crest, worst tolerance):

| | basis | A |
| --- | ---: | ---: |
| HF ripple V/A at 66 kHz | 0.416 | 0.131 |
| HF bus ripple at worst point (ripple.py) | 5.5 V rms | 2.0 V rms |
| bus after 71 A OCP-trip energy (0.159 J), from 280 V, no clamp | 369 V | 312 V |
| bus after nominal-ceiling energy (0.030 J) | 299 V | 287 V |
| bleed τ / 280 → 60 V (R_bleed 356 kΩ) | 2.2 s / 3.4 s | 7.2 s / 11.1 s |
| plug-in inrush peak / I²t, 2 µH lossless | 346 A / 0.66 A²s | 630 A / 4.0 A²s |
| plug-in inrush peak / I²t, 10 µH | 155 A / 0.29 A²s | 282 A / 1.8 A²s |
| burst-power (160 W) bus valley | 33 V | 106 V |
| line C·dV/dt peak | 0.46 A | 1.51 A |

  - Inrush against limits: KLDR025 melting I²t is 226 A²s, so A uses ≤ 1.8 %. GBJ2510's I²t is 510 A²s (≤ 0.8 %). Its IFSM of 350 A is an 8.3 ms rating; a 15–30 µs pulse is governed by I²t.
  - The 106 V valley no longer matters for zero-cross, because bursts now take LINE_ZC, but it changes the burst-current shape and must be re-checked.
- **Re-validation:**
  - BUS-CAP-SCREEN re-run (power_section.rs with 18.4 µF);
  - F6 / leg decks: done here at screen level (§5); the repo `f6_legs.py` deck has an ideal source on the bulk node, so C is invisible to it;
  - task-07 EMI CBULK = 18.4 µF (DM falls);
  - inrush and F1/BR1 note (F1-RECOMMENDATION §3.4 table);
  - bleed time (service note);
  - DECISIONS line on the burst valley.
  - No FEM.
  - audit.rs lines 278–279 change to `B32676G1905K000`. In parts.ato, the `BusFilm2u7` docstring and mpn change (diff in ALTERNATES-2026-10-09.md §1); keep the footprint.
- **Part count:** 0 change. **Risk:** low mechanically. The thermal margin is thinner, so measure the case temperature on the first powered run at 22 A.

### B / C. One stocked part per bank (C5 or C6 empty): **rejected**

| Option | Parts | Total bulk | Failure |
| --- | --- | ---: | --- |
| B | B32676G1905K000 at C5 only | 9 µF | Carries 23.4 A, against 13.7 A at 85 °C |
| C | R75PW456050H3J at C6 pads 1/3 only | 5.6 µF, the closest C match | Carries 27.4 A, against 16.5 A |
| C′ | R75PW4470JE30K at C6 only | 4.7 µF | 27 A, against 14.5 A |

- The rest of B and C is attractive: one fewer part, and C keeps the C band.
- They fail because **a single bulk part carries the whole 21 A bus HF current** (`ripple-tr100.md`).
- C also fails the switching decks: 75/84 and 72/84 pass, die VDS up to 616 V. Its single site is the far one, C6, at about 41 nH of bulk path.
- B (at C5, 20 nH) matches the basis in the decks: 167/168, plus one aborted run.

### D. Move the bulk closer to the legs / split per leg

- A bulk site on the trunk near BR1 (x 110–125) would cut the copper path from about 8–21 nH to about 2 nH (`plane_L.json`).
- **No courtyard there is free** (BR1, links J7–J10, the In1/In2 trunk band). Placing 37.5 mm film parts next to the legs means re-placing the F6 network or the HF film row, which DECISIONS 2026-10-08 rejects.
- The deck test (§5, D_bulk_at_trunk: basis caps at 2 nH trunk instead of 8, about 11.6 nH path) shows what it would buy: worst die VDS 448/435 V and off-gate −0.47/−0.26 V on legs A/B. **This is the biggest bulk-side lever, but it is a re-layout.**

### E. Several smaller stocked films in parallel: 4 × KEMET R75PR415050H3J (two per site), footprint ECO

- **C.** 6.0 µF ±5 % bulk, 6.4 µF total: +11 % over basis, inside the band.
- **Voltage.** 630 V at ≤ 85 °C, derating 2 %/K above that. The hot spot is ≤ 93 °C at a 85 °C ambient, giving VR ≥ 529 V.
- **Ripple.** 5.4 A per part against 8.5 A (64 %). ΔT ≈ 0.31 W × 26 K/W = 8 K against a 20 K allowance.
- **ESL.** 9 nH per site (2 × 18 nH in parallel).
- **Pulse.** 210 V/µs, 315 A per part.
- **In the anti-resonance model, the higher film ESR halves the HF current in the local row** (12 → 6.3 A). This is indicative only (§1).
- **F6 decks** (variant H, path about 14.4 nH): 168/168 pass. Worst die VDS 451/452 V and off-gate −0.10/0.14 V, better than both the basis and A.
- **Fit.**
  - C6: two rows of 14 mm bodies on new P27.5 pads, at (248.25, 74.25/89.25) bus_p and (275.75, …) hv_ret. All are clear (§3; panel E). Pads Ø2.4 / drill 1.1–1.2 mm for 0.8 mm leads.
  - **C5 does not fit without moving copper.** Every legal P27.5 pad column there conflicts with L_FILT/N_FILT (3.2 mm rule), the hv_ret bridge, or the 8 mm SELV barrier. A full E needs the C5-area mains runs re-routed (L_FILT F.Cu x 230, N_FILT B.Cu x 237.5), or the LINE_ZC spur moved.
- **Re-validation:**
  - new footprint (two parts per site, so four refs replace C5/C6);
  - zone refill and DRC/barrier gates;
  - JLC DFM;
  - audit.rs: `c_bus*` MPNs, the four-pin expect block (lines 745–750) and the **hv_ret exact-member set** (lines 760–766);
  - FEM P5 port moves (only native-17 legA5 used it; the bulk-ab test showed ≤ 0.3 V effect, so a deck re-run suffices);
  - F6 (§5, variant H);
  - EMI CBULK 6.4 µF (negligible);
  - STEP/enclosure height (28 mm, lower).
- **Part count:** +2 (four parts, eight joints, against two parts and eight joints).
- **Risk:** medium. It is a copper ECO at a frozen stage, and the re-route sits next to the mains/SELV spur.
- **Is it better than the basis?**
  - Equivalent on C (+11 %) and on ripple margin (64 % against 56 % of rating).
  - Better on bulk-path L and switching margin (−15 / −30 V die VDS).
  - Worse on voltage rating (630 V against 1000 V, ≥ 529 V hot), and it needs an ECO.
  - It is the right choice for a re-spin, not for this lot.

### M. MLCC-assisted

- **Bulk from MLCCs: rejected.**
  - X7R 630 V 1210 parts lose 30–50 % at 280 V DC bias. Building 5.4 µF effective needs 50 or more parts; with C0G 1 kV 10 nF it needs about 540.
  - Large X7R chips on a 2 oz, 1.65 mm board carrying heavy THT parts and a clamped sink are a flex-cracking risk.
  - X7R is piezoelectric under the 120 Hz-modulated bus (acoustic noise).
- **HF C0G decoupler at the FET row** (the DECISIONS 2026-10-08 "first lever"):
  - 8 × KEMET CKC18C103JDGACAUTO (10 nF/1 kV C0G 1812; Digi-Key 730, $5.27; not flex-terminated) bridging bus_p to **hv_ret** (not leg_ret, so R5 still sees shoot-through), with an assumed 5 nH mounted loop.
  - Result (variant E_basis_plus_c0g in §5): worst die VDS 427/425 V (−40/−57 V against basis), all 168 pass.
  - The worst off-gate rises in some cases, by up to +1.96 V against the same case; the worst is 1.18 V on leg A against the 1.9 V screen. The C0G-loop ring couples into the gate, which the FEM's mutuals would have to settle.
  - It does not replace C5/C6, and it needs copper inside the FET row plus a FEM re-extraction of both legs.

### Not stocked but zero-deviation

- **TDK samples of B32656G0275J000, or B32656G0275M000** (±20 %, 21.0 A, 30 × 45 × 42 mm).
- M at −20 % is variant G in §5. At bulk minimum (4.72 µF total) the OCP overshoot is 382 V against 369 V.

## 5. Switching-deck evidence (`f6_bulk.py`, `results/f6_summary.md`)

**Deck.**
- The base is the repo's generated F6 deck (`d2/results/f6-vneg-m1p6-legA21-s9b2/F6.cir`: F6 at −1.6 V, PMEG6030EP, itl4), with the native-21 s9b2 matrices for legs A and B. It was read only.
- The `ref` variant is that deck unchanged. It reproduces the repo maxima exactly: A 467.6 V / 0.694 V, B 490.2 V / 1.145 V.
- **Replaced bus section.** In the repo deck `Vbus → 10 mΩ` pins the bulk node, so CBULK does nothing and only LBULK (21.5 nH, round-3 heuristic) acts. Here the source feeds through 10 µH and two explicit bulk branches (C, ESR, ESL + site copper) hang off a shared trunk L to the FET drain node. This lets C, ESL and position act.
- Coupling of the bulk path to the gate loops is not modelled. The bulk-ab test bounds it at ≤ 0.3 V off-gate.

**Cases** (84 per leg, Tj 27 °C, where every repo maximum occurs):
- S4 at 3 buses × 3 dead times × 2 directions;
- S1 at 198/280 V;
- S2 at 280 V / 71 A;
- S5 at 3 × 3 × 2;
- local ESL 1.06 and 10 nH.

**Criteria:** die VDS ≤ 520 V (≤ 585 V for S2); off-gate < 1.9 V (hot screen); ZVS for S1.

**Variant parameters** (nH; copper from `plane_L.py`; ESL from datasheets):

| variant | trunk | site C5 branch | site C6 branch | equivalent bulk path |
| --- | ---: | --- | --- | ---: |
| basis | 8 | 2.7 µF, 19.2 | 2.7 µF, 12.7 + 19.2 | 20.0 |
| A_b32676x2 | 8 | 9 µF, 12 | 9 µF, 12.7 + 12 | 16.1 |
| B_b32676_C5only | 8 | 9 µF, 12 | – | 20.0 |
| C_r75_5u6_C6only | 8 | – | 5.6 µF, 12.7 + 20 | 40.7 |
| D_bulk_at_trunk | 2 | 2.7 µF, 19.2 | 2.7 µF, 19.2 | 11.6 |
| E_basis_plus_c0g | basis + 80 nF C0G at FET drain, 5 nH loop | | | |
| F_basis_lbulk_x2 | 16 | 2.7 µF, 19.2 | 2.7 µF, 25.4 + 19.2 | 29.4 |
| G_m000_tol_low | 8 | 2.16 µF, 19.2 | 2.16 µF, 31.9 | 20.0 |
| H_r75pr_2per_site | 8 | 3.0 µF, 9 | 3.0 µF, 12.7 + 9 | 14.4 |

| variant | leg | complete | pass (VDS + 1.9 V off-gate + S1 ZVS) | max die VDS (V) | max off-gate (V) | worst S4 VDS | worst S5 VDS | ΔVDS vs basis (min…max) | Δoff vs basis (min…max) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| A_b32676x2 | A | 84/84 | 84 | 455.1 | 0.134 | 455.1 | 424.5 | -22.2 … +17.5 | -0.477 … +0.091 |
| A_b32676x2 | B | 84/84 | 84 | 460.7 | 0.505 | 460.7 | 391.1 | -21.9 … +15.9 | -0.507 … -0.004 |
| B_b32676_C5only | A | 83/84 | 83 | 465.6 | 0.532 | 465.6 | 435.9 | -0.8 … +7.3 | -0.006 … +0.065 |
| B_b32676_C5only | B | 84/84 | 84 | 481.9 | 0.856 | 481.9 | 401.2 | -0.5 … +6.8 | -0.006 … +0.079 |
| C_r75_5u6_C6only | A | 84/84 | 75 | 615.6 | 1.751 | 615.6 | 496.9 | -34.3 … +161.1 | -0.156 … +1.608 |
| C_r75_5u6_C6only | B | 84/84 | 72 | 559.8 | 2.308 | 559.8 | 434.1 | -21.7 … +87.1 | -0.177 … +1.536 |
| D_bulk_at_trunk | A | 84/84 | 84 | 447.6 | -0.468 | 447.6 | 404.7 | -56.1 … +11.0 | -1.050 … -0.024 |
| D_bulk_at_trunk | B | 84/84 | 84 | 435.2 | -0.263 | 435.2 | 381.2 | -46.5 … +10.3 | -1.181 … -0.033 |
| E_basis_plus_c0g | A | 84/84 | 84 | 426.5 | 1.184 | 426.5 | 409.7 | -101.0 … +26.3 | -0.578 … +1.957 |
| E_basis_plus_c0g | B | 84/84 | 84 | 424.6 | 0.894 | 424.6 | 409.3 | -126.9 … +37.0 | -0.510 … +1.320 |
| F_basis_lbulk_x2 | A | 81/84 | 80 | 520.8 | 1.104 | 520.8 | 460.2 | -10.2 … +65.3 | +0.060 … +1.029 |
| F_basis_lbulk_x2 | B | 84/84 | 81 | 523.3 | 1.705 | 523.3 | 419.3 | -10.6 … +43.6 | -0.180 … +0.925 |
| G_m000_tol_low | A | 84/84 | 84 | 466.2 | 0.531 | 466.2 | 435.9 | -4.6 … +0.7 | -0.086 … -0.001 |
| G_m000_tol_low | B | 84/84 | 84 | 482.0 | 0.772 | 482.0 | 401.3 | -4.4 … +1.8 | -0.051 … +0.120 |
| H_r75pr_2per_site | A | 84/84 | 84 | 451.1 | -0.104 | 451.1 | 417.8 | -35.0 … +11.4 | -0.717 … +0.006 |
| H_r75pr_2per_site | B | 84/84 | 84 | 451.7 | 0.141 | 451.7 | 385.2 | -30.9 … +6.8 | -0.761 … -0.017 |
| basis | A | 84/84 | 84 | 466.1 | 0.534 | 466.1 | 435.9 | +0.0 … +0.0 | +0.000 … +0.000 |
| basis | B | 84/84 | 84 | 481.7 | 0.780 | 481.7 | 401.5 | +0.0 … +0.0 | +0.000 … +0.000 |
| ref | A | 84/84 | 84 | 467.6 | 0.694 | 467.6 | 439.6 | -6.7 … +17.4 | +0.010 … +0.268 |
| ref | B | 84/84 | 84 | 490.2 | 1.145 | 490.2 | 405.3 | -1.7 … +18.6 | +0.004 … +0.394 |

- The three `F` indeterminate runs on leg A are ngspice aborts. Count them as unknown.
- The S4 failures in C and F are the bulk path, not C. The sweep (`lbulk_sweep.py`; one bulk branch; total path L; worst S4 points; cells show die VDS / off-gate):

| leg | case | local ESL | C bulk µF | L 12 nH | L 16 nH | L 20 nH | L 24 nH | L 28 nH | L 32 nH |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | S4 280 V dir 1 | 1.06 | 5.4 | 419 V / -0.97 V | 433 V / -0.95 V | 454 V / -0.77 V | 480 V / -0.61 V | 508 V / -0.44 V | 538 V / -0.25 V FAIL |
| A | S4 280 V dir 1 | 1.06 | 18.0 | 420 V / -0.95 V | 434 V / -0.94 V | 455 V / -0.76 V | 481 V / -0.60 V | 508 V / -0.44 V | 539 V / -0.24 V FAIL |
| A | S4 280 V dir 1 | 10 | 5.4 | 424 V / -0.99 V | 437 V / -1.00 V | 453 V / -0.88 V | 471 V / -0.75 V | 490 V / -0.62 V | 514 V / -0.47 V |
| A | S4 280 V dir 1 | 10 | 18.0 | 425 V / -0.97 V | 438 V / -0.98 V | 454 V / -0.87 V | 471 V / -0.74 V | 490 V / -0.61 V | 514 V / -0.47 V |
| B | S4 170 V dir 1 | 1.06 | 5.4 | 424 V / -0.48 V | 446 V / 0.00 V | 463 V / 0.34 V | 479 V / 0.53 V | 494 V / 0.67 V | 502 V / 0.71 V |
| B | S4 170 V dir 1 | 1.06 | 18.0 | 424 V / -0.46 V | 446 V / 0.02 V | 463 V / 0.35 V | 479 V / 0.54 V | 494 V / 0.68 V | 502 V / 0.71 V |
| B | S4 170 V dir 1 | 10 | 5.4 | 438 V / -0.34 V | 459 V / 0.25 V | 482 V / 0.77 V | 501 V / 1.18 V | 519 V / 1.47 V | 525 V / 1.67 V FAIL |
| B | S4 170 V dir 1 | 10 | 18.0 | 438 V / -0.33 V | 460 V / 0.26 V | 482 V / 0.78 V | 501 V / 1.19 V | 519 V / 1.48 V | 525 V / 1.68 V FAIL |
| B | S4 198 V dir 1 | 1.06 | 5.4 | 420 V / -0.88 V | 439 V / -0.72 V | 455 V / -0.44 V | 468 V / -0.28 V | 482 V / -0.18 V | 492 V / -0.13 V |
| B | S4 198 V dir 1 | 1.06 | 18.0 | 421 V / -0.85 V | 440 V / -0.71 V | 456 V / -0.42 V | 469 V / -0.27 V | 482 V / -0.17 V | 492 V / -0.12 V |
| B | S4 198 V dir 1 | 10 | 5.4 | 434 V / -1.00 V | 454 V / -0.46 V | 474 V / 0.04 V | 492 V / 0.48 V | 509 V / 0.80 V | 529 V / 1.09 V FAIL |
| B | S4 198 V dir 1 | 10 | 18.0 | 435 V / -0.99 V | 454 V / -0.45 V | 474 V / 0.05 V | 492 V / 0.49 V | 509 V / 0.81 V | 529 V / 1.10 V FAIL |

**Reading:**
- C (5.4 against 18 µF) changes nothing on the edge.
- The path inductance moves die VDS about 4–7 V/nH. The first failures appear at 28–32 nH.
- The native-21 bulk path is not extracted. The plane estimate (±50 %) puts the basis at about 20 nH (16–24 nH), so a P5-style FEM port on native-21 (or a measurement) should close this for whatever is fitted.


## 6. Ranking

| Rank | Option | Copper change | Parts (Δ) | C total | Bulk path | F6 worst VDS A/B | Verdict |
| --- | --- | --- | ---: | ---: | ---: | --- | --- |
| 1 | **A: 2 × B32676G1905K000, existing pads** | none | 2 (0) | 18.4 µF | 16.1 nH | 455 / 461 V | **Build now** as a recorded basis change |
| 2 | TDK samples J000/M000 | none | 2 (0) | 5.8 (M min 4.72) µF | 20.0 nH | 466 / 482 V | Zero deviation if they arrive in time; not stocked |
| 3 | E: 4 × R75PR415050H3J, footprint ECO | both sites; C5 needs a mains re-route | 4 (+2) | 6.4 µF | 14.4 nH | 451 / 452 V | Better on everything except VR (630 V); re-spin option |
| 4 | M: C0G bank at FET row (add-on) | FET-row copper + FEM both legs | +8 | – | – | 427 / 425 V (off-gate ↑) | Only if the FEM fails a case (DECISIONS lever) |
| 5 | D: bulk next to legs | re-placement | – | – | 11.6 nH | 448 / 435 V | Largest bulk-side gain, but not possible at stage 13 |
| ✗ | B / C / C′ single-part banks; twin 2-pin per footprint | none | 1 (−1) | 4.7–9 µF | 20–41 nH | C: fails S4 | Ripple overload (23–27 A against 14–17 A); C also fails S4; no narrow 37.5 mm part in stock |

**Re-validation cost of A:**
- BUS-CAP-SCREEN re-run with 18.4 µF;
- F1-RECOMMENDATION inrush row;
- EMI CBULK;
- DECISIONS entries for the bleed time and burst valley;
- audit.rs lines 278–279 and the parts.ato `BusFilm2u7` MPN and docstring;
- the F6 decks at screen level (this note), or adopt `f6_bulk.py`'s explicit-bulk deck in the repo;
- a first-power case-temperature check at the 22 A ceiling.
- There is no FEM and no copper work.
- The bulk-path extraction is recommended independently of the part choice.

**Plain statement.**
- Option A is **better than the original for the power stage**: switching margins, bus ripple and overshoot.
- It is **worse for the capacitors' own ratings**: ripple self-heating, VR and dV/dt, though each still has adequate margin.
- It changes the bleed, inrush and burst-valley behaviour, and those must be re-checked.
- Net: not unambiguously better. It is the best stocked option that needs no copper change.
