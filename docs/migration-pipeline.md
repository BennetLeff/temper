# Migration Pipeline — Python→Rust

The per-migration pipeline for the Wave-4 full-migration program
(docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md).
Every migration runs through all stages; a candidate is not landed
until stage 6 passes. Stages run in order; stage 7 (wire) follows
immediately, and stage 8 (retire) follows once the retirement bar in
Hard rules is met — it may trail stage 6 by many commits, but it is
owed, not optional.

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
   - Performance A/B: CI wall-time comparison per the plan's R2
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

7. **wire** — repoint the production caller at the Rust kernel; the
   oracle is not touched at this stage:
   - Repoint the production call site(s) to the Rust kernel/pyfunction.
     Stage 3 already proved the kernel correct; this stage proves it
     used.
   - Delete the now-dead Python *implementation* — not the oracle,
     which stage 8 disposes of separately.
   - Prove it via `scripts/check_unwired_kernels.py` (PR-blocking as of
     #1004): the kernel drops off `.unwired-kernel-inventory`, or, for
     a legitimate never-wire-by-design entry, the ledger reason is
     added or corrected instead.
   - Commit + push per stage 3's worktree discipline; the orchestrator
     merges and verifies.

8. **retire** — once the differential has held for the retirement bar
   (Hard rules), dispose of the oracle and delete the differential's
   Python dependency:
   - Classify the oracle: FREEZE / REIMPLEMENT / KEEP (Hard rules).
     FREEZE is the default.
   - FREEZE: snapshot the oracle's outputs over a fixed input corpus
     into golden vectors, delete the Python oracle, keep the
     differential running against the frozen vectors.
   - REIMPLEMENT: write an independent Rust oracle from the
     specification — never from the Rust implementation under test,
     which yields two copies of the same bug and reports green.
   - KEEP: retain the Python oracle, with a written reason recorded
     alongside it.
   - Never retire by bulk import-scan deletion (Hard rules).
   - Commit + push per stage 3's worktree discipline; the orchestrator
     merges and verifies.

## Hard rules

- Stage 2 is the only stage that reviews the plan artifact; never
  start stage 3 for a candidate whose plan has unaddressed P1 doc-
  review findings.
- Subagent work is always worktree-isolated; never let two agents
  edit the same checkout, and never rely on the shared `.venv` for
  verification runs.
- A candidate whose parity cannot be pinned bit-exactly is reported
  and recorded, not faked.
- The bit-exactness catalog (Wave-4 discipline contract, section 2) is
  checked before implementation and extended when a new divergence class
  is found.
- Branches are never cut from a dirty worktree: create the branch in
  a scratch worktree off `origin/main`, then cherry-pick the single
  docs commit onto a fresh clean branch if the shared checkout has
  drifted (the Wave-4 plan PR lost its mergeability exactly this way —
  24 stale commits inherited from the shared worktree).
- Oracle disposition (stage 8) is exactly one of three routes; there is
  no default to "leave it":

  | route | when | effect |
  |---|---|---|
  | **FREEZE** | default; the kernel is deterministic and its input domain is enumerable or samplable | golden vectors from a fixed corpus, Python deleted, differential becomes wasm32-tier-executable |
  | **REIMPLEMENT** | continuous adversarial differential value is high: safety kernels (creepage, clearance, via/keepout geometry) | independent Rust oracle written from the specification; costs a genuine second implementation |
  | **KEEP** | CPython itself is the reference (a Python library's exact semantics, or a host-libm/`dlsym` property) | no change; must carry a written reason |

  Translating a Python oracle into Rust *from the Rust implementation*
  is never a valid route under any of the three — it yields two copies
  of the same bug and reports green, which is strictly worse than no
  oracle.
- Retirement bar: **R19 sustained agreement** — the same shape and
  number the WASM tier uses to license a crate's native suite off
  GitHub Actions (`tools/wasm/u6_campaign.sh`): 100% differential
  agreement across 10 consecutive `origin/main` commits, zero
  disagreements. REIMPLEMENT-class safety kernels are exempt — they
  keep a live differential indefinitely by design.
- Bulk import-scan deletion is never the retirement mechanism for a
  kernel's dead Python or its oracle. Commit `47349a50d` (2026-08-08)
  deleted `router_v6/pad_connectivity_audit.py` — the project's own
  declared PRIMARY routing-completion metric — because its import scan
  covered `src/` and `tests/` but not `scripts/`; `scripts/route_board.py:269`
  calls it unconditionally, so `make route` died with `ImportError` and
  true completion was unmeasurable for three days, until PR #1008
  restored it. Per-kernel retirement (stage 8) is safer than bulk
  deletion because at retirement time the pipeline knows exactly which
  Python the Rust replaced; a later import scan does not.
