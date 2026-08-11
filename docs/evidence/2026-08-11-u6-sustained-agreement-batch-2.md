<!-- provenance: commit=2dcc1f7880628dfbf8fedbb4f9c09ea0cfbeac2d dirty=false -- this measurement spans the 10 origin/main commits listed in "Commit span" below; the field above names the worktree HEAD this document was written from (branch docs/u6-campaign-batch-2, one commit ahead of origin/main: the cherry-picked tools/wasm/u6_campaign.sh runner), not a single anchor for the sweep itself. -->

# U6 — R19 Sustained Agreement, Batch 2 (six crates)

**Date:** 2026-08-11
**Bar:** 10 consecutive `origin/main` commits at 100% agreement (R24 / Phase 1
licensing bar, `docs/plans/2026-08-07-001-feat-wasm-tier-phase1-plan.md` §U6)
**Tooling:** `tools/wasm/u6_campaign.sh` (cherry-picked from `tools/u6-campaign-runner`,
commit `74e74a8be980c65b360ee18a5257ddde137b14c2`, unmodified), `tools/wasm/r19_compare.py`,
`tools/wasm/run_wasm_tests.mjs`
**Crates:** `temper-quality-oracle`, `temper-io-types`, `temper-constraints`,
`temper-rust-router`, `temper-pcl-ir`, `temper-drc-rs`

---

## Result

All six campaigns ran against the **same** 10-commit span (`git rev-list origin/main -10`
at the time this batch started), all 10/10, all `agreement_rate: 1.0`. Per the runner's
own header: **`agreement_rate: 1.0` is not the interesting number.** It means every test
present on *both* sides agreed — a test with no wasm32 counterpart cannot disagree,
because it is not there. The number that decides whether a native `cargo test` step can
leave (or, for these six, never needs to join) GitHub Actions is `native_only`.

| crate | commits passed | agreement rate | in-both | native-only | wasm32-only | verdict |
|---|---:|---:|---:|---:|---:|---|
| `temper-pcl-ir` | 10/10 | 1.0 | 2 | **0** | 0 | Tier fully covers the crate. |
| `temper-rust-router` | 10/10 | 1.0 | 20 | **3** | 0 | Intersection agrees; 3 proptests are permanently native-only. |
| `temper-constraints` | 10/10 | 1.0 | 29 | **13** | 0 | Intersection agrees; 13 (12 integration-test-target + 1 host-facility) permanently native-only. |
| `temper-quality-oracle` | 10/10 | 1.0 | 2,601 | **41** | 0 | Intersection agrees; 41 (40 proptest + 1 host-facility) permanently native-only. |
| `temper-io-types` | 10/10 | 1.0 | 6,633 | **55** | 0 | Intersection agrees; 55 proptests permanently native-only. |
| `temper-drc-rs` | 10/10 | 1.0 | 3,281 | **32** | 0 | Intersection agrees; **32 unchanged since 2026-08-10 despite corpus nearly doubling** — see §2. |

`wasm32_only` is **0 for every crate, on every one of the 10 commits** (checked
programmatically against all 60 `r19_*.json` files, not eyeballed) — no scope mismatch
in the direction that would mean the registry names a test the crate doesn't actually
have.

## Commit span

All six campaigns compared the same 10 consecutive `origin/main` commits (`git rev-list
origin/main -10`, taken once at the start of this batch and reused — the crate-specific
inputs vary per campaign, the commit span does not):

