<!-- provenance: commit=753da757781f227019c4ef95a4508ed320de7051 dirty=true (working tree carries this task's own uncommitted tools/wasm/ changes at authoring time; committed in the same PR this document ships in) -->

# WASM tier — R22/R23 result durability, implemented and fault-injected

**Date:** 2026-08-11
**Branch:** `feat/wasm-tier-durability-r22-r23`
**Task:** Close R22/R23 (result durability) in `tools/wasm/`, per
`docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md`, D10, and
report plainly whether that lifts R15.

---

## Bottom line

1. **R22 and R23, as literally defined, are now implemented in
   `tools/wasm/`** — dead-letter handling, idempotent keys, a reconciliation
   pass (R22), and replication of results outside the single point of
   failure that actually exists in this architecture (R23) — and every claim
   below is backed by a fault-injection test that fails if the property does
   not hold, not by inspection.
2. **The core invariant — dispatched == accounted-for — is now enforced and
   proven.** `sweep_multi_worker.mjs` previously had no explicit check for
   this; it happened to hold by construction (every code path pushed to a
   results array), which is exactly the kind of guarantee a future refactor
   breaks silently. It is now an assertion (`reconcile()`) with its own exit
   code, and a real subprocess test proves it catches a lost, duplicated, or
   hung delivery — see §3.
3. **R15 cannot be lifted on the strength of this work alone, and I want to
   say precisely why rather than round up.** The durability blocker D10
   named, and that `docs/plans/2026-08-10-001-feat-wasm-tier-phase5-plan.md`
   (D5.4) names as *the* explicit gate on promoting any tier verdict to
   required PR-context status, is closed. Two other, independent blockers
   the docs describe are untouched by this task and are not "durability"
   work — see §5.

---

## 1. What R22/R23 literally require, versus what was implemented

Read directly from
`docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md` (§Requirements,
§Key Decisions) — not from a summary:

> - R20. Every test outcome is recorded durably, attributable to a commit, a
>   crate, and a test function.
> - R21. Run completion is signalled back to GitHub Actions.
> - **R22.** Result delivery becomes loss-proof — dead-letter handling,
>   idempotent keys, and a reconciliation pass — before the tier's verdicts
>   gain merge authority under R15.
> - **R23.** Results are replicated outside the primary store, on the same
>   trigger as R22.
>
> - D10. Durability machinery is gated on gating (session-settled:
>   user-approved — chosen over building dead-letter handling,
>   reconciliation and replication up front: while R15 holds the tier
>   advisory, a lost result costs a data point rather than a merge). Governs
>   R22, R23.

And from `docs/plans/2026-08-10-001-feat-wasm-tier-phase5-plan.md`:

> - D5.4. R22/R23 durability is the gate on merge authority, and this phase
>   does not cross it. Restates D10's position under the new context: every
>   unit here keeps tier verdicts advisory or additive-informational, so the
>   dead-letter/idempotency/reconciliation machinery stays deferred. The
>   first unit that would make a tier verdict *required* is out of scope
>   until R22/R23 land.

**Literal reading.** R22 names three specific mechanisms — dead-letter
handling, idempotent keys, a reconciliation pass — and one bar: this must
happen *before* the tier's verdicts can hold merge authority. R23 adds one
more: replication outside the primary store, triggered the same way R22 is.
Neither requirement specifies *how* — no store, no protocol, no SLA — only
the properties.

**What was implemented, mapped 1:1:**

| Requirement | Implementation | Where |
|---|---|---|
| R22, dead-letter handling | Every request that fails delivery after retries is recorded as a terminal `error` verdict (never dropped) **and** separately written to a machine-readable dead-letter file naming exactly which `(family, index)` pairs to re-run | `writeDeadLetter()`, `tools/wasm/sweep_durability.mjs`; wired in `tools/wasm/sweep_multi_worker.mjs` |
| R22, idempotent keys | Every result is recorded into a `Map` keyed by `workKey(family, index)`. A duplicate delivery of the same verdict is a no-op; a **different** verdict for the same key is flagged as a conflict, never silently overwritten | `ResultLedger`, `tools/wasm/sweep_durability.mjs` |
| R22, reconciliation pass | After every dispatch completes, `reconcile()` compares the full dispatched-key set against the ledger and returns exactly what is missing. A non-empty result is a hard failure (exit 2), distinct from a genuine test failure (exit 1) | `reconcile()`, wired into `sweep_multi_worker.mjs`'s post-sweep phase |
| R23, replication | (a) An append-only, batch-flushed NDJSON log written **during** the run, so a crash loses at most the current flush batch, not the whole run; (b) the final summary JSON is written to two independent on-disk paths, byte-identical, both derived automatically from `--json` with no new required flag | `ReplicaLog`, `writeReplicatedSummary()`, `tools/wasm/sweep_durability.mjs` |
| (bonus, not required but load-bearing for R22's "recoverable") | `--only <key1,key2,...>` lets the dead-letter file's own keys be replayed directly — the recovery loop is demonstrated end-to-end, not just claimed | `sweep_multi_worker.mjs` |

**Gap between literal text and implementation — stated, not hidden:**

- R23 says "replicated **outside the primary store**." The only store that
  exists in this architecture is the invoking process's local filesystem —
  there is no server-side durable store to replicate *from* (the deployed
  Workers are stateless; see `sweep_durability.mjs`'s module header). What
  was built is replication onto a **second, independent file on the same
  host** — genuine insurance against a truncated write, a crashed process,
  or a bug that corrupts one file's content, but **not** against a dead disk
  or a dead host. True off-host replication (Cloudflare R2, S3, etc.) needs
  storage credentials this task was not given and did not attempt to
  provision. This is the one respect in which R23 is implemented in spirit
  and to the letter of "outside the primary store" only weakly — the
  "store" here is a single file, and the replica is a second file, which is
  outside *that* file but not outside the host.
- The "idempotent keys" property is proven exhaustively at the unit level
  (`ResultLedger.record()`, called directly, twice, with identical and
  conflicting payloads) but **not** exercised through the CLI as a genuine
  wire-level duplicate delivery. This is not a coverage gap glossed over: it
  is a structural fact of this client. `sweep_multi_worker.mjs`'s work queue
  is built by one pass over each family's index range with no repeats, and
  `fetchJsonWithRetry` only issues a second request after the first has
  fully settled (via a client-side race, not a bare `AbortSignal` the
  network layer might ignore — see `fetchOnce`'s comment), so no code path
  in this file can currently dispatch the same `(family, index)` twice
  within one run. The idempotent-key defense is real, exercised, and
  load-bearing for any *future* caller that does dispatch a key twice (the
  `--only` recovery flow is exactly such a caller, and F9 below runs it for
  real) — it is just not reachable as a same-run wire-level race today, and
  I am not claiming a fault-injection case that does not exist.

---

## 2. Was the belief correct — did `sweep_multi_worker.mjs` already track this?

The task's stated belief was that `sweep_multi_worker.mjs` does not enforce
dispatched == accounted-for. Verified by reading it before making any change
(`git show e35b6482e:tools/wasm/sweep_multi_worker.mjs` — the version this
branch forked from, HEAD of `main` for this file at the time): every code
path in the old `runOne()` did push to `results`,
including its `catch` block, so under **today's exact code shape** the
count happened to hold — a thrown `fetch` error became a pushed `error`
verdict, not a dropped one.

What was actually missing, and is the real bite of this work:

- **No explicit check.** Nothing computed "dispatched" and "accounted-for"
  as two numbers and compared them. The property held by accident of how
  `runOne` was written, not by anything that would catch a regression —
  e.g. a future change to fire-and-forget dispatch, or an unhandled
  rejection inside `pump()`'s `Promise.all`, would have silently broken it
  with no test anywhere noticing.
- **No timeout.** A hung connection (Cloudflare cold start stall, a stuck
  TCP connection) blocked that request's `await` forever with nothing
  bounding it — not a false green, but an unbounded hang indistinguishable
  from a runner timeout, which is a worse failure mode operationally (no
  attribution to which test hung).
- **No retries**, so a single transient blip turned a healthy test
  permanently into a hard `error` verdict with no attempt to recover it.
- **No dead-letter artifact.** An `error` verdict from a genuine delivery
  failure was indistinguishable, in the output, from a test whose assertion
  legitimately failed — nothing named "these specific requests could not be
  delivered, here is how to re-run exactly them."
- **Exactly-once writing of the summary.** One `JSON.stringify` +
  `writeFileSync` at the very end. A crash one line before that call loses
  every result computed during the run, with zero durable trace.

None of this is contradicted by the belief being "wrong" about the specific
mechanism — the belief that the harness does not defend against loss was
correct; the specific place it would have failed (an actively dropped
result under today's code) was narrower than stated, and the fix is broader
than "add one missing check" because R22 names three mechanisms and R23 a
fourth.

---

## 3. Fault injection — proof, not inspection

`tools/wasm/test_sweep_durability.mjs`, run via `node
tools/wasm/test_sweep_durability.mjs`: **115 assertions, 0 failures**, in two
halves.

**UNIT** (55 assertions) exercises `tools/wasm/sweep_durability.mjs`'s
exports directly and in-process: `workKey`, `ResultLedger` (including the
duplicate-delivery and conflicting-delivery cases central to "idempotent
keys"), `reconcile()` (including the case where it must report a genuinely
missing key — the anti-vacuity check that this file is proven to be able to
fail, the same discipline `test_check_deployed_freshness.mjs` established),
`fetchJsonWithRetry` (success, transient-then-recover, permanent failure,
non-2xx, missing-verdict body, unparsable JSON, zero-retry budget, and a
hang that ignores `AbortSignal` entirely — proving the client-side race
timeout, not the network layer's cooperation, is what bounds it),
`ReplicaLog` (batched flush, partial-batch retention, truncate-on-open), and
`writeReplicatedSummary` / `writeDeadLetter`.

**FAULT** (60 assertions) runs `sweep_multi_worker.mjs` as a real
subprocess — same argument parsing, same retry logic, same ledger, same
reconciliation, same exit codes — against a small fixture topology (18
tests across 3 families, not the committed 4,500+-test topology, so every
case is fast and its expected counts are checkable by hand) with
`globalThis.fetch` replaced by a fault-injecting stub, using the exact
`--import` substitution mechanism `test_check_deployed_freshness.mjs`
already established as this repo's pattern for faking the network without
touching the code under test:

| Case | Fault injected | What is proven |
|---|---|---|
| F1 | none | Baseline: a clean sweep is still green (without this, every later "goes red" claim would be unfalsifiable) |
| **F2** | 1 of 18 requests **permanently lost** (network fault on every retry) | **The central claim.** Exit nonzero, not zero. `dispatched == accounted_for == 18` (never 17). Dead-letter file names exactly the lost test. The other 17 still pass. Tally sums to 18, not 17 |
| F3 | 3 of 18 requests lost, across 3 different families | The same property holds per-family and scales past one loss — this is the scaled-down version of "3 of 27,000 lost" named in the task |
| F4 | 1 transient failure that succeeds on retry | Retries do real recovery work: exit 0, zero dead letters, the rescued test still counts as a pass |
| F5 | 1 request that **never resolves** (ignores `AbortSignal`) | Bounded by the client-side timeout (not an infinite hang), still dead-lettered, still accounted for |
| F6 | An **entire family** (4 of 18) permanently unreachable | Loss concentrated in one family is caught exactly like loss scattered across many; per-family breakdown is correct for both the affected and unaffected families |
| F7 | `--max-retries 0` against 1 transient fault | No retry budget means no rescue — dead-lettered on the first miss, attempts recorded as 1 |
| F8 | 1 permanent loss, only `--json` passed (no other durability flags) | Dead-letter file, replica JSON, and replica NDJSON log all exist at their **derived default paths** — durability is on by default, not opt-in, so the two existing CI callers get it with no workflow edit |
| **F9** | 2 of 18 requests lost, then a **second, separate subprocess run** replays exactly those 2 via `--only` after the fault clears | The recovery loop closes for real: the dead-letter file's keys are the only ones the replay dispatches, and both come back passing. Also proves `--only` fails loudly (exit nonzero, names the bad key) on an unknown key rather than silently replaying nothing |

Every case that asserts "exits nonzero" is a case where, before this
change, the identical injected fault would have produced a summary that
still printed a tally and, for F2/F3/F5/F6 specifically, **still exited
1** for the same reason (the old code's `catch` already turned a thrown
fetch into an `error` verdict) — but with no reconciliation check
confirming that, no dead-letter file to act on, no bound on how long a hang
could take, and no second copy of the results if the process died before
the final write. F8 and F9 are the cases with no equivalent in the old
code at all: derived-by-default replication, and an actual, exercised
recovery path.

**Independent confirmation against the real deployed infrastructure**
(not the fixture): `node tools/wasm/sweep_multi_worker.mjs --tier
temper-pcl-ir --json /tmp/x.json` (2 real tests) and `--tier temper-thermal`
(2,695 real tests, live count as of this session — grown from the 143 recorded
elsewhere in the topology's own comments, itself an illustration of the same
"a static number in a doc goes stale" pattern `wasm_tier_topology.json`'s
header already warns about) both completed cleanly end-to-end: real
`/health` census, real `/run-test` dispatch, real reconciliation
(`dispatched == accounted_for` in both cases), real dead-letter/replica
files written and empty, 2,695 requests in 4.68s (~576 req/s) with no
throughput regression attributable to the durability additions.

Existing tests unaffected: `test_check_deployed_freshness.mjs` (its own
53+-case suite) and `test_deploy_trigger_paths.mjs` both still pass
unmodified against this change.

---

## 4. What was NOT built, on purpose

- **No off-host replication.** Stated in §1. The residual single point of
  failure is the host/disk this sweep runs on, not the process.
- **No cross-run merge/resume tool.** `--only` replays specific keys within
  one invocation; nothing here automatically merges a recovery run's
  results back into the original run's summary file. An operator (or a
  future script) reads the dead-letter file and the recovery run's own
  output side by side. Building an automatic merge was judged out of scope:
  R22 asks for dead-letter handling to make loss *recoverable*, which
  `--only` demonstrably does (F9); it does not ask for an automated
  reconciliation-of-reconciliations tool, and inventing one would be scope
  creep against a plan that (D10) deliberately deferred durability
  machinery until it was needed.
- **No change to R20/R21.** Those requirements (durable per-commit result
  attribution; signalling completion back to GitHub Actions) are separate
  line items in the same plan, already served by the existing `--json`
  artifact-upload steps in `wasm-tier-nightly.yml`/`wasm-tier-pr.yml`. This
  task's brief and its boundary ("do NOT edit `.github/workflows/*`") both
  scope the work to R22/R23; R20/R21 were not touched.

---

## 5. Does this lift R15? No — and here is exactly what still blocks it

R15's own text: *"Verdicts from the WASM tier are advisory; native
`temper-drc-rs` and `kicad-cli` hold merge authority until R10's equivalence
bar is met."* Taken alone, R15 is gated on R10 (interval-based DRC
equivalence against `kicad-cli`), not on R22/R23 at all. R22's text is what
adds the durability precondition ("before the tier's verdicts gain merge
authority **under R15**"), and `docs/plans/2026-08-10-001-feat-wasm-tier-phase5-plan.md`
(D5.4) is where that precondition becomes operational: it is the named gate
on promoting *any* tier verdict — not only the DRC/kicad-cli one — to
required PR-context status under the R24–R28 suite-by-suite trajectory.

So there are, in the documents as written, at least **two** separate things
that must each independently hold before any tier verdict can stop being
advisory, and this task closed exactly one:

1. **R22/R23 durability (D5.4's named gate on promoting any verdict to
   required).** **Closed by this work**, evidenced above. D10's own stated
   reasoning for deferring it — *"while R15 holds the tier advisory, a lost
   result costs a data point rather than a merge"* — no longer describes
   current behavior for the mechanisms this closes: a lost result is now a
   hard failure of the sweep (exit 2, distinct from a test failure), proven
   under fault injection, never a silent gap.
2. **R19 sustained agreement.** R19's own text: *"sustained agreement is the
   bar for licensing any later gating under R15."* This is a multi-commit,
   ongoing measurement comparing tier verdicts against native `cargo test`
   verdicts for the same commit — not a durability property, and not
   something this task attempted. `docs/evidence/2026-08-07-wasm-tier-phase1-verdict.md`
   states plainly that even a completed Phase 1 "does not license merge
   gating under R15 — that requires Phase 5's suite-by-suite transition,"
   and Phase 5's own units (U1–U5,
   `docs/plans/2026-08-10-001-feat-wasm-tier-phase5-plan.md`) that would
   produce that sustained-agreement evidence per crate are, as of this
   writing, not reported complete anywhere in `docs/evidence/`.
3. **R10's kicad-cli equivalence bar**, if R15 is read at its own literal
   definition rather than through R22/D5.4's broader "any verdict" framing.
   `docs/plans/2026-08-03-002-feat-wasm-verification-tier-plan.md`'s own
   Outstanding Questions name this unresolved: *"Q1. What licenses
   `kicad-cli` retirement under R10 — how much agreement, over what corpus,
   sustained for how long. Without this the trajectory in D7 has no
   terminal condition."* Untouched by this task, and out of scope for
   durability work by any reading.

**Verdict: R15 stays advisory.** What changed today is that the specific
blocker named by D10 and operationalized by D5.4 — "durability machinery is
unbuilt" — is no longer true. What still blocks any tier verdict from
becoming required is (2) and, depending on which verdict, (3): both are
measurement/agreement campaigns, not engineering gaps in the harness, and
neither is something this task's scope (`tools/wasm/` durability) could
close.

**Handoff, per this task's own boundary** ("If promoting the tier to
required needs a workflow change, WRITE DOWN the exact change needed and
hand it off rather than making it"):

- **No workflow edit is needed for R22/R23's own failure modes to already
  be loud today.** Both `wasm-tier-nightly.yml` and `wasm-tier-pr.yml` call
  `sweep_multi_worker.mjs` and treat *any* nonzero exit as a sweep failure
  (`|| failed="${failed} ${crate}"`, unconditioned on the specific exit
  code) — so a reconciliation failure (this change's new exit code 2 path)
  already fails those jobs exactly as a test failure (exit 1) already did.
  This durability work required zero changes to either workflow file, by
  design, consistent with the boundary that assigned workflow ownership
  elsewhere.
- **The change that would still be needed, once (2) and/or (3) above are
  separately satisfied for a given crate/verdict:** add that crate's tier
  context to `required_contexts` in `.github/required-checks.json` (the
  aggregator `AGENTS.md` documents under "Board, Provenance & Requirements
  Gates" for the DRC-ceiling case — the same mechanism, different
  contexts list) so branch protection actually blocks a merge on it, not
  only reports it. That edit is out of this task's boundary and is not
  actionable yet regardless, because (2)/(3) are still open.

---

## 6. Files

- `tools/wasm/sweep_durability.mjs` — new. The durability primitives:
  `workKey`, `ResultLedger`, `reconcile`, `fetchJsonWithRetry`, `ReplicaLog`,
  `writeReplicatedSummary`, `writeDeadLetter`.
- `tools/wasm/sweep_multi_worker.mjs` — modified. Wires the above into the
  dispatch loop; adds `--request-timeout-ms`, `--max-retries`,
  `--retry-backoff-ms`, `--dead-letter-json`, `--replica-json`,
  `--replica-log`, `--replica-flush-every`, `--only`, `--topology`
  (all optional, all backward compatible — the two existing CI callers pass
  none of them and are unaffected in argument shape, only in the new
  `durability` field the JSON summary now carries).
- `tools/wasm/test_sweep_durability.mjs` — new. 115 assertions, table-driven,
  fault-injected, exits nonzero on any failure — run by hand or from the
  nightly, matching `test_check_deployed_freshness.mjs`'s house style and
  not wired into any required check (the tier itself is still advisory).
