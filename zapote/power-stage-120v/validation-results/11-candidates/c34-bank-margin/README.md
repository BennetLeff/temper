# Candidate 34: resonant-bank margin at the 28 A tank ceiling (desk study, no board change)

DECISIONS 10 sizes the hardware for a 28 A line-cycle tank RMS ceiling. The board ships at 22 A and moves to 28 A
only on bench evidence. The bank is the weakest 28 A item: at 85 °C the fitted 5 × TDK B32654A1104J000 sits above its
vendor curve. This study looks for a bank that carries 28 A with real margin.

**Answer:** 5 × **TDK B32643B8104J000** (B3264\*B "High frequency" MMKP, 100 nF ±5 %, 2000 V DC / 500 V AC,
14.5 × 29.5 × 26.5 mm, 22.5 mm pitch).
- Worst-share ratio at 28 A and 85 °C: **0.831** at the 35 kHz floor, 0.796 at 50 kHz. Today's bank is 1.045.
- That ratio is measured against a stricter 15 K self-heating curve. In the vendor's own terms the worst part rises
  about 10 K, where today's rises about 22 K.
- Same 0.50 µF, so f_res and round-6 yield do not change.
- The layout needs a new footprint, one strip moved 5 mm, and 1.3 mm of one SELV track.
- **Not stocked** anywhere I could read. That is the one open gate before a stage.

Basis: stage 32 (`native21s32`, copper.json `d6f55dfe…`). Unit `zapote/power-stage-120v`, branch
`codex/power-stage-integration`, 2026-10-14/15. Python 3 `-I`, stdlib and numpy only. Vendor PDFs are not committed.
Their sha256 and pages are cited below and in `raw/parts_*.json`.

## 1. Figure of merit and the control

**Definition** (fixed before any candidate was scored, `scripts/bank_margin.py`):

ratio(f) = max over parts of I_tank · s_i / I_allow,i(f, 85 °C)

- I_tank = 28 A line-cycle RMS.
- s_i is the worst share: part i at +tol and every other part at −tol.
- f runs over the firmware window 35–50 kHz, f ≥ max(35 kHz, 1.05 f_res) (round 6).
- **Go means ratio ≤ 0.85 at every f in the window.** For every curve here the worst f is the 35 kHz floor.

All parts in parallel see one voltage, so the same test can be written as V_bank · (1 + t) / V_allow(35 kHz).

**Voltage at 28 A** (C_min = 0.475 µF, 35 kHz) is **268 V rms**. That is a bound: I ≤ ceiling, f ≥ floor,
C ≥ C_min.
- A 0.50 µF J bank therefore needs parts with V_allow(35 kHz) ≥ 268 × 1.05 / 0.85 = 331 V. The `per_part_35k`
  table in `results/bank_margin.json` lists each part's V_allow.
- **Estimated peak: 566 V pk**, using round 6's peak/rms of 2.113 at 28 A.

**Controls** (`results/bank_margin.json` → `controls`, all pass):

| Control | Reproduced |
|---|---|
| C1 round 6 `board-side-bank.csv`, 5 × 100 nF K: tank A at the 85 °C curve | 24.8 / 25.3 / 26.1 / 27.3 A at 35/40/45/50 kHz: exact |
| C2 `bank_options.json` (the scorecard source), ratio at 28 A and 40 kHz | K 1.105, J **1.022**: exact |
| C3 round 6's "1.12× at 28 A" = `board-side-protection.csv` 1.117 | 1.117 recomputed from the 405 grid cases (28 A, 0.50 µF, gap84) |
| C4 TDK p.57 100 nF curve at 99 kHz against the p.23 table | 0.990 |

**Why three numbers.** They describe the same bank on different bases:
- **1.117 (round 6)** uses the K share (0.234), each grid case at its own operating f, and the maximum over L 70/80/90 µH.
  The 80 and 90 µH configurations sit on the 35 kHz floor. The 70 µH coil alone gives 1.098 (K) and 1.015 (J) on the
  grid's nominal-L/C cases, whose lowest f is 36.1 kHz.
