#!/usr/bin/env python3
"""Publish D15 summaries from complete, finite, identity-bound ngspice rows."""
from __future__ import annotations

import csv
import gzip
import hashlib
import itertools
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run as campaign  # noqa: E402

FREQUENCY = 36_000.0  # declared illustrative switching rate, within nominal 33–39 kHz


def write_json(name: str, value: object) -> None:
    (HERE / name).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def write_csv(name: str, rows: list[dict]) -> None:
    if not rows:
        return
    with (HERE / name).open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def key(row: dict) -> tuple:
    return tuple(row[k] for k in ('vbus', 'il', 'dir', 'dt_ns', 'esl_nH'))


def integrate(t: np.ndarray, y: np.ndarray, lo: float, hi: float) -> float:
    inside = (t > lo) & (t < hi)
    tx = np.r_[lo, t[inside], hi]
    yy = np.r_[np.interp(lo, t, y), y[inside], np.interp(hi, t, y)]
    return float(np.trapezoid(yy, tx))


def waveform_check(row: dict) -> dict:
    path = HERE / 'raw' / row['tag'] / 'waves.raw.gz'
    payload = gzip.decompress(path.read_bytes())
    if hashlib.sha256(payload).hexdigest() != row['waveform_sha256']:
        raise ValueError(f'Wave hash mismatch: {path}')
    with tempfile.NamedTemporaryFile(suffix='.raw') as stream:
        stream.write(payload)
        stream.flush()
        from run_ngspice import read_raw
        waves = {k: np.asarray(v) for k, v in read_raw(stream.name).items()}
    t = waves['time']
    if not all(np.isfinite(v).all() for v in waves.values()):
        raise ValueError(f'Nonfinite wave: {path}')
    lo, split, end = 2e-6, 2e-6 + row['dt_ns'] * 1e-9, 2.75e-6 + row['dt_ns'] * 1e-9
    if t[-1] < end:
        raise ValueError(f'Truncated wave: {path}')
    deltas = {}
    for side in ('l', 'h'):
        q = f'xq{side}'
        vds = waves[f'v({q}.dd)'] - waves[f'v({q}.s)']
        current = (waves[f'v({q}.ldrd)'] - waves[f'v({q}.dd)']) / 7.44e-5
        forward = np.maximum(0, -waves[f'i(v.{q}.x1.v_sense2)'])
        for window, start, stop in [('pre', lo, split), ('post', split, end)]:
            for metric, signal in [('e', np.maximum(0, vds * current)),
                                   ('diode_e', np.maximum(0, -vds) * forward)]:
                name = f'{metric}_{side}_{window}'
                energy = integrate(t, signal, start, stop)
                deltas[name] = (energy - row['meas'][name]) * 1e6
    return {'tag': row['tag'], 'wave_end_s': float(t[-1]),
            'max_abs_energy_disagreement_uJ': max(abs(v) for v in deltas.values()),
            'energy_deltas_uJ': deltas}



def validate_refinements(focused: list[dict], boundary: list[dict], current_identity: dict) -> list[dict]:
    """Require every planned refinement, including failures, from the same campaign."""
    expected_focused = set(itertools.product((198,), (2, 37), (0, 1), (348, 443), (1.06, 10), (.1, .05)))
    expected_boundary = set(itertools.product((170,), (10,), (0, 1), (443,), (1.06, 10), (.1, .05)))
    for name, rows, expected in [('focused', focused, expected_focused), ('boundary', boundary, expected_boundary)]:
        observed = {(*key(row), row['step_ns']) for row in rows}
        if len(rows) != len(expected) or observed != expected:
            raise ValueError(f'Incomplete, duplicate or unexpected {name} refinement cohort')
        for row in rows:
            if campaign.cache_key(row['identity']) != current_identity:
                raise ValueError(f'Refinement input identity mismatch: {row["tag"]}')
    return focused + boundary

