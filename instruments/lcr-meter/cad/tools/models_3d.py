"""3D models for the LCR footprints that have none in KiCad's library (CAD-env Python, OCP).

~/.local/share/temper/cadenv/bin/python -I cad/tools/models_3d.py [--refresh]

Exact-part models come from the EasyEDA/LCSC library of each part's LCSC code: the record already
cached in sources/placement-library/<LCSC>-product.json names the model (outline3D uuid, origin, z,
rotation). The STEP is fetched from modules.easyeda.com into build/models-3d/raw/ and is not
committed (vendor model, like the SPICE models). It is then placed in the KiCad footprint frame, so
that the footprint's model entry needs no offset or rotation, and written with its colours to
cad/3dmodels/ (gitignored; rerun this script after a fresh checkout).

Placement, in KiCad's 3D frame (x right, y up, z up from the board's top face):
1. EasyEDA's own placement: turn by c_rotation (degrees about X, Y, Z), move to c_origin (10 mil
   units, canvas y down), z = -z_param.
2. The EasyEDA footprint and ours differ by a 2D rigid motion: numbered pad centres, quarter turns,
   least RMS, as cad/tools/placement_offsets.py fits them. That motion carries the model over.
3. Corrections measured on the placed solid, because EasyEDA's z and origins are not reliable:
   - 'seat': SMD parts are lifted or lowered so their lowest point (lead feet) is on the board.
   - BNC: its four ground legs are symmetric, so the pad fit cannot say where the jack faces; the
     footprint has it facing -y canvas (+y here, the board edge). The model is turned 180 deg about
     the pad centre when its barrel points the other way, its pins (section 3 mm below the board)
     are centred on the pad pattern, and its body bottom (section at x = 2.5 mm, clear of the pins)
     is set on the board.
cad/3dmodels/models-3d.json records the source, hashes, fit and corrections per part.
"""
import hashlib
import json
import math
import re
import sys
import urllib.request
from pathlib import Path

from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.Bnd import Bnd_Box
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader, STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.gp import gp_Ax1, gp_Dir, gp_Pln, gp_Pnt, gp_Trsf, gp_Vec

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / 'sources' / 'placement-library'
PRETTY = ROOT / 'cad' / 'LCR.pretty'
RAW = ROOT / 'build' / 'models-3d' / 'raw'
OUT = ROOT / 'cad' / '3dmodels'
UNIT = 0.254
STEP_URL = 'https://modules.easyeda.com/qAxj6KHrDKw4blvCG8QJPs7Y/{uuid}'
AXES = {'x': gp_Dir(1, 0, 0), 'y': gp_Dir(0, 1, 0), 'z': gp_Dir(0, 0, 1)}

# footprint -> (LCSC code of the fitted part, correction)
PARTS = {
    'Relay_DPDT_Panasonic_TQ2SA_SMD': ('C2684450', 'seat'),
    'BNC_SAMZO_KYWE-295-W4-N_Horizontal': ('C41416668', 'bnc'),
    'USB_C_Receptacle_HRO_TYPE-C-31-M-12': ('C165948', 'seat'),
    'LED_LiteOn_LTST-S270KFKT_SideView': ('C160472', 'seat'),
}


def native_pads(name):
    text = (PRETTY / f'{name}.kicad_mod').read_text()
    pads = {}
    for num, x, y in re.findall(r'\(pad "([^"]+)" \w+\s+\w*\s*\(at ([-\d.]+) ([-\d.]+)', text):
        pads.setdefault(num, (float(x), -float(y)))       # y up
    return pads


def easyeda(lcsc):
    result = json.loads((LIB / f'{lcsc}-product.json').read_text())['result']
    pads, model = {}, None
    for item in result['packageDetail']['dataStr']['shape']:
        f = item.split('~')
        if f[0] == 'PAD' and f[8]:
            pads.setdefault(f[8], (float(f[2]) * UNIT, -float(f[3]) * UNIT))      # y up
        if f[0] == 'SVGNODE':
            attrs = json.loads(f[1])['attrs']
            if attrs.get('c_etype') == 'outline3D':
                model = attrs
    return pads, model, result['packageDetail']['title']


def fit(native, vendor):
    common = sorted(set(native) & set(vendor))
    best = []
    for turn in (0, 90, 180, 270):
        c, s = math.cos(math.radians(turn)), math.sin(math.radians(turn))
        rv = {n: (c * vendor[n][0] - s * vendor[n][1], s * vendor[n][0] + c * vendor[n][1]) for n in common}
        tx = sum(native[n][0] - rv[n][0] for n in common) / len(common)
        ty = sum(native[n][1] - rv[n][1] for n in common) / len(common)
        err = [math.hypot(rv[n][0] + tx - native[n][0], rv[n][1] + ty - native[n][1]) for n in common]
        best.append((math.sqrt(sum(e * e for e in err) / len(err)), turn, tx, ty))
    return sorted(best), common


def fetch(uuid, refresh):
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f'{uuid}.step'
    if refresh or not path.exists() or path.stat().st_size == 0:
        req = urllib.request.Request(STEP_URL.format(uuid=uuid), headers={'User-Agent': 'Mozilla/5.0'})
        data = urllib.request.urlopen(req, timeout=60).read()
        assert data.startswith(b'ISO-10303-21'), uuid
        path.write_bytes(data)
    return path


def trsf(steps):
    """Compose ('rot', axis, deg) / ('move', x, y, z) steps, applied in order."""
    total = gp_Trsf()
    for step in steps:
        t = gp_Trsf()
        if step[0] == 'rot':
            t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), AXES[step[1]]), math.radians(step[2]))
        else:
            t.SetTranslation(gp_Vec(*step[1:]))
        total.PreMultiply(t)
    return total


def bbox(shape):
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    return None if box.IsVoid() else box.Get()


def section(shape, axis, value):
    p = [0.0, 0.0, 0.0]
    p['xyz'.index(axis)] = value
    sec = BRepAlgoAPI_Section(shape, gp_Pln(gp_Pnt(*p), AXES[axis]))
    sec.Build()
    return bbox(sec.Shape())


def correction(shape, kind):
    """Extra steps measured on the placed solid (see the module docstring)."""
    x0, y0, z0, x1, y1, z1 = bbox(shape)
    if kind == 'seat':
        return [('move', 0, 0, -z0)], {'lift_mm': round(-z0, 3)}
    # BNC: barrel toward +y; pins centred on the pad pattern; body bottom on the board
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


def main():
    refresh = '--refresh' in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, (lcsc, kind) in PARTS.items():
        native = native_pads(name)
        vendor, model, title = easyeda(lcsc)
        ranked, common = fit(native, vendor)
        rms, turn, tx, ty = ranked[0]
        assert rms < 0.35 and ranked[1][0] > 2 * rms, (name, ranked)
        raw = fetch(model['uuid'], refresh)
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
        x0, y0, z0, x1, y1, z1 = write(raw, OUT / f'{name}.step', trsf(steps + extra))
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
        print(f'{name:38} {lcsc:10} fit turn {turn:3} rms {rms:.3f} (next {ranked[1][0]:.2f}) {note}  '
              f'bbox x {x0:6.2f}..{x1:6.2f} y {y0:6.2f}..{y1:6.2f} z {z0:6.2f}..{z1:6.2f}')
    (OUT / 'models-3d.json').write_text(json.dumps(manifest, indent=1) + '\n')


main()
