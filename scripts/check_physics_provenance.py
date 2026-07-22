#!/usr/bin/env python3
"""Physics parameter provenance gate: fail CI on module-level float constants in
physics/ lacking a ``# source:`` citation comment.

Per-constant binary gate: every module-level float constant in the ``physics/``
directory must have a ``# source:`` comment on the same line or the preceding
line, or appear on the monotonic-shrink allowlist.

Modes:
  --init               Populate .physics-provenance-allowlist with current
                       undocumented constants. CI passes on this commit.
  (default)            Find undocumented module-level floats, subtract the
                       allowlist. Fail on any not allowlisted. Warn on stale
                       allowlist entries (now documented).
  --check-shrink       Compare allowlist vs origin/main. Fail if entries were
                       removed without a ``# source:`` comment gained or
                       constant deletion in the same PR. Fail if entries were
                       added without a ticket reference.

Boundary: Only matches ``ast.Constant(value, kind=float)`` — expressions like
``MU_0 = 4 * math.pi * 1e-7`` (which produce ``BinOp``) are not flagged. These
become in-scope for the ``PhysicsConstant[T]`` dataclass migration.
"""

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path

from rich.console import Console

console = Console()

TICKET_PATTERN = re.compile(r"TODO:\s*temper-(?:\d+|xxx)")


def find_undocumented_constants(physics_dir: Path, repo_root: Path) -> dict:
    """Scan *physics_dir* for module-level float constants lacking ``# source:``.

    Returns a dict ``{allowlist_key: (line_no, value, const_name)}`` where
    *allowlist_key* is ``repo-rel-path::const_name`` (e.g.
    ``packages/temper-placer/src/temper_placer/physics/thermal.py::MY_CONST``).
    """
    undocumented: dict[str, tuple[int, float, str]] = {}

    for py_file in sorted(physics_dir.rglob("*.py")):
        if py_file.name == "__init__.py":
            continue

        source_text = py_file.read_text()
        source_lines = source_text.splitlines()

        tree = ast.parse(source_text, filename=str(py_file))

        # Compute repo-relative allowlist prefix
        try:
            rel = py_file.resolve().relative_to(repo_root.resolve())
        except ValueError:
            rel = py_file  # fallback: absolute path as-is

        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, ast.Assign):
                continue

            # Match value: Constant(float) — skip BinOp/Call/etc.
            values = _float_constants(node.value)
            if not values:
                continue

            # Match target: Name(s), flattening tuple targets
            names = _assignment_names(node)
            if not names:
                continue

            for val, const_name in zip(values, names, strict=True):
                has_source = _has_source_comment(
                    source_lines, node.lineno, node.end_lineno or node.lineno
                )
                if not has_source:
                    key = f"{rel}::{const_name}"
                    undocumented[key] = (node.lineno, val, const_name)

    return undocumented


def _float_constants(value_node: ast.expr) -> list[float]:
    """Extract float values from an AST expression node.

    Returns float values only when the value is a Constant with float kind.
    For tuples, recursively extracts float constants from each element.
    """
    if isinstance(value_node, ast.Constant):
        if isinstance(value_node.value, float):
            return [value_node.value]
        return []
    if isinstance(value_node, ast.Tuple):
        result: list[float] = []
        for elt in value_node.elts:
            result.extend(_float_constants(elt))
        return result
    return []


def _assignment_names(node: ast.Assign) -> list[str]:
    """Extract target names from an assignment, flattening tuple targets."""
    names: list[str] = []
    for target in node.targets:
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, ast.Tuple):
            for elt in target.elts:
                if isinstance(elt, ast.Name):
                    names.append(elt.id)
    return names


def _has_source_comment(
    source_lines: list[str], start_lineno: int, end_lineno: int,
) -> bool:
    """Check if any line in span [start_lineno, end_lineno], the line before,
    or the line after has a ``# source:`` substring."""
    check_lines = set()
    # The assignment line itself
    check_lines.add(start_lineno)
    # Preceding line (lineno - 1)
    if start_lineno > 1:
        check_lines.add(start_lineno - 1)
    # Following line (end_lineno + 1) — for comment blocks after the assignment
    check_lines.add(end_lineno + 1)
    # Multi-line assignments: include intermediate lines too
    for ln in range(start_lineno, end_lineno + 1):
        check_lines.add(ln)

    for ln in sorted(check_lines):
        idx = ln - 1
        if 0 <= idx < len(source_lines):
            if "# source:" in source_lines[idx]:
                return True
    return False


def load_allowlist(path: Path) -> dict[str, str]:
    """Parse an allowlist file into ``{key: ticket_comment}``.

    Format: ``path::constant_name  # TODO: temper-xxx``
    Lines starting with ``#`` (no preceding entry) are header comments.
    Empty lines are ignored.
    """
    entries: dict[str, str] = {}
    if not path.exists():
        return entries

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "#" in line:
            key_part, comment = line.split("#", 1)
            key_part = key_part.strip()
        else:
            key_part = line.strip()
            comment = ""
        if key_part:
            entries[key_part] = comment.strip()
    return entries


