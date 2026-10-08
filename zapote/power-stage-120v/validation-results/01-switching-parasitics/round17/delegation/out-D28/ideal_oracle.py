"""Independent ideal-SPICE oracle for the Rust exact series-RLC solution."""
from __future__ import annotations
import csv
import json
from pathlib import Path
import subprocess
HERE=Path(__file__).resolve().parent
rows=list(csv.DictReader((HERE/'ideal.csv').open()))
results=[]
for resistance in (2,100):
    for phase in (30,90,180):
        folder=HERE/'ideal-oracle-v2'/f'r{resistance}-p{phase}'
        folder.mkdir(parents=True,exist_ok=True)
        text=f'''* D28 ideal differential bridge; independent ngspice RLC oracle.
.param F=50000 T1=2u P={phase} R={resistance}
Va a 0 PULSE(0 170 {{T1}} 1p 1p {{0.5/F-1p}} {{1/F}})
Vb b 0 PULSE(0 170 {{T1+P/360/F}} 1p 1p {{0.5/F-1p}} {{1/F}})
R a n1 {{R}}
L n1 n2 70u
C n2 b 0.54u
.options method=trap reltol=1e-7 abstol=1e-12
.tran 2n {{T1+100/F}} {{T1+98/F}} 2n
.meas tran ia FIND i(L) AT={{T1+99/F}}
.meas tran ib FIND i(L) AT={{T1+99/F+P/360/F}}
.meas tran irms RMS i(L) FROM={{T1+99/F}} TO={{T1+100/F}}
.end
'''
        (folder/'ideal.cir').write_text(text)
        proc=subprocess.run(['/opt/homebrew/bin/ngspice','-b','ideal.cir'],cwd=folder,capture_output=True,text=True,timeout=90,check=False)
        (folder/'run.txt').write_text(proc.stdout+proc.stderr)
        assert proc.returncode==0 and 'aborted' not in proc.stdout.lower()
        values={line.split()[0]:float(line.split()[2]) for line in proc.stdout.splitlines() if line.startswith(('ia ','ib ','irms '))}
        expected=next(r for r in rows if r['bus_V']=='170' and r['R_ohm']==str(resistance) and r['phase_deg']==str(phase))
        results.append(dict(resistance=resistance,phase=phase,spice=values,rust=expected))
(HERE/'ideal-oracle-v2.json').write_text(json.dumps(results,indent=2)+'\n')

with (HERE/"ideal-oracle-v2.csv").open("w") as stream:
    writer=csv.writer(stream,lineterminator="\n")
    writer.writerow(["R","phase","ia","ib","irms"])
    for row in results:
        writer.writerow([row["resistance"],row["phase"],*[row["spice"][key] for key in ("ia","ib","irms")]])
