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
| M4 ring lug, nylon-insulated TE PIDG | [RS listing](https://se.rs-online.com/web/p/ring-terminals/7105376) | 105 °C maximum | **No** | **No** | A 150 °C part: the BOM allows a moulded lug or a bare lug plus at least 150 °C dual-wall heat-shrink; none was found or chosen |

## Reading
- Sustained heating uses route A: G11 former, class-155 stock Litz (class 200 for the qualification coil), silicone bonding. The 130 °C winding limit stands.
- A printed former is for bench inductance work and low power only.
- Ring lugs are the weakest link on the list: nylon-insulated PIDG lugs are rated 105 °C.
- Not covered: hot spots, thermal cycling, comb-tooth creep, ferrite at 140 °C.