- **1.022 (scorecard `bank_ratio_tdk_28A_40k`)** uses the J share (0.2165) at a fixed 40 kHz.
- **The right basis is the J share at the worst legal frequency.** That is 35 kHz, which the firmware rule allows on
  any pan and which the round-6 Monte Carlo reaches with L and C at ±10 %. On that basis the fitted bank is
  **1.045**, carries 26.8 A at the curve, and carries 22.8 A at 0.85. The 40 kHz metric reads 2.2 % optimistic.
- The ledger entry for B32654A1104J000 has a slip. It says "±10 %" next to the J value of 26.8 A.

## 2. The slot

From `scripts/slot_geometry.py` → `results/slot_geometry.json`. It reads the committed copper, pads, parts and
placement. The control is that today's pads clear every hard obstacle (+0.10 mm). KiCad DRC remains the authority.

**Bank today:**
- C21 / C22 / C23 / C151 / C152 sit with pins at x 163.0 (res_a) and 190.5 (sw_b), rows at y 53.2 / 67.7 / 82.5 /
  97.0 / 111.5.
- Courtyard column: x 160.5–193.0, y 46.0–118.7 (72.7 × 32.5 mm).

**Free pin span: y 53.2–111.5 (58.3 mm), and today's bank uses all of it.**
- **Top:** RES_A pin 1 must sit ≥ 5 mm below the sw_b band (edge y 46.8; place.py). The bleed string R22–R25 lies above
  at y 41 (courtyards 3.8 mm off).
- **Bottom, SW_B column:** the SW_B pin must stay 8 mm from line_zc_raw on B.Cu (segment x 184.0–203.3 at y 121.27).
  That limits it to y ≤ 111.9.
- **Bottom, RES_A column:** the RES_A pin must stay 12.6 mm from the SELV lane (y 127.5 / 128.6). That limits it to
  y ≤ 113.5.
- J6 (PE) is below at 13 mm.
- The same limits hold for the 22.5 mm-pitch columns (res_a at x 168 or sw_b at x 185.5).

**Width:**
- The RES_A pin can move left to x 155.5 at every row. The limits are an n_ls In1 track and T1's pads, and the sw_a F.Cu
  pour must be re-cut.
- The SW_B pin can move right to x 199.0. The limits are C5's bus_p pads, an hv_ret track and line_zc_raw.
- So pitches from 22.5 up to about 43 mm are reachable.

**Height:** the first R43 solid over the bank is the coil plenum floor at z 81.0. That leaves **52.5 mm** over the
board top with a 1 mm gap. The components-allocation envelope leaves 48.1 mm. Height is not a constraint.

## 3. Candidates

`results/bank_table.csv` and `results/bank_margin.json` have every bank (25 rows).

Curves:
- TDK B3265x 1600 V: round 6's p.57 digitization.
- TDK 2000 V p.57: `digitize_tdk.py`, control against round 6 within 2.2 %.
- B32643B p.24: `digitize_b32643b.py`, 99 kHz within 1.2 % of the p.11 table.
- KEMET R76 p.8: `digitize_kemet_r76.py`, within 2 % of the p.22 / p.21 tables.

Top five, plus today's bank (J share, 85 °C, 28 A):

| Bank | C µF | Ratio 35 / 40 / 50 kHz | Self-heating at 28 A, vendor terms | Fit on stage-32 copper | Volts (Vdc) | Price per board, JLC ladder | Stock |
|---|---|---|---|---|---|---|---|
| Today: 5 × B32654A1104J (1600 V, P27.5) | 0.500 | 1.045 / 1.022 / 0.950 | 21.8 K (of 20) | yes | 1600 (F3 1683 V = 1.05×) | $2.61 | JLC 104 |
| **A: 5 × B32643B8104J** (2000 V, P22.5) | 0.500 | **0.831 / 0.816 / 0.796** | **10.4 K (of 15)** | new footprint, a strip moves 5 mm, SW_B row 5 needs **+1.7 mm** (line_zc_raw −1.3 mm) | 2000 (F3 0.84×) | $1.24 | **0** at JLC (C3781430, listed) and Avnet. MOQ 2080 untaped |
| B: 6 × B32643B8823J (P22.5) | 0.492 | 0.764 / 0.753 / 0.734 | 8.8 K (of 15) | as A, +4.2 mm: SW_B lane −3.8 mm and the RES_A-side SELV lane −2.2 mm | 2000 | not listed at JLC | 0 found |
| C: 4 × B32643B8124J + 1 × B32643B8683J (P22.5) | 0.548 | 0.814 / 0.809 / 0.788 | 9.9 K (of 15) | pin span 58.2 ≤ 58.3: footprint and strip only | 2000 | — | 0 found |
| D: 5 × KEMET R76UR3100SE30J (P27.5) | 0.500 | 0.933 / 0.906 / 0.863 | 17.4 K (of 20) | **yes, BOM-only** (14 × 28 × 32; the courtyard is 32.5 long) | 2000 | $3.11 (C3800216 variant) | 0 at JLC |
| E: 8 × KEMET R76TR2680SE30J (P27.5) | 0.544 | 0.806 / 0.778 / 0.737 (**ESTIMATE**, 68 nF unplotted) | 13.0 K (of 20) | **+8.2 mm** | 1600 | $7.44 (Avnet, MOQ 2448) | 0 |

