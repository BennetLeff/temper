# Stage 52 (s52-proto-bom): the prototype BOM

Selv lane, 2026-10-16, branch `claude/native21-s52-proto-bom` (from ca3cb9bc1). BOM-only stage: no copper edit. This
directory is the build record; the DECISIONS draft is item 74 (`DECISIONS-DRAFT.md`).

Board **32665572** (`32665572a65177f49076586cd87eb783c2baf1d39900ca776f09037996a5afc8`), copper key **3a4c616e7870**
(unchanged from s51). Chain run 3 reached CHAIN_DONE (`runs-native21/s52/chain3.out`, no spine owner). Every gate passes.
The card is **REJECT** against s51, as expected for a part swap that costs more and trades EMI margin for stock:

```
REJECT vs validation-results/10-benchmark/scorecard-native21s51.json: cheaper ['jlc_extended_lines', 'zero_stock_lines', 'lines_short_for_5', 'build_lead_wk_500', 'jlc_assemblable_share_5', 'bom_lines_short_proto'], better ['bank_ratio_tdk_28A_40k', 'bank_air_ratio_28A_35k']; emi_min_margin_dB worse: 11.1 vs benchmark 12.4 (tolerance 0.5); bank_ratio_tdk_28A_35k worse: 0.985 vs benchmark 0.978 (tolerance 0.0)
```

The point of the stage is `bom_lines_short_proto` **1 → 0**: the 20-board prototype lot is buildable from stock read on
2026-10-16. Taking the card is a sourcing override.

## 1. Change

| Line | s51 | s52 (prototype lot) | Why |
|---|---|---|---|
| C21-C23, C151, C152 | KNSCHA MMK104J3DF1KN208G2 (27.5 mm hole) | **TDK B32643H8104J000** (22.5 mm hole) | 24 A strict, not 22 A; DigiKey 306 against 100 |
| L1 | TDK B82726S2203A020 (0 authorised stock, 29 weeks) | **TDK B82726S2243A020** | Mouser 62 / DigiKey 29 against 20; the 2203 stays the production part (owner pre-order) |
| C3, C4 | Murata DE1E3RA222MA4BP01F (A4 long leads) | **Murata DE1E3RA222MJ4BH01F** (J4 crimp) | JLC C7170908 104 against 40; Y1 400 V, same body and certificates |

- **Source.** `parts.ato`: `ResB32643HBank` (dual-pitch footprint), `Cmc24A` (temper:B82726S2_ReviewOnly, pins a_in 1 /
  a_out 4 / b_in 2 / b_out 3, as the 2203), `CapY1_2n2H` (the Murata footprint unchanged). The old components stay.
  `power_stage_120v.ato` c_res1..5, l1, cy1 / cy2.
- **Frozen exports** (`frozen/` and `native-21/frozen/`, byte-identical): only those 8 components change (MPN,
  manufacturer, footprint, libsource). 372 components, 187 nets. `verify_source.py` asserts the three parts.
- **Footprint** `Bank_Film_DualPitch_P22.5_P27.5_Radial`: pads unchanged. The 3D model is now
  `TDK_B32643B8104J000.step`. B3264*H p.14 gives the same 14.5 × 29.5 × 26.5 mm maximum body as the B32643B, centred on the
  22.5 mm pitch. KNSCHA stays one model-path swap away.
- **CPL pose.** `bom_cpl_jlc.py` `DUAL_PITCH` centres a dual-pitch part on pad 1 and the pad-2 hole at its own lead
  spacing: the bank is at **x 174.250** (163.0 + 22.5 / 2), not s51's 176.75. An MPN the table does not carry raises.
  - The CPL audit's centre check (`cpl-rotation-audit/audit.py` `pad_bbox_centre`) reads the same table from the
    generator's source.
  - At s51 the 27.5 mm part's centre equalled the all-pads box by coincidence. Chain run 1 stopped on that check (2.5 mm
    error). There is a new selftest: 11.25 / 13.75 / KeyError.
