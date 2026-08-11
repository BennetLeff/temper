<!-- provenance: commit=753da757781f227019c4ef95a4508ed320de7051 dirty=false -->

# Native `cargo test` duplication inventory — six named workflows

**Date:** 2026-08-11
**Snapshot commit:** `753da757781f227019c4ef95a4508ed320de7051` (`origin/main`, HEAD at measurement time)
**Scope:** every `cargo test` invocation in `.github/workflows/metrics-record.yml`,
`placer-regression.yml`, `regression.yml`, `trunk-health.yml`, `python-tests.yml`,
`codeql.yml`. `wasm-tier-{nightly,deploy,pr}.yml` are the tier itself and are read here
only for context (topology, rotation), never edited.

## Bottom line

**Exactly one `cargo test` invocation exists in the six named workflows today, and it does
not duplicate the wasm tier.** The assigning task's "known starting point" — that
`temper-geometry`, `temper-design-bundle` and `temper-orchestration` each carry both a
native `cargo test` step and a full wasm tier — is **stale**. It was accurate as of
2026-08-10, but PR #978 (`9e5fe92fa`, merged 2026-08-10T23:37 by the repo owner,
already an ancestor of this snapshot commit) removed the `temper-geometry` and
`temper-design-bundle` steps before this task began. What remains is
`temper-orchestration`'s step, which has **no** deployed wasm tier to duplicate — it never
qualified for the "both a native step and a full tier" starting point in the first place,
once the tier's actual deployed state (not its source-registered state) is checked.

Net effect: **Stage A has nothing to land.** Every unsafe-to-delete or already-duplicated
case this task was built to find was either never a duplicate (`temper-orchestration`, see
below) or had already been resolved by prior work outside this task (`temper-geometry`,
`temper-design-bundle`, reported in §2 for completeness, not claimed as this task's relief
per R25 — this document did not remove them).

## 1. Live inventory (as of this snapshot)

| step | crate | tests run (measured) | tier coverage today | overlap | runtime (measured) | verdict |
|---|---|---:|---|---:|---:|---|
| `python-tests.yml` job `rust-checks`, step "Test temper-orchestration (cargo test)", line 924: `cargo test --manifest-path packages/temper-orchestration/Cargo.toml` (default features, i.e. `python`/pyo3 **on**) | `temper-orchestration` | 187 (measured live: run [31500695767](https://github.com/BennetLeff/temper/actions/runs/31500695767), `test result: ok. 141 passed` + six 5-test doctest-adjacent groups + four 4-test groups + 0 doctests = 187) | **none** — no deployed Cloudflare Worker. `temper-orchestration` is absent from `tools/wasm/wasm_tier_topology.json`'s 9 `tiers` entries and from `packages/temper-worker/families/` (16 directories, none named `orchestration`). It is *registered* (`python3 scripts/gen_wasm_test_registry.py --crate temper-orchestration --check` → `91 tests across 16 modules`) but registration is source-level preparation, not live execution — nothing dispatches a request to a `temper-orchestration` Worker because none is deployed. `wasm-tier-nightly.yml`'s native-arm rotation and wasm32 build/execute steps are both loops strictly over the topology file's tiers (its own header, 2026-08-11: "NOTHING IN THIS FILE NAMES A CRATE ANY MORE... loops over that topology"), so `temper-orchestration` gets neither. | 0 / 187 | 17s (3 samples: 17s run `31500695767`, 13s run `31498138180`, 20s run `31464417390`, all 2026-08-11) | **must-stay-native.** Not eligible for Stage A (nothing to narrow — there is no tier-covered portion to cut) or Stage B (nothing to delete-when-required — there is no tier to promote). This is the sole execution site for all 187 tests, permanently for at least the 96 that are structurally wasm32-ineligible (`python`-feature-gated pyo3 code, `proptest-dev-dependency` modules — the gap between 187 native and 91 registered). |

Every other `Cargo.toml` reference in these six workflows is `maturin develop` (builds a
Python extension, runs no tests), `cargo check`, or `cargo clippy --all-targets` (lints,
including test code, but never executes it) — enumerated exhaustively in §4. None is a
`cargo test` invocation.

### 1.1 The "six other registered crates with no `cargo test` step" claim — corrected

Twelve crates carry a `wasm_test_registry.rs`: `temper-drc-rs`, `temper-geometry`,
`temper-thermal`, `temper-design-bundle`, `temper-rust-router-core`,
`temper-constraint-compiler`, `temper-quality-oracle`, `temper-io-types`,
`temper-pcl-ir`, `temper-orchestration`, `temper-rust-router`, and
`packages/temper-placer/temper-constraints`. Of these, **9 have a deployed tier**
(`wasm_tier_topology.json`'s 9 entries) and **3 do not**: `temper-orchestration`,
`temper-rust-router`, `temper-constraints`.

Of the 3 untiered crates, only `temper-orchestration` has a `cargo test` step anywhere in
the six named workflows (line 924, above). `temper-rust-router` and `temper-constraints`
have **zero** `cargo test` invocations in these six workflows — every reference to either
crate's `Cargo.toml` is a `maturin develop --release` build step (`python-tests.yml` lines
481, 1094, 1676, 2017, 2334, 2595, 2759, 2900, 3008, 3146, 3236, 3328 for
`temper-rust-router`; lines 515, 1112, 1694, 2035, 2352, 2613, 2777, 2918, 3026, 3164,
3254, 3346 for `temper-constraints`). Neither is in the wasm tier's rotation either (same
topology-only-loop argument as `temper-orchestration`). Both are therefore untested by
`cargo test` anywhere in CI today — a real gap, but outside this task's remit (duplication
removal, not coverage addition), so it is reported here and not acted on.

