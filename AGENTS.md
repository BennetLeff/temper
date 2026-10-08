# Instructions for AI Agents

## Project Context

Temper is an ESP32-S3 induction cooker. The repository holds:

- `zapote/` — the board validation workspace (Rust ERC/DRC/DFM, the five standalone
  units, the 120 V power stage). Its own rules are in [zapote/AGENTS.md](zapote/AGENTS.md);
  check discovery starts at [zapote/CHECKS.md](zapote/CHECKS.md).
- `firmware/` — ESP32-S3 firmware with host tests and its code generators/gates in `firmware/tools/`.
- `packages/` — the design-bundle crate chain zapote's unit tools build on.
- `components/`, `datasheets/`, `docs/`, `skills/`, `output/` — part docs, references, history and review skills.

The legacy placer/router, the old production board (`pcb/`, `elec/`), datasets and their CI
were removed on 2026-10-08; everything is recoverable from tag `archive/temper-legacy-2026-10-08`.

## Product design guidance

For consequential product, enclosure, PCB/power, or manufacturing decisions, use
the relevant source-backed skill under `skills/`: `temper-product-taste`,
`temper-mechanical-review`, `temper-pcb-power-review`, or
`temper-manufacturing-review`. Read only the skill relevant to the decision and
scale its review to the change. The methods and source map are in
`docs/research/mit-product-design/README.md`.

Resolve the current design artifact before transferring any earlier result:
the archived legacy board, the 120 V power-stage source, and enclosure prototypes have different
identities and maturity. Coursework informs design methods; actual component,
supplier, product-standard, and test evidence sets acceptance limits. Geometry,
connectivity, and simulation passes do not by themselves qualify hardware.

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

## Measurement Instruments That Lie — read before trusting any number

A measurement is only as trustworthy as its apparatus. The full incident record is
[docs/evidence/2026-08-19-measurement-instruments-that-lie.md](docs/evidence/2026-08-19-measurement-instruments-that-lie.md);
the rules that still apply:

* **Rebuild before you measure.** A stale pyo3 extension or binary silently runs old
  code. For the design-bundle module, run `uv sync` (or
  `python3 zapote/tools/generators/check_stale_extensions.py`) before trusting a result.
* **Use the native oracle.** KiCad (`pcbnew`, `kicad-cli`) is the ground truth for board
  geometry, DRC and ERC. KiCad places footprint children with clockwise `R(-theta)`; test
  rotation with asymmetric, non-90-degree probes, never with symmetric pads.
* **Record the apparatus.** Tool version, input hash, revision, dirty state, sample count and
  observed range go with every number. Repeat nondeterministic measurements.
* **When a result contradicts a recent change, inspect the instrument first** (stale build,
  fixture, environment) before concluding the change is wrong. Never widen a ceiling or
  baseline to make a check pass.

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
outright (exit 128, `fatal: ref updates aborted by hook`). worktree setup scripts
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

## Shared cargo build cache — enforced automatically, not just documented

`python3 scripts/install_cargo_target_dir_guard.py` installs a `cargo` wrapper at
`~/.local/bin/cargo` (ahead of `~/.cargo/bin` on PATH) that fixes
`CARGO_TARGET_DIR` for **every** cargo/maturin invocation on this host, from
any worktree, in any shell — no sourcing, no remembering. worktree setup scripts
install/refresh it automatically. Setting up a
worktree by hand (`git worktree add`, not worktree setup scripts)? Run it once:

```bash
python3 scripts/install_cargo_target_dir_guard.py
```

It is scoped to this repo only (checked via `git rev-parse
--git-common-dir`), never touches other cargo projects on the host, and
respects an explicitly-set `CARGO_TARGET_DIR`. See the script's module
docstring for the mechanism, and `scripts/check_no_worktree_target_dirs.py`
(`python3 scripts/check_no_worktree_target_dirs.py`, `--clean` to also delete violations
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

The only Python extension left is `temper_design_bundle_python`, built from
`packages/temper-design-bundle` (maturin backend, `python` feature) and imported by
zapote's unit tools. `uv sync` (or `make bundle-python`) rebuilds it into the uv
environment. After changing any crate in the design-bundle chain, rebuild before running
a zapote tool; `python3 zapote/tools/generators/check_stale_extensions.py` reports a
stale installed module. `.cargo/config.toml` carries the macOS link flags pyo3 needs.

## Physics Verification Conventions

### Bug-Triage Rule (R22)

When an invariant surfaces a real bug, produce a triaged bug report. Trivial fixes
in-scope: sign flip, index/stencil mis-orientation, BC swap, off-by-one. Architectural
fixes (e.g., "the solver needs a different discretization") are documented and scoped
as a separate follow-up — do not inline a redesign in a bugfix PR.

## Operational Rules

*   **No "Ready when you are"**: You must push your changes (`git push`).
*   **Sandboxing**: Recommend enabling sandboxing for shell execution.
*   **Context**: Read `AGENTS.md` for deep dives into specific subsystems.

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
