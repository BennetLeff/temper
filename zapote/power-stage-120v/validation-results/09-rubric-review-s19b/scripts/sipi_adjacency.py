#!/usr/bin/env python3
"""usage: sipi_adjacency.py copper.json.gz -> sw_a/sw_b vs victim nets: same-layer min distance (<10 mm), adjacent-layer overlap area"""
import gzip,json,sys,collections
from shapely.geometry import Polygon,LineString
from shapely.ops import unary_union
G=collections.defaultdict(list)
for p in json.load(gzip.open(sys.argv[1]))['primitives']:
    k=p['kind']
    if k=='track': g=LineString([p['start'],p['end']]).buffer(p['width_mm']/2)
    elif k in('zone','pad'): g=Polygon(p['shell'],p.get('holes') or []).buffer(0)
    else: continue
    G[(p['net'],p['layer'])].append(g)
U={k:unary_union(v) for k,v in G.items()}
O=['F.Cu','In1.Cu','In2.Cu','B.Cu']
for v in ['ocp_node','ocp_thresh','ocp_kelvin_p','ocp_kelvin_n','bus_fault_hot','ct_zc','ct_mon','pwm_ha','pwm_la','pwm_hb','pwm_lb','permit','bus_fault','line_zc','ocp_ok_hot']:
    for a in ['sw_a','sw_b']:
        row=[]
        for lv in O:
            for la in O:
                gv,ga=U.get((v,lv)),U.get((a,la))
                if gv is None or ga is None: continue
                if lv==la:
                    d=gv.distance(ga)
                    if d<10: row.append(f'same {lv}: {d:.2f}mm')
                else:
                    i=gv.intersection(ga).area
                    if i>0.01: row.append(f'{lv}/{la} overlap {i:.1f}mm2')
        if row: print(v,a,'|','; '.join(row))