| # | commit | date (local) | subject |
|---|--------|---------------|---------|
| 1 | `8452645c2` | 2026-08-11 09:27 | fix(wasm-tier): wire the 3 new tiers into deploy paths + r19 dropdown (#993) |
| 2 | `f997e4ad6` | 2026-08-11 09:27 | perf(ci): narrow Python CI triggers off the push-to-main pool (#991) |
| 3 | `36be871cf` | 2026-08-11 09:14 | test: pin min-cut (value+partition) bit-exact vs networkx on the bottleneck graph family |
| 4 | `8b11ec5f3` | 2026-08-11 10:34 | docs: record bottleneck min-cut petgraph spike — KEEP verdict on measured bit-exact parity |
| 5 | `5747d2df6` | 2026-08-11 10:39 | merge: spike/bottleneck-geometry — plan's last conditional item resolved (KEEP, parity verified bit-exact) |
| 6 | `ce1daeba3` | 2026-08-11 11:00 | feat(orchestration): migrate Phase-C tail pipeline contracts to Rust (dag_types/dag/bottleneck/metrics) |
| 7 | `5afa6dff3` | 2026-08-11 11:07 | test(orchestration): Phase-C-tail differential + PBT + metamorphic suite |
| 8 | `fbb281980` | 2026-08-11 11:09 | docs(orchestration): VERIFICATION.md Phase-C residual section + suite lint fixes |
| 9 | `441a4459e` | 2026-08-11 11:17 | merge: migrate/phase-c-tail — Phase C residual (dag_types/dag_observability/bottleneck_report/metrics_observer → temper-orchestration) |
| 10 | `9743616a0` | 2026-08-11 11:18 | chore: sync wasm-test-runner lock with the #987 temper-geometry dep |

None of these 10 commits touch any of the six crates measured here directly (they are
orchestration/geometry/CI-plumbing changes) — that is expected: `in_both` and
`native_only` are constant across all 10 commits for every crate in this batch (see the
per-crate tables below), consistent with a span where the crate under test did not
change. This is not a defect in the measurement: R19 sustained agreement is defined over
whatever `origin/main` produces in a 10-commit window, not over windows guaranteed to
touch the crate — see the Phase 1 plan §U6's own reasoning for why 10 commits (not 10
crate-touching commits) is the bar.

## Protocol (per crate, per commit)

1. `cargo build --release --target wasm32-unknown-unknown --manifest-path packages/temper-wasm-test-runner/Cargo.toml --no-default-features --features <tier>-wasm-test-registry`
2. `node tools/wasm/run_wasm_tests.mjs <wasm> --json … --expected-failures <tier-manifest>`
3. `cargo test <native_test_args from wasm_tier_topology.json>` (per-crate `--manifest-path`, `--no-default-features`; `temper-constraints`/`temper-rust-router`/`temper-quality-oracle`/`temper-io-types`/`temper-drc-rs`/`temper-pcl-ir` need no `--lib` — none of their `tests/*.rs` integration files reference pyo3, unlike `temper-orchestration`'s)
4. `r19_compare.py --fail-on-disagree`

The expected-failures manifest and comparison tooling are pinned to this branch's HEAD
and held fixed across all 10 commits per crate (same protocol as the `temper-orchestration`
U6 precedent, `docs/evidence/2026-08-11-u6-orchestration-sustained-agreement.md`).

Each crate ran in its own `CARGO_TARGET_DIR` (`/tmp/u6-target-<crate>`), so campaigns
were run concurrently in two batches of three (`temper-pcl-ir` + `temper-constraints` +
`temper-rust-router`, then `temper-quality-oracle` + `temper-io-types` in the same window,
then `temper-drc-rs` alone once the others finished — it is the largest corpus by a wide
margin and was left to run without contention).

---

## 1. Per-crate native-only triage

### `temper-pcl-ir` — 0 native-only

Registered 2, executable 2, native 2. Confirms the maintainer's own smoke test (rate 1.0,
native_only 0 at 2 commits) at the full 10-commit bar. The tier's corpus and the crate's
native corpus are identical name-for-name — nothing to triage.

### `temper-rust-router` — 3 native-only, all `proptest-dev-dependency`

```
proptests::p1_f32s_round_trip
proptests::p2_output_length_input_div_4
proptests::p3_zero_bytes_decode_to_zero
```

All three live in a `#[cfg(test)] mod proptests` that `use`s the `proptest` crate, a
`[dev-dependencies]` entry absent from the non-test build the wasm registry compiles
into — structurally uncompilable into the tier, same class and same count
`tools/wasm/wasm_tier_topology.json`'s own `_comment` already predicted for this crate
("`cargo test --no-default-features` runs 23: the wasm32 registry's 20 plus 3
`proptests::*` tests"). Measured count matches the topology comment exactly.

### `temper-constraints` — 13 native-only, two classes

| count | class | detail |
|---:|---|---|
| 9 | `integration-test-target` (proptest-based) | `tests/shared_ir_adapter_pbt.rs` — 9 `proptest!`-generated tests (`adjacent_preserves_every_field`, `aligned_preserves_every_field`, `anchored_preserves_region_and_position`, `enclosing_preserves_every_field`, `invalid_enum_strings_err_not_panic`, `keepout_always_errs_explicitly`, `loop_area_preserves_every_field`, `onside_some_distance_is_preserved_none_becomes_infinity`, `separated_preserves_every_field`) |
| 3 | `integration-test-target` (plain) | `tests/shared_ir_adapter.rs` — 3 plain `#[test]` fns, no proptest; still unreachable because the wasm registry's `pub const WASM_TESTS` mechanism only scans `src/`, never `tests/` |
| 1 | host-facility (dlsym) | `ipc::tests::host_libm_symbols_actually_resolve` — `#[cfg(not(target_arch = "wasm32"))]`, asserts `dlsym` resolution, definitionally false on wasm32 |

**This is a correction, not a new finding, against `wasm_tier_topology.json`'s own
`_comment`**, which states for `temper-constraints`: "registered 30, executable 29... The
30th ... carries its own `#[cfg(not(target_arch = "wasm32"))]` ... a plain `cargo test
--no-default-features` ... runs cleanly for both (30/30 ... 0 failed)." That text is
accurate for the crate's `src/` lib tests alone (30 registered-module tests, 29 of which
execute on wasm32) but does not count `tests/shared_ir_adapter.rs` and
`tests/shared_ir_adapter_pbt.rs` (12 more `#[test]` fns) — measured directly here:
`cargo test --no-default-features` on this crate runs **42** tests total (30 lib + 3 +
9), not 30. `native_only` is therefore 13, not the single dlsym test the topology comment
implies. All 12 of the previously-uncounted tests are structurally
`integration-test-target` (unreachable by the registry mechanism regardless of whether
they use proptest), the same class every other crate's `tests/*.rs` content falls into
— not a registry defect, but the topology file's own prose is stale on this crate's exact
count and should be corrected when that file is next touched (out of scope here per this
task's boundaries).

### `temper-quality-oracle` — 41 native-only, two classes

| count | module | class |
|---:|---|---|
| 4 | `classification::tests::proptests` | `proptest-dev-dependency` |
| 3 | `ipc2221::tests::proptests` | `proptest-dev-dependency` |
| 5 | `oracle::tests::proptests` | `proptest-dev-dependency` |
| 17 | `placement_metrics::tests::proptests` | `proptest-dev-dependency` |
| 6 | `routing_quality::tests::proptests` | `proptest-dev-dependency` |
| 3 | `thresholds::tests::proptests` | `proptest-dev-dependency` |
| 2 | `types::tests::proptests` | `proptest-dev-dependency` |
| 1 | `placement_metrics::tests::py_pow_resolves_to_host_libm_not_sqrt` | host-facility (dlsym/pow) |

40 + 1 = 41, matching `docs/evidence/2026-08-11-native-only-classification-all-crates.md`'s
independent classification of this crate exactly (same 7 modules, same counts, same
single host-facility test) — corroborated by an independent method (that document reads
`discover_eligible()` against source; this measurement runs the actual `cargo test` /
wasm32 build and diffs verdicts). **The crate's registered corpus grew from 125
(topology comment, pre-property-campaign) to 2,602** (`property_campaigns.rs` alone
contributes 2,476 of those) — `native_only`'s *count* held at 41 across that growth,
same story as `temper-drc-rs` (§2): the growth mechanism does not touch the
`proptest-dev-dependency` boundary.

### `temper-io-types` — 55 native-only, one class

All 55 are `proptest-dev-dependency`, across 7 modules:

| count | module |
|---:|---|
| 4 | `dsn::proptests` |
| 4 | `dsn_exporter::proptests` |
| 3 | `dsn_types::proptests` |
| 14 | `placer_core::placer_compute::proptests` |
| 17 | `placer_core::units::proptests` |
| 4 | `pyfmt::proptests` |
| 9 | `stackup_validator::proptests` |

Matches `docs/evidence/2026-08-11-native-only-classification-all-crates.md`'s
classification of this crate name-for-name. Registered corpus grew from 144 (topology
comment) to 6,633 in-both; `native_only` again held at exactly 55 across that growth —
third crate in this batch showing the same "corpus growth via deterministic property
campaigns does not create new native-only entries" pattern (§2 makes the case in full for
`temper-drc-rs`, where it was checked name-for-name, not just by count).

### `temper-drc-rs` — 32 native-only, two classes (see §2 for the growth comparison)

| count | class | detail |
|---:|---|---|
| 9 | `proptest-dev-dependency` | `ipc::proptests::p1`–`p9` |
| 15 | `proptest-dev-dependency` | `pymath::proptests::p1`–`p15` |
| 7 | `proptest-dev-dependency` | `validation_kernels::proptests::p1`–`p7` |
| 1 | `integration-test-target` | `edge_distance_to_reports_nonzero_boundary_gap_for_fully_nested_seed_0` (`tests/property_containment_gap.rs`) |

31 + 1 = 32. Same composition as `docs/evidence/2026-08-10-wasm-tier-u3-native-only-classification.md`'s
original 31 `proptest-dev-dependency` + 1 `integration-test-target` (that document's
`portable-but-missing` 11 `ipc::tests::*` entries are **not** present in this measurement
— they were fixed/registered between 2026-08-10 and the 2026-08-11 all-crates snapshot,
which already recorded 32; see §2).

---

## 2. `temper-drc-rs` — did corpus growth preserve agreement? (the anti-regression check)

This is the comparison the task called out as the single most valuable finding available
in this batch. `temper-drc-rs`'s registered corpus has grown enormously since the
2026-08-07 and 2026-08-10 measurements — a property campaign (`rules/drc/property_campaigns.rs`)
alone now registers 3,058 tests, and total registered tests are 3,281 (`python3
scripts/gen_wasm_test_registry.py --crate temper-drc-rs --census`, run at this branch's
HEAD).

| measurement | date | native total | registered (in-both) | native-only | source |
|---|---|---:|---:|---:|---|
| Original U6 | 2026-08-07 | 95 | 95 (91 pass + 4 expected-fail) | **0** | `docs/evidence/2026-08-07-phase1-u6-sustained-agreement.md` |
| U3 single-crate | 2026-08-10 | 1,751 | 1,708 (+ 4 wasm-registered-but-failing "expected") | **43** (31 proptest + 1 integration-test-target + **11 portable-but-missing**) | `docs/evidence/2026-08-10-wasm-tier-u3-native-only-classification.md` |
| U3 all-crates | 2026-08-11 (`86c6a01f`) | 1,751 | 1,719 | **32** (31 proptest + 1 integration-test-target) | `docs/evidence/2026-08-11-native-only-classification-all-crates.md` |
| **This batch** | 2026-08-11 (this HEAD) | 3,313 | 3,281 | **32** (31 proptest + 1 integration-test-target — verified name-for-name identical to the row above) | this document |

**Reading this top to bottom:** the 95→1,751→3,313 native growth reflects two distinct
events — the `temper-ipc` crate-fold (2026-08-09, added `src/ipc.rs` and its 11 unit
tests + 9 proptests, initially *not* registered — that's where the 43-with-11-portable-but-missing
row comes from) and the property campaign (`rules/drc/property_campaigns.rs`, +3,058
tests, landing between the second and third rows). The 11 `portable-but-missing` tests
were fixed (registered) somewhere between 2026-08-10 and 2026-08-11, dropping native-only
from 43 to 32 — that fix predates this batch and is not this document's work.

**What matters for R24: from 32 to 32, exactly, across +1,562 newly registered tests
(1,719 → 3,281).** Not just the count — the actual test names are identical (verified by
diffing this batch's `native_only_detail` against the U3 all-crates document's own
enumeration, §1 above). The property campaign's own module docstring
(`packages/temper-drc-rs/src/rules/drc/property_campaigns.rs:1-40`) explains why: it is
explicitly a *deterministic, seeded-generator* mirror of the crate's `proptest`-based
properties, written specifically so these tests do **not** depend on the `proptest`
dev-dependency and therefore **can** register into the wasm build — "three more portable
kernels each with its own `#[cfg(test)] mod proptests` that ... cannot be registered
directly because `proptest` is a dev-dependency ... mirrors `ipc::proptests`' nine
properties," etc. This is the same pattern the `temper-orchestration` U6 document
recommended as a follow-up ("Mirror the ... proptests onto the tier ... deterministic
campaign equivalents, keeping the native randomized proptests") — `temper-drc-rs` had
already done it for exactly the modules whose *native-only* proptest siblings are listed
in §1's table, which is why the two 31-test `proptest-dev-dependency` sets (mirrored
kernel + un-mirrorable original) coexist without the mirrored copies ever showing up as
native-only themselves.

**Verdict: no regression.** Corpus growth of this magnitude (+91% registered tests)
preserved both the agreement rate (1.0, unchanged) and the native-only set (32, unchanged
in count and in exact composition). The growth mechanism was deliberately engineered to
avoid the `proptest-dev-dependency` trap, and it worked.

---

## 3. Anti-vacuity — required check

A campaign that cannot fail proves nothing. Using `temper-rust-router`'s commit-1
(`36be871cf`) passing `wasm_36be871cf....json`, one result was flipped from `pass` to
`fail` under the `results` key (`layer_assignment::tests::all_seven_patterns_compile`,
an in-both test — not one of the 3 native-only proptests, so it is actually comparable),
and `r19_compare.py --fail-on-disagree` was re-run against the same commit's native
output:

```
$ /usr/bin/python3 tools/wasm/r19_compare.py \
    --native-file /tmp/u6-temper-rust-router/native_36be871cf....txt \
    --wasm-json wasm_flipped.json \
    --expected-failures /tmp/u6-temper-rust-router/expected.json \
    --commit 36be871cf... --output r19_flipped.json --fail-on-disagree

FAIL: --fail-on-disagree set and 1 disagreement(s) / 0 unexpected-pass(es) found. This is
the tier's actual safety property: a wasm32 verdict that disagrees with the same commit's
native/CI verdict, or a manifest exclusion that has gone stale, must not report green.
R19 Baseline at commit 36be871cf...
  Native  : 23 pass, 0 fail (23 tests)
  WASM32  : 19 pass, 1 fail, 0 expected-fail, 0 unexpected
  Agree   : 19 agree-pass, 0 agree-fail, 0 expected-fail
  Disagree: 1 disagreements
  Scope   : 3 native-only, 0 wasm32-only
  Agreement rate: 0.950000
  DISAGREEMENTS:
    layer_assignment::tests::all_seven_patterns_compile: native=pass, wasm32=fail
EXIT=1
```

Exit code 1, the offending test named, agreement rate dropped from 1.0 to 0.95. The
apparatus can fail, and does when given a genuine disagreement. The 6×10/10 results above
are a measurement, not a tautology.

---

## 4. Does R24 license anything today?

**None of these six crates has a standalone, gating native `cargo test` step in GitHub
Actions today.** Grepping every `.github/workflows/*.yml` for `cargo test` finds exactly
three crates with a PR-path native step (`temper-design-bundle`, `temper-geometry`,
`temper-orchestration`, per `wasm-tier-pr.yml`'s own header) plus `temper-drc-rs`'s
appearance *only* inside `wasm-tier-nightly.yml`'s own per-tier R19 comparison job (a
scheduled, non-gating nightly, not a PR-blocking step) — confirmed directly in that
workflow's comments ("NONE of them had a `cargo test` step in any workflow either", where
"them" is the three crates added 2026-08-11, and separately, `temper-drc-rs`'s own nightly
comparison predates this batch and is not a suite-removal candidate — it *is* the
measurement apparatus). So for all six crates in this batch, R24's "may leave GitHub
Actions" is not applicable today in the "delete a red/green gate" sense — there is no such
gate. What this evidence licenses is forward-looking: if a native `cargo test` step is
ever added for one of these crates, this measurement already tells you what it could be
narrowed to.

