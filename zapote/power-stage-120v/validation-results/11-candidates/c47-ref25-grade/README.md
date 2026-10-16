# Candidate 47: U5 (REF25) on its 125 °C grade, built as stage 47 (native21s47)

**Verdict: card REJECT against s46. Two things drive it. The Kelvin band low corner falls by 1.02 A, and that is the new
network-temperature basis, not the part. The other is cost: U5 costs +$2.16 per board, and the line becomes short at
500.** Board native21s47 `4139c87b…`. The geometry is identical to the s46 integration board `16a58861`, with the same
copper key `d33d77ac`. The chain reached CHAIN_DONE with no spine owner.

Branch `claude/native21-s47-ref25-grade` from `142649854` (DECISIONS 62, board of record s46, hot-copper c17.5 basis). The
integrator decides (`DECISIONS-DRAFT.md`, item 63).

```
REJECT native21s47 vs validation-results/10-benchmark/scorecard-native21s46.json: cheaper [], better []; kelvin_band_low_A worse: 66.75 vs benchmark 67.77 (tolerance 0.5); costlier on ['parts_usd_at_500_v2', 'lines_short_for_500', 'jlc_assemblable_share_500'] with no performance gain; neither cheaper/simpler nor better than the benchmark
```

On a like-for-like basis the Kelvin figure is better, not worse (section 3):
- on the committed −10/85 °C basis, s46 reads 67.77 A and s47 reads 67.89 A;
- on the solved basis, s46 (A25I) reads 66.63 A and s47 reads 66.75 A.

## 1. What changed (BOM only, 1 instance)

| Ref | s46 | s47 | JLC (2026-10-15) | Stock / need at 500 | $ at need |
|---|---|---|---|---:|---:|
| U5 (REF25) | LM4040A25IDBZR (C9421) | **LM4050AEM3-2.5/NOPB** | C2156518 | **50 / 500** | 3.4228 |

Source: `results/parts-s47.md` (`scripts/parts47.py`, from the live JLC records in `scripts/jlc-raw`, read 2026-10-16
03:09 UTC).

**TI SNOS455H (Mar 2025)**, `runs-native21/s47/dl/ti_lm4050n.pdf`, sha256 `950d0491…`:
- 5.3 p.5: the extended range is TA = TJ −40..125 °C.
- Addendum p.25: LM4050AEM3-2.5/NOPB is SOT-23 (DBZ), −40 to 125 °C, marking RCA.
- 5.6 p.7 (LM4050AEM3, 2.5 V):
  - VR is ±2.5 mV at 25 °C and **±15 mV over −40..125 °C**. Note 5 on p.11 gives the construction: 0.1 % ± 50 ppm/°C ×
    100 K × VR.
  - IRMIN is 65 µA over temperature.
  - ΔVR/ΔIR is **1.2 mV** for IRMIN..1 mA over temperature.
- 5.1 p.4: abs max reverse current 20 mA, TJ 150 °C.
- 5.4 p.5: RθJA 287 K/W. Note 1 on p.11 gives 326 K/W board mounted.

**Pinout:** SNOS455H 4 p.3 gives 1 = cathode, 2 = anode, 3 = no internal connection. The figure note says pin 3 "must
be left floating or connected to pin 2". This is the LM4040 DBZ pinout.
- U5 pin 3 is alone on `u_ref-nc`, so it floats, which p.3 allows. `audit.rs` now checks it.
- Table 4-1 note 1 recommends tying pin 3 to the anode in high-EMI applications. That would be a copper change, so it
  was not made here (section 7).

**JLC listing:** C2156518 shows "Operating Temperature −40℃~+85℃". That is wrong for the E suffix; the TI pages above give
−40..125 °C. The LM4050QAEM3 (Q1) records do show −40..125.

**Stock:**
- JLC holds 50 of C2156518, 43 of LM4050QAEM3-2.5/NOPB (C2157745) and 3 of C2157326, so **96 across the three**.
- **U5 is a sourced / consigned line for the lot: owner pre-order of ≥ 550 LM4050AEM3-2.5/NOPB** (500 plus attrition).
  No supplier was contacted.
