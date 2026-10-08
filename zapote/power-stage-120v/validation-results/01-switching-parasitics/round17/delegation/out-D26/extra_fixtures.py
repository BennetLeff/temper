"""UVLO, DIS both directions, and overlapping-input fixtures."""
from __future__ import annotations
from run import HERE, control, cross, dump, execute, ns_delta

rows=[]
for corner in [-1,0,1]:
    for what in ['dis','vcc','vdd','overlap']:
        if what=='dis':
            cc='3.3';dd='12';dis='PWL(0 0 1u 0 1.001u 3.3 2u 3.3 2.001u 0)';a='3.3';b='0';stop=4e-6;step='0.1n'
        elif what=='vcc':
            cc='PWL(0 3.3 1u 3.3 1.001u 2 12u 2 12.001u 3.3)';dd='12';dis='0';a='3.3';b='0';stop=100e-6;step='10n'
        elif what=='vdd':
            cc='3.3';dd='PWL(0 12 1u 12 1.001u 7 6u 7 6.001u 12)';dis='0';a='3.3';b='0';stop=25e-6;step='1n'
        else:
            cc='3.3';dd='12';dis='0';a='3.3';b='PULSE(0 3.3 1u 1n 1n 500n 4u)';stop=3e-6;step='0.1n'
        text=f'''* supplemental {what} CORNER={corner}
.include ucc21550_parametric.lib
Vcc vc 0 {cc}
Vdd vd 0 {dd}
Va a 0 {a}
Vb b 0 {b}
Vdis dis 0 {dis}
XU a b dis vc 0 vd 0 oa vd 0 ob UCC21550 CORNER={corner} RDT=50000 RTOL=0
Ca oa 0 1f
Cb ob 0 1f
.tran {step} {stop}
'''+control('v(vc) v(vd) v(dis) v(a) v(b) v(oa) v(ob)')
        status,w=execute(f'extra-{what}-{corner}',text,stop)
        row=dict(status,what=what,corner=corner)
        if status['status']=='COMPLETED' and w is not None:
            t,vc,vd,dis,a,b,oa,ob=w.T
            # VDD falling carries the rail itself below10.8V before UVLO.
            # Measure output ratio to contemporaneous VDD, not absolute12V.
            out=oa/vd if what=='vdd' else oa/12
            row['output_fall_s']=cross(t,out,0.9,False)
            row['output_rise_s']=cross(t,out,0.1,True,1e-6)
            source={'dis':dis,'vcc':vc,'vdd':vd,'overlap':b}[what]
            fallthr={'dis':2,'vcc':2.5,'vdd':7.9,'overlap':2}[what]
            risethr={'dis':1,'vcc':2.7,'vdd':8.5,'overlap':1}[what]
            row['disable_ns']=ns_delta(row['output_fall_s'],cross(t,source,fallthr,what in ['dis','overlap']))
            row['reenable_ns']=ns_delta(row['output_rise_s'],cross(t,source,risethr,what in ['vcc','vdd'],1.1e-6))
            row['other_output_peak_V']=float(ob.max())
        rows.append(row)
        dump(HERE/'extra-fixtures.json',rows)
        print(row,flush=True)
