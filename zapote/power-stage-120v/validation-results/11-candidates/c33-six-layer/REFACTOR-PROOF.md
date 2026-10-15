# Stage 33 refactor: one layer-stack source, behaviour-neutral on the four-layer board (proof on s31)

**Result: neutral.** With the refactored code, every gate and model reproduces the pre-refactor outputs exactly
on the same board file (86 of 86 artefacts equal, table below). A fresh rebuild gives the same board inputs
(footprints, tracks, vias, zone outlines and rules). It also prints the same chain summary as the pre-refactor
chain and the accepted s31 chain: every gate line, Kelvin, task 04 and B3 peaks, and the fab counts. The scorecard
is unchanged against `scorecard-native21s31.json`. Proven on s31 (38e856ef3) and again on s32 after the rebase onto
d35219516 (last section).

## What changed (code)
- `native-21/stackup.json` is now tracked and is native-21's single layer-stack source (schema v2: the KiCad stackup
  plus `kicad_id` / `z_mm` on each copper layer, `plane_roles`, `kicad_stackup`). Until now it was an untracked copy of
  native-20's, written over on every build.
- `prototype-closure/pcb/build_native21.py` writes the board's copper `(layers)` entries, `(setup (stackup ...))` and
  `(general (thickness ...))` from that file (write_stack; KiCad reads the result back and the builder checks it). It no
  longer copies native-20's stackup.json.
- `native-21/layout/layers21.py` exports CU / OUTER / INNER / KICAD_ID / T_UM / T_MM / Z_MM / ADJ / PLANE_ROLE (stdlib only).
  `$NATIVE21_STACKUP` swaps in another file (e.g. the six-layer proposal) without a code change.
- Layout and gates use layers21: rules21 (OUTER), geom21 / maze21 (CU), route21, incr21, patches21 / patches21_v1 (layer
  sets and plane roles; the layer of each hand-laid track stays literal), plan_board_only21, plot_copper (grid follows the
  layer count), gates/return_path19 (ADJ from z, equal to its old hand table), xfer_spots, trim_tails, apply_copper21 and
  chain.sh's Gerber list. `tools/export_power_copper.py` reads each board's own copper stack, because it is shared with
  older boards.
- Models: `sheet_solver.stackup_layers(path)` (LAYER_Z_MM stays as the default for older callers). run_board.py and
  kelvin_plane.py pass z and thickness from the stackup. B3 thermal.py takes `--stackup` / `$B3_STACKUP`, defaulting to
  native-21's (it read native-17's, which has the same numbers). f1_containment CU_T, res_a_creepage18, summarize.py
  order and run_ocp's planes also come from layers21. coil-pickup loops.py keeps its z values as a documented override
  (see the open item below).
- Fail loudly: B3 grid_geometry (it dropped a whole unknown copper layer) and barrel_edges, and summarize.barrel_index
  (`order.get` returned None), now raise.
- Tests: `native-21/layout/test_layers21.py` (literals, bit-identical z, ADJ = return_path19's old table, roles match
  copper.json, sheet-solver loader, six-layer and malformed stacks) and
  `round5-native21/b3/test_layers.py` (old sheets, self-test, unknown layer raises, six-layer loads). Both PASS.
  sheet_solver --selftest PASS.

## Step 1: baseline (unmodified code, worktree ps-layers at 38e856ef3)
`sh native-21/layout/gates/chain.sh native21s31 $R/s30/p10/i2 $R/refactor/base` (the s31 invocation). Both caches were
cleared so task 04 and B3 recomputed. Then s21_necks.py s31, run_ocp.py on the base export, and scorecard.py.
- Chain summary: identical to s31/chain1.log line for line, except the board hash and the cache lines. The Rust gate
  census is 5734 items, against 5738: four fewer filled-zone polygons.
- Board: sha256 ccfdfebf… vs the accepted 5ef1c37a… KiCad draws fresh footprint UUIDs on every build and orders
  footprints by them, and its refill is not bit-reproducible (regate.sh says so). With the uuid lines and fills removed,
  the base, s31 and after boards all hash to `ae8fb3a9200c`. Gerber ZIP ca4dae8e… vs f24f40fd…: same members, different
  fills and draw order.
