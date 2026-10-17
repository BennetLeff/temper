#!/usr/bin/env python3
"""usage: sipi_lengths.py copper.json.gz  -> track length per net"""
import gzip,json,sys,math,collections
L=collections.defaultdict(float)
for p in json.load(gzip.open(sys.argv[1]))['primitives']:
    if p['kind']=='track': L[p['net']]+=math.dist(p['start'],p['end'])
for n in ['pwm_ha','pwm_la','pwm_hb','pwm_lb','permit','bias_bad','ct_zc','bus_fault_hot','line_zc','ocp_kelvin_p','ocp_kelvin_n']: print(n,round(L[n],1),'mm')
