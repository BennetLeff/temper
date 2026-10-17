"""Build each sense loop from the stage-13b copper and compute its pickup. Writes loops_result.json."""
import json, math
import numpy as np
from loops import path, pad, flux, area, emf_mv, centroid, KS, W
from field import profiles, CASES, ComplexProfile
PM = profiles()
PF = {c: ComplexProfile(c) for c in CASES}
F, I1, I2, B = 'F.Cu', 'In1.Cu', 'In2.Cu', 'B.Cu'

def P_(net, a, la, b, lb):
    # pads with a via in the pad start on whichever layer the route leaves on; the pad itself stays on F
    for l0 in (la, B, I1, I2):
        for l1 in (lb, B, I1, I2):
            try:
                p, L = path(net, a, l0, b, l1)
            except ValueError:
                continue
            if l0 != la: p = [(a[0], a[1], la)] + p
            if l1 != lb: p = p + [(b[0], b[1], lb)]
            return p, L
    raise ValueError(net)
def pt(xy, l): return [(xy[0], xy[1], l)]

loops, meta = {}, {}
def add(name, parts, note, weight, lengths=None):
    pts = []
    for p in parts: pts += p
    # drop consecutive duplicates
    out = [pts[0]]
    for q in pts[1:]:
        if q != out[-1]: out.append(q)
    loops[name] = out; meta[name] = dict(note=note, weight=weight, lengths=lengths or {})

# ---------------- OCP Kelvin pair: R5 S2 -> KELVIN_N -> R33.2 ; R35.2 -> KELVIN_P -> R5 S1
kn, Lkn = P_('ocp_kelvin_n', pad('R5', 3), F, pad('R33', 2), F)
kp_tr, Lkp = P_('ocp_kelvin_p', pad('R5', 2), F, (107.6, 53.5), I1)      # trace part, ends where it enters the In1 KELVIN_P pour
# pour closure A: straight through the In1 pour to the via beside R35.2, up to R35.2
pourA = [(107.6, 53.5, I1), (117.225, 73.695, I1), (117.225, 73.695, F), (*pad('R35', 2), F)]
# pour closure B: return hugs KELVIN_N's own route inside the pour (pour edge beside the trace)
pourB = [(107.6, 53.5, I1), (107.6, 71.6, I1), (117.225, 71.6, I1), (117.225, 73.695, I1), (117.225, 73.695, F), (*pad('R35', 2), F)]
rev = lambda p: list(reversed(p))
for tag, pour in (('A_pour_straight', pourA), ('B_pour_hugging', pourB)):
    add('OCP_kelvin_' + tag,
        [kn, pt(pad('R33', 2), F), pt(pad('R35', 2), F), rev(pour), rev(kp_tr), pt(pad('R5', 2), F)],
        'R5.3 -> KELVIN_N (F/In1/In2/In1/F) -> R33.2 -> local ref R35.2 -> KELVIN_P pour -> KELVIN_P trace -> R5.2 -> across shunt sense pads',
        'shunt-equivalent: EMF mV == A of trip shift (OCP_NODE = 1.25 V + 0.5 V(KELVIN_N))',
        dict(kelvin_n_mm=Lkn, kelvin_p_trace_mm=Lkp))

# ---------------- comparator cluster: INP node loop and INN threshold loop, both closed through KELVIN_P at U6.2
node, _ = P_('ocp_node', pad('U6', 3), F, pad('C30', 1), F)
add('OCP_node_local',
    [node, pt(pad('C30', 2), F), [(117.225, 65.745, F), (117.225, 65.745, I1), (105.56, 57.735, I1), (105.56, 57.735, F)], pt(pad('U6', 2), F)],
    'U6.3 -> OCP_NODE trace -> C30.1|C30.2 -> KELVIN_P via -> In1 pour -> U6.2', 'INP: 1 mV = 2 A trip shift')
thr, _ = P_('ocp_thresh', pad('U6', 4), B, pad('C31', 1), F); thr = [(*pad('U6', 4), F)] + thr
add('OCP_thresh_local',
    [thr, pt(pad('C31', 2), F), [(113.075, 68.395, F), (113.075, 68.395, I1), (105.56, 57.735, I1), (105.56, 57.735, F)], pt(pad('U6', 2), F)],
    'U6.4 -> OCP_THRESH (F/B/F) -> C31.1|C31.2 -> KELVIN_P via -> In1 pour -> U6.2', 'INN: 1 mV = 2 A trip shift')
