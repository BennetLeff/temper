from lib import *
from shapely.geometry import MultiPoint
for layer,net in [('In1.Cu','selv_gnd'),('In4.Cu','selv_gnd'),('In2.Cu','v3v3'),('F.Cu','selv_gnd'),('B.Cu','selv_gnd')]:
    zp=zonepolys(net,layer)
    print('=====',layer,net,len(zp),'fill polys, total area %.0f mm2 (board 15656)'%sum(p.area for _,_,p in zp))
    vias=[v for v in B['vias'] if v['net']==net]
    pads=[p for p in B['pads'] if p['net']==net]
    for nm,l,pg in sorted(zp,key=lambda z:-z[2].area):
        nv=[v for v in vias if pg.intersects(Point(v['x'],v['y']).buffer(0.15))]
        npd=[p for p in pads if layer in p['layers'] and pg.intersects(padgeom(p))]
        trk=[t for t in B['tracks'] if t['net']==net and t['layer']==layer and pg.intersects(trackgeom(t))]
        b=pg.bounds
        if pg.area<3000 :
            print('  poly area %.2f bbox (%.1f,%.1f)-(%.1f,%.1f) vias %d pads %s tracks %d'%(pg.area,*b,len(nv),[p['ref']+'.'+p['num'] for p in npd][:8],len(trk)))
        else:
            # slots: holes with large extent
            big=[]
            for h in pg.interiors:
                hb=Polygon(h).bounds; ext=max(hb[2]-hb[0],hb[3]-hb[1])
                if ext>=2.5: big.append((round(ext,1),tuple(round(x,1) for x in hb)))
            big.sort(reverse=True)
            print('  MAIN poly area %.0f, %d holes, vias %d; holes with extent>=2.5mm: %d'%(pg.area,len(pg.interiors),len(nv),len(big)))
            for x in big[:25]: print('     ',x)
