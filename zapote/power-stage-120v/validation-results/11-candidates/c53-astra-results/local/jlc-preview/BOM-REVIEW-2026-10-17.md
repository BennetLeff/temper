# JLC SMT order, BOM review step (read-only snapshot, 2026-10-17 ~10:40)

Page `cart.jlcpcb.com/smt-order/?pcbFileNo=…`, "native-21-gerbers", step "Bill of Materials" (the CPL / "Component Placements"
step had not been reached; no CPL uploaded when this was read). Gerbers: `fab/native-21-gerbers.zip` (a6afd37a…). BOM:
`fab/bom-jlcpcb.csv`. The page quotes **5 boards** (quantities below are for 5 boards). Screenshot of the bottom of the table:
`shots/bom-review-bottom-2026-10-17.jpg`. Page text read through Claude in Chrome; nothing was clicked on this page by the agent.

**JLC's counts:** 95 parts detected, **85 confirmed, 8 inventory shortage, 2 not selected**.

## JLC marks these 8 lines "shortfall" (matched to an LCSC part, no stock at 5 boards)
| Designators | MPN / LCSC | Need (5 boards) | JLC stock | Our BOM says |
|---|---|---:|---|---|
| C5, C6 | B32676G1905K000 / C3802167 | 10 | 0 (10 short) | consign |
| D3, D17 | 30KPA150CA / C19111562 | 10 | 0 (10 short) | consign |
| F1 | KLDR025.TXP / C187688 | 5 | 0 (5 short) | consign |
| F2 | 3403.0279.23 / C3163739 | 5 | 0 (5 short) | JLC (Extended), distributor stock only |
| J2, J5 | 7466004R / C6708126 | 10 | 0 (10 short) | JLC (Extended), distributor stock only |
| J6 | 1704004 / C5481600 | 5 | 0 (5 short) | JLC (Extended), distributor stock only |
| L1 | B82726S2243A020 / C7084710 | 5 | 0 (5 short) | consign |
| Q2, Q3, Q5, Q6 | IPW65R018CFD7 (XKSA1) / C3289047 | 20 | 6 (14 short) | JLC (Extended), 4-6 at JLC, DigiKey 459 |

## Unmatched (not selected): the pre-order button is offered
- C21, C22, C23, C151, C152: B32643H8104J000, footprint Bank_Film_DualPitch_P22.5_P27.5_Radial.
- U41, U42: R24C2T25/R-R, footprint RECOM_SSOP-36_7.5x12.83mm_P0.65mm_ReviewOnly.

## Our "consign" lines that JLC matched WITH stock (source JLCPCB, Extended)
- **C1, C2** R463N410050N1K → C3299886, 10 for 5 boards.
- **J3, J11** B2P3-VH(LF)(SN) → C160745, 11 for 5 boards.

Everything else (the other 75 lines) is matched with JLCPCB stock, including through-hole parts: BR1 (C526644), C3 / C4 (C7170908),
C38-C41 (C125402), J1, J4, PS2, R130, RV1, plus all passives and ICs. U5 (LM4050, 5 needed) and T1 (CST3015, 5 needed) matched.

## What this means (read, not yet acted on)
1. JLC will not place the 8 shortfall lines without stock; each needs consigned parts, a pre-order / global-sourcing route, or removal
   from the JLC BOM. Our PROTOTYPE-LOT already treats F1, L1, C5 / C6, D3 / D17, the bank and U41 / U42 as consigned or hand-assembled,
   but F2, J2 / J5, J6 and Q2-Q6 appear as JLC lines in `bom-jlcpcb.csv` while JLC shows no stock for them.
2. JLC has stock of C1 / C2 and J3 / J11, so those four hand-solder lines could be JLC-placed instead (fewer through-hole hand parts).
3. The "pre-order" button on the two unmatched lines may let JLC source the bank and U41 / U42; whether JLC places those parts is
   not confirmed.
4. Quantities here are for 5 boards; the lot is 10-20.
