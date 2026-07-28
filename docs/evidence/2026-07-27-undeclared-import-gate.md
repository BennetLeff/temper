# Undeclared-import gate: decision, falsifier, mutation proofs, live findings

<!-- provenance: commit=8e0d8527e49e7455597607a48397de1ac50df8b4 dirty=UNKNOWN -->

**Date:** 2026-07-27
**Scope:** `scripts/check_undeclared_imports.py`, `.undeclared-imports-allowlist`,
`scripts/tests/test_check_undeclared_imports.py`, CI wiring in
`.github/workflows/python-tests.yml`, registration in `scripts/manifest.yaml`.
**Status:** implemented, tested, wired fail-closed from day one (no soft
launch -- see "Why no soft launch" below). Not a design document -- this is
the as-built report.

---

## The failure class, restated

Two third-party dependencies were imported by first-party code but declared
nowhere -- not in any `pyproject.toml`, not in `uv.lock`, not installed in
any environment:

1. **`jinja2`** -- imported top-level by `scripts/gen_domain_models.py`. The
   "Check domain model codegen drift" CI step died on `ModuleNotFoundError`
   on *every* run; that gate had never executed once.
2. **`sympy`** -- imported top-level by
   `packages/temper-placer/tests/physics/test_thermal_fdm_mms.py`, the
   Method of Manufactured Solutions 2nd-order convergence proof for the
   thermal FDM solver -- one of the strongest correctness claims in the
   repo. It had never been collected.

Both were invisible for the same reason: the CI step that would have run
them carries `continue-on-error: true`. Both are now declared in this
branch's `pyproject.toml` (`[dependency-groups] dev`), so the current tree
is clean -- which is exactly the trap: a gate built and only ever run
against a tree that's already fixed proves nothing about whether it would
have caught the incident. The falsifier and mutation tests below exist to
close that hole.

---

## Design: resolvability, not dependency-list parsing

A module's import name frequently differs from its PyPI distribution name
(`jinja2` ships as `Jinja2`; `yaml` as `PyYAML`; `sklearn` as
`scikit-learn`). Comparing AST-extracted import names against parsed
`pyproject.toml`/`uv.lock` dependency lists would need a private,
constantly-drifting import-name -> distribution-name table, and would
still be wrong for this workspace's own `pyyaml` situation: it is declared
only in `temper-placer`'s and `temper-workflow`'s `pyproject.toml`, and a
plain `uv sync` (without `--all-packages`) prunes workspace packages and
removes it.

Instead the gate asks the only question that actually matters: **is this
module resolvable in the interpreter about to run the test suite?**,
answered directly with `importlib.util.find_spec` (locate, not import --
no third-party top-level code executes as a side effect of running a CI
gate). This requires the gate to run under `uv run` **after**
`uv sync --all-packages` (never a plain `uv sync`) in CI, which is where it
is wired (see "Wiring" below).

---

## Scope decisions

### Which imports are scanned: module-level (`tree.body`) only

Mirrors `scripts/trace_invocations.py::extract_imports`'s own deliberate
choice. A full `ast.walk` would also catch imports nested inside a
function, a `try/except ImportError`, or an `if TYPE_CHECKING:` block --
all *legitimately optional* in this repo. Two real, tested cases:

- **`pcbnew`** (`scripts/kicad_fill_zones.py`): imported inside `main()`,
  guarded by `try/except ImportError`, specifically because it must run
  under a *different* (system) interpreter than `uv run`. Scanning only
  `tree.body` excludes it by construction -- it is not a direct child of
  the module.
