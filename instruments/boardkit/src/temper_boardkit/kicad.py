"""pcbnew helpers (KiCad's bundled Python 3.9; pcbnew is imported lazily, so this module imports anywhere).

load_board(path)                      pcbnew.LoadBoard
pad_table(board)                      {ref: {pad: net}}: the expected pad-net table for gerber.connectivity
footprint_pads(board, ref)            {pad: (x, y)} footprint-frame centres (y down), for jlc.easyeda fits
edge_clearance(path, label)           copper-to-edge per edge of a rectangular outline (filled board)
via_in_pad(board)                     vias whose drill / ring lands on an SMD pad, and untented vias
joint_counts(board, placed)           SMT / THT joints and leadless parts, for jlc.order
MODEL_SWAP, apply_model_swap(dir)     3D-model paths for KiCad 10 footprints that ship without a model
"""

from __future__ import annotations

import hashlib
from pathlib import Path

MM = 1e-6


def pcbnew():
    import pcbnew as k

    return k


def load_board(path):
    return pcbnew().LoadBoard(str(path))


def pad_table(board):
    out = {}
    for f in board.GetFootprints():
        for p in f.Pads():
            if p.GetNumber():
                out.setdefault(f.GetReference(), {})[p.GetNumber()] = p.GetNetname() or None
    return out


def footprint_pads(board, ref):
    """Numbered pad centres of one footprint in its own frame (mm, y down); first pad per number."""
    k = pcbnew()
    native = {}
    for pad in board.FindFootprintByReference(ref).Pads():
        if pad.GetNumber():
            rel = pad.GetFPRelativePosition()
            native.setdefault(pad.GetNumber(), (k.ToMM(rel.x), k.ToMM(rel.y)))
    return native


# ------------------------------------------------------------------ edge clearance
def _bbox(ps):
    pts = [
        (o.CPoint(j).x * MM, o.CPoint(j).y * MM)
        for i in range(ps.OutlineCount())
        for o in [ps.Outline(i)]
        for j in range(o.PointCount())
    ]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _shape(item, layer):
    k = pcbnew()
    ps = k.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(ps, layer, 0, 1000, k.ERROR_OUTSIDE)
    return _bbox(ps)


def edge_clearance(board_path, label=None, smt_within=2.0):
    """Copper-to-edge distances per straight edge of a rectangular outline, on a filled board.  For each edge:
    the nearest copper on any layer (pads, tracks, vias, filled zones), the nearest track or via, the nearest
    land, and every SMT land of an assembled part within smt_within mm.  Distances from the copper outline's
    bounding box, in mm.  Raises when no zone is filled (fill first)."""
    k = pcbnew()
    board_path = Path(board_path)
    board = k.LoadBoard(str(board_path))
    # outline from the Edge.Cuts centre lines (the bounding box would include half the line width)
    ends = [
        (pt.x * MM, pt.y * MM)
        for d in board.GetDrawings()
        if d.GetLayer() == k.Edge_Cuts
        for pt in (d.GetStart(), d.GetEnd())
    ]
    X0, Y0 = min(p[0] for p in ends), min(p[1] for p in ends)
    X1, Y1 = max(p[0] for p in ends), max(p[1] for p in ends)
    edges = {
        "front_y_min": lambda b: b[1] - Y0,
        "back_y_max": lambda b: Y1 - b[3],
        "left_x_min": lambda b: b[0] - X0,
        "right_x_max": lambda b: X1 - b[2],
    }
    cu = [k.F_Cu, k.In1_Cu, k.In2_Cu, k.B_Cu]
    items = []  # (kind, who, layer, bbox)
    for f in board.GetFootprints():
        assembled = (
            not (f.GetAttributes() & (k.FP_BOARD_ONLY | k.FP_EXCLUDE_FROM_POS_FILES))
            and not f.IsDNP()
        )
        for p in f.Pads():
            for layer in cu:
                if p.IsOnLayer(layer):
                    smt = assembled and p.GetAttribute() == k.PAD_ATTRIB_SMD and layer == k.F_Cu
                    items.append(
                        (
                            "smt_land" if smt else "land",
                            f"{f.GetReference()}.{p.GetNumber()}",
                            board.GetLayerName(layer),
                            _shape(p, layer),
                        )
                    )
    for t in board.GetTracks():
        for layer in cu:
            if t.IsOnLayer(layer):
                items.append(
                    (
                        "via" if isinstance(t, k.PCB_VIA) else "track",
                        t.GetNetname(),
                        board.GetLayerName(layer),
                        _shape(t, layer),
                    )
                )
    for z in board.Zones():
        if z.GetIsRuleArea():
            continue
        for layer in cu:
            if z.IsOnLayer(layer) and z.GetFilledPolysList(layer).OutlineCount():
                items.append(
                    (
                        "zone_fill",
                        z.GetNetname(),
                        board.GetLayerName(layer),
                        _bbox(z.GetFilledPolysList(layer)),
                    )
                )
    if not any(i[0] == "zone_fill" for i in items):
        raise RuntimeError("no filled zones: fill the zones first")

    def nearest(fn, kinds):
        d, kind, who, layer = min(
            (fn(b), kind, who, layer) for kind, who, layer, b in items if kind in kinds
        )
        return {"mm": round(d, 3), "item": kind, "who": who, "layer": layer}

    out = {
        "board": label or str(board_path),
        "board_sha256": hashlib.sha256(board_path.read_bytes()).hexdigest(),
        "outline_mm": [round(v, 3) for v in (X0, Y0, X1, Y1)],
        "edges": {},
    }
    for name, fn in edges.items():
        smt = {}
        for kind, who, _, b in items:
            ref = who.split(".")[0]
            if kind == "smt_land" and fn(b) <= smt_within:
                smt[ref] = min(smt.get(ref, 9.0), round(fn(b), 3))
        out["edges"][name] = {
            "nearest_copper": nearest(fn, {"smt_land", "land", "track", "via", "zone_fill"}),
            "nearest_track_or_via": nearest(fn, {"track", "via"}),
            "nearest_land": nearest(fn, {"smt_land", "land"}),
            "smt_parts_within_2mm": [
                {"ref": r, "mm": d} for r, d in sorted(smt.items(), key=lambda kv: kv[1])
            ],
        }
    return out


