"""Trunk path trace on power nets: BFS over copper connectivity (track ends, vias, pads) from a source pad to a
sink pad, reporting the bottleneck (narrowest track) along the widest-bottleneck path (maximin). Output work/path_trace.txt"""
import sys; sys.path.insert(0,'work')
from lib_board import *
import heapq
b=load(); T=tracks(b); P=pads(b)
def key(p): return (round(p[0],3), round(p[1],3))
def trace(net, src, dst):
    conn=b.GetConnectivity()
    adj={}
    items={}
    for t in T:
        if t['net']==net: items[id(t['obj'])]=t
    for p in P:
        if p['net']==net: items[id(p['obj'])]=p
    objs={}
    for t in T:
        if t['net']==net: objs[t['obj'].m_Uuid.AsString()]=t
    for p in P:
        if p['net']==net: objs[p['obj'].m_Uuid.AsString()]=p
    def w(x): return x['w'] if x.get('kind')=='track' else 9
    for u,x in objs.items():
        adj.setdefault(u,[])
        for c in conn.GetConnectedItems(x['obj'], [pcbnew.PCB_TRACE_T, pcbnew.PCB_VIA_T, pcbnew.PCB_PAD_T]):
            cu=c.m_Uuid.AsString()
            if cu in objs: adj[u].append((cu, min(w(x),w(objs[cu])), objs[cu]))
    padnodes={(p['ref'],p['num']):p['obj'].m_Uuid.AsString() for p in P if p['net']==net}
    s=padnodes.get(src); d=padnodes.get(dst)
    if s is None or d is None: return f"{net}: missing pad {src if s is None else dst}"
    best={s:9}; prev={}; cnt=[0]; pq=[(-9,0,s)]
    while pq:
        w_,_,u=heapq.heappop(pq); w_=-w_
        if u==d: break
        for v,ew,t in adj.get(u,[]):
            nw=min(w_,ew)
            if nw>best.get(v,-1):
                best[v]=nw; prev[v]=(u,t); cnt[0]+=1; heapq.heappush(pq,(-nw,cnt[0],v))
    if d not in best: return f"{net}: {src}->{dst} NOT CONNECTED"
    path=[]; u=d
    while u!=s:
        pu,t=prev[u]
        if t.get('kind')=='track': path.append(t)
        u=pu
    path.reverse()
    L=sum(dist(t['a'],t['b']) for t in path)
    wmin=min(t['w'] for t in path) if path else 9
    narrow=[t for t in path if t['w']<=wmin+1e-6]
    s_=f"{net}: {src}->{dst}: best-bottleneck path {len(path)} segs {L:.1f} mm, bottleneck {wmin:.2f} mm at "+ "; ".join(f"{t['layer']} ({t['a'][0]:.2f},{t['a'][1]:.2f})-({t['b'][0]:.2f},{t['b'][1]:.2f}) {dist(t['a'],t['b']):.2f}mm" for t in narrow[:6])
    s_+="\n     widths along path: "+" ".join(f"{t['layer'][:2]}{t['w']:.2f}" for t in path)
    return s_
out=[]
for args in [('USB_VBUS',('J1','A4'),('U16','1')),('USB_VBUS',('J1','B4'),('U16','1')),('USB_VBUS',('J1','A9'),('U16','3')),('USB_VBUS',('J1','B9'),('U16','3')),
             ('5V',('U16','6'),('U13','5')),('5V',('U16','6'),('U3','1')),('5V',('U16','6'),('R101','1')),('5V',('U16','6'),('L1','1')),('5V',('U16','6'),('U15','1')),('5V',('U16','6'),('C80','1')),
             ('3V3',('U3','5'),('U1','1')),('3V3',('U3','5'),('U14','6')),('3V3',('U3','5'),('U2','8')),('3V3',('U3','5'),('U17','1')),
             ('RAW_P',('U13','23'),('U11','8')),('RAW_N',('U13','15'),('U12','8')),('12V',('U11','1'),('U7','8')),('12V',('U11','1'),('U6','8')),('12V',('U11','1'),('U5','5')),('-12V',('U12','1'),('U7','4')),('-12V',('U12','1'),('U5','2')),
             ('VRLY',('R101','2'),('K4','1')),('VRLY',('R101','2'),('K1','1'))]:
    out.append(trace(*args))
open('work/path_trace.txt','w').write('\n'.join(out)+'\n'); print('\n'.join(out))
