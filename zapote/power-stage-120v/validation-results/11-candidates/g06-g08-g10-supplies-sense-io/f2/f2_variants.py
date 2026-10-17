"""F4 options for the J11 blower/controller tap fuse.  Rerun: python3 -I f2_variants.py (stdlib; writes result.json).
Reads the corner table of 02-protection-timing/f2-coordination/result.json (read-only) so the fault currents are the
F4 study's, not new.  New here: series-impedance options and the PS3 load after proposal P1.

Bound used for a series resistor R: Ik <= V / (R + R_fuse_cold)  (source impedance taken as 0: conservative, because
|Z_src + R| >= R).  V = 139.7 V (127 V + 10 %).
Normal-operation current: Mean Well IRM-60-SPEC 2025-11-21 p.2 'AC CURRENT 1.8 A typ at 115 Vac' (full 60 W), scaled
linearly with output power and 1/V (PF held constant; non-PFC rectifier-cap input, so the rms is the pulse rms)."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(HERE, '..', '..', '..', '02-protection-timing', 'f2-coordination', 'result.json')))
V = R['V_rms']
LOAD_NOW, LOAD_P1 = 39.7, 39.7 + 4.83     # W at PS3 output: blower buck input (plan-16 budget) / + controller logic (P1)
def i_in(p_out, v_line): return 1.8 * (p_out / 60.0) * (115.0 / v_line)
ik_corners = [(c['corner'], c['variant'], c['I_rms_A']) for c in R['corners']]
worst_Cu = max(i for _, v, i in ik_corners if v.startswith('Cu+'))
worst_all = max(i for _, _, i in ik_corners)
rows = {}
# (a) F2 as built
rows['UMT250 as built'] = dict(breaking_A=200, ik_worst_A=worst_all, ratio=worst_all / 200)
# (b) 02153.15MXP, 1.5 kA, cold 28.25 mOhm: F4 study's own numbers
rep = R['replacement_02153.15MXP']
rows['02153.15MXP alone'] = dict(breaking_A=1500, ik_worst_with_Cu_A=max(c['I_rms_A'] for c in rep['corners'] if c['variant'] == 'Cu'),
                                 ik_worst_Cu0_A=max(c['I_rms_A'] for c in rep['corners'] if c['variant'] == 'Cu=0'))
def option(name, breaking, r_fuse, r_ser):
    ik = V / (r_fuse + r_ser)
    d = dict(breaking_A=breaking, R_series_ohm=r_ser, ik_bound_A=round(ik, 0), margin_x=round(breaking / ik, 2))
    for p, tag in ((LOAD_NOW, 'now'), (LOAD_P1, 'P1')):
        for v in (108.0, 132.0):
            i = i_in(p, v)
            d[f'I_in_{tag}_{int(v)}V_A'] = round(i, 2)
            d[f'P_series_{tag}_{int(v)}V_W'] = round(i * i * r_ser, 2)
    rows[name] = d
for rs in (0.10, 0.15, 0.22):
    option(f'02153.15MXP + {rs} ohm series', 1500, 0.02825, rs)
for rs in (0.7, 1.0, 2.2):
    option(f'UMT250 + {rs} ohm series', 200, 0.0952, rs)       # F2 max cold R from the F4 study
json.dump(dict(V=V, rows=rows), open(os.path.join(HERE, 'result.json'), 'w'), indent=1)
for k, v in rows.items(): print('%-34s %s' % (k, v))
