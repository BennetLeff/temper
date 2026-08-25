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
coincidence — the `GATE_HS` ampacity incident (Rust's substring lookup
returned the right value only because the stale key `GATE_H` was a literal
prefix, and would equally have matched `XGATE_HSY`) is in
`docs/evidence/2026-08-17-gate-drive-ampacity-key-rename-fix.md`.

So the sequence is: **make Rust right → prove it against Python with a
differential oracle → delete the Python → keep the oracle.** The ~187 pinned
`_*_py_oracle.py` files exist to make that deletion safe; adding a new oracle
for newly-ported code is correct and expected. Re-pinning an *existing* one is
a separate, deliberately-committed act requiring evidence first.

**A differential test only proves what you feed it.** The Rust/Python
ampacity divergence above survived a genuinely-running differential test
because that test's input was `"Gate_H"` — a net name absent from this board.
When you write or trust a differential, check that its inputs are values the
production system actually sees.

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
*same* PR, not as a follow-up** — the re-measurement is logically part of
the board change, exactly like the firmware codegen steps above are part of
their manifest edits. Why same-PR is load-bearing (and why branch
protection does not enforce it):
`docs/solutions/best-practices/drc-ceiling-same-pr-discipline-2026-08-19.md`.

Re-measure with the same tool, flags, and sample count every prior entry in
the file's own `_march` log used (read that log before touching a number --
it documents an "observed max + headroom" convention for every category
whose count moves on a byte-identical board, and the reasoning behind every
prior ceiling move). **`clearance` is not the only such category any more --
`creepage` has been the chronically-scattering one since the #602 K3 swap
(2026-08-02), and both can be nondeterministic on the same board at once.**
Check `nondeterministic_error_types` in the CURRENT record, not this
sentence, for which categories apply today.

