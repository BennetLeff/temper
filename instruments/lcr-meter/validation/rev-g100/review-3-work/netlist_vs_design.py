"""Board pad nets vs design.json parts[].pins. Output work/netlist_vs_design.txt"""
import sys, json; sys.path.insert(0,'work')
from lib_board import *
b=load(); P=pads(b); d=json.load(open('cad/design.json'))
want={}
for p in d['parts']:
    for pin,net in p['pins'].items(): want[(p['ref'],pin)]=net
have={}
for p in P: have[(p['ref'],p['num'])]=p['net']
out=[]
refs_d=set(p['ref'] for p in d['parts']); refs_b=set(p['ref'] for p in P)
out.append(f"design parts {len(refs_d)}, board footprints {len(refs_b)}; only design: {sorted(refs_d-refs_b)}; only board: {sorted(refs_b-refs_d)}")
mism=0
for k,net in want.items():
    h=have.get(k)
    hn=None if (h is None or h=='' or h.startswith('unconnected')) else h
    if hn!=net:
        if h is None and net is None: continue
        out.append(f"  {k}: design {net} board {h}"); mism+=1
# board pads not in design (e.g. EP pads, shields)
extra=[(k,v) for k,v in have.items() if k not in want and v and not v.startswith('unconnected')]
out.append(f"mismatches {mism}; board pads with a net but no design pin: {len(extra)}")
for k,v in sorted(extra)[:60]: out.append(f"  {k}: {v}")
open('work/netlist_vs_design.txt','w').write('\n'.join(out)+'\n'); print('\n'.join(out))
