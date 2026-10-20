"""Print the README tables from extracted.json, inductance.json, closed_form.json and FD files."""
import json

from common import HERE

E = json.loads((HERE / 'extracted.json').read_text())
H = E['harness']
I = json.loads((HERE / 'inductance.json').read_text())
CF = json.loads((HERE / 'closed_form.json').read_text())


def lnh(d, k=2):
    return f"{d['low']:.{k}f} / {d['nom']:.{k}f} / {d['high']:.{k}f}"


print('## harness table')
for key in ('c_sum_gnd_pf', 'c_sum_tiaout_pf', 'c_hi_gnd_pf', 'c_hi_sum_pf', 'c_sum_lowbuf_pf',
            'c_tiaout_gnd_pf', 'c_hi_tiaout_pf'):
    print(f'| {key} | {lnh(H[key])} |')
print(f"| l_c104_branch_nh | {lnh(H['l_c104_branch_nh'])} | board+C104 only {lnh(H['l_c104_branch_board_only_nh'])} |")
for r, d in H['l_rf_branch_nh'].items():
    print(f"| l_rf_branch_nh {r} | {lnh(d)} | board+parts only {lnh(H['l_rf_branch_board_only_nh'][r])} | shared {H['l_shared_package_and_pin_path_nh'][r]} |")
for r, d in H['c_sum_tiaout_pf_by_range'].items():
    print(f'| c_sum_tiaout {r} | {lnh(d, 3)} |')
print('## verdicts', json.dumps(H['verdict_vs_simulation'], indent=1))
print('## noisy')
for lab, g in H['noisy_copper_coupling'].items():
    print(f"| {lab} | {g['min_distance_to_sum_mm']:.1f} | {g['c_to_sum_fF']['nom']:.3f} / {g['c_to_sum_fF']['high']:.3f} | "
          f"{g['min_distance_to_tiaout_mm']:.1f} | {g['c_to_tiaout_fF']['nom']:.3f} / {g['c_to_tiaout_fF']['high']:.3f} | "
          f"{g['min_distance_to_hi_mm']:.1f} | {g['c_to_hi_fF']['nom']:.3f} / {g['c_to_hi_fF']['high']:.3f} |")
print('## R_ISO (100R range; others in extracted.json)')
if 'rev_d_riso_variant' in E:
    rv = E['rev_d_riso_variant']['ranges']
    for key in ('c_sum_gnd_pf', 'c_sum_tiaout_pf', 'c_sum_j3side_pf', 'c_j3side_gnd_pf', 'c_j3side_lowbuf_pf',
                'c_hi_j3side_pf', 'c_hi_sum_pf', 'c_sum_lowbuf_pf'):
        vals = {c: max(rv[r][c][key] for r in rv) if c != 'low' else min(rv[r][c][key] for r in rv)
                for c in ('low', 'nom', 'high')}
        print(f'| {key} | {lnh(vals)} |')
print('## meta', json.dumps(E['meta'], indent=1))
print('## closed-form vs FD (7628)')
for n in ('DUT_LO', 'TIA_OUT', 'DUT_HI'):
    d = CF['c_gnd_pF'][n]
    print(n, {k.split('/')[1]: round(v['total'], 2) for k, v in d.items() if k.startswith('JLC04161H-7628')})
for k, v in CF['mutual_pF'].items():
    if k.endswith('7628') and k.startswith('DUT_LO|TIA_OUT'):
        print(k, round(v['total'], 3))
print('## inductance validation', json.dumps(I['validation'], indent=1))
