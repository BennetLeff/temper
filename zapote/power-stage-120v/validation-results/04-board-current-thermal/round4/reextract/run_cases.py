#!/usr/bin/env python3
"""Reproduce A4's stated boundary-condition experiments, one net at a time."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
THIRD = '6.233333333333333'

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
    ('sw_b_high', 'sw_b', ['Q5.3:18.7'], [], ['C21.2', 'C22.2', 'C23.2'], '18.7 A tank path, B high-side state; capacitor sink equipotential'),
    ('sw_b_low', 'sw_b', [f'C21.2:{THIRD}', f'C22.2:{THIRD}', f'C23.2:{THIRD}'], [], ['Q6.2'], '18.7 A tank path, B low-side state; equal capacitor sources'),
    ('res_a', 'res_a', [f'C21.1:{THIRD}', f'C22.1:{THIRD}', f'C23.1:{THIRD}'], [], ['J5.1'], '18.7 A bank-to-J5 path; equal capacitor sources'),
    ('coil_feed', 'coil_feed', ['T1.2:18.7'], [], ['J2.1'], '18.7 A T1-to-J2 path'),
]

PLATING_12 = {'bus_dc_q2', 'bus_mixed_q2', 'bus_mixed_q5', 'hv_dc', 'hv_mixed_a',
              'hv_mixed_b', 'leg_a_18p7', 'leg_b_18p7', 'sw_a', 'sw_b_high',
              'sw_b_low', 'res_a', 'coil_feed'}


def main() -> int:
    manifest=[]
    failed=[]
    for name, net, sources, draws, sinks, description in CASES:
        for plating in ((18, 12) if name in PLATING_12 else (18,)):
            label=f'{name}-p0125-pl{plating}'
            cmd=[sys.executable,str(HERE/'run_board.py'),'--net',net,'--name',label,
                 '--pitch','0.125','--plating',str(plating)]
            for source in sources:
                cmd.extend(('--source',source))
            for draw in draws:
                cmd.extend(('--draw',draw))
            for sink in sinks:
                cmd.extend(('--sink',sink))
            row={'name':label,'net':net,'description':description,'sources':sources,
                 'explicit_draws':draws,'reference_sinks':sinks,'plating_um':plating}
            run=subprocess.run(cmd,cwd=HERE,capture_output=True,text=True,env={
                **os.environ,'OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1'})
            row['exit_code']=run.returncode
            row['stdout']=run.stdout.strip()
            row['stderr']=run.stderr[-2000:]
            manifest.append(row)
            print(label,run.stdout.strip(),flush=True)
            if run.returncode:
                failed.append(label)
    (HERE/'outputs'/'cases.json').write_text(json.dumps({'cases':manifest,'failed':failed},indent=2)+'\n')
    return 1 if failed else 0


if __name__=='__main__':
    raise SystemExit(main())
