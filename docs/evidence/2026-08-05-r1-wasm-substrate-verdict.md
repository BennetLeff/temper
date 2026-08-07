<!-- provenance: commit=00ec5f94a535ff86b4042748f7b036c139b3cac2 dirty=false -->

# R1 WASM Substrate — Verdict-in-progress

**Date:** 2026-08-07
**Base:** `origin/main` @ `f8982e155700f8c224ad1d4944f1905bf94e92fa`
**Branch:** `wasm/u1-rung23-closing`
**Units:** U1 rungs 2–3 of `docs/plans/2026-08-05-001-feat-wasm-tier-phase0-plan.md`
**Scope:** build a linked `.wasm` artifact (rung 2), execute under wasmtime and
compare with native (rung 3). One rule from each of the six rule families.
**Base assertion:** `scripts/assert-base.sh origin/main` exited 0.

This document records U1's contribution to the R1 verdict (conditions 1–3 of
plan §2). Condition 4 (portable surface, all six families reachable) was
recorded by U2 on branch `origin/wasm/u2-portable-surface` — see its
`docs/evidence/2026-08-05-r1-wasm-substrate-verdict.md` §4 and §6.

---

## 1. Rung 2 — linked artifact

### Build command

```bash
cd packages/temper-wasm-test-runner
export CARGO_TARGET_DIR=/Users/bennet/Desktop/temper/target-shared
cargo build --release --target wasm32-unknown-unknown
```

### Required source change

One source change was required to make the wasm32 build link:

**`packages/temper-drc-rs/Cargo.toml`**:
- `temper-geometry` was an unconditional dependency with default features
  (`python`), which transitively enabled `pyo3` (with `extension-module`).
  `pyo3`'s build script rejects `wasm32-unknown-unknown` cross-compilation
  unless `PYO3_CROSS_LIB_DIR` or an `abi3` feature is set.
- Changed to `optional = true` and added `"dep:temper-geometry"` to the
  `python` feature. The only consumer of `temper-geometry` in this crate is
  `deterministic_connectivity.rs`, which is gated on
  `#[cfg(feature = "python")]`. The change is semantically correct: the
  dependency should only be active when the module that uses it is compiled.
- `cargo check` with default features (python) still passes; `cargo test
  --no-default-features` still passes (95 tests, same as before).

This is the feature-unification issue anticipated by the plan (§5 item 3,
issue #872). It is classified as **incidental** — a `cfg` that was never
added — and the fix is the one-line `optional = true` + feature entry.

### Artifact

| Property | Value |
|---|---|
| Path | `target-shared/wasm32-unknown-unknown/release/temper_wasm_test_runner.wasm` |
| Size | 1,183,886 bytes (~1.13 MiB) |
| sha256 | `5173726ea34802753854603787fe58266666391621d11ea7c8d7090efba648fe` |
| Build tool | `cargo 1.92.0` / `rustc 1.92.0` |
| Target | `wasm32-unknown-unknown` |
| Profile | `release` (`opt-level=z`, `lto=true`, `codegen-units=1`, `strip=true`, `panic=abort`) |

### Full import list (the artifact that matters)

```
ZERO imports.
```

The module contains no `(import ...)` declarations. This was verified with:

```bash
wasm-tools print target-shared/wasm32-unknown-unknown/release/temper_wasm_test_runner.wasm \
  | grep '(import'
# → no output
```

A module with zero non-WASI imports is deployable to a bare Cloudflare
isolate. No `env.dlsym`, no `__wbindgen_*`, no `getrandom` glue.

### Exports

```
(export "memory" (memory 0))
(export "temper_panic_message_len" (func 10))
(export "temper_panic_message_ptr" (func 11))
(export "temper_run_test" (func 12))
(export "temper_test_count" (func 16))
(export "temper_test_name_len" (func 17))
(export "temper_test_name_ptr" (func 18))
(export "temper_wasm_abi_version" (func 19))
(export "__data_end" (global 1))
(export "__heap_base" (global 2))
```

### Key dependencies that DID NOT appear in the import list

Despite the `temper-drc-rs` Cargo.toml dependency on `temper-geometry` (now
optional) and `temper-geometry`'s own `rand` + `getrandom` (js) dependencies
on `wasm32`, none of these produced imports:
- **`pyo3`** was excluded entirely by `optional = true` + feature
  `python = ["dep:pyo3", "dep:temper-geometry"]` — the wasm build uses
  `--no-default-features`, so `python` is off.
- **`rand` / `getrandom`** were excluded transitively: the
  `temper-wasm-test-runner` → `temper-drc-rs` edge no longer activates
  `temper-geometry` in the wasm config, so `rand` and `getrandom` never enter
  the dependency graph at all.
- **`wasm-bindgen`** was never a dependency of any crate in this graph.

The `temper-wasm-test-runner/Cargo.lock` confirms: `temper-drc-rs` has
`dependencies = [geo, regex, rstar, serde, serde_json, thiserror]` with no
`temper-geometry`, `pyo3`, `rand`, or `getrandom` entry.

---

## 2. Rung 3 — execute under wasmtime

### Runtime

| Property | Value |
|---|---|
| wasmtime version | 47.0.3 |
| Platform | aarch64-apple-darwin (Darwin 25.5.0) |
| wasm-tools version | 1.255.0 |

### Test census

```
Registered:     95
Executed:       95 (all via wasmtime --invoke temper_run_test)
Distinct names: 95
```

### Results: wasmtime vs native

```
wasmtime:
  pass:          91
  expected-fail:  4
  unexpected:     0

native (cargo test --no-default-features):
  pass:          95
  fail:           0
```

The four expected-fail tests are documented in
`tools/wasm/wasm_expected_failures.json`:

| Test | Class | Reason |
|---|---|---|
| `pymath::tests::host_libm_symbols_actually_resolve` | no-dynamic-loader | Asserts `dlsym(RTLD_DEFAULT, ...)` resolves; wasm32 has no dynamic loader |
| `pymath::tests::pow_is_not_a_multiply_or_a_sqrt` | b7-pow-divergence-absent | Asserts pow(x,2.0) != x*x for some x; LLVM folds on wasm32 |
| `dfm::tests::thermal_via_side_round_absorbs_the_pow_vs_sqrt_divergence` | b7-pow-divergence-absent | Same root cause — asserts pow-vs-sqrt divergence is non-empty |
| `dfm::tests::via_annular_area_uses_r_times_r_not_pow` | b7-pow-divergence-absent | Same root cause |

All four produce `wasm `unreachable` instruction executed` (panic→abort→trap)
under wasmtime and exit code 134 (SIGABRT). All 91 other tests return
`RUN_OK` (0) under wasmtime AND pass natively. **No unexpected traps, no
host-specific failures, no ULP threshold flips.**

### ULP / threshold findings

**None.** No test passed natively and failed on wasm32 due to a float
divergence. The `f64::powf` → LLVM folding is the only divergence observed,
and it affects exactly the 4 tests already listed as expected failures.
The plan's §5 item 6 risk (`getrandom`'s `js` feature trapping in a bare
host) did not manifest because the dependency graph no longer includes
`rand`/`getrandom` after the rung-2 source change.

