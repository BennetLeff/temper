"""F8: OCP Kelvin / comparator-cluster pickup at 59.2 A pk and 35/45/60 kHz. Stage 21b copy (DECISIONS 26) of
11-candidates/g06-g08-g10-supplies-sense-io/f8-pickup: copper from F8_COPPER (default native21s21b-all-copper), and the
KELVIN_P vias beside C30.2 / C31.2 / U6.2 are taken from the copper (nearest ocp_kelvin_p via) instead of the 19c
coordinates, so the as-built rows (base_*) describe the stage-21b board.
Rerun: python3 -I run_ocp.py   (needs field_phase_<kHz>.json beside it; writes result.json)

Loops are the same as 02-protection-timing/coil-pickup/run_loops.py (OCP part); pads and tracks come from the
19c copper.  Variants:
  base_A / base_B   Kelvin loop with the pour closure straight (A) or hugging KELVIN_N (B), cluster as drawn
  move_KN_under_KP  RESOLUTION-PLAN F8 step 3: from the pour-entry height KELVIN_N runs on In2 directly under the
                    In1 KELVIN_P pour line to the R33/R35 end (pour return = its image on In1)
  move + caps       the same plus C30 / C31 placed on U6.3 / U6.4 (node and threshold loops -> image returns)
Control: 31 kHz, 31.1 A pk reproduces the 13b report on the 19c copper (BASE_13B table below)."""
import json, math, os, sys
import numpy as np
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from loops import path, pad, flux, area, emf_mv, BOARD_SHA
from field import ComplexProfile, CASES
F, I1, I2, B = 'F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu'

def P_(net, a, la, b, lb):
    for l0 in (la, F, B, I1, I2):         # F added (stage 22: ocp_thresh re-routed all on F.Cu from U6.4 to C31.1)
        for l1 in (lb, F, B, I1, I2):
            try:
                p, L = path(net, a, l0, b, l1)
            except ValueError:
                continue
            if l0 != la: p = [(a[0], a[1], la)] + p
            if l1 != lb: p = p + [(b[0], b[1], lb)]
            return p, L
    raise ValueError(net)
pt = lambda xy, l: [(xy[0], xy[1], l)]
rev = lambda p: list(reversed(p))

def clean(parts):
    pts = []
    for p in parts: pts += p
    out = [pts[0]]
    for q in pts[1:]:
        if q != out[-1]: out.append(q)
    return out

# ---------------- loop construction (19c)
kn, Lkn = P_('ocp_kelvin_n', pad('R5', 3), F, pad('R33', 2), F)
kp_tr, Lkp = P_('ocp_kelvin_p', pad('R5', 2), F, (107.6, 53.5), I1)
ENTRY = (107.6, 53.5)
VIA_R35 = (117.225, 73.695)
pourA = [(*ENTRY, I1), (*VIA_R35, I1), (*VIA_R35, F), (*pad('R35', 2), F)]
pourB = [(*ENTRY, I1), (107.6, 71.6, I1), (VIA_R35[0], 71.6, I1), (*VIA_R35, I1), (*VIA_R35, F), (*pad('R35', 2), F)]
LOOPS = {}
for tag, pour in (('A', pourA), ('B', pourB)):
    LOOPS['kelvin_' + tag] = clean([kn, pt(pad('R33', 2), F), pt(pad('R35', 2), F), rev(pour), rev(kp_tr), pt(pad('R5', 2), F)])

