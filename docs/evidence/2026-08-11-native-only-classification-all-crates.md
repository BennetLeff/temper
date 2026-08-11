<!-- provenance: commit=d1b330b90a149f5effd09c7e63b87deeebdb0261 dirty=false -->

# WASM tier U3, all crates — native-only classification across the tier

**Date:** 2026-08-11
**Snapshot commit (this document, worktree HEAD):** `d1b330b90a149f5effd09c7e63b87deeebdb0261` (`origin/main`)
**Measurement commit (R19 figures, 8 of 9 crates):** `86c6a01f0654319c0f270cf3308c1a86929d4108` — the commit `WASM Tier Nightly Sweep (R19 Agreement)` run [`31455191432`](https://github.com/BennetLeff/temper/actions/runs/31455191432) (2026-08-11T03:22:22Z, `workflow_dispatch`, conclusion `success`) checked out and measured. It is six commits behind this document's own snapshot commit.
**`temper-pcl-ir` measured locally** at the snapshot commit above (see §7) — it has no nightly artifact at all (§7 explains why).
**Board:** `pcb/temper.kicad_pcb` sha256 `6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64` (unchanged from the nightly's own measurement — re-verified at the snapshot commit).
**Unit:** U3 of `docs/plans/2026-08-10-001-feat-wasm-tier-phase5-plan.md` (R27, D14), extended from `temper-drc-rs` alone
(`docs/evidence/2026-08-10-wasm-tier-u3-native-only-classification.md`) to all nine registered crates.
**Measurement:** `gh run download 31455191432`, the `wasm-tier-nightly-local-31455191432` artifact's eight per-crate
`r19_local_<crate>_86c6a01f_6928b7c8.json` files (each produced by `tools/wasm/r19_compare.py`, one native `cargo test`
run and one local wasm32 build/sweep per crate — see that workflow's own header for why one comparison per crate is a
correctness requirement, not tidiness). `temper-pcl-ir` reproduced locally the same way (§7). Every native-only test
was then classified by reading `scripts/gen_wasm_test_registry.py`'s own `discover_eligible()` (imported as a library,
never modified) against the source at the nightly's commit, cross-checked against each crate's `tests/` integration
targets and doctests. Full reproduction commands are in §8.

**Nine other agents are editing this repository's crates concurrently with this measurement.** The counts in this
document are already stale by the time you read them in one specific, demonstrated way (§1.1: `temper-geometry` and
`temper-thermal`'s *registered* counts grew between the nightly's commit and this document's snapshot commit, six
commits later, taken minutes apart). Treat every count here as "true at the cited commit," not as "true now."

## Bottom line

Extending U3 from one crate to all nine finds **325 native-only tests across the eight crates the nightly measures,
plus 0 in the ninth (`temper-pcl-ir`, measured locally — see §7).** Classified:

| class | count | self-selects correctly under D14? |
|---|---:|---|
| `proptest-dev-dependency` | 260 | yes — structurally uncompilable (dev-dependency absent from the non-test build) |
| `integration-test-target` | 57 | yes — structurally unreachable (`tests/`, a separate crate) |
| `cfg-excluded` | 5 | yes — the test carries its own `#[cfg(not(target_arch = "wasm32"))]`, deliberately |
| `doctest` | 1 | yes — a doctest is its own compilation unit, unreachable from the registry mechanism |
| **`portable-but-missing`** | **2** | **no** |
| **total** | **325** | |

**Portable-but-missing: 2, both in `temper-rust-router-core`.** `encoding::tests::exhaustive_at_most_k_n1_to_n8` and
`encoding::tests::encode_to_cnf_empty_model` use no proptest, no pyo3, no SAT solver, and no host-only symbol — nothing
distinguishes them from the 1,708+ tests the tier already runs. They are excluded from the registry not because of
anything about themselves, but because a **sibling** nested module (`encoding::tests::proptests`, five genuine
proptest tests) lacks its own `#[cfg(test)]` gate. `discover_eligible()`'s dependency scan then attributes the
sibling's `use proptest::prelude::*` to the *whole* `encoding::tests` module, and the two innocent tests are excluded
along with it. Demonstrated in a throwaway copy (§6): adding the one missing `#[cfg(test)]` line makes `encoding::tests`
register cleanly with exactly its own 2 tests, and `encoding::tests::proptests` becomes its own (correctly excluded)
5-test entry.

This is the same *shape* of finding as the `ipc.rs` bug the single-crate U3 document found (a portable test absent from
the tier with nothing in CI able to notice), but a **different mechanism** — not a module missing from `ELIGIBLE`
outright (that failure mode is now caught: `scripts/gen_wasm_test_registry.py --check`'s second gate arm,
`check_unregistered()`, ran clean on all nine crates at this snapshot, §1.2), but a module *wrongly and silently*
folded into a sibling's exclusion reason. `check_unregistered()` does not catch it because, from its point of view,
`encoding::tests` already has a reason (`proptest-dev-dependency`) — the two gates agree with each other, and both are
wrong. **Reported here; not fixed.** `temper-rust-router-core` is owned by another agent in this fleet, and this
document's only write is itself (see "Scope boundaries" in the assigning task).

**D14's self-selection claim: holds for 323 of 325 (99.4%) of the tier's native-only tests, and fails for the same 2
it would have failed for at any prior classification pass** — the failure is not new, it predates this document, and
nothing before this document had enumerated it. The single-crate U3 document already showed D14's reasoning is
"silent about tests the tier never sees" for one mechanism (module absent from `ELIGIBLE`); this document shows a
second, independent mechanism (module wrongly folded into a sibling's exclusion) produces the identical epistemic
gap — a native-only test with no tier verdict, invisible to a comparison that only compares what is present, and
invisible to a drift gate that only checks modules it already has a reason for.

## 0. Method, and its limits

`tools/wasm/r19_compare.py` (read, not modified) computes `native_only` as: every name in the native
`cargo test` output's `test <name> ... <status>` lines, minus every name the wasm32 registry actually
executed. Name normalisation is exactly that script's own `parse_native_output` (strip the leading `test `, strip the
trailing `... <status>`, strip a `#[should_panic]` test's ` - should panic` suffix) — reused, not reimplemented, per
this task's instruction.

Classification beyond that point (which *class* each native-only name belongs to) is this document's own work,
built on `scripts/gen_wasm_test_registry.py`'s `discover_eligible()` — imported as a Python library and called
read-only (no file writes) against the source tree at each test's measurement commit. Three supplementary lookups
were needed beyond what `discover_eligible()` reports directly, because it operates at module granularity and three
of the five classes are not module-level:

1. **`tests/` integration targets** are invisible to `discover_eligible()` by construction (it only scans `src/`, per
   the crate's own `ELIGIBLE`/registry mechanism, which cannot reach a separate compilation unit). Identified instead
   by walking every `packages/<crate>/tests/*.rs` file at the measurement commit and matching `#[test]` function
   names (including nested `mod`s, e.g. `temper-rust-router-core`'s `tests/test_loop_extractor.rs` declaring
   `mod bmc_tests { ... }`).
2. **Doctests** are identified by `cargo test`'s own doctest line shape (`<path> - <item> (line N)`), which
   `parse_native_output` accepts as a name like any other but which never has, and never can have, a wasm32-registry
   counterpart — a doctest is compiled as its own tiny binary per doctest, not through the crate's test harness at
   all.
3. **`cfg-excluded`** individual tests (a `#[test]` fn carrying its own `#[cfg(not(target_arch = "wasm32"))]`, inside
   an otherwise-eligible, otherwise-registered module) are invisible to `discover_eligible()`, which reports per
   *module*, not per function. Found instead by reading each such fn's own attributes directly (all five, in this
   tier, are literally named `host_libm_symbols_actually_resolve` / `py_pow_resolves_to_host_libm_not_sqrt` — see
   §3).

The two `portable-but-missing` tests were found by neither of the above: `discover_eligible()` reported their module
(`encoding::tests`) as excluded (`proptest-dev-dependency`), same as any genuinely-proptest module, so at first pass
they were indistinguishable from the 260 legitimate `proptest-dev-dependency` entries. Finding them required
noticing that `d.tests` (7, matching two structurally-distinct kinds of code) didn't match `d.ident` (`tests`, a name
that never independently signals "and also proptest"), and tracing *which* lines within the module actually matched
the proptest-use regex — see §6 for the full trace and the throwaway-copy proof.

### 0.1 What this method cannot see

This document's classification is **read-only against source, at named commits**. It did not run `cargo test` fresh
for eight of the nine crates (only `temper-pcl-ir`, §7, and the router-core throwaway-copy probe, §6, which never
touches a tracked file) — the native/wasm32 counts for those eight are the nightly's own, not independently
re-measured here. A method this size, applied by hand across nine crates under six commits of concurrent drift, is
exactly the situation the single-crate U3 document's own closing section warned generalises poorly; this document is
the generalisation, and its numbers should be read as "true at the cited commit, reproducible by the commands in
§8," not as a permanently-fixed inventory.

## 1. Per-crate summary

All figures at measurement commit `86c6a01f` except `temper-pcl-ir` (measured locally at `d1b330b9`, this document's
own snapshot commit — see §7).

| crate | native total | registered (wasm32) | native-only | proptest-dev-dep | integration-test-target | cfg-excluded | doctest | portable-but-missing |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `temper-drc-rs` | 1,751 | 1,719 | 32 | 31 | 1 | 0 | 0 | 0 |
| `temper-geometry` | 2,321 | 2,232 | 89 | 55 | 31 | 2 | 1 | 0 |
| `temper-thermal` | 191 | 143 | 48 | 47 | 0 | 1 | 0 | 0 |
| `temper-design-bundle` | 26 | 24 | 2 | 0 | 2 | 0 | 0 | 0 |
| `temper-rust-router-core` | 145 | 111 | 34 | 23 | 9 | 0 | 0 | **2** |
| `temper-constraint-compiler` | 93 | 69 | 24 | 9 | 14 | 1 | 0 | 0 |
| `temper-quality-oracle` | 166 | 125 | 41 | 40 | 0 | 1 | 0 | 0 |
| `temper-io-types` | 199 | 144 | 55 | 55 | 0 | 0 | 0 | 0 |
| `temper-pcl-ir` (local, `d1b330b9`) | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| **total** | **4,894** | **4,569** | **325** | **260** | **57** | **5** | **1** | **2** |

**Zero `python-gated` and zero `sat-gated` entries anywhere in the 325**, for the same structural reason the
single-crate U3 document found zero pyo3-gated entries in its 43: every native arm in this nightly runs
`--no-default-features` (`tools/wasm/wasm_tier_topology.json`'s `native_test_args`, the same flag the wasm32 build
uses), so a `#[cfg(feature = "python")]` or `#[cfg(feature = "sat")]` module is absent from **both** sides equally —
never native-only, because it is never native either. This is worth stating plainly because it is the single most
common wrong guess about why a test would be tier-absent, and it explains none of the 325.

### 1.1 Counts already moved

Re-running `python3 scripts/gen_wasm_test_registry.py --crate <X> --check` at this document's own snapshot commit
(`d1b330b9`, six commits after the nightly's `86c6a01f`) gives different *registered* totals for two crates:

| crate | registered @ `86c6a01f` (nightly) | registered @ `d1b330b9` (this doc's snapshot) |
|---|---:|---:|
| `temper-geometry` | 2,232 | 2,234 (+2) |
| `temper-thermal` | 143 | 145 (+2) |
| `temper-constraint-compiler` | 69 | 70 (+1) |
| `temper-quality-oracle` | 125 | 126 (+1) |
| (all other crates) | unchanged | unchanged |

This is not noise or a measurement error — it is other agents' work landing on `main` between the nightly's commit
and this document's own, exactly as the assigning task said would happen. The class breakdown in §1 is therefore a
snapshot, not a ceiling: new tests added since `86c6a01f` are not in the 325 (they may be newly-registered-and-passing,
or newly native-only of any class, including — unverified here — a third `portable-but-missing` instance). Anyone
reusing these numbers should re-run §8's commands rather than treat this table as current.

### 1.2 `check_unregistered()` — the generator's own second gate — is clean on all nine crates today

`scripts/gen_wasm_test_registry.py --crate <X> --check` (run read-only, no `--check`-less write, against this
document's own snapshot commit `d1b330b9`) reported **`wasm test registry up to date`** for all nine crates, with no
`check_unregistered()` warning on any of them. That gate (added after the single-crate U3 document's `ipc.rs`
finding) walks every `#[cfg(test)]` module under `src/` from source and fails if one is eligible-but-unlisted —
exactly the failure mode `ipc.rs` was. It is clean today: no crate has a whole module silently missing from
`ELIGIBLE`/discovery in that specific sense.

**This is not the same claim as "zero portable-but-missing."** §everything above this line is why: the router-core
bug is invisible to `check_unregistered()` precisely because `discover_eligible()` (which both `check_unregistered()`
and this document's classification are built on) already has a stated reason for `encoding::tests` — a wrong one,
but a *present* one, so the module never appears in `check_unregistered()`'s "eligible but unlisted" set. The
generator's own gate is necessary and was sufficient for the `ipc.rs` failure mode; it is not sufficient for this
one.

## 2. Class definitions (recap, unchanged from the single-crate U3 document)

- **`proptest-dev-dependency`** — the test module (or, correctly, the specific nested submodule) `use`s `proptest`,
  a `[dev-dependencies]` entry absent from the non-test build the registry compiles into.
- **`integration-test-target`** — the test lives under `packages/<crate>/tests/`, a separate crate the registry's
  in-module mechanism structurally cannot reach.
- **`cfg-excluded`** — the test carries its own `#[cfg(...)]` (here, always `not(target_arch = "wasm32")`), and is
  registered *with that cfg repeated on its registry entry* — present in the registry's source text, absent from
  the compiled wasm32 array.
- **`doctest`** — a `cargo test` doctest, its own per-example compilation unit, structurally outside the registry
  mechanism the same way an integration test is.
- **`portable-but-missing`** — nothing prevents registration; the classification pass (or, in `ipc.rs`'s case, the
  generator's `ELIGIBLE` list) simply has it wrong.

`sat-gated` and `python-gated` are established classes for this tier (`temper-rust-router-core` and
`temper-constraint-compiler` both declare `absent_features = ("python", "sat")`) but, per §1's note, contribute zero
of the 325 native-only tests: those modules are equally absent from the native arm, so they can never be native-only.

## 3. `cfg-excluded` — 5 tests, all host-libm dynamic-loader guards

Every one of the five is a `#[cfg(not(target_arch = "wasm32"))]` test asserting that `dlsym` resolves a host libm
symbol (`cos`/`sin`/`pow`/`sqrt`) — the load-bearing anti-vacuity check for a *different* mechanism entirely (that the
crate's host-math shim genuinely calls the platform's C library rather than a plausible-looking Rust fallback). The
property under test — "does `dlsym` exist and resolve" — is definitionally false on `wasm32-unknown-unknown` (no
dynamic loader at all), so excluding it via the test's own `cfg` rather than registering-and-expecting-failure
(the `wasm_expected_failures*.json` mechanism the single-crate U3 document's four host-libm/pow-divergence entries
use) is arguably the cleaner design: it never even attempts to call `dlsym` from wasm32, rather than attempting and
catching a trap.

| test | file:line | own cfg |
|---|---|---|
| `host_math::tests::host_libm_symbols_actually_resolve` | `packages/temper-geometry/src/host_math.rs:193` (fn at `:195`) | `#[cfg(not(target_arch = "wasm32"))]` |
| `pad_geometry::tests::host_libm_symbols_actually_resolve` | `packages/temper-geometry/src/pad_geometry.rs:526` (fn at `:528`) | `#[cfg(not(target_arch = "wasm32"))]` |
| `device_power::tests::host_libm_symbols_actually_resolve` | `packages/temper-thermal/src/device_power.rs:304` (fn at `:306`) | `#[cfg(not(target_arch = "wasm32"))]` |
| `constraints::tests::host_libm_symbols_actually_resolve` | `packages/temper-constraint-compiler/src/constraints/mod.rs:485` (fn at `:487`) | `#[cfg(not(target_arch = "wasm32"))]` |
| `placement_metrics::tests::py_pow_resolves_to_host_libm_not_sqrt` | `packages/temper-quality-oracle/src/placement_metrics.rs:864` (fn at `:866`) | `#[cfg(not(target_arch = "wasm32"))]` |

Each is registered — the committed `wasm_test_registry.rs`/module `WASM_TESTS` block for its module names it, with
the same `#[cfg(not(target_arch = "wasm32"))]` prefix repeated on the entry (e.g.
`packages/temper-geometry/src/host_math.rs:245`: `` #[cfg(not(target_arch = "wasm32"))] ("host_math::tests::host_libm_symbols_actually_resolve", host_libm_symbols_actually_resolve), ``).
The entry is *present in the source*, absent from the *compiled wasm32 array* — this is what distinguishes the class
from `portable-but-missing`: the generator, and whoever wrote the test, both already made the exclusion decision
explicitly, at the site.

## 4. `integration-test-target` — 57 tests, six crates, twelve files

Every one of these compiles as a separate `cargo test` integration-test crate under `packages/<crate>/tests/`, which
the registry mechanism (a `pub const` emitted *inside* each private `#[cfg(test)] mod`, per
`scripts/gen_wasm_test_registry.py`'s module docstring) cannot reach by construction, independent of whether the
test itself uses anything wasm32-incompatible.

| crate | file | tests |
|---|---|---:|
| `temper-drc-rs` | `tests/property_containment_gap.rs` | 1 |
| `temper-geometry` | `tests/proptest_equivalence.rs` | 31 |
| `temper-geometry` | doctest, `src/transform.rs:9` (separately counted as `doctest`, not here) | — |
| `temper-design-bundle` | `tests/temper_bundle.rs` | 2 |
| `temper-rust-router-core` | `tests/test_loop_extractor.rs` (`mod bmc_tests`, `mod proptest_tests`, `mod temper_tests`) | 8 |
| `temper-rust-router-core` | `tests/test_encoding.rs`, `tests/test_types.rs` (each one `fn scaffold()`, collapsed to one name by `r19_compare.py`'s name-keyed dict — see caveat below) | 1 |
| `temper-constraint-compiler` | `tests/proptest_provenance.rs` (`p1`..`p5`) | 5 |
| `temper-constraint-compiler` | `tests/proptest_tier0_to_tier1.rs` (`test_tier0_to_tier1_*`) | 4 |
| `temper-constraint-compiler` | `tests/proptest_tier1_to_tier2.rs` (`test_tier1_to_tier2_*`) | 4 |
| `temper-constraint-compiler` | `tests/test_incremental.rs`, `tests/test_provenance.rs`, `tests/test_tier0_to_tier1.rs`, `tests/test_tier1_to_tier2.rs`, `tests/test_type_lattice.rs` (each `fn placeholder()`, collapsed to one name) | 1 |
| **total** | | **57 distinct names** (62 `#[test]` fns exist across these twelve files; two `scaffold` occurrences and five `placeholder` occurrences collapse to 1 distinct name each under `r19_compare.py`'s name-keyed native map, see below) |

**A caveat on `r19_compare.py` itself, found while tracing `constraint-compiler`'s `placeholder`:** `parse_native_output`
builds `native_map: dict[str, str]` keyed purely by test *name*, with no binary/target qualifier. Five separate
integration-test binaries in `temper-constraint-compiler` each declare `fn placeholder() {}` (evidently a scaffold
left over from when each file was created), and `temper-rust-router-core` has two independent `fn scaffold()`.
`cargo test` prints `test placeholder ... ok` once per binary — five occurrences — but the dict collapses them to one
key, so the comparison silently under-counts by 4 (`placeholder`) and 1 (`scaffold`) native tests relative to what
actually ran. This does not change any classification in this document (all six collapse to the same
`integration-test-target` class regardless of which binary they're really in), but it is a real, small blind spot in
the shared tool this document was told to reuse rather than reimplement — noted here per this document's instruction
to report findings, not fix them.

## 5. `proptest-dev-dependency` — 260 tests, 42 modules across 8 crates

Full names, grouped by crate and module, generated directly from each crate's `r19_local_*.json` `native_only_detail`
and cross-checked against `discover_eligible()`'s own exclusion reason for that module. Sums match every crate's row
in §1 exactly (verified programmatically, not by eye).

<details>
<summary><code>temper-drc-rs</code> — 31 tests (3 modules: <code>ipc::proptests</code> 9, <code>pymath::proptests</code> 15, <code>validation_kernels::proptests</code> 7)</summary>

```
ipc::proptests::p1_current_capacity_non_negative
ipc::proptests::p2_current_capacity_monotone_in_width
ipc::proptests::p3_current_capacity_monotone_in_temp_rise
ipc::proptests::p4_external_carries_more_than_internal
ipc::proptests::p5_min_trace_width_non_negative
ipc::proptests::p6_min_trace_width_monotone_in_current
ipc::proptests::p7_internal_needs_wider_than_external
ipc::proptests::p8_trace_width_round_trip
ipc::proptests::p9_net_current_non_negative
pymath::proptests::p1_py_max_returns_larger
pymath::proptests::p2_py_max_returns_one_of_inputs
pymath::proptests::p3_py_max_nan_first_returns_nan
pymath::proptests::p4_py_max_nan_second_returns_first
pymath::proptests::p5_py_min_returns_smaller
pymath::proptests::p6_py_min_returns_one_of_inputs
pymath::proptests::p7_py_min_nan_first_returns_nan
pymath::proptests::p8_py_min_nan_second_returns_first
pymath::proptests::p9_py_round_to_int_is_integer
pymath::proptests::p10_py_round_to_int_diff_at_most_half
pymath::proptests::p11_py_round_to_int_ties_to_even
pymath::proptests::p12_py_hypot_non_negative
pymath::proptests::p13_py_hypot_symmetric
pymath::proptests::p14_py_hypot_ge_max_abs
pymath::proptests::p15_py_hypot_zero_returns_abs
validation_kernels::proptests::p1_infer_package_type_is_known
validation_kernels::proptests::p2_tht_no_violations_when_distant
validation_kernels::proptests::p3_tht_violation_message_has_both_refs
validation_kernels::proptests::p4_min_clearance_non_negative
validation_kernels::proptests::p5_min_clearance_symmetric
validation_kernels::proptests::p6_fingerprint_contains_code_and_message
validation_kernels::proptests::p7_fingerprint_order_invariant
```
</details>

<details>
<summary><code>temper-geometry</code> — 55 tests (5 modules: <code>creepage_check::properties</code> 8, <code>grid_raster::proptests</code> 8, <code>polygon::proptests</code> 9, <code>smooth::proptests</code> 15, <code>units::proptests</code> 7, <code>via_clearance::properties</code> 8)</summary>

```
creepage_check::properties::m1_distance_invariant_under_translation
creepage_check::properties::m2_distance_invariant_under_rotation
creepage_check::properties::m3_distance_scales_with_geometry
creepage_check::properties::p1_distance_is_non_negative
creepage_check::properties::p2_swapping_segments_is_bit_exact
creepage_check::properties::p3_distance_is_monotonic_moving_away
creepage_check::properties::p4_distance_is_bounded_by_midpoints
creepage_check::properties::p5_creepage_bracket_is_monotonic_in_voltage
grid_raster::proptests::p1_merge_cell_free_accepts
grid_raster::proptests::p2_merge_cell_same_net_idempotent
grid_raster::proptests::p3_merge_cell_different_positive_nets_conflict
grid_raster::proptests::p4_merge_cell_conflict_is_sticky
grid_raster::proptests::p5_effective_creepage_outer_is_identity
grid_raster::proptests::p6_effective_creepage_inner_is_scaled
grid_raster::proptests::p7_closest_component_empty_returns_none
grid_raster::proptests::p8_closest_component_result_is_an_input_ref
polygon::proptests::p1_polygon_area_non_negative
polygon::proptests::p2_area_sign_flips_on_reversal
polygon::proptests::p3_triangle_area_non_negative
polygon::proptests::p4_triangle_area_symmetric
polygon::proptests::p5_triangle_area_matches_polygon_area
polygon::proptests::p6_perimeter_non_negative
polygon::proptests::p7_perimeter_is_sum_of_edge_lengths
polygon::proptests::p8_bounding_box_contains_vertices
polygon::proptests::p9_translation_preserves_area
smooth::proptests::p1_smooth_max_ge_max
smooth::proptests::p2_smooth_max_symmetric
smooth::proptests::p3_smooth_max_monotonic_in_alpha
smooth::proptests::p4_smooth_min_le_min
smooth::proptests::p5_smooth_min_symmetric
smooth::proptests::p6_smooth_min_via_max_identity
smooth::proptests::p7_smooth_abs_symmetric
smooth::proptests::p8_smooth_abs_non_negative
smooth::proptests::p9_smooth_step_output_in_01
smooth::proptests::p10_smooth_max_axis_ge_max
smooth::proptests::p11_smooth_min_axis_le_min
smooth::proptests::p12_hpwl_smooth_ge_true_hpwl
smooth::proptests::p13_weighted_average_bounded_by_extrema
smooth::proptests::p14_alpha_schedule_endpoints
smooth::proptests::p15_alpha_schedule_monotonic
units::proptests::p1_mil_to_mm_matches_pinned_expression
units::proptests::p2_mm_to_mil_matches_pinned_expression
units::proptests::p3_inch_conversions_match_pinned_expressions
units::proptests::p4_mil_inch_conversions_match_pinned_expressions
units::proptests::p5_all_six_monotonic
units::proptests::p6_round_trip_within_two_rounding_bound
units::proptests::p7_power_of_two_scale_is_exact
via_clearance::properties::m1_path_length_invariant_under_translation
via_clearance::properties::m2_simplify_invariant_under_reflection
via_clearance::properties::m3_safety_distances_monotone_in_pollution
via_clearance::properties::p1_grid_to_world_axes_are_separable
via_clearance::properties::p2_path_length_two_cells_matches_formula
via_clearance::properties::p3_safety_distances_monotone_in_voltage
via_clearance::properties::p4_voltage_class_agnostic_to_numeric_suffix
via_clearance::properties::p5_via_counts_and_segments_consistent
```
</details>

<details>
<summary><code>temper-thermal</code> — 47 tests (7 modules: <code>geometric_metrics::tests::proptests</code> 4, <code>heat_removal::tests::proptests</code> 5, <code>hostmath::tests::proptests</code> 9, <code>thermal_edges::tests::proptests</code> 6, <code>thermal_potential::tests::linspace_proptests</code> 6, <code>thermal_potential::tests::field_proptests</code> 10, <code>thermal_potential::tests::uniqueness_proptests</code> 7)</summary>

```
geometric_metrics::tests::proptests::prop_boundary_violation_count_bounded
geometric_metrics::tests::proptests::prop_hv_lv_clearance_default_when_empty_classes
geometric_metrics::tests::proptests::prop_overlap_area_non_negative
geometric_metrics::tests::proptests::prop_zone_violation_max_non_negative
heat_removal::tests::proptests::prop_h_field_all_finite
heat_removal::tests::proptests::prop_h_field_cells_at_least_background
heat_removal::tests::proptests::prop_h_field_dimensions
heat_removal::tests::proptests::prop_h_field_uniform_when_empty
heat_removal::tests::proptests::prop_h_field_zero_cs_raises
hostmath::tests::proptests::prop_np_clip_bounded
hostmath::tests::proptests::prop_np_clip_inverted_returns_hi
hostmath::tests::proptests::prop_np_clip_nan_propagates
hostmath::tests::proptests::prop_np_maximum_finite
hostmath::tests::proptests::prop_np_maximum_propagates_nan
hostmath::tests::proptests::prop_py_max_min_agree_on_finite
hostmath::tests::proptests::prop_py_max_min_idempotent
hostmath::tests::proptests::prop_py_max_nan_semantics
hostmath::tests::proptests::prop_py_min_nan_semantics
thermal_edges::tests::proptests::prop_max_tj_at_least_ambient
thermal_edges::tests::proptests::prop_measure_deterministic
thermal_edges::tests::proptests::prop_measure_empty_returns_ambient
thermal_edges::tests::proptests::prop_measure_finite_for_finite_inputs
thermal_edges::tests::proptests::prop_pairwise_sum_f32_agrees_naive_below_8
thermal_edges::tests::proptests::prop_pairwise_sum_f32_finite_for_finite
thermal_potential::tests::linspace_proptests::prop_linspace_all_finite
thermal_potential::tests::linspace_proptests::prop_linspace_degenerate_constant
thermal_potential::tests::linspace_proptests::prop_linspace_endpoints_exact
thermal_potential::tests::linspace_proptests::prop_linspace_length_correct
thermal_potential::tests::linspace_proptests::prop_linspace_monotonic_increasing
thermal_potential::tests::linspace_proptests::prop_linspace_single_element_is_start
thermal_potential::tests::field_proptests::prop_build_potential_grid_dimensions
thermal_potential::tests::field_proptests::prop_build_potential_grid_xy_convention
thermal_potential::tests::field_proptests::prop_phi_convection_nan_magnitude_is_nan_field
thermal_potential::tests::field_proptests::prop_phi_convection_zero_or_negative_is_zero
thermal_potential::tests::field_proptests::prop_phi_coupling_empty_is_zero
thermal_potential::tests::field_proptests::prop_phi_coupling_finite_for_moderate_power
thermal_potential::tests::field_proptests::prop_phi_coupling_peaks_at_device
thermal_potential::tests::field_proptests::prop_phi_edge_non_negative_finite
thermal_potential::tests::field_proptests::prop_phi_edge_top_row_is_minimal
thermal_potential::tests::field_proptests::prop_phi_exclusion_non_negative
thermal_potential::tests::uniqueness_proptests::prop_enforce_unique_no_violations
thermal_potential::tests::uniqueness_proptests::prop_enforce_unique_noop_when_already_unique
thermal_potential::tests::uniqueness_proptests::prop_enforce_unique_stays_in_bounds
thermal_potential::tests::uniqueness_proptests::prop_search_free_x_found_within_bounds
thermal_potential::tests::uniqueness_proptests::prop_search_free_x_nan_offset_returns_none
thermal_potential::tests::uniqueness_proptests::prop_search_free_x_non_positive_offset_returns_none
thermal_potential::tests::uniqueness_proptests::uniqueness_distance_uses_pow_not_sqrt_proptest
```

Every one of these seven modules **correctly** carries its own `#[cfg(test)]` on the nested `mod` (verified — this is
the point of contrast with §6): `thermal_edges.rs:335` for instance is `#[cfg(test)]\nmod proptests {`, immediately
inside the already-eligible `mod tests`. That redundant-looking repetition is exactly what
`temper-rust-router-core/src/encoding.rs` is missing (§6).
</details>

<details>
<summary><code>temper-rust-router-core</code> — 23 tests (3 modules: <code>encoding::tests::proptests</code> 5, <code>loop_extractor::classify_py::tests</code> 7, <code>pruning::property_tests</code> 11)</summary>

```
encoding::tests::proptests::prop_clause_indices_in_bounds
encoding::tests::proptests::prop_empty_constraints_no_clauses
encoding::tests::proptests::prop_no_empty_clauses
encoding::tests::proptests::prop_no_tautological_clause
encoding::tests::proptests::prop_output_sizes_consistent
loop_extractor::classify_py::tests::classify_corpus_matches_cpython
loop_extractor::classify_py::tests::classify_is_case_folding_invariant_in_category_and_confidence
loop_extractor::classify_py::tests::classify_malformed_capacitance_raises
loop_extractor::classify_py::tests::parse_applies_unit_multiplier
loop_extractor::classify_py::tests::parse_capacitance_corpus_matches_cpython
loop_extractor::classify_py::tests::parse_capacitance_overflow_saturates_to_inf_like_cpython_float
loop_extractor::classify_py::tests::parse_capacitance_raises_like_cpython_on_malformed
pruning::property_tests::property_collinear_pins
pruning::property_tests::property_dist_zero_when_edge_contains_pin
pruning::property_tests::property_duplicate_pins_dont_break_predicate
pruning::property_tests::property_edge_within_pin_span_is_candidate
pruning::property_tests::property_emst_edges_are_candidates
pruning::property_tests::property_idempotent
pruning::property_tests::property_monotonic_looser_params_include_more
pruning::property_tests::property_predicate_consistent_with_formula
pruning::property_tests::property_span_non_negative
pruning::property_tests::property_symmetric_endpoints
pruning::property_tests::tight_margin_excludes_detour_edge
```

`encoding::tests::proptests` is the *correctly*-excluded sibling of the two `portable-but-missing` tests in §6 — it
genuinely uses `proptest::prelude::*` (`packages/temper-rust-router-core/src/encoding.rs:392`) and belongs in this
class once `encoding.rs` gets the one-line fix demonstrated in §6. `loop_extractor::classify_py::tests` and
`pruning::property_tests` use proptest directly in their own top-level scope (not via an ungated nested submodule),
so they are unaffected by the §6 bug and correctly excluded as-is.
</details>

<details>
<summary><code>temper-constraint-compiler</code> — 9 tests (1 module: <code>type_lattice::proptests</code>)</summary>

```
type_lattice::proptests::p1_join_idempotent
type_lattice::proptests::p2_join_commutative
type_lattice::proptests::p3_join_associative
type_lattice::proptests::p4_join_upper_bound
type_lattice::proptests::p5_meet_idempotent
type_lattice::proptests::p6_meet_commutative
type_lattice::proptests::p7_meet_associative
type_lattice::proptests::p8_absorption_meet_join
type_lattice::proptests::p10_safety_category_display_parse_roundtrip
```
</details>

<details>
<summary><code>temper-quality-oracle</code> — 40 tests (7 modules)</summary>

```
classification::tests::proptests::prop_classify_deterministic
classification::tests::proptests::prop_classify_net_name_never_panics
classification::tests::proptests::prop_classify_nets_preserves_length
classification::tests::proptests::prop_classify_nets_preserves_names
ipc2221::tests::proptests::prop_clearance_covers_input
ipc2221::tests::proptests::prop_clearance_in_known_set
ipc2221::tests::proptests::prop_clearance_monotonic
oracle::tests::proptests::pbt_clearance_monotonicity_adding_component
oracle::tests::proptests::pbt_oracle_deterministic
oracle::tests::proptests::pbt_oracle_empty_board_always_passes
oracle::tests::proptests::pbt_oracle_rejects_invalid_scores
oracle::tests::proptests::pbt_roundtrip_no_panic
placement_metrics::tests::proptests::prop_all_sums_not_nan
placement_metrics::tests::proptests::prop_builtin_differs_from_naive_on_large_cancellation
placement_metrics::tests::proptests::prop_builtin_sum_preserves_negative_zero
placement_metrics::tests::proptests::prop_builtin_sum_single_negative_zero
placement_metrics::tests::proptests::prop_compactness_in_01
placement_metrics::tests::proptests::prop_compactness_single_matches_bbox
placement_metrics::tests::proptests::prop_dual_rail_bounds
placement_metrics::tests::proptests::prop_hv_lv_clearance_in_01
placement_metrics::tests::proptests::prop_loop_area_score_in_01
placement_metrics::tests::proptests::prop_naive_sum_is_plain_fold
placement_metrics::tests::proptests::prop_pairwise_sum_no_nan_for_finite
placement_metrics::tests::proptests::prop_py_max_min_signed_zero
placement_metrics::tests::proptests::prop_py_pow_finite_for_small_operands
placement_metrics::tests::proptests::prop_sums_agree_below_eight
placement_metrics::tests::proptests::prop_thermal_score_in_01
placement_metrics::tests::proptests::prop_zone_compliance_all_true_is_one
placement_metrics::tests::proptests::prop_zone_compliance_in_01
routing_quality::tests::proptests::prop_drc_clean_score_in_20_100
routing_quality::tests::proptests::prop_drc_errors_zero_drc_points
routing_quality::tests::proptests::prop_monotonic_in_completion
routing_quality::tests::proptests::prop_routing_deterministic
routing_quality::tests::proptests::prop_score_in_0_100
routing_quality::tests::proptests::prop_zero_nets_full_efficiency
thresholds::tests::proptests::prop_clearance_count_bounded
thresholds::tests::proptests::prop_empty_config_never_violates
thresholds::tests::proptests::prop_thermal_single_or_empty_yields_no_violations
types::tests::proptests::pbt_netclass_roundtrip
types::tests::proptests::pbt_normalized_score_bounds
```
</details>

<details>
<summary><code>temper-io-types</code> — 55 tests (8 modules)</summary>

```
dsn::proptests::normalize_dsn_is_idempotent
dsn::proptests::normalize_dsn_preserves_data_lines
dsn::proptests::normalize_dsn_produces_is_normalized_true
dsn::proptests::strip_control_chars_is_dsn_normalized_result
dsn_exporter::proptests::natural_sort_key_total_order
dsn_exporter::proptests::py_format_fixed_round_trips_precision
dsn_exporter::proptests::py_round_half_even_idempotent
dsn_exporter::proptests::py_round_half_even_round_trips_sign
dsn_types::proptests::dsn_expression_has_balanced_parens
dsn_types::proptests::format_dsn_arg_float_round_trips_visually
dsn_types::proptests::format_dsn_arg_str_is_properly_quoted
placer_core::placer_compute::proptests::p18_py_max_returns_larger
placer_core::placer_compute::proptests::p19_py_max_returns_one_of_inputs
placer_core::placer_compute::proptests::p20_py_max_nan_first_returns_nan
placer_core::placer_compute::proptests::p21_py_max_nan_second_returns_first
placer_core::placer_compute::proptests::p22_py_max_signed_zero_first_wins
placer_core::placer_compute::proptests::p23_py_min_returns_smaller
placer_core::placer_compute::proptests::p24_py_min_returns_one_of_inputs
placer_core::placer_compute::proptests::p25_py_min_nan_first_returns_nan
placer_core::placer_compute::proptests::p26_py_min_nan_second_returns_first
placer_core::placer_compute::proptests::p27_py_min_signed_zero_first_wins
placer_core::placer_compute::proptests::p28_py_mod_result_in_range
placer_core::placer_compute::proptests::p29_py_mod_congruent
placer_core::placer_compute::proptests::p30_py_mod_idempotent
placer_core::placer_compute::proptests::p31_py_mod_add_b_invariant
placer_core::units::proptests::p1_distance_mm_non_negative
placer_core::units::proptests::p2_distance_mm_symmetric
placer_core::units::proptests::p3_distance_mm_self_is_zero
placer_core::units::proptests::p4_manhattan_non_negative
placer_core::units::proptests::p5_manhattan_symmetric
placer_core::units::proptests::p6_manhattan_ge_euclidean
placer_core::units::proptests::p7_cell_round_trip_quotient
placer_core::units::proptests::p8_round_trip_approximate
placer_core::units::proptests::p9_layer_negative_invalid
placer_core::units::proptests::p10_layer_ge_max_invalid
placer_core::units::proptests::p11_layer_in_range_valid
placer_core::units::proptests::p12_net_id_non_negative_valid
placer_core::units::proptests::p13_net_id_negative_invalid
placer_core::units::proptests::p14_deg_to_rad_monotonic
placer_core::units::proptests::p15_rad_to_deg_monotonic
placer_core::units::proptests::p16_deg_to_rad_zero_is_zero
placer_core::units::proptests::p17_rad_to_deg_zero_is_zero
pyfmt::proptests::py_float_fmt_0_always_integer_form
pyfmt::proptests::py_float_fmt_n_precision_exact
pyfmt::proptests::py_float_fmt_negative_zero
pyfmt::proptests::py_float_fmt_special_values_are_lowercase
stackup_validator::proptests::arg_first_wins_max_selects_correct_index
stackup_validator::proptests::first_wins_max_vs_naive
stackup_validator::proptests::neumaier_sum_agrees_with_naive_on_small_lists
stackup_validator::proptests::neumaier_sum_is_commutative
stackup_validator::proptests::neumaier_sum_non_negative_sum_is_non_negative
stackup_validator::proptests::py_float_str_exponent_is_lowercase
stackup_validator::proptests::py_float_str_no_internal_whitespace
stackup_validator::proptests::py_float_str_round_trips
stackup_validator::proptests::py_float_str_special_values
```
</details>

## 6. `portable-but-missing` — 2 tests, one crate — THIS IS A FINDING

| test | file:line | why it looks excluded, why it isn't |
|---|---|---|
| `encoding::tests::exhaustive_at_most_k_n1_to_n8` | `packages/temper-rust-router-core/src/encoding.rs:330` (`#[test]` at `:329`) | classified `proptest-dev-dependency` by `discover_eligible()`, but uses no proptest itself |
| `encoding::tests::encode_to_cnf_empty_model` | `packages/temper-rust-router-core/src/encoding.rs:374` (`#[test]` at `:373`) | same |

### Root cause

`packages/temper-rust-router-core/src/encoding.rs` declares:

```rust
#[cfg(test)]
mod tests {
    // ... exhaustive_at_most_k_n1_to_n8, encode_to_cnf_empty_model ...

    // --- proptest: encode_to_cnf structural invariants ---

    mod proptests {          // <-- line 388: NO #[cfg(test)] of its own
        #![allow(clippy::expect_used, clippy::unwrap_used)]
        use super::*;
        use proptest::prelude::*;
        // ... 5 proptest! tests ...
    }
}
```

`scripts/gen_wasm_test_registry.py`'s `nested_gated_mask()` only masks a nested submodule out of its parent's "own"
body when that submodule carries **its own** `#[cfg(test)]` (by design — see the function's own docstring: "Only
submodules carrying their own gate are masked... An ungated helper `mod` inside a test module is not a separate
entry, so it stays part of its parent"). `encoding.rs`'s `mod proptests` has no such gate, so its lines — including
`use proptest::prelude::*` — remain part of `tests`'s own scanned body. `discover_eligible()`'s
`proptest-dev-dependency` check (`PROPTEST_USE.search`) then matches against the *whole* `tests` module, and the two
non-proptest tests are excluded along with the five that legitimately need to be.

**Contrast with the class that gets this right** (§5's `temper-thermal` note): `thermal_edges.rs:335` writes
`#[cfg(test)]\nmod proptests {` — a redundant-looking repeat of the gate its own parent already carries, but load-bearing
for exactly this reason. Every one of the other 41 `proptest-dev-dependency` modules across the tier either *is*
itself a proptest-named top-level module (so the question does not arise), or repeats the `#[cfg(test)]` correctly
on its nested form (checked with `find_poisoned2.py`'s "does the module's own top-level body, with every nested
`mod` — gated or not — stripped, itself use proptest" sweep across all nine crates' `proptest-dev-dependency`
entries — `encoding.rs::tests` is the only match).

### Demonstrated, not argued

A throwaway copy of `packages/temper-rust-router-core/src/{lib.rs,encoding.rs}` was made outside the repository
(`/tmp/.../scratchpad/probe_src/`); no tracked file was read from or written to during this probe beyond the initial
`git show <commit>:<path>` copy-out. `scripts/gen_wasm_test_registry.py`'s `discover_eligible()` was imported and
pointed at the copy directly (`G.discover_eligible(Path(".../probe_src"), ("python", "sat"))`).

**Before** (unmodified copy, matching the committed source exactly):

```
encoding.rs tests 7 proptest-dev-dependency
```

**After** adding the single missing line (`#[cfg(test)]` immediately above `mod proptests {`):

```
encoding.rs tests 2 None
encoding.rs proptests 5 proptest-dev-dependency
```

`tests` becomes eligible with exactly its own 2 tests; `proptests` becomes its own, correctly-excluded 5-test entry.
Nothing else changes. This is the generator and its own exclusion predicate correctly discriminating a genuinely
proptest-dependent module from an innocent sibling, once the sibling is gated the same way every other crate's
equivalent nested module already is — the fix is one line, in a file this document does not touch.

### Why nothing caught it

Neither of this tier's two structural gates sees this shape of bug:

- `check_unregistered()` (`scripts/gen_wasm_test_registry.py`'s second gate arm, added after the single-crate U3
  document's `ipc.rs` finding) walks every `#[cfg(test)]` module and fails if one is eligible-but-unlisted. It does
  not fail here because `discover_eligible()` — the same function it calls — already reports `encoding::tests` as
  *excluded*, with a reason. The two agree with each other, and the shared reason is wrong.
- `tools/wasm/r19_compare.py`'s R19 comparison, run nightly, reports `agreement_rate: 1.0` for
  `temper-rust-router-core` (§1) — the same disagreement-based confidence D14 rests the whole self-selection claim
  on. A test that never registers never produces a wasm32 verdict, so it never has anything to disagree with; this
  is the exact "absence is not a signal" argument the single-crate U3 document made about `ipc.rs`, reproduced here
  under a different generator-level cause.

**No fix is applied here.** `temper-rust-router-core` is owned by another agent in this fleet; this document's only
write is itself, per the assigning task's scope boundary.

## 7. `temper-pcl-ir` — measured locally, native-only = 0, and a separate finding: it isn't wired in at all

`temper-pcl-ir` is not one of the six crates the nightly's own header describes (`SIX CRATES, SIX TIERS...`), nor is
it one of the eight in `tools/wasm/wasm_tier_topology.json`'s `tiers` array — despite `scripts/gen_wasm_test_registry.py`
carrying a full `CrateSpec` for it (`CRATES["temper-pcl-ir"]`) and `packages/temper-wasm-test-runner/Cargo.toml`
declaring both `pcl-ir-registry` and `pcl-ir-wasm-test-registry` features with `temper-pcl-ir` as an optional
dependency. The generation and build machinery is complete; nothing in CI or the nightly ever invokes it. This
document reports it as a finding rather than fixing it, for the same reason as §6 — `temper-pcl-ir`'s wiring is
outside this document's scope, and adding it to the topology/workflow is a code change this document does not make.

Measured locally at this document's own snapshot commit (`d1b330b90a149f5effd09c7e63b87deeebdb0261`), since no
nightly artifact exists to reuse:

```
$ cargo test --no-default-features --manifest-path packages/temper-pcl-ir/Cargo.toml
running 2 tests
test key_tests::pair_identity_includes_b_and_is_symmetric ... ok
test tests::all_pcl_kinds_round_trip_deterministically ... ok
test result: ok. 2 passed; 0 failed
Doc-tests: 0 tests

$ python3 scripts/gen_wasm_test_registry.py --crate temper-pcl-ir --census
temper-pcl-ir census: 2 `#[cfg(test)]` modules
  registered: 2 modules, 2 tests
    lib.rs::tests  1
    lib.rs::key_tests  1
  excluded:   0 modules, 0 tests

$ cargo build --release --target wasm32-unknown-unknown --no-default-features \
    --features pcl-ir-wasm-test-registry \
    --manifest-path packages/temper-wasm-test-runner/Cargo.toml
    Finished `release` profile [optimized] target(s) in 8.98s

$ node tools/wasm/run_wasm_tests.mjs <built module> --json wasm_local_pcl-ir.json
  executed        2
  passed          2
  failed          0
```

Both native tests are registered, both pass on wasm32, both native and wasm32 report the same 2 names —
`native_only = 0` by direct set comparison (no `r19_compare.py` run needed; the two 2-element name sets are
identical by inspection). `temper-pcl-ir` has no `python` feature at all (no pyo3 dependency in the crate), and its
one test-module dependency (`serde_json`, used for a round-trip test) is a normal non-optional dependency, not a
dev-dependency — consistent with `CrateSpec`'s own comment for this crate ("No exclusion classes apply here").

## 8. Reproduction

```bash
# 8 of 9 crates: download the nightly's own artifact rather than re-running cargo test nine times.
gh run download 31455191432 -D artifacts

# Per-crate R19 figures (native/wasm32 totals, native_only count) are already in:
#   artifacts/wasm-tier-nightly-local-31455191432/r19_local_<suffix>_86c6a01f_6928b7c8.json
# where <suffix> is drc-rs, geometry, thermal, design-bundle, rust-router-core,
# constraint-compiler, quality-oracle, io-types (tools/wasm/tier_topology.mjs's tierFlagSuffix).

# Classification (this document's own contribution): discover_eligible(), imported read-only.
python3 -c "
import sys; sys.path.insert(0, 'scripts')
import gen_wasm_test_registry as G
spec = G.select_crate('temper-thermal')          # any of the 9
found = G.discover_eligible(G.SRC, spec.absent_features)
for d in found:
    print(d.rel, d.ident, d.tests, d.excluded)
"

# The generator's own second gate arm (module-level portable-but-missing, e.g. ipc.rs's class):
python3 scripts/gen_wasm_test_registry.py --crate temper-rust-router-core --check

# temper-pcl-ir: no nightly artifact exists; reproduce directly (small crate, seconds).
cargo test --no-default-features --manifest-path packages/temper-pcl-ir/Cargo.toml
python3 scripts/gen_wasm_test_registry.py --crate temper-pcl-ir --census

# uv run is required for r19_compare.py itself (system python3 is miniconda 3.9, lacks datetime.UTC):
env -u CONDA_PREFIX uv run --no-sync python3 tools/wasm/r19_compare.py --help
```

## 9. What this licenses, and does not

**Does:** extend U3's enumeration from `temper-drc-rs` alone to all nine registered crates, at named commits, with a
class and file:line citation for every one of the 325 native-only tests the nightly measures (plus the 0 for
`temper-pcl-ir`, measured locally because it has no nightly artifact — itself a finding, §7).

**Does:** find and demonstrate one new `portable-but-missing` instance (`temper-rust-router-core`'s
`encoding::tests`, 2 tests) via a throwaway-copy probe that never touches a tracked file, and explain precisely why
neither of the tier's two structural gates (`check_unregistered()`, the R19 disagreement check) can see it. This is
the evidence the assigning task asked for when it said "the number that matters is `portable-but-missing`" — it is
not zero, and the reason it is not zero is a distinct generator-level mechanism from the one the single-crate U3
document found, not a repeat of the same bug.

**Does not:** fix anything. `temper-rust-router-core`, `temper-geometry`, `temper-thermal`, `temper-constraint-compiler`,
`temper-quality-oracle`, and every other crate this document reads are each owned by another agent in this fleet
per the assigning task's scope boundary; the two `portable-but-missing` tests, and `temper-pcl-ir`'s absence from
the nightly topology, are reported here and left for their owning agents.

**Does not:** validate D14 as written, tier-wide. §0 already narrows this per-crate; tier-wide the answer is the
same shape as the single-crate document's own verdict, generalised: D14's self-selection reasoning is sound for the
323 of 325 tests (99.4%) that are structurally excluded (proptest, integration target, doctest, or an explicit own
`cfg`) — a reviewer can check each in one command, and none of them depend on the R19 comparison having run at all
to be correctly excluded. It remains silent, in exactly the way the single-crate document said it would, about
tests the tier never sees: 2 of 325 are in that category today, found only by reading source, not by any tier
verdict disagreeing with anything.

**Does not:** claim these are the *only* `portable-but-missing` tests in the tier. This document's method (§0.1) is
read-only classification against `discover_eligible()`'s own reasoning, cross-checked by one targeted sweep
(`find_poisoned2.py`) for the *specific* mechanism §6 found (an ungated nested proptest submodule poisoning its
parent). A different mechanism producing a different false exclusion would not be caught by that sweep, and this
document does not claim to have looked for every possible mechanism — only the ones actually observed across the
325 native-only tests in front of it.

**Does not:** license removing any of these nine crates' `cargo test` step from GitHub Actions. 325 of 4,894 tests
(6.6%) have no tier execution today; 260 of them (proptest) permanently, by construction, would lose their only
execution site if the native arm were removed. Phase 5 U4's suite-removal unit is conditioned on U3's artifact
exactly as the single-crate document already established; this artifact extends that condition to the other eight
crates and finds it unmet for `temper-rust-router-core` specifically (2 tests that could run on the tier, do not),
and satisfied — for the reasons D14 gives — for the other eight.

**Does not:** grant merge authority to any tier verdict. R22/R23 durability remains deferred under D10, unchanged
by this document.

## 10. Related

- `docs/plans/2026-08-10-001-feat-wasm-tier-phase5-plan.md` — U3 (this artifact extends it tier-wide), U4 (the
  suite removal it gates), D14, R27.
- `docs/evidence/2026-08-10-wasm-tier-u3-native-only-classification.md` — the single-crate original (`temper-drc-rs`,
  43 native-only, 11 `portable-but-missing`, the `ipc.rs` finding this document's §6 finding is the same *shape* of
  bug as, via a different mechanism).
- `docs/evidence/2026-08-10-wasm-tier-u4-closure-deployed-full-corpus.md` — the artifact-staleness closure that made
  the single-crate enumeration tractable in the first place.
- `.github/workflows/wasm-tier-nightly.yml` — the eight-crate, topology-driven nightly this document's §1–§6 figures
  are read from (run [`31455191432`](https://github.com/BennetLeff/temper/actions/runs/31455191432)).
- `tools/wasm/wasm_tier_topology.json` — the eight-tier topology; `temper-pcl-ir` is conspicuously absent (§7).
- `scripts/gen_wasm_test_registry.py` — `discover_eligible()`, `check_unregistered()`, and the `nested_gated_mask()`
  docstring whose own stated design (masking only *gated* nested submodules) is precisely what §6's finding turns on.
- `tools/wasm/r19_compare.py` — the R19 comparison and name-normalisation logic reused (not reimplemented) throughout
  this document, including the `placeholder`/`scaffold` name-collision caveat in §4.
