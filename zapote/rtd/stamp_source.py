"""Copy compiled part identity fields into native KiCad footprint metadata."""
import json
from pathlib import Path
import sys
import pcbnew

board_path, manifest_path = map(Path, sys.argv[1:])
manifest = json.loads(manifest_path.read_text())
by_ref = {c["reference"]: c for c in manifest["bridge"]["components"]}
board = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(board_path), None)
for fp in board.GetFootprints():
    comp = by_ref.get(fp.GetReference())
    if comp is None:
        continue
    path = comp["instance_path"]
    attrs = manifest["source_attributes"][path]
    fp.SetField("MPN", attrs["mpn"])
    fp.SetField("SourceInstance", path)
    fp.SetField("SourceValue", str(attrs.get("value") or ""))
    fp.SetValue(attrs["mpn"])
pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(board_path), board)
