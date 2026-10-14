# F1 fuse data survey (fills the open gaps in `../F1-FUSE-DECISION.md`)

Date 2026-10-14. Desk research only: nothing ordered, no logins, no forms. Datasheets were downloaded to a scratch folder outside the repo; none are stored here.
Machine-readable copy: `survey.json` (one object per candidate, `null` where unknown, a `source` per field).

Tags:
- **[MIRROR]**: a manufacturer datasheet PDF read from a third-party host (distributor or datasheet site). The document is Littelfuse's, Eaton's, etc.; the host is not.
- **[PLOT]**: value read off a published curve by me (pixel-calibrated where stated). Expect ±5 % on % axes and ±10 % on log axes.
- **[UNVERIFIED]**: not read from a primary document (search-result summary, distributor spec sheet, or inference).
- Prices and stock: DigiKey pages read 2026-10-14 through a fetch tool. I checked that each extended price equals quantity × unit price. Mouser, Newark, Arrow and Farnell timed out or blocked, and LCSC search was blocked, so **every price below is DigiKey only**.
- Browser automation (Claude-in-Chrome) failed 3 times ("extension not connected"), and littelfuse.com returns HTTP 403 to scripted fetches, so all Littelfuse data comes from mirrors.

## 0. Corrections to the decision record

1. **The repo's "$29.41 at 500" for KLDR025.TXP is DigiKey's 10-piece price.** DigiKey F11252-ND today: 10 pcs $29.412, 100 pcs $22.446, **500 pcs $18.516**. The same applies to the clip: $3.249 is the 10-piece price of 01250003H, and **500 pcs costs $2.057**. Corrected baseline BOM at 500: **$18.52 + 2 × $2.06 = $22.63 per board**.
2. **The 505's 145 vs 210 A²s conflict is a datasheet revision change.** The 2008 and 2009 revisions list 25 A at **145 A²s, 0.0051 / 0.0048 Ω**. The 2019 revision (and, as far as the garbled mirror text shows, the 10/16/23 revision) lists **210 A²s, 0.0048 Ω**. Littelfuse's product page (145 A²s, 0.0051 Ω) matches the 2008 table, so it is stale. Use 210.
3. **The 505's 25 A AC interrupting rating is 30 kA @ 500 VAC, not 20 kA.** The 2019 table puts 20, 25 and 30 A in one merged cell: "30kA@500VAC / 20kA@500VDC". The "20,000 A" headline is the DC/TÜV figure. In the 2023 revision, note 1 narrows the TÜV 20 kA AC option to 30 A only (it was 15–30 A in 2019).
4. **A 505-class part does publish a clearing I²t: Bel Fuse 0ADEC9250-BE** (6.3 × 32 ceramic, fast, 25 A, 500 V, 30 kA AC, cURus E20624). It lists **pre-arc 200 A²s and total 470 A²s**, "measured at 500V IR test". It also costs less than the 505 ($2.76 at 500) and is in stock.
5. **There is a cheaper Class CC 25 A: Littelfuse KLKR025.T at $16.41 at 500** (fast-acting, same UL file and class as KLDR). Its published 25 A peak let-through is about 1.17 kA at 5 kA and 1.38 kA at 10 kA [PLOT]. No Class CC 25 A publishes a total clearing I²t below KLDR025's 1,710 A²s: KLKR and CCMR do not publish a 25 A row at all.

## 1. Littelfuse 0505025 (505 series, 6.3 × 32 ceramic, fast-acting)

Variants: `.MXP` = cartridge, bulk 1000 ("M" = 1000, "X" = filler, "P" = lead-free). `.MXEP` = the same fuse with axial leads ("E"). **`.HXP` does not exist** in the 505 part-numbering system (2019 datasheet p.3), and DigiKey returns no result for it.

