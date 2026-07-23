#!/usr/bin/env python3
"""
CI gate: check that workflow files with a push trigger also have a pull_request trigger.

Rationale: workflows that fire post-merge but not pre-merge (only push, no pull_request)
cause the exact failure mode seen in issue #315 — PRs fly blind until merge, then break.
The fix/docker-rustup-final arc shipped 19 of 25 merges because no pre-merge CI fired on
Dockerfile-only PRs.

Opt-out: add a YAML comment ``# no-pr-trigger: <reason>`` anywhere in the file.
The script reads the raw text to detect the opt-out so it is reviewable in the PR diff.

Usage:
    python3 scripts/check_workflow_pr_triggers.py [--workflows-dir <path>]

Exit 0 if all workflows are compliant; exit 1 with a list of non-compliant workflows.
"""

import argparse
import re
import sys
from pathlib import Path

import yaml


def _preprocess_yaml(raw: str) -> str:
    """Fix YAML 1.1 boolean gotchas and GitHub Actions expressions that confuse PyYAML."""
    # YAML 1.1 interprets bare 'on' as boolean True; quote it so PyYAML keeps it as a string.
    processed = re.sub(r"^on:", "'on':", raw, flags=re.MULTILINE)
    # GitHub Actions expressions (${{ }}) contain braces that break flow-style mappings.
    processed = re.sub(r'\$\{\{.*?\}\}', '__expr__', processed)
    return processed


def _check_workflow(filepath: Path) -> tuple[bool, bool, bool] | None:
    """Parse a workflow file and return (has_push, has_pr, has_opt_out).

    Returns None if the file cannot be parsed.
    """
    raw = filepath.read_text()

    # Check for opt-out comment anywhere in the file (not just the on: block).
    has_opt_out = bool(re.search(r"#\s*no-pr-trigger:", raw))

    try:
        doc = yaml.safe_load(_preprocess_yaml(raw))
    except yaml.YAMLError:
        return None

    if not doc or not isinstance(doc, dict):
        return None

    trigger = doc.get("on")
    if trigger is None:
        return False, False, has_opt_out

    # Shorthand string: ``on: push`` or ``on: workflow_dispatch``
    if isinstance(trigger, str):
        has_push = trigger == "push"
        has_pr = trigger in ("pull_request", "pull_request_target")
        return has_push, has_pr, has_opt_out

    # Shorthand list: ``on: [push, pull_request]``
    if isinstance(trigger, list):
        has_push = "push" in trigger
        has_pr = "pull_request" in trigger or "pull_request_target" in trigger
        return has_push, has_pr, has_opt_out

    # Full block: ``on:\n  push:\n    ...``
    if isinstance(trigger, dict):
        has_push = "push" in trigger
        has_pr = "pull_request" in trigger or "pull_request_target" in trigger
        return has_push, has_pr, has_opt_out

    return False, False, has_opt_out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check GitHub Actions workflow files for missing pull_request triggers"
    )
    parser.add_argument(
        "--workflows-dir",
        type=Path,
        default=None,
        help="Path to workflows directory (default: <repo_root>/.github/workflows/)",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    workflows_dir = args.workflows_dir or (repo_root / ".github" / "workflows")

    if not workflows_dir.is_dir():
        print(f"ERROR: workflows directory not found: {workflows_dir}", file=sys.stderr)
        sys.exit(2)

    non_compliant: list[str] = []
    parse_errors: list[str] = []
    total = 0

    for filepath in sorted(workflows_dir.glob("*.yml")):
        total += 1
        result = _check_workflow(filepath)
        if result is None:
            parse_errors.append(filepath.name)
            continue

        has_push, has_pr, has_opt_out = result
        if has_push and not has_pr and not has_opt_out:
            non_compliant.append(filepath.name)

    if parse_errors:
        for name in parse_errors:
            print(f"WARNING: could not parse {name}", file=sys.stderr)

    if non_compliant:
        print("The following workflow files have a push trigger but no pull_request trigger:")
        for name in non_compliant:
            print(f"  - {name}")
        print()
        print("If this is intentional, add an opt-out comment anywhere in the file:")
        print("  # no-pr-trigger: <reason>")
        print()
        print(
            "Context: issue #315 — the fix/docker-rustup-final arc shipped 19 of 25"
            " merges because no pre-merge CI fired on Dockerfile-only PRs."
        )
        sys.exit(1)

    print(
        f"Workflow PR trigger check passed — {total} file(s) checked, all compliant"
    )


if __name__ == "__main__":
    main()
