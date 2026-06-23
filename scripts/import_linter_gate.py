#!/usr/bin/env python3
"""Import-linter boundary enforcement CI gate.

Wraps import-linter (lint-imports), diffs violations against a ratchet baseline,
applies an allowlist, and enforces a monotonic-shrinking ratchet.

Exit codes:
  0 - OK (no new violations, WARNING-only mode, or all violations baseline/allowed)
  3 - New boundary violation (not in baseline or allowlist)
  5 - Gate script error (tool failure, missing config, etc.)

Soft-launch (R14): Before CUTOVER_DATE, violations print as warnings and exit 0.
After CUTOVER_DATE, new violations exit non-zero (merge-blocking).

Usage:
  uv run python scripts/import_linter_gate.py [--help]
"""

import argparse
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

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
            if next_line and all(c == "-" for c in next_line):
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
    """Extract syntax error lines from import-linter output."""
    errors = []
    for line in output.splitlines():
        if "Syntax error" in line:
            errors.append(line.strip())
    return errors


def load_yaml_set(filepath: Path) -> set[tuple[str, str, str]]:
    """Load a YAML file as set of (source, target, contract) tuples."""
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
    entries = data.get("violations", [])
    result = set()
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and all(
                k in entry for k in ("source", "target", "contract")
            ):
                result.add((entry["source"], entry["target"], entry["contract"]))
    return result


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
PHASE3_DIRS = ("tools", "experiments", "simulation", "router-experiments")
PHASE3_CONTRACT = "phase3-public-interface-only"

# Regex to find `import temper_placer.X` or `from temper_placer.X import ...` at
# module top level. (Skips indented imports — those are inside if blocks.)
TP_IMPORT_RE = re.compile(
    r"^(?:from\s+temper_placer(?:\.(\S+?))?\s+import|import\s+temper_placer(?:\.(\S+?))?(?:\s+as\s+\w+)?\s*)$",
    re.MULTILINE,
)


def scan_phase3_imports(
    repo_root: Path,
    dirs: tuple[str, ...] = PHASE3_DIRS,
) -> set[tuple[str, str, str]]:
    """Scan tools/, experiments/, etc. for temper_placer imports.

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
                if m.group(1) is None:
                    # `import temper_placer` (the root) - no enforcement
                    continue
                module = m.group(1)
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
        "--baseline",
        type=str,
        default=str(REPO_ROOT / "import-linter-baseline.yaml"),
        help="Path to ratchet baseline",
    )
    parser.add_argument(
        "--allowlist",
        type=str,
        default=str(REPO_ROOT / "import-linter-allowlist.yaml"),
        help="Path to monotonic-shrinking allowlist",
    )
    args = parser.parse_args()

    config_path = args.config
    baseline_path = Path(args.baseline)
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

    syntax_errors = parse_syntax_errors(output)
    if syntax_errors and exit_code != 0:
        print("=== SYNTAX ERRORS IN SOURCE FILES ===")
        for err in syntax_errors:
            print(f"  {err}")
        if is_warning_mode:
            print("WARNING mode: syntax errors reported but not blocking.")
            sys.exit(0)
        else:
            print("ERROR: Fix syntax errors to enable boundary checking.")
            sys.exit(5)

    if exit_code == 0:
        baseline = load_yaml_set(baseline_path)
        if baseline:
            print("=== BASELINE SHRINK OPPORTUNITY ===")
            print(
                f"  {len(baseline)} baseline entries can be removed — "
                "all violations resolved!"
            )
            print("  Commit the updated (empty) baseline to ratchet tighter.")
        else:
            print("Import boundary gate PASSED — 0 violations")
        sys.exit(0)

    # Parse violations from output
    current_violations = parse_violations(output)

    # Load baseline and allowlist
    baseline = load_yaml_set(baseline_path)
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

    new_violations = current_edges - baseline - allowed_edges
    resolved_violations = baseline - current_edges
    matched_violations = current_edges & baseline

    # Phase 3: scan tools/, experiments/, simulation/, router-experiments/
    # for temper_placer.* imports. These dirs aren't Python packages, so
    # import-linter doesn't scan them natively. The allowlist has per-file
    # entries matching the current import surface; new imports fail the gate.
    phase3_current = scan_phase3_imports(REPO_ROOT)
    phase3_new, phase3_allowed, _ = check_phase3_compliance(
        phase3_current, allowlist_raw
    )
    if phase3_current:
        print(
            f"\n=== PHASE 3 SCAN: tools/, experiments/, simulation/, "
            f"router-experiments/ ==="
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
                f"\n  Add per-file entries to import-linter-allowlist.yaml "
                f"for these imports:"
            )
            for src, tgt, _ in sorted(phase3_new)[:20]:
                print(f"    - source: {src}  target: {tgt}")
            if len(phase3_new) > 20:
                print(f"    ... and {len(phase3_new) - 20} more")

    # GitHub step summary
    gh_summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
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

    if resolved_violations:
        print(
            f"\n=== RESOLVED VIOLATIONS — BASELINE SHRINK "
            f"({len(resolved_violations)}) ==="
        )
        for src, tgt, contract in sorted(resolved_violations)[:20]:
            print(f"  {src} -> {tgt} ({contract})")
        if len(resolved_violations) > 20:
            print(f"  ... and {len(resolved_violations) - 20} more")
        print("  Commit the updated baseline to ratchet tighter.")

        if gh_summary:
            gh_summary.write(
                f"**RESOLVED ({len(resolved_violations)}):** can shrink baseline\n"
            )

    if matched_violations:
        print(
            f"\n=== KNOWN VIOLATIONS (baseline) — "
            f"{len(matched_violations)} suppressed ==="
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