Per crate:

- **`temper-pcl-ir`: neither delete nor narrow — there is nothing to narrow.** No native
  step exists; none is needed. If one were added, the wasm tier already proves all of it
  (native_only 0).
- **`temper-rust-router`: no native step exists today; if one is added, it can be
  narrowed to 3 tests** (`proptests::p1`–`p3`), the permanent `proptest-dev-dependency`
  residual. Nothing here is uncovered by *some* execution — the tier proves 20/23; the
  residual is exactly what an unmirrored proptest module contributes.
- **`temper-constraints`: no native step exists today; if one is added, it can be
  narrowed to 13 tests** — the 12 `tests/*.rs` integration tests (structurally outside the
  registry mechanism, 9 of them proptest-based) plus the 1 dlsym host-facility test. The
  tier proves 29/42.
- **`temper-quality-oracle`: no native step exists today; if one is added, it can be
  narrowed to 41 tests** — 40 `proptest-dev-dependency` plus 1 host-facility (dlsym/pow).
  The tier proves 2,601/2,642 (98.4%).
- **`temper-io-types`: no native step exists today; if one is added, it can be narrowed
  to 55 tests**, all `proptest-dev-dependency`. The tier proves 6,633/6,688 (99.2%).
- **`temper-drc-rs`: the one crate with an existing native run, but it is nightly-only
  and lives *inside* the R19 comparison job itself — there is no separate PR-gating step
  to delete or narrow.** If a PR-gating native step is ever added for this crate, this
  evidence licenses narrowing it to the 32-test residual (31 `proptest-dev-dependency` +
  1 `integration-test-target`); the tier already proves 3,281/3,313 (99.0%), and — per §2
  — that proportion held steady through a corpus that nearly doubled in the last measurement
  cycle, which is itself evidence the narrowing claim is durable rather than a one-time
  snapshot.

