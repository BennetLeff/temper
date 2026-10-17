import json, sys
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from shapely.geometry import Polygon, LineString, Point, box
from shapely.ops import unary_union
d=json.load(open(sys.argv[1])); X0,Y0,X1,Y1=map(float,sys.argv[3:7]); win=box(X0,Y0,X1,Y1)
col={'res_a':'red','coil_feed':'orange','sw_a':'purple','sw_b':'magenta','n_ls':'green','hv_ret':'blue','bus_p':'cyan'}
fig,axs=plt.subplots(2,2,figsize=(16,14))
for ax,L in zip(axs.flat,('F.Cu','In1.Cu','In2.Cu','B.Cu')):
    def draw(g,n):
        g=g.intersection(win)
        if g.is_empty: return
        for p in getattr(g,'geoms',[g]):
            if p.geom_type=='Polygon':
                x,y=p.exterior.xy; ax.fill(x,y,color=col.get(n,'grey'),alpha=0.5 if n in col else 0.25,lw=0)
    for z in d['zones']:
        if z['layer']==L and len(z['pts'])>=3: draw(Polygon(z['pts']).buffer(0),z['net'])
    for t in d['tracks']:
        if t['layer']==L: draw(LineString([t['a'],t['b']]).buffer(t['w']/2),t['net'])
    for v in d['vias']: draw(Point(v['at']).buffer(v['d']/2),v['net'])
    for p in d['pads']:
        if p['tht'] or L=='F.Cu': draw(Polygon(p['pts']).buffer(0),p['net'])
    for c in ((132,70.5),(132,85.5)):
        ax.add_patch(plt.Rectangle((c[0]-3.5,c[1]-3.5),7,7,fill=False,ec='k'))
    ax.set_xlim(X0,X1); ax.set_ylim(Y1,Y0); ax.set_aspect('equal'); ax.set_title(L); ax.grid(True,lw=0.3)
    ax.set_xticks(range(int(X0),int(X1)+1,5)); ax.set_yticks(range(int(Y0),int(Y1)+1,5)); ax.tick_params(labelsize=6)
fig.legend(handles=[plt.Rectangle((0,0),1,1,color=c) for c in col.values()],labels=list(col),loc='upper center',ncol=7)
plt.tight_layout(); plt.savefig(sys.argv[2],dpi=70)