- OCP result: equal to result-s31.json. Necks: equal except board_sha256. Scorecard: equal to
  scorecard-native21s31.json except the build path.
- Detail differences (all from the refill): copper dump, evidence, all-copper and power-copper exports, every task-04
  case (barrel order follows the UUID order), B3 runs. Size: B3 peak at most 0.017 K; task-04 R at most 3.3e-4 relative.
- Nondeterministic fields, normalised in every comparison (refactor_compare.py): (uuid) lines and footprint order;
  board_sha256 and the hashes of files that embed it; dates (Gerber and drill CreationDate, "Created on"); run
  directory paths; git commit / dirty. return_path19 also records CPython `id()` of a track object as "track", which
  changes on every run. incr21 / return_path19 output order follows Python's hash seed (PYTHONHASHSEED=0 pins it).

## Step 3: neutrality
### A. Same board file, refactored code: every downstream gate and model
`sh refactor_same_input.sh $R/refactor/base $R/refactor/xin native21s31` re-runs every post-build chain step on the
base board: copper dump, barrier, D5, core regate (Rust barrier, DFM, bypass, all-copper and power-copper exports),
stage-18/19 gates, Kelvin, Gerbers and drill, task 04 (recomputed: its cache key hashes the changed scripts), B3 and
the ceiling sweep. Then necks, OCP and scorecard. Table: `python3 refactor_table.py base base-tracked base-extra xin <unit>`.
Provenance hashes changed only because the scripts themselves changed: script / kit / extractor / stackup sha256.

