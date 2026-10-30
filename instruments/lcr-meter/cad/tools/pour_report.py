"""Copper balance per layer and the I2S / QSPI / USB return-path reference, for the GND pours (Rev F).

<kicad-python> cad/tools/pour_report.py [BOARD.kicad_pcb | REV: ...] [-o OUT.json]
Read-only; boards must carry their zone fill (cad/rebuild.sh saves it).  `REV:` reads the committed board at a
git revision (the committed record compares `1ab859588:` before the pours with the working board).  For each board:
  * copper area per layer: the union of pads, tracks, vias and filled zones (KiCad's own shapes);
  * for every B.Cu / In2.Cu segment of the I2S, QSPI and USB data nets, the nearest GND reference
    plane: a GND fill on the adjacent layer across the 0.21 mm prepreg (B.Cu <-> In2.Cu) when it
    covers the trace plus 0.2 mm each side, else In1.Cu (B.Cu: prepreg + In2 copper + core, 1.29 mm;
    In2: the 1.065 mm core).  Reported as length-weighted reference height and as loop area per mm
    of run (height x 1 mm): an estimate of the return loop, not a bound (stackup JLC04161H-7628).
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pcbnew as k

ROOT = Path(__file__).resolve().parents[2]
NM = 1e-6
CU = {'F.Cu': k.F_Cu, 'In1.Cu': k.In1_Cu, 'In2.Cu': k.In2_Cu, 'B.Cu': k.B_Cu}
NETS = ('I2S_BCLK', 'I2S_FSYNC', 'I2S_DIN', 'I2S_DOUT', 'QSPI0', 'QSPI1', 'QSPI2', 'QSPI3', 'QSPI_CLK',
        'QSPI_CLK_FLASH', 'QSPI_CS', 'USB_DP', 'USB_DM', 'USB_DP_MCU', 'USB_DM_MCU')
PREPREG, CORE, T_IN = 0.2104, 1.065, 0.0152
H_ADJ = PREPREG
H_IN1 = {'B.Cu': PREPREG + T_IN + CORE, 'In2.Cu': CORE}
ADJ = {'B.Cu': 'In2.Cu', 'In2.Cu': 'B.Cu'}


def report(path):
    b = k.LoadBoard(str(path))
    out = {'board': str(path), 'copper_mm2': {}, 'board_mm2': None, 'return': {}}
    e = b.GetBoardEdgesBoundingBox()
    out['board_mm2'] = round(e.GetWidth() * e.GetHeight() * NM * NM, 1)
    gnd_fill = {}
    for name, l in CU.items():
        ps = k.SHAPE_POLY_SET()
        for f in b.GetFootprints():
            for p in f.Pads():
                if p.IsOnLayer(l):
                    p.TransformShapeToPolygon(ps, l, 0, 5000, k.ERROR_INSIDE)
        for t in b.GetTracks():
            if t.IsOnLayer(l):
                t.TransformShapeToPolygon(ps, l, 0, 5000, k.ERROR_INSIDE)
        g = k.SHAPE_POLY_SET()
        for z in b.Zones():
            if not z.GetIsRuleArea() and z.IsOnLayer(l):
                fl = z.GetFilledPolysList(l)
                ps.Append(fl)
                if z.GetNetname() == 'GND':
                    g.Append(fl)
        ps.Simplify()
        g.Simplify()
        gnd_fill[name] = g
        out['copper_mm2'][name] = round(ps.Area() * NM * NM, 1)
    out['copper_fraction'] = {n: round(a / out['board_mm2'], 3) for n, a in out['copper_mm2'].items()}
    tot = {n: {'mm': 0.0, 'adj_mm': 0.0, 'h_x_mm': 0.0} for n in NETS}
    for t in b.GetTracks():
        if isinstance(t, k.PCB_VIA) or t.GetNetname() not in NETS:
            continue
        layer = b.GetLayerName(t.GetLayer())
        if layer not in ADJ:
            continue
        a, c = t.GetStart(), t.GetEnd()
        L = ((a.x - c.x) ** 2 + (a.y - c.y) ** 2) ** 0.5 * NM
        n = max(2, int(L / 0.25) + 1)
        covered = 0
        probe = k.SHAPE_POLY_SET()
        for i in range(n):
            x = a.x + (c.x - a.x) * (i + 0.5) / n
            y = a.y + (c.y - a.y) * (i + 0.5) / n
            r = int((t.GetWidth() / 2 + k.FromMM(0.2)))
            ok = all(gnd_fill[ADJ[layer]].Contains(k.VECTOR2I(int(x + dx * r), int(y + dy * r)))
                     for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)))
            covered += ok
        f = covered / n
        s = tot[t.GetNetname()]
        s['mm'] += L
        s['adj_mm'] += L * f
        s['h_x_mm'] += L * (f * H_ADJ + (1 - f) * H_IN1[layer])
    for n, s in tot.items():
        if s['mm'] > 0:
            out['return'][n] = {'buried_run_mm': round(s['mm'], 2),
                                'over_adjacent_gnd_fill_mm': round(s['adj_mm'], 2),
                                'mean_reference_height_mm': round(s['h_x_mm'] / s['mm'], 3),
                                'loop_area_mm2': round(s['h_x_mm'], 2)}
    return out


def main():
    args = [a for a in sys.argv[1:]]
    out = ROOT / 'validation' / 'pour-report-rev-f.json'
    if '-o' in args:
        i = args.index('-o')
        out = Path(args[i + 1])
        del args[i:i + 2]
    res = []
    for a in args or [str(ROOT / 'cad' / 'temper-lcr.kicad_pcb')]:
        if a.endswith(':'):
            rel = (ROOT / 'cad' / 'temper-lcr.kicad_pcb').relative_to(ROOT.parents[1])
            txt = subprocess.run(['git', 'show', f'{a}{rel}'], cwd=ROOT, capture_output=True, text=True, check=True).stdout
            with tempfile.NamedTemporaryFile('w', suffix='.kicad_pcb', delete=False) as f:
                f.write(txt)
            r = report(Path(f.name))
            Path(f.name).unlink()
            r['board'] = f'{a}{rel}'
        else:
            r = report(Path(a))
            r['board'] = str(Path(a).resolve().relative_to(ROOT.parents[1]))
        res.append(r)
    out.write_text(json.dumps(res, indent=1) + '\n')
    for r in res:
        print(r['board'])
        print('  copper mm2', r['copper_mm2'], 'fraction', r['copper_fraction'])
        for n, s in r['return'].items():
            print(f"  {n:15s} {s['buried_run_mm']:7.2f} mm, {s['over_adjacent_gnd_fill_mm']:6.2f} over adjacent GND, "
                  f"h {s['mean_reference_height_mm']:.3f} mm, loop {s['loop_area_mm2']:.1f} mm2")


if __name__ == '__main__':
    main()
