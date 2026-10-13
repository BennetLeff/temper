# R2-cost: cost-down proposals for native-21 stage 20 (2026-10-13)

Folder: `validation-results/11-candidates/r2-cost/`. Nothing outside it was edited. Every number comes from a script here (`python3 -I scripts/<name>.py`, offline after the first run because the JLC replies are cached in `raw/`) or from a cited page. `UNVERIFIED` marks what is not data.

| Script | Output | What it does |
|---|---|---|
| `scripts/jlc_lib.py` | `raw/` | JLC part API helpers (detail `cart.jlcpcb.com/shoppingCart/smtGood/getComponentDetail?componentCode=Cxxxx` gives price ladder, stock, library type; search `jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList` POST `{keyword,currentPage,pageSize}`). `python3 -I jlc_lib.py s "<kw>"` or `... C123 C456`. |
| `scripts/reprice_baseline.py` | `results/reprice_baseline.json` | Every STOCK row with an LCSC code against the live JLC ladder at qty x 500, with stock coverage. |
| `scripts/cost_model.py` | `results/cost_model.json`, `results/cost_model.md` | Stage-20 baseline (reproduces the scorecard 234.83), the two price bases, the top-25 table and every $ delta below. |
| `scripts/bus_peak_no_clamp.py` | `results/bus_peak_no_clamp.json` | R2-01: bus peak with the clamp deleted. |
| `scripts/fet_downsize_check.py` | `results/fet_downsize_check.json` | Why the FETs cannot be downsized (R2-X1). |

## 0. Findings that change the cost picture (read first)

