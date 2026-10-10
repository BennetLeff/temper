"""OCP: combine the Kelvin, OCP_NODE and OCP_THRESH loop EMFs into an equivalent shunt-current
trip shift, with phase; add image-return variants for the comparator-cluster traces and a
section breakdown of the Kelvin loop."""
import json, math, numpy as np
from loops import flux, emf_mv, KS
from field import CASES, ComplexProfile
R = json.load(open('loops_result.json'))
PL = R['polylines']
PF = {c: ComplexProfile(c) for c in CASES}
E = lambda name, c: complex(*R['loops'][name][c + '|fem']['emf_pk_mV'])
def Eloop(lp, c): return emf_mv(flux([tuple(p) for p in lp], PF[c])[0])

# image-return variants: trace path then the same xy path back on the In1 KELVIN_P pour (directly beneath)
def image(name, n_trace):
    lp = [tuple(p) for p in PL[name]][:n_trace]
    return lp + [(x, y, 'In1.Cu') for (x, y, l) in reversed(lp)]
# number of points that belong to the signal trace (up to and including the C30.1 / C31.1 pad)
def upto(name, xy):
    lp = PL[name]
    i = min(range(len(lp)), key=lambda k: math.dist(lp[k][:2], xy)); return i + 1
from loops import pad
out = {}
for c in CASES:
    Ek = {'A': E('OCP_kelvin_A_pour_straight', c), 'B': E('OCP_kelvin_B_pour_hugging', c)}
    En = {'drawn': E('OCP_node_local', c), 'image': Eloop(image('OCP_node_local', upto('OCP_node_local', pad('C30', 1))), c)}
    Et = {'drawn': E('OCP_thresh_local', c), 'image': Eloop(image('OCP_thresh_local', upto('OCP_thresh_local', pad('C31', 1))), c)}
    Er = E('OCP_ref25', c)
    rows = {}
    for kk in Ek:
        for cl in En:
            dI = 1.03 * Ek[kk] - 2 * En[cl] + 2 * Et[cl] + 0.03 * Er
            mag = abs(1.03 * Ek[kk]) + abs(2 * En[cl]) + abs(2 * Et[cl]) + abs(0.03 * Er)
            rows[f'kelvin_{kk}|cluster_{cl}'] = dict(dI_phasor_A=[dI.real, dI.imag], dI_abs_A=abs(dI), dI_at_current_peak_A=abs(dI.real),
                                                     dI_mag_sum_bound_A=mag,
                                                     parts_abs_A=dict(kelvin=abs(1.03 * Ek[kk]), node=abs(2 * En[cl]), thresh=abs(2 * Et[cl]), ref25=abs(0.03 * Er)))
    out[c] = rows
    print(c)
    for k, v in rows.items():
        print('  %-28s |dI| %5.2f A  at i-peak %5.2f A  bound %5.2f A   parts %s' % (k, v['dI_abs_A'], v['dI_at_current_peak_A'], v['dI_mag_sum_bound_A'],
              {a: round(b, 2) for a, b in v['parts_abs_A'].items()}))

# Kelvin section breakdown (pan & no-pan): close the pair across itself at two cuts
lp = [tuple(p) for p in PL['OCP_kelvin_A_pour_straight']]
def idx(xy, net_side):
    return min(range(len(lp)), key=lambda k: math.dist(lp[k][:2], xy) if (lp[k][0] < 41.75) == net_side or True else 1e9)
# cuts: kn (41.3, 20) / kp (42.2, 20) after the R5 breakout; kn (106.6, 43.4) / kp (107.6, 42.6) at the cluster entry
def nearest(xy, layer=None):
    return min(range(len(lp)), key=lambda k: math.dist(lp[k][:2], xy))
n_kn = len([p for p in lp])  # whole loop
def sub(i0, i1, j0, j1):
    """sub-loop: lp[i0..i1] (kn side, forward) + lp[j0..j1] (kp side, forward) closed by straight cuts."""
    return lp[i0:i1 + 1] + lp[j0:j1 + 1]
# indices along the listed loop: kn path first (R5.3 -> R33.2) then closure then kp reversed (cluster -> R5.2)
kn_end = nearest((119.95, 71.05))
cut1_kn = max(i for i in range(kn_end) if lp[i][0] == 41.3 and lp[i][1] <= 31.8)   # end of the first In1 run on kn
cut2_kn = max(i for i in range(kn_end) if abs(lp[i][0] - 106.6) < 1e-6 and abs(lp[i][1] - 43.4) < 1e-6)
kp_from = kn_end + 1
cut2_kp = min(i for i in range(kp_from, len(lp)) if abs(lp[i][0] - 107.6) < 1e-6 and abs(lp[i][1] - 42.6) < 1e-6)
cut1_kp = min(i for i in range(kp_from, len(lp)) if abs(lp[i][0] - 42.2) < 1e-6 and lp[i][1] <= 30.8)
secs = {'R5 breakout (R5 pads to y~31)': lp[:cut1_kn + 1] + lp[cut1_kp:],
        'pair run (y 31 -> x 107)': lp[cut1_kn:cut2_kn + 1] + lp[cut2_kp:cut1_kp + 1],
        'cluster end (pour closure A)': lp[cut2_kn:cut2_kp + 1]}
br = {}
for c in CASES:
    tot = Eloop(lp, c)
    br[c] = {}
    for k, s in secs.items():
        e = Eloop(s, c)
        br[c][k] = dict(emf_abs_mV=abs(e), area_mm2=abs(sum(s[i - 1][0] * s[i][1] - s[i][0] * s[i - 1][1] for i in range(len(s))) / 2))
    print(c, 'kelvin total %.3f mV; sections:' % abs(tot), {k: (round(v['emf_abs_mV'], 3), round(v['area_mm2'], 1)) for k, v in br[c].items()})
json.dump(dict(combos=out, kelvin_sections=br), open('ocp_combine.json', 'w'), indent=1)
