# D-22 discrete DM inductors (2 × ~41 µH, 15 A rms / 21 A pk): orderable-part survey and EMI check (2026-10-14)

Desk research plus the committed EMI model. Nothing was ordered, built or sent. No existing file was edited.

**Files in this folder:**
- `dm_emi_check.py` calls s19b through g01's wrapper, read-only, the same way `c29_emi.py run_full` does.
- `dm_emi_check.json` holds the results.
- `dm_emi_check_parts.log` and `dm_emi_check_sweep.log` are the console output.

**To rerun:** `python3 -I -B dm_emi_check.py [--procs N] [--only PREFIX]`

**Where the datasheets are:** under `/Users/bennet/.claude/jobs/fbfc46b4/tmp/dm-ds/`, outside the repo.

**How inductance values were read:** where a value comes from a curve, I read it off the vendor's "typical L vs I" plot, rendered at 200 dpi. The reading uncertainty is about ±0.5 µH.

## Bottom line

1. **Orderable parts exist.** The P3 statement "no MPN found" can close. The best fit is **Würth WE-HCFT 74437636355602**:
   - 56 µH, metal-alloy core, flat wire, through-hole.
   - **49.7 µH at 21 A** (89 %).
   - 3.19 mΩ, which gives **1.44 W for the pair at 15 A**.
   - Operating voltage 400 V.
   - 36 × 35.7 × 34.2 mm.
   - DigiKey: $18.94 at 30+, 61 in stock.
   - EMI on the D-22 basis: **11.7 dB nominal / 7.7 dB sensitivity minimum, PASS**. The 41 µH reference gives 10.5 / 6.5.
2. **The P3 floor of 32 µH does not carry over to D-22 as specified.** P3's 32 µH was derived on the K2 basis (3.2 mH module choke, module Y 2.2 nF). On the D-22 basis (TDK 1.6 mH choke, Y 4.7 + 2.2 nF), the 6 dB-in-every-sensitivity rule needs **≥ 40 µH per leg at 21 A**:

   | LNEW (5 mΩ, 15 pF) | Nominal | Sensitivity minimum |
   |---|---|---|
   | 38 µH | 9.99 dB | 5.98 dB |
   | 40 µH | 10.32 dB | 6.33 dB |
   | 42 µH | 10.63 dB | 6.67 dB |
   | 44 µH | 10.94 dB | 6.99 dB |

   The binding sensitivity is "X caps −20 %" at the 70 kHz line. Because of this, every 33–37 µH part found misses the rule (5.0–5.8 dB).
3. **Ranked candidates:**
   - **Primary:** the 56 µH part.
   - **Higher-margin alternative:** 62 µH, same body, 5.22 mΩ.
   - **Best-stocked and cheapest Würth option:** the 47 µH MnZn-ferrite part, 1,021 in stock, $15.23 at 18+. It has a second source with the same ratings, AW Coil AWFV3540-473KE.
   - **Cost:** none of the Würth parts shows a 100 or 500 price break at any distributor I could reach. Two pieces cost about $30–38 per module against D-22's $15.90 parts total.

## 1. Requirement used

- Per leg, at 21 A peak (the 15 A rms crest), the model needs **≥ 40 µH**. The task floor is ≥ 32 µH (prefer ≥ 41 µH). The PROPOSALS P3 spec is ≥ 80 % at 21 A.
- Current: ≥ 15 A rms continuous.
- DCR: ≤ 8 mΩ.
- Mains-suitable insulation or voltage rating.
- THT or chassis mount.
- **Heat allowance:** 3.6 W for the two inductors (2 × 8 mΩ × 15² A²; s19b README §9.5, c29 README §3). This is inside D-22's 8 W module allowance.

## 2. Candidates

**Column definitions:**
- "L curve": L at 0 A / L at 21 A, read from the vendor's L–I plot. A "≥" value is a bound from a published Isat point, not a curve reading.
- Loss: 2 × 15² × DCR.
- Prices: DigiKey, read 2026-10-14. No 100 or 500 break is listed unless shown.

