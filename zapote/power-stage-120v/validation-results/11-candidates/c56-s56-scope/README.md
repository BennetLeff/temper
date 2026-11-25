# c56: stage 56 scope and the CTRL divider (S22)

Lane `claude/native21-s55-unified`, 2026-11-24. DECISIONS 85 has the result and the items not built.

| Step | Command (from `zapote/power-stage-120v`) |
|---|---|
| scope numbers | `python3 -I validation-results/11-candidates/c56-s56-scope/scripts/s56_scope.py --check` |
| source | `uv tool run --offline --python 3.11 --from atopile==0.2.69 ato --non-interactive build elec/src/power_stage_120v.ato:PowerStage120V`, then `python tools/circuit_export.py` in the same tool environment (README "Build and verify") |
| board + gates | `sh native-21/layout/gates/chain.sh native21s56 RUNS/s55/u47 RUNS/s56/c56b` |
| ledger | `scripts/apply_ledger56.py`, then `scripts/recite56.py` after the chain |
| card | `scorecard.py native21s56 RUNS/s56/c56b --audit PASS --json validation-results/10-benchmark/scorecard-native21s56.json` |

A fresh worktree has no `native-21/section.kicad_pcb` (generated, not committed): run
`prototype-closure/pcb/build_native21.py` with KiCad's Python before the first chain.

`s56-scope.json` reads the margins of the board in `b3-ratings/margins.json`, so its `board` field follows the last chain;
the U26 margins quoted in DECISIONS 85 are the same on s55 and s56.
