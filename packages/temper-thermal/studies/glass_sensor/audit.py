"""Input/output integrity checks for the standalone Rust study; no physics logic."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(study: Path, repo: Path, output: Path, phase: str) -> None:
    manifest = json.loads((study / "input-provenance.json").read_text())
    for entry in manifest["inputs"]:
        base = study if entry["kind"] == "snapshot" else repo
        path = base / entry["path"]
        if digest(path) != entry["sha256"]:
            raise SystemExit(
                f"Input hash changed: {path}. Review before regenerating the manifest."
            )
    if phase == "before":
        print(f"Verified {len(manifest['inputs'])} input hashes")
        return
    # Normalize generated presentation/log whitespace, never the input snapshots.
    for path in output.iterdir():
        if path.suffix in {".svg", ".txt"}:
            text = "\n".join(line.rstrip() for line in path.read_text().splitlines())
            path.write_text(text.rstrip() + "\n")
    import matplotlib
    import numpy

    record = {
        "status": "executed simulation; physical validation not performed",
        "input_manifest_sha256": digest(study / "input-provenance.json"),
        "rustc": subprocess.check_output(["rustc", "--version"], text=True).strip(),
        "python": sys.version,
        "numpy": numpy.__version__,
        "matplotlib": matplotlib.__version__,
        "platform": platform.platform(),
        "sources": {
            p.name: digest(p)
            for p in study.iterdir()
            if p.suffix in {".rs", ".py", ".sh", ".c"}
        },
        "outputs": {
            p.name: digest(p)
            for p in output.iterdir()
            if p.is_file() and p.name != "run-provenance.json"
        },
    }
    (output / "run-provenance.json").write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n"
    )
    print("Recorded source and output hashes")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
