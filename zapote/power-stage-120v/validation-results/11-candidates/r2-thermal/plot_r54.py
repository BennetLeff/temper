import gzip,json,sys,numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import Polygon,box,LineString,Point
from matplotlib.patches import PathPatch
from matplotlib.path import Path as MPath
PS="/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v"
CACHE="/private/tmp/claude-501/-Users-bennet-Desktop-temper/5a71b9c0-fe6f-4b0a-a3af-0c109a4e3165/scratchpad/r2cache/rise_base_025.npz"
d=json.load(gzip.open(PS+"/native-21/verification/native21s20-all-copper.json.gz","rt"))
o=d["outline"]; xmin,ymin=Polygon(o["shell"]).bounds[:2]
z=np.load(CACHE); rise=z["rise"]; p=0.25
x0,x1,y0,y1=24,60,0,32
fig,axs=plt.subplots(2,2,figsize=(16,14))
cols={"hv_ret":"tab:red","leg_ret":"tab:blue","sw_a":"tab:green","sw_b":"tab:orange","bus_p":"tab:purple"}
for ax,(layer,zi) in zip(axs.ravel(),[("F.Cu",0),("In1.Cu",2),("In2.Cu",4),("B.Cu",6)]):
    T=50+rise[zi]
    i0,i1=int((x0-xmin)/p),int((x1-xmin)/p); j0,j1=int((y0-ymin)/p),int((y1-ymin)/p)
    im=ax.imshow(T[i0:i1,j0:j1].T,origin="lower",extent=[xmin+i0*p,xmin+i1*p,ymin+j0*p,ymin+j1*p],cmap="inferno",vmin=80,vmax=130)
    for it in d["primitives"]:
        if it["layer"]!=layer: continue
        k=it["kind"]
        if k in("zone","pad"):
            P=Polygon(it["shell"],it["holes"])
            if not P.intersects(box(x0,y0,x1,y1)): continue
            xs,ys=P.exterior.xy
            ax.plot(xs,ys,color=cols.get(it["net"],"w"),lw=0.5 if k=="zone" else 1.0)
            if k=="pad": ax.text(P.centroid.x,P.centroid.y,it["ref"],fontsize=5,color="c")
        elif k=="via":
            c=it["centre"]
            if x0<c[0]<x1 and y0<c[1]<y1: ax.add_patch(plt.Circle(c,it["diameter_mm"]/2,fill=False,ec="c",lw=0.4))
    ax.set_xlim(x0,x1);ax.set_ylim(y0,y1);ax.set_aspect("equal");ax.set_title(layer+" T [C] (base c28 h25 0.25mm)")
    fig.colorbar(im,ax=ax,shrink=0.6)
fig.savefig("figs/r54_region_base.png",dpi=110)
# numeric: top cells
T=50+rise
for zi,l in [(0,"F.Cu"),(2,"In1"),(4,"In2"),(6,"B.Cu")]:
    sub=T[zi][int((24-xmin)/p):int((60-xmin)/p),int((0-ymin)/p):int((32-ymin)/p)]
    i,j=np.unravel_index(sub.argmax(),sub.shape); print(l,"max in box",round(sub.max(),1),"at",round(24+i*p+xmin%p,2),round(j*p,2))
