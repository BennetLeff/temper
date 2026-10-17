"""F3 guard trade-offs through the C drivers/check (DECISIONS.md D-SOAKTAU).

Run manually: python3 cold_soak_guards.py --out /absolute/scratch/directory
Builds temporary libraries from the pinned pre-F3 C check, changing one guard
at a time. Uses cold_soak.py's trajectories, noise seeds and hazard weighting;
no gate, recorded expectation, or production threshold is changed by this study.
The 2399 s hazard evaluation stays fixed: delaying a check is lost coverage there.
CSV/text evidence goes only to --out; no tracked JSON is regenerated.
"""
import argparse
import csv
import json
import math
import subprocess
import sys
import tempfile
import zlib
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = 'ebf8a777b50ecb81040fc0c56fa8bde706720638'
OUT = None
sys.path.insert(0, str(HERE))
import cold_soak as CS  # noqa: E402

EXTRA_RESIDUAL = 1.0 / math.expm1(900 / 3600) - 1.0 / math.expm1(900 / 1800)
CANDIDATES = {
    'baseline': None,
    'off_2tau_7200': ('p->soak_n_s = PCS_SOAK_N_S;', 'p->soak_n_s = 7200.0f;'),
    'off_4tau_14400': ('p->soak_n_s = PCS_SOAK_N_S;', 'p->soak_n_s = 14400.0f;'),
    'flat_tau3600': ('p->hs_flat_k = PCS_HS_FLAT_K;', f'p->hs_flat_k = {CS.H.residual(1.0) * math.expm1(900 / 3600):.9f}f;'),
    'rate_002': ('    if (hs_hi - hs_lo > p->hs_flat_k) {', '''    const pcs_bucket_t *previous = &s->b[(s->head + PCS_BUCKET_MAX - 1u) % PCS_BUCKET_MAX];
    const float span_s = (float)(uint32_t)(previous->t0_ms - oldest->t0_ms) / 1000.0f;
    const float drift = 0.5f * ((previous->hs_min + previous->hs_max) - (oldest->hs_min + oldest->hs_max));
    if (span_s > 0.0f && fabsf(drift) > (0.02f / 60.0f) * span_s) {
        r.verdict = PCS_SKIP_HS_DRIFT;
        return r;
    }
    if (hs_hi - hs_lo > p->hs_flat_k) {'''),
    'pt_floor_4': ('    if (!rim_saturated) {', '''    if (pt_c < 4.0f || pt_lo < 4.0f) {
        r.verdict = PCS_SKIP_PT_INVALID;
        return r;
    }
    if (!rim_saturated) {'''),
    'pt_floor_6': ('    if (!rim_saturated) {', '''    if (pt_c < 6.0f || pt_lo < 6.0f) {
        r.verdict = PCS_SKIP_PT_INVALID;
        return r;
    }
    if (!rim_saturated) {'''),
    'threshold_tau3600': ('p->threshold_k = PCS_THRESHOLD_K;\n    p->threshold_measured_k = PCS_THRESHOLD_MEASURED_K;', f'p->threshold_k = PCS_THRESHOLD_K + {EXTRA_RESIDUAL:.9f}f;\n    p->threshold_measured_k = PCS_THRESHOLD_MEASURED_K + {EXTRA_RESIDUAL:.9f}f;'),
}
LIBS = {}

def build():
    src = subprocess.check_output(
        ['git', 'show', BASE + ':firmware/components/control/pan_cold_soak.c'], cwd=ROOT, text=True)
    script = (HERE / 'build_lib.sh').read_text().replace('here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)', f'here="{HERE}"')
    for name, edit in CANDIDATES.items():
        target = OUT / name
        target.mkdir(exist_ok=True)
        modified = src
        if edit:
            assert src.count(edit[0]) == 1
            modified = src.replace(*edit)
        (target / 'pan_cold_soak.c').write_text(modified)
        bs = script.replace('"$fw/pan_cold_soak.c"', f'"{target}/pan_cold_soak.c"')
        (target / 'build.sh').write_text(bs)
        subprocess.run(['sh', str(target / 'build.sh'), str(target)], check=True, stdout=subprocess.DEVNULL)
        print(f'BUILT {name}', flush=True)

