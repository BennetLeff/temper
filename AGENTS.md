# Instructions for AI Agents

## Project Context

**This is the Temper induction cooker project:**
- **Firmware**: ESP32-S3 with 8-state machine
- **PCB**: KiCad design with temper-placer optimizer
- **Language**: C (firmware), Python + Rust (placer)

**Key areas:**
- `firmware/` - ESP32-S3 control code
- `packages/temper-placer/` - CP-SAT PCB placement optimizer with Rust geometry/DRC crates
- `elec/` - Atopile electrical schematics
- `docs/solutions/` - documented fixes for past problems (bugs, patterns, tooling decisions), organized by category with YAML frontmatter — search before implementing or debugging in a known area

## Firmware Config Codegen

`firmware/config.h` is generated from `firmware/config.yaml` by
`firmware/tools/gen_config.py`. After editing the manifest:

```bash
python3 firmware/tools/gen_config.py
git add firmware/config.h && git commit -m "chore: regenerate config.h"
```

CI regenerates and `git diff --exit-code`s against the committed copy.

## Transition Table Regeneration

`firmware/main/transition_table.h` is generated from `firmware/transition_table.yaml`
by `firmware/tools/gen_transition_table.py`. After editing the manifest:

    python3 firmware/tools/gen_transition_table.py
    git add firmware/main/transition_table.h && git commit -m "chore: regenerate transition table"

CI regenerates and `git diff --exit-code`s against the committed copy.

`firmware/test/test_transition_table_generated.c` is also regenerated from the
same manifest via `firmware/test/gen_transition_table.py`. After manifest edits:

    python3 firmware/test/gen_transition_table.py --generate
    git add firmware/test/test_transition_table_generated.c
    git commit -m "test: regenerate transition table tests"

## Board Change -> DRC Ceiling Re-measurement

`power_pcb_dataset/drc_ceiling.json` records DRC violation counts for
`pcb/temper.kicad_pcb` with a content-hash `provenance` block
(`scripts/check_measurement_provenance.py`). **Any PR that touches
`pcb/temper.kicad_pcb` must re-measure and update `drc_ceiling.json` in the
*same* PR, not as a follow-up.** The re-measurement is logically part of the
board change, exactly like the firmware codegen steps above are part of
their manifest edits -- it is not a separable chore for someone else to
notice later.

Re-measure with the same tool, flags, and sample count every prior entry in
the file's own `_march` log used (read that log before touching a number --
it documents "observed max + 1 headroom" for the one genuinely
nondeterministic category, `clearance`, and the reasoning behind every prior
ceiling move):

    export PYTHONPATH="$(pwd)/packages/temper-placer/src"
    python3 -c "
    from pathlib import Path
    from collections import Counter
    from temper_placer.validation._drc_api import run_drc
    # run_drc() always passes --all-track-errors -- bare kicad-cli without it
    # is not reproducible (see _drc_api.py's own comment: 69-88 shorting_items
    # across 4 runs on a byte-identical board, measured 2026-07-29).
    # Run 120 times and take the observed range per category, not one sample.
    # Record the count in provenance: the structured sample_count field, or
    # measured_via prose on legacy records -- the approval gate requires
    # >= 120 for the nondeterministic clearance category.
    "

Then, in `power_pcb_dataset/drc_ceiling.json`:
- Update `violations_by_type` / `warnings_by_type` to the new observed counts.
- Update `provenance` (commit, branch, dirty, input hash, tool version).
- Append a new `_march` entry naming what changed and why, attributing every
  per-type delta to a specific cause (which component, which commit) rather
  than reporting only the aggregate.
- If any per-type or aggregate ceiling would RISE, the commit needs a
  `Ceiling-Approval:` trailer (enforced by
  `scripts/check_drc_ceiling_approval.py`) -- a rise is legitimate only for
  measured run-to-run noise or an already-investigated, attributed,
  deliberate change; never to silently absorb an unexplained regression. If
  you can't attribute a rise, stop and report it instead of ratcheting past it.

**The approval is machine-checked (R27 monotone contract).**
`scripts/check_drc_ceiling_approval.py` requires a raise to carry, in the
*same* PR: (1) a `Ceiling-Approval:` trailer on a PR commit -- the raise
detector, a plain substring deliberately not parsed further; (2) a NEW
non-empty `_march` entry naming the cause -- the `_march` log is the single
cause authority, there is no trailer-body grammar; and (3) a fresh
measured-live `provenance` record on the raised board: `source:
"measured-live"`, a resolvable `measured_at_commit`, `dirty: false`, a
recorded kicad-cli version, at least 120 samples for the nondeterministic
`clearance` category (structured `provenance.sample_count`, or the legacy
`measured_via` prose on records that predate the field), and an input hash
still matching `pcb/temper.kicad_pcb`'s current content. A raise that
fails any of these is an unapproved raise, mechanically. Existing `_march`
entries and records are grandfathered; the contract applies to new raises.

