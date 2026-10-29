# Rev F copper, executed inside cad/tools/rev_f.py (names: parts, routing, P, B, T, T45, V, KO).
# Hand routing: every segment and via is given by coordinates or a pad reference.  Layers: F.Cu parts
# side, In1 GND plane, In2 and B.Cu signal.  One section per block; each passes the pre-DRC before
# the next starts.

# ============================================================== 1. analog core
# --- DUT_HI (HCUR): a B.Cu tree, not a loop.  J3 centre pin -> y 56.9 under the jack band (GND pins
# end at y 56.0) -> K4 COM2 on its west side; one F.Cu branch at x 90.2 down the west flank of the
# relay column feeds R105 (to HPOT) and the three RG resistors.  No copper returns along another path.
T('DUT_HI', 'B.Cu', 'J3.5', (67.0, 56.9), (131.5, 56.9), (131.5, 66.0))
V('DUT_HI', 131.5, 66.0)
T('DUT_HI', 'F.Cu', (131.5, 66.0), 'K4.8')
V('DUT_HI', 90.2, 56.9)
T('DUT_HI', 'F.Cu', (90.2, 56.9), (90.2, 97.54))
T('DUT_HI', 'F.Cu', 'R105.1', (90.2, 61.125))
for r, y in (('R40', 67.54), ('R41', 82.54), ('R42', 97.54)):
    T('DUT_HI', 'F.Cu', (90.2, y), f'{r}.2')
for r, k in (('R40', 'K1'), ('R41', 'K2'), ('R42', 'K3')):
    T(parts[r]['pins']['1'], 'F.Cu', f'{r}.1', f'{k}.4')
# --- HPOT: J7 centre pin straight down to U6 +IN (pin 5); R105 (1M DUT_HI-HPOT bias) beside it
T('HPOT', 'F.Cu', 'J7.5', (89.0, 57.2), (87.475, 58.725), 'U6.5')
T('HPOT', 'F.Cu', 'R105.2', (87.475, 59.475))
# --- U6: HIGH_BUF to R60 (C1P leg series R at the op-amp), SRC_DRV to R104, EXCITE south
T('HIGH_BUF', 'F.Cu', 'U6.7', (86.175, 61.825), (85.6, 61.25), 'R60.1')
T('HIGH_BUF', 'F.Cu', 'U6.6', (86.825, 62.75), (86.175, 62.75))
T('SRC_DRV', 'F.Cu', 'U6.1', (85.525, 69.95), 'R104.1')
T('SRC_DRV', 'F.Cu', 'U6.2', (86.175, 68.9), (85.525, 68.9))
T('SOURCE_BUF', 'F.Cu', 'R104.2', (85.5, 72.025), (85.95, 72.475), (85.95, 72.8))
V('SOURCE_BUF', 85.95, 72.8)
T('SOURCE_BUF', 'In2.Cu', (85.95, 72.8), (92.4, 72.8), (93.2, 72.0))
T('SOURCE_BUF', 'In2.Cu', (93.2, 65.0), (93.2, 95.0))
for k in ('K1', 'K2', 'K3'):
    y = P(f'{k}.3')[1]
    V('SOURCE_BUF', 93.2, y)
    T('SOURCE_BUF', 'F.Cu', (93.2, y), f'{k}.3')
