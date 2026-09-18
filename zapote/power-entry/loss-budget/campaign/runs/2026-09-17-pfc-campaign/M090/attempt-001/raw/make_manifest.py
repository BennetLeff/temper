#!/usr/bin/env python3
"""Build raw/capture_log.json (URL/HTTP/hash for every captured source) and
manifest.json (SHA-256 of every produced file except itself)."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

CAPTURES = [
    ("raw/760800301.pdf", "datasheet_primary", "760800301",
     "zapote/power-entry/loss-budget/sources/760800301.pdf (delivered bundle)",
     "application/pdf", 200),
    ("raw/760801403.pdf", "datasheet_primary", "760801403",
     "https://www.we-online.com/components/products/datasheet/760801403.pdf",
     "application/pdf", 200),
    ("raw/760801202.pdf", "datasheet_primary", "760801202",
     "https://www.we-online.com/components/products/datasheet/760801202.pdf",
     "application/pdf", 200),
    ("raw/760801101.pdf", "datasheet_primary", "760801101",
     "https://www.we-online.com/components/products/datasheet/760801101.pdf",
     "application/pdf", 200),
    ("raw/760800202.pdf", "datasheet_primary", "760800202",
     "https://www.we-online.com/components/products/datasheet/760800202.pdf",
     "application/pdf", 200),
    ("raw/760800403.pdf", "datasheet_primary", "760800403",
     "https://www.we-online.com/components/products/datasheet/760800403.pdf",
     "application/pdf", 200),
    ("raw/WE-TORPFC_catalog.html", "manufacturer_catalog_secondary", "WE-TORPFC family",
     "https://www.we-online.com/en/components/products/WE-TORPFC",
     "text/html; charset=UTF-8", 200),
]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def main():
    cap = []
    for rel, kind, ident, url, ctype, http in CAPTURES:
        p = ROOT / rel
        cap.append({
            "path": rel, "kind": kind, "identifier": ident, "url": url,
            "http_status": http, "content_type": ctype,
            "bytes": p.stat().st_size, "sha256": sha256(p),
            "retrieved_at_utc": "2026-09-17T23:10:00Z",
            "is_datasheet": rel.endswith(".pdf"),
            "note": ("HTML secondary listing; NOT hashed as a datasheet"
                     if rel.endswith(".html") else None),
        })
    (HERE / "capture_log.json").write_text(json.dumps({
        "schema": "zapote.pfc.capture-log.v1",
        "captures": cap,
        "capture_failures": [
            {"target": "DigiKey per-part pages (760801101, 760801202)",
             "result": "no per-part price/stock obtained; search returned unrelated pages",
             "attempts": 1},
            {"target": "any published core-loss or AC-winding-loss curve for WE-TORPFC",
             "result": "not present in the datasheets (0 attempts: source absence, not a URL failure)",
             "attempts": 0},
        ],
    }, indent=2))

    produced = sorted(
        [p for p in ROOT.rglob("*")
         if p.is_file() and p.name not in ("manifest.json", "dispatch.json")]
    )
    entries = {}
    for p in produced:
        entries[str(p.relative_to(ROOT))] = {
            "sha256": sha256(p), "bytes": p.stat().st_size}
    manifest = {
        "schema": "zapote.pfc.manifest.v1",
        "task_id": "M090", "attempt_id": "attempt-001",
        "manifest_hash_note": "manifest.json is excluded from its own hash list",
        "produced_file_count": len(entries),
        "produced_files": entries,
        "input_files": {
            "dispatch.json": {"sha256": sha256(ROOT / "dispatch.json")},
        },
    }
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
