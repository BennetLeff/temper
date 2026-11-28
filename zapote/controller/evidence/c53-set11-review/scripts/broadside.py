from lib import *
from shapely.strtree import STRtree
AN=['p1','rtd_sense_p_ext','rtd_sense_n_ext','rtd_sense_p','rtd_sense_n','rtd_force_p','rtd_force_n','refin_n','vbias','rtd_pan.low_window-inp','rtd_sense_p_mid','rtd_sense_n_mid',
    'rtd2_sense_p_ext','rtd2_sense_n_ext','rtd2_sense_p','rtd2_sense_n','rtd2_force_p','rtd2_force_n','rtd2_refin_n','rtd2_bias','rtd2_sense_p_mid','rtd2_sense_n_mid','HS_SENSE','COIL_SENSE','RIM_SENSE','bay_node','ct_mon','vbus_p','vbus_n']
tr=B['tracks']
in3=[t for t in tr if t['layer']=='In3.Cu']; g3=[trackgeom(t) for t in in3]; tree=STRtree(g3)
in1=unary_union([p for _,_,p in zonepolys('selv_gnd','In1.Cu')])
sw=unary_union([k[2] for n in('sw_12','sw_3v3','sw_fan2') for k in netitems(n)])
ind={f['ref']:box(*f['cy']) for f in B['fps'] if f['ref'] in('L1','L2','L3')}
for n in AN:
    over=collections.defaultdict(float); L=0; dsw=99; dind={}
    for t in tr:
        if t['net']!=n: continue
        line=LineString([(t['x1'],t['y1']),(t['x2'],t['y2'])]); 
        dsw=min(dsw,line.distance(sw))
        for k,bx in ind.items():
            if line.intersects(bx): dind[(k,t['layer'])]=dind.get((k,t['layer']),0)+line.intersection(bx).length
        if t['layer']!='In2.Cu': continue
        L+=line.length
        for j in tree.query(line.buffer(0.15)):
            j=int(j)
            if in3[j]['net']==n: continue
            ol=line.intersection(g3[j].buffer(0.1)).length
            if ol>0.6: over[in3[j]['net']]+=ol   # more than a perpendicular crossing
    print('%-24s In2 len %6.1f | broadside-parallel over In3 nets (mm): %s | min plan dist to SW copper %.1f | under inductor courtyard: %s'%(n,L,{k:round(v,1) for k,v in sorted(over.items(),key=lambda x:-x[1])[:6]},dsw,{k:round(v,1) for k,v in dind.items()}))