**Why this must land in the same PR, not after**: `check_measurement_provenance.py`
fails closed the moment the board's content hash no longer matches this
file's recorded hash -- it already catches an unpaired board change, on the
board-changing PR itself, before merge. It does not, by itself, stop that
PR from merging. As of 2026-08-07, `main` **does** have branch-protection
required status checks (`gh api repos/<org>/<repo>/branches/main/protection`
-> `required_status_checks.contexts: ["Required Python Tests"]`; this
superseded the earlier "no branch protection at all" state this section
used to cite) -- but `Required Python Tests` is an aggregator
(`.github/workflows/required-checks.yml`, driven by
`.github/required-checks.json`) polling a fixed, named list of contexts,
and `Board, Provenance & Requirements Gates` -- the job this file's
provenance and DRC-ceiling checks run in -- is **not** one of them (see
`required_contexts` in `.github/required-checks.json`). So the conclusion
is unchanged, for a sharper reason than before: it is not that nothing
blocks the merge button, it is that the specific gate this section depends
on is not wired into what does. A red run of this job still does not block
merging. Landing the re-measurement inside the same commit is what
actually prevents the gap (there is no red window to begin with); a
separate follow-up PR only repeats the pattern this section exists to
stop, and depends on a person or agent remembering to open it before the
board moves again. See `docs/evidence/2026-07-30-drc-ceiling-remeasurement-cascade.md`.
The durable fix is adding `Board, Provenance & Requirements Gates` to
`required_contexts` in `.github/required-checks.json` (a maintainer call --
it changes what blocks every PR, not just DRC-adjacent ones -- not applied
by this section).

