"""Rev G isolation-switch drive, jack residual-voltage sense, and the USB power budget (README, "Drive and sense").

python3 validation/rev-g-protection/drive_budget.py   ->  drive-budget.json; exits 1 if a check fails

Drive: four TLP172AM photoMOS (one per jack), their LEDs in two strings of two from VRLY (the relay-coil supply:
the switched 5 V rail, U16 output, through R101) through one resistor each, sunk by one AO3400A on GPIO 15 (U1 pin
18; the Q6 pattern: 100 ohm gate resistor, 100 kOhm pull-down, so the switches are open from power-up until the
firmware closes them, and open again within tOFF of losing VBUS). The resistors and R101 are read from
cad/design.json. Both strings share R101, so i = (V5 - R101 I_COIL - 2 VF) / (R_LED + RDS_ON + 2 R101). Checked at
the rail and LED corners:
  - every LED at or above the TLP172AM's recommended 5 mA minimum (RON is specified at IF 5 mA; IFT max 3 mA)
    at the lowest rail and the highest VF, and at or below 25 mA at the highest rail and the lowest VF;
  - during the worst relay pulse (RESET, four coils, 112 mA through R101, the rail at its 4.30 V pulse minimum),
    every LED still above IFT max, so the switches stay closed through a range change;
  - the coils still see their 3.75 V must-operate voltage with the LED current added to R101's drop.
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

Sources: part-selection/parts.json (TLP172AM: IF 5-25 mA recommended, VF 1.1 / 1.27 / 1.4 V, IFT 3 mA max,
tON 2 ms max, tOFF 0.5 ms max; H4V5HD3B VC 10 V at 40 A); rev-e-plan 2026-10-21 (switched 5 V 4.32 V minimum
after U16 at VBUS 4.40 V; 5.5 V maximum); rev-f-handoff.md (0.46 A at attach); firmware-rev-e/README.md "Relays"
(TQ2SA-L2-5V 28.1 mA per coil, RESET drives four; the rail at least 4.30 V during it; 3.75 V must-operate).
"""

import json
import math
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent

V5 = (4.32, 5.0, 5.5)              # switched 5 V: min (VBUS 4.40 V less U16), nominal, max
V5_PULSE_MIN = 4.30                # the same during the RESET pulse (firmware-rev-e/README.md "Relays")
I_COIL, N_RESET = 28.1e-3, 4       # TQ2SA-L2-5V per coil at 5 V (overstates it at 4.3 V); RESET drives all four
V_MUST_OPERATE = 3.75
VF = (1.1, 1.27, 1.4)              # TLP172AM LED VF min / typ / max at 10 mA
IF_MIN, IF_MAX, IFT_MAX = 5e-3, 25e-3, 3e-3
LEDS_PER_STRING, STRINGS = 2, 2
RDS_ON = 0.05                      # AO3400A at VGS 3.3 V (order of; negligible against R_LED)
T_ON_MAX, T_OFF_MAX = 2e-3, 0.5e-3

V33 = 3.3
V_CLAMP = 10.0                     # H4V5HD3B VC max at 40 A (8/20): the jack never sits beyond it
CLOSE_MV, TRIP_MV = 1000, 3000     # firmware-rev-e/src/jackguard.h; main() checks they are equal
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
R_LED = DESIGN['r_led'][0][1]
R_TOP, R_BIAS, R_GND, C_PIN = (DESIGN['sense']['JACK_HC'][k][1] for k in ('r_top', 'r_bias', 'r_gnd', 'c_pin'))


def drive():
    out = {}
    for name, v5, vf, i_coil in (('worst_low', V5[0], VF[2], 0.0), ('typical', V5[1], VF[1], 0.0),
                                 ('worst_high', V5[2], VF[0], 0.0), ('reset_pulse', V5_PULSE_MIN, VF[2], N_RESET * I_COIL)):
        i = (v5 - R101 * i_coil - LEDS_PER_STRING * vf) / (R_LED + RDS_ON + STRINGS * R101)
        out[name] = dict(v5=v5, vf=vf, i_coil_ma=i_coil * 1e3, i_string_ma=i * 1e3, i_total_ma=STRINGS * i * 1e3,
                         vrly=v5 - R101 * (i_coil + STRINGS * i))
    return out


