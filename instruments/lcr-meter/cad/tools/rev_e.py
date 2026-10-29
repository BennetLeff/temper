"""Rev E: codec front end, relay ranges and 0.3 mm vias, as explicit edits of the Rev D sources.

python3 cad/tools/rev_e.py        (reads Rev D design.json/routing.json from git, writes cad/)

Every placement, segment and via below is given by coordinates or REF.pad: this is hand routing
in script form, the same as the Rev D audit edits (cad/tools/edit_lib.py). Circuit:
docs/rev-e-front-end.md and docs/rev-e-range-switching.md; decisions in docs/rev-e-plan.md.
"""
import json
import math
import subprocess
from pathlib import Path

CAD = Path(__file__).resolve().parents[1]
REV_D = '79f4edbba'  # last Rev D commit of cad/design.json and cad/routing.json


def git_json(name):
    out = subprocess.run(['git', 'show', f'{REV_D}:./{name}'], cwd=CAD, check=True,
                         capture_output=True, text=True).stdout
    return json.loads(out)


design = git_json('design.json')
routing = git_json('routing.json')
parts = {p['ref']: p for p in design['parts']}

# ---------------------------------------------------------------- catalogue
R0603 = 'Resistor_SMD:R_0603_1608Metric'
C0603 = 'Capacitor_SMD:C_0603_1608Metric'
C0805 = 'Capacitor_SMD:C_0805_2012Metric'
CAT = {
    # key: value, footprint, mpn, manufacturer, lcsc, unit_usd, library_type
    'R1k01': ('1k 0.1%', R0603, 'RT0603BRD071KL', 'YAGEO', 'C110776', 0.0313, 'extended'),
    'R2k01': ('2k 0.1%', R0603, 'RT0603BRD072KL', 'YAGEO', 'C728588', 0.035, 'extended'),
    'R2k201': ('2.2k 0.1%', R0603, 'RT0603BRD072K2L', 'YAGEO', 'C861295', 0.0363, 'extended'),
    'R470': ('470R', R0603, '0603WAF4700T5E', 'UNI-ROYAL(Uniroyal Elec)', 'C23179', 0.002, 'basic'),
    'R24k': ('24k 1%', R0603, '0603WAF2402T5E', 'UNI-ROYAL(Uniroyal Elec)', 'C23352', 0.0024, 'basic'),
    'R4k7': ('4.7k', R0603, '0603WAF4701T5E', 'UNI-ROYAL(Uniroyal Elec)', 'C23162', 0.002, 'basic'),
    'R100': ('100R', R0603, '0603WAF1000T5E', 'UNI-ROYAL(Uniroyal Elec)', 'C22775', 0.0026, 'basic'),
    'R100k': ('100k', R0603, '0603WAF1003T5E', 'UNI-ROYAL(Uniroyal Elec)', 'C25803', 0.0031, 'basic'),
    'R1k': ('1k', R0603, '0603WAF1001T5E', 'UNI-ROYAL(Uniroyal Elec)', 'C21190', 0.0021, 'basic'),
    'R47': ('47R', R0603, '0603WAF470JT5E', 'UNI-ROYAL(Uniroyal Elec)', 'C23182', 0.002, 'basic'),
    'R2R2': ('2.2R', R0603, '0603WAF220KT5E', 'UNI-ROYAL(Uniroyal Elec)', 'C22939', 0.0034, 'basic'),
    'C100n': ('100nF 50V', C0603, 'CC0603KRX7R9BB104', 'YAGEO', 'C14663', 0.0082, 'basic'),
    'C1u0603': ('1uF 50V X5R', C0603, 'CL10A105KB8NNNC', 'Samsung Electro-Mechanics', 'C15849', 0.0153, 'basic'),
    'C1u0805': ('1uF 50V', C0805, 'CL21B105KBFNNNE', 'Samsung Electro-Mechanics', 'C28323', 0.0344, 'basic'),
    'C10u': ('10uF 25V X5R', C0805, 'CL21A106KAYNNNE', 'Samsung Electro-Mechanics', 'C15850', 0.0426, 'basic'),
    'C22u': ('22uF 25V X5R', 'Capacitor_SMD:C_1206_3216Metric', 'CL31A226KAHNNNE', 'Samsung Electro-Mechanics', 'C12891', 0.1706, 'basic'),
    'C100p': ('100pF C0G 5%', C0603, 'CL10C101JB8NNNC', 'Samsung Electro-Mechanics', 'C14858', 0.0086, 'basic'),
    'C560p': ('560pF C0G 5%', C0603, 'CC0603JRNPO9BN561', 'YAGEO', 'C107054', 0.0066, 'extended'),
    'C270p': ('270pF C0G 5%', C0603, 'CC0603JRNPO9BN271', 'YAGEO', 'C107046', 0.0092, 'extended'),
}