---

## 3. Six-family exact-match table

One rule from each of the six rule families (`drc`, `emc`, `erc`, `safety`,
`placement`, `routing`) executed under wasmtime and produced the same verdict
as native on the same input.

| Family | Test | wasmtime | native | Match |
|---|---|---|---|---|
| `drc` | `rules::drc::clearance::tests::clearance_at_exact_threshold_flagged` | pass | pass | ✓ |
| `emc` | `rules::integration_tests::empty_board_zero_violations` | pass | pass | ✓ |
| `erc` | `rules::integration_tests::empty_board_zero_violations` | pass | pass | ✓ |
| `safety` | `rules::integration_tests::empty_board_zero_violations` | pass | pass | ✓ |
| `placement` | `rules::integration_tests::empty_board_zero_violations` | pass | pass | ✓ |
| `routing` | `rules::routing::power_pad_teardrop::tests::test_distance_to_rect_edge_outside` | pass | pass | ✓ |

The integration test `empty_board_zero_violations` calls
`create_default_registry()` → `reg.run_all()`, which invokes every registered
check from all six families against an empty board and asserts zero
violations. This test exercises all families simultaneously; four of the six
families (emc, erc, safety, placement) do not have individually-registered
per-family tests in the wasm32 registry, so the integration test is the
single test that covers them. The drc and routing families additionally have
dedicated tests (`clearance_at_exact_threshold_flagged`,
`test_distance_to_rect_edge_outside`) that also match.

---

## 4. Machine context

| Property | Value |
|---|---|
| OS | macOS 15.5.0 (Darwin 25.5.0) |
| Arch | aarch64 (Apple M-series) |
| rustc | 1.92.0 (ded5c06cf 2026-07-22) |
| cargo | 1.92.0 |
| wasmtime | 47.0.3 |
| wasm-tools | 1.255.0 |
| wasm32 target | wasm32-unknown-unknown (installed via rustup) |

---

## 5. Reproducible script

```bash
python3 tools/wasm/run_r1_smoke.py
```

Exits non-zero on any unexpected (non-manifested) wasm-vs-native mismatch.
Accepts `--build-only` to stop after rung 2.

---

## 6. R1 verdict for conditions 1–3 (plan §2)

**Verdict: PASS** on conditions 1, 2, 3.

| Condition | Plan requirement | Result |
|---|---|---|
| 1 — links | `cargo build --release --target wasm32-unknown-unknown --no-default-features` produces a `.wasm` | **PASS** — 1,183,886-byte artifact on disk |
| 2 — imports | Import list contains no host symbol a Cloudflare isolate cannot provide | **PASS** — zero imports |
| 3 — executes | At least one rule from each of six families executes under wasmtime, exactly equal to native | **PASS** — all six families, zero mismatches |

Combined with U2's condition 4 (all six families reachable under
`--no-default-features`, also PASS per the U2 evidence document), the overall
R1 verdict is **PASS**.

---

## 7. Source changes required for R1

**One change, incidental, 2 lines in Cargo.toml:**

```diff
-temper-geometry = { path = "../temper-geometry" }
+temper-geometry = { path = "../temper-geometry", optional = true }

-python = ["dep:pyo3"]
+python = ["dep:pyo3", "dep:temper-geometry"]
```