**So "six other registered crates with no `cargo test` step" is now "two"** (`temper-rust-router`,
`temper-constraints`); the third untiered crate (`temper-orchestration`) does have one, it
just isn't a duplicate. The starting point's count was for a different, earlier repo state
and should not be reused without re-measuring, per this document's own header instruction.

## 2. Historical: what PR #978 already removed (context only — not this task's relief)

Before 2026-08-10T23:37, two more `cargo test` steps existed in `python-tests.yml` and both
genuinely duplicated a live, deployed tier. PR #978 (commit `9e5fe92fa`,
`wasm-tier-nightly-r19-rotation` branch, authored by the repo owner,
already merged and an ancestor of this snapshot) deleted both outright. These numbers are
reported for completeness (the task says "verify it, do not trust it" about the starting
point) and are **not** counted toward this task's Stage A total — this document did not
remove them, and R25 requires relief to be counted per step actually removed by the work
being measured, not projected or borrowed from other PRs.

| step (removed) | crate | tier coverage | native-only exclusions (per `docs/evidence/2026-08-11-native-only-classification-all-crates.md`, measurement commit `86c6a01f`) | pre-removal runtime (measured) | what changed |
|---|---|---|---|---:|---|
| `rust-checks` job, "Test temper-geometry (cargo test)": `cargo test --manifest-path packages/temper-geometry/Cargo.toml --no-default-features` | `temper-geometry` | full tier, `temper-wasm-geometry`, 2,232 registered @ `86c6a01f` | 89 (55 `proptest-dev-dependency`, 31 `integration-test-target`, 2 `cfg-excluded`, 1 `doctest`) | 16s (run `31439730609`, 2026-08-10T23:00:52–23:01:08) | Step deleted entirely, not narrowed to the 89. Those 89 now run only when `temper-geometry` comes up on `wasm-tier-nightly.yml`'s R19 native-arm rotation (1 night in 9). PR-path/push-path coverage for them dropped from every run to roughly weekly. The `WASM32 build + clippy` guard immediately below (link/lint, not test execution) is unchanged and still covers `temper-geometry`. |
| `extended-bundle-workflow-checks` job (push/nightly/`workflow_dispatch` only — `if: github.event_name != 'pull_request'` on the job; this step never ran on PRs even before removal), one leg of a 3-way backgrounded `run:` block: `cargo test --manifest-path packages/temper-design-bundle/Cargo.toml` | `temper-design-bundle` | full tier, `temper-wasm-design-bundle`, 24 of 26 registered @ `86c6a01f` | 2 (both `tests/temper_bundle.rs`, `integration-test-target`) | not separately measurable — this leg ran concurrently with two backgrounded `pytest` suites inside one `run:` block, so no log timestamp isolates the `cargo test` portion's own wall time from the parallel suites'; reported as a real limitation rather than guessed | Step deleted entirely from the parallel chain. The 2 `tests/temper_bundle.rs` tests now run only on `temper-design-bundle`'s rotation night (same 1-in-9 cadence). The Python-import smoke check in the same parallel block is unchanged and does not depend on `cargo test` having run. |