- The STOCK addendum row (`sourcing/STOCK-2026-10-13-addendum-s47.csv`) carries
  `LOW_JLC_STOCK(50 < 500 for 500 boards);OWNER_PREORDER_CONSIGN(>=550)`.

**Source:**
- `elec/src/parts.ato` Ref2V5 changed, built with atopile 0.2.69 offline plus `circuit_export.py`.
- Refrozen to `frozen/` and `native-21/frozen/`, path normalised to `ps-integrate`.
- `default.csv` and `resolved-components.json` change only at U5.
- `default.net` changes only in its 11 footprint-aliased SOT-23 libsource / libpart lines (atopile names every SOT-23
  part after one MPN; README "Part identity"). Nodes and nets are unchanged.

## 2. U5 is a gated B3 row (hot copper, `b3-ratings/margins.json` on the s47 board)

Gate changes:
- `b3_ratings_gate.MONITORS` gains `U5: ("ref25", r"^ref25$")`.
- `MONITOR_GRADES` keys the limit to the frozen BOM MPN: LM4040A25IDBZR 85 °C (SLOS456Q 6.3 p.5, LM4040xxxI) and
  LM4050AEM3-2.5/NOPB 125 °C (SNOS455H 5.3 p.5).
- Self-heat uses U5's real operating maximum, 0.238 mA:
  - feed: R31 5.6 k −1 % from HOT5 5.15 V, at VR minimum 2.4838 V;
  - less the three 0.1 % load strings;
  - × 2.5162 V = 0.60 mW;
  - × 326 K/W = **0.2 K**.

| Case | U5 est (pad + self-heat) | LM4050AEM3 margin (125 °C) | A25I margin (85 °C) |
|---|---:|---:|---:|
| c17.5 @ 61 (release) | 89.1 °C | **+35.9 K** | −4.1 K |
| c22 @ 55 | 90.5 | +34.5 | −5.5 |
| c28 @ 55 | 104.7 | +20.3 | −19.7 |

- The release margin stays **+1.0 K**, bound by R10's 2512 terminal derating; U5 is far from binding.
- `b3_ratings` gate: PASS.
- Ratchet unchanged: laminate −51.1, rated part −51.3 K.

Tests in `test_b3_hot_copper.py` (34 ok):
- the U5 row on each grade (85 / 125 °C, same estimate);
- the self-heat power;
- refusals for the industrial LM4050AIM3, a TL431 at U5, and U5 moved off `ref25`.

## 3. Bands (`scripts/bands47.py` → `results/bands-s47.md`)

**Method:** the committed `thresholds.py` `exact_corners`, imported read-only, with the stage-17 R5 CSS2H tuple and R34
12.6 k / R35 11.7 k.
- REF25 error is T + L. For the A25I that is 19 + 1.0 mV (SLOS456Q 6.8 p.9). For the LM4050AEM3 it is **15 + 1.2 mV**
  (SNOS455H p.7).
- The two REF25 vertices are mapped as in `ref25_46.py`.
- `validate_inputs()` runs on the current freeze. It gained an `overrides` argument: its round-3 MPNs for R5 / R34 / R35 /
  R39 / R43 / R46 have been stale since stages 15–19, and it was failing on R5.

**Controls (asserted):**
- A25I, committed network: 69.89–116.44 A (`ocp_band17.json`) and OVP 272.09–288.02 V;
- A25I, uniform 105 °C: OVP top 288.75 V;
- LM4050, committed network: 272.50–287.58 V (u5-ref search).

### 3a. New finding: the divider network runs above 85 °C

Every band so far assumes the R26–R37 network at −10..85 °C. The hot-copper B3 probes on this board say otherwise. Values
use the gate estimator. R5 is the gate's element row.

