"""Shared helpers for the review scripts (read-only on the board)."""
import pcbnew, math, json
BOARD = 'cad/temper-lcr.kicad_pcb'
def load(path=BOARD):
    return pcbnew.LoadBoard(path)
def mm(v): return v/1e6
def pt(p): return (p.x/1e6, p.y/1e6)
def dist(a,b): return math.hypot(a[0]-b[0], a[1]-b[1])
def seg_dist(p, a, b):
    """distance from point p to segment ab"""
    ax,ay=a; bx,by=b; px,py=p
    dx,dy=bx-ax,by-ay
    L2=dx*dx+dy*dy
    if L2==0: return dist(p,a)
    t=max(0,min(1,((px-ax)*dx+(py-ay)*dy)/L2))
    return dist(p,(ax+t*dx, ay+t*dy))
def layername(b, l): return b.GetLayerName(l)
def tracks(b):
    out=[]
    for t in b.GetTracks():
        if t.GetClass()=='PCB_VIA':
            out.append(dict(kind='via', net=t.GetNetname(), at=pt(t.GetPosition()), drill=mm(t.GetDrillValue()), dia=mm(t.GetWidth(pcbnew.F_Cu)), obj=t))
        else:
            out.append(dict(kind='track', net=t.GetNetname(), layer=b.GetLayerName(t.GetLayer()), a=pt(t.GetStart()), b=pt(t.GetEnd()), w=mm(t.GetWidth()), obj=t))
    return out
def pads(b):
    out=[]
    for fp in b.GetFootprints():
        for pd in fp.Pads():
            ls=pd.GetLayerSet()
            layers=[b.GetLayerName(l) for l in ls.Seq() if b.GetLayerName(l) in ('F.Cu','In1.Cu','In2.Cu','B.Cu')]
            out.append(dict(ref=fp.GetReference(), num=pd.GetNumber(), net=pd.GetNetname(), at=pt(pd.GetPosition()),
                size=(mm(pd.GetSize().x), mm(pd.GetSize().y)), drill=mm(pd.GetDrillSize().x), layers=layers,
                th=pd.GetAttribute()==pcbnew.PAD_ATTRIB_PTH, obj=pd, fp=fp, rot=pd.GetOrientationDegrees()))
    return out
