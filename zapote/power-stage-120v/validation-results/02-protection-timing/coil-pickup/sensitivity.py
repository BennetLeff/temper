"""Protection error vs the requirement, with the field's +/-50 % and phase, at 31.1 A pk tank.
Nuisance (low-corner) check: apparent shunt current = |i_tank| + dI(t), dI in the phase the FEM gives
(and, as a bound, any phase).  The EMF is not rectified by the bridge, so it adds at one of the
two current peaks each cycle."""
import json, math, numpy as np
from field import CASES
C = json.load(open('ocp_combine.json'))['combos']
L = json.load(open('loops_result.json'))['loops']
IPK = 22 * math.sqrt(2)
LOW, REQ = 47.32, 44.0
th = np.linspace(0, 2 * np.pi, 7201)
def peak_shift(dI):          # dI phasor (A), tank current Ipk cos(th)
    app = np.abs(IPK * np.cos(th)) + np.real(dI * np.exp(1j * th))
    return app.max() - IPK
out = {}
print('OCP low corner %.2f A, requirement %.1f A, static margin %.2f A' % (LOW, REQ, LOW - REQ))
for c in CASES:
    for combo in ('kelvin_A|cluster_drawn', 'kelvin_B|cluster_image'):
        v = C[c][combo]; dI = complex(*v['dI_phasor_A'])
        ph = np.angle(dI)
        for k in (0.5, 1.0, 1.5):
            s_model = peak_shift(k * dI)
            s_bound_fem_phase = peak_shift(k * v['dI_mag_sum_bound_A'] * np.exp(1j * ph))
            s_bound_any = k * v['dI_mag_sum_bound_A']          # in phase with the current: worst possible
            out[f'{c}|{combo}|x{k}'] = dict(model=s_model, bound_fem_phase=s_bound_fem_phase, bound_any_phase=s_bound_any,
                                           margin_left_model=LOW - REQ - s_model, margin_left_bound_any=LOW - REQ - s_bound_any)
            print('  %-5s %-24s x%.1f  peak shift: model %.2f A | stacked bound, FEM phase %.2f A | stacked bound, any phase %.2f A -> margin left %.2f A' % (
                c[:5], combo, k, s_model, s_bound_fem_phase, s_bound_any, LOW - REQ - s_bound_any))
# CT: 15 mV/A at the burden. Over-current error (A of tank current) and ZC timing.
print('CT (15 mV/A): worst = 1.5 x (|Bz part| + 2 x |Br part|)  [2x = Br doubling at the top-side plane surface]')
for n in ('CT_ZC_cmp', 'CT_OC_cmp', 'CT_MON_to_J4', 'CT_secondary_burden'):
    for c in CASES:
        q = L[n][c + '|fem']
        worst = 1.5 * (q['emf_Bz_abs'] + 2 * q['emf_Br_abs'])
        dA = worst / 15.0
        dth = worst / (15.0 * IPK)   # rad, ZC crossing shift (ratio independent of current)
        out[f'{n}|{c}'] = dict(model_mV=q['emf_abs'], worst_mV=worst, tank_equiv_A=dA, zc_deg=math.degrees(dth), zc_ns=dth / (2 * math.pi * 31e3) * 1e9)
        print('  %-20s %-5s model %.3f mV  worst %.2f mV -> %.3f A tank-equiv, ZC %.3f deg = %.0f ns' % (n, c[:5], q['emf_abs'], worst, dA, math.degrees(dth), dth / (2 * math.pi * 31e3) * 1e9))
# LINE_ZC
for n in ('LINE_ZC_input', 'LINE_ZC_raw_straight', 'LINE_ZC_raw_image', 'LINE_ZC_out_to_J4'):
    for c in CASES:
        q = L[n][c + '|fem']; worst = 1.5 * q['emf_bound']
        out[f'{n}|{c}'] = dict(model_mV=q['emf_abs'], worst_mV=worst)
        print('  %-22s %-5s model %.3f mV worst %.2f mV' % (n, c[:5], q['emf_abs'], worst))
# LINE_ZC_input: series with 120 V / 66 k string; opto threshold crossing near the line zero
w = 1.5 * L['LINE_ZC_input'][CASES[1] + '|fem']['emf_bound']
print('  LINE_ZC input: %.2f mV / 66 k = %.0f nA (LED ~2.6 mA pk); line slew 64 V/ms -> %.0f ns' % (w, w / 66e3 * 1e6, w / 64 * 1e3))
w = 1.5 * L['LINE_ZC_raw_straight'][CASES[1] + '|fem']['emf_bound']
print('  LINE_ZC_RAW: %.1f mV vs Schmitt hysteresis (hundreds of mV); at ~66 mV/us edge -> %.2f us (allocation +/-250 us)' % (w, w / 66))
json.dump(out, open('sensitivity.json', 'w'), indent=1)
