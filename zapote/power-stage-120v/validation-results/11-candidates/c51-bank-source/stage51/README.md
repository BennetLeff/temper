# Stage 51 (c51-bank-source): dual-pitch bank footprint, KNSCHA MMK104J3DF1KN208G2 fitted

**Integrated as DECISIONS 73 (2026-10-16): board of record s51 with a sourcing override, integration build 0b0ebcf7**
(geometry identical to the lane build 9afc509b, copper key 3a4c616e7870; `results/geom-s51-lane-int.json`; chain
`runs-native21/s51/chain-int.out`, no spine owner). Integration card: REJECT vs s50 (bank metrics, +$0.28), better on the
20-board stock gate (`bom_lines_short_proto` 4 → 3); ACCEPT vs s48. The S25 pre-lot gate is on **C22**, the hottest
interior cap on this board (B3, release solve and both jetmix runs), not C151. OPEN-ITEMS rows are re-applied on the
integration copy (S24, S25, S28, owner action 7, B15). The S21 temperature rows are re-based on s51 (`scripts/temps_snap51.py`).

Selv lane, 2026-10-16, branch `claude/native21-s51-dual-pitch-bank` (from the s50 lane head 29f16fd77). This directory is
the build record. The sourcing study that chose the part is `../README.md` (the bank-src lane, copied here; see section 8).
The DECISIONS draft is item 73 (`DECISIONS-DRAFT.md`).

Board **9afc509b** (`9afc509b6944fb79ed05deded285fa81ba743fdbce56900b22d4f3686db25429`, copper key 3a4c616e7870). Chain run 1
reached CHAIN_DONE (`runs-native21/s51/chain1.out`, `SPINE_OWNER=selv`). Every gate passes. The card is **REJECT** against
s50, as expected: bank_air and both vendor-curve bank ratios are worse than c34's, and the part costs more. Taking it is a
sourcing override.

```
REJECT vs validation-results/10-benchmark/scorecard-native21s50.json: cheaper ['zero_stock_lines', 'lines_short_for_500', 'lines_short_for_5', 'jlc_assemblable_share_500', 'jlc_assemblable_share_5'], better []; bank_ratio_tdk_28A_40k worse: 0.984 vs benchmark 0.816 (tolerance 0.0); bank_ratio_tdk_28A_35k worse: 0.978 vs benchmark 0.831 (tolerance 0.0); bank_air_ratio_28A_35k worse: 1.221 vs benchmark 0.967 (tolerance 0.0); costlier on ['parts_usd_at_500_v2'] with no performance gain
```

**Stock (for the integrator's stock snapshot):** KNSCHA MMK104J3DF1KN208G2, JLC **C528962**, **4,952 in stock** (pre-sale
4,928) against the **2,500** a 500-board lot needs (5 per board). Read **2026-10-16** (JLC part API, `_fetched_utc`
2026-10-16T17:48:28Z; `../snapshots/jlc_stock_summary.json`, `sourcing/study-2026-10-15/scripts/jlc-raw/detail_C528962.json`).
Ladder 10+ $0.4764, 1000+ $0.3035. This branch does not have the ps-integrate stock gate (DECISIONS 72, 626ea8e48 /
2d2165bd8), so the card above has no `bom_buildable_500` / `bom_lines_short_at_500`; the integrator re-scores s51 with it.

## 1. Change

- **Part.** C21-C23, C151, C152: TDK B32643B8104J000 (JLC 0, 28-week lead, MOQ 2080, rejected by the owner) →
  **KNSCHA MMK104J3DF1KN208G2**, MMKP82 100 nF ±5 % 2000 V DC / 700 V AC, P27.5.
  - Source: `parts.ato` `ResMmkp82Bank`, `power_stage_120v.ato` c_res1..5. The `ResB32643B` component stays in
    `parts.ato` for the alternate.
  - Frozen exports (`frozen/` and `native-21/frozen/`, byte-identical): only the five bank lines change (MPN,
    manufacturer, footprint, libsource). 372 components, 187 nets.