T('EXCITE', 'F.Cu', 'U6.3', (86.825, 73.6), (79.6, 73.6))
V('EXCITE', 79.6, 73.6)
T('EXCITE', 'B.Cu', (79.6, 73.6), (79.6, 59.4), (71.53, 59.4), (70.88, 60.05))
# --- U6 supplies: 12V NW (C50 1.4 mm from pin 8), -12V SE (C51 1.7 mm from pin 4)
T('12V', 'F.Cu', 'U6.8', (85.525, 64.775), 'C50.1')
T('12V', 'F.Cu', (84.4, 64.775), (84.4, 66.5), (79.5, 66.5), (79.5, 70.45), 'C39.1')
V('12V', 84.4, 66.5)
V('GND', 84.2, 62.3)
T('GND', 'F.Cu', 'C50.2', (84.2, 62.3))
T('-12V', 'F.Cu', 'U6.4', (87.475, 68.375), 'C51.1', (89.1, 69.3))
V('-12V', 89.1, 69.3)
V('GND', 89.1, 65.9)
T('GND', 'F.Cu', 'C51.2', (89.1, 65.9))
# second tier on the supply taps
V('-12V', 89.1, 74.6)
T('-12V', 'F.Cu', 'C43.1', (89.1, 74.6))
V('-12V', 89.1, 76.8)
T('-12V', 'F.Cu', 'C45.1', (89.1, 76.8))
V('GND', 86.0, 75.5)
T('GND', 'F.Cu', 'C43.2', (86.0, 75.5))
V('GND', 85.4, 77.9)
T('GND', 'F.Cu', 'C45.2', (85.4, 77.9))
V('12V', 84.4, 80.3)
T('12V', 'F.Cu', (84.4, 80.3), 'C42.1', 'C44.1')
V('GND', 87.5, 80.4)
T('GND', 'F.Cu', 'C42.2', (87.5, 80.4))
V('GND', 87.4, 83.3)
T('GND', 'F.Cu', 'C44.2', (87.4, 83.3))

# --- TIA (U7): SUM node compact west of the pins, plane void under it
T('TIA_OUT', 'F.Cu', 'U7.1', (113.525, 72.925), 'C104.2', (111.3, 72.925), (110.9, 72.525), 'R67.1')
V('TIA_OUT', 110.9, 71.4)
T('TIA_OUT', 'In2.Cu', (110.9, 71.4), (106.9, 71.4))
T('TIA_OUT', 'In2.Cu', (106.9, 65.0), (106.9, 95.0))
for k in ('K1', 'K2', 'K3'):
    y = P(f'{k}.8')[1]
    V('TIA_OUT', 106.9, y)
    T('TIA_OUT', 'F.Cu', f'{k}.8', (106.9, y))
T('TIA_SUM', 'F.Cu', 'U7.2', (114.175, 73.6), (113.2, 74.575), 'C104.1', 'R43.1')
T('TIA_SUM', 'F.Cu', 'R94.2', (113.8, 75.175), (113.2, 74.575))
T('TIA_SUM', 'F.Cu', (111.3, 74.575), (111.3, 77.9), 'R45.1')
T('TIA_SUM', 'F.Cu', (111.3, 76.2), 'R44.1')
KO('TIA summing node', [(109.9, 73.6), (114.45, 73.6), (114.45, 76.2), (112.4, 78.4), (109.9, 78.4)])
T('RF100', 'F.Cu', 'K1.7', (107.6, 67.54), (107.6, 73.4), 'R43.2')
T('RF5K', 'F.Cu', 'K2.7', (106.3, 82.54), (107.6, 81.24), (107.6, 77.375), 'R44.2')
T('RF100K', 'F.Cu', 'K3.7', (108.8, 97.54))
V('RF100K', 108.8, 97.54)
T('RF100K', 'In2.Cu', (108.8, 97.54), (108.8, 79.0))
V('RF100K', 108.8, 79.0)
T('RF100K', 'F.Cu', (108.8, 79.0), 'R45.2')
T('DUT_LO', 'F.Cu', 'R94.1', 'C78.1')
V('GND', 113.8, 81.5)
T('GND', 'F.Cu', 'C78.2', (113.8, 81.5))
V('GND', 114.825, 73.65)
T('GND', 'F.Cu', 'U7.3', (114.825, 73.65))
# U7 supplies: 12V NW (C52 2.0 mm), -12V SE (C53 1.8 mm)
T('12V', 'F.Cu', 'U7.8', (113.525, 67.15), (113.05, 66.675), 'C52.1', 'C46.1', (109.425, 66.675), 'C48.1')
V('12V', 108.2, 66.9)
T('12V', 'F.Cu', 'C48.1', (108.2, 66.3), (108.2, 66.9))
V('GND', 111.5, 64.1)
T('GND', 'F.Cu', 'C52.2', (111.5, 64.1))
V('GND', 110.5, 63.9)
T('GND', 'F.Cu', 'C46.2', (110.5, 63.9))
V('GND', 108.6, 62.8)
T('GND', 'F.Cu', 'C48.2', (108.6, 62.8))
T('-12V', 'F.Cu', 'U7.4', (115.86, 71.725), 'C53.1', 'C47.1', (120.425, 71.725), 'C49.1')
V('-12V', 121.6, 71.0)
T('-12V', 'F.Cu', 'C49.1', (120.95, 71.65), (121.6, 71.0))
for c, y in (('C53', 74.2), ('C47', 74.2), ('C49', 74.5)):
    V('GND', P(f'{c}.2')[0], y)
    T('GND', 'F.Cu', f'{c}.2', (P(f'{c}.2')[0], y))