**Identity: what a measurement is anchored to, and why a squash merge must
not be able to orphan it.** 2026-08-07 incident:
`drc_ceiling.json`'s `provenance.measured_at_commit` was
`3410ee4e1fe8c3a5cce13b9262585016a06fce8d` -- a commit absent from this
repository's object store entirely (`git cat-file -t` fails on it).
Root cause, confirmed against `git log -p` and the GitHub API: the PR that
recorded it (#602, branch `feat/k3-swap-and-board-write`) named a
mid-development branch commit as the measurement anchor; that branch was
rebased more than once before merging (its own commit trailers say
"re-point wave-2 provenance to post-rebase HEAD"), and the squash/rebase
orphaned the original commit object before the PR landed. Neither existing
check would have caught it: `validate_provenance_shape` only checks that
`measured_at_commit` is 40 lowercase hex characters or `"UNKNOWN"` --
shape, not existence -- and `DrcRatchet.validate_raise_evidence`'s commit
check (`_SHA256_HEX_RE.fullmatch`) is the same regex-only check despite its
error message claiming otherwise, and it only runs when a ceiling *raise*
is being approved, not on every re-measurement.

The fix (`scripts/check_measurement_provenance.py`, 2026-08-07): a
measurement's **primary, authoritative identity is the content hash**
already recorded at `provenance.inputs[].sha256` -- this was already true
in design (the module docstring's "informational, never the thing
compared" language predates this incident) but was not fully true in
enforcement. `measured_at_commit` is **advisory** -- useful for a human
tracing which run produced a number -- but is now also **verified for
resolvability whenever it is not `"UNKNOWN"`**, via
`check_evidence_provenance.verify_commits_exist` (the same
`git cat-file --batch-check` mechanism that already closed this exact hole
for `docs/evidence/*`, reused rather than reimplemented). A commit SHA was
rejected as the *primary* identity outright, not merely deprioritized: it
is not stable under history rewriting by construction (squash merge,
rebase, `git gc` pruning an unreachable object), while a raw content hash
of the file bytes is independent of git object model, mtimes, or commit
topology entirely -- the only signal that directly answers "is this the
same content" regardless of how the repository's history around it
changed. A **dangling** `measured_at_commit` (well-formed but unresolvable)
is now treated as a hard failure -- worse than an honest `"UNKNOWN"`,
because it claims traceability it does not have while looking exactly like
a record that does. A `dirty: true` record is now also a hard failure on
every provenanced record, not only on a ceiling raise: an unnamed
uncommitted change at measurement time could have influenced the result
without ever appearing in `inputs`, which the content-hash check cannot
see. All three of these are checked unconditionally by
`check_measurement_provenance.py` on every PR that touches a registered
measurement artifact -- not only on a ceiling raise -- so a bad record now
fails closed on the PR that writes it, the same "same-PR" discipline this
section already requires of the re-measurement itself. See
`scripts/check_measurement_provenance.py`'s module docstring for the full
incident writeup and design rationale, including the alternatives
considered and rejected (re-anchoring freshness on the commit SHA instead
of content; silently downgrading a dangling commit to `"UNKNOWN"` instead
of failing on it).

## Import Boundary Check

Before pushing, verify your changes don't violate import boundaries:

```bash
uv run python scripts/import_linter_gate.py
```

If violations are reported:
1. Check `.importlinter` for the boundary contract violated
2. Option A: Move the import to a permitted module (use public `__init__.py` exports)
3. Option B: Add an allowlist entry to `import-linter-allowlist.yaml` with justification + ticket reference

The same check runs in CI. After the soft-launch period (until 2026-07-06), violations block PR merge.
See `docs/plans/2026-06-22-014-feat-import-linter-boundary-enforcement-plan.md`.

## GitHub Actions Workflow Linting

Any change under `.github/workflows/` is linted by `actionlint` (the
`Lint Workflows` CI job). It catches the failures that silently abort a run:
YAML indentation mistakes, duplicate keys (e.g. two `permissions:` blocks in
one job), unknown runner labels, and bad action references.

Run it locally before pushing workflow edits:

```bash
brew install actionlint   # or: go install github.com/rhysd/actionlint/cmd/actionlint@latest
SHELLCHECK_OPTS='--severity=error' actionlint -ignore 'constant expression "false" in condition'
```

Custom self-hosted runner labels are declared in `.github/actionlint.yaml`.

## Script Manifest Convention

Every `scripts/*.py` file must have an entry in `scripts/manifest.yaml`. The
CI `check_manifest_gate` rejects new scripts without a manifest entry.

**Adding a new script:**

1. Add an entry to `scripts/manifest.yaml`:
   ```yaml
   - path: your_script.py
     purpose: "What the script does"
     owner: your-name
     last_run: "2026-06-22"
     category: keep          # or ticket / delete
     disposition: utility    # or ci-gate / shell-invoked / temper-scripts-sunset
     imports: []             # populated by `scripts/trace_invocations.py`
   ```
2. Run `uv run python scripts/trace_invocations.py` to refresh the invocation graph
3. CI will fail on missing entries (`check_manifest_gate`); sunset warnings
   fire on stale `last_run` dates after 30/60 days (`check_script_sunset`)

**Sunset clock (per plan 2026-06-22-021):**
- 30 days no invocation → WARNING (keep/ticket)
- 60 days no invocation → ESCALATE (ticket auto-promotes to delete priority)
- Sunset never auto-deletes; deletion is always a `git rm` by a human

See `docs/plans/2026-06-22-021-feat-script-triage-sunset-plan.md`.

## Git Stash Guard

**Never use `git stash`, in any form, in this repo.** This repo runs 60+
concurrent agent worktrees against one shared `.git` directory, and the
stash stack is repo-global — it is not per-worktree. A `git stash pop` run
from your worktree can apply *another session's* stashed changes into your
working tree, and a `git stash drop`/`clear` can destroy another session's
unrecovered work. This has already happened more than once; the stash list
currently sits 80+ entries deep, including rescue records from prior
incidents. Asking politely does not hold at this concurrency: an agent used
`git stash` anyway on 2026-07-28 despite an explicit brief prohibition, and
avoided data loss only by luck (its push/pop happened to balance).

**Enforcement**: `scripts/git-hooks/reference-transaction`, installed into
the shared `.git/hooks/` directory by `scripts/install_git_stash_guard.py`,
blocks `git stash` / `git stash push` / `git stash save` / `git stash clear`
outright (exit 128, `fatal: ref updates aborted by hook`). This is a real,
tested block — verified to fire under non-interactive, direct `git`
invocation, from every worktree sharing this repo's `.git` directory,
without relying on any shell alias or `PATH` trick (a git hook is invoked by
the `git` binary itself, regardless of what invoked `git`).

**Known, tested gap — read before assuming full coverage**: the hook
*cannot* block `git stash apply`, because `apply` never performs a ref
transaction (no hook of any kind fires for it). It also cannot reliably
block `git stash pop` / `git stash drop <entry>` except in the edge case
where the entry being removed is the *only* one left on the stack — with
80+ existing entries, dropping/popping any one of them rewrites the reflog
directly, bypassing the hookable ref-transaction API entirely. **Do not
treat the hook as covering `apply`, `pop`, or `drop` of existing stack
entries — the prohibition on those remains a policy rule, not an enforced
one.** See the comments at the top of
`scripts/git-hooks/reference-transaction` for the full empirical writeup
(what was tested, in a throwaway `/tmp` repo, and what the results were).

**Detector (defense in depth for the gap above)**:
`uv run python scripts/check_stash_stack_gate.py` snapshots the stash
reflog and diffs it against the last snapshot, flagging any addition or
disappearance since the last run. It is not a CI gate (CI runners don't
share this `.git` directory) — run it manually, on a timer, or from a
`/loop` against the actual dev machine.

**Bypass** (for a human, working alone, in a clean single-worktree
context — not the concurrent-agent failure mode this guards against):

```bash
ALLOW_GIT_STASH=1 git stash push -m "..."
```

**Safe alternative** (the underlying need — comparing with/without your
changes — is real and not disabled, just routed elsewhere):

```bash
git worktree add ../scratch-<name> -b scratch/<name>   # isolated copy
git branch wip/<name> && git commit -am wip             # scratch branch
git diff > /tmp/patch.diff                               # patch file, git apply later
```

**What was ruled out and why** (see the PR that introduced this section for
the full test transcript): a `pre-commit` hook never fires for stash (it's
not a commit operation). A shell alias/function shadowing `git stash` only
protects interactive shells that source it, and agents invoke `git`
directly. A `git config alias.stash=...` override was tested empirically
and does **not** work — this git version resolves built-in commands
(`stash`, `status`, `log`, ...) before consulting aliases, so an alias can
never shadow an existing subcommand, only add a new one. A `PATH` wrapper
earlier than the real `git` was not pursued: it requires modifying the
user's shell environment (not something a repo-scoped fix should assume or
require) and offers no more coverage than the hook already provides.

## Building and Running Firmware Tests

```bash
cmake -B firmware/test/build firmware/test
cmake --build firmware/test/build
./firmware/test/build/test_state_machine_only
```

## Regenerate derived artifacts before pushing

```bash
make regen         # regenerate what is safe; refuse where it would hide a defect
make regen-check   # report only -- what CI's gates will see
```

Several committed files are *generated* from source: `README.md`'s package and
plan counts, `scripts/oracle_hashes.json`, the wasm test registry. When one
drifts behind a change, the gate that polices it fails on `main` **after** the
merge, and every open PR inherits the red. That happened four times on
2026-08-06 — README counts after a merge run, the oracle registry after the
gate landed, the workspace package count after a crate was added, and the
oracle registry again after five oracles were added.

`make regen` deliberately does **not** regenerate everything. Two of these
artifacts are evidence, not output, and it refuses rather than laundering them:

- A **hash-order `NEW_SITE`** is a determinism *defect* — a `set` iterated to
  build an ordered artifact carries `PYTHONHASHSEED`'s order into it. Fix the
  iteration (project through the input, or sort). Do not add it to
  `.hash-order-inventory`. Paid-down `STALE_ENTRY` records are written, since
  that is the shrink direction.
- A **drifted oracle pin** means a verbatim oracle's bytes changed, which is
  exactly what `check_oracle_hashes.py` exists to catch. `make regen` prints the
  commit that last touched each drifted file so the cause can be established,
  and records it only under `--accept-oracle-drift`. A genuinely *new* oracle is
  unregistered rather than drifted, and is recorded without ceremony.

## Shared cargo build cache — required when working in a worktree

Before invoking `cargo` or `maturin` **directly** (not via `make`), source
this once per shell:

```bash
source scripts/cargo_shared_env.sh
```

Anything run through `make` already exports the same value and needs no
action.

Why it matters: `.cargo/config.toml` sets `build.target-dir` to the
*relative* path `target-shared`. Cargo resolves a relative `target-dir`
against the config file's own directory, and every git worktree gets its own
tracked **copy** of that file — so each worktree lands on its own
`target-shared` and compiles all 10 pyo3 crates from cold. `CARGO_TARGET_DIR`
overrides `build.target-dir` and can hold an absolute path, which is why the
sharing is done there rather than in the config.

This is not hypothetical. It caused the 51 GB incident the config block
cites, and it recurred on 2026-08-06: 25 private caches totalling 36.6 GB,
the disk at 98%, and 16 GB reclaimed by hand. Agent worktrees are the main
source, because they are created outside the repo tree (`/private/tmp/...`)
and then run `cargo test` / `cargo build` / `cargo clippy` directly.

The trade-off is deliberate and unchanged: cargo takes an exclusive lock on
the target directory, so concurrent builds in different worktrees serialise
instead of running in parallel. That is still far cheaper than each doing a
cold build — after the first, the rest are incremental.

## Rebuilding pyo3/maturin Rust Extensions

This repo has 10 pyo3/maturin extension crates under `packages/`. A merge
that touches Rust source leaves the *installed* `.so` stale — it still
imports, so nothing looks broken until a symbol is missing or a test
asserts against frozen behavior. `scripts/check_stale_extensions.py`
detects this (STALE per crate); it does not fix it.

```bash
make extensions-check   # report only -- same gate CI runs
make extensions          # rebuild every pyo3/maturin crate in one command
```

`make extensions` derives its crate list from
`scripts/check_stale_extensions.py --list-crates`, the same
`discover_crates()` scan the gate itself checks freshness against — it is
not a hand-maintained list that can drift. Each crate is rebuilt with
`uv run --no-sync maturin develop --release --manifest-path <path>`.
`--no-sync` matters: a bare `uv run` can re-sync `.venv` against
`uv.lock` and silently evict the very `.so` files this target just
built (this bit a session in practice before this target existed).
`temper-constraints` additionally needs
`PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1` (mirrors the equivalent step in
`.github/workflows/python-tests.yml`).

After `make extensions`, `uv run --no-sync python
scripts/check_stale_extensions.py` should report 0 STALE.

### Worktree `.venv`: shared vs. isolated

Multiple agent worktrees historically pointed `UV_PROJECT_ENVIRONMENT` at
the main checkout's already-synced `.venv` to save disk/build time. This
was the dominant infrastructure cost in this repo on 2026-07-28 (see
`docs/solutions/best-practices/shared-mutable-state-dominant-cost-multi-agent-repo-2026-07-28.md`):
a concurrent session's `uv sync` (or a bare `uv run`'s implicit auto-sync)
can silently revert an extension a *different* worktree just built, and
`check_stale_extensions.py`'s old mtime comparison false-positived on
every fresh `git checkout -b` regardless of real staleness.