| Case | R26–R29 (1 % 100 ppm) | R30 | R32–R35 (OCP) | R36 / R37 (OVP) | R5 element | U5 pad |
|---|---|---:|---|---|---:|---:|
| c17.5 @ 61 | 78.6 / 76.8 / 76.1 / 81.3 | 91.7 | 93.1 / 94.7 / **95.8** / 95.2 | 92.1 / 92.8 | 124.2 | 88.9 |
| c28 @ 55 | 87.2 / 80.1 / 76.9 / 82.8 | 101.1 | 101.7 / 101.9 / **102.9** / 102.8 | 98.3 / 99.3 | 194.8 | 104.5 |

- The network maximum is 95.8 °C at the release case and 102.9 °C at c28, both above 85 °C.
- **The s47 band basis is therefore the solved network:** the −10 °C corner as before, and a hot corner with each
  resistor at its own B3 estimate.
- `kelvin_budget.BAND_BEFORE["native21s47"]` = (68.87, 117.45) A, the LM4050 release-case row. `bands47.py` asserts that
  the two agree.

### 3b. Band table

| REF25 | Network | OCP before Kelvin (A) | OCP low after Kelvin (margin to 64.17) | OVP band (V) | OVP top vs 288.02 |
|---|---|---|---|---|---:|
| A25I | committed −10/85 | 69.89–116.44 | 67.77 (+3.60) | 272.09–288.02 | 0.00 |
| A25I | uniform −10/105 | 67.33–119.25 | 65.21 (+1.04) | 271.39–288.75 | **+0.73** |
| A25I | solved c17.5 @ 61 | 68.75–117.62 | 66.63 (+2.46) | 272.22–287.88 | −0.14 |
| A25I | solved c28 @ 55 | 67.46–119.25 | 65.34 (+1.17) | 272.05–288.05 | **+0.03** |
| **LM4050AEM3** | committed −10/85 | 70.01–116.27 | 67.89 (+3.72) | 272.50–287.58 | −0.44 |
| LM4050AEM3 | uniform −10/105 | 67.44–119.08 | 65.32 (+1.15) | 271.81–288.31 | +0.29 |
| **LM4050AEM3** | **solved c17.5 @ 61 (s47 basis)** | **68.87–117.45** | **66.75 (+2.58)** | **272.64–287.45** | **−0.57** |
| LM4050AEM3 | solved c28 @ 55 | 67.57–119.09 | 65.45 (+1.28) | 272.47–287.62 | −0.40 |
| LM4050AEM3 | hottest c17.5 (95.8 °C uniform, R5 +50 K) | 68.62–117.79 | 66.50 (+2.33) | 272.13–287.98 | −0.04 |
| LM4050AEM3 | hottest c28 (102.9 °C uniform, R5 +50 K) | 67.71–118.79 | 65.59 (+1.42) | 271.88–288.24 | +0.22 |

**Reading:**
- **The A25I fails the OVP "must not rise" rule** on the solved c28 network (288.05 V) and at a uniform 105 °C (288.75 V).
  It passes on the solved release network (287.88 V) only because the thick-film string R26–R29 runs cooler (76–81 °C)
  than the committed 85 °C.
- **The LM4050AEM3 covers both solved cases.** Its OVP top is 287.45 / 287.62 V. The OCP floor margin is +2.58 A at
  release and +1.28 A at c28. The lower OVP corner, 272.47 V, is well above the 269.37 V nuisance limit.
- The "hottest uniform" rows put R26–R29 at the network maximum, which the solve does not support. They are a bound, not
  the basis. The LM4050 still passes it at release (287.98 V), but not at c28 (288.24 V).
- **The OCP margin is the real cost of the new basis.** It falls from +3.72 A (committed basis) to +2.58 A, because
  R32–R35 sit at 93–96 °C. It still clears the 64.17 A floor at both cases.
- **The OCP upper corner** is 117.45 A at release and 119.09 A at c28, against 116.44 A committed. No committed rule
  bounds it; stage 16 carried 118.74 A. R5's CSS2H pulse row cites 118.74 A. At c28 that row is 0.35 A short, but c28 is
  a ratchet case.
- **No divider change is needed.**

## 4. Card (`10-benchmark/scorecard-native21s47.json`) and compare (`results/compare.txt`)

Fields that move against s46:

