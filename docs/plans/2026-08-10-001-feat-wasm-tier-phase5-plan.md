---
title: WASM Tier Phase 5 — suite-by-suite transition off GitHub Actions (R24–R28)
type: feat
date: 2026-08-10
topic: wasm-tier-phase5
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
execution: code
product_contract_source: measurement
status: completed
swept: 2026-08-24
swept_basis: "verdicted in docs/evidence/2026-08-24-wasm-tier-phase5-verdict.md (#1479): complete by exhaustion. Additive half landed and works (12 deployed Workers, 30,349 executable tests, per-PR advisory verdict, push-triggered content-hash-verified deploy, hourly staleness watchdog). R25 satisfied at relief=0; R26 satisfied; R27 partial. R24 VACUOUS -- no removable suites remain that are not coverage. R28 BLOCKED and re-pulled as docs/plans/2026-08-24-001-feat-wasm-tier-phase6-plan.md (#1481) with the corrected premise: the blocker is R19 sustained per-crate agreement, not the R22/R23 durability D5.4 named, which #992 closed on 2026-08-11."
---

# WASM Tier Phase 5 — Plan

## Goal Capsule

**Objective:** Break Phase 5 of
[`2026-08-03-002-feat-wasm-verification-tier-plan.md`](./2026-08-03-002-feat-wasm-verification-tier-plan.md)
(R24–R28, governed by D12–D15) into implementable units — the phase that
moves each crate's `cargo test` suite off GitHub Actions onto the deployed
Worker tier as its R19 agreement sustains, ending with "GitHub Actions
running only CPython-bound work" (D15).

Phase 5 has been decided since 2026-08-03 and has never had units. So did
Phases 2–4 (`docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md` §2);
this plan covers Phase 5 only.

**What this plan changes about Phase 5:** its headline value proposition
does not survive measurement. D12 justifies the phase on "pool relief is the
immediate efficiency win." Measured against the workflows as they exist
(2026-08-10, §1 below), **the available pool relief is approximately zero**,
for the exact reason R25 anticipated. A different and larger prize is
available from the same infrastructure, and this plan is built around that
instead: **`temper-drc-rs` has no `cargo test` on the PR path at all**, and
it is the one crate the tier already covers with sustained R19 agreement.

The phase stops being "move work off GitHub Actions to free slots" and
becomes "use the tier to test what GitHub Actions is not testing." R24–R28
are retained; R24's ordering is re-derived from measurement rather than
from the assumption that every crate has a job worth reclaiming.

## Product Contract

### Summary

Phase 5 turns the deployed Worker tier from an advisory nightly into a
producer of PR-path verdicts, crate by crate, gated on sustained R19
agreement per D13/D14. This plan's units establish, in order: what is
actually on the PR path today (measured, not assumed), the coverage hole the
tier can close immediately, the staleness control that keeps deployed
artifacts honest, and only then the suite-by-suite removal D13 describes.

### Problem Frame

Four measurements, all taken 2026-08-10 against `origin/main` at `bd85d76e`
and the live Cloudflare account, frame this phase.

**1. `cargo test` on the PR path covers three crates, in two jobs.**
Exhaustive scan of `.github/workflows/*.yml` (29 files):

| crate | invocation | job |
|---|---|---|
| `temper-orchestration` | `python-tests.yml:924` | `rust-checks` |
| `temper-geometry` (`--no-default-features`) | `python-tests.yml:954` | `rust-checks` |
| `temper-design-bundle` | `python-tests.yml:2368` | `extended-bundle-workflow-checks` |

**2. Removing all three frees steps, not a job — R25's warning, realised.**
`rust-checks` also runs `cargo clippy -D warnings` across 13 crates, which
cannot move (it needs `cargo`, not a WASM runtime), so the job survives the
removal of both its `cargo test` steps. `temper-design-bundle`'s runs as a
backgrounded subprocess inside a shared job that does other work. R25 already
requires relief be counted "per GitHub Actions job or step actually
removed"; counted honestly, **the removable-job count is 0**.

**3. `temper-drc-rs` — the tier's own payload — is not `cargo test`ed on the
PR path at all.** It gets `clippy` and `maturin` builds. Its only `cargo
test` invocation anywhere in `.github/workflows/` is inside
`wasm-tier-nightly.yml:138`, which is nightly and advisory. As of this plan
that is **1,751 native tests with no PR-path execution**, in the crate the
DRC engine lives in.

