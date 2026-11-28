# copper to board edge, NPTH to copper, courtyards past the edge
from lib import *
edge=box(20,20,226,96).exterior
cu=[(trackgeom(t),'trk '+t['net']) for t in B['tracks']]+[(viageom(v),'via '+v['net']) for v in B['vias']]+[(padgeom(p),'pad '+p['ref']+'.'+p['num']) for p in B['pads'] if p['attr']!=3]+[(pg,'zone '+nm+' '+l) for nm,l,pg in zonepolys()]
print('copper to edge min: %.3f mm (%s)'%min((g.distance(edge),n) for g,n in cu))
for p in B['pads']:
    if p['attr']==3:
        h=Point(p['x'],p['y']).buffer(p['drill']/2,32); print('NPTH',p['ref'],(p['x'],p['y']),'dia',p['drill'],'to copper %.3f mm (%s)'%min((g.distance(h),n) for g,n in cu),'| wall to edge %.2f'%h.distance(edge))
for f in B['fps']:
    c=f['cy']
    if c and (c[0]<20 or c[1]<20 or c[2]>226 or c[3]>96): print('courtyard past edge:',f['ref'],[round(v,2) for v in c])
