#!/usr/bin/env python3
"""Inline-oracle content-hash gate: oracle blocks that live INSIDE test files
must be discovered and pinned, exactly like the ``_*_py_oracle.py`` files are.

What this closes
----------------
``scripts/check_oracle_hashes.py`` pins every oracle that lives in its own
``_*_py_oracle.py`` file. But a large share of this repo's oracles are not
files at all -- they are **inline blocks** pasted directly into a
``test_*_rust_differential.py``: a verbatim copy of the pre-migration Python
implementation, defined as ``_oracle_<name>`` functions or ``_Oracle<Name>``
classes, used as the reference arm of the differential.

Those blocks were invisible to the file-based registry, and the blind spot
was not theoretical:

    35e3f914a (2026-08-17, PR #1314) removed ``core/graph.py`` and
    ``core/power_topology.py`` as dead code and deleted the test files that
    covered them. Those files also carried a **pinned inline oracle**. The
    sweep checked ``oracle_hashes.json``, correctly found nothing, and
    reported success. The gate passed because it could not see the thing it
    protects.

This gate makes the inline blocks first-class registry citizens: it
discovers them structurally, hashes each block's exact source text, and
compares against ``scripts/inline_oracle_hashes.json``.

What gets pinned
----------------
Two tiers, because the oracles do not all have the same shape.

**Tier 1 -- symbol pins (``blocks``).** A **top-level** ``def``/``async
def``/``class`` in a test file that is an oracle by either test:

* *By name*: it matches one of the repo's oracle spellings -- ``_oracle_*``
  / ``_Oracle*`` (the dominant convention), ``_ref_*`` / ``_reference_*``
  (the validation and thermal suites), ``_scipy_*`` / ``_numpy_*`` (the R19
  pinned-library reference arms), or a private name suffixed ``_oracle``.

* *By region*: it sits inside a declared **oracle-block region** -- from a
  banner comment line down to an explicit ``# End of oracle block`` marker
  or the first top-level test, whichever comes first. This is what catches
  oracles pasted under their ORIGINAL, unprefixed names, which no naming
  rule can find: the ~740-line ``DRCOracle``/``Violation`` block in
  ``test_constraints_drc_oracle_rust_differential.py`` (the largest inline
  oracle in the repo) and the 19 classes in
  ``tests/pcl/test_constraints_rust_differential.py``.

Regions close at the first test on purpose. Helpers written below the tests
are not oracle content, and pinning them would generate re-pin churn until
nobody read the diff -- which is how oracle drift became invisible in the
first place. For the same reason the pin is of the block's own source text,
not the whole file: a differential test file changes constantly (new cases,
new imports) while its oracle block must not change at all.

Banner text alone is never sufficient. "Oracle block", "DO NOT EDIT" and
"verbatim copy" appear in 343 test files, mostly as docstring prose; only
*comment-line* banners open a region, so prose cannot be used to smuggle a
pin in or out.

**Tier 2 -- whole-file pins (``files``).** ``check_oracle_hashes.py``'s
``_*_py_oracle.py`` glob matches *files*, so the 20 modules that live inside
a ``*_oracle/`` or ``*_py_oracle/`` **directory** --
``tests/io/_parse_engine_py_oracle/``,
``tests/explainability/explain_oracle/``,
``tests/requirements/clearance_oracle/`` -- are pinned by nobody today. The
*directory* carries the oracle name, not the file. They are pinned here
whole-file, which is right for a module that is entirely a verbatim copy.

Files already pinned by ``check_oracle_hashes.py`` (``_*_py_oracle.py``)
are skipped, so no oracle is pinned twice and drift is never double-reported.

Why symbol pins rather than whole-file pins everywhere: a differential test
file changes constantly (new cases, new imports) while its oracle block must
not change at all. Whole-file hashes would force a re-pin on every unrelated
edit until nobody read the diff -- which is how oracle drift became invisible
in the first place.

Hashing
-------
Each block is pinned by the sha256 of its exact source segment (the block's
own text, from its first decorator/``def``/``class`` line through its last
line), not of the whole file. That is the property the differential depends
on: the file around a block changes constantly (new tests, new imports), and
a whole-file hash would force a re-pin on every unrelated edit until nobody
read the diff any more.

Failure modes (all fail closed):
  - DRIFTED      a block's sha256 no longer matches its registry entry.
  - DELETED      a registry entry's block no longer exists in the tree.
  - UNREGISTERED a block exists in the tree with no registry entry -- the
                 anti-vacuity direction, and the one that closes the
                 35e3f914a hole. A NEW inline oracle appearing without a
                 registry regeneration fails.

Regeneration is the authoring PR's job
(``scripts/update_inline_oracle_hashes.py``), in the same PR as the block
change -- the same keep-in-sync convention ``check_oracle_hashes.py`` uses.
This script is deliberately NOT a generator: a generator that ran on a
drifted tree would launder the drift into the registry.

Exit codes (mirrors ``scripts/check_oracle_hashes.py``):
  0 - clean: every block matches its pin, every pin has a block, and the
      scan was not vacuous.
  3 - drift: at least one DRIFTED / DELETED / UNREGISTERED block.
  5 - tool_error: registry missing, unparseable, wrong schema, or an empty
      scan (zero blocks discovered -- a run that checked nothing must not
      report clean).

Usage:
  uv run --no-sync python scripts/check_inline_oracles.py
  uv run --no-sync python scripts/check_inline_oracles.py --repo-root .
  uv run --no-sync python scripts/check_inline_oracles.py --registry /tmp/x.json
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_CLEAN = 0
EXIT_DRIFT = 3
EXIT_TOOL_ERROR = 5

SUPPORTED_VERSION = 1
SUPPORTED_ALGO = "sha256"

REGISTRY_FILENAME = "inline_oracle_hashes.json"

#: Top-level symbol names that denote an inline oracle block (tier 1).
ORACLE_SYMBOL_RE = re.compile(
    # prefix spellings, or a private helper explicitly suffixed `_oracle`
    # (e.g. `_numpy_rasterise_oracle`). The leading underscore matters: it
    # keeps ordinary test helpers like `helper_not_an_oracle` out.
    r"^(?:_[Oo]racle|_ref_|_reference_|_scipy_|_numpy_).*$|^_.*_oracle$"
)

#: Files already pinned by ``check_oracle_hashes.py`` -- skip, do not double-pin.
REGISTERED_ORACLE_GLOB = "_*_py_oracle.py"

#: Directories that ARE oracle packages: every module inside is a verbatim
#: copy, and the file-based gate's file-glob cannot see them (tier 2a).
ORACLE_PACKAGE_DIR_RE = re.compile(r"(^|/)([A-Za-z0-9_]*_oracle|[A-Za-z0-9_]*_py_oracle)/")

#: A comment-line (not docstring prose) declaring verbatim/oracle content.
#: Used only for the tier-2b closed-world requirement.
ORACLE_BANNER_RE = re.compile(
    r"^\s*#.*(oracle block|verbatim|pre-migration|DO NOT EDIT)", re.IGNORECASE | re.MULTILINE
)

_EXCLUDED_DIRS = {".venv", "venv", "target", "build", "dist", "node_modules", "__pycache__"}

#: Where test files live: ``packages/<pkg>/tests/**``.
TEST_GLOB = "packages/*/tests/**/*.py"

# Status labels used in the per-block report.
OK = "OK"
DRIFTED = "DRIFTED"
DELETED = "DELETED"
UNREGISTERED = "UNREGISTERED"


@dataclass
class Finding:
    status: str
    key: str
    detail: str = ""


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    clean_count: int = 0
    registry_block_count: int = 0
    disk_block_count: int = 0
    disk_file_count: int = 0
    tool_error: str | None = None


def block_key(rel_path: str, symbol: str) -> str:
    """Registry key for one block: ``<relpath>::<symbol>``."""
    return f"{rel_path}::{symbol}"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_excluded(path: Path, repo_root: Path) -> bool:
    """Skip only what another gate already pins, or what is not source."""
    if any(part in _EXCLUDED_DIRS for part in path.parts):
        return True
    # ``_*_py_oracle.py`` files are pinned by check_oracle_hashes.py.
    if fnmatch.fnmatch(path.name, REGISTERED_ORACLE_GLOB):
        return True
    return False


def is_oracle_package_file(rel: str) -> bool:
    """True for modules inside a ``*_oracle/`` / ``*_py_oracle/`` directory.

    These are dedicated oracle modules that ``check_oracle_hashes.py``'s
    file-glob cannot match (the *directory* carries the name, not the file),
    so they are whole-file pinned here (tier 2a).
    """
    parent = rel.rsplit("/", 1)[0] + "/" if "/" in rel else ""
    return bool(ORACLE_PACKAGE_DIR_RE.search(parent))


def oracle_regions(source: str) -> list[tuple[int, int]]:
    """Line ranges (1-based, inclusive) declared as oracle-block regions.

    A region opens at a banner comment line and closes at the first explicit
    ``# End of oracle block`` marker or the first top-level ``def test_`` /
    ``class Test``. This is what lets the gate see oracles pasted under their
    ORIGINAL, unprefixed names (``DRCOracle``, ``Violation``,
    ``CompilationTarget`` ...), which no naming rule can find -- the ~740-line
    block in ``test_constraints_drc_oracle_rust_differential.py`` and the 18
    classes in ``tests/pcl/test_constraints_rust_differential.py``.
    """
    lines = source.splitlines()
    opens: list[int] = []
    closes: list[int] = []
    for i, line in enumerate(lines, start=1):
        if re.match(r"^\s*#.*end of oracle block", line, re.IGNORECASE):
            closes.append(i)
        elif ORACLE_BANNER_RE.match(line):
            opens.append(i)
        elif re.match(r"^(def test_|class Test|async def test_)", line):
            closes.append(i)
    regions: list[tuple[int, int]] = []
    for start in opens:
        end = next((c for c in closes if c > start), len(lines))
        if not regions or start > regions[-1][1]:
            regions.append((start, end))
        else:  # extend an already-open region
            regions[-1] = (regions[-1][0], max(regions[-1][1], end))
    return regions


def extract_blocks(source: str) -> list[tuple[str, str]]:
    """Return ``(symbol, source_segment)`` for every top-level oracle block.

    A top-level ``def``/``class`` is an oracle block if its name matches an
    oracle naming convention, OR it is defined inside a declared oracle-block
    region (see :func:`oracle_regions`).

    Raises ``SyntaxError`` if *source* does not parse.
    """
    tree = ast.parse(source)
    regions = oracle_regions(source)
    out: list[tuple[str, str]] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        named = bool(ORACLE_SYMBOL_RE.match(node.name))
        in_region = any(start <= node.lineno <= end for start, end in regions)
        if not (named or in_region):
            continue
        segment = ast.get_source_segment(source, node)
        if segment is None:  # pragma: no cover - defensive
            continue
        out.append((node.name, segment))
    return out


def discover_blocks(repo_root: Path) -> tuple[dict[str, str], int, list[str]]:
    """Back-compat shim: tier-1 symbol pins only."""
    blocks, _files, count, errors = discover(repo_root)
    return blocks, count, errors


def discover(repo_root: Path) -> tuple[dict[str, str], dict[str, str], int, list[str]]:
    """Scan the tree for oracle content.

    Returns ``(symbol_pins, file_pins, files_with_blocks, parse_errors)``.
    """
    blocks: dict[str, str] = {}
    files: dict[str, str] = {}
    files_with_blocks = 0
    errors: list[str] = []
    for path in sorted(repo_root.glob(TEST_GLOB)):
        if not path.is_file() or _is_excluded(path, repo_root):
            continue
        rel = path.relative_to(repo_root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            errors.append(f"{rel}: unreadable ({exc})")
            continue
        try:
            found = extract_blocks(source)
        except SyntaxError as exc:
            errors.append(f"{rel}: unparseable ({exc})")
            continue

        if is_oracle_package_file(rel):
            # tier 2a: dedicated oracle module, whole-file pin.
            files[rel] = sha256_text(source)
            continue

        if found:
            files_with_blocks += 1
            for symbol, segment in found:
                blocks[block_key(rel, symbol)] = sha256_text(segment)
        elif ORACLE_BANNER_RE.search(source):
            # tier 2b: banner says verbatim oracle content is present, but no
            # symbol matched a naming convention -- the oracle is pasted under
            # its original (unprefixed) names. Pin the whole file rather than
            # let it escape.
            files[rel] = sha256_text(source)
    return blocks, files, files_with_blocks, errors


def load_registry(registry_path: Path) -> tuple[dict[str, str] | None, str | None]:
    """Return ``(blocks, error)``; ``blocks`` maps ``<relpath>::<symbol>`` -> sha256."""
    if not registry_path.is_file():
        return None, f"registry not found: {registry_path}"
    try:
        data = json.loads(registry_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"registry unparseable: {registry_path} ({exc})"
    if not isinstance(data, dict):
        return None, f"registry must be a JSON object: {registry_path}"
    version = data.get("version")
    if version != SUPPORTED_VERSION:
        return None, f"unsupported registry version {version!r} (expected {SUPPORTED_VERSION})"
    algo = data.get("algo")
    if algo != SUPPORTED_ALGO:
        return None, f"unsupported registry algo {algo!r} (expected {SUPPORTED_ALGO})"
    blocks = data.get("blocks")
    if not isinstance(blocks, dict):
        return None, "registry 'blocks' must be an object mapping <path>::<symbol> -> sha256"
    if not blocks:
        return None, "registry 'blocks' is empty -- zero inline oracles recorded (vacuous registry)"
    file_pins = data.get("files")
    if not isinstance(file_pins, dict):
        return None, "registry 'files' must be an object mapping <path> -> sha256"
    bad = []
    for key, digest in blocks.items():
        if not isinstance(key, str) or "::" not in key:
            bad.append(f"{key!r}: key must be '<path>::<symbol>'")
        elif not isinstance(digest, str) or len(digest) != 64:
            bad.append(f"{key!r}: digest must be a 64-char sha256 hex, got {digest!r}")
    for key, digest in file_pins.items():
        if not isinstance(key, str) or not key:
            bad.append(f"{key!r}: file key must be a non-empty path")
        elif not isinstance(digest, str) or len(digest) != 64:
            bad.append(f"{key!r}: digest must be a 64-char sha256 hex, got {digest!r}")
    if bad:
        return None, "registry entries malformed: " + "; ".join(bad[:5])
    # Merge into one keyspace: file pins have no "::", symbol pins do.
    merged = dict(blocks)
    merged.update(file_pins)
    return merged, None


def run(repo_root: Path, registry_path: Path) -> Report:
    """Compute the gate verdict. Never raises for expected failure shapes."""
    report = Report()

    registry_blocks, registry_error = load_registry(registry_path)
    if registry_error is not None:
        report.tool_error = registry_error
        return report
    report.registry_block_count = len(registry_blocks)

    blocks, file_pins, files_with_blocks, parse_errors = discover(repo_root)
    if parse_errors:
        report.tool_error = "test files could not be scanned: " + "; ".join(parse_errors[:5])
        return report

    on_disk = dict(blocks)
    on_disk.update(file_pins)
    report.disk_block_count = len(on_disk)
    report.disk_file_count = files_with_blocks + len(file_pins)

    if not on_disk:
        # Zero blocks on disk with a non-empty registry means every pinned
        # block vanished; with an empty registry the run checked nothing.
        # Either way "clean" would be a vacuous lie -- fail closed. This is
        # exactly the 35e3f914a shape: a sweep deletes the files and the
        # gate must not respond with success.
        report.tool_error = (
            "zero inline oracle blocks found under packages/*/tests -- "
            "nothing to compare, refusing to report clean"
        )
        return report

    # 1. every registry entry must still exist, unchanged.
    for key in sorted(registry_blocks):
        actual = on_disk.get(key)
        if actual is None:
            report.findings.append(
                Finding(DELETED, key, "registry entry has no matching block in the tree")
            )
            continue
        if actual == registry_blocks[key]:
            report.clean_count += 1
        else:
            report.findings.append(
                Finding(DRIFTED, key, f"hash {registry_blocks[key][:12]}... -> {actual[:12]}...")
            )

    # 2. every block in the tree must be registered (anti-vacuity).
    for key in sorted(on_disk):
        if key not in registry_blocks:
            report.findings.append(
                Finding(UNREGISTERED, key, "inline oracle block has no registry entry")
            )

    return report


def _print_report(report: Report) -> None:
    if report.tool_error is not None:
        print(f"inline-oracle content-hash gate: TOOL ERROR -- {report.tool_error}")
        return
    print(
        f"inline-oracle content-hash gate: {report.clean_count}/{report.disk_block_count} "
        f"blocks OK across {report.disk_file_count} files "
        f"(registry: {report.registry_block_count} entries)"
    )
    for f in sorted(report.findings, key=lambda x: x.key):
        print(f"  [{f.status}] {f.key} -- {f.detail}")
    if not report.findings:
        print("inline-oracle gate passed: every inline oracle block matches its pin")


def _append_summary(report: Report) -> None:
    summary_path = get_github_summary_path()
    if not summary_path:
        return
    with open(summary_path, "a") as f:
        f.write("\n### Inline-oracle content-hash gate\n")
        if report.tool_error is not None:
            f.write(f"- **TOOL ERROR**: {report.tool_error}\n")
        else:
            f.write(
                f"- Clean: {report.clean_count}/{report.disk_block_count} blocks "
                f"across {report.disk_file_count} files "
                f"(registry: {report.registry_block_count} entries)\n"
            )
            for find in report.findings:
                f.write(f"- `[{find.status}] {find.key}` -- {find.detail}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None,
                        help="Repository root (default: auto-discovered)")
    parser.add_argument("--registry", type=Path, default=None,
                        help=f"Registry path (default: <repo>/scripts/{REGISTRY_FILENAME})")
    args = parser.parse_args()

    repo_root = (args.repo_root or find_repo_root()).resolve()
    registry_path = args.registry or (repo_root / "scripts" / REGISTRY_FILENAME)

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