- **Footprint** `libraries/temper.pretty/Bank_Film_DualPitch_P22.5_P27.5_Radial.kicad_mod`:

  | Item | Value |
  |---|---|
  | Pad 1 (RES_A) | x 0, round 2.4 mm, drill 1.2 (round, as the s49 fix for the In1 v3v3 corner) |
  | Pad 2 (SW_B), TDK alternate | x 22.5, round 2.4 / 1.2 |
  | Pad 2 (SW_B), KNSCHA fitted | x 27.5, round 2.4 / 1.2; same pad number, so both holes are on sw_b |
  | F.Fab | KNSCHA maximum body x −2.25..29.75, ±5.75 (solid); TDK maximum body x −2.0..24.5, ±7.25 (dashed) |
  | F.SilkS | union rectangle x −2.37..29.87, ±7.37 |
  | F.CrtYd | union rectangle x −2.75..30.25, ±7.45 (0.5 mm beyond the union along X, 0.2 mm across) |
  | 3D | `models3d/capacitors/KNSCHA_MMK104J3DF1KN208G2.step` / `.wrl` (generate_step.cpp / generate.py entries; max body 32 × 11.5 × 20 mm, centred on the 27.5 mm pitch). The TDK model `TDK_B32643B8104J000.step` has the same origin: swap the path to view the alternate |

- **Holes and rings, both leads.**
  - KNSCHA spec KNS20200505002 p.3: d 0.8 ± 0.05 mm. TDK B3264*B p.2: d1 0.8 ± 0.05 mm.
  - The 1.2 mm drill leaves ≥ 0.27 mm diametral clearance on a 0.85 mm lead at JLC's −0.08 mm drill tolerance
    (FAB-JLCPCB.md: "PTH 0.15–6.3 mm; tolerance +0.13/−0.08 mm").
  - The ring is (2.4 − 1.2) / 2 = **0.6 mm**, against JLC's "PTH annular ring, Multilayer 2 oz" **≥ 0.254 mm**
    (FAB-JLCPCB.md row "Annular ring, 2 oz", re-read verbatim 2026-10-08). That 0.254 mm is the PTH rule, not the via rule.
- **Bodies at the s49 rows** (y 53.2 / 68.2 / 83.2 / 98.2 / 113.2, 15 mm pitch; `place.py` `S51_BANK`, courtyard centre
  x 163.0 + 13.75):
  - KNSCHA: 11.5 mm maximum thickness leaves 3.5 mm gaps; x 160.75–192.75 at maximum length.
  - **TDK alternate: 14.5 mm in 15 mm leaves 0.5 mm gaps, as at s49.** x 161.0–187.5. The courtyards are 14.9 mm
    tall at 15 mm pitch (0.1 mm apart), as at s49.
  - The enclosure fit uses the KNSCHA model: FIT 424 0 0 / R4 426 0, jet strip max 1.72 mm. The TDK body (29.5 mm
    tall) passed the same check at s49 / s50 at the same place.
- **Copper: no edit.** The x 190.5 holes sit on the widened s49 sw_b B.Cu strip (x 183–200.6, bottom y 114.4 at
  x 183–192; row 5's pad bottom is y 114.4). `passes51.sh` j1 was clean on the first pass (0 unconnected, 0 errors,
  0 open pairs). `copper.json` equals s50's; the chain's settle loop trimmed nothing. Plated holes 871 → 876.

## 2. Gates (chain run 1)