1. **The $234.83 is soft in both directions.** Two price bases (script `cost_model.py`): **S** = the scorecard (234.84), **B** = best-known (222.78). B replaces class-default estimates by the JLC ladder (the 1210 10 uF caps are really $5.25 not $2.88, the TLV3201 $3.07 not $2.25, but MMBT3904/TL431/AO3400 etc. are $0.03-0.15 not $0.40-0.45) and uses JLC where it is cheaper and stocked for 500 boards. **Three survey errors**: BR1 GBJ2510-F is priced at the qty-1 DigiKey price ($4.02); the DK break at 105 is **$1.82** and JLC is **$0.66** (DK page, https://www.digikey.com/en/products/result?keywords=GBJ2510-F); the R24C2T25 line uses the 250 break ($7.37) while 1000 pieces sit on the $7.18 T&R break and 1500 pieces (750 boards) on **$6.24** (https://www.digikey.com/en/products/result?keywords=R24C2T25%2FR-R); PS1/PS2 are $6.36 at LCSC with 1,498 / 7,180 in stock (covers 500 boards), $8.40 at DK.
2. **The owner's $200 target is not reachable from the lines the board has today by swaps.** Top 25 lines are 93 % of the S total. The sum of everything below that is low-risk (R2-03/04/05 + basis fixes) is about $5-12; the rest needs the bus clamp deletion (R2-01, $19.6), the round-1 structural items (studs $10.9, PS1 $6.4-8.4, filter, T1) and quotes for the three zero-stock "consign" lines whose LCSC reference prices are 4-5x below DigiKey (C5/C6, L1, TVS). **PCB fabrication and JLC assembly are not in the $235**, and for a 290 x 190 mm, 4-layer, 2 oz/2 oz, ENIG board with 749 epoxy-filled-and-capped vias they are likely the larger lever (section 3).
3. **JLC "global sourcing" cannot be priced offline.** The `C99xxxxxxxx` "JLCPCBAssembly" entries (`R24C2T25/R-R` C9900245652, `CST3015-300ED` C9900254294, `HLK-20M24` C9900094634) return placeholder ladders $0.0397/$0.0204 (`raw/detail_C99*.json`); the price is set at BOM quote. Only R24C2T25 is one of our consign lines. Whether global sourcing beats consign (DK price + freight + JLC kitting) must come from a JLC BOM quote with those lines marked; I do not claim a number.

## 1. Top-25 cost lines (stage 20 power board, per board at 500)
 (S rank), with B and note

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


S = scorecard basis, B = best-known basis (definition in `cost_model.py`). "JLC cheaper but stock N < M" means the listing is cheaper but cannot cover 500 boards: it is a quote lead, not a saving.

## 2. Ranked proposals

Ranked by $ saved per board at 500 on basis B (basis S in brackets). New proposals are R2-xx; re-priced round-1 items are R1-xx (same two bases, computed by `cost_model.py`; the lead orders the lot from one table).

| Rank | ID | Change | B $ | S $ | Lines / placements | Metrics touched | Risk / effort | SAFETY |
|---|---|---|---|---|---|---|---|---|
| 1 | R2-01 | Delete D3/D17 30KPA150CA (bus C already 18.4 uF) | -19.64 | -19.64 | consign -1, BOM -1, place. -2 | `parts_usd_at_500`, `hand_or_consign_lines`, `zero_stock_lines`; no performance metric moves | med-high / schematic + audit.rs, no copper | **yes** |
| 2 | R1-g02A | J7-J10 bring-up studs leave the mains build (g02-g03 A) | -10.92 | -10.92 | place. -4 | cost; fuse/DC-loss metrics per g02-g03 | med / re-layout | yes |
| 3 | R2-07 | C5/C6 quote at the LCSC reference (6.17 -> 1.23 each) | up to -9.93 | -9.93 | 0 | cost | low / quote | no |
| 4 | R2-08 / R1-g01P1 | L1: TDK at the LCSC reference (2.11) **or** KEMET SC-20-201 (g01 P1) | -7.78 or -3.68 | same | 0 | cost; g01 P1 also `emi_min_margin_dB`, `leakage_touch_mA` | low (quote) / med | g01 P1 yes |
| 5 | R1-g06P1 | Delete PS1 | -6.36 | -8.40 | BOM -1, place. -1 | cost, leakage, B3 (g06) | med / re-layout | yes |
| 6 | R1-g04P1 | T1 at the JLC listing price (64 pcs only) | -4.12 if quoted | same | 0 | cost | med / quote | yes (protection input) |
| 7 | R2-02 | **Only if R2-01 is rejected**: Brightking 30KPA150CA-B (C522439), or a unidirectional 30KPA150A (C1976335, ref $1.86) | -7.88 (-15.9 uni.) | same | 0 | cost | med / quote + owner approval | yes |
| 8 | R2-03 | BR1 GBJ2510-F -> MDD GBJ2510 (C27523): stock 27,087 vs 1,589 | -0.38 (vs corrected DK 1.82: -1.55) | -3.75 | 0 | cost | low / BOM | no (BR1 is sacrificial, DECISIONS 22) |
| 9 | R1-g05P2 | ISO6721FB for U33/U34 (ISO part only; their other savings stay in their file) | -1.80 | -1.80 | 0 | cost, `zero_stock_lines` | med-high / re-layout | yes |
| 10 | R2-04 | 24x 10 uF 50 V 1210: Taiyo UMK325 -> Samsung CL32B106KBJNNNE | -1.47 | +0.90 | 0 | cost, stock (3,923 -> 45,882 vs 12,000 needed) | low-med / BOM | no |
| 11 | R2-05 | 4x 6SVPC220M -> 6SVPC220MV | -0.78 | -0.78 | 0 | cost, stock 13 -> 845 | low / BOM | no |
| 12 | R1-g04P4 | U10+U11 -> one TLV3202 | -0.63 | -0.30 | BOM +1, place. -1 | cost | low-med / re-layout | no |

**Basis fixes with no design change** (S -> B, free): BR1 qty-1 price error -3.36; PS1 + PS2 -4.08 (LCSC, covered); TPS70950 x4 -2.02 (JLC 0.295 each, 18,232 stock); J4 -0.88, J1 -0.78; R24C2T25 break -0.38; the estimate lines go the other way (+2.4 for the 1210 caps, +0.82 for TLV3201). Net 234.84 -> 222.78 (-12.06).

Stacking (non-overlapping): R2-01 + R1-g02A + R1-g06P1 + R2-03/04/05 + R1-g05P2 iso + R1-g04P4 = **-41.98 on B**, giving 222.78 -> **180.8** for the power board; the three quote-dependent items (R2-07, R2-08, R1-g04P1) are another up to -21.8 -> about 159. The controller (S 52.9) and UI (S 26.2) boards are not in these numbers and have the same estimate inflation (JLC ladder lines in `reprice_baseline.json`, e.g. 0603 resistors at $0.003 vs the $0.50 class default in the UI sheet).

### R2-01. Delete the DC-link TVS pair D3/D17 (SAFETY, new)

**Change.** Remove D3, D17 (2 x 30KPA150CA, Good-Ark, DK $9.82 each, consign, P600 footprints at (254.00, 266.70) and (270.54, 283.24)). R3/R4 stay as the bleed string (their midpoint net `BUSBLEED_MID` becomes a plain resistor junction). No other part changes; copper is unchanged (two footprints go empty;  the D3 row frees the two P600 footprints). Edits outside the board: `audit.rs` lines 295-296 (`BARRIER_PARTS`-style part check for `tvs_bus`, `tvs_bus_b`), 747-755 (pin expectations) and the negative control at 1508-1515 ("tvs_bus missing"), `parts.ato` `BusTvs30kpa150` import, `power_stage_120v.ato` lines 685-691, DC-LINK-CLAMP.md, ALT-D3 status, and the 2026-10-09 stage-14 item 3.

**Mechanism.** The clamp was sized for a 5.8 uF bus (tank + 500 uH line-L event: 578 V with no clamp, ALT-D3 s1.2). Stage 14 already raised the bus to 2 x 9 uF = 18.4 uF (C5/C6 = B32676G1905K000), and ALT-D3 s3.1 (option C) states for exactly this bus: tank event at most 359 V, tank + 500 uH line 387 V, 1 / 2 / 4 kV DM surge **with no clamp** 356 / 386 / 410 V, and "this removes the clamp's role in every modelled event". The recommendation there was "keep option A as the backstop"; I price that backstop at $19.64 per board for events nobody has modelled. `bus_peak_no_clamp.py` re-derives the tank + line case in closed form (self-check against ALT-D3: 385.5 vs 387 V, 365.3 vs 359 V, 574 vs 578 V on the old bus), then adds capacitor tolerance: worst corner of the three events (V0 286 V static-OVP start, 500 uH / 30 A line, C = -19 % i.e. -10 % K tolerance and -10 % ageing) is **450.7 V**, against the 520 V die-VDS screen (DECISIONS stage-14 item 3) and a 650 V FET. Margin 69 V at that stacked corner; 110 V at nominal C and V0 198 V (385 V).

| Event | With 30KPA150CA pair (ALT-D3 A, 5.8 uF) | No clamp, 18.4 uF (ALT-D3 s3.1) | Rating |
|---|---|---|---|
| Tank return, V0 286 V | 400 V | 359 V (script 365 V) | screen 520 V |
| Tank + 500 uH/30 A, V0 198 V | 400 V | 387 V (script 385 V; -19 % C: 411 V) | 520 V |
| 1 / 2 / 4 kV DM surge through RV1 | 445 / 488 / 481 V | 356 / 386 / 410 V | 520 V; C21-C23 TDK 1.6 kV, C38-C41 1 kV |
| Static OVP / worst stacked corner | n/a | 451 V (script) | 520 V |

(Sources: ALT-D3 sections 1.1-1.3, 3.1 in `08-manufacturing-package/native-21/sourcing/alt-circuits-2026-10-09/ALT-D3.md`; the surge numbers are ALT-D3's simulation, not re-run here.) Note what the pair buys at 5.8 uF is worse than what the bus buys at 18.4 uF at every row.

**Scorecard effect.** `parts_usd_at_500` -19.64; `hand_or_consign_lines` -1; `bom_lines` -1; `placements` -2; `zero_stock_lines` -1 and `single_source_lines` -1 if the 30KPA150CA lines are counted there (DK "not normally stocked"); `leakage_touch_mA`, `emi_min_margin_dB`, D5, Kelvin, B3: unchanged (the TVS leakage 2 uA at 150 V is nowhere in the leakage budget). No performance metric moves; the card changes only on the cost side.

**Interfaces disturbed.** BUS_P / HV_RET / BUSBLEED_MID (G02, G03): G03's F6/S4 decks use the bulk node explicitly (ALT-C5C6) and never modelled D3 conducting, so nothing to rerun there; G02 owns the footprint row and R4 (moved for D3 at stage 14). G01: RV1 (TMOV20RP175E, 135 J) carries the surge alone: ALT-D3 s1.3 already has it carrying 245-750 A with the clamp fitted, so the duty does not change, but its residual voltage is now the bus peak (386-410 V above). G08: U7 bus OVP comparator is the only over-voltage detector left (unchanged). Bench: the "bench bus stays <= 150 V DC until the D3 pulse qualification passes" rule (DECISIONS stage-14 item 3) changes to "until the no-clamp pulse test passes".

**SAFETY.** This removes a protection device. What keeps it safe: the modelled events stay 70-110 V under the screen on the same capacitor that is already in the design; the clamp's remaining job is events outside the model. **Needs the certifier and a bench surge run** (IEC 61000-4-5 1 kV and 2 kV line-line with the bus at 198 V and a gate-off during the surge, capture BUS_P) before this is accepted; the lab chooses the surge level (DC-LINK-CLAMP.md). Not covered: lab surge levels above 4 kV, ring waves, repeated faults, source impedance outside 250-500 uH, and IPW65R018CFD7 avalanche rating (datasheet not read). If the lab asks for a backstop, R2-02 is the fallback and AK3-380C-Y is not an option (DK $48.88, https://www.digikey.com/en/products/result?keywords=AK3-380C-Y). Also depends on C5/C6 staying at 9 uF each: a cap swap back to 5.8 uF re-opens the 574 V case.

**Risk** med-high; **effort** schematic + audit.rs + doc edits, then chain to confirm nothing moves; **rank** #1, -$19.64, -1 consign line.

### R2-02. If R2-01 is rejected: source the clamp pair cheaper

Same ratings, other brand/polarity. All LCSC listings have stock 0, so the prices are references, not quotes: Brightking **30KPA150CA/B C522439** $5.88 at 100+ (Good-Ark's DK listing is $9.82; Littelfuse $16.58; MDE $18.50: https://www.digikey.com/en/products/result?keywords=30KPA150CA), Littelfuse **30KPA150A C1976335** (unidirectional) $1.86 at 500, Brightking 30KPA150A/B C522438 $7.01.

| Parameter | Good-Ark 30KPA150CA (built; ALT-D3 p.3) | Brightking 30KPA150CA/B (JLC C522439 listing) | Littelfuse 30KPA150A (C1976335 listing) |
|---|---|---|---|
| Standoff VRWM | 150 V | 150 V | 150 V |
| V(BR) min | 167.6 V @ 5 mA | 167.6 V | 184.36 V |
| Vc @ Ipp | 233.4 V @ 129.8 A | 233.4 V @ 129.8 A | 233.4 V @ 129.8 A |
| Polarity | bidirectional | bidirectional | **unidirectional** (the bus never reverses; two in series both cathode-to-BUS_P) |
| Leakage | 2 uA | 2 uA | 2 uA |

Delta -$7.88 (Brightking) or about -$15.9 (Littelfuse unidirectional, if the $1.86 holds). Requires owner approval of the brand (DC-LINK-CLAMP no-silent-substitution rule), the tempco (Good-Ark and Littelfuse publish none, ALT-D3 s2.1), and a datasheet read (`lcsc.com/datasheet/lcsc_datasheet_2304140030_Brightking-30KPA150CA-B_C522439.pdf` returns an HTML wrapper, not read). Unidirectional also needs the midpoint-leakage check in ALT-D3 s2.1. **SAFETY**, risk med, BOM only + a footprint check (same P600). This is the g02-g03 Proposal D lead, re-checked: its "$1.98 at 800" second listing is most likely the unidirectional Littelfuse 30KPA150A (C1976335, $1.82 at 800 today), which is the *A* part, not the *CA* part.

### R2-03. BR1 to the MDD GBJ2510 (C27523)

| Parameter | GBJ2510-F, Diodes (C526644; JLC attributes, datasheet https://www.lcsc.com/datasheet/lcsc_datasheet_2005181004_Diodes-Incorporated-GBJ2510-F_C526644.pdf not machine-readable) | GBJ2510, MDD (C27523; datasheet https://www.lcsc.com/datasheet/lcsc_datasheet_2407301038_MDD-Microdiode-Semiconductor-GBJ2510_C27523.pdf not machine-readable) |
|---|---|---|
| VRRM | 1 kV | 1 kV |
| IF(AV) | 25 A | 25 A |
| IFSM | 350 A | 350 A |
| VF @ 12.5 A | 1.05 V | 1.00 V |
| IR | 10 uA @ 1 kV | 10 uA @ 1 kV |
| Tj | -65..150 C | -55..150 C |
| JLC price @500 boards / stock | $0.656 / 1,589 | **$0.272 / 27,087** |
| DK (Diodes) | $1.82 at 105+ (574 in stock) | not listed at DK |

I did not read I2t or the isolation/RthJC (BR1 is sacrificial for fuse clearing, DECISIONS 22, and 510 A2s cannot survive any 25 A fuse either way). VF is 0.05 V lower so BR1 loss at 22 A drops about 0.5 W (B3 benefit, not computed). Footprint: both GBJ; confirm height and lead pitch in the datasheets before use. Metrics: `parts_usd_at_500`, JLC stock; B3 sign positive. Risk low, BOM only. **Basis-fix part:** the survey's $4.02 is wrong regardless (DK 105-break $1.82), worth -3.36 with no change.

### R2-04. 24 x 10 uF 50 V X7R 1210: Samsung CL32B106KBJNNNE

Current UMK325AB7106KM-T (Taiyo Yuden C386167): X7R (code B7, -55..125 C), 1210 3.2 x 2.5 mm, thickness code M 2.5 mm (Taiyo datasheet, size and thickness tables), JLC $0.2186 at 24 x 500 pieces, stock 3,923 against 12,000 needed for 500 boards. Candidate Samsung CL32B106KBJNNNE (C138687): 10 uF 50 V X7R +-10 % 1210 (JLC listing), $0.1871, stock 45,882. Datasheet `https://datasheet.lcsc.com/lcsc/1912112237_Samsung-Electro-Mechanics-CL32B106KBJNNNE_C138687.pdf` redirects to an HTML wrapper: **thickness and DC-bias curve at 17 V not read**; they are the checks before adopting (the F6 reservoir budget is DC-bias dependent, DECISIONS item 14: 2.2 uF effective). Equal-class alternatives with stock: Yageo CC1210KKX7R9BB106 (C596319, 74,717 pcs) at $0.365 (more expensive). Delta B -1.47, S +0.90 (the survey carried a $0.12 estimate). Risk low-med, BOM only. Touches `bypass` / `pi_distances` gates only if the body height collides (not an electrical change).

### R2-05. 4 x 6SVPC220M to 6SVPC220MV

C2162098 6SVPC220M: 220 uF 6.3 V polymer, ESR 27 mohm, D6.3 x 6 mm, JLC stock **13**, $0.7112 (1000+). C128504 6SVPC220MV: same 220 uF / 6.3 V / D6.3 x 6 mm, ESR 15 mohm @100 kHz (JLC attributes), stock 845, $0.5008 at 2000 pieces. Lower ESR, smaller price, 65x the stock. Datasheet not read (Panasonic SVPC series page); confirm the V suffix is the low-ESR variant and the same land pattern. Delta -0.78 on both bases. Low risk, BOM only.

### R2-06. Prices that are simply on the wrong break

R24C2T25/R-R (U41/U42): 250 break $7.37148 used; 1000 pieces (500 boards) sit on the 750 T&R break **$7.18188**, 1500 pieces on **$6.24003** (a 750-board lot). 1,185 in stock, 6 wk lead (DK). Not a design change.

### R2-07 / R2-08. Quote leads, not savings

LCSC lists B32676G1905K000 (C3802167) at $1.2265 at 500 pieces (DK $6.17) and B82726S2203A020 (C1534260) at $2.1089 (DK $9.88), both stock 0. Four-to-five-fold gaps between two distributors for the same part number are more likely a stale or reseller-bound reference than a real price, so they are **UNVERIFIED** and sized as "up to". A written LCSC/TDK quote is a one-email check worth up to $17.7 per board; g01 P1 (SC-20-201) is the fallback and on the LCSC references SC-20-201 (C1535245, $2.70) is *dearer* than the TDK choke. The same method applies to 74650074R (LCSC ref $1.18 vs DK $2.73 at 100, 32,606 at DK).

## 3. Architecture and sourcing moves checked

**Fabrication (not in the $235; needs a JLC quote, I cannot get one offline).** `fab/FAB-NOTE.md`: 290 x 190 mm L-shaped outline (bbox 55,100 mm^2), 4 layers, 2 oz outer and inner, ENIG, epoxy-filled-and-capped vias for all 749 x 0.3 mm vias, but `via_in_pad.py` finds only 67 fully-in-pad and 69 edge-overlapping (136), 36 test pads. Quote these variants at 500 boards: (a) as built; (b) POFV on the 136 pad vias only, remaining 613 tented; (c) 1 oz inner copper if the inner layers are not carrying the tank; (d) HASL-LF if ENIG is only for the 0.65 mm SSOP-36/VQFN pads. Each needs the layout owner's yes (POFV was "no exceptions" for the DECISIONS 2026-10-08 via-in-pad rule; I did not find the reason for the blanket scope). Likely larger than any single BOM line above.

**Assembly.** JLC Extended-part fee is per order, not per board: the round-1 "$3 per Extended line, $36 per order" (research A-rows) is $0.006 per board per line at 500 boards; line-count work matters for the 5-board prototype lot, not for cost at 500. THT count (18 lines: 4 FETs, studs, film caps, modules) is the assembly cost driver; R1-g02A (-4 studs) and R2-01 (-2 P600) cut THT joints.

**JLC global sourcing vs consign.** See finding 3. Only `R24C2T25/R-R` has a JLC global-sourcing entry (C9900245652); the other consign lines (F1, TVS, C5/C6, T1, bank, UCC21550, F2, C1/C2, J3/J11) have none. The decision needs a JLC BOM quote.

## 4. Considered and rejected

- **Cheaper / IGBT power devices instead of 4 x IPW65R018CFD7 ($40.70).** `fet_downsize_check.py`: at 22 A tank current a 41 mohm CFD7 adds 42 W of conduction loss (sink load 125.9 -> 168 W against R_SA <= 0.29 C/W that is sized for 125.9 W, DECISIONS item D-18); at 28 A +69 W. A 650 V IGBT (IKW40N65WR5, JLC C108740, $1.23; IKW40N65H5 C454249 $0.97) adds 10-20 W in conduction alone (Vce(sat) from the JLC listing; IGBT datasheets not read), before turn-off loss at 35-60 kHz, and invalidates the F6 gate decks (+17/-2 V network, CFD7 model, D2 grid). Savings would be about $35 per board; thermal and the whole F6 qualification are the price. Not a swap; a different power stage.
- **IPW60R018CFD7 (600 V) instead of the 650 V part:** DK $10.61 at 510 vs $10.18 for the 650 V (https://www.digikey.com/en/products/result?keywords=IPW60R018CFD7): dearer and less VDS margin (490 V screen on 600 V).
- **JLC for the FETs:** $17.54 at 100+ (stock 6), DK $10.18: DK wins (a consign line stays).
- **Hi-Link HLK-20M24 (C465409, $3.34 at 480, stock 60) for PS1/PS2** instead of IRM-20 ($6.36): half the price but the JLC attributes give 2.5 kV isolation and no safety-agency listing; a mains-side supply for a UL/CSA/NOM appliance with the leakage budget open (F5) is a certification loss. Rejected.
- **One R24C2T25 for both high sides:** the two secondaries need separate floating references (sw_a, sw_b) with the module's 3.5 pF barrier between each and the LS; one module cannot serve both.
- **Cheaper U26 (TPS7A4700, $3.96 JLC):** it is the nominal B3 peak part (126-127 C) and the only 34 V/1 A/+-1 % adjustable LDO found in stock at JLC is the same TI family (TPS7A4701, 2 pcs); ABLIC/Nisshinbo alternatives have stock 0.
- **Single 30KPA280CA, SMDJ strings, 15/20 kW pairs, MOV on the bus, AK3-380C-Y:** already rejected in ALT-D3 s2.3/s3; AK3-380C-Y is $48.88 at DK today.
- **Dropping to 1 x B32676 (9 uF) to save $6.17:** burst valley and R2-01's bus peak rely on 18.4 uF (ALT-D3 s3.1).

## 5. What I could not verify

- Every LCSC price on a stock-0 listing (R2-02, R2-07, R2-08, g02 D). They are references, not quotes.
- Datasheet values for the MDD GBJ2510, Samsung CL32B106KBJNNNE, Brightking 30KPA150CA/B and Panasonic 6SVPC220MV (LCSC datasheet URLs return an HTML wrapper to a non-browser fetch; the Taiyo UMK325 datasheet was read). Their table entries come from the JLC part attributes.
- JLC PCB and assembly price (no offline quote), JLC global-sourcing pricing, Mouser/Arrow/Newark prices (only DigiKey pages and the JLC API were read), the DigiKey break at 500 boards for parts whose page showed one price.
- Bus peak under unmodelled surge cases; IPW65R018CFD7 avalanche energy; the IGBT datasheets (screen only); the 125.9 W sink budget's current basis (the script reports deltas, the budget line is context).
- That `price_at()` for ladders that stop below qty x 500 (e.g. 100 pieces) extrapolates flat: lower tiers beyond the listed ones are possible.
