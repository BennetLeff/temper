#!/usr/bin/env python3
"""Extract native KiCad footprint, pad, copper and connectivity data.

Run with the KiCad bundled Python.  This is intentionally a measurement
projection for manual route authoring; it contains no placement, routing or
engineering verdict logic.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def xy(point) -> list[float]:
    return [float(pcbnew.ToMM(point.x)), float(pcbnew.ToMM(point.y))]


def field(footprint, name: str, default: str) -> str:
    try:
        return footprint.GetFieldText(name) or default
    except (AttributeError, KeyError):
        return default


def extract(board_path: Path) -> dict:
    global pcbnew
    import pcbnew  # type: ignore[import-not-found]

    board = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(board_path), None)
    components = []
    connections = []
    for footprint in board.GetFootprints():
        instance = field(footprint, "SourceInstance", field(footprint, "Sheetpath", footprint.GetReference()))
        pads = []
        for pad in footprint.Pads():
            entry = {
                "pad": str(pad.GetNumber()),
                "uuid": pad.m_Uuid.AsString(),
                "net": pad.GetNetname(),
                "position_mm": xy(pad.GetPosition()),
                "size_mm": xy(pad.GetSize()),
                "drill_mm": xy(pad.GetDrillSize()),
                "orientation_deg": float(pad.GetOrientationDegrees()),
                "shape": int(pad.GetShape()),
                "layers": [board.GetLayerName(layer) for layer in pad.GetLayerSet().Seq()],
            }
            pads.append(entry)
            if entry["net"]:
                connections.append(
                    {
                        "component": instance,
                        "reference": footprint.GetReference(),
                        "pad": entry["pad"],
                        "net": entry["net"],
                        "position_mm": entry["position_mm"],
                    }
                )
        components.append(
            {
                "id": instance,
                "reference": footprint.GetReference(),
                "uuid": footprint.m_Uuid.AsString(),
                "mpn": field(footprint, "MPN", footprint.GetValue() or "UNVERIFIED"),
                "kind": footprint.GetFPID().GetLibItemName().wx_str(),
                "position_mm": xy(footprint.GetPosition()),
                "angle_deg": float(footprint.GetOrientationDegrees()),
                "footprint_pads": pads,
            }
        )

    traces = []
    vias = []
    for item in board.GetTracks():
        if item.Type() == pcbnew.PCB_VIA_T:
            vias.append(
                {
                    "uuid": item.m_Uuid.AsString(),
                    "net": item.GetNetname(),
                    "position_mm": xy(item.GetPosition()),
                    "from_layer": board.GetLayerName(item.TopLayer()),
                    "to_layer": board.GetLayerName(item.BottomLayer()),
                    "drill_mm": float(pcbnew.ToMM(item.GetDrillValue())),
                    "diameter_mm": float(pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu))),
                }
            )
        elif item.Type() == pcbnew.PCB_TRACE_T:
            traces.append(
                {
                    "uuid": item.m_Uuid.AsString(),
                    "net": item.GetNetname(),
                    "layer": board.GetLayerName(item.GetLayer()),
                    "width_mm": float(pcbnew.ToMM(item.GetWidth())),
                    "points_mm": [xy(item.GetStart()), xy(item.GetEnd())],
                }
            )
        else:
            raise ValueError(f"unsupported copper geometry: {item.Type()}")

    # Keep the existing native connectivity apparatus as the source of truth.
    connectivity_data = pcbnew.CONNECTIVITY_DATA()
    if not connectivity_data.Build(board):
        raise RuntimeError("KiCad connectivity rebuild failed")
    pad_items = {
        f"{fp.GetReference()}.{pad.GetNumber()}": pad
        for fp in board.GetFootprints()
        for pad in fp.Pads()
    }
    parent = {name: name for name in pad_items}

    def find(name: str) -> str:
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    def union(left: str, right: str) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    by_item: dict[str, set[str]] = {}
    for pad_name, pad in pad_items.items():
        for connected in connectivity_data.GetConnectedItems(pad):
            by_item.setdefault(connected.m_Uuid.AsString(), set()).add(pad_name)
    for members in by_item.values():
        ordered = sorted(members)
        for other_name in ordered[1:]:
            union(ordered[0], other_name)
    clusters = {}
    for pad_name, pad in pad_items.items():
        clusters.setdefault(pad.GetNetname(), {}).setdefault(find(pad_name), []).append(pad_name)
    connectivity = {
        net: {
            "clusters": sorted(sorted(group) for group in groups.values()),
            "pad_count": sum(len(group) for group in groups.values()),
            "cluster_count": len(groups),
        }
        for net, groups in sorted(clusters.items())
    }
    return {
        "schema": "zapote.current-sense.native-extract.v1",
        "board": str(board_path),
        "board_sha256": sha256(board_path),
        "extractor_sha256": sha256(Path(__file__).resolve()),
        "kicad_version": pcbnew.GetBuildVersion(),
        "copper_layer_count": board.GetCopperLayerCount(),
        "components": sorted(components, key=lambda item: item["id"]),
        "connections": sorted(connections, key=lambda item: (item["component"], item["pad"])),
        "connectivity_clusters": connectivity,
        "traces": sorted(traces, key=lambda item: item["uuid"]),
        "vias": sorted(vias, key=lambda item: item["uuid"]),
        "zones": [
            {
                "uuid": zone.m_Uuid.AsString(),
                "net": zone.GetNetname(),
                "layer": board.GetLayerName(zone.GetLayer()),
                "filled": bool(zone.IsFilled()),
            }
            for zone in board.Zones()
            if not zone.GetIsRuleArea()
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--board", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = extract(args.board.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "native-extracted", "output": str(args.output)}))


if __name__ == "__main__":
    main()