def add(ref, key, sheet, pins, at, query=None, **kw):
    value, fp, mpn, mfr, lcsc, usd, lib = CAT[key]
    kind = 'C' if fp.startswith('Capacitor') else 'R'
    rec = {'ref': ref, 'value': value, 'kind': kind, 'footprint': fp, 'pins': pins, 'pcb': list(at),
           'sheet': sheet, 'mpn': mpn, 'manufacturer': mfr, 'lcsc': lcsc, 'unit_usd': usd,
           'stock': None, 'library_type': lib, 'assembly': 'SMT', 'source_query': query or 'Rev E'}
    rec.update(kw)
    parts[ref] = rec


def add_ic(ref, kind, value, fp, sheet, pins, at, mpn, mfr, lcsc, usd, lib, query):
    parts[ref] = {'ref': ref, 'value': value, 'kind': kind, 'footprint': fp, 'pins': pins,
                  'pcb': list(at), 'sheet': sheet, 'mpn': mpn, 'manufacturer': mfr, 'lcsc': lcsc,
                  'unit_usd': usd, 'stock': None, 'library_type': lib, 'assembly': 'SMT',
                  'source_query': query}


# ---------------------------------------------------------------- removals
REMOVE = ('U4 C30 C31 C32 C33 FB2 C36 R34 R11 U8 U9 U10 JP1 JP2 JP3 JP4 JP5 JP6 '
          'R62 R63 R64 R65 R68 R69 R70 R71 R90 R91 R92 R93 C106 C107 C108 C109 '
          'C60 C61 C62 C63 C64 C66 C67 C68 C69 C70 C72 C73 C74 C75 C76 C77 C78 C79 J2 Q1').split()
for ref in REMOVE:
    del parts[ref]
for ref in ('R30', 'R31', 'R32', 'C34', 'C35'):   # reused below with new values and nets
    del parts[ref]

# ---------------------------------------------------------------- pinouts
pinouts = design['pinouts']
for kind in ('AD9833', 'THS4551', 'ADS9224R', 'JACK', 'PMOS'):
    del pinouts[kind]
pinouts['TAC5112'] = {
    '1': ['DREG', 'power_out'], '2': ['BCLK', 'input'], '3': ['FSYNC', 'input'], '4': ['DOUT', 'output'],
    '5': ['DIN', 'input'], '6': ['IOVDD', 'power_in'], '7': ['SCL', 'input'], '8': ['SDA', 'bidirectional'],
    '9': ['GPIO1', 'bidirectional'], '10': ['GPIO2', 'bidirectional'], '11': ['GPO1', 'output'],
    '12': ['GPI1', 'input'], '13': ['ADDR', 'input'], '14': ['MICBIAS', 'output'], '15': ['IN1P', 'input'],
    '16': ['IN1M', 'input'], '17': ['IN2P', 'input'], '18': ['IN2M', 'input'], '19': ['OUT1M', 'output'],
    '20': ['OUT1P', 'output'], '21': ['OUT2P', 'output'], '22': ['OUT2M', 'output'], '23': ['AVDD', 'power_in'],
    '24': ['VREF', 'passive'], '25': ['VSS', 'power_in'], 'A1': ['VSS', 'power_in'], 'A2': ['VSS', 'power_in'],
    'A3': ['VSS', 'power_in'], 'A4': ['VSS', 'power_in']}
pinouts['RELAY2L'] = {
    '1': ['SET+', 'passive'], '2': ['NC1', 'passive'], '3': ['COM1', 'passive'], '4': ['NO1', 'passive'],
    '5': ['SET-', 'passive'], '6': ['RST-', 'passive'], '7': ['NO2', 'passive'], '8': ['COM2', 'passive'],
    '9': ['NC2', 'passive'], '10': ['RST+', 'passive']}
pinouts['BNC'] = {'1': ['GND', 'passive'], '2': ['GND', 'passive'], '3': ['GND', 'passive'],
                  '4': ['GND', 'passive'], '5': ['SIG', 'passive']}
pinouts['NMOS'] = {'1': ['G', 'passive'], '2': ['S', 'passive'], '3': ['D', 'passive']}
pinouts['USBSW'] = {'1': ['IN', 'power_in'], '2': ['GND', 'power_in'], '3': ['EN', 'input'],
                    '4': ['~{FAULT}', 'open_collector'], '5': ['ILIM', 'passive'], '6': ['OUT', 'power_out']}
