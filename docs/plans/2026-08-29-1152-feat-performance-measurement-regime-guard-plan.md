---
title: Performance measurement regime guard and reviewed recapture
date: 2026-08-29
type: feat
artifact_contract: ce-unified-plan/v1
artifact_readiness: implementation-ready
product_contract_source: ce-brainstorm
execution: code
---

# Performance measurement regime guard and reviewed recapture

## Goal Capsule

- **Objective:** Performance gates compare like-for-like measurements and give maintainers a safe, reviewable way to establish a new baseline after either timed implementation changes.
- **Means:** Fingerprint both timed arms and the harness, reject incompatible baseline regimes, and provide an immutable-SHA five-run capture workflow that emits a candidate append patch.
- **Product authority:** This plan owns performance measurement identity, incompatible-baseline behavior, and baseline recapture. It does not change benchmark implementations or relax regression margins.
- **Open blockers:** None.

## Product Contract

### Summary

Add explicit measurement-regime identity to performance records so the comparator cannot mix rows produced by different Rust, oracle, fixture, or timing-harness implementations. When a regime changes, fail with a specific recapture-required result and provide a manual workflow that generates reviewed baseline evidence without mutating `main`.

### Problem Frame

The current baseline key is only module, board, and stage. PR #1535 showed that this is insufficient: retiring a pure-Python oracle primitive changed the denominator of `rust_over_oracle_ratio`, but six older DSN rows remained eligible for the rolling median. Both timed arms improved while the stale mixed-regime ratio comparison reported a regression.

### Key Decisions

- **Fingerprint the measurement, not the commit.** A commit identifies a capture but does not state which source paths and harness parameters define the two timed arms. Governs R1–R4.
- **Preserve append-only history.** Incompatible historical rows remain auditable but cannot influence a current median. Governs R5 and R6.
- **Keep recapture reviewed.** The workflow emits evidence and a candidate patch; it never pushes or merges baseline changes. Governs R8–R12.
- **Do not weaken the gate.** A mismatch becomes a distinct failing state, and margins remain derived only from same-commit, same-regime evidence. Governs R6, R7, and R13.

### Requirements

**Measurement identity**

- R1. Each registered ratio benchmark can declare the source paths for its Rust arm and oracle arm plus a stable harness descriptor.
- R2. Each emitted record carries a deterministic SHA-256 measurement-regime fingerprint and enough canonical metadata to audit what the fingerprint covers.
- R3. The fingerprint changes when either arm's covered source bytes or a result-affecting harness descriptor changes.
- R4. Identical inputs produce the same fingerprint across machines and working directories.

**Comparison and compatibility**

- R5. Baseline selection groups rows by module, board, stage, and exact regime fingerprint; incompatible rows never enter the rolling median.
- R6. A current record with no compatible baseline fails closed as `INCOMPATIBLE_BASELINE`, reports observed regime identities, and directs the operator to the reviewed recapture path.
- R7. Fixed-commit noise and margin derivation use only rows sharing both commit and regime fingerprint.
- R8. Legacy rows without regime metadata retain a stable legacy identity so unrelated existing benchmarks continue working until deliberately migrated.

**Reviewed recapture**

- R9. A manual workflow requires an immutable, resolvable 40-hex `capture_sha` and checks out exactly that commit in every capture job.
- R10. The workflow runs five independent CI captures and fails unless each registered benchmark has exactly five valid, non-duplicated rows carrying the requested SHA.
- R11. The workflow rejects a capture commit that changes the benchmarked arm, oracle, fixture, or harness paths relative to its parent.
- R12. Successful capture produces a manifest, raw rows, and an append-only candidate patch; it has no permission or step that writes to `main`.
- R13. Candidate validation proves append-only history, fixed-SHA provenance, complete rolling windows, and exact agreement between derived and committed margins.
- R14. A regime-reset baseline PR can validate an independent current capture against its candidate baseline without making ordinary PR comparisons permissive.

### Actors

- **Maintainer:** Chooses a stable capture commit, reviews the generated evidence and patch, and opens the baseline-refresh PR.
- **Capture workflow:** Produces five same-commit measurement sets and fails closed on incomplete or inconsistent evidence.
- **PR comparator:** Selects only compatible baseline rows and distinguishes an incompatible regime from a code regression.

### Key Flows

- F1. Normal compatible comparison
  - **Trigger:** A PR performance record has a regime fingerprint present in the committed baseline.
  - **Steps:** Select the matching regime, take the trailing-five median, and apply the existing derived margin.
  - **Outcome:** Existing regression semantics remain unchanged.
  - **Covered by:** R1–R5, R7.
- F2. Regime drift detected
  - **Trigger:** A PR record has no compatible fingerprint for an otherwise known benchmark key.
  - **Steps:** Exclude incompatible rows and emit `INCOMPATIBLE_BASELINE` with the capture guidance.
  - **Outcome:** The gate fails without mislabeling drift as a performance regression.
  - **Covered by:** R5, R6, R8.