def git_show_main_allowlist(allowlist_path: str) -> str | None:
    """Return allowlist content from origin/main, or None if unavailable."""
    try:
        result = subprocess.run(
            ["git", "show", f"origin/main:{allowlist_path}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except Exception:
        return None


def check_shrink_mode(
    current_allowlist: dict[str, str],
    physics_dir: Path,
    repo_root: Path,
    allowlist_path: str,
) -> int:
    """Monotonic-shrink check: compare current allowlist to origin/main.

    - Entries removed must have gained a ``# source:`` comment or been deleted.
    - Entries added must have a ``# TODO: temper-xxx`` ticket.
    """
    main_content = git_show_main_allowlist(allowlist_path)
    if main_content is None:
        console.print(
            "[yellow]Warning: origin/main allowlist not available; "
            "skipping shrink check (gate check still runs)[/]"
        )
        return 0

    main_keys: set[str] = set()
    for line in main_content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "#" in line:
            key = line.split("#", 1)[0].strip()
        else:
            key = line
        if key:
            main_keys.add(key)

    current_keys = set(current_allowlist.keys())
    removed = main_keys - current_keys
    added = current_keys - main_keys

    failures = 0

    # Check removals: must have gained # source: or been deleted
    if removed:
        current_undoc = find_undocumented_constants(physics_dir, repo_root)

        for entry in sorted(removed):
            # If not in undocumented → has source OR constant deleted = valid
            if entry not in current_undoc:
                continue

            console.print(
                f"[red]FAIL: allowlist entry removed without # source: "
                f"comment or deletion: {entry}[/]"
            )
            failures += 1

    # Check additions: must have ticket
    for entry in sorted(added):
        ticket = current_allowlist.get(entry, "")
        if not TICKET_PATTERN.search(ticket):
            console.print(
                f"[red]FAIL: allowlist entry added without ticket reference: "
                f"{entry}[/]"
            )
            failures += 1

    if not failures:
        console.print("[green]Monotonic-shrink check passed[/]")
    return failures


def main():
    parser = argparse.ArgumentParser(
        description="Physics provenance gate: fail CI on undocumented "
                    "module-level float constants in physics/"
    )
    parser.add_argument(
        "--physics-dir",
        type=Path,
        default="packages/temper-placer/src/temper_placer/physics",
        help="Path to physics/ directory (default: packages/temper-placer/src/temper_placer/physics)",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=".physics-provenance-allowlist",
        help="Path to allowlist file (default: .physics-provenance-allowlist)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repo root for relative paths (default: cwd)",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Populate allowlist with current undocumented constants",
    )
    parser.add_argument(
        "--check-shrink",
        action="store_true",
        help="Enforce monotonic-shrink: compare against origin/main allowlist",
    )

    args = parser.parse_args()

    repo_root = args.repo_root or Path.cwd()

    physics_dir = args.physics_dir
    if not physics_dir.is_absolute():
        physics_dir = repo_root / physics_dir

    if not physics_dir.is_dir():
        console.print(f"[red]Physics directory not found: {physics_dir}[/]")
        sys.exit(1)

    undocumented = find_undocumented_constants(physics_dir, repo_root)

    if args.init:
        lines = [
            "# Physics provenance allowlist — monotonically-shrinking baseline",
            "# Format: path::constant_name  # TODO: temper-xxx",
            "#",
            "# An entry represents a module-level float constant in physics/",
            "# lacking a # source: citation comment.",
            "# Entries may only be removed when the same PR adds a # source:",
            "# comment or deletes the constant from source.",
            "# Entries may only be added with a # TODO: temper-xxx ticket reference.",
            "# See docs/plans/2026-07-22-007-refactor-physics-parameter-provenance-plan.md",
            "",
        ]
        for key in sorted(undocumented):
            lines.append(f"{key}  # TODO: temper-xxx")
        lines.append("")

        args.allowlist.write_text("\n".join(lines))
        console.print(
            f"[green]Allowlist populated with {len(undocumented)} entries: "
            f"{args.allowlist}[/]"
        )
        console.print("[bold]Review and replace TODO placeholders with real ticket IDs.[/]")
        sys.exit(0)

    # Default mode: gate check
    allowlist = load_allowlist(args.allowlist)
    allowlist_keys = set(allowlist.keys())

    undoc_keys = set(undocumented.keys())
    new_violations = undoc_keys - allowlist_keys
    stale = allowlist_keys - undoc_keys

    exit_code = 0

    if new_violations:
        for key in sorted(new_violations):
            lineno, value, name = undocumented[key]
            console.print(
                f"[red]FAIL: {key}:{lineno} — "
                f"'{name}' ({value}) missing # source: comment[/]"
            )
        exit_code = 1

    if stale:
        for key in sorted(stale):
            console.print(
                f"[yellow]WARNING: {key} is on the allowlist but now has "
                f"# source: comment — remove the entry[/]"
            )

    # Validate allowlist entries have ticket references
    for key, comment in sorted(allowlist.items()):
        if not TICKET_PATTERN.search(comment):
            console.print(
                f"[red]FAIL: allowlist entry missing ticket reference: "
                f"{key}  # {comment or 'MISSING TODO'}[/]"
            )
            exit_code = 1

    # Monotonic-shrink check
    if args.check_shrink:
        allowlist_rel = str(args.allowlist.relative_to(repo_root)) if args.allowlist.is_relative_to(repo_root) else str(args.allowlist)
        shrink_failures = check_shrink_mode(
            allowlist, physics_dir, repo_root, allowlist_rel,
        )
        if shrink_failures:
            exit_code = 1

    if exit_code:
        sys.exit(1)

    console.print("[green]Physics provenance gate passed[/]")


if __name__ == "__main__":
    main()
