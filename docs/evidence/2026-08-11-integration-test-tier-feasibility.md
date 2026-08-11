<!-- provenance: commit=962890548df6be40975bed6d80da8d9d7b5400af dirty=false -->

# Integration tests (`tests/`) on the WASM tier — feasibility, and a recommendation

**Date:** 2026-08-11
**Commit:** `962890548df6be40975bed6d80da8d9d7b5400af` (`origin/main`)
**Tree:** clean at read time (`git status --porcelain` empty)
**Scope:** design only. No Rust, `scripts/gen_wasm_test_registry.py`, workflow, or manifest was modified by
this document. Every crate below is owned by another agent in this fleet; this document's only write is itself.
**Method:** every claim below was read directly from the source files cited (path:line), not from prior
evidence documents. Two prior documents are cross-referenced for the numbers they already established
(`docs/evidence/2026-08-11-native-only-classification-all-crates.md`'s §4 `integration-test-target` table, and
the assigning task's own per-crate `#[test]` count), and one discrepancy in the first was found and is reported
in §5.

## Bottom line

**123 `#[test]` functions live in `tests/` across six crates. 17 of them could physically move into `src/` and
register on the wasm32 tier under the existing mechanism; 9 of those 17 are tests worth having (the rest are
no-op placeholders). The other 106 are blocked by a real dependency — `proptest`, `pyo3`, or an embedded
CPython interpreter — not by their location, and moving them would not change that.**

**Recommendation: option (a), move the 9 real, portable tests into `src/` under `#[cfg(test)]`, using the
crate's existing registration mechanism unmodified. Leave the 8 placeholders and the 106 dependency-blocked
tests native, each for a stated, verified reason.** Option (b) — a separate registry crate for `tests/` — is
rejected: analysed in §6, it turns out to face the *identical* privacy problem the existing mechanism was built
to solve, for no benefit over (a), plus a second compilation unit to keep in sync. Option (c) is what already
applies to 106 of the 123 and is the right call for that majority; it is not a legitimate reason to leave the
other 17 native given (a) is available for them.

| crate | `tests/` total | genuinely portable (real) | portable (placeholder, 0 assertions) | blocked: `proptest` dev-dep | blocked: `python`/pyo3 | blocked: crate is pyo3-native | registered on tier at all? |
|---|---:|---:|---:|---:|---:|---:|---|
| `temper-orchestration` | 51 | 0 | 0 | 0 | 0 | 51 | no |
| `temper-geometry` | 40 | 0 | 0 | 31 | 9 | 0 | yes |
| `temper-constraint-compiler` | 18 | 0 | 5 | 13 | 0 | 0 | yes |
| `temper-rust-router-core` | 11 | 6 | 3 | 2 | 0 | 0 | yes |
| `temper-design-bundle` | 2 | 2 | 0 | 0 | 0 | 0 | yes |
| `temper-drc-rs` | 1 | 1 | 0 | 0 | 0 | 0 | yes |
| **total** | **123** | **9** | **8** | **46** | **9** | **51** | |

`9 + 8 = 17` movable under (a). `46 + 9 + 51 = 106` stay native regardless of which option is chosen.

## 1. What is actually in `tests/`, per crate — read from the files, not inferred

### 1.1 `temper-orchestration` — 51 tests, genuinely integration-level, permanently native

All eleven files (`packages/temper-orchestration/tests/{d1..d7,e3,e4,e6,stages_runner}.rs`) call
`Python::initialize()` / `Python::attach(...)` and construct a fake Python module tree via `pyo3`
(`PyModule::new`, `sys.modules` injection — e.g. `packages/temper-orchestration/tests/d1_stages_runner.rs:98-157`
`install_fakes`) so that `PipelineRunner<BoardState>` can invoke stage objects whose leaf compute is still
Python. This is what the crate is *for* — Wave 4 Python→Rust migration scaffolding that sequences
Rust-implemented pipeline stages while the stage bodies still call into an embedded CPython interpreter — not
tests that happen to sit in the wrong directory. `pyo3` is a non-optional part of every one of the 11 files
(`grep -c pyo3` returns 1–3 per file, 11/11 files) and is the crate's `default` feature
(`packages/temper-orchestration/Cargo.toml`: `default = ["python"]`, `python = ["dep:pyo3"]`).

There is no `--no-default-features` build of this crate that keeps its stage-sequencing tests meaningful:
turning `python` off removes the very Python glue the runner is testing. `pyo3` itself has no
`wasm32-unknown-unknown` target (it links `libpython`, a native shared library) — the same constraint that
makes the wasm tier `--no-default-features` everywhere else. This crate is also **not** in
`scripts/gen_wasm_test_registry.py`'s `CRATES` dict at all today, so unlike the other five, there is no partial
registration to extend.

**Verdict: 0 of 51 portable under any option. Native-only, permanently, by architecture.**

### 1.2 `temper-geometry` — 40 tests, two files, both blocked by dependencies unrelated to location

- `tests/proptest_equivalence.rs` — 31 `#[test]` fns, all inside `proptest! { ... }` blocks (`use
  proptest::prelude::*` at line 9), checking geometric-primitive invariants (`overlap`, `polygon`, `sdf`,
  `transform`, …). This is the same `proptest-dev-dependency` class already tracked as 260 tests tier-wide
  (`docs/evidence/2026-08-11-native-only-classification-all-crates.md` §5) — `proptest` is a
  `[dev-dependencies]` entry, absent from the ordinary (non-test) build the registry compiles into, **whether
  the test module lives in `src/` or `tests/`.** Relocating this file does not change that; a module already in
  `src/` using `proptest` is excluded by `discover_eligible()`'s `PROPTEST_USE` check the same way.
- `tests/test_congestion_tensor.rs` — 9 `#[test]` fns, gated `#![cfg(feature = "python")]` at line 5, exercising
  `CongestionTensor` (`packages/temper-geometry/src/congestion_tensor.rs`). Read that file: `CongestionTensor`'s
  method surface is declared `#[pymethods]` directly (line 39-40) and its own doc comment says why (lines 11-20):
  *"This struct's whole method surface doubles as the pyo3 bridge... no split possible here."* The struct
  literally does not exist in a `--no-default-features` build. Moving the test changes nothing; the type it
  tests isn't compiled.

**Verdict: 0 of 40 portable without a separate, larger refactor (splitting `CongestionTensor`'s plain-Rust data
from its `pyo3` bridge) that is out of scope for a test-location change and belongs, if ever done, to whoever
owns that struct.**

### 1.3 `temper-constraint-compiler` — 18 tests: 13 genuine `proptest`, 5 empty placeholders

- `tests/proptest_provenance.rs` (5), `tests/proptest_tier0_to_tier1.rs` (4), `tests/proptest_tier1_to_tier2.rs`
  (4) — 13 tests, all `proptest!`-based. Same class as §1.2's `proptest_equivalence.rs`: blocked by the
  dev-dependency, not by location.
- `tests/test_provenance.rs`, `tests/test_incremental.rs`, `tests/test_tier0_to_tier1.rs`,
  `tests/test_tier1_to_tier2.rs`, `tests/test_type_lattice.rs` — each file's **entire content** is:
  ```rust
  #[test]
  fn placeholder() {}
  ```
  Five files, five identical no-op tests, verified byte-for-byte identical by `Read`. These are scaffolding left
  over from when each file was created (five test-target files stood up ahead of the tests that were meant to
  fill them), not integration tests in any real sense — nothing is asserted, nothing is exercised.

**Verdict: 0 of 13 `proptest` tests portable (same structural block as `temper-geometry`). 5 of 5 placeholders
are trivially portable — they assert nothing, so "portable" here means only "the harness could call them and
they'd pass," not that doing so adds coverage.**

### 1.4 `temper-rust-router-core` — 11 tests: 6 real portable tests, 3 placeholders, 2 blocked

Four files:

- `tests/test_encoding.rs`, `tests/test_extraction.rs`, `tests/test_types.rs` — each file is, again, exactly
  ```rust
  #[test]
  fn scaffold() {
      // placeholder — full test suite in progress
  }
  ```
  Same shape as §1.3's placeholders. **Correction to a prior document:** the tier-wide classification doc
  (`docs/evidence/2026-08-11-native-only-classification-all-crates.md` §4, table row for
  `temper-rust-router-core`) states *"temper-rust-router-core has two independent `fn scaffold()`"* and its §4
  table lists only `test_encoding.rs` and `test_types.rs` under that name. Reading the tree at this document's
  own commit finds **three** files with `fn scaffold()`: those two plus `test_extraction.rs`
  (`packages/temper-rust-router-core/tests/test_extraction.rs:6`). `git log --oneline -- tests/test_extraction.rs`
  shows its last change predates that document's cited measurement commit (`86c6a01f`) by many commits, so this
  is not a landed-since-then discrepancy — the earlier document undercounted by one file. It does not change
  that document's *totals* (all three collapse to the same `r19_compare.py` name-keyed `"scaffold"` entry either
  way, per its own §4 caveat about name collisions), but it does change the accurate file-level census reported
  here per this task's "verify against the code" instruction.