- **Bank-variant fit mark** (owner-approved, `plan_board_only21.py` `bank_fit_mark`; regenerated into `board_only21.json`
  by the chain). On F.SilkS, right of the bank column's foot:
  - `BANK FIT, TICK ONE:`;
  - `[ ] H  B32643H8104J000  24 A MAX`;
  - `[ ] B  B32643B8104J000  28 A`.
  - Text 1.0 mm high (the board's existing 1.0 mm note size), stroke 0.15 mm (JLC minimum line width). Tick boxes are
    2 × 2 mm at 0.15 mm stroke.
  - The block spans x 193.9–223.5, y 114.2–121.1. The planner searches a 0.5 mm grid for the first spot near
    (163, 122) that clears everything it knows by 0.5 mm and sits 1.5 mm inside the outline.
  - `scripts/bank_mark52.py` (KiCad polygons plus shapely) gives these clearances on this board → `results/bank-mark-s52.json`:
    - mask openings 3.469 mm (C152 pad 2);
    - other silk 0.995 mm;
    - courtyards **0.65 mm** (C152);
    - board edge 18.9 mm.
  - Visible with the parts fitted: it is outside every courtyard. The nearest tall bodies are the bank column (C152 ends
    at x 187.5 for TDK, 192.75 for KNSCHA) and C3 / C4 (y ≤ 111.1). The jet strip (x 0–90, y 7–23.5) is far away, and FIT
    and the jet-strip height gate are unchanged.
  - review_fab **silk_on_land 0**.
  - DRC silk counts equal s51: silk_over_copper 199, silk_overlap 199, silk_edge_clearance 28. KiCad caps the listing at
    199 per type, so an equal count proves nothing for the first two. The geometric check above is the evidence.

## 2. Gates (chain run 3)

| Gate | s52 | s51 |
|---|---|---|
| Chain DRC | unconnected 0, errors 0; warnings lib 199 / silk_overlap 199 / silk_over_copper 199 / silk_edge 28 | same |
| Barrier / RES_A outer | 0 / 0 (min F.Cu 18.993, B.Cu 13.375) | same |
| D5 HOT-SELV / HOT-PE | 8.047 / 8.507 mm | same |
| RUST barrier | 0 violations, 6325 items | 6329 (see below) |
| DFM / FIT / jet strip | PASS 777 vias / 424 0 0 426 0 / 1.72 mm | same |
| SPINE_LOCK, BYPASS, return path | PASS | same |
| cu_temp_basis `--fail-waived` | PASS (124 files, 39 registered, 0 waived) | same |
| pin_absmax | 0 failures (new 0), 5 warnings, 9 undeclared | same |
| Kelvin | trip shift −2.41 A; band after **69.18–114.57 A** (floor 64.17) | 69.18–114.58 |
| B3 ratings | release +1.3 K (R10); laminate −50.8, rated part −51.0; **advisory +7.9 K** | advisory −0.3 K (KNSCHA 105 °C) |
| ERC | 1 error (power_pin_not_driven), the s51 set | same |
| BOM / CPL | 95 lines, 372 placements; CPL OK 300 / CORRECTED 32 / NEEDS-PREVIEW 24, excluded 16 | 303 / 32 / 26, 11 |
| review_fab | no_outer_copper 0, no_mask_opening 0, silk_on_land 0 | same |
| coil pickup / necks | `result-s52.json` = s51 but for the board hash; necks 0.993 / 1.021 (`s52_necks.json`) | same |

- **RUST items 6329 → 6325.** The difference is four zero-area coil_feed F.Cu fill slivers (x 131–133, y 82–88) that
  s51's fill had and s50's and s52's do not. They come from the same copper (key 3a4c616e7870). The bank is untouched.
- **CPL counts.** The bank (5, OK at s51) is excluded: it has no LCSC number and is consigned. C3 / C4 move from
  NEEDS-PREVIEW to OK on the C7170908 pin evidence (P10, no polarity). L1 (C7084710) stays NEEDS-PREVIEW: no EasyEDA
  footprint and no pin evidence, the same class as s51's 2203. It is consigned (JLC 0).
- **Kelvin band.** `bands52.py --check` first reported a mismatch. This board's own release solve gives a basis band of
  71.59–114.57 A against the carried 114.58. The B32643H bank and the 2243 L1 put less heat into the board, so the band
  network sits cooler. `kelvin_budget.BAND_BEFORE["native21s52"]` is set to this board's value, as s48's was, and chain
  run 3 uses it.
- **Board hash.** It changes on every chain run of the same inputs:
  - run 1 c2cd5ee1;
  - run 2 5597de62 (after the CPL-audit fix and a docstring-only parts.ato edit);
  - run 3 32665572.
  - The copper key and every geometric output are identical across the runs; s51's lane and integration builds differed
    the same way. Run 3 is the board of record. Task 04 and B3 are reused from run 1 on the content key, as the cache
    records.

## 3. bank_air and the ladder (the chain's producer, now B32643H)

`bank28-air/scripts/bank_air_metric.py` carries the TDK B3264*H rows:
- p.19 IRMS 6.155 / 6.481 A at 35 / 40 kHz for 100 nF (dT ≤ 20 K at TA 85 °C);
- the vendor's own F_T(T_A) self-heating rule (p.22: allowance 20 K × F_T², F_T 1.22 at 60 °C), digitised in
  `c51-bank-source/results/b32643h.json`;
- body 14.5 × 29.5 × 26.5 mm.

Its control is the c51 study's 1.006 on the s51 pads.

| On board 32665572, 28 A / 35 kHz, declared flow | Strict (the card) | Vendor ratio 35 / 40 kHz |
|---|---|---|
| **B32643H8104J000 (fitted)** | **1.006**: interior, @61 °C, lo G_board; ΔT 27.24 / 26.92 K; T_A 67.5 °C; hottest T_op 99.9 / 125 °C | **0.985 / 0.935** |
| KNSCHA MMK104J3DF1KN208G2 (fallback) | 1.221 | 0.978 / 0.984 |
| B32643B8104J000 (28 A part) | 0.967 | 0.831 / 0.816 |

**Release, still air** (c17.5_h10, bay 61 °C, air at bay + 15 K; worst interior part, lo G_board):

| Current | With radiation | Without radiation |
|---|---|---|
| **18.375 A** | **0.8707** (ΔT 17.62 / 23.24 K, T_A 76.8 °C, T_op 94.4 °C) | **1.1331** (ΔT 29.58 / 23.03 K, T_op 106.9 °C) |
| 17.5 A | 0.8332 | 1.0860 |

**Ladder** (`scripts/steps52.py`: the producer re-run at each tank current on this board's pads → `results/steps-s52.*`;
control: the 28 A row equals the chain's value). Strict means vendor ratio ≤ 0.85, gate ≤ 1.00 and T_op ≤ 125 °C.

| Tank A | 18 | 20 | 22 | **24** | 26 | 28 |
|---|---|---|---|---|---|---|
| Vendor ratio, 35 kHz | 0.633 | 0.703 | 0.774 | **0.844** | 0.915 | 0.985 |
| Gate (strict) | 0.647 | 0.718 | 0.790 | **0.862** | 0.934 | 1.006 |
| Strict OK | yes | yes | yes | **yes** | no (85 % rule) | no |

- The vendor ratio reaches 0.85 at **24.17 A**.
- **The highest strict step is 24 A** (s51 KNSCHA: 22 A).
- These numbers equal the c51 study's on the s49 pads.

## 4. Bank voltages (`scripts/bank_voltage52.py` → `results/bank-voltage-s52.{json,md}`)

`bands52.py --check` gives the bands on this board's solve. The c28 R1 phys top is 119.455 A (s51 119.461).

The B32643H limits are VR 2000 V, VRMS 700 V and VC(125 °C) 1500 V (1.25 %/°C Vop derating above 105 °C, p.15), with dV/dt
3800 V/µs (p.16).

| Row | Stress | Limit | Utilisation |
|---|---|---|---|
| F3, worst R0 / R1 (c28_h10@55 R1 phys) | 1693.1 V | 1700 V (0.85 VR) | **0.996** (+6.9 V) |
| F3, any reading (R4 phys) | 1786.6 V | 2000 V | 0.893 |
| Double fault Z0,max × top | 1607.1 V | 2000 V | 0.804 |
| No-pan | 775 V | 1200 V (0.8 VC) | **0.646** |
| V 28 A / Vrms | 566 / 268 V | 1600 / 560 V | 0.354 / 0.479 |
| dV/dt | 345.4 V/µs | 3800 V/µs | **0.091** |

- `audit.rs` `S49_BANK_VR` lists B32643H8104J000 at 2000 V.
- All three bank parts pass on this board.

## 5. L1, EMI and S1

- **L1 B82726S2243A020**, on the same TDK B82726S22*3A020 sheet (May 2026). p.4 gives IR 24 A, 0.75 mH, Lstray 8 µH and
  3.2 mΩ per winding. The derating curve on p.5 is shared.
  - At 15 A it uses 62.5 % of IR, and 63.0 % of Iop at the 61 °C release bay.
  - The **80 % rule holds to 82.5 °C** of local air (2203: 67.7 °C), and IR itself holds to 94.4 °C
    (`b15-proto-alternates/results/l1_rating.json`).
  - Copper loss is **1.44 W at 15 A against 2.03 W**. `make_heat_sources.py` reads the fitted MPN from the frozen CSV
    and writes 2 × R_typ × 15² for the L1 row. B3 scales it as before (13.5 A inlet bound).
  - L1's B3 body is 92.4 / 87.8 / 90.4 °C at c17.5 / c22 / c28, against the 2203's 102.4 / 97.8 / 100.4 °C.
- **EMI deviation (recorded, prototype only).**
  - The 8 µH stray loses the board's DM pole with C2. On the s19b model, with today's 2 × 41 µH module DM inductors,
    the margins are **6.03 dB nominal and 1.57 dB worst (INCONCLUSIVE)**: the 70 kHz DM line.
  - With an inlet-module DM inductance of **≥ 100 µH per line at 21 A** they are **11.14 / 6.95 dB (PASS)**.
  - `MODULE-REQUEST.md` item 3 now states that requirement. No 100 µH / 21 A part is selected yet.
  - The card reads the 100 µH design point (`scorecard.py`: when the BOM's L1 is the 2243 it reads
    `emi-B82726S2243A020_moduleDM100u/results.json`, and `emi_src` says so). Hence 12.4 → 11.1 dB on the compare line.
  - The production lot keeps the 2203 and its 12.37 dB.
- **C3 / C4 DE1E3RA222MJ4BH01F**: Murata Type RA reference specification EGD08G (Jun. 2023), LCSC copy sha256
  c959488a. PDF pages are cited; the printed n/17 footer is one less.
  - p.6: UL/cUL E37921, ENEC 40043033, CQC16001138225; X1 440 V, **Y1 400 V** (the P01F is 300 V), DC 1 kV.
  - p.9: J4 drawing and part list, D 9.0 / T 4.0 / F 10.0 / d 0.6 mm.
  - p.14: 8 kV impulse life test.
  - Same body, pads and drill, so creepage is unchanged (8.5 mm copper gap L_FILT / N_FILT to PE).
  - The J4 crimp seats the disc: the crimp is ≤ 3.0 mm below the disc, so the seated top is ≤ 12.0 mm. The 3D model's
    14.0 mm top is conservative, and FIT is unchanged.
  - Lead trim to ASSEMBLY.md's 2.5 mm: J4 leads protrude 1.35–2.85 mm.
  - **S1: 0.24123 mA, margin 8.77 µA, PASS** (`scripts/s1_52.py` → `results/s1-s52.json`; 2200 pF +20 %, unchanged; the
    ±30 % control gives 0.2522 mA, FAIL).

## 6. Ledger, audit, tests

- **Ledger** (`scripts/ledger52.py`, then `scripts/recite52.py`; idempotent):
  - **B32643H8104J000**: PARTIAL, 18 checks. Every violation row passes:
    - V 0.283, no-pan 0.517 / 0.8, Vrms 0.383;
    - I release 0.647 / 0.85;
    - **I at the 24 A strict step 0.844 / 0.85**;
    - **column self-heating at 24 A 20.01 / 26.92 K**;
    - F3 0.8465 / 0.85, double fault 0.804, dV/dt 0.091;
    - body at release 82.4 / 125 °C.
  - B32643H gap rows:
    - I 26 A 0.915 and I 28 A 0.985;
    - self-heating at 28 A: 19.4 / 20 K isolated, 27.24 / 26.92 K in the column;
    - case 99.9 / 125 °C;
    - release still air 17.62 / 23.24 K;
    - c22 86.5 °C and c28 105.0 °C.
  - B32643H gaps (8): rating basis, ESR, the F_T credit, S24 / S25, body dimensions, the 24 A ceiling (with the
    bank-fit-mark rule), sourcing, and approval basis. The approval basis is a HOT tank part, so no UL / ENEC file is
    needed; the case is UL 94 V-0 (p.2), with AEC-Q200D and IEC 60384-16:2019 (p.15) and THB 85/85 (p.24).
  - **B82726S2243A020**: PARTIAL, 9 checks. The violation rows pass at 0.625 / 0.625 / 0.6295 / V 0.559 / body 0.739.
    - The 82.5 °C boundary and the 16.5 A envelope are gap rows.
    - There is a new copper-loss stress row.
    - Gaps: local air, digitising, certifier (EN 60938-2 only, no UL / CSA), the EMI deviation and module requirement,
      the stray measurement, ALT-D3's 18 µH (8 µH moves the 250–500 µH line range by < 4 %, not re-run), and stock.
  - **DE1E3RA222MJ4BH01F**: PARTIAL, 3 checks: V 139.7 / 400 = 0.349, surge 0.275, touch current 0.9648 (margin 8.8 µA).
  - **Alternates** (not read by the gate), each with a status note:
    - MMK104J3DF1KN208G2: the in-stock fallback, 22 A strict;
    - B82726S2203A020: production, owner pre-order;
    - DE1E3RA222MA4BP01F;
    - B32643B8104J000: the 28 A part, tick B.
  - recite52 re-cited 14 entries' keyed B3 rows.
  - **Gate PASS: 3 VERIFIED / 92 PARTIAL / 0 UNAUDITED / 0 VIOLATION** (95 lines). `tests/test_gate.py` reports 0
    failures; its named-PARTIAL list now holds B32643H8104J000.
- **audit.rs**:
  - IDENTITY: c_res = B32643H8104J000, cy1 / cy2 = DE1E3RA222MJ4BH01F, l1 = B82726S2243A020.
  - `S51_BANK_PARTS` adds B32643H.
  - New `stage52_checks`: L1 and C3 / C4 must be on their footprints, with a part each footprint carries.
  - New test `stage52_proto_bom_holds`.
  - PASS on both exports (372 / 187); `--test` **94 / 94**.
- **B3 inputs**:
  - `thermal_body.py` `film_mmkp_h` (Top,max 125 °C; B3264*H p.2, p.15);
  - the gate ADVISORY and `report_convergence` rows;
  - `part-bodies.json` (bank and L1);
  - `make_heat_sources.py`: bank ESR typ 10.9 mΩ (p.14, 100 kHz); worst R_s 11.25 mΩ + D 2.93e-4 / (2π f C) from the p.15
    tan δ limits, 22.9 mΩ at 40 kHz. L1 as above.
- **Unit tests: all pass.**
  - test_track_geometry, test_spine_lock, test_track_cleanup21, test_trim_tails, test_jet_strip_height;
  - test_bom_pricing, test_cu_temp_basis, test_pin_absmax;
  - `scoped/test_scoped.py` 16 / 16;
  - test_b3_hot_copper, test_b3_airflow;
  - the CPL selftest;
  - **test_stock_gate**, with two new s52 cases (0 short lines at 20 boards; the bank's read is the s52 file) and the
    default-`--stock` order check generalised to several dated reads.
- **depmap_check** `--card` s51 and s52: C2–C6 PASS. C1 lists the same pre-existing cu_temp_basis / pin_absmax / price_* /
  bom_* entries on both cards. New path rules: `c51-bank-source/results/b32643h.json` → b3_ratings, and the b15 module-DM
  EMI result → card.

## 7. Cost and sourcing

| Line | s51 at 500 | s52 at 500 | 20-board lot |
|---|---|---|---|
| Bank (5) | $0.3035 × 5 = $1.52 (JLC) | $1.36626 × 5 = **$6.83** (DigiKey 1040+; P3: 306 < 2,500) | $1.7334 × 5 = $8.67 (DigiKey 50+) |
| L1 | $9.88 (DigiKey) | $9.21 (distributor) | Mouser 10+ $11.70; DigiKey 1+ $14.23 |
| C3 / C4 (2) | $0.14 (JLC) | $0.78 | JLC 10+ $0.9528 |

- `parts_usd_at_500_v2` 169.77 → **175.04 (+$5.27)**; `parts_usd_at_5_v2` 266.81 → 274.93 (+$8.12).
- **The brief's "L1 +$6" does not hold at 500:** the 2243 is $0.67 cheaper there. The difference is at 5 boards.
- `bom_lines_short_proto` **1 → 0** (the gate). The legacy survey metric `lines_short_for_5` goes 3 → 1.
- Zero-stock lines 7 → 6, consign lines 6 → 7, build lead at 500: 29 → 28 weeks. The production lot (information only)
  has 13 short lines at 500, as s51; L1 2243 has 62 against 500.
- **Stock basis.** All reads are from 2026-10-16:
  - the bank: `STOCK-2026-10-16-bank-s52.csv` (DigiKey 306, read 18:35Z, c51 lane; no JLC / LCSC listing, so it is
    consigned);
  - L1 2243 and the H01F: `STOCK-2026-10-16.csv` (Mouser 62 / DigiKey 29; JLC 104);
  - survey rows: `STOCK-2026-10-13-addendum-s52.csv`.
  - `apply_lcsc.py` adds C7084710 / C7170908. `jlc-raw/detail_C7084710.json` and `detail_C7170908.json` come from the b15
    snapshots.
  - `run_all.sh` has an s52 block, with `snapshot/s52/`.
- **OPEN-ITEMS:**
  - S24: the bank line;
  - S25: the pre-lot gate, now on the B32643H interior cap C22, pass ΔT ≤ 20 K × F_T² and ≤ 125 °C;
  - S28: the 28 A route, B32643B or the 11-body re-floorplan, plus the fit-mark rule;
  - B1: the L1 EMI re-run done;
  - B15: closed for the prototype lot;
  - owner action 7: the prototype-lot buys.
- **Price-channel notes on the compare.** The bank's s51 JLC price and s52 DigiKey price have no common channel, so the
  line is left out of the like-for-like saving. The scorecard's wording "no-stock catalogue price" means that no read
  holds the 500-board lot.

## 8. Production notes (not this lot)

- **Bank:** DigiKey 306 is the only stock; TDK lead time is 28 weeks with an untaped MOQ of 2080. A 500-board lot needs
  2,500.
  - The in-stock route is the KNSCHA fallback (JLC 4,952, 22 A strict).
  - The 28 A route is B32643B8104J000 (0 stock, 28 weeks) or the 11-body re-floorplan (OPEN-ITEMS S28).
- **L1:** the production part stays B82726S2203A020 (owner pre-order, 29 weeks). The 2243 has 62 + 29 authorised, against
  500.
- **C3 / C4:** JLC 104 against 1,000 for 500 boards; Mouser 6,002 and DigiKey 5,409 cover it.

## 9. Commissioning rule (owner)

The fitted bank part is recorded per board:
- **H** = B32643H8104J000: never above 24 A.
- **A board marked H, or with no mark, is never commissioned above 24 A.**
- **B** = B32643B8104J000: 26 and 28 A stay bench-gated per step. The mark alone raises nothing.
- A KNSCHA board (27.5 mm hole, no tick box) stops at 22 A.

These rules are written into `firmware/components/power/COMMISSIONING.md`: the ceiling precondition list, gate 1 (on the
fitted part) and a record row. The same note is in OPEN-ITEMS S28.

## 10. What did not match the brief

- **EMI on the card is worse (12.4 → 11.1 dB).** The card reads the module-DM-100 µH design point. Without that module the
  model is INCONCLUSIVE at 6.03 / 1.57 dB: a recorded prototype deviation.
- **bank_ratio_tdk_28A_35k is worse (0.978 → 0.985).** B32643H's 35 kHz vendor ratio is above KNSCHA's. The 40 kHz ratio
  (0.984 → 0.935) and bank_air (1.221 → 1.006) are better.
- **The bank still fails strict bank_air at 28 A (1.006 > 1.00).** Its strict cap is 24 A. 28 A is S28.
- **The cost is $6.83, not about $8.67, at 500.** $8.67 is the 20-board-lot price. L1 is −$0.67 at 500, not +$6.
- **The c51 study cites the B3264*H ordering table as p.13; it is p.14** on the sheet's own footer. This stage cites p.14.
- **The dual-pitch footprint still heats both pad-2 holes** in task 04 / B3, which treat the empty 27.5 mm hole as
  copper on sw_b, as at s51. This is conservative for the pad temperature and is not modelled per hole.
- **Board hash is not reproducible run to run** (section 2). The copper key and geometry are.
- **The CPL audit's centre check needed a fix** (section 1). This was found by chain run 1.
- **The Kelvin band top moved 0.01 A** (114.58 → 114.57) on this board's own solve. It is pinned per the s48 precedent.
- **L1 stays NEEDS-PREVIEW in the CPL audit** (no EasyEDA footprint or pin evidence for C7084710). It is consigned.

## 11. Reproduce

```
R=../../runs-native21/s52     # /Users/bennet/Desktop/temper/worktrees/runs-native21/s52 here
TASK04_WORKERS=4 sh native-21/layout/gates/chain.sh native21s52 ../../runs-native21/s51/p1/j1 $R/c52
S=validation-results/11-candidates/s52-proto-bom/scripts
python3 -I $S/bands52.py --check && python3 -I $S/bank_voltage52.py
python3 -I $S/steps52.py $R/c52/b3-bank-air && python3 -I $S/s1_52.py
python3 -I $S/bank_mark52.py $R/c52/section.kicad_pcb
python3 -I $S/ledger52.py && python3 -I $S/recite52.py && python3 -I native-21/verification/datasheet-ledger/gate.py
(cd validation-results/02-protection-timing/coil-pickup/s21b && F8_COPPER=../../../../native-21/verification/native21s52-all-copper.json.gz \
    python3 -I run_ocp.py && cp result.json result-s52.json && git checkout -- result.json)
(cd validation-results/02-protection-timing/shoot-through-f1 && python3 -I s21_necks.py s52)
cp validation-results/08-manufacturing-package/native-21/fab/bom-jlcpcb.csv \
   validation-results/08-manufacturing-package/native-21/sourcing/study-2026-10-15/snapshot/s52/bom-jlcpcb.s52.csv
bash validation-results/08-manufacturing-package/native-21/sourcing/study-2026-10-15/run_all.sh
python3 -I native-21/layout/gates/scorecard.py native21s52 $R/c52 --audit PASS \
    --json validation-results/10-benchmark/scorecard-native21s52.json --compare validation-results/10-benchmark/scorecard-native21s51.json
```
