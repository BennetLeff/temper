"""Every capacitor's voltage rating and every resistor's power and working voltage against the
worst-case voltage across it (read-only).

Run:  python3 validation/passive-ratings/passive_ratings_check.py
Writes validation/passive-ratings/passive-ratings-check.json and exits 1 on any finding.

The datasheet audit (validation/datasheet-audit-rev-f/) reviewed the semiconductors, regulators,
inductors and the protection parts one by one; this is the complete, mechanical pass over the
passives, so that no capacitor or resistor is left unreviewed.

Method: each net gets a worst-case interval [min, max] in volts. Supply nets come from
power-spurs/regulator_check.json (the TPS65131 and LDO output corners) and the hot-plug model;
nets that only touch 3.3 V logic get [0, 3V3 max]; every other net gets the widest analog
interval, [RAW_N min, RAW_P max]. The worst voltage across a two-pad part is the larger of
max(a) - min(b) and max(b) - min(a). Where that bound is loose for a low-value resistor, the
resistor's real current is given in CURRENT with its source, and P = I^2 R is used instead.

Limits:
  - capacitor: worst voltage <= rating (finding); class II (X5R/X7R) above 80 % of the rating is a
    NOTE (DC-bias loss; the regulator check already counts retention where it matters);
  - resistor: power <= 50 % of 0.1 W (0603 rating at 70 C, UNI-ROYAL 0603WAF / Yageo RC0603 /
    RT0603: 1/10 W) is a pass, 50-100 % a NOTE, above the rating a finding; working voltage <= 50 V
    (UNI-ROYAL 0603WAF, the lowest of the three families).
"""
import json
import math
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get('LCR_ROOT') or Path(__file__).resolve().parents[2])  # LCR_ROOT: mutation tests on a copy
OUT = Path(__file__).resolve().parent / 'passive-ratings-check.json'
design = json.loads((ROOT / 'cad/design.json').read_text())
reg = json.loads((ROOT / 'validation/power-spurs/regulator_check.json').read_text())
hot = json.loads((ROOT / 'validation/power-spurs/hotplug_spice.json').read_text())
parts = {p['ref']: p for p in design['parts']}

V3V3 = 3.3 * 1.02  # AP2112K-3.3: +-2 % output (AP2112 datasheet, electrical characteristics)
RAW_P = reg['vpos']['max']
RAW_N = reg['vneg']['max']  # the most negative corner
P12 = reg['ldo']['pos']['vout'][2]
N12 = -reg['ldo']['neg']['vout'][2]
VBUS_PEAK = 6.5  # hot-plug at U16 IN: worst 6.24 V over 96 corners (hotplug_spice.json), held to the 6.5 V gate
VBUS = 5.5       # Type-C vSafe5V max

NET = {
    'GND': (0, 0),
    'USB_VBUS': (0, VBUS_PEAK), 'VBUS_DAMP': (-1.0, 1.0),  # R121 1.5 ohm to GND carries C113's ring current
    '5V': (0, VBUS), 'CONV_VIN': (0, VBUS), '5VA': (0, VBUS), 'VRLY': (0, VBUS),
    '3V3': (0, V3V3), '3V3A': (0, V3V3), '1V1': (0, 1.1 * 1.05),
    'CODEC_DREG': (0, V3V3), 'CODEC_VREF': (0, 2.75 * 1.02),  # TAC5112 VREF 2.75 V (firmware setting)
    'RAW_P': (0, RAW_P), 'LDOIN_P': (0, RAW_P), 'RAW_N': (RAW_N, 0), 'LDOIN_N': (RAW_N, 0),
    '12V': (0, P12), '-12V': (N12, 0),
    # Source stage (afe.md "Signal path"): codec DAC and U5 inputs sit in the 3.3 V codec domain,
    # EXCITE is +-1.7 V peak.
    'DAC_P': (0, V3V3), 'DAC_M': (0, V3V3), 'SOURCE_AC': (0, V3V3), 'SOURCE_FB': (0, V3V3),
    'SRC_AC_CMID': (0, V3V3), 'SRC_FB_CMID': (0, V3V3), 'EXCITE': (-1.7, 1.7),
    # Codec inputs behind the BAT54S clamps (D11-D14 to GND and 3V3A; VF <= 0.5 V at the clamp currents).
    **{f'{c}_{s}': (-0.5, V3V3 + 0.5) for c in ('C1P', 'C1M', 'C2P', 'C2M') for s in ('CLP', 'PIN')},
}
for _n in ('RNG_RESET_G', 'RNG_SET_LO_G', 'RNG_SET_MED_G', 'RNG_SET_HI_G', 'RNG_SET_REF_G'):
    NET[_n] = (0, V3V3)  # AO3400A gates: 100 R from a GPIO, 100 k to GND
