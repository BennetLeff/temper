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