| artefact | before | after | equal? |
|---|---|---|---|
| board (section.kicad_pcb, uuid-normalised, fills included) | `fc9f1cf02b95` | `fc9f1cf02b95` | yes |
| copper-dump.json | `ff2210f95026` | `ff2210f95026` | yes |
| pads-board.json | `4b29954bf608` | `4b29954bf608` | yes |
| evidence.json | `766076af9d13` | `766076af9d13` | yes |
| barrier-gate-rust.json | `b7820c98c8ae` | `b7820c98c8ae` | yes |
| jlc-dfm.json | `77ead15704cc` | `77ead15704cc` | yes |
| bypass-check.json | `4f8a11e8d2ad` | `4f8a11e8d2ad` | yes |
| native21-all-copper.json.gz | `21373e486262` | `21373e486262` | yes |
| power_copper.json.gz | `84c6c08afa07` | `84c6c08afa07` | yes |
| res-a-creepage.json | `a95af8f039a8` | `a95af8f039a8` | yes |
| pi-distances.json | `519d457eebc0` | `519d457eebc0` | yes |
| return-path.json | `540363d45d16` | `540363d45d16` | yes |
| barrier.txt | `7f3334164c93` | `7f3334164c93` | yes |
| d5-audit.json | `973a46c0ac29` | `973a46c0ac29` | yes |
| Gerber ZIP (date lines removed) | `026d33ea23cb` | `026d33ea23cb` | yes |
| drill-report.txt | `342942dc6ff7` | `342942dc6ff7` | yes |
| kelvin plane-native21s31.json | `19a5974973e8` | `19a5974973e8` | yes |
| kelvin budget-native21s31.json | `7f04f3520378` | `7f04f3520378` | yes |
| task04 ac_l_main-p0125-pl18.json | `ad9b8a725152` | `ad9b8a725152` | yes |
| task04 ac_n_main-p0125-pl18.json | `fe2750e854e5` | `fe2750e854e5` | yes |
| task04 bus-dc-q2-p00625-pl18.json | `8b91bec42352` | `8b91bec42352` | yes |
| task04 bus-dc-q2-p025-pl18.json | `5eeec5163a68` | `5eeec5163a68` | yes |
| task04 bus_dc_q2-p0125-pl12.json | `a60193a3a6d6` | `a60193a3a6d6` | yes |
| task04 bus_dc_q2-p0125-pl18.json | `7b5431f4c211` | `7b5431f4c211` | yes |
| task04 bus_dc_q5-p0125-pl18.json | `6cec3da9fac1` | `6cec3da9fac1` | yes |
| task04 bus_hf_q2-p0125-pl18.json | `1d28cb7b714e` | `1d28cb7b714e` | yes |
| task04 bus_hf_q5-p0125-pl18.json | `3720c9afe1c4` | `3720c9afe1c4` | yes |
| task04 bus_mixed_q2-p0125-pl12.json | `72157575c918` | `72157575c918` | yes |
| task04 bus_mixed_q2-p0125-pl18.json | `667afe863abb` | `667afe863abb` | yes |
| task04 bus_mixed_q5-p0125-pl12.json | `22f47e633ffa` | `22f47e633ffa` | yes |
| task04 bus_mixed_q5-p0125-pl18.json | `b36aabfe9aa9` | `b36aabfe9aa9` | yes |
| task04 cases.json | `95768c90b225` | `95768c90b225` | yes |
| task04 coil_feed-p0125-pl12.json | `c7f426268451` | `c7f426268451` | yes |
| task04 coil_feed-p0125-pl18.json | `cc8d3a11e5e6` | `cc8d3a11e5e6` | yes |
| task04 compare_native17.json | `04cad3d89fe2` | `04cad3d89fe2` | yes |
| task04 hv_dc-p00625-pl12.json | `41cb726cab15` | `41cb726cab15` | yes |
| task04 hv_dc-p00625-pl18.json | `2f01fea883c9` | `2f01fea883c9` | yes |
| task04 hv_hf_a-p00625-pl18.json | `92bd40ac8843` | `92bd40ac8843` | yes |
| task04 hv_hf_b-p00625-pl18.json | `a7bd81cbc397` | `a7bd81cbc397` | yes |
| task04 hv_mixed_a-p00625-pl12.json | `865f04f06967` | `865f04f06967` | yes |
| task04 hv_mixed_a-p00625-pl18.json | `48b40adffc8d` | `48b40adffc8d` | yes |
| task04 hv_mixed_b-p00625-pl12.json | `815153b59c78` | `815153b59c78` | yes |
| task04 hv_mixed_b-p00625-pl18.json | `a5c8a2e7f6a1` | `a5c8a2e7f6a1` | yes |
| task04 kit_topology_p00625.json | `02b3be02ec6c` | `02b3be02ec6c` | yes |
| task04 kit_topology_p0125.json | `50e497f47883` | `50e497f47883` | yes |
| task04 leg_a_15-p00625-pl18.json | `1a1417401475` | `1a1417401475` | yes |
| task04 leg_a_18p7-p00625-pl12.json | `952f172f862c` | `952f172f862c` | yes |
| task04 leg_a_18p7-p00625-pl18.json | `feeda7263c5c` | `feeda7263c5c` | yes |
| task04 leg_a_19-p00625-pl18.json | `262f981485a5` | `262f981485a5` | yes |
| task04 leg_a_34-p00625-pl18.json | `2c23ace51c02` | `2c23ace51c02` | yes |
| task04 leg_b_18p7-p00625-pl12.json | `47677de5cab6` | `47677de5cab6` | yes |
| task04 leg_b_18p7-p00625-pl18.json | `57b42b058d0b` | `57b42b058d0b` | yes |
| task04 leg_b_34-p00625-pl18.json | `7f2e4d522865` | `7f2e4d522865` | yes |
| task04 res_a-p0125-pl12.json | `61913d6b9057` | `61913d6b9057` | yes |
| task04 res_a-p0125-pl18.json | `06c908aa22e5` | `06c908aa22e5` | yes |
| task04 summary.json | `638dc6d7b73d` | `638dc6d7b73d` | yes |
| task04 sw_a-p00625-pl12.json | `38641b3044ff` | `38641b3044ff` | yes |
| task04 sw_a-p00625-pl18.json | `228d8b6067a9` | `228d8b6067a9` | yes |
| task04 sw_a_low-p00625-pl12.json | `844bffff9eae` | `844bffff9eae` | yes |
| task04 sw_a_low-p00625-pl18.json | `494129317917` | `494129317917` | yes |
| task04 sw_b_high-p00625-pl12.json | `2e00e4585224` | `2e00e4585224` | yes |
| task04 sw_b_high-p00625-pl18.json | `2680946389ba` | `2680946389ba` | yes |
| task04 sw_b_low-p00625-pl12.json | `1b54e76618f5` | `1b54e76618f5` | yes |
| task04 sw_b_low-p00625-pl18.json | `2fce17aeba8a` | `2fce17aeba8a` | yes |
| task04 via_currents.json | `91b28c933196` | `91b28c933196` | yes |
| B3 c28_h10_p0p5.json | `a33aeb53d0a8` | `a33aeb53d0a8` | yes |
| B3 c28_h10_p1p0.json | `a0078fdcd32f` | `a0078fdcd32f` | yes |
| B3 c28_h25_p0p5.json | `335e0385c881` | `335e0385c881` | yes |
| B3 c28_h25_p1p0.json | `ba92618b702d` | `ba92618b702d` | yes |
| B3 ceiling_sweep.json | `f4cb986904f8` | `f4cb986904f8` | yes |
| B3 extreme_h10_p0p5.json | `a821d6295651` | `a821d6295651` | yes |
| B3 extreme_h10_p1p0.json | `3575ff0b6507` | `3575ff0b6507` | yes |
| B3 extreme_h25_p0p5.json | `d16477d628d8` | `d16477d628d8` | yes |
| B3 extreme_h25_p1p0.json | `d348c45a46b1` | `d348c45a46b1` | yes |
| B3 nominal_h10_p0p5.json | `9d73fab3939b` | `9d73fab3939b` | yes |
| B3 nominal_h10_p1p0.json | `7f7d04f56529` | `7f7d04f56529` | yes |
| B3 nominal_h25_p0p5.json | `f40d1471ecc1` | `f40d1471ecc1` | yes |
| B3 nominal_h25_p1p0.json | `c01316afd88c` | `c01316afd88c` | yes |
| B3 summary.json | `9b59bb0e357f` | `9b59bb0e357f` | yes |
| B3 sweep_c22_h25_p1p0.json | `8a85c89a8537` | `8a85c89a8537` | yes |
| B3 sweep_c24_h25_p1p0.json | `f544097743ae` | `f544097743ae` | yes |
| B3 sweep_c26_h25_p1p0.json | `68025c5aac83` | `68025c5aac83` | yes |
| B3 sweep_c28_h25_p1p0.json | `ba92618b702d` | `ba92618b702d` | yes |
| necks s31_necks.json | `025b19f027e2` | `025b19f027e2` | yes |
| OCP pickup result.json | `083ff75336fe` | `083ff75336fe` | yes |
| scorecard.json | `fab8d0e364d1` | `fab8d0e364d1` | yes |

