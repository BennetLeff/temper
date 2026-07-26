#!/usr/bin/env python3
"""Type-check gate: fail CI if any file has more mypy errors than its allowlist baseline.

Per-file monotonic-shrink: each file in scope has an allowlist entry recording
its current mypy error count.  CI fails if a file grows beyond its baseline.
CI warns if a file has fewer errors (stale entry — reward for shrinking).

Modes:
  --init        Populate .typecheck-allowlist with current mypy error counts.
                CI passes on this commit.
  (default)     Run mypy, compare per-file error counts against allowlist.
                Fail on any file exceeding its baseline.
                Warn on stale entries (files now with fewer errors).
  --check-shrink  Compare allowlist vs origin/main. Fail if entries removed
                  without corresponding error reduction.

CALL-ARG HARD GATE (see docs/evidence/2026-07-26-api-signature-drift-gate.md):
  mypy's ``call-arg`` code ("Unexpected keyword argument ... ; did you mean
  ...?") is exactly the signature the ce882acf/5a17025b defect left: a lint
  autofix underscore-prefixed a public function's parameter while a keyword
  caller elsewhere still used the old name.  ``--init`` folds *all* mypy
  errors into ``.typecheck-allowlist`` as accepted debt with no scrutiny of
  which ones are new; that is precisely how the check_routability regression
  was absorbed on 2026-07-23 (commit fed27984, ~10h after the rename) without
  anyone noticing the file had gone from 0 errors to 1.  ``call-arg`` errors
  are therefore EXCLUDED from the generic per-file allowlist entirely — they
  can never be silently re-baselined by ``--init`` — and are instead checked
  against a small, hand-curated, always-manually-edited file,
  ``.call-arg-allowlist``.  Any call-arg error not already listed there is an
  unconditional hard failure, regardless of the general allowlist's state.
  This check runs even if ``.typecheck-allowlist`` itself is missing/empty,
  and fails closed (exit != 0) if ``.call-arg-allowlist`` is missing.

Usage:
  python3 scripts/check_typecheck_gate.py
  python3 scripts/check_typecheck_gate.py --init
  python3 scripts/check_typecheck_gate.py --check-shrink
"""

import argparse
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ALLOWLIST_PATH = Path(".typecheck-allowlist")
CALL_ARG_ALLOWLIST_PATH = Path(".call-arg-allowlist")
SCOPE = ["packages/temper-placer/src", "packages/temper-workflow/src", "packages/temper-tools/src"]

# mypy error line format: path:line: error: message  [code]
MYPY_LINE_RE = re.compile(r"^(.+?):(\d+): error: (.+?)(?:\[([a-z-]+)\])?$")

CALL_ARG_CODE = "call-arg"


def run_mypy() -> tuple[dict[str, int], list[tuple[str, str, str]]]:
    """Run mypy once and split results into (per-file counts, call-arg entries).

    ``call-arg`` errors ("unexpected keyword argument" / "too many arguments"
    / etc.) are deliberately excluded from the returned counts dict — they
    are governed by the separate, non-allowlistable hard gate below, not by
    the generic monotonic-shrink mechanism. Returns
    ``(counts, [(filepath, line, message), ...])``.
    """
    counts: dict[str, int] = defaultdict(int)
    call_arg_entries: list[tuple[str, str, str]] = []
    for scope in SCOPE:
        scope_path = Path(scope)
        if not scope_path.exists():
            continue
        result = subprocess.run(
            ["uv", "run", "mypy", str(scope_path), "--ignore-missing-imports"],
            capture_output=True, text=True,
        )
        for line in result.stdout.splitlines():
            m = MYPY_LINE_RE.match(line.strip())
            if not m:
                continue
            filepath, lineno, message, code = m.group(1), m.group(2), m.group(3), m.group(4)
            if code == CALL_ARG_CODE:
                call_arg_entries.append((filepath, lineno, message.strip()))
            else:
                counts[filepath] += 1
    return dict(counts), call_arg_entries


