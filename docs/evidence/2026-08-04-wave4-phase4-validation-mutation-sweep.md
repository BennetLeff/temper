# Wave 4 Phase 4 — validation DRC-check slice: anti-vacuity mutation sweep — 2026-08-04

<!-- provenance: commit=2893a88fe dirty=true -->

**Base commit:** `2893a88fe` (the TDD-RED commit) + uncommitted working-tree
changes (the `temper_drc_rs` validation kernels and the Python delegation
shims). `dirty=true` because this document is committed together with the
migration it verifies.

## Why this sweep exists

The R1 gate set requires anti-vacuity evidence for every migration: mutate
the Rust, confirm the differential **fails**, revert, and record every
mutation and what caught it. A differential never shown to fail is not
evidence. Landed migrations ran 6–11 mutants; two found surviving mutants
that were closed by adding discriminating cases.

The previous attempt at this migration (which died mid-stream) had not run
any mutations — no record exists in the RED commit or the working tree. This
sweep is that missing evidence, run after the delegation shims were
completed.

## Method

For each mutant: apply a single behavior-changing edit to
`packages/temper-drc-rs/src/validation.rs`, rebuild the extension
(`uv run --no-sync maturin develop --release`), run the differential/PBT
suite for the affected module(s), record the result, restore the file from
backup, and rebuild. The differentials compare the Rust kernels bit-exactly
against the verbatim pinned oracles (floats via `float.hex()`, typed
comparison keys for non-float leaves).

## Results — 12 mutants, all caught

| # | Kernel mutated | Mutation | Suite | Result |
|---|---|---|---|---|
| M1 | `infer_package_type` | dropped `"dip"` from the THT keyword list | drc_oracle | **1 failed** (deterministic `DIP-8 → tht` case) |
| M2 | `tht_hole_collisions` | message precision `:.3` → `:.2` | tht_check | **6 failed** (message-format comparisons) |
| M3 | `tht_hole_collisions` | dropped `+ min_clearance` from required distance | tht_check | **8 failed** |
| M4 | `trace_length` | net filter `==` → `!=` | trace_analyzer | **4 failed** |
| M5 | `min_hv_lv_trace_clearance` | `min` → `max` in the endpoint-pair fold | trace_analyzer | **4 failed** |
| M6 | `geometric_validate` | overlap severity threshold `> 5.0` → `> 50.0` | geometric | **4 failed** (CRITICAL-classification case) |
| M7 | `geometric_validate` | boundary flag predicate `> 0.0` → `> 1e9` (never flags) | geometric | **3 failed** |
| M8 | `parse_drc_violation` | default severity `"warning"` → `"error"` | drc | **2 failed** |
| M9 | `compute_drc_penalty` | default weight `1.0` → `0.0` | drc | **3 failed** |
| M10 | `group_violations` | removed the group-name sort | drc_oracle | **3 failed** (sorted-order assertions) |
| M11 | `issue_fingerprint` | item separator `,` → `;` | drc_fence | **6 failed** |
| M12 | `metrics_summary` | `"erc"` category arm increments `drc` instead | drc_fence | **3 failed** |

**No surviving mutants.** Every mutation was caught by at least one
differential assertion; no discriminating-case additions were required (unlike
the priority/net-types campaigns, where survivors had to be closed).

## Notes

- Two of the failing tests caught during completion of the migration were
  **test bugs, not kernel bugs** — the kernel matched the verbatim oracle
  bit-exactly on the exact failing inputs (verified directly against
  `_ref_compute_penalty` / `_ref_violations_to_run_result` before touching
  the tests):
  1. `test_mr2_penalty_doubled_weights_double_result` claimed doubling
     *both* weight dicts doubles the penalty; for known keys it quadruples
     ((2s)(2t) = 4st) and unknown keys keep the undoubled 1.0 default. Fixed
     to double one dict and to bound to known keys.
  2. `test_prop5_penalty_matches_independent_recompute` used CPython's
     Neumaier-compensated `sum()` as its "independent" arm, which
     legitimately disagrees with the oracle's `+=` at the last bit. Fixed to
     re-implement the oracle's `+=` strategy exactly (the guide's
     "summation strategy" trap).
  3. `test_drc_oracle_rust_differential.py::test_group_violations_differential_deterministic`
     passed `severity` twice (positional + keyword) to `_violation_dict`.
     Fixed to the intended unknown-severity value.
- The mutation sweep also independently re-verified the two platform-pinned
  arithmetic claims in `validation.rs`: the mounting-hole `** 0.5` libm-pow
  distinction (274/200000 measured mismatches vs `sqrt`) and the
  fixed-point `:.3` formatting parity.
