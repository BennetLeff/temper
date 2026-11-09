"""Rev F against Rev G from committed evidence: board, cost, parasitics, stability, protection, accuracy, enclosure.

    sh validation/rev-g/compare_f_g.sh [REV_F_GIT_REV]      (default study/lcr-in-box)

compare_f_g.sh prices both BOMs from one snapshot (validation/rev-g/prices/) and leaves Rev F's board, BOM, CPL
and order estimate in a temporary folder; this script reads that folder (argv[1]) and this tree, and writes
validation/rev-g/compare-f-g.json. It prints the tables of docs/rev-g-before-after.md.

Sources, Rev F | Rev G:
  board                 git REV:cad/temper-lcr.kicad_pcb | cad/temper-lcr.kicad_pcb (s-expression counts)
  cost                  order estimate on the Rev F package | validation/rev-g/order-estimate-5.json, same snapshot
  parasitics            layout-parasitics/extracted_revf.json | extracted_revg.json (worst range per corner)
  stability             stability-full-chain/summary-revfcng100.md | summary-revgxcng100.md (360 cases each)
  surge                 rev-g-protection/protection-screen.json, candidates `links` (Rev F) | `parts_jackside`
  accuracy verdicts     rev-g-protection/normal-operation.json, `parts_jackside` map counts (base = Rev F)
  enclosure envelope    enclosure-envelope/board-envelope.json | rev-g/board-envelope.json
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VAL = ROOT / 'validation'
F_DIR = Path(sys.argv[1])
REV_F = sys.argv[2] if len(sys.argv) > 2 else 'study/lcr-in-box'


def board(text):
    fps = re.findall(r'\(footprint "([^"]+)"', text)
    refs = re.findall(r'\(property "Reference" "([^"]+)"', text)
    return {
        'footprints': len(fps),
        'segments': len(re.findall(r'^\s*\(segment\b', text, re.M)),
        'arcs': len(re.findall(r'^\s*\(arc\b', text, re.M)),
        'vias': len(re.findall(r'^\s*\(via\b', text, re.M)),
        'teardrops': len(re.findall(r'^\s*\(zone\b(?:(?!^\s*\(zone\b).)*?\(teardrop\b', text, re.M | re.S)),
        'nets': len(set(re.findall(r'\(net "([^"]*)"\)', text)) - {''}),
        'refs': sorted(set(refs)),
    }


def estimate(path):
    d = json.loads(Path(path).read_text())
    return {'totals': d['totals'], 'economic': d['economic'], 'board_counts': {k: v for k, v in d['board_counts'].items() if k != 'tht_refs'},
            'extended_lines': d['extended_lines'], 'basic_or_preferred_lines': d['basic_or_preferred_lines'],
            'lines': len(d['lines']), 'fab_usd': d['fab_quote']['total_usd'],
            'parts_smt_usd': round(sum(l['cost'] for l in d['lines'] if l['assembly'] == 'SMT'), 2),
            'parts_hand_usd': round(sum(l['cost'] for l in d['lines'] if l['assembly'] not in ('SMT', 'DNP')), 2),
            'stock_findings': d['stock_findings']}


# Node capacitances to ground, the worst range at each corner; the first two are gate G1 as rev-f-before-after.md
# reports it (Rev F, high corner: source 11.68, tia 14.02 pF)
NODES = {'source (SOURCE_BUF + selected RG)': 'c_source_gnd_pf', 'tia (TIA_OUT + selected RF)': 'c_tiaout_gnd_pf',
         'sum (TIA_SUM)': 'c_sum_gnd_pf', 'sum <-> tia': 'c_sum_tiaout_pf', 'low (DUT_LO)': 'c_lo_gnd_pf',
         'hi (DUT_HI)': 'c_hi_gnd_pf', 'HPOT': 'c_hpot_gnd_pf', 'LPOT': 'c_lpot_gnd_pf'}
G1 = {'source (SOURCE_BUF + selected RG)': 13.7, 'tia (TIA_OUT + selected RF)': 14.7}


def parasitics(rev, u_ref=None):
    """The worst range per corner. With u_ref, also the high corner at that grid uncertainty: assemble_reve.py
    builds every element of the high matrix (thin-prepreg maximum included) as nominal FD x (1 + U), so the
    rescale (1 + u_ref) / (1 + U) is exact."""
    d = json.loads((VAL / f'layout-parasitics/extracted_rev{rev}.json').read_text())
    u = d['fd']['grid_uncertainty']
    out = {'board_sha256': d['board_sha256'], 'grid_uncertainty': round(u, 3),
           'nodes': {name: {c: round(max(r[c][key] for r in d['ranges'].values()), 2) for c in ('nom', 'high')}
                     for name, key in NODES.items()}}
    if u_ref is not None:
        for name, key in NODES.items():
            out['nodes'][name]['high_at_u_ref'] = round(
                max(r['high'][key] for r in d['ranges'].values()) * (1 + u_ref) / (1 + u), 2)
        out['u_ref'] = round(u_ref, 3)
    return out


def stability(name):
    rows = {}
    for line in (VAL / f'stability-full-chain/{name}').read_text().splitlines():
        m = re.match(r'\| (\w+) \| all \| all \| all \| (\d+) \| ([\d.]+)° \| ([\d.]+) \|', line)
        if m:
            rows[m[1]] = {'cases': int(m[2]), 'worst_pm_deg': float(m[3]), 'min_abs_1_plus_t': float(m[4])}
    return rows


def envelope(path):
    d = json.loads(Path(path).read_text())
    return {'board_mm': d['board']['size_mm'], 'tallest_top_mm': max(p['height_mm'] for p in d['tallest_top']),
            'holes': d['mounting_holes']}


def main():
    import subprocess
    f_text = (F_DIR / 'board.kicad_pcb').read_text()
    g_text = (ROOT / 'cad/temper-lcr.kicad_pcb').read_text()
    bf, bg = board(f_text), board(g_text)
    added, removed = sorted(set(bg['refs']) - set(bf['refs'])), sorted(set(bf['refs']) - set(bg['refs']))
    for b in (bf, bg):
        del b['refs']
    design = json.loads((ROOT / 'cad/design.json').read_text())
    f_design = json.loads(subprocess.check_output(['git', 'show', f'{REV_F}:./cad/design.json'], cwd=ROOT))
    outline = lambda d: [d['board']['outline'][2] - d['board']['outline'][0], d['board']['outline'][3] - d['board']['outline'][1]]
    u_f = json.loads((VAL / 'layout-parasitics/extracted_revf.json').read_text())['fd']['grid_uncertainty']
    prot = json.loads((VAL / 'rev-g-protection/protection-screen.json').read_text())['candidates']
    acc = json.loads((VAL / 'rev-g-protection/normal-operation.json').read_text())['candidates']['parts_jackside']
    out = {
        'rev_f': REV_F, 'rev_f_commit': subprocess.check_output(['git', 'rev-parse', '--short', REV_F], cwd=ROOT, text=True).strip(),
        'outline_mm': {'f': outline(f_design), 'g': outline(design)},
        'board': {'f': bf, 'g': bg, 'refs_added_in_g': added, 'refs_removed_in_g': removed},
        'cost_5_boards': {'f': estimate(F_DIR / 'order-estimate-5.json'), 'g': estimate(HERE / 'order-estimate-5.json'),
                          'prices': sorted(p.name for p in (HERE / 'prices').glob('jlc-parts-*.json'))[-1]},
        'parasitics_pf': {'f': parasitics('f'), 'g1_limit_high_pf': G1},
        'stability_360': {'f': stability('summary-revfcng100.md'), 'g': stability('summary-revgxcng100.md')},
        'surge_1uF_lowest_class_a_v': {
            'f': {'v': prot['links']['min_v_within_ratings'], 'target_30v_met': prot['links']['target_met_1uF_30V']},
            'g': {'v': prot['parts_jackside']['min_v_within_ratings'],
                  'target_30v_met': prot['parts_jackside']['target_met_1uF_30V']}},
        'accuracy_lcr6100_1m': {mode: {'f': acc['map'][mode]['counts']['gw_1m_base'], 'g': acc['map'][mode]['counts']['gw_1m_new']}
                                for mode in ('linear', 'drift', 'level')},
        'signal_100_range': {'i_short_ma': [round(v, 3) for v in acc['signal']['100']['i_short_ma']],
                             'snr_loss_db': round(acc['signal']['100']['snr_loss_db'], 2)},
        'envelope': {'f': envelope(VAL / 'enclosure-envelope/board-envelope.json'),
                     'g': envelope(HERE / 'board-envelope.json')},
    }
    out['parasitics_pf']['g'] = parasitics('g', u_f)
    (HERE / 'compare-f-g.json').write_text(json.dumps(out, indent=1, ensure_ascii=False) + '\n')
    report(out)


def report(o):
    f, g = o['board']['f'], o['board']['g']
    print('| | Rev F | Rev G |\n|---|---|---|')
    print(f"| Outline | {o['outline_mm']['f'][0]:g} × {o['outline_mm']['f'][1]:g} mm | {o['outline_mm']['g'][0]:g} × {o['outline_mm']['g'][1]:g} mm |")
    for k in ('footprints', 'nets', 'segments', 'arcs', 'vias', 'teardrops'):
        print(f'| {k} | {f[k]} | {g[k]} ({g[k] - f[k]:+d}) |')
    print(f"\nadded: {' '.join(o['board']['refs_added_in_g'])}\nremoved: {' '.join(o['board']['refs_removed_in_g'])}\n")
    cf, cg = o['cost_5_boards']['f'], o['cost_5_boards']['g']
    print('| Five boards | Rev F | Rev G | Δ |\n|---|---|---|---|')
    rows = [('BOM lines', cf['lines'], cg['lines']), ('extended lines', cf['extended_lines'], cg['extended_lines']),
            ('placements', cf['board_counts']['placements'], cg['board_counts']['placements']),
            ('SMT joints / board', cf['board_counts']['smt_joints'], cg['board_counts']['smt_joints']),
            ('bare boards, $', cf['fab_usd'], cg['fab_usd']), ('SMT parts, $', cf['parts_smt_usd'], cg['parts_smt_usd']),
            ('economic total, $', cf['totals']['economic'], cg['totals']['economic']),
            ('+ JLC hand fit, $', cf['totals']['jlc_hand_fit'], cg['totals']['jlc_hand_fit'])]
    for name, a, b in rows:
        print(f'| {name} | {a:g} | {b:g} | {b - a:+.2f} |' if isinstance(a, float) else f'| {name} | {a} | {b} | {b - a:+d} |')
    pf, pg = o['parasitics_pf']['f'], o['parasitics_pf']['g']
    print(f"\n| Node, pF (worst range) | Rev F nom / high (U {pf['grid_uncertainty']}) | Rev G nom / high (U {pg['grid_uncertainty']}) | Rev G high at U {pg['u_ref']} |\n|---|---|---|---|")
    for n, v in pf['nodes'].items():
        w = pg['nodes'][n]
        print(f"| {n} | {v['nom']} / {v['high']} | {w['nom']} / {w['high']} | {w['high_at_u_ref']} |")
    print('\n| Loop | Rev F worst PM, min abs(1+T) | Rev G |\n|---|---|---|')
    for loop, v in o['stability_360']['f'].items():
        w = o['stability_360']['g'][loop]
        print(f"| {loop} | {v['worst_pm_deg']}°, {v['min_abs_1_plus_t']} | {w['worst_pm_deg']}° ({w['worst_pm_deg'] - v['worst_pm_deg']:+.2f}), {w['min_abs_1_plus_t']} |")
    s = o['surge_1uF_lowest_class_a_v']
    print(f"\nsurge 1 µF lowest class A: F {s['f']['v']} V (30 V met {s['f']['target_30v_met']}), G {s['g']['v']} V ({s['g']['target_30v_met']})")
    for m, v in o['accuracy_lcr6100_1m'].items():
        print(f"accuracy {m}: F {v['f']} G {v['g']}")
    print('signal 100 range', o['signal_100_range'])
    e = o['envelope']
    print(f"envelope F {e['f']['board_mm']} tallest {e['f']['tallest_top_mm']} | G {e['g']['board_mm']} tallest {e['g']['tallest_top_mm']}")


if __name__ == '__main__':
    main()
