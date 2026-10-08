#!/usr/bin/env python3
"""Build deterministic, size-bounded round-4 raw-evidence release assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tarfile
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
RAW_MANIFEST = HERE.parent / "raw-manifest.json"
TARGET_BYTES = 1_400_000_000
MAX_ASSET_BYTES = 1_500_000_000
MEMBER_ALLOWANCE = 16_384  # More than the PAX and tar padding for these paths.


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def valid_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        value == path.as_posix()
        and not path.is_absolute()
        and len(path.parts) > 0
        and all(part not in (".", "..") for part in path.parts)
    )


def load_rows() -> tuple[dict, list[dict]]:
    manifest = json.loads(RAW_MANIFEST.read_text())
    rows = manifest["files"]
    paths = [row["path"] for row in rows]
    if (
        manifest["file_count"] != len(rows)
        or manifest["bytes"] != sum(row["bytes"] for row in rows)
        or len(set(paths)) != len(paths)
        or not all(valid_path(path) for path in paths)
        or not all(isinstance(row["bytes"], int) and row["bytes"] >= 0 for row in rows)
        or not all(isinstance(row["sha256"], str) and len(row["sha256"]) == 64 for row in rows)
    ):
        raise ValueError("invalid raw manifest")
    return manifest, sorted(rows, key=lambda row: row["path"])


def split_rows(rows: list[dict]) -> list[list[dict]]:
    parts: list[list[dict]] = [[]]
    estimated = 0
    for row in rows:
        contribution = row["bytes"] + MEMBER_ALLOWANCE
        if estimated + contribution > TARGET_BYTES and parts[-1]:
            parts.append([])
            estimated = 0
        parts[-1].append(row)
        estimated += contribution
    return parts


class HashingReader:
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()

    def read(self, size: int) -> bytes:
        block = self.stream.read(size)
        self.digest.update(block)
        return block


def add_checked_member(tar: tarfile.TarFile, source_root: Path, row: dict) -> None:
    source = source_root / row["path"]
    cursor = source_root
    for part in PurePosixPath(row["path"]).parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"source symlink: {row['path']}")
    with source.open("rb") as stream:
        mode = os.fstat(stream.fileno()).st_mode
        size = os.fstat(stream.fileno()).st_size
        if not stat.S_ISREG(mode) or size != row["bytes"]:
            raise ValueError(f"source type/size mismatch: {row['path']}")
        info = tarfile.TarInfo(row["path"])
        info.size = size
        info.mtime = info.uid = info.gid = 0
        info.mode = 0o644
        info.uname = info.gname = ""
        reader = HashingReader(stream)
        tar.addfile(info, reader)
        if reader.digest.hexdigest() != row["sha256"]:
            raise ValueError(f"source SHA-256 mismatch: {row['path']}")


def build(source_root: Path, output_dir: Path) -> None:
    manifest, rows = load_rows()
    parts = split_rows(rows)
    output_dir.mkdir(parents=True, exist_ok=True)
    names = [f"ps120-round4-raw-part-{index:02d}-of-{len(parts):02d}.tar" for index in range(1, len(parts) + 1)]
    if any((output_dir / name).exists() for name in [*names, "assets.json"]):
        raise FileExistsError("output already contains release assets; use an empty directory")
    assets = []
    for name, part in zip(names, parts, strict=True):
        path = output_dir / name
        try:
            with tarfile.open(path, "w", format=tarfile.PAX_FORMAT) as tar:
                for row in part:
                    add_checked_member(tar, source_root, row)
            size = path.stat().st_size
            if size >= MAX_ASSET_BYTES or size >= 2_000_000_000:
                raise ValueError(f"asset exceeds size limit: {name} ({size} bytes)")
            assets.append({
                "name": name,
                "bytes": size,
                "sha256": sha256_file(path),
                "file_count": len(part),
                "first_path": part[0]["path"],
                "last_path": part[-1]["path"],
            })
            print(f"{name}: {size} bytes, {len(part)} files, SHA-256 {assets[-1]['sha256']}", flush=True)
        except Exception:
            path.unlink(missing_ok=True)
            raise
    asset_manifest = {
        "schema": "ps120-round4-raw-assets-v1",
        "tag": "ps120-validation-round4-raw-v1",
        "raw_manifest_sha256": sha256_file(RAW_MANIFEST),
        "file_count": manifest["file_count"],
        "file_bytes": manifest["bytes"],
        "assets": assets,
    }
    (output_dir / "assets.json").write_text(json.dumps(asset_manifest, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True, help="validation-results root with raw files")
    parser.add_argument("--output-dir", type=Path, required=True, help="empty directory for tar assets")
    args = parser.parse_args()
    build(args.source_root, args.output_dir)


if __name__ == "__main__":
    main()
