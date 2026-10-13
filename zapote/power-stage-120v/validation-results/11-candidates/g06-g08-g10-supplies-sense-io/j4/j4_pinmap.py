"""F11: J4 (Molex 0430451612, Micro-Fit 3.0 2x8, 3.0 mm pitch, rows 3.0 mm apart) pin re-assignment.
Rerun: python3 -I j4_pinmap.py   (stdlib only, seeded; writes result.json)

HEURISTIC, not a field solve: it ranks pin maps by (1) aggressor->victim coupling proxy sum(w_v / (d/3mm)^2) between
every fast edge (the four PWM lines) and every victim, and (2) a return-loop proxy sum(w_s * d_nearest_return/3mm)
where a return is any GND pin (V3V3 counts at half weight: it is decoupled on both boards).  Pin n sits opposite pin n+8.
The CURRENT map is read from elec/src/power_stage_120v.ato lines 668-684.  Two cases:
  A  PS1 stays (V15 pin kept, 3 GND)         B  PS1 deleted (proposal P1: V15 pin becomes a 4th GND)
Validation: the optimiser must rank the current map worse than its own best map, and a map with all PWMs
packed in one row with no GND must score worse than the current one (control)."""
import itertools, json, math, os, random
HERE = os.path.dirname(os.path.abspath(__file__))
CUR = {1: 'V15', 2: 'GND', 3: 'V3V3', 4: 'GND', 5: 'PWM_HA', 6: 'PWM_LA', 7: 'PWM_HB', 8: 'PWM_LB',
       9: 'PERMIT', 10: 'BUS_FAULT', 11: 'VBUS_P', 12: 'VBUS_N', 13: 'CT_ZC', 14: 'CT_MON', 15: 'GND', 16: 'LINE_ZC'}
XY = {n: (((n - 1) % 8) * 3.0, 0.0 if n <= 8 else 3.0) for n in range(1, 17)}
AGG = ['PWM_HA', 'PWM_LA', 'PWM_HB', 'PWM_LB']
# victim sensitivity weights (analog differential and the CT chain highest; digital outputs low)
VW = {'VBUS_P': 1.0, 'VBUS_N': 1.0, 'CT_MON': 1.0, 'CT_ZC': 0.5, 'LINE_ZC': 0.3, 'PERMIT': 0.3, 'BUS_FAULT': 0.2,
      'V15': 0.0, 'V3V3': 0.0}
LOOPW = {'PWM_HA': 1, 'PWM_LA': 1, 'PWM_HB': 1, 'PWM_LB': 1, 'VBUS_P': 1, 'VBUS_N': 1, 'CT_MON': 1, 'CT_ZC': 0.5,
         'LINE_ZC': 0.3, 'PERMIT': 0.3, 'BUS_FAULT': 0.2}
def d(a, b): return math.dist(XY[a], XY[b]) / 3.0

def cost(m, detail=False):
    pins = {v: [] for v in set(m.values())}
    for n, s in m.items(): pins[s].append(n)
    xt = 0.0
    for a in AGG:
        pa = pins[a][0]
        for v, w in VW.items():
            if v in pins and v != a and w:
                xt += w / d(pa, pins[v][0]) ** 2
    loop = 0.0
    rets = [(n, 1.0) for n in pins['GND']] + [(n, 0.5) for n in pins['V3V3']]
    for s, w in LOOPW.items():
        p = pins[s][0]
        loop += w * min(d(p, r) / k for r, k in rets)
    # differential pair penalty: VBUS_P and VBUS_N must be adjacent in a row
    pair = 0.0 if abs(pins['VBUS_P'][0] - pins['VBUS_N'][0]) == 1 and (pins['VBUS_P'][0] - 1) // 8 == (pins['VBUS_N'][0] - 1) // 8 else 5.0
    tot = xt + 2.0 * loop + pair
    return (tot, xt, loop, pair) if detail else tot

def anneal(sigs, seed, iters=60000):
    rnd = random.Random(seed)
    cur = dict(zip(range(1, 17), rnd.sample(sigs, 16)))
    c = cost(cur); best, bc = dict(cur), c
    for i in range(iters):
        t = 2.0 * (1 - i / iters) + 0.01
        a, b = rnd.sample(range(1, 17), 2)
        cur[a], cur[b] = cur[b], cur[a]
        c2 = cost(cur)
        if c2 < c or rnd.random() < math.exp((c - c2) / t): c = c2
        else: cur[a], cur[b] = cur[b], cur[a]
        if c < bc: best, bc = dict(cur), c
    return best, bc

def run(label, sigs):
    best, bc = min((anneal(sigs, s) for s in range(12)), key=lambda x: x[1])
    return best, bc

if __name__ == '__main__':
    sigA = list(CUR.values())                                   # case A: same multiset as today
    sigB = [('GND' if s == 'V15' else s) for s in sigA]         # case B: V15 pin becomes GND
    out = {}
    cur_c = cost(CUR, True)
    ctrl = {1: 'PWM_HA', 2: 'PWM_LA', 3: 'PWM_HB', 4: 'PWM_LB', 5: 'GND', 6: 'GND', 7: 'GND', 8: 'V15', 9: 'CT_MON', 10: 'CT_ZC',
            11: 'VBUS_P', 12: 'VBUS_N', 13: 'LINE_ZC', 14: 'PERMIT', 15: 'BUS_FAULT', 16: 'V3V3'}
    out['current'] = dict(map=CUR, cost=cur_c)
    out['control_pwm_packed_over_victims'] = dict(map=ctrl, cost=cost(ctrl, True))
    for lab, sigs in (('A_PS1_kept', sigA), ('B_PS1_deleted', sigB)):
        best, bc = run(lab, sigs)
        out[lab] = dict(map=best, cost=cost(best, True))
    here = os.path.join(HERE, 'result.json'); json.dump(out, open(here, 'w'), indent=1)
    print('cost = (total, crosstalk, loop, pair)')
    for k, v in out.items():
        print('%-34s %s' % (k, tuple(round(x, 2) for x in v['cost'])))
        for r in (range(1, 9), range(9, 17)):
            print('    ' + ' '.join('%2d:%-9s' % (n, v['map'][n]) for n in r))
    ok = out['current']['cost'][0] > out['A_PS1_kept']['cost'][0] and out['control_pwm_packed_over_victims']['cost'][0] > out['current']['cost'][0]
    print('CONTROLS', 'OK' if ok else 'BROKEN')
