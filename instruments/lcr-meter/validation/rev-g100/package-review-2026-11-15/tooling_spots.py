"""Is there room for JLC's Economic-PCBA tooling holes (1.152 mm NPTH, 2-3 in opposite corners)?
Grid-search each 22 x 22 mm corner for points whose 1.152 mm hole + 0.35 mm margin touches no pad, no track/via and no
non-GND zone fill on any copper layer, no footprint courtyard, and stays >= 1.0 mm from the outline.  Reports, per corner,
how many 0.5 mm grid points qualify (a) with no copper at all on any layer, (b) with only GND fill.  Run with KiCad python."""
import pcbnew, math
b = pcbnew.LoadBoard('cad/temper-lcr.kicad_pcb')
mm = pcbnew.FromMM
RAD = mm(1.152 / 2 + 0.35)
layers = [pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
tracks = list(b.GetTracks()); pads = [p for f in b.GetFootprints() for p in f.Pads()]
zones = [z for z in b.Zones() if not z.GetIsRuleArea()]
court = []
for f in b.GetFootprints():
    for side in (pcbnew.F_CrtYd,):
        c = f.GetCourtyard(side)
        if c.OutlineCount(): court.append(c)
keep = [z for z in b.Zones() if z.GetIsRuleArea()]
def classify(x, y):
    p = pcbnew.VECTOR2I(mm(x), mm(y))
    for c in court:
        if c.Collide(p, RAD): return 'part'
    for pd in pads:
        if (pd.GetPosition() - p).EuclideanNorm() < RAD + max(pd.GetSizeX(), pd.GetSizeY()) // 2 + mm(0.1):
            if pd.GetEffectivePolygon(pcbnew.F_Cu if pd.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu, pcbnew.ERROR_INSIDE).Collide(p, RAD): return 'pad'
    for t in tracks:
        if t.GetNetname() == 'GND' and t.Type() != pcbnew.PCB_VIA_T: 
            if t.HitTest(p, RAD + 0): return 'gndtrack'
            continue
        if t.HitTest(p, RAD): return 'track'
    kind = 'bare'
    for z in zones:
        for l in layers:
            if z.IsOnLayer(l) and z.HasFilledPolysForLayer(l) and z.GetFilledPolysList(l).Collide(p, RAD):
                if z.GetNetname() != 'GND': return 'nonGNDfill'
                kind = 'gndfill'
    return kind
corners = {'front-left (50,45)': (50, 45, 1, 1), 'front-right (150,45)': (150, 45, -1, 1), 'back-left (50,145)': (50, 145, 1, -1), 'back-right (150,145)': (150, 145, -1, -1)}
for name, (cx, cy, sx, sy) in corners.items():
    res = {}
    best = None
    for i in range(3, 45):
        for j in range(3, 45):
            x, y = cx + sx * i * 0.5, cy + sy * j * 0.5
            k = classify(x, y)
            res[k] = res.get(k, 0) + 1
            if k in ('bare', 'gndfill'):
                d = math.hypot(i, j)
                if best is None or d < best[0]: best = (d, x, y, k)
    print(name, res, 'nearest-to-corner free spot:', best[1:] if best else None)