This is the same shape of tradeoff the assigning task's Part 3 preamble explicitly warns
against ("A step that runs 200 tests of which 150 are on the tier CANNOT simply be
deleted") — PR #978 deleted rather than narrowed, and its own commit message says so
plainly ("Native-only tests in the two trimmed crates lose PR-time... native execution and
now run only on their wasm-tier-nightly.yml rotation night"). It is a documented,
deliberate policy choice made by the repo owner with the tradeoff stated up front, not a
silent regression, and `wasm-tier-nightly.yml`'s own header names the "even if only
weekly" cadence as an accepted floor for native-only tests under this policy. It is
reported here for the record, not reversed — reverting a merged, intentional decision by
the repository owner is outside this task's remit, and the six-workflow files this task
scopes editing to do not contain these steps any more regardless.

## 3. Stage A / Stage B

**Stage A (land now): empty.** There is no `cargo test` step in the six named workflows
today whose scope can be narrowed or which is pure, fully-covered duplication — the one
live step (`temper-orchestration`) has 0% tier overlap, and the two steps that did overlap
were already removed before this task started (§2). No branch diff to `metrics-record.yml`,
`placer-regression.yml`, `regression.yml`, `trunk-health.yml`, `python-tests.yml`, or
`codeql.yml` is included with this document — there is nothing safe to change, and
inventing a change to have something to land would violate R25 ("do not write 'this saves
N minutes' for anything still in the file" cuts the other way too: don't remove something
that saves nothing, or that removes real coverage, to manufacture a number).

**Stage B (documented, contingent — not landed): also not yet applicable, for a reason
worth stating precisely.** Stage B in the assigning task is "the exact steps to delete the
moment the tier becomes required" — i.e., for a step that already duplicates a live tier
today. `temper-orchestration`'s step does not: there is no tier to promote to required,
only a source-level registry (91 of 187 tests wasm32-eligible) with no Worker built or
deployed. Promoting *nothing* to required promotes nothing. Two independent preconditions
would need to land, in order, before a Stage-B checklist for `temper-orchestration` would
mean anything:

1. **A `temper-orchestration` tier must be deployed** — a `wasm_tier_topology.json` entry,
   a `packages/temper-worker/families/orchestration/` Worker, and its wiring into
   `wasm-tier-nightly.yml`'s topology-driven loops and `wasm-tier-pr.yml`'s scoped
   dispatch. `packages/temper-orchestration` was unblocked for `wasm32-unknown-unknown`
   compilation on 2026-08-10 (PR #985, merged) but no deploy PR has landed or is open as of
   this snapshot (`gh pr list --search "orchestration wasm"` shows only #985, merged, and
   #978, unrelated). This is explicitly out of this task's scope (`tools/wasm/wasm_tier_topology.json`
   and `packages/temper-worker/**` are owned by another agent per this task's own
   boundaries) — noted here only so a future Stage-B pass knows what to check for.
2. **That tier's PR-path or nightly verdict must be promoted from advisory to required**
   (R15) — the separate durability/promotion work this task explicitly defers to.

**If and when both land**, the narrowing choice to make for `temper-orchestration` at that
point (estimate only, not measured, since no tier exists to measure against) is the same
one §2 shows the maintainer already chose for `temper-geometry` and `temper-design-bundle`:
delete the full-corpus `cargo test` step and accept that the ~96 native-only tests
(everything gated behind the default `python` feature, plus any `proptest-dev-dependency`
modules — the precise split is not known without a registry census taken after the
`--no-default-features` question is settled for this crate, since the current step runs
*with* default features and no `--no-default-features` variant has ever been measured for
it) fall back to `wasm-tier-nightly.yml`'s rotation cadence, consistent with the precedent
in §2. Estimated relief if that shape is followed: ~17s/run removed from the required
`rust-checks` job on every PR and push that touches `temper-orchestration`-relevant paths
— **an estimate, explicitly labelled as such**, not a measurement, since the step still
exists in the file today.

## 4. Full accounting of `Cargo.toml` references in the six workflows (why §1 is exhaustive)

Ran `grep -Pn 'cargo\s+test'` (whitespace-tolerant, not just a literal single space) across
all six files; the only match that is an executed step (not a comment) is line 924 of
`python-tests.yml`. Every other `Cargo.toml` mention across the six files, checked by
grepping `Cargo.toml` and reading each hit's preceding `run:` verb:

- `uv run maturin develop --release --manifest-path <crate>/Cargo.toml` — builds a Python
  extension (`temper-rust-router`, `temper-drc-rs`, `temper-placer/temper-constraints`),
  never invokes `cargo test`. Appears 12 times across `python-tests.yml`'s parallel gate
  jobs (`test`, `board-provenance-requirements-gates`, `consistency-gates`,
  `hygiene-gates`, `invariant-router-v6-{1,2,3,4}`, `invariant-rest`, `closure`).
- `cargo check --manifest-path packages/temper-constraint-compiler/Cargo.toml` (line 879)
  and the 14-crate `cargo clippy ... --all-targets -- -D warnings` loop (lines 884–909,
  `rust-checks` job) — compile/lint checks. `--all-targets` includes test targets in what
  clippy *lints*, but clippy never executes a test body.
- `cargo build --release --target wasm32-unknown-unknown --no-default-features` +
  `cargo clippy --no-default-features --all-targets` for `temper-drc-rs` and
  `temper-geometry` only (lines 1009–1018, `rust-checks` job) — a link/lint regression
  guard for the wasm32 substrate itself, explicitly not a test run (its own comment: "a
  link/lint check, not a test run").
- `metrics-record.yml`, `placer-regression.yml`, `regression.yml`, `trunk-health.yml`,
  `codeql.yml` — zero `cargo` invocations of any kind beyond `cargo --version` (the
  `cargo-smoke` job, `python-tests.yml` line 364, a 2-second toolchain check, not a test
  run). Read in full; no reusable-workflow (`uses: ./.github/workflows/...`) or composite
  action (`.github/actions/`) call from any of the six files reaches a `cargo test` either
  — `.github/actions/_build-rust` (the only local composite action referenced) contains no
  `cargo test`.

## 5. Honest total

- **Minutes of Actions time this task's Stage A removes: 0.** No step was safe to narrow
  or delete at this snapshot; none is included in this document's branch.
- **Minutes Stage B would remove once its two preconditions land: an estimate of ~17s per
  qualifying PR/push**, for `temper-orchestration` only, explicitly not measured (§3) —
  and contingent on work this task does not do (deploying the tier, promoting it to
  required).
- **Minutes already removed by prior, out-of-scope work (PR #978, not this task's relief):**
  16s/run (`temper-geometry`, measured) plus an unmeasured amount for `temper-design-bundle`
  (§2) — reported for the record, explicitly excluded from this task's own total per R25.

## 6. Related

- `docs/evidence/2026-08-11-native-only-classification-all-crates.md` — the tier-wide
  native-only classification this document's §2 tier-coverage figures are read from.
- `tools/wasm/wasm_tier_topology.json` — the 9-tier deployed topology (read-only here).
- `.github/workflows/wasm-tier-pr.yml`, `wasm-tier-nightly.yml` — the tier itself (read-only
  here; not touched, per this task's boundaries).
- PR #978 (`9e5fe92fa`), PR #985 — the prior, out-of-scope work this document reports on
  in §2 and §3 without reversing.
