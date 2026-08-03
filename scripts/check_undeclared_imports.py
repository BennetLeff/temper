#!/usr/bin/env python3
"""Undeclared third-party import CI gate.

Motivating incidents (2026-07-26, both found the same day, both invisible
for the same structural reason -- the CI step that would have caught them
carries ``continue-on-error: true``):

1. ``jinja2`` -- imported top-level by ``scripts/gen_domain_models.py`` but
   declared nowhere (not in any ``pyproject.toml``, not in ``uv.lock``, not
   installed anywhere). The "Check domain model codegen drift" step died on
   ``ModuleNotFoundError`` on *every* run; that gate had never executed
   once.
2. ``sympy`` -- imported top-level by
   ``packages/temper-placer/tests/physics/test_thermal_fdm_mms.py``,
   equally undeclared. That test is the Method of Manufactured Solutions
   2nd-order convergence proof for the thermal FDM solver -- one of the
   strongest correctness claims in the repo -- and it had never been
   collected: it failed at import inside a ``continue-on-error`` step.

Both are now declared in ``pyproject.toml``'s ``[dependency-groups] dev``.
This gate exists so the *next* undeclared import dies loudly in a blocking
CI step instead of silently inside a soft one.

Design: resolvability, not string-matching against dependency lists
---------------------------------------------------------------------
A module's PyPI distribution name is frequently not its import name
(``jinja2`` ships as ``Jinja2``; ``yaml`` as ``PyYAML``; ``sklearn`` as
``scikit-learn``). Comparing imported names against parsed
``pyproject.toml``/``uv.lock`` dependency lists would need a private,
constantly-drifting import-name -> distribution-name table and would still
be wrong for a scenario like "declared in one workspace member's
``pyproject.toml`` but pruned by a plain ``uv sync``" (this workspace's own
``pyyaml`` situation: declared only in ``temper-placer``/``temper-workflow``
and removed by a bare ``uv sync`` without ``--all-packages``). Instead,
this gate asks the only question that actually matters: **is this module
resolvable in the interpreter that is about to run the test suite?**
That is answered directly with ``importlib.util.find_spec`` -- no
dependency-list parsing, no distribution-name table to keep in sync.

This is why the gate step in CI must run under ``uv run`` **after**
``uv sync --all-packages`` (never a plain ``uv sync``, which prunes
workspace packages -- see the pyyaml note above) and after the Rust
extensions (``temper_rust_router`` etc.) are ``maturin develop``-installed:
those are guarded, function-scoped imports in production code (see
"Scope" below) so they never reach this gate's scan, but placing the step
early would still be fragile for any future top-level import of one.

Scope: which imports are scanned
---------------------------------
Only **module-level** imports (direct children of ``ast.Module.body``) are
scanned -- deliberately, mirroring ``scripts/trace_invocations.py``'s own
``extract_imports``. A full ``ast.walk`` would also catch imports nested
inside functions, ``try/except ImportError`` blocks, and
``if TYPE_CHECKING:`` guards -- all of which are *legitimately optional* in
this repo:

  - ``scripts/kicad_fill_zones.py`` imports ``pcbnew`` inside ``main()``,
    guarded by its own ``try/except ImportError`` with a message explaining
    it must run under a *different* (system) interpreter than ``uv run``.
    A top-level scan would never see it; that is correct; it is not
    supposed to be resolvable under ``uv run``.
  - Several ``packages/temper-placer/src`` modules (``loop_extractor_rs.py``,
    ``pcl/rust_bridge.py``, ``validation/drc_oracle.py``, ...) import Rust
    extensions (``temper_rust_router``, ``temper_constraints``,
    ``temper_drc_rs``) inside functions/try-blocks specifically so the pure-
    Python fallback path works when the extension hasn't been built.

Scanning only ``tree.body`` excludes both classes by construction --
neither is a compound statement's direct child of the module -- with no
special-casing needed. Relative imports (``from . import x``,
``from .foo import y``) are also skipped: they are intra-package by
definition, never third-party.

Scope: which directories
--------------------------
``scripts/`` (top-level + ``scripts/_lib/``), ``scripts/tests/``,
``packages/temper-placer/tests/``, ``packages/temper-workflow/tests/``,
and ``elec/validation/`` -- these are exactly the trees the two motivating
defects live in (a codegen script, a physics test) plus the sibling test
trees that share the same "undeclared third-party import -> dead gate"
failure mode.

``packages/*/src`` is deliberately **not** scanned in this pass. A survey
using this gate's own mechanism (top-level scan + ``find_spec`` against a
freshly ``uv sync --all-packages``'d environment) surfaced two live,
pre-existing findings there that are a different problem, not this one:

  - ``packages/temper-workflow/src/temper_workflow/metrics/
    aesthetic_turing_test.py`` imports ``jax.numpy`` top-level; ``jax`` is
    not declared/installed anywhere reachable from this workspace. This
    needs an owner decision (declare it, or the module is dead/broken),
    like the four already-broken test modules this task was told not to
    fix.
  - ``packages/temper-placer/src/temper_placer/placer/cp_sat/
    domain_clearance.py`` line 132 imports
    ``from tests.requirements.validators.clearance import ...`` -- a
    deliberate, documented shim where production code reuses its own
    package's test tree via manual ``sys.path`` insertion. This is
    first-party, not third-party, but is invisible to a bare
    ``find_spec`` without reproducing that shim's ``sys.path`` surgery,
    which would need per-package special-casing this pass does not build.

Extending scope to ``packages/*/src`` is a reasonable follow-up but would
require resolving both findings above first (an owner decision on ``jax``,
and either a per-package local-root mechanism or an allowlist entry for
the ``tests.`` shim) -- exactly the kind of unrelated scope decision this
task's own instructions say not to make unilaterally. Both findings are
reported in docs/evidence/2026-07-27-undeclared-import-gate.md rather than
silently fixed or silently ignored.

Not redundant with ``scripts/import_linter_gate.py``: import-linter
enforces *architectural boundary contracts* between first-party modules
that are already installed and resolvable (e.g. "``tools/`` may not import
``temper_placer`` internals"). This gate asks a different, prior question:
*is the imported module resolvable in the environment at all* -- it fires
on third-party packages that were never installed in the first place,
which import-linter's contract model has no notion of (it would either
skip an unresolvable module silently or crash, per its own tool_error
path).

Local ("first-party") modules
-------------------------------
A bare name like ``_lib`` (``scripts/_lib/``) or ``capacity_budget_gate``
(imported by ``scripts/tests/test_capacity_budget_gate.py`` via that
file's own ``sys.path.insert``) is a local, uninstalled sibling module --
not a PyPI package, so ``find_spec`` run from an unrelated cwd would not
find it either. Before falling back to ``find_spec``, this gate checks
whether ``<name>.py`` or ``<name>/__init__.py`` exists in the importing
file's own directory or in one of that scan target's configured
``local_roots`` (mirroring each tree's own ``sys.path``/pytest
``pythonpath`` conventions -- see ``build_scan_targets``). Workspace
packages themselves (``temper_placer``, ``temper_geometry``, ...) need no
such special-casing: ``uv sync --all-packages`` installs them editable, so
``find_spec`` finds them directly, same as any third-party dependency.

Exit codes (mirrors scripts/import_linter_gate.py, scripts/capacity_budget_gate.py):
  0 - clean: every module-level import in every scanned file is stdlib,
      a local sibling module, resolvable via ``importlib.util.find_spec``
      in the current interpreter, or matched by a justified, precisely
      scoped allowlist entry.
  3 - undeclared: at least one module-level import in first-party code is
      not resolvable and not allowlisted.
  5 - tool_error: a configured scan root is missing, zero files were found
      to inspect, a file could not be parsed, an allowlist entry has no
      justification comment (or no file-scope), or the run somehow
      inspected zero import statements across every parsed file
      (vacuous-run backstop). Never conflated with "0 violations".

No soft launch / CUTOVER_DATE. Unlike scripts/import_linter_gate.py and
scripts/check_derived_doc_drift.py, this gate has no bring-up period: a
*global*, time-boxed grace window (their pattern) would also silently
pass a brand-new undeclared import introduced anywhere during that
window -- including a hypothetical re-introduction of the exact jinja2/
sympy defect this gate exists to catch. That would defeat the point on
day one. Instead, the one real, pre-existing finding this gate's own
mechanism surfaced while it was being built -- ``jax``, imported
top-level and undeclared in ``scripts/check_perf_regression.py`` (run via
``uv run`` from ``make perf-regression``, itself already
``continue-on-error: true``) and ``scripts/internal_route.py`` (run via
``make route``); declared in no ``pyproject.toml`` and not imported
anywhere in ``packages/temper-placer/src`` either, so not a transitive
dependency of production code -- is exempted precisely, by two
``module::file-glob`` allowlist entries (see "Allowlist" below), not by a
blanket time window. Everything else, including those same two files
gaining a *second* undeclared import, is hard-blocking immediately. See
docs/evidence/2026-07-27-undeclared-import-gate.md.

Allowlist
---------
``.undeclared-imports-allowlist`` entries are ``module::file-glob  #
justification``, e.g. ``jax::scripts/check_perf_regression.py  # ...``.
Both the module name and the file glob must match for an entry to apply
-- a bare module name is deliberately not supported, so allowlisting the
known ``jax`` gap in these two specific scripts cannot silently exempt an
unrelated future ``jax`` import somewhere else in the scanned trees.
Every entry requires a ``#`` justification (unjustified entries are a
hard error -- fail closed, per the brief's "require a justification per
entry and make unjustified entries an error").

Usage:
  uv run python scripts/check_undeclared_imports.py [--help]
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

STDLIB = frozenset(sys.stdlib_module_names)

DEFAULT_ALLOWLIST_NAME = ".undeclared-imports-allowlist"


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Scan targets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScanTarget:
    label: str
    root: Path  # directory that must exist
    pattern: str  # glob pattern relative to root (e.g. "*.py", "**/*.py")
    local_roots: tuple[Path, ...]  # additional roots searched for local sibling modules


def build_scan_targets(repo_root: Path) -> list[ScanTarget]:
    scripts_dir = repo_root / "scripts"
    placer = repo_root / "packages" / "temper-placer"
    workflow = repo_root / "packages" / "temper-workflow"
    elec_validation = repo_root / "elec" / "validation"
    # firmware/tools is a local_roots sibling for scripts/*.py because two
    # gates share the derivation library there: check_pll_range_consistency.py
    # and check_firmware_board_contract.py both sys.path-insert
    # firmware/tools at import time (plan 2026-08-02-027, KTD3 -- one
    # formula implementation, two checks). Those modules are first-party
    # repo code, not undeclared third-party dependencies.
    fw_tools = repo_root / "firmware" / "tools"
    return [
        ScanTarget(
            "scripts/*.py (top-level)",
            scripts_dir,
            "*.py",
            (scripts_dir, fw_tools),
        ),
        ScanTarget("scripts/_lib/*.py", scripts_dir / "_lib", "*.py", (scripts_dir,)),
        ScanTarget(
            "scripts/tests/**/*.py",
            scripts_dir / "tests",
            "**/*.py",
            (scripts_dir, scripts_dir / "tests", fw_tools),
        ),
        ScanTarget(
            "packages/temper-placer/tests/**/*.py",
            placer / "tests",
            "**/*.py",
            (placer / "src", placer),
        ),
        ScanTarget(
            "packages/temper-workflow/tests/**/*.py",
            workflow / "tests",
            "**/*.py",
            (workflow / "src", workflow),
        ),
        ScanTarget(
            "elec/validation/**/*.py",
            elec_validation,
            "**/*.py",
            (elec_validation,),
        ),
    ]


# ---------------------------------------------------------------------------
# AST extraction -- module-level (tree.body) imports only. See module
# docstring "Scope: which imports are scanned" for why this is deliberate.
# ---------------------------------------------------------------------------


@dataclass
class ImportRef:
    module: str
    lineno: int


def extract_module_level_imports(source: str) -> list[ImportRef]:
    """Parse *source* and return every module-level import's top-level
    module name (``os.path`` -> ``os``) and line number.

    Only ``import X`` / ``from X import Y`` statements that are direct
    children of the module body are returned -- imports nested inside a
    function, ``try``/``except``, or ``if`` block are deliberately
    excluded (guarded/optional imports; see module docstring). Relative
    imports (``from . import x``) are also excluded -- always intra-package.

    Raises :class:`SyntaxError` if *source* cannot be parsed (propagated to
    the caller so it can be recorded as a tool error, never silently
    skipped).
    """
    tree = ast.parse(source)
    out: list[ImportRef] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append(ImportRef(alias.name.split(".")[0], node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue  # relative import -- always intra-package
            if node.module:
                out.append(ImportRef(node.module.split(".")[0], node.lineno))
    return out


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def is_local_module(name: str, file_path: Path, local_roots: tuple[Path, ...]) -> bool:
    """True if *name* resolves to an uninstalled sibling module/package --
    a ``.py`` file or a package directory with ``__init__.py`` -- reachable
    from the importing file's own directory or one of *local_roots*.
    """
    search_dirs = [file_path.parent, *local_roots]
    seen: set[Path] = set()
    for d in search_dirs:
        d = d.resolve()
        if d in seen:
            continue
        seen.add(d)
        if (d / f"{name}.py").is_file():
            return True
        if (d / name / "__init__.py").is_file():
            return True
    return False


def is_resolvable_in_environment(name: str) -> bool:
    """True if ``importlib.util.find_spec`` locates *name* in the current
    interpreter. Locating (not importing) is deliberate: this must not
    execute third-party module top-level code as a side effect of running
    a CI gate, and a module that would raise on import but can still be
    located is not this gate's problem to diagnose.
    """
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError, AttributeError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Allowlist
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AllowlistEntry:
    module: str
    file_glob: str
    justification: str


def load_allowlist(path: Path) -> list[AllowlistEntry]:
    """Return the parsed allowlist. Missing file -> empty list (no
    allowlist is a valid, common state, not an error).

    Each non-comment, non-blank line must be
    ``module::file-glob  # justification``. A line missing the ``::``
    file-scope separator, missing a ``#`` justification, or with an empty
    module/glob/justification is a hard error (fail closed) rather than a
    silently-accepted (or silently over-broad) exemption.
    """
    if not path.is_file():
        return []
    entries: list[AllowlistEntry] = []
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "#" not in stripped:
            raise GateError(
                f"{path}:{lineno}: allowlist entry {stripped!r} has no "
                "'# justification' comment -- unjustified entries are not allowed"
            )
        key_part, justification = stripped.split("#", 1)
        justification = justification.strip()
        if not justification:
            raise GateError(
                f"{path}:{lineno}: allowlist entry {key_part.strip()!r} has an "
                "empty justification comment"
            )
        key_part = key_part.strip()
        if "::" not in key_part:
            raise GateError(
                f"{path}:{lineno}: allowlist entry {key_part!r} is missing the "
                "'module::file-glob' separator -- a bare module name would "
                "exempt every file, which this gate does not allow"
            )
        module, file_glob = key_part.split("::", 1)
        module = module.strip()
        file_glob = file_glob.strip()
        if not module:
            raise GateError(f"{path}:{lineno}: allowlist entry has no module name")
        if not file_glob:
            raise GateError(
                f"{path}:{lineno}: allowlist entry for {module!r} has no file glob"
            )
        entries.append(AllowlistEntry(module, file_glob, justification))
    return entries


def matches_allowlist(module: str, file_rel: str, entries: list[AllowlistEntry]) -> bool:
    return any(
        e.module == module and fnmatch.fnmatch(file_rel, e.file_glob) for e in entries
    )


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass
class ToolError:
    where: str
    reason: str


@dataclass
class Violation:
    file: str
    module: str
    lineno: int


@dataclass
class Report:
    tool_errors: list[ToolError] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    targets_inspected: list[str] = field(default_factory=list)
    files_inspected: int = 0
    import_statements_seen: int = 0
    stdlib_count: int = 0
    local_count: int = 0
    allowlisted_count: int = 0
    resolved_count: int = 0


def run(
    repo_root: Path,
    allowlist_path: Path,
    scan_targets: list[ScanTarget] | None = None,
) -> tuple[str, Report]:
    """Returns (state, report) where state is 'clean' | 'undeclared' | 'tool_error'."""
    report = Report()
    targets = scan_targets if scan_targets is not None else build_scan_targets(repo_root)

    try:
        allowlist = load_allowlist(allowlist_path)
    except GateError as e:
        report.tool_errors.append(ToolError(str(allowlist_path), str(e)))
        return "tool_error", report

    if not targets:
        report.tool_errors.append(ToolError("<config>", "zero scan targets configured"))
        return "tool_error", report

    all_files: list[tuple[Path, tuple[Path, ...]]] = []
    for target in targets:
        report.targets_inspected.append(target.label)
        if not target.root.is_dir():
            report.tool_errors.append(
                ToolError(target.label, f"scan root does not exist: {target.root}")
            )
            continue
        files = sorted(target.root.glob(target.pattern))
        files = [f for f in files if f.is_file() and "__pycache__" not in f.parts]
        for f in files:
            all_files.append((f, target.local_roots))

    if not all_files:
        report.tool_errors.append(
            ToolError(
                "<run>",
                "zero files found to inspect across all scan targets -- "
                "scan misconfigured or every scan root is empty",
            )
        )
        return "tool_error", report

    report.files_inspected = len(all_files)

    for file_path, local_roots in all_files:
        rel = str(file_path.relative_to(repo_root))
        try:
            source = file_path.read_text()
        except (OSError, UnicodeDecodeError) as e:
            report.tool_errors.append(ToolError(rel, f"could not read file: {e}"))
            continue
        try:
            imports = extract_module_level_imports(source)
        except SyntaxError as e:
            report.tool_errors.append(ToolError(rel, f"could not parse file: {e}"))
            continue

        for ref in imports:
            report.import_statements_seen += 1
            name = ref.module
            if name in STDLIB:
                report.stdlib_count += 1
                continue
            if matches_allowlist(name, rel, allowlist):
                report.allowlisted_count += 1
                continue
            if is_local_module(name, file_path, local_roots):
                report.local_count += 1
                continue
            if is_resolvable_in_environment(name):
                report.resolved_count += 1
                continue
            report.violations.append(Violation(file=rel, module=name, lineno=ref.lineno))

    # Anti-vacuity backstop: every scanned file had zero top-level import
    # statements at all is suspicious enough (across the whole run) that a
    # silent "clean" would be indistinguishable from a scanning bug -- see
    # scripts/check_derived_doc_drift.py's identical-in-spirit backstop.
    if report.import_statements_seen == 0 and not report.tool_errors:
        report.tool_errors.append(
            ToolError(
                "<run>",
                f"0 import statements found across {report.files_inspected} "
                "file(s) -- vacuous run, not a clean pass",
            )
        )

    if report.tool_errors:
        return "tool_error", report
    if report.violations:
        return "undeclared", report
    return "clean", report


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _print_report(state: str, report: Report) -> None:
    print(
        f"Undeclared-import gate -- {len(report.targets_inspected)} scan target(s), "
        f"{report.files_inspected} file(s), {report.import_statements_seen} "
        f"module-level import(s) checked"
    )
    for t in report.targets_inspected:
        print(f"  - {t}")
    print(
        f"  stdlib: {report.stdlib_count}  local: {report.local_count}  "
        f"allowlisted: {report.allowlisted_count}  resolved: {report.resolved_count}"
    )

    if report.tool_errors:
        print(f"{len(report.tool_errors)} TOOL ERROR(S)")
        for e in report.tool_errors:
            print(f"  TOOL_ERROR {e.where}: {e.reason}")

    if report.violations:
        print(f"{len(report.violations)} UNDECLARED IMPORT(S)")
        for v in report.violations:
            print(
                f"  UNDECLARED {v.file}:{v.lineno} -- module '{v.module}' is imported "
                "at module level but is not resolvable in the synced environment "
                "(not stdlib, not a local module, not installed). Declare it in "
                "pyproject.toml's [dependency-groups] dev (or the relevant "
                f"package's pyproject.toml), or add a justified entry to "
                f"{DEFAULT_ALLOWLIST_NAME} if it is intentionally optional."
            )

    if state == "clean":
        print("Undeclared-import gate passed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=None,
        help=f"Path to allowlist (default: repo_root/{DEFAULT_ALLOWLIST_NAME})",
    )
    args = parser.parse_args()

    repo_root = find_repo_root()
    allowlist_path = args.allowlist or (repo_root / DEFAULT_ALLOWLIST_NAME)

    state, report = run(repo_root, allowlist_path)
    _print_report(state, report)

    summary_path = get_github_summary_path()
    if summary_path:
        with open(summary_path, "a") as f:
            f.write(f"\n### Undeclared-import gate: {state}\n")
            f.write(
                f"- Scan targets: {len(report.targets_inspected)}\n"
                f"- Files inspected: {report.files_inspected}\n"
                f"- Import statements checked: {report.import_statements_seen}\n"
                f"- Tool errors: {len(report.tool_errors)}\n"
                f"- Undeclared imports: {len(report.violations)}\n"
            )

    if state == "tool_error":
        sys.exit(5)
    if state == "undeclared":
        sys.exit(3)
    sys.exit(0)


if __name__ == "__main__":
    main()
