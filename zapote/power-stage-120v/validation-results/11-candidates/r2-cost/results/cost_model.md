Baseline stage 20 power board: S = 234.84 (scorecard 234.83), B = 222.78

## Top 25 lines (S rank), with B and note

| # | Designators | MPN | qty | S $ | B $ | class | note |
|---|---|---|---|---|---|---|---|
| 1 | Q2,Q3,Q5,Q6 | IPW65R018CFD7 | 4 | 40.70 | 40.70 | Extended/THT |  |
| 2 | F1 | KLDR025.TXP | 1 | 29.41 | 29.41 | consign/THT |  |
| 3 | D3,D17 | 30KPA150CA | 2 | 19.64 | 19.64 | consign/THT |  |
| 4 | J2,J5,J7,J8,J9,J10 | 74650074 | 6 | 16.38 | 16.38 | Extended/THT | JLC cheaper but stock 0 < 3000 |
| 5 | U41,U42 | R24C2T25/R-R | 2 | 14.74 | 14.36 | consign/SMD | DK T&R 750 break $7.18 (1000 pcs); survey used the 250 break |
| 6 | C5,C6 | B32676G1905K000 | 2 | 12.34 | 12.34 | consign/THT |  |
| 7 | T1 | CST3015-200ED | 1 | 11.43 | 11.43 | consign/SMD | JLC cheaper but stock 64 < 500 |
| 8 | C21,C22,C23,C151,C152 | B32654A1104J000 | 5 | 9.97 | 9.97 | consign/THT | JLC cheaper but stock 104 < 2500 |
| 9 | L1 | B82726S2203A020 | 1 | 9.88 | 9.88 | Extended/THT | JLC cheaper but stock 0 < 500 |
| 10 | PS1 | IRM-20-15 | 1 | 8.40 | 6.36 | Extended/THT | JLC covered |
| 11 | PS2 | IRM-20-24 | 1 | 8.40 | 6.36 | Extended/THT | JLC covered |
| 12 | U9,U32,U33,U34 | ISO7710DWR | 4 | 5.15 | 5.15 | Extended/SMD |  |
| 13 | U26 | TPS7A4700RGWR | 1 | 4.23 | 3.96 | Extended/SMD | JLC covered |
| 14 | BR1 | GBJ2510-F | 1 | 4.02 | 0.66 | Extended/THT | DK top break 105+: $1.82 (survey used the qty-1 $4.02) |
| 15 | U3,U37,U38,U39 | TPS70950DBVR | 4 | 3.20 | 1.18 | Extended/SMD | JLC covered |
| 16 | C9,C90,C91,C92,C93,C16,C94,C | UMK325AB7106KM-T | 24 | 2.88 | 5.25 | Extended/SMD | est->JLC |
| 17 | C126,C127,C128,C129 | 6SVPC220M | 4 | 2.78 | 2.78 | Extended/SMD |  |
| 18 | J6 | 1704004 | 1 | 2.37 | 2.37 | Extended/THT | JLC cheaper but stock 0 < 500 |
| 19 | U6,U7,U10,U11,U12 | TLV3201AIDBVR | 5 | 2.25 | 3.07 | Extended/SMD | est->JLC |
| 20 | U1,U2 | UCC21550BDWKR | 2 | 2.07 | 2.07 | consign/SMD |  |
| 21 | F2 | 3403.0171 | 1 | 1.80 | 1.80 | consign/SMD |  |
| 22 | C38,C39,C40,C41 | B32652A0104K000 | 4 | 1.80 | 1.80 | Extended/THT | JLC cheaper but stock 310 < 2000 |
| 23 | J4 | 0430451612 | 1 | 1.69 | 0.81 | Extended/THT | JLC covered |
| 24 | J1 | 1711725 | 1 | 1.49 | 0.71 | Extended/THT | JLC covered |
| 25 | U4 | AMC1311BDWVR | 1 | 1.43 | 1.42 | Extended/SMD | JLC covered |

Top-25 share of S: 93.0 % (218.48 of 234.84)

## Proposal deltas per board at 500 (negative = saving)

| id | proposal | dS | dB | d lines | d place. | risk | SAFETY |
|---|---|---|---|---|---|---|---|
| R2-01 | Delete D3/D17 30KPA150CA clamp pair (bus C is 18.4 uF) | -19.64 | -19.64 | -1 | -2 | med-high | yes |
| R2-02 | Keep D3/D17 but source Brightking 30KPA150CA-B (C522439, ref price, stock 0) | -7.88 | -7.88 | 0 | 0 | med | yes |
| R2-03 | BR1 GBJ2510-F -> MDD GBJ2510 (C27523) | -3.75 | -0.38 | 0 | 0 | low | no |
| R2-04 | 24x UMK325AB7106KM-T -> Samsung CL32B106KBJNNNE (C138687) | +0.90 | -1.47 | 0 | 0 | low-med | no |
| R2-05 | 4x 6SVPC220M -> 6SVPC220MV (C128504, lower ESR) | -0.78 | -0.78 | 0 | 0 | low | no |
| R2-06 | U41/U42 R24C2T25 priced at the 1000-pc break not the 250 break | -0.38 | -0.00 | 0 | 0 | none | no |
| R1-g02A-studs | g02-g03 A: J7-J10 leave the mains build (4 of 6 studs), repriced | -10.92 | -10.92 | 0 | -4 | med | yes |
| R1-g06P1 | g06 P1: delete PS1 (IRM-20-15) | -8.40 | -6.36 | -1 | -1 | med | yes |
| R1-g05P2-iso | g05-g07 P2, ISO part only: U33/U34 ISO7710 -> ISO6721FB (rest of P2 in their file) | -1.80 | -1.80 | 0 | 0 | med-high | yes |
| R1-g04P1-T1 | g04 P1: T1 CST3015-200ED at the JLC listing price (64 pcs only; Coilcraft volume price unquoted) | -4.12 | -4.12 | 0 | 0 | med | yes |
| R1-g01P1-L1 | g01 P1: L1 -> KEMET SC-20-201 (g01's DK EUR5.37@510 x1.16) | -3.68 | -3.68 | 0 | 0 | med | yes |
| R1-g04P4 | g04 P4: U10+U11 TLV3201 -> one TLV3202 (JLC ladder) | -0.30 | -0.63 | 1 | -1 | low-med | no |
| R2-07 | C5/C6 B32676G1905K000: quote at the LCSC reference ($1.23 at 500 vs DK $6.17) | -9.93 | -9.93 | 0 | 0 | low (price only) | no |
| R2-08 | L1 B82726S2203A020: quote at the LCSC reference ($2.11 at 500 vs DK $9.88) | -7.78 | -7.78 | 0 | 0 | low (price only) | no |
