#!/usr/bin/env python3
"""Attach reviewed, explicit model mappings without changing PCB placement.

Run with KiCad Python: tools/apply_3d_models.py <board> <new-output-board>
The separate output must not exist. Inspect it before promoting to the active board.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pcbnew

UNIT = Path(__file__).resolve().parents[1]


def apply(board_path: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError(f"refusing to replace {output}")
    before = hashlib.sha256(board_path.read_bytes()).hexdigest()
    board = pcbnew.LoadBoard(str(board_path.resolve()))
    footprints = {fp.GetReference(): fp for fp in board.GetFootprints()}
    changed = []
    seen = set()
    maps = sorted((UNIT / "models3d").glob("model-map-*.json"))
    if not maps:
        raise ValueError("no explicit model maps found")
    for mapping_path in maps:
        mapping = json.loads(mapping_path.read_text())
        for entry in mapping["models"]:
            name = entry["path"]
            prefix = "${KIPRJMOD}/../models3d/"
            if not name.startswith(prefix):
                raise ValueError(f"expected project-relative model path: {name}")
            asset = (UNIT / "models3d" / name.removeprefix(prefix)).resolve()
            if not asset.is_relative_to((UNIT / "models3d").resolve()) or not asset.is_file():
                raise ValueError(f"missing or out-of-scope asset: {asset}")
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()
            if entry.get("sha256") and entry["sha256"] != digest:
                raise ValueError(f"asset differs from recorded digest: {asset}")
            for reference in entry["references"]:
                if reference in seen:
                    raise ValueError(f"duplicate model assignment: {reference}")
                seen.add(reference)
                footprint = footprints[reference]
                if footprint.GetFPIDAsString() != entry["footprint"]:
                    raise ValueError(f"footprint changed for {reference}")
                model = pcbnew.FP_3DMODEL()
                model.m_Filename = name
                model.m_Offset = pcbnew.VECTOR3D(*entry["offset_mm"])
                model.m_Rotation = pcbnew.VECTOR3D(*entry["rotation_deg"])
                model.m_Scale = pcbnew.VECTOR3D(*entry["scale"])
                model.m_Show = True
                footprint.Models().clear()
                footprint.Add3DModel(model)
                changed.append({"reference": reference, "path": name,
                                "asset_sha256": digest, "status": entry["status"]})
    if hashlib.sha256(board_path.read_bytes()).hexdigest() != before:
        raise ValueError("input board changed during model application")
    pcbnew.SaveBoard(str(output.resolve()), board)
    return {"input_board_sha256": before,
            "output_board_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "models_attached": changed,
            "scope": "visual/assembly models only; no physical qualification"}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    print(json.dumps(apply(Path(sys.argv[1]), Path(sys.argv[2])), indent=2))
