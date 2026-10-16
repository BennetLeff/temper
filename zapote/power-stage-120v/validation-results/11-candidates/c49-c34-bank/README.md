# Candidate 49: the c34 resonant bank (5 x B32643B8104J000) and the S23 B'-1.02 V OCP divider (native21s49)

**Card: ACCEPT against s48.** Cheaper on `parts_usd_at_500_v2` (175.68 → 169.49) and `jlc_assemblable_share_500`.
Better on `kelvin_band_low_A`, the three B3 margins, the two vendor-curve bank ratios and `bank_air_ratio_28A_35k`.
Every gate passes. D5 (8.047 / 8.507 mm), RES_A outer (13.375 mm) and return-path opens (7) equal s48. B3 release
margin is +1.3 K (R10; s48 +1.2 K).
Board **73702f18** (copper key f704213432bf), chain run 2 CHAIN_DONE (`runs-native21/s49/chain2.out`, `SPINE_OWNER=selv`).

Branch `claude/native21-s49-c34-bank` (one-writer layout lane, worktree `ps-selv`), from b8ddef3da. Scope: DECISIONS 68
(fit the c34 bank) and, added mid-lane, OPEN-ITEMS S23's BOM-only fix B'-1.02 V
(`11-candidates/s23-ocp-cm-2026-10-16/results.md` section 5). The integrator decides (`DECISIONS-DRAFT.md`, item 70).

```
ACCEPT vs validation-results/10-benchmark/scorecard-native21s48.json: cheaper ['parts_usd_at_500_v2', 'jlc_assemblable_share_500'], better ['kelvin_band_low_A', 'b3_laminate_margin_K', 'b3_rated_part_margin_K', 'b3_release_margin_K', 'bank_ratio_tdk_28A_40k', 'bank_ratio_tdk_28A_35k', 'bank_air_ratio_28A_35k']
```

**The cost move is overstated by the price channels.** The card prices the old bank from DigiKey at $1.48848 (P3, nobody
holds 2,500). It prices the new one from JLC's catalogue ladder at $0.248 (P3, JLC listed with 0 stock). So it reads
−$6.19 per board. Compared on one channel:
- JLC to JLC is −$1.37 (C3794777 $0.5221 → C3781430 $0.248);
- DigiKey to DigiKey is −$0.90 ($1.48848 → $1.30931 at MOQ 2080, DECISIONS 37).

The ACCEPT does not depend on the cost: seven performance metrics improve and none falls.

## 1. The bank: TDK B32643B8104J000 on C21-C23, C151, C152

TDK B3264*B data sheet, June 2026 (`runs-native21/bank28/dl/b3264/MMKP_B32641B_B32643B.pdf`, sha256 ab9fdca0…4a58ab77;
PDF page = footer page). Facts used:

| Quantity | Value | Page |
|---|---|---|
| VR / VRMS | 2000 V DC / 500 V AC | p.11 (22.5 mm table header) |
| Body w × h × l, max | 14.5 × 29.5 × 26.5 mm | p.11, row B32643B8104+*** |
| Lead spacing / diameter | 22.5 ± 0.4 mm / 0.8 ± 0.05 mm | p.2 (dimensional drawing) |
| IRMS,max 85 °C 100 kHz / ESR typ | 8.3 A for ΔT ≤ 15 K (note 8) / 8 mΩ | p.11 |
| Top,max (case) / TR | 125 °C / 85 °C | p.2, p.12 |
| Category voltage above 85 °C | VC = VR × (165 − Top) / 80 (1000 V at 125 °C) | p.12 |
| tan δ max | 0.6 / 0.6 / 1.5 × 10⁻³ at 1 / 10 / 100 kHz | p.12 |
| Test voltage, terminal to terminal | 1.6 VR, 2 s | p.12 |
| dV/dt, k0 (22.5 mm, 2000 V) | 3800 V/µs, 15 × 10⁶ V²/µs | p.13 |
| Untaped MOQ | 2080 | p.11 |

**Approval basis.** This is a HOT-side tank part, not a safety capacitor, so it needs no UL / CSA file (as for
B32654A1104J000). The case is UL 94 V-0 (p.2) and the part is AEC-Q200D.