86 artefacts, 0 different

`scorecard.py --card base-extra/scorecard.json --compare xin/scorecard.json`: "cheaper [], better []", no metric changed
(the JSONs are equal above). The same holds against the committed scorecard-native21s31.json.

### B. Fresh rebuild with the refactored code (full chain)
`chain.sh native21s31 $R/s30/p10/i2 $R/refactor/after` with both caches cleared: CHAIN_DONE.
- Builder alone (place.py + build_native21.py, before copper): uuid-normalised hash `7aeeb8753200` before and after.
  The stackup is now written from native-21/stackup.json; the .kicad_pro is byte-equal.
- Final board: sha256 7a456bee… The uuid- and fill-normalised hash is `ae8fb3a9200c`, the same as base and s31.
  pads-board.json and board_only21.json (test-point plan) are equal.
- Chain summary: identical to the base chain's, line for line, apart from the board hash. The gate lines, D5, FIT,
  RUST, DFM, creepage, bypass, Kelvin (R_eff 152.8225 mOhm, trip shift -2.123 A), task 04 (39 scenarios, 0 failed,
  bus_p span 2.9185 %), B3 peaks (162.1 / 129.0 / 247.1 / 192.6 / 135.2 C), the ceiling sweep, BOM / CPL and fab
  counts all match.
