"""Sweep the C1 fixed-contact-model nominal h: design cases (contact-model spread) vs a
h_c = 700 floor. Picks h_nom = 1300 (DECISIONS section 3). Run: python hnom_sweep.py
"""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
import screen as s
from multiprocessing import Pool
def job(a):
    hn,pan,h,eta=a
    s.apply(s.CANDS['C1']); L,_=s.run('C1',pan,h,eta,'kf_fixed',11,hn); m=s.metrics(L)
    lim=1.5 if s.es.PANS[pan]['sp'][1]<=100 else 3.0
    ok=m['est_err_c_max_K']<=3 and m['overshoot_K']<=5 and max(abs(x) for x in m['hold_err_c_K'])<=lim
    return a,ok,m['est_err_c_max_K'],m['overshoot_K']
if __name__=='__main__':
    s.apply(s.CANDS['C1']); sp=s.h_spread(s.CANDS['C1'])
    jobs=[]
    for hn in (900.,1100.,1300.,1722.):
        for pan,(lo,hi) in sp.items():
            for h in (lo,hi,700.):
                for eta in (0.82,0.92): jobs.append((hn,pan,h,eta))
    with Pool(10) as pool: res=pool.map(job,jobs)
    for hn in (900.,1100.,1300.,1722.):
        r=[x for x in res if x[0][0]==hn]
        d=[x for x in r if x[0][2]!=700.]; f=[x for x in r if x[0][2]==700.]
        print(hn,'design pass',sum(x[1] for x in d),'/',len(d),'worst err',max(x[2] for x in d),'os',max(x[3] for x in d),'| h700 pass',sum(x[1] for x in f),'/',len(f),'worst',max(x[2] for x in f),max(x[3] for x in f))
