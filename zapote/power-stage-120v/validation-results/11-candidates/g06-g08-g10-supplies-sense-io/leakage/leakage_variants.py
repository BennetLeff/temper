"""F5 slice for G06/G10: how many of the three IRM modules reach the PE-open touch current, and what the
supply-count proposals do to it.  Rerun: python3 -I leakage_variants.py (stdlib; writes result.json)

Constants and formula are copied from 07-conducted-emi/leakage/leakage_budget.py (132 V, 60 Hz, +20 % Y,
supplies at the Mean Well datasheet maximum 0.25 mA @ 277 Vac scaled linearly and x60/50).  Only the question of
WHICH supplies are charged to the PE path is new.

Path argument (SAFETY, needs bench/certifier): touch current in the UL 1026 open-PE test is the current from the hot
line into the chassis/PE, metered to earth.
  PS1 (IRM-20-15) and PS3 (IRM-60-15ST): output - is SELV_GND, bonded to PE by R38 (and via the controller)  -> in path.
  PS2 (IRM-20-24): output - is N_LS / LEG_RET, the bridge-referenced HOT domain; it has no PE bond.  Its Y current
  enters that domain and returns to N through the rectifier bridge; it reaches PE only through HOT-to-PE parasitics
  (coil 31 pF, FET tab to sink), which are in series with it and are pF-scale.  -> excluded here, flagged 'unverified'."""
import json, math, os
V, F, TOL = 132.0, 60.0, 0.20
W = 2 * math.pi * F
SUP = 0.25 * (V / 277.0) * (60.0 / 50.0)          # mA per module, datasheet max
Y_BOARD = W * 2.2e-9 * (1 + TOL) * V * 1e3        # C3/C4
Y_MOD = W * 6.9e-9 * (1 + TOL) * V * 1e3          # D-22 inlet module
COIL = W * 31e-12 * (1 + TOL) * V * 1e3
BUDGET, LIMIT = 0.25, 0.5
def total(n_sup_in_path, y_board=Y_BOARD, y_mod=Y_MOD):
    return y_board + y_mod + COIL + n_sup_in_path * SUP
rows = {
 'baseline (3 modules charged, as F5 study)': total(3),
 'V1 PS2 not in PE path (HOT-referenced secondary)': total(2),
 'V2 PS1 merged into PS3 (proposal P1), PS2 still charged': total(2),
 'V3 = V1 + V2 (P1 and PS2 reclassified)': total(1),
 'V4 = V3 and typical-measured modules (0.015 mA @240 V Simpex, informational)': total(0) + 1 * 0.015 * (V / 240) * 1.2,
}
out = dict(supply_mA_each=SUP, y_board_mA=Y_BOARD, y_module_mA=Y_MOD, coil_mA=COIL, rows={k: round(v, 4) for k, v in rows.items()})
# what total Y per line (nominal, nF) the rest of the board must hold for PASS at the 0.25 mA budget / 0.5 mA limit
def y_allow_nF(n_sup, cap_mA):
    left = cap_mA - COIL - n_sup * SUP
    return max(left, 0) / (W * (1 + TOL) * V * 1e3) * 1e9
out['y_nominal_nF_allowed'] = {f'{n} supplies in path, {lab}': round(y_allow_nF(n, c), 2)
                               for n in (3, 2, 1) for lab, c in (('0.25 mA budget', BUDGET), ('0.5 mA limit', LIMIT))}
out['y_nominal_nF_now'] = 9.1
json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'result.json'), 'w'), indent=1)
for k, v in rows.items(): print('%-80s %.3f mA  %s' % (k, v, 'PASS' if v <= BUDGET else ('<= limit' if v <= LIMIT else 'FAIL')))
for k, v in out['y_nominal_nF_allowed'].items(): print('  Y allowed (nominal nF per line, board+module):', k, v)
# control: baseline must reproduce the F5 study's 0.974 mA
assert abs(rows['baseline (3 modules charged, as F5 study)'] - 0.9741) < 5e-4, 'does not reproduce leakage_budget.py'
print('control OK: baseline reproduces 0.974 mA')
