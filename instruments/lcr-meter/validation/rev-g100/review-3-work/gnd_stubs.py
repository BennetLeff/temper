"""GND return stubs for key decoupling pads: nearest GND vias and the F.Cu GND tracks at the pad (output work/gnd_stubs.txt)."""
import sys; sys.path.insert(0,'work')
from lib_board import *
b=load(); P=pads(b); T=tracks(b); TR=[t for t in T if t['kind']=='track']; V=[t for t in T if t['kind']=='via' and t['net']=='GND']
for ref,num in (('U16','2'),('C15','2'),('C17','2'),('U3','2'),('C113','2'),('R121','2'),('C81','2'),('C85','2'),('C89','2'),('C80','2'),('C82','2'),('U14','12'),('U14','13'),('C65','2'),('C66','2'),('U1','57')):
    p=next(q for q in P if q['ref']==ref and q['num']==num)
    dv=sorted((dist(p['at'],v['at']),v['at']) for v in V)[:2]
    tr=[t for t in TR if t['net']=='GND' and t['layer']=='F.Cu' and seg_dist(p['at'],t['a'],t['b'])<0.6]
    print(f"{ref}.{num} {p['net']} ({p['at'][0]:.2f},{p['at'][1]:.2f}): nearest GND vias {[(round(d,2),(round(a[0],2),round(a[1],2))) for d,a in dv]}; F.Cu GND tracks at pad: {[((round(t['a'][0],2),round(t['a'][1],2)),(round(t['b'][0],2),round(t['b'][1],2)),t['w']) for t in tr]}")
