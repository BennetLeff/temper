# Native-21 blocked parts: in-stock alternates

**Scope.** This covers the 120 V power stage, native-21 (`zapote/power-stage-120v`, branch `codex/power-stage-integration`, stage 13), as of 2026-10-09.

**How it was done.**
- The repo was read only. Nothing was committed, carted, quoted or logged in.
- Datasheet PDFs were saved only in the scratchpad: `dl/`, `dl-c5c6/`, `dl-t2/`, `dl-pmeg/`.
- Simulation scripts are in `alternates/emi-sens/` and `t2sim/`.

**Quantities.** The lot is 5 boards plus 2 spares per board, so each line needs 5 × (per-board quantity + 2):

| Part | Per board | Lot quantity |
| --- | --- | --- |
| C5/C6 | 2 | 20 |
| T2/T3 | 2 | 20 |
| C1/C2 | 2 | 20 |
| D3 | 1 | 15 |
| B32654A1104K000 | 5 | 35 |
| KLDR025.TXP | 1 | 15 |
| 01250003H clip | 2 | 20 |

**Sites that could not be read:**
- **Mouser:** WebFetch timed out every time, and curl got "Access Denied" plus a captcha page. That is bot detection, which I did not bypass.
- **Newark:** search timed out or returned 403. Newark figures here come through Findchips.
- **Arrow:** timed out.
- **TTI and Octopart:** 403.
- **TDK product.tdk.com and the TDK X2 PDF:** 403.
- **Littelfuse and coilcraft.com:** 403.
- **LCSC:** search rendered no results.
- **Claude-in-Chrome:** extension not connected.

So stock below is **Digi-Key-first**. Digi-Key product pages sometimes render the main product's stock beside the substitutes block. Wherever that made the attribution ambiguous, the figure is taken from Digi-Key's keyword listing and flagged.

**Correction to the brief.** T2/T3's ratio is **1.2:1 step-down** (N1+N2 : N3+N4, Würth rev 001.002 p.1, and `bias_sizing.py` `primary_to_secondary_ratio: 1.2`). It is not 1:1.2.

**Conflict in the recorded basis.** `bias_sizing.py` records "reinforced 500 Vrms". DECISIONS.md (2026-10-06, revised, item 2) and native-21/ECO.md call T2/T3 **HOT↔HOT functional** barriers. Candidates were judged against both readings.

---

## 1. C5/C6, TDK B32656G0275J000 (DC-link bulk film)

**Verdict: none.** No stocked part is functionally equivalent on the frozen footprint. Every 4-pin, 37.5 × 20.3 mm part at 2.2 to 3.3 µF is a TDK B32656G code, and none of them is stocked. The stocked parts that fit the same pads are TDK B32676G DC-link capacitors, which are 9 to 10 µF each. Fitting them changes the selection basis, so they **need an ECO** (an electrical basis change; the copper stays as is).

The least-risk route is to obtain the approved part, or its same-footprint sister B32656G0275M000, from TDK as samples. If the build cannot wait, fit B32676G1905K000 (9 µF / 750 V, 547 in stock) on the existing pads under a recorded deviation, and re-run the bus analyses listed under "Least-risk path" below.

### Recorded basis (requirements)

| Attribute | Recorded value | Source |
| --- | --- | --- |
| Capacitance | 2.7 µF ±5 % each; 5.4 µF bulk, 5.8 µF total with C38–C41 | parts.ato `BusFilm2u7`; BUS-CAP-SCREEN.md; DC-LINK-CLAMP.md |
| Rated voltage (approved) | 1000 VDC | DECISIONS.md "Prototype source revision, 2026-09-25" |
| Voltage actually needed | Bus ≤ 280 V (static OVP corner ≈ 286 V). Transient design target ≤ 520 V at returned tank current. The TVS clamps at 410 V max (282 A, 6.4/69 µs, before lead inductance). | DC-LINK-CLAMP.md |
| Dielectric | Polypropylene (MKP) | parts.ato |
| Ripple current | 22.8 A rms at 85 °C / 100 kHz | parts.ato; RADIAL-FOOTPRINTS.md; TDK B3265* p.29 |
| ESL | 19.2 nH, the resonance-equivalent value from TDK's typical model. Sweep points 11.364 / 19.2 / 23.447 nH. | round17/delegation/out-D7/README.md; FINDINGS M4 |
| Pins and footprint | 4 pins, Ø1.2 mm leads. Pads 1 (0,0), 2 (0,20.3), 3 (37.5,0), 4 (37.5,20.3); Ø2.8 mm pads, Ø1.8 mm drill. Pads 1/2 form one electrode, 3/4 the other. | temper.pretty/TDK_B32656G0275J000_4Pin_P37.50_P20.30_ReviewOnly; RADIAL-FOOTPRINTS.md |
| Body envelope | ≤ 42 × 33 mm plan (courtyard x −2.5…40, y −6.6…26.9 from pad 1); seated height ≤ 48 mm. The enclosure limit is about 48.4 mm above the board top (L12: ≤ 50 mm above the board bottom; 1.6 mm board). | footprint; RELAYOUT-REQUIREMENTS L12 |
| FEM boundary | The FEM reaches the PCB pads. Port P5 runs C6.1 → C6.3. The capacitor body and leads enter the deck as scalar C and ESL. | round17/README.md "Bulk current mode"; out-D7 |

### Candidate search: what exists on this footprint

The search used the TDK B3265*A/G/J/T datasheet (June 2026) and the TDK B3267*D/G/J/T DC-link datasheet (June 2026). It also covered KEMET R76 (F3034), the KEMET C4AQ part sheet, Vishay MKP1848S DC-Link, CDE 944U and 947D, and WIMA DC-LINK MKP 4 (03.26).

- **TDK B32656G** (p.3–4, drawing B1: 4-pin, e = 37.5, d1 = 1.2). These are the only parts at 2.2–3.3 µF with a 4-pin 37.5 × 20.3 grid. P1 = 20.3 applies only to the 30 × 45 and 33 × 48 bodies.
- **TDK B32676G** (DC link, p.9–10). Same drawing, e = 37.5, d1 = 1.2. Every P1 = 20.3 code is ≥ 7.5 µF.
- **KEMET C4AQ / C4AE.** 37.5 mm codes are ≥ 12–15 µF, and their 4-lead row spacing is S1 = 10.2 mm, not 20.3. The small-µF C4AQ parts are 27.5 mm pitch.
- **Vishay MKP1848S.** The 37.5 mm 4-pin codes have P2 = 10.2 mm only and are ≥ 7 µF (datasheet table). There are no 20.3 mm 37.5-pitch codes.
- **WIMA DC-LINK MKP 4.** At 1000 VDC and 37.5 mm the smallest part is 5 µF. The 4-pin row spacing b is 10, 12.5 or 20 mm (p.111).
- **CDE 944U / 947D.** 33–500 µF parts with stud terminals. Not applicable.
- **KEMET R76.** 2-pin only. R76PW4270…: 2.7 µF / 630 V, 20 × 40 × 41.5 mm, 12.3 A rms, 20 nH ESL, p.16.

