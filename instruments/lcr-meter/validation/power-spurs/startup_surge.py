"""TPS65131 start-up against the TPS2553 current limit: power-up from USB attach to both rails in regulation.

python3 validation/power-spurs/startup_surge.py  ->  startup_surge.json   (after regulator_check.py)

Model, from U16 turning on (t = 0) with the 5 V node empty:
  * U16 charges the 5 V node at its minimum current limit (regulator_check.json) up to VBUS after U16, then
    supplies the load, capped at that limit; above it the node discharges.
  * 3V3 (AP2112K, start-up 20 us) follows 5 V less 0.25 V once 5 V passes its EN high level (1.5 V; EN is
    tied to 5 V) and loads 5 V with OTHER_A for the rest of the board.
  * Enables, per variant: 'rc' = an RC from 3V3 on the pin (crossing at a threshold between VIL 0.4 V and
    VIH 1.4 V, SLVS493E 6.5; no hysteresis is specified); 'lm3880' = U17's flags (SNVS451M): its EN cap
    charges from 7 uA to 1.25 V once 3V3 >= 2.7 V (VCC minimum), then FLAG1 (ENP) after td1 = 10 ms and
    FLAG2 (ENN) td2 = 10 ms later, each +-15 % (Electrical Characteristics, timing AA), plus the 400 us
    EPROM refresh (7.3.3); the EN current has no stated tolerance, taken +-50 %.  A converter starts when
    its enable is high and VIN is above its UVLO (2.1-2.7 V, SLVS493E 6.5); if VIN then falls below the
    UVLO it restarts (fail).
  * Converters (SLVS493E 7.3.5): on enable the switch current limit ramps to 1.8 / 2.2 A in about 1 ms;
    until its output reaches regulation a converter runs at that limit (ripple ignored, which overstates the
    average).  boost: I_in = I_L, I_out = eta I_L Vin / Vpos; RAW_P is pre-charged to 5 V - VF through
    L1/D2 (that charge counts as 5 V load).  inverter: I_in = I_L D, D = |Vneg| / (Vin + |Vneg|),
    I_out = eta I_L (1 - D).  Each output: C89/C90 + C94 (or C91/C92 + C99), 3 x 10 uF 50 V X7R 1210 at a
    DC-bias retention of 0.4 / 0.6; then its static load.  The LDOs soft-start over 9-14 ms, not modelled.
  * 5 V capacitance: ceramics C16 1 uF, C80/C82 10 uF 50 V X7R, C83 100 nF, C67 1 uF, C103 and C112 22 uF
    25 V X5R (behind FB1 / R101 1 ohm: fast at these time scales), 66 uF nominal, 45 uF effective at 5 V;
    C117 330 uF polymer (no DC-bias loss) at +-20 % (Nichicon PCG catalog); its ESR (23 mOhm max) times the
    deficit current is taken off v5_min.
Pass: both converters reach regulation, neither sees VIN below its UVLO after enabling, and 5 V stays above
3.7 V from the first enable on (AP2112K: 3.3 V + 0.4 V dropout max, so 3V3 and the MCU never droop).
Corners: VBUS after U16 4.32 / 5.0 V, switch limit, retention, C117 tolerance, UVLO, EN thresholds (RC
variants), LM3880 timer and EN current.
"""

import itertools
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VPOS, VNEG = 14.19, 14.07           # design set points (regulator_check)
LOAD_P, LOAD_N = 0.040, 0.040       # A once in regulation (regulator_check loads 36 / 40 mA)
ETA, VF, T_SS, OTHER_A = 0.85, 0.4, 1e-3, 0.15
CERAMIC_UF, ESR_C117 = 45.0, 0.023
DT = 2e-6


