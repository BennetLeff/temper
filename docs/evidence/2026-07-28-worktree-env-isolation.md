<!-- provenance: commit=4125e47ca2a713335a949730801e507185697422 dirty=false -->

# Worktree environment isolation: closing the shared-`.venv` cost, without reinventing the fix already in the tree

Base commit: `0cf203af` (`merge: KiCad DOES have a real creepage constraint
-- and it is now enforced`; that commit is a descendant of
`docs/methodology-loop-discipline`'s tip `f8b5f43c`, confirmed by
`git merge-base --is-ancestor f8b5f43c 0cf203af`). Work done in worktree
`agent-a1a79621cea481d17`, branch `fix/worktree-env-isolation` created from
that commit.

Reads first, per task instructions:
`docs/solutions/best-practices/shared-mutable-state-dominant-cost-multi-agent-repo-2026-07-28.md`,
`docs/solutions/best-practices/green-rust-tests-are-not-evidence-the-extension-was-rebuilt-2026-07-27.md`,
`scripts/check_stale_extensions.py`, `.cargo/config.toml`, `Makefile`.

## FALSIFIER, stated up front

> "Isolating the environment removes the staleness class without an
> unacceptable disk or time cost. If per-worktree environments are
> unaffordable at 22 GB free, or rebuild time makes agents materially
> slower, then the right answer is a shared environment with content-hash
> freshness -- and that trade-off is the finding."