None of the above deletes, narrows, or otherwise modifies `.github/workflows/*`,
`wasm_tier_topology.json`, or any file under `packages/temper-orchestration/**` — this
document is a measurement only, per this task's boundaries.

---

## 5. Reproduce

```bash
git fetch origin
git checkout -b <scratch> origin/tools/u6-campaign-runner   # or cherry-pick 74e74a8be
bash tools/wasm/u6_campaign.sh temper-pcl-ir 10
bash tools/wasm/u6_campaign.sh temper-constraints 10
bash tools/wasm/u6_campaign.sh temper-rust-router 10
bash tools/wasm/u6_campaign.sh temper-quality-oracle 10
bash tools/wasm/u6_campaign.sh temper-io-types 10
bash tools/wasm/u6_campaign.sh temper-drc-rs 10
```

Each writes to `/tmp/u6-<crate>/` by default (override with a third argument) and its own
`CARGO_TARGET_DIR=/tmp/u6-target-<crate>`; 2-3 concurrent is faster than 6, and `temper-drc-rs`
(3,281-test corpus) is worth running alone once the others are done.

## 6. Related

- `docs/plans/2026-08-07-001-feat-wasm-tier-phase1-plan.md` — §U6, the R19 sustained-agreement
  bar this batch measures against.
- `docs/evidence/2026-08-07-phase1-u6-sustained-agreement.md` — original `temper-drc-rs` U6
  measurement (95-test corpus), superseded in scope by §2 above but not in method.
- `docs/evidence/2026-08-10-wasm-tier-u3-native-only-classification.md` — `temper-drc-rs`
  single-crate native-only classification (43, at the `portable-but-missing`-not-yet-fixed
  point in its history).
- `docs/evidence/2026-08-11-native-only-classification-all-crates.md` — nine-crate
  native-only classification (`temper-quality-oracle`, `temper-io-types`, `temper-drc-rs`
  entries corroborated here by an independent, execution-based method).
- `docs/evidence/2026-08-11-u6-orchestration-sustained-agreement.md` — `temper-orchestration`
  U6 (83 in-both / 46 native-only), the template this document's format follows, and the
  origin of the "deterministic campaign mirrors a proptest module" pattern §2 finds already
  applied to `temper-drc-rs`.
- `tools/wasm/u6_campaign.sh` — the campaign runner (from `tools/u6-campaign-runner`,
  unmodified by this task).
- `tools/wasm/wasm_tier_topology.json` — per-tier build/test configuration this runner
  reads; its `_comment` is stale for `temper-constraints`'s native-only count (§1) but was
  not edited here per this task's boundaries.
