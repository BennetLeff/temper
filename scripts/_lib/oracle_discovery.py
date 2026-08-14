"""Shared oracle-file discovery for the oracle content-hash registry
(``scripts/oracle_hashes.json`` / ``scripts/check_oracle_hashes.py`` /
``scripts/update_oracle_hashes.py``).

Why this module exists
-----------------------
``check_oracle_hashes.py`` (the gate) and ``update_oracle_hashes.py`` (the
generator) each used to carry their OWN copy of ``discover_oracles`` --
two independently-maintained implementations of the exact same "what counts
as a pinned oracle" question, with no mechanism forcing them to agree. That
is itself the shape this repo keeps finding elsewhere (a predicate
reimplemented in more than one place so a future edit to one silently stops
matching the other) -- so discovery lives here, once, and both scripts
import it.

The blind spot this widening closes (2026-08-13)
--------------------------------------------------
The original glob, ``_*_py_oracle.py``, matches FILES only. Three pinned
oracles under ``packages/temper-placer/tests/`` are PACKAGES (directories)
of several plainly-named ``.py`` files, none of which individually match
the file glob, so the whole package was invisible to both the gate and the
generator:

  - ``io/_parse_engine_py_oracle/`` (8 files: the KiCad parse engine)
  - ``requirements/clearance_oracle/`` (2 files + ``__init__.py``: the
    REQ-SAFE-01 IEC 60335-2-6 clearance/creepage validator -- this is the
    mains-safety-relevant one)
  - ``explainability/explain_oracle/`` (7 files + ``__init__.py``: the
    explainability/decision-trace data structures)

Found independently of the original name-based glob (grep for the
"VERBATIM"/"Pinned Python oracle" header marker every genuine oracle file
carries, then diffed against the glob's own output) rather than by
extending the same technique that missed them, per this repo's own
documented lesson that a name-based sweep systematically undercounts
(``docs/evidence/2026-08-13-defect-multiplier-duplication-audit.md``).

Widened discovery, kept falsifiable
------------------------------------
Rather than hand-enumerate the 3 known package paths (an allowlist that
would itself go blind the next time a Wave-4 migration pins a 4th package
the same way), discovery is now structural: any directory under
``packages/`` whose name ends in ``_oracle`` -- covering all three known
shapes (``_parse_engine_py_oracle``, ``clearance_oracle``,
``explain_oracle``) uniformly, since every one of them ends in the literal
substring ``_oracle`` -- is treated as a pinned-oracle package, and every
``.py`` file inside it (recursively) is part of the pin. Verified against
every ``*oracle*``-named directory in the real tree (2026-08-13): exactly
these 3 match; the other 4 (``temper-quality-oracle``, ``quality-oracle``,
``oracle`` (a Rust module dir), ``oracle_freeze_specs``) do not, either
because the separator before "oracle" is a hyphen, not an underscore, or
because there is no separator at all -- so the suffix check has zero false
positives against the current tree without needing a directory allowlist.
"""

from __future__ import annotations

from pathlib import Path

ORACLE_GLOB = "_*_py_oracle.py"
ORACLE_DIR_SUFFIX = "_oracle"

# Directories that may legitimately contain oracle-shaped files/dirs but are
# not source of truth (build artifacts, environments).
EXCLUDED_DIRS = {".venv", "venv", "target", "build", "dist", "node_modules", "__pycache__"}


def _is_excluded(rel_parts: tuple[str, ...]) -> bool:
    return any(part in EXCLUDED_DIRS for part in rel_parts)


def discover_oracles(repo_root: Path) -> list[Path]:
    """Every pinned oracle file under ``packages/``, sorted by relative path.

    Two discovery shapes, unioned:

    1. Flat file pins -- any file named ``_*_py_oracle.py`` (the original,
       still-valid convention for the majority of pins).
    2. Package pins -- every ``.py`` file (recursively) inside any
       directory whose name ends in ``_oracle`` (covers multi-file pinned
       packages the flat glob cannot see by construction, since none of
       their individual files are named ``_*_py_oracle.py``).
    """
    packages_dir = repo_root / "packages"
    if not packages_dir.is_dir():
        return []

    found: set[Path] = set()

    for path in packages_dir.rglob(ORACLE_GLOB):
        if not path.is_file():
            continue
        if _is_excluded(path.relative_to(packages_dir).parts):
            continue
        found.add(path)

    for candidate in packages_dir.rglob("*"):
        if not candidate.is_dir():
            continue
        if candidate.name in EXCLUDED_DIRS:
            continue
        if not candidate.name.endswith(ORACLE_DIR_SUFFIX):
            continue
        if _is_excluded(candidate.relative_to(packages_dir).parts):
            continue
        for path in candidate.rglob("*.py"):
            if not path.is_file():
                continue
            if _is_excluded(path.relative_to(packages_dir).parts):
                continue
            found.add(path)

    return sorted(found, key=lambda p: str(p.relative_to(repo_root)))
