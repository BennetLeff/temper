from lib import *
import csv,re
cpl={r['Designator']:r for r in csv.DictReader(open('../controller/fab/cpl-jlcpcb.csv'))}
bom=list(csv.DictReader(open('../controller/fab/bom-jlcpcb.csv')))
bomref={}
for r in bom:
    for d in r['Designator'].split(','): 
        assert d not in bomref, d
        bomref[d]=r
fps={f['ref']:f for f in B['fps']}
print('fps',len(fps),'cpl',len(cpl),'bom refs',len(bomref),'netlist',len(N['comps']))
print('in board not in CPL:',sorted(set(fps)-set(cpl)))
print('in CPL not board:',sorted(set(cpl)-set(fps)))
print('in board not BOM:',sorted(set(fps)-set(bomref)),' BOM not board:',sorted(set(bomref)-set(fps)))
print('netlist not board:',sorted(set(N['comps'])-set(fps)),'board not netlist:',sorted(set(fps)-set(N['comps'])))
# footprint agreement BOM vs board vs netlist
for r,f in fps.items():
    if r in bomref and bomref[r]['Footprint']!=f['fpid'].split(':')[-1]: print('FP MISMATCH bom',r,bomref[r]['Footprint'],f['fpid'])
    if r in N['comps'] and N['comps'][r]['footprint']!=f['fpid']: print('FP MISMATCH netlist',r,N['comps'][r]['footprint'],f['fpid'])
# position check + rotation offsets
off=collections.defaultdict(lambda: collections.defaultdict(list))
for r,c in cpl.items():
    f=fps[r]; x=float(c['Mid X'][:-2]); y=-float(c['Mid Y'][:-2]); rot=float(c['Rotation'])
    # pad-centroid
    pads=[p for p in B['pads'] if p['ref']==r and p['num']]
    cx=sum(p['x'] for p in pads)/len(pads); cy=sum(p['y'] for p in pads)/len(pads)
    bx=(min(p['bb'][0] for p in pads)+max(p['bb'][2] for p in pads))/2; by=(min(p['bb'][1] for p in pads)+max(p['bb'][3] for p in pads))/2
    d_origin=math.hypot(x-f['x'],y-f['y']); d_bb=math.hypot(x-bx,y-by)
    if min(d_origin,d_bb)>0.05: print('POS',r,f['fpid'],'cpl',(x,y),'origin',(f['x'],f['y']),'padbbox-centre',(round(bx,3),round(by,3)))
    o=(rot-f['rot'])%360
    off[(f['fpid'].split(':')[-1],bomref[r]['LCSC Part #'],bomref[r]['Comment'])][o].append(r)
    if c['Layer']!='Top': print('LAYER',r,c)
for k in sorted(off):
    print(k,{o:(v if len(v)<6 else '%d parts'%len(v)) for o,v in off[k].items()})