- **Rust extensions** (`temper_rust_router`, `temper_constraints`,
  `temper_drc_rs`): a survey of `packages/temper-placer/src` (see "Why
  `packages/*/src` is out of scope" below) found these imported exclusively
  inside functions or module-level `try/except` blocks (e.g.
  `loop_extractor_rs.py:144`, `pcl/rust_bridge.py:28`,
  `validation/drc_oracle.py:37`) specifically so a pure-Python fallback
  works when the extension isn't built. Same exclusion, same reason, no
  special-casing needed.

Relative imports (`from . import x`) are also skipped -- always
intra-package, never third-party.

### Which directories: `scripts/`, `scripts/tests/`, `packages/temper-placer/tests/`,
`packages/temper-workflow/tests/`, `elec/validation/`

Exactly the trees the two motivating defects live in (a codegen script, a
physics test), plus the sibling Python test trees sharing the same
failure mode. `packages/temper-constraint-compiler/tests`,
`packages/temper-rust-router-core/tests`, `packages/temper-design-bundle/tests`,
and `packages/temper-geometry/tests` were checked and contain only `.rs`
files -- not in scope for a Python import checker.

### Why `packages/*/src` is out of scope (for now)

A survey using this gate's own mechanism (top-level scan + `find_spec`
against a freshly `uv sync --all-packages`'d environment) against
`packages/*/src` surfaced two live findings that are a *different*
problem, not this one:

1. `packages/temper-workflow/src/temper_workflow/metrics/aesthetic_turing_test.py`
   imports `jax.numpy` top-level; `jax` is undeclared and unresolvable
   (see "The jax finding" below -- same root cause, different file).
2. `packages/temper-placer/src/temper_placer/placer/cp_sat/domain_clearance.py:132`
   imports `from tests.requirements.validators.clearance import (...)` -- a
   deliberate, documented shim (production code reusing its own package's
   test tree via manual `sys.path.insert`, see that file's own
   "Cross-layer import shim" comment). This is first-party, not
   third-party, but is invisible to a bare `find_spec` without reproducing
   that shim's `sys.path` surgery -- a per-package special case this pass
   does not build.

Extending scope to `packages/*/src` would require resolving both first
(an owner decision on `jax`, and either a per-package local-root mechanism
or a scoped allowlist entry for the `tests.` shim) -- exactly the kind of
unrelated scope decision this task's own instructions say not to make
unilaterally, and doing it here would risk either shipping a gate that
doesn't pass on the tree it's meant to protect, or silently allowlisting a
real gap to force it green. Both findings are reported here, not fixed.
Extending scope to `packages/*/src` is a reasonable, separately-scoped
follow-up.

### Local ("first-party") modules

A bare name like `_lib` (`scripts/_lib/`) or `capacity_budget_gate`
(imported by `scripts/tests/test_capacity_budget_gate.py` via that file's
own `sys.path.insert`) is an uninstalled sibling module, not a PyPI
package -- `find_spec` run from an unrelated interpreter state would not
find it either. Before falling back to `find_spec`, the gate checks
whether `<name>.py` or `<name>/__init__.py` exists in the importing file's
own directory or one of that scan target's `local_roots` (each tree's own
`sys.path`/pytest `pythonpath` convention -- see
`build_scan_targets()`). Workspace packages themselves (`temper_placer`,
`temper_geometry`, ...) need no such special-casing: `uv sync --all-packages`
installs them editable, so `find_spec` finds them directly, identically to
any third-party dependency.

### Not redundant with `scripts/import_linter_gate.py`

Import-linter enforces *architectural boundary contracts* between
first-party modules that are already installed and resolvable (e.g.
"`tools/` may not import `temper_placer` internals"). This gate asks a
prior, different question: *is the imported module resolvable in the
environment at all*. It fires on third-party packages never installed in
the first place -- a case import-linter's contract model has no notion of.

---

## Falsifier (stated before reconstruction)

**If reconstructing the jinja2 and sympy incidents against the checker
does not produce a violation naming the specific undeclared module and
file/line, the design is inadequate** -- a check that only compares
strings against dependency-list text, or that fires indiscriminately on
any nested/guarded import, would either miss the real incident shape or
drown it in noise from the `pcbnew`/Rust-extension pattern.

**Result: it did not fire.** Both fixture reconstructions
(`TestHistoricalDefectReconstruction::test_jinja2_incident_reconstructed`,
`test_sympy_incident_reconstructed`) produce a violation naming the exact
module, file, and line; a "declared dependency" control passes clean on
the same shape; five distinct guarded/local-module controls (function-
scoped, module-level `try/except`, `TYPE_CHECKING`, local sibling file,
local sibling package) all pass clean, proving no false positives on
adjacent shapes. 27 tests total, run below.

```
$ uv run pytest scripts/tests/test_check_undeclared_imports.py -v --tb=short
============================== 27 passed in 0.76s ==============================
```

---

## Mutation verification against the real repo (the actual falsifier)

Fixture reconstructions prove the *mechanism* works. The task's real bar
is stronger: would this gate, run against the **actual** repo at the
moment jinja2/sympy were undeclared, have caught it? Verified by literally
reproducing that state -- temporarily removing each declaration from the
real `pyproject.toml`, re-running `uv sync --all-packages`, running the
finished gate against the real repo, then restoring.

### jinja2

```
$ git diff pyproject.toml   # (jinja2 dependency line + its comment removed)
$ uv sync --all-packages --no-install-package temper-rust-router \
    --no-install-package temper-drc-rs --no-install-package temper-constraints
Uninstalled 1 package in 2ms
 - jinja2==3.1.6

$ uv run python3 -c "import jinja2"
ModuleNotFoundError: No module named 'jinja2'

$ uv run python scripts/check_undeclared_imports.py
Undeclared-import gate -- 6 scan target(s), 627 file(s), 3030 module-level import(s) checked
  ...
  stdlib: 1137  local: 1194  allowlisted: 2  resolved: 696
1 UNDECLARED IMPORT(S)
  UNDECLARED scripts/gen_domain_models.py:21 -- module 'jinja2' is imported
  at module level but is not resolvable in the synced environment ...
$ echo "EXIT=$?"
EXIT=3
```

