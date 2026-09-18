#!/usr/bin/env python3
"""Build manifest.json: SHA-256 + byte size of every produced file.

Excludes manifest.json itself and the delivered dispatch.json. Run from the
attempt directory: python3 raw/build_manifest.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ATTEMPT = Path(__file__).resolve().parent.parent
EXCLUDE = {"manifest.json", "dispatch.json"}

files = []
for p in sorted(ATTEMPT.rglob("*")):
    if not p.is_file():
        continue
    rel = p.relative_to(ATTEMPT)
    if rel.name in EXCLUDE:
        continue
    b = p.read_bytes()
    files.append({"path": str(rel), "sha256": hashlib.sha256(b).hexdigest(), "bytes": len(b)})

manifest = {
    "schema": "pfc-campaign-manifest/v1",
    "task_id": "AR-MERSEN",
    "attempt_id": "attempt-001",
    "campaign_id": "2026-09-17-pfc-campaign",
    "algorithm": "sha256",
    "note": "SHA-256 of every file produced by this attempt except manifest.json itself and dispatch.json (the delivered input).",
    "files": files,
}
(ATTEMPT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(f"wrote manifest.json: {len(files)} files")