**4. The deployed tier's coverage number was an artifact-staleness bug, not
a coverage gap.** The Phase 1 verdict recorded U4 PARTIAL on "family coverage
thin (drc 1, routing 2 of 95; erc 0 registered tests)" and named it the
Phase 2 precondition. Those counts are properties of `.wasm` modules built
2026-08-07 (confirmed via the Cloudflare API: every `temper-wasm-*` script
`modified_on` 2026-08-07), not of the test suite. Rebuilt from `main` at
`bd85d76e` the same modules carry:

| family | deployed 2026-08-07 | rebuilt 2026-08-10 |
|---|---:|---:|
| drc | 1 | **1,510** |
| safety | 0 | **25** |
| routing | 2 | **18** |
| placement | 12 | 18 |
| erc | 9 | 12 |
| emc | 14 | 15 |
| infra | 109 | 110 |
| **full corpus** | **147** | **1,708** |

The seven families sum to exactly 1,708, matching the full-corpus module —
a clean partition with no double-counting and no orphans. **The U4 gap is
closed by redeploying, not by writing tests.**

### Key Decisions

- **D5.1. Phase 5's ordering is driven by coverage gained, not slots
  freed.** Chosen over D12's pool-relief framing, which §1 measurements 1–2
  show is unavailable: the removable-job count is 0, so ordering crates by
  reclaimable CI capacity ranks every candidate equally at zero. Ordering by
  PR-path coverage gained ranks `temper-drc-rs` first by a wide margin
  (1,751 tests currently unexecuted on the PR path). Governs R24 ordering.
- **D5.2. The tier's first PR-path role is additive, not substitutive.**
  Chosen over starting with removal per D13: adding a verdict for a suite
  that runs nowhere on the PR path carries no regression risk, while
  removing a suite that does run trades coverage for capacity that
  measurement says is not there. Removal stays in the phase (R24) but is
  sequenced after the additive win.
- **D5.3. Deployed-artifact staleness is a first-class failure mode with its
  own control.** Chosen over treating deploys as a manual runbook step: the
  tier reported `agreement_rate: 1.0` while carrying 8.4% of the suite, and
  nothing in CI could observe the discrepancy. A tier whose verdicts are
  trusted must be unable to silently answer for a stale corpus. Governs R5.1.
- **D5.4. This phase does not cross into merge authority.** Every unit here
  keeps tier verdicts advisory or additive-informational. The durability gate
  named when this plan was written was satisfied on 2026-08-11 by #992:
  dead-letter handling, idempotent work keys, reconciliation, and replication
  are implemented and fault-injection tested. Promotion remains out of scope
  here because it still needs sustained R19 per-crate agreement, plus R10/Q1
  for the DRC verdict specifically. Governs the Scope Boundaries. See
  `docs/evidence/2026-08-11-wasm-tier-r22-r23-durability.md` and the correction
  in the Scope Boundaries below.

### Requirements

Parent-plan requirements R24–R28 are unchanged and inherited. This plan adds:

- **R5.1.** The deployed Workers' registered test count is compared against
  the count built from the commit under test, and a mismatch fails loudly.
  A tier that answers for a corpus other than the one in the repository is
  reporting on nothing, which is the failure mode
  `wasm-tier-nightly.yml`'s header already names.
- **R5.2.** Deployment of the `.wasm` modules is reproducible from a
  committed script and runs from CI or a documented one-command path, not
  from an operator's shell history. The 2026-08-07 → 2026-08-10 staleness
  window existed because redeploy was a manual step nobody owned.
- **R5.3.** `temper-drc-rs`'s suite gains a PR-path verdict from the tier
  before any crate's suite is removed from GitHub Actions (D5.2).
- **R5.4.** Every claim of pool relief names the job or step removed and the
  measured wall-clock or slot delta, per R25. A unit that frees no job says
  so.

## Units

Dependency order. U1 is the only unit that must precede the others.

### U1 — Redeploy, and make staleness impossible to repeat (R5.1, R5.2)

**Deliverable.** The 8 Workers carry the corpus built from `main`; a
staleness check fails the nightly when they do not.

- Deploy the 8 staged modules (`scripts/stage_wasm_families.sh` output).
  Requires a Cloudflare token with `Workers Scripts:Edit`; the token
  provisioned 2026-08-10 was verified to have read access only at the time
  of writing (`GET /accounts/{id}/workers/scripts` succeeded; edit
  untested).
