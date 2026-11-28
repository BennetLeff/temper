import json, math, collections
from shapely.geometry import Polygon, Point, LineString, box
from shapely.ops import unary_union
from shapely import affinity
B=json.load(open(__file__.rsplit('/',1)[0]+'/board.json'))
N=json.load(open(__file__.rsplit('/',1)[0]+'/net.json'))
CU=['F.Cu','In1.Cu','In2.Cu','In3.Cu','In4.Cu','B.Cu']
def padgeom(p):
    # shape: 0 circle 1 rect 2 oval 3 trapezoid 4 roundrect 5 chamfered 6 custom
    if p['shape']==0: return Point(p['x'],p['y']).buffer(p['sx']/2,16)
    if p['shape']==2:
        sx,sy=p['sx'],p['sy']; r=min(sx,sy)/2
        if sx>=sy: g=LineString([(-(sx/2-r),0),(sx/2-r,0)]).buffer(r,16) if sx>sy else Point(0,0).buffer(r,16)
        else: g=LineString([(0,-(sy/2-r)),(0,sy/2-r)]).buffer(r,16)
    else: g=box(-p['sx']/2,-p['sy']/2,p['sx']/2,p['sy']/2)
    g=affinity.rotate(g,-p['rot'],origin=(0,0))
    return affinity.translate(g,p['x'],p['y'])
def trackgeom(t): return LineString([(t['x1'],t['y1']),(t['x2'],t['y2'])]).buffer(t['w']/2,8)
def viageom(v): return Point(v['x'],v['y']).buffer(v['d']/2,16)
def zonepolys(net=None,layer=None):
    out=[]
    for z in B['zones']:
        if net is not None and z['net']!=net: continue
        for l,ps in z['fills'].items():
            if layer and l!=layer: continue
            for ext,holes in ps:
                pg=Polygon(ext,holes)
                if not pg.is_valid: pg=pg.buffer(0)
                out.append((z['name'],l,pg))
    return out
def netitems(net):
    """list of (kind, layerset, geom, obj)"""
    it=[]
    for p in B['pads']:
        if p['net']==net: it.append(('pad',set(p['layers']),padgeom(p),p))
    for t in B['tracks']:
        if t['net']==net: it.append(('trk',{t['layer']},trackgeom(t),t))
    for v in B['vias']:
        if v['net']==net: it.append(('via',set(CU),viageom(v),v))
    for nm,l,pg in zonepolys(net):
        it.append(('zone',{l},pg,dict(name=nm,layer=l)))
    return it
def graph(items):
    from shapely.strtree import STRtree
    geoms=[i[2] for i in items]; tree=STRtree(geoms)
    adj=collections.defaultdict(set)
    for i,g in enumerate(geoms):
        for j in tree.query(g):
            j=int(j)
            if j<=i: continue
            if not (items[i][1]&items[j][1]): continue
            if g.intersects(geoms[j]): adj[i].add(j); adj[j].add(i)
    return adj
def w2k(x,y): return x+58,110-y
def k2w(x,y): return x-58,110-y
