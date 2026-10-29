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

# ============================================================== 4. power entry, 5 V trunk, 5VA
# VBUS from the receptacle fan-out (C15) to C113 and U16 IN/EN (east column, x 57.75)
T('USB_VBUS', 'F.Cu', 'C15.1', (61.225, 127.9), (60.075, 129.05), 'C113.1', w=0.4)
T('USB_VBUS', 'F.Cu', 'U16.3', (57.75, 128.95), (57.75, 130.85), 'U16.1', w=0.4)
T('USB_VBUS', 'F.Cu', 'C113.1', (57.75, 129.05), w=0.4)
V('GND', 59.2, 131.9)
T('GND', 'F.Cu', 'C113.2', (59.2, 131.9))
V('GND', 55.6, 129.9)                      # inside the SOT-23-6 body, between the pin columns
T('GND', 'F.Cu', 'U16.2', (55.6, 129.9))
T('VBUS_ILIM', 'F.Cu', 'U16.5', (52.825, 129.9), 'R110.1')
V('GND', 52.0, 128.15)
T('GND', 'F.Cu', 'R110.2', (52.0, 128.15))
# U16 OUT -> C16 -> U3 IN/EN; FB1 feed via at OUT
T('5V', 'F.Cu', 'U16.6', (54.462, 131.75), (55.3, 131.75), (55.95, 132.4), 'C16.1', w=0.5)
T('5V', 'F.Cu', 'C16.1', (55.95, 134.0), 'U3.1', w=0.5)
T('5V', 'F.Cu', 'U3.1', (54.7, P('U3.1')[1]), (54.7, P('U3.3')[1]), 'U3.3', w=0.25)
V('GND', 53.1, 134.1)
T('GND', 'F.Cu', 'C16.2', (53.1, 134.1))
V('GND', *parts['U3']['pcb'][:2])          # inside the SOT-23-5 body
T('GND', 'F.Cu', 'U3.2', tuple(parts['U3']['pcb'][:2]))
# U3 OUT -> C17 -> C18 and the RP2040 core 3V3 network (its Rev E junction at (63.086, 137.939))
T('3V3', 'F.Cu', 'U3.5', (58.6, 134.95), (58.85, 134.7), 'C17.1', (60.6, 134.7), (61.3, 135.4), (61.3, 137.939), (63.086, 137.939))
T('3V3', 'F.Cu', (61.3, 137.939), (61.3, 140.25), 'C18.1')
V('GND', 60.0, 137.55)
T('GND', 'F.Cu', 'C17.2', (60.0, 137.55))
# 5 V trunk: B.Cu, 1.0 mm, down the west side of U3 and along the south edge (y 144.1) to L1 / C80
for x in (57.4, 58.3):
    V('5V', x, 132.9)
T('5V', 'F.Cu', 'C16.1', (58.3, 132.9), w=0.8)
# east end: the switcher block's own trunk via (128.604, 142.802, copied) plus a second one beside it
T('5V', 'B.Cu', (57.4, 132.9), (58.3, 132.9), (58.3, 143.6), (58.8, 144.1), (128.6, 144.1), (128.6044, 142.8016), w=1.0)
V('5V', 128.6, 143.75)
T('5V', 'F.Cu', (128.6, 143.75), (128.6, 143.0), w=0.5)
T('5V', 'F.Cu', 'C80.1', (131.45, 143.0), 'L1.1', w=1.0)
V('GND', 122.9, 143.0)
T('GND', 'F.Cu', 'C80.2', (122.9, 143.0), w=0.5)
# 5V to FB1 at the codec: B.Cu up the west edge, between the receptacle's shield legs
V('5V', 54.462, 131.75)
T('5V', 'B.Cu', (54.462, 131.75), (54.462, 89.6), w=0.3)
V('5V', 54.462, 89.6)
T('5V', 'F.Cu', (54.462, 89.6), (53.0, 89.6), 'FB1.1', w=0.3)
T('5VA', 'F.Cu', 'FB1.2', (53.0, 84.5), (53.4, 84.1), 'C67.1', w=0.3)
T('5VA', 'F.Cu', 'FB1.2', (53.413, 85.525), 'C103.1', w=0.3)
V('GND', 56.3, 89.4)
T('GND', 'F.Cu', 'C103.2', (56.3, 89.4))
# relay supply: 5V tap from the trunk up In2 to y 116.5, then F.Cu past the driver row to R101 (VRLY
# filter) at the relay column foot; the RNG gate lines cross it on In2 north of y 116
V('5V', 98.7, 144.1)
T('5V', 'In2.Cu', (98.7, 144.1), (98.7, 116.5), w=0.3)
V('5V', 98.7, 116.5)
T('5V', 'F.Cu', (98.7, 116.5), (98.7, 107.0), (99.3, 106.4), 'R101.1', w=0.3)

