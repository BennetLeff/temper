# c54-j1-thermal: J1 (Phoenix 1714971) with the real 14 AWG cord (OPEN-ITEMS S21)

Analysis lane, 2026-10-18, on the s53 board of record (`82af7bd9`, DECISIONS 75). There are no edits to DECISIONS,
OPEN-ITEMS, the ledger, the BOM or the layout. The proposed edits are in `patches/`. Every number comes from
`python3 -I scripts/*.py` (section 8).

## 1. Answer

- **J1 at the release case (c17.5_h10, bay 61 °C, 13.5 A, still air), with the 14 AWG lead: 76.2–98.8 °C (central 87.5) against 105 °C.**
  - That is **+6.2 K at the high bound**, on the board as it stands.
  - S21's 104.6 °C (s47) and 103.1 °C (s52 / s53) were "pad + 4.09 K". The 4.09 K was the 6 mm² curve scaled by I². That figure was not a bound, and it had the wrong sign.
  - The pad (99.0 °C in B3, which models nothing attached) is hotter than the 14 AWG lead's own far-field temperature (71–89 °C). So the lead draws heat out of the clamp. The clamp ends up at or below the B3 pad, not 4 K above it.
- **At the 15 A trip, held steady:** 79.0–107.1 °C, which is **−2.1 K at the high bound**. 15 A is the trip, not an operating point, but it is the reason a fix is taken.
- **c28_h10 at bay 55 °C:** 70.1–92.7 °C (+12.3 K).
- **Chosen fix: (b), board copper.** Add an `ac_n_in` F.Cu strip that mirrors the B.Cu edge strip that feeds J1.2 (the hot pole), and land it on J1.2's F.Cu pad.
  - Release high bound 96.4 °C (**+8.6 K**).
  - 15 A high bound 103.4 °C (**+1.6 K**).
  - No BOM or product-spec change. It is a layout change for the integration session, confirmed by the next B3 solve through the new gated row.
  - Fallback if the bench reads hotter: (d), a 12 AWG cord (95.4 °C / 102.8 °C).
- **Patches:**
  - `patches/b3-gate-j1-row.patch`: the J1 gated row in `b3_ratings_gate.py`, plus `test_b3_terminal.py`.
  - `patches/ledger-1714971.patch`
  - `patches/open-items-S21-J1.patch`
  - All three pass `git apply --check` against the current tree.
- **Still needs the bench:** see section 6. The lead's real cooling and local air, the clamp's mV drop on 14 AWG at torque, and B3's J1.2 pad temperature are model inputs, not measurements.

## 2. Sources and what each one says

Datasheet: Phoenix Contact online-catalog PDF 1714971 "MKDS 5/ 2-9,5", generated 2026-10-16, sha256 `36517cfd4b96d200…`. It is the copy temp-ratings cites, at `worktrees/runs-native21/s47/temp-ratings-dl/conn/phx1714971_b/` and not in git.

| Item | Value | Page |
|---|---|---|
| Nominal current / **nominal cross-section** | 32 A / **4 mm²** | p.1, p.2 |
| Conductor range | rigid 0.2–6 mm², flexible 0.2–4 mm², AWG 24–10 | p.2 |
| **Tightening torque** | 0.5–0.6 Nm | p.3 |
| Contact | Cu alloy, tin-plated | p.3 |
| Housing | PA, insulating material group I, CTI 600, UL 94 V0, **ball-pressure test 125 °C** | p.3 |
| Pin | 0.9 × 0.9 mm, 5 mm solder pin; hole 1.3 mm | p.4 |
| Temperature-rise test | IEC 60947-7-4:2019-01: ambient + rise ≤ upper limiting temperature | p.4 |
| **Operating ambient** | −40 to 105 °C, "depending on the current carrying capacity / derating curve" | p.5 |
| **Derating diagram** | one trace, labelled "1 = 6 mm²": flat at 32 A to 82 °C, then falls to 0 A at about 105 °C. A dashed continuation runs above 32 A (64 A at 20 °C) | p.6 |
| Approvals | cULus E60425: B / C 300 V 30 A, D 600 V 5 A, 30–10 AWG; CSA 13631: B / C 300 V 30 A, 28–10 AWG. No temperature is stated | p.8 |

