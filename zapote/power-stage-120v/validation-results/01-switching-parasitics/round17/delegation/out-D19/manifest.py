#!/usr/bin/env python3
"""Record or verify the exact D-19 deliverable files; never include vendor code."""

import argparse
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "deliverable-manifest.json"


def inventory():
    files = {}
    for path in sorted(HERE.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Unexpected symlink: {path}")
        if not path.is_file() or path == MANIFEST:
            continue
        if path.suffix in (".lib", ".pyc"):
            raise ValueError(f"Forbidden artifact: {path}")
        data = path.read_bytes()
        files[str(path.relative_to(HERE))] = {
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    return files


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    actual = inventory()
    if args.verify:
        assert actual == json.loads(MANIFEST.read_text()), "Deliverable inventory changed"
        print("PASS:", len(actual), "files verified")
    else:
        MANIFEST.write_text(json.dumps(actual, indent=2) + "\n")
        print("Recorded", len(actual), "files")


if __name__ == "__main__":
    main()
