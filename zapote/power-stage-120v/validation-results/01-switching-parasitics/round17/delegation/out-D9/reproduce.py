#!/usr/bin/env python3
"""Offline D9 counterexamples and read-only audit. No FEM/SPICE/builds.

Synthetic fixtures demonstrate missing guarantees, not board errors. Temporary
fixtures are confined to out-D9 and removed. Requires NumPy and meshio.
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import meshio
import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROUND = HERE.parents[1]
REVISION = 'f9b13b483d6d4ed52439d4da419c7670bab6966c'
sys.path.insert(0, str(ROUND / 'd2'))
import run_d2
import grid
import make_deck5


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROUND / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def result(path: Path) -> dict:
    return json.loads(next(s[7:] for s in path.read_text().splitlines() if s.startswith('RESULT ')))


def write_result(path: Path, data: dict) -> None:
    path.write_text('RESULT ' + json.dumps(data) + '\n')


def grid_checks(tmp: Path) -> dict:
    measurements = {'vds_ls_die_pk': 200., 'vds_hs_die_pk': 200.,
                    'vgs_ls_die_max': 15., 'vgs_hs_die_max': 15.,
                    'vgs_ls_die_min': -1., 'vgs_hs_die_min': -1.,
                    'vgs_ls_off_max': 2., 'vgs_hs_off_max': 4.,
                    'vds_hs_at_on': 100., 'vds_ls_at_on': 100.,
                    'vgs_ls_at_partner': 2., 'vgs_hs_at_partner': 4.}
    calls = []
    def fake_run(deck, params, **kwargs):
        calls.append(params.copy())
        return {'aborted': False, 'meas': measurements.copy()}
    matrix = np.eye(4).tolist()
    case = ('S1', 170, 37, 0, 348, 10)
    with patch.object(run_d2, 'run', fake_run):
        first = grid.one((case, matrix, tmp / 'grid', None))
        second = grid.one((case, (100 * np.eye(4)).tolist(), tmp / 'grid', None))
        assert not first['task_pass'] and first['stress_pass']
        assert len(calls) == 2 and first['identity'] != second['identity']
        grid.one((case, (100 * np.eye(4)).tolist(), tmp / 'grid', None))
        assert len(calls) == 2
        measurements['vgs_ls_off_max'] = 4.
        measurements.pop('vgs_ls_at_partner')
        unknown = grid.one((('S1', 170, 37, 0, 307, 10), matrix, tmp / 'missing', None))
        assert unknown['off_gate_cause'] == 'unknown'
        measurements['vgs_ls_off_max'] = 2.
        measurements['vgs_ls_at_partner'] = 2.
        # The exposed --set interface overrides the simulation, but verdicts
        # continue to use the original case tuple.
        override = grid.one((('S1', 170, 37, 0, 450, 10), matrix,
                             tmp / 'override', {'DT': '348n', 'DIR': '1'}))
        assert override['task_pass'] and not override['zvs']
    # Record exactly which real dependencies identity() opens. No source edit.
    accesses = []
    real_read = Path.read_bytes
    def tracking_read(path):
        accesses.append(str(path.resolve()))
        return real_read(path)
    with patch.object(Path, 'read_bytes', tracking_read):
        grid.identity(matrix)
    omitted = [run_d2.KIT / 'common/options.inc', run_d2.KIT / 'common/run_ngspice.py']
    assert all(str(p.resolve()) not in accesses for p in omitted)
    return {'fixed_non_zvs_rejected': not first['task_pass'],
            'fixed_matrix_change_reruns': True, 'fixed_missing_sample_unknown': True, 'identical_inputs_reused': True,
            'override_actual_parameters': calls[-1],
            'override_saved_row': override,
            'hashed_paths': [Path(p).name for p in accesses],
            'unhashed_dependencies': [str(p.relative_to(run_d2.POWER)) for p in omitted],
            'simulator_identity_present': any('ngspice' in k for k in first['identity'])}


def matrix_checks(tmp: Path) -> dict:
    ex = load('ex', 'scripts/extrapolate.py')
    data = result(ROUND / 'results/matrices/legA-h1-e1p0-m10.matrix.txt')
    expected = ['P1_C38', 'P2_C39', 'P3_gate_high', 'P4_gate_low']
    data['port_identity'] = [{'name': name, 'physical': 10+i, 'k_A_per_m': [1., 0., 0.]}
                             for i, name in enumerate(expected)]
    reversed_data = copy.deepcopy(data)
    # Legitimate change of one coordinate orientation, consistently applied to
    # the matrix and metadata, must be rejected/remapped at fixed deck boundary.
    signs = np.diag([1., 1., -1., 1.])
    reversed_data['L_nH'] = (signs @ np.array(data['L_nH']) @ signs).tolist()
    reversed_data['port_identity'][2]['k_A_per_m'] = [-x for x in data['port_identity'][2]['k_A_per_m']]
    reversed_path = tmp / 'reversed.matrix.txt'
    write_result(reversed_path, reversed_data)
    accepted = run_d2.read_L(str(reversed_path))
    ex.read_matrix(str(reversed_path), expected)
    assert accepted[0][2] == -data['L_nH'][0][2]
    # Corrector checks eigenvalues of the symmetric part but never symmetry.
    baseline = {'names': expected, 'L_nH': (30 * np.eye(4)).tolist()}
    asym = copy.deepcopy(baseline)
    asym['L_nH'][0][1] = 8.
    for name, value in [('m10', baseline), ('m20', asym), ('target', baseline)]:
        write_result(tmp / f'{name}.txt', value)
    corrected = tmp / 'corrected.txt'
    command = [sys.executable, str(ROUND / 'scripts/margin_correct.py')]
    for name in ('m10', 'm20', 'target'):
        command += ['--' + name, str(tmp / f'{name}.txt')]
    command += ['--out', str(corrected)]
    proc = subprocess.run(command, text=True, capture_output=True, check=True)
    wrong = result(corrected)
    assert wrong['L0_nH'][0][1] != wrong['L0_nH'][1][0]
    return {'reversed_orientation_accepted_by_both_readers': True,
            'original_M13_nH': data['L_nH'][0][2], 'accepted_M13_nH': accepted[0][2],
            'margin_asymmetric_exit': proc.returncode,
            'margin_asymmetric_matrix_nH': wrong['L0_nH'],
            'margin_claimed_min_eigenvalue_nH': wrong['min_eigenvalue_nH']}


def extraction_checks(tmp: Path) -> dict:
    root = tmp / 'extract'
    root.mkdir()
    mesh = root / 'unrelated.msh'
    mesh.write_text('not a mesh at all\n')
    port_list = [{'physical': 10 + i, 'name': f'P{i+1}_test',
                  'direction': [1., 0., 0.], 'k_A_per_m': 1.} for i in range(2)]
    write_result(mesh.with_suffix('.log'), {'ports': port_list})
    command = [sys.executable, str(ROUND / 'scripts/inductance_matrix.py'), str(mesh)]
    for i, vector in enumerate(([1e-6, 0., 0.], [.5e-6, 1e-6, 0.])):
        run = root / f'p{i}'
        (run / 'mesh').mkdir(parents=True)
        (run / 'case.sif').write_text(f'Boundary Condition 1\n  Target Boundaries(1) = {10+i}\n'
            '  Magnetic Field Strength 1 = Real 1\n  Magnetic Field Strength 2 = Real 0\n'
            '  Magnetic Field Strength 3 = Real 0\n')
        field = np.tile(vector, (4, 1))
        vtu = meshio.Mesh(np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]),
            [('tetra', np.array([[0,1,2,3]]))], point_data={'magnetic flux density e': field})
        meshio.write(run / 'mesh/case.vtu', vtu)
        energy = float(np.dot(vector, vector)) / (6 * 4e-7 * np.pi) * 1e9
        run.with_suffix('.out').write_text(json.dumps({'inductance_nH': energy}) + '\n')
        command += ['--port', str(10+i), str(run)]
    completed = subprocess.run(command, capture_output=True, text=True, check=True)
    data = json.loads(next(s[7:] for s in completed.stdout.splitlines() if s.startswith('RESULT ')))
    assert data['mesh_sha256'] == hashlib.sha256(mesh.read_bytes()).hexdigest()
    return {'invalid_unrelated_mesh_accepted': True, 'exit_code': completed.returncode,
            'result': data}


def campaign_checks(tmp: Path) -> dict:
    campaign = load('campaign', 'scripts/campaign.py')
    root = tmp / 'campaign'
    root.mkdir()
    tag = 'legA-h1-e1p0'
    (root / f'{tag}.msh').write_text('fixture')
    port = {'name': 'P1_C38', 'physical': 10, 'direction': [1, 0, 0], 'k_A_per_m': 1}
    write_result(root / f'{tag}.log', {'tets': 1, 'ports': [port], 'port_leak_A': [{'leak_A': 0}]})
    write_result(root / f'{tag}.columns.txt', {'inner_farfield_triangles': 0})
    write_result(root / f'{tag}.loops.txt', {'ports': [{'closed_loop': True}]})
    write_result(root / f'{tag}-P1_C38.out', {'converged': True, 'inductance_nH': 30,
                 'last_iteration': 100, 'wall_s': 1, 'last_residual': 1e-5})
    solves = []
    def fake_run(cmd, log):
        write_result(log, {'fixture': True})
        return 0
    def fake_subprocess(cmd, **kwargs):
        assert cmd == ['pgrep', '-x', 'ElmerSolver_mpi'], cmd
        return subprocess.CompletedProcess(cmd, 1)
    with patch.object(campaign, 'run', fake_run), patch.object(campaign.subprocess, 'run', fake_subprocess), \
         patch.object(campaign, 'solve_observed', lambda *args: solves.append(args)), contextlib.redirect_stdout(io.StringIO()):
        for tol, elmer in [('1e-4', '/synthetic/solver-a'), ('1e-8', '/synthetic/solver-b')]:
            with patch.object(sys, 'argv', ['campaign.py', str(root), '--cases', '1:1.0', '--elmer', elmer, '--tol', tol]):
                campaign.main()
    status = json.loads((root / 'status.json').read_text())
    assert not solves and status['tol'] == 1e-8 and status['done'][0]['converged']
    return {'old_result_residual': 1e-5, 'new_requested_tolerance': status['tol'],
            'solver_calls': len(solves), 'old_result_reused_and_marked_converged': True,
            'manifest_keys': sorted(json.loads((root / 'manifest-legA.json').read_text()))}


def pair_checks(tmp: Path) -> dict:
    script = (ROUND / 'scripts/pair_check.sh').read_text()
    code = script.split("<<'PY'\n")[2].split('\nPY\n')[0]
    tag = tmp / 'pair'
    write_result(tag.with_suffix('.matrix.txt'), {'ports': ['10', '12'], 'L_nH': [[30, 4], [4, 20]]})
    both = tmp / 'both.out'
    both.write_text(json.dumps({'converged': False, 'exit_code': 1, 'inductance_nH': 58.}) + '\n')
    stdout = io.StringIO()
    with patch.object(sys, 'argv', ['-', str(tag), '10', '12', str(both)]), contextlib.redirect_stdout(stdout):
        exec(compile(code, 'pair_check.sh:comparison', 'exec'), {})
    data = json.loads(stdout.getvalue().split('PAIR ')[1])
    assert data['same_sign'] and data['abs_diff_nH'] == 0
    return {'nonconverged_failed_pair_was_compared': True, 'comparison': data}


def audit_results() -> dict:
    rows = [json.loads(s) for s in (ROUND / 'd2/results/grid-h0-lin12-v2/results.jsonl').read_text().splitlines()]
    summary = grid.summarize(rows)
    old = json.loads((ROUND / 'd2/results/grid-h0-lin12-v2/summary.json').read_text())
    assert json.loads(json.dumps(summary)) == old
    counts = {s: {str(dt): [sum(r['task_pass'] for r in rows if r['case'] == s and r['dt_ns'] == dt),
                            sum(r['case'] == s and r['dt_ns'] == dt for r in rows)] for dt in grid.DT}
              for s in ('S1', 'S2', 'S3', 'S4')}
    assert make_deck5.build() == (ROUND / 'd2/leg_matrix5.cir').read_text()
    a = np.array(result(ROUND / 'results/matrices/legA-h1-e1p0-m10.matrix.txt')['L_nH'])
    b = np.array(result(ROUND / 'results/matrices/legA5-h1-e1p0-m10.matrix.txt')['L_nH'])
    changes = np.abs((b[:4,:4] - a) / a) * 100
    pairs = [json.loads(s[5:]) for s in (ROUND / 'results/pair-check-h1-e1p0.txt').read_text().splitlines()]
    def read_rows(directory: str) -> dict:
        values = [json.loads(s) for s in (ROUND / 'd2/results' / directory / 'results.jsonl').read_text().splitlines()]
        return {(r['case'], r['vbus'], r['il'], r['dir'], r['dt_ns'], r['esl_nH']): r for r in values}
    def compare(left: str, right: str) -> dict:
        x, y = read_rows(left), read_rows(right)
        common = sorted(x.keys() & y.keys())
        return {'cases': len(common), 'pass_left': sum(x[k]['task_pass'] for k in common),
                'pass_right': sum(y[k]['task_pass'] for k in common),
                'verdict_flips': sum(x[k]['task_pass'] != y[k]['task_pass'] for k in common),
                'off_gate_delta_V': [min(y[k]['vgs_off_max']-x[k]['vgs_off_max'] for k in common),
                                     max(y[k]['vgs_off_max']-x[k]['vgs_off_max'] for k in common)],
                'vds_delta_V': [min(y[k]['vds_pk']-x[k]['vds_pk'] for k in common),
                               max(y[k]['vds_pk']-x[k]['vds_pk'] for k in common)]}
    comparisons = {
        'bulk_ab': compare('bulk-ab/a-4port', 'bulk-ab/b-5port-uncoupled'),
        'bulk_bc': compare('bulk-ab/b-5port-uncoupled', 'bulk-ab/c-5port'),
        'bulk_ac': compare('bulk-ab/a-4port', 'bulk-ab/c-5port'),
        'crop': compare('grid-h0-lin12-v2', 'grid-h0-lin12-m20corr'),
        'curved': compare('extrap-test/lin12', 'extrap-test/quad05')}
    return {'case_comparisons': comparisons, 'grid_v2_summary_reproduced': summary, 'grid_v2_counts': counts,
            'generated_deck_matches': True,
            'A5_existing_diagonal_relative_changes_percent': np.diag(changes).tolist(),
            'A5_existing_max_entry_relative_change_percent': float(changes.max()),
            'A5_M34_relative_change_percent': float(changes[2,3]),
            'A5_M34_absolute_change_nH': float(b[2,3] - a[2,3]),
            'A5_min_eigenvalue_nH': float(np.linalg.eigvalsh(b).min()),
            'committed_signed_pair_checks': pairs,
            'committed_bulk_raw_waveforms': len(list((ROUND / 'd2/results/bulk-mode').rglob('waves.raw')))}


def main() -> None:
    files = ['d2/grid.py','d2/run_d2.py','d2/leg_matrix.cir','d2/leg_matrix5.cir','d2/bulk_mode.py',
             'scripts/campaign.py','scripts/inductance_matrix.py','scripts/extrapolate.py',
             'scripts/margin_correct.py','scripts/pair_check.sh','scripts/mesh25d_hybrid.py']
    with tempfile.TemporaryDirectory(dir=HERE) as directory:
        tmp = Path(directory)
        data = {'reviewed_revision': REVISION, 'runtime': {'python': platform.python_version(),
                'numpy': np.__version__, 'meshio': meshio.__version__},
                'scope': 'offline review; synthetic counterexamples do not establish current board errors',
                'source_sha256': {p: hashlib.sha256((ROUND / p).read_bytes()).hexdigest() for p in files},
                'grid': grid_checks(tmp), 'matrix': matrix_checks(tmp),
                'extractor': extraction_checks(tmp), 'campaign': campaign_checks(tmp),
                'pair': pair_checks(tmp), 'actual_results': audit_results()}
    print(json.dumps(data, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
