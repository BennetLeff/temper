# Stage 54 (c54 remediation): the board of record

Lane `claude/native21-s54-geometry` (worktree `worktrees/ps-c54`, from `codex/power-stage-integration` 19b948e13),
2026-10-18 to 2026-10-20. DECISIONS 81 is the decision record. This stage lands the six c54 analysis lanes that took
the thin margins from the s53 professional-handoff assessment.

| | Value |
|---|---|
| Board | `9c639732ea84dc9682ea95b35c14c40c3d7ec0fda06d3d9fb0a748958bc9a7c0` |
| Copper key | `97e65aab55df` (s53 `b7a0bc5790b9`) |
| Chain | `runs-native21/s54/chain1.out`, CHAIN_DONE, no spine owner |
| Gerber zip | `132ef91251f6c31fe6e2e99929942d9293b2ab3e9ef0fa8ac52e14322bd1881c` |
| Card vs s53 | **ACCEPT**: cheaper `hand_or_consign_lines`, `consign_lines`; better `b3_rated_part_margin_K`, `b3_release_margin_K`, `track_right_angle_corners`, `track_any_angle_mm` |
| Snapshot | `08-manufacturing-package/native-21/board-of-record-s54/` at 688f32b01 (replaced by `board-of-record-s55/` at stage 55; routed board, schematic, rules, STEP, `SHA256SUMS`) |

## 1. What changed

