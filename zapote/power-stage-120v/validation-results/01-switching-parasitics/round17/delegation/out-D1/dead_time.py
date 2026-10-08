"""D1 evidence only: extract fitted DT network and calculate labelled estimates.

No third-party dependencies, builds, simulation, or design writes. TI SLUSE89C
pp. 10, 25, 33; Yageo RC0603FR-0739KL specsheet p. 1. See README.md.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import platform
import re

ROOT = next(p for p in Path(__file__).resolve().parents if (p / '.git').exists())
POWER = ROOT / 'zapote/power-stage-120v'
SLOPE = 8.6
OFFSET = 13.0
R_KOHM = 39.0
TOL = 0.01
TCR = 100e-6
# Datasheet electrical-characteristic test points; no 39-kohm guaranteed row.
TI_ROWS = ((10.0, 86.0, 99.0, 112.0), (20.0, 167.0, 185.0, 203.0),
           (50.0, 399.0, 443.0, 487.0))


def sexpr(path: Path) -> list:
    """Read balanced KiCad S-expressions without importing the workspace."""
    stack: list[list] = [[]]
    for token in re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+', path.read_text()):
        if token == '(':
            node: list = []
            stack[-1].append(node)
            stack.append(node)
        elif token == ')':
            if len(stack) == 1:
                raise ValueError(f'Unbalanced input: {path}')
            stack.pop()
        else:
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    if len(stack) != 1 or len(stack[0]) != 1:
        raise ValueError(f'Unbalanced input: {path}')
    return stack[0][0]


def children(node: list, tag: str) -> list[list]:
    return [x for x in node if isinstance(x, list) and x and x[0] == tag]


def child(node: list, tag: str) -> list:
    matches = children(node, tag)
    if len(matches) != 1:
        raise ValueError(f'Expected one {tag}, found {len(matches)}')
    return matches[0]


def main() -> None:
    print('Source base: 67aec36f8c876a7026c07ce3752105ab34d3ce46')
    print(f'Runtime: Python {platform.python_version()}; model/provider: GPT-6 Astra/OpenAI')
    files = [POWER / 'frozen/default.csv', POWER / 'frozen/default.net',
             POWER / 'native-17/section.kicad_pcb', ROOT / 'datasheets/ucc21550.pdf',
             ROOT / 'docs/hardware/power-section-120v/POWER-SECTION.md',
             POWER / 'validation-plan/06-controller-interface.md',
             POWER / 'validation-results/01-switching-parasitics/round17/d2/leg_matrix.cir']
    for path in files:
        print(f'SHA256 {hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(ROOT)}')
    with files[0].open(newline='') as stream:
        bom = {ref: row['Comment'] for row in csv.DictReader(stream)
               for ref in row['Designator'].split(',')}
    nets: dict[str, set[str]] = {}
    for net in children(child(sexpr(files[1]), 'nets'), 'net'):
        nets[child(net, 'name')[1]] = {
            f'{child(n, "ref")[1]}.{child(n, "pin")[1]}' for n in children(net, 'node')}
    pcb: dict[str, set[str]] = {}
    properties: dict[str, dict[str, str]] = {}
    for fp in children(sexpr(files[2]), 'footprint'):
        props = {p[1]: p[2] for p in children(fp, 'property')}
        ref = props['Reference']
        properties[ref] = props
        for pad in children(fp, 'pad'):
            for net in children(pad, 'net'):
                pcb.setdefault(net[-1], set()).add(f'{ref}.{pad[1]}')
    for driver, resistor, leg in [('U1', 'R9', 'a'), ('U2', 'R17', 'b')]:
        name = f'leg_{leg}.driver-dt'
        expected = {f'{driver}.6', f'{resistor}.1'}
        if nets[name] != expected or pcb[name] != expected:
            raise ValueError(f'DT connectivity contradiction: {name}')
        if bom[resistor] != 'RC0603FR-0739KL' or bom[driver] != 'UCC21550BDWKR':
            raise ValueError('Unexpected fitted part')
        for ref in (driver, resistor):
            if properties[ref]['Value'] != bom[ref]:
                raise ValueError(f'Board/BOM contradiction: {ref}')
        for pin in (f'{resistor}.2', f'{driver}.4'):
            if pin not in nets['selv_gnd'] or pin not in pcb['selv_gnd']:
                raise ValueError(f'Wrong DT ground: {pin}')
        print(f'\n{name}: {", ".join(sorted(expected))}; board/netlist agree')
        print(f'{resistor}: {bom[resistor]}, 39 kohm +/-1%, +/-100 ppm/C; pin 2 SELV_GND')
        for pin in (1, 2, 5):
            name = next(n for n, pins in nets.items() if f'{driver}.{pin}' in pins)
            if nets[name] != pcb[name]:
                raise ValueError(f'Board/netlist contradiction: {name}')
            print(f'{driver}.{pin}: {name}: {", ".join(sorted(nets[name]))}')
    print('\nTI p10 guaranteed test-point rows: R[kohm] min/typ/max[ns]')
    for row in TI_ROWS:
        print(' '.join(f'{v:g}' for v in row))
    print('\nESTIMATES ONLY: linear interpolation between TI 20/50-kohm limit rows.')
    print('Resistor temperature assumed equal to labelled T; reference 25 C.')
    print('T[C] Rmin[kohm] Rmax[kohm] DTmin_est[ns] DTnom_fit[ns] DTmax_est[ns]')
    for temperature in (-40, 25, 150):
        drift = abs(temperature - 25) * TCR
        rmin = R_KOHM * (1 - TOL) * (1 - drift)
        rmax = R_KOHM * (1 + TOL) * (1 + drift)
        low = 167 + (rmin - 20) * (399 - 167) / (50 - 20)
        high = 203 + (rmax - 20) * (487 - 203) / (50 - 20)
        print(f'{temperature:4} {rmin:.6f} {rmax:.6f} {low:.3f} '
              f'{SLOPE * R_KOHM + OFFSET:.3f} {high:.3f}')
    print('\nInput-dominated conditional opposite-edge skew bound:')
    print('-40..-10 C: tDM+tPWD = 6.5+5 = 11.5 ns')
    print('-10..150 C: tDM+tPWD = 5+5 = 10 ns')
    print('These are not extra deductions from measured DTS output limits.')
    print('Guaranteed 39-kohm board minimum: NOT ESTABLISHED.')
    print('250 ns unreachable: NOT PROVEN; retain existing stress corner.')


if __name__ == '__main__':
    main()
