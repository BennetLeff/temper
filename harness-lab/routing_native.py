"""Thin KiCad copper adapter. KiCad owns geometry and physical connectivity."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pcbnew

import native


def load(path: Path) -> pcbnew.BOARD:
    # The high-level LoadBoard/SaveBoard helpers silently propagate track nets.
    return pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(path), None)


def save(board: pcbnew.BOARD, path: Path) -> None:
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path), board)


def route(path: Path, net: str, points: list) -> None:
    board = load(path)
    for track in list(board.GetTracks()):
        if track.GetNetname() == net:
            board.Delete(track)
    for start, end in zip(points, points[1:]):
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(native.position(*start))
        track.SetEnd(native.position(*end))
        track.SetWidth(pcbnew.FromMM(0.25))
        track.SetLayer(pcbnew.F_Cu)
        track.SetNet(board.FindNet(net))
        board.Add(track)
    save(board, path)


def measure(path: Path) -> dict:
    result = native.measure(path)
    board = load(path)
    pads = {
        p.m_Uuid.AsString(): (f.GetReference() + "." + p.GetNumber(), p)
        for f in board.GetFootprints()
        for p in f.Pads()
    }
    tracks = list(board.GetTracks())
    track_ids = {t.m_Uuid.AsString() for t in tracks}
    census = [
        {
            "uuid": t.m_Uuid.AsString(),
            "kind": "segment" if t.Type() == pcbnew.PCB_TRACE_T else str(t.Type()),
            "net": t.GetNetname(),
            "layer": board.GetLayerName(t.GetLayer()),
            "width_mm": pcbnew.ToMM(t.GetWidth()),
            "start_mm": list(pcbnew.ToMM(t.GetStart())),
            "end_mm": list(pcbnew.ToMM(t.GetEnd())),
            "bounds_mm": native.bounds(t.GetBoundingBox()),
        }
        for t in tracks
    ]
    # Census raw saved nets BEFORE Build(), which itself propagates track nets.
    connectivity = pcbnew.CONNECTIVITY_DATA()
    if not connectivity.Build(board):
        raise RuntimeError("KiCad connectivity rebuild failed")
    clusters = []
    for identity, (name, pad) in sorted(pads.items(), key=lambda entry: entry[1][0]):
        connected = {
            item.m_Uuid.AsString() for item in connectivity.GetConnectedItems(pad)
        }
        connected.add(identity)
        clusters.append(
            {
                "pad": name,
                "pads": sorted(pads[item][0] for item in connected if item in pads),
                "tracks": sorted(connected & track_ids),
            }
        )
    # Only inventoried copper objects are mutable. Footprints remain fixed;
    # zones, rules, net assignments, outline, and all other state stay protected.
    # Release the native graph before constructing the canonical board.
    del connectivity
    canonical_board = load(path)
    for track in list(canonical_board.GetTracks()):
        canonical_board.Delete(track)
    with tempfile.TemporaryDirectory(prefix="temper-e00r-canonical-") as tmp:
        canonical = Path(tmp) / "canonical.kicad_pcb"
        save(canonical_board, canonical)
        result["protected_sha256"] = native.digest(canonical)
    result["routing"] = {
        "tracks": sorted(census, key=lambda t: t["uuid"]),
        "connectivity": clusters,
    }
    return result


if __name__ == "__main__":
    if pcbnew.GetBuildVersion() != "10.0.4":
        raise RuntimeError("Routing adapter requires KiCad 10.0.4")
    command, path, *args = sys.argv[1:]
    if command == "measure":
        print(json.dumps(measure(Path(path)), allow_nan=False))
    elif command == "route":
        route(Path(path), args[0], json.loads(args[1]))
    else:
        raise ValueError("Unknown routing operation")
