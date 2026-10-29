#!/usr/bin/env python3
"""Archive checked CAD deliverables and hash their exact bytes."""
from __future__ import annotations
import hashlib
import json
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parent.parent
fab = root / "manufacturing"
with ZipFile(fab / "temper-lcr-gerbers.zip", "w", ZIP_DEFLATED) as z:
    for p in sorted((fab / "gerbers").iterdir()):
        if p.is_file() and p.suffix != ".pdf":
            z.write(p, p.name)
excluded = {"manifest-sha256.json", "temper-lcr-rev-a-package.zip", "temper-lcr-rev-b-package.zip", "temper-lcr-rev-c-package.zip", "temper-lcr-rev-d-package.zip", "temper-lcr-rev-e-package.zip", "temper-lcr-rev-f-package.zip", ".DS_Store",
            "assembly-preview.kicad_pcb", "temper-lcr.kicad_prl"}
# Rev E: the package is the tracked tree (git index, so staged new files count), not every file on
# disk; untracked solver work directories had grown the Rev D manifest to 30k entries.
tracked = subprocess.run(["git", "ls-files", "-z", "."], cwd=root, check=True, capture_output=True).stdout
files = [root / n for n in sorted(tracked.decode().split("\0")) if n]
files = [p for p in files if p.is_file()
         and p.name not in excluded and "__pycache__" not in p.parts
         and "archive" not in p.relative_to(root).parts and "build" not in p.relative_to(root).parts
         and not p.name.endswith(".lck")]
manifest = {
    "format": 1,
    "status": "engineering prototype; physical validation and final vendor placement preview pending",
    "files": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
}
manifest_path = root / "manifest-sha256.json"
manifest_path.write_text(json.dumps(manifest, indent=2)+"\n")
with ZipFile(root / "temper-lcr-rev-f-package.zip", "w", ZIP_DEFLATED) as z:
    for p in files + [manifest_path]:
        z.write(p, str(Path("temper-lcr-rev-f") / p.relative_to(root)))
print(f"Archived {len(files)} files with SHA256 manifest")
