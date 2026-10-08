#!/usr/bin/env python3
"""Download or use local round-4 assets, verify them, and restore raw files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import tarfile
import tempfile
from pathlib import Path

from build_archive import RAW_MANIFEST, load_rows, sha256_file, split_rows

HERE = Path(__file__).resolve().parent
REPOSITORY = "BennetLeff/temper"


def checked_assets() -> tuple[dict, list[list[dict]]]:
    asset_manifest = json.loads((HERE / "assets.json").read_text())
    raw_manifest, rows = load_rows()
    parts = split_rows(rows)
    if (
        asset_manifest["schema"] != "ps120-round4-raw-assets-v1"
        or asset_manifest["raw_manifest_sha256"] != sha256_file(RAW_MANIFEST)
        or asset_manifest["file_count"] != raw_manifest["file_count"]
        or asset_manifest["file_bytes"] != raw_manifest["bytes"]
        or len(asset_manifest["assets"]) != len(parts)
    ):
        raise ValueError("asset manifest does not match the committed raw manifest")
    for index, (asset, part) in enumerate(zip(asset_manifest["assets"], parts, strict=True), 1):
        expected_name = f"ps120-round4-raw-part-{index:02d}-of-{len(parts):02d}.tar"
        if (
            asset["name"] != expected_name
            or asset["file_count"] != len(part)
            or asset["first_path"] != part[0]["path"]
            or asset["last_path"] != part[-1]["path"]
            or not isinstance(asset["bytes"], int)
            or asset["bytes"] >= 2_000_000_000
            or len(asset["sha256"]) != 64
        ):
            raise ValueError(f"invalid asset entry: {expected_name}")
    return asset_manifest, parts


def existing_path(root: Path, relative: str) -> Path:
    path = root
    for component in relative.split("/"):
        path /= component
        try:
            mode = path.lstat().st_mode
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(mode):
            raise ValueError(f"destination symlink: {relative}")
        if path != root / relative and not stat.S_ISDIR(mode):
            raise ValueError(f"destination parent is not a directory: {relative}")
    return path


def matches(path: Path, row: dict) -> bool:
    if not path.exists():
        return False
    if not path.is_file() or path.stat().st_size != row["bytes"]:
        raise ValueError(f"existing file differs: {row['path']}")
    if sha256_file(path) != row["sha256"]:
        raise ValueError(f"existing file differs: {row['path']}")
    return True


def verify_asset_files(asset_manifest: dict, asset_dir: Path) -> list[Path]:
    paths = []
    for asset in asset_manifest["assets"]:
        path = asset_dir / asset["name"]
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"missing or non-regular asset: {asset['name']}")
        if path.stat().st_size != asset["bytes"] or sha256_file(path) != asset["sha256"]:
            raise ValueError(f"asset SHA-256/size mismatch: {asset['name']}")
        paths.append(path)
    return paths


def extract_part(asset_path: Path, expected: list[dict], stage: Path) -> None:
    expected_by_path = {row["path"]: row for row in expected}
    seen: set[str] = set()
    with tarfile.open(asset_path, "r:") as tar:
        for member in tar:
            name = member.name
            if name not in expected_by_path or name in seen or not member.isfile():
                raise ValueError(f"unsafe, duplicate, or unexpected archive member: {name}")
            row = expected_by_path[name]
            if member.size != row["bytes"]:
                raise ValueError(f"archive member size mismatch: {name}")
            seen.add(name)
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            source = tar.extractfile(member)
            if source is None:
                raise ValueError(f"unreadable archive member: {name}")
            with source, path.open("xb") as target:
                remaining = member.size
                while remaining:
                    block = source.read(min(1024 * 1024, remaining))
                    if not block:
                        raise ValueError(f"truncated archive member: {name}")
                    target.write(block)
                    digest.update(block)
                    remaining -= len(block)
            if digest.hexdigest() != row["sha256"]:
                raise ValueError(f"archive member SHA-256 mismatch: {name}")
    if seen != expected_by_path.keys():
        raise ValueError(f"archive missing {len(expected_by_path.keys() - seen)} members: {asset_path.name}")


def restore(asset_dir: Path, root: Path) -> None:
    asset_manifest, parts = checked_assets()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("destination root must be an existing real directory")
    # All asset hashes and every existing destination are checked before writing.
    asset_paths = verify_asset_files(asset_manifest, asset_dir)
    for part in parts:
        for row in part:
            matches(existing_path(root, row["path"]), row)
    with tempfile.TemporaryDirectory(prefix=".round4-raw-restore-", dir=root) as temp:
        stage = Path(temp)
        for asset_path, part in zip(asset_paths, parts, strict=True):
            extract_part(asset_path, part, stage)
            print(f"verified {asset_path.name}: {len(part)} files", flush=True)
        for part in parts:
            for row in part:
                destination = existing_path(root, row["path"])
                if matches(destination, row):
                    continue  # Another process restored the same verified bytes.
                destination.parent.mkdir(parents=True, exist_ok=True)
                try:
                    # Stage lives under root, so a same-filesystem hard link installs
                    # verified bytes atomically without replacing a competing file.
                    os.link(stage / row["path"], destination)
                except FileExistsError as error:
                    if not matches(existing_path(root, row["path"]), row):
                        raise ValueError(f"destination changed during restore: {row['path']}") from error
    print(f"restored and verified {asset_manifest['file_count']} files ({asset_manifest['file_bytes']} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-assets", type=Path, help="directory containing all tar parts; skips download")
    parser.add_argument("--root", type=Path, default=HERE.parent.parent, help="validation-results destination")
    args = parser.parse_args()
    manifest, _ = checked_assets()
    if args.local_assets is not None:
        restore(args.local_assets, args.root)
    else:
        with tempfile.TemporaryDirectory(prefix="ps120-round4-assets-") as temp:
            for asset in manifest["assets"]:
                subprocess.run(
                    ["gh", "release", "download", manifest["tag"], "--repo", REPOSITORY,
                     "--pattern", asset["name"], "--dir", temp],
                    check=True,
                )
            restore(Path(temp), args.root)


if __name__ == "__main__":
    main()