- Equal against base: barrier, Rust gate, DFM, bypass, creepage, PI distances, D5, drill report, Kelvin plane and
  budget, task-04 case list, necks, OCP (also equal to result-s31.json) and scorecard (also equal to
  scorecard-native21s31.json, compare: no change).
- 70 fill-bearing artefacts differ by refill noise of the same size as base vs s31: B3 peak at most 0.017 K, task-04 R
  at most 3.0e-4 relative. The Gerber ZIP is 55459a40… (fills).

### C. Layout scripts the chain does not run (incr21 / patches21 / route21 / plan_board_only21 / gates)
`sh refactor_layout_runs.sh OUT $R/s30/p10/i2 $R/s30/p10/i1`, run once with the 38e856ef3 files and once with the
refactored ones. It runs incr21 (copper_base + patches21 + the s30 p10 DRC pairs), route21 from scratch,
plan_board_only21, trim_tails, test_trim_tails, zone_priority_gate, xfer_spots and return_path19.
- incr21.json `1cf6de35b21a` / `1cf6de35b21a`; board_only21.json `cd7f1c5d3fab` / `cd7f1c5d3fab`. Every log and
  return-path.json is equal.
- route21.log differs only in traceback line numbers. From scratch, route21 stops on today's placement: J7-J10 are
  skipped in-memory, then it stops at U35, removed in stage 14. Its authored copper up to there is equal. Its later
  plane / fan-out lines (now PLANE_ROLE lookups) are covered by test_layers21: every role equals the old literal.

### Six-layer readiness (smoke tests only)
- A synthetic 6-layer stackup.json builds: KiCad reads back F, In1-In4, B with ids 0/4/6/8/10/2.
- c33's stackup-6L-proposed.json loads through `NATIVE21_STACKUP`, but it has no plane_roles yet.

## Open items (not changed: owner decisions)
- **coil-pickup loops.py z** (depth below F.Cu): In1 0.47, In2 1.03, B 1.50 mm. The stackup gives 0.501 / 1.062 /
  1.563 mm. The old values stay as `Z_DEPTH_OVERRIDE_MM` so result-s31.json reproduces; `F8_Z=stackup` uses the
  stackup instead.
- sheet_solver's via barrel length is a fixed 1.6 mm (`length_mm` default). The stack's copper span is 1.563 mm
  centre to centre, or 1.633 mm overall. Left as is.
- kelvin_plane.py records `thickness_um` as {outer, inner}. It raises if a stack mixes inner thicknesses.
- tools/jlc_dfm_check.py's size limit (663 x 593 mm) is the 4-layer figure.
- Docs still say "4 layers" / JLC041622-7628 (FAB-JLCPCB.md, FAB-NOTE.md, ORDER-PACKAGE.md, FLOORPLAN.md). That is
  correct for this board.
- kit_topology_native13.py (round 3, shared) builds Net() with the kit's default z. That is equal on this stack; it is
  not wired to the stackup.

## Re-proof on s32 (branch rebased onto d35219516: stage 32 + records)
The rebase was clean. Stage 32 added one more whole-stack tuple, in patches21.add_stage32_in2 (`unregister(... CU ...)`);
it now uses CU. Its In2 hops are authored geometry and stay literal. test_layers21 and b3/test_layers PASS on s32's
copper.json.

**Baseline** (d35219516 checked out, unmodified): `chain.sh native21s32 $R/s32/p3/i2 $R/refactor/s32-base`, caches
cleared.
- Board 277ff2f5… vs the accepted 2fb346dc…. Uuid- and fill-normalised, both are `4abd302e7d21`.
- Chain summary: equal to s32/chain2.log with three exceptions. The accepted run's settle-loop trims are absent: they
  were committed with copper.json. The Rust census is 5753 vs 5749 (refill). The CPL-audit counts changed because of
  b10228f62.
