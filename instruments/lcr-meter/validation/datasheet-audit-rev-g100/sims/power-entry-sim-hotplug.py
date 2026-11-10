"""Scratch ngspice runs for the power-entry audit (not repository evidence).
hot: hot-plug with C15 at the J1 node and board copper L between J1 and U16 IN (as-built G100 order).
short: hard short at U16 OUT while running; U16 = 85 mOhm until t_ios, then limits at 1.17 A."""
import itertools, subprocess, re, tempfile, pathlib, sys, json
VB=(5.0,5.25,5.5); LC=(0.3e-6,0.6e-6,1.0e-6,1.5e-6); RC=(0.05,0.1,0.2,0.3); C113=(4.7e-6*0.54,4.7e-6*1.1)
def ng(deck):
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/'c.cir'; p.write_text(deck)
        out=subprocess.run(['ngspice','-b',str(p)],capture_output=True,text=True,timeout=300).stdout
    return {k:float(v) for k,v in re.findall(r'^(\w+)\s*=\s*([-\d.eE+]+)',out,re.M)}
def hot(v,l,r,c,lb,c_at_u16):
    d=f"""* hot
Vs src 0 PWL(0 0 1n {v} 1 {v})
Rcab src n1 {r}
Lcab n1 j1 {l}
C15 j1 0 100n
R5 j1 0 100k
Lb j1 u {lb}
Rb u u2 0.03
C113 u2 c1 {c}
R121 c1 0 1.503
{'Cnew u2 0 100n' if c_at_u16 else ''}
.tran 1n 60u 0 2n
.meas tran vu MAX v(u2)
.meas tran vj MAX v(j1)
.end
"""
    return ng(d)
def short(v,l,r,c,lb,tios,c_at_u16,rs=0.05):
    d=f"""* short at OUT
Vs src 0 DC {v}
Rcab src n1 {r}
Lcab n1 j1 {l}
C15 j1 0 100n
Lb j1 u {lb}
Rb u u2 0.03
C113 u2 c1 {c}
R121 c1 0 1.503
{'Cnew u2 0 100n' if c_at_u16 else ''}
Bsw u2 out I = min(v(u2,out)/0.085, (time < {50e-6+tios} ? 1000 : 1.17))
C16 out 0 0.7u
Rload out 0 10.9
Sshort out 0 ctl 0 SW1
Vctl ctl 0 PWL(0 0 50u 0 50.001u 1)
.model SW1 SW(Ron={rs} Roff=1e9 Vt=0.5 Vh=0)
.tran 2n 80u 0 5n uic
.ic v(u2)={v-0.05} v(j1)={v-0.05} v(out)={v-0.09} v(c1)=0
.meas tran vu MAX v(u2) FROM=50u TO=80u
.meas tran vj MAX v(j1) FROM=50u TO=80u
.meas tran vmin MIN v(u2) FROM=50u TO=80u
.meas tran ipk MAX i(Vs) FROM=50u TO=80u
.end
"""
    return ng(d)
mode=sys.argv[1]
rows=[]
if mode=='hot':
    for lb,cu in ((0,False),(20e-9,False),(30e-9,False),(30e-9,True)):
        w=None
        for v,l,r,c in itertools.product(VB,LC,RC,C113):
            m=hot(v,l,r,c,lb,cu); row=dict(lb_nH=lb*1e9,c_at_u16=cu,v=v,l=l*1e6,r=r,c113=round(c*1e6,2),vu=m.get('vu'),vj=m.get('vj'))
            if w is None or row['vu']>w['vu']: w=row
            rows.append(row)
        n65=sum(1 for x in rows if x['lb_nH']==lb*1e9 and x['c_at_u16']==cu and x['vu']>6.5)
        n7=sum(1 for x in rows if x['lb_nH']==lb*1e9 and x['c_at_u16']==cu and x['vu']>=7)
        print('hot lb',lb*1e9,'cnew',cu,'worst',w,'>6.5:',n65,'>=7:',n7, flush=True)
else:
    for tios in (2e-6,):
        for cu in (False,True):
            w=None; n7=0
            for v,l,r,c in itertools.product(VB,LC,RC,C113):
                m=short(v,l,r,c,25e-9,tios,cu); row=dict(tios=tios,c_at_u16=cu,v=v,l=l*1e6,r=r,c113=round(c*1e6,2),**m)
                n7+= m['vu']>=7
                if w is None or row['vu']>w['vu']: w=row
            print('short tios',tios,'cnew',cu,'worst',w,'n>=7',n7,flush=True)
