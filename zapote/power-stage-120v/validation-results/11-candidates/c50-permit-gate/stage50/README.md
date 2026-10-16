# Stage 50 (c50-permit-gate): U46.A gated by PERMIT through R135 100 k

Selv lane, 2026-10-16, branch `claude/native21-s50-permit-gate` (from the s49 head db60f2692). This directory is the build
record. The review that chose the change is `../README.md` (the analysis lane, fd358959d); its scripts and results stay as
committed there.

Board **4876c42e** (`4876c42ed41a1ec7d4b3f4cb1a1c58d171bc30d3379657755a8db328a8631c4c`, copper key 095e5b732746). Chain run
1 reached CHAIN_DONE (`runs-native21/s50/chain1.out`, `SPINE_OWNER=selv`). The card is **ACCEPT** against s49. Every gate
passes, and spine_lock passes with no reissue. The DECISIONS draft is item 71 (`DECISIONS-DRAFT.md`).

## 1. Change

- **Source** (`elec/src/f6_bias.ato` Heartbeat):
  - adds `signal permit`;
  - `rgate = new R100k0603` (`value = 100kohm`), `rgate.p1 ~ permit`, `rgate.p2 ~ gate`.
- **Top level** (`power_stage_120v.ato`): `hb.permit ~ PERMIT`.
- **Kept on purpose:**
  - the net name HSB_GOOD, because renaming it changes spine track keys;
  - U46 is not touched;
  - R135 keeps its 0603 footprint.
- **Netlist diff, frozen exports** (both `frozen/` and `native-21/frozen/`; byte-identical, `verify_source.py`):
  - R135.1 moves from `v3v3` to `permit`;
  - R135 moves from the 0603WAF1002T5E line (10 k, now 9 refs) to the 0603WAF1003T5E line (100 k, now 9 refs).
  - Nothing else changes: 372 components, 187 nets.
- **Layout** (`patches21.edit_base50`, hooked in `incr21.py` after `edit_base49`; base = the s49 `copper.json`):
  - removes the F.Cu v3v3 stub R135.1 → (32.5, 109.675);
  - keeps that via, which C168.1's F.Cu stub and the B.Cu v3v3 run share;
  - adds a 0.25 mm F.Cu `permit` stub R135.1 (32.525, 108.3) → (33.95, 108.3), 1.425 mm long;
  - gives PERMIT's leg-B F.Cu trace a vertex at (33.95, 108.3), so the stub ends on a segment end. That makes a T at a
    vertex, which `track_geometry` does not count as a corner.
  - R135 at (31.7, 108.3) is outside the spine region (y 130-180).
  - Passes: `passes50.sh` j1 clean on the first pass (0 unconnected, 0 errors, 0 open pairs).
- **Clearances on the built board** (all-copper export, F.Cu, other nets):

  | From | Nearest other-net copper |
  |---|---|
  | stub | 0.95 mm (the v3v3 via), 1.00 mm (pwm_lb), 1.10 mm (v3v3 track), 1.125 mm (R135.2 hsb_good) |
  | R135.1 pad | 0.60 mm (the v3v3 via), 0.75 mm (v3v3 track), 0.779 mm (C168.1) |

  These are the review's 0.95 / 0.60 mm, against a 0.2 mm rule.

## 2. Gates (chain run 1)

| Gate | s50 | s49 |
|---|---|---|
| Passes j1 | unconnected 0, errors 0, barrier 0, RES_A outer 0 (min F.Cu 18.993, B.Cu 13.375) | same |
| D5 HOT-SELV min / next | 8.047 / 8.507 mm | same |
| SPINE_LOCK (owner selv) | PASS, no reissue (`spine-lock.json`) | PASS |
| track_geometry | acute 22, fold-backs 3, right-angle 53, any-angle **280.2** mm | 22 / 3 / 53 / 281.6 |
| return_path19 | pass (transfer limit 3.0 mm) | pass |
| BYPASS | True; U46 C163 1.98 mm | same |
| pin_absmax | 0 failures (new 0), 5 warnings, 9 undeclared | same |
| DFM / FIT / RES_A creepage | PASS, 777 vias / 424 0 0 / 0 pairs | same |
| Kelvin | trip shift −2.41 A; band after 69.18-114.58 A (floor 64.17) | same |
| B3 ratings | release margin +1.3 K (R10) | same |
| bank_air_ratio_28A_35k | 0.967 (B32643B8104J000) | same |
| coil pickup / necks | 4.17 A / 0.993, 1.021 (`result-s50.json`, `s50_necks.json`; only the board hash differs) | same |
| ERC | 1 error (power_pin_not_driven), the s49 set | same |
| BOM / CPL | 95 lines, 372 placements; CPL OK 303 / CORRECTED 32 / NEEDS-PREVIEW 26 | same |

- The any-angle drop (−1.4 mm) is the deleted v3v3 stub. It ran 0.025 mm off vertical over 1.375 mm.
- `pin_absmax_registry`: `hsb_good` is now `hull [selv_gnd, permit]`, cited to `default.net:3488` / `3253-3255`. Before,
  it was `[selv_gnd, v3v3]` through R135 to v3v3. PERMIT itself is the J4.9 logic net, [selv_gnd, v3v3].

**Card** (`10-benchmark/scorecard-native21s50.json --compare scorecard-native21s49.json`): **ACCEPT**, "cheaper [],
better ['track_any_angle_mm']". Every other card entry equals s49's.
- `parts_usd_at_500_v2` stays 169.49.
- The BOM moves one part from the 10 k line ($0.0043 at 500) to the 100 k line ($0.0024 at 500), so cost is $0 to the
  cent (−$0.002).

## 3. Band, ledger, audit

