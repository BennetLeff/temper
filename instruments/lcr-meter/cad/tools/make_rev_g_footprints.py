"""Write the two Rev G footprints that the KiCad library does not carry as needed (run with KiCad's Python).

- Toshiba_11-4M1S: TLP172AM photoMOS, Toshiba "4-pin SO6" (package 11-4M1S, TLP172AM datasheet p.10, Rev 9.0,
  sha256 9dd4fb2a...b76e): body 3.7 x 4.55, lead span 7.0 +-0.4, 2.54 pitch, pins 1 / 3 on one side and
  4 / 6 on the other (1 anode, 3 cathode, 4 and 6 drain).  KiCad's SO-4_4.4x3.9mm_P2.54mm (its description cites
  the Toshiba TLP3123, the same 4-pin SO6 body) has the land pattern; its pads 1-4 run counter-clockwise from
  the top left, as Toshiba's 1, 3, 4, 6 do, so they are renumbered 1 -> 1, 2 -> 3, 3 -> 4, 4 -> 6.
- D_SOD-323_HJC: the HJC H4V5HD3B "Suggested Pad Layout" (datasheet p.3, Rev 2.1, sha256 de8693aa...2c14):
  pad J >= 0.80 along the part, M >= 0.80 across it, gap K <= 1.40.  Pads 0.80 x 0.80 on 2.20 centres
  (gap 1.40).  KiCad's D_SOD-323 (0.6 x 0.45) is under both minimums.  The pin-1 silk bar moves out to keep
  0.15 mm from the wider pad (JLC pad to silk); the courtyard grows to take it.
  Written by text edit of the library file (KiCad 10's Python fails to save this one).
The H3V3LD5B (SOD-523) uses KiCad's D_SOD-523 unchanged: 0.6 x 0.7 pads on 1.4 centres are HJC's X / Y / Z.
"""
import re
from pathlib import Path

import pcbnew as k

LIB = Path(__file__).resolve().parents[1] / 'LCR.pretty'
KICAD = Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')


def mm(v):
    return k.FromMM(v)


def toshiba():
    f = k.FootprintLoad(str(KICAD / 'Package_SO.pretty'), 'SO-4_4.4x3.9mm_P2.54mm')
    ren = {'1': '1', '2': '3', '3': '4', '4': '6'}
    for p in f.Pads():
        p.SetNumber(ren[p.GetNumber()])
    f.SetFPID(k.LIB_ID('LCR', 'Toshiba_11-4M1S'))
    f.SetLibDescription('Toshiba 4-pin SO6 (11-4M1S), pins 1/3/4/6; TLP172AM. Land pattern of KiCad '
                        'SO-4_4.4x3.9mm_P2.54mm, renumbered')
    f.SetKeywords('Toshiba SO6 4pin photorelay TLP172AM')
    # KiCad 10 ships no model at the SO-4 path; the exact-part model is the LCSC record's (cad/tools/models_3d.py)
    f.Models().clear()
    m = k.FP_3DMODEL()
    m.m_Filename = '${KIPRJMOD}/3dmodels/Toshiba_11-4M1S.step'
    f.Add3DModel(m)
    k.FootprintSave(str(LIB), f)


def sod323_hjc():
    """Text edit of KiCad's D_SOD-323 (pcbnew's FootprintSave fails on this one in KiCad 10's Python)."""
    t = (KICAD / 'Diode_SMD.pretty' / 'D_SOD-323.kicad_mod').read_text()
    t = t.replace('(footprint "D_SOD-323"', '(footprint "D_SOD-323_HJC"', 1)
    t = re.sub(r'\(descr "[^"]*"\)', '(descr "SOD-323, HJC suggested pad layout (0.8 x 0.8 pads, 1.4 gap); H4V5HD3B")', t, 1)
    t = t.replace('(at -1.05 0)\n\t\t(size 0.6 0.45)', '(at -1.1 0)\n\t\t(size 0.8 0.8)')
    t = t.replace('(at 1.05 0)\n\t\t(size 0.6 0.45)', '(at 1.1 0)\n\t\t(size 0.8 0.8)')
    assert t.count('(size 0.8 0.8)') == 2, 'pad text not found'
    t = t.replace('1.6 -0.95)', '1.85 -0.95)').replace('1.6 0.95)', '1.85 0.95)')   # courtyard: pads + 0.25, silk inside
    # cathode-side silk bar: 0.15 mm (JLC pad-to-silk) beyond the wider pad 1 (edge -1.5): centre -1.73, 0.12 stroke
    assert t.count('-1.61 ') == 4, 'silk text not found'
    t = t.replace('-1.61 ', '-1.73 ')
    (LIB / 'D_SOD-323_HJC.kicad_mod').write_text(t)


# One footprint per process: a second FootprintSave in the same KiCad 10 Python session fails (SWIG plugin cache).
if __name__ == '__main__':
    import subprocess
    import sys
    if len(sys.argv) > 1:
        {'toshiba': toshiba, 'sod323': sod323_hjc}[sys.argv[1]]()
    else:
        for name in ('toshiba', 'sod323'):
            subprocess.run([sys.executable, __file__, name], check=True)
        print('wrote', LIB / 'Toshiba_11-4M1S.kicad_mod', LIB / 'D_SOD-323_HJC.kicad_mod')
