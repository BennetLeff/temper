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
        line(fp, k.F_SilkS, (2.11 * sx, 2.11 * sy), (1.55 * sx, 2.11 * sy), 0.12)
        line(fp, k.F_SilkS, (2.11 * sx, 2.11 * sy), (2.11 * sx, 1.55 * sy), 0.12)
line(fp, k.F_SilkS, (-2.45, -1.25), (-2.45, -0.9), 0.15)   # pin-1 tick, clear of the pads
rect(fp, k.F_CrtYd, -2.45, -2.45, 2.45, 2.45, 0.05)
fp.Reference().SetPosition(vec(0, -3.2))
fp.Value().SetPosition(vec(0, 3.2))
fp.Value().SetLayer(k.F_Fab)
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
k.FootprintSave(str(LIB), fp)
print('wrote', LIB)
