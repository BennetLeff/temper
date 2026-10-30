"""Exact-part 3D models from the EasyEDA/LCSC library, placed in the KiCad footprint frame (OCP).

Run under a Python with OCP (the CAD env: ~/.local/share/temper/cadenv/bin/python -I).  For each footprint:
the cached EasyEDA record of its LCSC part names the model (outline3D uuid, origin, z, rotation); the STEP is
fetched from modules.easyeda.com into raw_dir (vendor model, not committed); it is placed in the footprint
frame so the footprint's model entry needs no offset or rotation, and written with its colours to out_dir.

Placement, in KiCad's 3D frame (x right, y up, z up from the board's top face):
1. EasyEDA's own placement: turn by c_rotation (degrees about X, Y, Z), move to c_origin (10 mil units,
   canvas y down), z = -z_param.
2. The EasyEDA footprint and ours differ by a 2D rigid motion: numbered pad centres, quarter turns, least
   RMS (easyeda.fit_rigid).  That motion carries the model over.
3. Corrections measured on the placed solid, because EasyEDA's z and origins are not reliable:
   - 'seat': SMD parts are lifted or lowered so their lowest point (lead feet) is on the board.
   - 'bnc': a jack whose four symmetric ground legs leave the pad fit blind to where it faces: turned 180
     degrees when its barrel points at -y, pins (section 3 mm below the board) centred on the pad pattern,
     body bottom (section at x = 2.5 mm, clear of the pins) set on the board.
build() returns the manifest (source, hashes, fit and corrections per footprint).
"""
from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path

from . import easyeda

UNIT = easyeda.UNIT
STEP_URL = 'https://modules.easyeda.com/qAxj6KHrDKw4blvCG8QJPs7Y/{uuid}'


def native_pads(kicad_mod_text):
    """Pad centres of a .kicad_mod, y up (first record per number)."""
    pads = {}
    for num, x, y in re.findall(r'\(pad "([^"]+)" \w+\s+\w*\s*\(at ([-\d.]+) ([-\d.]+)', kicad_mod_text):
        pads.setdefault(num, (float(x), -float(y)))
    return pads


def fetch(uuid, raw_dir, refresh=False):
    raw_dir = Path(raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f'{uuid}.step'
    if refresh or not path.exists() or path.stat().st_size == 0:
        req = urllib.request.Request(STEP_URL.format(uuid=uuid), headers={'User-Agent': 'Mozilla/5.0'})
        data = urllib.request.urlopen(req, timeout=60).read()
        assert data.startswith(b'ISO-10303-21'), uuid
        path.write_bytes(data)
    return path


def _ocp():
    from OCP.gp import gp_Dir
    return {'x': gp_Dir(1, 0, 0), 'y': gp_Dir(0, 1, 0), 'z': gp_Dir(0, 0, 1)}


def trsf(steps):
    """Compose ('rot', axis, deg) / ('move', x, y, z) steps, applied in order."""
    import math
    from OCP.gp import gp_Ax1, gp_Pnt, gp_Trsf, gp_Vec
    axes = _ocp()
    total = gp_Trsf()
    for step in steps:
        t = gp_Trsf()
        if step[0] == 'rot':
            t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), axes[step[1]]), math.radians(step[2]))
        else:
            t.SetTranslation(gp_Vec(*step[1:]))
        total.PreMultiply(t)
    return total


def bbox(shape):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    return None if box.IsVoid() else box.Get()


def section(shape, axis, value):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.gp import gp_Pln, gp_Pnt
    p = [0.0, 0.0, 0.0]
    p['xyz'.index(axis)] = value
    sec = BRepAlgoAPI_Section(shape, gp_Pln(gp_Pnt(*p), _ocp()[axis]))
    sec.Build()
    return bbox(sec.Shape())


