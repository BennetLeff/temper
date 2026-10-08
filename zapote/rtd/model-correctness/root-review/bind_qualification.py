#!/usr/bin/env python3
"""Bind reviewed artifacts into a new input; Rust alone decides qualification."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parent
UNIT = AUDIT.parent / 'unit'


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> str:
    raw = json.dumps(value, indent=2, sort_keys=True) + '\n'
    path.write_text(raw)
    return raw


def main(binary: Path) -> None:
    output = AUDIT / 'qualified-input'
    output.mkdir(exist_ok=True)
    original = UNIT / 'evidence/acceptance-final/input.json'
    data = json.loads(original.read_text())
    certificate = json.loads((AUDIT / 'qualification/full_network_bound.json').read_text())
    spice = json.loads((AUDIT / 'qualification/ngspice_cases.json').read_text())
    source = AUDIT / 'qualification/full_network_bound.py'
    mapping = {
        'FORCE+': ('FORCE_PLUS', 'force_plus_open', 'LOW_COMPARATOR_FAULT'),
        'FORCE-': ('FORCE_MINUS', 'force_minus_open', 'HIGH_COMPARATOR_FAULT'),
        'SENSE+': ('SENSE_PLUS', 'sense_plus_open', 'HIGH_COMPARATOR_FAULT'),
        'SENSE-': ('SENSE_MINUS', 'sense_minus_open', 'LOW_COMPARATOR_FAULT'),
        'SHORT': ('SHORT', 'rtd_short_le_10ohm', 'LOW_COMPARATOR_FAULT'),
    }
    observed = {c['case']: c for c in spice['cases']}
    cases, replacement = [], {}
    for row in certificate['records']:
        name, legacy, classification = mapping[row['case']]
        observation = observed['SHORT_0OHM_EXACT' if name == 'SHORT' else row['case']]
        passive_ms = observation.get('ngspice_cross_ms_after_open', observation.get('ngspice_cross_ms_after_fault'))
        # A representative SPICE observation plus the explicitly conditional
        # device delay; this is not a claim of a worst sampled corner.
        latency = passive_ms + 65 / 1e6
        cases.append({'name': name, 'derived': row, 'observed': {
            'detected': True, 'latency_ms': latency,
            'kind': 'representative_ngspice_plus_conditional_device_delay',
            'spice_receipt_sha256': sha(AUDIT / 'qualification/ngspice_cases.json'),
        }})
        replacement[legacy] = {
            'name': legacy, 'observation_status': 'REPRESENTATIVE_NGSPICE_CONDITIONAL_DELAY',
            'observed_class': classification, 'observed_detected': True,
            'observed_latency_ms': latency, 'observed_detect_ms': latency,
            'bound_ms': row['bound_ms'], 'source_model': 'full_network_bound.py',
            'source_model_sha256': sha(source),
            'qualification_scope': 'adopted passive network only; device applicability indeterminate',
        }
    model = data['model']
    model['observed_faults'] = [replacement.get(r['name'], r) for r in model['observed_faults']]
    model['timing'] = {
        'analytic_max_rc_bound_ms': certificate['overall_certificate_bound_ms'],
        'actual_model_max_detect_ms': max(c['observed']['latency_ms'] for c in cases),
        'rounded_hardware_detector_budget_ms': 2.0,
        'fault_overdrive_v': .020, 'tlv3201_propagation_ns': 55,
        'logic_delay_assumption_ns': 10, 'output_load_assumption_pf': 15,
        'method': 'full adopted passive network G-energy bound; conditional devices',
    }
    model['generated_date'] = '2026-09-11'
    model['producer'] = 'reviewed full_network_bound.py + independent ngspice; bind_qualification.py transports evidence'
    model['qualification_scope'] = {
        'renewed': list(replacement),
        'inherited_assertions': 'Other model fields retained from historical input without renewed qualification; ordinary numerical checks do not validate their physical applicability.',
        'historical_input_sha256': sha(original),
    }
    model['source_model_hashes']['full_network_bound.py'] = sha(source)
    raw = write(output / 'model.json', model)
    data['identity']['model_sha256'] = sha(output / 'model.json')
    data['identity']['binary_sha256'] = sha(binary)
    r = certificate['parameter_ranges']
    envelope = {
        **{dst: r[src] for src, dst in [
            ('vb','vb_v'),('vref','vref_v'),('rref','rref_ohm'),
            ('rlt','rlow_top_ohm'),('rlb','rlow_bottom_ohm'),
            ('rht','rhigh_top_ohm'),('rhb','rhigh_bottom_ohm'),
            ('rdiag','rdiag_p_ohm'),('rdiag','rdiag_n_ohm'),
            ('rwin','rwindow_ohm'),('cdiff','cdiff_f'),
            ('cground','cground_p_f'),('cground','cground_m_f')
        ]},
        'rtd_ohm':[100,194.1], 'rtd_short_ohm':[0,10],
        **{f'lead_{n}_ohm':[1,50] for n in ['sp','sn','fp','fn']},
        'i_max_p_a':14e-9,'i_max_n_a':14e-9,'i_window_a':20e-9,
        'i_low_a':5e-9,'i_high_a':5e-9,'offset_v':.004,
        'overdrive_v':.020,'conditional_delay_ns':65,
    }
    receipt = {
        'schema':'zapote.rtd.model-qualification.v2', 'status':'qualified',
        'model_artifact_utf8':raw,'model_sha256':data['identity']['model_sha256'],
        'model_source_artifact_utf8':source.read_text(),
        'source_hashes':{
            'board_sha256':data['identity']['board_sha256'],
            'source_manifest_sha256':data['identity']['source_manifest_sha256'],
            'topology_source_sha256':data['identity']['source_manifest_sha256'],
            'model_source_sha256':sha(source),
        },
        'reference_envelope':{'vin_v':[3.135,3.465],'baseline_v':5,
            'regulation_ppm_per_v':35,'load_ppm_per_ma':20,
            'initial_tolerance_pct':.05,'drift_ppm_per_c':8,
            'delta_temp_c':60,'vref_v':[1.24869,1.25131]},
        'parameter_envelope':envelope,'cases':cases,
        'allocations':{'conditional_comparator_ns':55,'conditional_logic_ns':10,'max_detect_ms':2},
        'device_applicability':{'status':'indeterminate','review_sha256':sha(AUDIT/'applicability-review.json')},
    }
    data['model_qualification'] = receipt
    write(output/'qualification.json',receipt)
    write(output/'input.json',data)
    print(output/'input.json')


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve())
