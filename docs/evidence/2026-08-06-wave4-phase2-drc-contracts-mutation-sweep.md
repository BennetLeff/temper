# Wave 4 Phase 2 — drc_types/drc_result contracts: anti-vacuity mutation sweep — 2026-08-06

<!-- provenance: commit=UNKNOWN dirty=UNKNOWN -- neither the originally recorded abbreviated token (9995e8323) nor the Base commit named below (b7af1384b) resolves to any commit object in this repository (both dangling, orphaned by rebase/squash), and no persisting equivalent could be identified without guessing; count + pristine verification re-run 2026-08-06 on the completion commit (11/11 killed, pristine 52/52); driver /tmp/wt7-drc-mutants.py. See .evidence-provenance-allowlist. -->

**Base commit:** `b7af1384b` (TDD-RED) + the GREEN working-tree state this PR
commits (`packages/temper-drc-rs/src/drc_contracts.rs`,
`drc_types.py`/`drc_result.py` delegation shims,
`test_drc_contracts_rust_differential.py`). `dirty=true` because this
document is committed together with the migration it verifies.

**Incident note.** The original dispatch for this slice died on a provider
error AFTER committing the RED evidence (`b7af1384b`) and leaving
uncommitted WIP: `drc_contracts.rs` (17 pyclasses), `lib.rs` registration,
the `drc_types.py` shim, and a half-refactored differential test. The
`drc_result.py` half of the scope had NOT been started (it was still the
verbatim Python dataclass module). This session resumed from the RED commit,
verified the WIP (built the extension, ran the 52-test differential green),
finished the migration (`drc_result.py` → delegation shim), and ran this
sweep on the completed source.

## Why this sweep exists

The R1 gate set requires anti-vacuity evidence for every migration: mutate
the Rust, confirm the differential **fails**, revert, and record every
mutation and what caught it. A differential never shown to fail is not
evidence. The sweep follows the same protocol as the Phase-4 slices
(`docs/evidence/2026-08-04-wave4-phase4-validation-mutation-sweep.md`,
`2026-08-05-wave4-phase4-regression-mutation-sweep.md`): 6–11 mutants, every
one caught, no infra failure counted as a kill, pristine rebuild at the end.

## Method

For each mutant: apply a single behavior-changing edit to
`packages/temper-drc-rs/src/drc_contracts.rs`, rebuild the extension
(`cargo build --release -p temper-drc-rs` into the shared
`CARGO_TARGET_DIR`, then copy the built dylib over the installed
`temper_drc_rs.cpython-312-darwin.so` — cargo build + .so swap is the same
artifact `maturin develop` installs, at ~6s instead of ~60s per mutant),
run the full differential suite
(`tests/validation/test_drc_contracts_rust_differential.py`, 52 tests) from
`packages/temper-placer`, and record the result. A mutant is counted
**caught** only when the suite genuinely failed (pytest exit 1); a
rebuild/infra failure (`BUILD_FAILED`, `ANCHOR_FAIL`) is recorded as such
and never counted as a kill. Every mutant was reverted immediately after its
test run, and the campaign ended with a **PRISTINE rebuild** of the
extension from the final clean source (the `#766`/`#762` lesson — per-mutant
revert alone leaves the last mutant's `.so` installed). The driver is
`/tmp/wt7-drc-mutants.py` (outside the repo; a repo script would trigger the
script-manifest gate).

## Results — 11 mutants, all caught, no survivors

| # | Region | Mutation | Caught by |
|---|---|---|---|
| M1 | `Severity` weight table | WARNING weight `1.0` → `2.0` | `test_prop1_severity_weight_table`, `test_severity_surface_identical`, penalty PBTs (5 tests) |
| M2 | `CheckResult.info_count` | counts `ERROR` instead of `INFO` | `test_consumer_to_dict_and_json_identical` (counts block) |
| M3 | `RunResult.passed` | empty run no longer fails closed (vacuous `all([])` → `True`) | `test_prop2_run_result_passed_fail_closed`, `test_consumer_runresult_summary_access_patterns` |
| M4 | `CheckResult.merge` | later-metrics-wins merge dropped (`{**a}` instead of `{**a, **b}`) | `test_mr1_merge_is_order_preserving_concatenation` (`metrics == {"x": 2}`) |
| M5 | `Location.__repr__` | `layer` field omitted from the dataclass repr | `test_construction_field_repr_str_identical`, `test_collection_*` corpus repr pins |
| M6 | `Issue.__str__` | `affected_items` truncated at 2 instead of 3 | `test_consumer_location_issue_str_identical` (`A, B, C (+1 more)`) |
| M7 | `ComponentPlacement.bounds` | x_min sign flip (`x - hw` → `x + hw`) | `test_consumer_geometry_accessors_identical` (bounds canon) |
| M8 | `ConstraintSet.get_clearance` | rule matching disabled (always `0.0`) | `test_consumer_constraint_set_methods` (`get_clearance("HV","LV") == 6.0`) |
| M9 | `Placement.from_dict` | `rotation` default `0.0` → `90.0` | `test_consumer_from_dict_to_dict_roundtrip_identical` (canon) |
| M10 | `CheckResult.penalty` | accumulates `2*w` instead of `w` | `test_prop3_error_count_is_recomputed`, `test_prop4_penalty_is_severity_weighted_sum` (5 tests) |
| M11 | `Severity.members()` | member order swapped (`CRITICAL, INFO, WARNING, ERROR`) | `test_severity_surface_identical` (the direct `members()` ↔ oracle `list(Severity)` parity pin) |

**Pristine rebuild:** after the last mutant, the source was restored from
the pre-sweep backup and the extension rebuilt; the differential suite
reported **52 passed / 0 failed** against the pristine `.so`. The working
tree is byte-identical to the pre-sweep WIP state (verified by re-running
the 52-test suite and the `make extensions-check` freshness gate).

M11 targets the `Severity.members()` class-level-enumeration surface added
mid-sweep (the pyo3 substitute for the Enum's `list(Severity)` — no
metaclass hook, so the consumer `tests/report/test_report_pbt.py` was
adapted to `Severity.members()`; see VERIFICATION.md's narrowing record).
The differential's direct parity pin makes that region non-vacuous.

## Deviations from the Phase-4 sweep protocol

- Rebuild was `cargo build` + `.so` copy rather than `maturin develop` (see
  Method). The final `make extensions` in the PR re-installs every crate
  through maturin, so the shipped artifact is the maturin build.
- No `APPLY_FAILED`/`BUILD_FAILED` entries — the 11 mutants all built and
  were all caught. (`M5`'s first anchor was non-unique and re-anchored with
  class-specific context before the run; the recorded run has 11 clean
  kills. The `Severity.members()` surface was added mid-sweep, so M11 was
  run as an 11th mutant on the completed source.)