Classification: **incidental** — a `cfg`/feature gate that was never added.
The dependency was always used only in the python-gated module; the change
makes the feature graph reflect that truth. The fix is under 6 characters on
each of two lines. It does not change API, behavior, or the default-features
test surface (still 95 tests).

---

## 8. What could not be measured

- **The `getrandom` trap risk.** After the source change, `rand`/`getrandom`
  are not in the wasm dependency graph at all. The risk is therefore
  eliminated for the current wasm-test-runner, not merely unobserved. If a
  future change re-introduces `temper-geometry` into the non-python wasm
  graph, the risk returns and the import list would show `env.getrandom` (or
  equivalent). The import-list check in §1 would catch it.
- **Peak linear memory.** `wasmtime run --invoke` does not expose memory
  growth metrics. The Node host driver (`run_wasm_tests.mjs`) did measure
  this at a prior commit; it is not re-measured here.
- **Cold start (compile + instantiate).** Same limitation — these are
  host-bridge metrics, not available from bare `wasmtime run --invoke`.
- **Any float comparison in the last ULP that flips a threshold.** None
  occurred. All 91 passing tests agree exactly between wasm32 and native.
||||||| parent of 3c42adc60 (measure(wasm): U2 portable surface — 61 of 637 tests gated out under --no-default-features)

---

## Part 2 — The portable surface (U2, plan §2 condition 4)

*(U2's measurement was merged into this document when the U1 and U2
evidence branches landed; the two halves cover complementary conditions
of the R1 verdict and the consolidated verdict is at U9.)*

**Date:** 2026-08-06
**Base:** `origin/main` @ `f2c5af948ba2264b3fc05d1f7e6e63ce4d8fc59a`
**Branch:** `wasm/u2-portable-surface`
**Unit:** U2 "Measure the portable surface" of
`docs/plans/2026-08-05-001-feat-wasm-tier-phase0-plan.md`
**Scope:** measurement only. No production source was changed, nothing was
un-gated, no baseline or `power_pcb_dataset/` file was touched.
**Base assertion:** `scripts/assert-base.sh origin/main` exited 0 (HEAD ==
`origin/main` at dispatch).

This document records the U2 section of the R1 verdict. The full R1 verdict
requires all four conditions of plan §2; U2 owns condition 4. Conditions 1–3
are U1's rungs 2–3 and are recorded there.

---

## 1. Landed state (verified at HEAD, not assumed)

| Rung | What it establishes | Landed as | Verified here |
|---|---|---|---|
| 1 — type-checks | `cargo check --target wasm32-unknown-unknown --no-default-features` exits 0 | #656 (`bcfd3272e`, temper-drc-rs), #659 (`f9cbd8fde`, temper-geometry) | `cargo check` does **not** link (plan G1) |
| 2 — links | a `wasm32-unknown-unknown` artifact exists on disk | — | **not yet landed** (U1) |
| 3 — executes | one rule runs in a WASM runtime | #800 (`2259f8598`, `97dd0fc13`): `packages/temper-wasm-test-runner` + `tools/wasm/run_wasm_tests.mjs` + `tools/wasm/wasm_expected_failures.json` running the DRC test registry under Node/V8 | `docs/evidence/2026-08-06-wasm32-float-divergence.md` records the actual wasm32 module running 94 tests under Node's `WebAssembly` (V8, the engine `workerd` embeds) |
| 4 — surface | all six R5 rule families survive `--no-default-features` | **U2, this document** | ✓ PASS, §3 below |

Two HEAD-state facts the briefing warned could be stale, confirmed current:

