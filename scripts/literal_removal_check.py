#!/usr/bin/env python3
"""Literal-removal advisory check.

Flags hardcoded literals removed by a diff that are still referenced
elsewhere in the repo -- the "accidentally load-bearing hardcode" pattern
(e.g. the F.Cu layer hardcode, CONNECTION_THRESHOLD_MM) where deleting a
value in one place silently breaks code that implicitly depended on it.

Advisory only: always exits 0. Prints findings for human review.

Usage:
  uv run python scripts/literal_removal_check.py [--base <ref>]
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

NOISE_TOKENS = {"0", "1", "-1", '""', "''", "True", "False", "None", "0.0", "1.0"}

_STRING_RE = re.compile(r'"[^"]{2,}"|\'[^\']{2,}\'')
_NUMBER_RE = re.compile(r"-?\d+\.\d+|-?\d{2,}")
_CONST_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")


def extract_literals(line):
    """Extract literal-shaped tokens (strings, numbers, ALL_CAPS constants) from a line."""
    tokens = set()
    tokens.update(_STRING_RE.findall(line))
    tokens.update(_NUMBER_RE.findall(line))
    tokens.update(_CONST_RE.findall(line))
    return tokens


def is_noise(token):
    """True if a token is too common/generic to be worth flagging."""
    return token in NOISE_TOKENS


def hunks_from_diff(diff_text):
    """Parse `git diff -U0` output into per-file hunks of removed/added lines.

    Returns {file_path: [{"removed": [...], "added": [...]}, ...]}.
    """
    files = {}
    current_file = None
    current_hunk = None

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[len("+++ b/"):]
            files.setdefault(current_file, [])
            current_hunk = None
        elif line.startswith("--- "):
            continue
        elif line.startswith("@@"):
            current_hunk = {"removed": [], "added": []}
            if current_file is not None:
                files[current_file].append(current_hunk)
        elif current_hunk is None:
            continue
        elif line.startswith("-"):
            current_hunk["removed"].append(line[1:])
        elif line.startswith("+"):
            current_hunk["added"].append(line[1:])

    return files


def removed_literals_per_file(diff_text):
    """For each file in the diff, return literals removed in a hunk that
    don't reappear in that hunk's added lines (true removals, not edits)."""
    files = hunks_from_diff(diff_text)
    result = {}

    for file_path, hunks in files.items():
        flagged = set()
        for hunk in hunks:
            removed_tokens = set()
            for line in hunk["removed"]:
                removed_tokens |= extract_literals(line)
            added_tokens = set()
            for line in hunk["added"]:
                added_tokens |= extract_literals(line)
            flagged |= {t for t in (removed_tokens - added_tokens) if not is_noise(t)}
        if flagged:
            result[file_path] = flagged

    return result


def find_external_references(token, exclude_file, repo_root=REPO_ROOT):
    """git grep for `token` across the repo, excluding `exclude_file` and vendored paths."""
    result = subprocess.run(
        [
            "git", "grep", "-F", "-n", token, "--",
            ".",
            f":!{exclude_file}",
            ":!target",
            ":!.venv",
            ":!pcb/libs",
            ":!pcb/.history",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        return []
    return [line for line in result.stdout.splitlines() if line]


def git_diff(base, repo_root=REPO_ROOT):
    result = subprocess.run(
        ["git", "diff", "-U0", base],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def main(argv=None, repo_root=REPO_ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="HEAD", help="Base ref to diff against")
    args = parser.parse_args(argv)

    diff_text = git_diff(args.base, repo_root=repo_root)
    flagged = removed_literals_per_file(diff_text)

    found_any = False
    for file_path, tokens in sorted(flagged.items()):
        for token in sorted(tokens):
            refs = find_external_references(token, file_path, repo_root=repo_root)
            if refs:
                found_any = True
                print(f"warning: {file_path} removed {token!r}, still referenced:")
                for ref in refs:
                    print(f"  {ref}")

    if not found_any:
        print("literal-removal-check: no removed literals with lingering references")

    return 0  # advisory: never fails the build


if __name__ == "__main__":
    sys.exit(main())