def sense():
    g = 1 / R_TOP + 1 / R_BIAS + 1 / R_GND
    gain, mid = (1 / R_TOP) / g, (V33 / R_BIAS) / g
    pin = {f'{v:+g} V': mid + gain * v for v in (-V_CLAMP, 0.0, V_CLAMP)}
    i_bias = mid / R_TOP                       # into a jack held at 0 V
    tau = C_PIN / g
    settle = tau * math.log(V_CLAMP / (CLOSE_MV / 1e3 / 2))   # from the clamp to half the close threshold
    ripple = VS / math.sqrt(1 + (2 * math.pi * F_LOW * tau) ** 2)
    return dict(gain=gain, mid_v=mid, pin_v=pin, full_scale_jack_v=[-mid / gain, (V33 - mid) / gain],
                bias_into_jack_ua=i_bias * 1e6, tia_dc_offset_v={str(r): i_bias * rf for r, rf in RF.items()},
                lcur_ac_load=R_LC_PATH / R_TOP, tau_ms=tau * 1e3, settle_ms=settle * 1e3,
                tone_ripple_at_46hz_jack_v=ripple)


def main():
    d, s = drive(), sense()
    p = USB_BASE_A + d['typical']['i_total_ma'] / 1e3
    h = (HERE.parents[1] / 'firmware-rev-e' / 'src' / 'jackguard.h').read_text()
    fw = {k: int(re.search(rf'#define {k} (\d+)', h).group(1))
          for k in ('JG_CLOSE_MV', 'JG_TRIP_MV', 'JG_RTOP_G_PPM', 'JG_RTOP_RBIAS_PPM', 'JG_POLL_MS', 'JG_STABLE_POLLS')}
    checks = [
        ('firmware thresholds equal these (jackguard.h)', float(fw['JG_CLOSE_MV'] == CLOSE_MV and fw['JG_TRIP_MV'] == TRIP_MV),
         '>=', 1.0),
        ('firmware divider constants equal these (jackguard.h)',
         float(fw['JG_RTOP_RBIAS_PPM'] == round(R_TOP / R_BIAS * 1e6) and
               fw['JG_RTOP_G_PPM'] == round(R_TOP * (1 / R_TOP + 1 / R_BIAS + 1 / R_GND) * 1e6)), '>=', 1.0),
        ('firmware stable window (JG_STABLE_POLLS x JG_POLL_MS) >= sense settling from the clamp, ms',
         fw['JG_STABLE_POLLS'] * fw['JG_POLL_MS'] - s['settle_ms'], '>=', 0.0),
        ('LED current at the lowest rail, highest VF >= 5 mA', d['worst_low']['i_string_ma'], '>=', IF_MIN * 1e3),
        ('LED current at the highest rail, lowest VF <= 25 mA', d['worst_high']['i_string_ma'], '<=', IF_MAX * 1e3),
        ('LED current during the RESET pulse, lowest rail, highest VF > IFT max 3 mA', d['reset_pulse']['i_string_ma'],
         '>=', IFT_MAX * 1e3),
        ('relay coil voltage during the RESET pulse with the LED current on R101 >= 3.75 V',
         d['reset_pulse']['vrly'] - RDS_ON * N_RESET * I_COIL, '>=', V_MUST_OPERATE),
        ('sense pin at -10 V jack >= 0 V', s['pin_v']['-10 V'], '>=', 0.0),
        ('sense pin at +10 V jack <= 3.3 V', s['pin_v']['+10 V'], '<=', V33),
        ('TIA DC offset from the sense bias, 100 k range <= 2 % of the swing',
         s['tia_dc_offset_v']['100000'], '<=', 0.02 * TIA_SWING),
        ('46 Hz tone ripple at the sense, as jack volts < the trip threshold',
         s['tone_ripple_at_46hz_jack_v'], '<', TRIP_MV / 1e3),
        ('USB load with the drive (typical) <= 0.5 A', p, '<=', USB_LIMIT_A),
    ]
    rows = []
    ok = True
    for name, v, op, lim in checks:
        good = {'>=': v >= lim, '<=': v <= lim, '<': v < lim}[op]
        ok &= good
        rows.append(dict(check=name, value=round(v, 6), limit=lim, pass_=good))
        print(('PASS' if good else 'FAIL'), f'{name}: {v:.4g} ({op} {lim:g})')
    out = dict(design={k: v for k, v in DESIGN.items()}, drive=d, sense=s, usb_a=dict(base=USB_BASE_A, with_drive_typ=p,
                                           with_drive_max=USB_BASE_A + d['worst_high']['i_total_ma'] / 1e3),
               timing=dict(t_on_max_ms=T_ON_MAX * 1e3, t_off_max_ms=T_OFF_MAX * 1e3),
               thresholds_mv=dict(close=CLOSE_MV, trip=TRIP_MV), checks=rows, pass_=ok)
    (HERE / 'drive-budget.json').write_text(json.dumps(out, indent=1) + '\n')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