**What the p.6 curve assumes.**
- It is for a **6 mm² conductor**, one size above the 4 mm² nominal section and 2.9× the 14 AWG area.
- The test basis is the IEC 60947-7-4 rise test (p.4), on an IEC footing.
- Phoenix's quality-test page (phoenixcontact.com/en-us/quality-tests/…/electrical-tests-terminal-blocks, read 2026-10-18 in the browser) says this about its connector derating curves:
  - The curves are made per DIN EN 60512-5-1 / -5-2.
  - The plotted "derating curve" is **0.8 × the measured base current**.
  - It describes this for plug-in blocks. Whether 1714971's curve carries the factor is not stated, so the factor is not credited.
- Digitised (`results/phoenix_1714971_p6.json`): knee 23.6 K at 32 A. The curve read at 13.5 A gives **5.27 K**, more than S21's 4.09 K, because the tail is not I² (power fit n = 1.81). With the 0.8 factor the true rise would be 3.54 K.

**Contact resistance at torque.** No figure is published for 1714971. The Phoenix page states the voltage-drop requirement, which it attributes to IEC 61984 / 60947-7-x:
- The test is at 0.1 × the rated section's current-carrying capacity (4 mm²: 32 A, so 3.2 A).
- The drop must stay ≤ **3.2 mV** per terminal block, before and after the test sequence.
- That limit is **R ≤ 1.0 mΩ**, measured within 10 mm of the clamping point at the specified torque.
- Phoenix claims its blocks are up to 60 % below the limit, giving **0.4 mΩ**.
- The model uses 0.4–1.0 mΩ per pole for contact, bar and pin together.
- Calibration check: reproducing the p.6 knee with 6 mm² leads needs 0.26–0.86 mΩ for test-board ties of 0.01–0.03 W/K (`results/j1_thermal.md`), which is inside the range.
- Not covered: 14 AWG is below the rated section. That is bench item 1.

**The cord.**
- The cord is 14 AWG at 8.286 mΩ/m at 20 °C (`02-protection-timing/f2-coordination/README.md`).
- The inlet-to-J1 leads are "≥ 14 AWG, ≥ 105 °C" (`owner-items/f1cc/F1-RECOMMENDATION.md:179`).
- The leads are modelled as UL 1015-class 105 °C wire: 0.79 mm PVC wall, 3.43 mm OD. 12 AWG is 5.211 mΩ/m, 3.93 mm OD.

**UL / CSA temperature limits**

