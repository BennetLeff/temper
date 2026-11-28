import json,sys,csv,re
sys.path.insert(0,'_scratch')
import nl
comps,nets=nl.load('controller/frozen/default.net','controller/frozen/resolved-components.json')
pins={}
for n,nodes in nets.items():
    for r,p in nodes: pins.setdefault(r,{})[p]=n
pcb={f['ref']:f for f in json.load(open('_scratch/pcb.json'))}
print('in netlist not pcb:',sorted(set(comps)-set(pcb)))
print('in pcb not netlist:',sorted(set(pcb)-set(comps)))
bad=0
for r,c in comps.items():
    f=pcb.get(r)
    if not f: continue
    if f['fpid']!=c['fp']: print('FP differs',r,f['fpid'],c['fp'])
    padnets={}
    for p in f['pads']:
        if p['n']=='' : continue
        padnets.setdefault(p['n'],set()).add(p['net'])
    for n,s in padnets.items():
        exp=pins.get(r,{}).get(n)
        got=s
        if exp is None:
            if got!={''} : print('pad w/ net but not in netlist',r,n,got); bad+=1
        elif got!={exp}:
            # KiCad may prefix '/' 
            if {g.lstrip('/') for g in got}!={exp}: print('NET MISMATCH',r,n,got,exp); bad+=1
    for n in pins.get(r,{}):
        if n not in padnets: print('netlist pin missing pad',r,n); bad+=1
print('mismatches',bad)
# BOM/CPL
bom={}
for row in csv.DictReader(open('controller/fab/bom-jlcpcb.csv')):
    for d in row['Designator'].split(','): bom[d]=row
cpl={row['Designator']:row for row in csv.DictReader(open('controller/fab/cpl-jlcpcb.csv'))}
print('bom refs',len(bom),'cpl',len(cpl))
print('netlist not in bom:',sorted(set(comps)-set(bom)))
print('bom not in netlist:',sorted(set(bom)-set(comps)))
print('cpl^bom:',sorted(set(cpl)^set(bom)))
parts=json.load(open('controller/bom/controller-parts.json'))['parts']
for r,c in comps.items():
    if r in bom:
        if bom[r]['Manufacturer Part Number']!=c['mpn']: print('MPN differs',r,bom[r]['Manufacturer Part Number'],c['mpn'])
        if parts.get(c['mpn'],{}).get('lcsc')!=bom[r]['LCSC Part #']: print('LCSC differs',r)
        if bom[r]['Footprint']!=c['fp'].split(':')[-1]: print('BOM fp differs',r)
# CPL pos vs pcb
import collections
rotd=collections.Counter()
for r,row in cpl.items():
    f=pcb[r]
    x=float(row['Mid X'][:-2]); y=float(row['Mid Y'][:-2])
    dx=x-f['x']; dy=y+f['y']
    if abs(dx)>0.01 or abs(dy)>0.01: print('POS off',r,round(dx,3),round(dy,3),f['fpid'])
    d=(float(row['Rotation'])-f['rot'])%360
    rotd[(f['fpid'].split(':')[-1],bom[r]['LCSC Part #'],d)]+=1
    if f['layer']!='F.Cu' or row['Layer']!='Top': print('layer',r)
for k,v in sorted(rotd.items()): print(k,v)
