# Instructions for AI Agents

## Project Context

**This is the Temper induction cooker project:**
- **Firmware**: ESP32-S3 with 8-state machine
- **PCB**: KiCad design with temper-placer optimizer
- **Language**: C (firmware), Python + Rust (placer)

**Rust is preferred over Python, and the placer is actively migrating off
Python.** New logic goes in Rust with a thin pyo3 binding, following the
existing pattern. Do not introduce a new Python single-source-of-truth; if
you find yourself writing one, the Rust crate it belongs in already exists.
Two consequences that catch people:

*   Many `*.py` files in the placer are already pure-delegation shims whose
    every function calls a Rust pyfunction. Editing one because it "looks
    like the implementation" changes nothing. Check for a Rust owner first.
*   pyo3 module registration order matters: a later `add_function` silently
    shadows an earlier one of the same name, with no error. Two duplicate
    `kw_boundary_match_py` registrations shipped this way and one of them
    was dead for its entire lifetime.

### When Rust and Python disagree

**Standing rule: fix the Rust until it is definitely correct, then deprecate
and delete the Python.** Never reconcile by adjusting Rust to match Python,
and never leave both in place "in agreement" — two homes that agree today
drift tomorrow, and this repo has the scars to prove it.

"Definitely correct" means correct *by construction*, not correct by
coincidence. The distinction is not academic:

> `temper_drc_rs::ipc::net_currents()` returned the right ampacity for
> `GATE_HS` only because its lookup used a **substring** match and the stale
> key `GATE_H` happens to be a literal prefix. Python's exact match missed the
> same key and returned the 0.1A default — a 20× disagreement on a safety
> value. Rust's answer was right; its *mechanism* was wrong, and would equally
> have matched `XGATE_HSY`. Renaming the key without tightening the lookup
> would have preserved the coincidence.

So the sequence is: **make Rust right → prove it against Python with a
differential oracle → delete the Python → keep the oracle.** The ~187 pinned
`_*_py_oracle.py` files exist to make that deletion safe; adding a new oracle
for newly-ported code is correct and expected. Re-pinning an *existing* one is
a separate, deliberately-committed act requiring evidence first.

**A differential test only proves what you feed it.** The Rust/Python
ampacity divergence above survived a genuinely-running differential test
because that test's input was `"Gate_H"` — a net name absent from this board.
Both sides looked it up, both agreed, green. When you write or trust a
differential, check that its inputs are values the production system actually
sees.

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
it documents an "observed max + headroom" convention for every category
whose count moves on a byte-identical board, and the reasoning behind every
prior ceiling move). **`clearance` is not the only such category any more --
`creepage` has been the chronically-scattering one since the #602 K3 swap
(2026-08-02), and both can be nondeterministic on the same board at once.**
Check `nondeterministic_error_types` in the CURRENT record, not this
sentence, for which categories apply today.

**The headroom you pick is not free to choose -- it must satisfy
`ceiling - max(observed) >= max(observed) - min(observed)`
(`scripts/ci_check_drc.py`'s noise-headroom guard,
`DrcRatchet.check_noise_headroom`).** A blind `max + 1` is only correct
when the measured spread is 1; if a category visits 3 distinct values (a
spread of 2), `max + 1` gives 1 unit of headroom against a 2-unit spread and
the guard fails -- correctly, since a single future CI sample can then land
above the ceiling from noise alone. This is not hypothetical: every
`creepage` record from 2026-08-02 through 2026-08-11 (6 consecutive
re-measurements) carried exactly this bug, because each one copied `+ 1`
forward without checking it against the guard. Run
`python3 scripts/ci_check_drc.py --backend kicad-cli` (or call
`DrcRatchet.check_noise_headroom()` directly -- it costs nothing, no DRC run)
against your candidate ceiling BEFORE committing it. See
`docs/evidence/2026-08-11-creepage-noise-headroom-guard-fix.md` for the
full incident and the argument for `max(observed) + spread` as the correct
convention over a wider, arbitrary buffer.

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
    # >= 120 samples whenever ANY category is declared nondeterministic
    # (not just clearance -- see the 2026-08-11 creepage-guard fix).
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
recorded kicad-cli version, at least 120 samples whenever ANY category is
declared nondeterministic -- not only `clearance` (structured
`provenance.sample_count`, or the legacy `measured_via` prose on records
that predate the field), and an input hash
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

