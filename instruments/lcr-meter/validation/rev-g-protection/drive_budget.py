"""Rev G isolation-switch drive, jack residual-voltage sense, and the USB power budget (README, "Drive and sense").

python3 validation/rev-g-protection/drive_budget.py   ->  drive-budget.json; exits 1 if a check fails
LCR_OUT=path writes the report elsewhere (Rev G100: validation/rev-g100/drive-budget.json).

Drive: four TLP172AM photoMOS (one per jack), their LEDs in two strings of two from VRLY (the relay-coil supply:
the switched 5 V rail, U16 output, through R101) through one resistor each, sunk by one AO3400A on GPIO 15 (U1 pin
18; the Q6 pattern: 100 ohm gate resistor, 100 kOhm pull-down, so the switches are open from power-up until the
firmware closes them, and open again within tOFF of losing VBUS). The resistors and R101 are read from
cad/design.json. Both strings share R101 and the source resistance (see Rail below). Checked at
the rail and LED corners:
  - every LED at or above the TLP172AM's recommended 5 mA minimum (RON is specified at IF 5 mA; IFT max 3 mA)
    at the lowest rail and the highest VF, and at or below 25 mA at the highest rail and the lowest VF;
  - during the worst relay pulse (RESET, four coils, 112 mA through R101, VBUS at its 4.40 V minimum),
    every LED still above IFT max, so the switches stay closed through a range change;
  - the coils still see their 3.75 V must-operate voltage with the LED current added to R101's drop, at 20 C and
    at a warm relay (T_RELAY).
Sense: each CUR jack (R105 / R106 on the jack side tie each POT jack to it through 1 kOhm) to an RP2040 ADC
pin (GPIO 28 / 29, ADC2 / ADC3, Rev E / F's optional UART header, which Rev G drops) through R_TOP from the jack,
biased to mid-scale by R_BIAS to 3V3 and R_GND to ground, C_PIN to ground, all read from cad/design.json. Checked:
  - the pin stays inside 0..3.3 V for the whole clamp range of the jack TVS (+-10 V, H4V5HD3B VC at 40 A);
  - the bias current the divider pushes into a jack at 0 V, and what it does on the LCUR side (it flows through
    the TIA: a DC offset of I x RF at the TIA output, against its swing);
  - the AC load the divider puts on LCUR (R_TOP to AC ground), as a fixed fraction calibration removes;
  - the filter: settling to the close threshold (against the firmware's stable window), and the 46 Hz source
    tone's ripple at the pin.
Power: Rev F's 0.46 A estimate (rev-f-handoff.md) plus the drive, against USB 2.0's 500 mA.
Rail (G100 audit RCG-03): the coil and LED rail at R101 is computed from the routed copper, not taken as Rev F's
4.32 V. From VBUS 4.40 V at J1: the J1 -> U16 entry, U16's rDS(on) max and the 5V copper U16.6 -> R101.1
(routing.json, 60 C board), all carrying the board's 0.46 A plus the drive. Past R101, a nodal solve of the VRLY
and RLY_RST copper with every relay's RESET coil drawing I_COIL gives the worst coil's copper drop; Q2 (the shared
RESET sink) drops its rDS(on) at the four-coil current.

Sources: part-selection/parts.json (TLP172AM: IF 5-25 mA recommended, VF 1.1 / 1.27 / 1.4 V, IFT 3 mA max,
tON 2 ms max, tOFF 0.5 ms max; H4V5HD3B VC 10 V at 40 A); rev-e-plan 2026-10-21 (switched 5 V 4.32 V minimum
after U16 at VBUS 4.40 V; 5.5 V maximum); rev-f-handoff.md (0.46 A at attach); firmware-rev-e/README.md "Relays"
(TQ2SA-L2-5V 28.1 mA per coil, RESET drives four; the rail at least 4.30 V during it; 3.75 V must-operate).
"""

import json
import math
import os
import pathlib
import re
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'validation' / 'power-spurs'))
import copper as cu  # noqa: E402

