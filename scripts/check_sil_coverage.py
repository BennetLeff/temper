#!/usr/bin/env python3
"""
CI gate: SIL fault-injection coverage (plan 2026-08-02-031, U1/U4).

Thin wrapper around firmware/test/test_sil_coverage.py --gate, following the
repo's scripts/ convention of a standalone, individually-registered gate
script (see scripts/manifest.yaml) rather than folding the check into the
firmware CMake/CTest build. The coverage matrix logic itself lives in
firmware/test/test_sil_coverage.py because it doubles as a developer tool
(run without --gate to see the matrix without failing); this wrapper is the
CI-facing entry point named per the scripts/check_*.py convention.

Usage:
    python3 scripts/check_sil_coverage.py

Exit 0 if every (fault class, origin state) pair the transition table (plus
the documented C-only interlock paths) defines is covered by a manifest.json
scenario; non-zero otherwise, naming the missing pairs.

Wired into CI (2026-08-07): invoked from .github/workflows/firmware-tests.yml
as the "SIL fault-injection coverage gate" step, immediately after the
sil_fault_tests ctest step, with no continue-on-error.
"""

import subprocess
import sys
from pathlib import Path


def main():
    repo_root = Path(__file__).resolve().parent.parent
    coverage_script = repo_root / "firmware" / "test" / "test_sil_coverage.py"

    if not coverage_script.exists():
        print(f"ERROR: {coverage_script} not found", file=sys.stderr)
        return 1

    result = subprocess.run(
        [sys.executable, str(coverage_script), "--gate"],
        cwd=repo_root,
    )
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
