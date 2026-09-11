# Current-sense source pack

Read-only review date: 2026-09-11. Source entry is
`elec/src/current_sense_unit.ato:CurrentSenseUnit`, compiled in
`source-build-03` with 21 flat components. Datasheet and product links are
the manufacturer or distributor pages recorded in `source-pack.json`.

| References | Qty | Manufacturer MPN | Value | Native footprint | Datasheet / product | Availability evidence |
|---|---:|---|---|---|---|---|
| T1 | 1 | Coilcraft CST3015-100ED | — | `temper:CST3015_Datasheet2025` | [datasheet](https://www.coilcraft.com/getmedia/df31d5fe-b3af-4586-82a7-7b773ac9f838/cst3015.pdf) / [product](https://www.coilcraft.com/en-us/products/transformers/power-transformers/current-sensing/cst3015/cst3015-100e/) | Manual confirmation: product page mixes ready-to-ship language with an unavailable selected configuration. |
| J1 | 1 | `NON_PURCHASED_BARE_LANDS` | — | `lib:LitzPad_15A` | Root-authored land pattern; no vendor page | Not purchased; no connector or ampacity claim encoded. |
| R1 | 1 | YAGEO RC1206FR-071R5L | 1.50 ohm ±1% | `R_1206_3216Metric` | [RC datasheet](https://yageogroup.com/content/datasheet/asset/file/PYU-RC_GROUP_51_ROHS_L) / [DigiKey](https://www.digikey.com/en/products/detail/yageo/RC1206FR-071R5L/728440) | DigiKey search evidence: 12,640 in stock, 17-week lead time. |
| R4 | 1 | YAGEO RC1206FR-071KL | 1 kohm ±1% | `R_1206_3216Metric` | [RC datasheet](https://yageogroup.com/content/datasheet/asset/file/PYU-RC_GROUP_51_ROHS_L) / [DigiKey search](https://www.digikey.com/en/products?s=RC1206FR-071KL) | Manual confirmation: exact live stock row was not returned. |
| C1,C2 | 2 | Murata GRM31C5C1H104JA01L | 100 nF ±5% C0G 50 V | `C_1206_3216Metric` | [datasheet](https://search.murata.co.jp/Ceramy/image/img/A01X/G101/ENG/GRM31C5C1H104JA01-01A.pdf) / [product](https://www.murata.com/en-us/products/productdetail?partno=GRM31C5C1H104JA01%23) / [DigiKey](https://www.digikey.com/en/products/detail/murata-electronics/GRM31C5C1H104JA01L/3845702) | DigiKey search evidence: 54,742 in stock, 17-week lead time. |
| R2,R3,R6,R7 | 4 | Panasonic ERA3AEB103V | 10 kohm ±0.1% | `R_0603_1608Metric` | [Panasonic](https://na.industrial.panasonic.com/products/resistors/smd-chip-resistors/series/36034/model/46550) / [DigiKey](https://www.digikey.com/en/products/detail/panasonic-electronic-components/ERA-3AEB103V/1465878) | DigiKey search evidence: 219,134 in stock, 41-week lead time. |
| R5,R8 | 2 | Panasonic ERA3AEB3741V | 3.74 kohm ±0.1% | `R_0603_1608Metric` | [Panasonic](https://industrial.panasonic.com/ww/products/pt/high-precision-chip-resistors/models/ERA3AEB3741V) / [DigiKey](https://www.digikey.com/en/products/detail/panasonic-industry/ERA-3AEB3741V/3075947) | DigiKey search evidence: 10,099 in stock, 33-week lead time. |
| D1,D2 | 2 | Nexperia BAT54H,115 | 30 V, 200 mA | `D_SOD-123F` | [datasheet](https://www.nexperia-semiconductor.com/pdf-a4/bat54h%2C115.pdf) / [product](https://www.nexperia.com/product/BAT54H) / [DigiKey](https://www.digikey.com/en/products/detail/nexperia-usa-inc/BAT54H-115/1127168) | DigiKey search evidence: 0 in stock; expected 2027-05-03, 30-week lead time. |
| U1,U2 | 2 | Texas Instruments TLV3201AIDBVR | — | `SOT-23-5` | [datasheet](https://www.ti.com/lit/ds/symlink/tlv3201.pdf) / [TI product](https://www.ti.com/product/TLV3201/part-details/TLV3201AIDBVR) / [DigiKey](https://www.digikey.com/en/products/detail/texas-instruments/TLV3201AIDBVR/3188691) | DigiKey search evidence: 0 in stock; expected 2026-10-29 and 2026-11-02, 16-week lead time. |
| U3 | 1 | Texas Instruments SN74HC4075DR | — | `SOIC-14_3.9x8.7mm_P1.27mm` | [TI family page](https://www.ti.com/product/CD74HC4075) / [family datasheet](https://www.ti.com/lit/gpn/cd74hc4075) | Manual confirmation: exact `SN74HC4075DR` listing was not found. Do not substitute CD74HC4075 or HCS4075 without source identity approval. |
| C3,C4,C5 | 3 | KEMET C0603C104K5RACTU | 100 nF ±10% X7R 50 V | `C_0603_1608Metric` | [specification](https://search.kemet.com/download/specsheet/C0603C104K5RACTU) / [DigiKey](https://www.digikey.com/en/products/detail/kemet/C0603C104K5RACTU/1465623) | DigiKey search evidence: 6,484,964 in stock, 12-week lead time. |
| J2 | 1 | JST B4B-XH-A(LF)(SN) | — | `JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical` | [XH datasheet](https://www.jst.com/wp-content/uploads/2021/01/eXH.pdf) / [JST lookup](https://www.jst-mfg.com/product/index.php?lang=2&search_product=B4B-XH-A&type=1) / [DigiKey](https://www.digikey.com/en/products/detail/jst-sales-america-inc/B4B-XH-A/1651047) | DigiKey search evidence: 112,324 in stock, 16-week lead time. |

## Footprint identity check

The compiled source manifest resolves the generic resistor default to
`Resistor_SMD:R_0603_1608Metric`. All six ERA parts are 0603. R1 and R4
explicitly select 1206, so the current source build has no ERA footprint
mismatch. Recheck this if the generic `Resistor` default changes.

Availability is a dated distributor snapshot, not a purchase or a promise of
future supply. Exact manufacturer identity remains authoritative when a
distributor result is absent.

## Packaging and availability follow-up

The exact packaging review is recorded in
`packaging-availability-review.json`.

* `TLV3201AIDBVT` is confirmed by TI as the same DBV SOT-23-5 package and
  electrical family as `TLV3201AIDBVR`, but both exact variants were at zero
  US DigiKey/Mouser stock on 2026-09-11. Keep the existing MPN and verify
  regional stock manually before sourcing.
* Nexperia's BAT54H datasheet confirms `BAT54H,135` is the same SOD123F
  BAT54H type with the 10,000-piece reel option versus 3,000 for `,115`.
  No live DigiKey/Mouser listing for `BAT54H,135` was found; manual Nexperia
  or distributor confirmation is required.
* `CD74HC4075M96` is an active TI SOIC-14 orderable with 6,622 at DigiKey and
  2,465 at Mouser in the dated snapshot. It is a candidate for the source's
  `SN74HC4075DR` row pending circuit-owner approval; the source MPN was not
  changed here.
