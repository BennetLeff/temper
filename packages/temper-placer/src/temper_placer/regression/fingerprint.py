"""Fingerprint computation and cache management for incremental regression.

Fingerprints capture the state of board inputs and placer source code so
the regression runner can skip boards whose inputs haven't changed since
the last successful run.

Wave 4 Phase 4 (regression slice): the hashing/decision compute —
the SHA-256 update-sequence for input fingerprints
(``temper_design_bundle_python.input_fingerprint``), the ``"\n"``-join +
SHA-256 for source fingerprints (``source_fingerprint``), and the cache-skip
decision (``should_skip``) — moved to ``temper-design-bundle``
(packages/temper-design-bundle/src/fingerprint.rs). File I/O stays here: the
input files are read, ``SOURCE_FINGERPRINT_DIRS`` walked, and each file's
hash computed with the crate's own ``sha256_hex`` (identical to
``hashlib.sha256().hexdigest()``) before the kernels hash the marshalled
parts. The cache JSON load/save and the board-entry update (with its UTC
timestamp) stay here — I/O and marshalling. Design boundaries are argued in
``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

_TDB = None


def _tdb():
    global _TDB
    if _TDB is None:
        import temper_design_bundle_python  # type: ignore[import-untyped]

        _TDB = temper_design_bundle_python
    return _TDB

CACHE_FILENAME = ".regression-cache.json"
CACHE_VERSION = 1

SOURCE_FINGERPRINT_DIRS = [
    "packages/temper-placer/src",
    "packages/temper-drc/src",
]


def _hash_file(path: Path) -> str:
    # Wave 4 Phase 4: the crate's sha256_hex is byte-identical to
    # hashlib.sha256(...).hexdigest() (SHA-256 is standardized; pinned by the
    # differential).
    return _tdb().sha256_hex(path.read_bytes())


def compute_input_fingerprint(
    pcb_path: Path,
    constraints_path: Path,
    baseline_path: Path,
    manifest_seed: int,
    manifest_epochs: int,
) -> str:
    # Wave 4 Phase 4: the hashing runs in
    # ``temper_design_bundle_python.input_fingerprint``. The parts carry the
    # oracle's exact update sequence in the oracle's sorted-path order:
    # existing files contribute their bytes, missing files contribute
    # ``str(path).encode()``, then the ``seed:``/``epochs:`` suffixes.
    parts: list[tuple[bytes | None, str]] = []
    for path in sorted([pcb_path, constraints_path, baseline_path]):
        if path.exists():
            parts.append((path.read_bytes(), str(path)))
        else:
            parts.append((None, str(path)))
    return _tdb().input_fingerprint(parts, int(manifest_seed), int(manifest_epochs))


def compute_source_fingerprint(repo_root: Path) -> str:
    file_hashes: list[str] = []
    for rel_dir in SOURCE_FINGERPRINT_DIRS:
        src_dir = repo_root / rel_dir
        if not src_dir.is_dir():
            continue
        for py_file in sorted(src_dir.rglob("*.py")):
            file_hashes.append(f"{py_file.relative_to(repo_root)}:{_hash_file(py_file)}")
    # Wave 4 Phase 4: the "\n"-join + SHA-256 runs in
    # ``temper_design_bundle_python.source_fingerprint``.
    return _tdb().source_fingerprint(file_hashes)


def load_cache(corpus_root: Path) -> dict:
    cache_path = corpus_root / CACHE_FILENAME
    if not cache_path.exists():
        return {"version": CACHE_VERSION, "boards": {}}
    try:
        with open(cache_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"version": CACHE_VERSION, "boards": {}}
    if not isinstance(data, dict) or data.get("version") != CACHE_VERSION:
        return {"version": CACHE_VERSION, "boards": {}}
    return data


def save_cache(corpus_root: Path, cache: dict) -> None:
    """Write ``.regression-cache.json`` atomically.

    The cache's key is sufficient (each board entry is keyed on the input
    content hash and the full source-tree hash together -- see
    ``should_skip``), so a crash mid-write can never serve a foreign
    board's stale result under a live key. But the previous plain
    ``json.dump(cache, f, ...)`` wrote directly to the destination path
    with no atomicity: a crash (or a concurrent process opening the file)
    mid-write could observe a truncated/malformed JSON document -- and
    because this file holds every board's cache entry in one JSON object,
    that corrupts the whole cache, not just the one board being updated at
    the time. ``load_cache`` already treats a ``JSONDecodeError`` as "no
    cache" (full-corpus fallback, not a crash), so the failure mode was
    silent-but-slow rather than a hard error -- exactly the kind of defect
    that stays unnoticed. Fixed the same way as the EDT disk cache
    (``router_v6/channel_widths.py::_atomic_write_npz``, commit
    ``c57101ac``): write to a temp file in the *same directory* (so the
    final rename is same-filesystem, hence atomic on POSIX) and
    ``os.replace`` into place. A concurrent reader then only ever observes
    the fully-old file or the fully-new one, never a partial one.
    """
    cache_path = corpus_root / CACHE_FILENAME
    cache["generated_at"] = datetime.now(UTC).isoformat()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=cache_path.parent, prefix=f".{cache_path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(cache, f, indent=2)
            f.write("\n")
        os.replace(tmp_name, cache_path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def should_skip(
    board_id: str,
    input_fingerprint: str,
    source_fingerprint: str,
    cache: dict,
) -> bool:
    board_cache = cache.get("boards", {}).get(board_id)
    # Wave 4 Phase 4: the decision (falsy entry / both-fingerprints-match)
    # runs in ``temper_design_bundle_python.should_skip``.
    return _tdb().should_skip(input_fingerprint, source_fingerprint, board_cache)


def update_cache_entry(
    cache: dict,
    board_id: str,
    input_fingerprint: str,
    source_fingerprint: str,
    commit_sha: str,
) -> None:
    cache.setdefault("boards", {})[board_id] = {
        "input_fingerprint": input_fingerprint,
        "source_fingerprint": source_fingerprint,
        "last_pass_commit": commit_sha,
        "last_pass_at": datetime.now(UTC).isoformat(),
    }