**Footprint** `libraries/temper.pretty/TDK_B32643B_P22.5_W14.5_L26.5_Radial.kicad_mod`:
- pads 2.4 mm with a 1.2 mm drill at 0 and 22.5 mm;
- fab −2.0..24.5 × ±7.25, courtyard −2.5..25.0 × ±7.45 (the bank stacks at 15.0 mm pitch, 0.5 mm gaps);
- 3D model `models3d/capacitors/TDK_B32643B8104J000.step` / `.wrl` (generate.py / generate_step.cpp entries).

**Pad 1 is round**, like pad 2 (the part has no polarity). On pass p4 the square pad 1 corner of C152 was 8.035 mm, in
plan view, from the In1 v3v3 plane corner at (159.9, 122.2). That is below s48's 8.047 mm HOT-SELV minimum. Round, it
is 8.325 mm.

**Placement** (`place.py` `S49_BANK`, posed after every restore so no other part moves):
- RES_A pins at x 163.0, SW_B pins at x 185.5;
- rows y 53.2 / 68.2 / 83.2 / 98.2 / 113.2;
- the bodies span x 161.0–187.5, y 45.95–120.45.

The air column of DECISIONS 68 (x 161–193, y 46–119) stays open. The bodies reach 0.05 mm above and 1.45 mm below its
y limits, because 5 × 14.9 mm of courtyard needs 74.5 mm against its 73.

## 2. What changed in copper (`patches21.edit_base49`, frozen s48 copper)

- **sw_b strip** (B.Cu): left edge x 188.0 → 183.0; bottom y 112.9 → 114.4 at x 183–192 (the row-5 pad edge).
- **res_a strip** (B.Cu): bottom y 112.9 → 114.6 at x 163–166. A notch keeps y 112.9 at x 161–163. That holds the plan-view
  8 mm to the In1 / In2 SELV planes' corner at (160.0, 122.2): 8.17 mm. Pass p2, with all of x 161–166 at 114.6, had 2
  barrier violations at 7.706 mm.
- **line_zc_raw** (SELV, B.Cu), two changes:
  - The x 184.0–203.3 run moves y 121.27 → **122.75** (c34 planned ≥ 122.55). At 122.55 the SW_B row-5 pad sat 8.025 mm
    from it (p3, chain 1), and D5 fell from 8.047 to 8.025. At 122.75 it is 8.225 mm.
  - The y 127.5 run **dips to y 128.2 over x 157.7–171.3**, with 45° legs. The res_a strip corner (163–166, 114.6) was
    12.775 mm from it on p3, under s48's 13.375 mm RES_A outer minimum. Now it is 13.475 mm. J6's PE pads come to
    4.88 mm (was 5.58), SELV to PE. Nothing else on B.Cu is within 3.7 mm.
- No other copper moved. The spine lock passes (owner selv): the runs are outside the region (x 30–110, y 130–180).
- **S10 HOT-side return-path opens** (bus_fault_hot / ocp_ok_hot / ovp_ok_hot / U45.1 near x 105–125, y 50–65) are not in
  the re-cut area. None was closed; there are still 7 opens, as at s48.

Passes (`passes49.sh`, base = s48 copper.json `git show b8ddef3da:…`, sha 592a0d38…):

| Pass | Result |
|---|---|
| p1 | invalid (placement bug), killed |
| p2 | j1 clean except 2 barrier violations (the res_a corner) |
| p3 | j1 clean; chain 1 stopped: D5 8.025 and RES_A outer 12.775 mm |
| p4 | the line_zc_raw moves; RES_A outer 13.375, D5 8.035 (square pad 1) |
| **p5** | round pad 1. **j1: unconnected 0, errors 0, barrier 0, RES_A outer 0** (min F.Cu 18.993, B.Cu 13.375) |

## 3. S23 B'-1.02 V: R33 7.5 k, R34 16 k, R35 11 k (BOM only, same 0603 pads)

| Ref | Was | Now | LCSC (JLC stock 2026-10-16) |
|---|---|---|---|
| R32 | RT0603BRD0710KL | unchanged | C95204 |
| R33 | RT0603BRD0710KL | **RT0603BRD077K5L** | C728597 (20,378) |
| R34 | RT0603BRD0712K6L | **RT0603BRD0716KL** | C326732 (17,962) |
| R35 | TNPW060311K7BEEA | **RT0603BRD0711KL** (existing line) | C728581 (10,027) |

