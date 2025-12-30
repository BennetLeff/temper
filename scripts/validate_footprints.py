#!/usr/bin/env python3
"""
Footprint validation script for KiCad .kicad_mod files.
Identifies common issues like negative clearance, missing courtyards, and malformed S-expressions.
"""

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class FootprintIssue:
    """Immutable record of a footprint validation error."""
    footprint: str
    severity: str  # "error" | "warning"
    issue_type: str
    message: str
    fix_available: bool = False


def validate_footprint_file(fp_path: Path) -> List[FootprintIssue]:
    """Check single footprint for common issues.

    Returns list of issues (empty if valid).
    """
    issues = []
    try:
        content = fp_path.read_text()
    except Exception as e:
        return [FootprintIssue(
            footprint=fp_path.stem,
            severity="error",
            issue_type="read_error",
            message=f"Could not read file: {e}",
            fix_available=False
        )]

    # Check 1: Pad clearance values
    # Matches both (clearance 0.1) and (clearance -0.1)
    # We look for clearance in the whole file (can be at module level or pad level)
    for match in re.finditer(r'\(clearance\s+(-?\d+\.?\d*)\)', content):
        clearance = float(match.group(1))
        if clearance < 0:
            issues.append(FootprintIssue(
                footprint=fp_path.stem,
                severity="error",
                issue_type="negative_clearance",
                message=f"Negative clearance {clearance}mm",
                fix_available=True
            ))
        elif clearance > 5.0:
            issues.append(FootprintIssue(
                footprint=fp_path.stem,
                severity="warning",
                issue_type="excessive_clearance",
                message=f"Unusually large clearance {clearance}mm"
            ))

    # Check 2: Courtyard existence
    # courtyards are usually on F.CrtYd or B.CrtYd layers
    if "F.CrtYd" not in content and "B.CrtYd" not in content:
        issues.append(FootprintIssue(
            footprint=fp_path.stem,
            severity="warning",
            issue_type="missing_courtyard",
            message="No courtyard defined (recommended for DRC)",
            fix_available=False
        ))

    # Check 3: S-expression syntax (basic parenthesis balance)
    if content.count("(") != content.count(")"):
        issues.append(FootprintIssue(
            footprint=fp_path.stem,
            severity="error",
            issue_type="malformed_sexpr",
            message="Unbalanced parentheses",
            fix_available=False
        ))

    return issues


def auto_fix_issue(fp_path: Path, issue: FootprintIssue) -> bool:
    """Attempt to automatically fix footprint issue.

    Returns True if fixed, False if manual intervention needed.
    """
    if not issue.fix_available:
        return False

    try:
        content = fp_path.read_text()
    except Exception:
        return False

    if issue.issue_type == "negative_clearance":
        # Replace negative clearance with sensible default (0.2mm)
        # Using a regex that specifically targets the negative ones
        fixed = re.sub(
            r'\(clearance\s+-\d+\.?\d*\)',
            '(clearance 0.2)',
            content
        )
        if fixed != content:
            fp_path.write_text(fixed)
            return True

    return False


def validate_and_fix_footprints(footprint_dir: Path, auto_fix: bool = False) -> dict:
    """Validate all footprints in directory and optionally fix issues.

    Returns a summary dictionary.
    """
    if not footprint_dir.exists():
        return {
            "total": 0,
            "errors": 0,
            "warnings": 0,
            "fixed": 0,
            "issues": [FootprintIssue(
                footprint=str(footprint_dir),
                severity="error",
                issue_type="dir_not_found",
                message=f"Directory not found: {footprint_dir}"
            )]
        }

    fp_files = list(footprint_dir.glob("*.kicad_mod"))
    # Also look in .pretty directories if a parent dir was given
    if not fp_files and footprint_dir.suffix != ".pretty":
        fp_files = list(footprint_dir.glob("**/*.kicad_mod"))

    all_issues = []
    fixed_count = 0

    for fp_file in fp_files:
        issues = validate_footprint_file(fp_file)
        
        if auto_fix:
            current_fp_fixed = False
            for issue in issues:
                if auto_fix_issue(fp_file, issue):
                    current_fp_fixed = True
                    # Re-validate to clear the fixed issue from reporting
                    # (Simple approach: just don't add the fixed one to all_issues)
                else:
                    all_issues.append(issue)
            if current_fp_fixed:
                fixed_count += 1
        else:
            all_issues.extend(issues)

    errors = [i for i in all_issues if i.severity == "error"]
    warnings = [i for i in all_issues if i.severity == "warning"]

    return {
        "total": len(fp_files),
        "errors": len(errors),
        "warnings": len(warnings),
        "fixed": fixed_count,
        "issues": all_issues
    }


def main():
    parser = argparse.ArgumentParser(description="Validate KiCad footprints.")
    parser.add_argument("footprint_dir", type=Path, help="Directory containing .kicad_mod files")
    parser.add_argument("--fix", action="store_true", help="Auto-fix issues")
    args = parser.parse_args()

    results = validate_and_fix_footprints(args.footprint_dir, auto_fix=args.fix)

    print(f"\n📊 Footprint Validation Results:")
    print(f"  Total footprints: {results['total']}")
    print(f"  Errors: {results['errors']}")
    print(f"  Warnings: {results['warnings']}")
    print(f"  Auto-fixed: {results['fixed']}")

    if results['issues']:
        print("\n⚠️  Issues found:")
        # Show first 20
        for issue in results['issues'][:20]:
            print(f"  [{issue.severity.upper()}] {issue.footprint}: {issue.message} ({issue.issue_type})")
        
        if len(results['issues']) > 20:
            print(f"  ... and {len(results['issues']) - 20} more.")

    if results['errors'] > 0 and not args.fix:
        exit(1)
    exit(0)


if __name__ == "__main__":
    main()
