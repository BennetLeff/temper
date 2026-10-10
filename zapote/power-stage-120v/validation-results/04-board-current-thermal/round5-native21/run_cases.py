#!/usr/bin/env python3
"""Task 04 round 5: A4's boundary-condition experiments on native-21 copper.

Same cases as round 4 (every pad and net carries over), plus the two mains-entry cases.
Pitch per net from the topology preflight: 0.125 mm matches physical components except on
leg_ret / sw_a / sw_b / hv_ret, whose 0.15 mm via rings fragment at that pitch; those run at
0.0625 mm (outputs/kit_topology_p00625.json).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
# stage 15: the bank is 5 x TDK B32654 (C21-C23, C151, C152, stage 13); the tank cases share across all five
FIFTH = '3.74'
BANK = ('C21', 'C22', 'C23', 'C151', 'C152')

# Currents are assumed, conditional resistive experiments. Their signed
# operating waveforms and capacitor sharing have not been measured.
CASES = [
    ('bus_dc_q2', 'bus_p', ['J8.1:15'], [], ['Q2.2'], '15 A west replenishment'),
    ('bus_dc_q5', 'bus_p', ['J8.1:15'], [], ['Q5.2'], '15 A west replenishment, opposite leg'),
    ('bus_hf_q2', 'bus_p', ['C38.1:9.5', 'C39.1:9.5'], [], ['Q2.2'], '19 A local HF share, equally split capacitors'),
    ('bus_hf_q5', 'bus_p', ['C40.1:9.5', 'C41.1:9.5'], [], ['Q5.2'], '19 A local HF share, equally split capacitors'),
    ('bus_mixed_q2', 'bus_p', ['J8.1:15', 'C38.1:9.5', 'C39.1:9.5'], [], ['Q2.2'], '15+19 A coherent DC/HF experiment'),
    ('bus_mixed_q5', 'bus_p', ['J8.1:15', 'C40.1:9.5', 'C41.1:9.5'], [], ['Q5.2'], '15+19 A coherent DC/HF experiment, opposite leg'),
    ('hv_dc', 'hv_ret', ['R5.4:15'], [], ['J10.1'], '15 A shunt-to-west return'),
    ('hv_hf_a', 'hv_ret', ['R5.4:19'], [], ['C38.2', 'C39.2'], '19 A return to A local capacitor pair, equipotential sinks'),
    ('hv_hf_b', 'hv_ret', ['R5.4:19'], [], ['C40.2', 'C41.2'], '19 A return to B local capacitor pair, equipotential sinks'),
    ('hv_mixed_a', 'hv_ret', ['R5.4:34'], ['C38.2:9.5', 'C39.2:9.5'], ['J10.1'], '15 A west and 19 A local A return, coherent'),
    ('hv_mixed_b', 'hv_ret', ['R5.4:34'], ['C40.2:9.5', 'C41.2:9.5'], ['J10.1'], '15 A west and 19 A local B return, coherent'),
    ('leg_a_18p7', 'leg_ret', ['Q3.3:18.7'], [], ['R5.1'], '18.7 A low-side A path'),
    ('leg_b_18p7', 'leg_ret', ['Q6.3:18.7'], [], ['R5.1'], '18.7 A low-side B path'),
    ('leg_a_15', 'leg_ret', ['Q3.3:15'], [], ['R5.1'], '15 A leg A DC component experiment'),
    ('leg_a_19', 'leg_ret', ['Q3.3:19'], [], ['R5.1'], '19 A leg A HF component experiment'),
    ('leg_a_34', 'leg_ret', ['Q3.3:34'], [], ['R5.1'], '34 A coherent leg A experiment'),
    ('leg_b_34', 'leg_ret', ['Q6.3:34'], [], ['R5.1'], '34 A coherent leg B experiment'),
    ('sw_a', 'sw_a', ['Q2.3:18.7'], [], ['T1.1'], '18.7 A tank path, A high-side state'),
    # stage 15: the A low-side state (Q3 conducting) reaches T1 through the B.Cu leg-A link over Q3.S / Q2.D
    ('sw_a_low', 'sw_a', ['Q3.2:18.7'], [], ['T1.1'], '18.7 A tank path, A low-side state'),
    ('sw_b_high', 'sw_b', ['Q5.3:18.7'], [], [f'{c}.2' for c in BANK], '18.7 A tank path, B high-side state; capacitor sink equipotential'),
    ('sw_b_low', 'sw_b', [f'{c}.2:{FIFTH}' for c in BANK], [], ['Q6.2'], '18.7 A tank path, B low-side state; equal capacitor sources'),
    ('res_a', 'res_a', [f'{c}.1:{FIFTH}' for c in BANK], [], ['J5.1'], '18.7 A bank-to-J5 path; equal capacitor sources'),
    ('coil_feed', 'coil_feed', ['T1.2:18.7'], [], ['J2.1'], '18.7 A T1-to-J2 path'),
]

PLATING_12 = {'bus_dc_q2', 'bus_mixed_q2', 'bus_mixed_q5', 'hv_dc', 'hv_mixed_a',
              'hv_mixed_b', 'leg_a_18p7', 'leg_b_18p7', 'sw_a', 'sw_a_low', 'sw_b_high',
              'sw_b_low', 'res_a', 'coil_feed'}


FINE = {'leg_ret', 'sw_a', 'sw_b', 'hv_ret'}


def one(job):
    name, net, sources, draws, sinks, description, plating = job
    pitch = '0.0625' if net in FINE else '0.125'
    label = f"{name}-p{pitch.replace('.', '')}-pl{plating}"
    cmd = [sys.executable, str(HERE / 'run_board.py'), '--net', net, '--name', label,
           '--pitch', pitch, '--plating', str(plating)]
    for source in sources:
        cmd.extend(('--source', source))
    for draw in draws:
        cmd.extend(('--draw', draw))
    for sink in sinks:
        cmd.extend(('--sink', sink))
    row = {'name': label, 'net': net, 'pitch_mm': float(pitch), 'description': description, 'sources': sources,
           'explicit_draws': draws, 'reference_sinks': sinks, 'plating_um': plating}
    run = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, env={
        **os.environ, 'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'})
    row['exit_code'] = run.returncode
    row['stdout'] = run.stdout.strip()
    row['stderr'] = run.stderr[-2000:]
    print(label, run.stdout.strip(), flush=True)
    return row


def main() -> int:
    cases = CASES + [
        ('ac_n_main', 'ac_n_in', ['J1.2:15'], [], ['L1.2'], '15 A neutral entry'),
        ('ac_l_main', 'ac_l_in', ['J1.1:15'], [], ['F1.1'], '15 A line entry')]
    jobs = [(*c, pl) for c in cases for pl in ((18, 12) if c[0] in PLATING_12 else (18,))]
    with ThreadPoolExecutor(int(os.environ.get('WORKERS', '6'))) as ex:
        manifest = list(ex.map(one, jobs))
    failed = [r['name'] for r in manifest if r['exit_code']]
    (HERE / 'outputs' / 'cases.json').write_text(json.dumps({'cases': manifest, 'failed': failed}, indent=2) + '\n')
    return 1 if failed else 0


if __name__=='__main__':
    raise SystemExit(main())
