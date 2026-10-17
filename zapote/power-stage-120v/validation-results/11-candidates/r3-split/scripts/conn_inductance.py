#!/usr/bin/env python3 -I
"""Loop inductance added to a gate / sense loop by a board-to-board connector, computed (no vendor data found).
Method: partial inductances of straight rectangular pins (Rosa/Grover): self L = mu0*l/(2pi)*[ln(2l/(w+t)) + 0.5 + 0.2235*(w+t)/l],
mutual of two parallel equal filaments M = mu0*l/(2pi)*[asinh(l/d) - sqrt(1+(d/l)^2) + d/l]. Pins in a row at pitch p alternate
signal(+)/return(-); equal current sharing: L_loop = sum_ij a_i a_j L_ij with a_i = +-1/n. Adds vias (Johnson L=5.08 h [ln(4h/d)+1] nH,
h,d in inch, the pair treated with the same mutual formula) and a 2D stub allowance for the PCB breakout on each board.
    python3 -I conn_inductance.py -> ../results/conn_inductance.json"""
import json, math, sys
sys.dont_write_bytecode = True
from pathlib import Path
MU0 = 4e-7*math.pi
def Lself(l, w, t):
    return MU0*l/(2*math.pi)*(math.log(2*l/(w+t)) + 0.5 + 0.2235*(w+t)/l)
def M(l, d):
    return MU0*l/(2*math.pi)*(math.asinh(l/d) - math.sqrt(1+(d/l)**2) + d/l)
def loop(l, w, t, positions, signs):
    """positions: x (m) of pins in a row; signs +1 (signal) / -1 (return); equal sharing"""
    nS = sum(1 for s in signs if s > 0); nR = len(signs)-nS
    a = [s/(nS if s > 0 else nR) for s in signs]
    tot = 0.0
    for i in range(len(a)):
        for j in range(len(a)):
            Lij = Lself(l, w, t) if i == j else M(l, abs(positions[i]-positions[j]))
            tot += a[i]*a[j]*Lij
    return tot
def row(n_pairs, pitch):          # S R S R ...
    pos = [k*pitch for k in range(2*n_pairs)]; sg = [1 if k % 2 == 0 else -1 for k in range(2*n_pairs)]
    return pos, sg
def via_pair(h_mm, d_mm, pitch_mm):
    h = h_mm/25.4; d = d_mm/25.4
    Lv = 5.08*h*(math.log(4*h/d)+1)*1e-9
    return 2*(Lv - M(h_mm*1e-3, pitch_mm*1e-3))     # one signal + one return via, mutual subtracts
# connector classes: (name, pitch_mm, pin w, pin t (mm), mated current-path length l (mm))
CONN = [("2.54 mm square-pin header/socket (0.64 sq), mated path 9 mm", 2.54, 0.64, 0.64, 9.0),
        ("2.00 mm header (0.5 sq), 7 mm", 2.00, 0.50, 0.50, 7.0),
        ("1.27 mm header (0.4 sq), 6 mm", 1.27, 0.40, 0.40, 6.0),
        ("0.8 mm edge-rate class (contact 0.3x0.5), 5.97 mm stack", 0.80, 0.30, 0.50, 5.97)]
out = {"method": __doc__.strip().split("\n")[0], "rows": []}
STUB_NH_PER_10MM = 2.5     # 1 mm strip over a plane at 0.2 mm: mu0*h/w = 0.25 nH/mm (computed in the note below)
out["stub_nH_per_mm_strip_1mm_over_0p2mm_plane"] = MU0*0.2e-3/1e-3*1e9*1e-3*1e3 if False else round(MU0*0.2e-3/1e-3*1e-3*1e9, 3)
for name, p, w, t, l in CONN:
    for n in (1, 2, 3, 4):
        pos, sg = row(n, p*1e-3)
        Lc = loop(l*1e-3, w*1e-3, t*1e-3, pos, sg)*1e9
        Lv = via_pair(1.6, 0.3, p)*1e9/ n              # each pin has its own via pair, in parallel
        stub = 2*(10.0*out["stub_nH_per_mm_strip_1mm_over_0p2mm_plane"])/n   # 10 mm of breakout on each board, in parallel
        out["rows"].append(dict(connector=name, pairs=n, loop_conn_nH=round(Lc, 2), vias_nH=round(Lv, 2), stubs_nH=round(stub, 2),
                                total_added_nH=round(Lc+Lv+stub, 2)))
json.dump(out, open(Path(__file__).resolve().parent.parent/"results/conn_inductance.json", "w"), indent=1)
for r in out["rows"]: print(r)
