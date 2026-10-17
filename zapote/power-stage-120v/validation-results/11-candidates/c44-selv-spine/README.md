# Candidate 44: SELV-side return-path pass, built as stage 44 (native21s44)

**Verdict: card ACCEPT against s43.** Board native21s44 `2a84051f…`, chain CHAIN_DONE with `SPINE_OWNER=selv`
(SPINE_LOCK PASS after the selv lane re-issued the lock, section 5).

```
ACCEPT native21s44 vs validation-results/10-benchmark/scorecard-native21s43.json: cheaper [], better ['return_path_open_changes', 'track_acute_corners']
```

Branch `claude/native21-s44-selv-spine` from `cb48a12e6` (s43, `61447816`). OPEN-ITEMS S10 asked for a SELV-side
return-path pass. **Return-path open changes 15 → 7.** All 8 opens on SELV nets are closed. The 7 left are on HOT-side
nets (the Kelvin / LS domain), outside the SELV islands (section 3).

What changed:
- Seven 100 nF 0603 v3v3-selv_gnd transfer caps, **C169–C175** (`c_ref_xfer_6..12`). They use the existing JLC Basic line
  C14663, CC0603KRX7R9BB104, so no BOM line is added.
- BUS_FAULT's drop via moves 0.97 mm down its own trunk.
- BIAS_GOOD's In2 hop is extended to its leg-A drop, and its unreferenced edge via is removed.

Nothing else moved:
- no part outside the SELV islands;
- no contract-net copper, J4 pin or frozen transfer cap (C47, C144, C153–C156);
- the barrier floor, D5, RES_A and every other card metric are unchanged (section 4).

## 1. What ran

```sh
R=/Users/bennet/Desktop/temper/worktrees/runs-native21/s44
git show cb48a12e6:zapote/power-stage-120v/native-21/layout/copper.json > $R/base-s43.json     # e5f7f90e…
sh validation-results/11-candidates/c44-selv-spine/passes44.sh $R/base-s43.json $R/p1             # j1 clean
SPINE_OWNER=selv TASK04_WORKERS=4 sh native-21/layout/gates/chain.sh native21s44 $R/p1/j1 $R/c44   # run 1: SPINE_LOCK FAIL (expected)
# re-issue native-21/layout/selv_spine_lock.json from the run-1 export (section 5), then
SPINE_OWNER=selv TASK04_WORKERS=4 sh native-21/layout/gates/chain.sh native21s44 $R/p1/j1 $R/c44   # run 2: CHAIN_DONE
```

- **Pass j1:** 0 unconnected, 0 errors, barrier 0. The DRC warning set is s43's: lib 199, silk 199 + 199 + 21.
- **Copper:** `copper.json` is `9b48413e…`. The chain's settle loop trimmed nothing.
- **Run 1** (board `f27d5bba`):
  - every block passed except SPINE_LOCK;
  - task 04 and B3 recomputed, because the model key had changed since s43 (stackup.json).
- **Run 2** (board `2a84051f`):
  - its copper is identical to run 1's: 4,283 tracks, 765 vias and 1,082 pads equal, and `fill_hash.py` area hash
    `39fe161d` with 0.0 mm² symmetric difference. Only KiCad's footprint order in the file differs;
  - task 04 and B3 took cache hits;
  - B3 ratings were re-solved on this board.
- **Cleanup pass (DECISIONS 57):** `track_cleanup21.py` was run twice and made **0 edits** both times:
  - on the j1 copper and its export, before the chain;
  - on the final copper and the s44 export (`results/cleanup-s44-second-run.json`).

## 2. Opens: s43 → s44, net by net

Each layer change is judged against `return_path19.py`'s rule: it is open unless a v3v3-selv_gnd cap (or a stitch via) is
within 3.0 mm. The full table is in `results/return-path-s43-s44.json`.

