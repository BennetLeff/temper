"""Rev G vs G100: the analog core and jack band copper (signal nets) are meant to be identical. Compare every
track and via of the two boards, keyed by (layer, net, start, end, width) / (net, at, drill), restricted to the
region y < 107 and reporting by net which segments exist in one board only. Also compare footprint positions
in that region. Output work/revg_compare.txt"""
import sys; sys.path.insert(0,'work')
from lib_board import *
g=load('rev-g/temper-lcr-rev-g.kicad_pcb'); n=load('cad/temper-lcr.kicad_pcb')
def keyset(b):
    ks={}
    for t in tracks(b):
        if t['kind']=='track':
            a,c=t['a'],t['b']
            if a>c: a,c=c,a
            k=('T',t['layer'],t['net'],round(a[0],3),round(a[1],3),round(c[0],3),round(c[1],3),round(t['w'],3))
        else:
            k=('V',t['net'],round(t['at'][0],3),round(t['at'][1],3),round(t['drill'],3))
        ks[k]=t
    return ks
def fps(b):
    return {fp.GetReference():(round(mm(fp.GetPosition().x),3),round(mm(fp.GetPosition().y),3),fp.GetOrientationDegrees(),fp.GetValue()) for fp in b.GetFootprints()}
G=keyset(g); N=keyset(n); out=[]
bbg=g.GetBoardEdgesBoundingBox(); out.append(f"Rev G outline bbox {mm(bbg.GetLeft())},{mm(bbg.GetTop())} - {mm(bbg.GetRight())},{mm(bbg.GetBottom())}")
FG,FN=fps(g),fps(n)
out.append("== footprints moved / changed (y < 108 in G100) or missing in either")
for r in sorted(set(FG)|set(FN)):
    a=FG.get(r); c=FN.get(r)
    if a is None: out.append(f"  {r}: only in G100 at {c}"); continue
    if c is None: out.append(f"  {r}: only in Rev G at {a}"); continue
    if c[1]<108 and (abs(a[0]-c[0])>0.001 or abs(a[1]-c[1])>0.001 or a[2]!=c[2] or a[3]!=c[3]): out.append(f"  {r}: G {a} -> G100 {c}")
out.append("== value changes anywhere")
for r in sorted(set(FG)&set(FN)):
    if FG[r][3]!=FN[r][3]: out.append(f"  {r}: {FG[r][3]} -> {FN[r][3]}")
def y_of(k): return k[4] if k[0]=='T' else k[3]
onlyG=[k for k in G if k not in N and y_of(k)<107]; onlyN=[k for k in N if k not in G and y_of(k)<107]
from collections import Counter
out.append(f"== copper items y<107: Rev G {sum(1 for k in G if y_of(k)<107)}, G100 {sum(1 for k in N if y_of(k)<107)}; only-in-G {len(onlyG)}, only-in-G100 {len(onlyN)}")
cg=Counter((k[2] if k[0]=='T' else k[1]) for k in onlyG); cn=Counter((k[2] if k[0]=='T' else k[1]) for k in onlyN)
out.append("  per net (only in Rev G / only in G100):")
for net in sorted(set(cg)|set(cn)): out.append(f"    {net:16s} {cg.get(net,0):4d} / {cn.get(net,0):4d}")
out.append("== detail: signal-net (not GND / supply) differences y<107")
SUP={'GND','3V3','3V3A','5V','5VA','12V','-12V','RAW_P','RAW_N','VRLY','USB_VBUS','LDOIN_P','LDOIN_N'}
for k in sorted(onlyG, key=str):
    net=k[2] if k[0]=='T' else k[1]
    if net not in SUP: out.append(f"  Rev G only: {k}")
for k in sorted(onlyN, key=str):
    net=k[2] if k[0]=='T' else k[1]
    if net not in SUP: out.append(f"  G100 only : {k}")
open('work/revg_compare.txt','w').write('\n'.join(out)+'\n'); print('\n'.join(out))
