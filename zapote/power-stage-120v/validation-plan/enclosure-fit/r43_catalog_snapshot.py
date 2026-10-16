#!/usr/bin/env python3
"""Freeze the fit-relevant part of an enclosure catalog (name, group, bbox) into a tracked JSON beside the gate.

    python3 -I r43_catalog_snapshot.py /Users/bennet/Desktop/temper/output/temper-manufacturing-r43/catalog.json r43-catalog-bboxes.json

The enclosure CAD line (output/temper-manufacturing-rNN) lives outside this unit and is not tracked here, so the fit
gate reads this snapshot (stage 53, s52 footprint/3D review item 23): a clean checkout gates against the same solids,
and the source catalog's sha256 records which revision they came from.
"""
import hashlib
import json
import sys
from pathlib import Path

src, out = Path(sys.argv[1]), Path(sys.argv[2])
raw = src.read_bytes()
cat = json.loads(raw)
cur = src.with_name("CURRENT.json")
rev = json.loads(cur.read_text()).get("revision") if cur.exists() else None
items = [{"name": x["name"], "group": x["group"], "bbox": [round(float(v), 4) for v in x["bbox"]],
          "file": x.get("file"), "sha256": x.get("sha256")} for x in cat if x.get("bbox")]
out.write_text(json.dumps({"source": str(src), "source_sha256": hashlib.sha256(raw).hexdigest(), "revision": rev,
                           "frame": "enclosure world: x across, y from the front, z up (mm)", "items": items},
                          indent=0) + "\n")
print(f"{len(items)} solids from {rev} ({hashlib.sha256(raw).hexdigest()[:12]}) -> {out}")
