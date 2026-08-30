---
title: WASM Tier Phase 6 — sustained R19 agreement, then merge authority (R28)
type: feat
date: 2026-08-24
topic: wasm-tier-phase6
artifact_contract: ce-unified-plan/v1
artifact_readiness: requirements-only
execution: code
product_contract_source: measurement
status: draft
swept: null
swept_basis: null
---

# WASM Tier Phase 6 — Plan

## Goal Capsule

**Objective:** Take the deployed WASM tier from advisory to holding merge
authority for at least one crate, by building the one instrument that does not
exist — a per-crate, accumulating record of R19 agreement — and then promoting
that crate's tier verdict into `.github/required-checks.json`.

**Why this is a new phase and not more of Phase 5.** Phase 5 is verdicted in
[`docs/evidence/2026-08-24-wasm-tier-phase5-verdict.md`](../evidence/2026-08-24-wasm-tier-phase5-verdict.md):
R24 is vacuous (no suites left to move that are not coverage), R25's relief is
zero and always was, and R28 is blocked. Carrying R24 forward would carry
forward a mechanism with an empty population. This phase takes **R28 only**,
and drops the pool-relief framing (D12) entirely — it was falsified on
measurement and is not this phase's justification.

## Product Contract

### Summary

Phase 6 establishes that a tier verdict can be trusted to block a merge, one
crate at a time, and then makes it do so. It does this by turning R19 from a
per-night pass/fail that is forgotten into a durable per-crate streak that can
be cited, raising the derivation cadence for promotion candidates only, proving
the streak is falsifiable, and finally editing branch protection.

### Problem Frame

Four measurements frame this phase. The first two correct claims that current
documents state as fact.

**1. R22/R23 durability is not the blocker. It has been closed since
2026-08-11.** `wasm-tier-pr.yml`'s header says promoting a tier verdict
"crosses R22/R23 — the dead-letter, idempotency and reconciliation machinery
that is unbuilt BY DESIGN under D10," and Phase 5's D5.4 says the same. Both
were written on 2026-08-10 in #951; #992 landed the machinery on 2026-08-11 and
neither was updated. Re-verified at `9546f568e` for the Phase 5 verdict:
`tools/wasm/test_sweep_durability.mjs` passes every fault-injection case (lost
response, duplicate delivery, hung response, transient fault, partial outage),
and `sweep_multi_worker.mjs` carries `reconcile()` with its own `exit(2)` that
both consuming workflows already treat as failure.

**The engineering prerequisite for gating is already paid for.** What is missing
is evidence, not machinery.

**2. Deploys are not operator-triggered.** The same header says
"`wasm-tier-deploy.yml` is `workflow_dispatch`-only." It is not: it carries
`push: branches: [main]` with a per-tier path filter, plus a schedule. The
deployed corpus tracks `main` within one deploy cycle. This materially improves
the freshness position for a required check and is why U5 below is tractable at
all.

**3. R19 agreement is derived once every 12 nights per crate, and never
recorded.** `wasm-tier-nightly.yml`'s native-arm rotation runs one tier's native
`cargo test` per night, selected by day-of-year modulo the tier count. Combined
with `temper-orchestration` being the only crate keeping a PR-path `cargo test`
step, **native execution for 11 of 12 tier crates happens on its rotation night
and nowhere else.** The run prints an agreement rate and the run expires. There
is no artifact anywhere in the repo from which the sentence "crate X has agreed
for N consecutive derivations" can be written.

D13's licensing condition — "as its R19 agreement sustains" — is therefore not
merely slow to satisfy. It is **unstateable**, because nothing accumulates.

**4. Nine of twelve crates carry zero expected failures.** Measured at
`9546f568e`:

| expected failures | crates |
|---:|---|
| 0 | `io-types` (6,944 tests), `router-core` (3,462), `quality-oracle` (2,602), `constraint-compiler` (1,900), `orchestration` (1,022), `design-bundle` (60), `constraints` (30), `rust-router` (20), `pcl-ir` (2) |
| 4 | `drc-rs` (3,283), `thermal` (2,641) |
| 10 | `geometry` (8,386) |

