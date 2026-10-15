# Step 0 of phase A: the chain cache trap is closed (DECISIONS 38), proof on s32 (2026-10-14)

## The trap
`regate.sh task04` keyed its cache on the board's copper inputs plus four task-04 scripts. The B3 key in `chain.sh`
used its own four scripts. Suppose a B3 script (or the stackup) changed while the copper did not. Task 04 then
took a cache hit, so its A4 cases stayed on the board they were computed on, while B3 recomputed. B3's
same-board check (`thermal.py`: geometry board hash == A4 cases' board hash) then failed. Several model inputs were
in neither key: `sheet_solver.py`, `layers21.py`, the stackup file, the exporters, and B3's heat inputs.

## The fix
- `native-21/layout/gates/model_key.py` hashes every model input that is not the board's copper. That covers the
  task-04 scripts (run_cases, run_board, summarize, kit_topology_native13), `sheet_solver.py`,
  `export_power_copper.py`, `copper_key.py`, `layers21.py`, the B3 scripts (make_heat_sources, run_study with the
  TAG masked, ceiling_sweep, thermal) and `extract_geometry.py`. It also covers task 03's
  `board_heat_sources.json`, B3's `inputs/*.json`, the resolved stackup file(s) by content (`$NATIVE21_STACKUP`,
  `$B3_STACKUP`) and `$SHEET_BARREL`. `--list` prints each dependency and its hash.
- Both caches take this one key: task 04 = `copper_key + model_key`, B3 = `copper_key + model_key + task-04 results`.
  Any model change therefore misses both caches together. A task-04 hit now implies that B3's inputs are those of
  the run that computed it.
- `chain.sh` runs `make_heat_sources.py` before task 04, so the heat inputs in the key are current.
- Belt and braces: if B3 still misses after a task-04 hit (a lost or overwritten B3 cache), the chain re-runs task
  04 on this build (`TASK04_FORCE=1`) instead of failing late.
- `regate.sh`'s cache.json now records `copper_key` and `model_key`.
- Also in this commit: the `SHEET_BARREL=stackup` switch in `sheet_solver.add_via` (DECISIONS 38's depth basis).
  The barrel length becomes the copper-centre span of the listed layers (1.563 mm F-B on four layers) instead of
  the fixed 1.6 mm. It is unset by default, so every committed result reproduces. It is part of the model key.

## Proof (`runs-native21/s33/cache-p{1,2,3}`, `chain.sh native21s32 runs-native21/s32/p3/i2`)
| run | change | task 04 | B3 | result |
|---|---|---|---|---|
| P1 | new key format (first run) | computed | computed | CHAIN_DONE; task 04 39 / 0 failed, bus_p span 2.8351 %; B3 162.1 / 129.0 / 247.1 / 192.3 / 135.0 °C: the accepted s32 figures |
| P2 | none (rerun, a new refill: board 781f4117 vs 457405655) | **hit** (computed on 457405655b76) | **hit** | CHAIN_DONE, same figures |
| P3 | `thermal.py` touched (one comment line appended; B3-only, the old trap case) | **miss**, recomputed | **miss**, recomputed | CHAIN_DONE, same figures; no board-hash failure |

The touch was reverted afterwards. The model key is back to `054334104e26…`, the key P1 / P2 ran with.
Before the fix, P3's case gave a task-04 hit and a B3 failure.
