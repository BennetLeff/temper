import pcbnew
b = pcbnew.LoadBoard('cad/temper-lcr.kicad_pcb')
L = b.GetLayerID('Dwgs.User')
from collections import Counter
c = Counter(); xs=[]; ys=[]
for d in b.GetDrawings():
    if d.GetLayer() == L:
        c[d.GetClass()] += 1
        bb = d.GetBoundingBox(); xs += [bb.GetLeft(), bb.GetRight()]; ys += [bb.GetTop(), bb.GetBottom()]
        if hasattr(d, 'GetText') and d.GetClass() in ('PCB_TEXT', 'PCB_TEXTBOX'):
            print('---', round(pcbnew.ToMM(d.GetPosition().x),1), round(pcbnew.ToMM(d.GetPosition().y),1)); print(d.GetText())
print(c, 'extent mm', [pcbnew.ToMM(v) for v in (min(xs), max(xs), min(ys), max(ys))])
# silk text listing (board-level)
for d in b.GetDrawings():
    if d.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS) and d.GetClass() == 'PCB_TEXT':
        print('SILK', b.GetLayerName(d.GetLayer()), round(pcbnew.ToMM(d.GetPosition().x),1), round(pcbnew.ToMM(d.GetPosition().y),1), repr(d.GetText()))
