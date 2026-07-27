#!/usr/bin/env python3
"""Run pytest and fail if it executed fewer tests than expected.

Why this exists
---------------
Every dead test-gate found on 2026-07-27 was invisible for the same reason:
pytest reported the problem correctly and the reported count was never checked.

    pytest tests/router_v6/ tests/io/ ... tests/losses/ ...
    ERROR: file or directory not found: tests/losses/
    collected 0 items
    no tests ran in 0.02s

`tests/losses/` does not exist. pytest aborts on a missing path, so **none** of
the seven sibling directories ran either -- 3,526 collectible tests, executing
zero times, inside a `continue-on-error: true` step that discarded the non-zero
exit. Separately, `packages/temper-workflow` ran `pytest tests/` and collected 0
items because it has no test files at all.

Neither was a pytest failure. Both were a reporting failure: nobody asserted that
the suite actually ran anything. A suite that silently shrinks to zero is
indistinguishable from a suite that passes -- `docs/METHODOLOGY.md` §4, the
silently-skipped class.

This wrapper closes that hole. It runs pytest normally, then reads the JUnit XML
it produced and fails if the executed count fell below a floor recorded in the
workflow. The floor is a ratchet, not a target: raise it when the suite grows.

Counting is done from JUnit XML rather than by parsing pytest's terminal summary,
whose wording changes between versions and between `-q`/`-v`.

Usage:
    pytest_guard.py --min-tests 3000 -- tests/router_v6/ tests/io/ -q

Exit codes:
    0   pytest passed and ran at least --min-tests tests
    3   too few tests ran AND pytest was otherwise clean -- i.e. the count
        itself is the defect (silent deselection, a suite that shrank)
    *   pytest's own exit code, propagated unchanged, whenever pytest reported
        something concrete. A missing path exits 4 and a failing suite exits 1;
        both explain the low count better than 3 would, so they win.

Every non-zero path fails the build. The distinction is diagnostic, not
enforcement -- the point is that the next person reads the real cause.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

TOO_FEW = 3

# pytest's documented exit codes, so a low-count diagnosis names the real cause
# instead of guessing at one.
PYTEST_EXIT_MEANING = {
    1: "tests failed",
    2: "run interrupted",
    3: "internal error",
    4: "usage error -- typically a path that does not exist",
    5: "no tests collected",
}


def count_from_junit(xml_path: Path) -> tuple[int, int] | None:
    """Return (executed, skipped) from a JUnit XML report, or None if unreadable.

    ``executed`` deliberately excludes skips: a run where every test skipped has
    verified nothing, which is the failure mode this guard exists to catch.
    """
    try:
        root = ET.parse(xml_path).getroot()
    except (OSError, ET.ParseError):
        return None
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        return None
    total = sum(int(s.get("tests", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    return total - skipped, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--min-tests",
        type=int,
        required=True,
        help="fail if fewer than this many non-skipped tests execute",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="arguments passed through to pytest (put them after --)",
    )
    args = parser.parse_args()

    passthrough = args.pytest_args
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    if not passthrough:
        print("[pytest-guard] ERROR: no pytest arguments given", file=sys.stderr)
        return TOO_FEW

    with tempfile.TemporaryDirectory() as tmp:
        report = Path(tmp) / "report.xml"
        # Invoke pytest through the interpreter running this script, so the
        # caller's environment selection (`uv run python scripts/...`) is
        # honoured without nesting a second `uv run`.
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *passthrough, f"--junit-xml={report}"],
            check=False,
        )
        counts = count_from_junit(report)

    if counts is None:
        # No parseable report: pytest died before running anything -- a missing
        # path (exit 4), a collection abort, or a crash. This is exactly the
        # tests/losses/ case, and it must not be reported as success.
        print(
            "[pytest-guard] FAIL: pytest produced no test report at all "
            f"(pytest exit {proc.returncode}). Expected at least "
            f"{args.min_tests} tests. A missing path makes pytest abort before "
            "running ANY of the directories listed alongside it.",
            file=sys.stderr,
        )
        return TOO_FEW

    executed, skipped = counts
    if executed < args.min_tests:
        print(
            f"[pytest-guard] FAIL: only {executed} tests executed "
            f"({skipped} skipped), expected at least {args.min_tests}. "
            "Either a path in this invocation no longer exists, tests were "
            "silently deselected, or the floor needs lowering deliberately "
            "with a reason.",
            file=sys.stderr,
        )
        # A low count is sometimes a *consequence* rather than the cause --
        # `--maxfail=N` aborts early, a bad path stops pytest before it runs
        # anything. Blaming the count in those cases misattributes the problem,
        # so propagate pytest's own code and say what it means. Both paths are
        # non-zero, so CI fails either way; only the diagnosis differs.
        if proc.returncode not in (0, 5):
            print(
                f"[pytest-guard] NOTE: pytest exited {proc.returncode} "
                f"({PYTEST_EXIT_MEANING.get(proc.returncode, 'unknown')}). "
                "That is the more likely root cause; the low count follows "
                "from it. Fix that first, then re-check the floor.",
                file=sys.stderr,
            )
            return proc.returncode
        return TOO_FEW

    print(f"[pytest-guard] OK: {executed} tests executed ({skipped} skipped)")
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