Notes on the table:
- **Effect of C on yield** (round 6 `fstrat-b-bank-sweep.csv`, 70 µH, 220 mm, 28 A): 0.50 µF gives 88.6 %, 0.492 µF
  gives 89.0 %, 0.544–0.548 µF gives 82.5–83.0 %. So C and E cost about 6 points of yield, and A and B cost none.
- **KEMET's own temperature rule** (R76 p.6) allows more current when Th, the hotter of the surrounding air and the
  hottest contact point including tracks, is below 85 °C. The B3 model puts the bank pads at 77 / 78 °C at 28 A, h25.
  - At Th = 78 °C, D becomes 0.825. It needs Th ≤ 79.8 °C, which is only a model temperature.
  - TDK B3265x (p.64) and B3264\*B (p.25) give F_T = 1.0 below 85 °C, so they get no such credit.
- **Shadowing sensitivity** (estimate, not a bound). The 0.5 mm gaps shade each part's large h × l faces. If those
  faces shed nothing, the ratio rises to 1.47 (today), 1.16 (A), 1.08 (B) and 1.34 (D). The bench hot-spot reading
  decides, and A keeps the most room.

**Rejected** (numbers in `bank_margin.json`, `tdk_family_bound.json` and the agent notes summarised here):

TDK B3265x family (no arrangement that fits the slot passes; see `per_part_35k`):
- **1600 V:** 10 × A1473J reaches 0.853 but needs 45 mm more. 6 × A1104J reaches 0.874, at 0.60 µF and −13 points of
  yield. 7 × A1683J reaches 1.00 (estimate). Mixes run 1.06–1.47.
- **2000 V B32654A2:** passes (5 × A2104J at 0.771) but its 22 mm bodies need 32 mm more slot, and it costs $7.33.
- **The trade-off:** the family offers either V_allow ≥ 331 V or about 6.9 nF per mm of column, never both.

KEMET:
- **R76 0.82 µF / 0.1 µF 1600 V, 6–7 parts** fit but reach only 0.92 (estimate). The R76 27.5 mm parts are not
  AEC-Q200 (p.1).
- **R75:** no credit below 85 °C. It is similar to R76.
- **R73 (film/foil):** rated at Th 40 °C, about 55 % at 85 °C.
- **PHE450 / PHE448:** not for new designs. **C4AQ** is a DC-link part (ripple ≤ 0.2 V_N).

Vishay, all rejected:
- **MKP385:** 3.0 A per 0.1 µF at 100 kHz.
- **MKP383:** 10 K rise, no current table.
- **MKP386M:** too long for the slot.
- **MMKP386:** 85 °C maximum.
- **MKP1848 / 1837 / 1839 / 1840M / 1841:** DC-link, low voltage, or obsolete.

WIMA, all rejected:
- **MKP 10:** 15 K internal rise with no ambient stated, AC voltage derated from 75 °C, about 3.3–4 A per 0.1 µF.
- **FKP 1 / FKP 4:** too bulky.
- **MKP 4:** ≤ 1250 V.

CDE:
- **940C–943C:** axial, rated only at 70 °C / 100 kHz with no frequency rule.
- **942C:** the stage-13 rejection stands.
- **DPPM / DPFF / DPPS:** ≤ 33 nF at 1600 V.