| Field | s46 | s47 | Why |
|---|---|---|---|
| kelvin_band_low_A | 67.77 | 66.75 | new basis (section 3); 67.89 on the old one |
| parts_usd_at_500_v2 / at_5_v2 | 171.83 / 262.98 | **173.99** / 266.15 | U5 $3.4228 against $1.2636 at 500 (**+$2.16 / board**) |
| parts_usd_at_500 (legacy) | 201.31 | 204.33 | same line on the survey basis |
| lines_short_for_500 | 14 | **15** | U5: 50 at JLC, no read shows a 500 holder → consign / owner pre-order |
| price tiers at 500 P1 / P3 | 71 / 19 | 70 / 20 | the same line |
| short_lead_unknown_500 | 6 | 7 | the same line (no lead read) |

**Consign impact on the card:**
- `lines_short_for_500` rises by 1 and `jlc_assemblable_share_500` falls by one line.
- `consign_lines` (lines with no LCSC code) is unchanged, because U5 keeps C2156518 so JLC can place a consigned lot.

Everything else equals s46:
- D5 8.047 / 8.507, RES_A 13.375, OCP pickup 4.17 A, fuse ratio 0.993;
- DFM PASS 765, jet strip 1.72 mm, FIT 410 0 0 412 0;
- 94 BOM lines, 358 placements;
- B3 release +1.0 K, `b3_ratings` True; ledger 3 / 39 / 52 / 0.

## 5. Copper and placements are identical to s46

- **`results/geom-s46-s47.json`** (s46 `16a58861` against s47 `4139c87b`): footprints, pads, tracks, vias, zones and
  Edge.Cuts are identical. The only field changes are U5 `Value` / `MPN`.
- **Copper key:** `d33d77ac…` on both. Task 04 and B3 hit their caches on it.
- **`track_cleanup21.py`:** 0 edits.
- **`s47_necks.json`:** 0.993. **`coil-pickup/s21b/result-s47.json`:** equal to s46 apart from hashes.
- **Board hash:** the first chain run built `db91b207`. It stopped at the CPL control (section 6), and the re-run built
  `4139c87b` on the same copper key: the refilled copper is not bit-reproducible (chain.sh comment).

## 6. Source checks, CPL, ledger and sourcing

**`audit.rs`:**
- `u_ref` IDENTITY is now the LM4050AEM3.
- `reference_spec()` per MPN:
  - A25I: 2.520 / 2.480 V, IZ,min 80 µA;
  - LM4050AEM3: **2.5162 / 2.4838 V, IRMIN 65 µA**.
  - The fixed 2.520 V `ref_max` is gone.
- The minimum-current check uses the part's own IRMIN.
- A new ceiling check holds the whole R31 current, with all loads open at HOT5 5.15 V, inside the 1 mA regulation window:
  0.481 mA.
- U5 pin 3 must float alone on `u_ref-nc`.
- New test `stage47_ref25_grade_holds`. The 6.8 k bias regression is kept on the A25I.
- **89 / 89** tests; PASS on `build/` and on both frozen copies.

**Other source checks:**
- `verify_source.py` asserts the U5 MPN and footprint.
- `pin_functions21.py` adds the SNOS455H DBZ table. Annotation counts move: eco-pin-table 14, native19-reviewed 86. The
  schematic was rebuilt.

**CPL audit:**
- The EasyEDA record for C2156518 (raw in `runs-native21/s47/ee-raw`) was added to `sources/easyeda-footprints.json`.
- `pin-evidence.json` has SNOS455H p.3; `pin-evidence-datasheets.json` has the PDF sha256.
- The symbol names its pins C / A / NC, so the strict name match left U5 NEEDS-PREVIEW. That made the first chain run fail
  on the new U5 control.
- An evidence entry may now declare `ee_name_alias` (here C → CATHODE, A → ANODE). Only the listed names are mapped, and
  selftests cover the declared, missing and swapped alias.