Two independent fixes, addressing two independent hazards:

1. **The gate no longer trusts mtimes when a build stamp is present.**
   `scripts/write_extension_stamps.py` records a content-hash of each
   crate's sources beside its installed `.so`; `check_stale_extensions.py`
   compares against that first and only falls back to mtime when no stamp
   exists. This makes a *shared* `.venv` safe against the checkout-mtime
   false positive — it does **not** protect against a concurrent session's
   build genuinely evicting yours; that is a different failure mode (see
   `scripts/_lib/freshness.py`, and
   `docs/solutions/best-practices/green-rust-tests-are-not-evidence-the-extension-was-rebuilt-2026-07-27.md`).
2. **`make venv-isolate` gives a worktree its own `.venv`**, immune to
   *any* other checkout's `uv sync`/`uv run`, at a measured cost of
   ~700 MB disk and ~85s wall time with a warm `uv`/cargo cache (the
   shared `target-shared` Cargo build directory from `.cargo/config.toml`
   means the Rust half compiles incrementally even into a brand-new venv
   — see `docs/evidence/2026-07-28-worktree-env-isolation.md` for the
   measurement). Run it once, at the start of any session that will build
   or test Rust extensions.

**This is not the default for every worktree unconditionally.** At fleet
scale (dozens of agent worktrees existing at once, low double-digit GB
free) giving every one its own copy regardless of whether it does active
build/test work is the same disk-multiplication hazard that has already
exhausted disk twice. Isolate the worktrees that are actually building or
testing Rust extensions; rely on the content-hash gate (unconditional,
zero downside) everywhere else.

