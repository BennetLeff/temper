#!/usr/bin/env python3
"""D18 conditional enclosure arithmetic; not a production validator or heat bound."""
from __future__ import annotations
import csv
import hashlib
import json
import math
from pathlib import Path
import runpy

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[6]
PS = ROOT / 'zapote/power-stage-120v'
VR = PS / 'validation-results'
R3 = VR / '03-loss-thermal-budget/round3'
D = HERE.parent
REFS = ('BR1', 'Q5', 'Q6', 'Q3', 'Q2')
MOS = REFS[1:]
BASE = 'b30b3ae35a4bd3ad5c22d8c300c4640986e1232a'

def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline='') as f:
        return list(csv.DictReader(f))

def rds(t: float, factor: float = 1.0) -> float:
    # 18mOhm guaranteed at 25C scaled by the TYPICAL 15->33mOhm ratio.
    return factor * .018 * (1 + 1.2 * (t - 25) / 125)

def rating_r5(t: float) -> float:
    return max(0., min(1., (170 - t) / 100))

def solve(case: dict, sw: dict[str, float], ambient: float, rsa: float,
          rcs: float, flow_cfm: float, reverse: bool, r_factor: float = 1.,
          sw_factor: float = 1., sink_fraction: float = 1., bridge_vf_factor: float = 1.,
          bridge_rcs: float = .45) -> dict:
    # Isothermal common-sink model plus deliberately separate gradient allowance.
    # The allowance is NOT an additional catalog Rtheta: qualification must measure
    # hottest mounting location against inlet air; catalog curve applicability is open.
    order = list(reversed(REFS)) if reverse else list(REFS)
    tj = {r: ambient for r in REFS}
    history = []
    freq = float(case['frequency_hz'])
    i2 = float(case['i_rms_a']) ** 2 / 2
    iin = float(case['target_w']) / (.95 * float(case['vrms_v']))
    bridge = 2 * 1.05 * bridge_vf_factor * iin * 2 * math.sqrt(2) / math.pi
    cpflow = 1.09 * 1005 * flow_cfm * .00047194745
    for iteration in range(1, 301):
        powers = {'BR1': bridge}
        for ref in MOS:
            powers[ref] = i2 * rds(tj[ref], r_factor) + sw[ref] * freq / 36000 * sw_factor
        psink = sum(powers.values()) * sink_fraction
        ts = ambient + rsa * psink
        upstream = 0.
        next_t = {}
        local_sink = {}
        for ref in order:
            gradient = upstream / cpflow if cpflow else 0.
            local_sink[ref] = ts + gradient
            rpath = .25 + bridge_rcs if ref == 'BR1' else .28 + rcs
            next_t[ref] = local_sink[ref] + powers[ref] * sink_fraction * rpath
            upstream += powers[ref] * sink_fraction
        delta = max(abs(next_t[r] - tj[r]) for r in REFS)
        tj = next_t
        history.append({'iteration': iteration, 'max_tj_C': max(tj.values()), 'change_C': delta})
        if max(tj.values()) > 400:
            return {'converged': False, 'reason': 'outside temperature model', 'history': history}
        if delta < 1e-8:
            break
    else:
        raise RuntimeError('temperature iteration did not converge')
    return {'converged': True, 'tj_C': tj, 'sink_mount_C': local_sink,
            'max_tj_C': max(tj.values()), 'worst_device': max(tj, key=tj.get),
            'margin_to_125_C': 125 - max(tj.values()), 'sink_W': psink,
            'device_W': powers, 'conduction_W': {r: i2 * rds(tj[r], r_factor) for r in MOS},
            'switching_allocation_W': {r: sw[r] * freq / 36000 * sw_factor for r in MOS},
            'history': history, 'input_current_assumption_A': iin,
            'heat_diverted_to_board_W': sum(powers.values()) * (1 - sink_fraction)}

