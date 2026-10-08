"""Extract actual driver rail currents from all 504 ideal-bias F6 cases.

Run after sim-kit model fetch/hash verification and smoke_test.py. This uses
the physical 1 ohm discharge resistor and the selected PMEG diode. Observing
voltage sources copy the two conductance-branch currents without loading the
switching circuit. Negative current includes signed Miller displacement.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

import numpy as np

import rail_campaign as campaign

HERE = Path(__file__).resolve().parent
F6 = campaign.f6


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--bias', type=float, default=-1.6)
    parser.add_argument('--selected', action='store_true', help='Reuse worst waveform indices from the full -1.6 V screen')
    args = parser.parse_args()
    out = HERE / ('edge-current' if args.bias == -1.6 else f'edge-current-{abs(args.bias):g}V')
    out.mkdir(exist_ok=True)
    (out / '.gitignore').write_text('runs/\nwaveforms.npz\n')
    deck = (F6.D13 / 'decks/F6.cir').read_text()
    deck = deck.replace('.include params.inc', '.include params.inc\n.options itl4=100000')
    deck = deck.replace('-(-2))', f'-({args.bias}))').replace('1.34482758621', '1.0')
    deck = deck.replace('.model D6D D(Is=1u N=1 Rs=0.05 Cjo=20p Tt=0)\nDoffl gdl3 offl D6D',
                        f'.include {F6.PMEG}\nXDoffl gdl3 offl PMEG6030EP')
    deck = deck.replace('Doffh gdh3 offh D6D', 'XDoffh gdh3 offh PMEG6030EP')
    monitors = []
    for side, source in (('l', 's_ls'), ('h', 'sw')):
        monitors.extend([
            f'Bneg{side} neg{side} 0 V={{(v(gd{side},{source})-({args.bias}))*(1-v(g{side}_cmd,{source})/VDRV)/ROL}}',
            f'Bpos{side} pos{side} 0 V={{(VDRV-v(gd{side},{source}))*v(g{side}_cmd,{source})/(VDRV*ROH)}}',
        ])
    deck = deck.replace('.end', '\n'.join(monitors) + '\n.save v(negl) v(negh) v(posl) v(posh)\n.end')
    (out / 'F6.cir').write_text(deck)
    F6.OUT = out
    F6.MATRICES['B'] = F6.HERE / 'legB-h0-corr-n19.matrix.txt'
    original = F6.run_d2.run

    def with_raw(*a, **kw):
        return original(*a, **kw, raw=True)

    F6.run_d2.run = with_raw
    jobs = F6.jobs((27, 100, 150)) + F6.jobs((27, 100, 150), 'startup')
    if args.selected:
        selected = json.loads((HERE/'rail-qualified/selected-waveforms.json').read_text())
        indices = sorted({pair[0] for pair in selected})
        jobs = [jobs[i] for i in indices]
    if args.limit:
        jobs = jobs[:args.limit]
    # Fixed grid avoids ragged archives; include the entire edge window.
    time = np.arange(0, 1.301e-6, .2e-9)

    def one(job):
        row = F6.one(job)
        leg, temp, (case, vbus, il, dt), direction, esl = job
        name = f'{leg}_T{temp}_{case}_v{vbus}_i{il}_d{direction}_dt{dt}_esl{esl}'
        # Import the parser from the same sim-kit module that owns run().
        from run_ngspice import read_raw
        waves = read_raw(out / 'runs' / name / 'waves.raw')
        if row['status'] != 'complete' or waves['time'][-1] < (2e-6+dt*1e-9+.75e-6):
            raise RuntimeError(f'incomplete extraction: {name}')
        currents = np.array([np.interp(time+2e-6, waves['time'], waves[f'v({key})'])
                             for key in ('negl', 'negh', 'posl', 'posh')])
        row.update(name=name, peak_negative_A=float(currents[:2].max()),
                   charge_negative_C=[float(np.trapezoid(np.maximum(x, 0), time)) for x in currents[:2]])
        (out / 'runs' / name / 'waves.raw').unlink()
        print(name, row['pass_hot'], flush=True)
        return row, currents

    with ThreadPoolExecutor(args.workers) as pool:
        extracted = list(pool.map(one, jobs))
    rows, waveforms = zip(*extracted)
    np.savez_compressed(out / 'waveforms.npz', time=time, currents=np.array(waveforms))
    (out / 'results.json').write_text(json.dumps(rows, indent=2)+'\n')
    summary = {'cases': len(rows), 'hot_pass': sum(r['pass_hot'] for r in rows),
               'maximum_off_gate_V': max(r['off_V'] for r in rows),
               'maximum_negative_current_A': max(r['peak_negative_A'] for r in rows),
               'maximum_positive_negative_charge_C': max(max(r['charge_negative_C']) for r in rows),
               'inputs_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (Path(__file__), out/'F6.cir', *F6.MATRICES.values(), F6.PMEG)}}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))
    if not all(r['pass_hot'] for r in rows):
        raise SystemExit('Physical 1 ohm switching check failed')


if __name__ == '__main__':
    main()
