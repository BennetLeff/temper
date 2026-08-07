# R3 WASM CI Guard — Regression guard (U3)

**Date:** 2026-08-07
**Base:** `origin/main` @ `f8982e155700f8c224ad1d4944f1905bf94e92fa`
**Branch:** `wasm/u3-ci-guard`
**Unit:** U3 "The regression guard — one step, zero new job slots" of
`docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md`

---

## 1. What U3 delivers

Two steps appended to the existing `rust-checks` job in
`.github/workflows/python-tests.yml`, not a new job. The repo's binding CI
constraint is job count (~24-job ceiling against ~40 requested per push);
these steps add runner-minutes but zero new job slots.

**Step 1 — Install wasm32 target:**
```bash
rustup target add wasm32-unknown-unknown
```

**Step 2 — WASM32 build + clippy:**
```bash
# Build (not check — check cannot see link failures from unsafe extern "C" { fn dlsym })
cargo build --release --target wasm32-unknown-unknown --no-default-features \
  --manifest-path packages/temper-drc-rs/Cargo.toml
cargo build --release --target wasm32-unknown-unknown --no-default-features \
  --manifest-path packages/temper-geometry/Cargo.toml

# Clippy with --no-default-features (python OFF — the wasm config)
cargo clippy --manifest-path packages/temper-drc-rs/Cargo.toml \
  --no-default-features --all-targets -- -D warnings
cargo clippy --manifest-path packages/temper-geometry/Cargo.toml \
  --no-default-features --all-targets -- -D warnings
```

Both steps carry `if: ${{ !cancelled() && steps.setup.outcome == 'success' }}`,
matching every existing gate step in the job. They are placed after the last
existing step (`Test temper-geometry (cargo test)`) and before the
`board-provenance-requirements-gates` job.

---

## 2. Local verification transcript (green)

All commands verified on darwin/arm64, `rustc 1.92.0`, wasm32 target installed.
Run from repo root with `CARGO_TARGET_DIR=/private/tmp/wasm-u3-target`.

### 2a. wasm32 build (cargo build, not check)

```
$ cargo build --release --target wasm32-unknown-unknown --no-default-features \
    --manifest-path packages/temper-drc-rs/Cargo.toml
   Compiling temper-geometry v0.1.0
   Compiling temper-drc-rs v0.1.0
    Finished `release` profile [optimized] target(s) in 14.40s
```

```
$ cargo build --release --target wasm32-unknown-unknown --no-default-features \
    --manifest-path packages/temper-geometry/Cargo.toml
   Compiling temper-geometry v0.1.0
    Finished `release` profile [optimized] target(s) in 0.95s
```

### 2b. clippy --no-default-features

```
$ cargo clippy --manifest-path packages/temper-drc-rs/Cargo.toml \
    --no-default-features --all-targets -- -D warnings
   Compiling temper-geometry v0.1.0
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 5.06s
```

```
$ cargo clippy --manifest-path packages/temper-geometry/Cargo.toml \
    --no-default-features --all-targets -- -D warnings
   Compiling temper-geometry v0.1.0
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 1.23s
```

Both exit 0.

### 2c. Production host build still works

```
$ cargo check --manifest-path packages/temper-drc-rs/Cargo.toml --all-targets
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 8.94s
$ cargo check --manifest-path packages/temper-geometry/Cargo.toml --all-targets
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 6.84s
```

### 2d. 45-minute budget estimate

The `rust-checks` job has a 45-minute timeout. The two new steps add:
- `rustup target add wasm32-unknown-unknown`: ~5-15s (cached if already installed)
- wasm32 builds (2 crates, ~15-30s each on warm cache)
- clippy --no-default-features (2 crates, ~5-10s each on warm cache)

Estimated total addition: ~45-120s against a 45-minute budget. The existing
clippy loop across 14 manifests already dominates with ~20-30 minutes. The
wasm32 steps do not threaten the budget and the plan's "zero new job slots but
+runner-minutes" claim holds.

---

## 3. Source fixes made for U3

