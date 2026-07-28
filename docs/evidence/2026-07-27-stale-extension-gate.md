<!-- provenance: commit=06490e8c450b45500196b025f02ecfbc002d88f4 dirty=true -->

# Stale-compiled-Rust-extension CI gate

Base commit: `02e907b9a5e1dbca4eae9a0a53f8a2be6dc862c5` (`fix(build): no pyo3
extension in this repo could be rebuilt on macOS`), branch
`docs/methodology-loop-discipline`. Work done in worktree
`agent-a4c286fee4330230d` on branch `feat/stale-extension-gate`, checked out
directly at that commit.

All numbers below were produced by actually running the commands shown, on
this machine (macOS arm64, Python 3.12.13, `uv 0.10.9`, `cargo 1.92.0`), not
inferred.

## What was built

`scripts/check_stale_extensions.py` (see its own docstring for full design
rationale) plus `scripts/tests/test_check_stale_extensions.py` (25 unit
tests), wired into `scripts/manifest.yaml` and
`.github/workflows/python-tests.yml`.

## Crate discovery

The gate scans `packages/` for `pyproject.toml`/`Cargo.toml` pairs shaped
like a pyo3 extension (maturin backend, `cdylib` in `[lib].crate-type`,
`pyo3` in `[dependencies]`). On this tree it discovers **10** crates:

```
temper-constraint-compiler   temper_constraint_compiler
temper-constraints            temper_constraints          (packages/temper-placer/temper-constraints)
temper-design-bundle          temper_design_bundle_python  (module-name != crate name)
temper-drc-rs                 temper_drc_rs
temper-dsn                    temper_dsn
temper-geometry                temper_geometry
temper-io-types                temper_io_types
temper-ipc                     temper_ipc
temper-quality-oracle           temper_quality_oracle
temper-rust-router              temper_rust_router
```

The task brief said "~9"; the true count is 10 (`temper-placer/temper-constraints`
is a nested tenth pyo3 crate not immediately visible from `packages/*` top-level
listing). `temper-py-bridge` also depends on `pyo3` but is `rlib`-only (a shared
bridge helper crate, not independently importable) and is correctly excluded.

## Falsifier

> "This gate catches the temper_io_types staleness that actually happened. If
> it cannot reproduce a detection of that specific historical case, it does
> not work."

**It fired. Full sequence, every state independently verified (not narrated
from memory):**

### 1. Baseline: PASS on a fully-built tree

