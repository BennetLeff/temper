"""P3 U2 native geometry extractor for the control-assembly composition.

Reads a KiCad ``.kicad_pcb`` through ``pcbnew`` (the same engine the host
adapters use) and prints a JSON geometry census: footprint poses, pad
positions/nets, tracks (segments and vias), and non-rule-area zones.

This module owns no policy and draws nothing. It exists because the
hand-authored buck prototype board is not parseable by the pure-Python
``kiutils`` reader (unquoted net names), while the generated candidate
boards are. Extraction therefore goes through native KiCad for every view,
so the assembly and the prototype are read by one instrument.

Run as a script under the KiCad Python interpreter::

    $(harness.KICAD_PYTHON) harness-lab/assembly_geometry.py extract <board>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pcbnew


def _mm(vector) -> list:
    return [float(pcbnew.ToMM(vector.x)), float(pcbnew.ToMM(vector.y))]


def extract(path: Path) -> dict:
    board = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(path), None)
    footprints = []
    for fp in board.GetFootprints():
        pads = []
        for pad in fp.Pads():
            pads.append(
                {
                    "number": pad.GetNumber(),
                    "net": pad.GetNetname(),
                    "position_mm": _mm(pad.GetPosition()),
                }
            )
        footprints.append(
            {
                "reference": fp.GetReference(),
                "footprint": fp.GetFPID().GetLibItemName().wx_str(),
                "position_mm": _mm(fp.GetPosition()),
                "angle_deg": float(fp.GetOrientationDegrees()),
                "pads": sorted(pads, key=lambda p: p["number"]),
            }
        )
    tracks = []
    for track in board.GetTracks():
        kind = track.Type()
        if kind == pcbnew.PCB_TRACE_T:
            entry = {
                "kind": "segment",
                "net": track.GetNetname(),
                "layer": board.GetLayerName(track.GetLayer()),
                "width_mm": float(pcbnew.ToMM(track.GetWidth())),
                "start_mm": _mm(track.GetStart()),
                "end_mm": _mm(track.GetEnd()),
            }
        elif kind == pcbnew.PCB_VIA_T:
            entry = {
                "kind": "via",
                "net": track.GetNetname(),
                "layer": "F.Cu-B.Cu",
                "width_mm": float(pcbnew.ToMM(track.GetWidth())),
                "drill_mm": float(pcbnew.ToMM(track.GetDrill())),
                "position_mm": _mm(track.GetPosition()),
            }
        else:
            continue
        entry["uuid"] = track.m_Uuid.AsString()
        tracks.append(entry)
    zones = []
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        zones.append(
            {
                "uuid": zone.m_Uuid.AsString(),
                "net": zone.GetNetname(),
                "layer": board.GetLayerName(zone.GetLayer()),
                "filled": bool(zone.IsFilled()),
            }
        )
    return {
        "schema": "control-assembly.geometry-extract.v1",
        "board": str(path),
        "kicad_version": pcbnew.GetBuildVersion(),
        "copper_layers": sorted(
            board.GetLayerName(layer)
            for layer in board.GetEnabledLayers().Seq()
            if board.GetLayerName(layer).endswith(".Cu")
        ),
        "footprints": sorted(footprints, key=lambda f: f["reference"]),
        "tracks": sorted(tracks, key=lambda t: t["uuid"]),
        "zones": sorted(zones, key=lambda z: z["uuid"]),
    }


def connectivity(path: Path) -> dict:
    """Native per-net pad clusters (union of pads joined by copper items)."""
    board = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(path), None)
    data = pcbnew.CONNECTIVITY_DATA()
    if not data.Build(board):
        raise RuntimeError("KiCad connectivity rebuild failed")
    pad_items = {}
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            name = f"{footprint.GetReference()}.{pad.GetNumber()}"
            pad_items[name] = pad
    parent = {name: name for name in pad_items}

    def find(name):
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_item: dict = {}
    for name, pad in pad_items.items():
        for item in data.GetConnectedItems(pad):
            by_item.setdefault(item.m_Uuid.AsString(), set()).add(name)
    for members in by_item.values():
        members = sorted(members)
        for other in members[1:]:
            union(members[0], other)
    nets: dict = {}
    for name, pad in pad_items.items():
        net = pad.GetNetname()
        nets.setdefault(net, []).append(name)
    result = {}
    for net, names in sorted(nets.items()):
        groups: dict = {}
        for name in names:
            groups.setdefault(find(name), []).append(name)
        result[net] = {
            "pads": sorted(names),
            "clusters": sorted(sorted(group) for group in groups.values()),
            "pad_count": len(names),
            "cluster_count": len(groups),
        }
    return {
        "schema": "control-assembly.connectivity.v1",
        "board": str(path),
        "kicad_version": pcbnew.GetBuildVersion(),
        "nets": result,
    }


def main() -> None:
    command, path = sys.argv[1:3]
    if command == "extract":
        print(json.dumps(extract(Path(path)), allow_nan=False))
    elif command == "connectivity":
        print(json.dumps(connectivity(Path(path)), allow_nan=False))
    else:
        raise ValueError(f"unknown operation {command!r}")


if __name__ == "__main__":
    main()
