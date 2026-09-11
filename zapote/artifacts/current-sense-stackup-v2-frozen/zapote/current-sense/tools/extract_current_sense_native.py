#!/usr/bin/env python3
"""Extract native KiCad geometry using the proven Zapote RTD schema.

Run with the KiCad bundled Python. This is a transport projection for manual
route authoring; it contains no placement, routing or engineering verdict
logic. Connectivity is delegated to the existing ``assembly_geometry``
instrument rather than reimplemented here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def extract(repo: Path, board_path: Path) -> dict:
    global pcbnew
    import pcbnew  # type: ignore[import-not-found]

    sys.path.insert(0, str(repo / "harness-lab"))
    import assembly_geometry  # type: ignore[import-not-found]

    board = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(board_path), None)

    def xy(point) -> list[float]:
        return [pcbnew.ToMM(point.x), pcbnew.ToMM(point.y)]

    def field(footprint, name: str, default: str) -> str:
        try:
            return footprint.GetFieldText(name) or default
        except KeyError:
            return default

    ids = {}
    seen_source_instances = set()
    for fp in board.GetFootprints():
        source_instance = field(fp, "SourceInstance", "").strip()
        if not source_instance or source_instance.upper() == "UNVERIFIED":
            raise ValueError(
                f"footprint {fp.GetReference()} has missing/invalid SourceInstance"
            )
        if source_instance in seen_source_instances:
            raise ValueError(f"duplicate SourceInstance {source_instance}")
        seen_source_instances.add(source_instance)
        ids[fp.GetReference()] = source_instance
    components = []
    connections = []
    for fp in board.GetFootprints():
        ident = ids[fp.GetReference()]
        mpn = field(fp, "MPN", "").strip()
        if not mpn or mpn.upper() == "UNVERIFIED":
            raise ValueError(f"footprint {fp.GetReference()} has missing/invalid MPN")
        pads = []
        for pad in fp.Pads():
            # KiCad stores the roundrect radius as a ratio of the pad's
            # smaller dimension.  Preserve the native value for the Rust
            # shape-aware clearance donor; old KiCad builds may not expose
            # the accessor, in which case the field is explicitly null.
            try:
                roundrect_ratio = float(pad.GetRoundRectRadiusRatio())
            except (AttributeError, TypeError, ValueError):
                roundrect_ratio = None
            pads.append(
                {
                    "pad": pad.GetNumber(),
                    "uuid": pad.m_Uuid.AsString(),
                    "net": pad.GetNetname(),
                    "position_mm": xy(pad.GetPosition()),
                    "size_mm": xy(pad.GetSize()),
                    "drill_mm": xy(pad.GetDrillSize()),
                    "orientation_deg": pad.GetOrientationDegrees(),
                    "shape": int(pad.GetShape()),
                    "roundrect_ratio": roundrect_ratio,
                    "layers": [
                        board.GetLayerName(layer)
                        for layer in pad.GetLayerSet().Seq()
                    ],
                }
            )
            if pad.GetNetname():
                connections.append(
                    {
                        "component": ident,
                        "pin": pad.GetNumber(),
                        "net": pad.GetNetname(),
                    }
                )
        components.append(
            {
                "id": ident,
                "uuid": fp.m_Uuid.AsString(),
                "mpn": mpn,
                "kind": str(fp.GetFPID().GetLibItemName()),
                "position_mm": xy(fp.GetPosition()),
                "footprint_pads": pads,
            }
        )

    traces, vias = [], []
    for item in board.GetTracks():
        if item.Type() == pcbnew.PCB_VIA_T:
            vias.append(
                {
                    "uuid": item.m_Uuid.AsString(),
                    "net": item.GetNetname(),
                    "position_mm": xy(item.GetPosition()),
                    "from_layer": board.GetLayerName(item.TopLayer()),
                    "to_layer": board.GetLayerName(item.BottomLayer()),
                    "drill_mm": pcbnew.ToMM(item.GetDrillValue()),
                    "diameter_mm": pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu)),
                }
            )
        elif item.Type() == pcbnew.PCB_TRACE_T:
            traces.append(
                {
                    "uuid": item.m_Uuid.AsString(),
                    "net": item.GetNetname(),
                    "points_mm": [xy(item.GetStart()), xy(item.GetEnd())],
                    "layer": board.GetLayerName(item.GetLayer()),
                    "width_mm": pcbnew.ToMM(item.GetWidth()),
                }
            )
        else:
            raise ValueError("unsupported copper geometry: " + str(item.Type()))

    clusters = []
    for net, data in assembly_geometry.connectivity(board_path)["nets"].items():
        if not net:
            continue
        for group in data["clusters"]:
            nodes = []
            for node in group:
                ref, pad = node.rsplit(".", 1)
                nodes.append(ids[ref] + "." + pad)
            clusters.append({"net": net, "nodes": nodes, "source": "native"})

    def ring(chain) -> list[list[float]]:
        if chain.ArcCount():
            raise ValueError("unsupported curved native zone contour")
        return [xy(chain.CPoint(i)) for i in range(chain.PointCount())]

    zones = []
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        layer = zone.GetLayer()
        filled = pcbnew.Cast_to_SHAPE_POLY_SET(zone.GetFilledPolysList(layer))
        polygons = [
            {
                "outer_mm": ring(filled.COutline(i)),
                "holes_mm": [
                    ring(filled.CHole(i, h))
                    for h in range(filled.HoleCount(i))
                ],
            }
            for i in range(filled.OutlineCount())
        ]
        zones.append(
            {
                "uuid": zone.m_Uuid.AsString(),
                "net": zone.GetNetname(),
                "layer": board.GetLayerName(layer),
                "filled_polygons": polygons,
            }
        )

    return {
        "board_file_utf8": board_path.read_text(encoding="utf-8"),
        "components": components,
        "connections": connections,
        "traces": traces,
        "net_names": sorted(
            str(name) for name in board.GetNetsByName().keys() if str(name)
        ),
        "copper_layer_count": board.GetCopperLayerCount(),
        "polygon_max_error_mm": pcbnew.ToMM(board.GetDesignSettings().m_MaxError),
        "copper_layers": [
            board.GetLayerName(layer)
            for layer in board.GetEnabledLayers().Seq()
            if pcbnew.IsCopperLayer(layer)
        ],
        "vias": vias,
        "zones": zones,
        "connectivity_clusters": clusters,
        "kicad_version": pcbnew.Version(),
        "reference_to_instance": ids,
        "board_sha256": hashlib.sha256(board_path.read_bytes()).hexdigest(),
        "extractor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--board", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = extract(args.repo.resolve(), args.board.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "native-extracted", "output": str(args.output)}))


if __name__ == "__main__":
    main()
