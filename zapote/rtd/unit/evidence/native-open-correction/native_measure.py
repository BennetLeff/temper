"""Thin native measurement projection for Zapote's typed Rust input.

Reads actual saved footprint fields and copper. No engineering verdicts.
Reuses the existing native connectivity apparatus.
"""
import hashlib
import json
from pathlib import Path
import sys
import pcbnew

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "harness-lab"))
import assembly_geometry

board_path, output_path = map(Path, sys.argv[1:])
board = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(board_path), None)


def xy(point):
    return [pcbnew.ToMM(point.x), pcbnew.ToMM(point.y)]


def field(fp, name, default):
    try:
        return fp.GetFieldText(name) or default
    except KeyError:
        return default


ids = {fp.GetReference(): field(fp, "SourceInstance", fp.GetReference()) for fp in board.GetFootprints()}
components = []
connections = []
for fp in board.GetFootprints():
    ident = ids[fp.GetReference()]
    pads = []
    for pad in fp.Pads():
        pads.append({"pad": pad.GetNumber(), "uuid": pad.m_Uuid.AsString(),
            "net": pad.GetNetname(), "position_mm": xy(pad.GetPosition()),
            "size_mm": xy(pad.GetSize()), "drill_mm": xy(pad.GetDrillSize()),
            "orientation_deg": pad.GetOrientationDegrees(), "shape": int(pad.GetShape()),
            "layers": [board.GetLayerName(layer) for layer in pad.GetLayerSet().Seq()]})
        if pad.GetNetname():
            connections.append({"component": ident, "pin": pad.GetNumber(), "net": pad.GetNetname()})
    components.append({"id": ident, "uuid": fp.m_Uuid.AsString(),
        "mpn": field(fp, "MPN", fp.GetValue() or "UNVERIFIED"),
        "kind": str(fp.GetFPID().GetLibItemName()), "position_mm": xy(fp.GetPosition()), "footprint_pads": pads})
traces, vias = [], []
for item in board.GetTracks():
    if item.Type() == pcbnew.PCB_VIA_T:
        vias.append({"uuid": item.m_Uuid.AsString(), "net": item.GetNetname(), "position_mm": xy(item.GetPosition()),
            "from_layer": board.GetLayerName(item.TopLayer()), "to_layer": board.GetLayerName(item.BottomLayer()),
            "drill_mm": pcbnew.ToMM(item.GetDrillValue()), "diameter_mm": pcbnew.ToMM(item.GetWidth(pcbnew.F_Cu))})
    elif item.Type() == pcbnew.PCB_TRACE_T:
        traces.append({"uuid": item.m_Uuid.AsString(), "net": item.GetNetname(), "points_mm": [xy(item.GetStart()), xy(item.GetEnd())],
            "layer": board.GetLayerName(item.GetLayer()), "width_mm": pcbnew.ToMM(item.GetWidth())})
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

def ring(chain):
    if chain.ArcCount():
        raise ValueError('unsupported curved native zone contour')
    return [xy(chain.CPoint(i)) for i in range(chain.PointCount())]


zones = []
for zone in board.Zones():
    if zone.GetIsRuleArea():
        continue
    layer = zone.GetLayer()
    filled = pcbnew.Cast_to_SHAPE_POLY_SET(zone.GetFilledPolysList(layer))
    polygons = [{'outer_mm': ring(filled.COutline(i)),
        'holes_mm': [ring(filled.CHole(i, h)) for h in range(filled.HoleCount(i))]}
        for i in range(filled.OutlineCount())]
    zones.append({'uuid': zone.m_Uuid.AsString(), 'net': zone.GetNetname(),
        'layer': board.GetLayerName(layer), 'filled_polygons': polygons})
output = {"components": components, "connections": connections, "traces": traces,
    "net_names": sorted(str(name) for name in board.GetNetsByName().keys() if str(name)),
    "copper_layer_count": board.GetCopperLayerCount(),
    "copper_layers": [board.GetLayerName(layer) for layer in board.GetEnabledLayers().Seq() if pcbnew.IsCopperLayer(layer)],
    "vias": vias, "zones": zones, "connectivity_clusters": clusters, "kicad_version": pcbnew.Version(),
    "reference_to_instance": ids, "board_sha256": hashlib.sha256(board_path.read_bytes()).hexdigest(),
    "extractor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
output_path.write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