A crate with zero expected failures has no catalogued native/wasm32 divergence
to reason about, which makes it a cleaner first promotion target than the crate
the tier was originally built for.

### Key Decisions

- **D6.1. Phase 6 takes R28 only; R24 is retired, not inherited.** Chosen over
  carrying R24–R28 forward intact: the Phase 5 verdict shows R24's population is
  empty and its licensing condition unproducible. A requirement that cannot be
  executed should not be a successor phase's obligation.
- **D6.2. The first promoted crate is NOT `temper-drc-rs`.** Chosen over
  starting with the tier's original payload: R15's literal text gives merge
  authority to native `temper-drc-rs` and `kicad-cli` "until R10's equivalence
  bar is met," and Q1 ("how much agreement, over what corpus, sustained for how
  long") is still open with no terminal condition. Promoting a DRC verdict
  entangles this phase with R10/Q1; promoting a non-DRC crate does not. Governs
  R6.4.
- **D6.3. Cadence rises for promotion candidates only, never globally.** Chosen
  over widening the rotation: the rotation exists because the all-tiers native
  arm cost 88s of a 175s job and grew with the corpus, and that argument is
  still correct. A candidate set is small by construction, so cost scales with
  candidates rather than with corpus. Governs R6.2.
- **D6.4. The agreement record is a committed artifact, not a CI log.** Chosen
  over reading run history via `gh api` at promotion time: a streak that can
  only be reconstructed by querying an external service is not evidence anyone
  can review in a PR, and GitHub's log retention is finite. Governs R6.1.
- **D6.5. A promoted context is reversible in one commit, and that path is
  exercised before promotion, not after.** Chosen over promoting and handling
  regret ad hoc: the failure mode of a bad required check is a fully blocked
  repository. Governs R6.6.

### Requirements

- **R6.1.** A committed, append-only per-crate agreement ledger records, for
  every R19 derivation: crate, commit SHA, date, tests compared, agree-pass,
  agree-fail, expected-fail, disagreements, and the resulting streak length. A
  disagreement resets that crate's streak to zero.
- **R6.2.** Crates named as promotion candidates get a native arm on **every**
  nightly, not on their rotation night. Non-candidates keep the existing
  rotation unchanged.
- **R6.3.** The ledger is falsifiable: the existing `inject_disagreement`
  dispatch input must be shown to write a disagreement row and reset the streak,
  and that demonstration is a test, not a manual run.
- **R6.4.** The promotion bar is stated as a number before any crate is
  measured against it, and it is met by a non-DRC crate first (D6.2).
- **R6.5.** A required tier verdict answers for the commit under test. The PR
  workflow's verdict is computed against the deployed corpus, and a PR's own
  head is never deployed — so promotion requires either a per-commit build arm
  on the PR path for the promoted crate, or an explicit, written statement of
  what the required check does and does not cover.
- **R6.6.** Demotion is one commit, documented, and exercised on a scratch
  branch before promotion lands.
- **R6.7.** The stale prose that motivated this phase's Problem Frame §1 and §2
  is corrected at every source, so no future reader re-derives the wrong
  blocker.

## Units

### U1 — Correct the record (R6.7)

**Deliverable.** `wasm-tier-pr.yml`'s header, Phase 5's D5.4, and any other
document asserting R22/R23 is unbuilt or that deploys are `workflow_dispatch`-only
say what is true at `9546f568e` instead.

**Evidence of closure.** `grep -rn "unbuilt BY DESIGN\|workflow_dispatch-only"`
over `.github/workflows/` and `docs/plans/` returns nothing that contradicts
`docs/evidence/2026-08-11-wasm-tier-r22-r23-durability.md` or the deploy
workflow's own `on:` block.

**Why first.** Every later unit's justification rests on the corrected premise,
and the phase should not add a sixth document to a pile that already
misdescribes its own blocker in five places.

