#!/usr/bin/env python3
"""Anti-vacuous-truth gate: reject unguarded ``all(...)`` in gate and
validator modules.

``all()`` over an empty collection is vacuously ``True`` in Python -- a
verification function that aggregates per-item results with a bare
``all(...)`` therefore reports a clean verdict for input it never
actually measured -- see docs/METHODOLOGY.md Sec 4 ("vacuous", failure
class 4) and Sec 5 ("Anti-vacuous-truth"): *"Every ``all()`` in a
checker requires a non-empty assertion in front of it."*  This gate is
the mechanical form of that rule.

``any()`` is deliberately **not** flagged: ``any()`` over an empty
collection returns ``False`` in Python, which is already the desired
fail-closed behavior for a gate -- "nothing evaluated" correctly reads
as "not passing." Flagging ``any()`` would fire on correct code, which
is itself a defect in a checker (METHODOLOGY Sec 5, specificity: a
check that fires on correct code is a defect).

Scope
-----
**2026-07-27 rewrite** (see docs/evidence/2026-07-27-gate-subset-blindness-audit.md):
the previous scope was an *include-list* keyed on ``SCOPE_TOKENS = ("gate",
"valid")`` matched against the repo-relative path substring, restricted to
``packages/*/src``. Measured against the real validator surface it covered
2 of 13 known validator modules -- worse, it structurally could not see
``scripts/*.py`` at all (``find_scope_files`` only globbed
``packages/*/src``), so every one of the CI gate scripts audited alongside
this one (``check_domain_partition.py``, ``capacity_budget_gate.py``,
``mpn_fabrication_gate.py``, ``check_derived_doc_drift.py``, this file
itself, ...) was never scanned regardless of filename. A path substring is
also both too broad (a directory named ``validation/`` sweeps in
unrelated modules) and too narrow (``domain_clearance.py``,
``drc_runner.py`` under ``deterministic/feedback/`` have neither token
anywhere in their path).

The scope is now a **default-include, narrow documented-exclude** union of:

1. Every ``.py`` file under ``packages/*/src`` (recursive), except the
   ``router_v6`` package -- excluded per the forced-segment fail-closed
   plan (``docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-plan.md``);
   see that plan's current status before assuming this exclusion still
   applies (UNVERIFIED as of this rewrite -- a concurrent agent is
   actively working router_v6 code and this gate does not touch it).
2. Every ``.py`` file under ``packages/*/tests`` (recursive) EXCEPT actual
   test modules, matched by filename convention (``test_*.py``,
   ``*_test.py``, ``conftest.py``) rather than by path substring -- the
   previous ``"/tests/"`` substring exclusion silently dropped real
   validator *implementation* modules that happen to live under a
   ``tests/requirements/validators/`` tree (``isolation.py``,
   ``emi_filter.py``, ``ground_plane.py``, ``pick_and_place.py``,
   ``routability_check.py``, ``clearance_check.py``) even though they are
   not test files themselves. Same ``router_v6`` exclusion applies.
3. Every top-level ``.py`` file directly under ``scripts/`` (non-recursive
   -- this naturally excludes ``scripts/_lib/``, ``scripts/tests/``,
   ``scripts/spikes/``, ``scripts/templates/`` without a separate rule).

Rationale for "default-include, narrow exclude" over an allowlist: an
allowlist (of files, or of filename tokens) requires a maintainer to
remember to add every new gate/validator module to it -- exactly the
mechanism that produced the 2-of-13 blind spot in the first place. A
denylist only has to name known non-validator conventions (test files);
a new validator module added anywhere in scope is scanned automatically,
with no action required and no PR-invisible omission possible.

This is not free: the packages/*/tests union pulls in some fixture and
helper modules that are not "validators" in spirit (Hypothesis strategy
builders, golden-data generators). That is an accepted false-inclusion
cost -- the detector below only flags unguarded ``all()`` calls, so a
non-gate module with no such call produces no output either way. The
asymmetry matters: false-inclusion costs nothing when there is nothing to
flag; false-exclusion is silent forever.

Detection
---------
For every ``all(...)`` call, the gate resolves the source collection
being iterated (the comprehension's ``.iter``, or the bare call
argument) and considers the call **guarded** -- and therefore OK -- if
either:

1. an earlier statement in the same function/module (`if not <expr>:`,
   `assert <expr>`, or `assert len(<expr>)`) asserts the collection is
   non-empty before the call, or
2. the comprehension's predicate/element itself performs a per-item
   ``is None`` / ``is not None`` check -- i.e. it already treats a
   missing/unmeasured item as failing rather than passing it through.

This is a syntactic heuristic, not a prover: it is deliberately
conservative (favors false negatives over false positives) so it stays
usable as a hard CI gate rather than a noisy advisory one.

This gate asserts zero unguarded calls directly -- there is no
allowlist. Once a gate/validator module ships with an unguarded
``all()``, fix it; don't accumulate an exception file (see commit
df862924, which collapsed ``import-linter-baseline.yaml`` the same way
once it reached zero).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import ast
import re

from rich.console import Console

console = Console()

# Only all() is vacuous. any() over an empty collection is already
# fail-closed (returns False) -- see module docstring.
AGGREGATORS = {"all"}

# Package excluded from scope entirely (see module docstring: frozen per
# the forced-segment fail-closed plan; UNVERIFIED whether still current).
EXCLUDED_PACKAGE = "router_v6"

# Filename conventions that mark a file as an actual test module rather
# than a validator/gate implementation -- matched on the filename only,
# never on path substring (see module docstring for why "/tests/" as a
# path substring is wrong: it drops real validator implementations that
# happen to live under a tests/requirements/validators/ tree).
_TEST_FILENAME_RE = re.compile(r"^(test_.*|.*_test|conftest)\.py$")

_GUARD_RE_TEMPLATES = [
    r"if\s+not\s+{expr}\b",
    r"assert\s+{expr}\b",
    r"assert\s+len\(\s*{expr}\s*\)",
    r"if\s+len\(\s*{expr}\s*\)\s*==\s*0",
]

_STRIP_SUFFIX_RE = re.compile(r"\.(values|keys|items)\(\)$")


# ---------------------------------------------------------------------------
# scope
# ---------------------------------------------------------------------------


def _is_router_v6(rel_path: str) -> bool:
    """True when *rel_path* falls under the excluded router_v6 package."""
    parts = rel_path.split("/")
    return EXCLUDED_PACKAGE in parts


def find_packages_scope_files(packages_dir: Path) -> list[Path]:
    """Return every in-scope ``.py`` file under ``packages/*/src`` and
    ``packages/*/tests`` (see module docstring for the exclusion rules)."""
    results: list[Path] = []
    for src_dir in sorted(packages_dir.glob("*/src")):
        for py_file in sorted(src_dir.rglob("*.py")):
            rel = py_file.relative_to(packages_dir.parent).as_posix()
            if _is_router_v6(rel):
                continue
            results.append(py_file)
    for tests_dir in sorted(packages_dir.glob("*/tests")):
        for py_file in sorted(tests_dir.rglob("*.py")):
            rel = py_file.relative_to(packages_dir.parent).as_posix()
            if _is_router_v6(rel):
                continue
            if _TEST_FILENAME_RE.match(py_file.name):
                continue
            results.append(py_file)
    return results


def find_scripts_scope_files(scripts_dir: Path) -> list[Path]:
    """Return every top-level ``.py`` file directly under ``scripts/``.

    Non-recursive by construction: this naturally excludes ``_lib/``,
    ``tests/``, ``spikes/``, and ``templates/`` subdirectories without a
    separate exclusion rule.
    """
    if not scripts_dir.is_dir():
        return []
    return sorted(
        f for f in scripts_dir.glob("*.py") if f.is_file() and f.name != "__init__.py"
    )


def find_scope_files(packages_dir: Path, scripts_dir: Path | None = None) -> list[Path]:
    """Return every in-scope ``.py`` file (packages + top-level scripts/)."""
    results = find_packages_scope_files(packages_dir)
    if scripts_dir is not None:
        results.extend(find_scripts_scope_files(scripts_dir))
    return results


# ---------------------------------------------------------------------------
# detection
# ---------------------------------------------------------------------------


def _root_node(call: ast.Call) -> ast.AST | None:
    """Return the AST node for the collection an all() call iterates."""
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, (ast.GeneratorExp, ast.ListComp, ast.SetComp)) and arg.generators:
        return arg.generators[0].iter
    return arg


def _is_literal_source(node: ast.AST | None) -> bool:
    """True when the iterated collection is a non-empty literal.

    ``all(x in name for x in ["a", "b"])``-style keyword matching over a
    fixed literal written at the call site can never be "unmeasured" --
    the cardinality is baked into the source, not into runtime input.
    That is a different concern from the vacuity this gate targets, so
    such calls are out of scope.
    """
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return len(node.elts) > 0
    return False


def _root_expr(call: ast.Call) -> tuple[str, bool]:
    """Return ``(root_source, is_comprehension)`` for an all() call.

    ``root_source`` is the unparsed source of the collection being
    iterated (comprehension ``.iter``, or the bare call argument).
    """
    node = _root_node(call)
    if node is None:
        return "", False
    arg = call.args[0]
    is_comp = isinstance(arg, (ast.GeneratorExp, ast.ListComp, ast.SetComp)) and bool(
        arg.generators
    )
    return _STRIP_SUFFIX_RE.sub("", ast.unparse(node)), is_comp


def _inline_none_guarded(call: ast.Call) -> bool:
    """True if the comprehension already performs a per-item None check."""
    if not call.args:
        return False
    arg = call.args[0]
    if not isinstance(arg, (ast.GeneratorExp, ast.ListComp, ast.SetComp)):
        return False
    pieces = [ast.unparse(arg.elt)]
    pieces.extend(ast.unparse(cond) for gen in arg.generators for cond in gen.ifs)
    text = " ".join(pieces)
    return bool(re.search(r"\bis\s+(not\s+)?None\b", text))


def _preceding_guard(
    scope_source_lines: list[str],
    start_line: int,
    end_line: int,
    root: str,
) -> bool:
    """True if any line in ``[start_line, end_line)`` guards *root*."""
    if not root:
        return False
    patterns = [
        re.compile(t.format(expr=re.escape(root))) for t in _GUARD_RE_TEMPLATES
    ]
    for lineno in range(start_line, end_line):
        if lineno < 1 or lineno > len(scope_source_lines):
            continue
        line = scope_source_lines[lineno - 1]
        if any(p.search(line) for p in patterns):
            return True
    return False


def _sibling_guard(enclosing_stmt: ast.stmt | None, root: str) -> bool:
    """True if *root* is guarded elsewhere in the same statement.

    Catches ``return all(...) and bool(items)``-shaped expressions where
    the non-empty check sits beside the aggregation rather than on a
    preceding line.
    """
    if not root or enclosing_stmt is None:
        return False
    text = ast.unparse(enclosing_stmt)
    return bool(re.search(rf"not\s+{re.escape(root)}\b", text))


def find_violations(py_file: Path) -> list[tuple[int, str]]:
    """Return ``[(lineno, snippet), ...]`` of unguarded all() calls."""
    try:
        source = py_file.read_text()
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError:
        console.print(f"[yellow]WARNING: syntax error in {py_file}, skipping[/]")
        return []

    lines = source.splitlines()
    violations: list[tuple[int, str]] = []

    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent

    def enclosing_scope_start(node: ast.AST) -> int:
        cur = node
        while cur in parents:
            cur = parents[cur]
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return cur.lineno
        return 1

    def enclosing_stmt(node: ast.AST) -> ast.stmt | None:
        cur = node
        while cur in parents:
            cur = parents[cur]
            if isinstance(cur, ast.stmt):
                return cur
        return None

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        if node.func.id not in AGGREGATORS:
            continue

        if _is_literal_source(_root_node(node)):
            continue

        if _inline_none_guarded(node):
            continue

        root, _is_comp = _root_expr(node)
        scope_start = enclosing_scope_start(node)
        if _preceding_guard(lines, scope_start, node.lineno, root):
            continue
        if _sibling_guard(enclosing_stmt(node), root):
            continue

        snippet = lines[node.lineno - 1].strip() if node.lineno <= len(lines) else ""
        violations.append((node.lineno, snippet))

    return violations


def _rel_str(py_file: Path, repo_root: Path) -> str:
    try:
        return py_file.relative_to(repo_root).as_posix()
    except ValueError:
        return py_file.as_posix()


def find_all_violations(
    packages_dir: Path, scripts_dir: Path | None, repo_root: Path
) -> tuple[dict[str, tuple[int, str]], int]:
    """Scan every in-scope file.

    Returns ``({key: (lineno, snippet)}, files_scanned)`` -- the second
    element is the denominator this gate must report on both pass and
    fail (see docs/evidence/2026-07-27-gate-subset-blindness-audit.md:
    a gate reporting "0 violations" without also reporting how many
    files it looked at cannot be distinguished from a gate that scanned
    nothing).
    """
    results: dict[str, tuple[int, str]] = {}
    scope_files = find_scope_files(packages_dir, scripts_dir)
    for py_file in scope_files:
        rel = _rel_str(py_file, repo_root)
        for lineno, snippet in find_violations(py_file):
            results[f"{rel}:{lineno}"] = (lineno, snippet)
    return results, len(scope_files)


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Anti-vacuous-truth gate: require a non-empty guard"
        " (or per-item None check) in front of every all() in gate and"
        " validator modules"
    )
    parser.add_argument(
        "--packages-dir",
        type=Path,
        default="packages",
        help="Path to the packages/ directory (default: packages)",
    )
    parser.add_argument(
        "--scripts-dir",
        type=Path,
        default="scripts",
        help="Path to the top-level scripts/ directory (default: scripts)."
        " Pass a nonexistent path to disable this half of the scan"
        " (used by falsifier tests) -- find_scripts_scope_files returns"
        " an empty list for a non-directory rather than erroring.",
    )

    args = parser.parse_args()

    packages_dir = args.packages_dir
    if not packages_dir.is_absolute():
        packages_dir = Path.cwd() / packages_dir

    scripts_dir = args.scripts_dir
    if not scripts_dir.is_absolute():
        scripts_dir = Path.cwd() / scripts_dir

    if not packages_dir.is_dir():
        console.print(f"[red]Packages directory not found: {packages_dir}[/]")
        sys.exit(1)

    repo_root = packages_dir.parent
    violations, files_scanned = find_all_violations(packages_dir, scripts_dir, repo_root)

    denominator = (
        f"Scanned {files_scanned} file(s) in scope"
        f" ({packages_dir}/*/src + */tests, {scripts_dir or '<disabled>'}/*.py)."
    )

    if files_scanned == 0:
        console.print(
            f"[red]FAIL (closed): {denominator} An anti-vacuous-truth gate that"
            f" scans zero files cannot report a meaningful pass -- this is"
            f" exactly the failure mode this gate exists to catch. Check"
            f" --packages-dir/--scripts-dir.[/]"
        )
        sys.exit(1)

    if violations:
        for key in sorted(violations):
            lineno, snippet = violations[key]
            console.print(
                f"[red]FAIL: {key} — unguarded aggregation: {snippet!r}."
                f" all() over an empty collection is vacuously True;"
                f" assert non-empty (or a per-item None check) before"
                f" aggregating.[/]"
            )
        console.print(f"[red]{denominator} {len(violations)} violation(s).[/]")
        sys.exit(1)

    console.print(f"[green]Anti-vacuous-truth gate passed. {denominator} 0 violations.[/]")


if __name__ == "__main__":
    main()
