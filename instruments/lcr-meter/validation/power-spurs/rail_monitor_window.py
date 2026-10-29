#!/usr/bin/env python3
"""Worst-case +-12 V monitor readings on Rev E, and the host's gross-fault window derived from them.

python3 validation/power-spurs/rail_monitor_window.py   ->  rail_monitor_window.json

The host (host/src/lib.rs rails_from_line) converts the RP2040 ADC sums with the nominal monitor
dividers and a nominal 3.3 V ADC reference.  A healthy board must never read outside the window, so
the window is set below/above the worst corner of:
  - the rail itself: regulator_check.json r5_option.with_tcr (TPS7A49/TPS7A30 reference limits,
    divider tolerance and divider TCR over 25 +- DT_BOARD C);
  - the monitor dividers R97/R98 (+12 V) and R99/R100 (-12 V, pulled up to 3V3), 1 % thick film,
    +-100 ppm/C (UNI-ROYAL 0603WAF, sources/C23345-0603WAF220JT5E.txt);
  - 3V3, which is both the ADC reference (ADC_AVDD) and R99's pull-up: AP2112K +-1.5 %, +-100 ppm/C
    (sources/new/AP2112.txt);
  - RP2040 pin input leakage, +-1 uA maximum (datasheet, Pin Input Leakage IIN), into the divider's
    Thevenin resistance;
  - ADC conversion error: RP2040 publishes ENOB (8.7 bits min) and INL/DNL figures but no gain or
    offset limit, so ADC_ERR_LSB is an ESTIMATE allowance.
  - the ADC's 100 kOhm minimum input impedance (RIN_ADC), as a resistive load while a RAILS burst of
    257 conversions (2 us each, firmware-rev-e rail_sum) runs: C110/C111 (100 nF) start at the divider
    voltage and sag toward the loaded value with tau = (R_th || RIN) x 100 nF; the host sees the mean
    over the burst.  This is the datasheet bound; a sampling capacitor of a few pF loads far less.
"""
import itertools
import math
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DT_BOARD = 35.0                       # C, as regulator_check.py
R_TOL, R_TCR = 0.01, 100e-6           # monitor dividers, 1 % thick film
V3_NOM, V3_TOL, V3_TC = 3.3, 0.015, 100e-6
I_LEAK = 1e-6                         # A, RP2040 IIN max
ADC_ERR_LSB = 8                       # ESTIMATE: no published gain/offset limit
LSB = V3_NOM / 4096
RIN_ADC, C_HOLD, T_CONV, N_BURST = 100e3, 100e-9, 2e-6, 257
FAULT_MARGIN_V = 0.2                  # window edge beyond the worst healthy reading

design = {p['ref']: p for p in json.loads((ROOT / 'cad/design.json').read_text())['parts']}
ohms = lambda ref: float(design[ref]['value'].replace('k', 'e3').replace('M', 'e6').split()[0])
R97, R98, R99, R100 = (ohms(r) for r in ('R97', 'R98', 'R99', 'R100'))
tcr = json.loads((HERE / 'regulator_check.json').read_text())['r5_option']['with_tcr']
RAIL = {'pos': (tcr['pos']['vout_min'], tcr['pos']['vout_max']),
        'neg': (tcr['neg']['vout_min'], tcr['neg']['vout_max'])}   # magnitudes


def burst_sag(r_th):
    """Mean fractional drop of the pin over the burst, with RIN_ADC as a resistive load."""
    full = r_th / (r_th + RIN_ADC)                     # steady-state drop
    tau = r_th * RIN_ADC / (r_th + RIN_ADC) * C_HOLD
    t = N_BURST * T_CONV
    return full * (1 - tau / t * (1 - math.exp(-t / tau)))


def host_reading(kind, v_mon):
    """host/src/lib.rs: nominal divider, nominal 3.3 V reference."""
    if kind == 'pos':
        return v_mon * (R97 + R98) / R98
    return (v_mon * (R99 + R100) - V3_NOM * R100) / R99


def node(kind, rail, r_top, r_bot, v3, leak):
    """Pin voltage with the actual parts; leak flows out of the node (+) or in (-)."""
    if kind == 'pos':          # 12V -- R97 -- MON12 -- R98 -- GND
        g = 1 / r_top + 1 / r_bot
        return (rail / r_top - leak) / g
    g = 1 / r_top + 1 / r_bot  # 3V3 -- R99 -- MON_N12 -- R100 -- -12V
    return (v3 / r_top + rail / r_bot - leak) / g   # rail is negative here


rows = {}
for kind in ('pos', 'neg'):
    readings = []
    r_top_nom, r_bot_nom = (R97, R98) if kind == 'pos' else (R99, R100)
    dr = R_TOL + R_TCR * DT_BOARD
    sag = burst_sag(r_top_nom * r_bot_nom / (r_top_nom + r_bot_nom))
    for rail, s_top, s_bot, s3, s_leak, s_adc, s_rin in itertools.product(
            RAIL[kind], (-1, 1), (-1, 1), (-1, 1), (-1, 1), (-1, 1), (0, 1)):
        v3 = V3_NOM * (1 + s3 * (V3_TOL + V3_TC * DT_BOARD))
        v_rail = rail if kind == 'pos' else -rail
        v_pin = node(kind, v_rail, r_top_nom * (1 + s_top * dr), r_bot_nom * (1 + s_bot * dr), v3, s_leak * I_LEAK)
        v_pin *= 1 - s_rin * sag                            # RIN pulls the pin toward ground
        code = v_pin / v3 * 4096 + s_adc * ADC_ERR_LSB      # ratiometric to the actual 3V3
        readings.append(abs(host_reading(kind, code / 4096 * V3_NOM)))
    rows[kind] = {'rail_abs_v': list(RAIL[kind]), 'reading_abs_min_v': min(readings),
                  'reading_abs_max_v': max(readings), 'rin_burst_sag_fraction': sag}

