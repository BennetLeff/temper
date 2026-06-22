"""Gate test: enforce repo root hygiene by rejecting stray generated/artifact files.

This test runs ``git ls-files`` from the repository root and fails CI if any
root-level file matches forbidden suffixes (``.py``, ``.kicad_pcb``,
``.kicad_pro``, ``-drc.json``) unless it appears on an explicit allowlist.

*intended destinations:* ``scripts/`` (for ``.py``), ``pcb/`` (for ``.kicad_*``),
or an experiments directory (for ``*-drc.json``).

Imported by the existing CI step "Run temper-drc tests"
(``.github/workflows/python-tests.yml``, ``working-directory: packages/temper-drc``)
because ``packages/temper-drc/tests`` is listed in ``pyproject.toml`` ``testpaths``.
"""

import subprocess
from pathlib import Path

import pytest

# --- configuration -----------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]

# No root .py/.kicad_pcb/.kicad_pro/*-drc.json is a legitimate entry point.
# Add here only with a recorded reason; intended destinations: scripts/,
# tools/debug/, pcb/.
ALLOWLIST: frozenset[str] = frozenset()

FORBIDDEN_SUFFIXES = (".py", ".kicad_pcb", ".kicad_pro", "-drc.json")

# --- helpers -----------------------------------------------------------------

def _root_files() -> list[str]:
    """Return sorted list of git-tracked files at the repository root."""
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(p for p in result.stdout.splitlines() if "/" not in p)


def _violations(root_files: list[str]) -> list[str]:
    return [f for f in root_files if f.endswith(FORBIDDEN_SUFFIXES) and f not in ALLOWLIST]


def _message(violations: list[str]) -> str:
    hints = {
        ".py": "scripts/",
        ".kicad_pcb": "pcb/",
        ".kicad_pro": "pcb/",
        "-drc.json": "an experiments directory",
    }
    lines = [f"{len(violations)} root-level artifact(s) are tracked but forbidden:"]
    for f in violations:
        for suffix, dest in hints.items():
            if f.endswith(suffix):
                lines.append(f"  {f} -> move to {dest}")
                break
    return "\n".join(lines)

# --- tests -------------------------------------------------------------------

def test_no_root_artifacts_tracked() -> None:
    """Fail if any root-level file matches forbidden suffixes and is not in ALLOWLIST."""
    violations = _violations(_root_files())
    assert violations == [], _message(violations)