def run(enable, vbus, ilim, ret, c117_uf, uvlo, ulim, **e):
    """One power-up; enable(t, v33, state, **e) -> (enp, enn)."""
    c, cb = 3 * 10e-6 * ret, (CERAMIC_UF + c117_uf) * 1e-6
    v5 = vp = vn = t = 0.0
    tp = tn = None
    reg_p = reg_n = False
    vmin, fail, st = 9.0, None, {}     # a run stops at its first UVLO restart
    while t < 0.2:
        v33 = min(3.3, max(0.0, v5 - 0.25)) if v5 > 1.5 else 0.0
        enp, enn = enable(t, v33, st, **e)
        i_in = OTHER_A if v33 > 0 else 0.0
        if tp is None and enp and v5 > uvlo:
            tp = t
        if tn is None and enn and v5 > uvlo:
            tn = t
        if (tp is not None or tn is not None) and v5 < uvlo and fail is None:
            fail = f'UVLO restart at {t * 1e3:.2f} ms'
            break
        if tp is None:
            new = max(vp, v5 - VF)
            i_in += c * (new - vp) / DT
            vp = new
        elif not reg_p:
            il = ilim * min((t - tp) / T_SS, 1.0)
            i_in += il
            vp = max(vp, v5 - VF) + ETA * il * v5 / max(vp, 0.5) * DT / c
            reg_p = vp >= VPOS
        else:
            i_in += LOAD_P * VPOS / (v5 * ETA)
        if tn is not None:
            if not reg_n:
                il = ilim * min((t - tn) / T_SS, 1.0)
                d = vn / (v5 + vn) if vn > 0 else 0.0
                i_in += il * d
                vn += ETA * il * (1 - d) * DT / c
                reg_n = vn >= VNEG
            else:
                i_in += LOAD_N * VNEG / (v5 * ETA)
        supply = ulim if (i_in > ulim or v5 < vbus - 1e-6) else i_in
        v5 = min(vbus, v5 + (supply - i_in) * DT / cb)
        if tp is not None or tn is not None:
            vmin = min(vmin, v5 - ESR_C117 * (c117_uf > 0) * max(i_in - supply, 0.0))
        t += DT
        if reg_p and reg_n and t > max(tp, tn) + 2e-3:
            break
    ok = fail is None and reg_p and reg_n and vmin > 3.7
    return {'ok': ok, 'fail': fail, 'enp_ms': tp and round(tp * 1e3, 2), 'enn_ms': tn and round(tn * 1e3, 2),
            'v5_min_after_enable': round(vmin, 2)}


def rc(t, v33, st, tau_p, tau_n, th_p, th_n):
    """RC from 3V3 on each pin (tau 0 = tied to 3V3)."""
    for k, tau in (('p', tau_p), ('n', tau_n)):
        st[k] = v33 if tau == 0 else st.get(k, 0.0) + (v33 - st.get(k, 0.0)) * DT / tau
    return st['p'] > th_p, st['n'] > th_n


def lm3880(t, v33, st, c_en, i_en, td):
    """U17: EN cap charged by i_en once VCC (3V3) >= 2.7 V; FLAG1 td after EN, FLAG2 td later."""
    if v33 >= 2.7:
        st['ven'] = st.get('ven', 0.0) + i_en * DT / c_en
        if 'ten' not in st and st['ven'] >= 1.25:
            st['ten'] = t
    t0 = st.get('ten')
    return t0 is not None and t >= t0 + td + 400e-6, t0 is not None and t >= t0 + 2 * td + 400e-6


def worst(enable, c117_uf, ulim, extra):
    rows = []
    keys = list(extra)
    for vbus, ilim, ret, tol, uvlo, *ev in itertools.product(
            (4.32, 5.0), (1.8, 2.2), (0.4, 0.6), (0.8, 1.2), (2.1, 2.7), *extra.values()):
        e = dict(zip(keys, ev))
        r = run(enable, vbus, ilim, ret, c117_uf * tol, uvlo, ulim, **e)
        rows.append(dict(vbus=vbus, ilim_a=ilim, retention=ret, c117_tol=tol, uvlo=uvlo, **e, **r))
    w = min(rows, key=lambda x: (x['ok'], x['v5_min_after_enable']))
    return {'corners': len(rows), 'pass': sum(r['ok'] for r in rows), **w}


reg = json.loads((HERE / 'regulator_check.json').read_text())
ulim = next(c['value'] for c in reg['checks'] if c['item'].startswith('TPS2553 current limit'))[0]
design = {p['ref']: p for p in json.loads((ROOT / 'cad/design.json').read_text())['parts']}
c117 = float(design['C117']['value'].split('uF')[0])
c_en = float(design['C116']['value'].split()[0].rstrip('nF')) * 1e-9
assert design['C116']['pins']['2'] == design['U17']['pins']['3'] == 'SEQ_EN'
assert design['U17']['mpn'].startswith('LM3880MF-1AA')        # timing AA: 10 ms steps
SEQ = {'c_en': (c_en,), 'i_en': (3.5e-6, 10.5e-6), 'td': (8.5e-3, 11.5e-3)}
TH = (0.4, 1.4)
out = {
    'tps2553_limit_min_a': ulim,
    'c117_uf': c117,
    'as_built (U17 LM3880-1AA, C117)': worst(lm3880, c117, ulim, SEQ),
    'U17 without C117': worst(lm3880, 0.0, ulim, SEQ),
    'rev_f_before_audit (ENP = ENN = 3V3, no C117)': worst(rc, 0.0, ulim, {'tau_p': (0,), 'tau_n': (0,),
                                                                          'th_p': TH, 'th_n': TH}),
    'rejected: ENP = 3V3, ENN RC 10 ms, C117': worst(rc, c117, ulim, {'tau_p': (0,), 'tau_n': (10e-3,),
                                                                      'th_p': TH, 'th_n': TH}),
}
(HERE / 'startup_surge.json').write_text(json.dumps(out, indent=1) + '\n')
print(json.dumps(out, indent=1))
