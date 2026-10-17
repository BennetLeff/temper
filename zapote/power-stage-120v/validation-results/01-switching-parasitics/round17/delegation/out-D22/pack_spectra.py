#!/usr/bin/env python3
"""Archive every receiver-line CSV with member hashes, keeping the PR inspectable."""

import gzip
import hashlib
import json
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def verify_archive(record: dict, root: Path = HERE) -> int:
    """Verify exact member coverage and bytes without extracting any paths."""
    path = root / record["archive"]
    expected = record["members_sha256"]
    if not expected or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
        raise ValueError(f"empty or changed archive: {path.name}")
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) != len(expected) or {m.name for m in members} != set(expected):
            raise ValueError(f"archive member coverage differs: {path.name}")
        for member in members:
            if not member.isfile():
                raise ValueError(f"non-file archive member: {member.name}")
            stream = archive.extractfile(member)
            if stream is None or hashlib.sha256(stream.read()).hexdigest() != expected[member.name]:
                raise ValueError(f"archive member changed: {member.name}")
    return len(expected)


def main() -> None:
    paths = sorted((HERE / "qualified-spectra").glob("*.csv.gz"))
    if not paths or any(p.is_symlink() or not p.is_file() for p in paths):
        raise ValueError("regenerate the receiver CSVs with qualify_filter.py before packing")
    members = {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    manifest = HERE / "receiver-spectra-archive.json"
    if manifest.exists():
        previous = set().union(*(set(r["members_sha256"]) for r in json.loads(manifest.read_text())))
        if not previous <= set(members):
            raise ValueError("missing previously archived spectra; regenerate the complete receiver set")
    temporary = HERE / ".receiver-spectra.tar.gz.tmp"
    target = HERE / "receiver-spectra.tar.gz"
    with temporary.open("wb") as output:
        with gzip.GzipFile(filename="", fileobj=output, mode="wb", mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for path in paths:
                    info = archive.gettarinfo(str(path), arcname=str(path.relative_to(HERE)))
                    info.mtime = info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mode = 0o644
                    info.pax_headers = {}
                    with path.open("rb") as source:
                        archive.addfile(info, source)
    if temporary.stat().st_size >= 100 * 1024 * 1024:
        raise ValueError("archive exceeds the GitHub file-size limit; split before publishing")
    record = {"archive": temporary.name, "sha256": hashlib.sha256(temporary.read_bytes()).hexdigest(), "members_sha256": members}
    verify_archive(record)
    temporary.replace(target)
    record["archive"] = target.name
    manifest.write_text(json.dumps([record], indent=2) + "\n")
    for path in paths:
        path.unlink()
    print(f"PASS: {len(paths)} receiver CSVs archived and byte-verified before removing loose copies")


if __name__ == "__main__":
    main()