- `tests/test_loop_extractor.rs` — 8 `#[test]` fns in three modules:
  - `mod proptest_tests` (lines 11-112) — 2 tests, both inside `proptest! { ... }` (`use proptest::prelude::*`,
    line 12). Blocked, same class as §1.2/§1.3.
  - `mod bmc_tests` (lines 116-240) — 4 tests: `bmc_base_case_minimal_half_bridge`,
    `bmc_add_unrelated_component`, `bmc_modify_unrelated_footprint`, `bmc_remove_unrelated_component`. Pure
    computation over in-memory `Component`/`Pin` structs and `auto_extract_loops` (from
    `temper_rust_router_core::loop_extractor::extract`, a public, unconditional (`pub mod loop_extractor` at
    `packages/temper-rust-router-core/src/lib.rs:18`, no feature gate) module). No filesystem, no clock, no
    entropy, no `dlsym`, no `pyo3`.
  - `mod temper_tests` (lines 244-313) — 2 tests: `temper_to247_numeric_pins_work`,
    `temper_no_silent_none` — regression tests pinning real Temper-board component/pin shapes through the same
    `auto_extract_loops`. Same profile: pure computation, no host facility touched.

**Verdict: 6 of 8 `test_loop_extractor.rs` tests (`bmc_tests` + `temper_tests`) are genuine, meaningful,
currently-native-only tests with nothing wasm32-incompatible about them — misplaced, not mis-scoped. 3
placeholder `scaffold()` tests are trivially portable but empty. 2 `proptest_tests` tests are blocked.**

