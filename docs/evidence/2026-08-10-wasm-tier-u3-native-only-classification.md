<!-- provenance: commit=3b87c2e05b89a21aad4ac72ce9d7cb5b641c0049 dirty=false -->

# WASM tier U3 — the 43 native-only tests, enumerated and classified

**Date:** 2026-08-10
**Commit:** `3b87c2e05b89a21aad4ac72ce9d7cb5b641c0049` (`origin/main`)
**Board:** `pcb/temper.kicad_pcb` sha256 `6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64`
**Unit:** U3 of `docs/plans/2026-08-10-001-feat-wasm-tier-phase5-plan.md` (R27, D14)
**Measurement:** local reproduction of `wasm-tier-nightly.yml`'s `local-sweep-r19`
job — native `cargo test`, local wasm32 build, `tools/wasm/r19_compare.py`.

## Bottom line

D14 says the wasm-incompatible subset "self-selects via the R19 comparison"
without upfront classification. Enumerated at 43 tests, **that claim holds for
32 of them and fails for 11.**

| class | count | self-selects correctly? |
|---|---:|---|
| `proptest-dev-dependency` — test module `use`s `proptest`, which is a `[dev-dependencies]` entry and is therefore not in the dependency graph of the non-test build the registry is compiled into | 31 | yes — structurally uncompilable |
| `integration-test-target` — test lives in `tests/`, a separate crate the registry's in-module `pub const` mechanism cannot reach | 1 | yes — structurally unreachable, and documented in the test's own module docstring |
| **`portable-but-missing`** — nothing prevents registration; the module is simply absent from `ELIGIBLE` | **11** | **no** |
| **total** | **43** | |

**Portable-but-missing: 11.** All eleven are `ipc::tests::*`. They are not
wasm-incompatible in any sense. Added to the registry in a throwaway copy of the
crate (§4), all eleven compile for `wasm32-unknown-unknown` and **all eleven
pass** there. They are absent from the tier because `src/ipc.rs` was added to
the crate on 2026-08-09 (commit `840543e4`, the `temper-ipc` crate-fold) without
being added to `scripts/gen_wasm_test_registry.py`'s `ELIGIBLE` list — and the
registry's own drift gate cannot see that, because it only checks modules that
are already in `ELIGIBLE`.

This is the failure mode D14 traded away the classification pass to avoid, and
it is the reason U3 asks for the enumeration. A test that never enters the
registry never produces a tier verdict, so it can never *disagree* — it is
invisible to the exact mechanism that was supposed to catch it. **Absence is
not a signal in a comparison that only compares what is present.**

## 1. Reproduction and the numbers

Run at `3b87c2e0`, clean tree, `x86_64-unknown-linux-gnu` host:

```
cargo test --no-default-features --manifest-path packages/temper-drc-rs/Cargo.toml 2>&1 | tee native_raw.txt
grep '^test ' native_raw.txt > native.txt

cargo build --release --target wasm32-unknown-unknown --no-default-features \
  --features wasm-test-registry \
  --manifest-path packages/temper-wasm-test-runner/Cargo.toml
node tools/wasm/run_wasm_tests.mjs \
  target-shared/wasm32-unknown-unknown/release/temper_wasm_test_runner.wasm \
  --json wasm_local.json

uv run --no-sync python tools/wasm/r19_compare.py \
  --native-file native.txt --wasm-json wasm_local.json \
  --expected-failures tools/wasm/wasm_expected_failures.json \
  --commit 3b87c2e05b89a21aad4ac72ce9d7cb5b641c0049 \
  --board-sha256 6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64 \
  --output r19.json
```

Result — identical to the U4 closure document's figures, independently
reproduced:

```
Native  : 1751 pass, 0 fail (1751 tests)
WASM32  : 1704 pass, 0 fail, 4 expected-fail, 0 unexpected
Agree   : 1704 agree-pass, 0 agree-fail, 4 expected-fail
Disagree: 0 disagreements
Scope   : 43 native-only, 0 wasm32-only
Agreement rate: 1.000000
```

The native side is two test targets plus doc-tests: `src/lib.rs` (1,750
tests), `tests/property_containment_gap.rs` (1 test), doc-tests (0). The 43
are `r19_compare.py`'s `comparison.native_only_detail` verbatim — name
normalisation is that script's own (`parse_native_output` strips the leading
`test ` and the ` ... <status>` suffix; the registry emits the bare module
path), reused rather than reimplemented.

`uv run` is required: `tools/wasm/r19_compare.py` imports `datetime.UTC`, which
the system `python3` (miniconda 3.9) does not have.