## Measurement Instruments That Lie — read before trusting any number

Every one of these produced a wrong conclusion that someone acted on. They are
recorded here because agents kept re-deriving them from scratch, one session at
a time.

**A number from a mis-set-up instrument is indistinguishable from a real
result.** In a single day these manufactured five phantom test failures, one
invalid baseline, a regression that never existed, and two hypotheses that sent
whole investigations down dead ends.

### DRC / kicad-cli

* **`pcb/temper.kicad_dru` is gitignored and generated.** Without regenerating
  it (`scripts/generate_kicad_dru.py`), **creepage reads 0** and clearance
  reads a different count entirely. Regenerate before any DRC run. It also
  regenerates to a different byte size than any committed copy.
* **`_drc_api.run_drc(Path)` is necessary but NOT sufficient** — the *board
  file* needs an `fp-lib-table` sibling. Without one,
  `lib_footprint_issues` reads exactly the board's footprint count (168) and
  `lib_footprint_mismatch` reads 0, **even through the correct API**. With
  `pcb/fp-lib-table` beside it: 168 -> 16, mismatch -> 25. That 168/0 pair is
  the signature; if you see it, your harness is wrong, not the board.
* **kicad-cli saturation caps**: `ERROR_LIMIT` = 199, `EXTENDED_ERROR_LIMIT` =
  499. A count of **exactly** 199 or 499 is a cap, not a count.
* **kicad-cli is nondeterministic run-to-run.** Run 3x and intersect. Observed
  spreads: creepage {105,106,107}, total {777,778}, and `shorting_items` rows
  whose net order swaps (`nets A and B` vs `nets B and A`) — normalize before
  diffing or you will "find" changes that are not there.
* **kicad-cli reports one creepage violation per NET PAIR, not per pad pair.**
  Clearing one pair unmasks another that was hidden behind it. Expect new rows
  between parts you did not touch, and do not attribute them to your change
  without checking. `DrcResult` exposes `.error_count`/`.warning_count`/
  `.errors`/`.warnings` (not `.counts`); `DrcError` exposes `.rule`/`.nets`/
  `.message`/`.items`. **Diff the violation SETS, not the counts.**

### Build / environment

* **`make extensions` fails hard when `CONDA_PREFIX` is set** — maturin refuses
  when it coexists with `VIRTUAL_ENV`. Use `env -u CONDA_PREFIX`. A silent
  failure here left an extension unbuilt and manufactured **5 phantom test
  failures** that read as real creepage regressions.
* **A stale `.so` fails loudly, not subtly**: `AttributeError: module
  'temper_rust_router' has no attribute '...'`. `scripts/check_stale_extensions.py`
  reports which crates are stale. Any PR that changes a pyo3 boundary leaves
  every unrebuilt checkout broken, including CI's typecheck stubs.
* **`scripts/check_venv_integrity.py` false-positives from worktrees nested
  under `.claude/worktrees/`** — `classify_path` lets `other_worktrees` win
  because the main checkout is a string prefix. It reports all editable
  installs as violations while printing paths that are correct.

### Test harness

* **Set pytest timeouts above 1200s for full-route tests.**
  `test_route_pcb_production_board` needs ~1193s; a 900s cap manufactured a
  "20th failure" that could not have passed on any branch.
* **Hypothesis replays counterexamples from its example DB.** A test that fails
  only on your branch may be replaying a stored case. Clear the DB before
  concluding you caused it — and if the counterexample is real, it deserves its
  own ticket rather than being written off as flake.

### Figures that look measured and are not

* **`attempted_ripups` is a hardcoded literal** (`_astar_nlayer.py`
  `record_failure`), on a single-pass loop with no rip-up mechanism. Every net
  reports 0. It is not evidence about displacement of committed copper.
* **`RouteProfileStats.python_time_ms` is structurally always 0.0** since the
  Python search path was removed — and is still published as
  `maze_router_python_ms`.