pinouts['BAT54S'] = {'1': ['A1', 'passive'], '2': ['K2', 'passive'], '3': ['K1A2', 'passive']}

# ---------------------------------------------------------------- MCU pins (firmware-rev-e/src/pins.h)
u1 = parts['U1']['pins']
for pin in ('8', '9', '13', '14', '15', '32'):   # GPIO6, 7, 10, 11, 12, 21 lose their Rev D nets
    u1[pin] = None
u1.update({'4': 'I2S_DIN', '5': 'I2S_DOUT', '6': 'I2S_BCLK', '7': 'I2S_FSYNC',
           '11': 'I2C_SDA', '12': 'I2C_SCL',
           '8': 'RNG_SET_HI', '9': 'RNG_SET_LO', '13': 'RNG_RESET', '14': 'RNG_SET_MED'})
u1['17'] = 'RNG_SET_REF'   # GPIO14: K4 reference relay (GPIO12, pin 15, sits under the USB_SENSE run)

# ---------------------------------------------------------------- source: OPA810 difference stage
parts['R33'].update(value='2k 0.1%', mpn=CAT['R2k01'][2], lcsc=CAT['R2k01'][4], unit_usd=CAT['R2k01'][5],
                    source_query='Rev E difference stage feedback, 0.1 %')
add('R31', 'R2k201', 'source', {'1': 'SOURCE_FB', '2': 'DAC_M'}, (137, 65, 90))
add('R30', 'R2k201', 'source', {'1': 'DAC_P', '2': 'SOURCE_AC'}, (130.0, 73.0, 90))
add('R32', 'R2k01', 'source', {'1': 'SOURCE_AC', '2': 'GND'}, (126, 74, 0))
add('C34', 'C270p', 'source', {'1': 'SOURCE_AC', '2': 'GND'}, (128.4, 72.0, 270))
add('C35', 'C270p', 'source', {'1': 'EXCITE', '2': 'SOURCE_FB'}, (133.0, 61.2, 0))

# ---------------------------------------------------------------- codec
CX, CY = 141.0, 97.5
add_ic('U14', 'TAC5112', 'TAC5112', 'LCR:TI_RGE0024R_VQFN-24-1EP_4x4mm_P0.5mm_EP2.1mm_CornerPads', 'codec',
       {'1': 'CODEC_DREG', '2': 'I2S_BCLK', '3': 'I2S_FSYNC', '4': 'I2S_DOUT', '5': 'I2S_DIN', '6': '3V3',
        '7': 'I2C_SCL', '8': 'I2C_SDA', '9': None, '10': None, '11': None, '12': 'GND', '13': 'GND', '14': None,
        '15': 'C1P_PIN', '16': 'C1M_PIN', '17': 'C2P_PIN', '18': 'C2M_PIN', '19': 'DAC_M', '20': 'DAC_P',
        '21': None, '22': None, '23': '3V3A', '24': 'CODEC_VREF', '25': 'GND',
        'A1': 'GND', 'A2': 'GND', 'A3': 'GND', 'A4': 'GND'},
       (CX, CY, 0), 'TAC5112IRGER', 'Texas Instruments', 'C44853692', 5.93, 'extended', 'TAC5112 C44853692')
add_ic('U15', 'LDO', '3.3V AP2112K', 'Package_TO_SOT_SMD:SOT-23-5', 'codec',
       {'1': '5VA', '2': 'GND', '3': '5VA', '4': None, '5': '3V3A'}, (133.5, 91.5, 0),
       'AP2112K-3.3TRG1', 'Diodes Incorporated', 'C51118', 0.1773, 'extended', 'AP2112K-3.3, codec AVDD')
add('C67', 'C1u0805', 'codec', {'1': '5VA', '2': 'GND'}, (130.4, 91.5, 90))
add('C68', 'C1u0805', 'codec', {'1': '3V3A', '2': 'GND'}, (136.7, 90.3, 270))
add('C60', 'C10u', 'codec', {'1': '3V3A', '2': 'GND'}, (140.25, 90.3, 270))
add('C61', 'C100n', 'codec', {'1': '3V3A', '2': 'GND'}, (140.25, 93.55, 90))
add('C62', 'C1u0603', 'codec', {'1': 'CODEC_VREF', '2': 'GND'}, (138.6, 93.55, 90))
add('C63', 'C100n', 'codec', {'1': 'CODEC_DREG', '2': 'GND'}, (135.8, 96.25, 180))
add('C64', 'C10u', 'codec', {'1': 'CODEC_DREG', '2': 'GND'}, (135.4, 94.4, 180))
add('C65', 'C100n', 'codec', {'1': '3V3', '2': 'GND'}, (135.4, 99.1, 180))
add('C66', 'C10u', 'codec', {'1': '3V3', '2': 'GND'}, (135.0, 101.0, 180))
add('R72', 'R4k7', 'codec', {'1': '3V3', '2': 'I2C_SDA'}, (141.25, 101.7, 90))
add('R73', 'R4k7', 'codec', {'1': '3V3', '2': 'I2C_SCL'}, (139.75, 101.7, 90))