def load_call_arg_allowlist() -> set[tuple[str, str]]:
    """Load the hand-curated call-arg baseline: {(filepath, message), ...}.

    Deliberately keyed on (filepath, message) and NOT line number: line
    numbers churn on unrelated edits, and re-matching on message text keeps
    the baseline stable while still requiring an exact, specific match for
    any *new* call-arg error to be considered "already known."
    """
    entries: set[tuple[str, str]] = set()
    if not CALL_ARG_ALLOWLIST_PATH.exists():
        return entries
    with open(CALL_ARG_ALLOWLIST_PATH) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.strip().startswith("#"):
                continue
            if " ||| " not in line:
                continue
            filepath, message = line.split(" ||| ", 1)
            entries.add((filepath.strip(), message.strip()))
    return entries


def check_call_arg_gate(call_arg_entries: list[tuple[str, str, str]]) -> int:
    """Hard, allowlist-independent gate on mypy's call-arg error code.

    Fails closed: a missing ``.call-arg-allowlist`` file is treated as an
    empty baseline (nothing pre-approved), not as "nothing to check" — so
    every call-arg error found becomes an unconditional violation rather
    than the check silently no-oping.
    """
    if not CALL_ARG_ALLOWLIST_PATH.exists():
        print(
            f"WARNING: {CALL_ARG_ALLOWLIST_PATH} is missing — treating baseline as empty "
            "(fail-closed: every call-arg error below is therefore new)."
        )
    baseline = load_call_arg_allowlist()

    violations = 0
    for filepath, lineno, message in call_arg_entries:
        if (filepath, message) not in baseline:
            print(
                f"CALL-ARG HARD FAIL: {filepath}:{lineno}: {message}\n"
                "  This is the exact defect class from docs/evidence/"
                "2026-07-26-api-signature-drift-gate.md (a keyword-argument\n"
                "  call site that no longer matches the callee's signature). "
                "If this is a real bug, fix the\n"
                "  call site or restore the parameter name. If it is genuinely "
                "pre-existing and accepted,\n"
                f"  add it explicitly to {CALL_ARG_ALLOWLIST_PATH} by hand — "
                "it is never auto-populated."
            )
            violations += 1
    if violations:
        print(f"\n{violations} call-arg violation(s) not in {CALL_ARG_ALLOWLIST_PATH}")
    return violations


def load_allowlist() -> dict[str, int]:
    """Load the allowlist: file -> error count."""
    if not ALLOWLIST_PATH.exists():
        return {}
    entries = {}
    with open(ALLOWLIST_PATH) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                filepath = parts[0]
                try:
                    count = int(parts[1])
                    entries[filepath] = count
                except ValueError:
                    continue
    return entries


def init_allowlist() -> dict[str, int]:
    """Populate allowlist from current mypy error counts.

    Deliberately does NOT touch .call-arg-allowlist — that file is only ever
    edited by hand, so a routine ``--init`` re-sync can never absorb a new
    call-arg regression the way commit fed27984 absorbed check_routability's.
    """
    current, call_arg_entries = run_mypy()
    if call_arg_entries:
        print(
            f"NOTE: {len(call_arg_entries)} call-arg error(s) found; NOT written to "
            f"{ALLOWLIST_PATH}. They are governed by {CALL_ARG_ALLOWLIST_PATH}, which "
            "--init never modifies. Add them there by hand if they are genuinely "
            "pre-existing and accepted."
        )
    with open(ALLOWLIST_PATH, "w") as f:
        f.write("# Type-check allowlist — monotonic-shrink baseline\n")
        f.write(f"# {sum(current.values())} total errors across {len(current)} files\n")
        f.write("# <filepath> <max-allowed-error-count>\n")
        f.write("# Do not increase these numbers. Fix the errors.\n\n")
        for filepath in sorted(current.keys()):
            f.write(f"{filepath} {current[filepath]}\n")
    print(f"Initialized {ALLOWLIST_PATH} with {sum(current.values())} errors across {len(current)} files")
    return current