- The stray `#[cfg(feature = "python")]` on `wasm_test_registry` introduced by
  `13aee32b7` ("DO NOT MERGE", merged anyway, broke the tier) is **fixed on
  this HEAD**: `packages/temper-drc-rs/src/lib.rs:44-45` gates the module on
  `#[cfg(feature = "wasm-test-registry")]` alone, landed by `5a375ee1a`
  (#819, "fix(wasm): un-gate wasm_test_registry from the python feature").
- `temper-geometry` has **no** `wasm-test-registry` feature and **no**
  `wasm_test_registry.rs` — `grep -rn "wasm-test-registry" packages/temper-geometry/`
  returns nothing, and its `Cargo.toml` declares only `python`. The rung-3
  execution surface (#800) covers `temper-drc-rs` tests only; there is no wasm
  harness for geometry. The task briefing's mention of a `wasm-test-registry`
  feature in `temper-geometry/Cargo.toml` does not match the actual file.

---

## 2. What was measured, and the exact commands

Every number below is produced by the committed tool
`tools/wasm/portable_surface.py` (ruff-clean, runs the two `--no-run` builds,
parses `--list` from each compiled test binary, emits a JSON delta), executed
at revision `f2c5af948b`. The tool's build commands, per crate:

- default features: `cargo test --no-run --message-format=json`
- no-default: `cargo test --no-run --no-default-features --message-format=json`

and for each compiled test binary: `<binary> --list`, counting lines matching
`: test`. (0 `: ignored` lines in any binary.) Because `--list` counts test
functions in the *compiled test harness*, it includes `#[test]` functions from
the library and from integration-test targets, and excludes doctests — it is a
measurement of the test surface, not a source line count.

**Environment:** darwin/arm64 (Darwin 25.5.0), `rustc/cargo 1.92.0`, host
target `aarch64-apple-darwin`. Builds are host builds — no `wasm32` target
required, per the unit's instructions. `CARGO_TARGET_DIR` was the shared
`target-shared` cache via `scripts/cargo_shared_env.sh`.

**pyo3 note:** the default-features test binaries of both libs carry
`pyo3`'s `extension-module` surface, which does not link libpython — on macOS
the flat-namespace lookup for `_PyBool_Type` fails at load. `--list` for those
two binaries was therefore retried with the interpreter's libpython preloaded
(`DYLD_INSERT_LIBRARIES=/Users/bennet/Miniforge3/lib/libpython3.12.dylib`,
Python 3.12.12). This is preload, not a code change; the tool records
`preload_needed` per binary.

Reproduce the whole measurement with:

```
python3 tools/wasm/portable_surface.py --out portable_surface.json
```

---

## 3. The JSON delta

### 3a. temper-drc-rs

```json
{
  "default_features":  { "build_ok": true, "total_test_count": 116 },
  "no_default_features": { "build_ok": true, "total_test_count": 94 },
  "delta": {
    "test_count_default": 116,
    "test_count_no_default_features": 94,
    "gated_out_count": 22,
    "gated_out_tests": [
      "deterministic_connectivity::tests::clean_chain",
      "deterministic_connectivity::tests::orphan_and_dangling",
      "deterministic_connectivity::tests::same_layer_requirement",
      "deterministic_connectivity::tests::unconnected_pads",
      "deterministic_connectivity::tests::via_bridges_layers",
      "deterministic_leaf_drc::tests::clamp_position_bounds",
      "deterministic_leaf_drc::tests::dedup_none_and_empty_net_are_distinct_keys",
      "deterministic_leaf_drc::tests::dedup_normalizes_direction_and_rounds",
      "deterministic_leaf_drc::tests::point_to_segment_distance_cases",
      "deterministic_leaf_drc::tests::signal_hv_empty_hv_guard_before_path_length",
      "deterministic_leaf_drc::tests::signal_hv_kind_is_explicit_not_inferred",
      "deterministic_leaf_drc::tests::summarize_violations_orders_by_count_desc",
      "deterministic_leaf_drc::tests::threshold_strict_greater_than",
      "router_clearance::tests::accelerated_matches_brute_force_dense_fine_only",
      "router_clearance::tests::accelerated_matches_brute_force_on_random_inputs",
      "router_clearance::tests::empty_input_zero_checks",
      "router_clearance::tests::hv_escalation_matches_expected_value",
      "router_clearance::tests::nan_via_point_does_not_panic_and_poisons_layer_like_python",
      "router_clearance::tests::overlapping_segments_are_negative_and_violating",
      "router_clearance::tests::repeated_calls_are_exactly_idempotent",
      "router_clearance::tests::single_route_zero_checks",
      "violation_report::py_float_fixed_tests::matches_cpython_on_rounding_classes"
    ],
    "targets_missing_in_no_default_features": [],
    "surplus_targets_in_no_default_features": []
  }
}
```

### 3b. temper-geometry

```json
{
  "default_features":  { "build_ok": true, "total_test_count": 521 },
  "no_default_features": { "build_ok": false, "cargo_exit_code": 101, "total_test_count": 482 },
  "delta": {
    "test_count_default": 521,
    "test_count_no_default_features": 482,
    "gated_out_count": 39,
    "gated_out_tests": [
      "area_sufficiency::py_float_tests::fixed_matches_cpython_on_rounding_classes",
      "area_sufficiency::py_float_tests::str_repr_divergence_classes",
      "area_sufficiency::py_float_tests::str_repr_ordinary_values",
      "area_sufficiency::py_sum_tests::all_negative_zeros_stay_positive",
      "area_sufficiency::py_sum_tests::nan_propagates",
      "area_sufficiency::py_sum_tests::neumaier_discriminator",
      "area_sufficiency::py_sum_tests::single_negative_zero_normalises_to_positive",
      "congestion_tensor::tests::test_cost_clamp_band_is_exact_at_max_cost",
      "congestion_tensor::tests::test_cost_computed_in_f64_matches_python_oracle",
      "congestion_tensor::tests::test_cost_respects_cap",
      "congestion_tensor::tests::test_cost_zero_usage_returns_one",
      "congestion_tensor::tests::test_increment_adds_to_cell",
      "congestion_tensor::tests::test_increment_cells_applies_weight",
      "congestion_tensor::tests::test_increment_cells_batch",
      "congestion_tensor::tests::test_increment_cells_cannot_overflow_into_another_cell",
      "congestion_tensor::tests::test_increment_cells_skips_negative_coords",
      "congestion_tensor::tests::test_increment_cells_skips_out_of_bounds",
      "congestion_tensor::tests::test_load_flat_overwrites_storage",
      "congestion_tensor::tests::test_reset_zeros_all",
      "congestion_tensor::tests::test_to_flat_bytes_roundtrip",
      "escape_via::tests::empty_pad_list_is_always_valid",
      "escape_via::tests::nan_distance_is_accepted_not_rejected",
      "escape_via::tests::pow_two_is_libm_not_a_multiply",
      "escape_via::tests::quadrant_rotation_is_not_an_exact_axis_swap",
      "escape_via::tests::side_none_and_side_zero_both_resolve_to_f_cu",
      "escape_via::tests::zero_sized_pad_radius_is_the_documented_half_millimetre",
      "fixed_copper::tests::mm_to_units_matches_even_parity_examples",
      "fixed_copper::tests::rotated_matches_quadrant_table",
      "fixed_copper::tests::zone_exact_clearance_positive_when_disjoint",
      "fixed_copper::tests::zone_exact_clearance_zero_when_intersecting",
      "pbt_cost_always_at_least_one",
      "pbt_cost_monotonically_increasing",
      "pbt_cost_scales_with_weight",
      "pbt_decay_one_is_identity",
      "pbt_reset_all_zeros",
      "tdd_cost_respects_cap",
      "tdd_increment_matches_python",
      "tdd_new_allocates_flat_zeroed_vec",
      "tdd_reset_matches_python"
    ],
    "targets_missing_in_no_default_features": [
      { "target": "test_congestion_tensor", "default_test_count": 9 }
    ],
    "surplus_targets_in_no_default_features": []
  }
}
```

The last 9 `gated_out_tests` (`tdd_*`, `pbt_*`, no module prefix) are the
integration tests of `tests/test_congestion_tensor.rs`; they appear unprefixed
because they are top-level functions of an integration-test crate.

### 3c. Combined

| Crate | Default | `--no-default-features` | Delta |
|---|---|---|---|
| `temper-drc-rs` | 116 | 94 | **22** |
| `temper-geometry` | 521 | 482 | **39** |
| **Total** | **637** | **576** | **61** |

The 61-test delta is the test surface the wasm tier cannot run. The plan's §6
census ("488 `#[test]` in the two crates", "783 total") is a different count
(source scan of `#[test]`, this measurement is compiled-harness `--list`); the
two are not directly comparable.

### 3d. Per-binary detail

| Crate | Binary | Default | No-default | Note |
|---|---|---|---|---|
| temper-drc-rs | `temper_drc_rs` (lib) | 116 | 94 | pyo3 preload needed only in default |
| temper-geometry | `temper_geometry` (lib) | 481 | 451 | pyo3 preload needed only in default |
| temper-geometry | `proptest_equivalence` (integration) | 31 | 31 | identical in both configs |
| temper-geometry | `test_congestion_tensor` (integration) | 9 | **does not compile** | `E0432` under `--no-default-features` |

**Execution check (beyond `--list`, for confidence that the surviving surface
runs, not just compiles):** `cargo test --no-default-features` in
`packages/temper-drc-rs` → `94 passed; 0 failed`. In `packages/temper-geometry`,
`cargo test --no-default-features --lib` → `451 passed; 0 failed`, and
`--test proptest_equivalence` → `31 passed; 0 failed` (the aggregate
`cargo test --no-default-features` exits 101 only because of the
`test_congestion_tensor` build failure in §5).

---

## 4. Per-rule-family reachability under `--no-default-features`

**Method.** `rules/` is declared un-gated in `packages/temper-drc-rs/src/lib.rs:35`;
`grep -rn "cfg(feature" packages/temper-drc-rs/src/rules/` finds **zero** internal
gates. The families depend only on `board.rs`, `constraints.rs`, `types/`
(all un-gated) and portable deps (`geo`, `rstar`, `regex`, `serde`). The
`--no-default-features` test binary compiles with the full
`rules::integration_tests` module in it — and the whole suite **executes**:
`cargo test --no-default-features` in `packages/temper-drc-rs` reports
`94 passed; 0 failed`. That includes `rules::integration_tests::empty_board_zero_violations`,
which calls `create_default_registry()` + `run_all()` over every registered
family — runtime proof that the registry, and therefore each family below, is
reachable in the no-default configuration. Public entry point per family = the
`*Check` structs re-exported from each `rules/<family>/mod.rs`, all registered
in `create_default_registry` (`rules/mod.rs:225-255`).

| Family | Module | Public entry points | Internal `#[cfg]` gates | Reachable under `--no-default-features` |
|---|---|---|---|---|
| `drc` | `rules/drc` | `ClearanceCheck`, `ComponentOverlapCheck`, `CourtyardCheck`, `ZoneContainmentCheck`, `TraceClearanceCheck`, `ViaSpacingCheck` | none | **YES** |
| `emc` | `rules/emc` | `LoopAreaCheck`, `NoiseCouplingCheck`, `GroundPlaneCheck` | none | **YES** |
| `erc` | `rules/erc` | `NetConnectivityCheck`, `PowerDomainCheck`, `FloatingPinsCheck` | none | **YES** |
| `safety` | `rules/safety` | `HVLVSeparationCheck`, `CreepageCheck`, `IsolationCheck` | none | **YES** |
| `placement` | `rules/placement` | `ThermalViaCountCheck`, `WaveSolderKeepoutCheck` | none | **YES** |
| `routing` | `rules/routing` | `ParallelRunCheck`, `StitchingViaDensityCheck`, `CopperPullbackCheck`, `IsolationBarrierCheck`, `ThtThermalReliefCheck`, `PowerPadTeardropCheck`, `PartialDischargeCheck`, `PadEntryWidthCheck`, `SplitPlaneCrossingCheck`, `IsolationSlotCheck` | none | **YES** |

The Rust-level geometry dependency of the rule families is none: the only
`temper_geometry::…` use in the whole crate is
`deterministic_connectivity.rs:21`
(`drc_constraints_geometry::point_to_rotated_rect_distance`), inside a
python-gated module. The families run on `board`/`constraints`/`geo` alone.

---

## 5. Known-excluded list (explicitly out of the portable build)

### Modules wholly gated behind `#[cfg(feature = "python")]`

**temper-drc-rs** (12 modules; `lib.rs`):

| Module | Lines | What it is |
|---|---|---|
| `validation.rs` | 908 (plan says "~922") | 11 pyfunctions via `register`: `infer_package_type`, `tht_hole_collisions`, `trace_length`, `rdl_sum`, `min_hv_lv_trace_clearance`, `geometric_validate`, `parse_drc_violation`, `compute_drc_penalty`, `group_violations`, `issue_fingerprint`, `metrics_summary` — includes its `host_math` `dlsym` surface. 0 `#[test]`s, so it shows no test-function delta |
| `board_py_bridge.rs` | 619 | Python-dict → `BoardState` bridge. 0 `#[test]`s |
| `closure_test.rs`, `drc_ratchet.rs`, `physics_oracle.rs` | — | Wave 4 Phase 4 regression-slice kernels. 0 `#[test]`s |
| `drc_contracts.rs` | — | drc_types/drc_result pyclasses. 0 `#[test]`s |
| `req_safe_01.rs` | — | REQ-SAFE-01 clearance/creepage validator (calls `temper_geometry` via `py.import`). 0 `#[test]`s |
| `dfm_py.rs` | — | router_v6 post-route DFM register. 0 `#[test]`s |
| `router_clearance.rs` | — | route-clearance kernels; **8 `#[test]`s lost** |
| `violation_report.rs` | — | report kernels; **1 `#[test]` lost** |
| `deterministic_leaf_drc.rs` | — | leaf DRC-check kernels; **8 `#[test]`s lost** |
| `deterministic_connectivity.rs` | — | connectivity kernel (the only Rust consumer of temper-geometry in the crate); **5 `#[test]`s lost** |

**temper-geometry** (11 modules; `lib.rs`):

| Module | Lines | Notes |
|---|---|---|
| `bridge.rs` | 1537 | the whole pyo3 function-registration surface |
| `congestion_tensor.rs` | 284 | wholly pyo3 (see its module doc comment); **13 `#[test]`s lost** |
| `area_sufficiency.rs` | — | Neumaier + pyfunction wrapper; **7 `#[test]`s lost** |
| `congestion.rs`, `congestion_analysis.rs`, `congestion_heatmap.rs` | — | wholly pyo3 surfaces |
| `escape_via.rs` | — | **6 `#[test]`s lost** |
| `routing_demand.rs`, `placement_suggestions.rs`, `apply_suggestions.rs` | — | wholly pyo3 surfaces |
| `fixed_copper.rs` | — | **4 `#[test]`s lost** |

Plus the integration target `tests/test_congestion_tensor.rs` (9 tests) which
does **not compile** under `--no-default-features` (unconditional
`use temper_geometry::congestion_tensor::CongestionTensor`).

### Per-item gating (the #659 pattern, inside otherwise-un-gated modules)

- `temper-drc-rs/src/constraints.rs:195-223` — `build_constraint_set` and the
  `py_dict_to_json_value`/`py_any_to_json_value` helpers (the Python-dict
  builder). The core `ConstraintSet` type is un-gated.
- `temper-geometry` — the `pub use …::*_py` re-export blocks in `lib.rs`
  (pad_geometry, clearance_geometry, spice_estimators, grid_raster, grid_utils,
  via_placement, bottleneck_geometry, heuristics_geometry,
  drc_constraints_geometry): each `*_py` function is `#[cfg(feature =
  "python")]` inside a module whose kernels survive.

### Anything else the measurement found

1. **`temper-geometry`'s `cargo test --no-run --no-default-features` exits
   101**, not 0 — the only failing configuration in the four measured. Root
   cause: `tests/test_congestion_tensor.rs:1` imports a python-gated module
   without its own `#[cfg(feature = "python")]`. The lib and
   `proptest_equivalence` binaries still compiled; the failed target's 9 tests
   are counted in the delta.
2. **Feature unification does not propagate `--no-default-features` to
   temper-geometry.** `cargo tree -e features` shows that
   `--no-default-features` on `temper-drc-rs` (and, identically, the
   `temper-wasm-test-runner` graph) still activates `temper-geometry`'s
   `default`/`python` features, because temper-drc-rs's dependency edge
   (`temper-geometry = { path = "../temper-geometry" }`) requests default
   features and feature activation is a union. `python` is therefore *on* for
   temper-geometry in the current wasm-tier build command, so pyo3 is compiled
   for `wasm32-unknown-unknown`. Whether pyo3 code survives into the final
   artifact is a separate question — the existing
   `2026-08-06-wasm32-float-divergence.md` recorded a working module with
   empty imports at `d5f459314`, consistent with unreferenced pyo3 code being
   dead-code-eliminated. This is a nuance for U1's import-list measurement to
   arbitrate, not a U2 finding; it is stated here because the plan's §0 wording
   ("pyo3 optional behind a default-on `python` feature") reads as if the
   wasm config is python-free end to end, which the feature graph shows it is
   not unless the dependency edge is changed to `default-features = false`.
3. **`validation.rs` measures 908 lines**, not ~922, and exposes **11**
   pyfunctions via `register`, not the plan's "10 kernels" — a count
   correction, nothing more.

---

## 6. The gate verdict (plan §2 condition 4)

U2's gate is: **R1 = PASS only if all six rule families are reachable under
`--no-default-features`; otherwise PASS-WITH-CAVEAT.**

**Verdict for condition 4: PASS.** All six families (`drc`, `emc`, `erc`,
`safety`, `placement`, `routing`) are reachable: their modules are un-gated,
their public `*Check` entry points are exported and registered in
`create_default_registry`, and that registry compiles and executes in the
`--no-default-features` test build. No family is gated out, so no
PASS-WITH-CAVEAT naming is required and no un-gating work is gated on U2's
verdict.

**Phase-1 precondition the measurement does surface** (a caveat on the
*surface*, not on the R5 families): 61 of 637 test functions and the entire
kernel surface of 23 python-gated modules (`validation.rs`'s 11 kernels,
`bridge.rs`, `congestion_tensor.rs`, `board_py_bridge.rs`, the Wave-4 leaf
kernels, …) are absent from the portable build. The rung-3 registry today
runs 94 `temper-drc-rs` tests and nothing from `temper-geometry`. If Phase 1
needs `validation.rs`'s raw-comparison pass/fail checks on the tier, that is
the split-module work named in the plan (pure kernel + `#[cfg]` bridge, the
pattern #659 already used for eleven geometry modules) — a precondition for
Phase 1, not a reopening of D3, exactly as the plan's gate text says.

This document does not emit the overall R1 verdict; conditions 1–3 (a linked
`.wasm` artifact, its import list, and six families executing under a WASM
runtime with exact native equality) belong to U1, and the consolidated verdict
is recorded at U9 per the plan.

---

## 7. What could not be measured

- **The actual `wasm32-unknown-unknown` build.** This unit measures the host
  build in two feature configurations, per its definition. Whether the
  576-test no-default surface survives codegen+link for `wasm32`, and whether
  the resulting module imports any host symbol, is U1's rung-2 job. (The
  `wasm32-unknown-unknown` target is installed on this machine but was not
  used.)
- **Whether pyo3 code from the transitively-python-on `temper-geometry` lands
  in the wasm artifact** (§5.2). Feature *activation* was measured via
  `cargo tree`; artifact *content* was not rebuilt here.
- **The plan's §6 "783 `#[test]`" figure.** Not reproduced by any scoping
  tried; this measurement's compiled-harness counts (637 default / 576
  no-default) use a different, and for this unit the relevant, definition.

---

## Part 3 — Feature-shape change: `default = []` (R1 re-verification, 2026-08-07)

**Date:** 2026-08-07
**Base:** `origin/main` @ `00ec5f94a535ff86b4042748f7b036c139b3cac2`
**Branch:** `feat/wasm-tier-phase0`
**Base assertion:** `scripts/assert-base.sh origin/main` exited 0.

### 1. What changed

Parts 1–2 closed R1 with `default = ["python"]` and a `--no-default-features`
wasm32 build. This execution's R1 requirement specified the stronger shape
`[features] default = []`: a **plain** `cargo build --target wasm32-unknown-unknown`
(default features off by default) must be the pyo3-free build. Four files
changed:

| File | Change |
|---|---|
| `packages/temper-drc-rs/Cargo.toml` | `default = ["python"]` → `default = []` (feature comment updated) |
| `packages/temper-geometry/Cargo.toml` | `default = ["python"]` → `default = []` (feature comment updated) |
| both `pyproject.toml` | `[tool.maturin] features = ["pyo3/extension-module"]` → `["python", "pyo3/extension-module"]` — the Python extension build now re-enables the `python` feature explicitly, because default features are no longer the mechanism that supplies it |
| `.github/workflows/python-tests.yml` | "Test temper-geometry (cargo test)" step → `cargo test --features python` — preserves the python-gated `#[cfg(test)]` surface that the default-feature flip would otherwise silently drop from CI |

### 2. wasm32 build — plain command, both crates

```
$ cargo build --release --target wasm32-unknown-unknown \
    --manifest-path packages/temper-drc-rs/Cargo.toml      # no feature flags
Finished `release` profile [optimized] target(s) in 2.07s

$ cargo build --release --target wasm32-unknown-unknown \
    --manifest-path packages/temper-geometry/Cargo.toml    # no feature flags
Finished `release` profile [optimized] target(s) in 11.60s
```

Artifacts (shared `CARGO_TARGET_DIR`):

| Artifact | Size (bytes) |
|---|---|
| `target-shared/wasm32-unknown-unknown/release/temper_drc_rs.wasm` | 364 |
| `target-shared/wasm32-unknown-unknown/release/temper_geometry.wasm` | 465,977 |
| `target-shared/wasm32-unknown-unknown/release/temper_wasm_test_runner.wasm` | 1,183,886 (unchanged from Part 1) |

### 3. Import lists — the artifact-level finding

```
$ wasm-tools print .../temper_drc_rs.wasm  | grep -c '^  (import'   → 0
$ wasm-tools print .../temper_geometry.wasm | grep '^  (import'     → 4
```

- **`temper_drc_rs.wasm` — zero imports.** Same as the Part-1 runner artifact.
  The tier's rule surface (the six families, `create_default_registry`) is
  deployable to a bare Cloudflare isolate.
- **`temper_geometry.wasm` — 4 `__wbindgen_*` imports.** `__wbindgen_throw`,
  `__wbindgen_describe`, `__wbindgen_externref_table_grow`,
  `__wbindgen_externref_table_set_null`. Source: `transform.rs::gumbel_softmax`
  calls `rand::random()` unconditionally in a pure kernel; `rand` → `getrandom
  0.2` pulls the `js` feature (the `[target.'cfg(target_arch = "wasm32")']`
  dependency), whose entropy source routes through wasm-bindgen glue. This is
  the **exact risk the parent plan's §5.6 predicted** — now verified
  empirically at the artifact level rather than by inspection. It is NOT a
  build failure and does not reopen D3 (the rules the tier runs live in
  temper-drc-rs's import-free artifact); it is a recorded deployability caveat
  for a standalone temper-geometry module, matching the "unowned risk" the
  plan flagged for Phase 1. The `getrandom` `js` feature was previously
  thought to be excluded from the wasm graph (Part 1 §1) — that was true for
  the *runner* graph (which does not include temper-geometry), not for a
  standalone temper-geometry build.

### 4. dlsym fallback verification (pad_geometry.rs)

`pad_geometry.rs` resolves `cos`/`sin` through `dlsym` on non-wasm32 targets;
on wasm32 the `#[cfg(target_arch = "wasm32")]` std-intrinsic fallback
(`f64::cos`/`f64::sin`, no dynamic loader) is what compiles. The successful
`wasm32-unknown-unknown` build of temper-geometry above **proves the fallback
compiles and links** — `cargo check` could not have shown this (G1), and the
rung-2 link step now does.

### 5. Native pyo3 build — intact after the default flip

The Python extension build re-enables `python` via `[tool.maturin] features`,
verified end to end:

```
$ uv run --no-sync maturin develop --release --manifest-path packages/temper-geometry/Cargo.toml   # OK
$ uv run --no-sync maturin develop --release --manifest-path packages/temper-drc-rs/Cargo.toml     # OK ("Using build options features from pyproject.toml")
$ uv run --no-sync python scripts/write_extension_stamps.py
$ uv run --no-sync python scripts/check_stale_extensions.py
  fresh=13 stale=0 missing=0   # 0 STALE
$ python -c "import temper_geometry; import temper_drc_rs; import temper_rust_router"
  temper_geometry pyfunctions present; temper_drc_rs.serialize_board_state present; OK
```

### 6. Native gates (both feature modes)

| Gate | `--no-default-features` | `--all-features` (python on) |
|---|---|---|
| `cargo build --release` temper-drc-rs | PASS | PASS |
| `cargo build --release` temper-geometry | PASS | PASS |
| `cargo clippy --all-targets -- -D warnings` temper-drc-rs | PASS | PASS |
| `cargo clippy --all-targets -- -D warnings` temper-geometry | PASS | PASS |
| `cargo test` temper-drc-rs | 112 passed | — (macOS dyld abort for the python-gated test harness is the documented pre-existing platform limitation; CI runs the equivalent step on Linux) |
| `cargo test` temper-geometry | 482+31+1 passed | compiles; macOS dyld abort, documented, CI runs on Linux |

The four clippy lints the `--all-targets` sweep surfaced in
`examples/r2_full_board_pass.rs` (`doc_lazy_continuation`,
`unnecessary_map_or`, `expect_used`, `unwrap_used`) are **pre-existing** (the
example merged via #875) and were fixed mechanically in this execution so the
exact CI command is green for the touched crates.

### 7. Verdict

R1's feature-gate shape is now exactly `default = []`; the plain wasm32 build
works for both crates; the dlsym fallback links; and the native pyo3 build is
verified fresh (0 STALE, imports exercised). The one caveat carried forward
from the build: temper-geometry's standalone wasm artifact imports 4
wasm-bindgen glue functions (plan §5.6, now empirically confirmed). **R1
remains PASS**; the standalone-geometry glue caveat is Phase-1 input, not a
substrate failure.

**Guard repair (same commit set, 2026-08-07):** the U3 CI regression guard's
step used `set -euo pipefail`, which is an illegal option under the `sh`
(dash) shell the rust-checks container runs steps with — so CI had been
failing the step on that `set` line **before any cargo command ran**, and the
wasm32 build+clippy guard had never actually executed in CI (confirmed on main
runs through 2026-08-07). Fixed to `set -eu` (portable to sh and bash). The
same guard step's clippy and cargo-test siblings are independently red on main
at this date for pre-existing reasons outside this gate's scope
(temper-design-bundle clippy lint; temper-geometry pyo3 test-binary link);
both reproduce on unmodified main and are not caused by the feature-shape
change.
