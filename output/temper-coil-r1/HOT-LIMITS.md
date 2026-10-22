# Coil housing at 130 and 150 °C: what the datasheets say (read 2026-10-19)

Scope: the parts of the coil assembly that see winding temperature. Figures come from the sources named per row, read through web search results, not from
a purchased or measured part. Supplier grades are generic until a part is chosen, so each row says what is still unknown.

Winding mean temperature from the coil review's lumped model (`output/coil-review-2026-10-10/results/thermal-screen-actual-jets.json`, assumed
blower curve, not qualification): 22 A at expected R_ac 88–100 °C; 28 A 104–122 °C; 22 A at the R_ac acceptance limit 110–130 °C; 12.7 A fry hold
with 230 °C glass 113–131 °C; 28 A at the 0.23 Ω target 137–168 °C. Hot spots are not modelled.

| Part | Source | What it says | 130 °C | 150 °C | Still unknown |
|---|---|---|---|---|---|
| Stock Litz, RM Cybernetics 1000 × 0.05, OD 2.55 | [RM datasheet](https://www.rmcybernetics.com/files/pdf/Litz-Wire-Datasheet.pdf) | Thermal class 155, two layers polyester silk | OK, 25 K under the class | **Over the class** | Stock; class of the Elecify alternative |
| NEMA G-11 former (route A) | [Gund G-11 TDS](https://thegundcompany.com/wp-content/uploads/2025/05/NEMA-G-11-by-The-Gund-Co-TDS.pdf), [Piedmont MC511AF](https://www.piedmontplastics.com/resources/literatures/mc511af-grade-g-11) | Max continuous 155 °C (Gund); at least 50 % of room-temperature flexural strength retained at 150 °C (Piedmont) | OK | Inside the rating, with a stated strength loss | The machined supplier's own grade and its hot dielectric data |
| PPS-GF carrier (R43 BOM names no grade) | [AEP Techtron GF40](https://mcam.com/mam/54325/AEP-Techtron™%20GF40%20PPS_en_US.pdf), [Akro PPS GF 40](https://akro-plastic.com/en/product/akrotek-pps-gf-40-natural-8064-en) | 220 °C continuous allowable (20 000 h, Techtron); HDT/A 267 °C (Akro) | OK | OK | The actual grade and its UL RTI (none found) |
| Printed PC | Spool3D 130 °C, Materialise 127 °C, Garhem 124 °C, Bambu 117 °C (HDT at ~1.8 MPa) | HDT 117–141 °C depending on maker and annealing | **No**: at or past its HDT under load | **No** | Creep of wound turns under tension |
| Printed PA12-CF | [JLC3DP](https://jlc3dp.com/help/article/pa12-cf-plastic) 105 °C, [Spectrum](https://spectrumfilaments.com/wp-content/uploads/2024/11/en_tds_spectrum_pa12_cf15.pdf) about 150 °C | HDT sources conflict | Depends on grade | No | Grade, moisture |
| Printed ASA | Not looked up | Softens near 100 °C (typical) | No | No | |
| Bonding and NTC-pad silicone | [DOWSIL 736 TDS](https://www.aircraftspruce.ca/catalog/pdf/736TDS.pdf) | -65 to 260 °C continuous, 315 °C intermittent | OK | OK | Dielectric strength at temperature; only if this product is the one bought |
| PC95 ferrite bars | TDK PC95 sheet via [MHW](https://mhw-intl.com/wp-content/uploads/2021/01/TDK-EFD-Cores-PC95-PC47-With-Accessories.pdf) | Bs 530 mT at 25 °C, 410 mT at 100 °C, 380 mT at 120 °C; core loss minimum near 80–100 °C and rising by 120 °C | The coil review's ferrite estimate is about 85–110 °C | Ferrite itself is not at 150 °C | Bs and loss at 140 °C (the TDK graph was not readable); whether the bought bars are TDK PC95 |
| M4 ring lug, nylon-insulated TE PIDG | [RS listing](https://se.rs-online.com/web/p/ring-terminals/7105376) | 105 °C maximum | **No** | **No** | See the candidates below |
| Remington 260/38LITZ (decided, added 2026-10-21) | Remington product page | MW 80-C, 155 °C, unserved | OK | **Over the class** | Solder-strip temperature (not published) |
| Printed Formlabs Rigid 10K (route B, added 2026-10-21) | Formlabs TDS FLRG1001 Rev 04 | HDT 218 °C at 0.45 MPa, 110 °C at 1.8 MPa (UV + thermal cure) | Only at low stress: past the 1.8 MPa HDT | No | Creep under winding tension; bench and low power only, as for any printed former |
| **Panduit P14-8RHT6-C** bare ring lug (chosen 2026-10-21, `fit/README.md` §3) | Panduit product page | Brazed nickel-plated copper, 343 °C | OK | OK | Stock (DigiKey 0 on 2026-10-21) |
| Alpha Wire FIT-350 PVDF heat-shrink, two layers on the lug | Alpha customer spec | UL 224 150 °C / 600 V, −55 to 175 °C | OK | OK, at the UL rating | Acceptance in place of ASSEMBLY.md's "dual-wall" (power-stage owner) |
| Varflex Varglas Silicone Rubber C-1 No. 9 lead sleeve | Varflex data sheet | −73 to +200 °C, 2500 V min. avg. | OK | OK | — |

### Lug candidates for the 150 °C case (searched 2026-10-19; not ordered, no TE drawing read)
- **TE PIDG STRATO-THERM 50840**: PTFE insulation, nickel-plated copper barrel, 14 AWG (2.0–2.15 mm²), #8 (M4) stud, 288 °C ([Heilind](https://heilind.com/amp50840.html), [RS](https://benl.rs-online.com/web/p/ring-terminals/1641967)).
  - The barrel's copper area matches the Litz (1.96 mm² for 1000 × 0.05, 2.12 mm² for 270 × 0.10).
  - RS shows it temporarily out of stock; the suffix matters (Master Electronics lists 50840-1 as a #10-stud variant).
  - The RS listing gives a 4.0 mm ring hole, which is tight for an M4 screw: check TE's drawing.
  - Whether the barrel takes the stripped Litz bundle is for the scrap-crimp qualification (BUILD-AND-MEASURE W9) to show.
- **Availability of 50840 is poor (searched 2026-10-19, none of it a live stock check):**
  - TE's own datasheet (April and May 2024) lists 50840 and 50840-1 as ACTIVE, 1000-piece loose packaging.
  - Digi-Key marks 50840 obsolete and names 1577639-1 as the manufacturer's substitute. One Digi-Key listing for 1577639-1 says "#8, 12–14 AWG, PEEK" and out of stock/backorder; another snippet showed 1,698 in stock at $7.30. I did not verify that part's temperature rating or ring size.
  - RS UK showed 22 in stock at £2.79–3.20; RS Ireland showed it temporarily out of stock. TE's page for 50840-1 says "not currently available".
  - So 50840 is "best" only among what turned up. It is not a settled choice.
  - **1577639-1 (Digi-Key's substitute), second search 2026-10-19:** Digi-Key lists it as #8 stud, 12–14 AWG, PEEK insulation, beige, status active, limited stock with backorder and a 24-week standard lead time. No temperature rating appears for it. The sibling 1577638-1 (M3.5 stud) is listed by RS at 260 °C maximum, which suggests the series is rated near that but does not establish it for 1577639-1. Pull TE's drawing for 1577639-1 before relying on it; a 24-week lead time may rule it out for the first coils.
  - Another search for PTFE or other 260 °C ring lugs returned only the same 50840 RS listings (288 °C, ring ID 4.0 mm, OD 8.71 mm, length 21.82 mm), with no stock levels.
- **TE datasheet facts (50840-1, the #10 sibling):** tongue 0.79 mm, length 21.8 mm, compatible wire-insulation OD 2.03–3.81 mm (the 2.55 mm served Litz fits), 288 °C, partially insulated. The #8 50840's own datasheet was not retrieved.
- A CAD preview with the assumed dimensions marked is in `cad/lug_mock.py` (`cad/out/lug_50840_mock.step`, `renders/lug_50840_mock*.png`).
- **RS PRO DRNB** uninsulated M4 ring, brazed seam, 150 °C ([RS](https://uk.rs-online.com/web/p/products/8092228)), but its wire range is 0.5–1.5 mm², too small for this Litz.
- **Bare lug plus heat-shrink:** every dual-wall adhesive-lined polyolefin tubing found is rated 110–135 °C continuous, so none covers 150 °C. A fluoropolymer or silicone sleeve was not found in this search. **Superseded 2026-10-21:** the fit study found Alpha FIT-350 PVDF (UL 224 150 °C) and chose a bare brazed Panduit P14-8RHT6-C lug insulated with two layers of it. TE 1577639-1's drawing was read: PEEK 0–260 °C, insulation Ø6.05 max, and on J2 it touches CT T1, so it is rejected there (`fit/README.md` §3).
- **Stud size is M4, not unresolved (corrected 2026-10-19):** the "M6" in the R43 BOM is review item M6 (coil-stud spacing, `zapote/power-stage-120v/DECISIONS.md` line 242), not a thread. The J2/J5 terminal is Würth 7466004R, M4. Still open: DECISIONS line 245 requires insulated M4 lugs, while this study specifies non-insulated ones.

## Reading
- Sustained heating uses route A: G11 former, class-155 stock Litz (class 200 for the qualification coil), silicone bonding. The 130 °C winding limit stands.
- A printed former is for bench inductance work and low power only.
- Ring lugs were the weakest link on the list (nylon-insulated PIDG lugs are rated 105 °C). The 2026-10-21 choice (bare 343 °C lug + two layers of 150 °C PVDF) moves the limit to the shrink's 150 °C UL rating.
- Not covered: hot spots, thermal cycling, comb-tooth creep, ferrite at 140 °C.
