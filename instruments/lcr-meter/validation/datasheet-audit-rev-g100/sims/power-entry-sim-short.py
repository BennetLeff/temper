import itertools, subprocess, re, tempfile, pathlib
def ng(deck):
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/'c.cir'; p.write_text(deck)
        out=subprocess.run(['ngspice','-b',str(p)],capture_output=True,text=True,timeout=300).stdout
    m={k:float(v) for k,v in re.findall(r'^(\w+)\s*=\s*([-\d.eE+]+)',out,re.M)}
    if 'vu' not in m: print(out[-1500:])
    return m
def short(v,l,r,c,host_lim,d1,c15_at_u16,toff=100e-9,rs=0.05,tios=2e-6):
    t0=50e-6
    d=f"""* short at OUT
Vs src 0 DC {v}
Bh src n0 I = {host_lim}*tanh(v(src,n0)/(0.01*{host_lim}))
Rcab n0 n1 {r}
Lcab n1 j1 {l}
{'C15 u2 0 100n' if c15_at_u16 else 'C15 j1 0 100n'}
Lb j1 u 25n
Rb u u2 0.03
C113 u2 c1 {c}
R121 c1 0 1.503
{'D1 0 j1 DZ' if d1 else ''}
.model DZ D(BV=6.0 IBV=1m RS=2.25 CJO=1p)
Bsw u2 out I = min(v(u2,out)/0.085, (time < {t0+tios} ? 1000 : max(1.17, 1000*(1-(time-{t0+tios})/{toff}))))
C16 out 0 0.7u
Rload out 0 10.9
Sshort out 0 ctl 0 SW1
Vctl ctl 0 PWL(0 0 {t0} 0 {t0+1e-9} 1)
.model SW1 SW(Ron={rs} Roff=1e9 Vt=0.5 Vh=0)
.tran 2n 90u 0 5n
.meas tran vu MAX v(u2) FROM={t0} TO=90u
.meas tran vj MAX v(j1) FROM={t0} TO=90u
.meas tran vmin MIN v(u2) FROM={t0} TO=90u
.end
"""
    return ng(d)
for host in (1000, 5.0, 3.0, 1.5):
  for d1 in (False, True):
    for c15u in (False, True):
      w=None; n7=0; n=0
      for v,l,r,c in itertools.product((5.0,5.5),(0.3e-6,1.0e-6,1.5e-6),(0.05,0.2),(4.7e-6*0.54,4.7e-6*1.1)):
        m=short(v,l,r,c,host,d1,c15u); n+=1; n7+= m['vu']>=7
        if w is None or m['vu']>w[0]: w=(round(m['vu'],2),round(m['vj'],2),round(m['vmin'],2),v,l*1e6,r,round(c*1e6,2))
      print('host_lim',host,'d1',d1,'c15_at_u16',c15u,'worst (vU16,vJ1,vmin,vbus,L,R,C113)',w,f'{n7}/{n} >=7V',flush=True)
