# Scoped chain (native-21)

The scoped chain re-runs only the chain steps whose inputs changed against a benchmark build. Every other step's
output is reused, and the reuse is justified by a content key. The full `chain.sh` stays mandatory at merge to the
integration branch. A scoped card cannot serve as a benchmark: `scorecard.py --compare` refuses one.

    # once: any full chain.sh run (this version) writes BUILDDIR/scoped-manifest.json, which makes that build a benchmark
    python3 -I scoped_chain.py classify --bench-ref <benchmark commit>              # what changed, what would run
    python3 -I scoped_chain.py run TAG PASSDIR BUILDDIR --bench-build <full build> [--dry-run]
    python3 gates/scorecard.py TAG BUILDDIR --audit PASS --json fresh.json
    python3 -I scoped_chain.py card --plan BUILDDIR/scoped-plan.json --fresh fresh.json \
        --bench-card validation-results/10-benchmark/scorecard-native21sNN.json --out scoped-card.json
    python3 gates/scorecard.py --card scoped-card.json --compare validation-results/10-benchmark/scorecard-native21sNN.json

## How a run is decided

1. **Paths.** `git diff` from the benchmark commit to the working tree, including untracked files. `depmap.json`
   `path_rules` (first match wins) puts each path in one of these classes:
   - `build`: the frozen netlist and BOM, layout, `copper.json`, placement, rules, libraries;
   - `input` of named steps: gate scripts, thermal scripts, heat inputs, firmware `thermal_mgmt.h`, desk files;
   - `output`: files the chain writes;
   - `doc`, `test` or `not_read`: studies and records no step reads.
   A path no rule matches is `unknown`. An unknown path, a stack-up change or a change to `chain.sh`, `regate.sh` or
   this folder sends the run to the **full chain**.
2. **Board.** If any `build` path changed, the board is rebuilt. On every rebuilt board, every safety gate and export
   runs again: DRC, Rust barrier, D5, DFM, bypass, RES_A, PI, return path, spine lock, fit, fab and Kelvin. With no
   board input changed, the benchmark build is copied (same `board_sha256`). Only the steps whose own files changed
   run, plus every cheap step (under a minute; `policy: cheap`).
3. **Thermal steps** (task 04, B3 study and ceiling sweep, B3 ratings) run when their key differs from the manifest's.
   A key is built from:
   - the canonical copper key (`net_keys.py`: `copper_key.py`'s rows, with the `.kicad_pro` schematic sections dropped);
   - the step's files (`depmap.json` `step_files`, as git blob ids);
   - the upstream key (task 04 feeds B3 and the ratings).
   On a rebuilt board, a B3 rerun forces task 04 as well, because `thermal.py` checks that both come from the same
   board. A task-04 rerun reruns everything downstream of it. Two things can also block a reuse: local task-04
   `outputs/*.npz` that differ from the manifest's, or a `margins.json` that is not the benchmark's.
4. **Manual card inputs** are the F1 necks file, the OCP pickup file and `audit.rs`. Each is reused while its key holds:
   the `net_fill` keys of the nets it reads and the `part_geom` keys of the parts. A lane that provides the tag file
   counts as having rerun the step. Otherwise the entry is marked **STALE**, and the card is not final until the lane
   reruns the study. For `audit.rs`, the lane's `--audit` attestation counts as the rerun.

The scoped card (`scoped` key) lists every entry under one of three headings:
- *recomputed*;
- *reused*, with the key that proves the reuse. If the scorecard could recompute the value from the reused outputs it
  says so; otherwise the value is carried from the benchmark card;
- *stale*.

## Files

| File | What |
|---|---|
| `depmap.json` | Every chain step: its s43 wall time, workers, policy, card entries, outputs and read set (13-coupling read sets). Also the path rules, the step files that keys hash, the per-TAG rewrites to undo, and the multi-producer entries. |
| `net_keys.py` | KiCad Python. Builds per-net (`net_own`, `net_fill` with 13 mm refill reach) and per-part (`part`, `part_geom`) keys of a built board, and reproduces `copper_key.py`. |
| `scoped_lib.py` | Path classifier, trees (a git commit or a checkout), content keys, board and BOM diff, the planner, and the scoped-card merge. |
| `scoped_chain.py` | CLI: `classify`, `run`, `decide` (called by `chain.sh`), `manifest` (called by `chain.sh`), `card`. |
| `depmap_check.py` | Controls on the map. C1: every card entry has a producer. C2/C3: agreement with 13-coupling `verification.json`. C4: static scan of path literals in the thermal scripts and `chain.sh`. C5: firmware reads. C6: the import closure of the thermal steps. |
| `test_scoped.py` | 16 planner controls. |
| `backtest.py` | Replays 7 stage pairs and 10 re-scores from git and checks that no reused entry changed. Board keys for the 10 scored builds are cached in `backtest-netkeys/`; `backtest-results.json` is the last run. |
| `estimate.py` | Wall time and worker-minutes per lane, from the s43 timings. |

## Limits

- **Physical gaps.** A reuse is exactly as good as a rerun with the same inputs: it reproduces the full chain's answer,
  not physical truth. The full chain has the same gaps, and so does the scoped one:
  - the B3 ratings limits and `b3-convergence/inputs/part-bodies.json` are not derived from the BOM or the placement;
  - `make_heat_sources.py` derives heat from the BOM and the placement. That case is covered: it runs before the keys.
- **Static scans.** C4 and C6 cannot see dynamically built paths. Run `depmap_check.py` whenever a thermal script or a
  gate changes. It is cheap.
- **Layout lanes.** Any copper change reruns the whole thermal block: B3 reads all copper. Scoping does not shorten a
  layout iteration (see the measured profile in the study README).