* **A 16-character digest prefix is not a 64-character claim.** Compare full
  digests programmatically. Note also that after a **squash** merge the branch
  SHA is never an ancestor of `main` — that is expected, not lost work.

### The general rule

**When a measurement contradicts a change you just made, suspect the
measurement before the change.** And when relaying someone else's number,
check whether it was measured or inherited — several figures that circulated
for a full day ("271 calls per route", "attempted_ripups == 0", "the 200k
budget cap") turned out to have no committed measurement behind them.

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
blocks `git stash` / `git stash push` / `git stash push -u` / `git stash
save` / `git stash clear` outright (exit 128, `fatal: ref updates aborted by
hook`). This is a real, tested block — verified to fire under
non-interactive, direct `git` invocation, from every worktree sharing this
repo's `.git` directory, without relying on any shell alias or `PATH` trick
(a git hook is invoked by the `git` binary itself, regardless of what
invoked `git`).

It is installed into this repo's live shared `.git/hooks/` (not just tested
in a throwaway repo — that distinction mattered: the mechanism existed,
documented and tested, for two weeks before anyone actually ran the
installer against the real `.git`, during which three more agents used
`git stash` in a single session with the hook doing nothing). `make
worktree` (the standard way new worktrees are created, see
`docs/solutions/best-practices/per-workstream-worktree-2026-07-31.md`) now
runs `scripts/install_git_stash_guard.py` on every invocation, so the guard
reinstalls itself — idempotently, a no-op if already current — every time a
worktree is created, and cannot silently go missing from a fresh clone or a
`.git/hooks/` wiped by other tooling. To check or (re)install by hand:

```bash
python3 scripts/install_git_stash_guard.py --check   # report only
python3 scripts/install_git_stash_guard.py            # install/update
```

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
(what was tested, in a throwaway `/tmp` repo, and what the results were);
`scripts/tests/test_git_stash_guard.py` (`TestBlocksRealStashOperations`,
`TestDocumentedGaps`) pins every one of `stash` / `push` / `push -u` /
`save` / `clear` / `apply` / `pop` / `drop` against the real hook so any
future git version that changes this behaviour fails a test, not silently
changes the security posture.

Even in the one case where dropping *is* blocked (removing the last
remaining entry), git rewrites `refs/stash`'s reflog before the hook is
consulted, so `git stash list` goes empty regardless of the block — the
underlying commit is not deleted (`refs/stash` itself is unchanged and the
object stays resolvable/reachable) but it becomes invisible to the normal
stash UI. Do not read "hook fired" as "the stack looks untouched" for this
one case; it means "the data was not destroyed," which is not the same
thing.

**Detector (defense in depth for the gap above)**:
`uv run python scripts/check_stash_stack_gate.py` snapshots the stash
reflog and diffs it against the last snapshot, flagging any addition or
disappearance since the last run. It is not a CI gate (CI runners don't
share this `.git` directory) — run it manually, on a timer, or from a
`/loop` against the actual dev machine. A baseline snapshot now exists at
`<git-common-dir>/stash-guard-snapshot.json`; this script stays alongside
the hook rather than being superseded by it, because it is the only thing
that sees `apply`/`pop`/`drop` activity the hook structurally cannot block.

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

## Shared cargo build cache — enforced automatically, not just documented

`make cargo-target-dir-guard` installs a `cargo` wrapper at
`~/.local/bin/cargo` (ahead of `~/.cargo/bin` on PATH) that fixes
`CARGO_TARGET_DIR` for **every** cargo/maturin invocation on this host, from
any worktree, in any shell — no sourcing, no remembering. `make worktree`
and `make venv-isolate` install/refresh it automatically. If you're setting
up a worktree by hand (`git worktree add`, not `make worktree`), run it
once:

```bash
python3 scripts/install_cargo_target_dir_guard.py
```

