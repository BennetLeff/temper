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

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import ast
import json

from _lib.gate_allowlist import (
    TICKET_PATTERN,
    load_allowlist as _load_allowlist,
    git_show_main_allowlist as _git_show_main_allowlist,
    check_shrink_mode as _check_shrink_mode,
)
from _lib.repo import find_repo_root
from rich.console import Console

console = Console()


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
        # Normalize: strip leading 'src/' prefix if present so paths match
        # the allowlist convention (temper_placer/module.py) independent of
        # whether coverage reports paths relative to a source root or CWD.
        normalized = file_path
        if normalized.startswith("src/"):
            normalized = normalized[4:]

        # Resolve the source file on disk
        src_file = source_root / normalized
        if not src_file.exists():
            console.print(f"[yellow]Warning: source file not found: {src_file}[/]")
            continue

        public_names = ast_public_functions(src_file)
        func_dicts = file_data.get("functions", {})

        for func_name, func_info in func_dicts.items():
            if func_name not in public_names:
                continue

            # coverage.py 7.x: func_info is a dict with 'executed_lines' and 'summary'
            if isinstance(func_info, dict):
                executed_func = set(func_info.get("executed_lines", []))
                n_statements = func_info.get("summary", {}).get("num_statements", 0)
                has_no_coverage = not executed_func and n_statements > 0
                # Use first missing line as line reference, fallback to 0
                missing = func_info.get("missing_lines", [])
                line_ref = missing[0] if missing else 0
            else:
                # Legacy format: (start_line, end_line) tuple
                start_line, end_line = func_info
                executed_func = set(file_data.get("executed_lines", []))
                body_lines = set(range(start_line + 1, end_line + 1))
                has_no_coverage = not (body_lines & executed_func)
                line_ref = start_line

            if has_no_coverage:
                allowlist_key = f"{normalized}::{func_name}"
                zero_cov[allowlist_key] = line_ref

    return zero_cov


def load_allowlist(path):
    """Parse .coverage-allowlist into a dict {key: ticket_string}."""
    entries = {}
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


def git_show_main_allowlist():
    """Return the allowlist content from origin/main, or None if unavailable."""
    try:
        root = find_repo_root()
        lines = _git_show_main_allowlist(".coverage-allowlist", root)
        return "\n".join(lines)
    except (RuntimeError, FileNotFoundError):
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

    main_entries = main_content.splitlines()
    current_entries = [f"{k}  # {v}" for k, v in sorted(current_allowlist.items())]
    removed, added = _check_shrink_mode(main_entries, current_entries)

    failures = 0

    if removed:
        files = parse_coverage_json(coverage_json_path)
        current_zero = find_zero_coverage(files, source_root)

        for entry in sorted(removed):
            if entry not in current_zero:
                continue

            if "::" in entry:
                file_part, func_part = entry.split("::", 1)
                src_file = source_root / file_part
                if not src_file.exists():
                    continue

                public_names = ast_public_functions(src_file)
                if func_part not in public_names:
                    continue

            console.print(
                f"[red]FAIL: allowlist entry removed without test or deletion: "
                f"{entry}[/]"
            )
            failures += 1

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
        # Populate / extend the allowlist, preserving existing entries.
        existing = load_allowlist(args.allowlist)
        existing_keys = set(existing.keys())
        new_keys = set(zero_cov.keys()) - existing_keys
        stale = existing_keys - set(zero_cov.keys())

        lines = [
            "# Coverage gate allowlist — monotonically-shrinking baseline",
            "# Format: path::function  # TODO: temper-xxx",
            "#",
            "# An entry represents a public function with zero line coverage.",
            "# Entries may only be removed when the same PR adds a test",
            "# exercising the function or deletes the function from source.",
            "# Entries may only be added with a # TODO: temper-xxx ticket reference.",
            "# See AGENTS.md §Coverage Gate for details.",
            "",
        ]

        # Preserve existing entries (including stale ones — human triage).
        for key in sorted(existing_keys):
            ticket = existing.get(key, "TODO: temper-xxx")
            lines.append(f"{key}  # {ticket}")

        # Append new entries with placeholder tickets.
        for key in sorted(new_keys):
            lines.append(f"{key}  # TODO: temper-xxx")

        lines.append("")

        args.allowlist.write_text("\n".join(lines))
        console.print(
            f"[green]Allowlist: {len(existing_keys)} existing entries preserved, "
            f"{len(new_keys)} new entries added.[/]"
        )
        if stale:
            console.print(
                f"[yellow]{len(stale)} stale entries (now have coverage) were preserved — "
                f"consider removing them manually.[/]"
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
                f"(not on allowlist; see AGENTS.md §Coverage Gate)[/]"
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
