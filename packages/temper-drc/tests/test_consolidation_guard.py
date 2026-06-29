"""CI guard test for the N5 script consolidation.

Verifies that deleted duplicate scripts are not re-introduced and
that no tracker caller references them outside of docs/ files.
"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

DENYLIST_FILES = [
    "scripts/strip_routing.py",
    "scripts/strip_routing_v2.py",
    "scripts/strip_routing_kiutils.py",
    "run_router_v6_minimal.py",
    "run_router_v6_simple.py",
    "run_router_v6_baseline.py",
    "batch_validate_power_pcb_fixed.py",
]

EXEMPT_DIRS = {
    "docs/brainstorms/",
    "docs/plans/",
    "docs/consolidation-log.md",
    "packages/temper-drc/tests/test_consolidation_guard.py",
    "packages/temper-placer/tests/test_strip_routing_consolidation.py",
    "power_pcb_dataset/validation_reports/",
}


def _run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    return result.stdout.strip()


class TestDeletedFilesNotTracked:
    """Assert none of the 7 deleted files are tracked by git."""

    def test_no_denylist_files_tracked(self):
        output = _run(["git", "ls-files"] + DENYLIST_FILES)
        assert output == "", (
            f"Deleted files are still tracked by git:\n{output}"
            f"\nThese should not exist. See docs/consolidation-log.md."
        )


class TestNoReferencesOutsideDocs:
    """Assert no tracked file outside docs/ references the deleted filenames."""

    def test_no_grep_hits_for_denylist_basenames(self):
        for basename in DENYLIST_FILES:
            # Search for the basename in all tracked files
            result = subprocess.run(
                ["git", "grep", "-l", "--fixed-strings", basename],
                capture_output=True, text=True, cwd=REPO_ROOT,
            )
            hits = result.stdout.strip().split("\n") if result.stdout.strip() else []
            offending = [h for h in hits if not any(h.startswith(e) for e in EXEMPT_DIRS)]
            assert not offending, (
                f"Reference to deleted script '{basename}' found in:\n"
                + "\n".join(f"  {h}" for h in offending)
                + "\nUse the canonical survivor (see docs/consolidation-log.md)."
            )

    def test_no_strip_routing_v2_reference(self):
        result = subprocess.run(
            ["git", "grep", "-l", "--fixed-strings", "scripts/strip_routing_v2.py"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        hits = result.stdout.strip().split("\n") if result.stdout.strip() else []
        offending = [h for h in hits if not any(h.startswith(e) for e in EXEMPT_DIRS)]
        assert not offending, (
            f"Reference to deleted script 'strip_routing_v2.py'"
            f" — use canonical strip_routing() (see docs/consolidation-log.md)."
            f"\nFound in: {offending}"
        )

    def test_no_run_router_v6_wrapper_references(self):
        wrappers = [
            "run_router_v6_minimal.py",
            "run_router_v6_simple.py",
            "run_router_v6_baseline.py",
        ]
        for wrapper in wrappers:
            result = subprocess.run(
                ["git", "grep", "-l", "--fixed-strings", wrapper],
                capture_output=True, text=True, cwd=REPO_ROOT,
            )
            hits = result.stdout.strip().split("\n") if result.stdout.strip() else []
            offending = [h for h in hits if not any(h.startswith(e) for e in EXEMPT_DIRS)]
            assert not offending, (
                f"Reference to deleted script '{wrapper}'"
                f" — use run_router_v6.py (see docs/consolidation-log.md)."
                f"\nFound in: {offending}"
            )
