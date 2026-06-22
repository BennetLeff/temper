#!/usr/bin/env python3
"""Vulture dead-code CI gate: diff wrapper with baseline allowlist.

Exit codes (distinct from Vulture's own 0/1/2/3):
  0 - OK (no new dead code, no stale baseline entries)
  3 - New dead code detected (finding not in baseline)
  4 - Stale baseline entry (baseline line no longer reported)
  5 - Vulture error (unexpected exit code or unparseable output)

Usage:
  uv run python scripts/vulture_gate.py [--min-confidence N] [--help]
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MIN_CONFIDENCE = 80
VULTURE_OK_CODES = {0, 3}  # 0=no dead code, 3=dead code found

# Vulture report line: path:line: message (confidence% confidence[, N lines])
REPORT_RE = re.compile(
    r"^(?P<file>[^:]+):(?P<line>\d+):\s+"
    r"(?P<message>.+?)\s+"
    r"\((?P<confidence>\d+)% confidence(?:, \d+ lines)?\)\s*$"
)

# Named-items extractor: "unused variable 'name'" / "unused import 'name'" / etc.
NAMED_RE = re.compile(r"^unused\s+(?P<kind>\w+)\s+'(?P<name>[^']+)'$")

# Baseline named entry:  name  # unused kind (file:line)
BASELINE_NAMED_RE = re.compile(
    r"^(?P<name>\S+)\s+#\s+unused\s+(?P<kind>\w+)\s+"
    r"\((?P<file>.+?):(?P<line>\d+)\)\s*$"
)

# Baseline structural entry:  # message (file:line)
BASELINE_STRUCT_RE = re.compile(
    r"^\s*#\s+(?P<message>.+?)\s+"
    r"\((?P<file>.+?):(?P<line>\d+)\)\s*$"
)


def _make_key(file: str, line: int, name_or_kind: str) -> tuple:
    return (file, line, name_or_kind)


def parse_vulture_output(output: str):
    """Parse Vulture stdout into set of (file, line, name_or_kind) triples."""
    findings = set()
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = REPORT_RE.match(line)
        if m is None:
            print(f"[VULTURE-ERROR] Unparseable Vulture output: {line}",
                  file=sys.stderr)
            sys.exit(5)
        file = m.group("file")
        lineno = int(m.group("line"))
        message = m.group("message")
        # Check if named
        nm = NAMED_RE.match(message)
        if nm:
            name_or_kind = nm.group("name")
        else:
            name_or_kind = message  # structural: "unreachable code after 'return'" etc.
        findings.add(_make_key(file, lineno, name_or_kind))
    return findings


def parse_baseline(filepath: Path):
    """Parse deadcode-baseline.py into set of (file, line, name_or_kind) triples."""
    entries = set()
    with open(filepath) as f:
        for raw_line in f:
            line = raw_line.rstrip()
            if not line or line.startswith("#") and "(" not in line:
                continue  # header comment or blank line
            # Try named entry first
            nm = BASELINE_NAMED_RE.match(line)
            if nm:
                entries.add(_make_key(nm.group("file"), int(nm.group("line")),
                                      nm.group("name")))
                continue
            # Try structural entry
            sm = BASELINE_STRUCT_RE.match(line)
            if sm:
                message = sm.group("message")
                entries.add(_make_key(sm.group("file"), int(sm.group("line")),
                                      message))
                continue
            # If neither matched, fail loudly
            print(f"[VULTURE-ERROR] Unparseable line in deadcode-baseline.py: {line}",
                  file=sys.stderr)
            sys.exit(5)
    return entries


def run_vulture(packages_dir: Path, baseline_path: Path | None,
                min_confidence: int):
    """Run vulture and return (exit_code, stdout)."""
    args = ["uv", "run", "vulture", str(packages_dir)]
    if baseline_path is not None:
        args.append(str(baseline_path))
    args.extend(["--min-confidence", str(min_confidence)])
    result = subprocess.run(
        args, capture_output=True, text=True,
        cwd=str(REPO_ROOT)
    )
    if result.stderr:
        # Vulture writes syntax warnings to stderr; these are informational.
        # Only print if verbose/debug needed.
        pass
    if result.returncode not in VULTURE_OK_CODES:
        print(f"[VULTURE-ERROR] Vulture exited with unexpected code "
              f"{result.returncode}", file=sys.stderr)
        sys.exit(5)
    return result.returncode, result.stdout


def _format_finding(file: str, line: int, name_or_kind: str) -> str:
    return f"  {file}:{line}: {name_or_kind}"


def main():
    parser = argparse.ArgumentParser(
        description="Vulture dead-code gate: diff reported findings "
                    "against deadcode-baseline.py"
    )
    parser.add_argument("--min-confidence", type=int, default=DEFAULT_MIN_CONFIDENCE,
                        help=f"Minimum confidence threshold (default: "
                             f"{DEFAULT_MIN_CONFIDENCE})")
    args = parser.parse_args()

    packages_dir = REPO_ROOT / "packages"
    baseline_path = REPO_ROOT / "deadcode-baseline.py"

    if not packages_dir.is_dir():
        print(f"[VULTURE-ERROR] packages/ directory not found at {packages_dir}",
              file=sys.stderr)
        sys.exit(5)

    if not baseline_path.is_file():
        print(f"[VULTURE-ERROR] deadcode-baseline.py not found at {baseline_path}",
              file=sys.stderr)
        sys.exit(5)

    # 1. Raw run: without baseline (capture all current findings)
    _, raw_stdout = run_vulture(packages_dir, None, args.min_confidence)
    raw = parse_vulture_output(raw_stdout)

    # 2. Reported run: with baseline (capture findings not name-suppressed)
    _, reported_stdout = run_vulture(packages_dir, baseline_path,
                                     args.min_confidence)
    reported = parse_vulture_output(reported_stdout)

    # 3. Parse baseline
    baseline = parse_baseline(baseline_path)

    # 4. Diff into buckets
    new = reported - baseline        # Findings not in baseline → new dead code
    stale = baseline - raw           # Baseline entries no longer reported → stale
    matched = raw & baseline         # Present in both → known, suppressed

    # 5. Report
    summary_lines = []
    exit_code = 0

    if stale:
        print("=== STALE BASELINE ENTRIES (remove these lines from "
              "deadcode-baseline.py) ===")
        for s in sorted(stale):
            line = _format_finding(*s)
            print(line)
            summary_lines.append(f"- STALE: {line}")
        print()
        exit_code = 4

    if new:
        print("=== NEW DEAD CODE (not in baseline) ===")
        for n in sorted(new):
            line = _format_finding(*n)
            print(line)
            summary_lines.append(f"- NEW: {line}")
        print()
        exit_code = 3  # new dead code takes precedence over stale for exit code

    # GitHub step summary
    gh_summary = None
    import os
    gh_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if gh_summary_path:
        gh_summary = open(gh_summary_path, "a")

    if exit_code == 0:
        msg = f"Vulture gate PASSED — {len(matched)} known finding(s) suppressed, "
        msg += f"0 new, 0 stale"
        print(msg)
        if gh_summary:
            gh_summary.write(f"### Vulture Dead-Code Gate\n{msg}\n")
    else:
        if exit_code == 3:
            bucket_name = "NEW dead code"
        else:
            bucket_name = "STALE baseline entries"
        print(f"Vulture gate FAILED ({bucket_name})")
        if gh_summary:
            gh_summary.write(f"### Vulture Dead-Code Gate :x:\n")
            gh_summary.write(f"**{bucket_name}**\n")
            for s in summary_lines:
                gh_summary.write(f"{s}\n")
            gh_summary.write(f"\nKnown (suppressed): {len(matched)} entries\n")

    if gh_summary:
        gh_summary.close()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
