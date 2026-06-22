#!/usr/bin/env python3
"""Coverage gate: fail CI if any public function in scope has zero line coverage.

Per-function binary gate: every public function (module-level def not prefixed
with `_`, and methods of public classes not prefixed with `_`) must have at least
one executed line in its body, or appear on the monotonic-shrink allowlist.

Modes:
  --init               Populate .coverage-allowlist with current zero-coverage
                       public functions. CI passes on this commit.
  (default)            Compute zero-coverage public functions, subtract the
                       allowlist. Fail on any uncovered function not allowed.
                       Warn on stale allowlist entries (now covered).
  --check-shrink       Compare allowlist vs origin/main. Fail if entries were
                       removed without a test or deletion in the same PR.
                       Fail if entries were added without a ticket reference.

The script follows the scripts/check_regression.py convention: argparse, rich
Console, sys.path manipulation as needed.
"""

import argparse
import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from rich.console import Console

console = Console()

TICKET_PATTERN = re.compile(r"TODO:\s*temper-(?:\d+|xxx)")


def parse_coverage_json(coverage_json_path):
    """Load coverage.json and return the 'files' dict."""
    with open(coverage_json_path) as f:
        data = json.load(f)
    return data.get("files", {})


def ast_public_functions(source_path):
    """AST-parse a Python source file and return a set of qualified public function names.

    A function is public if:
      - Module-level FunctionDef / AsyncFunctionDef whose name does not start with `_`.
      - Method of a ClassDef whose name does not start with `_`, and the method name
        does not start with `_`. Qualified as ``ClassName.method_name``.
    """
    with open(source_path) as f:
        tree = ast.parse(f.read(), filename=str(source_path))

    public = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                public.add(node.name)
        elif isinstance(node, ast.ClassDef):
            if not node.name.startswith("_"):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if not item.name.startswith("_"):
                            public.add(f"{node.name}.{item.name}")
    return public


def find_zero_coverage(files, source_root):
    """Return a dict {allowlist_key: line_number} of zero-coverage public functions.

    allowlist_key format: ``temper_placer/core/module.py::func_or_Class.method``
    """
    zero_cov = {}

    for file_path, file_data in files.items():
        # Resolve the source file on disk
        src_file = source_root / file_path
        if not src_file.exists():
            console.print(f"[yellow]Warning: source file not found: {src_file}[/]")
            continue

        public_names = ast_public_functions(src_file)
        executed = set(file_data.get("executed_lines", []))
        functions = file_data.get("functions", {})

        for func_name, (start_line, end_line) in functions.items():
            if func_name not in public_names:
                continue

            # Lines in the function body (exclude the def line itself)
            body_lines = set(range(start_line + 1, end_line + 1))

            if not (body_lines & executed):
                allowlist_key = f"{file_path}::{func_name}"
                zero_cov[allowlist_key] = start_line

    return zero_cov


def load_allowlist(path):
    """Parse .coverage-allowlist into a dict {key: ticket_string}.

    Format: ``path::function  # TODO: temper-xxx``
    Lines starting with ``#`` (no preceding entry) are comments.
    Empty lines are ignored.
    """
    entries = {}
    if not path.exists():
        return entries

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Split on '#' to separate the key from the comment
        if "#" in line:
            key_part, comment = line.split("#", 1)
            key_part = key_part.strip()
        else:
            key_part = line.strip()
            comment = ""

        if key_part:
            entries[key_part] = comment.strip()

    return entries