All 10 crates built (`uv sync --all-packages --inexact
--no-install-package temper-rust-router --no-install-package temper-drc-rs
--no-install-package temper-constraints`, plus `maturin develop --release`
for those three excluded packages and for `temper-quality-oracle` /
`temper-constraint-compiler`, matching CI's own build steps).

```
$ uv run --no-sync python scripts/check_stale_extensions.py; echo $?
...
PASSED -- 10/10 extension module(s) fresh.
0
```

### 2. Mutate: real content edit to the exact file/symbol from the incident

Added a one-line comment above `use pyo3::create_exception;` at the top of
`packages/temper-io-types/src/lib.rs` (the file that, in the real incident,
gained `ConfigBoardMismatchError` at line 1178-1181 without the installed
`.so` being rebuilt). This is a genuine content change, not a bare `touch`
(confirmed: `git diff --stat` showed the file as modified before revert).

```
$ uv run --no-sync python scripts/check_stale_extensions.py; echo $?
...
[STALE] temper-io-types: temper_io_types: installed artifact
  .../temper_io_types.cpython-312-darwin.so (built 2026-07-27T22:46:30)
  predates .../packages/temper-io-types/src/lib.rs
  (modified 2026-07-27T22:53:13, 0.00 day(s) newer) -- rebuild with
  `uv run maturin develop --release --manifest-path .../Cargo.toml`
FAILED -- 1 stale extension(s).
3
```

Exit 3, correctly named `temper-io-types`. This is the direct reconstruction
the falsifier demands.

### 3. Restore: rebuild, then PASS

```
$ uv run maturin develop --release --manifest-path packages/temper-io-types/Cargo.toml
   Compiling temper-io-types v0.1.0 (...)
    Finished `release` profile [optimized] target(s) in 1.51s
🛠 Installed temper-io-types-0.1.0

$ uv run --no-sync python scripts/check_stale_extensions.py; echo $?
...
[OK] temper-io-types: ... is fresh
PASSED -- 10/10 extension module(s) fresh.
0
```

Reverted the comment (`git diff --stat packages/temper-io-types/src/lib.rs`
empty afterward), rebuilt once more, re-ran the gate: `PASSED -- 10/10`,
exit 0, tree left exactly as it started.

**Falsifier verdict: fired as required. FAIL on the reconstructed incident,
PASS after a real rebuild, both independently observed via direct file
`stat`/`md5` inspection, not just gate stdout.**

## An unplanned second finding: `uv run`'s implicit auto-sync silently
## reverted a real, successful rebuild

While reproducing step 2 above, an *unplanned* live recurrence of the
exact incident class surfaced, one level below anything this task asked
for:

1. `uv run maturin develop --release --manifest-path
   packages/temper-io-types/Cargo.toml` ran to completion, printed
   `Installed temper-io-types-0.1.0`, and a plain `stat`/`md5` of
   `.venv/lib/python3.12/site-packages/temper_io_types/temper_io_types.cpython-312-darwin.so`
   run in the very next shell command confirmed the artifact WAS fresh
   (mtime `2026-07-27T22:54:43`, md5 `c9c34783...`, matching
   `packages/temper-io-types/target/release/libtemper_io_types.dylib`
   byte-for-byte).
2. Running `uv run python -c "pass"` -- nothing but a no-op, not even
   touching `temper_io_types` -- printed `Uninstalled 1 package ...
   Installed 1 package` and silently reverted the `.so` back to the OLD
   content (md5 `ff4c7d47...`, mtime `2026-07-27T22:46:30`).

Root cause: `uv run <cmd>` performs an implicit environment sync before
running anything, unless `--no-sync`/`--frozen` is passed. `temper-io-types`
is declared as a workspace dependency of the root project
(`pyproject.toml`'s `[dependency-groups] dev` + `[tool.uv.sources]
temper-io-types = {workspace = true}`), so uv's own build cache for it --
populated by an earlier `uv sync`, independent of anything `maturin
develop` did afterward -- gets silently reinstalled over whatever a manual
`maturin develop` just placed there.

This means: on this repo, running `uv run maturin develop
--manifest-path packages/temper-io-types/Cargo.toml` (or the same for
`temper-geometry`, `temper-dsn`, `temper-ipc`, `temper-design-bundle` --
the other four workspace-managed pyo3 crates) followed by *any* other
`uv run` invocation can silently discard the rebuild, with no error and
no warning from either tool -- an even sharper version of "a success
message from the build tool is not proof the artifact was replaced" than
the original incident, because here BOTH tools report success and the
artifact still reverts.

**Practical implication confirmed by testing**: `uv run --no-sync
<cmd>` avoids the clobber. All verification in this document after this
discovery uses `--no-sync` for exactly that reason.

**Why CI is not exposed to this** (reasoned, not independently proven in
a real CI run -- see UNVERIFIED): `python-tests.yml` never runs `maturin
develop` for `temper-geometry`/`temper-dsn`/`temper-ipc`/`temper-io-types`/
`temper-design-bundle` at all -- they are built exactly once, by the
single `uv sync --all-packages --inexact ...` step, and every subsequent
`uv run` in that job sees an environment already consistent with what
`uv sync` itself just produced, so there is nothing for a later implicit
sync to "correct" back to. The hazard is specific to a local workflow that
interleaves manual `maturin develop` with `uv run` for one of these five
crates.

## Missing-module and required-flag behavior

```
$ mv .venv/.../temper_ipc .venv/.../temper_ipc.bak
$ uv run --no-sync python scripts/check_stale_extensions.py; echo $?      # lenient default
... WARN -- 1 extension module(s) not installed ...
0
$ TEMPER_REQUIRE_FRESH_EXTENSIONS=1 uv run --no-sync python scripts/check_stale_extensions.py; echo $?
... FAILED -- 0 stale extension(s), 1 missing extension(s) (required). ...
3
$ mv .venv/.../temper_ipc.bak .venv/.../temper_ipc   # restored
$ uv run --no-sync python scripts/check_stale_extensions.py; echo $?
0
```

STALE is unconditionally fatal regardless of this flag (see the script's
own docstring, "The 'is staleness fatal here' signal").

## Vacuous-case backstop

```
$ mkdir -p /tmp-scratch/empty/packages /tmp-scratch/empty/.git
$ uv run --no-sync python scripts/check_stale_extensions.py --repo-root /tmp-scratch/empty; echo $?
=== STALE-EXTENSION GATE ERROR ===
Reason: zero pyo3/maturin extension crates discovered under ...
5
```

## Full verification matrix (task's VERIFY section)

All run from a clean tree at this worktree's HEAD, with every pyo3 crate
freshly built, using `uv run --no-sync` throughout for the reason above:

| Check | Result |
|---|---|
| `make netlist` | exit 0, build complete |
| `check_stale_extensions.py` (this gate) | exit 0, `PASSED -- 10/10` |
| `check_domain_partition.py` | exit 0, `PASSED -- 0 domain crossings...` |
| `capacity_budget_gate.py` | exit 0, `PASSED — 0 defects` |
| `mpn_fabrication_gate.py` | exit 0, `PASSED -- 0 new violations` |
| `check_derived_doc_drift.py` | exit 0, `passed` |
| `check_copper_net_consistency.py` | exit 0, `PASSED -- 0 violations across 2482 copper item(s) and 510 pad(s)` |
| `check_rust_drc_presence.py` (`TEMPER_REQUIRE_RUST_DRC=1`) | exit 0, symbols `['run_drc', 'verify_route_clearance']` present |
| `check_undeclared_imports.py` | exit 0, `passed` |
| `uv run python -m pytest elec/validation -q` | exit 0, `30 passed` |
| `scripts/tests/test_check_stale_extensions.py` (25 tests) | all pass |

## Pre-existing findings noticed incidentally (not fixed -- out of scope)

- `scripts/check_copper_net_consistency.py` has no manifest.yaml entry and
  is not wired into any CI workflow (`check_manifest_gate.py` reports this
  as the sole remaining violation after this change adds this gate's own
  entry). Confirmed pre-existing: `git log` shows no local modification to
  either file, and it predates this task's base commit.
- Four pre-existing pytest failures, unrelated to this change (no file
  they touch was modified here): `test_capacity_budget_gate.py::
  test_real_tree_reports_zero_available_set_path_inputs` and
  `::test_real_tree_cli_exits_zero_not_three` (expect 0 AVAILABLE set-path
  inputs; the real tree currently reports 3), `test_mpn_fabrication_gate.py::
  test_gate_fails_on_real_tree_today` (expects exit 3 on a known violation;
  the real tree currently passes with 0 new violations), and
  `test_check_undeclared_imports.py::TestRealRepoIntegration::
  test_real_repo_is_clean` (expects `allowlisted_count == 2`; the real
  `.undeclared-imports-allowlist` currently has 1 entry -- the
  `check_perf_regression.py` entry was removed when that script was
  retired, per that file's own changelog comment, and this particular test
  assertion was not updated to match). None of these four are in the
  task's seven-gate verification list; none were touched to make this
  gate's own verification pass.

## UNVERIFIED

- The modified `.github/workflows/python-tests.yml` has not been run on a
  real GitHub Actions runner (no push/PR was opened as part of this task).
  Verified instead: `actionlint` (no new findings near the added lines --
  the only findings are pre-existing shellcheck warnings at line 385,
  untouched by this change) and `python3 -c "import yaml; yaml.safe_load(...)"`
  parse the file without error.
- The claim that CI's job ordering is immune to the `uv run` auto-sync
  clobber described above is reasoned from the workflow's structure (no
  `maturin develop` step targets the five uv-workspace-managed crates), not
  observed in an actual CI run.
- The root cause of the very first `maturin develop` invocation after the
  content edit not copying the freshly-compiled `.dylib` into
  `.venv/site-packages` (before the `uv run` auto-sync explanation was
  isolated) was not independently root-caused beyond "either the auto-sync
  explanation covers this case too, or maturin/pip's own install step
  no-ops on a matching version string." The auto-sync explanation was
  proven sufficient and reproducible in isolation (`uv run maturin
  develop` followed by a bare `uv run python -c pass`); a second,
  independent root cause for the very first occurrence was not ruled out.
- No test was run against a real GitHub Actions container image
  (`ghcr.io/bennetleff/temper-ci:latest`); all verification above ran on
  local macOS arm64 with a locally installed Rust/uv toolchain.