| # | MPN (core) | L0 / L@21 A | Irms rating | DCR typ / max | Loss, 2 pcs at 15 A | Voltage | Size (mm) | Price, stock | EMI nominal / sens. min (dB) at 21 A |
|---|---|---|---|---|---|---|---|---|---|
| 1 | **Würth 74437636355602** (metal alloy, WE-HCFT 3635) | 56.0 / **49.7** | IRP,40K 32.8 A; Isat30% 36.9 A | 3.19 ±10 % (3.51 max) | **1.44 / 1.58 W** | VOP 400 V | 36.0 × 35.7 × 34.2 | $24.68 (1), $18.94 (30+); 61 | **11.73 / 7.71 PASS** (0 A: 12.04 / 7.73) |
| 2 | **Würth 74437636356203** (metal alloy, 3635) | 62.0 / **56.1** | IRP,40K 26.3 A; Isat30% 43.1 A | 5.22 ±10 % (5.74) | 2.35 / 2.58 W | VOP 400 V | 36.0 × 35.7 × 34.2 | $18.94 (30+); 34 | **12.04 / 7.73 PASS** (the binding term moves to the 60 kHz CM line) |
| 3 | **Würth 7443763540470** (MnZn ferrite, WE-HCFT 3540) | 47.0 / **46.6** (20 °C curve) | IR 32 A (ΔT 50 K); Isat30% 31 A | 5.67 / 6.38 | 2.55 / 2.87 W | VOP 250 V | 36 × 41 × 35 max | $21.43 (1), $15.23 (18+); **1,021** | **11.31 / 7.39 PASS** (0 A: 11.36 / 7.45) |
| 3b | AW Coil AWFV3540-473KE (ferrite; same body and ratings as #3) | 47 ±10 % / **≥ 42.3** (Isat10% = 26.0 A) | Irms 28 A (20 K) / 34 A (40 K) | 5.67 / 6.38 | 2.55 / 2.87 W | not stated | 41 × 36 × 35 | DigiKey Marketplace $14.60 (50); 900, ships in about 30 days | not run (≥ 42.3 µH puts it at ≥ 10.6 / ≥ 6.6 per the sweep) |
| 4 | CODACA CPEX3222LV-470MC (composite) | 47 / **no curve** | 23 A (ΔT 50 K); Isat30% 30 A | – / 5.52 | 2.48 W | Hi-pot 1500 VAC | 32.2 × 22.2 × 30 | $17.78 (1), $11.95 (108), $11.13 (252), **$10.88 (504)**; 84; 14 wk | not run at 21 A (unknown); passes only if L(21 A) ≥ 40 µH |
| 5 | Würth 74437636353703 (metal alloy) | 37.0 / 34.8 | 32.8 A | 3.19 ±10 % | 1.44 W | 400 V | 3635 | $18.94 (30+); 55 | 9.42 / **5.38 – misses** |
| 6 | Würth 7443763540330 (ferrite) | 33.0 / 32.9 | 32 A | 5.67 / 6.38 | 2.87 W | 250 V | 3540 | $15.23 (18+); 37 | 9.06 / **5.00 – misses** |
| 7 | Coilcraft AGP4233-333ME (ferrite) | 33 / ≥ 29.7 (Isat10% = 22.5 A) | 24 A (20 K) / 34 A (40 K) | 2.80 / 2.95 | 1.33 W | not found | 135 g [secondary] | DigiKey: no listing; Mouser timed out | 8.41 / **4.31 – misses** |
| 8 | Vishay IHTH1500TZEB330M5A (composite) | 33.2 / 30.6 | 28.7 A (40 K); Isat20% 39.9 A | 4.9 / 5.1 | 2.29 W | not stated (48 V applications) | Ø38.1 × 19.8 | $10.58 (100), **$9.74 (500)**; 0 in stock, 21 wk | 8.60 / **4.52 – misses** |
| 9 | Vishay IHB-6, 47 µH (rod/drum filter inductor) | 47 / **no curve** | 21.7 A (+40 °C rise) | – / 8.0 | 3.60 W (= allowance) | 2500 VRMS dielectric (with optional sleeve) | Ø50.8 × 38.1 | no 47 µH IHB-6 listed at DigiKey | 11.37 / 7.45 at **0 A only** |

**Rejected outright:**
- **Coilcraft AGP4233-473ME:** Isat30% 18.6 A, so it is below 70 % at 21 A.
- **CODACA CPQ4228-470M:** a copy of AGP4233-473 (Isat 17.6 A).
- **Vishay IHTH1500TZEB470M5A:** 47 µH, 47.3 µH at 21 A, but 9.3 mΩ max gives 4.0 W, over the allowance.
- **All catalogue toroids at 47 µH**, from the DigiKey search "toroidal inductor 47uH through hole" (69 results). The best are:
  - Bourns 2309-V-RC / Signal HCTI-47-10.7: 10.7 A, 16 mΩ
  - Bourns 2200LL-470: 10.3 A, 12 mΩ
  - Bourns 2300HT-470: 10 A, 28 mΩ
  - Bourns 2300LL-470-V-RC: 11.8 A, 12 mΩ (distributor listing)
- **Murata 1400 series:** 47 µH tops out at 8.3–8.5 A, and the series is bobbin type.
- **Würth WE-FI:** 9 A maximum in the series.
- **TDK B82615:** 10 A maximum.
- **Hammond 195:** mH-class, 7 mH is the smallest value at 20 A.
- **Families that are CM or current-compensated, not DM:**
  - Schaffner RD
  - Schurter DKIH-1
  - KEMET SBT (0.5 A NiZn)
  - TDK B82721 / B82724 / B82725
- **Nothing ≥ 15 A THT at 33–100 µH found:** Sumida, Coilmaster, Sunlord, Pulse and Signal Transformer.
- **CWS J20 powder toroids:** the page returned HTTP 410, so not checked.

### Notes per candidate

**#1 / #2 (Würth WE-HCFT 3635, metal alloy):**
- Metal-alloy powder rolls off gradually (no knee) and keeps its Bsat at temperature. That makes it the most robust core here for a 60 Hz, 21 A peak bias.
- **Tolerance:** L is ±20 %. At the −20 % corner and 21 A:
  - #1 gives 39.8 µH, which sits on the 40 µH threshold (about 6.3 dB sensitivity minimum, per the sweep).
  - #2 gives 44.9 µH, which gives about 7 dB.
  - So #2 is the one that stays clear of the threshold at the low-tolerance corner.
- **Lead and footprint:** rated current is per IEC 62024-2 Class D (PCB copper). The leads are flat wire (pin pattern 24.3 × 11.5 mm).
- **Mass:** not in the datasheet.

**#3 (Würth 7443763540470 and its AW Coil equivalent, MnZn ferrite):**
- The curve is flat to about 24 A, then has a knee. The 46.6 µH reading is the 20 °C typical curve.
- MnZn saturation flux falls substantially when the core is hot. Würth publishes no hot curve, so the 21 A value on a warm core is **[UNVERIFIED]**.
- At ΔT ≈ 8 K at 15 A (Würth temperature-rise plot), self-heating is small. Ambient inside the module is the open question.
- At the −20 % L corner it gives 37.3 µH, which is below the 40 µH threshold (about 5.9 dB).

**#4 (CODACA CPEX3222LV-470MC):** the cheapest at volume. It is not adoptable without a measured L at 21 A, because no curve is published. Isat30% = 30 A, and a composite core loses L gradually below that point.

**Agency:**
- None of these inductors carries UL or VDE component recognition. They are general-purpose power inductors, and some (Würth) are AEC-Q200.
- Würth gives VOP 250 V (3540) and 400 V (3635). CODACA gives a 1500 VAC hi-pot. Vishay IHB gives 2500 VRMS dielectric with the optional sleeve.
- Each inductor sits wholly at line potential. The safety questions are therefore:
  - creepage and clearance from core/winding to PE or chassis in the module;
  - the certifier's acceptance of an unrecognised wound component in a UL 858 / CSA appliance.
- This is an open item for the lab; I did not resolve it.

## 3. EMI model runs (`dm_emi_check.py`, s19b through g01's wrapper, unmodified)

**Basis:** D-22 as specified plus s19b nominal (g01 `B0_baseline_s19b_nominal`). Only LNEW, RNEW and CPNEW change:
- LNEW = the curve value at 21 A (or at 0 A).
- RNEW = DCR max.
- CPNEW = 1/((2π·SRF)²·L0). That is 8.2 pF for #1, 10.7 pF for #2 and 15.0 pF for #3. It is 30 pF (the s19b default) where no SRF is published.

**Sweep and rule:**
- fs 35–60 kHz at a 1 kHz step, with a 0.5 kHz recheck.
- g01's eight one-at-a-time sensitivities, plus the pan-earthed INFO case.
- PASS = ≥ 6 dB nominal and in every sensitivity.

**Controls reproduce:**
- s19b nominal: 10.479 dB.
- B0 (41 µH): 10.48 / 6.50.
- D-22 as specified (LNEW 0): **−5.05 / −9.78 dB**, which matches c29's −5.1 / −9.8.

| Case | Nominal (binding line) | Sens. min (binding sensitivity) | Pan earthed (INFO) |
|---|---|---|---|
| CTL D-22 as specified, LNEW 0 | −5.05 (70 kHz DM) | −9.78 (X −20 %) | −5.4 |
| CTL B0, 41 µH / 8 mΩ / 30 pF | 10.48 | 6.50 (X −20 %) | 2.6 |
| #1 WE 56 µH @21 A (49.7 µH) | **11.73** | **7.71** (coil + board 51 pF) | 2.6 |
| #1 @0 A (56 µH) | 12.04 (60 kHz CM) | 7.73 | 2.7 |
| #2 WE 62 µH @21 A (56.1 µH) | **12.04** (60 kHz CM) | **7.73** | 2.7 |
| #3 WE 47 µH @21 A (46.6 µH) | **11.31** | **7.39** (X −20 %) | 2.6 |
| #9 IHB-6 47 µH @0 A only | 11.37 | 7.45 | 2.6 |
| #5 WE 37 µH @21 A | 9.42 | 5.38 | 2.6 |
| #6 WE 33 µH @21 A | 9.06 | 5.00 | 2.6 |
| #8 IHTH 33 µH @21 A | 8.60 | 4.52 | 2.6 |
| #7 AGP4233-333 at its 10 % bound (29.7 µH) | 8.41 | 4.31 | 2.6 |
| Sweep 38 / 40 / 42 / 44 µH (5 mΩ, 15 pF) | 9.99 / 10.32 / 10.63 / 10.94 | 5.98 / 6.33 / 6.67 / 6.99 | 2.6 |

- Above about 50 µH the 70 kHz DM line stops binding. The margin then saturates at about 12.0 dB, set by the 60 kHz CM line. A larger DM inductor buys nothing further.
- The pan-earthed INFO case stays at about 2.6 dB whatever the DM inductor. That case is CM.
- All margins are model results, not measurements.

## 4. Heat (allowance 3.6 W for the pair)

| Part | Pair at 15 A, DCR typ / max (20 °C) | Share of 3.6 W |
|---|---|---|
| #1 56 µH | 1.44 / 1.58 W | 44 % |
| #2 62 µH | 2.35 / 2.58 W | 72 % |
| #3 47 µH | 2.55 / 2.87 W | 80 % |
| #4 CODACA | – / 2.48 W | 69 % |
| #9 IHB-6 | – / 3.60 W | 100 % |

- Copper resistance rises about 0.39 %/K. At a 40 K winding rise, add about 16 %; #1 then sits at about 1.8 W.
- The module's ambient and enclosure airflow are not modelled here.

## 5. Assembled filters with built-in DM inductors (alternative to discrete parts)

Source: a separate research pass. I re-read the FN2080 table myself.

**Only two families publish a DM value:**
- **Schaffner/TE FN2080-16:** 43 µH per line, 2.8 mH CM, Cx 1 µF.
- **Schurter FMBB NEO "Design F" 5500.2625.xx:** the same values.

**FN2080-16 (Schaffner data sheet 2023-07-12, Filter Selection Table p.2, https://docs.rs-online.com/c5a0/0900766b81523ed9.pdf, read by me):**
- Rated 16 A at 40 °C (18.4 A at 25 °C).
- **Tolerance −30/+50 %**, so the low limit is 30.1 µH. No value is given under bias.
- 9.0 W loss.
- 1020 g; 119 × 85.5 × 57.6 mm.
- **Y per line:** standard 4.7 nF (0.38 mA at 120 V/60 Hz); **A 0.47 nF; B none**.
- Approvals: UL 1283, CSA 22.2 No. 8.
- Price and stock (DigiKey, 2026-10-14):
  - FN2080-16-06: $80.50 at 50, 0 in stock, 23 weeks.
  - FN2080B-16-06: $116.05 at 10, not stocked.

**Schurter 5500.2625.01 / .07 (M80, 0.47 nF) / .04 (M5, no Y)** (https://www.schurter.com/pdf/english/typ_FMBB_NEO.pdf, variants table pp.10–11):
- 16 A at 40 °C, 7 W.
- DigiKey: .01 at $66.76 for 102+, 0 in stock.
- No tolerance is stated for the 43 µH.

**Assessment:**
- Both are 16 A parts carrying 15 A in a hot enclosure.
- Both carry 43 µH nominal with no bias data. Below the 40 µH threshold at the −30 % corner.
- Both cost $67–116 and weigh about 1 kg.
- **Not recommended** in place of two discrete inductors. Using one would also replace D-22's topology (extra 2.8 mH CM and 1 µF X), which I did not model.

**Families that publish no DM value:**
- Schaffner FN2090, FN2410/2412, FN2415, FN350, FN9222/9260
- TE Corcom (SK, EMC, VR, EQ)
- TDK B84771/B84776/B84113
- Schurter FMAB NEO, 5110/5120
- Cosel NAC, TDK-Lambda RSHN

**Not usable for this Y budget:** FN2415 standard and L versions (Cy 100 / 33 nF).

## 6. Alternative: raise the fs floor (quoted from `11-candidates/g01-mains/f10_fsfloor_g01_results.json`; nominal only, no sensitivities)

**Caveat:** that file is on g01's **K2 basis**:
- module CM choke 3.2 mH with 36 µH leakage;
- module Y 4.7 nF removed (`CYADD` = 0);
- module HF Y 2.2 nF plus board Y 2.2 nF.

It is **not** the D-22-as-specified basis (1.6 mH / 18 µH / Y 4.7 + 2.2 nF) used in §3. Its 35 kHz row (1.9 dB at LNEW 0) differs from D-22's −5.05 dB.

| fs floor | LNEW 0 µH | 10 µH | 20 µH | 32 µH |
|---|---|---|---|---|
| 35 kHz | 1.88 | 5.94 | 8.66 | 11.04 |
| 38 kHz | 4.84 | 8.81 | 11.45 | 13.76 |
| 40 kHz | 6.68 | 10.58 | 13.18 | 15.44 |
| 45 kHz | 14.47 | 17.79 | 17.80 | 17.82 |

(dB, nominal margin.)

## 7. Recommendation

**Adopt Würth 74437636355602 (56 µH) as the D-22 DM inductor, one per line.** Electrically, Würth 74437636356203 (62 µH) is the better choice if you want to stay above 40 µH at −20 % tolerance and 21 A. It costs about 0.9 W more heat for the pair (2.35 vs 1.44 W) at the same price and body. Before committing to either:

1. **Bench-measure L at 21 A DC bias and at 60 Hz 15 A rms on a warm part.** Two samples are $50 at DigiKey. This replaces the "typical curve" reading.
2. **Get a volume quote from Würth or a distributor.** No 100 or 500 break is published at DigiKey. The 30+ price is $18.94 each, so a pair costs **+$37.9 per module (est.)** at that price.
3. **Ask the certifier about the unrecognised component and creepage in the module.** See the agency note in §2.

**Lower-cost path:** #3 (47 µH ferrite, $15.23, 1,021 in stock, second source AW Coil).
- It passes nominally (11.3 / 7.4 dB).
- It is marginal at −20 % tolerance (37.3 µH).
- Its hot-core saturation is unpublished.
- **Use it only with the bench measurement.**

**Cheapest at volume:** CODACA CPEX3222LV-470MC ($10.88 at 504). It needs a measured L-vs-I first.

## 8. Not verified

- **Prices:** no 100 or 500 price break for any Würth part. DigiKey trays stop at 18–30. Mouser, Farnell/element14, Newark, Arrow and TTI timed out or refused; LCSC and Octopart refused.
- **Mass:** not published for any Würth part. The 135 g for AGP4233 comes from a third-party copy.
- **Coilcraft AGP4233 values** come from a third-party copy of the datasheet (novapart.co; coilcraft.com returned 403) **[secondary]**. Search snippets of Coilcraft's own page match the 473 row.
- **Bourns 2300LL-470-V-RC** 11.8 A / 12 mΩ is from distributor listings only **[UNVERIFIED]**.
- **No L-vs-I curve at elevated core temperature** for any ferrite part. No curve at all for CODACA or Vishay IHB.
- **Würth "typical" curves** were read at about ±0.5 µH.
- **CODACA CPEX3222LV numeric table:** the vendor page shows placeholder cells. Values are DigiKey's parametric data **[secondary]**.
- **Agency:** the Würth VOP rating is not an agency approval. No UL or VDE file was found for any candidate inductor.
- **FN2080/FMBB DM values** are nominal, with no bias data. Schurter FMBB prices and the 5500.2625.04/.07 data come from the research pass and were not re-read by me.

## Sources (read 2026-10-14)

**Würth WE-HCFT:**
- Series table: https://www.we-online.com/en/components/products/WE-HCFT
- Per-part datasheets: `https://www.we-online.com/components/products/datasheet/{74437636355602, 74437636356203, 7443763540470, 74437636353703, 7443763540330}.pdf`. Page 1 has the "Electrical Properties" table and dimensions; page 2 has "Typical Inductance vs. Current Characteristics" and the temperature-rise plot. The 7443763540470 sheet is rev. 002.001, 2025-02-20.

**AW Coil:** AWFV3540 datasheet, p.2 "Electrical Characteristics": https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/8949/AWFV3540.pdf

**Vishay:**
- IHTH-1500TZ-5A, doc 34559 rev. 08-Oct-2026: p.1 table, p.3 performance graphs. https://www.vishay.com/doc?34559
- IHB, doc 34015 rev. 12-Dec-2025: pp.1–3. https://www.vishay.com/docs/34015/ihb.pdf

**Coilcraft:** AGP4233 table (third-party copy): https://novapart.co/datasheet/farnell:2527011/. Original: https://www.coilcraft.com/en-us/files/datasheet/AGP4233 (returned 403).

**CODACA:** https://www.codaca.com/Productsctr_CPEX3222LV.html (notes: Isat 30 % drop, Irms ΔT 50 K, hi-pot 1500 VAC)

**DigiKey price and stock** (`https://www.digikey.com/en/products/result?keywords=<MPN>`):
- 74437636355602, 74437636356203, 74437636353703, 7443763540470, 7443763540330
- AWFV3540-473KE, CPEX3222LV-470MC, IHTH1500TZEB330M5A
- Toroid sweep: `keywords=toroidal inductor 47uH through hole`

**Schaffner FN2080:** https://docs.rs-online.com/c5a0/0900766b81523ed9.pdf, p.2

**Schurter FMBB NEO:** https://www.schurter.com/pdf/english/typ_FMBB_NEO.pdf

**Repo inputs:**
- `11-candidates/g01-mains/PROPOSALS.md` P3
- `11-candidates/g01-mains/emi_g01.py`
- `11-candidates/g01-mains/f10_fsfloor_g01_results.json`
- `07-conducted-emi/s19b/README.md` §9.5
- `11-candidates/c29-inlet-filter/README.md` §1, §3
