# Candidate 43: geometry cleanup on s42, snubber source MPN, ledger re-citation (stage 43, native21s43)

**Verdict: card ACCEPT against s42.** Board native21s43 `61447816…`, chain CHAIN_DONE, no spine owner (SPINE_LOCK PASS).

```
ACCEPT native21s43 vs validation-results/10-benchmark/scorecard-native21s42.json: cheaper [], better ['b3_laminate_margin_K', 'b3_rated_part_margin_K', 'b3_release_margin_K', 'track_acute_corners', 'track_fold_backs', 'track_right_angle_corners', 'track_any_angle_mm']
```

There are three changes in one stage, on branch `claude/native21-s43-cleanup` from `ca839ed00` (s42, `9e075b4b`):
1. The DECISIONS 48 cleanup pass (`native-21/layout/track_cleanup21.py`, unchanged) on s42's routed copper (OPEN-ITEMS B5).
2. The snubber source MPN: C12 / C13 / C19 / C20 GRM31A5C3A102JW01D (not a Murata part) → YAGEO CC1206JKNPOCBN102
   (LCSC C113872). This is the part the JLC order already placed as a declared substitute.
3. The datasheet ledger:
   - the snubber entry is re-keyed;
   - GRM1885C1H472JA01D's temperature is re-cited to the DECISIONS 56 release case;
   - every margins.json citation now points at the s43 rows.

One card field gets worse: `jlc_extended_lines` 67 → 68. It does not change the verdict. The cause is the MPN fix, not
the cleanup (section 4).

## 1. What ran

```sh
R=/Users/bennet/Desktop/temper/worktrees/runs-native21/s43
git show ca839ed00:zapote/power-stage-120v/native-21/layout/copper.json > $R/base-s42.json         # b3295343…
cp native-21/verification/native21s42-all-copper.json.gz $R/export-s42.json.gz                    # 86d557fb…, board 9e075b4b
sh validation-results/11-candidates/c37-geometry-cleanup/passes37.sh $R/base-s42.json $R/export-s42.json.gz $R/p1
TASK04_WORKERS=4 sh native-21/layout/gates/chain.sh native21s43 $R/p1/b $R/c43
```

- **Cleaned copper.json:** `e5f7f90e…`. A second run of the tool on the same inputs is byte-identical.
- **First build** (`p1/b`): 0 unconnected, 0 errors, 0 dangling items. The warning set is the same as s42 (lib 199,
  silk 199 + 199 + 21).
- **Chain:** the settle loop trimmed nothing, so the chain's copper.json is the cleaned one. B3 and task 04 were
  recomputed because the model key changed in DECISIONS 56. `a4_fields.py check`: OK, 41 cases, board 61447816.
- **Idempotence:** the tool on s43's copper and its own export makes **0 edits** (`results/cleanup-s43-second-run.json`).

## 2. Geometry

Totals are from `gates/track_geometry.py` (`results/track-geometry-s4{2,3}.json`):

| Metric | s42 | s43 |
|---|---|---|
| Right-angle corners | 100 | **49** |
| Acute corners | 199 | **23** |
| Fold-backs (part of the acute count) | 43 | **3** |
| Any-angle track | 675.0 mm | **272.6 mm** |
| Track segments / length | 3,951 / 10,335.9 mm | 4,328 / 10,238.6 mm (−97.3 mm) |

Per layer (right / acute / fold-backs / any-angle mm):

| Layer | s42 | s43 |
|---|---|---|
| F.Cu | 69 / 137 / 31 / 478.8 | 29 / 13 / 2 / 167.8 |
| In1.Cu | 18 / 13 / 3 / 64.1 | 8 / 3 / 1 / 45.3 |
| In2.Cu | 5 / 22 / 4 / 58.8 | 3 / 4 / 0 / 31.0 |
| B.Cu | 8 / 27 / 5 / 73.3 | **9** / 3 / 0 / 28.5 |

- There were **621 edits on 100 nets** (`results/cleanup-s42-to-s43.json`; its `log` lists each one):
  - fold-backs 38 (5 free, 33 at a pad or via tip);
  - acute corners 131 (31 free, 100 at a pad or via tip);
  - right angles 67 (52 mitred free corners, 15 at pad or via tips);
  - any-angle segments 385.
