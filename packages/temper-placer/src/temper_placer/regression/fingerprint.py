"""Fingerprint computation and cache management for incremental regression.

Fingerprints capture the state of board inputs and placer source code so
the regression runner can skip boards whose inputs haven't changed since
the last successful run.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

CACHE_FILENAME = ".regression-cache.json"
CACHE_VERSION = 1

SOURCE_FINGERPRINT_DIRS = [
    "packages/temper-placer/src",
    "packages/temper-drc/src",
]


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_input_fingerprint(
    pcb_path: Path,
    constraints_path: Path,
    baseline_path: Path,
    manifest_seed: int,
    manifest_epochs: int,
) -> str:
    h = hashlib.sha256()
    for path in sorted([pcb_path, constraints_path, baseline_path]):
        if path.exists():
            h.update(path.read_bytes())
        else:
            h.update(str(path).encode())
    h.update(f"seed:{manifest_seed}".encode())
    h.update(f"epochs:{manifest_epochs}".encode())
    return h.hexdigest()


def compute_source_fingerprint(repo_root: Path) -> str:
    file_hashes: list[str] = []
    for rel_dir in SOURCE_FINGERPRINT_DIRS:
        src_dir = repo_root / rel_dir
        if not src_dir.is_dir():
            continue
        for py_file in sorted(src_dir.rglob("*.py")):
            file_hashes.append(
                f"{py_file.relative_to(repo_root)}:{_hash_file(py_file)}"
            )
    return hashlib.sha256("\n".join(file_hashes).encode()).hexdigest()


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
    cache_path = corpus_root / CACHE_FILENAME
    cache["generated_at"] = datetime.now(UTC).isoformat()
    with open(cache_path, "w") as f:
        json.dump(cache, f, indent=2)
        f.write("\n")


def should_skip(
    board_id: str,
    input_fingerprint: str,
    source_fingerprint: str,
    cache: dict,
) -> bool:
    board_cache = cache.get("boards", {}).get(board_id)
    if not board_cache:
        return False
    return (
        board_cache.get("input_fingerprint") == input_fingerprint
        and board_cache.get("source_fingerprint") == source_fingerprint
    )


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