Panasonic:
- **ECW-H(C)** is the IH-resonance series but publishes **no current rating**, and its 1250 V reopens F3.
- **ECW-FE / FD:** ≤ 630 V. **ECQ-UV** is an X2/Y2 safety-capacitor line.

TDK, other families:
- **B32643H:** peaks at 100 kHz, so 5 × 100 nF reaches 0.98 at 35 kHz.
- **B32656S / B32686S:** strap terminals.
- **B3267xL:** ≤ 47 nF.

Commodity induction-cooker MKPH / CBB parts (BM, Foshan CG, KYET, JURCC, generic MKPH):
- These datasheets give **no current rating**, so they cannot carry a margin claim.
- The rated Asian parts fall short: KNSCHA MMK224J (2 kV, 10.1 A at 35 kHz, ΔT 10 K basis) gives 1.45. Shizuki MIC-SA
  US16X224J (built for IH) gives 1.78. Faratronic C16 and KFSON TGC are snubber parts rated at 100 kHz or without a
  stated basis.

**Location and cooling, a different position instead of a different part:**
- TDK's curves are a self-heating rule (ΔT ≤ 20 K at T_A ≤ 85 °C), and F_T stays at 1.0 below 85 °C (p.64).
- A cooler spot therefore earns **no extra rated current** from TDK. Round 6's "≈ 38 A at 60 °C" (I² ∝ 105 − T_a) is
  not TDK's rule and should not be used.
- Moving the bank also does not help in practice. B3 shows the bank pads at 77–78 °C, against 50 °C air, because the
  copper conducts tank heat into the leads.
- What cooling can change is the real rise per watt: airflow across the column, or larger gaps. The slot has no spare
  length for gaps, so only the bench measures that. On the vendors' own rules, a different part is worth far more than
  a different location.

## 4. Recommendation and go / no-go

The 0.85 margin is kept. On a vendor curve it leaves 0.85² = 72 % of the rated self-heating. That headroom is what
absorbs the two effects the curve leaves out: the shadowed column and the 78 °C copper under the leads. A tighter 0.75
would rule out everything that fits.

| Gate | A: 5 × B32643B8104J | D: 5 × R76UR3100SE30J |
|---|---|---|
| Ratio ≤ 0.85, 35–50 kHz, 85 °C | **GO** (0.831 / 0.796) | NO-GO (0.933). Goes only under KEMET's Th rule if bench Th ≤ 79.8 °C |
| Fits | minimal re-placement (below) | GO, BOM-only |
| Voltage | GO: 566 V pk normal (0.28 of 2000 V DC); no-pan fault 775 V pk; F3 1683 V at 0.84×, which closes F3's 1.05× | GO, same |
| Stocked | **NO**: 0 at JLC and Avnet; DigiKey, Mouser and LCSC blocked the reads | NO |

**Ranked:**
1. **A.**
2. B, if a larger SELV-lane move is acceptable. It gives more margin (0.764).
3. D, as a no-layout fallback that roughly halves the overrun but is not a go.

## Proposed stage

"Bank to 5 × B32643B8104J000", BOM and layout:

**Parts:**
- C21–C23, C151, C152 change to TDK B32643B8104J000 (JLC C3781430).
- parts.ato gets a ResB32643B component.
- audit.rs identity strings need updating.
- Add a datasheet-ledger entry: 2000 V DC, 500 V AC, the p.24 curve, dV/dt 3800 V/µs, and ΔT ≤ 15 K (p.11 fn 8).

**Footprint and model:**
- New `temper:TDK_B32643B_P22.5_W14.5_L26.5_Radial` (0.8 mm leads, as today) and its STEP.
- The body is 5 mm shorter in x and 5 mm taller (29.5 mm).

**Layout:**
- Rows at y 53.2 / 68.2 / 83.2 / 98.2 / 113.2 (15.0 mm pitch at 14.5 mm maximum width).
- Keep RES_A at x 163.0 and move the SW_B column to x 185.5. That moves it away from C5's bus_p.
- Re-cut the sw_b and res_a strips (`patches21.py`, as stage 13 did).
- Move the line_zc_raw B.Cu segment x 184.0–203.3 from y 121.27 to ≥ 122.55. v15_selv at 123.6 stays, with
  0.75 mm between the edges.
