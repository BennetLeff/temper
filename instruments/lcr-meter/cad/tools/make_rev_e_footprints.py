"""Write the two Rev E footprints that the KiCad library does not carry (run with KiCad's Python).

- TI_RGE0024R: TAC5112 VQFN-24 4 x 4 mm, 0.5 mm pitch, 2.1 mm exposed pad and four 0.25 mm
  corner ground pads A1-A4. Land pattern and stencil from TI SLASF24A, RGE0024R "Example board
  layout" / "Example stencil design" (4225246/A): 24 x (0.6 x 0.24) pads on a 3.8 mm row span,
  corner pads 0.25 square on 3.45 mm centres, EP 2.1 square with 4 x 0.94 square paste (80 %).
  The JLC/EasyEDA record for C44853692 has the same pad numbers and positions.
- Panasonic TQ2SA (SA terminal): 10 pads 1.0 x 2.94 mm, 2.54 mm pitch, rows 9.56 mm apart
  ("Recommendable mounting pad (Top view)", TQ SMD datasheet p.3). Pin 1 bottom left, 1-5 along
  the bottom row, 6-10 right to left along the top row; the same numbering and pin-1 corner as
  the JLC/EasyEDA record for C2684450. Body 14 x 9 mm.
- SAMZO BNC-KYWE-295-W4-N (LCSC C41416668): right-angle PCB BNC. Signal pin 5 at the centre,
  1.8 mm pad / 1.2 mm drill; ground legs 1-4 at (+-4, +-4) mm, 2.0 mm pad / 1.4 mm drill: the
  pad numbers, positions and holes of the JLC/EasyEDA record (sources/rev-e/BNC-KYWE-295 notes in
  docs/rev-e-plan.md).  SAMZO drawing BNCKYWE-P03900 (sources/rev-f/BNC-KYWE-295-W4-N.txt): body
  10 x 10, flange 1.1 x 13.55 with its rear face 5.0 in front of the centre pin, 29.5 overall, so
  the barrel tip is 24.5 in front of the centre; the jack faces -y and the board edge sits 6.0 mm in
  front of the centre (the flange stands 0.1 proud).  The square pad pattern does not key the jack, so the
  footprint marks the opening on silk and fab.
"""
from pathlib import Path

import pcbnew as k

LIB = Path(__file__).resolve().parents[1] / 'LCR.pretty'


def mm(v):
    return k.FromMM(v)


def vec(x, y):
    return k.VECTOR2I(mm(x), mm(y))


def pad(fp, number, x, y, w, h, layers, shape=k.PAD_SHAPE_ROUNDRECT, ratio=0.2):
    p = k.PAD(fp)
    p.SetNumber(number)
    p.SetAttribute(k.PAD_ATTRIB_SMD)
    p.SetShape(shape)
    if shape == k.PAD_SHAPE_ROUNDRECT:
        p.SetRoundRectRadiusRatio(ratio)
    p.SetSize(vec(w, h))
    p.SetPosition(vec(x, y))
    p.SetLayerSet(layers)
    fp.Add(p)
    return p


def line(fp, layer, a, b, width):
    s = k.PCB_SHAPE(fp)
    s.SetShape(k.SHAPE_T_SEGMENT)
    s.SetStart(vec(*a))
    s.SetEnd(vec(*b))
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    fp.Add(s)


def rect(fp, layer, x0, y0, x1, y1, width):
    for a, b in [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]:
        line(fp, layer, a, b, width)


def base(name, descr):
    fp = k.FOOTPRINT(None)
    fp.SetFPID(k.LIB_ID('LCR', name))
    fp.SetLibDescription(descr)
    fp.SetAttributes(k.FP_SMD)
    fp.Reference().SetText('REF**')
    fp.Value().SetText(name)
    return fp


def model(fp, path):
    """3D model, already in the footprint frame (no offset or rotation): KiCad's library, or
    cad/3dmodels/ written by cad/tools/models_3d.py from the part's LCSC record."""
    m = k.FP_3DMODEL()
    m.m_Filename = path
    fp.Add3DModel(m)


SMD = k.LSET()
for layer in (k.F_Cu, k.F_Paste, k.F_Mask):
    SMD.AddLayer(layer)
NOPASTE = k.LSET()
for layer in (k.F_Cu, k.F_Mask):
    NOPASTE.AddLayer(layer)
PASTE = k.LSET()
PASTE.AddLayer(k.F_Paste)

# TAC5112, RGE0024R
name = 'TI_RGE0024R_VQFN-24-1EP_4x4mm_P0.5mm_EP2.1mm_CornerPads'
fp = base(name, 'TI RGE0024R VQFN-24 with corner pads (TAC5112), SLASF24A 4225246/A')
for i in range(24):
    side, idx = divmod(i, 6)
    off = -1.25 + 0.5 * idx
    if side == 0:
        x, y, w, h = -1.9, off, 0.6, 0.24        # pins 1-6, left, top to bottom
    elif side == 1:
        x, y, w, h = off, 1.9, 0.24, 0.6         # pins 7-12, bottom, left to right
    elif side == 2:
        x, y, w, h = 1.9, -off, 0.6, 0.24        # pins 13-18, right, bottom to top
    else:
        x, y, w, h = -off, -1.9, 0.24, 0.6       # pins 19-24, top, right to left
    pad(fp, str(i + 1), x, y, w, h, SMD, ratio=0.25)
for number, x, y in [('A1', -1.725, -1.725), ('A2', -1.725, 1.725), ('A3', 1.725, 1.725), ('A4', 1.725, -1.725)]:
    pad(fp, number, x, y, 0.25, 0.25, SMD, shape=k.PAD_SHAPE_RECT)
