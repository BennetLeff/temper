#!/usr/bin/env python3
"""D-13 evidence runner: unchanged D2 physics, explicit temperature, D6 proxy.

Run from any directory with Miniforge Python. Maximum two ngspice processes.
No cached runs: --mode main/refine/threshold chooses a fresh bounded campaign.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
D2 = HERE.parents[1] / 'd2'
D6 = HERE.parent / 'out-D6'
ROOT = HERE.parents[6]
sys.path.insert(0, str(D2))
import run_d2  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare() -> None:
    """Copy D6 decks, retaining its overlap proxy and adding only .temp."""
    (HERE / 'decks').mkdir(exist_ok=True)
    for variant, source in [('baseline', 'baseline'), ('F6', 'off1_c1_neg2')]:
        text = (D6 / 'decks' / f'{source}.cir').read_text()
        text = text.replace('.include params.inc', '.include params.inc\n.temp {TJ}')
        (HERE / 'decks' / f'{variant}.cir').write_text(text)
    (HERE / 'decks' / 'threshold.cir').write_text((D6 / 'threshold.cir').read_text())


def one(job: tuple) -> dict:
    variant, temp, scenario, bus, current, direction, dt, esl, step = job
    name = f'{variant}_T{temp}_{scenario}_v{bus}_i{current}_d{direction}_dt{dt}_esl{esl}_step{step}'
    output = HERE / 'raw' / name
    params = run_d2.matrix_params(run_d2.read_L(str(D2 / 'legA-h0-best.matrix.txt')))
    params.update(TJ=str(temp), VBUS=str(bus), IL=str(current), DIR=str(direction),
                  DT=f'{dt}n', LESL=f'{esl}n', LSHUNT='2n', TRMAX=f'{step}n')
    row = {'name': name, 'variant': variant, 'temp_C': temp, 'case': scenario, 'vbus': bus,
               'il': current, 'dir': direction, 'dt_ns': dt, 'esl_nH': esl, 'step_ns': step, 'params': params}
    try:
        result = run_d2.run(HERE / 'decks' / f'{variant}.cir', params, keep=output)
    except subprocess.TimeoutExpired as error:
        result = {'aborted': True, 'returncode': None, 'meas': {}, 'failed': ['timeout 1800s']}
        (output / 'run.log').write_text(str(error))
    finally:
        (output / 'IFX_CFD7_650V.lib').unlink(missing_ok=True)
        (output / f'{variant}.cir').unlink(missing_ok=True)
    m = result['meas']
    off, incoming = ('ls', 'hs') if direction == 0 else ('hs', 'ls')
    required = ['vds_ls_die_pk', 'vds_hs_die_pk', f'vgs_{off}_off_max', f'vds_{incoming}_at_on']
    required += [f'e_{side}_{part}' for side in ('l', 'h') for part in ('pre', 'post')]
    required += [f'vgs_{side}_die_{extreme}' for side in ('ls', 'hs') for extreme in ('min', 'max')]
    complete = not result['aborted'] and not result['failed'] and result['returncode'] == 0 and all(k in m for k in required)
    row.update(status='complete' if complete else 'indeterminate', meas=m,
               returncode=result['returncode'], failed=result['failed'])
    if complete:
        row.update(off_V=m[f'vgs_{off}_off_max'], vds_V=max(m['vds_ls_die_pk'], m['vds_hs_die_pk']),
                   incoming_V=m[f'vds_{incoming}_at_on'], zvs=m[f'vds_{incoming}_at_on'] <= .05 * bus,
                   vgs_abs_V=max(abs(m[f'vgs_{side}_die_{extreme}']) for side in ('ls', 'hs') for extreme in ('min', 'max')),
                   off_uJ=m[f'e_{off[0]}_pre'] * 1e6, on_uJ=m[f'e_{incoming[0]}_post'] * 1e6,
                   total_uJ=sum(m[f'e_{side}_{part}'] for side in ('l', 'h') for part in ('pre', 'post')) * 1e6)
    (output / 'result.json').write_text(json.dumps(row, indent=2) + '\n')
    print(name, row['status'], row.get('off_V'), flush=True)
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['main', 'refine', 'threshold'], default='main')
    parser.add_argument('--workers', type=int, choices=[1, 2], default=2)
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    prepare()
    sources = [Path(__file__), D2 / 'legA-h0-best.matrix.txt', D2 / 'run_d2.py',
               D6 / 'decks/baseline.cir', D6 / 'decks/off1_c1_neg2.cir',
               run_d2.KIT / 'common/run_ngspice.py', run_d2.KIT / 'common/options.inc',
               run_d2.KIT / 'models/vendor/IFX_CFD7_650V.lib']
    provenance = {'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
                  'python': sys.version, 'model_provider': 'OpenAI GPT-6 agent', 'argv': sys.argv,
                  'ngspice': subprocess.check_output(['ngspice', '--version'], text=True),
                  'inputs': {str(p.relative_to(ROOT)): sha(p) for p in sources},
                  'decks': {p.name: sha(p) for p in (HERE / 'decks').glob('*.cir')}}
    (HERE / f'provenance-{args.mode}.json').write_text(json.dumps(provenance, indent=2) + '\n')
    if args.mode == 'threshold':
        rows = []
        for temp in (25, 27, 100, 150):
            output = HERE / 'raw' / f'threshold_T{temp}'
            result = run_d2.run(HERE / 'decks/threshold.cir', {'TJ': str(temp), 'DV': '0'}, keep=output)
            (output / 'IFX_CFD7_650V.lib').unlink(missing_ok=True)
            (output / 'threshold.cir').unlink(missing_ok=True)
            assert not result['aborted'] and not result['failed'] and 'vth' in result['meas']
            rows.append({'temp_C': temp, 'model_threshold_V': result['meas']['vth'],
                         'model_screen_V': result['meas']['vth'] - .5})
    else:
        points = [('S1', bus, 37, dt) for bus in (170, 198, 280) for dt in (307, 348, 443)]
        points += [('S2', 280, 71, dt) for dt in (307, 348, 443)]
        points += [('S4', 198, -20, dt) for dt in (348, 443)]
        if args.mode == 'refine':
            points = [p for p in points if p[3] in (348, 443) and (p[0] != 'S1' or p[1] == 280)]
        jobs = [(variant, temp, *point[:3], direction, point[3], esl, .1 if args.mode == 'refine' else .2)
                for variant in ('baseline', 'F6') for temp in (27, 100, 150) for point in points
                for direction in (0, 1) for esl in ((10,) if args.mode == 'refine' else (1.06, 10))]
        if args.limit is not None:
            jobs = jobs[:args.limit]
        with ThreadPoolExecutor(args.workers) as pool:
            rows = list(pool.map(one, jobs))
    (HERE / f'results-{args.mode}.json').write_text(json.dumps(rows, indent=2) + '\n')


if __name__ == '__main__':
    main()