r_th = R97 * R98 / (R97 + R98)

# Calibration-to-use change on one board (option 2 in the host: rails stored with the calibration).
# Part tolerances, the 25 C regulator offset and the RIN sag are the same at both times and cancel;
# what can move is temperature (DT_BOARD between the two), leakage (its full +-1 uA swing) and ADC error
# (+-ADC_ERR_LSB each time).  TPS7A49/TPS7A30: +-1.5 % at 25 C (nominal accuracy) inside +-2.5 % overall,
# so a healthy rail may move by up to 4.0 % of VOUT (pessimistic: line and load are nearly constant).
# The LDO divider TCR term is regulator_check's with-TCR range less its no-TCR range.  The terms are
# summed linearly (worst case).
REG_NOMINAL, REG_OVERALL = 0.015, 0.025
ldo = json.loads((HERE / 'regulator_check.json').read_text())['ldo']
drift = {}
for kind in ('pos', 'neg'):
    r_top, r_bot = (R97, R98) if kind == 'pos' else (R99, R100)
    nom = ldo[kind]['vout'][1]
    sign = 1 if kind == 'pos' else -1
    base = dict(rail=nom, top=r_top, bot=r_bot, v3=V3_NOM, leak=0.0, adc=0.0)

    def reading(**kw):
        q = dict(base, **kw)
        v_pin = node(kind, sign * q['rail'], q['top'], q['bot'], q['v3'], q['leak'])
        return abs(host_reading(kind, (v_pin / q['v3'] * 4096 + q['adc']) / 4096 * V3_NOM))
    r0 = reading()
    dr = R_TCR * DT_BOARD
    ldo_tcr = max(abs(tcr[kind]['vout_min'] - ldo[kind]['vout'][0]),
                  abs(tcr[kind]['vout_max'] - ldo[kind]['vout'][2])) / nom
    terms = {
        'regulator_reference': abs(reading(rail=nom * (1 + REG_NOMINAL + REG_OVERALL)) - r0) / r0,
        'ldo_divider_tcr': abs(reading(rail=nom * (1 + ldo_tcr)) - r0) / r0,
        'monitor_divider_tcr': abs(reading(top=r_top * (1 + dr), bot=r_bot * (1 - dr)) - r0) / r0,
        'v3_tempco': abs(reading(v3=V3_NOM * (1 + V3_TC * DT_BOARD)) - r0) / r0,
        'pin_leakage_swing': abs(reading(leak=2 * I_LEAK) - r0) / r0,
        'adc_error_twice': abs(reading(adc=2 * ADC_ERR_LSB) - r0) / r0,
    }
    drift[kind] = {'terms_fraction': terms, 'limit_fraction': sum(terms.values())}
lo = min(r['reading_abs_min_v'] for r in rows.values()) - FAULT_MARGIN_V
hi = max(r['reading_abs_max_v'] for r in rows.values()) + FAULT_MARGIN_V
window = (int(lo * 10) / 10, -(-hi * 10 // 1) / 10)            # outward to 0.1 V
result = {
    'inputs': {'dt_board_c': DT_BOARD, 'divider_tol': R_TOL, 'divider_tcr': R_TCR, 'v3_tol': V3_TOL,
               'v3_tc': V3_TC, 'pin_leakage_a': I_LEAK, 'adc_error_lsb_estimate': ADC_ERR_LSB,
               'fault_margin_v': FAULT_MARGIN_V},
    'rails': rows,
    'leakage_error_pos_v': I_LEAK * r_th * (R97 + R98) / R98,
    'host_window_abs_v': window,
    'host_window_pos_abs_v': [int((rows['pos']['reading_abs_min_v'] - FAULT_MARGIN_V) * 10) / 10,
                              -(-(rows['pos']['reading_abs_max_v'] + FAULT_MARGIN_V) * 10 // 1) / 10],
    'host_window_neg_abs_v': [int((rows['neg']['reading_abs_min_v'] - FAULT_MARGIN_V) * 10) / 10,
                              -(-(rows['neg']['reading_abs_max_v'] + FAULT_MARGIN_V) * 10 // 1) / 10],
    'calibration_drift': drift,
    'host_drift_limit_percent': {k: -(-v['limit_fraction'] * 1000 // 1) / 10 for k, v in drift.items()},
}
(HERE / 'rail_monitor_window.json').write_text(json.dumps(result, indent=1) + '\n')
for kind, r in rows.items():
    print(f"{kind}: rail |V| {r['rail_abs_v'][0]:.3f}-{r['rail_abs_v'][1]:.3f} V reads "
          f"{r['reading_abs_min_v']:.3f}-{r['reading_abs_max_v']:.3f} V")
print(f"leakage alone on +12 V: +-{result['leakage_error_pos_v']*1e3:.0f} mV; RIN_ADC burst sag "
      f"{rows['pos']['rin_burst_sag_fraction']*100:.2f} % (+12) / {rows['neg']['rin_burst_sag_fraction']*100:.2f} % (-12 pin)")
print(f"host windows |V|: +12 {result['host_window_pos_abs_v']}, -12 {result['host_window_neg_abs_v']} "
      f"(worst healthy reading -/+ {FAULT_MARGIN_V} V)")
for kind, d in drift.items():
    print(f"{kind}: healthy calibration-to-use change <= {d['limit_fraction']*100:.2f} % ("
          + ', '.join(f"{k} {v*100:.2f}" for k, v in d['terms_fraction'].items()) + ")")
print(f"host drift limits (rounded up): {result['host_drift_limit_percent']}")
