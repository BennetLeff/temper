"""Resolve each saved footprint's 3D model path without fetching models."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pcbnew

HERE = Path(__file__).resolve().parent
OUT = HERE.parents[1] / "native-19"
LIBRARY = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels")


def main() -> None:
    board_path = OUT / "section.kicad_pcb"
    board = pcbnew.LoadBoard(str(board_path))
    rows = []
    file_metadata: dict[Path, tuple[bool, str | None]] = {}
    for footprint in board.GetFootprints():
        models = []
        for model in footprint.Models():
            name = model.m_Filename
            path = Path(
                name.replace("${KIPRJMOD}", str(OUT)).replace(
                    "${KICAD10_3DMODEL_DIR}", str(LIBRARY)
                )
            ).resolve()
            if path not in file_metadata:
                exists = path.is_file()
                digest = hashlib.sha256(path.read_bytes()).hexdigest() if exists else None
                file_metadata[path] = (exists, digest)
            exists, digest = file_metadata[path]
            models.append(
                {
                    "path": name,
                    "exists": exists,
                    "sha256": digest,
                    "classification": "provisional envelope"
                    if "${KIPRJMOD}" in name
                    else "library package representation",
                }
            )
        rows.append({"reference": footprint.GetReference(), "models": models})
    result = {
        "board_sha256": hashlib.sha256(board_path.read_bytes()).hexdigest(),
        "footprints": len(rows),
        "without_model": [r["reference"] for r in rows if not r["models"]],
        "missing_files": [
            r["reference"] for r in rows if any(not m["exists"] for m in r["models"])
        ],
        "provisional_envelope_references": [
            r["reference"]
            for r in rows
            if any(m["classification"] == "provisional envelope" for m in r["models"])
        ],
        "models": sorted(rows, key=lambda row: row["reference"]),
        "limitation": "Path resolution does not prove manufacturer geometry, export inclusion or absence of interference.",
    }
    (OUT / "verification/model-inventory.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "models"}))
    if result["without_model"] or result["missing_files"]:
        raise SystemExit("missing component bodies: export blocked")


if __name__ == "__main__":
    main()