These hold the nominal trip, 92.593 A. They move U6's trip common mode 1.204 → 1.0185 V. The trip sensitivity to an
input offset falls from 2.00 to 1.75 A/mV.
- **Gate:** `audit.rs` `stage49_checks` checks:
  - nominal 92.593 ± 0.25 A;
  - VCM inside 0.95–1.10 V;
  - C30 × (R32 ‖ R33) ≤ 500 ns.
- REF25 loads: `ocp_offset_load` 20 k → 17.5 k and `ocp_threshold_load` 24.3 k → 27 k.

**Bands on this board's own solve** (`scripts/bands49.py`, the committed bands47 engine with the B' divider plus S23's
TLV3201 terms, Kelvin shift −2.41 A from `kelvin/budget-native21s49.json`):

| Network | R0 band before Kelvin | Low after (margin) | R1 low (margin) | R4 (spec-literal) | OVP (R0) |
|---|---|---|---|---|---|
| Release c17.5 @ 61 | **71.59–114.58 A** | 69.18 (+5.01) | 66.54 (+2.37) | 59.92 (−4.25) | 272.61–287.47 V |
| c28 @ 55 | 70.50–115.96 A | 68.09 (+3.92) | 65.46 (+1.29) | 58.87 (−5.30) | 272.47–287.62 V |

All rows are HOT5 Q1 (4.89–5.11 V); the physical HOT5 window (4.632–5.5 V) costs about 0.4–0.7 A more (c28 R1 phys
+0.58 A). R4 (VIO taken flat at 5.4 mV) still fails, as in S23: the bench run (S23 section 4, Option C) closes S23.

- `kelvin_budget.BAND_BEFORE["native21s49"]` = (71.59, 114.58). That is this board's release R0 band with the HOT5 Q1
  PSRR term. `bands49.py --check` passes.
- Budget after Kelvin: **69.18 A** (s48 card 66.46).
- The committed engine alone reads 71.70–114.47 A, inside that basis.
- Control: on the s48 solve (ps-integrate runs) the script gives S23's 71.57–114.60 A exactly.
- U7 / OVP: untouched. The solved top is 287.47 / 287.62 V, ≤ 288.02 V. The "hottest uniform" bound rows read
  288.03 / 288.27 V, as their s47 / s48 counterparts did; they are a bound, not the acceptance row.

**Side checks:**
- C30 τ: 4.29 k × 100 pF = **429 ns** (500 ns before), under the 500 ns front-end RC (`audit.rs`).
- REF25 minimum cathode current: **98.8 µA** > 65 µA IRMIN (107.5 µA before).
- H1 watchdog: the trip window (63.4 k / 11.7 k, 0.1 % + 25 ppm/K × 100 K, VIT 0.396–0.404 V) is 2.526–2.610 V.
  - It sits above VR max 2.5162 V.
  - It sits below REF25 with U5 open, now 2.816 V at its lowest (was 2.845 V with the s48 loads).
  - Checked in `audit.rs` stage48_checks and the stage-49 test.
- Kelvin census unchanged: 15.505 mA.
- Coil pickup stack 4.17 A, = s48 (`coil-pickup/s21b/result-s49.json`).

**The s48 band in the records is the s47 solve.** `kelvin_budget.BAND_BEFORE["native21s48"]` = (68.87, 117.45). The s48
board's own solve gives 68.63–117.70 A. The s48 entry is left as committed, with a comment, and the s49 entry is this
board's own solve.

## 4. Bank voltages with 2000 V (`scripts/bank_voltage49.py` → `results/bank-voltage-s49.{json,md}`)

**F3** (CT-failed third fault, quasi-steady just under the shunt band top, no f floor) is linear in the OCP top: 1,683 V ×
top / 118.74 A.
- At the s49 tops it is 1,624–1,693 V (R0 / R1, both HOT5 windows).
- **Worst R0 / R1: c28 R1 phys, 1,693.2 V = 0.847 of 2000 V.** That is ≤ 0.85 (`audit.rs` S49_BANK_VR).
- The committed 1,683 V is 0.84×.
- The spec-literal R4 reading gives 1,787 V (0.89).