### A note on what is *not* in the 43

The wasm registry's module docstring
(`packages/temper-drc-rs/src/wasm_test_registry.rs`) says:

> Only modules that survive `--no-default-features` appear here. Tests inside
> `#[cfg(feature = "python")]` modules are structurally absent from a `wasm32`
> build and are censused in the Phase 0 report instead.

True, but it does not explain any part of this gap, and reading it as the
expected cause of a native/wasm32 count difference is a mistake. `temper-drc-rs`
declares `default = []` (`Cargo.toml:47`), so `python` is off on **both** arms:
the native arm of the R19 comparison is itself `--no-default-features`. Every
`#[cfg(feature = "python")]` test module — `router_clearance`, `violation_report`,
`clearance_matrix`, `deterministic_connectivity`, `deterministic_leaf_drc`,
`drc_marshal`, `drc_oracle`, `drc_oracle_marshal`, `oracle_marshal` — is absent
from the native list too, and so cannot appear in `native_only`. **Zero of the
43 are pyo3-gated.** The same applies to `ELIGIBLE`'s own comment
(`scripts/gen_wasm_test_registry.py:80-83`), which offers the pyo3 gate as the
reason the list is what it is; that reason is real for those modules but covers
none of the 43, and it is the only stated reason in the file.

Likewise, none of the 43 are host-libm or dynamic-loader dependent. Those
tests — the four in `tools/wasm/wasm_expected_failures.json`
(`b7-pow-divergence-absent` ×3, `no-dynamic-loader` ×1) — *are* registered, *do*
execute on wasm32, and *do* fail there, exactly as that manifest's own comment
argues they should ("a test excluded from the registry is invisible, whereas one
listed here is executed, observed to fail, and carries its reason"). They are
counted in the 1,708, not in the 43. The 43 contain no expected-failure classes
at all.

## 2. Class `proptest-dev-dependency` — 31 tests

**Evidence.** `proptest = "1"` is declared under `[dev-dependencies]`
(`packages/temper-drc-rs/Cargo.toml:84-85`). The registry is compiled by
`cargo build --features wasm-test-registry` — an ordinary library build, not a
test target — and Cargo does not put dev-dependencies in the graph for that
build. Any test module whose body names `proptest` therefore cannot compile
into the registry at all.

**Demonstrated, not assumed** (§4, probe 2): adding all three `proptests`
modules to a throwaway copy of `ELIGIBLE` makes the generator emit 1,739
registered tests (1,708 + 31 — so the generator's `#[test]` scanner *does*
find them), and the wasm32 build then fails:

```
error[E0433]: cannot find module or crate `proptest` in this scope
   --> .../src/pymath.rs:652:9
652 |     use proptest::prelude::*;
    |         ^^^^^^^^ use of unresolved module or unlinked crate `proptest`
error: cannot find macro `proptest` in this scope
   --> .../src/pymath.rs:660:5
```

(and the same pair for `ipc.rs` and `validation_kernels.rs`).

This class self-selects honestly under D14 in the strongest possible sense: the
subset cannot be included even by mistake. Note also that each of these modules
has a *sibling* `tests` module in the same file that **is** registered
(`pymath::tests`, `validation_kernels::tests`), so the exclusion is precisely
scoped to the proptest-bearing module, not to the file.

| test | file:line | gate |
|---|---|---|
| `ipc::proptests::p1_current_capacity_non_negative` | `packages/temper-drc-rs/src/ipc.rs:204` | `#[cfg(test)] mod proptests` @ `:175`; `use proptest::prelude::*` @ `:178` |
| `ipc::proptests::p2_current_capacity_monotone_in_width` | `src/ipc.rs:217` | same module |
| `ipc::proptests::p3_current_capacity_monotone_in_temp_rise` | `src/ipc.rs:234` | same module |
| `ipc::proptests::p4_external_carries_more_than_internal` | `src/ipc.rs:252` | same module |
| `ipc::proptests::p5_min_trace_width_non_negative` | `src/ipc.rs:270` | same module |
| `ipc::proptests::p6_min_trace_width_monotone_in_current` | `src/ipc.rs:282` | same module |
| `ipc::proptests::p7_internal_needs_wider_than_external` | `src/ipc.rs:300` | same module |
| `ipc::proptests::p8_trace_width_round_trip` | `src/ipc.rs:318` | same module |
| `ipc::proptests::p9_net_current_non_negative` | `src/ipc.rs:337` | same module |
| `pymath::proptests::p1_py_max_returns_larger` | `packages/temper-drc-rs/src/pymath.rs:669` | `#[cfg(test)] mod proptests` @ `:648`; `use proptest::prelude::*` @ `:651` |
| `pymath::proptests::p2_py_max_returns_one_of_inputs` | `src/pymath.rs:680` | same module |
| `pymath::proptests::p3_py_max_nan_first_returns_nan` | `src/pymath.rs:689` | same module |
| `pymath::proptests::p4_py_max_nan_second_returns_first` | `src/pymath.rs:697` | same module |
| `pymath::proptests::p5_py_min_returns_smaller` | `src/pymath.rs:708` | same module |
| `pymath::proptests::p6_py_min_returns_one_of_inputs` | `src/pymath.rs:717` | same module |
| `pymath::proptests::p7_py_min_nan_first_returns_nan` | `src/pymath.rs:724` | same module |
| `pymath::proptests::p8_py_min_nan_second_returns_first` | `src/pymath.rs:730` | same module |
| `pymath::proptests::p9_py_round_to_int_is_integer` | `src/pymath.rs:740` | same module |
| `pymath::proptests::p10_py_round_to_int_diff_at_most_half` | `src/pymath.rs:748` | same module |
| `pymath::proptests::p11_py_round_to_int_ties_to_even` | `src/pymath.rs:758` | same module |
| `pymath::proptests::p12_py_hypot_non_negative` | `src/pymath.rs:777` | same module |
| `pymath::proptests::p13_py_hypot_symmetric` | `src/pymath.rs:783` | same module |
| `pymath::proptests::p14_py_hypot_ge_max_abs` | `src/pymath.rs:789` | same module |
| `pymath::proptests::p15_py_hypot_zero_returns_abs` | `src/pymath.rs:797` | same module |
| `validation_kernels::proptests::p1_infer_package_type_is_known` | `packages/temper-drc-rs/src/validation_kernels.rs:417` | `#[cfg(test)] mod proptests` @ `:399`; `use proptest::prelude::*` @ `:401` |
| `validation_kernels::proptests::p2_tht_no_violations_when_distant` | `src/validation_kernels.rs:427` | same module |
| `validation_kernels::proptests::p3_tht_violation_message_has_both_refs` | `src/validation_kernels.rs:442` | same module |
| `validation_kernels::proptests::p4_min_clearance_non_negative` | `src/validation_kernels.rs:463` | same module |
| `validation_kernels::proptests::p5_min_clearance_symmetric` | `src/validation_kernels.rs:474` | same module |
| `validation_kernels::proptests::p6_fingerprint_contains_code_and_message` | `src/validation_kernels.rs:486` | same module |
| `validation_kernels::proptests::p7_fingerprint_order_invariant` | `src/validation_kernels.rs:500` | same module |

**Residual risk, stated plainly.** These 31 are structurally excluded, not
verified-equivalent. None of the three modules overrides `ProptestConfig`, so
each of the 31 runs proptest's default 256 generated cases natively — roughly
7,900 randomised float evaluations per run, across exactly the kernels
(`pymath::py_max`/`py_min`/`py_round_to_int`/`py_hypot`, `ipc`'s `powf`-based
IPC-2221/2152 formulas, `validation_kernels`' clearance math) whose wasm32-vs-native
float behaviour the whole tier exists to check. The wasm32 arm never runs any of
it. This is a real, permanent coverage asymmetry between the two arms, and it is
*not* something the R19 comparison can report on. Removing `temper-drc-rs`'s
`cargo test` from GitHub Actions would delete the only place these 31 tests run.
That is a fact about what U4-style suite removal costs, independent of whether
the removal is otherwise justified.

## 3. Class `integration-test-target` — 1 test

| test | file:line | gate |
|---|---|---|
| `edge_distance_to_reports_nonzero_boundary_gap_for_fully_nested_seed_0` | `packages/temper-drc-rs/tests/property_containment_gap.rs:35` (`#[test]` @ `:34`) | none — the whole file is a `cargo test` integration target, compiled as its own crate |

**Evidence.** The registry works by emitting a `pub const WASM_TESTS` *inside*
each test module, because the `#[test]` functions are private to their module
(`scripts/gen_wasm_test_registry.py`, module docstring). `ELIGIBLE` is a list of
paths relative to `packages/temper-drc-rs/src/`, and an integration test in
`tests/` is a separate crate that links the library — the mechanism cannot reach
it, and no amount of `ELIGIBLE` editing would change that.

This is stated at the top of the test file itself
(`tests/property_containment_gap.rs:6-20`):

> This file is a native `cargo test` integration test, deliberately NOT under
> `src/` — `scripts/gen_wasm_test_registry.py`'s `ELIGIBLE` list only scans
> specific `src/` files, so this test is structurally outside the wasm tier's
> registry and can never be picked up by it. That placement is intentional […]
> it is a *known, characterized* limitation covered by defense-in-depth
> elsewhere in the rule registry […] not something that should red the wasm
> tier's CI gate every run.

This is what a correct exclusion looks like: a stated reason, in the file, at
the exclusion site. It is the only one of the 43 that has one.

## 4. Class `portable-but-missing` — 11 tests — **THIS IS A FINDING**

| test | file:line | gate |
|---|---|---|
| `ipc::tests::test_estimate_external_1oz_10c` | `packages/temper-drc-rs/src/ipc.rs:98` | `#[cfg(test)] mod tests` @ `:93` — module not in `ELIGIBLE` |
| `ipc::tests::test_estimate_internal_conservative` | `src/ipc.rs:104` | same module |
| `ipc::tests::test_estimate_from_net_class` | `src/ipc.rs:110` | same module |
| `ipc::tests::test_min_trace_width_roundtrip` | `src/ipc.rs:116` | same module |
| `ipc::tests::test_ipc2152_min_width_basic` | `src/ipc.rs:125` | same module |
| `ipc::tests::test_ipc2152_current_capacity_roundtrip` | `src/ipc.rs:136` | same module |
| `ipc::tests::test_get_net_current_exact` | `src/ipc.rs:145` | same module |
| `ipc::tests::test_get_net_current_case_insensitive` | `src/ipc.rs:152` | same module |
| `ipc::tests::test_get_net_current_substring` | `src/ipc.rs:158` | same module |
| `ipc::tests::test_get_net_current_fallback` | `src/ipc.rs:164` | same module |
| `ipc::tests::test_get_net_current_zero_current` | `src/ipc.rs:169` | same module |

### Why these are portable

- `pub mod ipc;` is **unconditional** at `src/lib.rs:95` — no `cfg`. The kernels
  under test are already compiled into every deployed `.wasm` module; only their
  tests are not.
- The module's dependencies are `std::collections::HashMap`, `std::sync::LazyLock`,
  `f64::powf`, and `str::to_uppercase` (`src/ipc.rs:11-12`). No pyo3, no
  `proptest`, no filesystem, no clock, no `dlsym`.
- The tests are plain `#[test] fn` bodies with `assert!`/`assert_eq!` over
  tolerance-bounded float comparisons — the same shape as the 1,708 tests that
  already run on the tier.

### Demonstrated, not argued

`git archive`-style throwaway copies of `packages/temper-drc-rs`,
`packages/temper-wasm-test-runner`, and `scripts/gen_wasm_test_registry.py` were
made outside the repository; only the *copies* were edited. No tracked file was
modified to produce this evidence.

**Probe 1** — add `("ipc.rs", "tests")` to the copied `ELIGIBLE`:

```
$ python scripts/gen_wasm_test_registry.py
wrote registry: 1719 tests across 33 modules      # 1708 + 11
  updated packages/temper-drc-rs/src/ipc.rs
  updated packages/temper-drc-rs/src/wasm_test_registry.rs

$ cargo build --release --target wasm32-unknown-unknown --no-default-features \
    --features wasm-test-registry --manifest-path .../temper-wasm-test-runner/Cargo.toml
    Finished `release` profile [optimized] target(s) in 8.83s

$ node tools/wasm/run_wasm_tests.mjs <probe>.wasm --json wasm_probe.json
  passed            1715
  failed            0
  expected-fail     4  (native-only properties; see manifest)
  unexpected-pass   0  (stale exclusions)
```

All 11 `ipc::tests::*` present, all 11 `pass`. Nothing about wasm32 excludes
them.

**Probe 2** is the contrast case in §2 — the same edit for the `proptests`
modules does not compile. The generator and the wasm32 target are both perfectly
capable of telling a genuinely-incompatible module from a portable one. Nothing
asked them the question about `ipc`.

### How they went missing, and why nothing caught it

`src/ipc.rs` was created by `840543e4` (2026-08-09, *"refactor: move temper-ipc
IPC kernels into temper-drc-rs (milestone 1/4)"*). That commit touched neither
`scripts/gen_wasm_test_registry.py` nor
`packages/temper-drc-rs/src/wasm_test_registry.rs`. The intent at the time was
not to exclude them — `lib.rs:91-94` says the opposite:

> `ipc` holds the pure kernels **and their unit tests** (unconditional, like the
> other DRC kernels)

"like the other DRC kernels" is precisely the set that *is* registered.

The generator's `--check` mode is described as the gate that prevents this:

> `--check` is the gate: it regenerates into memory and fails if the committed
> registry has drifted from the actual `#[test]` functions, so a test added to
> an eligible module cannot silently stay out of the Worker tier.

Read the last eight words. The gate is scoped to *eligible* modules — it
iterates `ELIGIBLE` and compares. A test added to a module that is not in
`ELIGIBLE` is not drift; it is invisible. Run today, at the commit where 11
portable tests sit outside the tier, the gate is green:

```
$ python scripts/gen_wasm_test_registry.py --check
wasm test registry up to date: 1708 tests across 32 modules
```

Two independent gaps compound here, and both should be recorded:

1. **The drift gate has no "new module" arm.** It never enumerates
   `#[cfg(test)] mod` declarations under `src/` and compares that set against
   `ELIGIBLE`. Doing so is cheap — this document's §1 analysis is a `grep` — and
   would have failed `840543e4`.
2. **The drift gate is not in CI.** No file under `.github/workflows/` invokes
   `scripts/gen_wasm_test_registry.py --check` or `scripts/regen_derived.py`;
   the only invocation is the `regen-check` target in `Makefile:265-266`, run by
   hand. `wasm-tier-nightly.yml` is the only workflow that mentions the registry
   at all, and it consumes it rather than checking it.

**No fix is applied here.** `scripts/gen_wasm_test_registry.py` and the
workflows are owned by other units; this document is the evidence, not the
repair.

## 5. What this licenses and does not license

**Does:** satisfy the enumeration half of U3's evidence-of-closure — "a list of
self-selected wasm-incompatible tests with a class per entry" — for the 43
native-only tests at `3b87c2e0`. Every one of the 43 now carries a class and a
file/line/gate citation, and 32 of them carry a *structural* reason that a
reviewer can check in one command.

**Does:** independently reproduce the U4 closure document's R19 figures
(1,751 native / 1,708 wasm32 / 43 native-only / 0 disagreements / agreement 1.0)
from a clean tree at a named commit, on a different host architecture
(`x86_64-linux` here vs. the `aarch64` baseline in
`tools/wasm/wasm_expected_failures.json`'s comment). The four expected failures
reproduce with the same classes.

**Does not:** validate D14 as written. D14 chose self-selection over an upfront
classification pass on the reasoning that "a test whose tier verdict never
agrees with its GitHub Actions verdict never leaves." That reasoning is sound
for tests the tier *runs*. It is silent about tests the tier never sees, and
11 of 43 are in that category today. R27 says a test whose tier verdict never
agrees stays on GitHub Actions; it does not say what happens to a test that has
no tier verdict at all, and the comparison cannot distinguish "wasm-incompatible"
from "never registered." Any future use of D14 needs a companion invariant —
*every `#[cfg(test)]` module under `src/` is either in `ELIGIBLE` or carries a
stated reason at the exclusion site* — enforced by a gate, in CI. Only the
integration test in §3 meets that bar today.

**Does not:** license removing `temper-drc-rs`'s `cargo test` from GitHub
Actions, nor any U4 suite removal that would rely on the tier to cover this
crate. 43 of 1,751 tests (2.5%) have no tier execution, 31 of them permanently
by construction, and removing the native arm would delete their only execution
site. Phase 5 U4's own text already conditions removal on U3's artifact; this
artifact says the condition is not met for `temper-drc-rs`.

**Does not:** re-open the question of whether the 4 expected failures are
correctly classified. They are registered, executed, and observed — the
bidirectional gate in `run_wasm_tests.mjs` covers them, and it reported 0
unexpected passes in every run in this document.

**Does not:** grant merge authority to any tier verdict. R22/R23 durability
remains deferred under D10.

## 6. Related

- `docs/plans/2026-08-10-001-feat-wasm-tier-phase5-plan.md` — U3 (this
  artifact), U4 (the suite removal it gates).
- `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md` — R27
  (line 115), D14 (line 58).
- `docs/evidence/2026-08-10-wasm-tier-u4-closure-deployed-full-corpus.md` — the
  1,605 → 43 collapse that made this enumeration tractable, and the document
  that names U3 as the follow-on.
- `tools/wasm/wasm_expected_failures.json` — the 4 registered-and-failing tests,
  which are *not* among the 43.
- `scripts/gen_wasm_test_registry.py:80-118` — the `ELIGIBLE` list and its
  stated rationale.
- `packages/temper-drc-rs/src/lib.rs:89-95` — the crate-fold comment stating the
  `ipc` unit tests were meant to be treated "like the other DRC kernels."
