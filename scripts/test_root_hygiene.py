"""CI gate: reject root-level artifact files that should live in subdirectories.

Each category is a suffix or exact-path pattern paired with an allowlist
of legitimately-permitted root-level files. The test shells out to
``git ls-files`` from the repo root and asserts that no tracked root-level
file matches a forbidden category outside its allowlist.
"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Per-category allowlists.  Key is a suffix (e.g. "*.json") or an exact
# root name (e.g. "/10A").  Value is a frozenset of permitted root files.
_PER_GLOB_ALLOWLIST: dict[str, frozenset[str]] = {
    "*.py": frozenset(),
    "*.kicad_pcb": frozenset(),
    "*.kicad_pro": frozenset(),
    "*-drc.json": frozenset(),
    "*.stats": frozenset(),
    "*.json": frozenset({"opencode.json"}),
    "*.mesh": frozenset(),
    "*.gf": frozenset(),
}


def _root_tracked_files() -> list[str]:
    """Return all tracked files at the repo root (no ``/`` in path)."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    if not result.stdout:
        return []
    return [p for p in result.stdout.split("\0") if p and "/" not in p]


def _intended_destination(category: str) -> str:
    if category.endswith("py"):
        return "scripts/"
    if "kicad" in category or "drc" in category:
        return "pcb/"
    if category in ("*.json", "*.stats", "*.mesh", "*.gf"):
        return "a data or experiments subdirectory"
    return "a subdirectory"


def test_no_root_artifact_files() -> None:
    root_files = _root_tracked_files()

    violations: list[str] = []
    for category, allowed in sorted(_PER_GLOB_ALLOWLIST.items()):
        for fname in root_files:
            if fname in allowed:
                continue
            if category.startswith("*") and fname.endswith(category[1:]):
                dest = _intended_destination(category)
                violations.append(
                    f"  {fname}  (matches '{category}' — move to {dest})"
                )
            elif not category.startswith("*") and fname == category.lstrip("/"):
                violations.append(f"  {fname}  (matches '{category}' — move to a subdirectory)")

    assert not violations, (
        "Root contains tracked artifact files:\n"
        + "\n".join(sorted(violations))
        + "\n\nFix: git rm --cached <file>, add .gitignore pattern, "
        "and move the file to the correct subdirectory."
    )