LOGIC_KINDS = {'RP2040', 'FLASH', 'LED', 'SW', 'CRYSTAL', 'SEQ', 'USB'}
def ohms(value):
    m = re.match(r'([\d.]+)\s*([kMR]?)', value)
    return float(m.group(1)) * {'k': 1e3, 'M': 1e6, 'R': 1, '': 1}[m.group(2)] if m else None


DRIVE = 1.7  # V peak at EXCITE / U6A (afe.md signal path and AFE-14), held as if DC
R104 = 47.0


def ohm_of(ref):
    return ohms(parts[ref]['value'])


def i_short(rg):
    """Excitation current with the DUT shorted on a range: U6A drives R104 + Rg."""
    return DRIVE / (R104 + ohm_of(rg))


def chain(rail_v, refs):
    return abs(rail_v) / sum(ohm_of(r) for r in refs)


CURRENT = {
    # ref: (amps, source). Series parts, where the voltage bound between two nets is meaningless:
    # the current is set by what drives them. Normal operation only; charged-DUT faults on the jacks
    # are audit items AFE-01 to AFE-04 (a Rev G clamp study), not ratings in intended use.
    'R95': (reg['loads_a']['pos'], 'regulator_check.json loads_a.pos (+12 V rail load)'),
    'R96': (reg['loads_a']['neg'], 'regulator_check.json loads_a.neg (-12 V rail load)'),
    # Step-charging a capacitor through any series R-L dissipates exactly C V^2 / 2 in the resistances,
    # so R121 takes at most that per plug-in; C113 is 2.5-5.2 uF with bias and tolerance (hotplug_spice.py).
    'R121': (None, f'hot-plug pulse, not a continuous load: at most {0.5 * 5.2e-6 * VBUS ** 2 * 1e6:.0f} uJ per plug-in '
                   f'(C113 5.2 uF max at {VBUS} V), peak current under {VBUS / 1.5:.1f} A for microseconds; '
                   'UNI-ROYAL publishes no 0603WAF pulse curve, so the bench check is bring-up 2a step 3 (repeated USB-A plug-ins, R121 unchanged)'),
    'R101': (4 * 5.0 / 178, 'VRLY: four TQ2SA-L2-5V RESET coils at once, 5 V / 178 ohm each (relay.c, TQ datasheet coil table)'),
    'R80': (10 * 120e-6, 'TPS65131 VIN: control supply only, IQ 120 uA max (7.5), taken 10x'),
    'R3': (3.3 / (28 + 27 + 45), 'USB FS driver 3.3 V into 28 ohm min source + 27 ohm + 45 ohm line, held continuously'),
    'R4': (3.3 / (28 + 27 + 45), 'USB FS driver 3.3 V into 28 ohm min source + 27 ohm + 45 ohm line, held continuously'),
    'R13': (12e-3, 'RP2040 QSPI pad at its 12 mA maximum drive setting (datasheet 2.19.4 / 5.5.3)'),
    **{r: (12e-3, 'RP2040 GPIO at its 12 mA maximum drive setting into an AO3400A gate')
       for r in ('R74', 'R76', 'R78', 'R102', 'R108')},
    'R104': (i_short('R40'), 'U6A drive 1.7 V peak into R104 + R40 (100 R range, DUT shorted)'),
    'R94': (i_short('R40'), 'the DUT current into the TIA: 100 R range, DUT shorted'),
    **{rg: (i_short(rg), f'U6A drive 1.7 V peak into R104 + {rg}, DUT shorted') for rg in ('R40', 'R41', 'R42')},
    **{rf: (i_short(rg), f'the TIA feedback carries the DUT current of {rg}') for rf, rg in (('R43', 'R40'), ('R44', 'R41'), ('R45', 'R42'))},
    **{r: (11.06 / 2000, 'codec input divider (1 k + 1 k) from an OPA2810 output at its +-11.06 V swing (afe.md)')
       for r in ('R60', 'R61', 'R62', 'R63', 'R64', 'R65', 'R66', 'R67')},
    **{r: (DRIVE / 1000, 'at most the 1.7 V excitation across 1 k (DUT nets: DUT_HI <= EXCITE, DUT_LO at the TIA virtual ground)')
       for r in ('R105', 'R106', 'R107')},
    **{r: (chain(N12, ('R87', 'R89', 'R88', 'R112')), 'TPS7A3001 feedback chain R87 + R89 + R88 + R112 from -12 V')
       for r in ('R87', 'R88', 'R89', 'R112')},
}
if design['revision'] == 'G':   # the jack protection (validation/rev-g-protection/), switches closed
    led = json.loads((ROOT / 'validation/rev-g-protection/drive-budget.json').read_text())['drive']['worst_high']
    CURRENT.update({
        **{r: (led['i_string_ma'] / 1e3, 'TLP172AM LED string at 5.5 V and VF min (rev-g-protection/drive-budget.json worst_high)')
           for r in ('R132', 'R133')},
        'R134': (12e-3, 'RP2040 GPIO at its 12 mA maximum drive setting into an AO3400A gate'),
        'R122': (i_short('R40'), 'HCUR series 10 ohm carries the DUT current: 100 R range, DUT shorted'),
        'R125': (i_short('R40'), 'LCUR series 10 ohm carries the DUT current into the TIA: 100 R range, DUT shorted'),
        **{r: (2 * math.pi * 85e3 * 1.025e-9 * DRIVE, 'POT series 100 ohm: the follower input draws nothing; the 1 nF C0G and '
                  'the H3V3LD5B (25 pF max) behind it charge at the 85 kHz top tone, 1.7 V peak taken as RMS')
           for r in ('R123', 'R124')},
    })