Four changes were required before the CI guard would pass green. Three were
clippy-cleanup from the `--no-default-features` configuration (the plan's
predicted "expect this to be red on first run" from #659). One was a genuine
missing `#[cfg(feature = "python")]` guard — the exact regression class U3
exists to catch.

### 3a. `copper_reach.rs` — missing `#[cfg(feature = "python")]` (genuine regression)

**File:** `packages/temper-geometry/src/copper_reach.rs`
**Added by:** commit `5802bcdf5` (PR #863, feat(wave4): migrate _copper_reach_mm to Rust)
**Root cause:** The module used `use pyo3::prelude::*` and
`use pyo3::types::PyModule` at the top level with no `#[cfg]` guard, and
lib.rs declared `pub mod copper_reach;` without `#[cfg(feature = "python")]`.
This module was added AFTER U2's measurement (U2 ran at `f2c5af948b`; this
landed at `5802bcdf5`), so U2 did not see it. This is the exact regression
class U3 exists to catch.

**Fix:** Added `#[cfg(feature = "python")]` to the two `use pyo3` lines, the
`#[pyfunction]` wrapper `copper_reach_mm_py`, and the `register` function.
The pure kernel (`copper_reach_mm`, `cpython_max`, `PadRow`) remains un-gated.

### 3b. temper-drc-rs/Cargo.toml — transitive pyo3 pull via temper-geometry

**File:** `packages/temper-drc-rs/Cargo.toml`
**Change:** `temper-geometry = { path = "../temper-geometry", default-features = false }`
**Reason:** temper-drc-rs's dependency on temper-geometry previously used default
features, which includes `python` (and transitively `pyo3`). The only Rust-level
import from temper-geometry in the crate is
`deterministic_connectivity.rs:21` (`drc_constraints_geometry`), which lives
behind `#[cfg(feature = "python")]`. With `--no-default-features`, temper-drc-rs
does not need temper-geometry at all, so `default-features = false` is correct
for both configs.

### 3c. temper-geometry lib.rs — conditional dead_code allow

**File:** `packages/temper-geometry/src/lib.rs`
**Added:** `#![cfg_attr(not(feature = "python"), allow(dead_code))]`
**Reason:** When `--no-default-features` deactivates `python`, the pyo3-bridge
code (each module's `register`, `*_py` functions) is not compiled. ~70 functions
reachable ONLY through those bridges then appear dead to clippy. This conditional
allow suppresses them in the wasm config while keeping warnings active in the
production (python ON) build.

### 3d. organizational_geometry.rs — approx_constant lint

**File:** `packages/temper-geometry/src/organizational_geometry.rs`
**Changes:**
1. `#[allow(clippy::approx_constant, reason = "...")]` on `PY_PI_APPROX` (line 81)
2. `#[allow(clippy::approx_constant, reason = "...")]` on test `test_circle_offsets_uses_hardcoded_pi_not_std_pi` (line 456)
**Reason:** Both use `3.14159` deliberately to match CPython's
`_place_module_components` precision, not as typos. Documented in source comments.

### 3e. test_congestion_tensor.rs — gating integration test behind python feature

**File:** `packages/temper-geometry/tests/test_congestion_tensor.rs`
**Added:** `#![cfg(feature = "python")]` at the top
**Reason:** This integration test imports `CongestionTensor` from a
`#[cfg(feature = "python")]`-gated module. Without this guard,
`cargo test --no-default-features` fails to compile this test target.
Previously recorded in U2's evidence (§5.1) as a known gap.

---

## 4. Anti-vacuity demonstration

### 4a. Planted break

Added to `packages/temper-drc-rs/src/rules/mod.rs` (an un-gated module in the
`--no-default-features` build):

```rust
pub fn planted_unix_call() -> u64 {
    use std::os::unix::fs::MetadataExt;
    std::fs::metadata("does_not_exist").ok().map(|m| m.size()).unwrap_or(0)
}
```

`std::os::unix` does not exist on `wasm32-unknown-unknown`.

### 4b. Red transcript

```
$ cargo build --release --target wasm32-unknown-unknown --no-default-features \
    --manifest-path packages/temper-drc-rs/Cargo.toml

error[E0433]: failed to resolve: could not find `unix` in `os`
   --> src/rules/mod.rs:456:21
    |                  ^^^^ could not find `unix` in `os`

error[E0599]: no method named `size` found for struct `Metadata` in the current scope
   --> src/rules/mod.rs:457:56
    |                                                        ^^^^ method not found

Some errors have detailed explanations: E0433, E0599.
error: could not compile `temper-drc-rs` (lib) due to 2 previous errors
```

### 4c. Reversion

The planted break was reverted before commit. The guard is confirmed capable
of biting.

---

## 5. Container image pre-install opportunity

The `rust-checks` job runs on `ghcr.io/bennetleff/temper-ci:latest`, built by
`.github/docker/ci.Dockerfile` + `.github/workflows/docker-build.yml`. The
Dockerfile's Rust toolchain installation currently does:

```dockerfile
RUN curl ... | sh -s -- -y --default-toolchain stable --profile minimal \
    && /root/.cargo/bin/rustup component add clippy
```

Adding `&& /root/.cargo/bin/rustup target add wasm32-unknown-unknown` after
the `clippy` line would pre-install the wasm32 target in the image, saving
~5-30s of `rustup target add` per CI run. This is a follow-up opportunity
— out of scope for U3 (no image build/push here).

---

## 6. actionlint

```
$ SHELLCHECK_OPTS='--severity=error' actionlint \
    -ignore 'constant expression "false" in condition' \
    .github/workflows/python-tests.yml

(no output — clean)
```

---

## 7. Commit checklist

- [x] `scripts/assert-base.sh origin/main` passes (HEAD == f8982e155)
- [x] wasm32 build (both crates): green
- [x] clippy --no-default-features (both crates): green
- [x] Production host build (cargo check): green
- [x] Anti-vacuity planted break: caught, reverted
- [x] actionlint: clean
- [x] No new job created (two steps appended to existing `rust-checks`)
- [x] No `git stash` used