**CT-failed double fault, Z0,max × OCP top** (Z0,max 12.75 Ω):
- R0 release: 1,461 V;
- R1 c28 phys: 1,523 V;
- R4: 1,607 V.
- Against the old 1600 V rule, the B' top gives R0 +139 V (S23: about +43 V against the as-built divider).
- **Against the new 2000 V: ≥ +393 V on every reading.**

**dV/dt** at the largest turn-off current: 345 V/µs, 0.09 of 3800 V/µs.

**No-pan fault**, 775 V against VC at 125 °C (1000 V): 0.775 ≤ 0.8. That is the tightest bank voltage row.

## 5. Thermal

**B3:** the bank class is `film_mmkp`: r_pad 50 K/W, Top,max 125 °C, ESR 8 mΩ typ. The loss fit is to the p.12 tan δ:
R_S 15.9 mΩ, D 5.0e-4. This is an advisory row.

| Case | Hottest bank part | B3 temperature | Margin to 125 °C | s48 fitted bank (against 110 °C) |
|---|---|---|---|---|
| Release c17.5 @ 61 | C21 | 82.8 °C | +42.2 K | 90.4 °C |
| c22 @ 55 | C21 | 87.1 °C | | |
| c28 @ 55, still air | C21 | 106.2 °C | | 126.0 °C |

Release margin +1.3 K (R10, s48 +1.2). U5 91.3 °C.

**bank_air_ratio_28A_35k now follows the board.** chain.sh solves B3 cases `c28_h20_jet100@61` and `c28_h15_jet100@55` on
this board (`$B/b3-bank-air/jetmix/`, run files checked against the board hash), then runs
`bank28-air/scripts/bank_air_metric.py`.
- The producer's control (bank_thermal.py on the s47 airflow28 runs) is not board-following, so the chain passes
  `--control ''`.
- depmap: b3_ratings now produces the card entry. Its inputs (bank_air_metric.py, the c34 parts files and bank_margin,
  airflow28 enclosure.json) are path rules and step files, so C1 no longer lists it. C4 / C6 pass.