`packages/temper-rust-router-core/src/loop_extractor/extract.rs:441-443` already carries a registered
`#[cfg(any(test, feature = "wasm-registry"))] pub(crate) mod tests { ... }` block (the crate's existing unit
tests for the same module) — so the target this document recommends moving `bmc_tests`/`temper_tests` into
already exists and is already wired into the tier.

### 1.5 `temper-design-bundle` — 2 tests, genuinely portable today, misplaced only

`tests/temper_bundle.rs`, 2 tests:

- `temper_fixture_is_valid_and_deterministic` — parses `elec/exports/temper.design-input.v1.json`,
  `elec/exports/net-name-mapping.v1.yaml`, and `tests/fixtures/temper.pcl.yaml`, all three pulled in via
  `include_bytes!`/`include_str!` (lines 7-9, 24) — a **compile-time** embed, not a runtime filesystem read.
  Nothing about it touches the filesystem, clock, or entropy at test-execution time; it calls `parse_atopile`,
  `parse_mapping`, `parse_pcl`, `build_bundle`, `normalized_json`, `sha256` — all `pub fn` in
  `packages/temper-design-bundle/src/lib.rs`/`serialize.rs`, none behind `#[cfg(feature = "python")]`. `sha256`
  (`packages/temper-design-bundle/src/serialize.rs:3`) is the `sha2` crate (`Cargo.toml:34`, no optional
  feature gate) — pure Rust, no host dependency.
- `authored_safety_weakening_is_fatal` — builds an `AtopileExport`/`PclDocument` in-memory and asserts
  `build_bundle` rejects a safety-weakening constraint. Pure computation, no I/O at all.

`temper-design-bundle` is already a registered, discovered (`eligible=None`) crate
(`CRATES["temper-design-bundle"]` in `scripts/gen_wasm_test_registry.py`), so its library already compiles for
`wasm32-unknown-unknown --no-default-features` today; nothing about these two tests' dependencies is new to the
tier.

