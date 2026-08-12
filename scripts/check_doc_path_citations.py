#!/usr/bin/env python3
"""Doc-path citation gate: a comment/docstring/doc that names a
``docs/plans/*.md`` or ``docs/evidence/*.md`` file must name one that
actually exists somewhere in this repo's history.

Why this exists
----------------
Spiked in ``docs/brainstorms/2026-08-12-referential-integrity-options.md``:
this repo has a recurring defect shape where a declaration names an entity
that does not exist -- a netclass assignment naming a net absent from the
board, a manifest entry claiming CI wiring nothing provides. This is one
instance of that shape, applied to prose citations of two specific
directories. Measured on ``origin/main`` at spike time: of 155 distinct
``docs/plans/YYYY-MM-DD-NNN-*.md`` paths cited from 911 sites, 14 do not
resolve (9 with zero commits in this repo's history on any branch --
including an entire crate, ``packages/temper-drc-rs``, whose every source
file's provenance header cites a plan doc that never existed). Of ~207
distinct ``docs/evidence/*.md`` paths cited, 15 do not resolve anywhere
(6 of them cited six separate times each from ``generate_kicad_dru.py``
alone). Neither surface had any gate before this one:
``scripts/check_traceability.py`` only validates ``@req(...)`` tags, never
prose path citations; ``scripts/check_evidence_provenance.py`` validates
that files *already under* ``docs/evidence/`` carry a provenance stamp --
it never checks whether a citation *elsewhere* resolves.

Why one gate for two directories
----------------------------------
``docs/plans/`` and ``docs/evidence/`` have different authors, different
lifecycles, and different meanings -- but the citation-resolution rule is
identical for both: a literal repo-relative path string either names a
real file or it doesn't. That is a narrower, more defensible
generalisation than "check all referential integrity in this repo" (which
would have to reimplement KiCad net-name resolution, netclass-alias
resolution, and live pyo3 ``dir()`` introspection under one roof, each
with different semantics) -- see the spike document for the full
argument. A third directory can be added to ``TARGET_PATTERNS`` below at
the cost of one line, precisely because the resolution rule does not
change.

What counts as dangling
-------------------------
A cited path is dangling if it does not exist in the working tree. Every
dangling citation is further classified by ``git log --all --oneline --
<path>``:

* ``NEVER_EXISTED`` -- zero commits touch that path on any local ref.
  Either a typo, or a doc that was planned/referenced but never written.
* ``DELETED`` -- at least one commit touches that path. The file existed
  (here, or on a branch this checkout has fetched) and is now gone --
  removed intentionally or by accident, with nothing updating the citer.

This distinction matters for triage (a typo is a one-line fix; a genuinely
deleted doc needs a human decision about whether the citing code/doc
still needs it) but both are gate failures: an unreadable citation is not
serving whoever follows it either way.

Exemptions
----------
A citation may be marked as accepted-dangling in ``doc-path-citation-
allowlist.yaml`` (repo root, created on first use), following the same
convention as ``bom-reconciliation-allowlist.yaml``: a plain entry
(``path`` + ``reason``) for a citation whose dangling-ness is a reviewed,
deliberate exception, or a dated backlog entry (``backlog: true`` +
``seeded: "YYYY-MM-DD"``) for pre-existing drift seeded in bulk and not
yet triaged. Backlog entries are always reported under their own "N
backlog finding(s) suppressed" line so a growing backlog cannot fade into
silent permanent noise -- see ``--backlog-report``. This mirrors
``scripts/check_bom_source_reconciliation.py``'s allowlist exactly (see
that module's docstring for the "BACKLOG vs. JUSTIFIED" rationale); it is
not reinvented here.

Exit codes:
  0 - OK (no unallowlisted dangling citations)
  3 - VIOLATION (>=1 dangling citation not covered by the allowlist)
  5 - Gate error (malformed allowlist, not a git checkout, etc.)

Usage:
  uv run python scripts/check_doc_path_citations.py
  uv run python scripts/check_doc_path_citations.py --backlog-report
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.repo import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root(Path(__file__))
ALLOWLIST_PATH = REPO_ROOT / "doc-path-citation-allowlist.yaml"

# One (label, regex) pair per target directory. The regex must capture the
# full repo-relative path in group 0. Adding a third directory costs one
# line here -- see module docstring, "Why one gate for two directories".
TARGET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("plan", re.compile(r"docs/plans/\d{4}-\d{2}-\d{2}-\d{3}-[A-Za-z0-9_-]+\.md")),
    ("evidence", re.compile(r"docs/evidence/\d{4}-\d{2}-\d{2}-[A-Za-z0-9_.-]+\.md")),
]

# Directories never scanned for citations: version control, build/output
# artifacts, and pcb/** (out of scope for this spike -- see the brainstorm
# doc's "Do not modify pcb/**" constraint; this gate does not touch it
# either way, but excluding it from scanning keeps the run fast and keeps
# false positives from KiCad's own binary-ish text formats out of scope).
EXCLUDE_DIR_NAMES = {
    ".git",
    "__pycache__",
    "node_modules",
    "pcb",
    "output_gerbers",
    "elec_build",
    ".pytest_cache",
    "target",
}
EXCLUDE_DIR_PATH_PARTS = {"build"}

_TEXT_SUFFIXES = {
    ".py",
    ".rs",
    ".md",
    ".yaml",
    ".yml",
    ".toml",
    ".txt",
    ".sh",
    ".j2",
    ".pyi",
}


@dataclass(frozen=True)
class Citation:
    cited_path: str
    kind: str
    site_file: str
    site_line: int


@dataclass
class AllowlistEntry:
    path: str
    reason: str
    backlog: bool = False
    seeded: str | None = None


_SEEDED_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_allowlist(path: Path) -> list[AllowlistEntry] | None:
    """Same shape/validation convention as bom-reconciliation-allowlist.yaml
    (see scripts/check_bom_source_reconciliation.py). Returns None on any
    malformed structure -- caller must treat that as a tool error, not an
    empty-but-valid allowlist."""
    if not path.is_file():
        return []
    import yaml

    try:
        data = yaml.safe_load(path.read_text())
    except Exception:
        return None
    if data is None:
        return []
    if not isinstance(data, dict) or "allowlist" not in data:
        return None
    entries_raw = data["allowlist"]
    if not isinstance(entries_raw, list):
        return None
    entries: list[AllowlistEntry] = []
    for e in entries_raw:
        if not isinstance(e, dict):
            return None
        if not all(k in e for k in ("path", "reason")):
            return None
        if not isinstance(e["path"], str) or not e["path"].strip():
            return None
        if not isinstance(e["reason"], str) or not e["reason"].strip():
            return None
        backlog_val = e.get("backlog", False)
        if not isinstance(backlog_val, bool):
            return None
        seeded_val = e.get("seeded")
        if seeded_val is not None and not isinstance(seeded_val, str):
            return None
        if backlog_val:
            if not seeded_val or not seeded_val.strip() or not _SEEDED_DATE_RE.match(seeded_val.strip()):
                return None
            seeded_val = seeded_val.strip()
        else:
            if seeded_val is not None:
                return None
        entries.append(
            AllowlistEntry(
                path=e["path"].strip(), reason=e["reason"].strip(), backlog=backlog_val, seeded=seeded_val
            )
        )
    return entries


def iter_text_files(root: Path):
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(root).parts
        if any(part in EXCLUDE_DIR_NAMES for part in rel_parts[:-1]):
            continue
        if any(part in EXCLUDE_DIR_PATH_PARTS for part in rel_parts[:-1]):
            continue
        if p.suffix not in _TEXT_SUFFIXES:
            continue
        yield p


def find_citations(root: Path) -> list[Citation]:
    citations: list[Citation] = []
    for f in iter_text_files(root):
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        rel = f.relative_to(root).as_posix()
        for lineno, line in enumerate(text.splitlines(), start=1):
            for kind, pattern in TARGET_PATTERNS:
                for m in pattern.finditer(line):
                    citations.append(
                        Citation(cited_path=m.group(0), kind=kind, site_file=rel, site_line=lineno)
                    )
    return citations


def classify_dangling(root: Path, cited_path: str) -> str:
    """NEVER_EXISTED (zero commits touch this path on any ref this
    checkout knows about) or DELETED (>=1 commit touches it)."""
    result = subprocess.run(
        ["git", "log", "--all", "--oneline", "--", cited_path],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "UNKNOWN"
    return "DELETED" if result.stdout.strip() else "NEVER_EXISTED"


def run(root: Path) -> tuple[str, dict]:
    allowlist = load_allowlist(ALLOWLIST_PATH)
    if allowlist is None:
        return "tool_error", {"reason": f"malformed allowlist at {ALLOWLIST_PATH}"}
    allowlist_by_path = {e.path: e for e in allowlist}

    citations = find_citations(root)
    by_path: dict[str, list[Citation]] = {}
    for c in citations:
        by_path.setdefault(c.cited_path, []).append(c)

    dangling: dict[str, str] = {}
    for cited_path in by_path:
        if not (root / cited_path).exists():
            dangling[cited_path] = classify_dangling(root, cited_path)

    violations = {p: cls for p, cls in dangling.items() if p not in allowlist_by_path}
    backlog_suppressed = {p: cls for p, cls in dangling.items() if p in allowlist_by_path}

    state = "violation" if violations else "clean"
    return state, {
        "total_citation_sites": len(citations),
        "total_distinct_paths": len(by_path),
        "dangling": dangling,
        "by_path": by_path,
        "violations": violations,
        "backlog_suppressed": backlog_suppressed,
        "allowlist_by_path": allowlist_by_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--backlog-report", action="store_true", help="List every outstanding backlog entry and exit."
    )
    args = parser.parse_args()

    state, data = run(REPO_ROOT)

    if state == "tool_error":
        print(f"GATE RESULT: ERROR -- not PASSED, not a violation.\n  TOOL_ERROR {data['reason']}")
        sys.exit(5)

    if args.backlog_report:
        entries = [e for e in data["allowlist_by_path"].values() if e.backlog]
        print(f"{len(entries)} backlog entr(y/ies):")
        for e in sorted(entries, key=lambda e: e.path):
            still_dangling = e.path in data["dangling"]
            print(f"  {e.path} (seeded {e.seeded}, still dangling: {still_dangling}) -- {e.reason}")
        sys.exit(0)

    print(
        f"Doc-path citation gate -- {data['total_citation_sites']} citation site(s), "
        f"{data['total_distinct_paths']} distinct path(s) checked"
    )
    print()

    if data["backlog_suppressed"]:
        print(f"{len(data['backlog_suppressed'])} backlog finding(s) suppressed (see --backlog-report)")

    violations = data["violations"]
    if not violations:
        print("Doc-path citation gate passed")
        sys.exit(0)

    for cls in ("NEVER_EXISTED", "DELETED", "UNKNOWN"):
        paths = sorted(p for p, c in violations.items() if c == cls)
        if not paths:
            continue
        print(f"=== {cls}: {len(paths)} ===")
        for p in paths:
            sites = data["by_path"][p]
            shown = sites[:3]
            print(f"  VIOLATION {p} (cited {len(sites)}x)")
            for c in shown:
                print(f"    {c.site_file}:{c.site_line}")
            if len(sites) > len(shown):
                print(f"    ... and {len(sites) - len(shown)} more site(s)")
        print()

    print(f"FAILED -- {len(violations)} dangling citation(s) not in the allowlist")
    print(
        "Remediation: fix the citation (rename/retarget), or if genuinely a "
        "reviewed exception add an entry to doc-path-citation-allowlist.yaml "
        "(plain entry) or a dated backlog entry (backlog: true, seeded: "
        '"YYYY-MM-DD") for pre-existing, not-yet-triaged drift.'
    )
    sys.exit(3)


if __name__ == "__main__":
    main()
