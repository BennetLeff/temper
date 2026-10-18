"""Controller sweep on PERFECT feedback (true T_c), used to freeze KP/KI/KD/I_BAND/SP_RATE
in estimator_study.py before any estimator was compared (DECISIONS.md section 5).

Prints, per pan and jointly, the best gain sets by worst overshoot over eta 0.82/0.92,
keeping those whose hold error is <= 2 K. Run: python controller_sweep.py
"""
import sys, itertools, math
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
import estimator_study as s
from multiprocessing import Pool
def job(c):
    kp,ki,kd,ib,rate,p=c
    s.KP,s.KI,s.KD,s.I_BAND,s.SP_RATE=kp,ki,kd,ib,rate
    out=[]
    for eta in s.ETA_SWEEP:
        m=s.metrics(s.run(p,1000.,eta,0.2,'perfect'))
        out.append((m['overshoot_K'],max(abs(x) for x in m['hold_err_c_K']),m['t_reach_sp1_minus2K_s']))
    return c,(max(o[0] for o in out),max(o[1] for o in out),max(o[2] for o in out))
if __name__=='__main__':
    combos=list(itertools.product((0.02,0.05,0.1,0.2),(0.0005,0.002,0.005),(0,0.5,1.0),(10,30),(math.inf,1.0),list(s.PANS)))
    with Pool(10) as pool: res=pool.map(job,combos)
    for p in s.PANS:
        r=[(v,c[:5]) for c,v in res if c[5]==p]
        print(p, 'min overshoot', min(r)[:2])
        good=[x for x in r if x[0][1]<=2]
        print('   best with hold<=2K:', sorted(good)[:3])
    # joint
    keys=set(c[:5] for c,_ in res)
    joint=[]
    for k in keys:
        vs=[v for c,v in res if c[:5]==k]
        joint.append((max(v[0] for v in vs),max(v[1] for v in vs),max(v[2] for v in vs),k))
    print('joint best by overshoot (hold<=2):', sorted(j for j in joint if j[1]<=2)[:5])
    print('joint best by overshoot (any):', sorted(joint)[:5])
