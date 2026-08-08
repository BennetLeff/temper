# Branch Protection: Verified State and a Ready-to-Execute Promotion Recommendation

**Status:** recommendation only. No branch-protection API call has been made from this
document's research. Every `gh api` command below is a read, except the two write
commands under [Exact commands](#exact-commands-copy-pasteable), which are presented for
a maintainer to run manually, not executed here.

**Verified against:** live GitHub state as of 2026-08-07 ~21:30 UTC, via
`gh api repos/BennetLeff/temper/branches/main/protection`, `gh run list`, and
`gh api .../check-runs` / `.../jobs` on `origin/main` HEAD `7e1194b7`
("fix(ci): unbreak main — codegen drift + dead mutation scaffolding (2 of 8)", #911).

---

## 1. Verified current state

```json
{
  "required_status_checks": {
    "strict": false,
    "contexts": ["Required Python Tests"],
    "checks": [{"context": "Required Python Tests", "app_id": 15368}]
  }
}
```

`main` is **not unprotected**. Exactly one context is required at the branch-protection
level: `Required Python Tests`. That context is an aggregator
(`.github/workflows/required-checks.yml`, a `pull_request_target` job that checks out
the **base** revision so a PR cannot weaken the checker from within itself) which polls
`.github/required-checks.json` and mechanically fails/passes based on 8 named contexts
in `required_contexts`:

| Required context (per `.github/required-checks.json`) | Emitting job (`python-tests.yml` line) | Name match? |
|---|---|---|
| `Fast Gates` | `fast-gates` (L3110) | Exact |
| `Core Tests` | `test` (L425) | Exact |
| `Rust Checks (cargo check + clippy)` | `rust-checks` (L790) | Exact |
| `Cargo / Rustc Smoke Check` | `cargo-smoke` (L351) | Exact |
| `Cross-Source Consistency Gates` | `consistency-gates` (L1463) | Exact |
| `Repo Hygiene & Import Gates` | `hygiene-gates` (L1731) | Exact |
| `Invariant tests (router_v6 group 3)` | `invariant-router-v6-3` (L2716) | Exact |
| `PR Performance Comparison` | `pr-perf-check.yml` (separate workflow, L84) | Exact |

No name mismatches found — every polled context string matches a job's `name:` field
byte-for-byte. This matters because a required context that never reports (a stale or
renamed string) blocks every merge forever; that failure mode is not present today.

All 8 were **green** on the current `main` HEAD (`7e1194b7`) at verification time.

## 2. Candidate assessment

Three candidates were evaluated: the two named in the task (`golden-check`,
`regression`) and the one AGENTS.md's re-measurement section depends on
(`Board, Provenance & Requirements Gates`). All three currently exist as check-runs on
PRs and on `main` pushes; none is in `required_contexts`.

**Headline finding: all three are currently red on `main` HEAD, and have been red on
every sampled run in the last several hours (30/30 push-to-main and PR runs each).**
Promoting any of them right now would block every merge immediately.

| Candidate | Green on `main` HEAD now? | Pass rate (last 30 runs) | Runtime | Stable context name? | Verdict |
|---|---|---|---|---|---|
| `Board, Provenance & Requirements Gates` | **No** — failure | 0/30 success (22 failure, 3 cancelled, 3 skipped, 2 "cancelled" retries) | ~6–9 min | Yes, unchanged job name across all runs | **Do not promote now** |
| `golden-check` | **No** — failure | 0/30 success (26 failure, 4 cancelled) | ~5 min | Yes | **Do not promote now** |
| `regression` | **No** — failure | 0/30 success (28 failure, 2 cancelled) | ~6 min | Yes | **Do not promote now** |

None of the three is "flaky" in the sense of nondeterministic pass/fail — each fails
for a specific, attributable, currently-unaddressed reason, confirmed by reading the
live logs of the `main`-HEAD run of each:

- **`golden-check`** and **`regression`** both fail on the *same* root cause: the
  `+17 via_dangling` DRC regression named in the task brief. Live log from `regression`
  (job `KiCad DRC truth gate`, run 31219138532):
  `aggregate warnings 489 exceeds ceiling 472 (+17)` / `via_dangling 32 > 15 (+17)`.
  `golden-check`'s own regression suite fails on the identical number:
  `drc_warnings: 489.0 vs baseline 472.0 (+17.0)`. This is not two independent defects —
  it is one unaddressed board regression surfacing in two gates. Fixing it (re-measuring
  and either justifying the rise with a `Ceiling-Approval:` trailer, or fixing the
  routing defect that produced the extra dangling vias) turns both gates green from the
  same PR.
- **`Board, Provenance & Requirements Gates`** fails for two *independent* reasons in
  the same run (job 92999678032): (1) the mains↔SELV physical isolation-barrier gate —
  `No keepout zone named 'MAINS_SELV_ISOLATION_BARRIER' found on the board`, a
  long-standing, not-yet-placed physical keepout; (2) `test_check_board_defect_corpus.py`
  — the board-defect corpus manifest's recorded board hash no longer matches
  `pcb/temper.kicad_pcb`'s current content (`51e39844… != 1cce4a08…`), i.e. the corpus
  manifest is stale relative to a board change that landed without updating it.

Runtime is not the blocker for any of the three (all finish in single-digit minutes,
well under the existing required set's range) — correctness is.

### A note on timing, independent of the three candidates

`main` itself had a rough day on 2026-08-07: every one of the last 30 **pushes to
`main`** before the current HEAD shows `failure` or `cancelled` at the workflow-run
level, and spot-checking the required-context jobs themselves on 9 of those pushes
shows `Fast Gates`, `Core Tests`, `Rust Checks`, `Repo Hygiene & Import Gates`, and
`Cross-Source Consistency Gates` **also** red on most of them (`Invariant tests
(router_v6 group 3)` and `Cargo / Rustc Smoke Check` stayed green throughout). The
currently-required set only returned to fully green on the very latest push
(`7e1194b7`, "2 of 8" of an in-progress "unbreak main" fix series — implying up to 6
more parts may still land). This is a separate signal from "is the candidate gate
itself broken": it means the last few hours are a bad sample window to judge *general*
CI health from, and a bad moment to make a branch-protection change of any kind, since
the required set's own freshly-recovered green streak is one data point, not an
established trend. Recommendation: confirm several more consecutive green pushes to
`main` on the *existing* required set before touching protection at all.

## 3. Pending changes that affect these gates

None of the following are on `main` yet (verified: not an ancestor of `origin/main`
via `git merge-base --is-ancestor`); each lives in another agent's worktree/branch.
Per this task's instructions, `.github/workflows/*` is out of scope to edit here — this
section is context for sequencing only.

- **BOM reconciliation gate** (`cfc81fab feat(ci): add BOM<->source reconciliation gate
  (R14)`), wired into `consistency-gates` (the same job that emits the required
  `Cross-Source Consistency Gates` context). Currently reports 49 findings. A follow-up,
  `2be59df0 chore(ci): seed R14 BOM<->source backlog so the gate stops blocking main`,
  seeds a backlog allowlist so the new gate doesn't turn the *already-required*
  `Cross-Source Consistency Gates` context red on landing. **This is the one pending
  change with the power to break an already-required context** — it must land with its
  backlog-allowlist fix in the same PR, and the promoted-context recommendation in
  §5 explicitly does not depend on it landing (it doesn't need to, but its landing
  should be watched).
- **ERC gate** (`092d3c3d ci: triage continue-on-error masks and add an ERC gate`),
  its own new workflow (`.github/workflows/erc-gate.yml`). Not wired into any of the 8
  required contexts and carries a `null` warning ceiling pending a maintainer running it
  once against the pinned `kicad-cli` version — not a candidate for promotion until it
  has a real ceiling and its own green-run history.
- **Hardened provenance checker** (`2ebf226f fix(ci): verify measured_at_commit
  resolvability, close the dangling-SHA gap`) — adds dangling-`measured_at_commit`
  detection to `scripts/check_measurement_provenance.py`, reusing
  `check_evidence_provenance.verify_commits_exist`. **Confirmed not yet present on
  `origin/main`**: `grep -n "verify_commits_exist" scripts/check_measurement_provenance.py`
  on the current `main` HEAD checkout returns nothing; the function exists only in
  `check_evidence_provenance.py` today. This runs inside
  `Board, Provenance & Requirements Gates` and does not change §2's verdict for that
  context (it was already red for two unrelated reasons before this lands), but it is
  one more reason to wait for that job to stabilize before promoting it — its own gate
  logic is mid-change.
- **14 `continue-on-error` mask removals**, same commit `092d3c3d`. Of the 14 masks
  present on `origin/main` today, **2 sit inside `Board, Provenance & Requirements
  Gates`** (L1150, L1419) and **3 sit inside the already-required `Repo Hygiene & Import
  Gates`** (L1826/1865/1870 — ruff-error backlog, sunset-informational, and one
  unlabeled). None sit inside the other 6 required contexts. `Core Tests` itself carries
  1 mask (L769, coverage gate, warn-only). Removing the 2 inside
  `Board, Provenance & Requirements Gates` will surface currently-hidden failures in that
  job the moment it lands — another reason not to promote it until after that PR merges
  and the job is observed green (or its newly-unmasked failures are triaged) post-landing.
- **`Invariant tests (router_v6 group 2)` fix.** The task asked whether the required
  **group 3** shares group 2's "runs zero tests" defect. It does not, and the two were
  independently verified from live `main`-HEAD logs in the same workflow run
  (31219138500):
  - **Group 2** (job 92999508838, `if: github.event_name != 'pull_request'`, its test
    step masked with `continue-on-error: true`): `============ no tests ran in 1.54s
    ============`, `Process completed with exit code 3`. Root cause confirmed directly:
    its file list names `tests/router_v6/test_wave4_numba_astar.py`, which does not
    exist in `packages/temper-placer/tests/router_v6/` — a deleted-path usage error,
    exactly as described. `pytest_guard.py`'s own docstring documents this exact failure
    shape (a missing path aborts collection for the whole invocation, "no tests ran").
    Masked, so it reports job-success and never blocks anything, PR or trunk.
  - **Group 3** (job 92999678054, required, **unmasked**): `699 passed, 1 skipped, 18
    xfailed in 398.73s (0:06:38)`. All 50 of its listed test files exist. It genuinely
    runs its suite and genuinely gates on the result — confirming the workflow's own
    comment ("group 3 stays un-masked — it is genuinely green") against live evidence,
    not just the comment's word for it.

## 4. Documentation note

AGENTS.md's DRC-ceiling re-measurement section previously asserted that `main` had *no*
branch-protection required status checks at all (`404 Branch not protected`). That
claim is stale relative to the live state verified in §1 — `main` does have a required
context, `Required Python Tests`. But the section's underlying conclusion is unaffected
by that correction, for a sharper reason than the original text gave: it is not that
*nothing* blocks the merge button, it is that the specific gate the DRC re-measurement
discipline depends on — `Board, Provenance & Requirements Gates` — **is not one of the
8 contexts `Required Python Tests` polls**. A red run of that job today still does not
block a merge, for the same practical effect as if there were no protection at all, on
exactly the PRs that section cares about. Promoting `Board, Provenance & Requirements
Gates` into `required_contexts` — once it is green (see §2, §5) — is what would turn
AGENTS.md's stated contract from aspirational into actually enforced. This is the
strongest single argument for eventually making the change described in this document:
it closes the exact gap that let a dangling `measured_at_commit` and the unaddressed
`+17 via_dangling` regression both sit on `main` for weeks under a gate that runs, goes
red, and blocks nothing.

## 5. Recommendation and sequencing

**Do not promote anything today.** All three candidates are currently red; promoting a
red context blocks every merge immediately, which is the one outcome this task exists
to prevent. Sequence:

1. **Now → land the DRC regression fix.** Re-measure `pcb/temper.kicad_pcb` per
   AGENTS.md's re-measurement procedure, and either fix the routing defect behind the 17
   extra `via_dangling` warnings or justify the rise with a `Ceiling-Approval:` trailer
   and an attributed `_march` entry in `drc_ceiling.json`. This single fix is expected to
   turn both `golden-check` and `regression` green, since both fail on the identical
   number today.
2. **Then → confirm `golden-check` and `regression` green for several consecutive runs**
   (not just one — both were 0/30 in the sampled window, so one green run after the fix
   is a start, not proof of stability). Once confirmed stable, promote both together
   (they share a root cause and a fix; promoting one without the other leaves an
   asymmetric gap for no reason).
3. **In parallel → land the `Board, Provenance & Requirements Gates` fixes**: place the
   `MAINS_SELV_ISOLATION_BARRIER` keepout zone, and re-sync the board-defect corpus
   manifest's recorded hash with the current `pcb/temper.kicad_pcb`. Also let the 2
   `continue-on-error` mask removals inside this job (from `092d3c3d`) land and observe
   what they unmask — promote only after the job is green *with the masks already
   removed*, not before, since promoting first would hide exactly the regressions those
   masks were suppressing.
4. **Once §3 is green → promote `Board, Provenance & Requirements Gates`.** This is the
   change with the direct payoff described in §4 — it is what actually enforces the
   re-measurement and provenance discipline AGENTS.md already documents as if it blocks
   merges.
5. **Not yet, and not addressed by this recommendation**: the new BOM reconciliation
   gate (still at 49 findings, backlog-allowlist fix in flight — watch that it doesn't
   redden the *already-required* `Cross-Source Consistency Gates` on landing), the new
   ERC gate (no ceiling measured yet), and `Invariant tests (router_v6 group 2)` (fix
   not yet landed; group 3's required status is unaffected and correctly scoped as-is).
   None of these should be promoted until each has its own multi-run green history,
   following the same standard applied to the three candidates in §2.
6. **Before any promotion, regardless of the above**: confirm the currently-required 8
   contexts have shown several consecutive green pushes to `main` (see the timing note
   in §2) — `main` only just recovered from a same-day incident spanning most of
   2026-08-07, and a protection change should not be the first thing that happens after
   a fresh recovery.

## Exact commands (copy-pasteable)

Not run. For a maintainer to execute once §5's prerequisites are met — promote only the
contexts that are confirmed green at that time; do not copy this payload verbatim if
fewer than all three have landed their fixes.

**Apply (adds all three once each is confirmed stable — adjust the `contexts` array to
promote a subset if they land at different times):**

```bash
gh api -X PATCH repos/BennetLeff/temper/branches/main/protection/required_status_checks \
  -H "Accept: application/vnd.github+json" \
  -f strict=false \
  -f 'contexts[]=Required Python Tests' \
  -f 'contexts[]=golden-check' \
  -f 'contexts[]=regression' \
  -f 'contexts[]=Board, Provenance & Requirements Gates'
```

Equivalent full-JSON form (use if the `-f contexts[]=` repeated-flag form is rejected by
the `gh` version in use):

```bash
gh api -X PATCH repos/BennetLeff/temper/branches/main/protection/required_status_checks \
  -H "Accept: application/vnd.github+json" \
  --input - <<'EOF'
{
  "strict": false,
  "contexts": [
    "Required Python Tests",
    "golden-check",
    "regression",
    "Board, Provenance & Requirements Gates"
  ]
}
EOF
```

**Revert (back to exactly today's verified state, §1):**

```bash
gh api -X PATCH repos/BennetLeff/temper/branches/main/protection/required_status_checks \
  -H "Accept: application/vnd.github+json" \
  --input - <<'EOF'
{
  "strict": false,
  "contexts": [
    "Required Python Tests"
  ]
}
EOF
```

Both commands touch only `required_status_checks.contexts` — no other branch-protection
field (`enforce_admins`, `required_signatures`, `allow_force_pushes`, etc.) is read or
written by either, all of which are already `false`/unset per §1 and are out of scope
for this recommendation.