# ---------------------------------------------------------------- USB-C power entry
# Rev E: the board runs from USB-C VBUS alone; the DC-005 jack J2 and its reverse-polarity PMOS Q1
# are gone.  U16 TPS2553 (TI SLVS841F) is a current-limited switch from USB_VBUS to 5V: built-in soft
# start, so the ~45 uF on 5V/5VA charges at the limit, not at whatever the host allows.
# R110 24k: IOS 0.999 / 1.073 / 1.159 A min/nom/max (SLVS841F eq. 1), above the 0.45 A load and below
# a 1.5 A USB-C advertisement.  EN tied to IN (always on); FAULT open, unused.
add_ic('U16', 'USBSW', 'TPS2553', 'Package_TO_SOT_SMD:SOT-23-6', 'power',
       {'1': 'USB_VBUS', '2': 'GND', '3': 'USB_VBUS', '4': None, '5': 'VBUS_ILIM', '6': '5V'},
       (63.0, 121.0, 0), 'TPS2553DBVR', 'Texas Instruments', 'C55266', 0.5412, 'extended',
       'TPS2553DBVR C55266')
add('R110', 'R24k', 'power', {'1': 'VBUS_ILIM', '2': 'GND'}, (64.6, 123.6, 180))
add('C113', 'C1u0805', 'power', {'1': 'USB_VBUS', '2': 'GND'}, (61.8625, 117.4, 90))   # IN bypass, 0.9 mm from pin 1

# Input legs: R_series (kept at the Rev D FDA input positions) -> DIV (1k, 560 pF to GND) -> 1 uF ->
# clamp (BAT54S to 3V3A/GND) -> 470R -> pin.  Rows run west to the codec in pin order.
LEGS = [  # name, series ref, source, row y, codec pin, side of the shunt parts (-1 north, +1 south)
    ('C2M', 'R67', 'TIA_OUT', 88.4, '18', -1),
    ('C2P', 'R66', 'LOW_BUF', 92.6, '17', +1),
    ('C1M', 'R61', 'LOW_BUF', 100.6, '16', -1),
    ('C1P', 'R60', 'HIGH_BUF', 104.8, '15', +1),
]
SHUNT = ['R62', 'R63', 'R64', 'R65']
C560 = ['C69', 'C70', 'C72', 'C73']
CAC = ['C74', 'C75', 'C76', 'C77']
CLAMP = ['D11', 'D12', 'D13', 'D14']
RPIN = ['R68', 'R69', 'R70', 'R71']
for i, (name, rs, src, y, pin, side) in enumerate(LEGS):
    parts[rs]['pins'] = {'1': src, '2': f'{name}_DIV'}
    parts[rs]['sheet'] = 'codec'
    # shunt parts hang off the DIV node, pad 1 on the row
    rot = 270 if side > 0 else 90
    add(SHUNT[i], 'R1k01', 'codec', {'1': f'{name}_DIV', '2': 'GND'}, (157.6, y + side * 1.6, rot))
    add(C560[i], 'C560p', 'codec', {'1': f'{name}_DIV', '2': 'GND'}, (156.0, y + side * 1.6, rot))
    add(CAC[i], 'C1u0805', 'codec', {'1': f'{name}_CLP', '2': f'{name}_DIV'}, (153.5, y, 0))
    add_ic(CLAMP[i], 'BAT54S', 'BAT54S', 'Package_TO_SOT_SMD:SOT-23', 'codec',
           {'1': 'GND', '2': '3V3A', '3': f'{name}_CLP'}, (149.8, y, 0),
           'BAT54S', 'hongjiacheng', 'C7420333', 0.0129, 'preferred', 'BAT54S clamp')
    add(RPIN[i], 'R470', 'codec', {'1': f'{name}_PIN', '2': f'{name}_CLP'}, (145.9, y, 0))

# ---------------------------------------------------------------- AFE: DUT_LO capacitor
add('C78', 'C100p', 'afe', {'1': 'DUT_LO', '2': 'GND'}, (179.5, 102.4, 270),
    query='Rev E TIA stability: 100 pF C0G DUT_LO (LCUR) to ground')

