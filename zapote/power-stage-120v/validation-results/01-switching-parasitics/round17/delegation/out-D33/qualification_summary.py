"""Fail closed on incomplete final D-33 evidence and summarize its limits.

Run after all campaigns and refine_rail.py. This aggregates model results;
it does not certify component/layout assumptions or physical hardware.
"""
from pathlib import Path
import hashlib
import json
import math

HERE = Path(__file__).resolve().parent


def read(path: str):
    return json.loads((HERE / path).read_text())


def rail_result(path: str, expected: int) -> dict:
    rows = read(path)
    if len(rows) != expected or len({row['name'] for row in rows}) != expected:
        raise ValueError(f'{path}: expected {expected} distinct cases, got {len(rows)}')
    for row in rows:
        m = row['measurements']
        if not (row['complete'] and row['pass'] and
                all(math.isfinite(m[k]) for k in ('negmax', 'negmin', 'shuntmin', 'shuntmax')) and
                m['negmax'] < -1.6 and m['shuntmin'] > 0 and m['shuntmax'] < .07):
            raise ValueError(f'{path}: incomplete or failed {row["name"]}')
    worst = max(rows, key=lambda row: row['measurements']['negmax'])
    return {'path': path, 'cases': len(rows), 'completed': len(rows), 'passed': len(rows),
            'least_negative_partner_window_V': worst['measurements']['negmax'],
            'margin_to_minus_1p6_V': -1.6 - worst['measurements']['negmax'],
            'worst_case': worst['name'],
            'minimum_shunt_A': min(row['measurements']['shuntmin'] for row in rows),
            'maximum_shunt_A': max(row['measurements']['shuntmax'] for row in rows)}


def main() -> None:
    result = {'status': 'PASS within stated model and layout acceptance conditions',
              'base_commit': 'fada4c13c', 'hardware_qualified': False,
              'rail_limit_V': -1.6, 'switching_limit_V': 1.9,
              'edge_step_ps': 50, 'edge_span_V': 15.5,
              'repeated_pulse_charge_nC': 740, 'repeated_pulse_peak_A': 8,
              'hot_load_span_V': 18, 'hot_load_current_mA': 30,
              'corner_count_per_selected_waveform': 128,
              'qualification_limits': [
                  'gm/pole factors are engineering sensitivities, not vendor temperature/process bounds',
                  'effective capacitance and mounted ESL/ESR must meet ECO limits',
                  'transformer control startup, core loss, saturation and worst leakage are not qualified',
                  'rail monitor startup/recovery, DIS timing and D-20 harness remain physical gates',
                  'bursts remain disabled pending LINE_ZC firmware and timing qualification']}
    switching = []
    for folder, count in [('edge-current', 504), ('edge-current-2.4V', 26)]:
        rows = read(f'{folder}/results.json')
        if len(rows) != count or not all(r['status'] == 'complete' and r['pass_hot'] and
                                         math.isfinite(r['off_V']) and r['off_V'] < 1.9 for r in rows):
            raise ValueError(f'{folder}: incomplete or failed switching results')
        switching.append({'path': f'{folder}/results.json', 'cases': count, 'passed': count,
                          'maximum_off_gate_V': max(r['off_V'] for r in rows)})
    result['switching'] = switching
    campaigns = []
    for folder, count in [('rail-qualified', 1008), ('rail-deep-bias', 52)]:
        selected = read(f'{folder}/selected-waveforms.json')
        if not selected or len(selected) != len({tuple(pair) for pair in selected}):
            raise ValueError(f'{folder}: empty or duplicate waveform selection')
        campaigns.append(rail_result(f'{folder}/edge-screen.json', count))
        campaigns.append(rail_result(f'{folder}/edge-corners.json', 128 * len(selected)))
    campaigns.append(rail_result('rail-qualified/periodic.json', 256))
    campaigns.append(rail_result('rail-hot-18V/hot-load.json', 128))
    result['rail_campaigns'] = campaigns
    result['least_negative_partner_window_V'] = max(r['least_negative_partner_window_V'] for r in campaigns)
    result['rail_margin_V'] = -1.6 - result['least_negative_partner_window_V']
    loop = read('rail-qualified/loop.json')
    margins = [margin for row in loop['corners'] for margin in row['phase_margin_deg']]
    if (len(loop['corners']) != 128 or not all(row['phase_margin_deg'] for row in loop['corners']) or
            not all(math.isfinite(margin) and margin >= 45 for margin in margins) or
            loop['minimum_margin_deg'] != min(margins)):
        raise ValueError('Loop margin/count failed')
    result['minimum_phase_margin_deg'] = loop['minimum_margin_deg']
    refinement = read('rail-qualified/final-refinement.json')
    if len(refinement) != 6 or not all(r['step_25ps']['pass'] and r['negmax_difference_V'] <= .005 for r in refinement):
        raise ValueError('Timestep refinement failed')
    result['refinement'] = {'cases': 6, 'maximum_50_to_25ps_difference_V': max(r['negmax_difference_V'] for r in refinement)}
    transformer = read('transformer-check/results.json')
    if len(transformer) != 4 or not all(row['complete'] for row in transformer):
        raise ValueError('Transformer campaign incomplete')
    measurements = [row['measurements'] for row in transformer]
    result['transformer'] = {
        'cases': 4,
        'minimum_rectified_output_V': min(m[k] for m in measurements for k in ('outa_min', 'outb_min')),
        'maximum_switch_current_A': max(m[k] for m in measurements for k in ('switch1_max', 'switch2_max')),
        'maximum_drain_V': max(m[k] for m in measurements for k in ('drain1_max', 'drain2_max')),
        'maximum_rectifier_reverse_V': max(m[k] for m in measurements for k in ('rectifiera_reverse', 'rectifierb_reverse'))}
    t = result['transformer']
    if not (t['minimum_rectified_output_V'] > 17 and t['maximum_switch_current_A'] < .5 and
            t['maximum_drain_V'] < 85 and t['maximum_rectifier_reverse_V'] < 100):
        raise ValueError('Transformer model stress/headroom check failed')
    sizing = read('bias-sizing.json')
    result['maximum_supply_allocation_W'] = max(row['HOT_supply_allocation_W'] for row in sizing['rows'])
    result['supply_rating_before_derating_W'] = sizing['supply']['rating_W']
    files = [HERE / campaign['path'] for campaign in campaigns]
    files += [HERE / row['path'] for row in switching]
    files += [HERE / name for name in ('edge_currents.py', 'rail_qualification.py', 'refine_rail.py',
                                      'transformer_check.py', 'qualification_summary.py', 'bias-sizing.json',
                                      'rail-qualified/final-refinement.json', 'rail-qualified/loop.json',
                                      'transformer-check/results.json')]
    result['evidence_sha256'] = {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (HERE / 'qualification-summary.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
