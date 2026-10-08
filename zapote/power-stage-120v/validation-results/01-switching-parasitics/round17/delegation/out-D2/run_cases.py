#!/usr/bin/env python3
"""Sequential, thin wrapper around the round17 D2 runner; no new circuit rule logic.
Run the shared model fetch and smoke_test.py first (see README).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import platform
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
R17 = HERE.parents[1]
ROOT = HERE.parents[6]
D2 = R17 / 'd2'
VARIANTS = {
    'baseline': {'ROH': '5', 'ROL': '0.55', 'TCMD': '5n'},
    'boost': {'ROH': f'{5 * 1.47 / (5 + 1.47):.12g}', 'ROL': '0.55', 'TCMD': '5n'},
    'weak_sink': {'ROH': f'{5 * 1.47 / (5 + 1.47):.12g}', 'ROL': '0.75', 'TCMD': '5n'},
    'slow_edge': {'ROH': f'{5 * 1.47 / (5 + 1.47):.12g}', 'ROL': '0.75', 'TCMD': '10n'},
}
CASES = {'S1': ('170', '37'), 'S2': ('280', '71'), 'S4': ('170', '-20')}
MATRICES = {'h1': D2 / 'legA-h1-e0p35.matrix.txt', 'lin12': D2 / 'legA-h0-lin12.matrix.txt'}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    spec = importlib.util.spec_from_file_location('round17_d2', D2 / 'run_d2.py')
    assert spec and spec.loader
    d2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(d2)
    d2.DECK = HERE / 'leg_matrix.cir'
    d2.HERE = HERE
    model = d2.KIT / 'models/vendor/IFX_CFD7_650V.lib'
    assert digest(model) == '02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b'
    inputs = [D2/'run_d2.py', D2/'leg_matrix.cir', d2.KIT/'common/run_ngspice.py', d2.KIT/'common/options.inc', model, *MATRICES.values(), HERE/'run_cases.py', HERE/'leg_matrix.cir']
    provenance = {
        'source_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, cwd=ROOT).strip(),
        'model_provider': 'GPT-6 Astra / OpenAI',
        'python': platform.python_version(),
        'platform': platform.platform(),
        'ngspice': subprocess.check_output(['ngspice', '--version'], text=True),
        'inputs_sha256': {str(p.relative_to(ROOT)): digest(p) for p in inputs},
        'variants': VARIANTS,
        'status': 'running',
    }
    (HERE/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    rows = []
    for matrix, path in MATRICES.items():
        for case, (vbus, il) in CASES.items():
            for variant, settings in VARIANTS.items():
                tag = f'{matrix}-{case}-{variant}'
                params = d2.matrix_params(d2.read_L(str(path)))
                params.update(VBUS=vbus, IL=il, DIR='0', DT='348n', TRMAX='0.2n', LESL='10n', LSHUNT='2n', **settings)
                result = d2.run(d2.DECK, params, keep=HERE/'runs'/tag)
                # The common runner copies licensed models and writes absolute include
                # paths. Keep logs/params only; the committed deck is the replay input.
                run_dir = HERE/'runs'/tag
                (run_dir/model.name).unlink(missing_ok=True)
                (run_dir/'leg_matrix.cir').unlink(missing_ok=True)
                required = (*d2.MEAS, 'vds_hs_at_on', 'vgs_ls_at_partner', 'window_end')
                missing = [key for key in required if key not in result['meas']]
                assert not result['aborted'] and not result['failed'] and not missing, (tag, result, missing)
                assert abs(result['meas']['window_end'] - 3.098e-6) < 1e-12
                row = {'matrix': matrix, 'case': case, 'variant': variant, 'params': params, 'meas': result['meas'], 'returncode': result['returncode'], 'aborted': result['aborted'], 'failed': result['failed']}
                rows.append(row)
                (HERE/'results.json').write_text(json.dumps(rows, indent=2)+'\n')
                print(tag, json.dumps(result['meas']), flush=True)
    provenance['status'] = 'complete'
    provenance['completed_runs'] = len(rows)
    (HERE/'provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    headers = ['matrix', 'case', 'variant', 'VDS LS peak (V)', 'VDS HS peak (V)', 'LS VGS at partner (V)', 'LS off VGS max (V)', 'HS VDS at on (V)']
    keys = ['vds_ls_die_pk', 'vds_hs_die_pk', 'vgs_ls_at_partner', 'vgs_ls_off_max', 'vds_hs_at_on']
    table = ['| '+' | '.join(headers)+' |', '| '+' | '.join(['---']*len(headers))+' |']
    for row in rows:
        table.append('| '+' | '.join([row['matrix'], row['case'], row['variant']]+[f'{row["meas"][k]:.4f}' for k in keys])+' |')
    (HERE/'comparison.md').write_text('\n'.join(table)+'\n')


if __name__ == '__main__':
    main()