# move: KELVIN_N follows the pair to the pour-entry height (x=106.6, y=53.5) then runs on In2 straight under the
# In1 pour line ENTRY -> VIA_R35 (offset 1 mm in x so it needs its own via), up to F, to R33.2; pour return is the
# image of that In2 run, so the long hook closes on itself.
i_cut = max(i for i, p in enumerate(kn) if abs(p[0] - 106.6) < 1e-6 and abs(p[1] - 43.4) < 1e-6)
kn_pair = kn[:i_cut + 1]                                   # ... up to (106.6, 43.4, In1)
VIA_KN = (VIA_R35[0] + 1.0, VIA_R35[1] - 0.6)
kn_move = kn_pair + [(106.6, 53.5, I1), (106.6, 53.5, I2), (*VIA_KN, I2), (*VIA_KN, F), (*pad('R33', 2), F)]
pourM = [(*ENTRY, I1), (*VIA_R35, I1), (*VIA_R35, F), (*pad('R35', 2), F)]
# the pour return follows the In2 run: path ENTRY -> VIA_R35 on In1 is parallel (within ~1 mm) to the In2 run
LOOPS['kelvin_move'] = clean([kn_move, pt(pad('R33', 2), F), pt(pad('R35', 2), F), rev(pourM), rev(kp_tr), pt(pad('R5', 2), F)])

node, _ = P_('ocp_node', pad('U6', 3), F, pad('C30', 1), F)
from loops import _raw as _RAW
def _near_kp_via(xy):
    vs = [tuple(p["centre"]) for p in _RAW["primitives"] if p["kind"] == "via" and p["net"] == "ocp_kelvin_p"]
    return min(vs, key=lambda v: math.dist(v, xy))
VIA_C30 = _near_kp_via(pad('C30', 2))      # KELVIN_P via beside C30.2, from the copper
VIA_C31 = _near_kp_via(pad('C31', 2))
VIA_U6 = _near_kp_via(pad('U6', 2))
print("vias: C30", VIA_C30, "C31", VIA_C31, "U6", VIA_U6)
LOOPS['node_drawn'] = clean([node, pt(pad('C30', 2), F), [(*VIA_C30, F), (*VIA_C30, I1), (*VIA_U6, I1), (*VIA_U6, F)], pt(pad('U6', 2), F)])
thr, _ = P_('ocp_thresh', pad('U6', 4), B, pad('C31', 1), F); thr = [(*pad('U6', 4), F)] + thr
LOOPS['thresh_drawn'] = clean([thr, pt(pad('C31', 2), F), [(*VIA_C31, F), (*VIA_C31, I1), (*VIA_U6, I1), (*VIA_U6, F)], pt(pad('U6', 2), F)])
ref, _ = P_('ref25', pad('U5', 1), F, pad('R32', 1), F)
LOOPS['ref25'] = clean([ref, pt(pad('R32', 1), F), [(117.225, 73.695, F), (117.225, 73.695, I1), (110.729, 55.301, I1), (110.729, 55.301, F)], pt(pad('U5', 2), F)])
# image-return variants: trace out to C30.1 / C31.1, return directly beneath on In1
def image(lp, xy):
    i = min(range(len(lp)), key=lambda k: math.dist(lp[k][:2], xy)) + 1
    t = lp[:i]
    return t + [(x, y, I1) for (x, y, l) in reversed(t)]
LOOPS['node_image'] = image(LOOPS['node_drawn'], pad('C30', 1))
LOOPS['thresh_image'] = image(LOOPS['thresh_drawn'], pad('C31', 1))
# caps at the pins: C30 beside U6.3 / U6.2 (< 2 mm), C31 beside U6.4 / U6.2: node/thresh loop = short image strip
LOOPS['node_at_pin'] = [(*pad('U6', 3), F), (pad('U6', 3)[0] - 1.5, pad('U6', 3)[1], F), (pad('U6', 3)[0] - 1.5, pad('U6', 2)[1], F), (*pad('U6', 2), F)]
LOOPS['thresh_at_pin'] = [(*pad('U6', 4), F), (pad('U6', 4)[0] - 1.5, pad('U6', 4)[1], F), (pad('U6', 4)[0] - 1.5, pad('U6', 2)[1], F), (*pad('U6', 2), F)]