- **Bands** (`scripts/bands50.py --check`, the bands49 engine on this board's solve):
  - the basis band is 71.59-114.58 A, which equals `kelvin_budget.BAND_BEFORE["native21s50"]` (carried from s49);
  - every row and S23 reading equals s49's;
  - the OCP-network maximum temperatures are the same, 97.29 / 103.73 °C.
  - So the s49 bank fault voltages (`c49-c34-bank/results/bank-voltage-s49.json`: F3 ≤ 0.847 VR) stand unchanged.
- **Ledger** (`scripts/ledger50.py`, then `scripts/recite50.py`):
  - R135 moves to 0603WAF1003T5E. Its stress is 3.47 V over 100 k = 0.12 mW. Its temp-ratings pad temperature is
    65.1 / 60.0 / 61.4 °C, inside that line's R128 rows (98.5 / 98.2 / 107.9 °C at 3.94 mW).
  - The U46 function text now reads: heartbeat NAND, B = hb_rx (U46.2), gated by PERMIT through R135 100 k (A = U46.1 on
    hsb_good). The old "gated by HS-B's ISO7710F verdict" text had been stale since stage 40.
  - The re-cite touched no row, because the B3 rows equal s49's.
  - Gate PASS, 3 VERIFIED / 92 PARTIAL / 0 / 0; `tests/test_gate.py` 0 failures.
- **audit.rs:**
  - IDENTITY `hb.rgate` = 0603WAF1003T5E;
  - `audit_f6.rs` now expects `("rgate", "1", "permit")`;
  - the new test `stage50_heartbeat_gated_by_permit` fails R135.1 back on v3v3, and fails the 10 k part.
  - PASS on both frozen exports; 92 / 92 tests.
- **verify_source.py:** `hb.rgate` = 0603WAF1003T5E. **pin-functions21.json:** R135 MPN. **bypass_check.py:** U46
  description.
- **Unit tests:**
  - `test_track_geometry`, `test_spine_lock`, `test_track_cleanup21`, `test_jet_strip_height`, `test_bom_pricing`,
    `test_cu_temp_basis`, `test_pin_absmax`: all pass;
  - `scoped/test_scoped.py` 16 / 16;
  - `test_b3_hot_copper` and `test_b3_airflow`: 0 failures;
  - `depmap_check --card scorecard-native21s50.json`: C2-C6 PASS. C1 lists only the pre-existing cu_temp_basis /
    pin_absmax / price_* entries, the same set as at s49.
- **Sourcing:**
  - new `snapshot/s50/` (bom-jlcpcb.s50.csv, SNAPSHOT-s50.csv) and a `run_all.sh` s50 block;
  - `SNAPSHOT-2026-10-15.csv` re-merged;
  - quantity moves: 0603WAF1003T5E 8 → 9 and 0603WAF1002T5E 10 → 9. Both are JLC Basic.

## 4. Not done here / for the integrator

- **Firmware** is being changed in a separate lane. `firmware/` is untouched. The review's §5 start sequence (check 2
  off PAN_DET entry, check 3 keyed to PERMIT, RUN_EN before the pads) must land before or with this board. As the
  firmware stands, check 2 refuses every start: fail-safe, but the hob does not work.
- **TP19 reads low while PERMIT is low.** At idle, bias health shows only as the hb_rx square wave at U46.2 / U32.13,
  which has no pad.
  - B8 and COMMISSIONING H2 must drive J4.9 high with the PWM idle.
  - The generated `BRINGUP-PROBES.md` row still says "BIAS_GOOD (rail monitors, stage 22)". Its source is
    `plan_board_only21.py`. Changing that text is left to the docs lane, so the board-only plan (and the board) does not
    move in this stage.
- **`default.net` libsource fields stay stale.** The atopile 0.2.69 + `circuit_export.py` flow does not regenerate them:
  R135 shows `R100R0603` / 0603WAF1000T5E, U46 `DisNand` / SN74LVC1G00DBVR, R146 `R100k1206`. `resolved-components.json`
  and `default.csv` carry the true parts: R135 0603WAF1003T5E 100 kohm, U46 SN74LVC1G132DBVR, R146 220 k.
- The datasheet-ledger README's stage list ends at stage 43, as before. The stage-40 sentence "R135 joins 0603WAF1002T5E"
  is history; the s50 note is in the 0603WAF1003T5E entry's `notes`.

## 5. Reproduce

```
R=../../runs-native21/s50     # /Users/bennet/Desktop/temper/worktrees/runs-native21/s50 here
git show db60f2692:zapote/power-stage-120v/native-21/layout/copper.json > $R/base-s49-copper.json
sh validation-results/11-candidates/c50-permit-gate/stage50/passes50.sh $R/base-s49-copper.json $R/p1
SPINE_OWNER=selv TASK04_WORKERS=4 sh native-21/layout/gates/chain.sh native21s50 $R/p1/j1 $R/c50
python3 -I validation-results/11-candidates/c50-permit-gate/stage50/scripts/bands50.py --check
python3 -I validation-results/11-candidates/c50-permit-gate/stage50/scripts/ledger50.py
python3 -I validation-results/11-candidates/c50-permit-gate/stage50/scripts/recite50.py
(cd validation-results/02-protection-timing/coil-pickup/s21b && F8_COPPER=../../../../native-21/verification/native21s50-all-copper.json.gz \
    python3 -I run_ocp.py && cp result.json result-s50.json && git checkout -- result.json)
(cd validation-results/02-protection-timing/shoot-through-f1 && python3 -I s21_necks.py s50)
python3 -I native-21/layout/gates/scorecard.py native21s50 $R/c50 --audit PASS \
    --json validation-results/10-benchmark/scorecard-native21s50.json --compare validation-results/10-benchmark/scorecard-native21s49.json
```
