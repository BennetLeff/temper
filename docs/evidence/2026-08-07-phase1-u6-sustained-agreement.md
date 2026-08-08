<!-- provenance: commit=9478209623e068449f9b0bbb6edcba991322b7bd dirty=UNKNOWN -- this measurement spans 10 consecutive origin/main commits (see "Commit Selection" below); the field above names the most recent (#10, the state as-of which this document was written), not a single anchor for the whole sweep -->

# Phase 1 U6 — R19 Sustained Agreement

**Date:** 2026-08-07  
**Tooling:** `tools/wasm/run_wasm_tests.mjs` (per-commit version, `--json` only), `tools/wasm/r19_compare.py` (from branch `origin/wasm/phase1-trackb`, commit `4e26dd0e3`)

## The R19 Agreement Bar

Per the Phase 1 plan §U6:

> Sustained agreement is: All non-expected-fail tests show 100% pass/fail agreement (wasm32 verdict identical to native `cargo test --no-default-features` verdict) across 10 consecutive commits on `origin/main`, AND no expected-fail test produces an unexpected pass or a new failure class that was not in the manifest at the start of the observation window.

## Protocol

For each of 10 consecutive commits on `origin/main`:

1. Checkout the commit.
2. Build: `cargo build --release --target wasm32-unknown-unknown --no-default-features --manifest-path packages/temper-wasm-test-runner/Cargo.toml`
3. Run wasm32 suite: `node tools/wasm/run_wasm_tests.mjs <wasm> --json /tmp/u6_<sha>.json`
4. Run native tests: `cargo test --no-default-features --manifest-path packages/temper-drc-rs/Cargo.toml`
5. Compare: `python3 tools/wasm/r19_compare.py --native-file /tmp/native_<sha>.txt --wasm-json /tmp/u6_<sha>.json --expected-failures tools/wasm/wasm_expected_failures.json --commit <sha> --output /tmp/r19_<sha>.json`
6. Record agreement rate and any disagreements.

All native test runs were measured (not assumed). The native test suite takes ~0.04s per commit; 10 commits × 0.04s = 0.4s total — negligible, so no shortcut was used.

## Commit Selection

The 10 most recent commits on `origin/main` (as of 2026-08-07 ~09:15 UTC) for which the wasm32 build succeeds. All commits are after the wasm build fixes (#879 merged at `1195ffdc6`, #880 merged at `2068c8007`). Every candidate commit built successfully on the first attempt — zero exclusions.

| # | Commit | Date (UTC) | Description |
|---|--------|-----------|-------------|
| 1 | `cdc463746` | 2026-08-06 | Merge PR #876 (wasm/router-unmask) |
| 2 | `ff1aab7a6` | 2026-08-07 | Merge PR #882 (wasm/u9-phase0-verdict) |
| 3 | `5af4e3c01` | 2026-08-06 | measure(wasm): U2 portable surface |
| 4 | `c29e8bc37` | 2026-08-07 | Merge PR #874 (wasm/u2-portable-surface) |
| 5 | `14979d633` | 2026-08-07 | Merge PR #885 (wasm/phase1-plan) |
| 6 | `4052b118d` | 2026-08-07 | docs(wave4): triage constraints_spatial_index.py (#884) |
| 7 | `fc05617d5` | 2026-08-07 | chore: regenerate plans README index (#887) |
| 8 | `60c0d86fb` | 2026-08-07 | feat(wave4): migrate channel_skeleton (#886) |
| 9 | `be7e25538` | 2026-08-07 | wave4: port validation/metrics.py (#889) |
| 10 | `947820962` | 2026-08-07 | fix(baseline): re-record routing block (#890) |

All 10 commits are consecutive in `origin/main`'s history (verified via `git log --oneline --ancestry-path cdc463746..947820962`).

## Per-Commit Results

| # | Commit | Native | Wasm32 Pass | Wasm32 Expected-Fail | Agree-Pass | Expected-Fail | Disagree | Unx-Pass | Native-Only | Wasm32-Only | **Agreement Rate** |
|---|--------|--------|-------------|---------------------|------------|---------------|----------|----------|-------------|-------------|-------------------|
| 1 | `cdc463746` | 95 pass | 91 | 4 | 91 | 4 | 0 | 0 | 0 | 0 | **1.000000** |
| 2 | `ff1aab7a6` | 95 pass | 91 | 4 | 91 | 4 | 0 | 0 | 0 | 0 | **1.000000** |
| 3 | `5af4e3c01` | 95 pass | 91 | 4 | 91 | 4 | 0 | 0 | 0 | 0 | **1.000000** |
| 4 | `c29e8bc37` | 95 pass | 91 | 4 | 91 | 4 | 0 | 0 | 0 | 0 | **1.000000** |
| 5 | `14979d633` | 95 pass | 91 | 4 | 91 | 4 | 0 | 0 | 0 | 0 | **1.000000** |
| 6 | `4052b118d` | 95 pass | 91 | 4 | 91 | 4 | 0 | 0 | 0 | 0 | **1.000000** |
| 7 | `fc05617d5` | 95 pass | 91 | 4 | 91 | 4 | 0 | 0 | 0 | 0 | **1.000000** |
| 8 | `60c0d86fb` | 95 pass | 91 | 4 | 91 | 4 | 0 | 0 | 0 | 0 | **1.000000** |
| 9 | `be7e25538` | 95 pass | 91 | 4 | 91 | 4 | 0 | 0 | 0 | 0 | **1.000000** |
| 10 | `947820962` | 95 pass | 91 | 4 | 91 | 4 | 0 | 0 | 0 | 0 | **1.000000** |

### Stable Metrics Across All 10 Commits

| Metric | Value | Stability |
|--------|-------|-----------|
| Module size | 1,183,876 bytes | Identical across all 10 commits |
| Imports | 0 | Identical |
| Registered tests | 95 | Identical |
| Native pass | 95/95 | Identical |
| Wasm32 pass | 91 | Identical |
| Expected-fail | 4 | Identical |
| Peak linear memory | 1.75 MiB | Identical |
| Expected-failure manifest SHA256 | `534e98b8...` | Identical across all 10 commits |

## Expected-Failure Manifest Stability

The manifest (`tools/wasm/wasm_expected_failures.json`) is byte-identical across all 10 commits:

| Commit | SHA256 |
|--------|--------|
| All 10 | `534e98b834bd724331e82cd610997dc7ed96dd5a5b7bfc82547ac86b2bb47deb` |

The 4 expected-fail tests are:

| Test | Class | Native | WASM32 |
|------|-------|--------|--------|
| `pymath::tests::host_libm_symbols_actually_resolve` | `no-dynamic-loader` | pass | expected-fail |
| `pymath::tests::pow_is_not_a_multiply_or_a_sqrt` | `b7-pow-divergence-absent` | pass | expected-fail |
| `dfm::tests::thermal_via_side_round_absorbs_the_pow_vs_sqrt_divergence` | `b7-pow-divergence-absent` | pass | expected-fail |
| `dfm::tests::via_annular_area_uses_r_times_r_not_pow` | `b7-pow-divergence-absent` | pass | expected-fail |

The manifest did not change across the 10-commit observation window. No expected-fail test produced an unexpected pass at any commit. No new failure classes appeared.

## Build Verification

Every candidate commit was individually checked out and built. All 10 commits built successfully on the first attempt:

```bash
cargo build --release --target wasm32-unknown-unknown --no-default-features \
  --manifest-path packages/temper-wasm-test-runner/Cargo.toml
```

Zero build failures, zero exclusions. The wasm32 build is stable across the entire 10-commit window, including the wave4 commits (#886, #889, #890) that migrated Python code to Rust in other crates — confirming the #879/#880 fixes (making `temper-geometry` optional and gating `copper_reach.rs` pyo3) correctly isolate the wasm32 build from unrelated crate changes.

## Native Test Measurement

All 10 native test runs were **measured** (not assumed). The native suite is 95/95 pass at every commit. Per-commit native test output files:
- `/tmp/native_cdc463746.txt`
- `/tmp/native_ff1aab7a6.txt`
- `/tmp/native_5af4e3c01.txt`
- `/tmp/native_c29e8bc37.txt`
- `/tmp/native_14979d633.txt`
- `/tmp/native_4052b118d.txt`
- `/tmp/native_fc05617d5.txt`
- `/tmp/native_60c0d86fb.txt`
- `/tmp/native_be7e25538.txt`
- `/tmp/native_947820962.txt`

Each contains 97 lines (95 `test ... ok` lines + 2 `test result:` summary lines).

## Verdict

**R19 SUSTAINED.** Agreement rate: 1.000000 across 10 consecutive commits on `origin/main` (span: `cdc463746` through `947820962`).

- Zero disagreements across all 10 commits.
- Zero unexpected passes across all 10 commits.
- Zero native-only or wasm32-only tests — perfect scope match across all 10 commits.
- Expected-failure manifest stable and byte-identical across the window.
- No new failure classes appeared.
- Zero build failures — the wasm32 build remained valid through 3 wave4 Rust-migration merges.

The sustained-agreement evidence licenses later gating under R15 for the 95-test `temper-drc-rs` surface. The agreement bar is met across a window spanning 2,798 lines of changed source (wave4 migrations, wasm-tier documentation, plan merges) — the per-test wasm32-vs-native agreement holds as the code evolves.
