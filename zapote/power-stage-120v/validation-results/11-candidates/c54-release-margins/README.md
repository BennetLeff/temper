# c54: release-case margins with BOM-only swaps (native-21 s53, board 82af7bd9)

Analysis lane, 2026-10-18. Nothing outside this folder was edited. The proposed edits are in `results/`:
`bom-patch.json`, `ledger-patch.json` and `b3-gate.patch`. Nothing was built and no solve was run. Every number below
comes from the committed B3 outputs and this folder's scripts.

## Result

| Line | Fitted | Recommended (same footprint) | Release margin | c22 / c28 (worst ref) |
|---|---|---|---|---|
| R10/R12/R18/R20 R_on, 68 Ω 2512 | 25121WF680JT4E, 1 W | **PS122WF680JT4E** (UniRoyal PS12, 2 W, 1 %, AEC-Q200; JLC C2793964) | R10 **+1.3 → +12.9 K** | −10.8 → **+0.7 K** / −51.0 → −39.4 K |
| R71/R72/R74/R75 split bleed (+R131), 4.99 k 0603 | 0603WAF4991T5E, 0.1 W | **ERJ-PA3F4991V** (Panasonic, 0.25 W at 105 °C ambient / 0.33 W at 130 °C terminal; JLC C4036134) | R75 **+2.5 → +41.6 K** | −7.4 → +31.7 K / −36.5 → **+2.6 K** |
| C126–C129, 220 µF bias reservoir | 6SVPC220MV, 105 °C | **16SVPK220M** (OS-CON SVPK, 125 °C, 16 V, same C6 can) | C129 **+4.8 → +24.8 K** | −4.8 → +15.2 K / −33.6 → −13.6 K |
| U26 TPS7A4700RGWR | — | **no BOM fix**: needs layout (section 4) | +4.4 K (unchanged) | +6.9 / +0.1 K |

- **`b3_release_margin_K`: +1.3 → +3.8 K.** With the R_on swap, the release case is bound by "laminate: 1 mm-block
  copper peak" (+3.8 K). The next rows are PS2 local air (+4.2 K) and U26 TJ (+4.4 K). None of these can be fixed by
  changing the BOM.