| Item | Status |
|---|---|
| **UL 1059** (the component's own approval) | Phoenix's page: three blocks side by side at 25 °C ambient, **maximum rise 30 K** at the terminal point. This is the test behind the 30 A group-B rating, not an end-product limit. The standard itself was not read: **secondary source**. |
| **UL 858** end-product temperature test | **Unconfirmed.** The standard is not available here, and Intertek's 2017–2022 revision summary has no temperature table. Usual UL appliance practice judges a Recognized terminal block's housing against its material RTI, under the conditions of acceptability, and judges wire against its insulation rating. The test is run at about a 25 °C room, which is milder than this 61 °C bay basis. Phoenix publishes no RTI, and UL Product iQ (E60425) needs a login. This is a certifier item. |
| **Lead insulation** | 105 °C, the wire's UL (AWM) rating. It sits in the clamp, so it is a UL-basis limit **at the same point** as the terminal's 105 °C. That is why a hotter-rated terminal alone buys nothing (fix c). |
| CSA 13631 | 30 A group B; no temperature stated (p.8). |

The 105 °C limit the gate uses is therefore Phoenix's upper limiting temperature (IEC 60947-7-4 basis, p.4–p.5), and it is also the lead's UL rating.

## 3. Reproducing 104.6 °C (`scripts/j1_buildup.py`)

The S21 estimator is B3's `est` on the J1 pad-copper probe: Q(0.25) + 3|Q(0.25) − Q(0.5)| + (bay − 50 °C), plus 23 K × (13.5/32)².

| Build-up, release case | s47 (S21 text) | **s53, board of record** |
|---|---|---|
| bay air | 61.0 | 61.0 |
| B3 pad rise over model ambient (`pad_max_cell_c` − 50, p0p25) | | 37.19 K |
| mesh allowance (3 × |Δ|) | | 0.84 K |
| **pad estimate** | **100.5** | **99.03** |
| own rise (6 mm² knee scaled I²) | 4.09 K | 4.09 K |
| **J1** | **104.6 (+0.4 K)** | **103.1 (+1.9 K)** |

- The s53 run files are `b3-ratings/runs/c17.5_h10_p0p{25,5}.json`, with the same board sha as the committed `margins.json`. Their J1 probe rows and sha256 are in `results/b3_j1_probe_s53.json`.
- The s47 figure is read from git (`723589bc9`). Its run files are gone, so its rise is not split into parts.

### 3.1 Which pole is hot, and why

- J1's probe takes the maximum over both pads. Its per-pad means split as **98.0 °C on the hot pad against 71.1 °C on the other** (+26.9 K).
- The hot pole is J1.2 (`ac_n_in`). This is inferred: the probe does not name the pad. The task-04 DC fields (`results/neutral_feed.json`, `scripts/neutral_feed.py`) support it:
  - J1.2 is fed by a 5.88 mm-wide 2 oz B.Cu strip along the board edge (x 283.6–289.4, y 3.5–26.5).
  - The neutral path is **2.54 mΩ against 0.29 mΩ** for the line side (8.7×).
  - At 13.5 A the heat near J1.2 is 0.204 W: the strip sheet plus 0.066 W in J1.2's barrel hop, since the F.Cu pad has no copper and all current goes through to B.Cu.
  - The line side carries 0.053 W in total.
- J1's pad does not depend on the tank ceiling: it moves 0.07 K from c16.5 to c17.75. It is set by line current.

## 4. Model with the real conductor (`scripts/j1_thermal.py`)

**Nodes.** One pole has two nodes, the clamp C and the pad P. Both poles carry the line current, so no heat crosses between them.

**The pad.** B3's pad temperature T_P0 is the pad with nothing attached. It is treated as a Thevenin source behind the pad's driving-point resistance R_b.

**Heat paths**
- C to P: the 0.9 × 0.9 mm Cu-alloy pin, in series with R_b.
- C makes I²R_pole.
- C to the lead:
  - The lead is a semi-infinite insulated fin with Joule heat q′(T) = I²r′₂₀(1 + α(T − 20)), solved exactly.
  - H′ = 1 / (ln(do/dc)/(2πk_PVC) + 1/(h·π·do)).
  - θ∞ = q′(T_air)/(H′ − b), where b = I²r′₂₀α.
  - G = √(k_Cu·A·(H′ − b)).
- C to air: the PA housing, to board-heated air.

**Bounds.** Each bound is the min or max of T_C over every corner of the grid below, with no direction assumed. Whether a stiffer pin or board helps depends on whether the clamp is hotter or colder than the pad.

| Input | Low – high (central) | Basis |
|---|---|---|
| R_pole | 0.4–1.0 mΩ (0.6) | IEC 3.2 mV limit; Phoenix "60 % below"; p.6 calibration (section 2) |
| pin k | 120–380 W/m·K | "Cu alloy" (p.3), brass to high-copper alloy |
| pin length | 5–8 mm | p.6 section: 3.4 mm seat, jog and bar |
| R_b, pad driving point | 20–180 K/W | fin estimate of the 5.88 mm × 70 µm edge strip (85–180), down to 20 if inner-layer copper couples under it |
| lead surface h | 8–18 W/m²K | laced or jacketed pair, up to a single lead in free air (natural convection + radiation) |
| lead air | bay + 0–5 K | The wire enters at J1's rear face (y 4.6) and leaves over the y = 0 board edge within 5 mm (DECISIONS 29 placement). Its 6–10 cm decay length is off-board. |
| housing air | bay + 5–15 K | the gate's 15 K board-heated-air rule (`thermal_body.MODULE_AIR_RISE_K`) |
| G_h, housing to air | 0.005–0.010 W/K per pole | PA wall (k 0.25, 1.5–2 mm) to about 7.8 cm² of housing (p.4) at h 10–14 |

### Results, 14 AWG

| Case | T_P0 (B3) | low / central / **high** | margin at high |
|---|---|---|---|
| release c17.5_h10, 13.5 A | 99.03 | 76.2 / 87.5 / **98.8** | **+6.2 K** |
| c28_h10 at bay 55 | 93.01 | 70.1 / 81.4 / **92.7** | +12.3 K |
| 15 A held steady (pad's line-driven share × (15/13.5)²) | 105.3–108.0 | 79.0 / 92.5 / **107.1** | **−2.1 K** |

- **The lead alone at 13.5 A** (far field, its own Joule heat): 71.3–89.3 °C against its 105 °C rating. With 12 AWG: 66.5–78.3 °C.
- **High corner:**
  - Inputs: R_pole 1.0 mΩ, stiff pin, R_b 20, h 8, lead air +5, housing air +15.
  - The clamp makes 0.18 W and still sits 0.2 K below the pad, because the lead draws 0.075 W out of it.
- **Sensitivity about the central point:** R_b +3.3 / −2.2 K, lead h +3.2 / −2.7, R_pole −1.4 / +2.8, G_h, the air rises, then the pin.
- **The physics in one line:** a smaller cord does heat itself more. Here, though, the bay air (61 °C) is 38 K below the B3 pad, so even a 14 AWG lead in that air is a heat sink for J1. The 6 mm² curve's "own rise" was measured with ambient-temperature leads, so it does not carry over.
- **What would break the bound:**
  - The lead routed through hotter air for its first ~10 cm (over the board or the sink). At lead air above about bay + 14 K (h 8), its far field passes the pad.
  - A 14 AWG clamp joint above 1.0 mΩ.
  - A short lead ending on a hot inlet module.
  - All three are bench items.

## 5. Fixes (smallest first) and the choice

| Fix | What | Release high (margin) | 15 A high (margin) |
|---|---|---|---|
| none (s53 as built) | | 98.8 (+6.2) | 107.1 (−2.1) |
| (a) the limit | 105 °C is Phoenix's upper limiting temperature (p.5). The ball-pressure 125 °C (p.3) is a material test, not a use limit. The Phoenix site search for MKDS 5 at 9.5 mm pitch lists MKDS 5 HV, MKDSV 5 (a different wire entry) and MKKDS 5. Their datasheets were not read (the product PDFs return 403), and none is advertised with a higher limit. RTI unpublished. The lead's 105 °C co-binds. | **0 K credit** | 0 K |
| **(b) board copper** | `ac_n_in` **F.Cu** strip mirroring the B.Cu edge strip, x 283.6–289.4, y 3.5–26.5, tied into J1.2's F.Cu pad and stitched to B.Cu. The F.Cu there is empty: no pads, tracks or vias besides J1.2; `l_f` stops at x 279.5. Two equal sheets halve the strip's heat, and J1.2's barrel hop drops to (½)². Local heat falls 58 % (0.252 → 0.106 W at 15 A). The pad's hot-pole excess (26.9 K) is taken to fall by ⅓ to ½, so −9.0 to −13.4 K. The ½ is the cut in sheet heat alone; the 58 % local-heat cut and the better spreading are not credited. **Layout change for the integration session:** D5 L–N spacing to `l_f` (4.1 mm today), edge clearance as the B.Cu strip, B3 re-solve. | **96.4 (+8.6)** | **103.4 (+1.6)** |
| (c) another terminal | A higher-limit, UL-rated block gains nothing while the 105 °C lead sits in its clamp. It also needs a new footprint and UL/CSA verification. With a 125 °C block *and* a 125 °C lead the margin would be +26.2 K. | 0 K | 0 K |
| (d) 12 AWG cord and leads | product spec; Phoenix takes 24–10 AWG (p.2) | 95.4 (+9.6) | 102.8 (+2.2) |
| (b) + (d) | | 89.7 (+15.3) | |

**Decision: (b).**
- It is the smallest change that moves both the release and the 15 A bound into margin.
- It needs no BOM line, no product-spec change and no new UL component.
- It fixes the cause. J1.2's neutral feed carries 8.7× the line side's resistance, and that feed is why the hot pole runs 27 K above the line pole.
- Its effect is measured, not assumed, by the first B3 solve after the layout lands, because the gated row recomputes from the new pad.
- (d) gives a similar margin from a model-only estimate. Its cost lands on the cord set, strain relief and enclosure, and the cord-limited fault-current figures in F1-RECOMMENDATION §2 would need re-running. It stays the fallback if bench item 1 or 2 reads outside the model's range.
- **New margin with (b):**
  - release **+8.6 K** at the high bound (+21.3 K central);
  - 15 A **+1.6 K**;
  - still under the S21 10 K line at release, at the high bound.

## 6. Bench

1. **Clamp joint on the real lead.** Measure the mV drop from screw to J1 pad at 13.5 A DC, on 14 AWG stranded (and solid if allowed), at 0.5 and 0.6 Nm. At least 3 terminals, before and after 50 thermal cycles. Pass: ≤ 13.5 mV (1.0 mΩ). This closes the R_pole range.
2. **Temperature in the enclosure.** Production lead length and routing, release case: 13.5 A, worst bay air (S27), still air. Thermocouples on both screw heads (the terminal point), the J1.2 pad, the J1.1 pad, the lead 50 mm and 150 mm out, and the air 10 mm above J1. Pass: screw ≤ 105 °C at the S27 worst bay, read back to 61 °C. The run also fits R_b and lead h, and gives the per-pad split (section 3.1).
3. **15 A held steady**, same set-up, defeated trip, for the 15 A row.
4. **For the certifier:** the RTI of the 1714971 housing (UL Product iQ E60425) and the UL 858 temperature-test limits for the terminal and the lead.

## 7. Patches and their order

1. **`patches/b3-gate-j1-row.patch`**
   - Adds `TERMINALS` / `terminal_clamp_c()` / `terminal_rows()` to `b3_ratings_gate.py`, and calls them beside the probe and module rows (hot-copper runs only).
   - The row uses the same grid and model as `j1_thermal.py`, and its estimate is the grid maximum, so it bounds the clamp.
   - It refuses a non-1714971 J1, moved nets and missing probes. The row is gated at 105 °C.
   - Adds `test_b3_terminal.py` (8 checks: the s53 probe gives 98.79 °C, matching this study's high bound).
   - Run on the s53 run files: the J1 rows read c17.5 98.8 / c22 92.4 / c28 92.7 °C. Every metric of `margins.json` is unchanged (release worst stays R10 +1.3 K) and the result is PASS. `test_b3_hot_copper.py` passes on the patched gate.
   - The next chain run then carries J1. After fix (b), the B3 re-solve feeds the new pad straight into the row.
2. **`patches/ledger-1714971.patch`** (made by `scripts/make_ledger_patch.py`)
   - J1's release / c28 stresses become 98.79 / 92.68 °C, from the c54 grid maximum. It adds a 15 A stress (107.11 °C) with a `gap` check, re-words the 105 °C rating's basis, replaces the temp-ratings gap with the c54 / bench / certifier gaps, and adds two layout-guidance rows.
   - The entry stays PARTIAL. On a copy of the patched ledger, `gate.py --ledger` passes once this README exists.
   - When `margins.json` carries the J1 row, the release stress can switch to the `b3_row` key form (`{"case": "c17.5_h10", "item": "J1: 1714971 clamp"}`).
3. **`patches/open-items-S21-J1.patch`**: the three J1 clauses of S21, re-stated.
4. Not written here:
   - the DECISIONS entry, which goes to the integration session that lands fix (b) and the gate row;
   - the split-bleed (R71–R75) gated row that S21 also asks for, which is outside this lane.

## 8. Reproduce

```
cd validation-results/11-candidates/c54-j1-thermal
python3 -I scripts/digitize_p6.py [PDF]     # needs the cited PDF + pdftoppm, PIL, numpy -> results/phoenix_1714971_p6.json
python3 -I scripts/j1_buildup.py            # B3 run files if present, else results/b3_j1_probe_s53.json
python3 -I scripts/neutral_feed.py          # task-04 json (+ npz if present)
python3 -I scripts/j1_thermal.py            # stdlib -> results/j1_thermal.{json,md}
python3 -I scripts/make_ledger_patch.py     # -> patches/ledger-1714971.patch
python3 -I scripts/make_open_items_patch.py # -> patches/open-items-S21-J1.patch
```
