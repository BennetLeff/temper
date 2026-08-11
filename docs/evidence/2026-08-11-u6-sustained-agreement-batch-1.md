<!-- provenance: commit=9743616a0057043758d2652334cee80777bd6759 dirty=false -- this measurement spans 10 consecutive origin/main commits (see "Commit span" below); the field above names the most recent (#1 in the table below), not a single anchor for the whole sweep -->

# U6 sustained-agreement batch 1 — five tiers, 10 commits each

**Date:** 2026-08-11
**Runner:** `tools/wasm/u6_campaign.sh` (branch `tools/u6-campaign-runner`, commit `74e74a8be` — a single commit ahead of pre-batch `origin/main`); this batch's own branch, `docs/u6-campaign-batch-1`, was created directly from that commit. The runner itself is used unmodified.
**Crates measured:** `temper-geometry`, `temper-thermal`, `temper-design-bundle`, `temper-rust-router-core`, `temper-constraint-compiler`
**Definition applied:** R24 (`docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md:112`) — a crate's native `cargo test` suite may leave GitHub Actions once its per-test wasm32 verdicts agree with native, sustained. "Sustained" per §U6 of `docs/plans/2026-08-07-001-feat-wasm-tier-phase1-plan.md`: 100% pass/fail agreement on every non-expected-fail test across 10 consecutive `origin/main` commits, with no expected-fail test producing an unexpected pass.

## Bottom line

All five crates hit **10/10 commits at agreement rate 1.0**. Per the runner's own header comment, **that number is not the interesting one** — it only scores tests present on both sides. The number that decides whether anything can leave CI is `native_only`, and for every one of these five crates it is nonzero and, on inspection, **entirely structural** (proptest dev-dependency, a separate `tests/` integration-test binary, an explicit host-only `cfg`, or a doctest) — the same shape of finding `temper-orchestration`'s own U6 doc already established, not a registry gap. `wasm32_only` is zero everywhere: no scope mismatch in the other direction.

**None of the five crates' native-only sets are a registry gap in this measurement.** One near-miss is worth flagging: `temper-rust-router-core` had a genuine `portable-but-missing` registry bug (`encoding::tests::exhaustive_at_most_k_n1_to_n8`, `encoding::tests::encode_to_cnf_empty_model`) as of `docs/evidence/2026-08-11-native-only-classification-all-crates.md`'s snapshot (`d1b330b9`); it was fixed in commit `58d869ae3` ("fix(router-core): gate encoding.rs proptests submodule…", #977), 88 commits before this batch's window, and is confirmed absent from this measurement's native-only set (§4).

**A correction to the framing this task was given: as of `origin/main` today, none of these five crates has a duplicated native `cargo test` step anywhere in `python-tests.yml` left to delete or narrow.** `temper-geometry` had one, in the `rust-checks` job (which runs on both `push` and PRs touching rust paths); `temper-design-bundle` had one, in the `extended-bundle-workflow-checks` job (trunk-only: push-to-main / nightly / manual-dispatch, never PRs). **Both were already removed on 2026-08-11**, same day as this measurement, for cost reasons (see that file's own "REMOVED 2026-08-11 (cost policy: the deployed WASM tier should run ONLY there, not also in GitHub Actions)" comments at lines 953 and 2427, citing the exact 89/2 native-only counts this document independently reproduces). `temper-thermal`, `temper-rust-router-core`, and `temper-constraint-compiler` never had one anywhere. The only place any of the five still runs native `cargo test` in CI is inside `wasm-tier-nightly.yml`'s own R19 rotation (once per crate every ~9 nights) — that is the comparison's own measurement infrastructure, not a redundant duplicate step, and this document does not touch it (out of scope: `.github/workflows/*`). So for **all five** crates, per-crate verdicts below are about **what a native step would and would not still need to cover if one existed**, not about relief from a cost that is currently being paid — the removal already happened, on cost-policy grounds, ahead of and independent of this document's own R24/U6 measurement.

| crate | commits passed | agreement rate | in-both | native-only | wasm32-only | verdict |
|---|---:|---:|---:|---:|---:|---|
| `temper-geometry` | 10/10 | 1.000000 | 6,316 | 89 | 0 | SUSTAINED (intersection); native-only all structural; PR-path native step already removed 2026-08-11 |
| `temper-thermal` | 10/10 | 1.000000 | 2,695 | 48 | 0 | SUSTAINED (intersection); native-only all structural; never had a PR-path native step |
| `temper-design-bundle` | 10/10 | 1.000000 | 24 | 2 | 0 | SUSTAINED (intersection); native-only all structural; trunk-only native step already removed 2026-08-11 |
| `temper-rust-router-core` | 10/10 | 1.000000 | 3,438 | 32 | 0 | SUSTAINED (intersection); native-only all structural; never had a PR-path native step |
| `temper-constraint-compiler` | 10/10 | 1.000000 | 1,899 | 24 | 0 | SUSTAINED (intersection); native-only all structural; never had a PR-path native step |

"SUSTAINED (intersection)" means: R19 sustained agreement is met for every test the wasm32 registry actually runs. It is **not** a claim that the native `cargo test` step is redundant — see native-only figures and per-crate verdicts below.

## Commit span

10 consecutive `origin/main` commits, oldest to newest, identical set used for all five crates (`git rev-list origin/main -10` at measurement time):

| # | Commit | Date | Description |
|---|--------|------|-------------|
| 10 (oldest) | `8452645c2` | 2026-08-11 | fix(wasm-tier): wire the 3 new tiers into deploy paths + r19 dropdown (#993) |
| 9 | `f997e4ad6` | 2026-08-11 | perf(ci): narrow Python CI triggers off the push-to-main pool (#991) |
| 8 | `36be871cf` | 2026-08-11 | test: pin min-cut (value+partition) bit-exact vs networkx on the bottleneck graph family |
| 7 | `8b11ec5f3` | 2026-08-11 | docs: record bottleneck min-cut petgraph spike — KEEP verdict on measured bit-exact parity |
| 6 | `5747d2df6` | 2026-08-11 | merge: spike/bottleneck-geometry — plan's last conditional item resolved (KEEP, parity verified bit-exact) |
| 5 | `ce1daeba3` | 2026-08-11 | feat(orchestration): migrate Phase-C tail pipeline contracts to Rust (dag_types/dag/bottleneck/metrics) |
| 4 | `5afa6dff3` | 2026-08-11 | test(orchestration): Phase-C-tail differential + PBT + metamorphic suite |
| 3 | `fbb281980` | 2026-08-11 | docs(orchestration): VERIFICATION.md Phase-C residual section + suite lint fixes |
| 2 | `441a4459e` | 2026-08-11 | merge: migrate/phase-c-tail — Phase C residual (dag_types/dag_observability/bottleneck_report/metrics_observer → temper-orchestration) |
| 1 (newest) | `9743616a0` | 2026-08-11 | chore: sync wasm-test-runner lock with the #987 temper-geometry dep |

None of these commits touch the five measured crates' own source directly (the changes are orchestration/bottleneck-geometry work); the campaign is exercising "does agreement hold as the rest of the repo moves," which is exactly what §U6 asks for. All ten builds and native runs succeeded on the first attempt for every crate — zero `CHECKOUT-FAILED`/`WASM-BUILD-FAILED`/`WASM-RUN-FAILED`/`DISAGREE` lines across 50 crate×commit combinations.

Every metric (`agree_pass`, `agree_fail`, `expected_fail`, `disagree`, `unexpected_pass`, `native_only`, `wasm32_only`) was **byte-identical across all 10 commits** for every crate — verified by diffing the `comparison` block of all 10 `r19_<sha>.json` files per crate, not assumed from the runner's one-line summary.

## Per-crate results

### `temper-geometry`

- 10/10, rate 1.000000. `total_in_both=6316` (native total 6,405; wasm32 total 6,316), `native_only=89`, `wasm32_only=0`.
- 8 expected-fail tests, manifest-stable across all 10 commits, zero unexpected-passes: `bottleneck_geometry::tests::test_graph_deadline_fires_only_at_stride` (`deadline-needs-a-clock`), `pad_geometry::tests::pow2_is_exact_where_powi_is_not` (`powi-overflow-divergence-absent`), `projections::tests::test_project_onto_side_invalid_panics` + 3 more `smooth`/`transform` tests (`should-panic-traps`), `transform::tests::test_gumbel_softmax_{high,low}_temp_*` (`no-entropy-source`).
- **Native-only (89), fully classified:**

| class | count |
|---|---:|
| `proptest-dev-dependency` | 55 |
| `integration-test-target` | 31 |
| `cfg-excluded` (host-libm dlsym guards) | 2 |
| `doctest` | 1 |

  The 55 proptest tests span 6 modules (`creepage_check::properties`, `grid_raster::proptests`, `polygon::proptests`, `smooth::proptests`, `units::proptests`, `via_clearance::properties`). The 31 integration-test-target tests are `tests/proptest_equivalence.rs`, a separate compilation unit the registry mechanism cannot reach. The 2 `cfg-excluded` are `host_math::tests::host_libm_symbols_actually_resolve` and `pad_geometry::tests::host_libm_symbols_actually_resolve` — the dlsym-resolves-host-libm guard, definitionally false on wasm32 (no dynamic loader). The 1 doctest is `src/transform.rs:9`.
- This exactly reproduces `docs/evidence/2026-08-11-native-only-classification-all-crates.md`'s own per-crate breakdown for `temper-geometry` (55/31/2/1 = 89), independently re-derived here from this batch's own `native_only_detail`, not copied.
- **Can the native step be deleted, narrowed, or neither?** `temper-geometry`'s native `cargo test` step (`python-tests.yml`'s `rust-checks` job — runs on `push` and on PRs touching rust paths) was **already removed on 2026-08-11**, on cost-policy grounds, citing this exact 89-native-only figure. There is nothing left in the PR/push path to delete today. If it (or a narrowed version) were ever reintroduced, this measurement says: it could be **narrowed** to the 89-test native-only subset rather than restored at full width — the wasm tier already proves the other 6,316 (98.6%) at 10/10 sustained agreement — and 55 of the 89 (proptest) could never be dropped from a native step by construction, since proptest is a dev-dependency absent from the non-test build the registry compiles into.

### `temper-thermal`

- 10/10, rate 1.000000. `total_in_both=2695` (native total 2,743; wasm32 total 2,695), `native_only=48`, `wasm32_only=0`.
- 4 expected-fail tests, manifest-stable, zero unexpected-passes, all `b7-pow-divergence-absent`: `geometric_metrics::tests::pow_used_not_multiplication_in_hypot`, `hostmath::tests::pow_is_not_multiplication`, `thermal_potential::tests::separation_test_uses_pow_not_multiplication`, `thermal_potential::tests::uniqueness_distance_uses_pow_not_sqrt`.
- **Native-only (48), fully classified:**

| class | count |
|---|---:|
| `proptest-dev-dependency` | 47 |
| `cfg-excluded` (host-libm dlsym guard) | 1 |

  The 47 proptest tests span 7 modules: `geometric_metrics::tests::proptests` (4), `heat_removal::tests::proptests` (5), `hostmath::tests::proptests` (9), `thermal_edges::tests::proptests` (6), `thermal_potential::tests::linspace_proptests` (6), `thermal_potential::tests::field_proptests` (10), `thermal_potential::tests::uniqueness_proptests` (7). The 1 `cfg-excluded` test is `device_power::tests::host_libm_symbols_actually_resolve`. Matches the reference classification doc's 47/1 split exactly.
- **Can the native step be deleted, narrowed, or neither?** `temper-thermal` has **no native `cargo test` step in the PR/push path today, and never has** — confirmed against `.github/workflows/wasm-tier-nightly.yml`'s own header, which states `temper-thermal` was the first crate to make the "native arm has to exist per-crate" argument concrete because it had none anywhere before the nightly grew a thermal arm. So there is nothing to delete or narrow; this measurement is evidence about **future coverage**, not present relief. If a PR-path native step were ever added, this batch shows the wasm tier would already cover the 2,695-test intersection at 100% agreement, leaving 48 tests (1.7% of the crate) that would need the native step regardless — all structural (dev-dependency proptest + one host-facility guard).

### `temper-design-bundle`

- 10/10, rate 1.000000. `total_in_both=24` (native total 26, wasm32 total 24), `native_only=2`, `wasm32_only=0`.
- 0 expected-fail tests.
- **Native-only (2), fully classified:** both `integration-test-target` — `authored_safety_weakening_is_fatal` and `temper_fixture_is_valid_and_deterministic`, both from `tests/temper_bundle.rs`, a separate compilation unit the registry mechanism cannot reach. No proptest, no cfg-exclusion, no doctest in this crate's native-only set.
- **Can the native step be deleted, narrowed, or neither?** `temper-design-bundle`'s native `cargo test` step (`python-tests.yml`'s `extended-bundle-workflow-checks` job — trunk-only: push-to-main / nightly / manual-dispatch, never PRs) was **already removed on 2026-08-11**, same cost-policy change as `temper-geometry`'s, citing this exact 24-in-both/2-native-only split. Nothing left to delete today. If reintroduced, it could be **narrowed** to just the 2 native-only integration tests (`tests/temper_bundle.rs`, structurally outside the registry mechanism and never coverable by it) rather than restored at full width — the wasm tier already proves the other 24 (92.3% of the crate) at 10/10 sustained agreement.

### `temper-rust-router-core`

- 10/10, rate 1.000000. `total_in_both=3438` (native total 3,470, wasm32 total 3,438), `native_only=32`, `wasm32_only=0`.
- 0 expected-fail tests.
- **Native-only (32), fully classified:**

| class | count |
|---|---:|
| `proptest-dev-dependency` | 23 |
| `integration-test-target` | 9 |

  Proptest-dev-dependency (23): `encoding::tests::proptests` (5), `loop_extractor::classify_py::tests` (7, uses proptest directly in its own scope), `pruning::property_tests` (11). Integration-test-target (9): `tests/test_loop_extractor.rs`'s `bmc_tests` (4), `proptest_tests` (2), `temper_tests` (2), plus one `fn scaffold()` collapsed across `tests/test_encoding.rs`/`tests/test_types.rs` (1) — `r19_compare.py`'s native map is keyed by bare name with no binary qualifier, so multiple `scaffold`/`placeholder` occurrences across separate integration binaries collapse to one distinct name; this is a known small blind spot in the shared comparison tool, not a classification error (see the reference doc's §4 caveat, reproduced here).
- **The `portable-but-missing` finding from the prior classification doc is gone.** `docs/evidence/2026-08-11-native-only-classification-all-crates.md` (measured at `d1b330b9`, 88 commits before this batch's window) found `encoding::tests::exhaustive_at_most_k_n1_to_n8` and `encoding::tests::encode_to_cnf_empty_model` wrongly excluded (34 native-only, not 32) because the sibling `encoding::tests::proptests` submodule lacked its own `#[cfg(test)]`, poisoning the parent's exclusion reason. Commit `58d869ae3` ("fix(router-core): gate encoding.rs proptests submodule; mirror all 16 proptest properties onto the wasm tier", #977) fixed it — confirmed here because this batch's native-only set contains `encoding::tests::proptests::*` (5, correctly excluded) and no longer contains the two innocent siblings.
- **Can the native step be deleted, narrowed, or neither?** `temper-rust-router-core` has **no native `cargo test` step in the PR/push path today, and never has** (confirmed in `wasm-tier-nightly.yml`'s own header: named alongside `temper-constraint-compiler` as having "none anywhere"). Nothing to delete or narrow; this is a future-coverage measurement. If added, 32/3,470 tests (0.9%) would remain outside the tier — all structural, no registry gap as of this measurement.

### `temper-constraint-compiler`

- 10/10, rate 1.000000. `total_in_both=1899` (native total 1,923, wasm32 total 1,899), `native_only=24`, `wasm32_only=0`.
- 0 expected-fail tests.
- **Native-only (24), fully classified:**

| class | count |
|---|---:|
| `integration-test-target` | 14 |
| `proptest-dev-dependency` | 9 |
| `cfg-excluded` (host-libm dlsym guard) | 1 |

  Integration-test-target (14): `tests/proptest_provenance.rs` (`p1`–`p5`, 5), `tests/proptest_tier0_to_tier1.rs` (`test_tier0_to_tier1_*`, 4), `tests/proptest_tier1_to_tier2.rs` (`test_tier1_to_tier2_*`, 4), and one `fn placeholder()` collapsed across `tests/test_incremental.rs`/`tests/test_provenance.rs`/`tests/test_tier0_to_tier1.rs`/`tests/test_tier1_to_tier2.rs`/`tests/test_type_lattice.rs` (1 — same bare-name-collapse caveat as router-core's `scaffold`). Proptest-dev-dependency (9): `type_lattice::proptests` (`p1`–`p8`, `p10`). `cfg-excluded` (1): `constraints::tests::host_libm_symbols_actually_resolve`.
- **Can the native step be deleted, narrowed, or neither?** `temper-constraint-compiler` has **no native `cargo test` step in the PR/push path today, and never has** (same `wasm-tier-nightly.yml` citation as router-core). Nothing to delete or narrow; future-coverage measurement. If added, 24/1,923 tests (1.2%) would remain outside the tier — all structural.

## Anti-vacuity check — required, not skipped

A campaign that always reports `AGREE` proves nothing about the comparison actually discriminating pass from fail. Verified on `temper-design-bundle` (smallest crate, fastest to inspect by hand):

1. Took `wasm_36be871cf117a2331a6bdb9223983b72e6492d6a.json` (a passing run from this batch) and flipped `constraint_merge::tests::minimum_rules_accept_stronger_authored_values`'s `status` from `"pass"` to `"fail"` under the `results` key, in a scratch copy (`/tmp/claude-1000/-home-bennet-Desktop-temper/c0bf43ed-bc14-4a43-9c79-57bf591cf8ab/scratchpad/antivacuity/wasm_flipped.json`) — the original artifacts under `/tmp/u6-out-temper-design-bundle/` are untouched.
2. Re-ran `r19_compare.py --fail-on-disagree` against the flipped copy, same commit's native output, same expected-failures manifest:

```
$ /usr/bin/python3 tools/wasm/r19_compare.py \
    --native-file /tmp/u6-out-temper-design-bundle/native_36be871cf117a2331a6bdb9223983b72e6492d6a.txt \
    --wasm-json /tmp/claude-1000/-home-bennet-Desktop-temper/c0bf43ed-bc14-4a43-9c79-57bf591cf8ab/scratchpad/antivacuity/wasm_flipped.json \
    --expected-failures /tmp/u6-out-temper-design-bundle/expected.json \
    --commit 36be871cf117a2331a6bdb9223983b72e6492d6a \
    --output /tmp/claude-1000/-home-bennet-Desktop-temper/c0bf43ed-bc14-4a43-9c79-57bf591cf8ab/scratchpad/antivacuity/r19_flipped.json \
    --fail-on-disagree
FAIL: --fail-on-disagree set and 1 disagreement(s) / 0 unexpected-pass(es) found. This is the tier's actual safety property: a wasm32 verdict that disagrees with the same commit's native/CI verdict, or a manifest exclusion that has gone stale, must not report green.
R19 Baseline at commit 36be871cf117a2331a6bdb9223983b72e6492d6a
  Native  : 26 pass, 0 fail (26 tests)
  WASM32  : 23 pass, 1 fail, 0 expected-fail, 0 unexpected
  Agree   : 23 agree-pass, 0 agree-fail, 0 expected-fail
  Disagree: 1 disagreements
  Scope   : 2 native-only, 0 wasm32-only
  Agreement rate: 0.958333
  DISAGREEMENTS:
    constraint_merge::tests::minimum_rules_accept_stronger_authored_values: native=pass, wasm32=fail

Wrote /tmp/claude-1000/-home-bennet-Desktop-temper/c0bf43ed-bc14-4a43-9c79-57bf591cf8ab/scratchpad/antivacuity/r19_flipped.json
EXIT CODE: 1
```

Exit code **1**, the flipped test named exactly, agreement rate correctly dropped from 1.0 to 0.958333 (23/24). The comparison can fail, and does, on an injected disagreement. This batch's 50/50 clean `AGREE` results are therefore evidence, not an artifact of a check that cannot say no.

## Traps hit while reproducing (confirms the runner's own header)

- `r19_compare.py` needs CPython ≥ 3.11 (`datetime.UTC`); the environment's default `python3` (miniconda) is 3.9 and fails at import. `/usr/bin/python3` resolves correctly.
- `--manifest-path`, not `-p`: this repo has no root `Cargo.toml` / workspace, so `-p <crate>` fails from repo root.
- One `CARGO_TARGET_DIR` per crate is load-bearing for concurrency — ran `temper-geometry`/`temper-thermal`/`temper-design-bundle` concurrently, then `temper-rust-router-core`/`temper-constraint-compiler` concurrently, each isolated under `/tmp/u6-target-<crate>`, with no cargo build-lock contention observed.

No new traps beyond the three the runner's header already documents.

## What this does and does not license

**Does:** establish R19 sustained agreement (§U6's numeric bar, 10/10 consecutive `origin/main` commits, 100% agreement on the intersection, zero unexpected-passes) for all five crates, with a fully-classified native-only accounting for every crate — no `NEEDS-MANUAL` residue in any of the five.

**Does not:** license deleting any native `cargo test` step for these five crates in `python-tests.yml` — there currently is none to delete. `temper-geometry` and `temper-design-bundle` each had one until 2026-08-11, on cost-policy grounds, ahead of and independent of this document. `temper-thermal`, `temper-rust-router-core`, and `temper-constraint-compiler` never had one anywhere. For all five, if a native step were reintroduced or added, this measurement says it could be **narrowed** to each crate's native-only subset rather than run at full width — never that it should be dropped entirely, since every crate's native-only set is nonzero. Nothing here touches `wasm-tier-nightly.yml`'s own native arm, which remains the R19 comparison's own measurement infrastructure and is out of this document's scope (`.github/workflows/*`).

**Does not:** claim the native-only sets found here are exhaustive of every possible registry-generator bug — this document classifies by name pattern and known module-level exclusion, matching (and independently reproducing) `docs/evidence/2026-08-11-native-only-classification-all-crates.md`'s per-crate breakdown; it did not re-run that document's `discover_eligible()`-based module scan from scratch.

**Does not:** touch `packages/temper-orchestration/**`, `.github/workflows/*`, or `wasm_tier_topology.json`, per this task's boundaries. No production code was modified; this is a measurement only.

## Reproduction

```bash
git checkout <this branch>
bash tools/wasm/u6_campaign.sh temper-geometry 10 /tmp/u6-out-temper-geometry
bash tools/wasm/u6_campaign.sh temper-thermal 10 /tmp/u6-out-temper-thermal
bash tools/wasm/u6_campaign.sh temper-design-bundle 10 /tmp/u6-out-temper-design-bundle
bash tools/wasm/u6_campaign.sh temper-rust-router-core 10 /tmp/u6-out-temper-rust-router-core
bash tools/wasm/u6_campaign.sh temper-constraint-compiler 10 /tmp/u6-out-temper-constraint-compiler
```

Per-commit `r19_<sha>.json` (comparison matrix, `native_only_detail`/`wasm32_only_detail` included), `native_<sha>.txt` (raw `cargo test` output), and `wasm_<sha>.json` (raw wasm32 run) are written under each crate's output directory by the runner; they are not committed with this document (they total tens of MB across 50 crate×commit runs) but are reproducible in minutes from the commands above.

## Related

- `tools/wasm/u6_campaign.sh` — the runner used, unmodified (branch `tools/u6-campaign-runner`).
- `docs/plans/2026-08-07-001-feat-wasm-tier-phase1-plan.md` §U6 — the numeric definition of "sustained agreement" applied here.
- `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md` — R24's origin.
- `docs/evidence/2026-08-07-phase1-u6-sustained-agreement.md` — the `temper-drc-rs` precedent this batch's protocol follows.
- `docs/evidence/2026-08-11-native-only-classification-all-crates.md` — the tier-wide native-only classification this document's per-crate breakdowns independently reproduce (and, for `temper-rust-router-core`, update: the `portable-but-missing` finding there is fixed as of this batch).
- `.github/workflows/wasm-tier-nightly.yml` — source for which of the five crates ever had a native `cargo test` step anywhere in `python-tests.yml` (`temper-geometry`, `temper-design-bundle`: yes, until removed 2026-08-11; `temper-thermal`, `temper-rust-router-core`, `temper-constraint-compiler`: never, confirmed in that workflow's own header comment) and the only place any of the five still runs native `cargo test` today (its own R19 rotation).
- `.github/workflows/python-tests.yml` lines 911–979, 2417–2443 — the removal itself: `temper-orchestration`'s native step stayed (still live at line 924); `temper-geometry`'s (lines 953–978) and `temper-design-bundle`'s (lines 2426–2442) were commented out 2026-08-11, each comment citing the same native-only counts (89, 2) this document independently re-measures.
