#!/usr/bin/env python3
"""Losslessly bundle local run evidence and verify every safe archive member."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import tarfile
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
ARCHIVE = HERE / "raw-evidence.tar.gz"
LEDGER = HERE / "raw-evidence-manifest.json"
ALLOWED_NAMES = {".spiceinit", "case.cir", "params.inc", "run.log", "result.json"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build() -> None:
    paths = sorted(p for p in (HERE / "raw").rglob("*") if p.is_file())
    records = {}
    with (
        ARCHIVE.open("wb") as dest,
        gzip.GzipFile(filename="", fileobj=dest, mode="wb", mtime=0) as zipped,
        tarfile.open(fileobj=zipped, mode="w") as archive,
    ):
        for path in paths:
            if path.is_symlink() or path.name not in ALLOWED_NAMES:
                raise ValueError(
                    f"Unexpected raw evidence member (never bundle vendor libraries): {path}"
                )
            name = path.relative_to(HERE).as_posix()
            records[name] = {"sha256": digest(path.read_bytes()), "size": path.stat().st_size}
            info = archive.gettarinfo(str(path), arcname=name)
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ""
            info.mode = 0o644
            with path.open("rb") as source:
                archive.addfile(info, source)
    LEDGER.write_text(
        json.dumps(
            {
                "archive_sha256": digest(ARCHIVE.read_bytes()),
                "member_count": len(records),
                "members": records,
            },
            indent=2,
        )
        + "\n"
    )


def verify() -> None:
    ledger = json.loads(LEDGER.read_text())
    if digest(ARCHIVE.read_bytes()) != ledger["archive_sha256"]:
        raise ValueError("Archive digest mismatch")
    seen = set()
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if (
                not member.isfile()
                or name.is_absolute()
                or ".." in name.parts
                or name.parts[0] != "raw"
                or name.name not in ALLOWED_NAMES
            ):
                raise ValueError(f"Unsafe/unexpected member: {member.name}")
            if member.name in seen:
                raise ValueError(f"Duplicate member: {member.name}")
            seen.add(member.name)
            content = archive.extractfile(member)
            if content is None:
                raise ValueError(f"Unreadable member: {member.name}")
            data = content.read()
            if ledger["members"].get(member.name) != {"sha256": digest(data), "size": len(data)}:
                raise ValueError(f"Member digest mismatch: {member.name}")
    if seen != set(ledger["members"]) or len(seen) != ledger["member_count"]:
        raise ValueError("Archive inventory mismatch")
    print(
        f"Verified {len(seen)} regular relative-path members; no symlinks or vendor library; SHA-256 {ledger['archive_sha256']}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--verify", action="store_true", help="Verify existing archive without rebuilding"
    )
    args = parser.parse_args()
    if not args.verify:
        build()
    verify()