# ============================================================== 5. USB data, VBUS sense
# (the five Rev E vias these lines end on are the copied ones, kept now that they lead somewhere)
# D-: ESD-array bar via (Rev E position) -> B.Cu -> the core's Rev E via at R3 (Rev E stub)
T('USB_DM', 'F.Cu', (63.3021, 123.1496), (63.3021, 123.838))
T('USB_DM', 'B.Cu', (63.3021, 123.838), (64.3, 123.838), (66.662, 126.2), (70.6, 126.2), (72.279, 127.879),
  (77.219, 127.879))   # between the In2 escape vias of U1's west pins (section 8)
T('USB_DM', 'F.Cu', (77.219, 127.879), (77.2, 127.9), (77.2, 129.15), (76.0, 130.35), w=0.15)
# D+: receptacle via (Rev E position) -> In2 under D1 -> ESD-array via -> In2 south past D- ->
# B.Cu along the Rev E y 128.45 line -> the core's Rev E via at R4.  The D+/D- crossing is the In2 leg.
T('USB_DP', 'F.Cu', 'J1.B6', (58.7525, 122.75), (58.8831, 122.619))
T('USB_DP', 'In2.Cu', (58.8831, 122.619), (59.6021, 121.9), (65.342, 121.9), (65.9, 122.458), (65.9, 127.9))
V('USB_DP', 65.342, 121.9)
T('USB_DP', 'F.Cu', (64.492, 121.05), (65.342, 121.9))
V('USB_DP', 65.9, 127.9)
T('USB_DP', 'B.Cu', (65.9, 127.9), (66.45, 128.45), (78.981, 128.45), (79.597, 129.065))
T('USB_DP', 'F.Cu', (78.3368, 130.325), (79.597, 129.065))
# VBUS to the sense divider R5/R6 (core group, Rev E offsets): via off the receptacle's VBUS ring,
# B.Cu along the Rev E y 117.05 line, Rev E F.Cu entry to R5
T('USB_VBUS', 'F.Cu', (57.2, 116.9233), (57.2, 116.2))
V('USB_VBUS', 57.2, 116.2)
T('USB_VBUS', 'B.Cu', (57.2, 116.2), (69.0, 116.2), (69.85, 117.05), (73.55, 117.05), (73.75, 116.85),
  (76.35, 116.85), (76.6, 117.1), (77.1, 117.1))
T('USB_VBUS', 'F.Cu', (77.1, 117.1), (82.4, 117.1), (83.175, 116.325), 'R5.1')

# ============================================================== 6. codec bus: U1 east pins -> U14 (B.Cu bundle)
# U1 end: Rev E escape stubs and vias (U1 keeps its Rev E pose relative to these pins).  B.Cu exits east
# between the core's GND vias, then a 0.4 mm-pitch bundle north at x 82.2-84.6, jogging 0.6 mm west
# beside the sense divider (staggered, y 117.7-115.3), west along y 99.0-102.6 under the codec legs' south edge.  3V3 for the codec
# rides as the bundle's east/north line from the core 3V3 column at C10.
T('I2C_SCL', 'F.Cu', 'U1.12', (79.1, 121.7), (79.85, 120.95))
V('I2C_SCL', 79.85, 120.95)
T('I2C_SDA', 'F.Cu', 'U1.11', (79.198, 122.1), (79.3, 122.0), (79.75, 122.0))
V('I2C_SDA', 79.75, 122.0)
T('I2S_BCLK', 'F.Cu', 'U1.6', (78.347, 124.1), (78.796, 124.55), (79.727, 124.55), (79.938, 124.761))
V('I2S_BCLK', 79.938, 124.761)
T('I2S_DIN', 'F.Cu', 'U1.4', (78.54, 124.9), (78.779, 125.139))
V('I2S_DIN', 78.779, 125.139)
T('I2S_DOUT', 'F.Cu', 'U1.5', (76.476, 124.5), (76.067, 124.909))
V('I2S_DOUT', 76.067, 124.909)          # inside U1's pin ring, clear of the EP vias (Rev E)
DROP('I2S_DOUT', 79.6, 125.1, 80.4, 125.4)  # Rev E's continuation east of the via field
V('3V3', 81.0, 129.4)                    # on the core 3V3 column (C6/C10)
BUS = [  # net, exit row (east of the vias), vertical x below / above the jog, codec-side row
    ('I2C_SCL', 120.95, 82.2, 102.6), ('I2C_SDA', 121.7, 82.6, 102.0), ('I2S_FSYNC', 124.2, 83.0, 101.4),
    ('I2S_BCLK', 124.761, 83.4, 100.8), ('I2S_DOUT', 125.25, 83.8, 100.2), ('I2S_DIN', 126.4, 84.2, 99.6),
    ('3V3', 129.4, 84.6, 99.0)]
