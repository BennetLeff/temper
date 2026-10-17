#!/usr/bin/env python3
"""Build the round-3 raw-evidence tarball from manifest.json, deterministically.

Run from zapote/power-stage-120v/validation-results:
    python3 round3-coordination/raw-evidence/build_archive.py OUT.tar
Every file is checked against its manifest SHA-256 before it is added.
Entries are sorted, with mtime 0 and uid/gid 0, so the same files give the
same tarball bytes.
"""
import hashlib, json, sys, tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
manifest = json.loads((HERE / "manifest.json").read_text())
out = sys.argv[1]
with tarfile.open(out, "w", format=tarfile.PAX_FORMAT) as tar:
    for row in sorted(manifest["files"], key=lambda r: r["path"]):
        data = Path(row["path"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != row["sha256"]:
            sys.exit(f"hash mismatch: {row['path']}")
        info = tarfile.TarInfo(row["path"])
        info.size, info.mtime, info.mode = len(data), 0, 0o644
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        import io
        tar.addfile(info, io.BytesIO(data))
print(hashlib.sha256(Path(out).read_bytes()).hexdigest(), out)
