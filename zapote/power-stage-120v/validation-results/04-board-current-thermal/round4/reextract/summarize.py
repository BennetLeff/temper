#!/usr/bin/env python3
"""Audit every A4 result and write the electrical/thermal handoff index."""
from __future__ import annotations

import gzip
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
OUT=HERE/'outputs'
INPUT=HERE/'inputs/power_copper.json.gz'


def barrel_index(data):
    by_net=defaultdict(dict)
    for item in data['primitives']:
        kind=item['kind']
        if kind not in ('pad','via'):
            continue
        drill=item.get('drill_mm',0)
        if kind=='pad':
            if drill[0]!=drill[1]:
                raise ValueError('slotted drill unsupported')
            drill=drill[0]
        if drill<=0:
            continue
        key=(kind,*item['centre'])
        barrel=by_net[item['net']].setdefault(key,{
            'kind':kind,'ref':item.get('ref'),'xy_mm':item['centre'],
            'drill_mm':drill,'layers':[]})
        if item['layer'] not in barrel['layers']:
            barrel['layers'].append(item['layer'])
    order={'F.Cu':0,'In1.Cu':1,'In2.Cu':2,'B.Cu':3}
    return {net:[{**barrel,'layers':sorted(barrel['layers'],key=order.get)}
                 for barrel in barrels.values()] for net,barrels in by_net.items()}


def main():
    data=json.load(gzip.open(INPUT,'rt'))
    barrels=barrel_index(data)
    cases=json.loads((OUT/'cases.json').read_text())
    rows=[]
    via_cases={}
    failed=[]
    for case in cases['cases']:
        name=case['name']
        path=OUT/f'{name}.json'
        if not path.exists():
            failed.append(f'{name}: missing output')
            continue
        result=json.loads(path.read_text())
        if result['status']!='conditional DC experiment':
            failed.append(f'{name}: {result["status"]} {result.get("reason", "")}')
        expected=barrels[result['net']]
        actual=result.get('via_currents',[])
        if len(expected)!=len(actual):
            failed.append(f'{name}: barrel census {len(expected)} != {len(actual)}')
        vias=[]
        for barrel,current in zip(expected,actual):
            if list(current['xy'])!=barrel['xy_mm']:
                failed.append(f'{name}: barrel order mismatch at {barrel["xy_mm"]}')
            peak=current['amps']
            row={**barrel,'hop_layers':[list(pair) for pair in zip(barrel['layers'],barrel['layers'][1:])],
                 'hop_amps':current['hop_amps'],'peak_signed_amps':peak,
                 'status':current['status'],
                 'over_3a_flag':barrel['kind']=='via' and peak is not None and abs(peak)>3}
            vias.append(row)
        via_cases[name]=vias
        flags=[v for v in vias if v['over_3a_flag']]
        empty=[v for v in vias if v['kind']=='via' and v['peak_signed_amps'] is not None]
        energy_err=result.get('energy_balance_error_w')
        if energy_err is not None and abs(energy_err)>max(1e-8,abs(result['loss_w'])*1e-6):
            failed.append(f'{name}: energy imbalance {energy_err} W')
        with np.load(OUT/result['nodal_heat_file']) as nodal:
            node_w=sum(float(nodal[key].sum()) for key in nodal.files if key.endswith('_joule_w'))
        barrel_w=sum(sum(item['layer_joule_w'].values()) for item in result['barrel_heat_by_layer'])
        transfer_err=node_w+barrel_w-result['loss_w']
        if abs(transfer_err)>max(1e-8,abs(result['loss_w'])*1e-6):
            failed.append(f'{name}: thermal transfer imbalance {transfer_err} W')
        rows.append({
            'name':name,'net':result['net'],'pitch_mm':result['pitch_mm'],
            'plating_um':result['plating_um'],'status':result['status'],
            'description':case['description'],'r_mohm':result.get('r_ohm',0)*1e3,
            'loss_w':result.get('loss_w'),'drive_amps':result.get('drive_amps'),
            'layer_max_a_per_mm':result.get('layer_max_a_per_mm'),
            'max_empty_via_a':max((abs(v['peak_signed_amps']) for v in empty),default=None),
            'flagged_empty_vias_over_3a':len(flags),
            'undefined_island_barrels':sum(v['peak_signed_amps'] is None for v in vias),
            'nodal_heat_file':result.get('nodal_heat_file'),
            'nodal_heat_sha256':hashlib.sha256((OUT/result['nodal_heat_file']).read_bytes()).hexdigest()
                if result.get('nodal_heat_file') else None,
            'energy_balance_error_w':energy_err,
            'thermal_transfer_balance_error_w':transfer_err,
            'radial_contacts_checked':result.get('contact_audit',{}).get('radial_contacts_checked'),
            'bad_radial_contacts':len(result.get('contact_audit',{}).get('uncovered_contacts',[]))})
    for name in ('bus-dc-q2-p025-pl18','bus_dc_q2-p0125-pl18','bus-dc-q2-p00625-pl18'):
        if not (OUT/f'{name}.json').exists():
            failed.append(f'missing BUS_P convergence point {name}')
    convergence=[]
    for pitch,name in ((0.25,'bus-dc-q2-p025-pl18'),(0.125,'bus_dc_q2-p0125-pl18'),
                       (0.0625,'bus-dc-q2-p00625-pl18')):
        result=json.loads((OUT/f'{name}.json').read_text())
        convergence.append({'pitch_mm':pitch,'r_mohm':result['r_ohm']*1e3,
                            'loss_w':result['loss_w'],'bad_radial_contacts':len(result['contact_audit']['uncovered_contacts'])})
    resistances=[x['r_mohm'] for x in convergence]
    span=(max(resistances)-min(resistances))/resistances[-1]
    if span>0.03:
        failed.append(f'BUS_P full pitch span {span:.3%} exceeds 3%')
    topo=json.loads((OUT/'topology-p0125.json').read_text())
    if topo['total_spanning'] or any(x['grid_components']!=x['physical_components'] for x in topo['layers'].values()):
        failed.append('0.125 mm topology did not match physical components')
    summary={'board_sha256':data['board_sha256'],
             'input_sha256':hashlib.sha256(INPUT.read_bytes()).hexdigest(),
             'evidence_class':'simulation/model-based, conditional current paths',
             'status':'A4 electrical model completed; operating waveform and thermal qualification pending'
                      if not failed else 'A4 failed/partial',
             'rows':rows,'bus_p_convergence':convergence,
             'bus_p_full_span_relative_to_fine':span,
             'bus_p_convergence_3pct_pass':span<=0.03,
             'topology_p0125_zero_false_joins':topo['total_spanning']==0,
             'all_numeric_checks_pass':not failed,'failures':failed,
             'thermal_handoff':{
                 'nodal_heat_files':'outputs/<case>-heat.npz',
                 'grid_keys':'<F_Cu|In1_Cu|In2_Cu|B_Cu>_<x_mm|y_mm|copper|joule_w|thickness_um>',
                 'barrel_heat':'scenario JSON barrel_heat_by_layer',
                 'accounting':'sum nodal joule_w + sum barrel_heat_by_layer layer_joule_w = loss_w',
                 'copper_only_rise_c':None,'component_plus_copper_temperature_c':None}}
    (OUT/'via_currents.json').write_text(json.dumps(via_cases,indent=2,allow_nan=False)+'\n')
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'scenarios':len(rows),'failed':failed,'bus_p_span_percent':100*span}))
    return 1 if failed else 0


if __name__=='__main__':
    raise SystemExit(main())
