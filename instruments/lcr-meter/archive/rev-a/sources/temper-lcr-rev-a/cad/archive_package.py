#!/usr/bin/env python3
"""Archive checked CAD deliverables and hash their exact bytes."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parent.parent
fab = root / "manufacturing"
with ZipFile(fab / "temper-lcr-gerbers.zip", "w", ZIP_DEFLATED) as z:
    for p in sorted((fab / "gerbers").iterdir()):
        if p.is_file() and p.suffix != ".pdf":
            z.write(p, p.name)
excluded = {"manifest-sha256.json", "temper-lcr-rev-a-package.zip", ".DS_Store",
            "assembly-preview.kicad_pcb", "temper-lcr.kicad_prl"}
files = [p for p in sorted(root.rglob("*")) if p.is_file()
         and p.name not in excluded and "__pycache__" not in p.parts
         and "target" not in p.parts and not p.name.endswith(".lck")]
manifest = {
    "format": 1,
    "status": "engineering prototype; physical validation and final vendor placement preview pending",
    "files": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
}
manifest_path = root / "manifest-sha256.json"
manifest_path.write_text(json.dumps(manifest, indent=2)+"\n")
with ZipFile(root / "temper-lcr-rev-a-package.zip", "w", ZIP_DEFLATED) as z:
    for p in files + [manifest_path]:
        z.write(p, str(Path("temper-lcr-rev-a") / p.relative_to(root)))
print(f"Archived {len(files)} files with SHA256 manifest")
