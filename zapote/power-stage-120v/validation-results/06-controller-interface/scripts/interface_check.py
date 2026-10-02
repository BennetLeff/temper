#!/usr/bin/env python3
"""D10 one-off structural extraction/calculation, not a permanent engineering gate.

No third-party dependencies. Reads committed CAD/source bytes, never imports the
workspace or rewrites CAD. JSON output exposes correspondence gaps, not passes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[5]
UNIT = Path('zapote/power-stage-120v')
OUT = UNIT / 'validation-results/06-controller-interface'
BASE = '587447466ba1fbf04eab29d8d099a2cacc9b2726'
BOARDS = {
    'power': UNIT / 'native-17/section.kicad_pcb',
    **{name: Path(f'zapote/{name}/candidate/section.kicad_pcb') for name in
       ('interlock', 'gate-drive', 'current-sense', 'thermal-sense')},
    'rtd': Path('zapote/rtd/unit/candidate/section.kicad_pcb'),
    'controller_monolith': Path('pcb/temper.kicad_pcb'),
}
SOURCES = [UNIT / 'elec/src/power_stage_120v.ato', UNIT / 'elec/src/parts.ato',
    UNIT / 'frozen/default.csv', UNIT / 'frozen/resolved-components.json',
    Path('elec/src/main.ato'), Path('elec/src/modules.ato'), Path('elec/src/components.ato'),
    Path('firmware/components/hal/include/temper_pins.h'),
    Path('zapote/ports.toml'), Path('zapote/project.toml'),
    Path('zapote/interlock/interface-contract.json'),
    *[Path(f'zapote/{n}/INTERFACES.md') for n in ('interlock','gate-drive','current-sense','thermal-sense')],
    Path('zapote/rtd/unit/HANDOFF.md'), Path('zapote/rtd/unit/profile.json'),
    Path('zapote/rtd/unit/candidate/source-manifest.json'),
    Path('zapote/interlock/source-build-02/elec/src/interlock_unit.ato'),
    Path('zapote/gate-drive/source-build-09/elec/src/gate_drive_unit.ato'),
    Path('zapote/current-sense/source-build-04/elec/src/current_sense_unit.ato'),
    Path('zapote/thermal-sense/source-build-02/elec/src/thermal_sense_unit.ato')]


def parse(text: str) -> list[Any]:
    """Strict balanced S-expression parser; quoted atoms decoded with JSON rules."""
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', text)
    stack: list[list[Any]] = [[]]
    for token in tokens:
        if token == '(':
            child: list[Any] = []
            stack[-1].append(child)
            stack.append(child)
        elif token == ')':
            if len(stack) == 1:
                raise ValueError('unexpected closing parenthesis')
            stack.pop()
        else:
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    if len(stack) != 1 or len(stack[0]) != 1:
        raise ValueError('unbalanced or multiple documents')
    return stack[0][0]


def children(node: list[Any], key: str) -> list[list[Any]]:
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


def one(node: list[Any], key: str) -> list[Any]:
    matches = children(node, key)
    if len(matches) != 1:
        raise ValueError(f'expected one {key}, got {len(matches)}')
    return matches[0]


def board(path: Path) -> dict[str, Any]:
    doc = parse((ROOT / path).read_text())
    components = {}
    for fp in children(doc, 'footprint'):
        props = {p[1]: p[2] for p in children(fp, 'property')}
        ref = props['Reference']
        pads = {}
        for pad in children(fp, 'pad'):
            if not pad[1]:
                continue
            nets = children(pad, 'net')
            net = nets[0][-1] if nets else None
            if pad[1] in pads and pads[pad[1]]['net'] != net:
                raise ValueError(f'{path} {ref}.{pad[1]} duplicate net conflict')
            pads[pad[1]] = {'net': net, 'local_xy_mm': one(pad, 'at')[1:3]}
        components[ref] = {'value': props.get('Value'), 'pads': pads}
    return components


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    paths = [*BOARDS.values(), *SOURCES, UNIT / 'frozen/default.net']
    identities = {str(p): hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}
    # Refuse silent input drift; output folder never enters its own source identity.
    for path in paths:
        original = subprocess.run(['git','show',f'{BASE}:{path}'], cwd=ROOT,
                                  check=True, capture_output=True).stdout
        if hashlib.sha256(original).hexdigest() != identities[str(path)]:
            raise ValueError(f'input changed from cited commit: {path}')
    native = {name: board(path) for name, path in BOARDS.items()}
    netdoc = parse((ROOT / UNIT / 'frozen/default.net').read_text())
    nets = {one(n, 'name')[1]: sorted(f'{one(p,"ref")[1]}.{one(p,"pin")[1]}'
            for p in children(n,'node')) for n in children(one(netdoc, 'nets'),'net')}
    j4_netlist = {pin: name for name, nodes in nets.items() for node in nodes
                  if node.startswith('J4.') for pin in [node.split('.')[1]]}
    source = (ROOT / SOURCES[0]).read_text()
    source_map = dict(re.findall(r'j_selv\.p(\d+)\s*~\s*(\w+)', source))
    rows = []
    for pin in map(str, range(1,17)):
        actual = native['power']['J4']['pads'][pin]['net']
        rows.append({'pin': int(pin), 'source': source_map[pin], 'netlist': j4_netlist[pin],
                     'native': actual, 'equal': source_map[pin].lower() == actual == j4_netlist[pin],
                     'nodes': nets[actual], 'cable_counterpart': None})
    if not all(row['equal'] for row in rows):
        raise ValueError('source/netlist/native J4 mismatch; inspect before reporting')
    key = re.compile(r'(PWM|V_BUS|I_SENSE|ESP32|LMR51430|PERMIT|SHUTDOWN)',re.I)
    picked = {name: {ref: data for ref,data in comps.items() if
              ref.startswith('J') or key.search(data['value'] or '') or
              any(key.search(p['net'] or '') for p in data['pads'].values())}
              for name,comps in native.items()}
    relevant_nets = {n:v for n,v in nets.items() if n.startswith(('ct_','leg_a-permit', 'leg_b-permit')) or
                    n in ('v3v3','v15_selv','selv_gnd','pe','bus_fault','bus_fault_iso','vbus_p','vbus_n')}
    native_net_diff = {}
    for name, expected in relevant_nets.items():
        actual = sorted(f'{ref}.{pin}' for ref, comp in native['power'].items()
                        for pin, pad in comp['pads'].items() if pad['net'] == name)
        if actual != expected:
            native_net_diff[name] = {'netlist': expected, 'native': actual}
    if native_net_diff:
        raise ValueError(f'power interface native/netlist mismatch: {native_net_diff}')
    source_lines = {str(p): [{'line': i, 'text': line} for i,line in enumerate((ROOT/p).read_text().splitlines(),1)
                            if re.search(r'\.p\d.*~|~.*\.p\d|unit_io\.|PWM|pwm_|adc_v_bus|gnd ~ pe|r_fe\.|permit|PERMIT',line)]
                    for p in SOURCES if p.suffix in ('.ato','.h','.toml')}
    rtop, rbot = 1880000, 15800
    cases = []
    for bus in (0,198,280):
        vin = bus*rbot/(rtop+rbot)
        cases.append({'bus_v':bus,'amc_input_nominal_v':vin,'in_guaranteed_input_range_nominal':vin<=2,
                      'nominal_linear_outp_v':1.44+vin/2 if vin<=2 else None,
                      'nominal_linear_outn_v':1.44-vin/2 if vin<=2 else None,
                      'hypothetical_12bit_3v3_differential_code':round(4095*vin/3.3) if vin<=2 else None,
                      'actual_ADC_code':None})
    calc = {
      'adc_cases':cases, 'amc_2V_bus_limit_nominal_v':2*(rtop+rbot)/rbot,
      'amc_2V_bus_limit_tolerance_low_v':2*(rtop*.99+rbot*1.001)/(rbot*1.001),
      'amc_input_280V_tolerance_low_v':280*rbot*.999/(rtop*1.01+rbot*.999),
      'pwm_high_impedance_example_VOH_v':.8*3.3,
      'pwm_high_impedance_example_VOL_v':.1*3.3,
      'pwm_pulldown_max_a':3.465/50000,
      'permit_including_interlock_pulldown_max_a':3.465/9900+2*3.465/(100000*.99+100*.99),
      'interlock_fault_pullup_max_a':3.465/9900,
      'interlock_sink_with_20uA_allowance_a':3.465/9900+20e-6,
      'permit_two_pulldowns_max_a':2*3.465/(100000*.99+100*.99),
      'permit_gate_at_2V7_min_v':2.7*(100000*.99)/(100000*.99+100*1.01),
      'dis_pulls_max_a':2*3.465/(1000*.99),
      'bias_divider_max_a':3.465/(2000*.999),
      'reference_dividers_max_a':2*3.465/(13320*.999),
      # This is a conditional component allowance, NOT a certified rail budget.
      'v3v3_conditional_allowance_a':2*.0048+.0072+.0056+3*65e-6+10e-6+
                                   2*3.465/990+3.465/1998+2*3.465/(13320*.999),
      'ct_nominal_monitor_v':{str(i):[1.65-1.5*i/100,1.65+1.5*i/100] for i in (0,37,61,71)},
      'ct_nominal_burden_power_18A7rms_w':(18.7/100)**2*1.5,
      'ground_contacts':[r['pin'] for r in rows if r['native']=='selv_gnd'],
    }
    historical = subprocess.run(['git','show',f'{BASE}:{OUT}/README.md'],cwd=ROOT,check=True,capture_output=True).stdout
    report_bytes=(ROOT/OUT/'README.md').read_bytes()
    if not report_bytes.startswith(historical):
        raise ValueError('historical CT record was altered')
    evidence={'source_commit':BASE,'evidence_class':'exact structural and explicitly conditional calculation',
       'runtime':'Python standard library; no native or Rust builds', 'input_sha256':identities,
       'historical_readme_preserved':report_bytes.startswith(historical),
       'historical_readme_sha256':hashlib.sha256(historical).hexdigest(),
       'j4':rows,'counterpart_native_connectors_and_selected_nodes':picked,
       'power_key_nets':relevant_nets,'power_key_native_netlist_differences':native_net_diff,'source_lines':source_lines,'calculations':calc,
       'harness_status':'No declared mapping. Candidate roles are not cable correspondence.'}
    text=json.dumps(evidence,indent=2,sort_keys=True)+'\n'
    if args.output:
        args.output.write_text(text)
    else:
        print(text,end='')

if __name__ == '__main__':
    main()
