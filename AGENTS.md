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

**DRC integration**: `packages/temper-drc/src/temper_drc/checks/safety/_safety_keywords.py`
exports a shared `resolve_safety_category(net_class_str)` used by all three safety
checks. When a net class is in `TEMPER_NET_CLASSES` with a non-`None` `safety_category`,
the category is used directly. Otherwise a keyword-scan fallback fires with a
**stderr warning** (grep-visible in CI logs). The warning convention:
`"[temper-drc] safety_category fallback: ... Declare safety_category on net class
'...' or add net to TEMPER_NET_ASSIGNMENTS."`

**Regression note**: `HighCurrent` was reclassified from *neither HV nor LV* to
`"HV"` in this changeset. Existing boards with `HighCurrent`-classed components
will now trigger HV/LV separation checks.

## Coverage Gate

### Scope (Phase 2)

The coverage gate currently applies to all public functions in `temper_placer/`
except `_constraint_types/` (generated type stubs) and `profiling/` (production
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

- `temper_placer/_constraint_types/` — generated constraint type stubs.
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