| Net | Via | s43 | s44 | Fix |
|---|---|---|---|---|
| permit | (33.2, 120.2) F↔B, leg-B drop | C47 6.94 mm | **C169 1.10** | cap |
| permit | (70.0, 127.8) F↔B, leg-A drop | C144 8.69 | **C172 1.48** | cap |
| permit | (36.5, 178.6) F↔B at J4 | C156 20.89 | **C174 2.43** | cap |
| bus_fault | U13.4 drop (34.843, 131.565) F↔B | C47 4.55 | **C170 2.60**, via at (35.0, 132.523) | via move + cap |
| bus_fault_iso | (76.825, 125.875) B↔F | C144 9.83 | **C173 1.13** | cap |
| bias_good | (74.0, 123.4) F↔B, leg-A drop | C144 12.2 | **C171 1.51** (now F / In2 / B) | cap |
| bias_good | (69.2, 127.0) In2↔B | no pour under either side | **via removed** | reroute on In2 |
| bias_good | (33.2, 70.4) F↔B, leg-B drop (TP19) | C61 7.15 | **C175 1.94** | cap |
| bus_fault_hot ×3, ocp_ok_hot, ovp_ok_hot ×2, monitor_ls-good | HOT side | open | open | not in this lane (section 3) |

Two s43 changes were already closed and stay closed: bus_fault_iso at U9 (C37, 2.89 mm) and the pwm / ct_zc changes.
The asserted worst stays at **2.72 mm**.

**Why the opens were open.** The slow SELV lines (PERMIT, BUS_FAULT, BUS_FAULT_ISO, BIAS_GOOD) run on F.Cu over the In1
v3v3 pour and on B.Cu over the In2 selv_gnd pour. So every F↔B via moves the return current from one plane to the other.
No transfer cap was in reach of any of them: the nearest were C47 / C144 / C156 / C61, at 4.6–21 mm.

**Fix options considered, per via.** The search tools are `scripts/cap_spots.py` and `scripts/via_spots.py`, with records
in `results/cap-spots-s43.txt`.
- **Reroute on one reference.** F↔In2 keeps In1 v3v3 under both sides, and In1↔B keeps In2 selv_gnd. But every one of
  these lines lands on an F.Cu SMD pin, and its trunk would then slice a plane. This was used only for BIAS_GOOD's U40
  hop, which already ran on In2.
- **Move the via to an existing cap.**
  - C47: best 3.0 mm for PERMIT (fails) and 3.57 mm for BUS_FAULT.
  - C61: 2.67 mm for BIAS_GOOD, but the move is 4.5 mm and crosses the leg-B permit-gate vias. Not taken; the new cap
    gives 1.94 mm with no reroute.
- **New cap with its own plane vias.** Taken for all seven:
  - a via 0.85 mm off each pad (return_path19 holds C153–C156 to ≤ 1.6 mm, and now C169–C175 too);
  - ≥ 8.1 mm plan view from HOT copper, above the 8.047 mm D5 floor;
  - rules21 clearance + 0.02 mm on all four layers.
- **Plane stitch.** Not applicable: there are no same-net references on two layers on four layers.

**Per via:**
- **BUS_FAULT:** no 0603 fits within 3.0 mm of the old via (0 poses; U13 / R134 / C167 fill the row). The via moves down
  its own B.Cu trunk to (35.0, 132.523):
  - its 45° / 90° F.Cu escape is U13.4 → (34.843, 131.565) → (34.843, 132.366) → via;
  - it clears R134.1 by 0.2 mm;
  - C170 sits below the row;
  - the trunk's B.Cu tail under U13 goes, which also removes one acute corner (23 → 22).
- **BIAS_GOOD at (69.2, 127.0):** the In2→B via sat on the SELV pour edge, the 8 mm line, so there was no pour under its
  ring on either side. Between that edge and PERMIT's F.Cu diagonal there is no room for a referenced via (the legal spots
  read ~8/16 ring votes). Instead, the U40 feed's In2 leg runs on along the B.Cu trunk's own stair-step path to the
  leg-A drop (74.0, 123.4), which becomes an F / In2 / B junction that C171 serves.
- **C171 pad 2** lands on the existing selv_gnd via (77.401, 122.512); the via overlaps the pad edge by 0.15 mm. Under
  POFV, every 0.3 mm via is filled and capped.

## 3. The 7 opens left, and why

