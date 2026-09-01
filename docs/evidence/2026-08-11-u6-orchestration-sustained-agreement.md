<!-- provenance: commit=1bdfd7b6a82ec86fc3953e0c6c44e6a0c9494e42 dirty=UNKNOWN -->
# U6 — R19 Sustained Agreement for `temper-orchestration`

**Date:** 2026-08-11
**Crate:** `temper-orchestration`
**Bar:** 10 consecutive `origin/main` commits at 100% agreement (Phase 1 licensing bar,
`docs/plans/2026-08-07-001-feat-wasm-tier-phase1-plan.md` §U6)
**Tooling:** `tools/wasm/u6_campaign.sh` (this commit), `tools/wasm/r19_compare.py`,
`tools/wasm/run_wasm_tests.mjs`
**Verdict:** **MET for the intersection — 10/10 at `agreement_rate: 1.0`.**
**But R24 is NOT satisfied.** See "What this does and does not license".

---

## Result

| # | commit | rate | in both | disagree | unexpected-pass | native-only |
|---|--------|------|--------:|---------:|----------------:|------------:|
| 1 | `f997e4ad6` | 1.0 | 83 | 0 | 0 | 46 |
| 2 | `8452645c2` | 1.0 | 83 | 0 | 0 | 46 |
| 3 | `269eb08b9` | 1.0 | 83 | 0 | 0 | 46 |
| 4 | `5d905eba3` | 1.0 | 83 | 0 | 0 | 46 |
| 5 | `41b1d2aae` | 1.0 | 83 | 0 | 0 | 46 |
| 6 | `352f2d767` | 1.0 | 83 | 0 | 0 | 46 |
| 7 | `8ef690387` | 1.0 | 83 | 0 | 0 | 46 |
| 8 | `c1efdb242` | 1.0 | 83 | 0 | 0 | 46 |
| 9 | `7eb02f61b` | 1.0 | 83 | 0 | 0 | 46 |
| 10 | `b2134e34c` | 1.0 | 83 | 0 | 0 | 46 |

`wasm32_only` was 0 on every commit — no test exists on the tier that is absent
natively, which is the direction that would indicate a registry naming tests
that the crate does not actually have.

## Protocol

For each of the 10 commits, in a detached worktree with a shared
`CARGO_TARGET_DIR`:

1. `cargo build --release --target wasm32-unknown-unknown --manifest-path packages/temper-wasm-test-runner/Cargo.toml --no-default-features --features orchestration-wasm-test-registry`
2. `node tools/wasm/run_wasm_tests.mjs <wasm> --json … --expected-failures tools/wasm/wasm_expected_failures_orchestration.json`
3. `cargo test --no-default-features --manifest-path packages/temper-orchestration/Cargo.toml --lib`
4. `r19_compare.py --fail-on-disagree`

The measurement apparatus (`r19_compare.py`, the expected-failures manifest, the
runner) is pinned to HEAD and held **fixed** across all 10 commits; only the code
under test varies. That matches the `temper-drc-rs` U6 precedent
(`docs/evidence/2026-08-07-phase1-u6-sustained-agreement.md`), which ran
`r19_compare.py` from a branch against 10 historical commits.

`--lib` on the native arm is load-bearing, not a convenience: all 11 of this
crate's `tests/*.rs` integration files import `pyo3` and do not compile under
`--no-default-features`, and cargo refuses to run **any** target — including the
lib — when another requested target fails to build. Without `--lib` the native
arm runs zero tests and the comparison is against nothing.

## Anti-vacuity

A campaign that cannot fail proves nothing. Taking commit 1's passing
`wasm_*.json` and flipping exactly one result from `pass` to `fail`:

```
FAIL: --fail-on-disagree set and 1 disagreement(s) / 0 unexpected-pass(es) found.
  Native  : 129 pass, 0 fail (129 tests)
  WASM32  : 82 pass, 1 fail, 0 expected-fail, 0 unexpected
  Disagree: 1 disagreements
  Agreement rate: 0.987952
  DISAGREEMENTS:
    channel_mapping::tests::find_paren_groups_matches_regex_semantics: native=pass, wasm32=fail
EXIT=1
```

The gate drops off 1.0, names the offending test, and exits nonzero. The 10/10
above is therefore a measurement, not a tautology.

## What this does and does NOT license

**`agreement_rate: 1.0` is the less interesting half of this result.** It says
every test present on *both* sides agreed. A test with no wasm32 counterpart
cannot disagree, because it is not there to disagree.

The crate's native lib suite is **129** tests. The tier carries **83**. The
**46** native-only tests break down as:

| count | module | class |
|------:|--------|-------|
| 10 | `timing::proptests` | `proptest-dev-dependency` |
| 7 | `copper_length::proptests` | `proptest-dev-dependency` |
| 7 | `host_math::proptests` | `proptest-dev-dependency` |
| 6 | `phased_assignment_stage::proptests` | `proptest-dev-dependency` |
| 6 | `zone_aware_slot_generation_stage::proptests` | `proptest-dev-dependency` |
| 3 | `clearance::proptests` | `proptest-dev-dependency` |
| 3 | `grid_stage::proptests` | `proptest-dev-dependency` |
| 3 | `phased_component_assignment_validator_stage::proptests` | `proptest-dev-dependency` |
| 1 | `host_math::tests::host_libm_symbols_actually_resolve` | host-facility (dlsym) |

This is a **structural** gap, not a registry defect: `proptest` is a
dev-dependency and cannot compile into the registry's non-test build, and the
dlsym test asserts a native-host property that wasm32 genuinely does not have.
45 of the 46 are mirrorable by the deterministic `SplitMix64` campaign pattern
used elsewhere in this repo; the dlsym test is permanently native.

**And the 129 is not the whole crate either.** `--lib` excludes `tests/*.rs`
entirely — a further **51** `#[test]`s across 11 pyo3-bound integration files.
The CI step at `.github/workflows/python-tests.yml:924` runs with *default*
features, so it covers 129 lib + 51 integration ≈ 180 tests.

So, precisely:

- **R19 sustained agreement: MET** at the Phase 1 bar, for the 83-test intersection.
- **R24 (the step leaves GitHub Actions): NOT met.** The tier proves 83 of ~180
  tests. Deleting `python-tests.yml:924` today would silently drop ~97 tests.
- **What IS licensed: narrowing.** The native step no longer needs to re-run the
  83 tier-covered tests. Its irreducible residual is the 51 pyo3 integration
  tests plus the dlsym test — genuinely CPython-bound work, which is the
  intended end state rather than a gap to close.

## Follow-ups

1. Mirror the 45 proptests onto the tier (deterministic campaign equivalents,
   keeping the native randomized proptests). That takes native-only 46 → 1.
2. Narrow `python-tests.yml:924` to its irreducible residual once (1) lands.
3. The bar used here is the **Phase 1 licensing bar of 10 commits**. The plan
   notes it "can be raised later (e.g., to 50 commits for Phase 5 gating) if the
   maintainer wants a stronger bar", and removing a native step is Phase 5 work.
   10 was the bar chosen for this campaign.

## Reproduce

```
bash tools/wasm/u6_campaign.sh temper-orchestration 10
```
