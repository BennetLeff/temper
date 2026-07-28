#!/usr/bin/env python3
"""Physics parameter provenance gate: reject module-level float literals in
``physics/`` lacking a ``# source:`` comment citation.

The gate scans every ``.py`` file under the physics directory, AST-parses each
module, and identifies assignments of the form ``NAME = float`` at module level
(not inside a function or class body).  For each such constant the gate checks
whether a ``# source:`` substring appears on the **same line**, the
**immediately preceding line**, or the **immediately following line**.  Constants
that satisfy this check are considered documented; the gate fails on any
undocumented constant not on the monotonic-shrink allowlist.

**Scope boundary** (documented in the docstring per plan §Deferred
Implementation Notes): the AST gate only matches ``ast.Constant(value,
kind=float)``.  Expressions like ``MU_0 = 4 * math.pi * 1e-7`` produce a
``BinOp`` node and are **not** flagged.  Function-body constants and dataclass
field defaults are out of scope.  These become in-scope for the deferred
``PhysicsConstant[T]`` dataclass migration.

Modes
-----
``--init``
    Populate ``.physics-provenance-allowlist`` with every currently
    undocumented module-level float constant.  CI passes on this commit.
``(default)``
    Scan for undocumented module-level floats, subtract the allowlist, and
    fail on any constant not on the allowlist.  Warn on stale allowlist
    entries (constants that now carry a ``# source:`` comment).
``--check-shrink``
    Compare the current allowlist against ``origin/main``.  Fail if entries
    were removed without the constant gaining a ``# source:`` comment or
    being deleted from source.  Fail if entries were added without a
    ``# TODO: temper-xxx`` ticket reference.  Gracefully WARNING-skip when
    ``origin/main`` is unavailable (shallow clone).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import ast
import re

from _lib.gate_allowlist import (
    TICKET_PATTERN,
    load_allowlist as _load_allowlist,
    git_show_main_allowlist as _git_show_main_allowlist,
    check_shrink_mode as _check_shrink_mode,
)
from _lib.repo import find_repo_root
from rich.console import Console

console = Console()

SOURCE_PATTERN = re.compile(r"#\s*source:")


# ---------------------------------------------------------------------------
# core scan
# ---------------------------------------------------------------------------


def _is_module_level(node: ast.AST, tree: ast.Module) -> bool:
    """True when *node* is a direct child of the module body."""
    return any(node is child for child in ast.iter_child_nodes(tree))


def find_all_constants(
    physics_dir: Path,
) -> dict[str, tuple[float, int, bool]]:
    """AST-walk *physics_dir* for module-level ``NAME = float`` assigns.

    Returns
    -------
    dict
        ``{allowlist_key: (float_value, lineno, has_source_comment)}``
        where *allowlist_key* is ``repo_relative_path::CONSTANT_NAME``.
    """
    resolved_phys = physics_dir.resolve()
    results: dict[str, tuple[float, int, bool]] = {}

    for py_file in sorted(resolved_phys.rglob("*.py")):
        if py_file.name.startswith("_"):
            continue

        try:
            source_lines = py_file.read_text().splitlines()
            tree = ast.parse("\n".join(source_lines), filename=str(py_file))
        except SyntaxError:
            console.print(
                f"[yellow]WARNING: syntax error in {py_file}, skipping[/]"
            )
            continue

        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not _is_module_level(node, tree):
                continue

            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                if not isinstance(node.value, ast.Constant):
                    continue
                if not isinstance(node.value.value, float):
                    continue

                const_name = target.id
                lineno = node.lineno
                value = node.value.value

                has_source = False
                # same line (lineno is 1-indexed)
                line_idx = lineno - 1
                if 0 <= line_idx < len(source_lines):
                    if SOURCE_PATTERN.search(source_lines[line_idx]):
                        has_source = True
                # preceding line
                if not has_source and line_idx - 1 >= 0:
                    if SOURCE_PATTERN.search(source_lines[line_idx - 1]):
                        has_source = True
                # following line (common Python convention: comment after const)
                if not has_source and line_idx + 1 < len(source_lines):
                    if SOURCE_PATTERN.search(source_lines[line_idx + 1]):
                        has_source = True

                rel = py_file.resolve().relative_to(resolved_phys)
                key = f"{rel}::{const_name}"
                results[key] = (value, lineno, has_source)

    return results


def find_undocumented_constants(
    physics_dir: Path,
) -> dict[str, tuple[float, int]]:
    """Like :func:`find_all_constants` but return only undocumented entries."""
    all_c = find_all_constants(physics_dir)
    return {
        k: (v, l)
        for k, (v, l, has_src) in all_c.items()
        if not has_src
    }


# ---------------------------------------------------------------------------
# allowlist i/o
# ---------------------------------------------------------------------------


def load_allowlist(path: Path) -> dict[str, str]:
    """Parse ``.physics-provenance-allowlist`` into ``{key: ticket_string}``."""
    entries: dict[str, str] = {}
    for line in _load_allowlist(path):
        if "#" in line:
            key_part, comment = line.split("#", 1)
            key_part = key_part.strip()
        else:
            key_part = line.strip()
            comment = ""
        if key_part:
            entries[key_part] = comment.strip()
    return entries


def git_show_main_allowlist() -> str | None:
    """Return the allowlist content from ``origin/main``, or *None*."""
    try:
        root = find_repo_root()
        lines = _git_show_main_allowlist(".physics-provenance-allowlist", root)
        return "\n".join(lines)
    except (RuntimeError, FileNotFoundError):
        return None


# ---------------------------------------------------------------------------
# --check-shrink
# ---------------------------------------------------------------------------


def check_shrink_mode(
    current_allowlist: dict[str, str],
    physics_dir: Path,
) -> int:
    """Monotonic-shrink check: compare current allowlist to ``origin/main``.

    - Entries removed from the allowlist must have the constant gain a
      ``# source:`` comment or be deleted from source.
    - Entries added to the allowlist must carry a ticket reference.
    """
    main_content = git_show_main_allowlist()
    if main_content is None:
        console.print(
            "[yellow]Warning: origin/main:.physics-provenance-allowlist not"
            " available; skipping shrink check[/]"
        )
        return 0

    main_entries = main_content.splitlines()
    current_entries = [f"{k}  # {v}" for k, v in sorted(current_allowlist.items())]
    removed, added = _check_shrink_mode(main_entries, current_entries)

    failures = 0

    if removed:
        all_constants = find_all_constants(physics_dir)
        resolved_phys = physics_dir.resolve()

        for entry in sorted(removed):
            if "::" not in entry:
                console.print(
                    f"[red]FAIL: cannot parse removed entry: {entry}[/]"
                )
                failures += 1
                continue

            file_part, const_name = entry.split("::", 1)
            src_file = resolved_phys / file_part

            if not src_file.exists():
                continue  # file deleted — valid removal

            const_info = all_constants.get(entry)
            if const_info is None:
                continue  # constant deleted — valid removal

            _value, _lineno, has_source = const_info
            if not has_source:
                console.print(
                    f"[red]FAIL: allowlist entry removed but constant still"
                    f" exists without # source: comment: {entry}[/]"
                )
                failures += 1

    for entry in sorted(added):
        ticket = current_allowlist.get(entry, "")
        if not TICKET_PATTERN.search(ticket):
            console.print(
                f"[red]FAIL: allowlist entry added without ticket"
                f" reference: {entry}[/]"
            )
            failures += 1

    if not failures:
        console.print("[green]Monotonic-shrink check passed[/]")
    return failures


# ---------------------------------------------------------------------------
# cli
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Physics provenance gate: require # source: comments on"
        " module-level float constants in physics/"
    )
    parser.add_argument(
        "--physics-dir",
        type=Path,
        default="packages/temper-placer/src/temper_placer/physics",
        help="Path to the physics/ package directory"
        " (default: packages/temper-placer/src/temper_placer/physics)",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=".physics-provenance-allowlist",
        help="Path to .physics-provenance-allowlist"
        " (default: .physics-provenance-allowlist)",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Populate allowlist with current undocumented module-level"
        " float constants",
    )
    parser.add_argument(
        "--check-shrink",
        action="store_true",
        help="Enforce monotonic-shrink: entries removed require"
        " # source: or deletion; entries added require ticket",
    )

    args = parser.parse_args()

    physics_dir = args.physics_dir
    if not physics_dir.is_absolute():
        physics_dir = Path.cwd() / physics_dir

    allowlist_path = args.allowlist
    if not allowlist_path.is_absolute():
        allowlist_path = Path.cwd() / allowlist_path

    if not physics_dir.is_dir():
        console.print(
            f"[red]Physics directory not found: {physics_dir}[/]"
        )
        sys.exit(1)

    all_constants = find_all_constants(physics_dir)
    undocumented = {
        k: (v, l) for k, (v, l, has_src) in all_constants.items() if not has_src
    }
    files_scanned = len(
        {key.split("::", 1)[0] for key in all_constants} if all_constants else set()
    )
    denominator = (
        f"Scanned {len(all_constants)} module-level float constant(s) across"
        f" {files_scanned} file(s) under {physics_dir}: {len(undocumented)}"
        f" undocumented."
    )

    if len(all_constants) == 0:
        console.print(
            f"[red]FAIL (closed): {denominator} A provenance gate that finds"
            f" zero constants to check cannot report a meaningful pass --"
            f" check --physics-dir.[/]"
        )
        sys.exit(1)

    if args.init:
        lines = [
            "# Physics parameter provenance allowlist"
            " — monotonically-shrinking baseline",
            "# Format: path::CONSTANT_NAME  # TODO: temper-xxx",
            "#",
            "# An entry represents a module-level float constant lacking"
            " a # source: comment.",
            "# Entries may only be removed when the same PR adds a"
            " # source: comment",
            "# or deletes the constant from source.",
            "# Entries may only be added with a # TODO: temper-xxx"
            " ticket reference.",
            "# See AGENTS.md and the plan"
            " 2026-07-22-007 for details.",
            "",
        ]
        for key in sorted(undocumented):
            lines.append(f"{key}  # TODO: temper-xxx")
        lines.append("")

        allowlist_path.write_text("\n".join(lines))
        console.print(
            f"[green]Allowlist populated with {len(undocumented)} entries:"
            f" {allowlist_path}[/]"
        )
        if undocumented:
            console.print(
                "[bold]Review and replace TODO placeholders with real"
                " ticket IDs.[/]"
            )
        sys.exit(0)

    allowlist = load_allowlist(allowlist_path)
    allowlist_keys = set(allowlist.keys())

    undocumented_keys = set(undocumented.keys())
    new_violations = undocumented_keys - allowlist_keys
    stale = allowlist_keys - undocumented_keys

    exit_code = 0

    if new_violations:
        for key in sorted(new_violations):
            value, lineno = undocumented[key]
            console.print(
                f"[red]FAIL: {key}:{lineno} — '{key.split('::')[-1]}'"
                f" ({value}) missing # source: comment[/]"
            )
        exit_code = 1

    if stale:
        for key in sorted(stale):
            console.print(
                f"[yellow]WARNING: {key} is on the allowlist but now has"
                f" a # source: comment — remove the entry[/]"
            )

    for key, comment in sorted(allowlist.items()):
        if not TICKET_PATTERN.search(comment):
            console.print(
                f"[red]FAIL: allowlist entry missing ticket reference:"
                f" {key}  # {comment or 'MISSING TODO'}[/]"
            )
            exit_code = 1

    if args.check_shrink:
        shrink_failures = check_shrink_mode(allowlist, physics_dir)
        if shrink_failures:
            exit_code = 1

    allowlist_denominator = f"Allowlist: {len(allowlist)} entries loaded from {allowlist_path}."

    if exit_code:
        console.print(f"[red]{denominator} {allowlist_denominator} FAILED.[/]")
        sys.exit(1)

    console.print(f"[green]Physics provenance gate passed. {denominator} {allowlist_denominator}[/]")


if __name__ == "__main__":
    main()