# LOW_BUF to R61/R66 (codec leg series R at the op-amp), LPOT from J8
T('LOW_BUF', 'F.Cu', 'U7.6', 'R66.1', 'R61.1')
T('LOW_BUF', 'F.Cu', 'U7.7', (114.175, 67.0), (114.825, 66.35))
T('LPOT', 'F.Cu', 'J8.5', (111.0, 55.5), (116.3, 60.8), (116.3, 66.6), (115.475, 67.425), 'U7.5')
T('LPOT', 'F.Cu', 'R106.2', (115.5, 60.0))
# --- DUT_LO (LCUR): J9 -> R107 (REF_A) and R106 (LPOT) -> C78/R94 at the TIA, all F.Cu
T('DUT_LO', 'F.Cu', 'J9.5', (133.0, 57.6), (130.5, 60.1), (122.6, 60.1), (119.725, 60.1))
T('DUT_LO', 'F.Cu', (130.5, 60.1), (128.775, 61.825), 'R107.1')
T('DUT_LO', 'F.Cu', (122.6, 60.1), (122.6, 77.0), (121.8, 77.8), (113.8, 77.8))
T('REF_A', 'F.Cu', 'R107.2', 'K4.7')

# --- codec leg dividers: series R at the op-amp, divider node to the legs on In2 north of the
# relays (y 58.1-60.1), down the west side (x 81.2-83.45), F.Cu into each leg.  Order west->east =
# deepest leg first, so no two cross.
T('C1M_DIV', 'F.Cu', 'R61.2', (113.175, 61.0))
V('C1M_DIV', 113.175, 61.0)
T('C2P_DIV', 'F.Cu', 'R66.2', (112.6, 63.6), (112.4, 63.4), (112.4, 62.8))
V('C2P_DIV', 112.4, 62.8)
T('C2M_DIV', 'F.Cu', 'R67.2', (110.9, 67.6))
V('C2M_DIV', 110.9, 67.6)
T('C1P_DIV', 'F.Cu', 'R60.2', (85.6, 58.1))
V('C1P_DIV', 85.6, 58.1)
LEG = {'C1P_DIV': (81.2, 58.1, 'R65', 'C73', 'C77'), 'C1M_DIV': (81.95, 58.9, 'R64', 'C72', 'C76'),
       'C2P_DIV': (82.7, 59.5, 'R63', 'C70', 'C75'), 'C2M_DIV': (83.45, 60.1, 'R62', 'C69', 'C74')}
T('C1M_DIV', 'In2.Cu', (113.175, 61.0), (113.175, 58.9), (81.95, 58.9))
T('C2P_DIV', 'In2.Cu', (112.4, 62.8), (112.4, 59.5), (82.7, 59.5))
T('C2M_DIV', 'In2.Cu', (110.9, 67.6), (109.95, 66.65), (109.95, 60.1), (83.45, 60.1))
T('C1P_DIV', 'In2.Cu', (85.6, 58.1), (81.2, 58.1))
for net, (x, yh, r, c, cac) in LEG.items():
    ry = P(f'{r}.1')[1]
    yv = ry - 1.1 if net == 'C1P_DIV' else ry
    T(net, 'In2.Cu', (x, yh), (x, yv))
    V(net, x, yv)
    T(net, 'F.Cu', (x, yv), (P(f'{r}.1')[0] + 0.6, ry) if net == 'C1P_DIV' else (x, yv), f'{r}.1', f'{c}.1')
    T(net, 'F.Cu', f'{c}.1', f'{cac}.2')

