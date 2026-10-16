# c34 bank replacement sourcing (B32643B8104J000 rejected)

Lane: bank-src, read 2026-10-16. Analysis plus read-only sourcing only: no PCB build, no chain.sh, no commits, no
supplier contact, no accounts, no orders. Bot checks were not bypassed: Mouser interstitial, Octopart 403 after one read,
TDK product.tdk.com 403.

Design under test: 5 x 0.1 uF J = 0.50 uF (35 kHz floor; round-6 yield at 28 A 88.6 %), slot x 161-193, s49 rows at
y 53.2 / 68.2 / 83.2 / 98.2 / 113.2 (15 mm pitch), RES_A x 163.0, SW_B x 185.5 (P22.5).

## Verdict

**No part in stock passes every row strictly.** The rejected TDK B32643B8104J000 is still the only part that clears both
the vendor rated-current row and the producer bank_air gate (0.967).

1. **KNSCHA MMK104J3DF1KN208G2, JLC C528962.** Ranked first, but conditional.
   - Stock: 4,952 at JLC, $0.3035 at 1000+, $1.52 per board. It is the only stocked 2 kV part whose vendor publishes a
     current curve.
   - Voltage: passes every voltage and pulse row.
   - Current: fails the vendor row (0.978 against the ledger's 0.85) and the bank_air gate (1.221 at 28 A). It reaches
     0.869 only with the gap-flow credit, because its 11.5 mm body leaves 3.5 mm air gaps where c34 had 0.5 mm.
   - Release (18.375 A, still air): 0.957 with radiation, 1.208 without.
   - Needs B3/CFD or bench evidence for the gap flow before 28 A can be claimed.
2. **Second source: none in stock.**
   - KEMET R75UR31004030J has 1,294 at DigiKey plus 510 at Newark. That is short of 2,500, and it fails on heat (gate
     1.444, KEMET Th rule fails with 87.5 C pads).
   - The only real second path is TDK B32643B8104J000 itself, on a 28-week non-cancelable order (MOQ 2,080 at
     $1.30931).
3. **6 x KNSCHA (0.60 uF) at 13.08 mm pitch.**
   - Ratios: vendor 0.818, gate 1.021, with gap credit 0.72, release 0.81 / 1.03.
   - Costs: yield 88.6 % -> 75.9 % (-12.7 pts), and about 1-2 mm more pin span at the R22/R25 end.

## 28 A options (in-stock parts, ~0.50 uF; scripts/options28.py -> results/options28.{json,md})

**Answer.** No in-stock bank reaches 28 A on the vendor row (<= 0.85) inside today's column. One that does reach it
strictly is **O6: 10 x KEMET R76UR24704030J (47 nF, 2 kV, P27.5) + 1 x TDK B32654A2333K000 (33 nF K)**.

| | O6 |
|---|---|
| C | 0.503 uF (C_min 0.476) |
| Yield | -0.4 pts |
| Vendor ratio | 0.648 |
| Gate, strict | 0.890 |
| Gate, with gap credit | 0.856 |
| Release | 0.61 / 0.77 |
| F3 R0/R1 | 0.993 |
| Highest strict step | 28 A |

The catch is fit. It is 11 bodies, and the column holds 6 of them, so **5 go into a second column outside the slot**.

The simplest fully curve-rated bank is O1, 11 x R76UR24704030J (0.517 uF). It passes the same way but costs 2.2 yield
points.

### Tolerance band (round 6 `fstrat-b-bank-sweep.csv`, L 70 uH, 220 mm pans, 28 A)

- **Yield falls monotonically with C above 0.35 uF:** 0.45 -> 91.4 %, 0.50 -> 88.6 %, 0.60 -> 75.9 %. Interpolated
  linearly as in c34, it costs about 1.27 points per +0.01 uF above 0.50.
- **The 35 kHz floor does not bind for C <= 0.50.** The floor-limited share is 0.4 % at 0.50 and 0 at 0.45.
- **F3 sets the floor on C.** F3 R0/R1 is 0.996 of the 0.85 x VR limit at C_min 0.475. Scaling conservatively as 1/C,
  this needs C_min >= 0.4731 uF, i.e. C_nom >= 0.498 uF for J parts.
- **Band: C_nom 0.498-0.500 uF moves nothing.** Every 0.01 uF above it costs about 1.3 points of yield.
- So 10 x 47 nF (0.47 uF) fails F3 (1.06), and 7 x 68 nF (0.476 uF) fails F3 (1.046).

### Why n x (0.50/n) only helps with a different part

- In a parallel bank every part sees the same voltage. Part i's vendor ratio is about V_bank x (1 + t) / V_allow,i(35 kHz),
  and n cancels out (c34 rule: V_allow >= 268 x 1.05 / 0.85 = 331 V rms).
- **KNSCHA 104 has V_allow = 282 V.** It reads 0.978 in any 0.50 uF bank, mixed or not: 4 x 0.1 + 2 x 0.047 leaves the
  104 parts at 0.978.
- **Smaller parts of the same family carry more volts at 35 kHz** (less heat per unit of surface):

| Part | C | V_allow(35 kHz) | Basis |
|---|---|---|---|
| R76UR2470 | 47 nF | 429 V | plotted curve |
| R76UN2470 | 47 nF | 430 V | ESR model x 0.973 control, ESTIMATE |
| R76UN2390 | 39 nF | 449 V | ESTIMATE |
| R76UR2680 | 68 nF | 336 V | ESTIMATE, marginal |
| R76 82 / 100 nF | 82 / 100 nF | 294-329 V | fail |
| TDK B32654A2333K | 33 nF | 504 V | p.57 2000 V chart interpolated between 22 and 47 nF, ESTIMATE |

**Ruled out:**
- **KNSCHA 2 kV 473J / 683J / 823J / 333J.** None is listed in stock at JLC/LCSC; the only KNSCHA 47-82 nF parts in stock
  are 630 V-1.6 kV. The family chart's 473 P27.5 curve (about 4.3 A, ~416 V) would pass if it could be bought.
- **Faratronic C82 (C823D473J90C000, 1,000 at JLC).** Its datasheet (dl/C5121891, pp.1-5) gives no current rating, only
  tan d <= 10e-4 at 1 kHz and a rated temperature of 75 C for U_R(ac), so it cannot carry a margin claim.
- **82 nF options (6 x 82 nF = 0.492 uF fails F3; 5 x 82 + 1 x 91).** No in-stock 2 kV 82 nF part with a rating reaches
  331 V: R76 82 nF is 301-329 V, B32643B8823 is not stocked, and B32643H has no readable sheet. No 2 kV 91 nF part was
  found.

### Options (28 A, S24 flow; strict = producer method, gap 0.5 mm; per-part detail in results/options28.md)

| id | bank | C nom / min uF | yield pts | vendor 35k | F3 R0/R1 | gate strict / gap | release 18.375 A rad / no-rad | highest step strict / gap | columns (pin span mm) | stock 20 / 500 boards | $/board @500 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **O6** | 10 x R76UR2470 + 1 x B32654A2333K000 | 0.503 / 0.476 | -0.4 | 0.648 | 0.993 | **0.890 / 0.856** | 0.612 / 0.770 | **28 / 28** | 6 (58.75) + 5 (46.0) | yes / yes | 13.60 |
| **O1** | 11 x R76UR2470 | 0.517 / 0.491 | -2.2 | 0.629 | 0.963 | **0.864 / 0.830** | 0.595 / 0.749 | **28 / 28** | 6 (57.5) + 5 (46.0) | yes / yes | 13.24 |
| O2 | 11 x R76UN2470 (P22.5, AEC) | 0.517 / 0.491 | -2.2 | 0.627 | 0.963 | 0.827 / 0.787 | 0.576 / 0.712 | 28 / 28 | 7 (63.0) + 4 (31.5) | yes / **no** (2,117 vs 5,500) | short |
| O3 | 10 x R76UR2470 + 1 x R76UN2390 | 0.509 / 0.484 | -1.1 | 0.639 | 0.978 | 0.877 / 0.843 | 0.604 / 0.760 | 28 / 28 | 6 + 5 | yes / **no** (39 nF: 296) | short |
| O4 | 2 x R76UR2470 + 6 x R76UR2680 | 0.502 / 0.477 | -0.3 | 0.822 | 0.992 | 1.093 / 1.054 | 0.748 / 0.952 | 24 / 26 | 5 + 3 | yes / **no** (68 nF: 917) | short |
| O5 | 5 x R76UR2470 + 4 x R76UR2680 | 0.507 / 0.482 | -0.9 | 0.814 | 0.982 | 1.083 / 1.044 | 0.742 / 0.945 | 24 / 26 | 6 + 3 | yes / no | short |
| R1 | 5 x KNSCHA 104 (s51 as built) | 0.500 / 0.475 | 0 | 0.978 | 0.996 | 1.221 / 1.177 | 0.957 / 1.206 | 22 / 22 | 5 (48.0) | yes / yes | 1.52 |
| R2 | 10 x R76UR2470 | 0.470 / 0.447 | +1.7 | 0.691 | **1.060 F3 fail** | 0.950 / 0.912 | 0.650 / 0.816 | 28 / 28 | 6 + 4 | yes / yes | 12.00 |
| R3 | 7 x R76UR2680 | 0.476 / 0.452 | +1.3 | 0.867 | **1.046 F3 fail** | 1.153 / 1.111 | 0.785 / 0.997 | 24 / 24 | 5 + 2 | yes / no | short |
| R4 | 8 x R76UR2680 | 0.544 / 0.517 | **-5.6** | 0.760 | 0.915 | 1.010 / 0.974 | 0.696 / 0.888 | 26 / 28 | 5 + 3 | yes / no | short |

**Notes on the table**
- **Stock** (read 2026-10-16; snapshots/digikey-2026-10-16b.json, snapshots/findchips.json, JLC part API):

| Part | DigiKey | Newark | JLC | Notes |
|---|---|---|---|---|
| R76UR24704030J | 998 (20 wk) | 336 + 8,672 (two rows) | 0 (C3783048) | |
| R76UN24704040J | 408 | 1,709 | 0 | |
| B32654A2333K000 | 820 (28 wk) | — | — | |
| R76UN23905050J | 250 | 46 | — | |
| R76UR26804030J | 315 | 602 | — | |

  - LCSC is the same record as JLC (0).
  - None of these is at JLC, so the bank is a consigned THT line.
  - Prototype quantities (n x 20 boards) are covered by DigiKey alone.
- **Cost** allocates each line's 500-board quantity to the cheapest distributor up to its stock (O6: 998 DigiKey at
  $1.039 + 4,002 Newark at $1.24 + 500 TDK at $1.604). By comparison, 5 x c34 TDK on order is about $6.55 and the KNSCHA
  bank is $1.52.