def git_show_main_allowlist():
    """Return the allowlist content from origin/main, or None if unavailable."""
    try:
        result = subprocess.run(
            ["git", "show", "origin/main:.coverage-allowlist"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return None
        return result.stdout
    except Exception:
        return None


def check_shrink_mode(current_allowlist, coverage_json_path, source_root):
    """Monotonic-shrink check: compare current allowlist to origin/main.

    - Entries removed from allowlist must have either a test (coverage)
      or the function deleted from source.
    - Entries added to allowlist must have a # TODO: temper-xxx ticket.
    """
    main_content = git_show_main_allowlist()
    if main_content is None:
        console.print("[yellow]Warning: origin/main:.coverage-allowlist not available; "
                       "skipping shrink check (zero-coverage check still runs)[/]")
        return 0

    # Parse main allowlist keys (ignore comments/tickets for comparison)
    main_keys = set()
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

    # Check removals: must have coverage or be deleted
    if removed:
        # Load current coverage to check for exercise
        files = parse_coverage_json(coverage_json_path)
        current_zero = find_zero_coverage(files, source_root)

        for entry in sorted(removed):
            # Check if the function now has coverage (not in zero_cov)
            if entry not in current_zero:
                continue  # has coverage, removal is valid

            # Check if the file/function was deleted
            if "::" in entry:
                file_part, func_part = entry.split("::", 1)
                src_file = source_root / file_part
                if not src_file.exists():
                    continue  # file deleted, removal is valid

                # File still exists but function might be deleted
                public_names = ast_public_functions(src_file)
                if func_part not in public_names:
                    continue  # function deleted, removal is valid

            console.print(
                f"[red]FAIL: allowlist entry removed without test or deletion: "
                f"{entry}[/]"
            )
            failures += 1

    # Check additions: must have a ticket
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
        description="Coverage gate: fail CI on zero-coverage public functions"
    )
    parser.add_argument(
        "--coverage-json",
        type=Path,
        default="coverage.json",
        help="Path to coverage.json (default: coverage.json)",
    )
    parser.add_argument(
        "--allowlist",
        type=Path,
        default=".coverage-allowlist",
        help="Path to .coverage-allowlist (default: .coverage-allowlist)",
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=None,
        help="Root for resolving source file paths (default: derived from --coverage-json parent + 'src')",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Populate allowlist with current zero-coverage public functions",
    )
    parser.add_argument(
        "--check-shrink",
        action="store_true",
        help="Enforce monotonic-shrink: entries removed require test/deletion, entries added require ticket",
    )

    args = parser.parse_args()

    # Derive source root from coverage.json location
    if args.source_root is None:
        coverage_dir = args.coverage_json.resolve().parent
        args.source_root = coverage_dir / "src"

    if not args.coverage_json.exists():
        console.print(f"[red]coverage.json not found: {args.coverage_json}[/]")
        sys.exit(1)

    files = parse_coverage_json(args.coverage_json)
    if not files:
        console.print("[red]No file data found in coverage.json[/]")
        sys.exit(1)

    zero_cov = find_zero_coverage(files, args.source_root)

    if args.init:
        # Populate the allowlist
        lines = [
            "# Coverage gate allowlist — monotonically-shrinking baseline",
            "# Format: path::function  # TODO: temper-xxx",
            "#",
            "# An entry represents a public function with zero line coverage.",
            "# Entries may only be removed when the same PR adds a test",
            "# exercising the function or deletes the function from source.",
            "# Entries may only be added with a # TODO: temper-xxx ticket reference.",
            "# See CLAUDE.md §Coverage Gate for details.",
            "",
        ]
        for key in sorted(zero_cov):
            lines.append(f"{key}  # TODO: temper-xxx")
        lines.append("")

        args.allowlist.write_text("\n".join(lines))
        console.print(
            f"[green]Allowlist populated with {len(zero_cov)} entries: "
            f"{args.allowlist}[/]"
        )
        console.print("[bold]Review and replace TODO placeholders with real ticket IDs.[/]")
        sys.exit(0)

    # Default mode: gate check
    allowlist = load_allowlist(args.allowlist)
    allowlist_keys = set(allowlist.keys())

    new_uncovered = set(zero_cov.keys()) - allowlist_keys
    stale = allowlist_keys - set(zero_cov.keys())

    exit_code = 0

    if new_uncovered:
        for key in sorted(new_uncovered):
            line = zero_cov[key]
            console.print(
                f"[red]FAIL: {key}:{line} — zero coverage "
                f"(not on allowlist; see CLAUDE.md §Coverage Gate)[/]"
            )
        exit_code = 1

    if stale:
        for key in sorted(stale):
            console.print(
                f"[yellow]WARNING: {key} is on the allowlist but now has coverage "
                f"— remove the entry[/]"
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
        shrink_failures = check_shrink_mode(
            allowlist, args.coverage_json, args.source_root
        )
        if shrink_failures:
            exit_code = 1

    if exit_code:
        sys.exit(1)

    console.print("[green]Coverage gate passed[/]")


if __name__ == "__main__":
    main()