**Result: partially fires, and the partial result is the finding, not a
dodge.** Per-worktree isolation is cheap and clean on a *single-worktree*
basis (§3: ~675 MB, ~85s with a warm cache -- not a material slowdown for
a session). It is **not** cheap at the *fleet* scale this repo actually
runs at: 42 agent-worktree directories exist right now, 19 of which
already independently carry their own ~700 MB `.venv` (built ad hoc, not
through any coordinated policy), and free disk is 19-21 GB and moving
during this session because concurrent agents are actively writing to the
same volume (§3.3). Unconditionally isolating all 42 would cost roughly
23 more x ~700 MB ≈ 16 GB against 19-21 GB free -- that *would* be the
falsifier's "unacceptable disk cost" branch. So the actual deliverable is
the hybrid the falsifier's own escape hatch describes: content-hash
freshness unconditionally (§1, zero downside, already real code in this
repo's history -- see below), plus an opt-in, one-command per-worktree
isolation path (§2) for the worktrees that are actually doing active
build/test work, not a blanket default for all 42.

## 0. What already existed in this repo's history, and why I did not redo it

Before writing anything, I checked whether the false-positive fix and the
"one command to rebuild every extension" tooling this task calls for
already existed elsewhere in this repo's object database, per the task's
own instruction to "check whether it exists in your base and build on it
rather than duplicating." All three pieces did, on commits not reachable
from `0cf203af` (my assigned base):

| Commit | What it does | Relation to my base |
|---|---|---|
| `0a94206e` | `make extensions` / `make extensions-check`, `--list-crates` on the gate | divergent from `0cf203af` (neither is an ancestor of the other) |
| `c59589b0` | `scripts/_lib/freshness.py` -- the shared content-hash mechanism, applied first to the netlist gate (`check_domain_partition.py`) | divergent from `0cf203af` |
| `f9c043a6` | Applies that same mechanism to `check_stale_extensions.py`: a build stamp (SHA-256 of a crate's source set, keyed on the installed `.so`'s own bytes) is checked first; mtime is only a fallback when no stamp exists | divergent from `0cf203af`; depends on `c59589b0` |

All three cherry-picked cleanly onto `fix/worktree-env-isolation` with
**zero conflicts** (`git cherry-pick 0a94206e c59589b0 f9c043a6`, in that
dependency order), and the full test suite for the touched area passed
immediately after: **96/96** across
`scripts/tests/test_check_stale_extensions.py`,
`scripts/tests/_lib/test_lib_freshness.py`, and
`scripts/tests/test_check_domain_partition.py`. I did not re-derive or
re-implement any of this design; I verified it, integrated it, and built
the remaining, un-addressed half of the task (the isolation decision
itself, §2) on top of it.

This closes the task's explicit "fix the false positive" requirement
already, by construction: `f9c043a6`'s mechanism is exactly "content-hash
based freshness instead of mtime, so `git checkout` no longer produces
false positives", which is what §4 demonstrates empirically.

## 1. The false-positive fix, demonstrated against the real tree (not just inherited on trust)

Cherry-picking code is not evidence it works in *this* tree. I ran both
falsifier legs live, against `temper-drc-rs`, after building all 10
crates fresh and running `scripts/write_extension_stamps.py` (10/10
stamped):

**Leg A -- the false positive this task exists to fix.** Touched every
`.rs`/`Cargo.toml`/`pyproject.toml` file under `packages/temper-drc-rs`
to the current time via `touch` (the exact effect `git checkout -b`
has -- content unchanged, mtime now newer than the installed `.so`):

```
$ uv run --no-sync python3 scripts/check_stale_extensions.py
  [OK] temper-drc-rs: ... matches its build stamp (digest 64230ca207fc...
       over 52 source file(s); mtimes not consulted)
PASSED -- 10/10 extension module(s) fresh.
```

No false STALE, because the stamp is content-keyed and mtimes are never
consulted once a stamp exists.

**Leg B -- the gate must still catch a genuinely stale extension.** With
sources back at their touched (newer) mtimes, appended a real line to
`packages/temper-drc-rs/src/lib.rs` (a byte-content change) without
rebuilding:

```
$ uv run --no-sync python3 scripts/check_stale_extensions.py; echo "EXIT=$?"
  [STALE] temper-drc-rs: ... current digest 9b8f551e68ac... does not match
          its build stamp 64230ca207fc... over 52 source file(s) --
          rebuild with `uv run maturin develop --release ...`
FAILED -- 1 stale extension(s).
EXIT=3
```

Both legs ran in the same tree, back to back, with the *only* variable
being whether the source content actually changed. The gate is stricter
than the mtime rule it replaced, not just more tolerant of checkouts:
content hashing catches a real edit regardless of the mtime it lands with,
which the old mtime rule could not (see `f9c043a6`'s own commit message
for the back-dated-edit case, which I did not need to re-demonstrate
since it already has its own test in `TestContentStamp`).

The edit to `lib.rs` was reverted (`git checkout --
packages/temper-drc-rs/src/lib.rs`) immediately after; `git status`
confirmed the worktree was clean again, and the gate returned to
`PASSED -- 10/10` because the reverted content hashes back to the
original stamped digest.

## 2. The isolation half: `make venv-isolate`

The content-hash fix closes the false-positive/detection gap regardless
of whether a worktree shares `.venv` with another checkout. It does
**not** close a different, separately-documented hazard: "a `uv sync`
from a concurrent session reverted freshly-built extensions to cached
wheels, repeatedly" (the shared-mutable-state doc's second incident). That
is not a staleness-*detection* problem -- the extension really was
replaced, by a different session's legitimate build, and no freshness
check can distinguish "my crate's real content changed" from "the exact
same crate was correctly, freshly rebuilt by someone else in the same
directory a moment ago." The only fix for that is not sharing the
directory.

Added `make venv-isolate` (Makefile): `uv sync --all-packages` followed by
`make extensions`, giving the invoking worktree its own `.venv`
independent of any other checkout's. No other worktree's `uv sync`/`uv
run` can touch it afterward, by construction (different directory, not a
freshness argument). Deliberately **not** wired as an automatic default
for worktree creation (no such hook exists in this repo for me to wire it
into in any case -- worktree creation is done by the outer harness, not
by anything under version control here) -- see the falsifier verdict
above for why a blanket default is the wrong call at current fleet scale.

## 3. Measurements (not asserted)

### 3.1 Time

Ran live in this worktree, which had no `.venv` at task start:

| Step | Wall time |
|---|---|
| `uv sync --all-packages` (fresh venv, warm `uv` package cache, 9 of 10 pyo3 crates built via workspace path deps) | **72.7s** (`294.12s user, 25.54s system, 439% cpu` -- parallelized) |
| `maturin develop --release` for `temper-constraints` (the 10th crate, not covered by the `packages/*` workspace glob) | **12.5s**, including compiling `pyo3`, `nalgebra`, and 9 other crates from scratch |
| **Total to a fully fresh, 10/10 environment** | **~85s** |

The second row is the sharper number: `temper-constraints` had never been
built in *this* worktree, yet took 12.5s, not minutes, because
`.cargo/config.toml`'s shared `target-shared` build directory already had
`pyo3`/`nalgebra`/etc. compiled from other worktrees' builds. The
Rust-compile-time half of "per-worktree isolation is expensive" was
already solved before this task by the shared Cargo target directory;
this task's own measurement confirms that fix generalizes to a
brand-new venv, not just to rebuilding within an existing one.

### 3.2 Disk -- this worktree

`du -sh .venv`: **675 MB** logical size for a fully-built, 10/10-fresh
environment (measured after `make extensions` completed).

### 3.3 Disk -- fleet-wide context (why the verdict is a hybrid, not a clean yes)

```
42  agent-worktree directories under .claude/worktrees/
19  of them already carry their own independent .venv (ad hoc -- not
    through any coordinated mechanism; ranges 673-729 MB, one partial
    at 152 MB, four empty/broken stubs at 76 KB)
```

`df` on the same volume, at the start and end of this session's work:

| | Free |
|---|---|
| Before `uv sync --all-packages` | 21 GiB |
| After (post cherry-picks, post `make extensions`, post `make netlist`) | 19 GiB |

That -2 GiB delta is **not** a clean per-worktree cost measurement -- it
is confounded by other concurrently-running agent sessions writing to the
same disk during the same window (this machine had ~15-20 other active
worktrees the whole time). The `du -sh .venv` figure (675 MB, matching the
14 already-independent worktrees' 673-729 MB range almost exactly) is the
reliable number; the `df` delta is reported for completeness but is
explicitly *not* trustworthy as an isolated measurement on a machine this
busy, and I am not asserting otherwise.

At 675 MB/worktree and 19-21 GiB free, the *marginal* cost of isolating
one more actively-working worktree is trivial. The cost of isolating
**every** worktree that currently exists (23 more beyond the 19 already
isolated) would be roughly 23 x 675 MB ≈ 15.5 GiB -- most of the
remaining headroom, on a disk that has already been fully exhausted twice
by exactly this multiplication (per the shared-mutable-state doc's
incident #3). That is the concrete basis for "opt-in per actively-working
worktree, not a blanket default" in §2.

## 4. Verification

Denominators throughout; `X`/`Y` never means `X` is a subset of an
unstated `Y`.

| Check | Result |
|---|---|
| `scripts/tests/test_check_stale_extensions.py` + `scripts/tests/_lib/test_lib_freshness.py` + `scripts/tests/test_check_domain_partition.py` | **96/96 passed** |
| `uv run --no-sync python3 scripts/check_stale_extensions.py` | **PASSED -- 10/10** extension module(s) fresh, all 10 decided by content hash (0 by mtime fallback) after `write_extension_stamps.py` |
| False-positive falsifier (§1 leg A) | confirmed fixed: touched-to-now mtimes on `temper-drc-rs`, still FRESH |
| Genuine-staleness falsifier (§1 leg B) | confirmed still caught: real `lib.rs` edit, no rebuild -> exit 3, STALE |
| `make netlist` | **passes** (10.9s; also exercises the cherry-picked netlist build-stamp writer, `[write-build-stamp] elec/build/default.net: 8 input(s), digest 2c7a04623052...`) |
| `uv run --no-sync python -m pytest elec/validation -q` | **30/30 passed** |
| `scripts/check_domain_partition.py` (depends on the same cherry-picked `_lib/freshness.py`) | **PASSED** -- 0 domain crossings, 0 isolator-barrier breaches, 0 protective-impedance chain defects, over 164 compiled nets / 168 components |
| `scripts/check_manifest_gate.py` | **PASSED** -- 76 files, 77 manifest entries, 0 empty-imports warnings (the two new scripts this task's cherry-picks introduce, `write_extension_stamps.py`/`write_build_stamp.py`, are already registered -- they shipped with their own manifest entries) |
| `scripts/check_vacuous_gates.py` | **PASSED** -- 542 files scanned, 0 violations |
| `scripts/import_linter_gate.py` | **PASSED** -- 0 new violations (1 pre-existing allowlisted) |
| `scripts/check_rust_drc_presence.py` | **OK** -- `temper_drc_rs` present and fresh, both required symbols found |
| `ruff check` on every file this task's cherry-picks touch (`check_stale_extensions.py`, `write_extension_stamps.py`, `write_build_stamp.py`, `_lib/freshness.py`) | **clean, 0 findings** |
| `scripts/check_evidence_provenance.py` | **FAILED**, but on 13 other sessions' evidence docs this task never touched -- this file's own stamp passes -- see below |
| `scripts/vulture_gate.py` | **FAILED**, but on files this task never touched -- see below |

### `check_evidence_provenance.py`: pre-existing failures, out of scope, not introduced here

Running this gate reports 13 pre-existing FAILs, all in `docs/evidence/`
files this branch never touched (e.g. `2026-07-28-drc-creepage-
constraint.md`, `2026-07-28-pd3-retarget-keepout.md`) -- evidence docs
from other, concurrent agent sessions, dated later than the
`.evidence-provenance-allowlist` file's last commit (`da4b5857`, 08:27),
not yet reconciled with it. `git status --porcelain docs/evidence/`
confirms the only change I made under that directory is adding this file.
This file itself is **not** in the FAIL list -- its own
`provenance: commit=... dirty=false` stamp (line 1) passes the gate
cleanly.

### `vulture_gate.py`: pre-existing failure, out of scope, not introduced here

`vulture_gate.py` reports dead code in
`packages/temper-placer/tests/router_v6/test_dfm_interaction.py` and
`packages/temper-placer/tests/requirements/safety/_real_board_fixture.py`.
Neither file is touched by anything in this branch. Confirmed by diffing
both files (and `scripts/deadcode-baseline.py`) between my base commit
`0cf203af` and my current HEAD: **zero byte difference**
(`git diff 0cf203af HEAD --stat -- <those paths>` produced no output).
This failure predates this task, lives entirely in `packages/temper-placer`
(explicitly out of my assigned scope -- a sibling agent's territory per
the task brief), and is unrelated to shared-mutable-state or environment
isolation. Reporting it rather than silently omitting it, per the
"counts with denominators, no silent scope-narrowing" convention this
repo's own gates enforce on everyone else.

## 5. Files touched

- `Makefile` -- `make extensions`/`make extensions-check` (from `0a94206e`)
  plus the new `make venv-isolate` target (this task).
- `scripts/check_stale_extensions.py` -- `--list-crates` (from `0a94206e`)
  plus content-hash freshness with mtime fallback (from `f9c043a6`).
- `scripts/_lib/freshness.py`, `scripts/write_build_stamp.py`,
  `scripts/write_extension_stamps.py` -- the shared content-hash mechanism
  (from `c59589b0`/`f9c043a6`).
- `scripts/check_domain_partition.py`, `scripts/manifest.yaml`,
  `.github/workflows/python-tests.yml` and related workflow files, and the
  associated test files -- carried along as part of `c59589b0`/`f9c043a6`
  (both are real, already-tested commits; I did not hand-edit any of
  these beyond what the cherry-picks brought in).
- `AGENTS.md` -- documents the shared-vs-isolated `.venv` decision, when
  to reach for `make venv-isolate`, and why it is opt-in.
- This file.

## UNVERIFIED

- **CI-workflow-level effect of the cherry-picked `.github/workflows/*`
  changes.** I did not run GitHub Actions; I verified the underlying
  Python/gate logic locally (§4). The workflow YAML edits themselves are
  inherited from already-merged-elsewhere commits (`c59589b0`, `f9c043a6`,
  `0a94206e`), not authored fresh here.
- **Whether any of the other 41 worktree directories are currently
  "actively working"** (as opposed to idle/completed and awaiting
  cleanup/merge) at the moment of this measurement -- I did not survey
  each one's session state, only counted directories and `.venv`
  presence/size. The "23 more would cost ~15.5 GiB" figure in §3.3 is
  therefore an upper bound assuming all 42 isolate, not a claim that all
  42 are simultaneously active agents today.
- **The exact cause of the -2 GiB `df` delta in §3.3** beyond "confounded
  by concurrent sessions" -- I did not instrument or attribute it to any
  specific other process, since doing so would require inspecting other
  sessions' worktrees, out of scope and explicitly disallowed (this task's
  hard rules restrict me to my own worktree).
- **Whether `make venv-isolate` should eventually become a hook fired
  automatically at worktree-creation time.** No such hook exists in this
  repo for me to wire it into (worktree creation is done by the outer
  harness/coordinator, not by any script under version control here); this
  finding is therefore that a manual, one-command, well-documented action
  is the right scope for *this* task, not a claim that automation would be
  wrong if the harness later exposes a creation-time hook.

## Related

- `docs/solutions/best-practices/shared-mutable-state-dominant-cost-multi-agent-repo-2026-07-28.md`
  -- the problem statement this task responds to.
- `docs/solutions/best-practices/green-rust-tests-are-not-evidence-the-extension-was-rebuilt-2026-07-27.md`
  -- why `cargo test` green is not evidence the installed `.so` is current.
- Commits `0a94206e`, `c59589b0`, `f9c043a6` -- cherry-picked onto this
  branch rather than duplicated; see §0.
- `scripts/_lib/measurement_provenance.py` -- the same content-hash-over-
  mtime correction, applied earlier to measurement-artifact provenance;
  cited by the task brief as the precedent this generalizes.
