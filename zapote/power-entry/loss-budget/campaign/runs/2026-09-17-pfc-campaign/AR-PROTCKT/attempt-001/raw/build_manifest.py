#!/usr/bin/env python3
"""Build manifest.json: SHA-256 of every produced file except manifest.json and the delivered dispatch.json."""
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
    rel = p.relative_to(ATTEMPT).as_posix()
    if rel in EXCLUDE:
        continue
    data = p.read_bytes()
    files.append(
        {"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    )

manifest = {
    "schema": "pfc-campaign-manifest/v1",
    "task_id": "AR-PROTCKT",
    "attempt_id": "attempt-001",
    "campaign_id": "2026-09-17-pfc-campaign",
    "algorithm": "sha256",
    "note": "SHA-256 of every file produced by this attempt except manifest.json itself and dispatch.json (the delivered input).",
    "files": files,
}
(ATTEMPT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(f"wrote manifest.json with {len(files)} files")
