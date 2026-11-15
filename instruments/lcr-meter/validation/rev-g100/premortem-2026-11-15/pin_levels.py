"""Pre-mortem arithmetic (read-only on the design): (1) USB_SENSE level at U1.16 with the RP2040 pad's reset
pull-down still enabled; (2) jack-sense error terms against the guard thresholds. Values from cad/design.json,
firmware-rev-e/src/jackguard.h and sources/new/RP2040-datasheet.txt (Table 'Pull-Down RPD 50..80 kOhm',
'VIH 2 V / VIL 0.8 V at IOVDD 3.3 V', PADS_BANK0 GPIOx reset PDE = 1)."""
import itertools, json
d = json.load(open('cad/design.json'))
val = {p['ref']: p['value'] for p in d['parts']}
assert val['R5'] == '100k' and val['R6'] == '100k' and val['R126'] == '1.5M' and val['R127'] == '240k' and val['R128'] == '240k'
par = lambda a, b: a * b / (a + b)
print('(1) USB_SENSE at U1.16 (GPIO13), R5 = R6 = 100k; VIH(min) 2.0 V, VIL(max) 0.8 V')
for vbus in (4.40, 4.75, 5.00, 5.25, 5.50):
    row = [f'no pull {vbus * 0.5:.2f} V']
    for rpd in (50e3, 65e3, 80e3):
        lo = par(100e3, rpd)
        row.append(f'RPD {rpd / 1e3:.0f}k {vbus * lo / (100e3 + lo):.2f} V')
    print(f'  VBUS {vbus:.2f}: ' + ', '.join(row))
print('(2) jack sense, V_jack = pin * 13.5 - 3.3 * 6.25 (jackguard.h); thresholds TRIP_LC 0.5 V, CLOSE_DIFF 1.0 V')
def pin(vj, rt, rb, rg, v33=3.3):
    return (vj / rt + v33 / rb) / (1 / rt + 1 / rb + 1 / rg)
nom = pin(0, 1.5e6, 240e3, 240e3)
worst = max(abs(pin(0, 1.5e6 * a, 240e3 * b, 240e3 * c) - nom) for a, b, c in itertools.product((0.99, 1.01), repeat=3))
print(f'  pin at 0 V jack {nom:.4f} V; 1 LSB = {3.3 / 4096 * 13.5 * 1e3:.1f} mV jack-referred')
print(f'  1 % resistors (R126-R131), worst corner: {worst * 1e3:.1f} mV at the pin = {worst * 13.5 * 1e3:.0f} mV at the jack')
rs = par(par(1.5e6, 240e3), 240e3)
print(f'  source resistance at the pin {rs / 1e3:.0f} kOhm: 1 uA leakage (datasheet max) = {rs * 1e-6 * 13.5:.2f} V at the jack')
for mv in (5, 10, 20, 30):
    print(f'  an ADC offset of {mv} mV at the pin = {mv * 13.5:.0f} mV at the jack')
q = 256 * 2 * 1e-12 * nom  # two channels are not shared; per pin: 256 conversions of ~1 pF from 0 V (upper bound)
q = 256 * 1e-12 * nom
print(f'  256 conversions per 5 ms poll, 1 pF sample cap from 0 V (upper bound): {q * 1e12:.0f} pC per poll = '
      f'{q / 5e-3 * 1e9:.0f} nA average = {q / 5e-3 * rs * 1e3:.1f} mV at the pin = {q / 5e-3 * rs * 13.5 * 1e3:.0f} mV at the jack')