- Result: **U5 CORRECTED 180°, the same rotation as C9421**. Totals OK 284 / NEEDS-PREVIEW 31 / CORRECTED 32, unchanged.
- The EasyEDA land is the narrower SOT-23-3 (W1.3, LS2.4, against C9421's W1.6, LS2.8). It fits at rms 0.059 mm.

**Datasheet ledger** (`scripts/ledger47.py`, idempotent):
- LM4040A25IDBZR (UNAUDITED) → **LM4050AEM3-2.5/NOPB, PARTIAL**, with page-cited ratings.
- Checks:
  - reverse current: 0.481 / 20 mA;
  - regulation window: 0.481 / 1 mA;
  - PD: 1.21 mW against the 139 mW derated at 104.7 °C;
  - temperature: 89.1 / 104.7 °C against 125 °C, as keyed B3 citations.
- The s47 bands are recorded as informational stresses.
- `gate.py` PASS: 94 lines, **3 / 39 / 52 / 0**. `tests/test_gate.py` 24 ok.

**Sourcing:**
- `apply_lcsc.py` maps C2156518.
- `STOCK-2026-10-13-addendum-s47.csv` has the consign flag.
- `study-2026-10-15/run_all.sh` gains an s47 step that builds `snapshot/s47/`; earlier steps re-ran byte-identical.
- `SNAPSHOT-2026-10-15.csv` re-keys U5.
- `test_bom_pricing.py` had read the live fab BOM for its s45 checks, which broke at stage 46 (KeyError TL431BIDBZR). It now
  reads the frozen `snapshot/s45` BOM, and a new check covers the LM4050 line: P1 $5.1472 at 5, P3 $3.4228 at 500. 30 ok.

## 7. Other parts in the B3 sweep

`results/monitor-sweep-s47.json` is the committed `monitor_sweep.py`, run on the s47 runs with the s47 ledger, written
here so the dated s42 record is not overwritten.

- **Of the parts rated ≤ 105 °C with no B3 row, only PS2 (MPM-20-24) remains over its rating:** 111.5 °C pad against its
  85 °C working ambient, −26.5 K (c28: −35.6 K). S18 owns it.
- U5 has left the list (it is now a gated row).

Noted, outside this list:
- **U3 TPS70950DBVR (HOT5)** has no ledger rating. Its pad reads 106.7 °C at release and 124.3 °C at c28.
- SBVS186H 6.3 p.4 gives TJ 125 °C, and its ±1 % DC accuracy (6.5 p.5) is specified only for TA −40..85 °C.
- With its own dissipation, the c28 junction is likely over 125 °C.
- HOT5 feeds R31, but U5's current window covers 4.75–5.15 V.

## 8. Tests (with `native-21/section.kicad_pcb` = the s47 board `4139c87b`)

| Test | Result |
|---|---|
| `audit.rs --test` | 89 / 89 |
| `audit.rs` on frozen / native-21 frozen / build | PASS |
| `verify_source.py` | PASS |
| `gates/test_track_geometry.py` | 7 / 7 |
| `gates/test_spine_lock.py` | 11 / 11 |
| `layout/test_track_cleanup21.py` | 45 / 45 |
| `gates/test_jet_strip_height.py` | 7 / 7 |
| `gates/scoped/test_scoped.py` | 16 / 16 |
| `gates/scoped/depmap_check.py` | C1–C3, C5, C6 PASS; **C4 FAIL**: `b3/thermal.py` names `validation-plan/sim-kit/04-current/sheet_solver.py`, which no keyed step reaches. Pre-existing: the same FAIL on ps-integrate `1e2d3a95a`; not touched here |
| `gates/test_cu_temp_basis.py` (`CU_TEMP_ROOT=$PWD`) | 47 ok |
| `b3-ratings/test_b3_hot_copper.py` / `test_b3_airflow.py` | 34 ok / 0 failures |
| ledger `gate.py` / `tests/test_gate.py` | PASS / 24 ok |
| `gates/test_bom_pricing.py` | 30 ok |
| CPL `audit.py` selftest and controls | ok (U5 control added) |

## 9. Reproduce

```sh
R=/Users/bennet/Desktop/temper/worktrees/runs-native21/s47
uv tool run --offline --from "atopile==0.2.69" ato --non-interactive build elec/src/power_stage_120v.ato:PowerStage120V
rm build/resolved-components.json; uv tool run --offline --from "atopile==0.2.69" python tools/circuit_export.py \
    "$PWD" "$PWD/build/resolved-components.json" --entry-file elec/src/power_stage_120v.ato --entry PowerStage120V
# freeze: sed 's#/worktrees/ps-layers/#/worktrees/ps-integrate/#g' build/X > frozen/X; cp frozen/X native-21/frozen/X
python3 prototype-closure/pcb/pin_functions21.py && python3 prototype-closure/pcb/build_schematic21.py
TASK04_WORKERS=4 sh native-21/layout/gates/chain.sh native21s47 runs-native21/s46/pass-j1 $R/c47      # CHAIN_DONE, 4139c87b
(cd validation-results/02-protection-timing/shoot-through-f1 && python3 -I s21_necks.py s47)
(cd validation-results/02-protection-timing/coil-pickup/s21b && F8_COPPER=$PWD/../../../../native-21/verification/native21s47-all-copper.json.gz \
    python3 -I run_ocp.py && cp result.json result-s47.json && git checkout -- result.json)
(cd validation-results/08-manufacturing-package/native-21/sourcing/study-2026-10-15 && bash run_all.sh)
python3 -I validation-results/11-candidates/c47-ref25-grade/scripts/bands47.py
python3 -I validation-results/11-candidates/c47-ref25-grade/scripts/ledger47.py
python3 -I validation-results/11-candidates/c47-ref25-grade/scripts/parts47.py
python3 -I native-21/layout/gates/scorecard.py native21s47 $R/c47 --audit PASS --json validation-results/10-benchmark/scorecard-native21s47.json
python3 -I native-21/layout/gates/scorecard.py --card validation-results/10-benchmark/scorecard-native21s47.json \
    --compare validation-results/10-benchmark/scorecard-native21s46.json
KICAD_PY validation-results/11-candidates/c45-s16-monitor/scripts/geom_diff45.py runs-native21/s46/c46int/section.kicad_pcb \
    $R/c47/section.kicad_pcb --json validation-results/11-candidates/c47-ref25-grade/results/geom-s46-s47.json
```

## 10. Not done, and what did not match

**Not done:**
- **FMEA re-run** on the new reference: the C5/C6 OVP and OCP rows with the s47 bands.
- **Owner pre-order of ≥ 550 LM4050AEM3-2.5/NOPB** (50 + 43 + 3 at JLC). Add it to the OPEN-ITEMS owner pre-order list.
- **JLC preview of U5: not needed for rotation.** The audit settles 180°, the same as C9421. The EasyEDA land is the
  narrower SOT-23 variant, so a routine look at the placement preview is still worthwhile.
- **Pin 3 to anode** (TI's high-EMI recommendation): a copper change, left for a layout stage.

**Did not match:**
- The JLC listing gives −40..85 °C for C2156518 (TI: −40..125).
- `thresholds.validate_inputs` had been failing on the current BOM since stage 17 (R5); fixed with `overrides`.
- `test_bom_pricing.py` had been broken since stage 46 (live BOM); fixed.
- `depmap_check` C4 FAIL, pre-existing.
- The first chain run failed the new U5 CPL control (EasyEDA C / A pin names); fixed with a declared alias.
- The ledger's bus-OVP stresses (D3, C5/C6, isolators, RC dividers) quote **286 V** (ALT-D3.md:60). That is below the
  band's upper corner (287.45 V at the s47 basis, 288.02 V on the old one): a pre-existing understatement, recorded as a
  gap in the LM4050 entry and not re-cited here.

**Not edited:** DECISIONS.md, OPEN-ITEMS.md, firmware, FAB-NOTE.

**Not staged:**
- `fab/assembly-drawing.pdf` (restored);
- `validation-plan/enclosure-fit/plan-result.json`;
- datasheets (`runs-native21/s47/dl/`), `.npz` caches;
- the untracked `native-21/section.kicad_pcb` copy.
