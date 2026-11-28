import json,csv,math,collections
C='controller/'
jl={}
for f,scale in [('evidence/fab-loose-ends/cpl-rotation/easyeda_pads.json',0.254),('evidence/c51/jlc_pads.json',0.254),('evidence/c52/jlc_pads.json',1.0)]:
    d=json.load(open(C+f))
    for k,v in d.items():
        if 'pads' not in v: continue
        s=1.0
        jl[k]={'title':v.get('title'),'package':v.get('package'),'pads':[(p['n'],p['x']*s,-p['y']*s) for p in v['pads']],'src':f}
pcb={f['ref']:f for f in json.load(open('_scratch/pcb.json'))}
bom={}
for row in csv.DictReader(open(C+'fab/bom-jlcpcb.csv')):
    for d in row['Designator'].split(','): bom[d]=row
cpl={row['Designator']:row for row in csv.DictReader(open(C+'fab/cpl-jlcpcb.csv'))}
missing=collections.defaultdict(list); title_bad=set(); res=collections.defaultdict(list)
for r,row in cpl.items():
    code=bom[r]['LCSC Part #']; mpn=bom[r]['Manufacturer Part Number']
    if code not in jl: missing[code].append(r); continue
    j=jl[code]
    if j['title']!=mpn: title_bad.add((code,mpn,j['title']))
    X=float(row['Mid X'][:-2]); Y=float(row['Mid Y'][:-2]); R=float(row['Rotation'])
    jp=j['pads']
    xs=[p[1] for p in jp]; ys=[p[2] for p in jp]
    cx=(min(xs)+max(xs))/2; cy=(min(ys)+max(ys))/2
    kp=collections.defaultdict(list)
    for p in pcb[r]['pads']:
        if p['n']: kp[p['n']].append((p['x'],-p['y']))
    def rms(rot):
        a=math.radians(rot); s=0;n=0
        for num,x,y in jp:
            x-=cx;y-=cy
            gx=X+x*math.cos(a)-y*math.sin(a); gy=Y+x*math.sin(a)+y*math.cos(a)
            if num not in kp: return None
            s+=min((gx-kx)**2+(gy-ky)**2 for kx,ky in kp[num]); n+=1
        return math.sqrt(s/n)
    vals={d:rms((R+d)%360) for d in (0,90,180,270)}
    if None in vals.values(): print('PADNUM mismatch',r,code,sorted(kp),[p[0] for p in jp]); continue
    best=min(vals,key=vals.get)
    res[(bom[r]['Footprint'],code,mpn)].append((r,round(vals[0],3),best,round(vals[best],3), len(jp), sum(len(v) for v in kp.values())))
for k,v in sorted(res.items()):
    worst=max(x[1] for x in v); flag='' if all(x[2]==0 or abs(x[1]-x[3])<0.02 for x in v) and worst<0.35 else '  <<<<<<'
    print(k, 'n=%d'%len(v), 'rms@cpl max', worst, 'npads jlc/kicad',v[0][4],v[0][5], flag, [x for x in v if x[2]!=0 and abs(x[1]-x[3])>=0.02][:4])
print('NO JLC PAD DATA:',dict(missing))
print('TITLE != MPN:',title_bad)
