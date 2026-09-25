"""Seeded falsification of analytic inequalities; not interval proof or acceptance policy."""
from pathlib import Path
import importlib.util,sys,random,json,hashlib
here=Path(__file__).parent
source=(Path(__file__).resolve().parent.parent / 'qualification/full_network_bound.py')
spec=importlib.util.spec_from_file_location('sample_network',source);m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m);m.OPEN=float('inf')
ref=json.loads((here/'reference_calculation.json').read_text());rng=random.Random(39165)
def span(r,t,c):return (r*(1-t)*(1-c*60),r*(1+t)*(1+c*60))
def draw(a,b):return rng.choice((a,b,rng.uniform(a,b)))
def q(g,x):return sum(x[i]*g[i][j]*x[j] for i in range(2) for j in range(2))
def psd(g):return g[0][0]>=-1e-10 and g[1][1]>=-1e-10 and g[0][0]*g[1][1]-g[0][1]*g[1][0]>=-1e-12
maxima={n:{'energy_fraction':0.,'dual_fraction':0.,'final_margin_v':-100.,'delta_fraction':0.} for n in ref}
for k in range(500):
 p=m.Params(vb=draw(1.95,2.06),vref=draw(1.24869,1.25131),rref=draw(*span(430,.0005,5e-6)),rlt=draw(*span(61900,.001,25e-6)),rlb=draw(*span(10000,.001,25e-6)),rht=draw(*span(5900,.001,25e-6)),rhb=draw(*span(10000,.001,25e-6)),rdiag=draw(944000,1057000),rdiag_n=draw(944000,1057000),rwin=draw(98000,102000),ileak_max_p=draw(-14e-9,14e-9),ileak_max_n=draw(-14e-9,14e-9),ileak_window=draw(-20e-9,20e-9),ileak_low=draw(-5e-9,5e-9),ileak_high=draw(-5e-9,5e-9),voffl=draw(-.004,.004),voffh=draw(-.004,.004))
 lead=tuple(draw(1,50) for _ in range(4));initial=draw(100,194.1)
 for name,r in ref.items():
  target=draw(.001,10) if name=='SHORT' else initial
  g,w,e,margin=m._solve_static_partition('healthy' if name=='SHORT' else name,target,lead,p,initial,name=='SHORT')
  assert psd([[g[i][j]-r['g_min'][i][j] for j in range(2)] for i in range(2)]),(name,'Gmin',g)
  assert psd([[(r['g_max_diag'][i] if i==j else 0)-g[i][j] for j in range(2)] for i in range(2)]),(name,'Gmax')
  energy=q(g,e);dual=q(m._mat_inv(g),w)
  assert energy<=r['energy_max']*(1+1e-8),(name,'energy',energy)
  assert dual<=r['dual_max']*(1+1e-8),(name,'dual',dual)
  assert margin<=-(.020+r['remaining_v'])+1e-9,(name,'margin',margin)
  assert all(abs(e[i])<=r['delta_v'][i]+1e-9 for i in range(2)),(name,'delta',e)
  d=maxima[name];d['energy_fraction']=max(d['energy_fraction'],energy/r['energy_max']);d['dual_fraction']=max(d['dual_fraction'],dual/r['dual_max']);d['final_margin_v']=max(d['final_margin_v'],margin);d['delta_fraction']=max(d['delta_fraction'],max(abs(e[i])/r['delta_v'][i] for i in range(2)))
receipt={'seed':39165,'parameter_draws':500,'fault_evaluations':2500,'scope':'sample falsification only; exact zero separately checked by ngspice; continuous coverage requires analytic proof','network_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'maxima':maxima,'status':'no counterexample found'}
(here/'sample_inequalities.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