## Documentation & Context Maintenance

**Critical Rules for AI Agents:**

1.  **Context Awareness**: Before editing or using a script, check for a corresponding `*_INSTRUCTIONS.md` or `*_DESIGN.md` file in the same directory or project root (e.g., `AUTOMATED_PCB_DESIGN_INSTRUCTIONS.md`). Read it to understand the "Why" and "How" of the tool.
2.  **Documentation Sync**: If you modify the logic of a script (e.g., `add_power_planes_v2.py`), you **MUST** update the corresponding instructions file to reflect the change. Code and documentation must never drift apart.
3.  **Decision Logging**: Major architectural decisions must be recorded in `docs/` or the relevant `*_INSTRUCTIONS.md` file. Do not rely on git history alone.

### Traceability Convention

Inline `# @req(<plan-id>, <req-id>): <note>` comments link code to plan
requirements. Two CI gates enforce consistency: every claimed @req tag must
correspond to a live requirement in a plan document, and every plan's
non-deferred requirement must have at least one code annotation — but only
in directories that have opted in via a `TRACEABILITY` sentinel file.

See `docs/TRACEABILITY.md` for the full specification.

## Physics Verification Conventions

### Bug-Triage Rule (R22)

When an invariant surfaces a real bug, produce a triaged bug report. Trivial fixes
in-scope: sign flip, index/stencil mis-orientation, BC swap, off-by-one. Architectural
fixes (e.g., "the solver needs a different discretization") are documented and scoped
as a separate follow-up — do not inline a redesign in a bugfix PR.

