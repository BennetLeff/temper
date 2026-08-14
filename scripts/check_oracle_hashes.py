#!/usr/bin/env python3
"""Oracle content-hash gate: ``_*_py_oracle.py`` files must stay byte-identical
to their pinned content (``scripts/oracle_hashes.json``).

What this closes
----------------
Every pinned oracle under ``packages/`` -- a file named ``_*_py_oracle.py``,
or every ``.py`` file inside a directory whose name ends in ``_oracle``
(``scripts/_lib/oracle_discovery.py``; the latter shape closes a confirmed
2026-08-13 discovery blind spot, see that module's docstring) -- is a
VERBATIM pin of a pre-migration Python implementation. The Wave-4
differential suites compare the Rust kernels against these files -- but
nothing previously noticed when an oracle drifted: the suites compare Rust
against *whatever the oracle now says*, so an accidental edit silently
redefined the reference and the differentials kept passing against the
wrong target (issues #754 P2-2, #758). The registry is the committed record
of the pinned content; this gate makes any drift from that record a CI
failure instead of an invisible redefinition.

Failure modes (all fail closed):
  - DRIFTED      an oracle's sha256 no longer matches its registry entry.
  - DELETED      a registry entry's file no longer exists on disk.
  - UNREGISTERED an oracle file on disk has no registry entry -- the
                 anti-vacuity direction. A new oracle added without a
                 registry regeneration fails, so the registry cannot
                 silently go stale by omission.
  - (tool error) discovery itself regressed below the registry's recorded
                 ``min_files`` floor -- see "Anti-vacuity floor" below.
                 DELETED/UNREGISTERED only fire for files that ARE
                 registered; they cannot catch "narrow discover_oracles()"
                 + "regenerate the registry against the now-narrower
                 discovery" landing in the same change, which would launder
                 a coverage regression into an internally-consistent but
                 silently-smaller registry.

Anti-vacuity floor
-------------------
The registry records ``min_files``: the largest oracle count any prior
regeneration has observed (monotonically non-decreasing -- see
``update_oracle_hashes.py``'s ``--allow-shrink``, required for a
deliberate oracle retirement to lower it, e.g. #1021's U5 retirement of
``_copper_reach_py_oracle.py``). If a run's own discovery finds FEWER files
than ``min_files``, that is a tool error, never a clean pass and never an
ordinary DELETED-only finding -- "the registry's discovery silently sees
less than it used to" is exactly the failure mode this whole gate exists
to make loud.

Regeneration is the migration PR's job (the keep-in-sync convention: a
migration PR that adds or re-pins an oracle regenerates the registry in the
same PR, exactly like the config-reference and .pyi regeneration steps).
This script is deliberately NOT a generator -- a generator that ran on a
drifted tree would launder the drift into the registry.

Exit codes (mirrors ``scripts/check_derived_doc_drift.py``):
  0 - clean: every oracle file matches its registry entry, every registry
      entry has a file, and neither set is empty (a run that checked
      nothing must not report clean).
  3 - drift: at least one DRIFTED / DELETED / UNREGISTERED oracle.
  5 - tool_error: registry missing, unparseable, wrong schema, an empty
      scan (zero oracle files and zero registry entries), or discovery
      regressed below the registry's ``min_files`` floor.

Usage:
  uv run --no-sync python scripts/check_oracle_hashes.py
  uv run --no-sync python scripts/check_oracle_hashes.py --repo-root .
  uv run --no-sync python scripts/check_oracle_hashes.py --registry /tmp/x.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.oracle_discovery import (  # noqa: E402
    EXCLUDED_DIRS as _EXCLUDED_DIRS,
    ORACLE_GLOB,
    discover_oracles,
)
from _lib.repo import find_repo_root  # noqa: E402

EXIT_CLEAN = 0
EXIT_DRIFT = 3
EXIT_TOOL_ERROR = 5

SUPPORTED_VERSION = 1
SUPPORTED_ALGO = "sha256"

# Status labels used in the per-file report.
OK = "OK"
DRIFTED = "DRIFTED"
DELETED = "DELETED"
UNREGISTERED = "UNREGISTERED"


@dataclass
class Finding:
    status: str
    rel_path: str
    detail: str = ""


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    clean_count: int = 0
    registry_file_count: int = 0
    disk_file_count: int = 0
    registry_min_files: int | None = None
    tool_error: str | None = None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_registry(
    registry_path: Path,
) -> tuple[dict[str, str] | None, int | None, str | None]:
    """Return (files, min_files, error).

    ``files`` is the registry's path->hash mapping. ``min_files`` is the
    anti-vacuity floor (``None`` if the registry predates that field --
    treated as "no floor recorded", not as an error, so older/synthetic
    registries without it still load).
    """
    if not registry_path.is_file():
        return None, None, f"registry not found: {registry_path}"
    try:
        data = json.loads(registry_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return None, None, f"registry unparseable: {registry_path} ({exc})"
    if not isinstance(data, dict):
        return None, None, f"registry must be a JSON object: {registry_path}"
    version = data.get("version")
    if version != SUPPORTED_VERSION:
        return None, None, f"unsupported registry version {version!r} (expected {SUPPORTED_VERSION})"
    algo = data.get("algo")
    if algo != SUPPORTED_ALGO:
        return None, None, f"unsupported registry algo {algo!r} (expected {SUPPORTED_ALGO})"
    files = data.get("files")
    if not isinstance(files, dict):
        return None, None, "registry 'files' must be an object mapping path -> sha256"
    if not files:
        return None, None, "registry 'files' is empty -- zero oracles recorded (vacuous registry)"
    bad = []
    for rel, digest in files.items():
        if not isinstance(rel, str) or not rel:
            bad.append(f"{rel!r}: path must be a non-empty string")
        elif not isinstance(digest, str) or len(digest) != 64:
            bad.append(f"{rel!r}: digest must be a 64-char sha256 hex, got {digest!r}")
    if bad:
        return None, None, "registry entries malformed: " + "; ".join(bad[:5])
    min_files = data.get("min_files")
    if min_files is not None and (not isinstance(min_files, int) or isinstance(min_files, bool) or min_files < 0):
        return None, None, f"registry 'min_files' must be a non-negative integer, got {min_files!r}"
    return files, min_files, None


def run(repo_root: Path, registry_path: Path) -> Report:
    """Compute the gate verdict. Never raises for expected failure shapes."""
    report = Report()

    registry_files, registry_min_files, registry_error = load_registry(registry_path)
    if registry_error is not None:
        report.tool_error = registry_error
        return report
    report.registry_file_count = len(registry_files)
    report.registry_min_files = registry_min_files

    on_disk = discover_oracles(repo_root)
    report.disk_file_count = len(on_disk)
    disk_by_rel = {str(p.relative_to(repo_root)): p for p in on_disk}

    if not on_disk:
        # Zero files on disk with a non-empty registry means every registered
        # oracle is missing; with an empty registry the run checked nothing.
        # Either way "clean" would be a vacuous lie -- fail closed.
        report.tool_error = (
            "zero oracle files found on disk under packages/ -- "
            "nothing to compare, refusing to report clean"
        )
        return report

    # Anti-vacuity floor: discovery must never silently regress. A narrower
    # discover_oracles() regenerated in the same change as this registry
    # would otherwise be internally consistent (files == registry) and
    # report clean -- this is the backstop for exactly that case, checked
    # BEFORE the per-file comparison so it fails closed even when every
    # registered file still matches.
    if registry_min_files is not None and report.disk_file_count < registry_min_files:
        report.tool_error = (
            f"discovery regressed: found {report.disk_file_count} oracle file(s) on "
            f"disk, fewer than the registry's recorded floor of {registry_min_files} "
            "('min_files') -- discover_oracles() may have narrowed silently, or "
            "oracles were deleted without a deliberate, --allow-shrink regeneration; "
            "investigate before lowering this floor"
        )
        return report

    # 1. every registry entry must have a matching, unchanged file on disk.
    for rel in sorted(registry_files):
        path = disk_by_rel.get(rel)
        if path is None:
            report.findings.append(Finding(DELETED, rel, "registry entry has no file on disk"))
            continue
        actual = sha256_file(path)
        if actual == registry_files[rel]:
            report.clean_count += 1
        else:
            report.findings.append(
                Finding(DRIFTED, rel, f"hash {registry_files[rel][:12]}... -> {actual[:12]}...")
            )

    # 2. every oracle file on disk must be registered (anti-vacuity).
    for rel in sorted(disk_by_rel):
        if rel not in registry_files:
            report.findings.append(
                Finding(UNREGISTERED, rel, "oracle file has no registry entry")
            )

    return report


def _print_report(report: Report) -> None:
    if report.tool_error is not None:
        print(f"oracle content-hash gate: TOOL ERROR -- {report.tool_error}")
        return
    print(
        f"oracle content-hash gate: {report.clean_count}/{report.disk_file_count} oracle "
        f"files OK (registry: {report.registry_file_count} entries)"
    )
    for f in sorted(report.findings, key=lambda x: x.rel_path):
        print(f"  [{f.status}] {f.rel_path} -- {f.detail}")
    if not report.findings:
        print("oracle content-hash gate passed: all oracle files byte-identical to their pins")


def _append_summary(report: Report) -> None:
    summary_path = get_github_summary_path()
    if not summary_path:
        return
    with open(summary_path, "a") as f:
        f.write("\n### Oracle content-hash gate\n")
        if report.tool_error is not None:
            f.write(f"- **TOOL ERROR**: {report.tool_error}\n")
        else:
            f.write(
                f"- Clean: {report.clean_count}/{report.disk_file_count} "
                f"(registry: {report.registry_file_count} entries)\n"
            )
            for find in report.findings:
                f.write(f"- `[{find.status}] {find.rel_path}` -- {find.detail}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None,
                        help="Repository root (default: auto-discovered)")
    parser.add_argument("--registry", type=Path, default=None,
                        help="Registry path (default: <repo>/scripts/oracle_hashes.json)")
    args = parser.parse_args()

    repo_root = (args.repo_root or find_repo_root()).resolve()
    registry_path = args.registry or (repo_root / "scripts" / "oracle_hashes.json")

    report = run(repo_root, registry_path)
    _print_report(report)
    _append_summary(report)

    if report.tool_error is not None:
        sys.exit(EXIT_TOOL_ERROR)
    if report.findings:
        sys.exit(EXIT_DRIFT)
    sys.exit(EXIT_CLEAN)


if __name__ == "__main__":
    main()
