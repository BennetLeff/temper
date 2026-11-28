# independent CPL rotation check: JLC/EasyEDA pad records rotated by the CPL rotation must land pad-number-for-pad-number on the board pads
from lib import *
import csv
recs={}
for f in ['evidence/fab-loose-ends/cpl-rotation/easyeda_pads.json','evidence/c51/jlc_pads.json','evidence/c52/jlc_pads.json']:
    recs.update(json.load(open('../controller/'+f)))
cpl={r['Designator']:r for r in csv.DictReader(open('../controller/fab/cpl-jlcpcb.csv'))}
bom={}
for r in csv.DictReader(open('../controller/fab/bom-jlcpcb.csv')):
    for d in r['Designator'].split(','): bom[d]=r
def centred(pts):
    xs=[p[1] for p in pts]; ys=[p[2] for p in pts]
    cx=(min(xs)+max(xs))/2; cy=(min(ys)+max(ys))/2
    return [(n,x-cx,y-cy) for n,x,y in pts]
norec=collections.Counter(); res=collections.Counter(); bad=[]
for ref,c in cpl.items():
    lc=bom[ref]['LCSC Part #']; rec=recs.get(lc)
    if not rec or not rec.get('pads'): norec[(lc,bom[ref]['Comment'])]+=1; continue
    jp=[(p['n'],float(p['x']),float(p['y'])) for p in rec['pads'] if p['n']]
    # unit: easyeda std = 10 mil units; pro = mm. detect by span
    bp=[(p['num'],p['x'],p['y']) for p in B['pads'] if p['ref']==ref and p['num']]
    jp=centred(jp); bp=centred(bp)
    sj=max(abs(v) for p in jp for v in p[1:]); sb=max(abs(v) for p in bp for v in p[1:])
    scale=0.254 if sj>2.5*sb else 1.0
    jp=[(n,x*scale,y*scale) for n,x,y in jp]
    def rms(theta):
        t=math.radians(theta); tot=0;cnt=0
        jr=collections.defaultdict(list)
        for n,x,y in jp: jr[n].append((x*math.cos(t)+y*math.sin(t),-x*math.sin(t)+y*math.cos(t)))
        for n,x,y in bp:
            if n not in jr: return 99
            tot+=min((x-a)**2+(y-b)**2 for a,b in jr[n]); cnt+=1
        return math.sqrt(tot/cnt)
    rot=float(c['Rotation'])
    e={o:rms((rot+o)%360) for o in (0,90,180,270)}
    best=min(e,key=e.get)
    amb=sorted(e.values())[1]-e[best]<0.05
    if best!=0 and not amb:
        bad.append((ref,lc,bom[ref]['Comment'],c['Mount'],'CPL rot %s; pads fit only with extra %d deg'%(rot,best),{k:round(v,2) for k,v in e.items()}))
    res['ok' if best==0 or amb else 'BAD '+c['Mount']]+=1
    if e[best]>0.35: print('poor fit',ref,lc,bom[ref]['Comment'],{k:round(v,2) for k,v in e.items()})
print(res); print('no record:',dict(norec))
for b in bad: print(b)