def nets_of(ref):
    return [n for n in parts[ref]['pins'].values() if n]


def interval(net):
    if net in NET:
        return NET[net]
    kinds = {parts[ref]['kind'] for ref, p in parts.items() for n in p['pins'].values() if n == net}
    others = {n for ref, p in parts.items() if net in p['pins'].values() for n in p['pins'].values() if n}
    if kinds & LOGIC_KINDS and not kinds & {'OPA810', 'OPA2810', 'TPS7A', 'TPS65131'} and not others & {'RAW_P', 'RAW_N', '12V', '-12V'}:
        return (0, V3V3)
    return (RAW_N, RAW_P)


def across(ref):
    a, b = (interval(n) for n in nets_of(ref))
    return max(a[1] - b[0], b[1] - a[0])


def cap_rating(p):
    m = re.search(r'(\d+(?:\.\d+)?)\s*V\b', p['value'])
    if m:
        return float(m.group(1)), 'value'
    # MPN voltage codes (manufacturer part-numbering guides): Samsung CL10C...JB8 'B' = 50 V;
    # Yageo CC0603...9BN 'B' (9 = 50 V series) = 50 V; Fenghua 0603CG...C500 '500' = 50 V.
    mpn = p['mpn']
    if re.match(r'CL10C\d{3}[JKC]B8', mpn) or re.match(r'CC0603[JK]RNPO9BN', mpn) or re.search(r'500NT$', mpn):
        return 50.0, f'MPN {mpn}'
    return None, f'MPN {mpn} not decoded'


findings, notes, rows = [], [], []
for ref, p in sorted(parts.items()):
    if p.get('assembly') is False or len(nets_of(ref)) != 2:
        continue
    if p['kind'] == 'C':
        v = across(ref)
        rating, src = cap_rating(p)
        row = {'ref': ref, 'value': p['value'], 'nets': nets_of(ref), 'worst_v': round(v, 2), 'rating_v': rating, 'rating_source': src}
        rows.append(row)
        if rating is None:
            findings.append({'ref': ref, 'detail': f'no voltage rating found ({src})'})
        elif v > rating:
            findings.append({'ref': ref, 'detail': f'{v:.2f} V across, rated {rating:g} V'})
        elif re.search(r'X[57]R', p['value']) and v > 0.8 * rating:
            notes.append({'ref': ref, 'detail': f'class II at {v / rating:.0%} of rating ({v:.2f} / {rating:g} V): DC-bias loss'})
    elif p['kind'] == 'R':
        r = ohms(p['value'])
        v = across(ref)
        if ref in CURRENT:
            amps, src = CURRENT[ref]
            power = amps * amps * r if amps is not None else None
        else:
            power, src = v * v / r, 'worst voltage across'
        row = {'ref': ref, 'value': p['value'], 'nets': nets_of(ref), 'worst_v': round(v, 2), 'power_w': power and round(power, 5), 'basis': src}
        rows.append(row)
        if v > 50:
            findings.append({'ref': ref, 'detail': f'{v:.1f} V across, 0603 working voltage 50 V'})
        if power is None:
            notes.append({'ref': ref, 'detail': src})
        elif power > 0.1:
            findings.append({'ref': ref, 'detail': f'{power * 1e3:.1f} mW ({src}), rated 100 mW'})
        elif power > 0.05:
            notes.append({'ref': ref, 'detail': f'{power * 1e3:.1f} mW ({src}): above 50 % of 100 mW'})

result = {'net_intervals_v': {n: [round(a, 3), round(b, 3)] for n, (a, b) in NET.items()},
          'default_analog_interval_v': [round(RAW_N, 3), round(RAW_P, 3)],
          'hotplug_worst_v': hot.get('worst_v') if isinstance(hot, dict) else None,
          'rows': rows, 'findings': findings, 'notes': notes}
OUT.write_text(json.dumps(result, indent=1) + '\n')
n_c = sum(1 for r in rows if 'rating_v' in r)
print(f'{n_c} capacitors, {len(rows) - n_c} resistors; {len(findings)} findings, {len(notes)} notes')
for f in findings:
    print('FINDING', f['ref'], '-', f['detail'])
for n in notes:
    print('NOTE', n['ref'], '-', n['detail'])
sys.exit(1 if findings else 0)
