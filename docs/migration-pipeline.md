# Migration Pipeline — Python→Rust

The per-migration pipeline for the Wave-4 full-migration program
(docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md).
Every migration runs through all stages; a candidate is not landed
until the final stage passes. Stages run in order.

## Pipeline stages

1. **brainstorm** — `ce-brainstorm` produces or refreshes the
   requirements-only unified plan for the candidate/phase
   (`docs/plans/YYYY-MM-DD-NNN-<type>-<topic>-plan.md`, per the
   artifact contract). Large/strategic plans are drafted by a
   worker-bee (V4 Flash) subagent from a detailed prompt; the
   dialogue, synthesis, and confirmation stay in the orchestrator
   conversation.

2. **doc-review** — `ce-doc-review`, dispatched as subagents on the
   plan artifact before any implementation starts:
   - `ce-adversarial-document-reviewer` — challenge the plan's claims
     against the code, the scorecards, and the artifact contract.
   - `ce-coherence-reviewer` — internal consistency, ID/reference
     integrity, no orphan/duplicate IDs, no answered-in-body
     questions.
   All P1 findings are fixed in place before stage 3 is entered.

3. **work** — implementation, dispatched as worker-bee (V4 Flash)
   subagents, one per candidate, worktree-isolated with its own
   isolated venv (`UV_PROJECT_ENVIRONMENT=/tmp/<task>-venv`):
   - TDD: differential test pinning the pre-migration implementation
     as oracle, written first (red), then the Rust pyfunction (green).
   - Behavioral A/B: bit-identical parity asserted on identical
     inputs.
   - Performance A/B: CI wall-time comparison per the plan's Q1
     tolerance policy.
   - PBT: >=5 non-vacuous properties (vacuity-guarded).
   - Metamorphic testing: >=3 invariant relations per module.
   - Induction proof: base case + induction step in the home crate's
     VERIFICATION.md.
   - Rust best practices: no unwrap outside tests, catch_unwind at
     pyo3 boundaries, borrow over clone, iterators, doc comments.
   - Commit + push to the worktree branch; the orchestrator merges
     and verifies.
   The full gate checklist — per-gate evidence locations, the
   bit-exactness catalog, and the residual decision procedure — is
   `docs/wave4-discipline-contract.md`; stage 3 is that checklist run.

4. **code-review** — reviewer personas on the merged diff:
   `ce-correctness-reviewer`, optionally `ce-adversarial-reviewer`
   and `ce-code-simplicity-reviewer`. P0/P1 findings fixed before
   stage 5.

5. **verify** — combined isolated-venv battery: cargo test for every
   touched crate, the differential/PBT/metamorphic suites, ruff,
   import-linter, vulture gate. Pre-existing failures are A/B
   verified at the base commit before being dismissed.

6. **land** — commit + PR (stacked or main-based), CI checks watched,
   merge with admin when the only red check is a documented
   pre-existing state.

## Hard rules

- Stage 2 is the only stage that reviews the plan artifact; never
  start stage 3 for a candidate whose plan has unaddressed P1 doc-
  review findings.
- Subagent work is always worktree-isolated; never let two agents
  edit the same checkout, and never rely on the shared `.venv` for
  verification runs.
- A candidate whose parity cannot be pinned bit-exactly is reported
  and recorded, not faked.
- The bit-exactness catalog (R3 of the Wave-4 plan) is checked before
  implementation and extended when a new divergence class is found.
- Branches are never cut from a dirty worktree: create the branch in
  a scratch worktree off `origin/main`, then cherry-pick the single
  docs commit onto a fresh clean branch if the shared checkout has
  drifted (the Wave-4 plan PR lost its mergeability exactly this way —
  24 stale commits inherited from the shared worktree).
