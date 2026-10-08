#!/usr/bin/env python3
"""Export native KiCad copper and board outline for the one-off thermal solve.

Run with KiCad's Python. Pad polygons come from GetEffectivePolygon, so this
script does not implement or guess KiCad's footprint rotation convention.
"""
from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pcbnew as pcb


def main() -> None:
    board_path, output_path = map(Path, sys.argv[1:3])
    source = Path(__file__).resolve().parents[2] / "round2/scripts/extract_power_copper.py"
    spec = importlib.util.spec_from_file_location("copper_extract", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    board = pcb.LoadBoard(str(board_path))
    module.NETS = {z.GetNetname() for z in board.Zones()}
    module.NETS.update(p.GetNetname() for f in board.GetFootprints() for p in f.Pads())
    module.NETS.update(t.GetNetname() for t in board.GetTracks())
    data = module.export(board_path)
    outline = pcb.SHAPE_POLY_SET()
    if not board.GetBoardPolygonOutlines(outline, False) or outline.OutlineCount() != 1:
        raise RuntimeError("expected one closed native board outline")
    data["outline"] = module.polygon_set(outline)[0]
    data["extractor_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
    data["kicad_version"] = pcb.Version()
    raw = json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as out:
        with gzip.GzipFile(fileobj=out, mode="wb", filename="", mtime=0) as stream:
            stream.write(raw)
    print(json.dumps({"board_sha256": data["board_sha256"],
                      "primitive_count": len(data["primitives"]),
                      "net_count": len(module.NETS), "outline_holes": len(data["outline"]["holes"]),
                      "output_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest()}))


if __name__ == "__main__":
    main()