- R22–R25 are unchanged.

**Gates to rerun:** DRC, barrier21 including RES_A 12.6 mm outer, D5, the fit gate (height), task 04 strips, B3 bank
rows, the CPL rotation audit (the part class changes), the ledger, audit.rs and the JLC class.

**Scorecard:**
- `bank_ratio_tdk_28A_40k` goes from 1.022 to **0.816**.
- `scorecard.py` reads only B32654A1104 parts, so it must learn the new MPN. The c34 results provide it.
- I recommend that the card carry the worst-f value: 1.045 → 0.831 at 35 kHz.

**Cost:**
- Same-channel JLC ladder: −$1.37 per board ($2.61 → $1.24).
- On the benchmark's DigiKey-derived price for today's J part ($1.9947 each), the saving would read −$8.73. Compare
  on one channel only.

**Unchanged:**
- C = 0.50 µF, so f_res, the round-6 yield (88.6 % at 28 A on 220 mm pans) and the firmware window stay.
- The tank current at 0.85 rises from 22.8 A to **28.6 A** at 35 kHz.

**Before the stage:**
- Get TDK or distributor stock and lead time for B32643B8104J000 (MOQ 2080 untaped).
- The B32643B8823J (option B) has no distributor listing at all.

**Release:** the bench hot-spot measurement stays the 28 A release condition (DECISIONS 2026-10-09). The expected rise
is about 10 K free-air plus shadowing, against a 15 K vendor basis.

## Open items

- **Stock and lead time** for every passing part. No passing part showed stock: JLC 0, Avnet 0, findchips no rows.
  DigiKey, Mouser and LCSC were bot-blocked to the readers.
- **B32643B8104 has a 14.5 mm maximum width.** At 0.5 mm gaps that leaves no spare length. If TDK's typical width is
  smaller, a 0.3 mm gap could be considered; that needs TDK's body tolerance.
- **The scorecard metric** should be redefined to the 35 kHz floor and the fitted MPN.
- **The ledger slip** ("±10 %" next to the J value).
- **ESTIMATE rows:** the KEMET 68 / 82 nF and TDK 68 nF values come from interpolated curves or an ESR model. They are
  not used for the recommendation.
- **Shadowing and hot-copper** effects are unquantified beyond the area estimate. Bench IR decides.

## Files

| What | Script → output |
|---|---|
| Slot geometry, neighbours, pin-span and pitch scans, R43 headroom | `scripts/slot_geometry.py` → `results/slot_geometry.json` |
| TDK 2000 V p.57 curves, with the p.57 1600 V control against round 6 | `scripts/digitize_tdk.py <MKP_B32651_658.pdf>` → `results/tdk_curves_c34.json` |
| TDK B32643B p.24 curves | `scripts/digitize_b32643b.py <MMKP_B32641B_B32643B.pdf>` → `results/b32643b_curves.json` |
| KEMET R76 p.8 curves | `scripts/digitize_kemet_r76.py <KEM_F3034_R76.pdf>` → `results/kemet_r76_curves.json` |
| TDK B3265x family lower bound (100 kHz tables) | `scripts/tdk_family_bound.py` → `results/tdk_family_bound.json` |
| Banks, controls, per-part V_allow, sensitivities | `scripts/bank_margin.py` → `results/bank_margin.json`, `results/bank_table.csv` |
| Part data (typed, with page citations) | `raw/parts_tdk.json`, `raw/parts_tdk_b3264.json`, `raw/parts_kemet.json`; banks in `raw/banks.json` |
| Stock / price records | `scripts/jlc_fetch.py` → `scripts/jlc-raw/`; findchips / blocked-site records in `raw/stock/` |

Run order: run `slot_geometry.py` first, then the three digitizers (each needs its PDF path), then
`tdk_family_bound.py`, then `bank_margin.py`. Each exits 1 on a failed control.

**PDFs used** (not committed; sha256):

| Datasheet | sha256 |
|---|---|
| TDK MKP_B32651_658 (6/26) | `c32e3754…afdd3` |
| TDK MMKP_B32641B_B32643B (6/26) | `ab9fdca0…4a58ab77` |
| KEMET F3034_R76 (3/21/2025) | `c45e4c7f…26804b9` |
