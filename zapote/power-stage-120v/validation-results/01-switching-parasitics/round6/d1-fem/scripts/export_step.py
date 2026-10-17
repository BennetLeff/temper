"""Export and structurally inspect the pinned native-17 copper STEP.

KiCad 10.0.4 currently returns 2 after OCC fuse warnings while still writing
an importable STEP. This script records that status and accepts only an
independently imported 84-solid result on the pinned board content hash.
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import gmsh

BOARD_SHA256 = "16e8b70bb7f2bc9020ea574022c13661cd09640ca3a52db1ff43f9f6db976162"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_step(path: Path) -> dict:
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        imported = gmsh.model.occ.importShapes(str(path))
        gmsh.model.occ.synchronize()
        solids = gmsh.model.getEntities(3)
        if len(imported) != 84 or len(solids) != 84:
            raise ValueError(f"expected 84 imported solids, got {len(imported)}/{len(solids)}")
        zlo = min(gmsh.model.getBoundingBox(3, tag)[2] for _, tag in solids)
        zhi = max(gmsh.model.getBoundingBox(3, tag)[5] for _, tag in solids)
        if not (-0.071 < zlo < -0.069 and 1.562 < zhi < 1.564):
            raise ValueError(f"wrong native-17 layer elevations: {zlo}, {zhi}")
        return {"solids": len(solids), "surfaces": len(gmsh.model.getEntities(2)),
                "z_extent_mm": [zlo, zhi]}
    finally:
        gmsh.finalize()


def export(board: Path, output: Path) -> dict:
    board_hash = sha256(board)
    if board_hash != BOARD_SHA256:
        raise ValueError(f"native-17 board SHA mismatch: {board_hash}")
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"refusing pre-existing STEP output: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    command = ["kicad-cli", "pcb", "export", "step", "--no-components",
               "--no-board-body", "--include-tracks", "--include-pads",
               "--include-zones", "--include-inner-copper", "--fuse-shapes",
               "--no-extra-pad-thickness", "--output", str(output), str(board)]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode not in (0, 2) or not output.is_file():
        raise RuntimeError(f"STEP export failed ({result.returncode}): {result.stderr}")
    geometry = inspect_step(output)
    return {"board_sha256": board_hash, "step_sha256": sha256(output),
            "kicad_exit_code": result.returncode, "command": command,
            "stdout": result.stdout, "stderr": result.stderr, "geometry": geometry}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("board", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(export(args.board, args.output), indent=2))
