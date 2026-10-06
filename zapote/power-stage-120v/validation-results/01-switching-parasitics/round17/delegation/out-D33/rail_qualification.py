"""Standalone TLVH431 rail qualification, separate from switching physics.

220 uF polymer through 0.68 ohm damps the shunt loop; local ceramic bank is
10..24 uF effective plus 2 x 1 uF and 4 x 100 nF. Full TI nonlinear macro, with explicit
engineering sensitivity factors on gm and each pole (not vendor limits).
Reference extremes include the BQ full-temperature range and VKA slope.
Usage: --loop, --periodic, --edges (requires edge_currents.py output).
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np

import rail_campaign

HERE = Path(__file__).resolve().parent
OUT = HERE / 'rail-qualified'


@dataclass(frozen=True)
class Corner:
    bulk_u: float = 220
    local_u: float = 20
    bulk_r: float = .707
    local_r: float = .02
    local_l_n: float = .25
    mid_u: float = 2
    mid_r: float = .05
    mid_l_n: float = .25
    hf_u: float = .4
    hf_r: float = .025
    hf_l_n: float = .05
    gm: float = 4
    pole1: float = 1
    pole2: float = 1
    ref: float = 1.24
    banks: int = 1
    span: float = 15.5


def loop(c: Corner) -> dict:
    f = np.geomspace(1, 1e8, 60000)
    s = 2j*np.pi*f
    y = c.banks/4990 + 1/16120 + 1/14420 + 1/17620 + c.banks/10000 + c.banks*(
        1/(c.bulk_r+s*10e-9+1/(s*c.bulk_u*1e-6)) +
        1/(c.local_r+s*c.local_l_n*1e-9+1/(s*c.local_u*1e-6)) +
        1/(c.mid_r+s*c.mid_l_n*1e-9+1/(s*c.mid_u*1e-6)) +
        1/(c.hf_r+s*c.hf_l_n*1e-9+1/(s*c.hf_u*1e-6)))
    gain = (c.gm*10000/16120)/((1+s*159e-6*c.pole1)*(1+s*80e-9*c.pole2)*y)
    crossings = np.flatnonzero(np.diff((abs(gain)>1).astype(int)))
    if not len(crossings):
        raise ValueError('No loop unity crossing in frequency range')
    phase = np.unwrap(np.angle(gain))*180/np.pi
    return {'corner': asdict(c), 'crossing_Hz': f[crossings].tolist(),
            'phase_margin_deg': (180+phase[crossings]).tolist()}


def corners() -> list[Corner]:
    return [Corner(bulk_u=bulk, local_u=local, bulk_r=r,
                   local_r=.04, local_l_n=.5, mid_u=local/10, mid_r=.1, mid_l_n=.5,
                   hf_u=.32, hf_r=.05, hf_l_n=.1,
                   gm=gm, pole1=p1, pole2=p2, ref=1.2188, banks=banks)
            for bulk, local, r, gm, p1, p2, banks in itertools.product(
                (140.8, 316.8), (10, 24), (.67, 1.1), (2, 8), (.5, 2), (.5, 2), (1, 2))]


def network(c: Corner) -> str:
    # Keep licensed macro derivatives in ignored .models only.
    original = rail_campaign.model().read_text()
    original = original.replace('N59715 A 1.24', f'N59715 A {c.ref}')
    original = original.replace('Fdbk N59715 4', f'Fdbk N59715 {c.gm}')
    original = original.replace('159e-6', str(159e-6*c.pole1)).replace('80n  ', f'{80e-9*c.pole2}  ')
    private = HERE / '.models' / f'rail-{c.ref}-{c.gm}-{c.pole1}-{c.pole2}.lib'
    # Written once in main before starting any parallel simulations.
    if not private.exists() or private.read_text() != original:
        private.write_text(original)
    return f""".include {private}