# ---------------------------------------------------------------- four-terminal BNC jacks on the top edge
# The J3 header (DUT_HI / DUT_LO) becomes four BNCs, 22 mm pitch (the usual 4TP spacing), in the
# Keysight front-panel order L CUR, L POT, H POT, H CUR read facing the jacks (board x descending).
# HCUR keeps the net DUT_HI (source side, RG resistors) and LCUR keeps DUT_LO (R94 to the TIA); the
# HIGH and LOW followers (U6.5, U7.5) now sense HPOT and LPOT.  R105/R106 (1k) tie each POT to its
# CUR so two-terminal use still reads; a Kelvin lead in parallel is ~0.1 ohm, so they carry no
# measurement current.
del parts['J3']
for ref, x, net, use in [('J3', 108.0, 'DUT_HI', 'HCUR'), ('J7', 130.0, 'HPOT', 'HPOT'),
                         ('J8', 152.0, 'LPOT', 'LPOT'), ('J9', 174.0, 'DUT_LO', 'LCUR')]:
    parts[ref] = {'ref': ref, 'value': f'BNC {use}', 'kind': 'BNC',
                  'footprint': 'LCR:BNC_SAMZO_KYWE-295-W4-N_Horizontal',
                  'pins': {'1': 'GND', '2': 'GND', '3': 'GND', '4': 'GND', '5': net},
                  'pcb': [x, 51.0, 0], 'sheet': 'afe', 'group': 'AFE', 'mpn': 'BNC-KYWE-295-W4-N',
                  'manufacturer': 'SAMZO', 'lcsc': 'C41416668', 'unit_usd': 1.29, 'stock': None,
                  'library_type': 'extended', 'assembly': 'Hand fit', 'source_query': 'BNC-KYWE-295 C41416668'}
add('R105', 'R1k', 'afe', {'1': 'DUT_HI', '2': 'HPOT'}, (137.0, 58.5, 0), query='Rev E HPOT default to HCUR')
add('R106', 'R1k', 'afe', {'1': 'DUT_LO', '2': 'LPOT'}, (177.0, 61.15, 270), query='Rev E LPOT default to LCUR')
parts['U6']['pins']['5'] = 'HPOT'
parts['U7']['pins']['5'] = 'LPOT'

# ---------------------------------------------------------------- relays (row below the TIA)
RLY_Y = 128.0
RELAYS = [  # ref, x, range, RG ref, RF net, RG net, set net
    ('K2', 152.5, '5k', 'R41', 'RF5K', 'RG5K', 'RLY_SET_MED'),
    ('K1', 167.5, '100R', 'R40', 'RF100', 'RG100', 'RLY_SET_LO'),
    ('K3', 182.3, '100k', 'R42', 'RF100K', 'RG100K', 'RLY_SET_HI'),
]
for ref, x, rng, rg, rf, rgnet, setnet in RELAYS:
    parts[ref] = {'ref': ref, 'value': f'TQ2SA-L2-5V {rng}', 'kind': 'RELAY2L',
                  'footprint': 'LCR:Relay_DPDT_Panasonic_TQ2SA_SMD',
                  'pins': {'1': 'VRLY', '2': None, '3': 'SOURCE_BUF', '4': rgnet, '5': setnet,
                           '6': 'RLY_RST', '7': rf, '8': 'TIA_OUT', '9': None, '10': 'VRLY'},
                  'pcb': [x, RLY_Y, 0], 'sheet': 'range', 'mpn': 'TQ2SA-L2-5V-Z', 'manufacturer': 'Panasonic',
                  'lcsc': 'C2684450', 'unit_usd': 2.27, 'stock': None, 'library_type': 'extended',
                  'assembly': 'SMT', 'source_query': 'docs/rev-e-range-switching.md'}
    # RG resistor sits under its relay's NO1 pad (pin 4 at x+2.54, y+4.78), RG pad north
    parts[rg]['pcb'] = [x + 2.54, RLY_Y + 8.0, 270]
    parts[rg]['pins'] = {'1': rgnet, '2': 'DUT_HI'}
    parts[rg]['sheet'] = 'afe'

# Coil drivers: AO3400A low side, 1N4148WS across each driven node, 100R gate, 100k pull-down.
# One driver row under the relays (y 140.6); each SET driver's drain is under its relay's pin 5
# (x+5.08) and its diode stands beside pin 5.  The shared RESET driver sits between K2 and K1.
DRV_Y = 140.6