# ============================================================== 2. +/-12 V trunks (B.Cu)
# LDO outputs west under the relay column: -12V at y 81.0 (north), 12V at y 82.5 (south), so every
# -12V tap comes down from the north without crossing 12V; the two 12V taps that must cross the
# -12V trunk (U6 at x 84.4, U7 at x 108.2) hop it on In2 between two vias.
V('12V', 123.0, 98.1)
T('12V', 'F.Cu', 'C95.1', (123.0, 98.1))
T('12V', 'B.Cu', (123.0, 98.1), (123.0, 82.5), (84.4, 82.5))
V('12V', 84.4, 82.5)
T('12V', 'In2.Cu', (84.4, 82.5), (84.4, 80.3))
T('12V', 'B.Cu', (84.4, 80.3), (84.4, 66.5))
T('12V', 'B.Cu', (108.2, 66.9), (108.2, 79.9))
V('12V', 108.2, 79.9)
T('12V', 'In2.Cu', (108.2, 79.9), (108.2, 82.5))
V('12V', 108.2, 82.5)
V('-12V', 136.2, 98.1)
T('-12V', 'F.Cu', 'C100.1', (136.2, 98.1))
T('-12V', 'B.Cu', (136.2, 98.1), (136.2, 81.0), (67.0, 81.0), (67.0, 77.0))
V('-12V', 67.0, 77.0)
T('-12V', 'F.Cu', (67.0, 77.0), (66.6, 77.4), (63.55, 77.4), 'C40.1')
T('-12V', 'B.Cu', (89.1, 69.3), (89.1, 81.0))
T('-12V', 'B.Cu', (121.6, 71.0), (121.6, 81.0))

# --- codec DAC to the U5 difference stage: F.Cu out of the pins between the 3V3A riser and the
# corner GND via, B.Cu round the source-stage plane void (DAC_P west and under, DAC_M east side)
T('DAC_P', 'F.Cu', 'U14.20', (64.75, 84.4), (64.85, 84.3), (64.85, 83.9))
V('DAC_P', 64.85, 83.9)
T('DAC_P', 'B.Cu', (64.85, 83.9), (64.85, 74.6), (69.4, 74.6), (69.4, 72.3))
V('DAC_P', 69.4, 72.3)
T('DAC_P', 'F.Cu', (69.4, 72.3), (68.5, 71.4), 'R30.1')
T('DAC_M', 'F.Cu', 'U14.19', (65.25, 85.4), (65.4, 85.25), (65.4, 84.9))
V('DAC_M', 65.4, 84.9)
T('DAC_M', 'B.Cu', (65.4, 84.9), (66.3, 84.0), (66.3, 76.0), (78.7, 76.0), (78.7, 60.2), (75.5, 60.2))
V('DAC_M', 75.5, 60.2)
T('DAC_M', 'F.Cu', (75.5, 60.2), 'R31.2')

# ============================================================== 3. relay coils: VRLY, SET, RST
# Under the relay bodies, between the pad rows (x 96.7-103.3): SET columns F.Cu on the west half,
# the RST column F.Cu on the east half, VRLY on In2 (spine x 100, a bar per relay; K1's bar is F.Cu
# because the codec divider lines pass under K1's top row on In2).  Fan-out to the drivers below K3.
T('VRLY', 'F.Cu', 'K1.1', 'K1.10')
T('VRLY', 'F.Cu', (100.0, 59.92), (100.0, 61.0))
V('VRLY', 100.0, 61.0)
T('VRLY', 'In2.Cu', (100.0, 61.0), (100.0, 103.6))
for k in ('K2', 'K3'):
    y = P(f'{k}.1')[1]
    for pin, x in (('1', 97.2), ('10', 102.8)):
        V('VRLY', x, y)
        T('VRLY', 'F.Cu', f'{k}.{pin}', (x, y))
    T('VRLY', 'In2.Cu', (97.2, y), (102.8, y))
