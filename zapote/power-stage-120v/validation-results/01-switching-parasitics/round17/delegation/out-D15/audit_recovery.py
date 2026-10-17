#!/usr/bin/env python3
"""Compare isolated solver qualification rows without erasing original failures."""
from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIELDS = ('vbus', 'il', 'dir', 'dt_ns', 'esl_nH')


def point(row: dict) -> tuple:
    return tuple(row[k] for k in FIELDS)


def compare(new: dict, old: dict) -> dict:
    result = {'tag': new['tag'], 'indeterminate': new['aborted'] or old['aborted'],
              'old_step_ns': old['step_ns'], 'new_step_ns': new['step_ns'],
              'old_itl4': old['identity'].get('solver_candidate', {}).get('itl4', 200),
              'new_itl4': new['identity'].get('solver_candidate', {}).get('itl4', 200)}
    if not result['indeterminate']:
        result.update(energy_delta_percent=100 * (new['total_uJ'] / old['total_uJ'] - 1),
                      peak_delta_percent=100 * (new['peak_V'] / old['peak_V'] - 1),
                      off_delta_V=new['off_V'] - old['off_V'], incoming_delta_V=new['incoming_V'] - old['incoming_V'],
                      same_zvs=new['zvs'] == old['zvs'])
    return result



def unresolved_recovery(original_refinements: list[dict], recovered: list[dict], probes: list[dict]) -> list[str]:
    """Missing replacements remain indeterminate; partial cohorts cannot certify recovery."""
    affected = {point(row) for row in original_refinements if row['aborted']}
    expected = {(case, step) for case in affected for step in (.2, .1, .05)}
    recovered_by_key = {(point(row), row['step_ns']): row for row in recovered}
    if len(recovered_by_key) != len(recovered) or set(recovered_by_key) != expected:
        raise ValueError('Incomplete, duplicate or unexpected 1000-budget recovery cohort')
    failed = {key: row for key, row in recovered_by_key.items() if row['aborted']}
    probes_by_key = {(point(row), row['step_ns']): row for row in probes}
    if len(probes_by_key) != len(probes) or not set(probes_by_key) <= set(failed):
        raise ValueError('Duplicate or unexpected 10000-budget recovery probe')
    return [row['tag'] for key, row in failed.items()
            if key not in probes_by_key or probes_by_key[key]['aborted']]

def main() -> None:
    original = json.loads((HERE / 'sweep.json').read_text())
    baseline = {point(r): r for r in original}
    recovered = json.loads((HERE / 'recovery-itl4-1000/results.json').read_text())
    look = {(point(r), r['step_ns']): r for r in recovered}
    fidelity = [compare(r, baseline[point(r)]) for r in recovered if r['step_ns'] == .2]
    refinement = [compare(r, look[(point(r), .2 if r['step_ns'] == .1 else .1)])
                  for r in recovered if r['step_ns'] != .2]
    probes_path = HERE / 'recovery-itl4-10000/results.json'
    probes = json.loads(probes_path.read_text()) if probes_path.exists() else []
    # These comparisons change both the timestep and iteration ceiling;
    # report them distinctly from the same-budget convergence cohort.
    mixed = [compare(r, look[(point(r), .2 if r['step_ns'] == .1 else .1)]) for r in probes]
    all_checks = refinement + mixed
    original_refinements = [row for filename in ('refine.json', 'refine-boundary.json')
                            for row in json.loads((HERE / filename).read_text())]
    final_failures = unresolved_recovery(original_refinements, recovered, probes)
    output = {'itl4_1000_cases': len(recovered), 'itl4_1000_aborted': sum(r['aborted'] for r in recovered),
              'itl4_10000_probes': len(probes), 'remaining_indeterminate': final_failures,
              'fidelity_at_0p2ns': fidelity, 'same_budget_refinement': refinement, 'mixed_budget_probe_comparisons': mixed,
              'max_complete_fidelity_energy_percent': max((abs(r['energy_delta_percent']) for r in fidelity if not r['indeterminate']), default=None),
              'max_complete_refinement_energy_percent': max((abs(r['energy_delta_percent']) for r in all_checks if not r['indeterminate']), default=None),
              'max_complete_refinement_peak_percent': max((abs(r['peak_delta_percent']) for r in all_checks if not r['indeterminate']), default=None),
              'zvs_flips': [r['tag'] for r in fidelity + all_checks if not r['indeterminate'] and not r['same_zvs']]}
    selected = {(point(r), r['step_ns']): r for r in original}
    for filename in ('refine.json', 'refine-boundary.json'):
        for row in json.loads((HERE / filename).read_text()):
            if not row['aborted']:
                selected[(point(row), row['step_ns'])] = row
    for row in recovered + probes:
        if not row['aborted']:
            selected.setdefault((point(row), row['step_ns']), row)
    costs = []
    for esl in (1.06, 10):
        for step in (.2, .1, .05):
            powers, budgets = {}, []
            for dt in (348, 443):
                pair = [selected.get(((198, 37, d, dt, esl), step)) for d in (0, 1)]
                powers[dt] = None if any(r is None for r in pair) else .018 * sum(r['total_uJ'] for r in pair)
                budgets += [None if r is None else r['identity'].get('solver_candidate', {}).get('itl4', 200) for r in pair]
            costs.append({'vbus': 198, 'il': 37, 'esl_nH': esl, 'step_ns': step,
                          'proxy_W_348': powers[348], 'proxy_W_443': powers[443],
                          'delta_W': None if None in powers.values() else powers[443] - powers[348],
                          'itl4_for_348_d0_d1_443_d0_d1': ','.join(str(v) for v in budgets)})
    with (HERE / 'full-load-convergence.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(costs[0]))
        writer.writeheader()
        writer.writerows(costs)
    output['full_load_cost_convergence'] = costs
    (HERE / 'recovery-audit.json').write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps({k: v for k, v in output.items() if k not in ('fidelity_at_0p2ns', 'same_budget_refinement', 'mixed_budget_probe_comparisons')}, indent=2))


if __name__ == '__main__':
    main()