def correction(shape, kind):
    """Extra steps measured on the placed solid (see the module docstring)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    x0, y0, z0, x1, y1, z1 = bbox(shape)
    if kind == 'seat':
        return [('move', 0, 0, -z0)], {'lift_mm': round(-z0, 3)}
    if kind != 'bnc':
        raise ValueError(kind)
    steps, note = [], {}
    if -y0 > y1:                                   # longer extent on -y: barrel faces the board
        steps.append(('rot', 'z', 180))
        note['turned_deg'] = 180
    turned = BRepBuilderAPI_Transform(shape, trsf(steps), True).Shape() if steps else shape
    px0, py0, _, px1, py1, _ = section(turned, 'z', -3.0)
    dx, dy = -(px0 + px1) / 2, -(py0 + py1) / 2
    body_z0 = section(turned, 'x', 2.5)[2]
    steps.append(('move', dx, dy, -body_z0))
    note.update({'pin_centre_shift_mm': [round(dx, 3), round(dy, 3)], 'body_lift_mm': round(-body_z0, 3)})
    return steps, note


def write(raw, out, total):
    """Read raw with colours, put its free shapes under one assembly at `total`, write out."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Reader, STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDF import TDF_LabelSequence
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    doc = TDocStd_Document(TCollection_ExtendedString('XmlOcaf'))
    reader = STEPCAFControl_Reader()
    reader.SetColorMode(True)
    reader.SetNameMode(True)
    assert reader.ReadFile(str(raw)) == IFSelect_RetDone, raw
    reader.Transfer(doc)
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    free = TDF_LabelSequence()
    tool.GetFreeShapes(free)
    top = tool.NewShape()
    for i in range(1, free.Length() + 1):
        tool.AddComponent(top, free.Value(i), TopLoc_Location(total))
    tool.UpdateAssemblies()
    writer = STEPCAFControl_Writer()
    writer.SetColorMode(True)
    writer.SetNameMode(True)
    writer.Transfer(doc, STEPControl_AsIs)
    assert writer.Write(str(out)) == IFSelect_RetDone, out
    return bbox(tool.GetShape_s(top))


def build(parts, pretty_dir, record_dir, raw_dir, out_dir, refresh=False, log=print):
    """parts {footprint name: (LCSC code, correction kind)}.  Writes out_dir/<footprint>.step; returns the
    manifest dict (the caller writes it)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.STEPControl import STEPControl_Reader
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, (lcsc, kind) in parts.items():
        native = native_pads((Path(pretty_dir) / f'{name}.kicad_mod').read_text())
        result = json.loads((Path(record_dir) / f'{lcsc}-product.json').read_text())['result']
        vendor = easyeda.easyeda_pads(result, y_up=True)
        model, title = easyeda.model_3d(result), result['packageDetail']['title']
        ranked, common = easyeda.fit_rigid(native, vendor)
        rms, turn, tx, ty = ranked[0]
        assert rms < 0.35 and ranked[1][0] > 2 * rms, (name, ranked)
        raw = fetch(model['uuid'], raw_dir, refresh)
        rx, ry, rz = (float(v) for v in model['c_rotation'].split(','))
        ox, oy = (float(v) for v in model['c_origin'].split(','))
        steps = [('rot', 'x', rx), ('rot', 'y', ry), ('rot', 'z', rz),
                 ('move', ox * UNIT, -oy * UNIT, -float(model['z']) * UNIT),
                 ('rot', 'z', turn), ('move', tx, ty, 0)]
        reader = STEPControl_Reader()
        reader.ReadFile(str(raw))
        reader.TransferRoots()
        placed = BRepBuilderAPI_Transform(reader.OneShape(), trsf(steps), True).Shape()
        extra, note = correction(placed, kind)
        x0, y0, z0, x1, y1, z1 = write(raw, out_dir / f'{name}.step', trsf(steps + extra))
        manifest[name] = {
            'lcsc': lcsc, 'easyeda_title': title, 'model_title': model.get('title'), 'uuid': model['uuid'],
            'source_url': STEP_URL.format(uuid=model['uuid']),
            'raw_sha256': hashlib.sha256(raw.read_bytes()).hexdigest(),
            'pad_fit': {'turn_deg': turn, 'rms_mm': round(rms, 4), 'matched_pads': len(common),
                        'next_rms_mm': round(ranked[1][0], 3)},
            'correction': {'kind': kind, **note},
            'bbox_mm': {'min': [round(x0, 3), round(y0, 3), round(z0, 3)],
                        'max': [round(x1, 3), round(y1, 3), round(z1, 3)]},
        }
        log(f'{name:38} {lcsc:10} fit turn {turn:3} rms {rms:.3f} (next {ranked[1][0]:.2f}) {note}  '
            f'bbox x {x0:6.2f}..{x1:6.2f} y {y0:6.2f}..{y1:6.2f} z {z0:6.2f}..{z1:6.2f}')
    return manifest
