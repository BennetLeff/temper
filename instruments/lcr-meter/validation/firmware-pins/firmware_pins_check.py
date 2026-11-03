"""Cross-check the firmware's pin map (firmware-rev-e/src/pins.h) against the board (cad/design.json).

Run:  python3 validation/firmware-pins/firmware_pins_check.py
Writes validation/firmware-pins/firmware-pins-check.json and exits 1 on any finding.

design.json is the board's netlist: validation/independent_check.py asserts every pin net in it
equals the built board's pad net and the schematic netlist, and validation/pinout-ledger/ checks its
pad-number -> function maps against the datasheets. This check closes the remaining link, firmware
-> design: every PIN_* lands on the net and the part the firmware's comments and code assume.

Checks:
  - each PIN_* GPIO reaches the expected net on U1 (RP2040 pad from design.json pinouts);
  - the RP2040 function the firmware uses (I2C0, UART0, ADC, PIO side-set) exists on that GPIO
    (RP2040 datasheet 2.19.2 function-select table, sources/new/RP2040-datasheet.txt);
  - relay drivers: GPIO -> series R -> AO3400A gate; drain -> the relay coil the firmware means
    (relay.c ranges -> design.json ranges[].relay; REF -> K4; RESET -> all four RST- coils);
  - LEDs: GPIO -> series R -> LED anode, cathode on GND (active high);
  - codec: I2S and I2C nets land on the TAC5112 pins of the same name; ADDR on GND = 0x50;
  - rail monitors: the divider resistors on MON12 / MON_N12 equal the constants in rails.c;
  - USB_SENSE: the VBUS divider puts 4.0 V VBUS at VIH and 5.5 V under IOVDD.
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get('LCR_ROOT') or Path(__file__).resolve().parents[2])  # LCR_ROOT: mutation tests on a copy
FW = ROOT / 'firmware-rev-e/src'
OUT = Path(__file__).resolve().parent / 'firmware-pins-check.json'
design = json.loads((ROOT / 'cad/design.json').read_text())
parts = {p['ref']: p for p in design['parts']}
pinouts = design['pinouts']
findings, passes = [], []


def check(ok, what, detail):
    (passes if ok else findings).append({'check': what, 'detail': detail})


def on_net(net):
    return [(p['ref'], pad) for p in design['parts'] for pad, n in p['pins'].items() if n == net]


def other_end(ref, net):
    """The net on the other pad of a two-pad part."""
    nets = [n for n in parts[ref]['pins'].values() if n != net]
    return nets[0] if len(nets) == 1 else None


def pin_name(ref, pad):
    return pinouts[parts[ref]['kind']][pad][0]


def ohms(value):
    m = re.match(r'([\d.]+)\s*([kMR]?)', value)
    return float(m.group(1)) * {'k': 1e3, 'M': 1e6, 'R': 1, '': 1}[m.group(2)]


# ---------------------------------------------------------------- pins.h
pins_h = (FW / 'pins.h').read_text()
defines = {m.group(1): int(m.group(2), 0) for m in re.finditer(r'#define (PIN_\w+|CODEC_I2C_ADDRESS) (0x[0-9a-fA-F]+|\d+)u', pins_h)}

# PIN_* -> net. The net is the name without PIN_, except where the board names the signal by role.
NET = {'PIN_USB_VBUS': 'USB_SENSE', 'PIN_LED': 'STATUS', 'PIN_LED_FAULT': 'FAULT', 'PIN_LED_HEARTBEAT': 'HEARTBEAT'}
u1_gpio = {name: pad for pad, (name, _) in pinouts['RP2040'].items() if name.startswith('GPIO')}
gpio_net = {}
for name, gpio in defines.items():
    if not name.startswith('PIN_'):
        continue
    want = NET.get(name, name[4:])
    pad = u1_gpio.get(f'GPIO{gpio}')
    got = parts['U1']['pins'].get(pad) if pad else None
    gpio_net[name] = got
    check(got == want, 'gpio net', f'{name} = GPIO{gpio} = U1 pad {pad}: net {got}, expected {want}')

# Every U1 GPIO with a net is claimed by pins.h (an unclaimed driven pin is wiring firmware never touches).
claimed = set(gpio_net.values())
for gname, pad in sorted(u1_gpio.items(), key=lambda kv: int(kv[0][4:])):
    net = parts['U1']['pins'].get(pad)
    if net:
        check(net in claimed, 'gpio claimed', f'U1 pad {pad} {gname} net {net} is {"" if net in claimed else "not "}in pins.h')

# ---------------------------------------------------------------- RP2040 function select (datasheet 2.19.2)
ds = (ROOT / 'sources/new/RP2040-datasheet.txt').read_text().splitlines()
fsel = {}
for line in ds[700:900]:  # the first copy of the table (the register chapter repeats it)
    m = re.match(r'\s+(\d{1,2})\s{2,}(SPI\d \w+)\s+(.*)$', line)
    if m and int(m.group(1)) not in fsel:
        fsel[int(m.group(1))] = line
uses = [('PIN_I2C_SDA', 'I2C0 SDA'), ('PIN_I2C_SCL', 'I2C0 SCL'), ('PIN_UART_TX', 'UART0 TX'), ('PIN_UART_RX', 'UART0 RX')]
main_c = (FW / 'main.c').read_text()
check('i2c_init(i2c0' in main_c, 'i2c block', 'main.c initialises i2c0, the block on GPIO8/9')
for name, func in uses:
    row = fsel.get(defines[name], '')
    check(func in row, 'function select', f'{name} GPIO{defines[name]} offers {func}: {"yes" if func in row else "NO"} (datasheet 2.19.2 row: {row.strip()})')
# ADC: GPIO26..29 are ADC inputs 0..3 (datasheet 4.9.1); rails_wait reads rail_sum(0) for +12 and rail_sum(1) for -12.
for name, ch in (('PIN_MON12', 0), ('PIN_MON_N12', 1)):
    check(defines[name] - 26 == ch and f'rail_sum({ch})' in main_c, 'adc channel', f'{name} GPIO{defines[name]} is ADC{defines[name] - 26}; main.c reads ADC{ch}')
# PIO side-set: FSYNC must be BCLK + 1 (pins.h comment, tdm.pio side-set base).
check(defines['PIN_I2S_FSYNC'] == defines['PIN_I2S_BCLK'] + 1, 'pio side-set', f'BCLK GPIO{defines["PIN_I2S_BCLK"]}, FSYNC GPIO{defines["PIN_I2S_FSYNC"]}')

# ---------------------------------------------------------------- relay drivers
relay_c = (FW / 'relay.c').read_text()
fw_ranges = {int(m.group(1)): m.group(2) for m in re.finditer(r'case (\d+)u: return (PIN_\w+);', relay_c)}
want_relay = {r['ohms']: r['relay'] for r in design['ranges']}
check(set(fw_ranges) == set(want_relay), 'relay ranges', f'relay.c ranges {sorted(fw_ranges)}, design.json ranges {sorted(want_relay)}')


def coil_of(pin_name_):
    """GPIO net -> series R -> NMOS gate; returns (R, Q, drain net, [(relay, coil pin name)])."""
    net = gpio_net[pin_name_]
    rs = [ref for ref, _ in on_net(net) if parts[ref]['kind'] == 'R']
    if len(rs) != 1:
        return None
    gate = other_end(rs[0], net)
    qs = [(ref, pad) for ref, pad in on_net(gate) if parts[ref]['kind'] == 'NMOS']
    if len(qs) != 1 or pin_name(*qs[0]) != 'G':
        return None
    q = qs[0][0]
    pins = {pin_name(q, pad): n for pad, n in parts[q]['pins'].items()}
    coils = [(ref, pin_name(ref, pad)) for ref, pad in on_net(pins['D']) if parts[ref]['kind'] == 'RELAY2L']
    return rs[0], q, pins['S'], pins['D'], coils


for ohm, pin in sorted(fw_ranges.items()):
    c = coil_of(pin)
    want = [(want_relay.get(ohm), 'SET-')]
    check(c is not None and c[2] == 'GND' and c[4] == want, 'relay set coil',
          f'{ohm} ohm: {pin} -> {c and c[0]} -> {c and c[1]} (source {c and c[2]}) -> {c and c[4]}, expected {want}')
c = coil_of('PIN_RNG_SET_REF')
check(c is not None and c[4] == [('K4', 'SET-')], 'relay set coil', f'REF: PIN_RNG_SET_REF -> {c and c[1]} -> {c and c[4]}, expected [K4 SET-]')
c = coil_of('PIN_RNG_RESET')
want = sorted((k, 'RST-') for k in ('K1', 'K2', 'K3', 'K4'))
check(c is not None and sorted(c[4]) == want, 'relay reset coil', f'RESET: PIN_RNG_RESET -> {c and c[1]} -> {c and sorted(c[4])}, expected {want}')
# Coil + ends on the relay supply; the range relay's contacts reach that range's RG / RF.
for r in design['ranges']:
    k = parts[r['relay']]['pins']
    names = {pin_name(r['relay'], pad): n for pad, n in k.items()}
    check(names['SET+'] == names['RST+'] == 'VRLY', 'relay coil supply', f'{r["relay"]} SET+ {names["SET+"]}, RST+ {names["RST+"]}')
    rg_nets, rf_nets = set(parts[r['rg']]['pins'].values()), set(parts[r['rf']]['pins'].values())
    check(names['NO1'] in rg_nets and names['NO2'] in rf_nets, 'relay contacts',
          f'{r["ohms"]} ohm {r["relay"]}: NO1 {names["NO1"]} on {r["rg"]} {sorted(rg_nets)}, NO2 {names["NO2"]} on {r["rf"]} {sorted(rf_nets)}')

# ---------------------------------------------------------------- LEDs (active high)
for pin, led in (('PIN_LED', 'D4'), ('PIN_LED_FAULT', 'D20'), ('PIN_LED_HEARTBEAT', 'D19')):
    net = gpio_net[pin]
    rs = [ref for ref, _ in on_net(net) if parts[ref]['kind'] == 'R']
    anode = other_end(rs[0], net) if len(rs) == 1 else None
    leds = {pin_name(ref, pad): ref for ref, pad in on_net(anode) if parts.get(ref, {}).get('kind') == 'LED'} if anode else {}
    k_net = next((n for pad, n in parts[led]['pins'].items() if pin_name(led, pad) == 'K'), None)
    check(leds == {'A': led} and k_net == 'GND', 'led', f'{pin} -> {rs} -> {anode}: {leds}, {led} K on {k_net}')

# ---------------------------------------------------------------- codec
codec = {pin_name('U14', pad): n for pad, n in parts['U14']['pins'].items()}
for pin, fn in (('PIN_I2S_DIN', 'DIN'), ('PIN_I2S_DOUT', 'DOUT'), ('PIN_I2S_BCLK', 'BCLK'), ('PIN_I2S_FSYNC', 'FSYNC'),
                ('PIN_I2C_SDA', 'SDA'), ('PIN_I2C_SCL', 'SCL')):
    check(codec.get(fn) == gpio_net[pin], 'codec pin', f'{pin} net {gpio_net[pin]}; TAC5112 {fn} on {codec.get(fn)}')
# TAC5112 SLASF24A Table 7-72 (p89-90): ADDR short to ground selects I2C address 0x50.
check(codec.get('ADDR') == 'GND' and defines['CODEC_I2C_ADDRESS'] == 0x50, 'codec address',
      f'ADDR on {codec.get("ADDR")}, firmware address 0x{defines["CODEC_I2C_ADDRESS"]:02x}')
for net in ('I2C_SDA', 'I2C_SCL'):
    pulls = [ref for ref, _ in on_net(net) if parts[ref]['kind'] == 'R' and other_end(ref, net) == '3V3']
    check(len(pulls) == 1, 'i2c pull-up', f'{net}: pull-ups to 3V3 {pulls}')

# ---------------------------------------------------------------- rail monitor dividers vs rails.c
rails_c = (FW / 'rails.c').read_text()


def divider(net, top_rail):
    rs = [ref for ref, _ in on_net(net) if parts[ref]['kind'] == 'R']
    top = [r for r in rs if other_end(r, net) == top_rail]
    other = [r for r in rs if r not in top]
    return (ohms(parts[top[0]]['value']), ohms(parts[other[0]]['value']), other_end(other[0], net)) if len(top) == len(other) == 1 else None


d = divider('MON12', '12V')
check(d == (100e3, 10e3, 'GND') and '100k / 10k multiplies by 11' in rails_c and '* 11' in rails_c, 'rail divider',
      f'MON12: 12V-{d and d[0]:.0f}-MON12-{d and d[1]:.0f}-{d and d[2]}; rails.c scales by 11')
d = divider('MON_N12', '-12V')
check(d == (150e3, 10e3, '3V3') and '* 160' in rails_c and '* 150' in rails_c, 'rail divider',
      f'MON_N12: -12V-{d and d[0]:.0f}-MON_N12-{d and d[1]:.0f}-{d and d[2]}; rails.c uses 160k total, 150k to 3V3')

# ---------------------------------------------------------------- USB_SENSE threshold
d = divider('USB_SENSE', 'USB_VBUS')
ratio = d[1] / (d[0] + d[1]) if d else 0
# RP2040 datasheet 5.5.3: VIH min 2 V at IOVDD 3.3 V; abs max IOVDD + 0.5 V. USB VBUS 4.4-5.5 V (5.25 V nominal max).
check(d is not None and d[2] == 'GND' and 4.4 * ratio >= 2.0 and 5.5 * ratio <= 3.3, 'usb sense',
      f'divider {d}: VBUS 4.4 V -> {4.4 * ratio:.2f} V (VIH 2.0 V), 5.5 V -> {5.5 * ratio:.2f} V (IOVDD 3.3 V)')

result = {
    'inputs': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
               ('cad/design.json', 'firmware-rev-e/src/pins.h', 'firmware-rev-e/src/relay.c',
                'firmware-rev-e/src/rails.c', 'firmware-rev-e/src/main.c')},
    'findings': findings,
    'passes': passes,
}
OUT.write_text(json.dumps(result, indent=1) + '\n')
print(f'{len(passes)} pass, {len(findings)} findings')
for f in findings:
    print('FINDING', f['check'], '-', f['detail'])
sys.exit(1 if findings else 0)