It is scoped to this repo only (checked via `git rev-parse
--git-common-dir`) and never touches other cargo projects on the host, and
it respects an explicitly-set `CARGO_TARGET_DIR` rather than overriding it.
See `scripts/install_cargo_target_dir_guard.py`'s module docstring for the
full mechanism and `scripts/check_no_worktree_target_dirs.py` (`make
check-worktree-target-dirs`, `CLEAN=1` to also delete violations that pass
a `CACHEDIR.TAG` safety check) for the gate that catches anything that
still slips through — e.g. a worktree that existed before the guard was
installed.

**Why this replaced "source `scripts/cargo_shared_env.sh` once per shell"
(2026-08-13):** that guidance was correct for a persistent interactive
shell but not for how agents actually invoke commands. Agent tool-calling
harnesses start a *fresh shell process per tool call* — shell state,
including exported env vars, does not persist between calls. Sourcing the
script in one call has zero effect on a `cargo build` issued in the next
call, which is the overwhelmingly common pattern. This was confirmed
directly while investigating the 2026-08-12 recurrence: exporting
`CARGO_TARGET_DIR` in one shell and checking it in a fresh one showed it
unset, and a bare `cargo metadata` run from a worktree with the var unset
resolved `target_directory` to that worktree's own private
`target-shared` — reproducing the incident mechanism live. The
`source`-based guidance is still correct and still works for a genuinely
persistent interactive shell (it's what the wrapper itself uses
internally), but it is no longer the primary defense.

**The "anything run through `make` already exports the same value" claim
was verified and holds**: `CARGO_TARGET_DIR` is computed and exported at
the top of the Makefile itself
(`CARGO_TARGET_DIR := $(shell dirname "$(shell git rev-parse
--path-format=absolute --git-common-dir)")/target-shared`), recomputed
fresh on every `make` invocation regardless of the calling shell's prior
state, and inherited by every recipe command as a normal OS environment
variable. `make extensions`, `make build`, etc. were never the gap — direct
`cargo`/`maturin` calls outside `make` were.

Why it matters underneath all of this: `.cargo/config.toml` sets
`build.target-dir` to the *relative* path `target-shared`. Cargo resolves a
relative `target-dir` against the config file's own directory, and every
git worktree gets its own tracked **copy** of that file — so, absent the
guard above, each worktree lands on its own `target-shared` and compiles
all 10 pyo3 crates from cold. `CARGO_TARGET_DIR` overrides `build.target-dir`
and can hold an absolute path, which is why the sharing is done there
rather than in the config (a hardcoded absolute path in the tracked config
would also break CI, whose checkout lives at a different absolute path).

This is not hypothetical. It caused a 51 GB incident, recurred on
2026-08-06 (25 private caches totalling 36.6 GB, the disk at 98%, 16 GB
reclaimed by hand), and recurred again on 2026-08-11/12 at ~74 GB across 99
worktrees despite the documented `source`-based remedy being in every agent
brief — which is why enforcement moved from a shell convention to a PATH
wrapper plus a standing gate. Agent worktrees are the main source, because
they are created outside a persistent shell's lifetime and run `cargo
test` / `cargo build` / `cargo clippy` / `maturin develop` directly, one
tool call at a time.

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

**A stale `.so` does not just fail — it lies.** Believing a measurement
taken against one is the expensive mistake, not the rebuild. In one
session `tests/deterministic` reported 76 failures of which 72 were stale
extensions and only 4 were real; separately, an agent reported
`temper_orchestration.RouterPipeline` as "missing — a pre-existing repo
defect" when the symbol was simply absent from an installed `.so` that
predated the commit adding it. Run the gate *before* you believe a number,
not after a result surprises you. Absence of a symbol is not evidence of a
missing feature.

**A poisoned cargo cache defeats the rebuild silently.** `cargo check` and
clippy compile these crates *without* their `python` feature. maturin will
reuse such an artifact, report success, and install a `.so` with no
`PyInit_<crate>` symbol — `import <crate>` then fails with "dynamic module
does not define module export function", and the freshness gate is happy
because the file's mtime is new. The tell is maturin printing
`Finished ... in 0.0Xs` with **no `Compiling <crate>` line**, usually
alongside a `Couldn't find the symbol PyInit_<crate>` warning. Fix:

```bash
source scripts/cargo_shared_env.sh   # so -p cleans the SHARED target dir
cargo clean -p <crate>
```