All 7 are HOT-side lines. Their vias sit where no pour lies on an adjacent layer: off the In1 `ocp_kelvin_p` / `n_ls`
pours (0.5–3.4 mm away), with In2 and B.Cu bare there.

| Net | Via | Layers | Nearest pour |
|---|---|---|---|
| bus_fault_hot | (101.1, 74.9) | In2↔B | In1 ocp_kelvin_p 1.2 mm |
| bus_fault_hot | (113.635, 114.5) | F↔In2 | In1 n_ls 1.5 mm |
| bus_fault_hot | (100.6, 114.0) | In2↔B | In1 n_ls 3.4 mm |
| ocp_ok_hot | (117.0, 54.995) | F↔B | In1 ocp_kelvin_p 0.5 mm |
| ovp_ok_hot | (117.847, 55.095), (114.448, 55.695) | F↔In1 | the F side is on In1 ocp_kelvin_p; the In1 side has none |
| monitor_ls-good | (104.4, 99.65), U45.1 | F↔B | In1 n_ls 1.0 mm (DECISIONS 52: the only legal via spot) |

Why they are left:
- Closing them takes HOT-domain copper: an In2 Kelvin image pour, an extended In1 Kelvin / n_ls pour, or a coupled
  Kelvin track.
- The `ocp_*` / Kelvin nets are locked: the stage-28 OCP lock, `track_cleanup21.LOCKED_NETS`, and the OCP pickup 4.17 A
  rests on their geometry.
- They are G08 / LS (WS4) territory, outside the SELV islands this lane may touch.

**Lane for them:** a WS4 / G08 pass, with OCP pickup and Kelvin re-checked. For the GOOD node, the B8 end-of-line veto test
still covers the corridor (DECISIONS 52).

## 4. Gates and metrics, s43 → s44

