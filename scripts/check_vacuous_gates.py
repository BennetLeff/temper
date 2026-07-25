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
Only files that look like gates/validators are scanned: any ``.py`` file
under ``packages/*/src`` whose repo-relative path contains ``gate`` or
``valid`` as a path-component/filename substring (case-insensitive),
excluding tests and the frozen ``router_v6`` package (out of scope per
the forced-segment fail-closed plan).

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

# Path components (case-insensitive) that mark a file as a gate/validator.
SCOPE_TOKENS = ("gate", "valid")

# Packages/subtrees excluded from scope even if they match SCOPE_TOKENS.
EXCLUDE_SUBSTRINGS = ("router_v6", "/tests/", "test_")

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


def in_scope(rel_path: str) -> bool:
    """True when *rel_path* (posix, repo-relative) is a gate/validator file."""
    low = rel_path.lower()
    if any(ex in low for ex in EXCLUDE_SUBSTRINGS):
        return False
    return any(tok in low for tok in SCOPE_TOKENS)


def find_scope_files(packages_dir: Path) -> list[Path]:
    """Return every in-scope ``.py`` file under ``packages/*/src``."""
    results: list[Path] = []
    for src_dir in sorted(packages_dir.glob("*/src")):
        for py_file in sorted(src_dir.rglob("*.py")):
            rel = py_file.relative_to(packages_dir.parent).as_posix()
            if in_scope(rel):
                results.append(py_file)
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


def find_all_violations(packages_dir: Path) -> dict[str, tuple[int, str]]:
    """Scan every in-scope file. Returns ``{key: (lineno, snippet)}``."""
    results: dict[str, tuple[int, str]] = {}
    for py_file in find_scope_files(packages_dir):
        rel = py_file.relative_to(packages_dir.parent).as_posix()
        for lineno, snippet in find_violations(py_file):
            results[f"{rel}:{lineno}"] = (lineno, snippet)
    return results


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

    args = parser.parse_args()

    packages_dir = args.packages_dir
    if not packages_dir.is_absolute():
        packages_dir = Path.cwd() / packages_dir

    if not packages_dir.is_dir():
        console.print(f"[red]Packages directory not found: {packages_dir}[/]")
        sys.exit(1)

    violations = find_all_violations(packages_dir)

    if violations:
        for key in sorted(violations):
            lineno, snippet = violations[key]
            console.print(
                f"[red]FAIL: {key} — unguarded aggregation: {snippet!r}."
                f" all() over an empty collection is vacuously True;"
                f" assert non-empty (or a per-item None check) before"
                f" aggregating.[/]"
            )
        sys.exit(1)

    console.print("[green]Anti-vacuous-truth gate passed[/]")


if __name__ == "__main__":
    main()
