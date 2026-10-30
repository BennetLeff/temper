"""Supply copper against its worst-case current: every track segment and via of the power nets.

python3 validation/power-spurs/current_check.py      -> current_check.json (exit 1 on any FAIL)

Ampacity: IPC-2152 (2009), the generic chart (Figure 5-2: 0.070 in polyimide board, still air, no plane,
3 oz copper), through the least-squares power fit published with the smps.us PCB calculator
(https://smps.us/pcb-calculator.html, fitted between 2 and 100 C rise; its check point is 10 A at 20 C ->
513 mil^2 against the chart's 500):
    A [mil^2] = (117.555 * dT^-0.913 + 1.15) * I^(0.84 * dT^-0.108 + 1.159),   I in A rms, dT in C.
The same area is used on every layer, as IPC-2152 recommends (internal and external alike).  No modifier is
taken for copper weight, board thickness or planes; the board's solid In1 plane would only lower the rise.
Rise limit 10 C.  Copper: outer 35 um (1 oz, before plating), inner 15.2 um (0.5 oz), JLC04161H-7628
(layout-parasitics/common.py).  A via is a plated barrel, pi * drill * 18 um (copper.py VIA_PLATING_MM,
IPC-6012 class 2 thin-area minimum), treated as a conductor of that cross-section.

Worst current per net (the most the source can deliver into a fault downstream):
    USB_VBUS, 5V   1.17 A  TPS2553 current limit maximum with R110 at -1 % (regulator_check.json)
    RAW_P, 12V     0.50 A  TPS7A4901 ILIM maximum (sources/ti/TPS7A49.txt, 7.5: 220 / 309 / 500 mA)
    RAW_N, -12V    0.50 A  TPS7A3001 ICL maximum (sources/ti/TPS7A30.txt, 7.5: 220 / 330 / 500 mA)
    3V3            0.60 A  AP2112K-3.3 rated output (sources/new/AP2112.txt; no ILIM maximum is given, its
                           foldback limit returns the short-circuit current to 50 mA)
Each net is solved as a resistor network (segments rho L / (w t), via barrels, lands as near-zero links
between the copper they touch) once per fault case: the source part delivers the net's worst current into one
load part at a time (every pin of a part tied together, as inside the part), a resistor load taking only
min(worst, V / R) and capacitors, test pads and fiducials none.  A segment or via is charged the largest
current it carries in any case, so a branch carries the full current only if a load on it could fault.
For USB_VBUS each receptacle VBUS pin is a separate source case (the plug may make contact on one pin only).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'cad' / 'tools'))
import craft  # noqa: E402
import predrc  # noqa: E402

DT = 10.0
T_MM = {'F.Cu': 0.035, 'B.Cu': 0.035, 'In1.Cu': 0.0152, 'In2.Cu': 0.0152}
VIA_PLATING_MM = 0.018
REG = json.loads((HERE / 'regulator_check.json').read_text())
I_TPS2553 = next(c['value'][2] for c in REG['checks'] if c['item'].startswith('TPS2553 current limit'))
NETS = {'USB_VBUS': (I_TPS2553, 5.5, 'TPS2553 ILIM max'), '5V': (I_TPS2553, 5.5, 'TPS2553 ILIM max'),
        'RAW_P': (0.50, 14.9, 'TPS7A49 ILIM max'), '12V': (0.50, 12.4, 'TPS7A49 ILIM max'),
        'RAW_N': (0.50, 14.8, 'TPS7A30 ICL max'), '-12V': (0.50, 12.2, 'TPS7A30 ICL max'),
        '3V3': (0.60, 3.35, 'AP2112K rating')}
SOURCE = {'USB_VBUS': 'J1', '5V': 'U16', 'RAW_P': 'D2', 'RAW_N': 'D3', '12V': 'U11', '-12V': 'U12', '3V3': 'U3'}
NO_LOAD = {'D1': 'SRV05-4 ESD array on VBUS: clamp leakage only'}
RULES = {'rise_c': DT, 'copper_mm': T_MM, 'via_plating_mm': VIA_PLATING_MM, 'board_mm': 1.6,
         'rho': 1.72e-8 * (1 + 0.0039 * 40),   # ohm m at 60 C; only current division depends on it
         'link': 1e-6,                          # ohm: land-to-copper and in-part ties
         'land_neck': 0.35}                     # mm: a segment with less than this outside its lands runs on the land


def width_mm(i, layer):
    return craft.ipc2152_width_mm(i, T_MM[layer], DT)


def via_amps(drill):
    return craft.ipc2152_via_amps(drill, VIA_PLATING_MM, DT)


def ohms(value):
    v = value.split()[0].upper().replace('Ω', '')
    m = re.match(r'^([\d.]+)([RKM]?)([\d]*)$', v)
    if not m:
        return None
    a, unit, b = m.groups()
    x = float(a + ('.' + b if b else ''))
    return x * {'': 1, 'R': 1, 'K': 1e3, 'M': 1e6}[unit]


def main():
    design = json.loads((ROOT / 'cad/design.json').read_text())
    routing = json.loads((ROOT / 'cad/routing.json').read_text())
    parts = {p['ref']: p for p in design['parts']}
    pads, _, _ = predrc.craft_inputs(design)
    rows, vrows, fails = [], [], 0
    for net, (inet, vnet, why) in NETS.items():
        refs = list(dict.fromkeys(p['ref'] for p in pads if p['net'] == net))
        src_pads = [(p['ref'], p['pad']) for p in pads if p['net'] == net and p['ref'] == SOURCE[net]]
        sources = src_pads if net == 'USB_VBUS' else src_pads[:1]   # each VBUS pin is its own case
        loads = []
        for ref in refs:
            part = parts.get(ref)
            if ref == SOURCE[net] or part is None or part['kind'] == 'C' or ref in NO_LOAD or part.get('assembly') == 'DNP':
                continue
            r = ohms(part['value']) if part['kind'] == 'R' else None
            loads.append((ref, min(inet, vnet / r) if r else inet))
        res = craft.current_checks(net, routing, pads, sources, loads, inet, RULES)
        for ref in res['unjoined']:
            print(f'{net}: {ref} has no copper joined to it')
        if res['singular']:
            print(f'{net}: singular network (disconnected copper)')
        rows += res['segments']
        vrows += res['vias']
        fails += len(res['violations'])
    summary = {}
    for net, (inet, _, why) in NETS.items():
        r = [x for x in rows if x['net'] == net]
        v = [x for x in vrows if x['net'] == net]
        summary[net] = {'worst_current_a': inet, 'basis': why, 'source': SOURCE[net], 'segments': len(r),
                        'need_outer_mm': round(width_mm(inet, 'F.Cu'), 3), 'need_inner_mm': round(width_mm(inet, 'In2.Cu'), 3),
                        'max_segment_current_a': max((x['current_a'] for x in r), default=0),
                        'fail_segments': sum(x['status'] == 'FAIL' for x in r), 'vias': len(v),
                        'max_via_current_a': max((x['current_a'] for x in v), default=0),
                        'fail_vias': sum(x['status'] == 'FAIL' for x in v)}
    out = {'method': __doc__.strip(), 'rise_c': DT, 'via_capacity_a_0p3mm': round(via_amps(0.3), 3),
           'no_load': NO_LOAD, 'summary': summary, 'fails': fails,
           'failing_segments': [x for x in rows if x['status'] == 'FAIL'],
           'failing_vias': [x for x in vrows if x['status'] == 'FAIL'], 'segments': rows, 'vias': vrows}
    (HERE / 'current_check.json').write_text(json.dumps(out, indent=1) + '\n')
    for net, s in summary.items():
        print(f"{net:9s} {s['worst_current_a']:.2f} A ({s['basis']}): need {s['need_outer_mm']:.2f} mm outer / "
              f"{s['need_inner_mm']:.2f} mm inner; {s['segments']} segments, {s['fail_segments']} FAIL; "
              f"{s['vias']} vias (max {s['max_via_current_a']:.2f} A), {s['fail_vias']} FAIL")
    print(f"via 0.3 mm drill carries {via_amps(0.3):.2f} A at {DT:.0f} C; {fails} FAIL -> {HERE / 'current_check.json'}")
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