| Gate / metric | s43 | s44 |
|---|---|---|
| DRC errors / unconnected / parity | 0 / 0 / 0 | 0 / 0 / 0 |
| Barrier 8 mm (Rust) / RES_A outer 12.6 mm | 0 / 0, min B.Cu 13.375 | identical |
| Rust census | 6,177 | 6,226 (new pads, vias, stubs) |
| D5 HOT–SELV / HOT–PE | 8.047 / 8.507 | **8.047 / 8.507** |
| DFM / vias / min track | PASS / 753 / 0.2 | PASS / **765** / 0.2 (+13 plane vias, −1 bias_good) |
| Plated holes; 0.3 mm vias in / at a pad (`via_in_pad.py`) | 847; 59 / 75 | 859; 60 / 75 (a TP pad on a new plane via) |
| SPINE_LOCK | PASS (owner none) | PASS (owner selv, re-issued) |
| Bypass / PI / RES_A creepage 18 / return_path19 | PASS | PASS (U13 still on C47 2.65 mm) |
| Return-path open changes / worst asserted | 15 / 2.72 mm | **7** / 2.72 mm |
| Kelvin band / R_eff R35.2 | 67.77–116.44 A / 152.9 mΩ | identical |
| OCP pickup (pan-60 stack) | 4.17 A | 4.17 A (`result-s44.json` equal to s43 except the board hash) |
| Fuse-copper min ratio | 0.993 | 0.993 (`s44_necks.json` equal to s43's) |
| Task 04 | 39 / 0, bus_p span 2.857 % | identical |
| B3 release margin / laminate / rated part | +1.2 / −30.2 / −32.3 K; `b3_ratings` PASS | **identical**; PASS |
| EMI / touch / CMTI | 12.4 dB / 0.241 mA / 1.579 | identical (desk studies; no input moved) |
| Jet strip | max 1.72 mm (C13) | max 1.72 mm (C12, the same height) |
| FIT (board-only) | 403 0 0 405 0 | 410 0 0 412 0 |
| CPL audit / BOM-CPL | 351 / 351, PASS | 358 / 358, PASS |
| Gerber ZIP | `4442ef0a…` | `d5707f03…` |

**B3:** of 132 margins.json rows, 2 moved, both by 0.1 K:
- c22 C152, 90.4 → 90.3 °C;
- c22 U41 Tj, 124.7 → 124.8 °C.

**Card: every field that moved** (`10-benchmark/scorecard-native21s44.json`):

| Field | s43 | s44 |
|---|---|---|
| return_path_open_changes | 15 | **7** |
| track_acute_corners | 23 | **22** (BUS_FAULT's B.Cu tail) |
| parts_usd_at_500 / at_5 | 202.32 / 306.76 | 202.38 / 306.90 (+7 × C14663) |
| placements | 351 | 358 |
| vias | 753 | 765 |

BOM lines (93), extended lines (68) and every buildability field are unchanged. Against the other benchmarks
(`results/compare.txt`):
- ACCEPT against s42 and s38;
- REJECT against s41 on the laminate ratchet only (−30.2 against −25.2 K). That is the DECISIONS 55 override, as for s42
  and s43.

**Test points:** the board-only planner re-placed some test points from the new copper; `BRINGUP-PROBES.md` follows.
- TP13 (pwm_ha) moves to (71.4, 128.0), with its reference on C172's selv_gnd via.
- TP20 (bus_fault) moves to (35.8, 173.0). Its old spot was on the removed trunk tail.
- TP21 / TP22 take reference TP40.
- TP4 / TP26 (n_ls) move 1.0 mm, the same toggle seen at s42 → s43.

## 5. SELV-spine lock re-issued (selv lane)

Run 1, in `--owner selv` scope (`results/spine-lock-run1-vs-s38.json`):
- **added 20, removed 0:** the four plane vias (as 16 per-layer keys) and four F.Cu stubs of C170 (35.1, 135.9) and
  C174 (36.5, 175.4);
- **fill:** selv_gnd In2.Cu and v3v3 In1.Cu each lose 3.155 mm² (their antipads);
- nothing else.

In full (non-owner) scope, other lanes also see:
- the C170 / C174 pads;
- the BUS_FAULT via move, with 5 track and 4 via keys out and 3 and 4 in;
- the TP13 / TP20 / TP34 → TP39 re-plan.

No contract-net copper, J4 pad or frozen cap changed.

`native-21/layout/selv_spine_lock.json`:
- **baseline** → `native-21/verification/spine-baseline-native21s44-all-copper.json.gz`, the run-1 export kept under its
  own name. Its board is `f27d5bba`; run 2's copper is identical.
- a `reissued` record with the previous baseline (s38, `6f080b0d`).
- **frozen_refs** gains C169–C175. They are checked wherever they lie, like the stage-19b caps. This is a tightening:
  non-owner lanes may not move them.

Run 2: SPINE_LOCK PASS in both scopes. `gates/test_spine_lock.py` passes 11 / 11.

## 6. Source, BOM and ledger

**Source:** `elec/src/power_stage_120v.ato` adds `c_ref_xfer_6..12` (C100n0603, v3v3 / selv_gnd), with designators
C169–C175.
- Built with atopile 0.2.69 offline and exported (`tools/circuit_export.py`).
- Refrozen to `frozen/` and `native-21/frozen/`, with the worktree path normalised to the existing `ps-integrate` prefix.
- The only differences are the 7 components, their 14 net nodes, the CSV line and the source hashes.
- 358 components, 183 nets.

**`audit.rs`:**
- `c_ref_xfer_5..12` are in IDENTITY;
- the transfer-cap net check now loops over 1..=12;
- new test `stage44_selv_transfer_caps_hold`;
- **86 / 86** tests pass, and the audit passes on `build/` and on both frozen copies.

`verify_source.py` asserts 358 components and the 12 transfer caps' MPN.

**BOM / CPL:** C169–C175 join the CC0603KRX7R9BB104 / **C14663 JLC Basic** line (qty 44 → 51; JLC stock 50.9 M). There is
no new line and no new MPN.
- The sourcing study gains an s44 step (`run_all.sh`, `snapshot/s44/`), which re-keys qty in `SNAPSHOT-2026-10-15.csv`.
- No other output changed.

**Ledger:** C169–C175 are added to the CC0603KRX7R9BB104 entry (SIGNAL, UNAUDITED as before).
- `gate.py` PASS, 3 / 32 / 58 / 0.
- `tests/test_gate.py` 0 failures.

**Gate (tightening):** `return_path19.XFER_CAPS` now holds C169–C175 to the ≤ 1.6 mm pad-to-plane-via rule. All are 0.85 mm,
except C171's selv_gnd pad at 0.63 mm.

## 7. Files and reproduce

**Layout:**
- `native-21/layout/patches21.py`: `S44_CAPS` (poses and plane vias, one source), `edit_base44`, `s44_pads`;
- `incr21.py`: `edit_base44` on load;
- `place.py`: the poses from `S44_CAPS`;
- `parts.json`: 7 rows.

**Scripts** (study aids, not gates):
- `scripts/cap_spots.py`: cap poses with their own plane vias;
- `scripts/via_spots.py`: legal via spots with ring references;
- `scripts/precheck44.py`: the stage-44 copper against the s43 dump, PASS (`results/precheck44-on-s43.txt`);
- `scripts/zoom.py`: zoom plots.

**Not staged** (per the lane brief):
- `fab/assembly-drawing.pdf`, regenerated by the chain;
- `validation-plan/enclosure-fit/plan-result.json`.

**Not edited:**
- FAB-NOTE's board / gerber SHA and the drill and via-in-pad counts (859 plated, 750 × 0.3 mm vias; 60 / 75). These are
  for the integration records commit.
- DECISIONS.md and OPEN-ITEMS.md (draft in `DECISIONS-DRAFT.md`).

```sh
uv tool run --offline --from "atopile==0.2.69" ato --non-interactive build elec/src/power_stage_120v.ato:PowerStage120V
rm build/resolved-components.json; uv tool run --offline --from "atopile==0.2.69" python tools/circuit_export.py \
    "$PWD" "$PWD/build/resolved-components.json" --entry-file elec/src/power_stage_120v.ato --entry PowerStage120V
rustc --edition=2021 -O audit.rs -o /tmp/a && /tmp/a frozen/default.net frozen/default.csv frozen/resolved-components.json
rustc --edition=2021 --test audit.rs -o /tmp/t && /tmp/t
python3 native-21/verification/verify_source.py
# layout and chain: section 1; re-issue: section 5
(cd validation-results/02-protection-timing/shoot-through-f1 && python3 -I s21_necks.py s44)
(cd validation-results/02-protection-timing/coil-pickup/s21b && F8_COPPER=$PWD/../../../../native-21/verification/native21s44-all-copper.json.gz \
    python3 -I run_ocp.py && cp result.json result-s44.json && git checkout -- result.json)
(cd validation-results/08-manufacturing-package/native-21/sourcing/study-2026-10-15 && bash run_all.sh)
(cd native-21/verification/datasheet-ledger && python3 -I gate.py; python3 -I tests/test_gate.py)
python3 native-21/layout/track_cleanup21.py native-21/layout/copper.json native-21/verification/native21s44-all-copper.json.gz \
    --report validation-results/11-candidates/c44-selv-spine/results/cleanup-s44-second-run.json      # 0 edits
python3 -I native-21/layout/gates/scorecard.py native21s44 $R/c44 --audit PASS --json validation-results/10-benchmark/scorecard-native21s44.json
python3 -I native-21/layout/gates/scorecard.py --card validation-results/10-benchmark/scorecard-native21s44.json \
    --compare validation-results/10-benchmark/scorecard-native21s43.json
```

**Tests** (with `native-21/section.kicad_pcb` = the s44 board `2a84051f`):

| Test | Result |
|---|---|
| `gates/test_track_geometry.py` | 7 / 7 |
| `gates/test_spine_lock.py` | 11 / 11 |
| `gates/test_jet_strip_height.py` | 7 / 7 |
| `gates/test_trim_tails.py` | PASS |
| `layout/test_track_cleanup21.py` | 45 / 45 |
| `layout/test_layers21.py` | PASS |
| ledger `tests/test_gate.py` | 0 failures |
| `audit.rs` | 86 / 86 |

**Runs** (outside the repo): `worktrees/runs-native21/s44/`
- `p1`: the pass, its build, the j1 export and the cleanup report;
- `c44-run1`: the run-1 chain build, the spine baseline's board;
- `c44`: the run-2 chain build;
- `margins-s43.json`;
- `base-s43.json`.