- B.Cu gains one right angle, as on s37: an acute corner on a short arm traded for a square T.
- Items left, with reasons, are in the report's `left` field. The classes are the same as c37 section 6:
  - pad / via square exits;
  - arms too short to mitre;
  - the locked RES_A / OCP-sense nets;
  - the spine region;
  - other-net clearance;
  - dogleg pieces under 0.05 mm.

**Nothing was excluded from the cleanup.** The tool's own locks applied:
- res_a and the OCP-sense / Kelvin nets are never edited;
- the SELV-spine region is untouched;
- the barrier and RES_A-pair distances can only stay or grow;
- no fill may grow near the barrier.

The tracks the brief names were checked separately:
- **Gate networks** (`scripts/gate_net_spacing.py`, `results/gate-net-spacing.json`, PASS). 25 edits touched the 12
  gate-drive nets of the four CFD7s (gate / off / out, h / l):
  - no minimum spacing fell, either to any other net or to another HOT potential group (the hand-laid runs keep their
    3.2–4.8 mm);
  - every gate loop (gate + off + out) is shorter: 90.8 → 88.1, 116.5 → 113.7, 109.9 → 105.0 and 90.2 → 87.6 mm;
  - only the F.Cu OUT_L runs got longer, from doglegs: leg A +0.37 mm (+0.03 mm with its In1 run) and leg B +0.25 mm.
- **Fuse-copper necks** (`shoot-through-f1/s43_necks.json`): every segment field is identical to s42; min ratio 0.993.
- **Kelvin and the OCP sense:** unchanged (section 3).

## 3. Gates and metrics, s42 → s43

| Gate / metric | s42 | s43 |
|---|---|---|
| DRC errors / unconnected / plane splits | 0 / 0 / 0 | 0 / 0 / 0 |
| Barrier 8 mm (Rust) / RES_A outer 12.6 mm | 0 / 0, min F 20.393 / B 13.375 | identical |
| Rust census (item count, tracks the segment count) | 5,800 (F 949, B 495) | 6,177 (F 1,014, B 506) |
| D5 HOT–SELV / HOT–PE | 8.047 / 8.507 | 8.047 / 8.507 |
| DFM / vias / min track | PASS / 753 / 0.2 | PASS / 753 / 0.2 |
| SPINE_LOCK (owner none) / FIT | PASS / 403 0 0 405 0 | PASS / 403 0 0 405 0 |
| Bypass / PI distances / RES_A creepage 18 | PASS / PASS / PASS | identical (PI and bypass files unchanged) |
| Return path: open changes / worst asserted | 15 / 2.72 mm | 15 / 2.72 mm |
| Kelvin band / R_eff R35.2 | 67.77–116.44 A / 152.9 mΩ | identical |
| OCP pickup (pan-60 stack) | 4.17 A | 4.17 A |
| Fuse-copper min ratio | 0.993 | 0.993 |
| Task 04 | 39 / 0 failed, bus_p span 2.857 % | identical |
| CPL audit / BOM-CPL | 351 / 351, PASS | 351 / 351, PASS |
| Gerber ZIP | `658de5d3…` | `4442ef0a…` |

- **Task 04:** the largest R / loss changes are:
  - hv_dc −0.011 % (shorter copper);
  - res_a +0.043 % (0.69955 → 0.69986 mΩ). res_a is a locked net: this is a refill change beside it, not an edit.
  - Everything else is under 0.01 %.
- **Return path:** the open changes are re-ordered in `return-path.json`, because some polylines now run the other way.
  The count and the worst asserted gap are unchanged.
- **Test points:** the board-only planner re-placed TP3, TP4, TP7 and their references TP26 and TP29 along their own
  reshaped tracks, by 0.5–1.03 mm. These are the same points that moved on s37. `BRINGUP-PROBES.md` follows.

## 4. Scorecard: every field that moved

| Field | s42 | s43 | Why |
|---|---|---|---|
| track_right_angle_corners | 100 | 49 | the pass |
| track_acute_corners | 199 | 23 | the pass |
| track_fold_backs | 43 | 3 | the pass |
| track_any_angle_mm | 675.0 | 272.6 | the pass |
| b3_release_margin_K | +0.7 | **+1.2** | the worst release row is now C40 (+1.1 → +1.2 K); R10 is +0.7 → +3.1 K |
| b3_laminate_margin_K | −30.7 | −30.2 | c28 laminate block −30.6 → −30.2 K |
| b3_rated_part_margin_K | −33.4 | −32.3 | c28 R12 terminal 165.4 → 164.3 °C |
| b3_nominal_h10_peak_C (legacy, reference only) | 165.3 | 165.0 | |
| **jlc_extended_lines** | 67 | **68** | **the MPN fix, not the cleanup** |