VBUS = (4.40, 5.0, 5.5)            # at J1: USB 2.0 device minimum, nominal, Type-C vSafe5V maximum
U16_RDS = 0.135                    # TPS2553 rDS(on) max (power-spurs/regulator_check.py, SLVS841F 7.5)
R_ENTRY = 0.045                    # J1 -> U16 copper (power-spurs/regulator_check.py)
Q_RDS = 0.048                      # AO3400A rDS(on) max at VGS 2.5 V (Q2, the shared RESET sink)
DT_BOARD = 35.0                    # K above 25 C: a 60 C board, as regulator_check.py
I_COIL, N_RESET = 28.1e-3, 4       # TQ2SA-L2-5V per coil at 5 V (overstates it at 4.3 V); RESET drives all four
V_MUST_OPERATE = 3.75             # at 20 C
T_RELAY = 45.0                     # C: a 30-35 C bench plus about 10 C inside the box (G100 audit RCG-01)
VF = (1.1, 1.27, 1.4)              # TLP172AM LED VF min / typ / max at 10 mA
IF_MIN, IF_MAX, IFT_MAX = 5e-3, 25e-3, 3e-3
LEDS_PER_STRING, STRINGS = 2, 2
RDS_ON = 0.05                      # AO3400A at VGS 3.3 V (order of; negligible against R_LED)
T_ON_MAX, T_OFF_MAX = 2e-3, 0.5e-3

V33 = 3.3
V_CLAMP = 10.0                     # H4V5HD3B VC max at 40 A (8/20): the jack never sits beyond it
# firmware-rev-e/src/jackguard.h; main() checks they are equal. Close: the jacks within CLOSE_DIFF of each other and
# each inside CLOSE_LO..CLOSE_HI. Trip: HCUR beyond TRIP, LCUR beyond TRIP_LC once closed (audit PROT-01, G-AFE-01).
CLOSE_DIFF_MV, CLOSE_LO_MV, CLOSE_HI_MV, TRIP_MV, TRIP_LC_MV = 1000, -1000, 2650, 3000, 500
SETTLE_MS = 40                     # jackguard.h JG_SETTLE_MS: closed to ready
POLL_MS = 5                        # jackguard.h JG_POLL_MS
RF = {100: 100.0, 5000: 5e3, 100000: 100e3}
TIA_SWING = 11.0                   # OPA2810 output on +-12 V, order of
R_LC_PATH = 1.0 + 10.0 + 22.0      # switch + series R + R94 from the LCUR jack to the virtual ground
F_LOW, VS = 45.8, 1.7              # lowest tone and source amplitude (accuracy_map.py)

USB_BASE_A, USB_LIMIT_A = 0.46, 0.5