- Add a step to `wasm-tier-nightly.yml`'s `worker-dispatch-r19`: build the
  full-corpus module for the commit under test, read `temper_test_count()`
  from it, compare against the deployed Workers' reported registry size, and
  fail with both numbers on mismatch. This is the R5.1 control and it would
  have caught the 147-vs-1,708 gap on 2026-08-09.
- Make the deploy reproducible (R5.2): either a `workflow_dispatch` job that
  runs `stage_wasm_families.sh` + `wrangler deploy`, or a documented
  one-command path. The `wrangler deploy` credential requirement belongs on
  the step that consumes it — see #932 for why a credential check detached
  from its consumer is worse than none.

**Evidence of closure.** A nightly run reporting `wasm32.total == 1708` from
the deployed path; a deliberately reverted module proving the staleness check
fails.

**Why first.** Every downstream unit's agreement number is meaningless while
the deployed corpus is a four-day-old 8.4% sample.

### U2 — `temper-drc-rs` gains a PR-path tier verdict (R5.3, D5.1, D5.2)

**Deliverable.** A PR-triggered job dispatching the deployed Workers for
`temper-drc-rs` and publishing a verdict, advisory (not required) per D5.4.

- The crate has no PR-path `cargo test` to remove, so this is purely
  additive: 1,751 tests go from "executed nightly, advisory" to "executed
  per PR."
- Cost is bounded and already measured: the full 147-test sweep took 379 ms
  wall at concurrency 64 (387.9 tests/s) against the stale corpus. The
  1,708-test sweep should be re-measured, not extrapolated, and recorded
  against D3's $5–7/month cost basis.
- Concurrency impact on the GitHub Actions pool is one short job that does
  no `cargo` work — it curls Workers and compares. This is the D12 premise
  in the only form measurement supports.

**Evidence of closure.** A PR whose tier verdict is published and disagrees
with nothing; an injected disagreement proving the comparison bites (the
`inject_disagreement` input already exists on the nightly for exactly this).

**Open question O1.** Whether the PR-path job compares against a native
`cargo test` run of `temper-drc-rs` (adding the job that does not exist
today) or against the tier alone. Comparing needs a native arm, which
reintroduces the `cargo` cost D12 wanted to avoid; not comparing means the
PR-path verdict has no R19 guard on the commit it is judging. This is the
same shape as the parent plan's Q1 and should be answered before U2 is built.

### U3 — Wasm-incompatible self-selection is recorded, not assumed (R27, D14)

**Deliverable.** The set of tests whose tier verdict never agrees with their
native verdict, as a committed artifact rather than a claim.

- `tools/wasm/wasm_expected_failures.json` already carries 4 expected
  failures (`b7-pow-divergence-absent`, `no-dynamic-loader`, host-libm
  classes). D14 says the R19 comparison self-selects this subset without
  upfront classification — over 1,708 tests rather than 147, that set will
  grow, and it must be observed over sustained runs before any crate is
  removed from GitHub Actions.
- Requires N consecutive agreeing runs at full corpus. N is the parent
  plan's own unanswered Q1 ("the agreement duration is the same question Q1
  poses for `kicad-cli` retirement under R10").

**Evidence of closure.** A sustained-agreement record at 1,708 tests, and a
list of self-selected wasm-incompatible tests with a class per entry.

### U4 — Suite-by-suite removal, honestly counted (R24, R25, R5.4)

**Deliverable.** For each of the three PR-path crates, a decision recorded
with its measured relief.

- Order by R19 agreement sustained (D13), evaluated per crate.
- `temper-geometry` and `temper-orchestration` share `rust-checks` with
  unmovable clippy; `temper-design-bundle` shares a job with other work.
  Per R5.4 each removal states the step removed and the measured delta, and
  states plainly when the job count is unchanged.
- A crate whose tests are not wasm-portable (pyo3-gated, host-libm
  sensitive) does not move; U3's artifact is the evidence.

**Evidence of closure.** Per crate: agreement record, the diff removing the
step, and a before/after wall-clock measurement of the containing job.

### U5 — The Phase 5 verdict

Consolidates U1–U4 into the licence for D15's end-state, or records the
preconditions for a re-pull. Mirrors the Phase 1 verdict's structure
(`docs/evidence/2026-08-07-wasm-tier-phase1-verdict.md`).