START = {'I2C_SCL': [(79.85, 120.95)], 'I2C_SDA': [(79.75, 122.0), (80.05, 121.7)],
         'I2S_FSYNC': [(79.45, 124.2)], 'I2S_BCLK': [(79.938, 124.761)],
         'I2S_DOUT': [(76.067, 124.909), (76.422, 124.554), (78.974, 124.554), (79.386, 124.966), (79.67, 125.25)],
         'I2S_DIN': [(78.779, 125.139), (80.04, 126.4)], '3V3': [(81.0, 129.4)]}
# codec end: where each line leaves the westward run (x), and what it does there
WEST_END = {'3V3': 65.4, 'I2S_DIN': 60.15, 'I2S_DOUT': 59.6, 'I2S_BCLK': 59.1, 'I2S_FSYNC': 61.0,
            'I2C_SDA': 67.4, 'I2C_SCL': 68.2}
for i, (net, row, x, crow) in enumerate(BUS):
    xe = WEST_END[net]
    w = 0.3 if net == '3V3' else 0.2
    yj = 117.7 - 0.4 * i          # staggered horizontal jogs (west line first), so the pitch holds
    T(net, 'B.Cu', *START[net], (x, row), (x, yj), (x - 0.6, yj), (x - 0.6, crow), (xe, crow), w=w)
# 3V3: up to a via, F.Cu bar through R73/R72's 3V3 lands to C66 (Rev E bar position)
T('3V3', 'B.Cu', (65.4, 99.0), (65.4, 94.3), w=0.3)
V('3V3', 65.4, 94.3)
T('3V3', 'F.Cu', (65.4, 94.3), (64.8, 93.7), (58.95, 93.7), 'C66.1', w=0.3)
# I2S: Rev E via positions at the codec pins; DIN/DOUT/BCLK straight up on B.Cu, FSYNC (whose order is
# swapped between the two ICs' pin rows) hops on In2 round the west side
for net, pin, vx in (('I2S_BCLK', '2', 60.85), ('I2S_FSYNC', '3', 60.15), ('I2S_DOUT', '4', 60.85),
                     ('I2S_DIN', '5', 60.15)):
    vy = P(f'U14.{pin}')[1]
    T(net, 'F.Cu', f'U14.{pin}', (vx, vy))
    V(net, vx, vy)
T('I2S_DIN', 'B.Cu', (60.15, 99.6), (60.15, 89.25))
T('I2S_DOUT', 'B.Cu', (59.6, 100.2), (59.6, 88.75), (60.85, 88.75))
T('I2S_BCLK', 'B.Cu', (59.1, 100.8), (59.1, 87.75), (60.85, 87.75))
V('I2S_FSYNC', 61.0, 101.4)
T('I2S_FSYNC', 'In2.Cu', (61.0, 101.4), (58.6, 101.4), (58.0, 100.8), (58.0, 88.85), (58.6, 88.25), (60.15, 88.25))
# I2C: both hop on In2 across the I2S lines; SCL to the Rev E via west of R73, SDA to the one east of R72
V('I2C_SDA', 67.4, 102.0)
T('I2C_SDA', 'In2.Cu', (67.4, 102.0), (67.4, 93.0), (66.275, 91.875), (65.2, 91.875))
V('I2C_SDA', 65.2, 91.875)
T('I2C_SDA', 'F.Cu', (64.25, 91.875), (65.2, 91.875))
V('I2C_SCL', 68.2, 102.6)
T('I2C_SCL', 'In2.Cu', (68.2, 102.6), (67.6, 103.2), (62.4, 103.2), (61.75, 102.55), (61.75, 91.875))
V('I2C_SCL', 61.75, 91.875)
T('I2C_SCL', 'F.Cu', (62.75, 91.875), (61.75, 91.875))

