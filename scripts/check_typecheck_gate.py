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

COVERAGE GATE (see check_coverage):
  A per-file error count is only evidence if mypy actually analysed the file.
  It otherwise cannot tell "0 errors" from "never looked", and the latter is
  reported as ``STALE`` — a warning.  On 2026-08-05 a botched merge left three
  stray ``) -> LoopCollection: ...`` lines in a ``.pyi`` stub; mypy stopped at
  that one syntax error ("errors prevented further checking"), every other
  file reported zero, and the gate printed "1 errors in 1 files (baseline:
  209)" plus 27 STALE entries — output indistinguishable from a broken local
  environment, which is what it was misdiagnosed as.  Had the stub already
  been in the allowlist, the same abort would have PASSED the gate while
  type-checking nothing at all.  The gate therefore now demands positive
  evidence of coverage: it collects the analysed-module set from mypy's
  ``--linecount-report`` and hard-fails if the run aborted or if any
  still-existing allowlisted file is absent from that set.

Usage:
  python3 scripts/check_typecheck_gate.py
  python3 scripts/check_typecheck_gate.py --init
  python3 scripts/check_typecheck_gate.py --check-shrink
"""

import argparse
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ALLOWLIST_PATH = Path(".typecheck-allowlist")
CALL_ARG_ALLOWLIST_PATH = Path(".call-arg-allowlist")
SCOPE = ["packages/temper-placer/src", "packages/temper-workflow/src", "packages/temper-tools/src"]

# mypy error line format: path:line: error: message  [code]
MYPY_LINE_RE = re.compile(r"^(.+?):(\d+): error: (.+?)(?:\[([a-z-]+)\])?$")

CALL_ARG_CODE = "call-arg"

# mypy prints this in its summary line when a *blocking* error (a syntax error,
# an unresolvable duplicate module, ...) made it give up before analysing the
# rest of the tree.  See ``COVERAGE GATE`` in the module docstring.
MYPY_ABORT_MARKER = "errors prevented further checking"


def path_to_module(filepath: str) -> str | None:
    """Map an allowlist file path to the dotted module name mypy reports.

    ``packages/temper-placer/src/temper_placer/core/state.py`` ->
    ``temper_placer.core.state``.  Returns None if the path is not under any
    SCOPE root (such an entry is not something this run could have analysed).
    """
    for scope in SCOPE:
        prefix = scope.rstrip("/") + "/"
        if not filepath.startswith(prefix):
            continue
        rel = filepath[len(prefix):]
        for suffix in (".pyi", ".py"):
            if rel.endswith(suffix):
                rel = rel[: -len(suffix)]
                break
        module = rel.replace("/", ".")
        if module.endswith(".__init__"):
            module = module[: -len(".__init__")]
        return module
    return None


def parse_linecount_report(report_dir: Path) -> set[str]:
    """Extract the set of modules mypy actually analysed from its linecount report.

    ``--linecount-report`` writes one row per analysed module, plus a leading
    ``total`` row.  Columns are ``lines lines_annotated funcs funcs_annotated
    module``; we only want the last field.
    """
    modules: set[str] = set()
    report = report_dir / "linecount.txt"
    if not report.exists():
        return modules
    for line in report.read_text().splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        name = parts[4]
        if name == "total":
            continue
        modules.add(name)
    return modules


def run_mypy() -> tuple[dict[str, int], list[tuple[str, str, str]], set[str], list[tuple[str, str]]]:
    """Run mypy once per SCOPE entry and split results into (per-file counts,
    call-arg entries).

    SCOPE entries are separate packages, not a partition of the import graph:
    mypy's default ``follow_imports=normal`` means running it against
    ``packages/temper-workflow/src`` also type-checks (and re-reports errors
    for) any ``packages/temper-placer/src/...`` file that temper-workflow
    imports, under the exact same path string mypy uses when
    ``packages/temper-placer/src`` is scanned directly. Without
    deduplication, every error in a file imported across a SCOPE boundary is
    counted once per importing scope -- observed 2026-07-29: nearly every
    file with a temper-workflow -> temper-placer import edge had its mypy
    error count exactly double its ``.typecheck-allowlist`` baseline (e.g.
    core/board.py 1 -> 2, _loop_core.py 63 -> 126), which is duplicate
    reporting of the identical (file, line, message, code) tuple, not new
    errors. Deduplicating on that tuple before counting fixes it without
    hiding a genuine regression, which would still add a *new* tuple.

    ``call-arg`` errors ("unexpected keyword argument" / "too many arguments"
    / etc.) are deliberately excluded from the returned counts dict — they
    are governed by the separate, non-allowlistable hard gate below, not by
    the generic monotonic-shrink mechanism.

    Also returns the coverage evidence the gate needs to tell "this file has
    zero errors" apart from "mypy never looked at this file": the set of
    modules mypy reported analysing (via ``--linecount-report``) and the list
    of scopes whose run aborted on a blocking error. Returns
    ``(counts, [(filepath, line, message), ...], analysed_modules, aborted)``.
    """
    seen: set[tuple[str, str, str, str | None]] = set()
    counts: dict[str, int] = defaultdict(int)
    call_arg_entries: list[tuple[str, str, str]] = []
    analysed: set[str] = set()
    aborted: list[tuple[str, str]] = []
    for scope in SCOPE:
        scope_path = Path(scope)
        if not scope_path.exists():
            continue
        with tempfile.TemporaryDirectory() as report_dir:
            result = subprocess.run(
                [
                    "uv", "run", "mypy", str(scope_path), "--ignore-missing-imports",
                    "--linecount-report", report_dir,
                ],
                capture_output=True, text=True,
            )
            analysed |= parse_linecount_report(Path(report_dir))
        for line in result.stdout.splitlines():
            if MYPY_ABORT_MARKER in line:
                aborted.append((scope, line.strip()))
            m = MYPY_LINE_RE.match(line.strip())
            if not m:
                continue
            filepath, lineno, message, code = m.group(1), m.group(2), m.group(3), m.group(4)
            key = (filepath, lineno, message.strip(), code)
            if key in seen:
                continue
            seen.add(key)
            if code == CALL_ARG_CODE:
                call_arg_entries.append((filepath, lineno, message.strip()))
            else:
                counts[filepath] += 1
    return dict(counts), call_arg_entries, analysed, aborted


def check_coverage(allowlist: dict[str, int], analysed: set[str], aborted: list[tuple[str, str]]) -> int:
    """Refuse to report a verdict unless mypy actually analysed the allowlist.

    Two distinct false-verdict modes, both observed in the wild:

    1. **Blocking abort.** A syntax error in a single ``.pyi`` stub makes mypy
       print one error and stop ("errors prevented further checking"). Every
       other file then reports zero errors, so the gate emits a wall of
       ``STALE`` warnings and — if the offending file happened to already be
       in the allowlist — *passes*. That is a false PASS covering the entire
       codebase. (2026-08-05: a botched merge resolution left three stray
       ``) -> LoopCollection: ...`` lines in the temper_design_bundle_python
       stub; the gate reported "1 errors in 1 files (baseline: 209)" and 27
       stale entries, which reads as a local-environment problem rather than
       as "mypy analysed nothing".)

    2. **Silently unanalysed file.** An allowlist entry mypy never reached
       looks identical to one whose errors were all fixed: zero errors, so
       ``STALE``, which is only a warning.

    Both are eliminated by requiring positive evidence of coverage. An
    allowlist entry whose file no longer exists is reported but not failed —
    a deleted file genuinely has no errors.
    """
    if aborted:
        print("FAIL (closed): mypy aborted before analysing the full tree.")
        for scope, summary in aborted:
            print(f"  {scope}: {summary}")
        print(
            "  A blocking error (syntax error in a .py/.pyi, duplicate module, bad config)\n"
            "  stops mypy early, so every remaining file reports zero errors. The per-file\n"
            "  counts below would be meaningless — and would read as 'everything shrank'.\n"
            "  Fix the blocking error above, then re-run. Do NOT re-run --init in this state:\n"
            "  it would wipe the entire baseline to zero."
        )
        return 1

    missing: list[str] = []
    gone: list[str] = []
    for filepath in sorted(allowlist):
        module = path_to_module(filepath)
        if module is None:
            continue
        if module in analysed:
            continue
        if not Path(filepath).exists():
            gone.append(filepath)
        else:
            missing.append(filepath)

    for filepath in gone:
        print(f"GONE: {filepath} no longer exists — remove its allowlist entry")

    if missing:
        print(
            f"FAIL (closed): {len(missing)} allowlisted file(s) exist but mypy did not "
            "analyse them:"
        )
        for filepath in missing:
            print(f"  {filepath}")
        print(
            "  Their zero-error result is an absence of evidence, not evidence of absence,\n"
            "  and would otherwise be reported as a harmless STALE entry. Check for an\n"
            "  exclude rule, a shadowed module name, or a missing __init__.py."
        )
        return 1
    return 0


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


def init_allowlist() -> int:
    """Populate allowlist from current mypy error counts.

    Deliberately does NOT touch .call-arg-allowlist — that file is only ever
    edited by hand, so a routine ``--init`` re-sync can never absorb a new
    call-arg regression the way commit fed27984 absorbed check_routability's.

    Refuses to write anything if mypy aborted: re-baselining from a run that
    stopped at the first blocking error would silently reset every file to
    zero and permanently launder the real backlog away.
    """
    current, call_arg_entries, _analysed, aborted = run_mypy()
    if aborted:
        print("REFUSING to --init: mypy aborted before analysing the full tree.")
        for scope, summary in aborted:
            print(f"  {scope}: {summary}")
        print(
            f"  Writing {ALLOWLIST_PATH} now would record near-zero counts for every file "
            "and destroy the baseline.\n  Fix the blocking error above first."
        )
        return 1
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
    return 0


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
    current, _call_arg_entries, analysed, aborted = run_mypy()
    # An aborted run reports zero errors everywhere, which would "prove" that
    # every removed entry was legitimately fixed. Refuse to certify that.
    if check_coverage(allowlist, analysed, aborted):
        return 1
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
        return init_allowlist()

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

    current, call_arg_entries, analysed, aborted = run_mypy()

    # Call-arg hard gate: runs unconditionally and independent of the
    # generic per-file allowlist below (see module docstring for why).
    call_arg_violations = check_call_arg_gate(call_arg_entries)

    allowlist = load_allowlist()

    # Coverage gate: a verdict is only meaningful if mypy actually looked.
    # Runs before the per-file comparison so an aborted/incomplete run can
    # never be reported as a wall of harmless STALE entries.
    if check_coverage(allowlist, analysed, aborted):
        return 1

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