def driver(q, drain, gate, gpio, dio, rg_, rpd, qx, dpos):
    add_ic(q, 'NMOS', 'AO3400A', 'Package_TO_SOT_SMD:SOT-23', 'range', {'1': gate, '2': 'GND', '3': drain},
           (qx, DRV_Y, 0), 'AO3400A', 'Alpha & Omega Semicon', 'C20917', 0.0973, 'basic', 'AO3400A relay driver')
    add_ic(dio, 'DIODE', '1N4148WS', 'Diode_SMD:D_SOD-323', 'range', {'1': 'VRLY', '2': drain}, dpos,
           '1N4148WS', 'Jiangsu Changjing Electronics Technology Co., Ltd.', 'C2128', 0.0143, 'basic',
           '1N4148WS coil flyback')
    add(rg_, 'R100', 'range', {'1': gpio, '2': gate}, (qx - 3.4425, DRV_Y - 0.95, 0))
    add(rpd, 'R100k', 'range', {'1': gate, '2': 'GND'}, (qx - 3.4425, DRV_Y + 0.8, 180))


for (ref, x, *_), (q, setnet, gpio, dio, rg_, rpd) in zip(RELAYS, [
        ('Q3', 'RLY_SET_MED', 'RNG_SET_MED', 'D6', 'R76', 'R77'),
        ('Q4', 'RLY_SET_LO', 'RNG_SET_LO', 'D7', 'R78', 'R79'),
        ('Q5', 'RLY_SET_HI', 'RNG_SET_HI', 'D8', 'R102', 'R103')]):
    driver(q, setnet, gpio + '_G', gpio, dio, rg_, rpd, x + 5.08 - 0.9375, (x + 6.4, RLY_Y + 8.6, 90))
driver('Q2', 'RLY_RST', 'RNG_RESET_G', 'RNG_RESET', 'D5', 'R74', 'R75', 164.0, (163.3, RLY_Y + 7.6, 0))
# K4: reference relay.  Pole 2 closes HCUR (COM2, pin 8) onto R107 (1k 0.1 %) to LCUR, a known
# impedance across the jacks for the firmware REFCAPTURE self-check.  Its RESET coil shares RLY_RST,
# so every range change opens it; its SET driver Q6 is on GPIO14.  Pole 1 is unused.
parts['K4'] = {'ref': 'K4', 'value': 'TQ2SA-L2-5V REF', 'kind': 'RELAY2L',
               'footprint': 'LCR:Relay_DPDT_Panasonic_TQ2SA_SMD',
               'pins': {'1': 'VRLY', '2': None, '3': None, '4': None, '5': 'RLY_SET_REF', '6': 'RLY_RST',
                        '7': 'REF_A', '8': 'DUT_HI', '9': None, '10': 'VRLY'},
               'pcb': [182.0, 70.0, 0], 'sheet': 'range', 'mpn': 'TQ2SA-L2-5V-Z', 'manufacturer': 'Panasonic',
               'lcsc': 'C2684450', 'unit_usd': 2.27, 'stock': None, 'library_type': 'extended',
               'assembly': 'SMT', 'source_query': 'docs/rev-e-range-switching.md'}
add('R107', 'R1k01', 'range', {'1': 'DUT_LO', '2': 'REF_A'}, (184.54, 62.0, 270), query='Rev E K4 reference, 0.1 %')
DRV_Y, _drv_y = 81.0, DRV_Y      # driver() places from DRV_Y: K4's driver sits under the relay
driver('Q6', 'RLY_SET_REF', 'RNG_SET_REF_G', 'RNG_SET_REF', 'D9', 'R108', 'R109', 187.08 - 0.9375, (188.6, 78.4, 90))
DRV_Y = _drv_y
# Coil supply from the unfiltered 5 V rail (relay pulses stay off 5VA, which feeds the codec LDO).
add('R101', 'R2R2', 'range', {'1': '5V', '2': 'VRLY'}, (143.2, 145.2, 0))
add('C112', 'C22u', 'range', {'1': 'VRLY', '2': 'GND'}, (148.2, 145.2, 0))

# ---------------------------------------------------------------- basic / preferred swaps
# sources/rev-e/JLC-basic-swaps-2026-10-20.json (JLC library API, 2026-10-20/21).
# D1: SRV05-4 (preferred, free line); datasheet pinout I/O 1,3,4,6, GND 2, rail 5 = USBLC6 roles.
parts['D1'].update(value='SRV05-4', mpn='SRV05-4', manufacturer='hongjiacheng', lcsc='C7420376',
                   unit_usd=0.0851, library_type='preferred', source_query='SRV05-4 C7420376')