## Scope Boundaries

- **Not in scope: making any tier verdict a required PR context.** D5.4 —
  this phase stops short of it; the parent plan's R28 describes the end-state.

  **Corrected 2026-08-24 (#1482).** This boundary originally read "that
  crosses R22/R23, which are unbuilt by design under D10." R22/R23 were
  unbuilt when this plan was written on 2026-08-10, and were closed the next
  day by #992 — dead-letter handling, idempotent work keys, a `reconcile()`
  pass with its own `exit(2)`, and replication, each fault-injection tested
  (`docs/evidence/2026-08-11-wasm-tier-r22-r23-durability.md`; re-verified at
  `9546f568e`). The boundary itself still stands for this phase, but the
  reason is now R19 sustained per-crate agreement — derived once every twelve
  nights and recorded nowhere — plus R10/Q1 for the DRC verdict specifically.
  See `docs/evidence/2026-08-24-wasm-tier-phase5-verdict.md` §5 and
  `docs/plans/2026-08-24-001-feat-wasm-tier-phase6-plan.md`, which takes R28
  on with the corrected premise.
- **Not in scope: the Python suites.** R26 — CPython-bound, permanently on
  GitHub Actions. `pytest`, `numpy`/`scipy`/`ortools`, `kicad-cli`,
  `maturin`, and Docker builds cannot run in a Workers isolate and are not
  candidates at any point in this phase.
- **Not in scope: `cargo` itself.** Workers execute WASM; they do not
  compile Rust. `cargo build`, `cargo clippy`, and the `maturin` extension
  builds stay on GitHub Actions regardless of how much test execution moves.
- **Not in scope: Phases 2–4.** Manufacturing variation, fault injection,
  and design-space variants remain unplanned; see
  `docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md`.

## Dependencies / Assumptions

- **A Cloudflare token with `Workers Scripts:Edit`.** U1 is blocked without
  it. The 2026-08-10 token has verified read access; edit is untested.
- **The 128 MiB isolate limit remains the binding constraint** (parent R2:
  median 4 ns per kernel case, so CPU is not the limit; an occupancy grid
  costs 24 MB at 0.1 mm and 2,400 MB at 0.01 mm). The 1.4 MiB full-corpus
  module is far inside it, but any unit that moves grid-resolution work to
  the tier re-opens this.
- **Issue #872** — pyo3 is still compiled for wasm32 via feature
  unification, so the "python-free wasm" premise is not strictly true. It
  does not block this phase but it undercuts any claim that the tier's
  payload is pyo3-free.
- **Issue #873** — `board_py_bridge` does not populate traces/vias/zones, so
  routing rules were no-ops in the measured full-board pass. Bounds what a
  tier verdict on routing families currently means.
- **The Workers are unauthenticated public endpoints.** Anyone who learns
  the hostnames can invoke them and consume the account's request budget.
  Not a blocker at the current advisory scale; worth a decision before the
  tier carries merge authority.

## Outstanding Questions

- **O1** (U2). Native-arm comparison on the PR path, or tier-only? See U2.
- **O2** (U3). How many consecutive agreeing runs constitute "sustained" at
  full corpus? Inherited unanswered from the parent plan's Q1/R10.
- **O3** (U4). Is `rust-checks`' clippy step splittable, so that removing
  the `cargo test` steps could eventually free a job rather than two steps?
  If not, R25 relief for those two crates is permanently zero and U4 is
  documentation rather than reclamation.

## Sources / Research

- Parent plan: `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md`
  (D12–D15, R24–R28, Phase 5).
- `docs/evidence/2026-08-07-wasm-tier-phase1-verdict.md` — U4 PARTIAL, the
  coverage-spread finding this plan re-attributes to artifact staleness.
- `docs/evidence/2026-08-07-wasm-tier-phase2-4-status.md` — the precedent for
  a phase decided but never given units.
- `docs/evidence/2026-08-07-phase1-u8-multi-worker.md` — the per-family
  layout and the 2026-08-07 deployed counts this plan measures against.
- PR #929 (wasm32 registry feature), #932 (Worker preflight replacing an
  unused-secret gate) — the two defects that kept the nightly red from the
  day it landed until 2026-08-10.
- Measurements in §Problem Frame taken 2026-08-10 against `origin/main`
  `bd85d76e`, the Cloudflare API, and nightly run 31431417726.