### Future CP-SAT Physics Constraint Discipline (R24)

Any future CP-SAT constraint that gates on a physics quantity (e.g., zone penalty
from a thermal field) must carry:

1. A **Chebyshev-style soundness proof** — the constraint is either a conservative
   bound (overestimates cost / underestimates margin) or the proof classifies the
   approximation error.
2. **BMC-exhaustive validation on small N** — the constraint is verified against
   a truthful oracle on all inputs up to a bounded size.
3. **Post-solve audit** — after each CP-SAT solve, the constraint's actual value is
   recomputed from the placement coordinates and compared against the encoded bound;
   a mismatch is a hard CI failure.

These gates are prerequisites for the constraint to ship; they are NOT optional
nice-to-haves. See `docs/physics-verification-methodology.md` for the broader
verification pattern.

## Session Lifecycle

### Base-Commit Assertion (Session Start — do this first)

Before measuring, building, or concluding anything, confirm you are actually
on the commit/branch you were told to work from:

```bash
scripts/assert-base.sh <expected-ref>
```

`<expected-ref>` is whatever you were dispatched against (a branch name, a
SHA, `origin/main`, ...). Exit 0 means you match; exit 1 means you don't
(it prints both SHAs and how far apart they are — the fix is almost always
`git rebase <expected-ref>`, not a force-checkout); exit 2 means the ref
itself doesn't resolve (typo, or you need to `git fetch` first).