# SW1/SW2: XUNPU TS-1088-AR02016 (basic), 3.9 x 3 mm top-actuated; KiCad footprint cites C720477.
for ref in ('SW1', 'SW2'):
    parts[ref].update(footprint='Button_Switch_SMD:SW_SPST_TS-1088-xR020', mpn='TS-1088-AR02016',
                      manufacturer='XUNPU', lcsc='C720477', unit_usd=0.0527, library_type='basic',
                      source_query='TS-1088-AR02016 C720477')
# sources/rev-e/JLC-basic-swaps-2026-10-29.json (JLC library API, 2026-10-29).
# TPS65131 boost divider 1.62M/150k -> 430k/40.2k (preferred): VPOS ratio 11.70 vs 11.80, divider current
# about 30 uA (datasheet: R2 < 200k).  Feed-forward caps re-sized to TI Eq. 11/12 for the new R1:
# C87 15 pF (basic, already on the BOM), C88 4.7 pF (preferred).  Two extended lines go.
parts['R81'].update(value='430k', mpn='0603WAF4303T5E', manufacturer='UNI-ROYAL(Uniroyal Elec)', lcsc='C25969',
                    unit_usd=0.0031, stock=188296, library_type='preferred', source_query='430k 1% 0603 C25969')
parts['R82'].update(value='40.2k', mpn='0603WAF4022T5E', manufacturer='UNI-ROYAL(Uniroyal Elec)', lcsc='C12447',
                    unit_usd=0.0021, stock=157370, library_type='preferred', source_query='40.2k 1% 0603 C12447')
parts['C87'].update(value='15pF C0G', mpn='CL10C150JB8NNNC', manufacturer='Samsung Electro-Mechanics',
                    lcsc='C1644', unit_usd=0.0111, stock=1076606, library_type='basic', source_query='15pF C0G C1644')
parts['C88'].update(value='4.7pF C0G', mpn='0603CG4R7C500NT', manufacturer='FH (Guangdong Fenghua Advanced Tech)',
                    lcsc='C1669', unit_usd=0.0054, stock=608277, library_type='preferred',
                    source_query='4.7pF C0G C1669')
# Stock and TCR, still extended: RT0603BRD072KL (C728588) fell to 22 in stock; Viking AR03BTCX2001 is the same
# 2k 0.1 % 25 ppm/C thin film.  The 5k RG/RF pair was 50 ppm/C against the 25 ppm/C drift budget
# (validation/rev-e-improvements/README.md); Viking AR03BTCX5001 is 25 ppm/C.
for ref in ('R32', 'R33'):
    parts[ref].update(mpn='AR03BTCX2001', manufacturer='Viking Tech', lcsc='C318130', unit_usd=0.0364,
                      stock=57336, source_query='2k 0.1% 25ppm 0603 C318130')
for ref in ('R41', 'R44'):
    parts[ref].update(mpn='AR03BTCX5001', manufacturer='Viking Tech', lcsc='C2828621', unit_usd=0.0318,
                      stock=55599, source_query='5k 0.1% 25ppm 0603 C2828621')

# ---------------------------------------------------------------- power flags, notes, ranges
design['power_flags'] = [n for n in design['power_flags'] if n not in ('3V3_DDS', '5VIN', '5V')] + ['USB_VBUS']
design['notes'][0] = 'One PCB; USB-C power (5V, 1A current limit) and USB data; USB-ground referenced.'
design['ranges'] = [
    {'ohms': 100, 'rg': 'R40', 'rf': 'R43', 'relay': 'K1', 'cf': 1e-10},
    {'ohms': 5000, 'rg': 'R41', 'rf': 'R44', 'relay': 'K2', 'cf': 1e-10},
    {'ohms': 100000, 'rg': 'R42', 'rf': 'R45', 'relay': 'K3', 'cf': 1e-10},
]
design['frequency'] = {'codec_fs_hz': 187500, 'bclk_hz': 12000000, 'mcu_clock_hz': 120000000,
                       'min_hz': 100, 'max_hz': 85000}

# ---------------------------------------------------------------- In1 ground plane follows the taller board
for z in routing['zones']:
    if z['net'] == 'GND' and z['layer'] == 'In1.Cu':
        z['points'] = [[x, 45.5 if y == 50.5 else y] for x, y in z['points']]

# ---------------------------------------------------------------- routing: drop removed nets
nets = {n for p in parts.values() for n in p['pins'].values() if n}
routing['tracks'] = [t for t in routing['tracks'] if t['net'] in nets]
routing['vias'] = [v for v in routing['vias'] if v['net'] in nets]
routing['keepouts'] = [k for k in routing['keepouts'] if not k['name'].startswith('FDA ')
                       and k['name'] != 'Matched RG and high sense']

