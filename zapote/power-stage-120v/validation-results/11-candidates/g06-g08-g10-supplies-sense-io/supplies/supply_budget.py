"""Supply load / derating / BOM arithmetic for proposals P1 (delete PS1, controller on PS3) and F12 (PS2, PS1, PS3).
Rerun: python3 -I supply_budget.py (stdlib; writes result.json).
Sources: IRM-20-SPEC 2025-11-21 p.2 (ratings 21 W @15 V, 21.6 W @24 V; efficiency 84 %/85 %; leakage <0.25 mA @277 V),
         p.3 derating graph 'OTHERS' read from the PDF image: 100 % to 50 C, straight to 5 % at 85 C.
         IRM-60-SPEC 2025-11-21 p.3 as read in stage16 PLAN-16 sec 1.2: 100 % to 50 C, 75 % at 60 C, 15 % at 85 C.
         PS3 load 39.7 W (blower buck input) and PS1 logic 4.83 W: PLAN-16 sec 1.1 and DECISIONS 16 (controller verify
         ps1.p_total_W).  PS2 load: native-21/bias_sizing.py sizing() HOT_supply_allocation_W (rerun below).
         Prices: BOM sheet STOCK-2026-10-13.csv (DK basis) and LCSC pages fetched 2026-10-13 (stated per line)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
def interp(pts, t):
    for (t0, l0), (t1, l1) in zip(pts, pts[1:]):
        if t0 <= t <= t1: return l0 + (l1 - l0) * (t - t0) / (t1 - t0)
    return pts[0][1] if t < pts[0][0] else pts[-1][1]
def t_for_load(pts, load):         # ambient at which the allowed load fraction falls to `load`
    for (t0, l0), (t1, l1) in zip(pts, pts[1:]):
        if l1 <= load <= l0: return t0 + (l0 - load) / (l0 - l1) * (t1 - t0)
    return pts[-1][0] if load < pts[-1][1] else pts[0][0]
IRM20 = [(50, 1.0), (85, 0.05)]
IRM60 = [(50, 1.0), (60, 0.75), (85, 0.15)]
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(HERE, '..', '..', '..', '..', 'native-21'))
import bias_sizing
rows = {r['frequency_Hz']: r['HOT_supply_allocation_W'] for r in bias_sizing.sizing()['rows']}
out = {'PS2_load_W_by_f': rows}
def entry(name, load_w, rated, curve):
    f = load_w / rated
    return dict(load_W=round(load_w, 2), load_pct=round(100 * f, 1), max_ambient_C=round(t_for_load(curve, f), 1))
for f, w in rows.items(): out[f'PS2 @{f//1000} kHz (24 V, 21.6 W)'] = entry('PS2', w, 21.6, IRM20)
out['PS1 now: 4.83 W controller'] = entry('PS1', 4.83, 21.0, IRM20)
out['PS3 now: 39.7 W blower'] = entry('PS3', 39.7, 60.0, IRM60)
out['PS3 after P1: 39.7 + 4.83 W'] = entry('PS3', 44.53, 60.0, IRM60)
out['PS3 after P1 at the 40 W-class blower corner 35.7/0.9 + 4.83 W'] = entry('PS3', 35.7 / 0.9 + 4.83, 60.0, IRM60)
# heat the B3 model carries for PS1 / PS2 (G10/G06: 1.524 / 1.419 W) vs the loss implied by the load
for nm, p, eta in (('PS1', 4.83, 0.84), ('PS2', 8.0, 0.85)):
    out[f'{nm} loss at that load (W)'] = round(p * (1 / eta - 1), 2)
out['PS3 loss after P1 (W, 89 % eff, in chassis)'] = round(44.53 * (1 / 0.89 - 1), 2)
# BOM arithmetic at 500 units
bom = dict(PS1_IRM20_15_DK=8.40, PS1_IRM20_15_LCSC=6.3537, F2_UMT250=1.80, F2_02153_15MXP_LCSC_500=0.1099, clip_pair_est=0.70)
out['P1 BOM delta at 500 (USD, DK basis for PS1/F2 line)'] = round(-bom['PS1_IRM20_15_DK'] - bom['F2_UMT250'] + bom['F2_02153_15MXP_LCSC_500'] + bom['clip_pair_est'], 2)
out['P1 BOM delta at 500 (USD, LCSC price for PS1)'] = round(-bom['PS1_IRM20_15_LCSC'] - bom['F2_UMT250'] + bom['F2_02153_15MXP_LCSC_500'] + bom['clip_pair_est'], 2)
out['bom_note'] = 'clip pair 0.70 is an UNVERIFIED RS/Littelfuse 100-series figure (0.62-0.69 per clip x2 would be 1.2-1.4); no LCSC clip listing was found'
out['bom_note'] = 'clip price is a placeholder: RS lists Littelfuse 100 series at ~0.62-0.69 per clip (currency unclear), pair ~1.2-1.4; replace with the lead quote. Delta with clips at 1.40: %.2f' % (-bom['PS1_IRM20_15_DK'] - bom['F2_UMT250'] + bom['F2_02153_15MXP_LCSC_500'] + 1.40)
json.dump(out, open(os.path.join(HERE, 'result.json'), 'w'), indent=1)
for k, v in out.items(): print('%-62s %s' % (k, v))