| Attribute | **Basis B32656G0275J000** | B32656G0275M000 | B32656G0225J000 | B32656G8275J000 / G8305J000 / G8335J000 | **B32676G1905K000** | B32676G1106K000 | B32676G8106K000 | B32656A0225J000 (2-pin) | R76PW4270SE30J (2-pin) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Capacitance | 2.7 µF ±5 % | 2.7 µF, "M" (±20 %; the + legend on p.29 decodes only J/K) | 2.2 µF ±5 % | 2.7 / 3.0 / 3.3 µF | 9 µF ±10 % | 10 µF ±10 % | 10 µF ±10 % | 2.2 µF ±5 % | 2.7 µF ±5 % |
| VR | 1000 VDC | 1000 VDC | 1000 VDC | 850 VDC | 750 VDC at 85 °C (Vop 900 V at 70 °C) | 750 VDC | 875 VDC | 1000 VDC | 630 VDC |
| Pins / grid | 4 / 37.5 × 20.3 | 4 / 37.5 × 20.3 | 4 / 37.5 × 20.3 | 4 / 37.5 × 20.3 | 4 / 37.5 × 20.3 | 4 / 37.5 × 20.3 | 4 / 37.5 × 20.3 | **2 / 37.5** | **2 / 37.5** |
| Lead Ø | 1.2 | 1.2 | 1.2 | 1.2 | 1.2 | 1.2 | 1.2 | 1.0 | 1.0 |
| Body w × h × l | 33 × 48 × 42 | 30 × 45 × 42 | 30 × 45 × 42 | 30×45×42 / 30×45×42 / 33×48×42 | 30 × 45 × 42 | 30 × 45 × 42 | 33 × 48 × 42 | 30 × 45 × 42, centred on the lead row | 20 × 40 × 41.5 |
| Fits courtyard and height? | yes (basis) | yes | yes | yes | yes | yes | yes | **no**: centred on pads 1/3 (or 2/4), the body overhangs the courtyard by ≈ 8.4 mm | **no**: same issue (≈ 3.4 mm overhang) |
| Irms | 22.8 A (85 °C/100 kHz) | 21.0 A | 20.0 A | 21.6 / 22.7 / 23.0 A | 19.5 A (**70 °C/10 kHz**, not comparable) | 20.5 A (70 °C/10 kHz) | 22.5 A (70 °C/10 kHz) | 16.0 A (85 °C/100 kHz) | 12.3 A (85 °C/100 kHz) |
| ESR typ | 2.6 mΩ (100 kHz) | 2.8 mΩ | 2.9 mΩ | 2.8 / 2.6 / 2.5 mΩ | 5.1 mΩ (10 kHz, 70 °C) | 4.7 mΩ | 4.3 mΩ | 4.4 mΩ | 7.1 mΩ max |
| ESL | 19.2 nH (TDK model, D-7) | not published (in TDK's licensed library) | not published | not published | 12 nH typ | 13 nH typ | 14 nH typ | not published | 20 nH (2 × 4 mm leads) |
| dV/dt | 400 V/µs (37.5 mm, 1000 V/500 VAC, p.36) | 400 V/µs | 400 V/µs | 340 V/µs | 85 V/µs (p.14) | 85 V/µs | 100 V/µs | 400 V/µs | 450 V/µs |
| Datasheet page | B3265* p.29 | p.29 | p.29 | p.28 | B3267* p.10 | p.10 | p.10 | p.29 | R76 p.16 |
| **Stock** | Digi-Key: no listing. Mouser: non-stocked, quote only (Codex CSV). TDK MOQ 360. | Digi-Key: no listing | Digi-Key: no listing | Digi-Key: no listing (only B32656G8225J000 is listed: 0 stock, 27 wk; its P1 = 10.2, so it does **not** fit) | **547**, $10.53/1, 27 wk factory | 18,789 as "B32676G1106K Z 1" (non-catalogue suffix, see note) | **7** | **120**, $17.91/1, 27 wk | 0 (Digi-Key; MOQ 378) |

**Note on B32676G1106K Z 1:** Digi-Key's MPN does not follow the catalogue code (`…K000`) in TDK's ordering-code composition (B3267* p.10). Treat it as a special variant. Confirm it with TDK before relying on it. B32676G1905K000 is a catalogue code.

### Stock and lead time (read 2026-10-09)

| MPN | Distributor | Stock | Price | Lead time | URL | Read UTC |
| --- | --- | --- | --- | --- | --- | --- |
| B32656G0275J000 | Digi-Key | no result | – | – | https://www.digikey.com/en/products/result?keywords=B32656G0275J000 | ≈17:34Z |
| B32656G0275M000 | Digi-Key | no result | – | – | https://www.digikey.com/en/products/result?keywords=B32656G0275M000 | ≈17:39Z |
| B32656G0225J000 | Digi-Key | no result | – | – | https://www.digikey.com/en/products/result?keywords=B32656G0225J000 | ≈17:39Z |
| B32656G8275J000, B32656G8335J000 | Digi-Key | no result | – | – | …keywords=B32656G8275J000 / …G8335J000 | ≈17:39Z |
| All B32656G* codes listed | Digi-Key, film-capacitor filter, keyword B32656G | 4 codes listed, all 0 stock: G3156K, G2224J, G8225J, G5505K | MOQ-only pricing | 27 wk (G8225J) | https://www.digikey.com/en/products/filter/film-capacitors/62?keywords=B32656G | ≈17:33Z |
| B32676G1905K000 | Digi-Key (495-3024-ND) | 547 | $10.53 (1), $8.015 (10) | 27 wk factory | https://www.digikey.com/en/products/result?keywords=B32676G1905K000 | 17:39:18Z |
| B32676G1106K Z 1 | Digi-Key (495-B32676G1106KZ1-ND) | 18,789 | $11.39 (1), $8.715 (10) | 18 wk factory | https://www.digikey.com/en/products/result?keywords=B32676G1106K000 | 17:39:18Z |
| B32676G8106K000 | Digi-Key | 7 | $17.09 (1) | 27 wk | https://www.digikey.com/en/products/result?keywords=B32676G8106K000 | 17:39:18Z |
| B32656A0225J000 | Digi-Key (495-B32656A0225J000-ND) | 120 | $17.91 (1), $14.11 (10) | 27 wk | https://www.digikey.com/en/products/result?keywords=B32656A0225J000 | 17:35:20Z |
| R76PW4270SE30J / R76PW42704030J | Digi-Key | 0 / 0 | MOQ 378 / 504 | "check lead time" | https://www.digikey.com/en/products/filter/film-capacitors/62?keywords=R76PW4270 | ≈17:40Z |
| B32656G* | Avnet, via Findchips | 0 (G2224J, G5505K, G3156K, G8225J) | – | – | https://www.findchips.com/search/B32656G | ≈17:37Z |

**Blocked sources:** Mouser timed out on WebFetch twice, and curl returned a bot-challenge page. Arrow and Newark timed out. TTI and Octopart returned HTTP 403. TDK's product.tdk.com returned 403, and the LCSC search page rendered no results. Findchips prefix matching is unreliable: it returned "no results" for B32656A0225, which Digi-Key stocks. Its zero-stock rows are therefore only indicative. The Claude-in-Chrome extension was not connected.

**Manufacturer datasheets:**
- TDK B3265*A/G/J/T, June 2026: https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/MKP_B32651_658.pdf. Pages 3–4 (drawings), 28–29 (37.5 mm ordering tables), 36 (dV/dt). Read 17:31:59Z.
- TDK B3267*D/G/J/T, June 2026: https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/MKP_B32674_678.pdf. Pages 3–4, 9–10, 14. Read 17:31:59Z.
- KEMET R76: https://content.kemet.com/datasheets/KEM_F3034_R76.pdf. Pages 13, 15, 16, 18. Read 17:35:52Z.
- Vishay MKP1848S: https://www.vishay.com/docs/26010/mkp1848sdclink.pdf. Ordering-code and dimension table. Read 17:35:52Z.
- CDE 944U and 947D: https://www.cde.com/resources/catalogs/944U.pdf and https://www.cde.com/resources/catalogs/947D.pdf. Read 17:35:52Z.
- WIMA DC-LINK MKP 4, 03.26: https://www.wima.de/wp-content/uploads/media/e_WIMA_DC_Link_MKP_4.pdf. Pages 110–111. Read 17:36:32Z.
- KEMET C4AQLBW5500M3JK part sheet: https://www.farnell.com/datasheets/3185244.pdf. S1 = 10.2 mm. Read 17:36:32Z.

PDFs were saved only to the scratchpad (`scratchpad/dl-c5c6/`), not to the repo.

### Electrical consequence of each footprint-compatible option (BUS-CAP-SCREEN method)

These figures use 140 V rms crest, 33 kHz and 60 Hz, and include the 0.4 µF of local capacitance.

| Bank | Total C | 33 kHz V/A | Energy at crest | 60 Hz C·dV/dt peak | Comment |
| --- | ---: | ---: | ---: | ---: | --- |
| Basis, 2 × 2.7 µF | 5.8 µF | 0.832 | 0.114 J | 0.433 A | – |
| 2 × B32656G0275M at −20 % | 4.72 µF | 1.022 | 0.093 J | 0.352 A | Bus ripple +23 % worst case. Minor input-current effect. |
| 2 × B32656G0225J | 4.8 µF | 1.005 | 0.094 J | 0.358 A | Bus ripple +21 %. Less energy absorbed per joule of returned tank energy, so the TVS/OVP margin shrinks. |
| 2 × B32656G8335 | 7.0 µF | 0.689 | 0.137 J | 0.522 A | Benign. |
| 2 × B32676G1905K | 18.4 µF | 0.262 | 0.361 J | 1.373 A | **Basis change.** 3.2× the bus capacitance. |
| 2 × B32676G1106K | 20.4 µF | 0.236 | 0.400 J | 1.523 A | **Basis change.** |

The 9–10 µF banks make returned tank energy less of a threat to the TVS and MOSFETs: the same energy gives a lower overshoot. They break or must re-validate the following:

- (a) the D-32 / LINE_ZC bus-valley lag and burst-scheduling estimates, which assume about 5.8 µF;
- (b) input current shape, PF and harmonics, since an unfiltered bus with a larger C has peakier conduction; the line-frequency C·dV/dt term rises from 0.43 A to about 1.4–1.5 A;
- (c) plug-in inrush through F1 (KLDR025) and BR1 (GBJ2510 IFSM);
- (d) the bleed time of the R220k bus bleed, since τ scales with C;
- (e) the EMI deck's CBULK (task 07);
- (f) ripple ratings. B32676 currents are rated at 70 °C / 10 kHz, not 85 °C / 100 kHz, and the dV/dt rating is 85 V/µs, versus 400 V/µs for the basis. The edge current slew reaching the bulk branch (round17 "bulk current mode": 3.8–8.9 A/ns) must be checked against B32676 pulse ratings.

### FEM round 17 and F6: what must be redone

- **Any 4-pin part on the same pads** (all B32656G and B32676G codes above): **no FEM re-extraction.** The board copper, pads and port P5 (C6.1 → C6.3) are unchanged, and the FEM stops at the pads.
- **Deck and F6 re-runs are still needed.** The bulk branch in `d2/leg_matrix5.cir` uses C5BULK/C6BULK and an ESL. A different C or ESL changes how the edge current divides between the bulk and the C38/C39 local branches.
  - The B32676G ESLs (12–14 nH typ) lie inside D-7's 11.364–23.447 nH sweep. For ESL alone, the existing sensitivity points bracket them.
  - However, round17/README notes that the deck's LBULK (21.5 nH, copper only) and the shared LESL do not yet carry a separate bulk ESL. A capacitance change from 2.7 to 9–10 µF has not been run.
  - **Verdict for B32676G: re-run F6 / leg grids with the new C (cheap, no FEM). Same for B32656G codes other than 2.7 µF.**
  - B32656G0275M000 has the same C and construction and a smaller body. Its ESL can be taken from the same licensed TDK library with `out-D7/model_analysis.py` before use; the archive is already licensed by the owner. Re-running D-7 for that subcircuit is enough; no FEM is needed.
- **2-pin parts** (B32656A0225J000, R76): **FEM/F6 must be redone, and an ECO is needed.**
  - The body overhangs the courtyard by about 3.4–8.4 mm toward D3 and the zero-cross string.
  - One pad of each electrode pair goes unused, so the current path into P5 changes.
  - The 2-pin ESL is unpublished (R76: 20 nH with leads).
  - The B32656A0225J000 ripple rating is 16 A against 22.8 A.

### Verdict

**None** is a drop-in or a drop-in with an audit edit. The only same-footprint, same-C parts are B32656G0275J000 and B32656G0275M000, and neither is stocked at any distributor I could read.

**Least-risk path, in order:**
1. **Ask TDK, through a distributor FAE, for samples of B32656G0275J000.** Ask also for **B32656G0275M000**: same pads and pins, 30 × 45 × 42 mm (smaller), 21.0 A, ±20 %. With M, the only bases that change are the tolerance (worst case 4.72 µF total) and an ESL check via the D-7 script. That would be a "drop-in with audit edit" once the M tolerance is accepted. **Stock not found.**
2. **If parts are needed now: B32676G1905K000 × 2** (547 at Digi-Key, $10.53).
   - It drops mechanically onto the frozen pads: 4-pin 37.5 × 20.3, Ø1.2 leads, 30 × 45 × 42 mm, inside the courtyard and the 48.4 mm height limit.
   - Electrically it is a basis change, and the DECISIONS entry should record it as one.
   - Before power-up, re-run BUS-CAP-SCREEN, the F6 / leg decks with C = 9 µF and ESL = 12 nH, the inrush and fuse I²t check, and the LINE_ZC / D-32 bus-valley assumption. Also check B32676 pulse ratings (85 V/µs) against the round-17 bulk current slew.
   - Avoid the "B32676G1106K Z 1" code until TDK confirms it.

**Edits if option 2 is adopted** (deviation, not a drop-in):

`elec/src/parts.ato`, component `BusFilm2u7` (rename optional):
```diff
-    """TDK 2.7 uF +/-5%, 1000 VDC, four-pin radial polypropylene.
+    """TDK B32676G1905K000 9 uF +/-10%, 750 VDC (85 C), four-pin radial MKP DC link,
+    B3267* datasheet 6/26 p.10: 30 x 45 x 42 mm, P1 20.3, e 37.5, d1 1.2, ESL 12 nH typ.
+    PROTOTYPE DEVIATION from B32656G0275J000 (not stocked 2026-10-09); bus = 18.4 uF.
     Drawing B1: pairs at each x end share an electrode; numbers are local
-    pad assignments. 22.8 A RMS at 85 C / 100 kHz, not an all-frequency rating."""
+    pad assignments. 19.5 A RMS at 70 C / 10 kHz (not comparable to the 100 kHz basis)."""
     designator_prefix = "C"
-    mpn = "B32656G0275J000"
+    mpn = "B32676G1905K000"
     manufacturer = "TDK"
     footprint = "temper:TDK_B32656G0275J000_4Pin_P37.50_P20.30_ReviewOnly"
```
In `audit.rs`, lines 278–279:
```diff
-    ("c_bus1", "B32656G0275J000"),
-    ("c_bus2", "B32656G0275J000"),
+    ("c_bus1", "B32676G1905K000"),
+    ("c_bus2", "B32676G1905K000"),
```
For option 1 with the M code, apply the same two audit lines with `B32656G0275M000`, and change the parts.ato docstring to "2.7 uF ±20 %, 30 × 45 × 42 mm, 21.0 A". The footprint is unchanged in both cases; its name merely keeps the old MPN.

---

## 2. T2/T3: Würth 750320775 (SN6507 push-pull transformer, WE-PPTI EP7 HV)

### Recorded basis

Sources: `native-21/bias_sizing.py` (`transformer` block), `native-21/ECO.md` (Supply and gate circuit; manufacturer sources), `DECISIONS.md` (2026-10-06 entry, "F6 bias architecture REVISED"), `libraries/temper.pretty/WE_750320775_EP7HV_ReviewOnly.kicad_mod`, `elec/src/f6_bias.ato:280-288`, and `out-D33/transformer_check.py` with its `results.json`.

| Requirement | Recorded value | 750320775, datasheet rev 001.002 (2026-07-29) |
|---|---|---|
| Turns ratio | `primary_to_secondary_ratio: 1.2`, giving about 20 V per half-secondary from 24 V | **1.2:1 (N1+N2 : N3+N4)**, p.1. This is a step-down ratio. **The brief's "1:1.2 primary to secondary" is inverted**: a 1:1.2 part would produce about 28.8 V. |
| V·t, half primary | ≥ (24×1.025+0.1)/(2×500 kHz) = **24.7 V·µs** at the 500 kHz minimum clock | 60 V·µs (N1, bipolar), p.1 |
| Full-primary L | 300 µH min (model value) | 300 µH min, 10 kHz, p.1 |
| DCR | 0.41 Ω primary / 0.29 Ω secondary max | Same, p.1 |
| Cww | 3 pF typ. This is "typical, not a maximum". The F6 rail campaign uses `--cww-p 3` and says "sweep separately". | 3 pF typ, p.1 |
| Leakage | 9 µH typ (k = 0.984885 in the model) | 9 µH typ, p.1 |
| Insulation | `reinforced_working_Vrms: 500`, ≤ 700 kHz | IEC/EN 61558-2-16: reinforced at 500 Vrms / 700 Vpk at ≤ 700 kHz, OVC II, PD2. This is "designed to comply"; there is no agency file. Hipot is 4000 Vac, p.1–2. |
| Insulation actually needed (DECISIONS 2026-10-06 revised, item 2; ECO.md) | T2/T3 are **HOT↔HOT functional barriers** (SW_A/SW_B to LEG_RET). They create no path to PS1/PE. | Under that reading, the need is functional isolation for 0–280 V DC switch-node swing with ≤ 520 V overshoot, continuously. |
| Driver limits | SN6507 0.5 A recommended switch current; 30.1 kΩ current limit; clock 500–700 kHz | The existing model peaks at 0.43–0.47 A (`results.json`) |
| Rectifier | 2 × PMEG10030ELPX (**100 V**) per transformer | The existing model peaks at 63–89 V reverse |
| Downstream | TPS7A4700 17 V span: needs > 17 V plus dropout, and ≤ 36 V in | The existing model gives 17.28 V minimum at 23.3 V / 700 kHz, which is already tight |
| Footprint | 8 SMD pads. Two columns at **11.06 mm** c-c, **2.50 mm** pitch, pads 2.50 × 1.29. Left column 4,3,2,1 top to bottom, right column 5,6,7,8. Pins 1/4 are primary ends with 2+3 the CT; pins 5/8 are secondary ends with 6+7 the CT. Body 13.40 × 11.46 × 11.94 max. | p.1 land pattern |

### Shortage evidence (re-read)

- Digi-Key 750320775, read 2026-10-09T17:39Z: <https://www.digikey.com/en/products/result?keywords=750320775>. **0 in stock**, **250 expected 2027-03-17**, 16-week factory lead. Digi-Key labels the part "NXF6501".
- Codex CSV row 4: Mouser 0, 750 expected 2027-04-01. Würth sample availability needs a login.

### Search coverage

These sources were read:
- the Würth WE-PPTI catalogue page (<https://www.we-online.com/en/components/products/WE-PPTI>, 17:33Z);
- Digi-Key's WE-PPTI highlight page, with its SN6501/SN6505B/SN6507 groupings (<https://www.digikey.com/en/product-highlight/w/wurth-electronics/we-ppti-push-pull-transformers>, 17:33Z);
- TI SN6507 SLLSFM0A Table 9-3 (p.29–30, <https://www.ti.com/lit/ds/symlink/sn6507.pdf>, 17:32Z);
- the Coilcraft TX2 datasheet, Doc 1790-1, revised 09/04/26 (<https://www.coilcraft.com/getmedia/612282c6-46b3-4f9d-a85e-d6d5b2df94fa/tx2.pdf>, 17:38Z). **coilcraft.com product pages return HTTP 403 to fetch tools.**

I also downloaded Würth datasheets directly (`https://www.we-online.com/components/products/datasheet/<code>.pdf`, 17:33–17:37Z) for 750319690–697, 750319948/949, 750320324/325, 750313626/638/734/769, 750315232–250, 750316028–033, 750319920–935 and 750320760–790.

**No other Würth EP7 HV order code exists in those ranges.** 750320775 is the only EP7 HV part found, and the catalogue shows "NEW EP7 HV" as a size with no second order code visible.

### Candidates

| Attribute (requirement) | **750315240** (Würth WE-PPTI 1512) | 750316033 (Würth 1512) | 750319697 (Würth 1308) | TX2-ZE2429-AED / -2430-AED (Coilcraft) | TI Table 9-3 24 V parts (750319696, TX1-ZB1459-BE, SM91207L-E, PAG6356.086NLT) |
|---|---|---|---|---|---|
| Ratio (1.2:1 step-down) | **1:1.1** (step-up), p.1 | 1.3:1, p.1 | 1:1.07, p.1 | 1:0.71 / 1:1.43 | 1:0.71–0.75 (Table 9-3 p.29) |
| V·t ≥ 24.7 V·µs | **46** ✔ | 40 ✔ | 36 ✔ | 30 ✔ | 15–25 (750319696 15 ✘; others 25–30) |
| L min (300 µH) | 440 µH (100 kHz) ✔ | 370 µH ✔ | 500 µH ✔ | 196 µH ✘ (lower) | — |
| DCR (≤ 0.41 / 0.29) | 0.15 / 0.15 ✔ | 0.16 / 0.11 ✔ | 0.28 / 0.29 ✔ | 0.12/0.11, 0.17/0.24 ✔ | — |
| Cww (3 pF typ) | **18 pF max** (6× higher) ✘ | not stated | **25 pF typ** ✘ | not stated | — |
| Insulation | **Reinforced**: IEC62368-1 ES3 > 30 kHz at 550 Vrms / 1600 Vpk; IEC60950 550 Vrms; IEC61010-1 1000 Vrms; IEC60664-1 490 Vrms / 700 Vpk; 11 mm creepage/clearance; **UL/cUL E205930 certified**; 5000 Vrms hipot (p.1–2) | Same reinforced family and agency file (p.2) | Functional only: 2500 Vac test, no insulation-class statement | 5000 Vrms hipot, 10 mm creepage; "Functional, Basic, or Reinforced depending on application… contact Coilcraft" | 2.5–3.75 kVrms; no reinforced statement |
| Output at 23.3 V, 500–700 kHz (> ~17.3 V needed) | 22.4–23.8 V ✔ (sim below) | 23.3/1.3 ≈ 17.9 V before diode/DCR drop; below the current part's 17.28 V margin ✘ | 23.0–23.2 V ✔ | 0.71: ≈ 16.5 V ✘; 1.43: ≈ 33–35 V, near TPS7A47's 36 V ✘ | ≈ 17 V or less ✘ |
| Rectifier reverse (PMEG10030 100 V) | **117 V** ✘ (sim) | — | **113–117 V** ✘ (sim) | — | — |
| SN6507 switch peak (0.5 A recommended) | **0.58–0.93 A** ✘ (sim) | — | **2.4–2.6 A** ✘ (sim) | — | — |
| Pins / footprint | 6 pins, **not drop-in** | 6 pins, not drop-in | 6 pins, not drop-in | 8 pins with the same 1/4, 2+3, 5/8, 6+7 scheme, but **14.1 mm columns, 2.00 mm pitch**, 17.3 × 10.3 × 7.0 mm body: not drop-in | not drop-in |
| Digi-Key stock (read 17:39Z) | **90**, 52-week factory lead, $3.70 @10 (<https://www.digikey.com/en/products/result?keywords=750315240>) | 227, 15-week lead, $4.79 @10 (<https://www.digikey.com/en/products/result?keywords=750316033>) | 781, 52-week lead, $3.33 @10 (<https://www.digikey.com/en/products/result?keywords=750319697>) | Digi-Key: "no results" (<https://www.digikey.com/en/products/result?keywords=TX2-ZE2429-AED>); Coilcraft direct blocked (403) | 750319696: 1,002 (highlight page) |

Rejected without full tabulation:
- **750313626/638/734/769** are reinforced 1209 parts, but they are 5 V/3.3 V SN6501 types at **10 V·µs** (p.1 of each), failing the 24.7 V·µs requirement.
- **750320324/325** are 2.4:1 and 5.33:1 parts at 2500 Vac.
- **Murata 78253/55JVC**: Digi-Key describes it as a "MAX253" 360 µH part, a 5 V-class SN6501/MAX253 transformer. I did not retrieve its ratings because the Murata PDF returned HTTP 500.
- **Coilcraft NA5743-AL**: Digi-Key "no results".
- **Bourns SM91207L-E / SM91208L-E** (Table 9-3) are 2.5 kVrms parts with ratio 0.73 or 1.2 (1:N). The 1:1.2 part is a 12 V→15 V design, a step-up that gives about 28.8 V at 24 V.

### Simulation evidence (scratch, not committed)

`scratchpad/t2sim/xfmr_check.py` re-implements `out-D33/transformer_check.py` exactly: same deck, ×1.4 DCR, minimum L, 1 Ω RON, snubbers, 80 µH/1 Ω filter, 85 mA clipped load, and the Nexperia PMEG10030ELP model (SHA-256 `dada2dcd…008c3`, matching the repo pin, downloaded 17:39:55Z). Run with ngspice under `python3 -I xfmr_check.py`.

**Baseline check:** the 750320775 rows reproduce the repository's `transformer-check/results.json` to every printed digit: 17.74599 V, 63.28808 V, 0.4602796 A at 23.3 V / 500 kHz. Results are in `results-a.json` and `results-b.json`.

| Part (k) | Vin / f | out min | rectifier reverse | switch peak | input W |
|---|---|---|---|---|---|
| 750320775 (0.9849) | 23.3 V / 700 kHz | 17.28 V | 86.3 V | 0.43 A | 3.45 |
| 750320775 | 24.7 V / 700 kHz | 18.29 V | 89.5 V | 0.43 A | 3.66 |
| 750315240 (0.97–0.995) | 23.3 V / 500–700 kHz | 22.4–23.8 V | **117 V** | **0.69–0.91 A** | 4.0–4.7 |
| 750315240 | 24.7 V / 500–700 kHz | 23.5–25.1 V | **117 V** | **0.58–0.93 A** | 4.6–5.1 |
| 750319697 (0.9995) | 23.3–24.7 V | 23.0–24.7 V | **113–117 V** | **2.4–2.6 A** | 4.4–4.8 |

The 1:1.1 and 1:1.07 parts push the PMEG10030 past its 100 V rating; the model sits in breakdown at about 117 V. They also push the SN6507 above its 0.5 A recommended switch current. Each would raise HS-LDO dissipation from about (20−17)×82 mA ≈ 0.25 W to about (24−17)×82 mA ≈ 0.6 W per channel at 80 kHz.

### Verdict: **none (no drop-in)**. The least-risk path is to keep 750320775 and source it.

1. **No stocked part matches the 1.2:1 ratio, V·t, reinforced rating and the EP7 HV 8-pad pattern.** Every candidate fails the land pattern. Every stocked candidate also fails at least one electrical item:
   - the ratio gives too much or too little secondary voltage;
   - the 100 V rectifier is over-stressed;
   - SN6507 current exceeds 0.5 A;
   - Cww is 6–8× the 3 pF basis.
2. **Least-risk option:** keep 750320775 and request Würth Midcom samples or a factory allocation. Need **20 pieces** for the 5-board lot (5 × (2 + 2 spares)). The order package used 2 spares per MPN, giving 12. Digi-Key 250 expected 2027-03-17; Mouser 750 expected 2027-04-01. Würth Midcom normally sample-ships new WE-PPTI codes; the procurement CSV notes that needs a login, so this is an owner action. Bench lots of 2 boards need 4 pieces.
3. **Best fallback if samples fail: 750315240.** It is reinforced, agency-certified (UL E205930), 46 V·µs and 90 in stock, but it needs an ECO bundle:
   - **Footprint ECO.** Replace `WE_750320775_EP7HV_ReviewOnly` with a 6-pad pattern per the 750315240 p.1 land pattern: two columns **13.74 mm** c-c, **3.81 mm** pitch, pads **1.9 × 1.4 mm**. Left column top to bottom 1,2,3; right column 6,5,4. Body **15.41 (lead span) × 12.32 × 11.89 mm max**. Courtyard grows from 14.06 × 11.96 mm to about 15.9 × 12.8 mm.
   - **Pin map (`f6_bias.ato:280-288`):**
     - sw1 → 1, raw24 → 2 (CT), sw2 → 3;
     - sa → 6, n → 5 (CT), sb → 4;
     - `BiasTransformer` loses p7/p8, and its pins become 1–6.
   - **Rectifier change.** PMEG10030ELPX at 100 V is exceeded at about 117 V. A ≥ 150 V Schottky or ultrafast diode is needed, selected separately.
   - **SN6507 current.** Re-check the current-limit resistor and the 0.5 A recommendation; peaks are 0.58–0.93 A.
   - **F6/D-33 reruns.** `rail_campaign.py --cww-p 18` (datasheet maximum), the HS-LDO thermal check, and the PS2 budget at about +1.3 W input.
   - **Isolation.** Reinforced 550 Vrms at > 30 kHz (IEC 62368-1) meets the 500 Vrms basis. Its IEC 60664-1 figure is 490 Vrms / 700 Vpk, marginally below 500 Vrms. Under DECISIONS' functional-only reading this is moot.
4. **750316033** (1.3:1, reinforced, 227 in stock) **leaves too little span headroom.** Its secondary is 7.7 % lower than the current part's, and 750320775 already reaches only 17.28 V at 23.3 V / 700 kHz. It would need the LS supply raised, and IRM-20-24 has no trim.

### Source/audit edits

There is **no drop-in**, so there are no source or audit edits. For the record, the ECO path (750315240) would need these edits.

`elec/src/f6_parts.ato:310-322`:
```
component BiasTransformer:
    designator_prefix = "T"
    mpn = "750315240"
    manufacturer = "Wurth Elektronik"
    footprint = "temper:WE_750315240_1512_ReviewOnly"
    signal p1 ~ pin 1
    signal p2 ~ pin 2
    signal p3 ~ pin 3
    signal p4 ~ pin 4
    signal p5 ~ pin 5
    signal p6 ~ pin 6
```

`elec/src/f6_bias.ato:280-288` connections, rewired to the 1512 pinout:
```
    transformer.p1 ~ sw1
    transformer.p2 ~ raw24
    transformer.p3 ~ sw2
    transformer.p6 ~ sa
    transformer.p5 ~ n
    transformer.p4 ~ sb
```

`audit.rs:461` and `audit.rs:500`:
```
    ("bias_ha.transformer", "750315240"),
    ("bias_hb.transformer", "750315240"),
```

audit.rs has no pin-level transformer checks; they are in audit_f6.rs (below).

In `audit_f6.rs:199-210`, the per-pin table becomes `("1","bias_sw1"), ("2","v24_raw"), ("3","bias_sw2"), ("4", {base}-sb), ("5", n), ("6", {base}-sa)`, with pins 7/8 removed. The test at `audit_f6.rs:425` rewires `bias_ha.transformer` pin "2" to v15_selv. It stays valid because pin 2 is still the primary CT. Any audit entry that pins PMEG10030ELPX changes with the rectifier.

---

## 3. C1/C2: KEMET R463N410000N1M (X2 1 µF, 310 Vac, 22.5 mm)

### Recorded basis

| Requirement | Recorded value | Source |
| --- | --- | --- |
| Function | Line-to-line X2 across L_F/AC_N_IN (C1) and L_FILT/N_FILT (C2) | `elec/src/power_stage_120v.ato:328-346` |
| Class / rating | X2, 310 Vac (630 Vdc), metallized PP | `parts.ato:81-84`; KEMET R46 datasheet p.1 |
| Capacitance / tolerance | 1.0 µF ±20 %. The bleed calc assumes +20 %: 2 × 100 k, τ 0.40 s, 0.85 s to 34 V at +20 % C | `parts.ato:102`; `bom-simplification/calc_discharge.py` |
| Pitch / leads | 22.5 ± 0.4 mm, Ø0.8 ± 0.05 mm leads. Pads Ø2.4 mm, drill 1.2 mm at (0,0) and (22.5,0) | R46 p.3; `KEMET_R463N410000N1M_P22.50_ReviewOnly.kicad_mod` |
| Body | 26.5 × 11.0 × 20.0 nominal, **26.8 × 11.2 × 20.1 max**. Courtyard x −2.25…24.75 (27.0 mm), y ±5.85 (11.7 mm) | R46 p.3 and p.10; footprint |
| Height envelope | ≤ 50 mm above board bottom (R4 L12), so ≈ 48.4 mm above board top. C1/C2 are in the mains zone, not in the 22 mm tongue band | `RELAYOUT-REQUIREMENTS.md` L12; `validation-plan/enclosure-fit/native21-plan.json` |
| dV/dt | 200 V/µs | R46 p.10 |
| Approvals | ENEC (IMQ V4413), UL/cUL 60384-14 (E97797), CQC | R46 p.9 |
| Humidity | IEC 60384-14:2023 Ed.5 biased humidity, 40 °C/93 % RH at rated voltage, 21 days; damp heat 40/93/56 d; climatic category 40/110/56 | R46 p.1 and p.9 |
| EMI model input | 1 µF, 12.20 nH ESL, 35 mΩ ESR. These are a related-series K-SIM scenario (R46KN4100JHP1M), not exact-part data | `07-conducted-emi/round3/README.md` |

Datasheet: KEMET/YAGEO F3095_R46_X2_310_110C (2026-05-13), <https://content.kemet.com/datasheets/KEM_F3095_R46_X2_310_110C.pdf>. A copy is saved in the repo at `validation-results/07-conducted-emi/sources/` (SHA-256 `5a3131ce…`), and I read that copy at 2026-10-09T17:37Z. The Digi-Key pages link the same document at <https://yageogroup.com/content/datasheet/asset/file/KEM_F3095_R46_X2_310_110C>.

How the part number decodes (R46 p.1–2): `R46` series, `3` = 310 Vac, `N` = 22.5 mm, `4100` = 1 µF, then packaging (`00` bulk short leads 4 +2/−0 mm; `40` long leads 30 mm; `50` long leads 25 mm; `JE`/`JH` short-cut leads; `CK`/`DQ` taped), then "internal use" (`N1` = 11 × 20 body, `N2` = 10 × 18.5 body, both on the p.10 rows), then tolerance K/M.

### Candidates (attribute by attribute)

| Attribute | **R463N410000N1M** (baseline) | **R463N410050N1K** | R463N410050N1M | **R463N410000N2M** | TDK B32923C3105K000 |
| --- | --- | --- | --- | --- | --- |
| Datasheet row | R46 p.10 `R463N4100(1)N1(2)` | same row | same row | R46 p.10 `R463N4100(1)N2(3)`, footnote (3): M only | TDK B32921…928 X2 (datasheet not readable: 403) |
| C / tol | 1 µF ±20 % | 1 µF **±10 %** (inside the ±20 % basis) | 1 µF ±20 % | 1 µF ±20 % | 1 µF ±10 % |
| Rating | X2 310 Vac / 630 Vdc | same | same | same | X2 **305 Vac** / 630 Vdc |
| Pitch / lead | 22.5 / Ø0.8 | same | same | same | 22.5 (Digi-Key); lead Ø not verified |
| Body max (L × T × H) | 26.8 × 11.2 × 20.1 | same (N1) | same (N1) | **26.8 × 10.2 × 18.6** (p.3 row 22.5/10.0/18.5) | 26.5 × 11.0 × 20.5 (Digi-Key; max/nominal not verified) |
| Lead length | 4 +2/−0 (`00`) | 25 +2/−1 (`50`): **trim before insertion** | 25 +2/−1 (`50`): trim | 4 +2/−0 (`00`) | `000` untaped (length not verified) |
| dV/dt | 200 V/µs | 200 | 200 | 200 | not verified |
| Approvals / humidity | R46 series (ENEC, UL, CQC; Ed.5 biased humidity 21 d) | identical (series-level) | identical | identical | TDK (not verified: datasheet 403) |
| Inside the existing courtyard and 3D envelope? | — | yes, same body | yes | yes, smaller on every axis | marginal: 11.0 vs 11.7 courtyard; H 20.5 > 20.1 model, but well under the 48.4 mm envelope |
| Digi-Key stock | 0. Mouser MOQ 1 / 38 wk; Digi-Key MOQ 360 / 24 wk (Codex CSV) | **955**, 399-12693-ND, $1.34 @1, std lead 24 wk. [page](https://www.digikey.com/en/products/detail/kemet/R463N410050N1K/5731184), read 2026-10-09T17:38Z | 51 in the Digi-Key keyword listing; the product-page parse attributed the figure ambiguously. [page](https://www.digikey.com/en/products/detail/kemet/R463N410050N1M/18196219), read 17:38Z | 42,906 in the Digi-Key keyword listing (product-page parse ambiguous, as above). **Newark 3,467 + 361** via [Findchips](https://www.findchips.com/search/R463N410000N2M), read 17:36Z. [DK page](https://www.digikey.com/en/products/detail/kemet/R463N410000N2M/2571305), $1.44 @1 | **3,528**, 495-6918-ND, $1.25 @1, 28 wk std. [page](https://www.digikey.com/en/products/detail/tdk/B32923C3105K000/964226), read 17:36Z |

Digi-Key keyword listing used for the stock column: <https://www.digikey.com/en/products/result?keywords=R463N4100>, read 2026-10-09T17:36Z. It also showed R463N410040N1M (30 mm leads, ±20 %) at 95 and R463N4100CKN1M (taped) at 120.

Need for the 5-board lot with 2 spares per board: 5 × (2 + 2) = **20**. Every bold candidate covers it from one distributor.

### EMI model (task 07, D-22) sensitivity

I ran the committed deck `round3/scripts/emi_topology.cir` read-only. A temporary copy was perturbed with ngspice 45 at 200 points/decade from 150 kHz to 30 MHz. The scripts and output are in `alternates/emi-sens/`.

| Drive | Perturbation | 0.15–0.5 MHz | 0.5–1 MHz | 1–2.5 MHz | 2.5–30 MHz |
| --- | --- | --- | --- | --- | --- |
| CM, single leg (the drive behind every reported 60/64 dBµV scenario line) | ESL 8–20 nH, ESR 10–80 mΩ, C ±20 % | **0.00 dB** | 0.00 | 0.00 | 0.00 |
| DM, 1 A bus ripple (`EXC_DM`, zero in every reported scenario) | ESL 10 / 14.5 nH | +0.25 / −0.27 | +2.4 / −2.9 | −6.6 / +5.8 | −4.8 / +4.9 |
| DM | ESR 25 / 50 mΩ | +0.07 / −0.07 | +0.2 / +0.5 | −5.7 / +6.0 | ±0.3 |
| DM | C ±20 % | — | ≈ ±6 near 1 MHz | ≈ ±6–8 | ≈ 0.2 |

Figures are the largest |Δ| in each band, relative to the deck's 12.2 nH / 35 mΩ / 1 µF.

What this shows:

- The CM transfer, which the task-07 scenario outputs rest on, is insensitive to C1/C2 ESR, ESL and C. The change is below 0.01 dB everywhere.
- The DM transfer is insensitive (≤ 0.35 dB) from 150 to 500 kHz, where the low-order 35/60 kHz harmonics sit.
- The DM transfer is **not** insensitive around the X-cap/choke resonance (≈ 1–2.5 MHz) or above it. A few nH or tens of mΩ move it by 5–10 dB there.

That DM band carries no result today, because `EXC_DM` is zero in every scenario and task 07 is already "BLOCKED: exact C1/C2 impedance data". The change does not invalidate any recorded EMI result. Candidates with the same N1 body (R463N410050N1K/N1M) differ from the baseline only in lead length and tolerance, so their ESL and ESR should be the same construction. R463N410000N2M has the same 26.5 mm length and pitch but a thinner body. Its ESL should be close, but that is not verified: KEMET K-SIM returned no match for the N1M baseline either, per `round3/sources/intake.md`. The open task-07 item "impedance sweep of the exact C1/C2" applies unchanged to whichever part is fitted.

### Verdict: **drop-in with audit edit**

- **Recommended: R463N410050N1K.** It has the same R46 N1 body, rating, approvals and footprint. The only differences are 25 mm leads (trim to the `00` length, 4 +2/−0 mm, at hand assembly) and a tighter ±10 % tolerance. There are 955 at Digi-Key.
- **Second: R463N410000N2M**, with high stock at Newark and Digi-Key. Its smaller body (max 26.8 × 10.2 × 18.6 mm) sits inside the existing courtyard and 3D envelope.
- TDK B32923C3105K000 is a third-tier option. It is 305 Vac, a lower rating than the recorded 310 Vac, and its body tolerance against the 11.7 mm courtyard was not verified because the TDK datasheet returned 403.

Board copper and the footprint stay as they are. The footprint name `KEMET_R463N410000N1M_P22.50_ReviewOnly` is cosmetic, so keep it to avoid a board-file identity change.

Edits for R463N410050N1K:

- `elec/src/parts.ato:81-86`. Docstring: "KEMET R463N410050N1K X2 1 uF ±10 % 310 VAC, 22.5 mm pitch, R46 N1 body 26.5 x 11.0 x 20.0 mm (p.10 row R463N4100(1)N1(2); p.3 max 26.8 x 11.2 x 20.1); packaging 50 = 25 mm long leads, trim to 4 mm at assembly (p.2)". Set `mpn = "R463N410050N1K"`.
- `audit.rs:286-287`. Change `("cx1", "R463N410000N1M")` and `("cx2", "R463N410000N1M")` to `"R463N410050N1K"`.
- Regenerate the native-21 frozen netlist/BOM (`native-21/frozen/default.{net,csv}`, `resolved-components.json`) so the value fields follow. There is no copper change.
- Record the substitution in DECISIONS.md with this table.

For R463N410000N2M, use the same edits with `"R463N410000N2M"`, and change the docstring body to 26.5 x 10.0 x 18.5 nominal / 26.8 x 10.2 x 18.6 max (p.3). The 3D model (`native-21/models3d/capacitors`) stays a conservative over-envelope.

---

## 4. D3, DC-link TVS clamp (Microchip MRT130KP295CV)

The manufacturer is **Microchip**, not Littelfuse. Source: `elec/src/parts.ato:147-156` (`BusTvsMrt130kp295`), instantiated at `power_stage_120v.ato:688-690` (p1 BUS_P, p2 HV_RET, designator D3 at line 1126). audit.rs pins the MPN at line 291 and the nets at lines 757-758. Native-21 routed board: D3 sits at (254, 106) mm, horizontal. Pad 1 (bus_p) is at x 254 and pad 2 (hv_ret) at x 274. R3 (bus_p/busbleed_mid) is at 249.5 and R4 (busbleed_mid/hv_ret) at 283.0, so they bracket D3 on the same row.

### Recorded requirements (DC-LINK-CLAMP.md, FOOTPRINTS.md F10, footprint .yaml)

| Requirement | Recorded value | Source |
|---|---|---|
| Polarity | Bidirectional | parts.ato:148 |
| Stand-off | Above the ~286 V static OVP/restart-inhibit corner. 295 V approved. "Do not select the 275 V variant" | DC-LINK-CLAMP.md §1 |
| Clamp at returned tank current (~100 A) | ≤ 520 V at the bus caps and MOSFET terminals, including layout inductance. The MRT130KP295CV is rated 410 V max at 282 A (6.4/69 µs) and excludes lead inductance | DC-LINK-CLAMP.md table and §1 |
| Absorption | ≥ 2 J. That is ~49 µs rectangular at 100 A / 410 V. A rectangular pulse is derated to 66 % of the exponential rating (DS00005551B p.6 Fig. 4-1 note) | DC-LINK-CLAMP.md |
| Surge coordination | V(BR) min 300 V @ 5 mA was flagged as conducting *before* the upstream TMOV20RP175E. A higher onset helps coordination | DC-LINK-CLAMP.md "Mains surge coordination" |
| Footprint | `MRT130KP_Axial_P20.00mm_ReviewOnly`: pads (0,0) and (20,0), Ø3.2 copper, Ø1.6 drill. Max lead 1.3462 mm, body ≤ 12.954 × Ø7.874 mm. The 20 mm pitch is an assembly choice | FOOTPRINTS.md F10, .yaml |
| Suffix policy | "Keep the approved base MPN explicit; do not silently substitute a different suffix or clamp family." Owner approval is required for any change | DC-LINK-CLAMP.md §Procurement |
| Quantity for this check | 1 per board. 5-board lot + 2 spares/board = **15** | brief |

### MRT130KP family: what the datasheet actually offers

Microchip DS00005551B, Table 3-1, **p.5**. PDF: https://ww1.microchip.com/downloads/aemDocuments/documents/HRDS/ProductDocuments/DataSheets/130-kW-Transient-Voltage-Suppressor-TVS-Device-00005551.pdf (read 2026-10-09T17:31:52Z). The family has **only 275 V and 295 V** stand-offs, in CV (low clamp) and CA (normal clamp) versions. E3 is the RoHS finish, and M/MX/MXL are screening prefixes (p.1, p.3).

| Part | VWM | V(BR) min @ 5 mA | VC max @ IPP (6.4/69 µs) | Verdict vs basis |
|---|---|---|---|---|
| MRT130KP295CV (approved) | 295 | 300 | 410 V @ 282 A | Basis |
| MRT130KP295CVE3 | Same row, RoHS finish | 300 | 410 V @ 282 A | Electrically identical. A suffix change that needs owner approval |
| MRT130KP295CA | 295 | 300 | 460 V @ 282 A | Meets ≤ 520 V, but with less inductance margin |
| MRT130KP275CV/CA | 275 | 300 | 400/445 V | **Excluded** by the recorded basis (275 V class) |

The audit's negative-test MPN `MRT130KP300CV` (audit.rs:1466) does not exist in DS00005551B. It is a pure negative test.

Digi-Key stock, read 2026-10-09T17:32:13Z (https://www.digikey.com/en/products/result?keywords=MRT130KP): **every** MRT130KP listing shows **0**, "Check Lead Time", and a price at 100 pcs only:

- 295CV, 295CA, 275CV, 275CA, 275CAE3 and 275CVE3: $46.2154.
- 295CVE3 and the /TR variants: $46.431.

Codex's record also stands: Microchip direct has 0 stock, multiples of 100, 42 weeks. Mouser shows 42 weeks / MOQ 100. My microchipdirect.com fetch for MRT130KP295CVE3 timed out (17:32Z), so I could not check it. **No MRT130KP suffix is in stock.**

### Candidates outside the family

| Attribute | Need | **Littelfuse AK3-380C-Y** | **Bourns PTVS3-380C-TH** | Littelfuse 30KPA300CA |
|---|---|---|---|---|
| Polarity | Bi | Bi | Bi | Bi (CA) |
| VWM | > 286 V, ≥ 295 V | 380 V | 380 V | 300 V |
| V(BR) | — (higher helps MOV coordination) | 401–443 V @ 10 mA | 401 / 422 typ / 443 V @ 10 mA | 334–367.4 V @ 5 mA |
| VC at rating | 410 V @ 282 A (basis) | 520 V max @ 3 kA 8/20 | 520 V typ @ 3 kA 8/20 | 484 V @ 62 A 10/1000 |
| VC at ~100 A (est.) | ≤ 520 V incl. layout; aim ≤ ~460–480 V | **≈ 446 V**, from a linear interpolation of 443 V@10 mA → 520 V@3 kA. Not a published point | **≈ 446 V**, same method | **≈ 555 V**: (484−367.4)/62 ≈ 1.9 Ω slope. **Fails** |
| Energy ≥ 2 J @ ~49 µs | ≥ 2 J | 3 kA 8/20 rating (≈ 30+ J class). **No published 10/1000 or rectangular rating.** MCC AK3 Fig. 2 has a Ppp-vs-pulse-width curve, unread | 3 kA 8/20 only. No long-pulse rating | 30 kW 10/1000 (≈ 30 J): passes |
| Leads | ≤ 1.6 mm drill | 1.20–1.32 mm (MCC AK3 dims, equivalent family) | 1.25 ± 0.05 mm | P600 (~1.3 mm) |
| Lead pitch | **20.00 mm pads** | **23.43–24.87 mm preformed** ("Axial, Right Angle Bend (24.15mm Center)") | **24.15 ± 0.72 mm preformed** | Straight axial. Can be formed to 20 mm |
| Body | ≤ 12.95 × Ø7.87 | G 13.2–15.6 × A ≤ 11.5 × D 6.0–7.5 mm (MCC -380C) | G ≤ 16.5 × D ≤ 10.8 × H 6.0 ± 1 mm | P600 ~Ø9 × 9 |
| Footprint | MRT130KP_Axial_P20.00 | **No.** Pitch +4.15 mm, and the body is too long to re-form to 20 mm (≤ ~2 mm per side for a bend) | **No**, same reason | Yes (mechanical) |
| Status / stock | 15 | **Active, 71 in stock**, $48.88@1 / $38.955@10, mfr lead 18 wk | **Active, 19 in stock**, $58.98@1 / $44.677@10, mfr lead 20 wk | Active, 796 in stock, $30.49@1, 12 wk |
| Verdict | | **Needs ECO** | **Needs ECO** | **None**: fails the ≤ 520 V clamp at ~100 A (already rejected in DC-LINK-CLAMP.md) |

Sources and UTC read times:

- AK3-380C-Y: Digi-Key https://www.digikey.com/en/products/detail/littelfuse-inc/AK3-380C-Y/10445935 (17:35Z; status, stock, price, 401 V, 520 V @ 3 kA 8/20, 24.15 mm bend).
  - The Littelfuse datasheet (https://www.littelfuse.com/assetdocs/tvs-diode-ak3-y-series-datasheet?assetguid=82b75749-ebd9-4fcf-9621-4acd912be880) and the product pages return **HTTP 403 to automated fetch** (17:35:10Z). The -Y datasheet's page numbers are therefore not verified.
  - Equivalent-family dimensions and electrical table come from MCC "AK3 Series(AK)" Rev.4-3-05072025, p.1 dimension table and p.2 electrical table: https://www.mccsemi.com/pdf/products/AK3_Series(AK).pdf (17:36:46Z).
  - The legacy AK3-380C is **obsolete**. Digi-Key lists AK3-380C-Y as the "MFR Recommended" substitute, plus PTVS3-380C-TH as a direct one: https://www.digikey.com/en/products/detail/littelfuse-inc/AK3-380C/3131007 (17:34Z).
- PTVS3-380C-TH: Digi-Key https://www.digikey.com/en/products/result?keywords=PTVS3-380C-TH (17:34Z). Bourns datasheet "PTVS3-xxxC-TH Series" REV. 11/25: p.1 ratings and electrical table, p.3 dimensions. https://www.bourns.com/docs/Product-Datasheets/PTVS3-xxxC-TH_HV.pdf (17:34:45Z).
  - The older non-TH PTVS3-380C (570 V max) is obsolete: https://www.digikey.com/en/products/detail/bourns-inc/PTVS3-380C/2890919.
- 30KPA300CA: Digi-Key https://www.digikey.com/en/products/detail/littelfuse-inc/30KPA300CA/3997247 (17:36:22Z).
  - The V(BR) max of 367.4 V is from the Littelfuse spec table as reported by search. The Littelfuse page itself returned 403.
- Also seen and not pursued:
  - MDE 30KPA300CA (483 V): same class and same failure.
  - LCSC/JLC Chinese 30KP350CA / 30KP400CA (https://jlcpcb.com/partdetail/DOWO-30KP400CA/C293998): 30 kW class with higher VC. Fails the clamp.
  - Littelfuse AK10-380C-Y ($96.26, Digi-Key "also interested"): larger radial package. Not a footprint candidate.
  - I checked no SMD alternatives: the pads are THT, and no PLAD-class part number was confirmed on a page.

### Two-part options on the existing pads

- **Series pair** (e.g. two ~150 V bidirectional parts): it needs a mid-node. Two THT pads cannot provide one unless one device's lead is soldered to the other off-board, in free air on the HV bus. That is not acceptable for a mains-derived DC link, so this option is **rejected**.
- **Parallel pair on the same two holes**: a Ø1.6 mm drill cannot take two ~1.3 mm leads. Even physically, two 30KPA300CA in parallel do not guarantee current sharing. V(BR) spreads over 334–367 V, so one device can take most of the 100 A. The clamp claim would be no better than a single part. **Rejected.**

### Verdict: **none** as a drop-in; least-risk option **needs ECO**

1. **No in-stock part meets every recorded number on the existing 20 mm footprint.** Every MRT130KP suffix is 0 stock. The only straight-axial stocked part that fits the pads (30KPA300CA) fails the clamp at ~100 A.
2. **Least-risk substitute: Littelfuse AK3-380C-Y** (71 in stock). The second source is Bourns PTVS3-380C-TH (19 in stock). Both need a footprint ECO.
   - Electrically they beat the basis on stand-off margin: 380 V vs the 286 V corner, against 295 V on the basis part.
   - They also beat it on surge coordination: V(BR) min 401 V vs 300 V, so the upstream MOV takes more of a line surge.
   - Their estimated ~446 V clamp at 100 A leaves ~74 V for loop inductance below 520 V, against ~110 V with the 410 V MRT part. That is less margin, but still inside the target.
   - Open items: neither vendor publishes a VC point near 100 A or a long-pulse (10/1000 or rectangular) energy rating. The ≥ 2 J at ~49 µs, the clamp at 100 A and the hot-temperature V(BR) rise (+0.1 %/°C) are **unverified**. They need a vendor statement or the planned bench pulse before the clamp claim is made. The bus also rises ~100 V higher than with the MRT before the TVS conducts. That is still under the 520 V target, but the D3 shutdown/surge assessment must be redone with this V-I curve.
3. **Lowest risk overall, if the schedule allows:** keep MRT130KP295CV and pursue Microchip samples or brokers. MRT130KP295CVE3 is electrically identical (same datasheet row) but is a suffix change that needs owner approval. It is also 0 stock.

### ECO geometry (if the owner approves AK3-380C-Y / PTVS3-380C-TH)

- **New footprint** `temper:Littelfuse_AK3-380C-Y_Axial_P24.15mm_ReviewOnly`:
  - Pads 1 (0,0) and 2 (24.15,0), Ø3.2 copper, Ø1.6 drill. The leads are 1.20–1.32 mm, and the pitch tolerance is ±0.72 mm (Bourns) / 23.43–24.87 mm (MCC). Consider a 1.8 mm drill or 1.6 × 2.6 mm slots along x to absorb the pitch tolerance.
  - Fab body centred at x 12.075, 16.5 × 11.5 mm (the larger of Bourns G 16.5 and MCC A 11.5). Courtyard +0.25 mm. Height ≤ 11.5 mm lying flat; confirm the orientation on a sample.
- **Board impact at D3 (254,106)**: pad 2 moves from x 274 to 278.15 (pad edge 279.75). R4's pad 1 (busbleed_mid, ~140 V from hv_ret) has its edge at 280.975, which leaves **1.2 mm**. So R4, and the bleed track, must move ≥ ~3 mm right, or D3 must be re-placed or rotated. R3 at 249.5 blocks a leftward shift. This is a copper change in the mains/bus zone. Re-run DRC, the D5 clearance check and fit_gate. The D3 loop inductance is part of the 520 V budget, so re-measure it on the board.

### Exact source and audit edits (ECO case only; owner approval required per DC-LINK-CLAMP.md)

`elec/src/parts.ato:147-156` becomes (component renamed; update the import at power_stage_120v.ato:34 and the instance at line 688):

```
component BusTvsAk3380:
    """Littelfuse AK3-380C-Y bidirectional axial TVS across the DC link (replaces MRT130KP295CV, 0 stock).
    380 V stand-off, V(BR) 401-443 V @ 10 mA, 520 V max @ 3 kA 8/20 us; preformed 24.15 mm lead pitch.
    No published clamp at ~100 A or long-pulse energy: ~446 V / >=2 J are estimates pending vendor data or bench pulse."""
    designator_prefix = "D"
    mpn = "AK3-380C-Y"
    manufacturer = "Littelfuse"
    footprint = "temper:Littelfuse_AK3-380C-Y_Axial_P24.15mm_ReviewOnly"
    signal p1 ~ pin 1
    signal p2 ~ pin 2
```

Pin numbering and nets are unchanged (p1 BUS_P, p2 HV_RET), so audit.rs:757-758 and 763 stay as they are.

`audit.rs`:
- Line 291: `("tvs_bus", "MRT130KP295CV"),` becomes `("tvs_bus", "AK3-380C-Y"),`.
- Lines 1466-1467: the negative test `MRT130KP300CV` still fails under the new pin, so it remains valid. For it to keep meaning "wrong suffix of the approved family", change it to `m.set_part("tvs_bus", "AK3-380C");` / `fails(&m, "tvs_bus is AK3-380C");`. That suffix is obsolete and must not pass.
- For the Bourns second source, use `PTVS3-380C-TH` instead.

Docs to update with the owner decision: DC-LINK-CLAMP.md (candidate table and Procurement), FOOTPRINTS.md F10 (new row), DECISIONS.md (2026-09-25 entry). The suffix-change rule requires explicit owner approval in DECISIONS.md before the audit edit lands.

---

## 5. Stock for items the Codex check didn't cover

| MPN | Lot need | Digi-Key | Lead time | Other sources | URL / read UTC |
| --- | --- | --- | --- | --- | --- |
| TDK **B32654A1104K000** (resonant bank, 5/board) | 35 | **2,669 in stock**, 495-4194-ND. $2.87 @1, $1.99 @10, $1.639 @50 | Mfr std 23 wk | Findchips: no rows (its search is unreliable) | <https://www.digikey.com/en/products/result?keywords=B32654A1104K000>, 2026-10-09T17:31Z |
| Littelfuse **KLDR025.TXP** | 15 | **88 in stock**, F11252-ND, Active. $38.43 @1, $29.412 @10 | Mfr std 5 wk | Findchips: Sager 50, IBS 311, New Advantage 240, Newark 6, RS 9 | <https://www.digikey.com/en/products/detail/littelfuse-ibu/KLDR025-TXP/3740687>, 17:35Z; <https://www.findchips.com/search/KLDR025.TXP>, 17:32Z |
| Littelfuse **01250003H** clip (2/board) | 20 | **9,223 in stock**, F3306-ND. $4.24 @1, $3.249 @10 | Mfr std 14 wk | — | <https://www.digikey.com/en/products/result?keywords=01250003H>, 17:31Z |

All three are covered from Digi-Key stock alone.

Side note, outside this task: Digi-Key describes 01250003H as "250 V 30 A", while the KLDR fuse is 600 V. That is fine at 127 V + 10 %, but it is the holder rating that goes on the certification file.

---

## Summary

| Part | Blocker | Best in-stock option | Stock (lot need) | Verdict | Re-work |
| --- | --- | --- | --- | --- | --- |
| **C1/C2** KEMET R463N410000N1M | 0 stock, 24–38 wk | **KEMET R463N410050N1K**: same R46 N1 body, 310 Vac X2, ENEC/UL/CQC. Differences: ±10 % and 25 mm leads, trimmed at assembly. Alternative R463N410000N2M, smaller body, high stock | 955 at DK (20). N2M: Newark 3,467 + 361; DK listing 42,906 | **Drop-in with audit edit** | `parts.ato:81-86`, `audit.rs:286-287`, regenerate frozen BOM. No copper change. CM EMI transfer is unaffected (0.00 dB). DM is within 0.35 dB at 150–500 kHz but moves 5–10 dB around the 1–2.5 MHz resonance, which no current result depends on |
| **C5/C6** TDK B32656G0275J000 | Not stocked anywhere readable; TDK MOQ 360 | Same footprint and C: none stocked (G0275M000 also unlisted). Same pads, different C: **TDK B32676G1905K000** (9 µF, 750 V, 4-pin 37.5 × 20.3, 30 × 45 × 42 mm, ESL 12 nH) | 547 at DK (20) | **None** as an equivalent. B32676G is an electrical-basis ECO (no copper) | Bus goes 5.8 → 18.4 µF. Re-run BUS-CAP-SCREEN, F6/leg decks with the new C (no FEM: P5 and pads unchanged), inrush/I²t, LINE_ZC valley, EMI CBULK. Also check the 85 V/µs and 70 °C/10 kHz ratings. **Least risk: TDK samples of G0275J000 or G0275M000.** Any 2-pin part needs FEM/F6 redone plus a board ECO |
| **T2/T3** Würth 750320775 | 0 stock; DK 250 due 2027-03-17, Mouser 750 due 2027-04-01 | None on the EP7 HV pads. Best fallback **Würth 750315240** (1:1.1, reinforced 550 Vrms, UL E205930, 46 V·µs) | 90 at DK, 52 wk (20) | **None**. Fallback **needs ECO** | 6-pad footprint (13.74 mm columns, 3.81 mm pitch, 1.9 × 1.4 pads). Rectifier ≥ 150 V (PMEG10030 sees about 117 V). SN6507 peak 0.58–0.93 A against a 0.5 A recommended maximum. Cww 18 pF max against 3 pF, so F6 must be re-run. **Least risk: Würth Midcom samples or allocation of 750320775** |
| **D3** Microchip MRT130KP295CV | Every MRT130KP suffix is 0 stock, 42 wk, MOQ 100 | None on the 20 mm pads that meets ≤ 520 V (30KPA300CA ≈ 555 V at 100 A). Best: **Littelfuse AK3-380C-Y**, second source Bourns PTVS3-380C-TH (380 V stand-off, V(BR) ≥ 401 V, about 446 V at 100 A estimated) | 71 / 19 at DK (15) | **None**. Fallback **needs ECO** (owner approval required by DC-LINK-CLAMP.md) | New 24.15 mm-pitch axial footprint; pad 2 moves to x 278.15, so R4 moves about 3 mm. Neither part publishes clamp voltage at 100 A or a ≥ 2 J long-pulse rating: get vendor data or a bench pulse. Redo the shutdown/surge assessment. `audit.rs:291`, negative test at :1466 |
| B32654A1104K000 / KLDR025.TXP / 01250003H | — | — | 2,669 / 88 / 9,223 (35 / 15 / 20) | In stock | — |

---