`b3_ratings` (the release gate) stays **PASS** with no failing row.

**`jlc_extended_lines` +1.** The snubber line was always C113872, a JLC Extended part (lcsc-map, the SNAPSHOT's
`jlc_library`). Its Assembly label used to read "JLC substitute …", so the scorecard's substring count skipped it. As a
plain source MPN, the line is now labelled "JLC (Extended)" and counted. The count is now correct. The order, price and
stock are the same:
- parts $ 306.76 / 202.32;
- assemblable share 0.968 / 0.849.

**B3 rows** (`b3-ratings/margins.json` against s42's; heat inputs unchanged, so this is copper only):
- The R_on rows improve the most. Terminal derating gains 0.9–3.5 K at c18, 0.9–3.9 K at c22 and 1.1–3.7 K at c28.
  R18 c22 is now +0.5 K, from −3.4.
- The copper within 6 mm of each R_on is unchanged on In1 / In2 / B.Cu and 0.25–0.3 mm² smaller on F.Cu. The likely
  cause is the gate-loop mitres next to each R_on's pad 2 (the off runs at y 15.6 and the gate runs at y 20.3–21.8), but
  no separation run was made.
- Rows that got worse:
  - R_off R53 / R54 (1206) lose 0.2–0.7 K in every case; the worst is c28 R54 terminal, −14.2 → −14.9 K;
  - C38 / C39 / C152 / L1 lose 0.1–0.2 K;
  - R39 (unverified 1206 row) loses 0.3–0.5 K.
  None of these rows sets a card ratchet, and none crosses zero.
- The legacy single-cell peaks move as mesh artefacts (extreme_h10 247.0 → 241.4 °C). They are not compared.

The compare against the other benchmarks is in `results/compare.txt`:
- ACCEPT against s37, s35 and 19c;
- REJECT against s41, on the laminate ratchet only (−30.2 against −25.2). That is the DECISIONS 55 override, as for s42.

## 5. MPN change and ledger

**Source:**
- `elec/src/parts.ato` `Snubber1n1kV`: mpn CC1206JKNPOCBN102, manufacturer YAGEO, and a docstring citing YAGEO HV
  NP0/X7R spec V.16 pp.2/3/5/10.
- The footprint stays `Capacitor_SMD:C_1206_3216Metric`.

**Build:**
- Compiled with atopile 0.2.69 offline and exported (`tools/circuit_export.py`). Copied into `frozen/` and
  `native-21/frozen/` with the absolute worktree path normalised to the frozen files' existing prefix (as c39 did).
- The only differences are the four MPN / manufacturer records, the six libsource aliases (C12 / C13 / C19 / C20 and
  the aliased C42 / C43 lines), the CSV line, and the source hashes.
- 351 components and 183 nets; designators and nets are identical.

**Checks:**
- `audit.rs`: the four `c_snub` paths are added to IDENTITY, plus test `stage43_snubber_mpn_holds`. 85 / 85 tests pass,
  and the audit passes on build/ and on frozen/.
- `verify_source.py` asserts the MPN and the footprint.

**BOM / CPL:**
- `apply_lcsc.py` maps CC1206JKNPOCBN102 → C113872, Extended, and `ACCEPT_ALT` is empty. Line 34 now reads
  `CC1206JKNPOCBN102,…,C113872,…,JLC (Extended)`; the substitute note is gone.
- positions / CPL carry the new value.
- `STOCK-2026-10-13-addendum-s43.csv` and `study-2026-10-15/snapshot/s43` re-key the existing C113872 rows, with
  unchanged numbers; `run_all.sh` gains the s43 step.

**Ledger** (`gate.py` PASS: **3 VERIFIED / 32 PARTIAL / 58 UNAUDITED / 0 VIOLATION**; `tests/test_gate.py` 0 failures):
- **GRM31A5C3A102JW01D → CC1206JKNPOCBN102.** The ratings basis is unchanged (Yageo, batch A). The "source MPN to be
  corrected" owner gap is closed, and the Murata p.162 terminal-gap note now cites Yageo p.3 L4. Status: PARTIAL, with
  its bench / certifier gaps.
- **GRM1885C1H472JA01D:**
  - The temperature is re-cited from the c22 FET-row value (133.5 °C) to the release case c18_h10 (bay 61 °C): FET-row
    copper **122.1 °C ≤ 125 °C**. This is a violation-severity check, ratio 0.977, and it passes.
  - The c22 overrun (132.6 °C) is now an `owner: airflow route (c22/c28)` gap.
- **Every margins.json citation follows the s43 rows.** The rows are sorted by margin, so line numbers moved.
  - Values moved on L1 (c22 97.6), C38–C41 (C40 108.8 / 137.7), U41 / U42 (Tj 133.6), and R5 (terminals 118.3 / 130.9 /
    162.5, elements 122.8 / 138.0 / 174.4).
  - On 25121WF680JT4E, R10 at the release case is terminal 128.8 °C, so the allowed power is 0.3082 W and the ratio is
    0.704 (was 0.775). The c22 worst R_on is now **R12** (terminal 136.1 °C, 0.976 of the derated power; element
    140.9 °C).
  - The snubber's FET-row bound is 122.1 / 132.6 °C.
  - Ratios and rule texts were recomputed, and no status changed.

## 6. Reproduce

```sh
# source and audit
uv tool run --offline --from "atopile==0.2.69" ato --non-interactive build elec/src/power_stage_120v.ato:PowerStage120V
rm build/resolved-components.json; uv tool run --offline --from "atopile==0.2.69" python tools/circuit_export.py \
    "$PWD" "$PWD/build/resolved-components.json" --entry-file elec/src/power_stage_120v.ato --entry PowerStage120V
rustc --edition=2021 -O audit.rs -o /tmp/a && /tmp/a build/default.net build/default.csv build/resolved-components.json
rustc --edition=2021 --test audit.rs -o /tmp/t && /tmp/t
python3 native-21/verification/verify_source.py
# layout (section 1), then
(cd validation-results/02-protection-timing/shoot-through-f1 && python3 -I s21_necks.py s43)
(cd validation-results/02-protection-timing/coil-pickup/s21b && F8_COPPER=$PWD/../../../../native-21/verification/native21s43-all-copper.json.gz \
    python3 -I run_ocp.py && cp result.json result-s43.json && git checkout -- result.json)
python3 validation-results/04-board-current-thermal/round5-native21/a4_fields.py check
python3 -I validation-results/11-candidates/c43-cleanup/scripts/gate_net_spacing.py \
    $R/../s42/c42b/copper-dump.json $R/c43/copper-dump.json --json validation-results/11-candidates/c43-cleanup/results/gate-net-spacing.json
python3 native-21/layout/track_cleanup21.py native-21/layout/copper.json native-21/verification/native21s43-all-copper.json.gz \
    --report validation-results/11-candidates/c43-cleanup/results/cleanup-s43-second-run.json        # 0 edits
(cd validation-results/08-manufacturing-package/native-21/sourcing/study-2026-10-15 && bash run_all.sh)
(cd native-21/verification/datasheet-ledger && python3 -I gate.py; python3 -I tests/test_gate.py)
python3 -I native-21/layout/gates/scorecard.py native21s43 $R/c43 --audit PASS --json validation-results/10-benchmark/scorecard-native21s43.json
python3 -I native-21/layout/gates/scorecard.py --card validation-results/10-benchmark/scorecard-native21s43.json \
    --compare validation-results/10-benchmark/scorecard-native21s42.json
```

**Tests:**
- `gates/test_track_geometry.py` 7 / 7;
- `gates/test_spine_lock.py` 11 / 11;
- `layout/test_track_cleanup21.py` 45 / 45 (`results/test_track_cleanup21.txt`);
- ledger `tests/test_gate.py` 0 failures;
- `audit.rs` 85 / 85.

The tests ran with `native-21/section.kicad_pcb` = the s43 board (`61447816…`).

**Runs** (outside the repo): `worktrees/runs-native21/s43/`, with `p1` (the pass and its build), `c43` (the chain build),
`margins-s42.json` (s42's margins, kept for the comparison) and `determinism-copper.json`.
