from pathlib import Path
import importlib.util,sys,math,json
s=importlib.util.spec_from_file_location('network_oracle',(Path(__file__).resolve().parent.parent / 'qualification/full_network_bound.py'));m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);m.OPEN=float('inf')
# Independent analytic calculation from root proposal; only the established
# external-node network reduction is reused for the three fast cases.
def span(r,t,c):return (r*(1-t)*(1-c*60),r*(1+t)*(1+c*60))
vb=(1.95,2.06);vr=(1.24869,1.25131);rr=span(430,.0005,5e-6);lt=span(61900,.001,25e-6);lb=span(10000,.001,25e-6);ht=span(5900,.001,25e-6);hb=lb;rd=(944000,1057000);rw=(98000,102000)
L=58e-9;Rp=294.101;Rn=100.001;al=lt[1]/(lt[1]+lb[0]);bt=lb[0]/(lt[1]+lb[0]);par=lambda a,b:a*b/(a+b)
hi=vr[1]*hb[1]/(ht[0]+hb[1])+5e-9*par(ht[1],hb[1]);gmn=1/rd[1]+1/(lt[1]+lb[1]);J=2*vb[1]/rd[0]+vr[1]/(lt[0]+lb[0])+L
isp=(vb[1]+L*Rp)/rd[0]+34e-9
isn=(vb[1]+L*Rn)/rd[0]+max(vr[1]+L*Rn,vb[1]+L*Rn-vr[0])/(lt[0]+lb[0])+19e-9
p_low,p_hi=vb[0]-rd[1]*34e-9,vb[1]+rd[1]*34e-9
sp_delta=max(p_hi+L*Rp,vb[1]+L*Rp-p_low)
m_low,m_hi=vr[0]-19e-9/gmn,vb[1]+19e-9/gmn
sm_delta=max(m_hi+L*Rn,vb[1]+L*Rn-m_low)
final={}
final['SENSE+']=vb[0]-rd[1]*34e-9-rw[1]*20e-9-hi-.004-.020
sp_upper=vb[1]*(194.1+50+.001)/(rr[0]+1+194.1+50+.001)+(vb[1]/rd[0]+L)*Rp
final['SENSE-']=vr[0]-19e-9/gmn-5e-9*par(lt[1],lb[1])-sp_upper-rw[1]*20e-9-.004-.020
final['FORCE+']=vr[0]*bt-al*L*Rn-5e-9*par(lt[1],lb[1])-J*Rp-rw[1]*20e-9-.004-.020
final['FORCE-']=vb[0]-((vb[1]-vr[0])/(lt[0]+lb[0])+L)*(rr[1]+100)-rw[1]*20e-9-hi-.004-.020
wi=(vb[1]/(rr[0]+2+.001)+J)*10+(vb[1]/rd[0]+34e-9)*50+(vb[1]/rd[0]+vr[1]/(lt[0]+lb[0])+19e-9)*50+rw[1]*20e-9
mn=vb[1]*(50+.001)/(rr[0]+1+50+.001)+J*Rn
final['SHORT']=bt*(vr[0]-mn)-5e-9*par(lt[1],lb[1])-wi-.004-.020
cp=[[1.3e-9,-1.1e-9],[-1.1e-9,1.3e-9]]
p=m.Params(vb=0,vref=0,rref=rr[1],rlt=lt[1],rlb=lb[1],rht=ht[1],rhb=hb[1],rdiag=rd[1],rdiag_n=rd[1],rwin=rw[1],ileak_max_p=0,ileak_max_n=0,ileak_window=0,ileak_low=0,ileak_high=0,voffl=0,voffh=0)
rows={}
for name in ['FORCE+','FORCE-','SENSE+','SENSE-','SHORT']:
 gm=[1+1/rd[0]+1/rw[0],1+1/rd[0]+1/lb[0]];d=[2.1,2.1]
 if name=='SENSE+':
  g=[[1/rd[1],0],[0,1/Rn]];gm=[1/rd[0],1+1/rd[0]+1/(lt[0]+lb[0])];d=[sp_delta,isp*Rn]
 elif name=='SENSE-':
  g=[[1/Rp,0],[0,gmn]];gm=[1+1/rd[0],1/rd[0]+1/(lt[0]+lb[0])];d=[isn*Rp,sm_delta]
 else:
  g=m._solve_static_partition('healthy' if name=='SHORT' else name,10 if name=='SHORT' else 194.1,(50.,)*4,p,194.1,name in ['SHORT','FORCE+'])[0]
 detg=g[0][0]*g[1][1]-g[0][1]*g[1][0];detc=cp[0][0]*cp[1][1]-cp[0][1]**2
 cross=g[0][0]*cp[1][1]+g[1][1]*cp[0][0]-2*g[0][1]*cp[0][1]
 lam=2*detg/(cross+math.sqrt(cross*cross-4*detc*detg))
 gi=[[g[1][1]/detg,-g[0][1]/detg],[-g[1][0]/detg,g[0][0]/detg]]
 c=[1,0 if name in ['SENSE+','FORCE-'] else al]
 dual=sum(c[i]*abs(gi[i][j])*c[j] for i in range(2) for j in range(2));E=sum(gm[i]*d[i]**2 for i in range(2));t=max(0,math.log(math.sqrt(E*dual)/final[name]))/lam*1000+.000065
 rows[name]={'g_min':g,'g_max_diag':gm,'c_max':cp,'delta_v':d,'lambda_min_per_s':lam,'energy_max':E,'dual_max':dual,'remaining_v':final[name],'bound_ms':t}
print(json.dumps(rows,indent=2));(Path(__file__).resolve().parent / 'reference_calculation.json').write_text(json.dumps(rows,indent=2)+'\n')