def initialize(directory):
    global OUT
    OUT = Path(directory)


def select(name):
    if name not in LIBS:
        CS._L = None
        LIBS[name] = CS.lib(str(OUT / name / 'libpantemp.so'))
    CS._L = LIBS[name]

def benign(job):
    group, kind, p, corner, variant = job
    hs, pt, gl, coil = CS.traj(kind, p)
    seed = zlib.crc32(repr((kind, sorted(p.items()), corner)).encode())
    result = []
    for name in CANDIDATES:
        select(name)
        rows = CS.run_traj(hs, pt, gl, coil, corner, variant, 0.0, seed=seed)
        leaked = rows[rows[:, 1] == 2]
        ran = rows[(rows[:, 1] == 1) | (rows[:, 1] == 2)]
        r = {'candidate': name, 'group': group, 'kind': kind, 'parameters': p, 'corner': corner, 'rail': variant,
                 'evaluations': len(rows), 'ran': len(ran), 'latches': len(leaked)}
        if len(leaked):
            for label, row in [('first', leaked[0]), ('max_gap', leaked[np.argmax(leaked[:, 2])])]:
                r[label] = dict(zip(('time_s', 'verdict', 'window_gap_K', 'hs_state', 'hs_C', 'pt_C'), map(float, row), strict=False))
                r[label]['instant_gap_K'] = float(row[4] - row[5])
        result.append(r)
    return result

def hazard(job):
    v, c, family, a, rr, n = job
    results = []
    for name in CANDIDATES:
        select(name)
        _, r = CS.hazard_job((v, c, family, a, rr, 0.0))
        results.append(dict(candidate=name, rail=v, corner=c, family=family, ambient=a, r_hot=rr, weight=n, **r))
    return results

def main():
    global OUT
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--jobs', type=int, default=4)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cold-soak-guards-') as directory:
        OUT = Path(directory)
        build()
        study(args.out, args.jobs)