# ============================================================== 7. relay-driver gate lines (In2)
# Rev E escapes at U1; In2 diagonals to a via between each gate resistor's input land and the pull-down's
# GND land below it (y 111.5), crossing the codec bundle (B.Cu) and the 5 V tap (south of y 116.5).
T('RNG_SET_MED', 'F.Cu', 'U1.14', (79.6, 118.738))
V('RNG_SET_MED', 79.6, 118.738)
T('RNG_SET_MED', 'In2.Cu', (79.6, 118.738), (79.6, 116.633), (84.733, 111.5))
T('RNG_RESET', 'F.Cu', 'U1.13', (78.017, 121.3), (79.581, 119.735), (79.794, 119.735))
V('RNG_RESET', 79.794, 119.735)
T('RNG_RESET', 'In2.Cu', (79.794, 119.735), (86.0, 119.735), (90.1, 115.635), (90.1, 113.0), (91.6, 111.5),
  (92.09, 111.5))
T('RNG_SET_LO', 'F.Cu', 'U1.9', (76.8, 122.9), (76.6, 123.1))
V('RNG_SET_LO', 76.6, 123.1)            # inside U1's pin ring (Rev E)
T('RNG_SET_LO', 'In2.Cu', (76.6, 123.1), (79.25, 123.1), (79.55, 122.8), (88.4, 122.8), (97.0, 114.2),
  (97.0, 113.5), (99.0, 111.5), (99.733, 111.5))
T('RNG_SET_HI', 'F.Cu', 'U1.8', (79.75, 123.3))
V('RNG_SET_HI', 79.75, 123.3)
T('RNG_SET_HI', 'In2.Cu', (79.75, 123.3), (91.2, 123.3), (102.2, 112.3), (113.732, 112.3), (114.532, 111.5))
DROP('RNG_RESET', 91.5, 109.0, 92.6, 111.3)     # Rev E's R74 escape (via on the Rev F VRLY bus)
for net, r in (('RNG_SET_MED', 'R76'), ('RNG_RESET', 'R74'), ('RNG_SET_LO', 'R78'), ('RNG_SET_HI', 'R102')):
    x = P(f'{r}.1')[0]
    V(net, x, 111.5)
    T(net, 'F.Cu', (x, 111.5), f'{r}.1')
# K4 reference-relay gate: In2 north past the RP2040's crystal side, east along y 108.3 under the driver
# row's VRLY links, north along x 133.4 between the LDOs, to R108
T('RNG_SET_REF', 'F.Cu', 'U1.17', (75.8, 118.6))
V('RNG_SET_REF', 75.8, 118.6)
T('RNG_SET_REF', 'In2.Cu', (75.8, 118.6), (78.4, 118.6), (78.4, 108.3), (133.4, 108.3), (133.4, 77.0), (138.3, 77.0))
V('RNG_SET_REF', 138.3, 77.0)
T('RNG_SET_REF', 'F.Cu', (138.3, 77.0), 'R108.1')