def edge_summary(out):
    lines = []
    for name, v in out["edges"].items():
        lines.append(
            f"{name:12s} copper {v['nearest_copper']['mm']:.3f} ({v['nearest_copper']['item']} "
            f"{v['nearest_copper']['who']}), track/via {v['nearest_track_or_via']['mm']:.3f}, land "
            f"{v['nearest_land']['mm']:.3f} ({v['nearest_land']['who']}); SMT <= 2 mm: "
            + ", ".join(f"{p['ref']} {p['mm']:.2f}" for p in v["smt_parts_within_2mm"])
        )
    return "\n".join(lines)


# ------------------------------------------------------------------ via in pad
def via_in_pad(board, process="exposed-pad thermal via, unfilled, tented on B.Mask"):
    """-> (drill_rows, ring_rows, untented).  drill_rows: vias whose drill lands on an SMD pad (sorted dicts);
    ring_rows: vias whose ring but not drill touches an SMD pad ((ref, pad, net, x, y)); untented: positions of
    vias with a B.Mask opening.  Native PAD.HitTest with the via radius / drill radius (conservative near
    rounded corners)."""
    k = pcbnew()
    rows, ring_rows = [], []
    for via in board.GetTracks():
        if not isinstance(via, k.PCB_VIA):
            continue
        for footprint in board.GetFootprints():
            for pad in footprint.Pads():
                if pad.GetAttribute() != k.PAD_ATTRIB_SMD:
                    continue
                if pad.HitTest(
                    via.GetPosition(), via.GetWidth(k.F_Cu) // 2, k.F_Cu
                ) and not pad.HitTest(via.GetPosition(), via.GetDrillValue() // 2, k.F_Cu):
                    # drill outside the land but the ring touches it: an untented ring wicks paste
                    ring_rows.append(
                        (
                            footprint.GetReference(),
                            pad.GetNumber(),
                            via.GetNetname(),
                            k.ToMM(via.GetPosition().x),
                            k.ToMM(via.GetPosition().y),
                        )
                    )
                if pad.HitTest(via.GetPosition(), via.GetDrillValue() // 2, k.F_Cu):
                    rows.append(
                        {
                            "reference": footprint.GetReference(),
                            "pad": pad.GetNumber(),
                            "net": via.GetNetname(),
                            "x_mm": k.ToMM(via.GetPosition().x),
                            "y_mm": k.ToMM(via.GetPosition().y),
                            "drill_mm": k.ToMM(via.GetDrillValue()),
                            "diameter_mm": k.ToMM(via.GetWidth(k.F_Cu)),
                            "process": process,
                        }
                    )
    rows.sort(key=lambda row: (row["reference"], row["pad"], row["x_mm"], row["y_mm"]))
    untented = [
        via.GetPosition()
        for via in board.GetTracks()
        if isinstance(via, k.PCB_VIA) and not via.IsTented(k.B_Mask)
    ]
    return rows, ring_rows, untented


def via_in_pad_audit(board, expected):
    """Assert the via-in-pad set is exactly `expected` {(ref, pad)}, no other ring touches an SMD land and every
    via is tented; -> the drill rows."""
    rows, ring_rows, untented = via_in_pad(board)
    actual = {(row["reference"], row["pad"]) for row in rows}
    assert actual == set(expected), f"Unexpected drill/SMT overlap set: {actual ^ set(expected)}"
    ring_rows = [r for r in ring_rows if (r[0], r[1]) not in expected]
    assert not ring_rows, f"Via ring overlaps an SMD land: {ring_rows}"
    assert not untented, f"via at {untented[0]} is not tented on B.Mask"
    return rows


# ------------------------------------------------------------------ joints
def joint_counts(board, placed, leadless_re=None):
    """placed: CPL designators.  -> (placements, smt_joints, leadless refs, tht_joints, tht refs) per board.
    Board-only footprints have no joints; unnumbered pads (exposed-pad paste windows) are not joints."""
    k = pcbnew()
    if leadless_re is None:
        from .jlc.order import LEADLESS as leadless_re
    smt_joints = tht_joints = 0
    leadless, tht_refs = [], []
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        if fp.GetAttributes() & k.FP_BOARD_ONLY:
            continue
        pads = [p for p in fp.Pads() if p.GetAttribute() != k.PAD_ATTRIB_NPTH and p.GetNumber()]
        if ref in placed:
            smt_joints += len(pads)
            if leadless_re.search(fp.GetFPIDAsString()):
                leadless.append(ref)
        elif pads and not fp.IsDNP():
            tht_joints += len(pads)
            tht_refs.append(ref)
    return len(placed), smt_joints, sorted(leadless), tht_joints, sorted(tht_refs)


# ------------------------------------------------------------------ 3D model swaps
# KiCad 10 ships no 3D model under these footprints' model paths: point them at a matching package model, or
# at an exact-part model written to ${KIPRJMOD}/3dmodels/ by jlc.models_3d.
KI3D = "${KICAD10_3DMODEL_DIR}/"
MODEL_SWAP = {
    "USB_C_Receptacle_HRO_TYPE-C-31-M-12": (
        "Connector_USB.3dshapes/USB_C_Receptacle_HRO_TYPE-C-31-M-12.step",
        "${KIPRJMOD}/3dmodels/USB_C_Receptacle_HRO_TYPE-C-31-M-12.step",
    ),
    "VQFN-24-1EP_4x4mm_P0.5mm_EP2.45x2.45mm": (
        "Package_DFN_QFN.3dshapes/VQFN-24-1EP_4x4mm_P0.5mm_EP2.45x2.45mm.step",
        KI3D + "Package_DFN_QFN.3dshapes/Texas_RGE0024C_VQFN-24-1EP_4x4mm_P0.5mm_EP2.1x2.1mm.step",
    ),
    "HVSSOP-8-1EP_3x3mm_P0.65mm_EP1.57x1.89mm": (
        "Package_SO.3dshapes/HVSSOP-8-1EP_3x3mm_P0.65mm_EP1.57x1.89mm.step",
        KI3D + "Package_SO.3dshapes/MSOP-8-1EP_3x3mm_P0.65mm_EP1.68x1.88mm.step",
    ),
}


def apply_model_swap(pretty_dir, swaps=None):
    """Rewrite the model path of each vendored footprint in pretty_dir that has a swap.  -> names changed."""
    done = []
    for name, (old, new) in (MODEL_SWAP if swaps is None else swaps).items():
        path = Path(pretty_dir) / (name + ".kicad_mod")
        if path.exists():
            path.write_text(path.read_text().replace(KI3D + old, new))
            done.append(name)
    return done


def clear_silk_circles(fp, gap=0.16):
    """Grow each silk circle of a footprint that rings a round pad so its inner edge stays gap mm from the pad
    copper (JLC: 0.15 mm pad to silkscreen; KiCad's TestPoint_Pad_D*mm rings sit 0.14 mm away).  Concentric
    circles only; returns [(old radius, new radius)] in mm."""
    k = pcbnew()
    changed = []
    for item in fp.GraphicalItems():
        if item.GetLayer() not in (k.F_SilkS, k.B_SilkS) or item.GetShape() != k.SHAPE_T_CIRCLE:
            continue
        c, r, w = item.GetCenter(), k.ToMM(item.GetRadius()), k.ToMM(item.GetWidth())
        rings = [
            k.ToMM(p.GetSize().x) / 2
            for p in fp.Pads()
            if p.GetShape() == k.PAD_SHAPE_CIRCLE and p.GetPosition() == c
        ]
        if not rings:
            continue
        need = max(rings) + gap + w / 2
        if r < need:
            item.SetEnd(k.VECTOR2I(c.x + k.FromMM(need), c.y))
            changed.append((round(r, 4), round(need, 4)))
    return changed
