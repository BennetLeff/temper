#!/usr/bin/env python3
"""KiCad oracle for flashed versus nominal pad and via layer copper."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

import pcbnew as pcb

EXPECTED_BOARD_SHA256 = "a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155"
CASES = (("Q3", "1", pcb.In1_Cu, False),
         ("Q3", "3", pcb.In1_Cu, True),
         ("C38", "1", pcb.F_Cu, False),
         ("C38", "1", pcb.In2_Cu, True))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--board", type=Path, required=True)
    p.add_argument("--export", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    board_hash = hashlib.sha256(args.board.read_bytes()).hexdigest()
    if board_hash != EXPECTED_BOARD_SHA256:
        raise ValueError(f"board hash changed: {board_hash}")
    board = pcb.LoadBoard(str(args.board.resolve(strict=True)))
    export = json.load(gzip.open(args.export,"rt"))
    if export["board_sha256"] != board_hash:
        raise ValueError("export/board mismatch")
    pads = {(f.GetReference(),pad.GetNumber()):pad for f in board.GetFootprints() for pad in f.Pads()}
    rows=[]
    for ref,num,lid,expected in CASES:
        pad=pads[ref,num]
        layer=board.GetLayerName(lid)
        flashed=bool(pad.FlashLayer(lid))
        exported=any(item["kind"]=="pad" and item.get("ref")==f"{ref}.{num}" and item["layer"]==layer
                     for item in export["primitives"])
        if flashed!=expected or exported!=expected:
            raise AssertionError(f"{ref}.{num}/{layer}: KiCad flash={flashed}, export={exported}, expected={expected}")
        rows.append({"ref":f"{ref}.{num}","layer":layer,"is_on_layer":bool(pad.IsOnLayer(lid)),
                     "remove_unconnected":bool(pad.GetRemoveUnconnected()),"flashed":flashed,"exported":exported})
    via=next(pcb.Cast_to_PCB_VIA(t) for t in board.GetTracks() if t.Type()==pcb.PCB_VIA_T)
    via_layers={board.GetLayerName(lid):bool(via.FlashLayer(lid)) for lid in (pcb.F_Cu,pcb.In1_Cu,pcb.In2_Cu,pcb.B_Cu)}
    result={"status":"PASS","board_sha256":board_hash,
            "export_sha256":hashlib.sha256(args.export.read_bytes()).hexdigest(),
            "kicad_version":pcb.Version(),"pad_cases":rows,
            "sample_via_flash_layers":via_layers,
            "suppressed_pad_layer_count":export["suppressed_pad_layer_count"],
            "suppressed_via_layer_count":export["suppressed_via_layer_count"]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
