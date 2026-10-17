#!/usr/bin/env python3
"""D-15 evidence only: best-matrix D2 loss/ZVS sweep, no circuit changes."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
D2 = HERE.parents[1] / 'd2'
sys.path.insert(0, str(D2))
import run_d2  # noqa: E402

CURRENTS = (2, 5, 10, 20, 30, 37)
DTS = (307, 348, 391, 443, 498)
MATRIX = D2 / 'legA-h0-best.matrix.txt'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_deck() -> Path:
    text = run_d2.DECK.read_text()
    extra = ['* D15: measurements/probes only; original circuit and solver unchanged.']
    for side in ('l', 'h'):
        q = f'xq{side}'
        power = f'max(0,(v({q}.dd)-v({q}.s))*(v({q}.ldrd)-v({q}.dd))/7.44e-5)'
        forward = f'max(0,-i(v.{q}.x1.v_sense2))'
        heat = f'max(0,v({q}.s)-v({q}.dd))*({forward})'
        extra.append(f'.save v({q}.ldrd) i(v.{q}.x1.v_sense2)')
        for label, lo, hi in [('pre', 'T1', 'T1+DT'), ('post', 'T1+DT', 'T1+DT+0.75u')]:
            for metric, expr in [('e', power), ('diode_e', heat), ('diode_q', forward),
                                 ('diode_t', f'(-i(v.{q}.x1.v_sense2)>0.1)')]:
                extra.append(f".meas tran {metric}_{side}_{label} INTEG par('{expr}') from={{{lo}}} to={{{hi}}}")
    extra.append('.meas tran coverage_end FIND v(bus) AT={T1+DT+0.75u}')
    text = text.replace('.end\n', '\n'.join(extra) + '\n.end\n')
    path = HERE / 'losses.cir'
    path.write_text(text)
    return path


def identity() -> dict:
    sources = [Path(__file__), run_d2.DECK, HERE / 'losses.cir', MATRIX, D2 / 'run_d2.py', D2 / 'grid.py',
               run_d2.KIT / 'common/run_ngspice.py', run_d2.KIT / 'common/options.inc',
               run_d2.KIT / 'models/vendor/IFX_CFD7_650V.lib']
    return {'inputs': {str(p.relative_to(HERE.parents[6])): sha(p) for p in sources},
            'ngspice': subprocess.check_output(['ngspice', '-v'], text=True),
            'python': sys.version, 'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()}


def cache_key(ident: dict) -> dict:
    """Revision is advisory; actual input bytes and runtime govern reuse."""
    return {key: value for key, value in ident.items() if key != 'source_revision'}


def one(job: tuple, ident: dict, raw: bool) -> dict:
    v, il, direction, dt, esl, step = job
    tag = f'v{v}_i{il}_d{direction}_dt{dt}_esl{esl}_step{step}'
    output = HERE / 'raw' / tag
    cached = output / 'result.json'
    if cached.exists():
        old = json.loads(cached.read_text())
        if cache_key(old['identity']) == cache_key(ident) and (not raw or old.get('raw_saved')):
            return old
        raise RuntimeError(f'Stale output at {output}; retain it and choose a fresh output root')
    p = run_d2.matrix_params(run_d2.read_L(str(MATRIX)))
    p.update(VBUS=str(v), IL=str(il), DIR=str(direction), DT=f'{dt}n', LESL=f'{esl}n', LSHUNT='2n', TRMAX=f'{step}n')
    result = run_d2.run(HERE / 'losses.cir', p, keep=output, raw=raw)
    # Generated licensed copies are redundant with the hash-verified original.
    (output / 'IFX_CFD7_650V.lib').unlink(missing_ok=True)
    measurements = result['meas']
    required = ['coverage_end', 'vds_ls_die_pk', 'vds_hs_die_pk', 'vds_hs_at_on', 'vds_ls_at_on',
                'vgs_ls_off_max', 'vgs_hs_off_max'] + [f'{m}_{s}_{w}' for m in ('e', 'diode_e', 'diode_q', 'diode_t')
                                                   for s in ('l', 'h') for w in ('pre', 'post')]
    missing = [key for key in required if key not in measurements]
    row = {'tag': tag, 'vbus': v, 'il': il, 'dir': direction, 'dt_ns': dt, 'esl_nH': esl, 'step_ns': step,
           'identity': ident, 'params': p, 'meas': measurements, 'aborted': result['aborted'] or bool(missing),
           'missing': missing, 'returncode': result['returncode'], 'raw_returncode': result['raw_returncode'],
           'raw_saved': raw, 'failed': result['failed']}
    if not row['aborted']:
        off, inc = ('l', 'h') if direction == 0 else ('h', 'l')
        incoming = measurements[f'vds_{inc}s_at_on']
        row.update(incoming_V=incoming, zvs=incoming <= .05 * v,
                   off_V=measurements[f'vgs_{off}s_off_max'],
                   peak_V=max(measurements['vds_ls_die_pk'], measurements['vds_hs_die_pk']),
                   off_uJ=measurements[f'e_{off}_pre'] * 1e6,
                   on_uJ=measurements[f'e_{inc}_post'] * 1e6,
                   total_uJ=sum(measurements[f'e_{s}_{w}'] for s in ('l', 'h') for w in ('pre', 'post')) * 1e6,
                   diode_incoming_deadtime_ns=measurements[f'diode_t_{inc}_pre'] * 1e9,
                   diode_incoming_deadtime_uJ=measurements[f'diode_e_{inc}_pre'] * 1e6,
                   diode_incoming_deadtime_uC=measurements[f'diode_q_{inc}_pre'] * 1e6,
                   diode_both_deadtime_uJ=sum(measurements[f'diode_e_{s}_pre'] for s in ('l', 'h')) * 1e6)
    if (output / 'waves.raw').exists():
        wave = output / 'waves.raw'
        row['waveform_sha256'] = sha(wave)
        with wave.open('rb') as source, gzip.open(output / 'waves.raw.gz', 'wb') as target:
            import shutil
            shutil.copyfileobj(source, target)
        wave.unlink()
    (output / 'result.json').write_text(json.dumps(row, indent=2) + '\n')
    print(f'{tag}: ' + ('INDETERMINATE' if row['aborted'] else f"E={row['total_uJ']:.6f}uJ ZVS={row['zvs']} diode={row['diode_incoming_deadtime_ns']:.4f}ns"), flush=True)
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=('sweep', 'refine'), default='sweep')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    make_deck()
    ident = identity()
    (HERE / 'provenance.json').write_text(json.dumps(ident, indent=2) + '\n')
    if args.phase == 'sweep':
        jobs = [(*case, .2) for case in itertools.product((170, 198), CURRENTS, (0, 1), DTS, (1.06, 10))]
    else:
        jobs = [(198, il, d, dt, esl, step) for il, d, dt, esl, step in
                itertools.product((2, 37), (0, 1), (348, 443), (1.06, 10), (.1, .05))]
    if args.limit:
        jobs = jobs[:args.limit]
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(lambda job: one(job, ident, args.phase == 'refine'), jobs))
    (HERE / f'{args.phase}.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps({'cases': len(rows), 'aborted': sum(r['aborted'] for r in rows)}))


if __name__ == '__main__':
    main()
