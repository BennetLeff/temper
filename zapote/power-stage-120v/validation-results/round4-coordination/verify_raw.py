#!/usr/bin/env python3
"""Verify the local round-4 raw handback; this does not qualify its physics."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="validation-results directory containing restored raw files")
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads(Path(__file__).with_name("raw-manifest.json").read_text())
    rows = manifest["files"]
    if len(rows) != manifest["file_count"] or len({r["path"] for r in rows}) != len(rows):
        raise SystemExit("Manifest count or duplicate-path error")
    bad = []
    for row in rows:
        path = (root / row["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size != row["bytes"]:
            bad.append(row["path"])
            continue
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != row["sha256"]:
                bad.append(row["path"])
    print(f"{len(rows) - len(bad)}/{len(rows)} round-4 local files verified")
    if bad:
        print("\n".join(bad))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