* Span lower than the rail-monitor enable window; includes regulator variation.
Vspan raw n {c.span}
Ispan p n {0.014 + .0044*c.banks}
Rsp raw p 1
Cspan p n {10*c.banks}u
Rbleed p 0 {4990/c.banks}
Rtop 0 fb 6113.88
Rbot fb n 10010
Rmonitoruv 0 n 14420
Rmonitorov 0 n 17620
Rhold 0 n {10000/c.banks}
Ipolymer 0 n {300e-6*c.banks}
Xsh n cath fb TLVH431
Vsense 0 cath 0
Lbulk n be {10e-9/c.banks}
Rbulk be bc {c.bulk_r/c.banks}
Cbulk bc 0 {c.bulk_u*c.banks}u
Llocal n le {c.local_l_n/c.banks}n
Rlocal le lc {c.local_r/c.banks}
Clocal lc 0 {c.local_u*c.banks}u
Lmid n me {c.mid_l_n/c.banks}n
Rmid me mc {c.mid_r/c.banks}
Cmid mc 0 {c.mid_u*c.banks}u
Lhf n he {c.hf_l_n/c.banks}n
Rhf he hc {c.hf_r/c.banks}
Chf hc 0 {c.hf_u*c.banks}u
.options method=gear reltol=1e-3 abstol=1e-9 vntol=1e-6 itl4=1000 gmin=1e-10
"""


def simulate(name: str, circuit: str, retry: bool = True) -> dict:
    work = OUT / 'runs' / name
    work.mkdir(parents=True, exist_ok=True)
    (work/'rail.cir').write_text('* D33 standalone negative rail\n'+circuit+'\n.end\n')
    (work/'.spiceinit').write_text('set ngbehavior=psa\n')
    proc = subprocess.run(['/opt/homebrew/bin/ngspice', '-b', 'rail.cir'], cwd=work,
                          capture_output=True, text=True, timeout=180)
    log = proc.stdout+proc.stderr
    (work/'run.log').write_text(log)
    meas = {m[1]: float(m[2]) for m in re.finditer(r'^([a-z][a-z0-9_]*)\s*=\s*([-+0-9.eE]+)', log, re.M)}
    complete = proc.returncode == 0 and not re.search('timestep too small|aborted|failed', log, re.I)
    complete = complete and all(k in meas for k in ('negmax', 'negmin', 'shuntmin', 'shuntmax'))
    if not complete and retry:
        result = simulate(name+'-klu', circuit+'\n.options klu\n', retry=False)
        result['name'] = name
        result['solver'] = 'KLU'
        result['default_solver_complete'] = False
        return result
    if complete:
        shutil.rmtree(work)  # Reproducible temporary deck/log; measurements retained below.
    return {'name': name, 'complete': complete, 'measurements': meas,
            'pass': complete and meas['negmax'] < -1.6 and meas['shuntmin'] > 0 and meas['shuntmax'] < .07}


def periodic(c: Corner, frequency: int, net: str) -> str:
    period = 1/frequency
    # 740 nC/8 A exceeds both extracted bias-voltage corners; periodic stress,
    # not an assertion that every hard-switching event repeats continuously.
    return net+f"""Ipull p 0 PULSE(0 {8*c.banks} 10u 5n 5n 87.5n {period})
