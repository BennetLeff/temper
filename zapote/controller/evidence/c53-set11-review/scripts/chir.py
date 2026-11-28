# body-vs-numbering comparison of JLC/EasyEDA footprints (pro.easyeda.com records) with the board's KiCad footprints
import json,sys,math
sys.path.insert(0,'..')
from lib import *
MIL=0.0254
def jlc(code):
    pads=[];shape=None
    for line in open(code+'.txt'):
        try: r=json.loads(line)
        except Exception: continue
        if not r: continue
        if r[0]=='PAD' and str(r[5]): pads.append((str(r[5]),r[6]*MIL,-r[7]*MIL))   # y down
        if r[0]=='POLY' and r[4]==48:
            nums=[v for v in r[6] if isinstance(v,(int,float))]
            xs=nums[0::2]; ys=[-v for v in nums[1::2]]
            bb=(min(xs)*MIL,min(ys)*MIL,max(xs)*MIL,max(ys)*MIL)
            if shape is None or (bb[2]-bb[0])*(bb[3]-bb[1])>(shape[2]-shape[0])*(shape[3]-shape[1]): shape=bb
    return pads,shape
import re
libdir='../../controller/pcb/libs/'
def kicad(ref):
    f=[f for f in B['fps'] if f['ref']==ref][0]
    lib,name=f['fpid'].split(':')
    s=open(libdir+lib+'.pretty/'+name+'.kicad_mod').read()
    # F.Fab lines bbox
    xs=[];ys=[]
    for m in re.finditer(r'\(fp_(?:line|rect)\s*\(start ([-\d.]+) ([-\d.]+)\)\s*\(end ([-\d.]+) ([-\d.]+)\)(?:(?!\(fp_).)*?\(layer "F.Fab"\)',s,re.S):
        a=list(map(float,m.groups())); xs+=[a[0],a[2]]; ys+=[a[1],a[3]]
    pads=[(m.group(1),float(m.group(2)),float(m.group(3))) for m in re.finditer(r'\(pad "(\d+)" \w+ \w+\s*\(at ([-\d.]+) ([-\d.]+)',s)]
    return pads,(min(xs),min(ys),max(xs),max(ys)),f
def rot(p,th):
    t=math.radians(th); x,y=p
    return (x*math.cos(t)+y*math.sin(t),-x*math.sin(t)+y*math.cos(t))
import csv
cpl={r['Designator']:r for r in csv.DictReader(open('../../controller/fab/cpl-jlcpcb.csv'))}
for ref,code in [('J1','C158012'),('J3','C144395'),('J9','C144395'),('J10','C144394'),('J12','C144394'),('J15','C157991'),('J7','C158027'),('J14','C131337'),('J13','C160315'),('J4','C277731'),('J2','C158012')]:
    jp,js=jlc(code); kp,ks,f=kicad(ref)
    # express each as: body bbox relative to pad-bbox centre
    def rel(pads,shape):
        cx=(min(p[1] for p in pads)+max(p[1] for p in pads))/2; cy=(min(p[2] for p in pads)+max(p[2] for p in pads))/2
        p1=[p for p in pads if p[0]=='1'][0]
        return (p1[1]-cx,p1[2]-cy),(shape[0]-cx,shape[1]-cy,shape[2]-cx,shape[3]-cy)
    jp1,jb=rel(jp,js); kp1,kb=rel(kp,ks)
    out=[]
    for off in (0,90,180,270):
        # JLC footprint rotated by 'off' relative to KiCad footprint
        c=[rot((jb[0],jb[1]),off),rot((jb[2],jb[3]),off)]
        b=(min(c[0][0],c[1][0]),min(c[0][1],c[1][1]),max(c[0][0],c[1][0]),max(c[0][1],c[1][1]))
        p=rot(jp1,off)
        body_err=max(abs(b[i]-kb[i]) for i in range(4)); pin_err=math.dist(p,kp1)
        out.append((off,round(body_err,2),round(pin_err,2)))
    print(ref,code,'CPL rot',cpl[ref]['Rotation'],'board rot',f['rot'],'| offset: (body mismatch mm, pin-1 mismatch mm):',out)
    print('     kicad body rel pads',[round(v,2) for v in kb],'pin1',[round(v,2) for v in kp1],'| jlc body',[round(v,2) for v in jb],'pin1',[round(v,2) for v in jp1])