# ============================================================== 8. U1 west / north pins: RUN, STATUS, MON, UART, SWD
# Six lines leave U1's west side on In2 (x 66.4-69.9, crossing the USB pair's B.Cu legs), run down to the
# south edge, east along y 142.6-144.35 and up to J6 (UART), the rail-monitor cluster, the LED and SW2.
# Order west->east = RUN, STATUS, MON12, MON_N12, UART_TX, UART_RX, so nothing crosses.
T('RUN', 'B.Cu', (70.6324, 119.2922), (66.4, 119.2922))
V('RUN', 66.4, 119.2922)
T('RUN', 'In2.Cu', (66.4, 119.2922), (66.4, 144.35), (97.6, 144.35), (97.6, 138.6))
V('RUN', 62.2, 131.5)                     # R9/C14 (pull-up and cap, core group) join from the west
T('RUN', 'F.Cu', (62.2, 131.5), 'R9.1')
T('RUN', 'In2.Cu', (62.2, 131.5), (66.4, 131.5))
V('RUN', 97.6, 138.6)
T('RUN', 'F.Cu', (97.6, 138.6), 'SW2.1')
T('STATUS', 'F.Cu', 'U1.37', (68.9, 124.1), (68.4, 123.6), (67.0, 123.6))
V('STATUS', 67.0, 123.6)
T('STATUS', 'In2.Cu', (67.0, 123.6), (67.0, 144.0), (96.0, 144.0), (96.0, 136.0))
V('STATUS', 96.0, 136.0)
T('STATUS', 'B.Cu', (96.0, 136.0), (98.7, 136.0), (99.3, 136.6))
V('STATUS', 99.3, 136.6)
T('STATUS', 'F.Cu', (99.3, 136.6), 'R12.1')
T('LED_A', 'F.Cu', 'R12.2', 'D4.2')
V('GND', 105.8, 136.0)
T('GND', 'F.Cu', 'D4.1', (105.8, 136.0))
T('MON12', 'F.Cu', 'U1.38', (68.3, 124.5))
V('MON12', 68.3, 124.5)
T('MON12', 'In2.Cu', (68.3, 124.5), (67.65, 125.15), (67.65, 143.65), (89.2, 143.65), (89.2, 128.3))
T('MON_N12', 'F.Cu', 'U1.39', (69.3, 124.9), (69.1, 125.1))
V('MON_N12', 69.1, 125.1)
T('MON_N12', 'In2.Cu', (69.1, 125.1), (68.25, 125.95), (68.25, 143.3), (88.4, 143.3), (88.4, 131.0))
T('UART_TX', 'F.Cu', 'U1.40', (70.0, 125.3), (69.6, 125.7), (69.6, 127.1), (69.45, 127.25), w=0.15)
V('UART_TX', 69.45, 127.25)
T('UART_TX', 'In2.Cu', (69.45, 127.25), (69.45, 142.95), (86.5, 142.95), 'J6.1', w=0.15)
T('UART_RX', 'F.Cu', 'U1.41', (70.0, 125.75), (69.9, 125.85), (69.9, 127.7), w=0.15)
V('UART_RX', 69.9, 127.7)
T('UART_RX', 'In2.Cu', (69.9, 127.7), (69.9, 142.6), (83.96, 142.6), 'J6.2', w=0.15)
# rail monitors: each divider + filter shares one F.Cu bar on its MON land column
T('MON12', 'F.Cu', 'R97.1', 'R98.2', 'C110.2')
V('MON12', 89.2, 128.3)
T('MON12', 'F.Cu', (89.2, 128.3), (90.225, 127.275), 'C110.2')
T('MON_N12', 'F.Cu', 'R100.1', 'R99.2', 'C111.2')
V('MON_N12', 88.4, 131.0)                  # B.Cu hop under the MON12 In2 line to the east column
T('MON_N12', 'B.Cu', (88.4, 131.0), (98.0, 131.0), (98.0, 127.3))
V('MON_N12', 98.0, 127.3)
T('MON_N12', 'F.Cu', (98.0, 127.3), (94.225, 127.3), 'C111.2')
# 12V from the B.Cu 12V trunk (south of the -12V one) straight down x 86.5; -12V from the LDO via down
# x 135.2 and west along y 119.4; both land on a via above their divider resistor
T('12V', 'B.Cu', (86.5, 82.5), (86.5, 121.95), (91.825, 121.95))
V('12V', 91.825, 121.95)
T('12V', 'F.Cu', (91.825, 121.95), 'R97.2')
T('-12V', 'B.Cu', (136.2, 98.1), (135.2, 99.1), (135.2, 119.4), (95.825, 119.4), (95.825, 121.95))
V('-12V', 95.825, 121.95)
T('-12V', 'F.Cu', (95.825, 121.95), 'R100.2')
# 3V3: branch of the codec-bus 3V3 line (B.Cu, y 129.4) through J5's 3V3 land to R99
T('3V3', 'B.Cu', (84.6, 129.4), (97.3, 129.4), (97.3, 124.6), w=0.3)
V('3V3', 97.3, 124.6)
T('3V3', 'F.Cu', (97.3, 124.6), 'R99.1')
for x, y in ((93.0, 124.6), (93.0, 126.2)):
    V('GND', x, y)