| Gate | s51 | s50 |
|---|---|---|
| Passes j1 / chain DRC | unconnected 0, errors 0 (warnings 625, the s50 set) | same |
| Barrier (plan view 8.0 mm) / RES_A outer 12.6 mm | 0 / 0 (min F.Cu 18.993, B.Cu 13.375) | same |
| D5 HOT-SELV / HOT-PE | **8.047 / 8.507 mm** | 8.047 / 8.507 |
| RES_A outer minimum | **13.375 mm** | 13.375 |
| RUST barrier | 0 violations, 6329 items | 0 |
| SPINE_LOCK (owner selv) | PASS | PASS |
| DFM / FIT / RES_A creepage | PASS, 777 vias / 424 0 0 / 0 pairs | same |
| return_path19, BYPASS, pi_distances | pass | same |
| cu_temp_basis `--fail-waived` | PASS (124 files, 39 registered, 0 waived) | same |
| pin_absmax `--fail-stale` | 0 failures (new 0), 5 warnings, 9 undeclared | same |
| Kelvin | trip shift −2.41 A; band after 69.18–114.58 A (floor 64.17) | same |
| B3 ratings | release margin +1.3 K (R10); laminate −50.8, rated part −51.0 | same |
| B3 advisory | **−0.3 K: C21 105.3 °C at c28_h10 still air against KNSCHA's 105 °C** | +7.3 K (TDK 125 °C) |
| track geometry | acute 22, fold-backs 3, right-angle 53, any-angle 280.2 mm | same |
| coil pickup / necks | 4.17 A / 0.993, 1.021 (`result-s51.json`, `s51_necks.json`) | same |
| ERC | 1 error (power_pin_not_driven), the s50 set | same |
| BOM / CPL | 95 lines, 372 placements; CPL OK 303 / CORRECTED 32 / NEEDS-PREVIEW 26; bank OK | same |

- The B3 advisory row is not a gate: the c28 still-air case is the airflow route (S24). The KNSCHA bank body temperatures
  are close to c34's s49 values (release C21 82.8 / 82.8 °C, c22 86.9 / 87.1 °C, c28 105.3 / 106.2 °C), but the limit is
  105 °C, not 125 °C.

**Bank pad clearances** (`scripts/hole_clearance51.py` on `native21s51-all-copper.json.gz` → `results/hole-clearance-s51.md`):

| New x 190.5 holes | Value | Rule / s50 |
|---|---|---|
| Same layer, nearest other-net copper | 3.201 mm (C21.2 to the In1 hv_ret trunk, HOT-HOT) | DRC netclass rule: 0 errors. The x 185.5 hole has the same 3.201 mm |
| Plan view to SELV copper | 8.229 mm (C152.2 to the B.Cu line_zc_raw run at y 122.75) | ≥ 8.0 mm barrier; above D5's 8.047. Same as the x 185.5 hole |
| Plan view to the In1 v3v3 plane | 14.801 mm (C152.2) | the corner's binding pad stays C152.1 at 8.328 mm |
| Plan view to PE | 20.004 mm | ≥ D5 HOT-PE 8.507 |

## 3. bank_air on this board (the chain's producer, now KNSCHA)

`bank28-air/scripts/bank_air_metric.py` now carries `bank_air_cand.py`'s KNSCHA rows. It reads the part data from
`../data/candidates.json` id knscha: body 11.5 × 20 × 32 mm, 6.2 / 6.16 A at 35 / 40 kHz for 10 K, rule end 105 /
span 20 ASSUMED above 85 °C. It writes `by_mpn` for all three MPNs and `fitted_mpn` from the frozen BOM. For the fitted
part it also writes `release` rows on the board's own B3 release solve; their board must equal the jetmix board.
- **Control:** `--control-cand runs-native21/s49/c49/b3-bank-air` reproduces bank_air_cand.py's 1.221 on the s49 pads.
- **Scorecard:** `bank_mpn` recognises MMK104J3DF1. The two `bank_ratio_tdk_*` keys take KNSCHA's own curve from the
  same producer (key names kept).