- F3. Reviewed baseline recapture
  - **Trigger:** A maintainer dispatches the capture workflow with an immutable SHA.
  - **Steps:** Run five captures, aggregate and validate rows, derive margins, and publish the evidence bundle plus candidate patch.
  - **Outcome:** A human can review and land a comparable append-only baseline update.
  - **Covered by:** R9–R14.

### Acceptance Examples

- AE1. Given old DSN rows near 0.519916 and a current post-oracle fingerprint, when no compatible row exists, then the gate reports `INCOMPATIBLE_BASELINE` rather than `REGRESSION`. Covers R5 and R6.
- AE2. Given old DSN rows plus five compatible rows near 0.61, when a current ratio is 0.644020, then only the compatible rows determine the median and the result stays within the unchanged 20% default margin. Covers R5 and R8.
- AE3. Given a source-byte or harness-descriptor mutation, when the benchmark record is emitted, then its fingerprint differs. Covers R2–R4.
- AE4. Given five workflow jobs where one row has another SHA or one benchmark is missing, when aggregation runs, then no candidate patch is emitted. Covers R9–R12.
- AE5. Given a hand-edited margin unsupported by same-commit, same-regime rows, when candidate validation runs, then it fails. Covers R7 and R13.
- AE6. Given a valid five-run capture, when the workflow completes, then the only outputs are review artifacts and no repository ref is changed. Covers R10–R12.

### Scope Boundaries

- In scope: benchmark regime metadata, comparator selection and reporting, fixed-commit noise grouping, manual recapture automation, candidate-patch validation, tests, and workflow linting.
- Out of scope: optimizing the DSN exporter, restoring a pure-Python oracle, widening global or per-benchmark margins without derived evidence, rewriting all legacy baseline rows, and automatically committing or merging baseline data.
- Independent follow-up: the production routing and zone/pour CI jobs still require an evidence-backed timeout adjustment after both exhausted the new 35-minute ceiling.

### Risks and Mitigations

- **Incomplete source coverage:** A fingerprint could remain stable while an indirect dependency changes. Require explicit descriptors and tests for both arms; future registrations expand covered paths rather than inferring from imports.
- **Migration blast radius:** Making metadata mandatory would unbaseline every benchmark. Preserve a legacy sentinel and migrate intentionally per benchmark.
- **Self-approving evidence:** A workflow that commits its own patch bypasses review. Artifact-only permissions and append-only validation keep authority with the maintainer.
- **Vacuous margins:** New captures could be used to widen thresholds opportunistically. Require the existing fixed-commit derivation and exact table tests.

## Planning Contract

### Key Technical Decisions

- KTD1. Add a benchmark-spec metadata registry beside the existing callable registry first, avoiding a broad rewrite of all benchmark definitions. It declares covered source paths and a stable harness descriptor for DSN while preserving the current callable API. Governs R1–R4 and R8.
- KTD2. Canonicalize regime metadata as sorted compact JSON and hash it with SHA-256. Emit both the digest and auditable arm metadata. Governs R2–R4.
- KTD3. Treat absent regime metadata as `legacy-v2`. The comparator filters by exact identity before calculating the trailing-five median. Governs R5, R6, and R8.
- KTD4. Add a dedicated immutable-SHA capture workflow plus a pure validation/aggregation script. Keeping validation in Python makes the fail-closed contract unit-testable outside Actions. Governs R9–R14.

### Technical Design

`benchmarks/perf_ab.py` gains a small regime descriptor for registered benchmarks. For `dsn-exporter/export_pcb`, it covers the Python exporter entry point, Rust exporter implementation, Rust-backed DSN primitives, frozen exporter oracle, and explicit timing/fixture parameters. Hashing uses repository-relative paths, file-byte digests, and canonical JSON so checkout location cannot affect identity.

`scripts/pr_perf_compare.py` resolves a row identity to its explicit fingerprint or `legacy-v2`. Baseline loading retains append-only history but selects a compatible regime before median calculation. Known keys with no compatible rows produce `INCOMPATIBLE_BASELINE`; genuinely unknown keys remain `NO_BASELINE`. Fixed-commit noise grouping includes regime identity.

A new validator script consumes five capture artifacts, an immutable requested SHA, and the existing baseline. It validates completeness, uniqueness, SHA identity, resolvability, path-change restrictions, append-only output, and derived margins, then emits a manifest and candidate patch. The manual workflow checks out the exact SHA in a five-entry matrix, rebuilds and freshness-checks extensions, runs the benchmark, aggregates artifacts, and uploads review outputs with read-only repository permissions.

### Sequencing

U1 establishes the record identity and comparator contract. U2 builds the capture validator against that schema. U3 wires the validator into GitHub Actions. U4 performs integrated verification and prepares the first post-migration DSN capture; it does not silently accept or commit measurement rows.

## Implementation Units

### U1. Measurement regime identity and comparator filtering