V('VRLY', 100.0, 103.6)
T('VRLY', 'B.Cu', (100.0, 103.6), (100.0, 109.6))
T('VRLY', 'B.Cu', (91.257, 109.6), (121.058, 109.6))
# D6-D8 VRLY vias at y 109.6 come with the copied driver block
V('VRLY', 94.608, 107.6)
T('VRLY', 'F.Cu', 'D5.1', (94.608, 107.6))
T('VRLY', 'B.Cu', (94.608, 107.6), (94.608, 109.6))
# filter R101 (5V -> VRLY) and C112 at the foot of the column
T('VRLY', 'B.Cu', (100.0, 107.4), (101.3, 107.4))
V('VRLY', 101.3, 107.4)
T('VRLY', 'F.Cu', (101.3, 107.4), 'R101.2', (102.2, 106.4), (103.3, 105.3), 'C112.1')
V('GND', 101.9, 108.9)
T('GND', 'F.Cu', 'C112.2', (101.9, 108.9))
# SET lines
T('RLY_SET_LO', 'F.Cu', 'K1.5', (98.6, 70.08), (98.6, 104.5), (104.938, 104.5), 'Q4.3')
T('RLY_SET_LO', 'F.Cu', (104.938, 105.2), (106.257, 106.519), 'D7.2')
T('RLY_SET_MED', 'F.Cu', 'K2.5', (97.9, 85.08), (97.9, 103.6), (89.938, 103.6), 'Q3.3')
T('RLY_SET_MED', 'F.Cu', (91.257, 103.6), 'D6.2')
T('RLY_SET_HI', 'F.Cu', 'K3.5', (97.2, 100.08), (97.2, 101.8))
V('RLY_SET_HI', 97.2, 101.8)
T('RLY_SET_HI', 'B.Cu', (97.2, 101.8), (120.0, 101.8), (121.058, 102.858), (121.058, 105.4))
V('RLY_SET_HI', 121.058, 105.4)
T('RLY_SET_HI', 'F.Cu', (121.058, 105.4), 'D8.2')
T('RLY_SET_HI', 'F.Cu', (121.058, 105.4), (119.737, 105.4), 'Q5.3')
# RST: one column, K1-K3 stubs, B.Cu to Q2/D5 and north to K4
T('RLY_RST', 'F.Cu', (102.0, 68.5), (102.0, 103.0))
for k in ('K1', 'K2', 'K3'):
    T('RLY_RST', 'F.Cu', f'{k}.6', (102.0, P(f'{k}.6')[1]))
V('RLY_RST', 102.0, 103.0)
T('RLY_RST', 'B.Cu', (102.0, 103.0), (97.3, 103.0), (96.7, 103.6), (96.7, 105.2))
V('RLY_RST', 96.7, 105.2)
T('RLY_RST', 'F.Cu', (96.7, 105.2), 'D5.2')
V('RLY_RST', 102.0, 68.5)
T('RLY_RST', 'B.Cu', (102.0, 68.5), (102.0, 57.6), (130.9, 57.6), (130.9, 60.92))
V('RLY_RST', 130.9, 60.92)
T('RLY_RST', 'F.Cu', (130.9, 60.92), 'K4.6')
# K4: VRLY from the column foot on In2, bar under the body; SET_REF to D9 and Q6
T('VRLY', 'In2.Cu', (100.0, 103.6), (132.0, 103.6), (132.0, 72.0), (131.2, 71.2))
V('VRLY', 131.2, 71.2)
T('VRLY', 'F.Cu', (131.2, 71.2), 'K4.10', 'K4.1', (144.6, 71.08), (144.6, 73.05), 'D9.1')
T('RLY_SET_REF', 'F.Cu', 'K4.5', (146.0, 60.92), (147.9, 62.82), (147.9, 77.0), (146.9, 78.0), 'Q6.3')
T('RLY_SET_REF', 'F.Cu', (147.9, 70.95), 'D9.2')