then rebuild and confirm a real `Compiling <crate>` line appears. Note this
is a cargo-cache problem, not a maturin-invocation problem: the
`--manifest-path` form above reads `[tool.maturin] features` correctly from
any working directory.

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

### Four ways a worktree silently poisons the venv it's building into

2026-08-11 incident: the shared `.venv` was found with its editable-install
pointers rewritten to **an agent's git worktree** rather than the main
checkout —

```
_editable_impl_temper_placer.pth      -> .claude/worktrees/agent-ab1dbe8162fa0fbae
_editable_impl_temper_workflow.pth    -> .claude/worktrees/agent-ab1dbe8162fa0fbae
__editable__.temper_rust_router_core  -> .claude/worktrees/agent-ab1dbe8162fa0fbae
```

Every measurement taken against that venv in that window ran against the
worktree's code, not `main` — and nothing indicated it: imports succeed,
numbers come back confident and wrong. Confirmed the same day: four
distinct silent-staleness modes, all reachable from an ordinary worktree
session running `maturin`/`uv` directly instead of through `make`. A
developer or agent will actually hit one of these, not a contrived edge
case:

1. **`maturin` refuses outright if `VIRTUAL_ENV` and `CONDA_PREFIX` are
   both set** — a loud failure, the safe end of this list. Unset whichever
   you are not using before invoking `maturin` directly.
2. **Plain `uv run maturin develop` from a worktree targets a *per-worktree*
   venv and no-ops against the shared one.** If `UV_PROJECT_ENVIRONMENT`
   is not pointed at the shared `.venv` (or the worktree has its own via
   `make venv-isolate`), the build "succeeds" into a venv nobody is
   importing from — a silent no-op, not a hijack, but just as misleading:
   the shared venv's extension is untouched and still stale.
3. **`maturin develop --active` run from a worktree rewrites the SHARED
   venv's editable pointers** — this incident. `--active` targets whatever
   venv is currently *active* (`VIRTUAL_ENV`), not one scoped to the
   worktree it ran from; when that active venv is the shared one, every
   subsequent `import` from *any* worktree — including the main checkout —
   silently resolves into the worktree that ran the command, until someone
   notices or rebuilds. This is the mode `scripts/check_venv_integrity.py`
   (below) exists to catch.
4. **`maturin develop` can report "Installed" while leaving the `.so`
   untouched** — five rebuilds exited 0 in a row while the artifact stayed
   dated a day behind the source that had changed underneath it. This is
   `scripts/check_stale_extensions.py`'s territory (its own module
   docstring covers this exact incident in depth), not this section's —
   named here only because it is the fourth mode in the same day's
   confirmed set, and because it is the reason "the build tool said
   success" is never trusted anywhere in this repo's gates.

**`scripts/check_stale_extensions.py` catches (4)'s mtime symptom but not
(3)'s redirection** — a hijacked-but-not-yet-rebuilt venv still imports a
`.so` that is content-fresh *relative to the worktree it was built from*,
which is exactly what makes (3) silent: the staleness gate has no way to
know it is comparing against the wrong checkout's sources in the first
place.

### Ad-hoc DRC harnesses: copy the library table, not just the sidecars

2026-08-18. A DRC scratch harness that copies only `temper.kicad_pcb` and
`temper.kicad_pro` — and points `KICAD_CONFIG_HOME` at an empty directory —
silently fails to resolve **every footprint on the board**.

The symptom is distinctive and worth memorising: **`lib_footprint_issues`
reads exactly the board's total footprint count** (168 here), and
**`lib_footprint_mismatch` reads 0**. A number equal to 100% of the
population is a resolution failure, not a census. The second reading is the
tell for the first — a footprint that never resolved cannot register as
*mismatched* against a library it never found, so the pair is corrupted in
opposite directions at once.

Measured, three controlled runs on the same board:

```
fp-lib-table + libs/   KICAD_CONFIG_HOME    lib_footprint_issues
       no                    empty                  168
      yes                    empty                  165
      yes                   seeded                   13   <- the truth
```

`KICAD10_FOOTPRINT_DIR` is **not** an OS environment variable. It is defined
inside `kicad_common.json`, under `KICAD_CONFIG_HOME`.