- **Thermal binding term.** The KEMET temperature rule takes Th = max(T_A, T_pad). With the s49 pads at 87.2 C, the
  allowed rise is 18.2 K, and that sets the R76 gate.
  - The second column's pads are unknown, so the same pads are assumed.
  - The gate reaches 1.00 at Th of about 93 C (O1) or 92 C (O6). So the column-2 copper must keep pads <= ~92 C at 28 A.
- **Release pads are now board 9afc509b (s51).** The ps-selv runs were rewritten again. The R1 release value (0.957) is
  unchanged from the earlier run.

### Fit and layout (O6; O1 is the same geometry)

- **Column 1 (today's slot)**
  - Holds 6 bodies at about 11.5 mm row pitch (0.5 mm gaps), pin span 57.5-58.75 mm inside the s49 / s51 rows (y 53.2-113.2).
  - Uses the P27.5 holes' x positions (RES_A x 163.0, SW_B x 190.5) on the existing strips.
  - **The dual-pitch footprints' drills sit on 15 mm rows, so only row 1 (y 53.2) coincides.** The five bank footprints
    are re-placed at the new pitch with 6 new footprint instances. The strips stay; drills and pour clearances move.
  - The TDK part is 13.5 mm thick; put it in column 1.
- **Column 2 (new)**
  - 5 x R76UR2470 at 11.5 mm pitch: pin span 46.0 mm, body envelope about 57 x 32 mm, courtyard about 58 x 33 mm.
  - It needs RES_A and SW_B strips carrying about 14 A rms worst case (5 parts x 2.79 A).
  - **This lane did not find or check a location for it.** It is a layout stage (B3 + DRC). Inter-column loop inductance
    is not a sharing issue at 35 kHz (96.7 ohm per part against tens of mOhm of copper).
- **One long column instead** needs a 115-116 mm pin span against 65.2. That means moving the R22-R25 bleed string above
  and line_zc_raw / the SELV lane / J6 below by about 50 mm in total.

### BOM, cost and bench items for the top option (O6)

**BOM:** C21-C23, C151, C152 plus 6 new references:
- 10 x KEMET R76UR24704030J (47 nF +-5 %, 2000 VDC / 700 VAC, 32 x 11 x 20.1 mm, P27.5, 55/110/56, case UL94 V-0, not
  AEC at 27.5 mm);
- 1 x TDK B32654A2333K000 (33 nF +-10 %, 2000 VDC / 700 VAC, 31.5 x 13.5 x 23 mm, P27.5, -55..100 C, AEC-Q200).

**Cost:** $13.60 per board at 500 boards.

**Bench items:**
1. **R76UR2470 rating basis.** The p.8 curve is Th <= 85 C with about 20 K hot-spot rise. The curve implies a heat of
   about 0.65 W at 4.43 A (Rth 31 K/W), which is an ESR of about 33 mOhm at 35 kHz. Measure ESR at 35 / 40 kHz and
   80 C. The gate (0.890) tolerates ESR up to x1.26.
2. **Column-2 pad temperature <= ~92 C** at 28 A. The KEMET Th rule makes the pads the binding term. A B3 solve of the
   new copper is needed first.
3. **TDK B32654A2333K000 rating** (ESTIMATE, interpolated). It is a single part at 0.576. Confirm it against the p.23
   table row once the B3265x sheet is readable.
4. **Yield at 0.503 uF.** The -0.4 points are from linear interpolation, so no new run is needed.
5. **No gap credit is needed:** both columns pass strictly at 0.5 mm gaps.

## Decision inputs (5 x KNSCHA MMK104J3DF1KN208G2; scripts/decision_inputs.py)

**How these are computed**
- The S24 design flow is jets + base, 3.07 m/s along x at the bank with a 3.7 K bulk rise.
- There are two declared points: h20 pads at 61 C and h15 pads at 55 C. The worst over both points, every position and
  both G_board bounds is taken.
- "Strict" means no gap credit (the producer method). "+gap" adds the gap-channel credit. Pad heat is off in both.
- The control passes: strict 28 A = 1.221, matching bank_air_cand.

**(1) Highest tank-ceiling step with gate <= 1.00 and vendor ratio <= 0.85**

| tank A | I part A | vendor ratio 35 kHz | gate strict | gate +gap |
|---|---|---|---|---|
| 18 | 3.897 | 0.629 | 0.785 | 0.559 |
| 20 | 4.330 | 0.698 | 0.872 | 0.621 |
| 22 | 4.763 | 0.768 | **0.959** | 0.683 |
| 24 | 5.196 | 0.838 | 1.046 | **0.745** |
| 26 | 5.629 | 0.908 | 1.134 | 0.807 |
| 28 | 6.062 | 0.978 | 1.221 | 0.869 |

- **Strict: 22 A.** The gate is linear in current at this flow and crosses 1.00 at 28 / 1.221 = 22.9 A.
- **+gap: 24 A.** Here the vendor row limits, not the gate. The vendor ratio reaches 0.85 at 24.3 A. The gate alone
  passes to 28 A (and to 28 / 0.869 = 32 A).
- The pads do not move these numbers. Scaling the pad rise down with current gives identical gates, using the
  same-board B3 h10 solves c17.5 / c22 / c28 on board 4876c42e. The reason: the KNSCHA rule is flat (10 K) while the
  dummy ambient T_A <= 85 C, and the highest T_A at the S24 points is 78.9 C.

**(2) Air velocity along x across the column for the 28 A gate <= 1.00**

| case | point | gate at 3.07 m/s | v for gate 1.00 |
|---|---|---|---|
| strict | 61 C | 1.221 | **6.17 m/s** |
| strict | 55 C | 1.218 | 6.12 m/s |
| +gap | 61 C | 0.869 | 1.19 m/s |
| +gap | 55 C | 0.869 | 1.19 m/s |

- Strict therefore needs 6.2 m/s, about 2x the S24 flow. The bulk rise is scaled as 3.7 K x 3.07 / v.
- The strict values are conservative because the pads are held at the 3.07 m/s solve.
- The +gap values are NOT conservative: pads would run hotter below 3.07 m/s. At 1.19 m/s the model's T_A reaches
  79.3 C, close to the 85 C knee where the assumed derating starts.
- **The vendor ratio <= 0.85 is a pure current ratio**: I_tank x 0.2165 / 6.2 A. No airflow changes it. At 28 A it is
  0.978, and only a current ceiling <= 24.3 A, a sixth part, or a part with a higher curve moves it.

**(3) What the bench must confirm (KNSCHA publishes none of these per part)**
1. **Current rating basis.** The curve is digitised from an embedded JPEG: 6.2 A at 35 kHz, 6.16 A at 40 kHz, for a
   10 K internal rise at ambient <= 85 C. Confirm the rise at 6.2 A / 35 kHz sine on a single part in still air. Measure
   the case and infer the core, or measure the core with a thermocouple through the lead.
2. **ESR / tan d at 35 and 40 kHz**, at 25 C and at about 80 C.
   - The rating implies a heat of 10 K x G_vtest = 0.41 W (at the lo G_board bound the gate uses). That is
     ESR <= 10.7 mOhm at 35 kHz (tan d 2.3e-4).
   - The gate scales as sqrt(ESR / 10.7 mOhm). The +gap 0.869 tolerates ESR <= 14.1 mOhm. The strict 22 A step
     (0.959) tolerates ESR <= 11.6 mOhm.
3. **Behaviour above 85 C ambient.** The sheet gives no current derating above 85 C. The model ASSUMES it is linear to
   0 at Top,max 105 C, and also uses a 1.25 %/C DC derating. This does not bind at the S24 points (T_A <= 78.9 C). It
   binds at lower flow or in hot corners. Confirm the 40/105/56 climatic rating and the derating rule with KNSCHA's
   documentation, or by a hot soak with a bench current.
4. **Gap-flow credit** (this decides strict 22 A versus +gap 24-28 A). At 28 A with the S24 flow on the s49 bank
   column, the worst interior part (C22 / C23 / C151) must show an internal rise <= 10 K over its local air
   (eff = sqrt(dT / 10 K)).
   - The model predicts 7.6 K with the credit and 14.9 K strict.
   - Also measure the gap velocity, which the model puts at 2.5 m/s in the 3.5 mm channel at 3.07 m/s approach.
5. **Body dimensions.** The datasheet gives 31.5 x 19.5 x 11 +-0.5 mm; the model uses 32 x 20 x 11.5. The gap width
   (3.5-4 mm) drives the credit, so measure 10 bodies.

## Candidates

The voltage column is the worst utilisation of each part, from results/voltage_rows.md. "Ratio" columns are utilisation
of the limit (1.000 = at the limit). Prices are USD per unit at about 2,500 pcs (500 boards x 5).

| id | MPN | series | C / V | dims w x h x l mm, pitch | tan d / ESR | I rated 35 / 40 kHz (basis) | approval | stock (read 2026-10-16) | $ @2.5k | F3 R0/R1 (<=0.85 VR) | vendor ratio 35 kHz | bank_air 28 A gate / +gap | release rad / no-rad | fit |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| c34 | B32643B8104J000 | TDK B3264*B | 100 nF / 2 kV, 500 VAC | 14 x 29.5 x 31.5, P27.5 | per c34 ledger | per c34 ledger (dT 15 K) | UL94 V-0, AEC-Q200D | JLC 0, DigiKey 0 (28 wk, MOQ 2,080 $1.309), Avnet 0; brokers TIST 27,690 / Fmall 11,690 (unauthorised) | 1.309 (DK) | 0.996 | 0.831 | **0.967** / 0.926 | 0.80 / 1.05 | baseline |
| knscha | MMK104J3DF1KN208G2 | KNSCHA MMKP82 | 100 nF / 2 kV, 700 VAC | 11 x 19.5 x 31.5 (modelled 11.5 x 20 x 32), P27.5 | not published per part | 6.2 / 6.16 A (sine, ambient <= 85 C, internal rise 10 K; digitised, controls pass) | case UL94 V-0, passive flammability cat. B; no AEC | **JLC 4,952** (pre-sale 4,928); Unikey broker 400 | 0.3035 (JLC) | 0.996 | 0.978 | **1.221** / 0.869 | 0.957 / 1.208 | yes (see Fit) |
| r75 | R75UR31004030J | KEMET R75 | 100 nF / 2 kV, 700 VAC | 11 x 20.1 x 32, P27.5 | p.24 row | 5.84 / 6.23 A (Th <= 85 C, dT ~20 K; chart scaled to the 7.56 A table row) | UL94 V-0; AEC-Q200 only to P22.5 | DigiKey 1,294 (20 wk), Newark 209 + 301, Avnet 0, JLC n/a | 0.979 (DK) | 0.996 | 1.038 | **1.444** / n/a (Th rule fails, pads 87.5 C > 85 C) | 1.115 / 1.331 | yes |
| r76 | R76UR3100SE30J | KEMET R76 | 100 nF / 2 kV, 700 VAC | P27.5 (c34 parts_kemet.json) | p.22 | dT 40 K to Th 60 C rule | UL94 V-0 | DigiKey: SE30J no listing; R76UR3100* all 0; JLC C3800216 / C3787563 0 | 0.62-0.84 (JLC, no stock) | 0.996 | 0.933 | **1.236** / n/a | 0.972 / 1.256 | yes |
| wima | MKP1U031006D00JSSD | WIMA MKP 10 | 100 nF / 2 kV, 700 VAC | 13 x 24 x 31.5, P27.5 | sheet | ESTIMATE ~4.0 A (15 K "general guide") | sheet | **DigiKey 5,598** (26 wk), TME 0 | 1.252 (DK) | 0.996 | 1.515 | **1.894** / 2.284 | 2.68 / inf | yes |
| b32643h | B32643H8104J000 | TDK B32643H | 100 nF / 2 kV | 14.5 x 29.5 x 26.5, P22.5 | datasheet not readable (403) | ESTIMATE from c34 (0.98) | AEC-Q200 | DigiKey 306 (28 wk), Newark (82 nF only: 738) | 1.304 (DK @2,600) | 0.996 | 0.98 (est.) | **1.141** / 1.092 | 0.93 / 1.21 | yes (P22.5 = c34 SW_B) |
| knscha6 | 6 x MMK104J3DF1KN208G2 | KNSCHA | 0.60 uF | P27.5 at 13.08 mm pitch | | 6.2 A | as knscha | JLC 4,952 covers 3,000 | 0.3035 | 0.996 (F3 scales as 1 / C, so lower) | 0.818 | **1.021** / 0.72 | 0.81 / 1.03 | needs 1-2 mm more span; yield -12.7 pts |
| fitted (ref.) | B32654A1104J000 | TDK B3265x | 100 nF / 1.6 kV | | | | | | | **1.245 FAIL** | 1.045 | 1.308 / 1.818 | 1.00 / 1.28 | reference only |

### Voltage rows (results/voltage_rows.md)

Every 2 kV candidate passes every row:

| row | utilisation |
|---|---|
| normal peak | 0.354 |
| no-pan | 0.61-0.97 (c34 0.969, R75 0.807, KNSCHA 0.646) |
| Vrms | <= 0.67 |
| F3 R0/R1 | 0.996 of the 0.85 VR limit (1693.2 V against 1700 V) |
| F3 at any reading | 0.893 |
| Z0max x top | 0.804 |
| dV/dt | <= 0.17 |

**A 1600 V part cannot pass**:
- F3 R0/R1: 1.245 of the limit.
- F3 at any reading: 1.117.
- Z0max x top: 1.004 (one R4 row 7.1 V over).
- At the R0 release reading (top 114.575 A, F3 1624.0 V), F3 is 264.0 V over 0.85 x 1600 V and 24.0 V over 1600 V.
- To pass, the OCP top would have to drop to <= 95.95 A (for the 0.85 x VR rule) or <= 112.88 A (for F3 <= VR).
- So the 11,383 JLC 1600 V KNSCHA stock, KYET 3C, JURCC 1.6 kV and the TDK B32653A (1 kV) are all out.

## Fit (KNSCHA against the s49 copper)

- **Rows:** P27.5, 11 mm thick on the 15 mm rows, which leaves gaps of about 3.5-4 mm.
- **Height:** 20 mm, where c34 is 29.5 mm.
- **Pads:** RES_A pads stay at x 163.0. SW_B pads move from x 185.5 (P22.5) back to x 190.5, which is the s48 location on
  the widened s49 sw_b strip.
- **Slot:** inside x 161-193 (pin + body 163.0-190.5 + about 2 mm).
- **Copper:** no new re-cut is needed. A footprint swap plus DRC confirms it.
- **knscha6:** at 13.08 mm pitch, the 6-row stack needs about 1-2 mm more span. The limits are R22/R25 bleed pads at
  y 48.0 and line_zc_raw at y 122.75. A re-cut would be needed.

## Rejected families (reason)

- **KEMET**
  - PHE450: the sheet says it is replaced by R76.
  - C4AS / C4AT / C4AE: Top 85 C, P27.5 C4AS is 14 x 28; JLC has 20 pcs.
  - R73 / R74: no 0.1 uF 2 kV part appears among DigiKey's 26 in-stock '0.1uF 2000V' rows, and none is at JLC. KEMET
    stock at JLC is only PHE450 / C4 / R76, all <= 68 pcs.
- **WIMA:** FKP1 / FKP4 are too large at 0.1 uF 2 kV, and none are stocked. MKP10 is stocked but fails current (1.52).
- **Vishay:** MKP1848 is DC-link (not 2 kV). MKP385 0.082 uF is not stocked. MKP1837 / 715P / MKP1845 / MKP1841 / MKP386M
  are axial, P37.5, or 30 mm+ tall, with <= 174 stocked.
- **CDE:** 940C / 942C are axial (21-29.5 dia x 34-46 mm). They have stock (940C20P15K-F 6,233) but do not fit
  radially in the column. SCD / SNU are snubber modules.
- **Panasonic ECW-H:** 1250 V class (ECWH12104JV, 44 at JLC), fails F3 the same way 1600 V does.
- **TDK**
  - B32656S / B32656J / B32656T / B32686: P37.5, 41.5-42 mm long; 410-759 stocked. They do not fit the 27.5 mm pin
    column with the RES_A / SW_B pads.
  - B32653A / B32654A: <= 1.6 kV.
- **Faratronic, KYET, Dongtong CBB81, JURCC (Chinese 2 kV parts at JLC):** no published current rating, so no margin
  claim is possible. Of these, only KYET MMKP154J (150 nF, 3,055) and Dongtong (2,151) come near 2,500. Faratronic
  C823C/D (712-1,000 pcs, 2.1-4.0 $/board) is short.
- **Nichicon / Rubycon / Hongfa / Jb JFL / JFM:**
  - No Nichicon, Rubycon or Jb parts appear in the JLC survey (24 brands, 2,704 parts >= 1 kV).
  - Hongfa has one part, HAPD1K6P22J0N200A: 1.6 kV, stock 0.
  - None of these brands appear among DigiKey's 26 in-stock 0.1 uF 2 kV rows.
- **Two in series:** gives 4 kV but needs 0.2 uF parts at double the pin span. That is 10 bodies in the 32 x 74.5 mm
  column, or twice the pitch, and it does not fit.
- **Fewer, larger parts (2-3 x 0.15-0.22 uF):** each part carries a share of the full 28 A tank current, roughly
  9-14 A. The only stocked rated family (KNSCHA 224J, 2,959) is P37.5 and does not fit. KYET 154J is unrated. Not run
  through bank_air.

## Re-run (from this directory; all `python3 -I`)

```
python3 -I scripts/jlc_fetch.py detail C528962 C3781430 ...   # snapshots/jlc-raw (cached; delete a file to refetch)
python3 -I scripts/jlc_survey.py                              # snapshots/jlc_survey.csv (2,704 film parts >= 1 kV)
python3 -I scripts/jlc_summary.py                             # snapshots/jlc_stock_summary.json
python3 -I scripts/fetch_datasheets.py                        # dl/<key>/, dl/SHA256SUMS
python3 -I scripts/findchips.py parse                         # snapshots/findchips.json (Newark / Avnet / TME / brokers)
python3 -I scripts/octopart.py parse                          # snapshots/octopart/ (1 page; then 403)
python3 -I scripts/digitize_knscha.py                         # results/knscha_curves.json, controls must pass
python3 -I scripts/digitize_r75.py                            # results/r75_curves.json, control must pass
python3 -I scripts/bank_air_cand.py                           # results/bank_air_cand.{json,md}; controls 0.967 / 1.308
python3 -I scripts/voltage_rows.py                            # results/voltage_rows.{json,md}
python3 -I scripts/decision_inputs.py                         # results/decision_inputs.{json,md}; control = bank_air_cand 1.221
python3 -I scripts/options28.py                               # results/options28.{json,md}; controls: knscha 1.221 via share override, ESR model within 3 %
```

**Inputs read**
- 28 A jetmix pads bay61 / bay55: `worktrees/runs-native21/s49/c49/b3-bank-air/jetmix`, board 73702f18 (s49).
- Release pads: s49 lane `worktrees/ps-selv` (branch claude/native21-s49-c34-bank)
  `.../b3-ratings/runs/c17.5_h10_p0p25.json` and `p0p5.json`. **Both are board 4876c42e, not s49's 73702f18.** The files
  were rewritten 2026-10-16 about 12:00 local, and 4876c42e was earlier identified as the s50 board.
- PS `airflow28-2026-10-16/results/enclosure.json` and `bank28-air/results/bank_pads.json`.
- data/bank-voltage-s49.json is a byte copy of s49 commit db60f2692.
- data/candidates.json holds the per-part inputs. Rows marked ESTIMATE (wima, b32643h) are not datasheet values.
- The DigiKey reads are transcribed by hand in snapshots/digikey-2026-10-16.json (browser, about 18:05-18:35Z, no login).
  This is the one snapshot no script reproduces.

## Caveats

- **KNSCHA rating basis is weaker than TDK's.** The curve is for a 10 K internal rise at ambient <= 85 C. Above 85 C the
  derating is ASSUMED linear, because the sheet gives no rule. There is no ESR/tan d per part, no AEC, and no UL file.
  This is a HOT-side tank part, so no UL/ENEC approval is required.
- **The gap-flow credit is a reported sensitivity, not the gate.** Its only validation is that it reproduces bank28's
  c34 slot sensitivity (0.926 vs 0.93).
- **Pad heat (k_pad 80.6 K/W) is crude.** It gives "inf" for the KEMET Th rule and is not used as a gate.
- **The release ratios (0.957 / 1.208 for KNSCHA) use pads from board 4876c42e (both p0p25 and p0p5), not the s49 board.**
  Re-run on an s49 release solve before quoting them as s49 numbers. The 28 A numbers use s49 board 73702f18.
- **B32643H rows are estimates.** The datasheet was refused (403) and was not read.
- **Stock moves.** Every count is a 2026-10-16 read with the fetch time recorded in its snapshot.

## Datasheets (dl/SHA256SUMS, first 16 hex)

All of these are LCSC downloads. The KEMET F3106_R75 / F3034_R76 and WIMA_MKP10 PDFs are in dl/ as well, with full
sums in dl/SHA256SUMS.

| sha256 (first 16 hex) | file |
|---|---|
| 4621763054ad5e92 | C528962 KNSCHA MMK104J3DF1KN208G2 |
| 15c7cdc95e9d3b40 | C528963 KNSCHA 224J |
| 39ea96c070da5f1e | C565696 KNSCHA family / 1600 V (chart source) |
| eae18ecc7978c7b0 | C3975308 KNSCHA 334J |
| eb06f85ebd41fe3f | C3804413 TDK B32653A |
| 5c450eb4a203f34b | PHE450 (C3781501 / C3793752) |
| 036e025167231455 / 93dbdd889ffa769b / ef1f787f37281f25 / 4a926f5c4b02af81 / f60478a0400d5ae2 | KYET |
| ffbd1a92416c4f9d / 110644ea17bbabc9 | Faratronic |