VARIANTS = {   # name -> (kelvin loop, node loop, thresh loop)
    'base_A|cluster_drawn': ('kelvin_A', 'node_drawn', 'thresh_drawn'),
    'base_B|cluster_image': ('kelvin_B', 'node_image', 'thresh_image'),
    'move|cluster_drawn': ('kelvin_move', 'node_drawn', 'thresh_drawn'),
    'move|cluster_image': ('kelvin_move', 'node_image', 'thresh_image'),
    'move|caps_at_pins': ('kelvin_move', 'node_at_pin', 'thresh_at_pin'),
    # conservative: only the 13b report's -56 % on the base-A Kelvin EMF, not this script's idealised closure
    'move56|cluster_drawn': ('kelvin_A*0.44', 'node_drawn', 'thresh_drawn'),
    'move56|cluster_image': ('kelvin_A*0.44', 'node_image', 'thresh_image'),
    'move56|caps_at_pins': ('kelvin_A*0.44', 'node_at_pin', 'thresh_at_pin'),
}
KEL = 1.03    # A per mV: kelvin/ README -1.03 A/mV at R35.2, same factor as the 13b report
LOW, REQ_FLOOR = 67.72, 59.17  # band low edge and the 28 A tank peak floor (RESOLUTION-PLAN F8)
IPK_TANK = 59.2

def run(f_khz, ipk, label):
    out = {}
    for c in CASES:
        P = ComplexProfile(c, f_khz)
        E = {}
        for n, lp in LOOPS.items():
            E[n] = emf_mv(flux(lp, P)[0], f_khz * 1e3, ipk)
        areas = {n: area(lp)[1] for n, lp in LOOPS.items()}
        for v, (k, nd, th) in VARIANTS.items():
            ek = E[k] if '*' not in k else E[k.split('*')[0]] * float(k.split('*')[1])
            dI = KEL * ek - 2 * E[nd] + 2 * E[th] + 0.03 * E['ref25']
            parts = dict(kelvin=abs(KEL * ek), node=abs(2 * E[nd]), thresh=abs(2 * E[th]), ref25=abs(0.03 * E['ref25']))
            mag = sum(parts.values())
            # time-domain peak shift of the apparent current for the phasor dI; tank current Ipk cos(th)
            th_ = np.linspace(0, 2 * np.pi, 7201)
            def pk(d): return (np.abs(ipk * np.cos(th_)) + np.real(d * np.exp(1j * th_))).max() - ipk
            out[f'{label}|{c}|{v}'] = dict(
                f_khz=f_khz, ipk=ipk, case=c, variant=v,
                dI_abs_A=abs(dI), dI_peak_shift_A=pk(dI), dI_peak_shift_x1p5_A=pk(1.5 * dI),
                stack_mag_A=mag, stack_any_phase_x1p5_A=1.5 * mag, parts_A={a: round(b, 3) for a, b in parts.items()},
                kelvin_area_mm2=round(areas[k.split('*')[0]], 1))
    return out

if __name__ == '__main__':
    res = {'board_sha256': BOARD_SHA, 'rows': {}}
    # control: 31 kHz, 22 A rms = 31.1 A pk (as the 13b report)
    res['rows'].update(run(31, 22 * math.sqrt(2), 'control31'))
    for f in (35, 45, 60):
        res['rows'].update(run(f, IPK_TANK, f'f{f}'))
    json.dump(res, open('result.json', 'w'), indent=1)
    print('board sha', BOARD_SHA[:16])
    for k, r in res['rows'].items():
        print('%-9s %-5s %-22s |dI| %5.2f  pkshift %5.2f  (x1.5 %5.2f)  stack %5.2f -> any-phase x1.5 %5.2f A  %s' % (
            k.split('|')[0], r['case'][:5], r['variant'], r['dI_abs_A'], r['dI_peak_shift_A'], r['dI_peak_shift_x1p5_A'],
            r['stack_mag_A'], r['stack_any_phase_x1p5_A'], r['parts_A']))
