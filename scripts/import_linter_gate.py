#!/usr/bin/env python3
"""Import-linter boundary enforcement CI gate.

Wraps import-linter (lint-imports), applies an allowlist, and fails directly
on any unallowlisted violation. (Previously diffed against a ratchet baseline
file, import-linter-baseline.yaml; that baseline sat empty for 32 days
(2026-06-23 -> 2026-07-25) and was collapsed per
docs/plans/2026-07-25-002-refactor-baseline-burndown-plan.md R4 — the
"zero violations" contract is now asserted directly instead of diffed
against a committed empty file.)

Every lint-imports run is classified into exactly one of three states
(see `classify_lint_report`): "clean" (0 contracts broken), "contracts_broken"
(>=1 contract broken with parseable violation detail -- the expected failure
mode), or "tool_error" (crash, bad config, missing module, or any output that
doesn't match the tool's own completion markers). Only "clean" may exit 0.
A crash used to be silently read as "0 violations" because the violation
parser found no violation-shaped lines in crash output; classification is
now driven by whether the report's completion markers are present at all,
so it fails closed on unknown-shaped crashes too.

Exit codes:
  0 - OK (state == clean, WARNING-only mode, or all violations allowed)
  3 - New boundary violation (not allowlisted; state == contracts_broken)
  5 - Gate script error (state == tool_error: tool failure, missing config,
      missing module, unparseable output, etc.)

Soft-launch (R14): Before CUTOVER_DATE, violations print as warnings and exit 0.
After CUTOVER_DATE, new violations exit non-zero (merge-blocking). This
soft-launch window applies only to contracts_broken; tool_error always
exits 5 regardless of date.

Usage:
  uv run python scripts/import_linter_gate.py [--help]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import datetime
import re
import subprocess

from _lib.repo import find_repo_root
from _lib.github_summary import get_github_summary_path

REPO_ROOT = find_repo_root()

# R14: 2-week WARNING-only soft-launch
CUTOVER_DATE = datetime.date(2026, 7, 6)

# Regex to parse import-linter violation headers
VIOLATION_HEADER_RE = re.compile(
    r"^(?P<source>[\w.]+)\s+is\s+not\s+allowed\s+to\s+import\s+(?P<target>[\w.]+):$"
)


def parse_violations(output: str) -> dict[str, set[tuple[str, str]]]:
    """Parse import-linter output into {contract_name: set[(source, target)]} violations."""
    violations: dict[str, set[tuple[str, str]]] = {}
    lines = output.splitlines()
    current_contract = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip art lines and blank lines
        if not stripped or stripped.startswith("\u2554") or stripped.startswith("\u2566"):
            continue
        if stripped.startswith("\u2500") or stripped.startswith("\u2514"):
            continue

        # Check if this is a contract header (name followed by dashes)
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if not next_line:
                # A blank line can never be a "----" separator; nothing to
                # check it against, so don't even ask all() to decide (an
                # empty next_line would otherwise make the all() below
                # vacuously True and misclassify a blank line as a
                # contract-header separator).
                pass
            elif all(c == "-" for c in next_line):
                # Skip known non-contract headers
                if stripped not in (
                    "Contracts",
                    "Broken contracts",
                    "",
                    "--------",
                ):
                    if " -> " not in stripped and "is not allowed" not in stripped:
                        if "Syntax error" not in stripped and "Could not find" not in stripped:
                            current_contract = stripped
                            continue

        # Check for violation headers
        m = VIOLATION_HEADER_RE.match(stripped)
        if m:
            if current_contract:
                violations.setdefault(current_contract, set()).add(
                    (m.group("source"), m.group("target"))
                )
            continue

    return violations


def parse_syntax_errors(output: str) -> list[str]:
    """Extract syntax error lines from import-linter output (diagnostic detail only)."""
    errors = []
    for line in output.splitlines():
        if "Syntax error" in line:
            errors.append(line.strip())
    return errors


# Markers that indicate lint-imports actually completed its analysis and
# printed its standard report, as opposed to crashing before it got that far
# (stale module in the config, a syntax error in scanned source, or any
# other tool-level failure). Classification is anchored on the tool's own
# completion markers -- not on substring-matching specific known crash
# messages ("does not exist", "Syntax error", ...) -- so a *new*,
# never-seen crash shape is caught by construction instead of silently
# reading as "0 violations found". That silent misread was the actual bug:
# a crash prints no violation-shaped lines, `parse_violations()` returns an
# empty dict, and an empty dict used to be indistinguishable from a clean
# run.
ANALYZED_RE = re.compile(r"^Analyzed \d+ files?, \d+ dependenc(?:y|ies)\.\s*$", re.MULTILINE)
CONTRACTS_SUMMARY_RE = re.compile(
    r"^Contracts:\s+(?P<kept>\d+)\s+kept,\s+(?P<broken>\d+)\s+broken\.\s*$",
    re.MULTILINE,
)


class LintOutcome:
    """Result of classifying one lint-imports run.

    `state` is exactly one of three mutually exclusive, exhaustive values:

      "clean"            - report parsed; 0 contracts broken; exit 0.
                            The only state allowed to make the gate exit 0.
      "contracts_broken" - report parsed; >=1 contract broken, with at
                            least one parsed violation edge. This is the
                            expected failure mode of a working gate.
      "tool_error"        - anything else: crash, bad config, missing
                            module, unparseable output, or an exit code
                            inconsistent with what the parsed report says
                            (e.g. "0 broken" but nonzero exit, or ">0
                            broken" but exit 0). Never treated as "0
                            violations" and never allowed to exit 0.
    """

    def __init__(self, state, *, kept=None, broken=None, violations=None, reason=""):
        self.state = state
        self.kept = kept
        self.broken = broken
        self.violations = violations or {}
        self.reason = reason


def classify_lint_report(exit_code: int, output: str) -> LintOutcome:
    """Classify a lint-imports run as clean, contracts_broken, or tool_error.

    Fixes the defect where lint-imports crashing (stale module referenced
    in config, syntax error in scanned source, etc.) printed no
    violation-shaped lines; `parse_violations()` returned an empty dict;
    and an empty dict of violations was indistinguishable from "0
    violations" -- so the gate printed PASSED on a crash.

    Classification requires the tool's own completion markers ("Analyzed N
    files...", "Contracts: X kept, Y broken.") to be present AND the exit
    code to be consistent with what they say. Anything that fails either
    check is a tool error, never a pass.
    """
    analyzed = ANALYZED_RE.search(output)
    summary = CONTRACTS_SUMMARY_RE.search(output)

    if not analyzed or not summary:
        return LintOutcome(
            state="tool_error",
            reason=(
                "lint-imports output does not contain the expected "
                "'Analyzed N files...' / 'Contracts: X kept, Y broken.' "
                "completion markers -- the tool did not finish a normal "
                f"run (exit code {exit_code})."
            ),
        )

    kept = int(summary.group("kept"))
    broken = int(summary.group("broken"))

    if broken == 0:
        if exit_code != 0:
            return LintOutcome(
                state="tool_error",
                kept=kept,
                broken=broken,
                reason=(
                    f"lint-imports reported 0 broken contracts but exited "
                    f"{exit_code} (expected 0 for a clean run)."
                ),
            )
        return LintOutcome(state="clean", kept=kept, broken=broken)

    if exit_code == 0:
        return LintOutcome(
            state="tool_error",
            kept=kept,
            broken=broken,
            reason=(
                f"lint-imports reported {broken} broken contract(s) but "
                "exited 0 (expected non-zero for a broken-contracts run)."
            ),
        )

    violations = parse_violations(output)
    total_edges = sum(len(v) for v in violations.values())
    if total_edges == 0:
        # Anti-vacuous-truth guard (METHODOLOGY.md failure class 4): the
        # report says contracts are broken, so zero parsed violation edges
        # means our parser drifted from the tool's output format -- not
        # that there is nothing to report.
        return LintOutcome(
            state="tool_error",
            kept=kept,
            broken=broken,
            reason=(
                f"lint-imports reported {broken} broken contract(s) but no "
                "violation detail lines could be parsed from its output "
                "(parser drift or an output-format change)."
            ),
        )

    return LintOutcome(
        state="contracts_broken", kept=kept, broken=broken, violations=violations
    )


def load_yaml_allowlist(filepath: Path) -> set[tuple[str, str, str]]:
    """Load allowlist as set of (source, target, contract) tuples."""
    import yaml

    if not filepath.is_file():
        return set()
    with open(filepath) as f:
        try:
            data = yaml.safe_load(f)
        except Exception:
            return set()
    if not data or not isinstance(data, dict):
        return set()
    entries = data.get("allowlist", [])
    result = set()
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and all(
                k in entry for k in ("source", "target", "contract")
            ):
                result.add((entry["source"], entry["target"], entry["contract"]))
    return result


def matches_allowlist(
    source: str,
    target: str,
    contract: str,
    allowlist: set[tuple[str, str, str]],
) -> bool:
    """Check if a violation matches any allowlist entry (with regex support)."""
    for asrc, atgt, actr in allowlist:
        try:
            if (
                re.fullmatch(asrc, source)
                and re.fullmatch(atgt, target)
                and re.fullmatch(actr, contract)
            ):
                return True
        except re.error:
            if asrc == source and atgt == target and actr == contract:
                return True
    return False


# Phase 3 (plan 2026-06-22-014): top-level directories that import from
# temper_placer internals. These aren't Python packages so import-linter
# doesn't scan them natively. The gate has a separate code path that
# scans these dirs directly and checks against the per-file allowlist.
PHASE3_DIRS = ("tools", "simulation")
PHASE3_CONTRACT = "phase3-public-interface-only"

# Regex to find `import temper_placer.X` or `from temper_placer.X import ...` at
# module top level. (Skips indented imports — those are inside if blocks.)
# Two alternatives, each with its own capture group; we use whichever is non-None.
TP_IMPORT_RE = re.compile(
    r"^(?:from\s+temper_placer\.(\S+)\s+import|import\s+temper_placer\.(\S+))",
    re.MULTILINE,
)


def scan_phase3_imports(
    repo_root: Path,
    dirs: tuple[str, ...] = PHASE3_DIRS,
) -> set[tuple[str, str, str]]:
    """Scan tools/, simulation/, etc. for temper_placer imports.

    Returns a set of (file, target_module, contract) tuples representing
    every temper_placer.* import found in the scanned directories.
    """
    found: set[tuple[str, str, str]] = set()
    for d in dirs:
        dpath = repo_root / d
        if not dpath.is_dir():
            continue
        for f in dpath.rglob("*.py"):
            if "__pycache__" in f.parts:
                continue
            try:
                content = f.read_text()
            except (UnicodeDecodeError, OSError):
                continue
            for m in TP_IMPORT_RE.finditer(content):
                # Either group 1 (from import) or group 2 (import) is set;
                # pick whichever is non-None.
                module = m.group(1) or m.group(2)
                if module is None:
                    # `import temper_placer` (the root) - no enforcement
                    continue
                # target is the full submodule path (e.g. "core.board")
                target = "temper_placer." + module
                rel_file = str(f.relative_to(repo_root))
                found.add((rel_file, target, PHASE3_CONTRACT))
    return found


def check_phase3_compliance(
    current_edges: set[tuple[str, str, str]],
    allowlist: set[tuple[str, str, str]],
) -> tuple[set, set, set]:
    """Compare scanned phase3 imports against the allowlist.

    Returns (new_violations, allowed, unmatched_allowlist_entries).
    """
    allowed: set[tuple[str, str, str]] = set()
    new_violations: set[tuple[str, str, str]] = set()
    for edge in current_edges:
        if matches_allowlist(*edge, allowlist):
            allowed.add(edge)
        else:
            new_violations.add(edge)
    return new_violations, allowed, set()


def run_lint_imports(config_path: str) -> tuple[int, str]:
    """Run import-linter and return (exit_code, combined stdout+stderr)."""
    args = ["uv", "run", "lint-imports", "--config", config_path]
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    return result.returncode, result.stdout + "\n" + result.stderr


def format_remediation(source: str, target: str, contract: str) -> list[str]:
    """Generate R16-compliant remediation messages."""
    messages = []
    messages.append(f"  Boundary rule: {contract}")
    top_module = ".".join(target.split(".")[:2])
    messages.append(
        f"  Option A: Use the public interface at '{top_module}' "
        f"instead of '{target}'"
    )
    messages.append(
        "  Option B: Add an allowlist entry to "
        "'import-linter-allowlist.yaml' with justification + ticket reference"
    )
    return messages


def main():
    parser = argparse.ArgumentParser(
        description="Import-linter boundary enforcement CI gate"
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(REPO_ROOT / ".importlinter"),
        help="Path to import-linter config file",
    )
    parser.add_argument(
        "--allowlist",
        type=str,
        default=str(REPO_ROOT / "import-linter-allowlist.yaml"),
        help="Path to monotonic-shrinking allowlist",
    )
    args = parser.parse_args()

    config_path = args.config
    allowlist_path = Path(args.allowlist)

    if not Path(config_path).is_file():
        print(
            f"[IMPORT-LINTER-ERROR] Config not found: {config_path}",
            file=sys.stderr,
        )
        sys.exit(5)

    is_warning_mode = datetime.date.today() < CUTOVER_DATE
    mode = "warn" if is_warning_mode else "block"

    # Run import-linter
    exit_code, output = run_lint_imports(config_path)

    outcome = classify_lint_report(exit_code, output)

    if outcome.state == "tool_error":
        # A tool error (crash, bad config, missing module, unparseable
        # output) is never a pass and is never silently swallowed: the
        # full raw stdout+stderr from lint-imports is echoed below, and
        # this path always exits non-zero regardless of warn/block mode --
        # the soft-launch warn window only ever applied to *violations*,
        # not to the tool failing to run at all.
        print("=== IMPORT-LINTER TOOL ERROR ===", file=sys.stderr)
        print(
            "GATE RESULT: ERROR — not PASSED, not a contract violation. "
            "lint-imports did not complete a normal run.",
            file=sys.stderr,
        )
        print(f"Reason: {outcome.reason}", file=sys.stderr)
        print(f"lint-imports exit code: {exit_code}", file=sys.stderr)
        extra_syntax_errors = parse_syntax_errors(output)
        if extra_syntax_errors:
            print("Syntax errors detected in scanned source:", file=sys.stderr)
            for err in extra_syntax_errors:
                print(f"  {err}", file=sys.stderr)
        print("--- raw lint-imports output (stdout+stderr) ---", file=sys.stderr)
        print(output, file=sys.stderr)
        print("--- end raw output ---", file=sys.stderr)

        gh_summary_path = get_github_summary_path()
        if gh_summary_path:
            with open(gh_summary_path, "a") as gh_summary:
                gh_summary.write("### Import Boundary Enforcement — TOOL ERROR\n")
                gh_summary.write(
                    f"`lint-imports` exited {exit_code} without producing a "
                    "parseable contracts report.\n\n"
                )
                gh_summary.write(f"Reason: {outcome.reason}\n\n")
                gh_summary.write("```\n" + output + "\n```\n")

        sys.exit(5)

    # outcome.state is "clean" or "contracts_broken" here.
    print(
        f"lint-imports report: {outcome.kept} kept, {outcome.broken} broken "
        f"(exit code {exit_code})."
    )

    # Parse violations from output (empty dict for the clean state)
    current_violations = outcome.violations

    # Load allowlist
    allowlist_raw = load_yaml_allowlist(allowlist_path)

    # Flatten current violations into (source, target, contract) tuples
    current_edges: set[tuple[str, str, str]] = set()
    for contract_name, edges in current_violations.items():
        for src, tgt in edges:
            current_edges.add((src, tgt, contract_name))

    # Compute buckets
    allowed_edges: set[tuple[str, str, str]] = set()
    for edge in current_edges:
        if matches_allowlist(*edge, allowlist_raw):
            allowed_edges.add(edge)

    new_violations = current_edges - allowed_edges

    # Phase 3: scan tools/, simulation/
    # for temper_placer.* imports. These dirs aren't Python packages, so
    # import-linter doesn't scan them natively. The allowlist has per-file
    # entries matching the current import surface; new imports fail the gate.
    phase3_current = scan_phase3_imports(REPO_ROOT)
    phase3_new, phase3_allowed, _ = check_phase3_compliance(
        phase3_current, allowlist_raw
    )
    if phase3_current:
        print(
            "\n=== PHASE 3 SCAN: tools/, simulation/ ==="
        )
        print(
            f"  Found {len(phase3_current)} temper_placer.* imports across "
            f"{len({e[0] for e in phase3_current})} files"
        )
        print(f"  Allowlisted (per-file): {len(phase3_allowed)}")
        print(f"  New violations: {len(phase3_new)}")
        if phase3_new:
            new_violations |= phase3_new
            print(
                "\n  Add per-file entries to import-linter-allowlist.yaml "
                "for these imports:"
            )
            for src, tgt, _ in sorted(phase3_new)[:20]:
                print(f"    - source: {src}  target: {tgt}")
            if len(phase3_new) > 20:
                print(f"    ... and {len(phase3_new) - 20} more")

    # GitHub step summary
    gh_summary_path = get_github_summary_path()
    gh_summary = open(gh_summary_path, "a") if gh_summary_path else None

    exit_code_out = 0

    if mode == "warn":
        header = (
            f"Import boundary enforcement is in WARNING-ONLY mode "
            f"until {CUTOVER_DATE}. "
            f"After that date, violations will block PR merge."
        )
    else:
        header = "Import boundary enforcement — violations will block PR merge."

    print(header)
    if gh_summary:
        gh_summary.write(
            f"### Import Boundary Enforcement ({mode.upper()} mode)\n"
        )
        if is_warning_mode:
            gh_summary.write(f"> Warning-only until {CUTOVER_DATE}\n\n")

    if new_violations:
        print(
            f"\n=== NEW IMPORT BOUNDARY VIOLATIONS "
            f"({len(new_violations)}) ==="
        )
        for src, tgt, contract in sorted(new_violations)[:30]:
            print(f"\n  {src} imports {tgt}")
            for msg in format_remediation(src, tgt, contract):
                print(msg)
        if len(new_violations) > 30:
            print(f"\n  ... and {len(new_violations) - 30} more")

        if mode == "block":
            exit_code_out = 3

        if gh_summary:
            gh_summary.write(
                f"**NEW violations ({len(new_violations)}):**\n"
            )
            for src, tgt, contract in sorted(new_violations):
                gh_summary.write(
                    f"- `{src}` -> `{tgt}` (contract: `{contract}`)\n"
                )

    if allowed_edges:
        print(
            f"\n=== ALLOWLISTED VIOLATIONS — "
            f"{len(allowed_edges)} suppressed ==="
        )

    if exit_code_out == 0 and not new_violations:
        print("\nImport boundary gate PASSED — 0 new violations")
        if gh_summary:
            gh_summary.write("**PASSED** — 0 new violations\n")

    if gh_summary:
        gh_summary.close()

    sys.exit(exit_code_out)


if __name__ == "__main__":
    main()