**`_drc_api._single_threaded_kicad_env` already does this correctly.** The
production path has never been wrong. Ad-hoc harnesses copied its
thread-pinning and not its environment construction — so mirror the whole
function, or better, call it.

Cost: this artifact was reported and repeated for hours as "the largest
unexplained DRC regression" and blocked a ceiling re-baseline, when the
stored ceiling of 13 had been correct the entire time.

**The deltas survived, the absolutes did not.** Because the error is constant
across a before/after pair, category *deltas* measured this way remain valid;
only *totals* are inflated. If you inherit a DRC total from a document, check
how it was measured before trusting it.

### The fifth mode: the shared venv reads *main*, not your worktree

2026-08-17. The four modes above are all "a worktree poisons the venv."
**The complementary mode is the venv silently serving you the wrong code,
and it needs no poisoning at all — it is the healthy, correct state of a
shared venv.**

The shared `.venv`'s `temper_placer` is editable-installed against the
**main checkout**:

```
$ .venv/bin/python -c "import temper_placer; print(temper_placer.__file__)"
/home/bennet/Desktop/temper/packages/temper-placer/src/temper_placer/__init__.py
```

So a worktree agent that edits Python and then runs
`.venv/bin/python scripts/route_board.py` **measures `main`'s code, not its
own change.** Nothing errors. The route succeeds. The numbers come back
confident and wrong.

This cost a real round trip: an agent fixing the pour-stitch
`track_width` defect measured **197 violations still present after its
fix**, and would have reported a regression. The tell was that every
violation still read `"actual 0.3000 mm"` — the literal value the fix had
just removed. Code that no longer exists cannot produce violations; the
measurement was of `main`.

**Two defences, in order of preference:**

1. **`make venv-isolate` in your worktree.** The worktree gets its own
   `.venv` and the question disappears. This is what the "check for a Rust
   owner / no shared-venv rebuild" rules already push you toward, and it
   fixes reads as well as writes.
2. **If you must use the shared venv, verify what you are importing before
   you believe a number** — `python -c "import temper_placer; print(...__file__)"`
   and confirm the path is your worktree. A `sys.path` override wrapper
   works, but is easy to get subtly wrong.

**The generalizable rule: when a measurement contradicts a change you just
made, suspect the measurement before the change.** Ask what the number
would look like if your edit were not in effect at all — here, "identical
to before" was exactly the observed result, and that is the signature.

**`scripts/check_venv_integrity.py` closes (3).** It asserts every
editable-install `.pth` file and every `direct_url.json` in the checked
venv's site-packages resolves under the expected repo root — not into a
different registered git worktree (`git worktree list`, so this covers
`.claude/worktrees/agent-*` and any other worktree location, not a
hardcoded path) and not into an unrelated checkout entirely. Fast,
deterministic, local-only (one `git worktree list --porcelain`, no
network). Run it any time a shared venv's trustworthiness is in doubt:

```bash
.venv/bin/python scripts/check_venv_integrity.py     # or: make venv-integrity-check
```

