#!/usr/bin/env python3
"""Generate D13 audit, matched comparisons and tables from retained raw results."""
from __future__ import annotations

import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
D2 = HERE.parents[1] / 'd2'


def load(name: str) -> list[dict]:
    return json.loads((HERE / name).read_text())


def key(row: dict) -> tuple:
    return tuple(row[k] for k in ('case', 'vbus', 'il', 'dir', 'dt_ns', 'esl_nH'))


def main() -> None:
    rows, refined, thresholds = load('results-main.json'), load('results-refine.json'), load('results-threshold.json')
    assert len(rows) == 336 and len(refined) == 72
    assert len({r['name'] for r in rows + refined}) == 408
    screens = {r['temp_C']: r['model_screen_V'] for r in thresholds}
    for row in rows + refined:
        assert row == load('raw/' + row['name'] + '/result.json')
        log = (HERE / 'raw' / row['name'] / 'run.log').read_text()
        assert f'TEMP = {row["temp_C"]:.6f}' in log
        assert (row['status'] == 'indeterminate') or 'Total analysis time' in log
        if row['status'] == 'complete':
            assert all(math.isfinite(row[k]) for k in ('off_V', 'vds_V', 'total_uJ', 'incoming_V'))
            row['off_model'] = row['off_V'] < screens[row['temp_C']]
            row['off_3V'] = row['off_V'] < 3
            row['off_1p9V'] = row['off_V'] < 1.9
            row['vds_pass'] = row['vds_V'] <= (585 if row['case'] == 'S2' else 520)
            row['vgs_pass'] = row['vgs_abs_V'] <= 30
    summaries = []
    table = ['# D-13 decision tables', '', 'All values are simulator observations, not hardware bounds. Indeterminate runs have no verdict.', '']
    for name, variant, dead_time in [('baseline all', 'baseline', None), ('F6 all', 'F6', None),
                                      ('baseline nominal', 'baseline', 348), ('F6 nominal', 'F6', 348),
                                      ('F7 nominal', 'baseline', 443)]:
        table += [f'## {name}', '', '| Tj °C | attempted / indeterminate | max off V | max VDS V | off fails model / 3.0 / 1.9 | VDS fails | S1 ZVS / completed | EΣ µJ range |', '|---|---|---|---|---|---|---|---|']
        for temp in (27, 100, 150):
            selection = [r for r in rows if r['variant'] == variant and r['temp_C'] == temp and (dead_time is None or r['dt_ns'] == dead_time)]
            complete = [r for r in selection if r['status'] == 'complete']
            s1 = [r for r in complete if r['case'] == 'S1']
            summary = {'view': name, 'temp_C': temp, 'attempted': len(selection), 'indeterminate': len(selection) - len(complete),
                       'off_max_V': max((r['off_V'] for r in complete), default=None), 'vds_max_V': max((r['vds_V'] for r in complete), default=None),
                       'vgs_abs_max_V': max((r['vgs_abs_V'] for r in complete), default=None),
                       'off_failures': {screen: sum(not r[screen] for r in complete) for screen in ('off_model', 'off_3V', 'off_1p9V')},
                       'vds_failures': sum(not r['vds_pass'] for r in complete),
                       'zvs_S1_yes': sum(r['zvs'] for r in s1), 'zvs_S1_complete': len(s1),
                       'energy_min_uJ': min((r['total_uJ'] for r in complete), default=None), 'energy_max_uJ': max((r['total_uJ'] for r in complete), default=None)}
            summaries.append(summary)
            fails = ' / '.join(str(v) for v in summary['off_failures'].values())
            if not complete:
                table.append(f'| {temp} | {len(selection)} / {len(selection)} | — | — | no verdict | no verdict | — | — |')
                continue
            table.append(f'| {temp} | {len(selection)} / {summary["indeterminate"]} | {summary["off_max_V"]:.6f} | {summary["vds_max_V"]:.4f} | {fails} | {summary["vds_failures"]} | {summary["zvs_S1_yes"]} / {len(s1)} | {summary["energy_min_uJ"]:.3f}–{summary["energy_max_uJ"]:.3f} |')
        table.append('')
    reference = {}
    for folder in ('grid-best', 'grid-best-longdt'):
        for line in (D2 / 'results' / folder / 'results.jsonl').read_text().splitlines():
            row = json.loads(line)
            reference[key(row)] = row
    comparisons = []
    for row in rows:
        if row['variant'] != 'baseline' or row['temp_C'] != 27 or key(row) not in reference:
            continue
        old = reference[key(row)]
        comparison = {'name': row['name'], 'historical_aborted': old['aborted'], 'status': row['status']}
        if not old['aborted'] and row['status'] == 'complete':
            comparison.update(off_delta_V=row['off_V'] - old['vgs_off_max'], vds_delta_V=row['vds_V'] - old['vds_pk'], zvs_agrees=row['zvs'] == old['zvs'])
        comparisons.append(comparison)
    base = {(r['variant'], r['temp_C'], key(r)): r for r in rows}
    convergence = []
    for row in refined:
        old = base[row['variant'], row['temp_C'], key(row)]
        entry = {'name': row['name'], 'main_status': old['status'], 'refine_status': row['status']}
        if old['status'] == row['status'] == 'complete':
            entry.update(off_delta_V=row['off_V'] - old['off_V'], vds_delta_V=row['vds_V'] - old['vds_V'],
                         energy_delta_percent=100 * (row['total_uJ'] / old['total_uJ'] - 1),
                         verdicts_agree=all(row[k] == old[k] for k in ('off_model', 'off_3V', 'off_1p9V', 'vds_pass', 'vgs_pass', 'zvs')))
        convergence.append(entry)
    transitions = []
    for row in rows:
        if row['temp_C'] == 27:
            continue
        cold = base[row['variant'], 27, key(row)]
        if row['status'] == cold['status'] == 'complete':
            transitions.append({'name': row['name'], 'off_delta_V': row['off_V'] - cold['off_V'],
                                'vds_delta_V': row['vds_V'] - cold['vds_V'],
                                'energy_delta_percent': 100 * (row['total_uJ'] / cold['total_uJ'] - 1),
                                'cold_off_model_pass': cold['off_model'], 'hot_off_model_pass': row['off_model'],
                                'cold_1p9_pass': cold['off_1p9V'], 'hot_1p9_pass': row['off_1p9V'],
                                'zvs_changed': row['zvs'] != cold['zvs']})
    for name, data in [('summary', summaries), ('baseline-comparison', comparisons), ('refinement-comparison', convergence),
                       ('temperature-comparison', transitions), ('decisions', rows),
                       ('indeterminate', [r['name'] for r in rows + refined if r['status'] != 'complete'])]:
        (HERE / f'{name}.json').write_text(json.dumps(data, indent=2) + '\n')
    table += ['## Individual decision cases', '', '| case | status | off V | model / 3.0 / 1.9 off screen | VDS V | incoming V / ZVS | Eoff / Eon / EΣ µJ |', '|---|---|---|---|---|---|---|']
    for row in rows:
        if row['status'] != 'complete':
            table.append(f'| {row["name"]} | indeterminate | — | — | — | — | — |')
        else:
            verdict = '/'.join('pass' if row[k] else 'FAIL' for k in ('off_model', 'off_3V', 'off_1p9V'))
            table.append(f'| {row["name"]} | complete | {row["off_V"]:.6f} | {verdict} | {row["vds_V"]:.4f} | {row["incoming_V"]:.4f} / {row["zvs"]} | {row["off_uJ"]:.3f} / {row["on_uJ"]:.3f} / {row["total_uJ"]:.3f} |')
    (HERE / 'TABLES.md').write_text('\n'.join(table) + '\n')
    print(json.dumps({'main_runs': len(rows), 'refinement_runs': len(refined), 'threshold_runs': len(thresholds),
                      'indeterminate': sum(r['status'] != 'complete' for r in rows + refined),
                      'historical_matches': len(comparisons)}, indent=2))


if __name__ == '__main__':
    main()