This exists because it kept not happening: four confirmed cases in one day
of an agent measuring in a stale worktree and reporting the result as
current state — a "broken" crate that builds fine one commit later, a
fault-tree survey that was correct for a tree that no longer exists, two
agents that started work from commits several patches behind the branch tip
they thought they were on. See `docs/METHODOLOGY.md` Sec 5 ("a measurement
carries the commit it was taken at, or it is not a measurement") and
`docs/evidence/2026-07-26-measurement-provenance.md`. Every dispatch that
names a base commit or branch should have the receiving agent run this
before doing anything else.

Note the check is exact-match, not ancestry: once you've legitimately
rebased onto `<expected-ref>` and made your own commits on top, HEAD no
longer equals it and a re-run correctly reports FAIL (you're ahead, not
on it anymore) -- that's expected, not a bug. Re-run the assertion mid-session
only if you suspect the *base* moved out from under you (e.g. a long-running
session on a shared branch); if it fails with HEAD *behind* the expected
ref, rebase before trusting anything you measured after that point.

### Issue Tracking & Management

*   **Granularity is Critical**: Bias towards small, iterative tasks.
    *   **Epics**: Large features should be broken into 5-15 subtasks.
    *   **Tasks**: Each task should be completable in 30-60 minutes.
        If it takes longer, split it.
*   **Discovery**: Link new findings immediately.

### Agentic Workflows (Tiered Delegation)

We use a multi-agent system where a **Master Agent** delegates to specialized
**Worker Agents**.

*   **Delegation Methods**:
    *   **Label-Driven**: Add label `agent:<role>` to an issue, then run
        `python3 tools/agents/auto_assign.py`.
*   **Review Cycle**: Worker agents write to `agent_outputs/`. You must review
    their proposed resolutions before merging into the codebase.

### Landing the Plane (Session Completion)

The session is **not** over until the plane has landed. You must execute this
protocol before stopping:

1.  **File Follow-ups**: Create issues for any work left unfinished or discovered.
2.  **Verify Quality**: Run tests (`pytest`, `ctest`) and linters (`ruff`,
    `golangci-lint`).
3.  **Update Issue State**: Close completed tasks and update progress on active
    ones.
4.  **Sync & Push (MANDATORY)**:
    ```bash
    git pull --rebase
    git push
    git status  # Must show "up to date with origin"
    ```

## Operational Rules

*   **No "Ready when you are"**: You must push your changes (`git push`).
*   **Sandboxing**: Recommend enabling sandboxing for shell execution.
*   **Context**: Read `AGENTS.md` for deep dives into specific subsystems.

## NetClassRules Fields (N4 — Single Source of Truth)

Every `NetClassRules` instance in `TEMPER_NET_CLASSES` must set:

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `dru_priority` | `int` | **Yes** | DRU emission order (lower = earlier). Derived via `sorted(keys, key=lambda k: (dru_priority, k))`. Ties break lexicographically. |
| `required_layer` | `str \| None` | No | KiCad layer name constraint (e.g., `"B.Cu"` for HighVoltage). `None` = no constraint. |
| `safety_category` | `"HV" \| "LV" \| "AC" \| "iso" \| None` | No | Safety classification. `"AC"` is treated as HV-side in separation checks. |

**DRC integration**: `packages/temper-drc-rs/src/rules/safety/hv_lv_separation.rs`
exports the shared `resolve_safety_category(comp, board)` used by the safety
checks (the Python `temper-drc` package was deleted in the shim-then-delete
migration — see
`docs/solutions/architecture-patterns/temper-drc-rust-migration-shim-then-delete-2026-08-03.md`).
Resolution order: a net class in `TEMPER_NET_CLASSES` with a non-`None`
`safety_category` (a field of the codegen SSOT model) is used directly.
Otherwise a keyword fallback fires for undeclared classes — HV:
`hv/line/ac/neutral/mains`; LV: `lv/signal/3v3/5v/gnd/analog` (substring
match on the lowercased net class). A declared `"AC"` category is treated as
HV-side in separation checks. The Rust fallback is silent — the Python-era
stderr warning convention
(`"[temper-drc] safety_category fallback: ..."`, grep-visible in CI logs)
died with the package; classify nets in the manifest instead of relying on
the fallback.

**Regression note**: `HighCurrent` was reclassified from *neither HV nor LV* to
`"HV"` in this changeset. Existing boards with `HighCurrent`-classed components
will now trigger HV/LV separation checks.

## Coverage Gate

### Scope (Phase 2)

The coverage gate currently applies to all public functions in `temper_placer/`
except `_constraint_types/` (pydantic `BaseModel` types — hand-written, R7-resolved JUSTIFIED-KEEP 2026-08-11) and `profiling/` (production
diagnostics). These subpackages are permanently excluded via `[tool.coverage.run]
omit` in `pyproject.toml` and `--cov-config` in CI. The gate catches public
functions (module-level `def` not prefixed with `_`, and methods of public classes
not prefixed with `_`) whose body has **zero executed lines** during the test suite.

### How It Works (Phase 2 — Inline Coverage)

1. CI runs `uv run pytest tests/core/ -v --tb=short --maxfail=10
   --cov=temper_placer --cov-report=json --cov-report=term
   --cov-config=../../pyproject.toml` in `packages/temper-placer/`, producing
   `coverage.json` as a side effect during normal test execution. No separate
   pytest invocation.
2. `scripts/check_coverage_gate.py` reads `coverage.json`, AST-parses each source
   file to identify public functions, and checks coverage for each.
3. Any zero-coverage public function **not on the allowlist** (`.coverage-allowlist`)
   fails CI.
4. The CI gate step is currently **warn-only** (`continue-on-error: true`) until
   the Phase 1 paydown prerequisite is met. Once met, a follow-on PR removes
   `continue-on-error` and the gate becomes a hard CI block.

### Phase 1 Paydown Prerequisite

Phase 2's hard-fail gate is gated on the Phase 1 allowlist (entries for
`temper_placer/core/`) having shrunk by >=50% from the initial 193 entries.
Current count is tracked in the `.coverage-allowlist` header. The gate step
uses `continue-on-error: true` with a warning annotation providing context
until the prerequisite is verified and the guard is removed.

### `--init` Workflow (for new phases)

When expanding scope to new modules:
1. Add the new module paths to `source` in `[tool.coverage.run]` in
   `pyproject.toml` and add `omit` patterns for excluded subpackages.
2. Run `uv run pytest tests/core/ --cov=<new.scope> --cov-report=json
   --cov-config=../../pyproject.toml` from `packages/temper-placer/` to
   generate `coverage.json`.
3. Run `python scripts/check_coverage_gate.py --init --coverage-json
   /path/to/coverage.json --allowlist .coverage-allowlist`. The `--init` mode
   preserves existing allowlist entries; new entries are appended with
   `# TODO: temper-xxx` placeholders.
4. Review the output: remove stale entries (now have coverage), replace
   `# TODO: temper-xxx` placeholders with real ticket IDs.