| Bank | s48 (pads from the s47 airflow28 runs) | s49 (this board's pads) | Worst point |
|---|---|---|---|
| Fitted B32654A1104J000 | 1.308 | 1.308 | interior, ΔT 34.2 / 20 K |
| **c34 B32643B8104J000 (fitted)** | (0.967) | **0.967** | interior, design flow @61 °C, ΔT 14.04 / 15 K, T_A 67.5 °C; hottest T_op 88.9 / 125 °C |

Vendor-curve ratios (info): 0.831 at 35 kHz, 0.816 at 40 kHz.

## 6. Sourcing

**C3781430** (JLC Extended THT):
- listed with **0 stock**; ladder 12+ $0.6738, 1040+ $0.248;
- untaped MOQ 2080 (p.11), 28-week lead;
- DigiKey $1.30931 at MOQ 2080 (DECISIONS 37).

**This is an owner pre-order, consigned to JLC:** 2,500 parts for 500 boards plus attrition, which means buying 4 × 2080
MOQ lots or a distributor split. It goes in `STOCK-2026-10-13-addendum-s49.csv` with flags
ZERO_JLC_STOCK;OWNER_PREORDER_CONSIGN;LONG_LEAD.
- R33 / R34 rows are in the same addendum.
- `run_all.sh` gains the s49 block (`snapshot/s49/`); `../SNAPSHOT-2026-10-15.csv` is re-merged.
- `apply_lcsc.py` maps the three new MPNs.

**TLV3201AIDBVR (C105188), re-read 2026-10-16:** JLC 3,221 against 2,500 needed (U6, U7, U10, U11, U12 × 500). Put it on
the pre-order note with the bank.

## 7. Gates and records

- **CPL rotation audit:** a new non-polar THT evidence path (`audit.py`, with selftests). It uses pin-evidence C3781430
  (p.2: e 22.5 ± 0.4, d1 0.8, no polarity).
  - The five bank caps are OK at 0/180. Their NEEDS-PREVIEW renders are removed.
  - Totals: OK 303 / CORRECTED 32 / NEEDS-PREVIEW 26 (s48: 298 / 32 / 31), covering 372 / 372. BOM / CPL designators PASS.
- **Ledger** (`scripts/ledger49.py`, `scripts/recite49.py`):
  - B32643B8104J000 replaces B32654A1104J000, PARTIAL. 14 checks, every violation-severity row passes:
    - V 28 A 0.283; no-pan 0.775 / 0.8; Vrms 0.536;
    - I release 0.546; I design 0.831 / 0.85; self-heating 10.4 / 15 K;
    - F3 0.847 / 0.85; double fault 0.804; dV/dt 0.091; body at release 0.662.
  - Gaps: the airflow route (S24 / S25), sourcing, digitised curves.
  - New entries RT0603BRD077K5L (R33) and RT0603BRD0716KL (R34). Yageo RT V.16 p.5 Table 2: 75 V, 0.1 W. Temperatures
    from bands-s49.json.
  - RT0603BRD0712K6L leaves. TNPW060311K7BEEA is R145 only. RT0603BRD0711KL gains R35. RT0603BRD0710KL loses R33.
  - recite49 re-cited 23 entries' keyed B3 rows.
  - Gate PASS: 3 VERIFIED / 92 PARTIAL / 0 / 0. `tests/test_gate.py` 0 failures; its named-PARTIAL list now holds the new
    bank MPN.
- `audit.rs` PASS (372 components, 187 nets), `--test` 91 / 91. `verify_source.py` PASS.
- `test_track_geometry`, `test_spine_lock`, `test_track_cleanup21`, `test_jet_strip_height`, `test_bom_pricing`: PASS.
  `scoped/test_scoped.py` 16 / 16.
- depmap_check C2–C6 PASS. C1 lists the cu_temp_basis / pin_absmax / price_* entries, as it did at s48 (pre-existing).
  bank_air is off that list.
- `test_cu_temp_basis` and `cu_temp_basis --fail-waived` PASS. `test_pin_absmax` and `pin_absmax --fail-stale` PASS (0
  failures, 0 stale).
- `test_b3_hot_copper` and `test_b3_airflow`: 0 failures. Firmware host tests 31 / 31 (firmware unchanged).
- After the chain: `s21_necks.py s49` (0.993 / 1.021, = s48); coil pickup `result-s49.json` (4.17 A).

## 8. What did not match the brief

- **line_zc_raw at y 122.75, not 122.55, plus a dip at y 128.2.** Both hold D5 and RES_A outer at s48's values
  (section 2).
- **The bank footprint's pad 1 is round** (section 1).
- **The column does not fit inside y 46–119 exactly.** The bodies span y 45.95–120.45, because 5 × 14.9 mm courtyards at
  15 mm pitch need it.
- **The card's cost delta is a price-channel artefact** (top of this file). The decision does not rest on it.
- **Ledger temperature rows** for lines whose designators moved (TNPW R35 → R145-only, RT0603BRD0711KL with R35,
  RT0603BRD0710KL without R33) still carry their s48 temp-ratings rows, with a stage-49 gap. The S21 temp-ratings
  re-base on s49 is the integrator's step, as at s48.
- **`thresholds.py` `validate_inputs` defaults stay the round-3 BOM.** Committed round-3 records import them, and its own
  main() already fails on the current BOM. The s49 MPNs are passed as overrides (`bands49.py`) and listed in its
  docstring.
- **Fresh JLC reads** of C105188 and C3781430 overwrite two `jlc-raw` files (2026-10-16).

## 9. Reproduce

```
sh validation-results/11-candidates/c49-c34-bank/passes49.sh runs-native21/s49/base-s48-copper.json runs-native21/s49/p5
SPINE_OWNER=selv TASK04_WORKERS=4 sh native-21/layout/gates/chain.sh native21s49 runs-native21/s49/p5/j1 runs-native21/s49/c49
python3 -I validation-results/11-candidates/c49-c34-bank/scripts/bands49.py --check
(cd validation-results/02-protection-timing/kelvin && python3 kelvin_budget.py native21s49)
python3 -I validation-results/11-candidates/c49-c34-bank/scripts/bank_voltage49.py
python3 -I validation-results/11-candidates/c49-c34-bank/scripts/ledger49.py && python3 -I .../scripts/recite49.py
python3 -I native-21/layout/gates/scorecard.py native21s49 runs-native21/s49/c49 --audit PASS \
    --json validation-results/10-benchmark/scorecard-native21s49.json --compare validation-results/10-benchmark/scorecard-native21s48.json
```
