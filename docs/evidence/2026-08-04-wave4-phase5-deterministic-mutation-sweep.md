# Wave 4 Phase 5 — deterministic leaf stages slice: anti-vacuity mutation sweep — 2026-08-04

<!-- provenance: commit=9b4a672d6755423e74b56593409afa33302f1829 dirty=true -->

**Base commit:** `9b4a672d6` (the TDD-RED commit for
slot_generation/zone_geometry/zone_assignment) + uncommitted working-tree
changes (the `temper-design-bundle` kernels in `deterministic_stages.rs`
and the Python delegation shims). `dirty=true` because this document is
committed together with the migration it verifies.

## Why this sweep exists

The R1 gate set requires anti-vacuity evidence for every migration: mutate
the Rust, confirm the differential **fails**, revert, and record every
mutation and what caught it. A differential never shown to fail is not
evidence.

This sweep is a **re-run**: the original Batch-2 campaign run was lost when
the worktree directory was deleted mid-session by an external cleanup, and
a zombie copy of the campaign driver (orphaned from the failed resume
attempt) was found cycling mutants on the recreated worktree's source file
concurrently with verification. The zombie was killed and the source
restored from the pinned oracles; the sweep below is the clean, complete
run (driver `scripts/phase5_batch2_mutations.py`, output captured to
`/tmp/wt5_campaign_clean2.txt`).

## Method

For each mutant: apply a single behavior-changing edit to
`packages/temper-design-bundle/src/deterministic_stages.rs`, rebuild the
extension (`uv run --no-sync maturin develop --release`), run the six
Batch-2 suites (3 differential + 3 PBT), expect a failure, then revert in a
`finally` block. The differentials compare the Rust kernels bit-exactly
against the verbatim pinned oracles (floats via `float.hex()`, type-carrying
`canon` keys, empty-input semantics, dict-insertion order).

## Results — 12 mutants, all caught

| # | Kernel mutated | Mutation | What caught it | Result |
|---|---|---|---|---|
| M1 | `generate_slots` | outer bound `<=` for `<` | `test_slots_strict_upper_bound` (x at 11 not emitted) | **fail** |
| M2 | `generate_slots` | inner bound `<=` for `<` | `test_slots_strict_upper_bound` (y at 11 not emitted) | **fail** |
| M3 | `generate_slots` | anchor `min + spacing` for `min + spacing/2` | `test_slots_basic_grid` first-slot (1.0 vs 2.0) | **fail** |
| M4 | `generate_slots` | inner anchor `min` for `min + spacing/2` | `test_slots_float_accumulation` (0.0 vs 0.05) | **fail** |
| M5 | `layout_boundaries` | Power boundary `0.7` for `0.6` | `test_layout_boundaries` (60.0 not 70.0) | **fail** |
| M6 | `layout_boundaries` | Signal boundary `0.8` for `0.9` | `test_layout_boundaries` (90.0 not 80.0) | **fail** |
| M7 | `scale_bounds` | y scaled by width not height | `test_scale_zone_bounds_dict_branch` (ratio[1]*h) | **fail** |
| M8 | `scale_bounds` | x2/y2 swapped | `test_scale_zone_bounds_dict_branch` | **fail** |
| M9 | `infer_zone` | `U_MCU` prefix without underscore | `test_mcu_prefix_and_protocol_nets` (U_MCU1) | **fail** |
| M10 | `infer_zone` | UART dropped from protocol scan | `test_mcu_prefix_and_protocol_nets` (uart_tx) | **fail** |
| M11 | `infer_zone` | net-class spelling `HighVoltageX` | `test_hv_net_class` | **fail** |
| M12 | `infer_zone` | Power rule before HV rule | `test_component_on_multiple_nets` (rule 3 beats 4) | **fail** |

**No surviving mutants.** Every mutation was caught by at least one
differential/PBT assertion; no discriminating-case additions were required
(the strict-bound and rule-priority cases written at RED time already
killed M1/M2/M12; the M1/M2 strict-bound cases were extended with
lattice-lands-exactly-on-boundary inputs during GREEN to make the kill
unambiguous).

## Notes

- The first clean run of the campaign aborted at M5 with `anchor not
  found`: the zombie campaign had left M5's mutation (`0.7`) applied in the
  source when it was killed. The source was restored from the pinned
  oracle and the sweep re-run to completion.
- The 43 Batch-2 assertions/examples re-passed after the sweep (exit 0,
  suites green), confirming the revert cycle restored the bit-exact state.
- RED re-verification (R1f): with the `deterministic_stages` submodule
  absent (simulated by deleting the module attribute before collection,
  identical to the pre-migration build), all six suites fail to collect
  with `AttributeError` — exit 2, not vacuously green.