Exact file (`scripts/gen_domain_models.py`), exact line (21, the
`from jinja2 import Environment, FileSystemLoader` statement), exact
module name, real non-zero exit code -- against the real repository, not
a fixture.

### sympy

pyproject.toml restored, re-synced (jinja2 back to installed), then the
same procedure for sympy:

```
$ uv sync --all-packages --no-install-package temper-rust-router \
    --no-install-package temper-drc-rs --no-install-package temper-constraints
Uninstalled 2 packages in 125ms
Installed 1 package in 1ms
 + jinja2==3.1.6
 - mpmath==1.3.0
 - sympy==1.14.0

$ uv run python3 -c "import sympy"
ModuleNotFoundError: No module named 'sympy'

$ uv run python scripts/check_undeclared_imports.py
Undeclared-import gate -- 6 scan target(s), 627 file(s), 3030 module-level import(s) checked
  ...
1 UNDECLARED IMPORT(S)
  UNDECLARED packages/temper-placer/tests/physics/test_thermal_fdm_mms.py:30 --
  module 'sympy' is imported at module level but is not resolvable ...
$ echo "EXIT=$?"
EXIT=3
```

Exact file, exact line (30, `import sympy as sp`), exact module,
exit 3.

pyproject.toml then restored to its exact original content (`git diff
--stat pyproject.toml` shows no diff) and `uv sync --all-packages`
re-run to bring both jinja2 and sympy back into the environment before
any further verification.

---

## Anti-vacuity proofs

Per the brief: a scan root that doesn't exist, zero files found, a file
that fails to parse, and a malformed/unscoped allowlist entry must all
fail closed, never `clean`. `TestAntiVacuity`, all pass, each asserting
`state == "tool_error"` (exit 5):

| Degenerate input | Result |
|---|---|
| Zero scan targets configured | `tool_error` ("zero scan targets configured") |
| A configured scan root does not exist | `tool_error` (names the root) |
| Zero files found across all scan targets | `tool_error` ("zero files found to inspect") |
| A file cannot be parsed (`SyntaxError`) | `tool_error` (names the file, "could not parse file") |
| Allowlist entry has no `#` justification | `tool_error` |
| Allowlist entry's justification is empty | `tool_error` (`load_allowlist` raises directly) |
| Allowlist entry has no `module::file-glob` separator (bare module name) | `tool_error` -- this gate deliberately never supports a module-wide exemption |
| Every parsed file has zero top-level import statements at all | `tool_error` ("vacuous run, not a clean pass") -- structural backstop independent of the per-file checks above |

Anti-vacuity (positive form): `test_jinja2_incident_reconstructed` and
`test_sympy_incident_reconstructed` prove the gate detects an injected
undeclared import via a controlled `find_spec` patch, so it cannot rot
into a no-op; `test_allowlist_entry_scoped_to_one_file_does_not_exempt_another`
proves an allowlist entry cannot silently widen into a module-wide
exemption.

---

## What it found on today's tree: the jax finding

Running the gate for real (not the fixture reconstructions above) against
the current tree surfaced one additional, pre-existing, real defect of
the *exact same shape* as the two motivating incidents -- found by the
gate's own mechanism, not hypothesized:

```
UNDECLARED scripts/check_perf_regression.py:22 -- module 'jax' ...
UNDECLARED scripts/internal_route.py:13 -- module 'jax' ...
```

`jax` is imported top-level by both scripts (`import jax` /
`import jax.numpy as jnp`), both are invoked via `uv run` from the
Makefile (`make perf-regression`, `make route`), `make perf-regression`
is itself already `continue-on-error: true` in CI's "regression" job --
the same silent-failure shape as jinja2/sympy. Confirmed genuinely
undeclared, not merely un-synced in this environment:

```
$ grep -rn "\"jax" packages/*/pyproject.toml pyproject.toml
(no output)
$ grep -rln "^import jax\|^from jax" packages/temper-placer/src --include="*.py"
(no output)   # not even a transitive dependency of production code
```

This is out of this task's scope to fix (per the task's own instruction
not to unilaterally "fix" pre-existing broken modules that need an owner
decision -- declare `jax`? retire the scripts?), so it was not added to
`pyproject.toml`. It is not silently ignored either: two precisely scoped
`.undeclared-imports-allowlist` entries
(`jax::scripts/check_perf_regression.py`,
`jax::scripts/internal_route.py`) exempt exactly these two known files,
each with a `# TODO: temper-xxx` justification, so the gate reports
`clean` today without hiding the finding (it is fully documented here and
in the allowlist file itself) and without exempting `jax` anywhere else
in the scanned trees.

