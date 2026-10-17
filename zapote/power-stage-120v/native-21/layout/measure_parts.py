import pcbnew, csv, json, re, collections, os
net=open('native-21/frozen/default.net').read()
refpath={m.group(1):m.group(2) for m in re.finditer(r'\(comp \(ref "([^"]+)"\).*?\(sheetpath \(names "[^"]*::([^"]+)"\)', net, re.S)}
fp_of={}
for row in csv.DictReader(open('native-21/frozen/default.csv')):
    for r in row['Designator'].split(','): fp_of[r]=row['Footprint']
libs={'temper':'libraries/temper.pretty','lib':'libraries/lib.pretty'}
cache={}
def crt(fp):
    if fp in cache: return cache[fp]
    lib,name=fp.split(':',1)
    f=None
    for d in ([libs[lib]] if lib in libs else [])+['native-20/candidate-libs/%s.pretty'%lib,'/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/%s.pretty'%lib]:
        if os.path.exists(os.path.join(d,name+'.kicad_mod')):
            f=pcbnew.FootprintLoad(d,name); break
    if f is None:
        print('MISSING',fp); cache[fp]=(0,0,0,0); return cache[fp]
    b=f.GetCourtyard(pcbnew.F_CrtYd).BBox() if f.GetCourtyard(pcbnew.F_CrtYd).OutlineCount() else f.GetBoundingBox(False,False)
    cache[fp]=(b.GetWidth()/1e6,b.GetHeight()/1e6,b.GetCenter().x/1e6,b.GetCenter().y/1e6); return cache[fp]
def group(p):
    for k in ('leg_a','leg_b','bias_ha','bias_hb','monitor_ls','bias_ls','line_zc'):
        if p.startswith(k): return k
    if p.startswith(('bias_','u_bias','r_bias','c_bias')): return 'bias_common'
    if 'ct' in p.split('.')[0] or p.startswith(('t_ct','u_ct','d_ct','r_ct','c_ct','u_fault','c_fault')): return 'ct_selv'
    if p.startswith(('u_ocp','u_ovp','u_ref','r_th','r_ocp','c_ocp','r_ovp','c_ovp','u_nand','c_nand','u_iso','c_iso','u_ldo','c_ldo','u_hot5','r_hot5','c_hot5','r_ref','c_th','u_vsense','c_vs','r_div','c_div')): return 'hot_protect'
    if p.startswith(('j_mains','f1','rv1','cx','cy','l1','rb1','br1')): return 'mains'
    if p.startswith(('c_bus','c_hf','tvs','r_bus','r_crb','c_res','r_shunt','j_coil','link_','c_v15','ps_','j_tco','j_selv','j_pe','r_fe')): return 'power_misc'
    return 'other:'+p.split('.')[0]
area=collections.Counter(); cnt=collections.Counter(); big=[]; rows_out=[]
for r,p in refpath.items():
    w,h,ox,oy=crt(fp_of[r]); a=(w)*(h); g=group(p); area[g]+=a; cnt[g]+=1
    if a>300: big.append((r,p,round(w,1),round(h,1)))
    rows_out.append({'ref':r,'path':p,'fp':fp_of[r],'w':round(w,2),'h':round(h,2),'ox':round(ox,3),'oy':round(oy,3),'group':g})
import json as _j; _j.dump(rows_out, open("/private/tmp/claude-501/parts21.json","w"), indent=0)
tot=sum(area.values())
for g,a in area.most_common(): print(f"{g:16s} n={cnt[g]:3d} area={a:8.0f} mm2")
print('TOTAL', round(tot), 'mm2 courtyard;', 'board 290x140 =', 290*140, '; fill', round(tot/(290*140)*100), '%')
print(sorted(big,key=lambda x:-x[2]*x[3])[:20])