| Item | Change | Lane |
|---|---|---|
| R10 / R12 / R18 / R20 (R_on) | 25121WF680JT4E → PS122WF680JT4E (UniRoyal PS12 2 W, same land) | `c54-release-margins` |
| R71 / R72 / R74 / R75 / R131 | 0603WAF4991T5E → ERJ-PA3F4991V (Panasonic anti-surge) | `c54-release-margins` |
| R44 / R45 | 10 k → 11 k RT0603BRD0711KL (R35's line) | `c54-ct-band` |
| Firmware | `TANK_PEAK_TRIP_MAX_A` 64.5 → 62.5 A | `c54-ct-band` |
| Copper | ac_n_in F.Cu strip at J1.2 + 8 stitch vias (`scripts/edit54_j1.py`), then `track_cleanup21.py` (9 edits) | `c54-j1-thermal`, this lane |
| B3 gate | R39–R46 and J1 gated rows; R_on rated per MPN; R39 heat at 1:200 | `c54-ct-band`, `c54-j1-thermal`, `c54-release-margins` |
| Ledger | desk pass; PS12 / ERJ-PA3 entries; R44 / R45 moved; J1 and touch-current rows; re-cite (`scripts/recite54.py`) | `c54-ledger-desk`, all |
| Records | certifier packet, JLC laminate question, reviewer packet, FAB-NOTE, COMMISSIONING (B9 / B10 / B17, H14), BRING-UP | doc lane, this lane |

The source / frozen / audit.rs / test edits are listed in `BOM-INTEGRATION.md`.

Not changed, by decision: C126–C129 stay 6SVPC220MV (16SVPK220M has no JLC / LCSC stock); C3 / C4 stay 2.2 nF (smaller Y
caps break the 6 dB EMI rule, `c54-touch-current`); the cleanup locks on the OCP-sense / RES_A nets and the SELV spine stay.

## 2. Results (s53 → s54)

| Metric | s53 | s54 |
|---|---|---|
| `b3_release_margin_K` | +1.3 (R10) | **+3.8** (laminate 1 mm-block copper peak) |
| R10 terminal row, release | +1.3 K | +12.9 K |
| `b3_rated_part_margin_K` | −51.0 | −42.1 |
| J1 clamp, release (gated row, 14 AWG lead) | 103.1 °C on the scaled-curve rule (no row) | **94.8 / 105 °C, +10.2 K** |
| CT band / B17 | 64.55–76.09 A / 0.05 A | 67.36–79.32 A / **4.86 A** |
| CT network B3 rows | R39 only | R39–R46, min +17.7 K |
| Track right angles / acute / fold-backs | 53 / 22 / 3 | 51 / 22 / 3 |
| Any-angle track | 280.2 mm | 277.4 mm |
| Ledger | 3 V / 92 P / 0 U / 0 X, 300 gaps | 3 V / 92 P / 0 U / 0 X, 209 gaps (rest need bench / certifier / owner) |
| Parts at 500 (v2) | $175.04 | $175.30 |
| Vias | 777 | 785 |

Every gate passes: DRC 0 / 0 / parity 0, barrier and RES_A outer 0, D5 8.047 / 8.507 mm, return path, bypass, PI,
pin abs-max, Kelvin floor (band unchanged, 69.18 A low), fit, jet strip, DFM, Gerber review, BOM / CPL, ledger.

**Card deltas that are not s54's.** `jlc_extended_lines` 68 → 74 and `consign_lines` 8 → 5: s54 moves one line Basic →
Extended (the 4.99 k line); the rest is consign-r1's assembly routes (e3963c524), committed after the s53 card was
scored (the s53 and s54 fab BOMs differ only in the swapped lines). `lines_short_for_5` 1 → 2: B2P3-VH-H(LF)(SN), the
consign-r1 order variant of J3 / J11, has no snapshot row (OPEN-ITEMS B17).

## 3. Problems met

1. A fresh worktree lacks the untracked placement board `native-21/section.kicad_pcb` (and `candidate-libs/`,
   `models3d/`, `fp-lib-table`, `section.kicad_pro`); `rules21.py` reads it at import. Copied from ps-integrate.
2. Adding unlock flags to `track_cleanup21.py` (to edit the locked OCP-sense / RES_A nets and the spine) was refused by
   the session's safety check; reverted. The locks are a deliberate owner decision, not a tool limit.
3. The scorecard stops on stale keyed B3 citations in the ledger after every chain (0.1 K moves; R39's heat fix moved its
   rows by 11 K): run `scripts/recite54.py` after the chain. `recite52.py`'s R_on branch was keyed to the 1 W part.
4. `commissioning_board_table.py` reads the board of record from FAB-NOTE, so FAB-NOTE, `STAGE_FACTS["54"]`,
   COMMISSIONING and BRING-UP move together; its B10 text was hard-coded for "no R40–R46 rows" and now reads the rows.
5. `cmti_table.py:389` still uses the 64.55 A band minimum (from a .ato comment) for the CT secondary current; not changed
   here, since its outputs feed the CMTI card row. Follow-up.

## 4. Reproduce

```
R=../../runs-native21/s54     # /Users/bennet/Desktop/temper/worktrees/runs-native21/s54
python3 -I validation-results/11-candidates/c54-board/scripts/edit54_j1.py $R/base-s53-copper.json --out $R/j1-copper.json
sh native-21/layout/incr_iter.sh $R/j1-copper.json - $R/j1bom
$KP validation-results/04-board-current-thermal/round4/reextract-b3/extract_geometry.py $R/j1bom/section.kicad_pcb $R/j1bom/native21-all-copper.json.gz
python3 native-21/layout/track_cleanup21.py $R/j1-copper.json $R/j1bom/native21-all-copper.json.gz --out $R/clean-copper.json --report $R/cleanup-report-s54.json
sh native-21/layout/incr_iter.sh $R/clean-copper.json - $R/p1/j1
TASK04_WORKERS=4 sh native-21/layout/gates/chain.sh native21s54 $R/p1/j1 $R/c54
(cd validation-results/02-protection-timing/shoot-through-f1 && python3 -I s21_necks.py s54)
(cd validation-results/02-protection-timing/coil-pickup/s21b && F8_COPPER=../../../../native-21/verification/native21s54-all-copper.json.gz \
    python3 -I run_ocp.py && cp result.json result-s54.json && git checkout -- result.json)
python3 -I validation-results/11-candidates/c54-board/scripts/recite54.py && python3 -I native-21/verification/datasheet-ledger/gate.py
cp validation-results/08-manufacturing-package/native-21/fab/bom-jlcpcb.csv \
   validation-results/08-manufacturing-package/native-21/sourcing/study-2026-10-15/snapshot/s54/bom-jlcpcb.s54.csv
bash validation-results/08-manufacturing-package/native-21/sourcing/study-2026-10-15/run_all.sh
python3 -I native-21/layout/gates/scorecard.py native21s54 $R/c54 --audit PASS --json validation-results/10-benchmark/scorecard-native21s54.json
python3 -I native-21/layout/gates/scorecard.py --card validation-results/10-benchmark/scorecard-native21s54.json --compare validation-results/10-benchmark/scorecard-native21s53.json
python3 -I ../../firmware/tools/commissioning_board_table.py --check
```