def main() -> None:
    rows = json.loads((HERE / 'sweep.json').read_text())
    current_identity = campaign.cache_key(campaign.identity())
    refined = validate_refinements(
        json.loads((HERE / 'refine.json').read_text()),
        json.loads((HERE / 'refine-boundary.json').read_text()), current_identity)
    expected = set(itertools.product((170, 198), campaign.CURRENTS, (0, 1), campaign.DTS, (1.06, 10)))
    lookup = {key(r): r for r in rows}
    assert len(rows) == len(expected) and set(lookup) == expected, 'Incomplete or duplicate grid'
    known = [r for r in rows if not r['aborted']]
    for row in known:
        assert all(np.isfinite(v) for v in row['meas'].values()), row['tag']
        assert campaign.cache_key(row['identity']) == current_identity, row['tag']
    fields = ['tag', 'vbus', 'il', 'dir', 'dt_ns', 'esl_nH', 'aborted', 'zvs', 'incoming_V', 'peak_V', 'off_V',
              'off_uJ', 'on_uJ', 'total_uJ', 'diode_incoming_deadtime_ns', 'diode_incoming_deadtime_uJ',
              'diode_incoming_deadtime_uC', 'diode_both_deadtime_uJ']
    write_csv('points.csv', [{k: r.get(k) for k in fields} for r in rows])
    baseline = [json.loads(s) for s in (campaign.D2 / 'results/grid-best/results.jsonl').read_text().splitlines()]
    comparisons = []
    for old in baseline:
        k = key(old)
        if old['dt_ns'] != 348 or k not in lookup:
            continue
        new = lookup[k]
        item = {'tag': new['tag'], 'old_aborted': old['aborted'], 'new_aborted': new['aborted']}
        if not old['aborted'] and not new['aborted']:
            for newname, oldname in [('peak_V', 'vds_pk'), ('off_V', 'vgs_off_max'), ('incoming_V', 'vds_incoming_at_on')]:
                item[f'{newname}_delta'] = new[newname] - old[oldname]
            item['same_zvs'] = new['zvs'] == old['zvs']
        comparisons.append(item)
    assert len(comparisons) == 32, 'Missing baseline decision cases'
    assert all(r['old_aborted'] == r['new_aborted'] for r in comparisons)
    assert all(r.get('same_zvs', True) for r in comparisons)
    assert all(abs(r.get(k, 0)) < 0.002 for r in comparisons
               for k in ('peak_V_delta', 'off_V_delta', 'incoming_V_delta'))
    write_json('baseline-check.json', comparisons)
    cycles = []
    for v, il, esl, dt in itertools.product((170, 198), campaign.CURRENTS, (1.06, 10), campaign.DTS):
        pair = [lookup[(v, il, d, dt, esl)] for d in (0, 1)]
        row = {'vbus': v, 'il': il, 'esl_nH': esl, 'dt_ns': dt, 'indeterminate': any(r['aborted'] for r in pair),
               'zvs_directions': sum(r.get('zvs', False) for r in pair), 'frequency_hz': FREQUENCY,
               'proxy_W_per_switch': None, 'proxy_W_HS': None, 'proxy_W_LS': None, 'diode_deadtime_W_per_switch': None, 'delta_proxy_W_vs_348': None}
        if not row['indeterminate']:
            for side, name in [('h', 'HS'), ('l', 'LS')]:
                row[f'proxy_W_{name}'] = FREQUENCY * sum(r['meas'][f'e_{side}_{w}'] for r in pair for w in ('pre', 'post'))
            row['proxy_W_per_switch'] = FREQUENCY * sum(r['total_uJ'] for r in pair) * 1e-6 / 2
            row['diode_deadtime_W_per_switch'] = FREQUENCY * sum(r['diode_both_deadtime_uJ'] for r in pair) * 1e-6 / 2
        cycles.append(row)
    cyc = {(r['vbus'], r['il'], r['esl_nH'], r['dt_ns']): r for r in cycles}
    for r in cycles:
        base = cyc[(r['vbus'], r['il'], r['esl_nH'], 348)]['proxy_W_per_switch']
        if base is not None and r['proxy_W_per_switch'] is not None:
            r['delta_proxy_W_vs_348'] = r['proxy_W_per_switch'] - base
    write_csv('cycles.csv', cycles)
    mixed = []
    for v, esl, dt in itertools.product((170, 198), (1.06, 10), campaign.DTS):
        subset = [cyc[(v, il, esl, dt)] for il in campaign.CURRENTS]
        valid = all(not r['indeterminate'] for r in subset)
        mixed.append({'vbus': v, 'esl_nH': esl, 'dt_ns': dt, 'indeterminate': not valid,
                      'weight_each_current': 1 / len(campaign.CURRENTS),
                      'proxy_W_per_switch': sum(r['proxy_W_per_switch'] for r in subset) / len(subset) if valid else None,
                      'diode_deadtime_W_per_switch': sum(r['diode_deadtime_W_per_switch'] for r in subset) / len(subset) if valid else None})
    write_csv('illustrative-profile.csv', mixed)
    checks, wave_checks = [], []
    refine_lookup = {(key(r), r['step_ns']): r for r in refined}
    for r in refined:
        if not r['aborted']:
            wave_checks.append(waveform_check(r))
        parent = lookup[key(r)] if r['step_ns'] == .1 else refine_lookup[(key(r), .1)]
        check = {'tag': r['tag'], 'compared_step_ns': parent['step_ns'], 'indeterminate': r['aborted'] or parent['aborted']}
        if not check['indeterminate']:
            check.update(energy_delta_percent=100 * (r['total_uJ'] / parent['total_uJ'] - 1),
                         peak_delta_percent=100 * (r['peak_V'] / parent['peak_V'] - 1),
                         off_delta_V=r['off_V'] - parent['off_V'], incoming_delta_V=r['incoming_V'] - parent['incoming_V'],
                         diode_energy_delta_uJ=r['diode_both_deadtime_uJ'] - parent['diode_both_deadtime_uJ'],
                         same_zvs=r['zvs'] == parent['zvs'])
        checks.append(check)
    write_json('timestep-checks.json', checks)
    write_json('waveform-checks.json', wave_checks)
    summary = {'cases': len(rows), 'aborted': [r['tag'] for r in rows if r['aborted']],
               'baseline_cases': len(comparisons),
               'baseline_max_abs_deltas_V': {k: max(abs(r.get(k, 0)) for r in comparisons)
                                           for k in ('peak_V_delta', 'off_V_delta', 'incoming_V_delta')},
               'zvs_by_dt': {dt: {'pass': sum(r['zvs'] for r in known if r['dt_ns'] == dt),
                                  'complete': sum(r['dt_ns'] == dt for r in known)} for dt in campaign.DTS},
               'refinement_cases': len(refined),
               'max_waveform_energy_disagreement_uJ': max((r['max_abs_energy_disagreement_uJ'] for r in wave_checks), default=None)}
    summary['refinement_max_abs'] = {
        k: max((abs(r[k]) for r in checks if not r['indeterminate']), default=None)
        for k in ('energy_delta_percent', 'peak_delta_percent', 'off_delta_V', 'incoming_delta_V', 'diode_energy_delta_uJ')}
    summary['refinement_zvs_flips'] = [r['tag'] for r in checks if not r['indeterminate'] and not r['same_zvs']]
    summary['refinement_indeterminate'] = [r['tag'] for r in checks if r['indeterminate']]
    write_json('summary.json', summary)
    inputs = [Path(__file__), HERE / 'sweep.json', campaign.D2 / 'results/grid-best/results.jsonl',
              HERE.parents[6] / 'docs/hardware/power-section-120v/POWER-SECTION.md']
    if (HERE / 'refine.json').exists():
        inputs.append(HERE / 'refine.json')
    if (HERE / 'refine-boundary.json').exists():
        inputs += [HERE / 'refine-boundary.json', HERE / 'refine_boundary.py']
    write_json('analysis-provenance.json', {str(p.relative_to(HERE.parents[6])): campaign.sha(p) for p in inputs})
    lines = ['# D-15 loss and ZVS tables', '', 'Generated by `analyze.py`. Values are simulation proxies, not measured device heat.', '',
             '## ZVS map', '', 'Each cell is the number of directions meeting signed incoming VDS ≤ 5% Vbus at command (0/1/2). `?` is indeterminate.', '',
             '| Bus V | ESL nH | Current A | 307 ns | 348 ns | 391 ns | 443 ns | 498 ns |',
             '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for v, esl, il in itertools.product((170, 198), (1.06, 10), campaign.CURRENTS):
        values = [cyc[(v, il, esl, dt)] for dt in campaign.DTS]
        lines.append(f'| {v} | {esl} | {il} | ' + ' | '.join('?' if r['indeterminate'] else str(r['zvs_directions']) for r in values) + ' |')
    lines += ['', '## Fixed-load representative switching-cycle subtotal', '',
              '36 kHz; sum both directions’ whole-event EΣ, divide by two devices, multiply by frequency. Diode column is diagnostic, already partly contained in EΣ; do not add it.', '',
              '| Bus V | ESL nH | Current A | 348 ns W/switch | 443 ns W/switch | Change W/switch | Diode at 348 ns mW/switch | Diode at 443 ns mW/switch |',
              '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for v, esl, il in itertools.product((170, 198), (1.06, 10), campaign.CURRENTS):
        b, r = [cyc[(v, il, esl, dt)] for dt in (348, 443)]
        values = [b['proxy_W_per_switch'], r['proxy_W_per_switch'], r['delta_proxy_W_vs_348'],
                  None if b['indeterminate'] else b['diode_deadtime_W_per_switch'] * 1000,
                  None if r['indeterminate'] else r['diode_deadtime_W_per_switch'] * 1000]
        lines.append(f'| {v} | {esl} | {il} | ' + ' | '.join('indeterminate' if x is None else f'{x:.5f}' for x in values) + ' |')
    (HERE / 'TABLES.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