def study(destination, workers):
    gated, reported = CS.benign_cases()
    # Keep the pre-F3 partitions when cold_soak.py promotes the slow-sink set.
    reported = [(k, p) for k, p in gated if p.get('tau_h') == 3600.0] + reported
    gated = [(k, p) for k, p in gated if p.get('tau_h') != 3600.0]
    jobs = [(g, k, p, c, v) for g, sets in [('gated', gated), ('reported', reported)]
            for k, p in sets for c in CS.CORNERS for v in CS.VARIANTS]
    print(f'BENIGN jobs={len(jobs)} candidates={len(CANDIDATES)}', flush=True)
    results = []
    with Pool(workers, initializer=initialize, initargs=(str(OUT),)) as pool:
        for i, group in enumerate(pool.imap(benign, jobs, chunksize=2)):
            results.extend(group)
            if i % 100 == 0:
                print(f'BENIGN completed={i}/{len(jobs)}', flush=True)
    print('BENIGN DONE', flush=True)
    lc = json.loads((HERE / 'leak-checks.json').read_text())
    haz = [r for r in lc['leak_rows'] if CS.LC.hazardous(r)]
    by_r = Counter(r['r_leak_ohm'] for r in haz)
    jobs = [(v, c, f, a, rr, n) for v in CS.VARIANTS for c in ('nominal', 'miss')
            for f in ('independent',) + tuple(map(str, CS.EA_EV)) for a in CS.AMBIENTS for rr, n in by_r.items()]
    with Pool(workers, initializer=initialize, initargs=(str(OUT),)) as pool:
        coverage = [r for group in pool.map(hazard, jobs, chunksize=4) for r in group]
    print(f'HAZARDOUS runs={len(haz)} cells={len(jobs)}', flush=True)
    benign_summary, coverage_summary = [], []
    for name in CANDIDATES:
        for v in CS.VARIANTS:
            for g in ('gated', 'reported'):
                selected = [r for r in results if r['candidate'] == name and r['rail'] == v and r['group'] == g]
                counts = {k: (sum(r['latches'] > 0 for r in selected if r['kind'] == k), sum(r['kind'] == k for r in selected)) for k in sorted({r['kind'] for r in selected})}
                print(f'BENIGN {name} {v} {g} latched/trajectories={counts}')
                for kind, (latched, total) in counts.items():
                    benign_summary.append({'candidate': name, 'rail': v, 'group': g, 'kind': kind,
                                               'latched_trajectories': latched, 'trajectories': total})
            for c in ('nominal', 'miss'):
                for f in ('independent',) + tuple(map(str, CS.EA_EV)):
                    counts = [sum(r['weight'] for r in coverage if r['candidate'] == name and r['rail'] == v and r['corner'] == c and r['family'] == f and r['ambient'] == a and r['caught_by']) for a in CS.AMBIENTS]
                    print(f'COVERAGE {name} {v} {c} {f} {counts} / {len(haz)}')
                    coverage_summary.append(dict(candidate=name, rail=v, corner=c, family=f,
                                                 **{str(a): n for a, n in zip(CS.AMBIENTS, counts, strict=False)},
                                                 hazardous=len(haz)))
    false_latches = []
    for r in results:
        if r['candidate'] == 'baseline' and r['latches']:
            print('FALSE_LATCH ' + json.dumps(r, sort_keys=True))
            for check in ('first', 'max_gap'):
                false_latches.append(dict(rail=r['rail'], kind=r['kind'], corner=r['corner'],
                                          parameters=json.dumps(r['parameters'], sort_keys=True),
                                          check=check, **r[check]))
    for filename, rows in [('benign.csv', benign_summary), ('coverage.csv', coverage_summary),
                           ('false-latches.csv', false_latches)]:
        with (destination / filename).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    baseline = {(r['rail'], r['corner'], r['family'], r['ambient'], r['r_hot']): r
                for r in coverage if r['candidate'] == 'baseline'}
    for name in CANDIDATES:
        losses = [r for r in coverage if r['candidate'] == name
                  and baseline[(r['rail'], r['corner'], r['family'], r['ambient'], r['r_hot'])]['caught_by']
                  and not r['caught_by']]
        print(f'LOST_HAZARD_CELLS {name} {len(losses)}')
        if name == 'rate_002':
            assert not losses
    for r in coverage_summary:
        if r['candidate'] in ('baseline', 'rate_002') and r['corner'] == 'nominal' and r['family'] == 'independent':
            assert {str(a): r[str(a)] for a in CS.AMBIENTS} == CS.EXPECTED_INDEP_NOMINAL[r['rail']]
    assert all(r['latches'] == 0 for r in results if r['group'] == 'gated')
    for v in CS.VARIANTS:
        selected = [r for r in results if r['rail'] == v and r['group'] == 'reported']
        before = sum(r['latches'] > 0 for r in selected if r['candidate'] == 'baseline')
        after = sum(r['latches'] > 0 for r in selected if r['candidate'] == 'rate_002')
        assert after <= before
        print(f'SELECTED {v} report-only latched trajectories {before} -> {after}')
    assert sum(r['latches'] > 0 for r in results if r['candidate'] == 'rate_002') < sum(
        r['latches'] > 0 for r in results if r['candidate'] == 'baseline')
    # A longer timer can merely move a false latch beyond the original horizon.
    names = dict(CANDIDATES)
    CANDIDATES.clear()
    CANDIDATES['off_4tau_14400'] = names['off_4tau_14400']
    for v in CS.VARIANTS:
        for kind, p in [('ambient', {'A': -5.0, 't_end': 86400}),
                        ('frozen_plateau', {'A': 25.0, 't_place': 1800.0, 't_end': 86400})]:
            corner = 'false' if kind == 'ambient' else 'nominal'
            print('EXTENDED ' + json.dumps(benign(('extended', kind, p, corner, v)), sort_keys=True))
    CANDIDATES.clear()
    CANDIDATES.update(names)
    print('ALL F3 GUARD COMPARISONS PASS')

if __name__ == '__main__':
    main()