- OCP equals result-s32.json; necks equal s32_necks.json except board_sha256; scorecard equals
  scorecard-native21s32.json except the build path.

**A. Same board file, refactored code**: `refactor_same_input.sh $R/refactor/s32-base $R/refactor/s32-xin native21s32`.
Result: **86 of 86 artefacts equal** (`$R/refactor/s32-xin-table.md`). This covers the copper dump, all gates, the
all-copper and power-copper exports, the Gerber ZIP, Kelvin, all 39 task-04 cases and summaries recomputed, every B3
run and the ceiling sweep, necks, OCP and scorecard.

**B. Fresh rebuild, refactored code**: `chain.sh native21s32 $R/s32/p3/i2 $R/refactor/s32-after`, CHAIN_DONE.
- Builder output `7aeeb8753200` before and after. Final board 906392c2…, uuid- and fill-normalised `4abd302e7d21`.
- The chain summary is identical to the s32 baseline except the refill census: 5749, the accepted run's figure.
- Equal to the accepted s32 artefacts: OCP (result-s32.json), necks (s32_necks.json) and scorecard
  (scorecard-native21s32.json, compare: no change).
- Equal to the baseline: pads, test-point plan, DFM, bypass, PI distances, drill report, Kelvin plane and budget.
- 70 fill-bearing artefacts differ by refill noise: B3 peak at most 0.018 K, task-04 R at most 3.3e-4 relative. These
  are the same sizes as two runs of the unmodified chain.