| Field | Value | Source |
|---|---|---|
| Voltage, AIR | **500 VAC, 30 kA @ 500 VAC; 500 VDC, 20 kA @ 500 VDC** (one merged cell for 20/25/30 A). Covers 140 VAC by voltage. Headline "20,000 A". | 505 datasheet Rev 01/15/19, p.1, "Electrical Characteristic Specifications by Item" table [MIRROR: https://agelectronica.lat/pdfs/textos/0/0505025_MXP.PDF, footer "Downloaded from Arrow.com"]. 2009 rev p.1 has the same cell [MIRROR: https://datasheet.octopart.com/0505012.MXP-Littelfuse-datasheet-8700652.pdf]. 2023 rev note 1: "20kA @ 500VAC and 20kA @ 500VDC interrupting rating available for TUV certification of 30A" [MIRROR text: https://pdf.jiepei.com/0505010.-45698391.html, "Revised: GD. 10/16/23"] |
| Nominal melting I²t | **210 A²s** (rev 2019; 0.0048 Ω). Earlier revs: 145 A²s (2008: 0.0051 Ω; 2009: 0.0048 Ω) | 2019 rev p.1 table [MIRROR as above]; 2008 rev p.1 [MIRROR: https://media.digikey.com/pdf/Data%20Sheets/Littelfuse%20PDFs/505%20Series.pdf]; 2009 rev p.1 [MIRROR]. The 2023 mirror text (garbled column order) shows "025. 25 500 … 210 0.0048" [MIRROR, UNVERIFIED column mapping] |
| Clearing I²t / let-through | **Not published** (none in the 2008, 2009 or 2019 revs, or in the 2023 text) | same |
| Opening time | 150 %: 30 min max; **200 %: 30 min max**; 300 %: 10 s max. **135 %: not specified** | 2019 rev p.1, "Electrical Characteristics for Series" [MIRROR] |
| Temperature rerating | **≈ 98 % at 50 °C, ≈ 96 % at 70 °C** [PLOT]. The 2019 note says the rerating is "in addition to the standard derating of 25% for continuous operation", so continuous capacity is 25 × 0.75 × 0.98 ≈ 18.4 A at 50 °C | 2019 rev p.2, "Temperature Re-rating Curve" [MIRROR]; same curve in the 2009 rev p.2 |
| Agency | 2019: cURus E10480 (10–30 A), PSE 1620079 (10–12 A), TÜV T5026910801 (15–30 A), CE. 2023: "Recognized to UL/CSA/NMX 248-1 and UL/CSA/NMX 248-14"; files E10480, SE-S-2300703, T5026910801, J50521465. **Recognized (component), not Listed.** UL category JDYX2: [UNVERIFIED] (UL Product iQ not consulted) | 2019 rev p.1 [MIRROR]; 2023 text [MIRROR jiepei] |
| Size | Cartridge 6.35 ± 0.3 × 31.75 ± 1.12 mm | 2019 rev p.3, "Dimensions" [MIRROR] |
| Price, stock (.MXP) | DigiKey F3259-ND: 100 = $4.3178, **500 = $3.5710**, 1000 = $3.4905; **3,112 in stock**; lead time 17 wk | https://www.digikey.com/en/products/result?keywords=0505025.MXP (2026-10-14) |
| Price, stock (.MXEP) | DigiKey F3266-ND: 100 = $5.0729, **500 = $4.19446**; **3,013 in stock** | https://www.digikey.com/en/products/result?keywords=0505025.MXEP (2026-10-14) |

### 1a. Bel Fuse 0ADEC9250-BE (drop-in 505 equivalent; offered by DigiKey as a substitute)

| Field | Value | Source |
|---|---|---|
| Voltage, AIR | 500 V AC/DC; **30 kA @ 500 VAC, 20 kA @ 500 VDC** (10–30 A) | Bel datasheet Rev "0ADEC/0ADEP Apr2023" p.1, "Safety Agency Approvals": https://belfuse.com/media/datasheets/products/circuit-protection/ds-cp-0adex-series.pdf |
| I²t | Typical pre-arc **200 A²s** (at 10 In); **total I²t 470 A²s** ("measured at 500V IR test") | same, p.2, "Electrical Specifications" |
| Opening time | 150 %: 30 min max; **200 %: 5 min max**; 300 %: 10 s max. 135 %: not specified | same, p.1 |
| Rerating | **≈ 0.96 at 50 °C, ≈ 0.91 at 70 °C** [PLOT] | same, p.3, "Temperature Re-Rating Curve" |
| Agency | cURus **E20624** (Recognized), "Designed to UL 248-14"; UKCA, CE. No CSA file or NMX printed | same, p.1 |
| Price, stock | DigiKey 5923-0ADEC9250-BE-ND: 100 = $3.3392, **500 = $2.76336**; **1,313 in stock** | https://www.digikey.com/en/products/result?keywords=0ADEC9250-BE (2026-10-14) |
| Size | 6.3 × 32 mm | same datasheet, p.1 title |

## 2. Class CC 25 A alternatives (UL 248-4 Listed, 600 VAC, 200 kA; all 10.3 × 38.1 mm)

| Part | AIR @ V | Melt I²t | Clearing I²t (published) | Let-through near 5 / 10 kA | 50 / 70 °C | 135 % / 200 % | Agency | $ @ 500 (DigiKey) | Stock |
|---|---|---|---|---|---|---|---|---|---|
| **Littelfuse KLDR025.TXP** (TD) | 200 kA @ 600 VAC | **226.0** | **1,710** (column "Total clearing I²t", no test current stated) | **No 25 A column or curve.** Apparent RMS (p.6 table): 20 A 456 / 575, 30 A 621 / 783. Peak (p.8 curve) [PLOT]: 20 A 1.05 / 1.32 kA, 30 A 1.42 / 1.80 kA | **≈ 90 % / ≈ 81 %** [PLOT, p.6] | 60 min max / 12 s **min** | UL Listed E81895, CSA LR29862; no NMX printed | **$18.516** (100 = $22.446) | 88 (+4,660 factory) |
| Littelfuse KLDR025.HXP (same fuse, 100-pack) | same | same | same | same | same | same | same | $22.27965 @ 200 (only break) | 0 |
| **Littelfuse KLKR025.T** (fast) | 200 kA @ 600 VAC | not published | **25 A row not published** (20 A = 900, 30 A = 1,720, "@ 200 kA") | **25 A curve published**, peak [PLOT]: 1.15 kA @ 4.7 kA, **1.17 kA @ 5 kA**, 1.33 kA @ 8.4 kA, **1.38 kA @ 10 kA** (÷ 2.3 ≈ 509 / 602 A apparent RMS) | no curve in DS | not printed | UL Listed E81895, CSA LR29862 | **$16.40748** (100 = $19.8851) | 15 |
| Littelfuse CCMR025.TXP (TD) | 200 kA @ 600 VAC (500 VDC) | not published | **25 A row not published** (20 A = 918, 30 A = 1,790, "@ 200 kA") | no 25 A column or curve; apparent RMS 20 A 355 / 447, 30 A 621 / 783 | ≈ 90 % / ≈ 81 % [PLOT; same curve as KLDR] | not printed | UL Listed E81895, CSA LR29862 | **$18.82642** | 320 |
| Littelfuse CCMR025.HXP | same | | | | | | | $22.6922 @ 200 | 0 |
| Eaton Bussmann LP-CC-25 (TD) | 200 kA @ 600 VAC | not published | not published | **25 A column**: apparent RMS **690 A @ 5 kA, 870 A @ 10 kA** (× 2.3 ≈ 1.59 / 2.00 kA peak per sheet note) | not in DS | 12 s min at 200 % [UNVERIFIED: Eaton spec page via RS] | UL Listed 248-4, **Guide JDDZ, File E4273**; CSA 1422-02, File 53787 | n/a (100 = $61.8903) | 6 |
| Eaton Bussmann KTK-R-25 (fast) | 200 kA @ 600 VAC | not published | not published | **No 25 A curve** (10/15/20/30 A only). Peak [PLOT]: 20 A 1.40 / 1.82 kA, 30 A 1.64 / 2.13 kA | not in DS | not printed | UL Listed JDDZ E4273; CSA 53787 | n/a (100 = $57.6346) | 0 (10 due 18-Nov-2026) |
| Eaton Bussmann FNQ-R-25 (TD) | 200 kA @ 600 VAC [UNVERIFIED, DigiKey/search] | DS not read | DS not read | DS not read | | | | n/a (100 = $69.0272) | 0 (10 due 13-May-2027) |
| Mersen ATDR25 (TD) | 200 kA AC, 100 kA DC (300 VDC) | not published | not published | not published | not in DS | not in DS | UL Listed 248-4 **E2137**; CSA C22.2 No. 248.4 | n/a (250 = $22.99892) | 51 |
| Mersen ATQR25 (TD) | 200 kA AC, 100 kA DC | not published | not published | not published | | | UL 248-4 E2137; CSA | n/a (250 = $23.1918) | 96 |
| Mersen ATMR25 (fast) | 200 kA AC, 100 kA DC (600 VDC) | not published | not published | not published | | | UL 248-4 E2137; CSA | **$19.396** | 10 |
| Eaton Edison HCTR25 / EDCC25 | spec sheet says both "10 kAIC" and "200,000a IR" | | | | | | "UL Listed, CSA" | not on DigiKey; Elliott spec sheet says **Status: Inactive** | [UNVERIFIED] |
| SIBA Class CC 25 A | not found | | | | | | | | |

Sources for section 2 (all read 2026-10-14):
- KLDR: Littelfuse KLDR Rev 092821, pp.1, 2, 4 ("Electrical Specification – Agency Requirements": 135 % = 60 min max, 200 % = 12 s min), 5 (I²t table), 6 (Current-Limiting Effects, derating), 8 (peak let-thru, 20 A / 30 A) [MIRROR: https://static.chipdip.ru/lib/254/DOC027254593.pdf]. Price and stock: https://www.digikey.com/en/products/detail/littelfuse-ibu/KLDR025-TXP/3740687 and https://www.digikey.com/en/products/result?keywords=KLDR025
- KLKR: Littelfuse KLKR Rev 062218, p.1 (ratings, approvals), p.2 ("Electrical Specifications" total clearing @ 200 kA; "Peak Let-Thru Curve" 12/15/20/25/30 A, drawing 05542001) [DigiKey-hosted copy: https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/1067/KLKR_Class_CC_Series_DS.pdf]. Plot calibration: decade gridlines at 100/1k/10k/100k/200k A (x) and 100…1M A (y). The 2.3 × available-peak diagonal reads 2.29 kA at 1 kA, which checks the calibration. Price: https://www.digikey.com/en/products/detail/littelfuse-inc/KLKR025-T/2517730
- CCMR: Littelfuse CCMR, Revised 10/10/2022, pp.2 (specs, approvals), 4 ("Electrical Specifications"), 5 ("Temperature Rerating Curve", "Current-Limiting Effects") [MIRROR: https://www.elliottelectric.com/Media/CCMR5-L$F]. Price: https://www.digikey.com/en/products/detail/littelfuse-inc/CCMR025-TXP/3740820, https://www.digikey.com/en/products/detail/littelfuse-inc/CCMR025-HXP/3740653
- LP-CC: Bussmann Data Sheet 1023 (10-2-02), p.1, "Current-Limiting Effects" table, 25 A column [MIRROR: https://www.farnell.com/datasheets/207472.pdf]. The current Eaton DS (https://www.eaton.com/content/dam/eaton/products/electrical-circuit-protection/fuses/data-sheets/bus-ele-ds-1023-lp-cc1.pdf) timed out. Price: https://www.digikey.com/en/products/result?keywords=LP-CC-25 (2041-1089-ND)
- KTK-R: Bussmann Data Sheet 1015 (0813), p.1 (agency), p.3 ("Current-Limitation Curves 10 to 30 Amps"; curve labels 30/20/15/10) [MIRROR: https://static.chipdip.ru/lib/016/DOC021016690.pdf]. Price: https://www.digikey.com/en/products/result?keywords=KTK-R-25
- FNQ-R: https://www.digikey.com/en/products/result?keywords=FNQ-R-25 (283-2481-ND). Datasheet (Eaton TD 1014) not reachable
- Mersen: ATDR https://pim.mersen.com/91C3610E476E4CD196245BC3BDDFB39B-1en.pdf; ATQR https://pim.mersen.com/78ABDA9D8C854B57A18C7508452DFD77-1en.pdf; ATMR https://pim.mersen.com/7F64737D5B0444DE87A1C4C79EF7BB97-1en.pdf (© 2025, "RATINGS" and "APPROVALS/STANDARDS" blocks). Prices: DigiKey 2378-ATDR25-ND, 2378-ATQR25-ND (https://www.digikey.com/en/products/detail/mersen-usa-newburyport-ma-l-l-c/ATQR25/21729071), 2378-ATMR25-ND
- Edison: https://static.elliottelectric.com/Media/HCTR25-EDN (distributor spec sheet) [UNVERIFIED]

**Answer to the key question.** Yes, there is a materially cheaper Class CC 25 A: **KLKR025.T at $16.41 at 500** (fast-acting, same Littelfuse UL/CSA files). But the real saving against the true KLDR price ($18.52) is $2.11, not the $13 implied by the repo's $29.41. No Class CC 25 A publishes a total clearing I²t, or a let-through at 5–10 kA, that **demonstrably** beats KLDR025: KLKR and CCMR publish no 25 A I²t row, Mersen publishes nothing, and LP-CC-25's let-through (690/870 A apparent RMS) is higher than the KLDR 20–30 A bracket (456–621 / 575–783). On published peak let-through, KLKR025's 25 A curve (≈ 1.17 / 1.38 kA) sits inside KLDR's 20–30 A bracket (1.05–1.42 / 1.32–1.80 kA), so it is "probably no worse", not proven better. KLKR's 20 A/30 A total clearing values (900/1,720) are almost identical to KLDR's (1,363/1,990 bracket around 1,710). The Class CC I²t figures are stated at 200 kA, not at 5–10 kA.

## 3. Holders and clips

| Part | For | Rating | Agency | $ @ 500 (DigiKey) | Stock | Source |
|---|---|---|---|---|---|---|
| **Littelfuse 01250003H** (current design, 125 series) | 13/32" (10.3 mm) midget / Class CC | **30 A max**; voltage not on the DS (DigiKey lists 250 V) | UR mark, E14721 (cell spans 105 and 125 series) | **$2.05726** (10 = $3.249) | 9,223 | DS Rev 02/07/18 p.1 [MIRROR: https://wmsc.lcsc.com/wmsc/upload/file/pdf/v2/lcsc/1810152114_Littelfuse-01250003H_C223911.pdf]; DigiKey F3306-ND https://www.digikey.com/en/products/result?keywords=01250003H |
| Keystone 3566 | 5AG 13/32" (10.3 mm), with end stops | **UL current rating 30 A**; voltage not stated; 0.030" tin-plated brass | "UL"; the catalog says clips **without** end stops are not UL recognized | **$0.4467** | 49,315 | Keystone catalog p.52: https://www.keyelco.com/userAssets/file/K75p52.pdf; DigiKey 36-3566-ND https://www.digikey.com/en/products/detail/keystone-electronics/3566/316035. Fit with the Class CC rejection cap: [UNVERIFIED] |
| Schurter CSO 0751.0507 (THT, tin) | 10.3 × 38 / 10.3 × 85 mm | **1500 V, 32 A**; ≈ 30 A at 50 °C, ≈ 29 A at 70 °C [PLOT] | UL Recognized **E39328**, to UL 4248-1 / CSA C22.2 No. 4248.1 | **$0.95594** | 1,145 | Schurter CSO DS (dated 22.07.2026) pp.1–3: https://www.schurter.com/en/datasheet/typ_CSO.pdf; DigiKey 486-3272-ND https://www.digikey.com/en/products/result?keywords=0751.0507 |
| OptiFuse CSG-01 | "13/32", end stops" | 250 V / 30 A (DigiKey columns) | not shown | $2.13 @ 1 only | 35,122 (marketplace) | DigiKey search; [UNVERIFIED] |
| **Littelfuse 01220088Z** (122 series, BeCu, tin) | 1/4" / 6.3 mm (lists 505, 506, 508 series) | **30 A max**; voltage not on DS (DigiKey lists 1 kV) | UR, E14721 | **$0.50532** | 46,519 | DS Rev 08/25/15 [MIRROR: https://mfgdatasheets.nlight.net/25-07361%20Littelfuse%2001220083Z.pdf]; DigiKey F3783-ND https://www.digikey.com/en/products/detail/littelfuse-inc/01220088Z/2498891 |
| Littelfuse 01220083Z (122, BeCu, silver) | 1/4" / 6.3 mm | 30 A max | UR, E14721 | $0.53564 | 48,117 | same DS; DigiKey F3782-ND https://www.digikey.com/en/products/result?keywords=01220083Z |
| Keystone 3AG/5 mm clips | 1/4" | UL 15 A only | | | | Keystone p.52 (excluded: under 25 A) |

No enclosed PCB holder for 10 × 38 rated ≥ 25 A / ≥ 250 VAC was found in this pass (Schurter OGN is 5 × 20 only).

## 4. Per-board cost at 500 pieces (DigiKey, 2026-10-14)

| Build | Fuse | 2 clips | Total |
|---|---|---|---|
| KLDR025.TXP + 2 × 01250003H (current) | 18.516 | 4.115 | **22.63** |
| KLDR025.TXP + 2 × Keystone 3566 (footprint change, fit unverified) | 18.516 | 0.893 | 19.41 |
| KLKR025.T + 2 × 01250003H | 16.407 | 4.115 | 20.52 |
| CCMR025.TXP + 2 × 01250003H | 18.826 | 4.115 | 22.94 |
| ATMR25 + 2 × 01250003H | 19.396 | 4.115 | 23.51 |
| 0505025.MXP + 2 × 01220088Z | 3.571 | 1.011 | **4.58** (saves $18.05 against the current build) |
| Bel 0ADEC9250-BE + 2 × 01220088Z | 2.763 | 1.011 | **3.77** (saves $18.86) |

## 5. What this does to the copper-ratio question (data only, no new estimates)

- **Reviewer note (2026-10-14):** the 355 A²s necks below are the stage-19 board's. On stage 29 the governing neck is
  1,697.7 A²s (`s29_necks.json`, `s21_necks.py` lim()), so Bel's 470 A²s gives a ratio of **3.61**, not 0.76
  (`f1_decision.py`). The Bel 470 A²s figure was re-read from the PDF (sha256 363ec204…, Electrical Specifications table).
- The only **published** clearing I²t for a 25 A, 6.3 × 32, 500 V / 30 kA ceramic fuse is Bel's **470 A²s** (at its 500 V interrupting test). That gives 355/470 = **0.76**, a ratio inside the decision record's assumed 0.56–1.63 band. A 2 × target of 940 A²s still fails the two 355 A²s necks and BR1's half-I²t rule (< 255 A²s).
- No equivalent number exists for the Littelfuse 505 (melt 210 A²s in current revs).

## 6. Could not verify

- Littelfuse 505 **current (10/16/23 or later) PDF**. Only a text mirror was available, with garbled table columns. The 25 A AIR and melt I²t were read from the 2019 PDF and only cross-checked against the 2023 text. The search index cites a "© 2024 … 10/24/24" revision that I could not open.
- Any **clearing I²t or let-through for the 505** (none found in any revision).
- **UL category codes** (JDYX2 for the 505 and Bel; JDDZ for Littelfuse/Mersen Class CC). JDDZ is printed only on the Eaton sheets. UL Product iQ was not consulted.
- **NMX/NOM** marks: only the 505's 2023 text says "UL/CSA/NMX". KLDR, KLKR, CCMR, Mersen, Eaton and Bel print none.
- **135 % opening time** for KLKR, CCMR, Mersen and Eaton (not printed); Class CC parts must meet UL 248-4 regardless.
- **KLKR025 and Mersen derating curves** (not in the sheets read). **Mersen** I²t and let-through (not in the 2025 sheets).
- **FNQ-R-25 datasheet** (Eaton site timed out). **Current Eaton LP-CC DS 1023** (only the 2002 Farnell copy was read).
- **Mouser, Newark, Arrow and LCSC** prices and stock (blocked or timed out). **DigiKey 500-piece breaks** for ATDR25/ATQR25 (shown only to 250) and LP-CC/KTK-R/FNQ-R (shown only to 100).
- Voltage ratings of the Littelfuse 122 and 125 clips are not on their datasheets (distributor fields only). Keystone 3566 voltage and its fit on the Class CC rejection end.