def from_design():
    """The drive and sense values on the board (cad/design.json), by net, so a moved or renamed part still resolves."""
    d = json.loads((HERE.parents[1] / 'cad' / 'design.json').read_text())
    parts = d['parts']

    def value(v):
        n, u = re.match(r'([\d.]+)\s*([pnuµkMR]?)', v).groups()
        return float(n) * {'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'µ': 1e-6, 'k': 1e3, 'M': 1e6, 'R': 1, '': 1}[u]

    def between(a, b, kind):
        hits = [p for p in parts if p['kind'] == kind and sorted(p['pins'].values()) == sorted((a, b))]
        assert len(hits) == 1, f'one {kind} between {a} and {b}: {[p["ref"] for p in hits]}'
        return hits[0]['ref'], value(hits[0]['value'])

    leds = [p for p in parts if p['kind'] == 'PHOTOMOS']
    feeds = [between('VRLY', f'ISO_S{i}', 'R') for i in (1, 2)]
    assert feeds[0][1] == feeds[1][1] and len(leds) == LEDS_PER_STRING * STRINGS
    sense = {}
    for net, jack in (('JACK_HC', 'JK_HCUR'), ('JACK_LC', 'JK_LCUR')):
        sense[net] = dict(r_top=between(jack, net, 'R'), r_bias=between(net, '3V3', 'R'), r_gnd=between(net, 'GND', 'R'),
                          c_pin=between(net, 'GND', 'C'))
    assert sense['JACK_HC'].keys() == sense['JACK_LC'].keys() and all(
        sense['JACK_HC'][k][1] == sense['JACK_LC'][k][1] for k in sense['JACK_HC'])
    return dict(revision=d['revision'], r101=between('5V', 'VRLY', 'R'), r_led=feeds, sense=sense)


DESIGN = from_design()
R101 = DESIGN['r101'][1]


def split_crossings(routing, nets):
    """routing with same-net, same-layer tracks that cross mid-segment split at the crossing, so the copper graph
    (which joins segments only at end points and vias) sees the junction KiCad connects."""
    tracks = [t for t in routing['tracks'] if t['net'] not in nets]
    segs = [[t['net'], t['layer'], t['width'], tuple(a), tuple(b)] for t in routing['tracks'] if t['net'] in nets
            for a, b in zip(t['points'], t['points'][1:])]
    cuts = {i: [] for i in range(len(segs))}
    for i, (n1, l1, _, a, b) in enumerate(segs):
        for j in range(i + 1, len(segs)):
            n2, l2, _, c, d = segs[j]
            if (n1, l1) != (n2, l2):
                continue
            den = (b[0] - a[0]) * (d[1] - c[1]) - (b[1] - a[1]) * (d[0] - c[0])
            if abs(den) < 1e-12:
                continue
            t = ((c[0] - a[0]) * (d[1] - c[1]) - (c[1] - a[1]) * (d[0] - c[0])) / den
            u = ((c[0] - a[0]) * (b[1] - a[1]) - (c[1] - a[1]) * (b[0] - a[0])) / den
            if 1e-6 < t < 1 - 1e-6 and 1e-6 < u < 1 - 1e-6:
                x = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
                cuts[i].append(x)
                cuts[j].append(x)
    for i, (net, layer, w, a, b) in enumerate(segs):
        pts = [a] + sorted(cuts[i], key=lambda x: math.dist(a, x)) + [b]
        tracks += [dict(net=net, layer=layer, width=w, points=[list(p), list(q)]) for p, q in zip(pts, pts[1:])]
    return dict(routing, tracks=tracks)


def network_drop(cop, net, source, sinks, amps):
    """Nodal solve of a net's copper: source pad held at 0 V, amps drawn at each sink pad. Returns the largest drop
    (V) and the sink that sees it."""
    adj = cop.graph(net)
    root = ('pad',) + source
    seen, todo = {root}, [root]
    while todo:     # the source's connected copper only
        for b, _, _ in adj[todo.pop()]:
            if b not in seen:
                seen.add(b)
                todo.append(b)
    missing = [sk for sk in sinks if ('pad',) + sk not in seen]
    assert not missing, f'{net}: no copper from {source} to {missing}'
    nodes = sorted(seen, key=str)
    index = {n: i for i, n in enumerate(nodes)}
    g = np.zeros((len(nodes), len(nodes)))
    for a in nodes:
        for b, ohm, _ in adj[a]:
            y = 1e6 if ohm == 0 else 1 / ohm
            g[index[a], index[a]] += y
            g[index[a], index[b]] -= y
    i = np.zeros(len(nodes))
    for sink in sinks:
        i[index[('pad',) + sink]] -= amps
    keep = [k for k in range(len(nodes)) if k != index[('pad',) + source]]
    v = np.zeros(len(nodes))
    v[keep] = np.linalg.solve(g[np.ix_(keep, keep)], i[keep])
    worst = min(sinks, key=lambda sk: v[index[('pad',) + sk]])
    return -float(v[index[('pad',) + worst]]), worst


def copper():
    """Routed copper (60 C) for the rail: the 5V resistance U16.6 -> R101.1 (charged with every current), and the
    largest drop to a relay coil during the four-coil RESET from a nodal solve of VRLY (R101.2 -> each relay's RESET
    coil + pin, 10) and RLY_RST (each relay's pin 6 -> Q2's drain), I_COIL per relay."""
    pads, half, _ = cu.load_pads(ROOT)
    routing, _ = cu.load_routing(ROOT)
    cop = cu.Copper(split_crossings(routing, {'VRLY', 'RLY_RST'}), pads, half, dt_from_20c=25 + DT_BOARD - 20)
    parts = {p['ref']: p for p in json.loads((ROOT / 'cad' / 'design.json').read_text())['parts']}
    r101 = DESIGN['r101'][0]
    relays = sorted(r for r in parts if r.startswith('K'))
    assert all(parts[k]['pins']['10'] == 'VRLY' and parts[k]['pins']['6'] == 'RLY_RST' for k in relays)
    (q,) = [(r, n) for r, p in parts.items() if r.startswith('Q') for n, x in p['pins'].items() if x == 'RLY_RST']
    trunk = cop.path('5V', [('U16', '6')], [(r101, '1')])
    assert trunk['routed'], 'no routed 5V path U16.6 -> R101.1'
    vrly, at_v = network_drop(cop, 'VRLY', (r101, '2'), [(k, '10') for k in relays], I_COIL)
    rst, at_r = network_drop(cop, 'RLY_RST', q, [(k, '6') for k in relays], I_COIL)
    return dict(trunk=dict(ohm=trunk['ohm'], mm=trunk['mm']), vrly_drop_v=vrly, vrly_worst=at_v[0],
                rly_rst_drop_v=rst, rly_rst_worst=at_r[0])


COPPER = copper()
R_LED = DESIGN['r_led'][0][1]
R_TOP, R_BIAS, R_GND, C_PIN = (DESIGN['sense']['JACK_HC'][k][1] for k in ('r_top', 'r_bias', 'r_gnd', 'c_pin'))


def drive():
    """Each corner solved for the LED current with the shared drops: the source resistance up to R101.1 (entry, U16,
    trunk) carries the board's base current, the coils and both strings; R101 carries the coils and both strings."""
    r_src = R_ENTRY + U16_RDS + COPPER['trunk']['ohm']
    out = {}
    for name, vbus, vf, i_coil, base in (('worst_low', VBUS[0], VF[2], 0.0, USB_BASE_A),
                                         ('typical', VBUS[1], VF[1], 0.0, USB_BASE_A),
                                         ('worst_high', VBUS[2], VF[0], 0.0, 0.0),
                                         ('reset_pulse', VBUS[0], VF[2], N_RESET * I_COIL, USB_BASE_A)):
        v0 = vbus - r_src * (base + i_coil) - R101 * i_coil
        i = (v0 - LEDS_PER_STRING * vf) / (R_LED + RDS_ON + STRINGS * (R101 + r_src))
        v5 = vbus - r_src * (base + i_coil + STRINGS * i)
        vrly = v5 - R101 * (i_coil + STRINGS * i)
        copper_v = (COPPER['vrly_drop_v'] + COPPER['rly_rst_drop_v']) if i_coil else 0.0
        coil = vrly - copper_v - Q_RDS * i_coil
        out[name] = dict(vbus=vbus, v5_at_r101=v5, vf=vf, i_coil_ma=i_coil * 1e3, i_string_ma=i * 1e3,
                         i_total_ma=STRINGS * i * 1e3, vrly=vrly, coil_v=coil)
    return out


def sense():
    g = 1 / R_TOP + 1 / R_BIAS + 1 / R_GND
    gain, mid = (1 / R_TOP) / g, (V33 / R_BIAS) / g
    pin = {f'{v:+g} V': mid + gain * v for v in (-V_CLAMP, 0.0, V_CLAMP)}
    i_bias = mid / R_TOP                       # into a jack held at 0 V
    tau = C_PIN / g
    # An open jack (or a passive DUT) floats at the pin's own bias: no current in R_TOP, so jack = pin = mid.
    # Open: from a jack clamped at -10 V back to the float, against the other jack at the float, to the close difference.
    settle = tau * math.log((V_CLAMP + mid) / (CLOSE_DIFF_MV / 1e3))
    # Closed: the front end pulls both jacks to 0 V; the sense falls from the highest closable reading to TRIP_LC
    lc_settle = tau * math.log((CLOSE_HI_MV / 1e3) / (TRIP_LC_MV / 1e3)) + T_ON_MAX
    ripple = VS / math.sqrt(1 + (2 * math.pi * F_LOW * tau) ** 2)
    return dict(gain=gain, mid_v=mid, pin_v=pin, full_scale_jack_v=[-mid / gain, (V33 - mid) / gain],
                open_jack_float_v=mid, bias_into_jack_ua=i_bias * 1e6,
                tia_dc_offset_v={str(r): i_bias * rf for r, rf in RF.items()},
                lcur_ac_load=R_LC_PATH / R_TOP, tau_ms=tau * 1e3, settle_ms=settle * 1e3,
                lc_trip_settle_ms=lc_settle * 1e3,
                tone_ripple_at_46hz_jack_v=ripple)


def main():
    d, s = drive(), sense()
    p = USB_BASE_A + d['typical']['i_total_ma'] / 1e3
    h = (HERE.parents[1] / 'firmware-rev-e' / 'src' / 'jackguard.h').read_text()
    fw = {k: int(re.search(rf'#define {k} \(?(-?\d+)', h).group(1))
          for k in ('JG_CLOSE_DIFF_MV', 'JG_CLOSE_LO_MV', 'JG_CLOSE_HI_MV', 'JG_TRIP_MV', 'JG_TRIP_LC_MV', 'JG_SETTLE_MS',
                    'JG_RTOP_G_PPM', 'JG_RTOP_RBIAS_PPM', 'JG_POLL_MS', 'JG_STABLE_POLLS')}
    mine = dict(JG_CLOSE_DIFF_MV=CLOSE_DIFF_MV, JG_CLOSE_LO_MV=CLOSE_LO_MV, JG_CLOSE_HI_MV=CLOSE_HI_MV,
                JG_TRIP_MV=TRIP_MV, JG_TRIP_LC_MV=TRIP_LC_MV, JG_SETTLE_MS=SETTLE_MS)
    checks = [
        ('firmware thresholds equal these (jackguard.h)', float(all(fw[k] == v for k, v in mine.items())), '>=', 1.0),
        ('open-jack float inside the close window (audit PROT-01): CLOSE_HI - float, V',
         CLOSE_HI_MV / 1e3 - s['open_jack_float_v'], '>=', 0.0),
        ('open-jack float inside the close window: float - CLOSE_LO, V', s['open_jack_float_v'] - CLOSE_LO_MV / 1e3,
         '>=', 0.0),
        ('a closable jack does not trip HCUR: TRIP - CLOSE_HI, V', (TRIP_MV - CLOSE_HI_MV) / 1e3, '>', 0.0),
        ('settle before the LCUR trip arms (JG_SETTLE_MS) >= tON + sense fall CLOSE_HI -> TRIP_LC, ms',
         SETTLE_MS - s['lc_trip_settle_ms'], '>=', 0.0),
        ('firmware divider constants equal these (jackguard.h)',
         float(fw['JG_RTOP_RBIAS_PPM'] == round(R_TOP / R_BIAS * 1e6) and
               fw['JG_RTOP_G_PPM'] == round(R_TOP * (1 / R_TOP + 1 / R_BIAS + 1 / R_GND) * 1e6)), '>=', 1.0),
        ('firmware stable window (JG_STABLE_POLLS x JG_POLL_MS) >= sense settling from the clamp, ms',
         fw['JG_STABLE_POLLS'] * fw['JG_POLL_MS'] - s['settle_ms'], '>=', 0.0),
        ('LED current at the lowest rail, highest VF >= 5 mA', d['worst_low']['i_string_ma'], '>=', IF_MIN * 1e3),
        ('LED current at the highest rail, lowest VF <= 25 mA', d['worst_high']['i_string_ma'], '<=', IF_MAX * 1e3),
        ('LED current during the RESET pulse, lowest rail, highest VF > IFT max 3 mA', d['reset_pulse']['i_string_ma'],
         '>=', IFT_MAX * 1e3),
        ('relay coil voltage during the RESET pulse, VBUS 4.40 V, routed copper >= 3.75 V must-operate (20 C)',
         d['reset_pulse']['coil_v'], '>=', V_MUST_OPERATE),
        (f'relay coil voltage during the RESET pulse >= must-operate at a {T_RELAY:g} C relay (coil copper +0.4 %/C, '
         'TQ catalog guideline)', d['reset_pulse']['coil_v'], '>=', V_MUST_OPERATE * (1 + 0.004 * (T_RELAY - 20))),
        ('sense pin at -10 V jack >= 0 V', s['pin_v']['-10 V'], '>=', 0.0),
        ('sense pin at +10 V jack <= 3.3 V', s['pin_v']['+10 V'], '<=', V33),
        ('TIA DC offset from the sense bias, 100 k range <= 2 % of the swing',
         s['tia_dc_offset_v']['100000'], '<=', 0.02 * TIA_SWING),
        ('46 Hz tone ripple at the sense, as jack volts < the HCUR trip threshold',
         s['tone_ripple_at_46hz_jack_v'], '<', TRIP_MV / 1e3),
        ('USB load with the drive (typical) <= 0.5 A', p, '<=', USB_LIMIT_A),
    ]
    rows = []
    ok = True
    for name, v, op, lim in checks:
        good = {'>=': v >= lim, '<=': v <= lim, '<': v < lim, '>': v > lim}[op]
        ok &= good
        rows.append(dict(check=name, value=round(v, 6), limit=lim, pass_=good))
        print(('PASS' if good else 'FAIL'), f'{name}: {v:.4g} ({op} {lim:g})')
    out = dict(design={k: v for k, v in DESIGN.items()}, copper_ohm=COPPER, drive=d, sense=s,
               usb_a=dict(base=USB_BASE_A, with_drive_typ=p,
                          with_drive_max=USB_BASE_A + d['worst_high']['i_total_ma'] / 1e3),
               timing=dict(t_on_max_ms=T_ON_MAX * 1e3, t_off_max_ms=T_OFF_MAX * 1e3),
               thresholds_mv={k: v for k, v in mine.items()}, checks=rows, pass_=ok)
    pathlib.Path(os.environ.get('LCR_OUT', HERE / 'drive-budget.json')).write_text(json.dumps(out, indent=1) + '\n')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