Idump 0 n PULSE(0 {8*c.banks} {10e-6+period/2} 5n 5n 87.5n {period})
.tran 5n 4m 0 5n
.meas tran negmax_global MAX v(n) from=10u to=4m
.meas tran negmin MIN v(n) from=10u to=4m
.meas tran shuntmin MIN i(Vsense) from=10u to=4m
.meas tran shuntmax MAX i(Vsense) from=10u to=4m
.control
run
let phase = time-{10e-6+period/2}-floor((time-{10e-6+period/2})/{period})*{period}
let rail_window = (v(n)+10)*(phase ge 391n)*(phase le 1.248u)*(time gt {10e-6+period/2})-10
meas tran negmax MAX rail_window
.endc
"""


def edge(c: Corner, time: np.ndarray, currents: np.ndarray, side: int, dt: int, net: str) -> str:
    lines = [net]
    delay = 50e-9
    # Preserve signed currents and 0.2 ns samples; no clipping/smoothing.
    for name, nodes, data in [('Ipull', 'p 0', currents[side+2]), ('Idump', '0 n', currents[side])]:
        # DC operating point must describe the energized idle rail, not hold
        # an instantaneous Miller current indefinitely during the OP solve.
        lines.append(f'{name} {nodes} PWL(0 0 {delay-.2e-9} 0')
        lines.extend(f'+ {t+delay:.12g} {i*c.banks*1.1:.12g}' for t, i in zip(time, data))
        lines.append('+ )')
    lines.append(f'''.tran .05n {time[-1]+delay} 0 .05n
.meas tran negmax MAX v(n) from={delay+dt*1e-9} to={delay+dt*1e-9+.75e-6}
.meas tran negmin MIN v(n) from={delay+dt*1e-9} to={delay+dt*1e-9+.75e-6}
.meas tran shuntmin MIN i(Vsense)
.meas tran shuntmax MAX i(Vsense)''')
    return '\n'.join(lines)


def main() -> None:
    global OUT
    parser = argparse.ArgumentParser()
    parser.add_argument('--loop', action='store_true')
    parser.add_argument('--periodic', action='store_true')
    parser.add_argument('--hot-load', action='store_true')
    parser.add_argument('--edges', action='store_true')
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--waveforms', default='edge-current')
    parser.add_argument('--output', default='rail-qualified')
    parser.add_argument('--span', type=float, default=15.5)
    args = parser.parse_args()
    OUT = HERE / args.output
    OUT.mkdir(exist_ok=True)
    (OUT/'.gitignore').write_text('runs/\n')
    from dataclasses import replace
    all_corners = [replace(c, span=args.span) for c in corners()]
    if args.loop:
        rows = [loop(c) for c in all_corners]
        result = {'nominal': loop(Corner()), 'corners': rows,
                  'minimum_margin_deg': min(min(r['phase_margin_deg']) for r in rows),
                  'limits': 'gm/pole factors 0.5..2 are engineering sensitivities, not manufacturer temperature bounds'}
        (OUT/'loop.json').write_text(json.dumps(result, indent=2)+'\n')
        print('minimum phase margin', result['minimum_margin_deg'], flush=True)
        if result['minimum_margin_deg'] < 45:
            raise SystemExit('Phase margin below 45 degrees')
    # Reuse immutable model files; no concurrent writer to a model file.
    networks = {c: network(c) for c in [Corner(span=args.span), *all_corners]}
    if args.periodic or args.hot_load:
        label = 'hot-load' if args.hot_load else 'periodic'
        jobs = [(f'{label}-{i}-{freq}', periodic(c, freq, networks[c] + ('Ihot p 0 .030\n' if args.hot_load else '')))
                for i, c in enumerate(all_corners) for freq in (33000, 80000)
                if not args.hot_load or c.banks == 2]
        with ThreadPoolExecutor(args.workers) as pool:
            rows = list(pool.map(lambda job: simulate(*job), jobs))
        (OUT/f'{label}.json').write_text(json.dumps(rows, indent=2)+'\n')
        print(label, len(rows), 'pass', sum(r['pass'] for r in rows), flush=True)
        if not all(r['pass'] for r in rows):
            raise SystemExit('Periodic corner campaign did not pass')
    if args.edges:
        meta = json.loads((HERE/args.waveforms/'results.json').read_text())
        data = np.load(HERE/args.waveforms/'waveforms.npz')
        time, currents = data['time'], data['currents']
        nominal = Corner(span=args.span)
        jobs = [(i, side) for i in range(len(meta)) for side in (0, 1)]
        def run_nominal(job):
            i, side = job
            return simulate(f'edge-{i}-{side}', edge(nominal, time, currents[i], side, meta[i]['dt_ns'], networks[nominal]))
        with ThreadPoolExecutor(args.workers) as pool:
            rows = list(pool.map(run_nominal, jobs))
        (OUT/'edge-screen.json').write_text(json.dumps(rows, indent=2)+'\n')
        print('edge screen', len(rows), 'pass', sum(r['pass'] for r in rows), flush=True)
        if not all(r['complete'] for r in rows):
            raise SystemExit('An edge screening case did not complete')
        # Select by actual rail response and independently by peak/charge/slew.
        selected = {tuple(map(int, r['name'].split('-')[1:])) for r in
                    sorted(rows, key=lambda r: r['measurements']['negmax'], reverse=True)[:8]}
        for metric in (currents[:,:2].max(axis=2),
                       np.trapezoid(np.maximum(currents[:,:2], 0), time, axis=2),
                       np.abs(np.diff(currents[:,:2], axis=2)).max(axis=2)):
            selected.update(tuple(map(int, np.unravel_index(i, metric.shape))) for i in np.argsort(metric.ravel())[-8:])
        (OUT/'selected-waveforms.json').write_text(json.dumps(sorted(selected), indent=2)+'\n')
        # Corner sweep of worst waveforms. Circuit strings generated lazily.
        jobs = [(j, i, side) for j in range(len(all_corners)) for i, side in sorted(selected)]
        def run_corner(job):
            j, i, side = job
            c = all_corners[j]
            return simulate(f'corner-{j}-{i}-{side}', edge(c, time, currents[i], side, meta[i]['dt_ns'], networks[c]))
        with ThreadPoolExecutor(args.workers) as pool:
            rows = list(pool.map(run_corner, jobs))
        (OUT/'edge-corners.json').write_text(json.dumps(rows, indent=2)+'\n')
        print('edge corners', len(rows), 'pass', sum(r['pass'] for r in rows), flush=True)
        if not all(r['pass'] for r in rows):
            raise SystemExit('Edge corner campaign did not pass')


if __name__ == '__main__':
    main()