**Verdict: 2 of 2 portable. The only thing keeping them off the tier is the `tests/` directory itself.**

### 1.6 `temper-drc-rs` — 1 test, genuinely portable, deliberately placed in `tests/` for a documented reason

`tests/property_containment_gap.rs` — 1 test, `edge_distance_to_reports_nonzero_boundary_gap_for_fully_nested_seed_0`.
Its own doc comment (lines 1-19) explains the placement was **intentional**: it pins a known,
already-characterized geometric edge case (`docs/evidence/2026-08-07-property-campaign-containment-gap.md`) and
the author chose to keep it outside `src/` specifically so it would *not* red the wasm tier's CI gate on every
run. Reading the test itself: it calls `gen_case(0)`, `naive_closest`, `polygon_points` — all `pub fn` in
`packages/temper-drc-rs/src/rules/drc/property_campaigns.rs`. `gen_case` takes a `u64` seed and is verified
deterministic by that same file's own unit tests (`gen_case_is_deterministic_in_seed`,
`gen_case_varies_with_seed` — grep confirms no `rand::thread_rng`, `SystemTime`, or `Instant::now` anywhere in
the file; the PRNG is seeded, not entropy-sourced). No filesystem, clock, or entropy dependency.

`property_campaigns.rs` already has a registered `#[cfg(any(test, feature = "wasm-registry"))] pub(crate) mod
tests` at line 717-719 (and is already in `ELIGIBLE_DRC_RS` as `("rules/drc/property_campaigns.rs", "tests")`
in `scripts/gen_wasm_test_registry.py`), so no `ELIGIBLE` list edit is needed to register this test once moved —
only adding the function itself to the existing module.

**Verdict: 1 of 1 portable. The stated reason for keeping it in `tests/` (don't fail CI loudly for a
characterized, defense-in-depth-covered limitation) is a CI-noise concern, not a wasm32-portability concern —
those are separable, see §7's caveat on this exact point.**

## 2. Which of the 123 could run on `wasm32` at all — the numbers behind the table above

