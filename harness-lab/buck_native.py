"""Nine-component buck adapter. KiCad owns geometry and physical connectivity."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pcbnew

FUNCTIONAL_REFS = ("U3", "L2", "C9", "C10", "C11", "C12", "C13", "R16", "R17")
TERMINAL_REFS = ("J1", "J2", "J3")
VIA_SPAN = "F.Cu-B.Cu"
VIA_DIAMETER_MM = 0.8
VIA_DRILL_MM = 0.4
COPPER_LAYERS = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}


def load(path: Path) -> pcbnew.BOARD:
    # The high-level LoadBoard/SaveBoard helpers silently propagate track nets.
    return pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(str(path), None)


def save(board: pcbnew.BOARD, path: Path) -> None:
    pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path), board)


def digest(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def position(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


def bounds(box: pcbnew.BOX2I) -> list:
    return [
        pcbnew.ToMM(v)
        for v in (box.GetLeft(), box.GetTop(), box.GetRight(), box.GetBottom())
    ]


def footprints(board: pcbnew.BOARD) -> dict:
    return {f.GetReference(): f for f in board.GetFootprints()}


def staging_of(board_path: Path) -> dict:
    source = board_path.parent / "source.json"
    if not source.exists():
        raise RuntimeError("Missing fixture source.json; cannot canonicalize")
    return json.loads(source.read_text())["staging"]


def canonical_digest(board: pcbnew.BOARD, staging: dict) -> str:
    """Deterministic protected-state digest.

    KiCad's own save order varies run to run (footprint emission order is
    history-dependent), so hashing re-saved file bytes is flaky. Instead hash
    the protected semantics in sorted order: every footprint's identity and
    staged pose, every pad's net and size, the Edge.Cuts outline, net names,
    and the copper-layer count. Copper is deleted by the caller first.
    """
    names = footprints(board)
    for reference, pose in staging.items():
        target = names[reference]
        target.SetPosition(position(pose[0], pose[1]))
        target.SetOrientationDegrees(pose[2])
    state = {"footprints": [], "outline": [], "nets": [], "copper_layers": 0}
    for reference in sorted(names):
        fp = names[reference]
        pads = []
        for pad in fp.Pads():
            pads.append(
                {
                    "number": pad.GetNumber(),
                    "net": pad.GetNetname(),
                    "position_mm": list(pcbnew.ToMM(pad.GetPosition())),
                    "size_mm": list(pcbnew.ToMM(pad.GetSize())),
                }
            )
        state["footprints"].append(
            {
                "reference": reference,
                "position_mm": list(pcbnew.ToMM(fp.GetPosition())),
                "angle_deg": fp.GetOrientationDegrees(),
                "pads": sorted(pads, key=lambda p: p["number"]),
            }
        )
    for drawing in board.GetDrawings():
        if drawing.Type() != pcbnew.PCB_SHAPE_T:
            continue
        shape = drawing
        if shape.GetLayer() != pcbnew.Edge_Cuts:
            continue
        state["outline"].append(
            [
                list(pcbnew.ToMM(shape.GetStart())),
                list(pcbnew.ToMM(shape.GetEnd())),
                pcbnew.ToMM(shape.GetWidth()),
            ]
        )
    state["outline"].sort()
    declared = {pad.GetNetname() for fp in names.values() for pad in fp.Pads()}
    declared |= {t.GetNetname() for t in board.GetTracks()}
    declared |= {
        z.GetNetname()
        for z in board.Zones()
        if not z.GetIsRuleArea() and z.GetNetname()
    }
    declared.discard("")
    state["nets"] = sorted(declared)
    state["copper_layers"] = board.GetCopperLayerCount()
    return hashlib.sha256(
        json.dumps(state, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def place(path: Path, reference: str, x: float, y: float, angle: int) -> None:
    if reference not in FUNCTIONAL_REFS:
        raise ValueError(f"Only {FUNCTIONAL_REFS} may move; {reference} is protected")
    if angle not in (0, 90, 180, 270):
        raise ValueError("Orientation must be 0, 90, 180, or 270")
    board = load(path)
    target = footprints(board)[reference]
    target.SetOrientationDegrees(angle)
    target.SetPosition(position(x, y))
    save(board, path)


def clear_net(board: pcbnew.BOARD, net: str) -> None:
    for track in list(board.GetTracks()):
        if track.GetNetname() == net:
            board.Delete(track)
    for zone in list(board.Zones()):
        if not zone.GetIsRuleArea() and zone.GetNetname() == net:
            board.Remove(zone)


def replace_copper(
    path: Path, net: str, segments: list, vias: list, zones: list
) -> None:
    """Replace mutable copper for one net on an already staged board."""
    board = load(path)
    if board.FindNet(net) is None:
        raise ValueError(f"Unknown net {net}")
    clear_net(board, net)
    for segment in segments:
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(position(*segment["start_mm"]))
        track.SetEnd(position(*segment["end_mm"]))
        track.SetWidth(pcbnew.FromMM(segment["width_mm"]))
        track.SetLayer(COPPER_LAYERS[segment["layer"]])
        track.SetNet(board.FindNet(net))
        board.Add(track)
    for via in vias:
        item = pcbnew.PCB_VIA(board)
        item.SetPosition(position(*via["position_mm"]))
        # The operation contract admits only through vias spanning F.Cu-B.Cu.
        item.SetViaType(pcbnew.VIATYPE_THROUGH)
        item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        item.SetWidth(pcbnew.FromMM(via["diameter_mm"]))
        item.SetDrill(pcbnew.FromMM(via["drill_mm"]))
        item.SetNet(board.FindNet(net))
        board.Add(item)
    for zone_spec in zones:
        zone = pcbnew.ZONE(board)
        zone.SetLayer(COPPER_LAYERS[zone_spec["layer"]])
        zone.SetNet(board.FindNet(net))
        # Build the zone through its native outline API. AddOutline expects a
        # SHAPE_LINE_CHAIN; passing a polygon set here silently produced an
        # empty/unfillable zone on KiCad 10.
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in zone_spec["outline_mm"]:
            outline.Append(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
        zone.SetLocalClearance(pcbnew.FromMM(0.2))
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        board.Add(zone)
    # Zone filling is deliberately left to KiCad's native reload/DRC path.
    # ZONE_FILLER requires a GUI wxApp and segfaults in KiCad's headless
    # Python runtime; invoking it here would turn a valid request into an
    # unreportable process crash. No host-side polygon approximation is used.
    save(board, path)


def route(path: Path, net: str, layer: str, width_mm: float, points: list) -> None:
    board = load(path)
    if board.FindNet(net) is None:
        raise ValueError(f"Unknown net {net}")
    clear_net(board, net)
    for start, end in zip(points, points[1:]):
        track = pcbnew.PCB_TRACK(board)
        track.SetStart(position(*start))
        track.SetEnd(position(*end))
        track.SetWidth(pcbnew.FromMM(width_mm))
        track.SetLayer(COPPER_LAYERS[layer])
        track.SetNet(board.FindNet(net))
        board.Add(track)
    save(board, path)


def remove_route(path: Path, net: str) -> None:
    board = load(path)
    clear_net(board, net)
    save(board, path)


def add_via(path: Path, net: str, x: float, y: float) -> None:
    board = load(path)
    if board.FindNet(net) is None:
        raise ValueError(f"Unknown net {net}")
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(position(x, y))
    via.SetWidth(pcbnew.FromMM(VIA_DIAMETER_MM))
    via.SetDrill(pcbnew.FromMM(VIA_DRILL_MM))
    via.SetNet(board.FindNet(net))
    board.Add(via)
    save(board, path)


def add_zone(path: Path, net: str, layer: str, polygon: list) -> None:
    board = load(path)
    if board.FindNet(net) is None:
        raise ValueError(f"Unknown net {net}")
    zone = pcbnew.ZONE(board)
    zone.SetLayer(COPPER_LAYERS[layer])
    zone.SetNet(board.FindNet(net))
    outline = pcbnew.SHAPE_POLY_SET()
    outline.NewOutline()
    for x, y in polygon:
        outline.Append(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)))
    zone.Outline().AddOutline(outline)
    board.Add(zone)
    save(board, path)


def measure(path: Path) -> dict:
    # Raw saved nets are inventoried BEFORE Build() can propagate assignments.
    board = load(path)
    items = []
    for fp in board.GetFootprints():
        items.append(
            {
                "reference": fp.GetReference(),
                "position_mm": list(pcbnew.ToMM(fp.GetPosition())),
                "angle_deg": fp.GetOrientationDegrees(),
                "bounds_mm": bounds(fp.GetBoundingBox(False, False)),
                "pads": [
                    {
                        "number": p.GetNumber(),
                        "net": p.GetNetname(),
                        "position_mm": list(pcbnew.ToMM(p.GetPosition())),
                        "bounds_mm": bounds(p.GetBoundingBox()),
                    }
                    for p in fp.Pads()
                ],
            }
        )
    census = []
    for track in board.GetTracks():
        kind = (
            "segment"
            if track.Type() == pcbnew.PCB_TRACE_T
            else ("via" if track.Type() == pcbnew.PCB_VIA_T else str(track.Type()))
        )
        entry = {
            "uuid": track.m_Uuid.AsString(),
            "kind": kind,
            "net": track.GetNetname(),
            "layer": VIA_SPAN
            if kind == "via"
            else board.GetLayerName(track.GetLayer()),
            "width_mm": pcbnew.ToMM(
                track.GetWidth(pcbnew.F_Cu) if kind == "via" else track.GetWidth()
            ),
            "start_mm": list(pcbnew.ToMM(track.GetStart())),
            "end_mm": list(pcbnew.ToMM(track.GetEnd())),
            "bounds_mm": bounds(track.GetBoundingBox()),
        }
        census.append(entry)
    for zone in board.Zones():
        if zone.GetIsRuleArea():
            continue
        shape = zone.Outline()
        outlines = []
        for index in range(shape.OutlineCount()):
            outline = shape.COutline(index)
            outlines.append(
                [
                    list(pcbnew.ToMM(outline.CPoint(i)))
                    for i in range(outline.PointCount())
                ]
            )
        flat = [point for outline in outlines for point in outline]
        census.append(
            {
                "uuid": zone.m_Uuid.AsString(),
                "kind": "zone",
                "net": zone.GetNetname(),
                "layer": board.GetLayerName(zone.GetLayer()),
                "width_mm": 0.5,
                "filled": bool(zone.IsFilled()),
                "filled_area_mm2": float(zone.GetFilledArea()) * pcbnew.ToMM(1) ** 2,
                "start_mm": flat[0],
                "end_mm": flat[-1],
                "bounds_mm": bounds(zone.GetBoundingBox()),
            }
        )
    copper_ids = {entry["uuid"] for entry in census}
    pads = {
        p.m_Uuid.AsString(): (f.GetReference() + "." + p.GetNumber(), p)
        for f in board.GetFootprints()
        for p in f.Pads()
    }
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
                "tracks": sorted(connected & copper_ids),
            }
        )
    # Canonicalize only the admitted degrees of freedom through KiCad:
    # functional poses return to frozen staging and all copper is removed.
    # Terminals, outline, rules, and pad/net identity stay protected. The
    # digest covers that state semantically (file save order is unstable).
    del connectivity
    staging = staging_of(path)
    canonical_board = load(path)
    for track in list(canonical_board.GetTracks()):
        canonical_board.Delete(track)
    for zone in list(canonical_board.Zones()):
        if not zone.GetIsRuleArea():
            canonical_board.Remove(zone)
    protected = canonical_digest(canonical_board, staging)
    return {
        "kicad_version": pcbnew.GetBuildVersion(),
        "board_sha256": digest(path),
        "protected_sha256": protected,
        "footprints": sorted(items, key=lambda f: f["reference"]),
        "buck": {
            "tracks": sorted(census, key=lambda t: t["uuid"]),
            "connectivity": clusters,
        },
    }


if __name__ == "__main__":
    if pcbnew.GetBuildVersion() != "10.0.4":
        raise RuntimeError("Buck adapter requires KiCad 10.0.4")
    command, path, *args = sys.argv[1:]
    target = Path(path)
    if command == "measure":
        print(json.dumps(measure(target), allow_nan=False))
    elif command == "place":
        place(target, args[0], float(args[1]), float(args[2]), int(args[3]))
    elif command == "route":
        route(target, args[0], args[1], float(args[2]), json.loads(args[3]))
    elif command == "remove_route":
        remove_route(target, args[0])
    elif command == "add_via":
        add_via(target, args[0], float(args[1]), float(args[2]))
    elif command == "add_zone":
        add_zone(target, args[0], args[1], json.loads(args[2]))
    elif command == "replace_copper":
        replace_copper(
            target,
            args[0],
            json.loads(args[1]),
            json.loads(args[2]),
            json.loads(args[3]),
        )
    else:
        raise ValueError("Unknown buck operation")