def limit_rsa(case: dict, sw: dict, ambient: float, rcs: float, reverse: bool) -> float | None:
    ideal = solve(case, sw, ambient, 0, rcs, 20, reverse)
    if not ideal['converged'] or ideal['max_tj_C'] > 125:
        return None
    low, high = 0., 2.
    for _ in range(45):
        mid = (low + high) / 2
        result = solve(case, sw, ambient, mid, rcs, 20, reverse)
        if not result['converged'] or result['max_tj_C'] > 125:
            high = mid
        else:
            low = mid
    return low

def main() -> None:
    paths = [HERE/'losses.py', R3/'inputs/cases.csv', R3/'inputs/board-parts.json',
             R3/'outputs/losses.json', D/'out-D15/cycles.csv', D/'out-D13/results-main.json',
             PS/'native-17/section.kicad_pcb', PS/'frozen/default.net', PS/'frozen/default.csv',
             PS/'DECISIONS.md', VR/'06-controller-interface/scripts/interface_check.py']
    paths += list((R3/'sources').glob('*.pdf'))
    parser = runpy.run_path(str(VR/'06-controller-interface/scripts/interface_check.py'))
    board = parser['board']('zapote/power-stage-120v/native-17/section.kicad_pcb', True)
    old = json.loads((R3/'inputs/board-parts.json').read_text())['parts']
    positions = {}
    for fp in parser['parse']('zapote/power-stage-120v/native-17/section.kicad_pcb').children('footprint'):
        props = {p.items[1]: p.items[2] for p in fp.children('property')}
        ref = props.get('Reference')
        if ref in REFS:
            positions[ref] = [float(x) for x in fp.one('at').items[1:3]]
            assert positions[ref] == old[ref]['centre_mm'], (ref, positions[ref])
            assert board[ref]['value'] == old[ref]['part']
    assert tuple(sorted(positions, key=lambda r: positions[r][0])) == REFS
    cold = [r for r in read_csv(D/'out-D15/cycles.csv') if r['dt_ns'] == '443']
    assert len(cold) == 24 and all(r['indeterminate'] == 'False' for r in cold)
    hot = [r for r in json.loads((D/'out-D13/results-main.json').read_text())
           if r['variant'] == 'baseline' and r['dt_ns'] == 443 and r['case'] in ('S1', 'S2')]
    assert len(hot) == 48 and all(r['status'] == 'complete' for r in hot)
    # Envelope of SAMPLED per-device, complete-cycle proxy at 27/100/150C,
    # 170/198/280V, 37/71A, ESL1.06/10. Not an envelope of all real waveforms.
    groups = {}
    for row in hot:
        key = (row['temp_C'], row['case'], row['vbus'], row['il'], row['esl_nH'])
        groups.setdefault(key, []).append(row)
    envelopes = {'HS': [], 'LS': []}
    for key, pair in groups.items():
        assert sorted(r['dir'] for r in pair) == [0, 1]
        for side, letter in [('HS','h'), ('LS','l')]:
            watts = 36000 * sum(r['meas'][f'e_{letter}_pre'] + r['meas'][f'e_{letter}_post'] for r in pair)
            envelopes[side].append({'case': key, 'W_at_36kHz': watts})
    for side in envelopes:
        envelopes[side] += [{'case': ['D15',r['vbus'],r['il'],r['esl_nH']],
                             'W_at_36kHz': float(r[f'proxy_W_{side}'])} for r in cold]
    stress_allocation = {s: max(rows, key=lambda r:r['W_at_36kHz']) for s, rows in envelopes.items()}
    cold_hot = {(r['case'],r['vbus'],r['il'],r['dir'],r['esl_nH']):r for r in hot if r['temp_C']==27}
    hot_factor = max(r['total_uJ']/cold_hot[(r['case'],r['vbus'],r['il'],r['dir'],r['esl_nH'])]['total_uJ'] for r in hot)
    allocation = {}
    for side in ('HS','LS'):
        row = max(cold, key=lambda r:float(r[f'proxy_W_{side}']))
        allocation[side] = {'case':['D15',row['vbus'],row['il'],row['esl_nH']], 'W_at_36kHz':float(row[f'proxy_W_{side}'])*hot_factor}
    sw = {r: allocation['HS' if r in ('Q2','Q5') else 'LS']['W_at_36kHz'] for r in MOS}
    cases = [r for r in read_csv(R3/'inputs/cases.csv') if r['vrms_v'] in ('120','140')]
    assert len(cases) == 90
    results = []
    for c in cases:
        peak = float(c['i_pk_a']); irms = float(c['i_rms_a'])
        category = 'below_static_CT_min' if peak < 50.9 else ('CT_spread' if peak <=59.5 else 'above_static_CT_max')
        rec = {'run_id': c['run_id'], 'f_Hz': float(c['frequency_hz']), 'peak_A': peak,
               'rms_A': irms, 'category': category, 'sampled_current_domain_exceeded': peak >71,
               'r5_nominal_W': irms**2 * .001,
               'r5_125C_resistance_W': irms**2 * .001 * 1.01 * (1+250e-6*100),
               'gate_power_350nC_15V_W': 4 * 350e-9 * 15 * float(c['frequency_hz']) + .045,
               'gate_power_500nC_15V_W': 4 * 500e-9 * 15 * float(c['frequency_hz']) + .045,
               'thermal': {}}
        for ambient in (40,50):
            for direction, reverse in [('left_to_right',False), ('right_to_left',True)]:
                rec['thermal'][f'{ambient}_{direction}'] = solve(c, sw, ambient,.15,1.,20,reverse)
        results.append(rec)
    sustained = [r for r in results if r['category']=='below_static_CT_min']
    worst = max(sustained, key=lambda r:r['thermal']['50_right_to_left']['max_tj_C'])
    selected = next(c for c in cases if c['run_id']==worst['run_id'])
    sensitivities = []
    for r_factor, sw_factor, rcs, flow, fraction in [(1,1,1.,20,1),(1.25,1,1.,20,1),(1,1.25,1.,20,1),
            (1,1,.5,20,1),(1,1,1.75,20,1),(1,1,1.,10,1),
            (1,1,1.,40,1),(1,1,1.,20,.9),(1.25,1.25,1.,20,1)]:
        sensitivities.append({'rds_factor':r_factor,'switch_factor':sw_factor,'rcs_C_per_W':rcs,
            'flow_CFM':flow,'sink_fraction':fraction,
            'result':solve(selected,sw,50,.15,rcs,flow,True,r_factor,sw_factor,fraction)})
    limits = {}
    for t in (40,50):
        for direction,reverse in [('LR',False),('RL',True)]:
            for pad in (.5,1.,1.75):
                candidates=[]
                for c in cases:
                    if float(c['i_pk_a']) < 50.9:
                        limit=limit_rsa(c,sw,t,pad,reverse)
                        candidates.append({'run_id':c['run_id'],'limit_C_per_W':limit})
                limits[f'{t}_{direction}_pad{pad}']=min(candidates,key=lambda r:-1 if r['limit_C_per_W'] is None else r['limit_C_per_W'])
    unknowns = sorted({r['ref']+': '+r['mechanism'] for r in json.loads((R3/'outputs/losses.json').read_text())['records'] if r['watts'] is None})
    records = []
    for result in results:
        thermal = result['thermal']['50_right_to_left']
        for ref in REFS:
            mechanisms = [('bridge_rectification_estimate', thermal['device_W'][ref])] if ref == 'BR1' else [
                ('conduction_conditional_hot', thermal['conduction_W'][ref]),
                ('switching_proxy_allocation', thermal['switching_allocation_W'][ref])]
            for mechanism, watts in mechanisms:
                records.append({'scenario':result['run_id'], 'ref':ref, 'mechanism':mechanism,
                    'watts':watts, 'sink_fraction':1., 'board_fraction':0.,
                    'basis':'50C inlet, right-to-left, Rsa=.15, Rcs=1, 20CFM; see README equations',
                    'source':'D15 cycles / D13 hot ratio / Infineon Rev2 p5 / GBJ2510 p2'})
        for ref, mechanism, watts in [('R5','shunt_resistance_corner',result['r5_125C_resistance_W']),
                ('gate_network','gate_drive_allocation',result['gate_power_350nC_15V_W'])]:
            records.append({'scenario':result['run_id'],'ref':ref,'mechanism':mechanism,
                'watts':watts,'sink_fraction':0.,'board_fraction':1.,
                'basis':'See README; engineering allowance, not measured loss',
                'source':'WSK2512 pp1-3 / Infineon Rev2 p5'})
    inherited_records = [r for r in json.loads((R3/'outputs/losses.json').read_text())['records'] if r['watts'] is None]
    bridge_sensitivity = []
    for vf, pad in [(1., .9), (1.2, .45), (1.2, .9)]:
        candidates = [(c['run_id'], solve(c,sw,50,.15,1.,20,True,bridge_vf_factor=vf,bridge_rcs=pad))
                      for c in cases if float(c['i_pk_a']) < 50.9]
        name, result = max(candidates, key=lambda item:item[1]['max_tj_C'])
        bridge_sensitivity.append({'vf_factor':vf,'bridge_rcs_C_per_W':pad,'run_id':name,'result':result})
    out = {'source_revision':BASE,'author':'OpenAI GPT-6','status':'CONDITIONAL_ENCLOSURE_BUDGET_NOT_BOUND',
       'input_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
       'records':records,'inherited_unknown_records':inherited_records,
       'bridge_sensitivity_all_candidates':bridge_sensitivity,
       'native17_positions_mm':positions,'switching_sample_envelope':allocation,
       'hot_factor_transferred_to_cold_grid':hot_factor,'S2_stress_allocation':stress_allocation,
       'diode_W_per_switch_443ns_36kHz':[{k:r[k] for k in ('vbus','il','esl_nH','diode_deadtime_W_per_switch')} for r in cold],
       'cases':results,'conditional_sustained_count':len(sustained),'worst_candidate':worst['run_id'],
       'sink_limit_C_per_W':limits,'sensitivity':sensitivities,
       'S2_repeated_every_cycle_sensitivity':solve(selected,{r:stress_allocation['HS' if r in ('Q2','Q5') else 'LS']['W_at_36kHz'] for r in MOS},50,.15,1.,20,True),
       'r5_rating_W':{str(t):rating_r5(t) for t in (40,50,70,100,125,150,170)},
       'r5_max_below_CT_min_W':max(r['r5_125C_resistance_W'] for r in sustained),
       'r5_max_all_requested_W':max(r['r5_125C_resistance_W'] for r in results),
       'inherited_unknowns_not_zero':unknowns}
    (HERE/'results.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    with (HERE/'loss-table.csv').open('w',newline='') as f:
        fields=['run_id','category','f_Hz','rms_A','peak_A','Q2_W','Q3_W','Q5_W','Q6_W','BR1_W','sink_W','max_tj_C','r5_nominal_W','r5_125C_resistance_W','gate_power_350nC_15V_W']
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for r in results:
            t=r['thermal']['50_right_to_left']
            row={k:r[k] for k in fields if k in r}
            row.update({ref+'_W':t['device_W'][ref] if t['converged'] else None for ref in REFS})
            row.update({k:t.get(k) for k in ('sink_W','max_tj_C')});w.writerow(row)
    print(json.dumps({k:out[k] for k in ('worst_candidate','switching_sample_envelope','sink_limit_C_per_W','r5_max_below_CT_min_W','r5_max_all_requested_W')},indent=2))

if __name__ == '__main__':
    main()