**C. Layout scripts** (`refactor_layout_runs.sh OUT $R/s32/p3/i2 $R/s32/p3/i1`, d35219516 files vs refactored):
incr21.json (with stage 32's std_vias and add_stage32_in2), board_only21.json, every log and return-path.json are
equal. route21.log differs in traceback line numbers only.

## Rerun notes
Order: baseline on the old code (checkout, place.py + build_native21.py, `chain.sh` with caches cleared, then necks,
OCP and scorecard; snapshot the tracked outputs with rsync), then `refactor_layout_runs.sh` on the old code. Then, on
the refactored branch: layout runs, `refactor_same_input.sh` (pin the tag's Kelvin hash to the baseline board first),
`refactor_table.py`, and the full chain. Finally restore the chain-written tracked files and the Kelvin pin before
committing.

### Appendix: s32 same-input table (A)

| artefact | before | after | equal? |
|---|---|---|---|
| board (section.kicad_pcb, uuid-normalised, fills included) | `83e3b38c4696` | `83e3b38c4696` | yes |
| copper-dump.json | `9e39782d09b8` | `9e39782d09b8` | yes |
| pads-board.json | `15eb01b0bdea` | `15eb01b0bdea` | yes |
| evidence.json | `afd0ac49e4b5` | `afd0ac49e4b5` | yes |
| barrier-gate-rust.json | `a640b50fca15` | `a640b50fca15` | yes |
| jlc-dfm.json | `51cef01b2600` | `51cef01b2600` | yes |
| bypass-check.json | `8798d465075a` | `8798d465075a` | yes |
| native21-all-copper.json.gz | `6c1f2227bfa3` | `6c1f2227bfa3` | yes |
| power_copper.json.gz | `87d060935d8e` | `87d060935d8e` | yes |
| res-a-creepage.json | `9d6d10e3ca42` | `9d6d10e3ca42` | yes |
| pi-distances.json | `519d457eebc0` | `519d457eebc0` | yes |
| return-path.json | `49b910dbbd41` | `49b910dbbd41` | yes |
| barrier.txt | `7f3334164c93` | `7f3334164c93` | yes |
| d5-audit.json | `fbe8bceb8d98` | `fbe8bceb8d98` | yes |
| Gerber ZIP (date lines removed) | `a804b4c07a7f` | `a804b4c07a7f` | yes |
| drill-report.txt | `342942dc6ff7` | `342942dc6ff7` | yes |
| kelvin plane-native21s32.json | `5336f693e9f8` | `5336f693e9f8` | yes |
| kelvin budget-native21s32.json | `cd7c8863e80e` | `cd7c8863e80e` | yes |
| task04 ac_l_main-p0125-pl18.json | `8a99395d4651` | `8a99395d4651` | yes |
| task04 ac_n_main-p0125-pl18.json | `8e9230910d38` | `8e9230910d38` | yes |
| task04 bus-dc-q2-p00625-pl18.json | `32217a613a9b` | `32217a613a9b` | yes |
| task04 bus-dc-q2-p025-pl18.json | `75ded339d0f7` | `75ded339d0f7` | yes |
| task04 bus_dc_q2-p0125-pl12.json | `f11871776b8f` | `f11871776b8f` | yes |
| task04 bus_dc_q2-p0125-pl18.json | `031338258938` | `031338258938` | yes |
| task04 bus_dc_q5-p0125-pl18.json | `1c5bda4714c5` | `1c5bda4714c5` | yes |
| task04 bus_hf_q2-p0125-pl18.json | `fd61a9ba3f1f` | `fd61a9ba3f1f` | yes |
| task04 bus_hf_q5-p0125-pl18.json | `31fea869fb19` | `31fea869fb19` | yes |
| task04 bus_mixed_q2-p0125-pl12.json | `e6ab0669d5bb` | `e6ab0669d5bb` | yes |
| task04 bus_mixed_q2-p0125-pl18.json | `4d797242b9ec` | `4d797242b9ec` | yes |
| task04 bus_mixed_q5-p0125-pl12.json | `d467e5b433e9` | `d467e5b433e9` | yes |
| task04 bus_mixed_q5-p0125-pl18.json | `9a213ae56886` | `9a213ae56886` | yes |
| task04 cases.json | `95768c90b225` | `95768c90b225` | yes |
| task04 coil_feed-p0125-pl12.json | `b28cc967e8fc` | `b28cc967e8fc` | yes |
| task04 coil_feed-p0125-pl18.json | `da626e31657e` | `da626e31657e` | yes |
| task04 compare_native17.json | `d8e5871ab248` | `d8e5871ab248` | yes |
| task04 hv_dc-p00625-pl12.json | `9a0549dface1` | `9a0549dface1` | yes |
| task04 hv_dc-p00625-pl18.json | `a362f21c05b0` | `a362f21c05b0` | yes |
| task04 hv_hf_a-p00625-pl18.json | `2a65e17976d8` | `2a65e17976d8` | yes |
| task04 hv_hf_b-p00625-pl18.json | `d169d46fa104` | `d169d46fa104` | yes |
| task04 hv_mixed_a-p00625-pl12.json | `6daf812f417c` | `6daf812f417c` | yes |
| task04 hv_mixed_a-p00625-pl18.json | `d51e5bdacbc0` | `d51e5bdacbc0` | yes |
| task04 hv_mixed_b-p00625-pl12.json | `e6c26981ece6` | `e6c26981ece6` | yes |
| task04 hv_mixed_b-p00625-pl18.json | `599fadbfdf9d` | `599fadbfdf9d` | yes |
| task04 kit_topology_p00625.json | `11753a976459` | `11753a976459` | yes |
| task04 kit_topology_p0125.json | `61cd2567dc54` | `61cd2567dc54` | yes |
| task04 leg_a_15-p00625-pl18.json | `c4dc549e08ff` | `c4dc549e08ff` | yes |
| task04 leg_a_18p7-p00625-pl12.json | `2e3b220f902b` | `2e3b220f902b` | yes |
| task04 leg_a_18p7-p00625-pl18.json | `dee11feb5d10` | `dee11feb5d10` | yes |
| task04 leg_a_19-p00625-pl18.json | `f0518312e165` | `f0518312e165` | yes |
| task04 leg_a_34-p00625-pl18.json | `51173750cbf9` | `51173750cbf9` | yes |
| task04 leg_b_18p7-p00625-pl12.json | `2a076afb97e5` | `2a076afb97e5` | yes |
| task04 leg_b_18p7-p00625-pl18.json | `757d68d8afdd` | `757d68d8afdd` | yes |
| task04 leg_b_34-p00625-pl18.json | `124756bb2b1f` | `124756bb2b1f` | yes |
| task04 res_a-p0125-pl12.json | `4f352d765b48` | `4f352d765b48` | yes |
| task04 res_a-p0125-pl18.json | `bb0e0aa2ec0a` | `bb0e0aa2ec0a` | yes |
| task04 summary.json | `d2091a681327` | `d2091a681327` | yes |
| task04 sw_a-p00625-pl12.json | `4cb194a0156f` | `4cb194a0156f` | yes |
| task04 sw_a-p00625-pl18.json | `19a61d1f35c9` | `19a61d1f35c9` | yes |
| task04 sw_a_low-p00625-pl12.json | `7aa8db49c934` | `7aa8db49c934` | yes |
| task04 sw_a_low-p00625-pl18.json | `ba40250bb86b` | `ba40250bb86b` | yes |
| task04 sw_b_high-p00625-pl12.json | `23064948ce00` | `23064948ce00` | yes |
| task04 sw_b_high-p00625-pl18.json | `7908486332dd` | `7908486332dd` | yes |
| task04 sw_b_low-p00625-pl12.json | `68b508b1fa80` | `68b508b1fa80` | yes |
| task04 sw_b_low-p00625-pl18.json | `f74be81eea0a` | `f74be81eea0a` | yes |
| task04 via_currents.json | `2d3b23df823f` | `2d3b23df823f` | yes |
| B3 c28_h10_p0p5.json | `10d525c90777` | `10d525c90777` | yes |
| B3 c28_h10_p1p0.json | `3d76b507c6d2` | `3d76b507c6d2` | yes |
| B3 c28_h25_p0p5.json | `6f96fc9c9480` | `6f96fc9c9480` | yes |
| B3 c28_h25_p1p0.json | `6bbfebe838ae` | `6bbfebe838ae` | yes |
| B3 ceiling_sweep.json | `b9100343eb9c` | `b9100343eb9c` | yes |
| B3 extreme_h10_p0p5.json | `2b108c83a65b` | `2b108c83a65b` | yes |
| B3 extreme_h10_p1p0.json | `c522f7e93f7e` | `c522f7e93f7e` | yes |
| B3 extreme_h25_p0p5.json | `9883c2e0480f` | `9883c2e0480f` | yes |
| B3 extreme_h25_p1p0.json | `7c3b5e918477` | `7c3b5e918477` | yes |
| B3 nominal_h10_p0p5.json | `00155c5939f9` | `00155c5939f9` | yes |
| B3 nominal_h10_p1p0.json | `bbc16b3f1a14` | `bbc16b3f1a14` | yes |
| B3 nominal_h25_p0p5.json | `edec0683ee25` | `edec0683ee25` | yes |
| B3 nominal_h25_p1p0.json | `8a7700b29824` | `8a7700b29824` | yes |
| B3 summary.json | `efc90e895f00` | `efc90e895f00` | yes |
| B3 sweep_c22_h25_p1p0.json | `893e76ed327c` | `893e76ed327c` | yes |
| B3 sweep_c24_h25_p1p0.json | `afe2b51a0c24` | `afe2b51a0c24` | yes |
| B3 sweep_c26_h25_p1p0.json | `c13a8d2d9036` | `c13a8d2d9036` | yes |
| B3 sweep_c28_h25_p1p0.json | `6bbfebe838ae` | `6bbfebe838ae` | yes |
| necks s32_necks.json | `102c73cd5af1` | `102c73cd5af1` | yes |
| OCP pickup result.json | `083ff75336fe` | `083ff75336fe` | yes |
| scorecard.json | `5de74c3683d0` | `5de74c3683d0` | yes |

86 artefacts, 0 different
