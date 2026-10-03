#!/usr/bin/env python3
"""Record hashes of ignored D1 diagnostic decks, logs, and calibration runs."""
from __future__ import annotations

import json

from audit_geometry import HERE, digest


def main() -> None:
    root = HERE / "extraction"
    files = sorted(path for path in root.rglob("*") if path.is_file())
    rows = [
        {"path": str(path.relative_to(HERE)), "bytes": path.stat().st_size,
         "sha256": digest(path)}
        for path in files
    ]
    source_files = sorted((*HERE.glob("*.py"), *HERE.glob("*.json")))
    source_rows = [
        {"path": path.name, "bytes": path.stat().st_size, "sha256": digest(path)}
        for path in source_files if path.name != "raw-manifest.json"
    ]
    result = {"status": "RAW_DIAGNOSTICS_UNQUALIFIED", "file_count": len(rows),
              "total_bytes": sum(row["bytes"] for row in rows), "files": rows,
              "source_files": source_rows}
    (HERE / "raw-manifest.json").write_text(json.dumps(result, indent=2) + "\n")
    print(f"Recorded {len(rows)} ignored diagnostic files")


if __name__ == "__main__":
    main()