- **Ratchet `b3_rated_part_margin_K`: −51.0 → −42.1 K.** The worst row becomes R58 (the 1206 R_off) at c28.
- **c22:** every R_on row now passes; the worst rated part there is R58 at −3.8 K.
- **Evidence:**
  - `results/margins-c54.md` / `.json` (from `release_margins.py`);
  - `results/gate-patch-control.json` (the patched gate run on the real s53 run files: release margin 3.8 K, gate PASS);
  - `results/ledger-patch.json` (all three proposed entries pass the ledger gate's own `validate_entry`).
- **Cost:** about +$0.52 per board at 500 boards (JLC ladder): R_on +$0.149, bleed +$0.156, caps +$0.216.
  JLC extended-line count: +1 (PS12 replaces the 1 W part, which was extended, so that line is neutral; ERJ-PA3
  replaces a basic part; 16SVPK replaces an extended one).
- **Blocker, C126–C129 sourcing only:** JLC and LCSC both show 0 16SVPK220M in stock (read 2026-10-19 UTC).
  Digi-Key has 1,420 (factory lead time 55 weeks). The 20-board prototype needs 80 pieces: buy them at Digi-Key and
  consign them to JLC (or use JLC global sourcing). If consigning is not acceptable, keep 6SVPC220MV, which passes
  at +4.8 K. The two resistor swaps have no sourcing issue.

## 1. How the +1.3 K is computed (reproduced)

`scripts/release_margins.py` imports the gate's own `est()`. It reads R10's run-file values from
`results/b3-inputs-s53.json`, an extract of the gitignored `b3-ratings/runs/c17.5_h10_p0p25|p0p5.json` with the
sha256 of each file; the board sha matches margins.json. The calculation, for the release case c17.5_h10 (17.5 A at
its 18.375 A trip, still air h 10, bay 61 °C, hot copper):

- **Terminal estimate.** The estimate is the pad-copper maximum, extrapolated over the two meshes:
  108.124 + 3 × |108.124 − 104.292| + (61 − 50) = **130.62 °C**.
- **Limit.** UniRoyal V.3 gives 1 W at 70 °C (p.4/9 table 6), falling linearly to 0 at 155 °C (p.5/9 §9 fig. 1,
  ambient abscissa). B3 reads that curve at the terminal and applies the 80 % rule. At P = 0.21699 W:
  155 − 85 × 0.21699 / (0.8 × 1 W) = **131.94 °C**.
- **Margin.** 131.94 − 130.62 = **+1.3 K**.

All 12 R_on terminal and element rows, in all three cases, equal margins.json; the script asserts this. The control
`gate_patch_control.py` C1 also reproduces the whole of margins.json bit for bit from the run files.

## 2. Candidates searched (JLC/LCSC; `results/jlc-search-log.json`, raw records in `scripts/jlc-raw`, `scripts/lcsc-raw`)

### R_on, 68 Ω 2512

The gate-network stress (c39 / gate-network study, DECISIONS 54) sets the requirements:

- 0.217 W continuous (charge-split bound; the study simulates about 0.17 W);
- a 17 V edge step, giving at most 17²/68 = 4.25 W peak and 3.6 µJ per edge (`margins-c54.json` `r_on_edge`).

| MPN | P70 | knee → zero (abscissa) | tol / TCR | JLC stock | verdict |
|---|---|---|---|---|---|
| **PS122WF680JT4E** (UniRoyal PS12) | 2 W | 70 → 155 °C (ambient) | 1 % / 100 ppm | 3,856 (LCSC 2,930) | **chosen** |
| RC2512JK-7W68RL (Yageo RC_L "7W" double power) | 2 W | 70 → 155 °C (Tamb) | 5 % / 200 ppm | 3,708 | second source |
| AS122WJ0680T4E (UniRoyal AS12) | 2 W | same catalogue curve | 5 % | 431 | not taken (5 %, low stock) |
| CRH2512J68R0E04Z (Ever Ohms) | 2 W | — | 5 % | 825 | not taken (5 %, an unknown maker) |
| RC2512FK-7W68RL, SR2512FK-7W68RL, RMCP2512FT68R0, 352168RFT, CRGP2512F68R | 2 W | — | 1 % | 0–8 | out of stock |
| 352268RFT, RM25F68R0CT-U | 3 W | — | 1 % | 0 | out of stock (no 3 W 2512 in stock) |
| CRCW251268R0FKEGHP | 1.5 W | — | 1 % | 0 | out of stock, and lower than 2 W |
| ROHM MCR100, KOA RK73H3A | 1 W | — | 1 % | 0 | no gain |

No 68 Ω 2512 rated against **terminal** temperature was found in stock: the KOA and ROHM parts were the ones looked
for. Both stocked 2 W parts are rated on the same ambient basis as the fitted part. The gate rule is therefore
unchanged; only the rated power doubles.

**PS122WF680JT4E**, from the UniRoyal product catalogue 2023~2024, PS series:

- **p.23:**
  - PS12 is 2512 (6432) at 2W;
  - Derating Curve: 100 % at 70 °C to 0 % at 155 °C, x-axis "Ambient temperature";
  - operating −55~+155 °C;
  - max working voltage 500 V, max overload 1000 V;
  - dimensions L 6.35±0.10, W 3.20±0.20, H 0.55±0.10, A 0.60±0.25, B 0.50±0.20 mm. The B 1.80 mm wide terminal is a
    special order only, and is not this code;
  - "Curve of Pulse Duration": PS12 one-pulse limit is about 2000 W, flat from 1 to 10 µs (read from the plot). The
    4.25 W edge peak is 0.002 of it;
  - AEC-Q200.
- **p.24:** TCR ±100 ppm/°C; ordering code PS12 2W F = 1 %.
- **Terminal temperature does not change** for this same-footprint, same-dissipation swap:
  - same 68 Ω, so the same charge split and the same 0.217 W;
  - same body and terminals as 25121WF (V.3 p.4/9 gives the identical dimension row), so the same pads and copper;
  - the B3 body model's chip2512 r_pad of 37.6 K/W is derived from those dimensions (`thermal_body.py`), not from the
    power rating, so the element estimate does not change either.
  - Only the special 1.80 mm bottom terminal would change the pad conduction. It is not proposed.
- **The gate needs a rating by MPN:** `results/b3-gate.patch` adds `GATE_R_MPN`. Its control (C1–C3) shows the patch
  is a no-op for the fitted part, gives exactly the predicted rows for PS12, and stops the gate on an unlisted 2512
  MPN.

### Split bleed, 4.99 k 0603

The bleed dissipates P = (V_PN − V_SPLIT)²/4.99 k = 0.04815 W in R71/R72/R74/R75. R131 is `hb.rosc`, the same
Bias4k99 component, and carries no bleed current.

**ERJ-PA3F4991V** (Panasonic ERJ P/PA/PM, 29-Sep-23):

- **p.2 Ratings, ERJPA3:**
  - 0.25 W at rated **ambient** temperature 105 °C, **or** 0.33 W at rated **terminal-part** temperature 130 °C;
  - limiting element voltage 150 V;
  - ±1 % (E96), ±100 ppm/K;
  - category −55 to +155 °C;
  - AEC-Q200 grade 1.
- **Footnote *2:** "give priority to the rated terminal part temperature".
- **p.3:** both derating curves, each falling to 0 at 155 °C.
- **Gated basis:** the stricter line, ambient read at the pad: 155 − 50 × 0.04815 / 0.2 = **143.0 °C**. Panasonic's
  own terminal-part line gives 150.4 °C.
- **Second source:** Vishay RCS06034K99FKEA, 0.25 W at 70 °C, film limit 155 °C (doc 20065 p.1), limit 134.5 °C.
  JLC holds 745.
- Not taken because they are out of stock: UniRoyal PS03W4F4991T5E and Yageo RC0603FR-7W4K99L.

### C126–C129, 220 µF on the ~2.0 V split

The working voltage is src − n = V_SPLIT = 2.01 V. Each cap sits behind a 0.68 Ω damping resistor (DECISIONS 28:
moving from 27 to 15 mΩ ESR changed the damped impedance by less than 2 %).

**16SVPK220M** (Panasonic OS-CON SVPK):

- **p.1:** "125 ℃ 1000 h"; category −55 to +125 °C.
- **C6 dimensions:** D 6.3, L 5.9, W = H 6.6, C 7.3, P 2.1 mm. These are identical to SVPC C6, so the existing
  `CP_Elec_6.3x5.9` land is unchanged.
- **p.2:**
  - 220 µF at 16 V;
  - ESR 22 mΩ (fitted part 15);
  - ripple 3300 mA up to 105 °C and 1040 mA from 105 to 125 °C, against an own ripple of about 0.1 A or less;
  - LC 704 µA maximum at the rated 16 V after 2 min. That is well under the roughly 3.1 mA of split bleed current
    (bench check listed as a ledger gap).

Rejected:

- Vishay 286 CPNX MAL228697401E3: 125 °C and pad-identical, but a 6.3 × 6.3 × 9 mm can (10 mm maximum), and no stock
  anywhere.
- Kemet A768EB127M1DLAE034: 125 °C and in stock, but only 120 µF.
- Chemi-Con APXH: 8 mm, or 2.5 V at 220 µF.
- AISHI SVZ0JM221: its JLC listing says "2000 h at 125 °C", but the category is 105 °C.

## 3. Margins (s53, `results/margins-c54.md`)

Release case c17.5_h10 at bay 61 °C:

- R_on: R10 +12.9, R20 +15.7, R18 +16.8, R12 +16.9 K. The element rows are unchanged: R10 134.5 °C against 155,
  +20.5 K.
- Bleed: R75 +41.6, R74 +44.5 K.
- Caps: C129 +24.8, C128 +25.8 K.
- The s53 rows differ from OPEN-ITEMS S21's quoted values (R75 +2.3, C129 +4.7, U26 +4.1/+5.1 K), which come from
  older boards. On s53 the fitted parts give R75 +2.5, C129 +4.8 and U26 +4.4 K.

**Model caveat:** the bleeds' own 0.048 W each is not in the B3 heat file (`runs/heat_c17.5.json`), so their pad
temperature is board heat only. This applies to both the fitted and the new part. The swap leaves about 40 K for it.

## 4. U26: no BOM fix

TI SBVS204G p.4 gives TJ −40..125 °C. TPS7A4701QRGWRQ1 (-Q1) is also −40..125 °C, so no pin-compatible grade raises
the limit.

U26's heat is (24 − 17 V) × (2 I_ch + 30 mA) = 7 V × 0.129 A = **0.903 W** (`b3/make_heat_sources.py` C28_F). A BOM
change can only alter the limit, not the dissipation.

Layout options, for the integration / layout session; neither is modelled here:

- **Series dropping resistor (largest lever).** Put a resistor in v24_raw ahead of U26 IN, for example a 2512 of about
  20 Ω. It moves about 0.33 W (I²R at 0.129 A) off the LDO and onto a separate part. Size it to keep at least 1 V of
  headroom at PS2's minimum output and the maximum I_ch. This needs a footprint and a re-route.
- **Better junction-to-board path.** Add more thermal vias in the RGW exposed pad, into a larger inner-layer copper
  area away from the FET-row heat.

A B3 solve is needed to put a number on either option.

## 5. For the integration session (proposed; nothing applied)

1. **Source.** Edit the MPN fields; values and footprints stay the same.
   - `elec/src/parts.ato` `R68Gate2512`: → PS122WF680JT4E;
   - `elec/src/f6_parts.ato` `Bias4k99`: → ERJ-PA3F4991V (moves R71/R72/R74/R75/R131);
   - `elec/src/f6_parts.ato` `Bias220u`: → 16SVPK220M.
   - Then update the MPN asserts in `native-21/verification/verify_source.py` (lines 39 and 52), `audit.rs`, and
     `datasheet-ledger/tests/test_gate.py:63`, which names 25121WF680JT4E.
2. **BOM rows:** `results/bom-patch.json` `frozen_bom_rows_after`. It also holds stock and price, read 2026-10-19 UTC
   (JLC detail and the LCSC product API), plus the one Digi-Key web read.
3. **B3 gate:** apply `results/b3-gate.patch`, then run the chain. The heat file and solves do not change; only the
   2512 line moves.
4. **Ledger:** `results/ledger-patch.json` replaces the entries for 25121WF680JT4E, 0603WAF4991T5E and 6SVPC220MV.
   All three stay PARTIAL.
   - Key B3 numbers: R_on release ratio 0.378 (80 % rule); c22 0.754, now passing.
   - The temp-ratings table (`b3-ratings/temp-ratings-2026-10-15/scripts`) needs rows for the two new passive MPNs.
5. **Optional next lever (not done):** R58 / R53 / R54 / R57 R_off (1206W4F100KT5E) is the next resistor row: +10.9 K
   at release, −3.8 K at c22, −42.1 K at c28. The same approach applies with a 1206 anti-surge part of 0.5–0.66 W.

## Reproduce

```
python3 -I scripts/release_margins.py            # margins (committed inputs only)
python3 -I scripts/patches.py                    # bom-patch.json, ledger-patch.json (+ ledger validate_entry)
python3 -I scripts/gate_patch_control.py         # needs the gitignored b3-ratings/runs/ and `patch`
python3 -I scripts/release_margins.py --extract  # regenerate b3-inputs-s53.json from b3-ratings/runs/
python3 -I scripts/search_log.py                 # jlc-search-log.json (online for searches not cached)
python3 -I scripts/fetch_datasheets.py DIR       # datasheets (not committed); prints sha256[:16]
```
