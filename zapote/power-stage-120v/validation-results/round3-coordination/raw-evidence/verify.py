#!/usr/bin/env python3
"""Check every manifest.json entry exists under ROOT with its size and SHA-256."""
import hashlib, json, sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
manifest = json.loads((Path(__file__).resolve().parent / "manifest.json").read_text())
bad = []
for row in manifest["files"]:
    p = root / row["path"]
    if not p.is_file() or p.stat().st_size != row["bytes"] or hashlib.sha256(p.read_bytes()).hexdigest() != row["sha256"]:
        bad.append(row["path"])
print(f"{manifest['file_count'] - len(bad)}/{manifest['file_count']} files verified")
sys.exit(1 if bad else 0)