### Why no soft launch (CUTOVER_DATE)

`scripts/import_linter_gate.py` and `scripts/check_derived_doc_drift.py`
both use a global, time-boxed `CUTOVER_DATE` bring-up window for exactly
this situation (real pre-existing violations found at gate-build time).
That pattern was considered and rejected here: a *global* grace window
would also silently pass a **brand-new** undeclared import introduced
anywhere in the scanned trees during the window -- including a
hypothetical re-introduction of the exact jinja2/sympy defect this gate
exists to catch. That defeats the point on day one. The precisely scoped
allowlist entries above give the `jax` finding the same "not immediately
blocking, but tracked and visible" treatment without that hole: this gate
is hard-blocking, `continue-on-error`-free, from the first commit.

---

## Manual survey: other test trees checked and found out of scope

`packages/temper-constraint-compiler/tests`,
`packages/temper-rust-router-core/tests`,
`packages/temper-design-bundle/tests`, `packages/temper-geometry/tests` --
all contain only `.rs` files (Rust integration/property tests), not
Python. Confirmed via direct listing; not silently assumed.

---

## Wiring

Wired into `.github/workflows/python-tests.yml`'s existing `Core Tests`
(`test`) job, immediately after the design-capacity-budget gate and before
`Rebuild script invocation graph`:

```yaml
- name: Undeclared-import gate tests
  run: uv run pytest scripts/tests/test_check_undeclared_imports.py -v --tb=short

- name: Undeclared-import gate (scripts/ and Python test trees)
  run: uv run python scripts/check_undeclared_imports.py
```

Deliberately placed after `Install dependencies` (`uv sync --all-packages`)
so `find_spec` resolution reflects the same environment the rest of the
job runs under -- see "Why no soft launch" above for why this step carries
no `continue-on-error`. Path filters added to both `push` and
`pull_request` triggers for `scripts/check_undeclared_imports.py`,
`scripts/tests/test_check_undeclared_imports.py`, and
`.undeclared-imports-allowlist`.

**Exit-code contract**, mirroring the repo's other gates:

- `0` -- clean (no undeclared imports, no tool errors).
- `3` -- at least one undeclared import found and not allowlisted.
- `5` -- tool error (missing scan root, zero files, unparseable file,
  malformed/unscoped allowlist entry, or the vacuous-run backstop). Never
  soft-launched, never conflated with "0 violations".

Also registered in `scripts/manifest.yaml` (the manifest gate is blocking,
not `continue-on-error`).

---

## Verification summary

- `uv run python scripts/check_undeclared_imports.py` against the real,
  current repo: **clean**, exit 0 (627 files, 3030 module-level imports
  checked, 2 precisely-scoped allowlist entries exercised, 0 tool errors,
  0 violations).
- Mutation tests: removing jinja2's declaration and re-syncing produces
  exit 3 naming `scripts/gen_domain_models.py:21`; removing sympy's
  declaration and re-syncing produces exit 3 naming
  `packages/temper-placer/tests/physics/test_thermal_fdm_mms.py:30`. Both
  restored afterward; `git diff --stat pyproject.toml` confirmed clean
  before finishing.
- `uv run pytest scripts/tests/test_check_undeclared_imports.py`: 27
  passed.
- `uv run ruff check scripts/check_undeclared_imports.py
  scripts/tests/test_check_undeclared_imports.py`: clean.
- `actionlint .github/workflows/python-tests.yml`: same five pre-existing
  shellcheck findings at the (now shifted) "Run extended test suites in
  parallel" step, confirmed identical before and after this change via
  `git stash`; zero new findings from this change.
- `uv run python scripts/check_manifest_gate.py`: fails, but on a
  **pre-existing**, unrelated gap -- `scripts/resync_pcb_netlist.py` (added
  in commit `32cc972f`, already on this branch before this task started)
  has no manifest entry. Confirmed via `git show HEAD:scripts/manifest.yaml`
  before this task's changes. Not fixed here, per "touch only what this
  task needs" -- this task's own new script (`check_undeclared_imports.py`)
  has a correct manifest entry and introduces no new manifest violation.

## Explicitly out of scope / not attempted

- Extending scan scope to `packages/*/src` (see "Why `packages/*/src` is
  out of scope" above) -- needs an owner decision on the `jax` gap there
  and a per-package mechanism for the `tests.` shim pattern.
- Fixing `scripts/resync_pcb_netlist.py`'s missing manifest entry --
  pre-existing, unrelated to this task.
- Declaring `jax` as a real dependency, or deciding whether
  `scripts/check_perf_regression.py`/`scripts/internal_route.py` are still
  needed -- an owner decision, tracked via the two allowlist entries.