def check_shrink(allowlist: dict[str, int]) -> int:
    """Check that allowlist entries removed from origin/main had corresponding error fixes."""
    result = subprocess.run(
        ["git", "diff", "origin/main", "--", str(ALLOWLIST_PATH)],
        capture_output=True, text=True,
    )
    removed = []
    added = []
    for line in result.stdout.splitlines():
        if line.startswith("-") and not line.startswith("---"):
            stripped = line[1:].strip()
            if stripped and not stripped.startswith("#"):
                parts = stripped.split()
                if len(parts) >= 2 and parts[0] not in added:
                    removed.append(parts[0])
        elif line.startswith("+") and not line.startswith("+++"):
            stripped = line[1:].strip()
            if stripped and not stripped.startswith("#"):
                parts = stripped.split()
                if len(parts) >= 2:
                    added.append(parts[0])

    if not removed:
        print("Allowlist unchanged or only additions — OK")
        return 0

    # Check each removed entry against current errors
    current, _call_arg_entries = run_mypy()
    allowlist_current = load_allowlist()
    violations = 0
    for filepath in removed:
        current_count = current.get(filepath, 0)
        old_allowed = allowlist.get(filepath, 0)
        if filepath in allowlist_current:
            # Entry still exists — was just reduced. Verify reduction matches.
            new_allowed = allowlist_current[filepath]
            if new_allowed > old_allowed:
                print(f"FAIL: {filepath} allowlist grew: {old_allowed} -> {new_allowed}")
                violations += 1
        else:
            # Entry removed entirely — verify errors are actually gone
            if current_count > 0:
                print(f"FAIL: {filepath} removed from allowlist but still has {current_count} errors")
                violations += 1
            else:
                print(f"OK: {filepath} removed — errors fixed")

    if violations:
        print(f"\n{violations} allowlist shrink violation(s)")
    return violations


def main():
    parser = argparse.ArgumentParser(description="Type-check monotonic-shrink gate")
    parser.add_argument("--init", action="store_true", help="Populate allowlist from current errors")
    parser.add_argument("--check-shrink", action="store_true", help="Verify allowlist shrinkage is legitimate")
    args = parser.parse_args()

    if args.init:
        init_allowlist()
        return 0

    if args.check_shrink:
        allowlist = load_allowlist()
        if not allowlist:
            print("No allowlist found. Run --init first.")
            return 0
        return check_shrink(allowlist)

    # Default mode: gate check.
    #
    # Fail closed if there is nothing to check: a misconfigured/missing SCOPE
    # must not silently report "OK" as if type-checking actually happened.
    existing_scope = [s for s in SCOPE if Path(s).exists()]
    if not existing_scope:
        print(f"FAIL (closed): none of the configured SCOPE paths exist: {SCOPE}")
        print("  Refusing to report a pass when there is nothing to type-check.")
        return 1

    current, call_arg_entries = run_mypy()

    # Call-arg hard gate: runs unconditionally and independent of the
    # generic per-file allowlist below (see module docstring for why).
    call_arg_violations = check_call_arg_gate(call_arg_entries)

    allowlist = load_allowlist()
    violations = 0
    stale = 0

    if not allowlist:
        print("No .typecheck-allowlist found. Run --init first for the generic per-file gate.")
    else:
        # Check current files against allowlist
        all_files = set(list(current.keys()) + list(allowlist.keys()))
        for filepath in sorted(all_files):
            current_count = current.get(filepath, 0)
            allowed = allowlist.get(filepath, 0)

            if filepath not in allowlist:
                if current_count > 0:
                    print(f"NEW: {filepath} has {current_count} errors (not in allowlist)")
                    violations += 1
            elif current_count > allowed:
                print(f"REGRESSION: {filepath}: {current_count} errors > {allowed} allowed")
                violations += 1
            elif current_count < allowed:
                print(f"STALE: {filepath}: {current_count} errors < {allowed} allowed — update allowlist!")
                stale += 1

    total_current = sum(current.values())
    total_allowed = sum(allowlist.values()) if allowlist else 0

    print(
        f"\nTotal (excl. call-arg): {total_current} errors in {len(current)} files "
        f"(baseline: {total_allowed})"
    )
    print(f"Call-arg: {len(call_arg_entries)} found, {call_arg_violations} not in {CALL_ARG_ALLOWLIST_PATH}")
    if stale:
        print(f"  {stale} stale allowlist entries — update with --init to lock in improvements")

    total_violations = violations + call_arg_violations
    if total_violations:
        print(f"  {total_violations} total violation(s) — fix the errors or update the relevant allowlist")
        return 1

    print("OK — all files within allowlist baseline, no unapproved call-arg errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