It is a **separate** gate from `check_stale_extensions.py` rather than a
mode folded into it, deliberately: the two answer different questions on
different axes (venv *identity*, scanned from installed site-packages, vs.
per-crate artifact *freshness*, scanned from `packages/` source) and the
identity question is logically prior — a freshness verdict computed
against a hijacked venv is meaningless, not merely stale. CI runs it in
the `test` job (`python-tests.yml`), immediately before the staleness gate
it protects the meaning of. See the script's own module docstring for the
full argument and the exit-code convention (mirrors
`check_stale_extensions.py`'s 0/3/5 on purpose — same job, same reader).

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

### Absence Is Not Evidence (before concluding a file/PR/doc doesn't exist)

A file missing from your worktree means one of two things, and you cannot
tell them apart by looking: it never existed, or it merged after your base.
Before reporting anything as absent, fabricated, or never-written:

```bash
git fetch origin
git log origin/main --oneline -5          # has main moved past your base?
git log --all --oneline -- <path>         # does the path exist on ANY ref?
gh pr list --state all --search "<topic>" # was it merged under another name?
```

Only after all four come back empty is "does not exist" a finding.

This exists because the failure mode is loud and expensive: an agent
dispatched with a citation to
`docs/evidence/2026-08-12-hvlv-candidate-board-measurement.md` searched its
own worktree, found nothing, and reported the citation as **fabricated** --
refusing the task on the grounds that its dispatcher had invented the
evidence. The document was real, merged as #1053 (`d8062c6e6`), and its
worktree was cut exactly one commit earlier. The agent was right to refuse
the underlying action for other reasons, but its stated reason was false,
and a false accusation of fabrication is worse than a missing file: it
discredits real prior work and invites re-doing it.

Note the asymmetry with the Base-Commit Assertion above. That rule catches
you *measuring* stale state. This one catches you *reasoning* from stale
state -- the assertion can pass (you are exactly on the base you were
given) while the base itself is behind the tip that has the file you were
sent to read. `git fetch` costs a second; concluding fabrication costs a
session.

### Never Work Directly in the Main Checkout

Dispatched agents work in their own worktree, always:

```bash
git worktree add <path> -b <branch> origin/main
```

The main checkout is shared. When two agents use it concurrently, one
switching branches silently discards the other's uncommitted edits -- no
error, no conflict, no warning. This is not hypothetical: in one session an
agent lost a completed, user-requested `AGENTS.md` edit this way, and a
second agent independently hit the same thing mid-task, discovering it only
because `git reflog` showed branch switches it had not made.

Two corollaries:

*   **Commit early even when the work is unfinished.** An uncommitted edit
    in a shared checkout is not saved work; it is work that happens to
    still be on disk. Committing to a throwaway branch costs nothing.
*   **Leave the main checkout on `main`.** If you did work there, return it
    when done. A shared checkout parked on a feature branch silently
    changes what the next agent measures.

**Your own worktree means *yours*, not merely "not the main checkout."**
Run `git worktree list` and confirm the directory is yours before your
first write. Reusing a directory another agent is already in is the same
failure as sharing the main checkout, and it is the more common one: in a
single session on 2026-08-14, seven collisions occurred, including three
separate agents working in one `.claude/worktrees/agent-*` directory —
one agent's commits landed on another's branch, and a third's uncommitted
edits sat in the same tree while HEAD was moved out from under them twice.

If you discover foreign work in your tree:

*   **Do not `git checkout`, `restore`, `reset`, or revert it.** Copy your
    own files out and rebranch. Reverting someone else's uncommitted work
    is unrecoverable, and `git stash` is forbidden repo-wide.
*   **Check what your branch is stacked on.** A branch created inside a
    shared worktree inherits whatever was checked out there. Cherry-pick
    the commit you need onto a clean base rather than carrying three
    commits belonging to two other agents into your PR.

### Never Background a Long Run and Wait For It

Long pipeline stages -- `route_board.py` (~250-400 s), a full placement
solve, a `cargo build` of the workspace -- must be run **in the foreground**,
or launched and then polled by reading their log/output file directly.

Do not background one and stop, expecting to be woken. Nothing wakes you.
Four dispatched agents did this in a single session; one did it twice after
being told explicitly that nothing would wake it. Each burned its remaining
budget parked on a notification that does not exist, and two of them had
already finished the work they were sent to do.

The instinct is reasonable -- backgrounding a 6-minute job and yielding is
what you would do if something *would* wake you. It won't. Treat "I'll wait
for the background task" as a bug in your own plan.

Two consequences worth stating separately:

*   **A long run is not a prerequisite for reporting.** If the run does not
    finish, report what you measured and mark the rest **outstanding**, with
    one sentence on why. A labelled gap is a fine outcome. Inferring the
    result you would have measured is not -- "the change is
    representation-only, so the output must be identical" is the argument,
    not the evidence.
*   **Do not relaunch a run that died.** This machine has had routing runs
    OOM-killed at 54-59 GB with several agents active. Check for other live
    `route_board.py`/`pumpkin_engine` processes before starting one, and if
    yours dies under load, report it rather than competing for the memory
    that killed it.

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