| On board 9afc509b | Strict (the card) | + gap credit | Vendor ratio 35 / 40 kHz |
|---|---|---|---|
| **28 A / 35 kHz, declared flow** | **1.221** (interior, @61 °C, lo G_board: ΔT 14.9 / 10 K, T_A 68.8 °C; hottest T_op 90.6 / 105 °C) | 0.869 (bank_air_cand.py on these pads) | 0.978 / 0.984 |
| TDK alternate, same pads | 0.967 | 0.926 | 0.831 / 0.816 |

**Release, still air** (c17.5_h10 at bay 61 °C, air at bay + 15 K; worst interior part, lo G_board):

| Current | With radiation | Without radiation |
|---|---|---|
| **18.375 A** (the 17.5 A ceiling's trip) | **0.9578** (ΔT 9.17 / 10 K, T_A 77.2 °C) | **1.2088** (ΔT 14.61 K) |
| 17.5 A | 0.9154 | 1.1569 |

- The bank-src lane's 0.957 / 1.208 were on the s50 release pads (board 4876c42e) with a pad-heat correction. On this
  board's own release solve the producer gives 0.9578 / 1.2088 with no correction: these pads already carry the KNSCHA
  heat row.
- `bank_air_cand.py` itself on these pads (temporary copy, correction on) gives 0.9587 / 1.2105, strict 1.221 and
  +gap 0.869. Its controls pass.

## 4. Bank voltages (`scripts/bank_voltage51.py` → `results/bank-voltage-s51.{json,md}`)

The bands come from `scripts/bands51.py --check` on this board's solve. The basis band is 71.59–114.58 A, equal to
`kelvin_budget.BAND_BEFORE["native21s51"]` (carried from s50). The c28 R1 phys top is 119.461 A.

| Row (KNSCHA: VR 2000, VRMS 700, VC(105 °C) 1500, dV/dt 2200) | Stress | Limit | Utilisation | Margin |
|---|---|---|---|---|
| **F3, worst R0 / R1** (c28_h10@55 R1 phys) | **1693.2 V** | 1700 V (0.85 VR) | **0.996** (0.8466 of VR) | **+6.8 V** |
| F3, any reading (R4 phys) | 1786.6 V | 2000 V | 0.893 | +213.4 V |
| Double fault Z0,max × top (R4 phys) | 1607.1 V | 2000 V | 0.804 | +392.9 V |
| No-pan | 775 V | 1200 V (0.8 VC) | 0.646 | +425 V |
| V 28 A / Vrms | 566 V / 268 V | 1600 / 560 V | 0.354 / 0.479 | |
| dV/dt | 345.4 V/µs | 2200 V/µs | 0.157 | |

- The F3 and double-fault rows equal c34's (both parts are 2000 V).
- KNSCHA's no-pan row (0.646) is looser than TDK's (0.969), because the category voltage at its Top,max is higher.
- `audit.rs` `S49_BANK_VR` now lists KNSCHA at 2000 V.

## 5. Ledger, audit, tests

- **Ledger** (`scripts/ledger51.py`, then `scripts/recite51.py`):
  - New entry MMK104J3DF1KN208G2, PARTIAL, 17 checks. Every violation-severity row passes:
    - V 0.283, no-pan 0.517 / 0.8, Vrms 0.383;
    - I release 0.642 / 0.85;
    - **I at the 22 A strict ladder step 0.768 / 0.85**;
    - F3 0.8466 / 0.85, double fault 0.804, dV/dt 0.157;
    - body at release 82.8 / 105 °C.
  - Gap rows:
    - I 24 A (+gap) 0.838;
    - I 28 A 0.978 (the 28 A route);
    - 28 A self-heating: 9.56 / 10 K isolated, 14.9 / 10 K strict in the column;
    - case at 28 A 90.6 / 105 °C;
    - release still air 9.17 / 10 K with radiation (no radiation 1.209 eff);
    - c22 86.9 °C; c28 105.3 / 105 °C.
  - Eight gaps: the five bench items, the ceiling, sourcing (single source) and the approval basis.
  - **Approval basis:** a HOT-side tank part, so no UL / ENEC file is required. KNSCHA lists no UL file and no AEC.
    Flammability grade B (passive flammability, p.4). The UL 94 V-0 case grade the sourcing study reports is **not in
    the spec's text layer**, so the entry records it as "reported, to confirm".
  - TDK B32643B8104J000 leaves `entries` and is kept under `alternates`, its s50 audit, marked NOT FITTED. The gate does
    not read `alternates`.
  - recite51 re-cited 12 entries' keyed B3 rows.
  - **Gate PASS: 3 VERIFIED / 92 PARTIAL / 0 UNAUDITED / 0 VIOLATION** (95 lines). `tests/test_gate.py` 0 failures; its
    named-PARTIAL list holds the KNSCHA MPN.
- **audit.rs:**
  - IDENTITY c_res1..5 = MMK104J3DF1KN208G2.
  - New `stage51_checks`: the bank must be on the dual-pitch footprint, with a part the footprint carries (KNSCHA or
    TDK).
  - New test `stage51_dual_pitch_bank_holds`:
    - the TDK alternate fails only the identity row;
    - the P22.5-only footprint fails;
    - an R75 part fails both stage51 and the S49 VR table.
  - PASS on both frozen exports (372 components, 187 nets); `--test` **93 / 93**.
- **verify_source.py:** the bank MPN and footprint. **CPL audit:** a dual-pitch footprint settles on the pad-2 hole at
  the part's lead spacing (selftests added). Pin evidence C528962 (p.3, no polarity, 27.5 ± 0.5 mm). The bank is OK.
- **Unit tests:** all pass:
  - test_track_geometry, test_spine_lock, test_track_cleanup21, test_trim_tails, test_jet_strip_height;
  - test_bom_pricing, test_cu_temp_basis, test_pin_absmax;
  - `scoped/test_scoped.py` 16 / 16;
  - test_b3_hot_copper and test_b3_airflow: 0 failures.
- **depmap_check** `--card` s50 and s51: C2–C6 PASS. C1 lists only the pre-existing cu_temp_basis / pin_absmax /
  price_* entries, the s50 set. New path rule: `c51-bank-source/data/candidates.json` → b3_ratings.
- **B3 inputs:**
  - `thermal_body.py` `film_mmkp82`: lead path 50 K/W, Top,max 105 °C (40/105/56);
  - the `b3_ratings_gate` ADVISORY and `report_convergence` rows;
  - `part-bodies.json` bank bodies.
  - `make_heat_sources.py` ESR: typ 10.7 mΩ (rating-implied); worst 39.8 mΩ at 40 kHz (tan δ ≤ 0.1 % at 1 kHz held
    flat). Both are ASSUMED; ESR is a bench item.

## 6. Cost and sourcing

- **The bank line:** $0.3035 × 5 = **$1.52** per board at 500 (JLC 1000+), against c34's JLC ladder $0.248 × 5 = $1.24
  (listed at 0 stock). `parts_usd_at_500_v2` goes 169.49 → **169.77** (+$0.28).
- **Short lines:** the line is no longer zero-stock or short. Zero-stock lines 8 → 7; short at 500: 15 → 14; short at
  5: 4 → 3. JLC-assemblable share 0.842 → 0.853 (500) and 0.958 → 0.968 (5); consign lines 3 → 2. Single-source lines
  17 → 18.
- **Files:**
  - `STOCK-2026-10-13-addendum-s51.csv` (flag SINGLE_SOURCE(JLC));
  - `apply_lcsc.py` MMK104J3DF1KN208G2 → C528962;
  - `jlc-raw/detail_C528962.json` (the bank-src read);
  - a `run_all.sh` s51 block, `snapshot/s51/`, and `SNAPSHOT-2026-10-15.csv` re-merged.
- **TDK B32643B8104J000 is off the pre-order list** (OPEN-ITEMS owner step 7).
- **OPEN-ITEMS:** the S24 bank line, the S25 pre-lot gate (now on the KNSCHA interior cap, 10 K basis, 105 °C) and a new row
  **S28**, the 28 A bank route. S26 / S27 are taken on ps-integrate.

## 7. What did not match the brief

- **B3 advisory margin goes negative (−0.3 K).** The KNSCHA Top,max is 105 °C. C21 reaches 105.3 °C in the c28 still-air
  context case. It is an advisory, context row: the 28 A ceiling is not commissioned on this bank, and S24's flow is the
  route.
- **Release ratio 0.9578 / 1.2088, not 0.957 / 1.208.** It is on this board's own solve, without the pad-heat
  correction; with the correction it is 0.9587 / 1.2105.
- **UL 94 V-0 is unconfirmed.** The ledger records it as reported by the study, not read. The spec's own row is
  flammability grade B.
- **The KNSCHA rating rule above 85 °C is the study's ASSUMED linear derating.** The chain metric carries it; it is
  flagged in the ledger gaps.
- **The CPL audit has no EasyEDA footprint for C528962.** It was not fetched. The bank is settled by datasheet pin
  evidence, as C3781430 was at s49.

## 8. The study copy (`../`)

Byte copy of the bank-src lane (`/Users/bennet/.claude/jobs/fbfc46b4/tmp/bank-src`):
- included: README.md, `scripts/*.py`, `results/`, `data/`, `snapshots/*.json` and `*.csv`, and `snapshots/jlc-raw/`
  `detail_*.json` and `search_*.json` (read by `jlc_summary.py` / `fetch_datasheets.py` / `jlc_fetch.py`);
- left out: `dl/`, `render/`, the octopart / findchips HTML, and the 32 MB `survey_*.json` cache.
  `jlc_survey.py --offline` needs that cache; `snapshots/jlc_survey.csv` is its committed output.

## 9. Reproduce

```
R=../../runs-native21/s51     # /Users/bennet/Desktop/temper/worktrees/runs-native21/s51 here
git show 29f16fd77:zapote/power-stage-120v/native-21/layout/copper.json > $R/base-s50-copper.json
sh validation-results/11-candidates/c51-bank-source/stage51/passes51.sh $R/base-s50-copper.json $R/p1
SPINE_OWNER=selv TASK04_WORKERS=4 sh native-21/layout/gates/chain.sh native21s51 $R/p1/j1 $R/c51
S=validation-results/11-candidates/c51-bank-source/stage51/scripts
python3 -I $S/hole_clearance51.py native-21/verification/native21s51-all-copper.json.gz
python3 -I $S/bands51.py --check && python3 -I $S/bank_voltage51.py
python3 -I $S/ledger51.py && python3 -I $S/recite51.py && python3 -I native-21/verification/datasheet-ledger/gate.py
(cd validation-results/02-protection-timing/coil-pickup/s21b && F8_COPPER=../../../../native-21/verification/native21s51-all-copper.json.gz \
    python3 -I run_ocp.py && cp result.json result-s51.json && git checkout -- result.json)
(cd validation-results/02-protection-timing/shoot-through-f1 && python3 -I s21_necks.py s51)
cp validation-results/08-manufacturing-package/native-21/fab/bom-jlcpcb.csv \
   validation-results/08-manufacturing-package/native-21/sourcing/study-2026-10-15/snapshot/s51/bom-jlcpcb.s51.csv
bash validation-results/08-manufacturing-package/native-21/sourcing/study-2026-10-15/run_all.sh
python3 -I native-21/layout/gates/scorecard.py native21s51 $R/c51 --audit PASS \
    --json validation-results/10-benchmark/scorecard-native21s51.json --compare validation-results/10-benchmark/scorecard-native21s50.json
python3 -I validation-results/11-candidates/bank28-air/scripts/bank_air_metric.py --ps "$PWD" --runs $R/c51/b3-bank-air \
    --out /tmp/bam.json --control '' --control-cand ../../runs-native21/s49/c49/b3-bank-air     # the port's control
```