# ---------------------------------------------------------------- prune Rev D copper left dangling
# A Rev D track end or via survives only if it still touches copper of its own net: a pad of a part
# that keeps its Rev D position (cad/tools/rev_d_pads.json, native pad centres from the Rev D build),
# a via, or another segment.  Pads count on F.Cu, through-hole pads on every layer.
REV_D_PADS = json.loads((CAD / 'tools' / 'rev_d_pads.json').read_text())
REV_D_PARTS = {p['ref']: p for p in git_json('design.json')['parts']}
THT = ('J', 'H')


def anchors():
    out = []
    for ref, p in parts.items():
        old = REV_D_PARTS.get(ref)
        same_pads = old and (old['footprint'] == p['footprint'] or ref in ('SW1', 'SW2'))  # TS-1088 pads cover B3U's
        if not old or old['pcb'] != p['pcb'] or not same_pads:
            continue
        for pin, net in p['pins'].items():
            if net and pin in REV_D_PADS[ref]:
                x, y, _, hx, hy = REV_D_PADS[ref][pin]
                out.append((net, x, y, hx, hy, ref.startswith(THT) or (ref == 'J1' and pin.startswith('S'))))
    return out


def in_pad(pt, x, y, hx, hy, tol=0.06):
    return abs(pt[0] - x) <= hx + tol and abs(pt[1] - y) <= hy + tol


# Rev D GND vias stitch to the In1 plane and need no track; they stay unless they sat inside a
# removed part (its exposed-pad vias), where Rev E parts now go.
GONE = [REV_D_PADS[r]['_courtyard'] for r in REMOVE + ['R30', 'R31', 'R32', 'C34', 'C35']]


def resolve(pt):
    if isinstance(pt, str):
        ref, pin = pt.split('.')
        return REV_D_PADS[ref][pin][:2]
    return pt


segs = []
for t in routing['tracks']:
    pts = [resolve(p) for p in t['points']]
    for a, b in zip(pts, pts[1:]):
        if a != b:
            segs.append({'net': t['net'], 'layer': t['layer'], 'width': t.get('width', 0.2),
                         'points': [list(a), list(b)]})


def on_segment(p, s, tol=0.01):
    (ax, ay), (bx, by) = s['points']
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    u = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L)) if L else 0.0
    return math.hypot(ax + u * dx - p[0], ay + u * dy - p[1]) < tol


pads = anchors()
changed = True
while changed:
    changed = False
    vias = routing['vias']
    for s in list(segs):
        for end in s['points']:
            ok = any(n == s['net'] and (s['layer'] == 'F.Cu' or tht) and in_pad(end, x, y, hx, hy)
                     for n, x, y, hx, hy, tht in pads)
            ok = ok or any(v['net'] == s['net'] and math.hypot(v['at'][0] - end[0], v['at'][1] - end[1]) < 0.05
                           for v in vias)
            ok = ok or any(o is not s and o['net'] == s['net'] and o['layer'] == s['layer'] and on_segment(end, o)
                           for o in segs)
            if not ok:
                segs.remove(s)
                changed = True
                break
    keep = []
    for v in vias:
        hits = [s for s in segs if s['net'] == v['net'] and on_segment(v['at'], s, 0.05)]
        hits += [1 for n, x, y, hx, hy, tht in pads if n == v['net'] and in_pad(v['at'], x, y, hx, hy)]
        layers = {s['layer'] for s in hits if isinstance(s, dict)}
        gone = any(x0 <= v['at'][0] <= x1 and y0 <= v['at'][1] <= y1 for x0, y0, x1, y1 in GONE)
        if v['net'] == 'GND' and not gone or len(layers) >= 2 or (hits and len(hits) >= 2):
            keep.append(v)
        else:
            changed = True
    routing['vias'] = keep
routing['tracks'] = segs

# ---------------------------------------------------------------- Rev E copper
exec((CAD / 'tools' / 'rev_e_routes.py').read_text())

# ---------------------------------------------------------------- vias: 0.3 mm drill everywhere
for v in routing['vias']:
    v['drill'] = 0.3
    v['diameter'] = max(v.get('diameter', 0.6), 0.45)   # JLC 0.3 mm option: 0.45 mm minimum

design['parts'] = list(parts.values())
(CAD / 'design.json').write_text(json.dumps(design, indent=2) + '\n')
(CAD / 'routing.json').write_text(json.dumps(routing, indent=2) + '\n')
print(f"{len(design['parts'])} parts, {len(routing['tracks'])} tracks, {len(routing['vias'])} vias")
