# Stage 53 (c53-cert-provisions), first part: S10 ovp_ok_hot, the R43 fit gate, the model gate

Selv lane, 2026-10-16, branch `claude/native21-s53-cert-provisions` (from df9f46f68), integrated into
`codex/power-stage-integration`. DECISIONS 75 is the decision record. The BOM is s52's. The R5 average-current trip, the
inlet relay provision and the F1 tabs of `11-candidates/c53-stuck-on/S53-SCOPE.md` are not in this part.

| | Lane | Integration (board of record) |
|---|---|---|
| Board | `2c2f2223…` | `82af7bd93e62d1f2e6c7c2c2b971a4830bf6e09078bae3f269d8bead9a31fd27` |
| Copper key | `b7a0bc5790b9` | `b7a0bc5790b9` |
| Chain | `runs-native21/s53/chain3.out` (SPINE_OWNER=selv) | `runs-native21/s53/chain-int.out` (CHAIN_DONE) |
| Card vs s52 | ACCEPT | ACCEPT: `cheaper [], better ['return_path_open_changes']` |
| Gerber zip | `4c81a5a7…` | `a6afd37a4f4e0039de8de7fd86755ff65328f21e43501a23d0904e78ffbd4ddc` |

## Results

- **Return path (S10):** 7 → 4 opens on KiCad's fill (`gates/return_path19.py` on the pass's `copper-dump.json`).
  `edit_base53` moves the `ovp_ok_hot` In1 run to In2; that closes the two ovp_ok_hot opens and, as a consequence, the
  ocp_ok_hot launch at (117.0, 54.995) (the planning simulator wrongly kept it open). Pass j1: unconnected 0, errors 0.
  Left: `bus_fault_hot` (101.1, 74.9), (100.6, 114.0), (113.635, 114.5); `monitor_ls-good` (104.4, 99.65).
- **Kelvin band:** 69.18–114.57 A, floor 64.17 A met (`kelvin/budget-native21s53.json`).
- **Fit:** `blk-fit.log`: `MODELS PASS: 360 model refs, 33 files … failures 0`; `FIT 424 0 0 R43 425 hits 4 new 0 worse 0
  stale 0 outside 0`. The 4 hits are in `validation-plan/enclosure-fit/r43-expected-hits.json`.
- **Fit mark:** `results/bank-mark-s53.json` PASS (text 1.2 mm / stroke 0.2 mm): 0.625 mm to the C152 courtyard, 0.97 mm
  to other silk, 3.18 mm to a mask opening, 18.85 mm to the board edge.
- **F1 necks:** `shoot-through-f1/s53_necks.json`, min ratio 0.993 (same as s52). Without that file the card falls back to
  the generic `result.json` (0.208) and reports a false regression: run `s21_necks.py s53` before scoring a new tag.

## Problems met (for the next stage)

1. A placeholder board hash in `kelvin_plane.py` broke the chain's auto-pin step; add no pin by hand.
2. `0690d5602`'s model repoint edited pcbnew copies (`fp.Models()` returns copies). The model gate found it; fixed in
   `build_native21.py` by rebuilding the model list.
3. The ledger's cited temperatures move by 0.1 K between builds of the same copper; re-read them after each chain
   (this stage: U5 102.9, R59 87.5 → 87.6, R83 margin 71.5, U42 137.5).
4. `plan_board_only21.py` / the fit gate need the tracked `PS/models3d/`; the untracked `native-21/models3d/` copy is not
   used any more.

## Reproduce

```
R=../../runs-native21/s53
git show 902faaa5c:zapote/power-stage-120v/native-21/layout/copper.json   # (the s52 copper is the committed copper.json before this stage)
sh validation-results/11-candidates/c53-cert-provisions/stage53/scripts/passes53.sh $R/base-s52-copper.json $R/p1
TASK04_WORKERS=4 sh native-21/layout/gates/chain.sh native21s53 $R/p1/j1 $R/c53int
(cd validation-results/02-protection-timing/shoot-through-f1 && python3 -I s21_necks.py s53)
python3 -I native-21/layout/gates/scorecard.py native21s53 $R/c53int --audit PASS --json validation-results/10-benchmark/scorecard-native21s53.json
python3 -I native-21/layout/gates/scorecard.py --card validation-results/10-benchmark/scorecard-native21s53.json --compare validation-results/10-benchmark/scorecard-native21s52.json
python3 -I validation-results/11-candidates/s52-proto-bom/scripts/bank_mark52.py $R/c53int/section.kicad_pcb   # then move the output
```