Applying the same four filters the existing registry uses (`proptest` dev-dependency, `#[cfg(feature =
"python")]`/pyo3, filesystem/clock/entropy/`dlsym` at *runtime*, and — for `temper-orchestration` specifically —
an embedded interpreter that is the crate's whole purpose):

| class | count | crates | could ever run on wasm32? |
|---|---:|---|---|
| pure computation, no blocking dependency, real assertions | **9** | router-core (6) | **yes** |
| pure computation, no blocking dependency, zero assertions (`placeholder`/`scaffold`) | **8** | constraint-compiler (5), router-core (3) | **yes, trivially — nothing to fail** |
| pure computation, no blocking dependency, real assertions, compile-time fixture embed | **3** | design-bundle (2), drc-rs (1) | **yes** — folded into the 9 above in the bottom-line table (design-bundle 2 + drc-rs 1 + router-core 6 = 9) |
| `proptest` dev-dependency | **46** | geometry (31), constraint-compiler (13), router-core (2) | no, not without promoting `proptest` to a non-dev dependency (rejected — see §7) |
| `#[cfg(feature = "python")]` / `pyo3`-bridged struct | **9** | geometry (`congestion_tensor`) | no, not without splitting the struct from its `pyo3` bridge |
| crate is pyo3-native by design, embedded CPython interpreter | **51** | orchestration | no, structurally, by what the crate is for |
| **total** | **123** | | **17 could run; 106 cannot without a dependency-level change out of this task's scope** |

(The "9" row is a rollup of router-core's 6 + design-bundle's 2 + drc-rs's 1, shown split by file in §1.)

## 3. Why this is a design decision, not a scan-the-other-directory fix — verified against the generator's own mechanism

`scripts/gen_wasm_test_registry.py`'s own module docstring (lines 9-19) states the constraint precisely: unit
tests live in `#[cfg(test)] mod tests { fn ... }`, where both the module and its functions are private by
default, so the registry's `pub const WASM_TESTS` trick works **only** because it is emitted *inside* that
private module, where the private functions are already in lexical scope (`crate::path::to::tests::WASM_TESTS`
reaches the const, and the const's initializer, written inside the module, can name the private fns directly).

A `tests/*.rs` integration-test file is a **separate crate** at compile time (`cargo test` builds
`packages/<crate>/tests/foo.rs` as its own binary that `extern crate`s the library) — under an ordinary
(non-test) build, that file is not compiled *at all*, not merely privacy-restricted. There is no `crate::` path
from the library's own `wasm-registry`-gated code that reaches into `tests/test_loop_extractor.rs`, because
nothing links that file into the library build in the first place. Pointing `discover_eligible()` at `tests/`
in addition to `src/` (the "scan the other directory" fix) would find the right test names but could not
generate code that compiles — the aggregator lives in a different compilation unit than the tests it would
need to name.

## 4. Options, with trade-offs

### (a) Move qualifying tests into `src/` under `#[cfg(test)]` — **recommended**

**What it costs:** relocating 9 real tests (6 router-core, 2 design-bundle, 1 drc-rs) plus a decision on the 8
placeholders (§7 recommends deleting them, not moving them). For router-core and drc-rs, the destination
`#[cfg(test)] mod tests` blocks already exist and are already registered (`extract.rs:441-443`,
`property_campaigns.rs:717-719`) — this is adding functions to an existing, wired module, not standing up new
machinery. For design-bundle, a new `#[cfg(test)] mod tests` in `src/lib.rs` (or `serialize.rs`, wherever
`build_bundle`/`parse_atopile` are most naturally tested) is auto-discovered by `discover_eligible()`
(`eligible=None` for this crate) — no `ELIGIBLE` list edit needed there either. `temper-drc-rs` is the one crate
on the tier using an explicit list (`ELIGIBLE_DRC_RS`), but the target module is already in that list, so even
there no list edit is needed — only the source file changes.

**What it risks:** for `temper-design-bundle`, the `include_bytes!`/`include_str!` relative paths
(`../../../elec/exports/...`, `fixtures/...`, `golden/...`) are relative to the *declaring file's* path, which
changes when the code moves from `tests/temper_bundle.rs` to `src/lib.rs`. Both files sit at the same depth
under `packages/temper-design-bundle/` (`tests/` and `src/` are siblings), so `../../../elec/exports/...` is
unchanged; `fixtures/temper.pcl.yaml` and `golden/temper.design-bundle.json` need their relative prefix updated
from bare (`tests/fixtures/...` implicit) to `../tests/fixtures/...` (or the fixture/golden files move too — a
judgment call for whoever implements this, not fixed here). This is the only nontrivial mechanical wrinkle
across the whole set; everything else (router-core, drc-rs) has zero external file dependencies to re-path.

**Why this is the right shape:** it reuses a mechanism that is already reviewed, already has a drift gate
(`--check`'s two arms) and an unregistered-module gate (`check_unregistered()`), and asks nothing new of the
generator. The tests that qualify are, definitionally, indistinguishable in content from the 1,708+ unit tests
the tier already runs — the router-core `bmc_tests`/`temper_tests` in particular read like unit tests on a
public function that someone filed under `tests/` because the file predates (or was never reconciled with) the
crate's later unit-test convention, not because the tests are integration-level in any technical sense.

### (b) Teach the generator to compile `tests/*.rs` into a separate registry crate — not recommended

**The privacy problem does not go away — it recurs identically.** `#[test] fn` items inside a `tests/*.rs` file
are private by default, exactly like `src/`'s unit tests (§3). A hypothetical registry crate that pulls in
`tests/test_loop_extractor.rs` via `#[path = "..."] mod test_loop_extractor;` faces the same privacy check
`gen_wasm_test_registry.py`'s docstring describes: an item without `pub` is visible only to its declaring module
and that module's descendants, and the registry aggregator (needing to build a `pub const` array of function
pointers reachable from the *library's* crate root) is not a descendant of `tests/test_loop_extractor.rs`'s
module scope under this scheme. Making it work would require the same "rewrite `#[test]` → `#[cfg_attr(test,
test)]`, raise the module's/functions' visibility" transformation the generator already performs for `src/` —
just aimed at a second location, with a second copy of the same rewrite logic, a second `--check` drift gate to
add per crate, and a second entry point (`main.rs`/`lib.rs` of the new registry crate) that has to be kept
current as `tests/` files are added or removed. It also introduces a second `Cargo.toml` per crate needing this
(or one shared crate depending on all six libraries, coupling their release cadence for zero benefit).

**What it would buy that (a) doesn't:** nothing, for the 17 tests actually at stake here. It would only matter
if a `tests/` file needed something a `src/`-embedded module structurally cannot have — e.g. multiple
compilation units linked together, or `tests/`-only dev-dependencies used in ways `src/` forbids. None of the 17
portable tests need that: they use only the crate's own `pub` API and, for design-bundle, compile-time
`include_bytes!`. Building this machinery to move 17 tests (9 of them real) is a worse cost/benefit than (a) by
a wide margin, and the "second aggregator to keep in sync" risk is exactly the class of bug
(`docs/evidence/2026-08-11-native-only-classification-all-crates.md`'s `ipc.rs` and `portable-but-missing`
findings) this generator's whole design has been hardened against once already.

**Verdict: rejected.** Only reconsider if a future qualifying test genuinely cannot be expressed as a `src/`
`#[cfg(test)]` module (e.g. it needs to link two sibling crates together, which `src/` unit tests cannot do) —
none of the 123 tests examined here are that shape.

### (c) Leave them native, documented — correct for 106 of 123, wrong as a blanket answer

This is already the right call for the `proptest` (46), `python`-gated (9), and `temper-orchestration` (51)
tests — each is blocked by an actual dependency the wasm32 target cannot satisfy, and no amount of relocation
changes that. Documenting *why*, per test class, is valuable and this document is partly that documentation.

**Where it's wrong:** applied to all 123 indiscriminately, it leaves 17 tests off the tier — 9 of them real,
currently-uncovered, wasm32-portable tests — for a reason (`tests/` structural exclusion) that has nothing to
do with their content. That is exactly the gap the assigning task set out to find, and it is real: verified
line-by-line in §1, not inferred from the class name.

## 5. A correction found while doing this work

`docs/evidence/2026-08-11-native-only-classification-all-crates.md` §4's caveat states *"`temper-rust-router-core`
has two independent `fn scaffold()`."* Reading the tree at this document's commit finds **three**:
`test_encoding.rs:6`, `test_extraction.rs:6`, `test_types.rs:7` all declare `fn scaffold() {}` verbatim. `git
log --oneline -- packages/temper-rust-router-core/tests/test_extraction.rs` shows its last change
(`b27851fec`, "extract temper-rust-router-core as pure-Rust rlib") predates that document's own measurement
commit (`86c6a01f`) by many commits — this is not new drift since that document was written, it is an
undercount at the time it was written. It does not change that document's totals (all three names collapse to
one key under `r19_compare.py`'s name-keyed dict, exactly as its own §4 caveat about `constraint-compiler`'s
`placeholder()` describes for that crate) — it changes the file-level census, which is why this document reports
it rather than silently reusing the "two" figure.

## 6. Concrete implementation plan for the recommendation (option (a))

For a later agent to execute once the five agents currently regenerating registries are done and each crate's
owner has signed off. None of this was executed by this document.

1. **`packages/temper-rust-router-core/src/loop_extractor/extract.rs`** — inside the existing
   `#[cfg(any(test, feature = "wasm-registry"))] pub(crate) mod tests { ... }` block (currently ending around
   the crate's existing unit tests), add the 4 `bmc_tests` functions and the 2 `temper_tests` functions from
   `packages/temper-rust-router-core/tests/test_loop_extractor.rs` (lines 116-240 and 244-313), either as nested
   `mod bmc_tests { ... }` / `mod temper_tests { ... }` (preserving their current names, mirroring how
   `proptest_tests` already nests in the same file today) or flattened into the existing `mod tests` — nesting
   is closer to a pure cut/paste and keeps `git blame` legible. Do **not** move `mod proptest_tests` (2 tests,
   blocked — leave it in `tests/test_loop_extractor.rs`, or leave the whole `proptest_tests` submodule in place
   and only extract the two other modules). Delete the moved code from `tests/test_loop_extractor.rs`, leaving
   only `use ...` and `mod proptest_tests { ... }` behind, or restructure the file into a thin re-export if the
   crate owner prefers to keep the file. Then `cargo test -p temper-rust-router-core` (native) and
   `python3 scripts/gen_wasm_test_registry.py --crate temper-rust-router-core` (regenerate; `eligible=None`
   means the new tests are picked up automatically, no `ELIGIBLE` list to edit) and `--check` to confirm no
   drift.

2. **`packages/temper-rust-router-core/tests/test_encoding.rs`, `test_extraction.rs`, `test_types.rs`** — these
   are the 3 empty `scaffold()` placeholders. Recommend deleting them (§7); they assert nothing and moving them
   adds a discovery/registration entry for zero coverage. If the crate owner wants to keep the scaffolding as a
   reminder that real tests are still owed, that's a legitimate call too — but then leave them in `tests/`
   exactly as-is rather than spending registry machinery on a no-op.

3. **`packages/temper-design-bundle/src/lib.rs`** — add a new `#[cfg(test)] mod tests { ... }` (this crate has
   none today) holding `temper_fixture_is_valid_and_deterministic` and `authored_safety_weakening_is_fatal`,
   copied from `packages/temper-design-bundle/tests/temper_bundle.rs`. Update the `include_bytes!`/`include_str!`
   paths: `elec/exports/...` paths (`../../../elec/exports/...`) are unchanged (same depth from `src/` as from
   `tests/`); `fixtures/temper.pcl.yaml` and `golden/temper.design-bundle.json` need `../tests/fixtures/...` and
   `../tests/golden/...` respectively unless those two directories are relocated to sit under `src/` or a
   crate-root `fixtures/`/`golden/` — either is fine, pick one and keep `tests/fixtures`/`tests/golden` as the
   canonical location only if `tests/temper_bundle.rs` itself is deleted (otherwise both copies would need the
   files and that's worse). Delete `tests/temper_bundle.rs` once the move is verified (`cargo test -p
   temper-design-bundle` native, then `python3 scripts/gen_wasm_test_registry.py --crate temper-design-bundle`
   + `--check`).

4. **`packages/temper-drc-rs/src/rules/drc/property_campaigns.rs`** — add
   `edge_distance_to_reports_nonzero_boundary_gap_for_fully_nested_seed_0` to the existing `pub(crate) mod tests`
   at line 719 (no `ELIGIBLE_DRC_RS` edit needed — `("rules/drc/property_campaigns.rs", "tests")` is already
   listed). Preserve the doc comment explaining *why* this is a pinned characterization test, not a "should
   pass" property (it documents a known limitation covered by defense-in-depth elsewhere) — that context is
   exactly as relevant inside `src/` as it was in `tests/`; only the CI-noise argument for keeping it out of
   `src/` (see §7) needs re-examination by the crate owner, not the test itself. Delete
   `packages/temper-drc-rs/tests/property_containment_gap.rs` once moved and verified (`cargo test -p
   temper-drc-rs`, `python3 scripts/gen_wasm_test_registry.py --crate temper-drc-rs --check`).

5. **`packages/temper-constraint-compiler/tests/{test_provenance,test_incremental,test_tier0_to_tier1,
   test_tier1_to_tier2,test_type_lattice}.rs`** — same call as step 2: 5 empty placeholders, recommend deletion
   rather than migration, or leave as-is if the crate owner wants the scaffolding retained.

6. **Do not touch** `temper-geometry/tests/{proptest_equivalence.rs,test_congestion_tensor.rs}`,
   `temper-constraint-compiler/tests/{proptest_provenance,proptest_tier0_to_tier1,proptest_tier1_to_tier2}.rs`,
   `temper-rust-router-core/tests/test_loop_extractor.rs`'s `proptest_tests` module, or any
   `temper-orchestration/tests/*.rs` file — all are correctly native for a stated, dependency-level reason (§1,
   §2), and none of the above steps change any generator code, `ELIGIBLE_DRC_RS` list (except by not needing
   to), or CI workflow.

**Net effect if fully executed: +9 real tests on the wasm32 tier (6 `temper-rust-router-core`, 2
`temper-design-bundle`, 1 `temper-drc-rs`), 8 fewer or unchanged placeholder tests depending on the
deletion call, 106 tests unchanged and correctly native.** This is a small number in absolute terms — smaller
than any of the three blocked classes — which is itself the honest answer to "how much does fixing the `tests/`
gap actually buy": most of what's in `tests/` across this codebase is there because it structurally has to be
(`proptest`, `pyo3`), not because nobody got around to moving it.

## 7. Two things this document deliberately does not resolve

- **`temper-drc-rs`'s CI-noise argument (§1.6) is not primarily a portability argument, and this document does
  not adjudicate it.** The test's own comment says it was kept in `tests/` so a documented, defense-in-depth-
  covered limitation would not fail the wasm tier's gate on every run. If the crate owner still wants that
  property after reading this document — "don't let this specific pinned characterization test red the gate" —
  the registry mechanism already has a tool for exactly that without keeping the test in `tests/`:
  `tools/wasm/wasm_expected_failures_geometry.json`-style expected-failure registration (referenced in
  `scripts/gen_wasm_test_registry.py`'s `temper-geometry` `extra_notes`, used there for `#[should_panic]` tests
  that trap as designed on `wasm32`). This document flags the option; it does not choose between "move it and
  register it live" and "move it and expected-fail it" — that is a judgment call for whoever owns
  `temper-drc-rs`, not a portability question this document's evidence can settle.
- **Whether to promote `proptest` off `[dev-dependencies]` for any of the 46 blocked tests, or split
  `CongestionTensor` from its `pyo3` bridge for the 9 blocked `temper-geometry` tests, is out of scope.** Both
  are real, larger engineering changes (dependency-surface and binary-size implications for the first; an API
  redesign for the second) that the assigning task's own boundaries (read-only against code, no crate is this
  document's to change) correctly exclude. §2's table states the blocking mechanism precisely enough that
  whoever eventually takes either on has a starting point.

## 8. Reproduction

```bash
# Per-crate #[test] counts in tests/
grep -rc '#\[test\]' packages/temper-orchestration/tests/*.rs
grep -rc '#\[test\]' packages/temper-geometry/tests/*.rs
grep -rc '#\[test\]' packages/temper-constraint-compiler/tests/*.rs
grep -rc '#\[test\]' packages/temper-rust-router-core/tests/*.rs
grep -rc '#\[test\]' packages/temper-design-bundle/tests/*.rs
grep -rc '#\[test\]' packages/temper-drc-rs/tests/*.rs

# pyo3 usage in temper-orchestration's integration tests
grep -c pyo3 packages/temper-orchestration/tests/*.rs

# The scaffold() undercount (§5)
grep -rn "fn scaffold" packages/temper-rust-router-core/tests/*.rs
git log --oneline -3 -- packages/temper-rust-router-core/tests/test_extraction.rs

# gen_case's determinism (§1.6)
grep -n "fn gen_case\|rand::\|thread_rng\|SystemTime\|Instant::now" \
  packages/temper-drc-rs/src/rules/drc/property_campaigns.rs

# Existing registered `tests` modules the plan in §6 extends
grep -n "mod tests" packages/temper-rust-router-core/src/loop_extractor/extract.rs
grep -n "mod tests" packages/temper-drc-rs/src/rules/drc/property_campaigns.rs
```

## 9. Related

- `scripts/gen_wasm_test_registry.py` — the mechanism this document's option (a) reuses unmodified; its own
  docstring (lines 9-19) is the primary source for §3's privacy analysis.
- `docs/evidence/2026-08-11-native-only-classification-all-crates.md` — established the 57-of-325
  `integration-test-target` figure across the nine *registered* crates; this document narrows to the six crates
  that actually have a `tests/` directory, adds the unregistered `temper-orchestration` (51, not in that
  document's scope because it isn't registered), and goes one level deeper — file contents, not just counts —
  to answer the portability question that document's method (comparing test *names* between native and wasm32
  runs) could not reach. §5 records one correction found against it.
- `docs/evidence/2026-08-11-host-facility-acquisition-sweep.md` — the closest prior precedent for "the honest
  answer is a small number, not a bug list"; this document's §6 net effect (+9 real tests) is the same shape of
  finding.