**The headroom you pick is not free to choose: it must satisfy the
noise-headroom invariant
(`ceiling - max(observed) >= max(observed) - min(observed)`).** See
`temper_placer.regression.drc_ratchet.NoiseHeadroomViolation` for the
invariant and its proof. This is not hypothetical: every
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
  than reporting only the aggregate. Entries use the standardized structured
  format (`{"date": ..., "cause": "...", "per_type_delta": {...}}`, see the
  file's own `_goal` header) -- the `cause` field is the attribution and
  must be non-empty.
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

**Why same-PR, not after**: the provenance check fails closed the moment
the board's content hash drifts, but a red run of the `Board, Provenance &
Requirements Gates` job does **not** block merging — it is not among
`required_contexts` in `.github/required-checks.json` (as of 2026-08-07;
adding it is a maintainer call). Landing the re-measurement in the same
commit is what actually prevents the gap. Full analysis:
`docs/solutions/best-practices/drc-ceiling-same-pr-discipline-2026-08-19.md`;
the cascade it prevents:
`docs/evidence/2026-07-30-drc-ceiling-remeasurement-cascade.md`.

**Provenance identity**: a measurement's primary, authoritative identity
is the content hash at `provenance.inputs[].sha256`; `measured_at_commit`
is advisory but must resolve when not `"UNKNOWN"` (a dangling commit is a
hard failure — worse than an honest `"UNKNOWN"`), and `dirty: true` is a
hard failure on every provenanced record, not only on a raise. All three
are checked unconditionally by `check_measurement_provenance.py` on every
PR that touches a registered measurement artifact. Full 2026-08-07
incident and design rationale (why a commit SHA cannot be the primary
identity):
`docs/evidence/2026-08-07-drc-ceiling-provenance-identity-incident.md`.

## Measurement Instruments That Lie — read before trusting any number

Every one of these produced a wrong conclusion that someone acted on. Full
incident narratives and measured numbers:
`docs/evidence/2026-08-19-measurement-instruments-that-lie.md`.

**A number from a mis-set-up instrument is indistinguishable from a real
result.** In a single day these manufactured five phantom test failures, one
invalid baseline, a regression that never existed, and two hypotheses that
sent whole investigations down dead ends.

### DRC / kicad-cli

* **Regenerate `pcb/temper.kicad_dru`** (`scripts/generate_kicad_dru.py`)
  before any DRC run — it is gitignored/generated; without it creepage
  reads 0 and clearance reads a different count.
* **`_drc_api.run_drc()` is necessary but NOT sufficient** — the board
  needs an `fp-lib-table` sibling. Signature: `lib_footprint_issues` ==
  board footprint count (168) with `lib_footprint_mismatch` == 0 — that
  pair is a resolution failure, not a census.
* **kicad-cli caps**: a count of exactly 199 or 499 is a cap, not a count.
* **kicad-cli is nondeterministic run-to-run** — run 3x and intersect;
  normalize net-order swaps before diffing.
* **Creepage reports per NET PAIR, not pad pair** — clearing one unmasks
  another; diff violation SETS, not counts (`DrcResult.errors`/`.warnings`,
  `DrcError.rule`/`.nets`/`.items`).
* **Ad-hoc DRC harnesses must copy the library table** (`fp-lib-table` +
  libs/, and a seeded `KICAD_CONFIG_HOME`), not just the board sidecars —
  same 168/0 signature above. `_drc_api._single_threaded_kicad_env` already
  does this correctly: mirror it, or call it. Category *deltas* survive a
  constant harness error; absolutes do not.

### Build / environment

* **`make extensions` fails hard when `CONDA_PREFIX` is set** — maturin
  refuses when it coexists with `VIRTUAL_ENV`. Use `env -u CONDA_PREFIX`.
* **A stale `.so` fails loudly, not subtly**: `AttributeError: module
  'temper_rust_router' has no attribute '...'`. Run
  `scripts/check_stale_extensions.py` before trusting any number; any PR
  that changes a pyo3 boundary leaves every unrebuilt checkout broken.
* **`check_venv_integrity.py` false-positives** on worktrees nested under
  `.claude/worktrees/` (`classify_path` prefix bug) — check the printed
  paths before acting on a violation report.

### Test harness

* **Set pytest timeouts above 1200s for full-route tests** —
  `test_route_pcb_production_board` needs ~1193s; a 900s cap manufactured a
  phantom "20th failure".
* **Hypothesis replays counterexamples from its example DB** — a failure
  only on your branch may be a stored replay; clear the DB before
  concluding you caused it. A real counterexample deserves its own ticket,
  not a flake write-off.

### Figures that look measured and are not

* **`attempted_ripups` is a hardcoded literal** (every net reports 0) — not
  evidence about displacement of committed copper.
* **`RouteProfileStats.python_time_ms` is structurally always 0.0** — still
  published as `maze_router_python_ms`.
* **A 16-character digest prefix is not a 64-character claim** — compare
  full digests programmatically; after a squash merge the branch SHA is
  never an ancestor of `main` (expected, not lost work).

### Correct by coincidence — a passing test that proves nothing

* **All 527 pads on `pcb/temper.kicad_pcb` sit at a multiple of 90 degrees**
  (0:58, 90:202, 180:175, 270:92 — measured 2026-08-18, none elsewhere). At a
  multiple of 90, KiCad's R(-theta) and the standard-math R(+theta) produce the
  **same corner set** for a pad's copper rectangle; they differ only in ring
  traversal order, which no distance, containment or area query can observe.
  `pad_core_polygon`, `pad_polygon` and their Rust twin
  `clearance_geometry.rs::pad_core` were R(+theta) — the mirror of the truth —
  from the Wave 3 migration until 2026-08-18, and reproduced `kicad-cli` to four
  decimals throughout. **Agreement on this board is not evidence of a correct
  convention.** Any geometry claim about rotation has to be tested off a 90
  multiple: `scripts/check_pad_core_polygon_oracle.py` does that against pcbnew.
  See `docs/evidence/2026-08-18-pad-core-polygon-rotation-convention.md`.
* **A differential suite cannot see a convention error.**
  `test_clearance_rust_differential.py` pins Rust == Python bit-for-bit. A
  **consistently wrong pair passes it**, and did for months. Bit-exactness
  between two of your own implementations is not correctness; only an external
  oracle (pcbnew, `kicad-cli`) can supply that. Correcting one side alone does
  not produce evidence either — it produces a red suite. Move both, and anchor
  the convention somewhere the oracle cannot reach.
* **A plain `cargo build`/`cargo test` in a pyo3 crate poisons the extension
  everyone else imports, and `maturin develop` then reports success.** The
  `python` feature is not default, so a bare `cargo build --release -p
  temper-geometry` links `target-shared/release/libtemper_geometry.so`
  *without* `PyInit_temper_geometry` — and that path is SHARED across every
  worktree. The next `maturin develop --release` prints `Finished ... in
  0.04s`, `Installed temper-geometry-0.1.0`, and a single easily-missed
  `⚠️ Warning: Couldn't find the symbol PyInit_...` line, then installs the
  broken artifact. Every import of that module dies with
  `ImportError: dynamic module does not define module export function`.
  Observed 2026-08-18; `check_stale_extensions.py` reports it as
  `[UNLOADABLE]` and names the cause.
  **`cargo clean -p temper-geometry` did NOT fix it** — it printed
  `Removed 0 files` because cargo's fingerprint was already satisfied. What
  worked: `touch packages/temper-geometry/src/lib.rs`, then `maturin develop
  --release`, **confirming a real `Compiling temper-geometry` line and a
  minute of build time**. A `Finished ... in 0.0Xs` means it reused the
  poisoned artifact. Then rebuild every dependent crate, whose own `.so`s the
  touch just made `[STALE]`.
  Use `make extensions` / `maturin develop`, not bare `cargo build`, in these
  crates — and **run `make extensions-check` between the edit and the
  measurement**, not merely after the build command claims success.
* **An installed extension can silently REVERT to an older cached wheel, in a
  worktree with its own `.venv`.** Observed 2026-08-18: an hour after a
  verified `make extensions-check` PASS, `temper_geometry`'s `.so` was back at
  the mtime of the wheel built during `make venv-isolate` (link count 2 — a
  hardlink into a cache another process rewrote). The result was post-fix
  Python running against a pre-fix Rust kernel — a state no commit describes —
  and it manufactured **48 phantom failures**, including the change's own gate
  self-test. After `maturin develop --release` the same selection reported
  3623 passed / 3 failed (all 3 pre-existing on `origin/main`).
  This is the same class as the shared-`.venv` poisoning below, but `venv-
  isolate` does NOT immunise against it. **Re-verify `make extensions-check`
  immediately before every measurement you intend to report — not once per
  session** — and treat a sudden broad failure as a suspect instrument first.

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

**Never use `git stash`, in any form, in this repo.** The stash stack is
repo-global, not per-worktree — with 60+ concurrent agent worktrees, a
`git stash pop` can apply *another session's* changes into your tree, and a
`stash drop`/`clear` can destroy another session's unrecovered work. This
has happened (2026-07-28, with real cross-session damage); see
`docs/evidence/2026-07-28-git-stash-guard-incidents.md`.

**Enforcement**: `scripts/git-hooks/reference-transaction`, installed into
the shared `.git/hooks/` by `scripts/install_git_stash_guard.py`, blocks
`git stash` / `stash push` / `stash push -u` / `stash save` / `stash clear`
outright (exit 128, `fatal: ref updates aborted by hook`). `make worktree`
reinstalls it on every invocation; to check or (re)install by hand:

```bash
python3 scripts/install_git_stash_guard.py --check   # report only
python3 scripts/install_git_stash_guard.py            # install/update
```

**Known, tested gap — read before assuming coverage**: the hook *cannot*
block `git stash apply` (it never performs a ref transaction), and cannot
reliably block `git stash pop` / `git stash drop <entry>` of existing
entries (the reflog rewrite bypasses the hookable API). **The prohibition
on `apply`/`pop`/`drop` is a policy rule, not an enforced one.** Even in
the one case where dropping *is* blocked (the last remaining entry), the
reflog is rewritten before the hook fires, so `git stash list` goes empty
regardless — read the block as "the data was not destroyed", not "the
stack looks untouched". Empirical writeup: comments atop
`scripts/git-hooks/reference-transaction`; design rationale and ruled-out
alternatives: `docs/solutions/best-practices/git-stash-guard-mechanism-and-gaps-2026-08-19.md`.

**Detector (defense in depth for the gap)**: `uv run python
scripts/check_stash_stack_gate.py` snapshots the stash reflog and flags
additions/removals since the last run. Not a CI gate — run it manually or
on a timer against the dev machine. Baseline:
`<git-common-dir>/stash-guard-snapshot.json`.

**Bypass** (human, working alone, in a clean single-worktree context — not
the concurrent-agent failure mode):

```bash
ALLOW_GIT_STASH=1 git stash push -m "..."
```

**Safe alternative** (the underlying need — comparing with/without your
changes — routed elsewhere):

```bash
git worktree add ../scratch-<name> -b scratch/<name>   # isolated copy
git branch wip/<name> && git commit -am wip             # scratch branch
git diff > /tmp/patch.diff                               # patch file, git apply later
```

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
merge, and every open PR inherits the red (happened four times on 2026-08-06).

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
and `make venv-isolate` install/refresh it automatically. Setting up a
worktree by hand (`git worktree add`, not `make worktree`)? Run it once:

```bash
python3 scripts/install_cargo_target_dir_guard.py
```

It is scoped to this repo only (checked via `git rev-parse
--git-common-dir`), never touches other cargo projects on the host, and
respects an explicitly-set `CARGO_TARGET_DIR`. See the script's module
docstring for the mechanism, and `scripts/check_no_worktree_target_dirs.py`
(`make check-worktree-target-dirs`, `CLEAN=1` to also delete violations
that pass a `CACHEDIR.TAG` safety check) for the gate that catches anything
that still slips through.

**Why the wrapper, not a shell convention (2026-08-13):** agent
tool-calling harnesses start a *fresh shell process per tool call*, so
shell state — including exported env vars — does not persist between calls;
without the wrapper, `.cargo/config.toml`'s *relative*
`build.target-dir = target-shared` resolves per-worktree and each worktree
cold-compiles all 10 pyo3 crates into its own `target-shared`. Recurrences:
51 GB (2026-07-28), 36.6 GB across 25 caches (2026-08-06), ~74 GB across 99
worktrees (2026-08-11/12) — see
`docs/evidence/2026-08-13-cargo-target-dir-shell-convention-failure.md` and
`docs/solutions/best-practices/shared-cargo-target-dir-guard-2026-08-19.md`.

Trade-off, deliberate: cargo takes an exclusive lock on the target
directory, so concurrent builds in different worktrees serialise instead of
running in parallel — still far cheaper than each doing a cold build.

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

**A stale `.so` does not just fail — it lies.** Run the gate *before* you
believe a number, not after a result surprises you. Absence of a symbol is
not evidence of a missing feature (two real instances:
`docs/evidence/2026-08-11-worktree-poisons-shared-venv.md`).

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

`make venv-isolate` gives a worktree its own `.venv`, immune to *any* other
checkout's `uv sync`/`uv run` — at a measured cost of ~700 MB disk and ~85s
wall time with a warm `uv`/cargo cache (`docs/evidence/2026-07-28-worktree-env-isolation.md`).
**Run it once, at the start of any session that will build or test Rust
extensions.**

**Not the default for every worktree unconditionally.** At fleet scale
(dozens of agent worktrees, low double-digit GB free), isolating every one
is the same disk-multiplication hazard that has already exhausted disk
twice. Isolate the worktrees actually building or testing Rust extensions;
everywhere else rely on the content-hash freshness gate
(`scripts/check_stale_extensions.py`, unconditional, zero downside). Why a
shared `.venv` is the historical default, what it cost, and the two
independent fixes (content-hash stamps + opt-in isolation):
`docs/solutions/best-practices/shared-mutable-state-dominant-cost-multi-agent-repo-2026-07-28.md`.

### The venv can be the wrong tree in five distinct ways

Four 2026-08-11 modes where a worktree poisons the shared venv it builds
into, plus a 2026-08-17 fifth mode where the *healthy* shared venv reads
`main` instead of your worktree. Full narratives:
`docs/evidence/2026-08-11-worktree-poisons-shared-venv.md`,
`docs/evidence/2026-08-17-shared-venv-serves-main-code.md`, and the
five-mode catalog with gate-ordering rationale:
`docs/solutions/best-practices/shared-venv-silent-staleness-modes-2026-08-19.md`.

1. **`maturin` refuses outright if `VIRTUAL_ENV` and `CONDA_PREFIX` are
   both set** — a loud failure, the safe end of the list. Unset whichever
   you are not using before invoking `maturin` directly.
2. **Plain `uv run maturin develop` from a worktree targets a *per-worktree*
   venv and no-ops against the shared one** — unless `UV_PROJECT_ENVIRONMENT`
   points at the shared `.venv` (or the worktree has its own via
   `make venv-isolate`), the build "succeeds" into a venv nobody imports
   from; the shared extension stays stale.
3. **`maturin develop --active` from a worktree rewrites the SHARED venv's
   editable pointers** — `--active` targets whatever venv is *active*
   (`VIRTUAL_ENV`), not one scoped to the worktree it ran from, so every
   subsequent `import` from *any* worktree silently resolves into the
   worktree that ran the command. Closed by `scripts/check_venv_integrity.py`
   (venv *identity*: asserts every editable-install `.pth`/`direct_url.json`
   resolves under the expected repo root — fast, deterministic, local-only):
   ```bash
   .venv/bin/python scripts/check_venv_integrity.py   # or: make venv-integrity-check
   ```
4. **`maturin develop` can report "Installed" while leaving the `.so`
   untouched** — five rebuilds exited 0 in a row while the artifact stayed
   dated a day behind the source. Caught by `scripts/check_stale_extensions.py`
   (per-crate artifact *freshness*); it catches this mtime symptom but not
   mode 3's redirection — identity is logically prior, which is why the two
   are separate gates (CI runs identity first, then freshness).
5. **The shared venv reads `main`, not your worktree** — its `temper_placer`
   is editable-installed against the main checkout, so a worktree agent that
   edits Python and runs `.venv/bin/python scripts/route_board.py` measures
   `main`'s code, not its own change. Defences, in order of preference:
   (1) `make venv-isolate` in your worktree — fixes reads as well as writes;
   (2) if you must use the shared venv, verify what you import before you
   believe a number — `python -c "import temper_placer; print(temper_placer.__file__)"`
   and confirm the path is your worktree.

**The generalizable rule: when a measurement contradicts a change you just
made, suspect the measurement before the change.** Ask what the number
would look like if your edit were not in effect at all — "identical to
before" was exactly the observed result, and that is the signature.

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
current state (see `docs/METHODOLOGY.md` Sec 5 and
`docs/evidence/2026-07-26-measurement-provenance.md`). Every dispatch that
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
the doc was real, merged as #1053 (`d8062c6e6`), and the worktree was cut
exactly one commit earlier. A false accusation of fabrication is worse than
a missing file: it discredits real prior work and invites re-doing it.

Note the asymmetry with the Base-Commit Assertion above: that rule catches
you *measuring* stale state; this one catches you *reasoning* from stale
state — the assertion can pass while the base itself is behind the tip that
has the file you were sent to read. `git fetch` costs a second; concluding
fabrication costs a session.

### Never Work Directly in the Main Checkout

Dispatched agents work in their own worktree, always:

```bash
git worktree add <path> -b <branch> origin/main
```

The main checkout is shared. When two agents use it concurrently, one
switching branches silently discards the other's uncommitted edits -- no
error, no conflict, no warning (in one session an agent lost a completed,
user-requested `AGENTS.md` edit this way; a second discovered branch
switches in the reflog it had not made).

Two corollaries:

*   **Commit early even when the work is unfinished.** An uncommitted edit
    in a shared checkout is not saved work; it is work that happens to
    still be on disk. Committing to a throwaway branch costs nothing.
*   **Leave the main checkout on `main`.** If you did work there, return it
    when done. A shared checkout parked on a feature branch silently
    changes what the next agent measures.

**Your own worktree means *yours*, not merely "not the main checkout."**
Run `git worktree list` and confirm the directory is yours before your
first write — reusing another agent's directory is the more common failure
(on 2026-08-14, seven collisions in one session, including three agents in
one `.claude/worktrees/agent-*` directory: commits landed on another's
branch, and a third's uncommitted edits sat in the tree while HEAD moved
under them twice).

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

Do not background one and stop, expecting to be woken. Nothing wakes you —
four dispatched agents did this in a single session; one did it twice after
being told explicitly. Treat "I'll wait for the background task" as a bug
in your own plan.

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

The coverage gate applies to all public functions in `temper_placer/`
except `_constraint_types/` and `profiling/` (permanently excluded via
`[tool.coverage.run] omit` in `pyproject.toml`). Full spec — scope,
allowlist format, `--init` workflow, shrink rule, paydown cadence:
`docs/solutions/best-practices/coverage-gate-spec-2026-08-19.md`.

**Key rules:**
* A public function (module-level `def` or public-class method, no `_`
  prefix) with **zero executed lines** during the test suite fails the gate
  unless it is on the allowlist (`.coverage-allowlist`, repo root).
* The gate is currently **warn-only** (`continue-on-error: true`) until the
  Phase 1 allowlist (entries for `temper_placer/core/`) shrinks >=50% from
  the initial 193 entries (count tracked in the `.coverage-allowlist`
  header); a follow-on PR then removes `continue-on-error` and the gate
  becomes a hard CI block.
* **Monotonic shrink**: an allowlist entry may only be removed when the
  same PR adds a test exercising the function OR deletes it from source
  (`--check-shrink` enforces this); additions need a real `# TODO:
  temper-xxx` ticket reference (placeholder only for initial bulk
  population). Stale entries (now covered) are WARNINGs, not failures.
* **Phase advancement** (expanding scope, e.g. Phase 3) is gated on 50%
  allowlist paydown; recommended cadence is a quarterly hardening sprint.
* **New phases**: run `check_coverage_gate.py --init --coverage-json
  <path> --allowlist .coverage-allowlist` (preserves existing entries,
  appends new ones with `temper-xxx` placeholders); review, replace
  placeholders with real ticket IDs, commit.
* **Escape hatch**: there is no env-var override — the allowlist IS the
  recorded justification (a reviewer sees additions/removals in `git
  diff`). Emergency skip means editing the CI step config
  (`python-tests.yml`) directly.

## Documented Solutions

`docs/solutions/` — documented solutions to past problems (bugs, best practices,
architecture patterns, workflow issues), organized by category with YAML
frontmatter (`module`, `tags`, `problem_type`). Relevant when implementing or
debugging in documented areas.

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