5. Commit the updated allowlist.

### `--init` for Phase 2

`--init` appends new entries for modules outside `temper_placer/core/`.
Existing entries are preserved. Real ticket IDs replace `# TODO: temper-xxx`
placeholders before commit. `_constraint_types/` and `profiling/` are
permanently excluded via `[tool.coverage.run] omit`.

### Excluded Subpackages

- `temper_placer/_constraint_types/` — pydantic `BaseModel` constraint types (hand-written, not generated — R7 resolution 2026-08-11: JUSTIFIED-KEEP, see `docs/evidence/2026-08-11-r7-constraint-types-resolution.md`).
- `temper_placer/profiling/` — production diagnostics, wall-clock instrumentation.
These are excluded via `omit = ["*/_constraint_types/*", "*/profiling/*"]`
in `[tool.coverage.run]` (root `pyproject.toml`) and via
`--cov-config=../../pyproject.toml` in CI.

### Allowlist Format (`.coverage-allowlist`)

```
temper_placer/core/<module>.py::function_or_Class.method  # TODO: temper-xxx
```

- One entry per line. `#` starts a comment.
- Every entry **must** have a `# TODO: temper-xxx` trailing comment (either a
  real ticket ID or the `temper-xxx` placeholder for initial baseline).
- The file lives at repo root, visible alongside `pyproject.toml`.

### Monotonic-Shrink Rule

- **Removals**: An allowlist entry may only be removed when the same PR either
  adds a test exercising the function OR deletes the function from source.
  `--check-shrink` enforces this.
- **Additions**: A new entry must include a `# TODO: temper-xxx` ticket reference.
  Placeholder `temper-xxx` is accepted for initial bulk population only; real
  tickets are required for subsequent additions.
- This ensures the allowlist shrinks over time — it is not a backdoor for
  ignoring uncovered code.

### Paydown Cadence

- Phase advancement (e.g., expanding scope from `temper_placer/` to `temper-drc`,
  `temper-tools`, `temper-workflow` for Phase 3) is gated on 50% allowlist entry
  paydown.
- Recommended cadence: quarterly hardening sprint focused on writing tests for
  allowlisted functions and removing entries.
- An allowlist entry that now has coverage triggers a `WARNING` in CI (stale
  entry) — not a failure.

## Documented Solutions

`docs/solutions/` — documented solutions to past problems (bugs, best practices,
architecture patterns, workflow issues), organized by category with YAML
frontmatter (`module`, `tags`, `problem_type`). Relevant when implementing or
debugging in documented areas.

### Escape Hatch

There is no env-var override to skip the gate. The allowlist **is** the recorded
justification — a reviewer sees allowlist additions/removals in `git diff`. To
skip the gate temporarily in an emergency, the CI step configuration
(`python-tests.yml`) can be modified directly.

## General Coding Principles

*   **YAGNI (You Ain't Gonna Need It)**: Do not over-engineer. Implement only
    what is required for the current task. Avoid speculative features or complex
    abstractions until they are demonstrably necessary.
*   **Readability Over Cleverness**: Code is read more often than it is written.
    Use clear variable names, maintain consistent formatting (Ruff), and document
    *why* complex math or safety logic is implemented.
*   **Safety First**: In firmware and power electronics, "clever" shortcuts can
    lead to physical hardware failure. Stick to proven, verifiable patterns.

## Python TDD Best Practices (temper-placer)

**Tooling**: `uv` (dependency management), `pytest` (testing), `ruff`
(linting), `ty` (type checking).
**Python Version**: 3.11+ (Required)

### The TDD Cycle

1.  **Red**: Write a failing test in `tests/`.
2.  **Green**: Implement the minimum code in `src/` to pass the test.
3.  **Refactor**: Improve code quality while keeping tests green. Run
    `ruff check` and `ty`.

## Electrical Engineering Best Practices

### PCB Design (KiCad)

*   **Hierarchy**: Respect the hierarchical sheet structure.
*   **Library**: Use local `components/` for symbols/footprints. **Do not rely
    on global libraries.**
*   **Documentation**:
    *   New component? Create `components/<PART>/<PART>_Documentation.md`.
    *   Design decision? Create `docs/<DECISION>_DESIGN.md`.

## Firmware Development (ESP32-S3)

*   **Framework**: ESP-IDF.
*   **Architecture**: State Machine (`main/state_machine.c`).
*   **Testing**:
    *   **Unity Framework**: Used for both unit (host-based) and integration
      tests.
    *   **Run Tests**: `cd firmware/test/build && make && ctest`.