ref, _ = P_('ref25', pad('U5', 1), F, pad('R32', 1), F)
add('OCP_ref25',
    [ref, pt(pad('R32', 1), F), [(117.225, 73.695, F), (117.225, 73.695, I1), (110.729, 55.301, I1), (110.729, 55.301, F)], pt(pad('U5', 2), F)],
    'U5.1 -> REF25 (F/In2) -> R32.1/R34.1 -> KELVIN_P pour -> U5.2', 'common to INP (x0.5) and INN (x0.485): 0.015 x 2 A per mV')

# ---------------- CT detector
sm_zc, Lsm = P_('ct_sense_mon', pad('U12', 3), F, pad('R42', 2), F)
s1, _ = P_('ct_s1', pad('R42', 1), F, pad('R39', 1), F)
s2_zc, Ls2 = P_('ct_s2', pad('R39', 2), F, pad('U12', 4), F)
add('CT_ZC_cmp',
    [sm_zc, pt(pad('R42', 1), F), s1, pt(pad('R39', 2), F), s2_zc],
    'U12.3 -> CT_SENSE_MON (F/B) -> R42 -> CT_S1 -> R39 burden -> CT_S2 (B/F/B/In1) -> U12.4', 'vs 15 mV/A burden signal',
    dict(sense_mon_mm=Lsm, ct_s2_mm=Ls2))
sm_oc, _ = P_('ct_sense_mon', pad('U10', 3), F, pad('R42', 2), F)
s2_c43, _ = P_('ct_s2', pad('R39', 2), F, pad('C43', 1), F)
rhi, _ = P_('ct_ref_hi', pad('R44', 1), F, pad('U10', 4), F)
add('CT_OC_cmp',
    [sm_oc, pt(pad('R42', 1), F), s1, pt(pad('R39', 2), F), s2_c43, pt(pad('C43', 2), F),
     [(*pad('C43', 2), I2), (*pad('R44', 2), I2)], pt(pad('R44', 2), F), rhi],
    'U10.3 -> CT_SENSE_MON -> R42 -> CT_S1 -> R39 -> CT_S2 -> C43 -> SELV_GND plane (straight) -> R44 -> CT_REF_HI -> U10.4',
    'vs 15 mV/A burden signal (trip ~55 A)')
mon, Lmon = P_('ct_mon', pad('J4', 14), F, pad('R47', 2), F)
sm_mon, _ = P_('ct_sense_mon', pad('R47', 1), F, pad('R42', 2), F)
add('CT_MON_to_J4',
    [mon, pt(pad('R47', 1), F), sm_mon, pt(pad('R42', 1), F), s1, pt(pad('R39', 2), F), s2_c43, pt(pad('C43', 2), F),
     [(*pad('C43', 2), I2), (*pad('J4', 15), I2)], pt(pad('J4', 15), F)],
    'J4.14 -> CT_MON -> R47 -> CT_SENSE_MON -> R42 -> CT_S1 -> R39 -> CT_S2 -> C43 -> SELV_GND plane (straight) -> J4.15',
    'analog monitor to controller ADC, vs 15 mV/A', dict(ct_mon_mm=Lmon))
sec_s1, _ = P_('ct_s1', pad('T1', 3), F, pad('R39', 1), F)
sec_s2, _ = P_('ct_s2', pad('R39', 2), F, pad('T1', 4), F)
add('CT_secondary_burden', [sec_s1, pt(pad('R39', 2), F), sec_s2, pt(pad('T1', 4), F)],
    'T1.3 -> CT_S1 -> R39 -> CT_S2 -> T1.4 (winding closure straight)', 'series with a current source: rejected by R_b/|R_b + jwLm|')
zcd, Lzcd = P_('ct_zc', pad('U12', 1), F, pad('J4', 13), F)
add('CT_ZC_to_J4', [zcd, pt(pad('J4', 15), F), [(*pad('J4', 15), I2), (*pad('U12', 2), I2)], pt(pad('U12', 2), F)],
    'U12.1 -> CT_ZC -> J4.13 | J4.15 -> SELV_GND plane (straight) -> U12.2', 'digital push-pull 3.3 V', dict(ct_zc_mm=Lzcd))