### U2 — The agreement ledger (R6.1, D6.4)

**Deliverable.** `tools/wasm/r19_agreement_ledger.json` (or `.jsonl`), written
by the nightly's R19 comparison step and committed back on `main`, plus a
`--check` gate so a hand-edited ledger fails CI the way every other derived
artifact in this repo does.

- Schema per row: `{crate, commit, date, run_id, compared, agree_pass,
  agree_fail, expected_fail, disagreements, streak}`.
- `streak` is derived, not stored independently — a regeneration from the row
  history must reproduce it, or the gate fails.
- The nightly already computes every input; `r19_compare.py` prints them today
  and discards them.

**Evidence of closure.** Three consecutive nightlies produce three rows for the
rotated crate with a monotonically increasing streak, and a fourth run with
`inject_disagreement` produces a row with `streak: 0`.

**Why before U3.** Raising the cadence before there is somewhere to put the
result buys nothing but CI minutes.

### U3 — Candidate-scoped cadence (R6.2, D6.3)

**Deliverable.** A `promotion_candidates` array in
`tools/wasm/wasm_tier_topology.json`. The nightly runs a native arm for every
candidate on every run, in addition to that night's rotated tier.

- Cost must be reported per run in the step summary: candidate count, added
  seconds, and the rotation's own cost, so D6.3's scaling claim stays checkable
  rather than assumed.
- Empty candidate list ⇒ behaviour identical to today. This is the anti-vacuity
  property for the unit: the change must be a no-op until a candidate is named.

**Evidence of closure.** A run with one candidate shows two native arms and a
measured delta; a run with an empty list is byte-identical in behaviour to the
current nightly.

### U4 — Prove the streak can break (R6.3)

**Deliverable.** A test — not a runbook — that drives the ledger writer with an
injected disagreement and asserts the row records it and the streak resets.

`inject_disagreement` already exists as a dispatch input and already targets
whichever tier is rotated. This unit extends the demonstration from "the run
fails" to "the ledger says why, and the streak is zero."