T('GND', 'F.Cu', 'R98.1', (93.0, 124.6))
T('GND', 'F.Cu', 'C110.1', (93.0, 126.2))
V('GND', 96.6, 125.4)
T('GND', 'F.Cu', 'C111.1', (96.6, 125.4))
# buttons
T('BOOTSEL', 'F.Cu', 'R8.2', (69.4, 144.075), (69.475, 144.2), (82.4, 144.2), (82.975, 143.625), 'SW1.1')
V('GND', 87.4, 141.6)
T('GND', 'F.Cu', 'SW1.2', (87.4, 141.6))
V('GND', 90.775, 140.4)
T('GND', 'F.Cu', 'SW2.2', (90.775, 140.4))
# SWD to J4 (DNP) north-west of U1: SWCLK from its Rev E via, SWDIO from its Rev E via, both In2
DROP('SWCLK', 70.6, 118.0, 70.9, 118.3)
T('SWCLK', 'In2.Cu', (70.7332, 117.9811), (69.0, 116.2479), 'J4.1')
T('SWDIO', 'F.Cu', 'U1.25', (72.6, 120.557), (71.557, 121.6))
V('SWDIO', 71.557, 121.6)
T('SWDIO', 'In2.Cu', (71.557, 121.6), (68.6, 121.6), (68.0, 121.0), (68.0, 110.5), (66.46, 108.96), 'J4.2')

# ============================================================== 9. switcher <-> LDO links, U13 EN, K4 gate
# RAW_P: R95 (LDO group) straight down F.Cu x 128.775 into C90's RAW_P land
T('RAW_P', 'F.Cu', 'R95.1', (128.775, 127.975), 'C90.1', w=0.3)
# RAW_N: Rev E route out of U13 pin 15 (F stub, via, B.Cu north, via, F.Cu into the C91/C92 bar), then
# on north along x 142.5 to R96 under U12; R96 -> U12 LDOIN_N
T('RAW_N', 'F.Cu', 'U13.15', (137.75, 132.6017), (139.0369, 131.3148), (139.0369, 130.293))
V('RAW_N', 139.0369, 130.293)
T('RAW_N', 'B.Cu', (139.0369, 130.293), (139.9289, 129.401), (139.9289, 117.0585))
V('RAW_N', 139.9289, 117.0585)
T('RAW_N', 'F.Cu', (139.9289, 117.0585), (142.5, 119.6296), (142.5, 123.475), w=0.3)
T('RAW_N', 'F.Cu', (142.5, 119.6296), 'R96.1', w=0.3)
T('LDOIN_N', 'F.Cu', 'R96.2', (142.5, 104.1), (145.15, 101.45), 'U12.5', w=0.3)
# 3V3 to U13's enable pins: B.Cu hop east of the 5 V tap, In2 along y 123.9 and down x 141.2 beside D3,
# via, F.Cu into U13's 3V3 ring (Rev E ring, east side)
T('3V3', 'B.Cu', (97.3, 124.6), (99.5, 124.6))
V('3V3', 99.5, 124.6)
T('3V3', 'In2.Cu', (99.5, 124.6), (100.2, 123.9), (141.2, 123.9), (141.2, 136.4))
V('3V3', 141.2, 136.4)
T('3V3', 'F.Cu', (141.2, 136.4), (140.5497, 135.7497), (140.1642, 135.7048))
V('GND', 148.35, 125.4)
T('GND', 'F.Cu', 'L2.2', (148.35, 125.4), w=0.5)
# K4 reference gate: R108 -> Q6 gate, R109 pull-down, GND vias
T('RNG_SET_REF_G', 'F.Cu', 'R108.2', 'Q6.1')
T('RNG_SET_REF_G', 'F.Cu', 'R109.1', 'R108.2')
V('GND', 138.4, 79.4)
T('GND', 'F.Cu', 'R109.2', (138.4, 79.4))
V('GND', 142.6, 79.9)
T('GND', 'F.Cu', 'Q6.2', (142.6, 79.9))