- **Goal:** Emit auditable regime metadata and prevent incompatible rows from entering performance comparisons or noise derivation.
- **Requirements:** R1–R8; F1–F2; AE1–AE3 and AE5.
- **Files:** `benchmarks/perf_ab.py`, `scripts/pr_perf_compare.py`, `scripts/tests/test_pr_perf_compare.py`, and the existing benchmark test surface discovered during implementation.
- **Approach:** Add a minimal metadata registry and deterministic fingerprint helper; migrate DSN first; preserve legacy identity; add explicit mismatch status and reporting; include identity in fixed-commit grouping.
- **Test scenarios:** deterministic hashing; Rust/oracle/harness mutation sensitivity; legacy compatibility; incompatible-only failure; mixed old/new selection; unchanged regression behavior; same-commit mixed-regime exclusion; PR #1535 fixture.
- **Verification:** Focused benchmark and comparator tests plus `python3 scripts/pr_perf_compare.py --derive-margins --baseline-jsonl power_pcb_dataset/metrics/perf_ab_baseline.jsonl`.

### U2. Fail-closed capture aggregation and candidate patch

- **Goal:** Turn five immutable-SHA CI outputs into reviewable evidence without repository mutation.
- **Requirements:** R9–R13; F3; AE4–AE6.
- **Files:** New or existing script under `scripts/`, `scripts/tests/`, `scripts/manifest.yaml`, and regenerated invocation metadata required by repository convention.
- **Approach:** Implement aggregation as pure validation plus explicit artifact writes. Require complete keys, exactly five rows per key, one requested SHA, unique rows, resolvable commit, unchanged registered source/harness paths, append-only baseline construction, and exact margin derivation.
- **Test scenarios:** valid five-run fixture; malformed SHA; symbolic SHA; unresolved SHA; mixed SHA; partial key set; duplicate rows; malformed JSON; changed registered path; non-append edit; unsupported margin change.
- **Verification:** Focused unit tests, script manifest gate, invocation trace regeneration/check, and candidate-patch round trip against fixtures.

### U3. Manual five-run capture workflow

- **Goal:** Produce U2's complete evidence bundle from a maintainer-selected commit.
- **Requirements:** R9–R14; F3; AE4 and AE6.
- **Files:** `.github/workflows/pr-perf-baseline-capture.yml` or the repo-conventional equivalent, workflow tests/trigger fixtures, and documentation references only when necessary.
- **Approach:** Require `capture_sha`; validate it before checkout; run five independent matrix captures at the exact SHA; preserve per-run artifacts; aggregate in a dependent job; upload raw rows, manifest, and candidate patch; grant no contents-write permission.
- **Test scenarios:** trigger/input contract; five-run matrix; artifact naming; aggregation dependency; read-only permissions; partial failure blocks aggregation; actionlint compatibility.
- **Verification:** `actionlint` with repository flags, workflow trigger tests, and any workflow-policy gates.

### U4. Integrated migration evidence

- **Goal:** Prove the new regime behavior end to end and prepare, but do not auto-land, a valid DSN baseline refresh.
- **Requirements:** R5–R14; AE1–AE6.
- **Files:** Test fixtures and generated review artifacts only; `power_pcb_dataset/metrics/perf_ab_baseline.jsonl` changes only from an actually completed five-run capture reviewed in this PR.
- **Approach:** Run focused and repository gates, verify extension freshness immediately before reported measurements, dispatch the workflow at one unchanged post-migration main SHA, and inspect its evidence bundle. If external capture cannot complete in-session, leave the code verified and report baseline refresh as an explicit residual rather than fabricating rows.
- **Test scenarios:** PR #1535 stale-regime reproduction; compatible candidate comparison; independent capture against candidate; no global margin change.
- **Verification:** `make extensions-check`, focused pytest, `uv run python scripts/import_linter_gate.py`, `make regen-check`, and relevant CI workflows.

## Verification Contract

| Gate | Applies to | Done signal |
|---|---|---|
| Focused Python tests | U1–U2 | Regime, comparator, aggregator, and failure-path tests pass |
| Margin derivation | U1–U2, U4 | Committed margin table exactly matches same-commit, same-regime evidence |
| Script manifest and regeneration | U2 | New script is registered and invocation/generated artifacts are current |
| `actionlint` and workflow policy tests | U3 | Workflow syntax, triggers, permissions, matrix, and artifact flow pass |
| `make extensions-check` | U4 | Every imported pyo3 extension is fresh immediately before measurement |
| Import and regeneration gates | U1–U4 | `uv run python scripts/import_linter_gate.py` and `make regen-check` pass |
| CI capture evidence | U4 | Five complete rows per registered key share one immutable SHA and regime |

## Definition of Done

- Current performance records carry deterministic, auditable regime identity for DSN.
- The comparator never mixes incompatible regimes and reports a distinct recapture-required failure.
- Legacy benchmarks remain operational without rewriting historical rows.
- Fixed-commit margin derivation rejects mixed regimes.
- A read-only manual workflow emits a validated five-run evidence bundle and candidate append patch.
- Focused tests, workflow linting, repository gates, and freshness checks pass.
- No margin is widened and no baseline row is fabricated or committed without real reviewed CI evidence.