**Evidence of closure.** The test fails if the reset is removed from the ledger
writer. Stated explicitly because this repo has shipped anti-vacuity gates that
ran zero tests (#1423, #494385928).

### U5 — Promote one crate (R6.4, R6.5, R6.6, D6.2, D6.5)

**Deliverable.** One non-DRC crate's tier verdict is a required context in
`.github/required-checks.json`.

- **Bar, stated before measuring (R6.4):** agreement 1.0 across **10
  consecutive derivations** with no disagreement, matching the precedent Phase 1
  U6 set for R19 SUSTAINED (`docs/evidence/2026-08-07-phase1-u6-sustained-agreement.md`)
  rather than inventing a new number.
- **Recommended first candidate:** `temper-io-types` — 6,944 tests, zero
  expected failures, no R10/kicad-cli entanglement, and the largest clean corpus
  available. `temper-rust-router-core` (3,462, zero) is the fallback.
- **R6.5 must be answered in the same change, not deferred.** State plainly
  which of the two options is taken: a per-commit build arm for the promoted
  crate on the PR path, or a written scope statement that the required check
  answers for `main`'s deployed corpus plus a drift report. The second is
  cheaper and may be sufficient; what is not acceptable is promoting without
  saying which.
- **R6.6 first.** Exercise the demotion commit on a scratch branch and record
  the diff *before* the promotion lands.

**Evidence of closure.** A PR that breaks a `temper-io-types` test on wasm32 is
blocked from merging, demonstrated on a scratch PR, and the demotion commit is
shown to unblock it.

### U6 — The Phase 6 verdict

**Deliverable.** A verdict document in `docs/evidence/`, in the format of the
Phase 0, Phase 1 and Phase 5 verdicts, recording R6.1–R6.7 and whether R28 is
closed for the promoted crate and open for the rest.

## Scope Boundaries

- **`temper-drc-rs` promotion.** Blocked on R10/Q1 by D6.2. This phase may
  accumulate its agreement streak, but does not promote it.
- **R10 / Q1 (`kicad-cli` equivalence).** Untouched. It is a separate question
  with its own unresolved terminal condition.
- **R24, R25, and pool relief.** Retired by D6.1 and the Phase 5 verdict. This
  phase removes no `cargo test` step and claims no CI capacity.
- **The wasm32 build+execute step's own cost.** The nightly's header records
  that the corpus-growth problem is unsolved on that side (68s of 175s at
  measurement time, and the corpus has grown ~6.6× since). Real, and not this
  phase's.
- **Per-family coverage reporting for the other 11 crates.** The Phase 5
  verdict §6.3 names the gap (3,283 of 30,349 tests classified); closing it is
  not a gating prerequisite.

## Dependencies / Assumptions

- R22/R23 remains closed. If a future change regresses `reconcile()` or the
  dead-letter path, this phase's premise fails and U5 must stop — hence R6.3's
  insistence that the durability tests stay live.
- The deploy workflow's `push` trigger keeps the deployed corpus within one
  cycle of `main`. If deploys become dispatch-only, R6.5's cheaper option
  evaporates.
- The rotation's cost argument stays true as the corpus grows, which is why
  D6.3 scopes the cadence rise rather than reverting the rotation.
- Nine crates carrying zero expected failures reflects genuine native/wasm32
  parity, not an empty manifest that nothing writes to. `run_wasm_tests.mjs`
  exits non-zero on an unexpected pass, which is the check that makes an empty
  manifest meaningful — but this assumption is worth re-deriving in U5 for the
  chosen candidate before promoting on it.

## Outstanding Questions

**Resolve Before Planning**

- **Q6.1.** Does the required check answer for the PR's head commit or for
  `main`'s deployed corpus? R6.5 forces the answer; the choice between a
  per-commit build arm and a written scope statement is a cost/rigour trade
  nobody has priced. A per-commit arm reintroduces `cargo` on the PR path, which
  is what D12 wanted removed — and D12 is falsified, so that objection may no
  longer bind.

**Deferred to Planning**

- **Q6.2.** Does the ledger live in the repo (committed by the nightly, with the
  bot-commit noise that implies) or in R2 alongside the sweep artifacts, with a
  committed digest? D6.4 requires reviewability, which the first satisfies
  trivially and the second satisfies with an extra hop.
- **Q6.3.** What happens to a candidate's streak when its registry changes? A
  crate that gains 200 tests has not "sustained agreement" over the same corpus.
  Options: reset on registry-hash change (strict, possibly never converges on an
  active crate), carry the streak with the corpus size recorded per row (honest,
  weaker), or require N derivations at a stable registry hash.
- **Q6.4.** How many crates should be candidates at once? D6.3 makes it a cost
  question, and U3's per-run cost report is what answers it.

## Sources / Research

- `docs/evidence/2026-08-24-wasm-tier-phase5-verdict.md` — the verdict that
  retires R24 and reframes R28; this plan's Problem Frame §1, §3 and §4 come
  from its measurements.
- `docs/evidence/2026-08-11-wasm-tier-r22-r23-durability.md` — #992's durability
  work and its own §5, which named R19 sustained agreement as the real remaining
  blocker thirteen days before this plan.
- `docs/evidence/2026-08-07-phase1-u6-sustained-agreement.md` — the 10-consecutive
  precedent U5's bar adopts.
- `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md` — R15, R19,
  R22, R23, R28, D10, and Q1.
- `docs/plans/2026-08-10-001-feat-wasm-tier-phase5-plan.md` — the phase this
  succeeds; D5.4 is corrected by U1.
- `.github/workflows/wasm-tier-nightly.yml` — the rotation, its cost argument,
  and `inject_disagreement`.
- `.github/workflows/wasm-tier-pr.yml` — the advisory verdict, and the header
  U1 corrects.
- `tools/wasm/sweep_durability.mjs`, `tools/wasm/test_sweep_durability.mjs` —
  the R22/R23 implementation re-verified for this plan.