# ---------------- LINE_ZC
seg = lambda net, a, b: P_(net, a, F, b, F)[0]
add('LINE_ZC_input',
    [pt(pad('R67', 1), F), pt(pad('R67', 2), F), seg('r1mid', pad('R67', 2), pad('R68', 1)), pt(pad('R68', 2), F),
     seg('led1', pad('R68', 2), pad('U36', 1)), pt(pad('U36', 2), F), seg('led2', pad('U36', 2), pad('R69', 1)),
     pt(pad('R69', 2), F), seg('r2mid', pad('R69', 2), pad('R70', 1)), pt(pad('R70', 2), F)],
    'L_FILT R67.1 -> R67 -> R68 -> U36 LED -> R69 -> R70 -> N_FILT R70.2 -> straight L/N closure', 'in series with 120 V / 66 k')
raw, Lraw = P_('line_zc-raw', pad('U36', 4), F, pad('U24', 2), F)
add('LINE_ZC_raw_straight', [raw, pt(pad('U24', 3), F), [(*pad('U24', 3), I2), (*pad('U36', 3), I2)], pt(pad('U36', 3), F)],
    'U36.4 -> LINE_ZC_RAW (F/B, 330 mm) -> U24.2 | U24.3 -> SELV_GND plane straight -> U36.3', 'opto output (33 k pull-up) into Schmitt buffer',
    dict(raw_mm=Lraw))
# image return: plane current flows under the trace (In2), loop = vertical strip only
img = [(x, y, I2) for (x, y, l) in reversed(raw)]
add('LINE_ZC_raw_image', [raw, img], 'LINE_ZC_RAW with return directly beneath on the In2 SELV_GND plane', 'same')
lz, Llz = P_('line_zc', pad('U24', 4), F, pad('J4', 16), F)
add('LINE_ZC_out_to_J4', [lz, pt(pad('J4', 15), F), [(*pad('J4', 15), I2), (*pad('U24', 3), I2)], pt(pad('U24', 3), F)],
    'U24.4 -> LINE_ZC -> J4.16 | J4.15 -> plane straight -> U24.3', 'digital', dict(line_zc_mm=Llz))

res = {}
C = lambda z: [round(z.real, 5), round(z.imag, 5)]
for n, lp in loops.items():
    sa, ga = area(lp)
    cx, cy = centroid(lp)
    r = {'n_pts': len(lp), 'signed_area_mm2': sa, 'abs_area_mm2': ga, 'centroid': [cx, cy], 'meta': meta[n]}
    for c in CASES:
        for src, P in (('map', PM[c]), ('fem', PF[c])):
            tot, bz, br = flux(lp, P)
            e, ez, er = emf_mv(tot), emf_mv(bz), emf_mv(br)
            r[c + '|' + src] = dict(flux_uTmm2=C(tot), emf_pk_mV=C(e), emf_abs=abs(e), emf_Bz_abs=abs(ez), emf_Br_abs=abs(er),
                                    emf_bound=abs(ez) + abs(er), at_current_peak=abs(e.real), at_zero_cross=abs(e.imag),
                                    phase_deg=float(np.degrees(np.angle(e))))
    res[n] = r
import numpy as np
json.dump(dict(scale_current=KS, f_Hz=31e3, loops=res, polylines=loops), open('loops_result.json', 'w'), indent=1)
print('EMF mV peak at %.1f A pk tank. |E| (Bz part, Br part) [bound=|Bz|+|Br|]  E at i-peak / at i-zero' % (KS * 45))
for n, r in res.items():
    print('%-26s A=%6.1f/%6.1f mm2 cent(%3.0f,%3.0f)' % (n, r['signed_area_mm2'], r['abs_area_mm2'], *r['centroid']))
    for c in CASES:
        for src in ('map', 'fem'):
            q = r[c + '|' + src]
            print('    %-6s %-3s |E| %7.3f (%6.3f, %6.3f) bound %7.3f   pk %6.3f zc %6.3f  ph %6.1f' % (
                c[:5], src, q['emf_abs'], q['emf_Bz_abs'], q['emf_Br_abs'], q['emf_bound'], q['at_current_peak'], q['at_zero_cross'], q['phase_deg']))