pad(fp, '25', 0, 0, 2.1, 2.1, NOPASTE, shape=k.PAD_SHAPE_RECT)
for x in (-0.53, 0.53):
    for y in (-0.53, 0.53):
        pad(fp, '', x, y, 0.94, 0.94, PASTE, ratio=0.1)
rect(fp, k.F_Fab, -2, -2, 2, 2, 0.1)
line(fp, k.F_Fab, (-2, -1.4), (-1.4, -2), 0.1)
for sx in (-1, 1):
    for sy in (-1, 1):
        # corner marks end 0.17 mm from the nearest pad (JLC pad to silk >= 0.15 mm)
        line(fp, k.F_SilkS, (2.11 * sx, 2.11 * sy), (1.6 * sx, 2.11 * sy), 0.12)
        line(fp, k.F_SilkS, (2.11 * sx, 2.11 * sy), (2.11 * sx, 1.6 * sy), 0.12)
line(fp, k.F_SilkS, (-2.45, -1.25), (-2.45, -0.9), 0.15)   # pin-1 tick, clear of the pads
rect(fp, k.F_CrtYd, -2.45, -2.45, 2.45, 2.45, 0.05)
fp.Reference().SetPosition(vec(0, -3.2))
fp.Value().SetPosition(vec(0, 3.2))
fp.Value().SetLayer(k.F_Fab)
model(fp, '${KICAD10_3DMODEL_DIR}/Package_DFN_QFN.3dshapes/Texas_RGE0024C_VQFN-24-1EP_4x4mm_P0.5mm_EP2.1x2.1mm.step')
k.FootprintSave(str(LIB), fp)

# Panasonic TQ2SA, SA terminals
name = 'Relay_DPDT_Panasonic_TQ2SA_SMD'
fp = base(name, 'Panasonic TQ2SA (SA terminal) DPDT signal relay, recommended pad, datasheet p.3')
for i in range(5):
    x = -5.08 + 2.54 * i
    pad(fp, str(i + 1), x, 4.78, 1.0, 2.94, SMD, ratio=0.15)
    pad(fp, str(10 - i), x, -4.78, 1.0, 2.94, SMD, ratio=0.15)
rect(fp, k.F_Fab, -7, -4.5, 7, 4.5, 0.1)
line(fp, k.F_Fab, (-6.4, -4.5), (-6.4, 4.5), 0.1)       # orientation stripe at the 1/10 end
rect(fp, k.F_SilkS, -7.1, -3.1, 7.1, 3.1, 0.12)
line(fp, k.F_SilkS, (-6.5, -3.1), (-6.5, 3.1), 0.12)
rect(fp, k.F_CrtYd, -7.25, -6.5, 7.25, 6.5, 0.05)
fp.Reference().SetPosition(vec(0, 0))
fp.Value().SetPosition(vec(0, 1.5))
fp.Value().SetLayer(k.F_Fab)
model(fp, '${KIPRJMOD}/3dmodels/Relay_DPDT_Panasonic_TQ2SA_SMD.step')
k.FootprintSave(str(LIB), fp)


def tht(fp, number, x, y, size, drill):
    p = k.PAD(fp)
    p.SetNumber(number)
    p.SetAttribute(k.PAD_ATTRIB_PTH)
    p.SetShape(k.PAD_SHAPE_CIRCLE)
    p.SetSize(vec(size, size))
    p.SetDrillSize(vec(drill, drill))
    p.SetPosition(vec(x, y))
    p.SetLayerSet(k.PAD.PTHMask())
    fp.Add(p)


# SAMZO BNC-KYWE-295-W4-N, right angle, through hole
name = 'BNC_SAMZO_KYWE-295-W4-N_Horizontal'
fp = base(name, 'SAMZO BNC-KYWE-295-W4-N right-angle PCB BNC (LCSC C41416668); jack faces -y')
fp.SetAttributes(k.FP_THROUGH_HOLE)
tht(fp, '5', 0, 0, 1.8, 1.2)
for number, x, y in [('1', 4, -4), ('2', 4, 4), ('3', -4, 4), ('4', -4, -4)]:
    tht(fp, number, x, y, 2.0, 1.4)
rect(fp, k.F_Fab, -5, -5.0, 5, 5.0, 0.1)                # body
rect(fp, k.F_Fab, -6.775, -6.1, 6.775, -5.0, 0.1)       # flange at the board edge
rect(fp, k.F_Fab, -5.5, -24.5, 5.5, -6.1, 0.1)          # M12 thread and barrel beyond the edge
line(fp, k.F_SilkS, (-5.1, 5.6), (5.1, 5.6), 0.12)       # back of the body
line(fp, k.F_SilkS, (-5.1, 5.6), (-5.1, 5.1), 0.12)
line(fp, k.F_SilkS, (5.1, 5.6), (5.1, 5.1), 0.12)
line(fp, k.F_SilkS, (-1.0, -4.3), (0, -5.0), 0.12)       # opening mark toward the edge
line(fp, k.F_SilkS, (1.0, -4.3), (0, -5.0), 0.12)
rect(fp, k.F_CrtYd, -7.0, -6.0, 7.0, 5.75, 0.05)
fp.Reference().SetPosition(vec(0, 2.0))
fp.Value().SetPosition(vec(0, 3.5))
fp.Value().SetLayer(k.F_Fab)
model(fp, '${KIPRJMOD}/3dmodels/BNC_SAMZO_KYWE-295-W4-N_Horizontal.step')
k.FootprintSave(str(LIB), fp)
print('wrote', LIB)
