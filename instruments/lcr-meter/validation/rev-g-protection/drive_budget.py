"""Rev G isolation-switch drive, jack residual-voltage sense, and the USB power budget (README, "Drive and sense").

python3 validation/rev-g-protection/drive_budget.py   ->  drive-budget.json; exits 1 if a check fails

Drive: four TLP172AM photoMOS (one per jack), their LEDs in two strings of two from the switched 5 V rail
(U16 output) through one resistor each, sunk by one AO3400A on GPIO 15 (U1 pin 18; the Q6 pattern: 100 ohm gate
resistor, 100 kOhm pull-down, so the switches are open from power-up until the firmware closes them, and
open again within tOFF of losing VBUS). Checked at the rail and LED corners:
  - every LED at or above the TLP172AM's recommended 5 mA minimum (RON is specified at IF 5 mA; IFT max 3 mA)
    at the lowest rail and the highest VF, and at or below 25 mA at the highest rail and the lowest VF.
Sense: each CUR jack (R105 / R106 on the jack side tie each POT jack to it through 1 kOhm) to an RP2040 ADC
pin (GPIO 28 / 29, ADC2 / ADC3, the optional UART header) through R_TOP from the jack, biased to mid-scale by
R_BIAS to 3V3 and R_GND to ground, C_PIN to ground. Checked:
  - the pin stays inside 0..3.3 V for the whole clamp range of the jack TVS (+-10 V, H4V5HD3B VC at 40 A);
  - the bias current the divider pushes into a jack at 0 V, and what it does on the LCUR side (it flows through
    the TIA: a DC offset of I x RF at the TIA output, against its swing);
  - the AC load the divider puts on LCUR (R_TOP to AC ground), as a fixed fraction calibration removes;
  - the filter: settling to the close threshold, and the 46 Hz source tone's ripple at the pin.
Power: Rev F's 0.46 A estimate (rev-f-handoff.md) plus the drive, against USB 2.0's 500 mA.

Sources: part-selection/parts.json (TLP172AM: IF 5-25 mA recommended, VF 1.1 / 1.27 / 1.4 V, IFT 3 mA max,
tON 2 ms max, tOFF 0.5 ms max; H4V5HD3B VC 10 V at 40 A); rev-e-plan 2026-10-21 (switched 5 V 4.32 V minimum
after U16 at VBUS 4.40 V; 5.5 V maximum); rev-f-handoff.md (0.46 A at attach).
"""

import json
import math
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent

V5 = (4.32, 5.0, 5.5)              # switched 5 V: min (VBUS 4.40 V less U16), nominal, max
VF = (1.1, 1.27, 1.4)              # TLP172AM LED VF min / typ / max at 10 mA
IF_MIN, IF_MAX, IFT_MAX = 5e-3, 25e-3, 3e-3
LEDS_PER_STRING, STRINGS = 2, 2
R_LED = 300.0                      # per string
RDS_ON = 0.05                      # AO3400A at VGS 3.3 V (order of; negligible against R_LED)
T_ON_MAX, T_OFF_MAX = 2e-3, 0.5e-3

R_TOP, R_BIAS, R_GND, C_PIN = 1e6, 200e3, 249e3, 100e-9
V33 = 3.3
V_CLAMP = 10.0                     # H4V5HD3B VC max at 40 A (8/20): the jack never sits beyond it
CLOSE_MV, TRIP_MV = 1000, 3000     # firmware-rev-e/src/jackguard.h; main() checks they are equal
RF = {100: 100.0, 5000: 5e3, 100000: 100e3}
TIA_SWING = 11.0                   # OPA2810 output on +-12 V, order of
R_LC_PATH = 1.0 + 10.0 + 22.0      # switch + series R + R94 from the LCUR jack to the virtual ground
F_LOW, VS = 45.8, 1.7              # lowest tone and source amplitude (accuracy_map.py)

USB_BASE_A, USB_LIMIT_A = 0.46, 0.5


def drive():
    out = {}
    for name, v5, vf in (('worst_low', V5[0], VF[2]), ('typical', V5[1], VF[1]), ('worst_high', V5[2], VF[0])):
        i = (v5 - LEDS_PER_STRING * vf) / (R_LED + RDS_ON)
        out[name] = dict(v5=v5, vf=vf, i_string_ma=i * 1e3, i_total_ma=STRINGS * i * 1e3)
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
    import re
    h = (HERE.parents[1] / 'firmware-rev-e' / 'src' / 'jackguard.h').read_text()
    fw = {k: int(re.search(rf'#define {k} (\d+)', h).group(1)) for k in ('JG_CLOSE_MV', 'JG_TRIP_MV', 'JG_RTOP_RBIAS')}
    g_ppm = int(re.search(r'#define JG_RTOP_G_PPM (\d+)', h).group(1))
    checks = [
        ('firmware thresholds equal these (jackguard.h)', float(fw['JG_CLOSE_MV'] == CLOSE_MV and fw['JG_TRIP_MV'] == TRIP_MV),
         '>=', 1.0),
        ('firmware divider constants equal these (jackguard.h)',
         float(fw['JG_RTOP_RBIAS'] == R_TOP / R_BIAS and abs(g_ppm - R_TOP * (1 / R_TOP + 1 / R_BIAS + 1 / R_GND) * 1e6) < 1),
         '>=', 1.0),
        ('LED current at the lowest rail, highest VF >= 5 mA', d['worst_low']['i_string_ma'], '>=', IF_MIN * 1e3),
        ('LED current at the highest rail, lowest VF <= 25 mA', d['worst_high']['i_string_ma'], '<=', IF_MAX * 1e3),
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
    out = dict(drive=d, sense=s, usb_a=dict(base=USB_BASE_A, with_drive_typ=p,
                                           with_drive_max=USB_BASE_A + d['worst_high']['i_total_ma'] / 1e3),
               timing=dict(t_on_max_ms=T_ON_MAX * 1e3, t_off_max_ms=T_OFF_MAX * 1e3),
               thresholds_mv=dict(close=CLOSE_MV, trip=TRIP_MV), checks=rows, pass_=ok)
    (HERE / 'drive-budget.json').write_text(json.dumps(out, indent=1) + '\n')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
